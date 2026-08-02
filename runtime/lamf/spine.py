"""LAMF Witness Spine — append-only hash-chained event log (DECISIONS.md §G).

On-disk layout mirrors the spool format (03_CONTRACTS/spool-format.md §2):
`<events_dir>/segment-NNNNNN.jsonl`, one LAMF-CANON-1 event per line, segment
rotation at 64 MiB, files 0600. The chain fields are finalized at append:

    seq        = previous seq + 1 (strictly monotonic; seq is the ordering
                 authority, ts advisory)
    prev_hash  = hash of the event at seq-1 (genesis = 64 ASCII zeros)
    hash       = sha256_hex(canonicalize(event minus hash/sig))
    sig        = base64url(Ed25519_sign(key, bytes.fromhex(hash)))

Signing: V-03 key custody means signing keys are server-held; U-07 pins the
well-known `lamf-system` actor's events to the instance key. The reference
runtime signs every event with the InstanceKey it is constructed with (the
server-held key); per-actor keypairs from the pairing ceremony are an
api-layer concern built on top of this module.

Pinned interface (runtime/README.md):
    class Spine(events_dir)
        .append(event: dict) -> tuple[int, str]
        .verify_tail(n=1000) -> bool
        .verify_deep() -> bool
        .head() -> tuple[int, str]
"""

from __future__ import annotations

import base64
import contextlib
import os
import time
import uuid
from pathlib import Path
from typing import Iterator, Optional, Tuple

from . import canon

SEGMENT_MAX_BYTES = 64 * 1024 * 1024     # spool-format.md §2 rotation bound
EVENT_LINE_MAX_BYTES = 64 * 1024         # single canonical line incl. \n (§2)
GENESIS_PREV_HASH = "0" * 64             # canonical-hashing.md §6.3
_SEGMENT_NAME = "segment-%06d.jsonl"


def now_ms() -> int:
    """Current unix time in milliseconds (event ts; advisory only)."""
    return int(time.time() * 1000)


def uuid7() -> str:
    """UUIDv7 (event ids, per event.schema.json pattern).

    Python 3.10 has no uuid7; construct per RFC 9562 §5.7:
    48-bit unix ms, ver=7, 12-bit rand_a, var=10, 62-bit rand_b.
    """
    ms = now_ms() & 0xFFFFFFFFFFFF
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = (rand >> 62) & 0xFFF
    rand_b = rand & 0x3FFFFFFFFFFFFFFF
    val = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0x2 << 62) | rand_b
    return str(uuid.UUID(int=val))


class SpineError(Exception):
    """Chain integrity or append failure."""


class Spine:
    """Append-only Witness Spine over JSONL segments.

    Parameters:
        events_dir: directory holding the segment files (created if missing).
        instance_key: optional crypto.InstanceKey used to sign appended events
            and to verify signatures. Without it, append() raises and
            verify_* check the hash chain only (signature checks skipped).
    """

    def __init__(self, events_dir, instance_key=None):
        self.dir = Path(events_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.key = instance_key
        self.last_verify_count = 0
        self._head_seq, self._head_hash = self._scan_head()

    # -- segment plumbing ---------------------------------------------------
    def _segments(self) -> list:
        segs = sorted(self.dir.glob("segment-*.jsonl"))
        return segs

    def _scan_head(self) -> Tuple[int, str]:
        segs = self._segments()
        if not segs:
            return 0, GENESIS_PREV_HASH
        last_line = next(self._reverse_lines(segs[-1]), None)
        if last_line is None:
            return 0, GENESIS_PREV_HASH
        ev = canon.parse_json(last_line.decode("utf-8"))
        return int(ev["seq"]), ev["hash"]

    @staticmethod
    def _reverse_lines(path: Path, block_size: int = 64 * 1024):
        """Yield non-empty lines newest-first without scanning the file.

        Segment files may be 64 MiB. Routine startup and tail verification
        must touch only the requested tail, not every event in the segment.
        """
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            carry = b""
            while pos > 0:
                take = min(block_size, pos)
                pos -= take
                f.seek(pos)
                chunk = f.read(take) + carry
                parts = chunk.split(b"\n")
                carry = parts[0]
                for line in reversed(parts[1:]):
                    if line.strip():
                        yield line.strip()
            if carry.strip():
                yield carry.strip()

    def tail_events(self, n: int = 1000) -> list:
        """Return at most ``n`` finalized events in ascending chain order."""
        if n <= 0:
            return []
        newest = []
        for seg in reversed(self._segments()):
            for line in self._reverse_lines(seg):
                newest.append(canon.parse_json(line.decode("utf-8")))
                if len(newest) >= n:
                    return list(reversed(newest))
        return list(reversed(newest))

    def _active_segment(self) -> Path:
        segs = self._segments()
        if not segs:
            return self.dir / (_SEGMENT_NAME % 1)
        return segs[-1]

    def _open_append(self, path: Path):
        new = not path.exists()
        f = open(path, "ab")
        if new:
            os.chmod(path, 0o600)
        return f

    @contextlib.contextmanager
    def _append_lock(self):
        """Serialize spine writers across processes on the same machine."""
        # v2 avoids legacy Windows ACL/share flags left by older runtimes.
        lock_path = self.dir / "append-v2.lock"
        # On Windows, opening an already locked file through Path.touch can
        # fail before msvcrt gets a chance to wait for the byte-range lock.
        if not lock_path.exists():
            lock_path.touch()
        with open(lock_path, "r+b") as lock_file:
            if os.name == "nt":
                import msvcrt
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    # -- append ---------------------------------------------------------------
    def append(self, event: dict) -> Tuple[int, str]:
        """Finalize chain fields and append `event`. PINNED SIGNATURE.

        Two accepted forms:
          * DEFERRED (the capture/spool form, spool-format.md §2 — no
            seq/prev_hash/hash/sig): chain fields are assigned and the event
            is signed with this Spine's InstanceKey, finalized IN PLACE on
            the passed dict so the ingester can mirror the exact finalized
            event into SQLite.
          * FINALIZED (import/restore replay, §M): all four chain fields
            present. The event is validated (seq == head+1, prev_hash ==
            current head, hash recomputes) and appended AS-IS, preserving
            the original hashes and the source instance's signature (U-13d
            anchors trust on the manifest-pinned pubkey, not this key).
        A partially-chained event (some but not all chain fields) is
        rejected. Returns (seq, hash).
        """
        with self._append_lock():
            # Another server/CLI process may have appended since this Spine
            # object was constructed. Refresh under the process lock before
            # assigning the next sequence number.
            self._head_seq, self._head_hash = self._scan_head()
            chain_fields = {"seq", "prev_hash", "hash", "sig"}
            present = chain_fields & event.keys()
            if present and present != chain_fields:
                raise SpineError(
                    f"partially-chained event rejected: {sorted(present)}")
            if present:
                return self._append_finalized(event)
            if self.key is None:
                raise SpineError(
                    "Spine.append requires an InstanceKey "
                    "(signing is server-side, V-03)")

            seq = self._head_seq + 1
            ev = event  # finalized in place (see docstring)
            ev["seq"] = seq
            ev["prev_hash"] = self._head_hash
            h = canon.event_hash(ev)
            raw_sig = self.key.sign(bytes.fromhex(h))
            ev["hash"] = h
            ev["sig"] = base64.urlsafe_b64encode(raw_sig).decode("ascii")

            self._write_line(ev)
            self._head_seq, self._head_hash = seq, h
            return seq, h

    def _append_finalized(self, ev: dict) -> Tuple[int, str]:
        """Validated replay of an already-chained event (import/restore, §M).
        Hash and chain continuity are verified; the foreign signature is
        preserved unverified (trust anchors on the manifest-pinned source
        pubkey per U-13d, confirmed out-of-band at import)."""
        if ev["seq"] != self._head_seq + 1:
            raise SpineError(
                f"finalized replay out of order: seq {ev['seq']}, head is {self._head_seq}")
        if ev["prev_hash"] != self._head_hash:
            raise SpineError(f"finalized replay prev_hash mismatch at seq {ev['seq']}")
        if canon.event_hash(ev) != ev["hash"]:
            raise SpineError(f"finalized replay hash mismatch at seq {ev['seq']}")
        try:
            raw_sig = base64.urlsafe_b64decode(ev["sig"])
        except Exception as e:
            raise SpineError(f"sig not base64url at seq {ev['seq']}") from e
        if len(raw_sig) != 64:
            raise SpineError(f"sig not 64 bytes at seq {ev['seq']}")
        self._write_line(ev)
        self._head_seq, self._head_hash = ev["seq"], ev["hash"]
        return ev["seq"], ev["hash"]

    def _write_line(self, ev: dict) -> None:
        line = (canon.canonicalize(ev) + "\n").encode("utf-8")
        if len(line) > EVENT_LINE_MAX_BYTES:
            raise SpineError(
                f"canonical event line {len(line)} B exceeds 64 KiB bound; "
                "payload must go to payload_store by reference (§F.3/U-04)")

        path = self._active_segment()
        if path.exists() and path.stat().st_size + len(line) > SEGMENT_MAX_BYTES:
            # rotate: fsync sealed segment + directory, open next number
            with open(path, "ab") as f:
                f.flush()
                os.fsync(f.fileno())
            num = int(path.stem.split("-")[1]) + 1
            path = self.dir / (_SEGMENT_NAME % num)
            dir_fd = os.open(str(self.dir), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

        with self._open_append(path) as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())  # durability.fsync default "per-append" (V-04)

    # -- reads ------------------------------------------------------------------
    def iter_events(self) -> Iterator[dict]:
        """Yield every event in chain order (segment number, then offset)."""
        for seg in self._segments():
            with open(seg, "rb") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        yield canon.parse_json(line.decode("utf-8"))

    def head(self) -> Tuple[int, str]:
        """(seq, hash) of the chain head; (0, 64 zeros) when empty. PINNED."""
        return self._head_seq, self._head_hash

    # -- verification -------------------------------------------------------------
    def _verify_event(self, ev: dict, expect_seq: int, expect_prev: str):
        """Returns (error_str|None, sig_status) with sig_status in
        'ok' | 'bad' | 'unchecked'. Chain/hash errors are absolute; signature
        outcomes are aggregated by the caller (see verify_deep policy)."""
        if ev.get("seq") != expect_seq:
            return (f"seq gap at {ev.get('id')}: want {expect_seq}, got {ev.get('seq')}",
                    "unchecked")
        if ev.get("prev_hash") != expect_prev:
            return f"prev_hash mismatch at seq {expect_seq}", "unchecked"
        if canon.event_hash(ev) != ev.get("hash"):
            return f"hash mismatch at seq {expect_seq}", "unchecked"
        if self.key is None:
            return None, "unchecked"
        try:
            sig = base64.urlsafe_b64decode(ev["sig"])
        except Exception:
            return f"sig not base64url at seq {expect_seq}", "bad"
        if len(sig) != 64:
            return f"sig not 64 bytes at seq {expect_seq}", "bad"
        return None, ("ok" if self.key.verify(bytes.fromhex(ev["hash"]), sig) else "bad")

    @staticmethod
    def _sig_policy_ok(statuses: list) -> bool:
        """Signature policy over the per-event statuses ('ok'/'bad'/'unchecked'):
        the legitimate shapes are
          * all 'ok'            — a purely local chain;
          * all 'bad'           — a wholly foreign-restored chain (§M import;
                                  its sigs anchor on the manifest-pinned source
                                  pubkey, U-13d — hash integrity was checked);
          * 'bad'* then 'ok'*   — a restored base continued locally (V-01:
                                  the local instance appends its own events
                                  on top of an imported chain).
        Any 'bad' AFTER the first locally-verified event is a splice
        (T-chain-splice-rejected) => False.
        """
        first_ok = next((i for i, s in enumerate(statuses) if s == "ok"), None)
        if first_ok is None:
            return True  # no local sigs: hash-chain-only assessment
        return "bad" not in statuses[first_ok:]

    def verify_tail(self, n: int = 1000) -> bool:
        """Verify the bounded tail: the last `n` events re-hash and re-sign
        correctly and chain to each other (§H routine startup check). PINNED.

        The first tail event's prev_hash is trusted as the anchor (checking it
        against seq-1 is what --deep is for), matching the checkpoint+bounded-
        tail startup semantics.
        """
        tail = self.tail_events(n)
        self.last_verify_count = len(tail)
        prev = tail[0].get("prev_hash") if tail else GENESIS_PREV_HASH
        statuses = []
        for ev in tail:
            err, sig_status = self._verify_event(ev, ev.get("seq", -1), prev)
            if err:
                return False
            statuses.append(sig_status)
            prev = ev["hash"]
        if tail and (tail[-1]["seq"], tail[-1]["hash"]) != self.head():
            return False
        return self._sig_policy_ok(statuses)

    def verify_deep(self) -> bool:
        """Full-chain verification from genesis: seq strictly monotonic from
        1, genesis prev_hash = 64 zeros, every hash recomputed, every signature
        valid (when a key is loaded). PINNED."""
        expect_seq = 1
        prev = GENESIS_PREV_HASH
        count = 0
        statuses = []
        for ev in self.iter_events():
            err, sig_status = self._verify_event(ev, expect_seq, prev)
            if err:
                return False
            statuses.append(sig_status)
            prev = ev["hash"]
            expect_seq += 1
            count += 1
        head_ok = (expect_seq - 1, prev) == self.head() if count \
            else self.head() == (0, GENESIS_PREV_HASH)
        return head_ok and self._sig_policy_ok(statuses)
