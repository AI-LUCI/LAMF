"""LAMF spool + ingester — the capture pipeline after sanitize (DECISIONS §F).

Pipeline (normative order): hook -> sanitize -> [payload spill] -> spool ->
ack -> async ingestion. This module owns the second half:

  * spool_append: deferred-form spool lines (spool-format.md §2 — ONE
    representation, U-04): canonical event minus seq/prev_hash/hash/sig, one
    LAMF-CANON-1 line per event, segment rotation at 64 MiB, fsync per-append
    (V-04 default), files 0600.
  * capture_event: the full synchronous capture path — sanitize (fail-closed;
    a SecretBlocked propagates and the caller emits capture_dropped), payload
    spill to payload_store BEFORE spool append when canonical payload > 4 KiB
    or sensitivity != 'ordinary' (U-04/U-08b; blob > 1 MiB => CaptureDropped),
    then spool append + ack.
  * Ingester.drain_once: replay un-ingested spool lines in order (segment
    number, then offset), idempotency key (id, payload_sha256)
    (spool-format.md §6): duplicates skip; same id + different payload hash
    is an integrity anomaly => quarantine + quarantine spine event. Each
    accepted event is finalized by Spine.append (seq/prev_hash/hash + sig
    with the server-held key, V-03/U-07) and mirrored into SQLite; the
    ingester high-water mark moves transactionally (U-17). Fully drained
    segments are retired (deleted).

Pinned interface (runtime/README.md):
    class Ingester(spool_dir, spine, store, policy, instance_key, on_event=None)
        .drain_once() -> int
        .run_forever(interval=0.5)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from . import canon
from .sanitize import sanitize, SecretBlocked
from .spine import Spine, now_ms, uuid7

SEGMENT_MAX_BYTES = 64 * 1024 * 1024      # spool-format.md §2
EVENT_LINE_MAX_BYTES = 64 * 1024          # §2 max canonical line incl. \n
INLINE_PAYLOAD_MAX_BYTES = 4 * 1024       # §G inline payload bound
SPILL_BLOB_MAX_BYTES = 1024 * 1024        # U-04: larger => capture_dropped
_SEGMENT_NAME = "segment-%06d.jsonl"


class CaptureDropped(Exception):
    """Fail-closed capture drop; the caller emits a capture_dropped event."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"capture_dropped: {reason}")


def _segments(spool_dir: Path) -> list:
    return sorted(spool_dir.glob("segment-*.jsonl"))


def spool_append(spool_dir, event: Dict[str, Any]) -> Path:
    """Append one DEFERRED event line to the active spool segment.

    Enforces the 64 KiB canonical line bound (§2 — violating events must
    carry payload_ref instead). Returns the segment path written.
    """
    spool_dir = Path(spool_dir)
    spool_dir.mkdir(parents=True, exist_ok=True)
    for forbidden in ("seq", "prev_hash", "hash", "sig"):
        if forbidden in event:
            raise ValueError(f"spool lines omit {forbidden!r} (deferred form, U-04)")
    line = (canon.canonicalize(event) + "\n").encode("utf-8")
    if len(line) > EVENT_LINE_MAX_BYTES:
        raise CaptureDropped(
            f"canonical event line {len(line)} B exceeds the 64 KiB spool bound "
            "and no payload_ref was used (spool-format.md §2)")

    segs = _segments(spool_dir)
    path = segs[-1] if segs else spool_dir / (_SEGMENT_NAME % 1)
    if path.exists() and path.stat().st_size + len(line) > SEGMENT_MAX_BYTES:
        with open(path, "ab") as f:  # fsync sealed segment + directory (§4)
            f.flush()
            os.fsync(f.fileno())
        num = int(path.stem.split("-")[1]) + 1
        path = spool_dir / (_SEGMENT_NAME % num)
        dfd = os.open(str(spool_dir), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    new = not path.exists()
    with open(path, "ab") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())  # durability.fsync default "per-append" (§4/V-04)
    if new:
        os.chmod(path, 0o600)
    return path


def capture_event(spool_dir, store, event: Dict[str, Any], policy,
                  registered_values=None) -> Dict[str, Any]:
    """Synchronous capture path: sanitize -> spill -> spool -> ack.

    `event` carries the §G fields known at capture (actor, session, type,
    scope, sensitivity, taint, payload [object|null], optional channel).
    Returns the ack: the deferred event as spooled (with id, ts,
    payload_sha256, and payload_ref when spilled).

    Fail-closed: sanitize.SecretBlocked and CaptureDropped propagate — the
    caller drops the event and emits a `capture_dropped` gap event
    (SECRET_PATTERNS.md §1). An ack means: sanitized, spilled, crash-durable
    in the spool (spool-format.md §3) — NOT ingested or indexed.
    """
    ev = dict(event)
    ev.setdefault("id", uuid7())
    ev.setdefault("ts", now_ms())
    ev.setdefault("session", None)
    sensitivity = ev.get("sensitivity", "ordinary")

    payload = ev.get("payload")
    if payload is not None:
        # Sanitize text-bearing fields: message bodies at the 32 KiB bound,
        # tool-result excerpts at 8 KiB (SECRET_PATTERNS.md §4). Detectors
        # always run on the full pre-truncation text inside sanitize().
        if isinstance(payload, dict):
            payload = dict(payload)
            notes = []
            if isinstance(payload.get("text"), str):
                r = sanitize(payload["text"], policy, sensitivity,
                             registered_values=registered_values)
                payload["text"] = r.text
                notes += r.notes
            if isinstance(payload.get("excerpt"), str):
                r = sanitize(payload["excerpt"], policy, sensitivity,
                             registered_values=registered_values, excerpt=True)
                payload["excerpt"] = r.text
                notes += r.notes
            if notes:
                ev["sanitizer_note"] = "; ".join(notes)[:1024]
        ev["payload"] = payload

    ev["payload_sha256"] = canon.payload_sha256(payload)

    # Payload spill (U-04/U-08b): BEFORE spool append. Oversized (>4 KiB
    # canonical) OR any non-ordinary sensitivity goes to payload_store.
    if payload is not None:
        blob = canon.canonical_bytes(payload)
        must_spill = sensitivity != "ordinary" or len(blob) > INLINE_PAYLOAD_MAX_BYTES
        if must_spill:
            if len(blob) > SPILL_BLOB_MAX_BYTES:
                raise CaptureDropped(
                    f"payload {len(blob)} B exceeds the 1 MiB spill bound (U-04)")
            ref = store.put_payload(blob, owner_id=ev["id"])
            del ev["payload"]
            ev["payload_ref"] = ref

    spool_append(spool_dir, ev)
    return ev


class Ingester:
    """Async ingestion: spool replay -> chain finalize -> SQLite index.

    Parameters (PINNED): spool_dir, spine (Spine), store (Store), policy
    (Policy), instance_key, on_event (optional callback invoked with the
    finalized event dict after it is indexed — the projection hook, W-02).
    """

    def __init__(self, spool_dir, spine: Spine, store, policy,
                 instance_key=None, on_event: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.spool_dir = Path(spool_dir)
        self.spine = spine
        self.store = store
        self.policy = policy
        self.key = instance_key
        self.on_event = on_event

    # -- quarantine ------------------------------------------------------------
    def _quarantine(self, reason: str, source_event_id: Optional[str],
                    raw_line: Optional[bytes], scope: str = "system") -> None:
        """Quarantine a violating/anomalous spool line and emit a quarantine
        spine event (spool-format.md §6; never silently overwrite)."""
        qid = "qu_" + uuid7().replace("-", "")
        payload_ref = None
        if raw_line is not None:
            payload_ref = self.store.put_payload(raw_line[:SPILL_BLOB_MAX_BYTES],
                                                 owner_id=qid)
        ttl_days = 30
        if self.policy is not None:
            ttl_days = int(self.policy.get("quarantine", "ttl_days", default=30))
        now = now_ms()
        with self.store.conn:
            self.store.conn.execute(
                "INSERT INTO quarantine (id, source_event_id, reason, state, scope,"
                " sensitivity, taint, payload_ref, created_at, expires_at)"
                " VALUES (?,?,?,'quarantined',?,?,?,?,?,?)",
                (qid, source_event_id, reason, scope, "ordinary", "system",
                 payload_ref, now, now + ttl_days * 86400_000))
        qevent = {
            "id": uuid7(), "ts": now, "actor": "lamf-system", "session": None,
            "type": "quarantine", "scope": scope, "sensitivity": "ordinary",
            "taint": "system",
            "payload": {"reason": reason, "quarantine_id": qid,
                        "source_event_id": source_event_id},
        }
        qevent["payload_sha256"] = canon.payload_sha256(qevent["payload"])
        self.spine.append(qevent)
        self.store.insert_event(qevent)

    # -- drain -------------------------------------------------------------------
    def _ingest_line(self, line: bytes) -> str:
        """Process one spool line. Returns 'ingested' | 'duplicate' |
        'quarantined'."""
        try:
            ev = canon.parse_json(line.decode("utf-8"))
        except Exception:
            self._quarantine("malformed_spool_line", None, line)
            return "quarantined"

        ev_id = ev.get("id")
        psha = ev.get("payload_sha256")
        if not ev_id or not psha:
            self._quarantine("missing_id_or_payload_sha256", ev_id, line)
            return "quarantined"

        # Replay idempotency (§6): dedup key = (id, payload_sha256)
        existing = self.store.event_exists(ev_id)
        if existing is not None:
            if existing == psha:
                return "duplicate"
            self._quarantine("replay_anomaly_id_payload_mismatch", ev_id, line)
            return "quarantined"

        # Belt-and-braces enforcement of U-08b: non-ordinary events never go
        # on-chain with an inline payload; spill now if capture did not.
        sensitivity = ev.get("sensitivity", "ordinary")
        if "payload" in ev and ev.get("payload_ref") is None \
                and sensitivity != "ordinary":
            blob = canon.canonical_bytes(ev["payload"])
            if len(blob) > SPILL_BLOB_MAX_BYTES:
                self._quarantine("payload_exceeds_spill_bound", ev_id, line)
                return "quarantined"
            ref = self.store.put_payload(blob, owner_id=ev_id)
            del ev["payload"]
            ev["payload_ref"] = ref

        # Finalize chain fields + sign with the server-held key (V-03), then
        # mirror into SQLite. The actor must exist (events FK); lamf-system
        # and the bootstrap operator are seeded at init.
        if not self.store.actor_exists(ev.get("actor", "")):
            self._quarantine("unknown_actor", ev_id, line)
            return "quarantined"
        self.spine.append(ev)          # assigns seq/prev_hash/hash/sig in place
        self.store.insert_event(ev)
        if self.on_event is not None:
            self.on_event(ev)
        return "ingested"

    def drain_once(self) -> int:
        """Replay all un-ingested spool lines once. PINNED SIGNATURE.
        Returns the number of newly ingested events (duplicates and
        quarantined lines are not counted). Fully drained segments are
        retired (spool-format.md §7)."""
        ingested = 0
        for seg in _segments(self.spool_dir):
            with open(seg, "rb") as f:
                lines = [ln for ln in f if ln.strip()]
            fully_drained = True
            for line in lines:
                try:
                    result = self._ingest_line(line)
                except Exception:
                    # Any failure keeps the segment for the next replay;
                    # idempotency makes reprocessing safe (§6).
                    fully_drained = False
                    break
                if result == "ingested":
                    ingested += 1
            if fully_drained:
                seg.unlink()
        return ingested

    def run_forever(self, interval: float = 0.5) -> None:
        """Drain loop. PINNED SIGNATURE. Individual drain failures are
        logged to stderr and retried on the next tick — the ingester never
        dies on a single bad segment."""
        import sys
        while True:
            try:
                self.drain_once()
            except Exception as e:  # pragma: no cover - defensive loop
                print(f"[ingester] drain error: {e}", file=sys.stderr)
            time.sleep(interval)
