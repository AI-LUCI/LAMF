"""LAMF reference runtime — portable export/import bundles (DECISIONS.md §M).

Bundle = tar.gz containing ``manifest.json`` (per
03_CONTRACTS/schemas/export-manifest.schema.json), ``events/events.jsonl``
(finalized spine events), ``records/records.jsonl`` (plaintext snapshot),
``policy.yaml`` and ``checkpoint.json`` (latest signed chain head), encrypted
with ``crypto.export_encrypt(passphrase, blob)``.

The manifest ``mac`` field is HMAC-SHA-256 over the manifest-without-mac plus
the file checksum list, keyed by an HKDF-SHA-256 derivative (info
"lamf-manifest-mac") of the export passphrase material — verified after
decrypt, before any extraction (U-13b).

Import: decrypt → verify MAC/checksums → safe path validation (floor F4
allowlist ``^[a-z0-9_./-]+$``, no ``..``, no absolute, no device names) →
restore spine + records → ``verify_deep`` → indexes rebuilt by re-upserting
records (foreign indexes are never trusted, §M.3). Import targets an EMPTY
destination directory unless ``force=True`` (the CLI's --force-reimport).
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import io
import json
import os
import re
import tarfile
import time
from pathlib import Path

try:  # pragma: no cover - import shim
    from . import canon as _canon
except Exception:  # noqa: BLE001
    try:
        import canon as _canon  # type: ignore
    except Exception:  # noqa: BLE001
        _canon = None

try:
    from . import crypto as _crypto
except Exception:  # noqa: BLE001
    try:
        import crypto as _crypto  # type: ignore
    except Exception:  # noqa: BLE001
        _crypto = None

try:
    import yaml
except Exception:  # noqa: BLE001
    yaml = None

LAMF_VERSION = "2.0.0"
FORMAT_VERSION = 1
SAFE_PATH = re.compile(r"^(?!/)(?!.*\.\.)[a-z0-9_./-]+$")
DEVICE_NAMES = {"con", "nul", "aux", "prn"} | {f"com{i}" for i in range(1, 10)} \
    | {f"lpt{i}" for i in range(1, 10)}
MAX_ENTRIES = 10000
MAX_BYTES = 4 * 1024 ** 3

SCHEMA_VERSIONS = {"event": "2.0.0", "memory_record": "2.0.0",
                   "export_manifest": "2.0.0", "security_policy": "2.0.0",
                   "sqlite_schema": 1}
EXCLUDES = ["quarantine", "vector_cache", "indexes", "secrets",
            "foreign_index_dbs", "receipts", "spool", "instance_key_material"]


class ExportError(RuntimeError):
    pass


class ImportError_(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _canonical(obj) -> str:
    if _canon is not None and hasattr(_canon, "canonicalize"):
        return _canon.canonicalize(obj)
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _hkdf_sha256(ikm: bytes, info: bytes, length: int = 32,
                 salt: bytes = b"lamf-export") -> bytes:
    """RFC 5869 HKDF (extract+expand) with SHA-256, stdlib only."""
    prk = _hmac.new(salt, ikm, hashlib.sha256).digest()
    okm, t, counter = b"", b"", 1
    while len(okm) < length:
        t = _hmac.new(prk, t + info + bytes([counter]),
                      hashlib.sha256).digest()
        okm += t
        counter += 1
    return okm[:length]


def _mac_key(passphrase: str) -> bytes:
    ikm = hashlib.sha256(passphrase.encode("utf-8")).digest()
    return _hkdf_sha256(ikm, b"lamf-manifest-mac")


def _compute_mac(passphrase: str, manifest_without_mac: dict,
                 files: list) -> str:
    msg = (_canonical(manifest_without_mac)
           + _canonical(files)).encode("utf-8")
    return _hmac.new(_mac_key(passphrase), msg, hashlib.sha256).hexdigest()


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _data_dir(ctx, data_dir) -> Path:
    d = data_dir or getattr(ctx, "data_dir", None) \
        or os.environ.get("LAMF_DATA_DIR")
    if not d:
        raise ExportError("export: data_dir (ctx/env/arg) is required")
    return Path(d)


def _store_db_path(ctx, data_dir: Path):
    store = getattr(ctx, "store", None)
    for attr in ("db_path", "path", "db_file", "database"):
        p = getattr(store, attr, None) if store is not None else None
        if p and Path(p).exists():
            return Path(p)
    for cand in sorted(data_dir.rglob("*.sqlite3")) + \
            sorted(data_dir.rglob("*.db")):
        return cand
    return None


def _read_events(ctx, data_dir: Path) -> list:
    """Finalized spine events (all §G fields) — the SPINE is the authority.

    Preferred source: the spine's own segment files (every spine.append
    lands there; the SQLite events table is only an ingester-maintained
    index and misses direct appends). Fallback: the events table."""
    spine = getattr(ctx, "spine", None)
    events_dir = getattr(spine, "dir", None) or getattr(
        spine, "events_dir", None)
    if events_dir is None:
        for cand in (data_dir / "spine", data_dir / "events"):
            if cand.exists():
                events_dir = cand
                break
    if events_dir is not None:
        segs = sorted(Path(events_dir).glob("segment-*.jsonl"))
        events = []
        for seg in segs:
            for ln in seg.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if ln:
                    try:
                        events.append(json.loads(ln))
                    except json.JSONDecodeError:
                        continue
        if events:
            events.sort(key=lambda e: e.get("seq", 0))
            return events
    return _read_events_from_table(ctx, data_dir)


def _read_events_from_table(ctx, data_dir: Path) -> list:
    """Finalized spine events from the store database (fallback)."""
    import sqlite3
    db = _store_db_path(ctx, data_dir)
    if db is None:
        return []
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
        if not cols:
            return []
        fields = [c for c in ("id", "seq", "ts", "actor", "session", "type",
                              "scope", "sensitivity", "taint", "payload_json",
                              "payload_ref", "payload_sha256", "prev_hash",
                              "hash", "sig", "channel_json", "sanitizer_note",
                              "capture_sig") if c in cols]
        rows = conn.execute(
            f"SELECT {', '.join(fields)} FROM events ORDER BY seq").fetchall()
        events = []
        for row in rows:
            d = dict(zip(fields, row))
            ev = {}
            for k, v in d.items():
                if k == "payload_json":
                    if v is not None:
                        try:
                            ev["payload"] = json.loads(v)
                        except Exception:  # noqa: BLE001
                            ev["payload"] = v
                elif k == "channel_json":
                    if v:
                        try:
                            ev["channel"] = json.loads(v)
                        except Exception:  # noqa: BLE001
                            pass
                elif v is not None:
                    ev[k] = v
            events.append(ev)
        return events
    finally:
        conn.close()


def _read_records(ctx, data_dir: Path) -> list:
    """Plaintext record snapshot via the authority (store.get_record)."""
    import sqlite3
    db = _store_db_path(ctx, data_dir)
    store = getattr(ctx, "store", None)
    records = []
    ids: list = []
    if db is not None:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT id FROM records WHERE state != 'tombstoned'").fetchall()
            ids = [r[0] for r in rows]
        except sqlite3.Error:
            ids = []
        finally:
            conn.close()
    if store is not None:
        for rid in ids:
            try:
                rec = store.get_record(rid, include_history=True)
                if isinstance(rec, dict):
                    rec = rec.get("record", rec)
                if rec:
                    records.append(rec)
            except Exception:  # noqa: BLE001
                continue
    return records


def _policy_snapshot(ctx, data_dir: Path) -> tuple:
    policy = getattr(ctx, "policy", None)
    raw = getattr(policy, "raw", None)
    if raw:
        if yaml is not None:
            return yaml.safe_dump(raw, sort_keys=False), \
                str(raw.get("profile", getattr(policy, "name", "controlled")))
        return json.dumps(raw, indent=2), str(raw.get("profile", "controlled"))
    for name in ("policy.yaml", "policy.yml"):
        p = data_dir / name
        if p.exists():
            prof = getattr(policy, "name", None) or "controlled"
            return p.read_text(encoding="utf-8"), str(prof)
    return f"profile: {getattr(policy, 'name', None) or 'controlled'}\nversion: 1\n", \
        str(getattr(policy, "name", None) or "controlled")


def _checkpoint(ctx, events: list) -> dict:
    spine = getattr(ctx, "spine", None)
    seq, head = 0, "0" * 64
    if events:
        seq, head = int(events[-1].get("seq", 0)), events[-1].get("hash", head)
    if spine is not None:
        try:
            s, h = spine.head()
            if s:
                seq, head = int(s), h
        except Exception:  # noqa: BLE001
            pass
    instance_key = getattr(ctx, "instance_key", None)
    pub, sig, fingerprint = "", "", ""
    if instance_key is not None:
        try:
            pub_hex = instance_key.pub_hex
            pub_hex = pub_hex() if callable(pub_hex) else pub_hex
            fingerprint = ":".join(
                hashlib.sha256(str(pub_hex).encode()).hexdigest()[i:i + 2]
                for i in range(0, 32, 2))
            pub = _b64u(bytes.fromhex(str(pub_hex)))
        except Exception:  # noqa: BLE001
            pub, fingerprint = "", ""
        try:
            msg = _canonical({"seq_hi": seq, "chain_head_hash": head,
                              "event_count": len(events)}).encode()
            raw_sig = instance_key.sign(msg)
            if isinstance(raw_sig, str):
                sig = raw_sig
            else:
                sig = _b64u(bytes(raw_sig))
        except Exception:  # noqa: BLE001
            sig = ""
    return {"seq_hi": max(1, seq), "chain_head_hash": head,
            "event_count": len(events), "instance_sig": sig or _b64u(b""),
            "instance_pubkey": pub or _b64u(b""), "fingerprint": fingerprint}


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def export_bundle(dest_lamf_path, passphrase: str, ctx=None,
                  data_dir=None) -> dict:
    """Build and encrypt a portable bundle. Returns the export receipt dict."""
    if not passphrase:
        raise ExportError("passphrase is mandatory (floor F3)")
    if _crypto is None or not hasattr(_crypto, "export_encrypt"):
        raise ExportError("crypto.export_encrypt unavailable")
    data_dir = _data_dir(ctx, data_dir)

    events = _read_events(ctx, data_dir)
    records = _read_records(ctx, data_dir)
    policy_yaml, profile = _policy_snapshot(ctx, data_dir)
    checkpoint = _checkpoint(ctx, events)

    payload_files = {
        "events/events.jsonl": ("\n".join(_canonical(e) for e in events)
                                + ("\n" if events else "")).encode(),
        "records/records.jsonl": ("\n".join(_canonical(r) for r in records)
                                  + ("\n" if records else "")).encode(),
        "policy.yaml": policy_yaml.encode("utf-8"),
        "checkpoint.json": json.dumps(checkpoint, indent=2).encode(),
    }
    files_meta = [{"path": p, "sha256": _sha256_bytes(b), "bytes": len(b)}
                  for p, b in sorted(payload_files.items())]

    seq_lo = int(events[0]["seq"]) if events else 1
    seq_hi = int(events[-1]["seq"]) if events else max(1, checkpoint["seq_hi"])
    manifest = {
        "format_version": FORMAT_VERSION,
        "lamf_version": LAMF_VERSION,
        "created_at": int(time.time() * 1000),
        "seq_range": {"lo": seq_lo, "hi": seq_hi},
        "checkpoint": checkpoint,
        "files": files_meta,
        "schema_versions": dict(SCHEMA_VERSIONS),
        "policy_profile": profile if profile in (
            "locked", "controlled", "trusted-local", "open-local",
            "ai-custom") else "controlled",
        "excludes": list(EXCLUDES),
    }
    manifest["mac"] = _compute_mac(passphrase,
                                   {k: v for k, v in manifest.items()
                                    if k != "mac"}, files_meta)

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("manifest.json")
        data = json.dumps(manifest, indent=2).encode()
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
        for path, blob in sorted(payload_files.items()):
            info = tarfile.TarInfo(path)
            info.size = len(blob)
            tf.addfile(info, io.BytesIO(blob))
    encrypted = _crypto.export_encrypt(passphrase, buf.getvalue())

    dest = Path(dest_lamf_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(encrypted)
    os.replace(tmp, dest)

    event_id = None
    spine = getattr(ctx, "spine", None)
    if spine is not None:
        try:
            from . import api as _api  # late, defensive
            ev = _api.make_event(ctx, "export",
                                 {"path": str(dest), "seq_range":
                                  manifest["seq_range"],
                                  "chain_head_hash":
                                      checkpoint["chain_head_hash"]},
                                 scope="system", sensitivity="ordinary",
                                 taint="system")
            _, _, event_id = _api.spine_append(
                spine, ev, getattr(ctx, "store", None))
        except Exception:  # noqa: BLE001
            event_id = None

    return {"export_id": f"exp_{hashlib.sha256(encrypted).hexdigest()[:16]}",
            "path": str(dest), "seq_range": manifest["seq_range"],
            "chain_head_hash": checkpoint["chain_head_hash"],
            "files": len(files_meta) + 1, "bytes": len(encrypted),
            "event_id": event_id}


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

def _seed_import_actors(db_path: Path, events: list, records: list) -> None:
    """Actor rows are instance-local (pairing ceremony; never exported), so
    the destination store needs placeholder rows to satisfy FK constraints
    for restored content. Attribution (actor ids) is preserved."""
    import sqlite3
    actors = {e.get("actor") for e in events if e.get("actor")}
    actors |= {r.get("owner_actor") for r in records if r.get("owner_actor")}
    if not actors:
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        now = int(time.time() * 1000)
        for actor_id in sorted(actors):
            kind = {"lamf-system": "system", "lamf-operator": "operator"}.get(
                actor_id, "agent")
            conn.execute(
                "INSERT OR IGNORE INTO actors (actor_id, kind, public_key,"
                " token_sha256, scopes, created_at)"
                " VALUES (?, ?, ?, NULL, '[]', ?)",
                (actor_id, kind, b"\x00" * 32, now))
        conn.commit()
    finally:
        conn.close()


def _check_safe_path(path: str) -> None:
    if not SAFE_PATH.match(path):
        raise ImportError_(f"unsafe path in bundle: {path!r}")
    parts = path.split("/")
    if any(seg in ("", ".") for seg in parts) or path.endswith("/"):
        raise ImportError_(f"unsafe path segments in bundle: {path!r}")
    for seg in parts:
        stem = seg.split(".")[0].lower()
        if stem in DEVICE_NAMES:
            raise ImportError_(f"windows device name in bundle path: {path!r}")


def _package_root() -> Path:
    return Path(__file__).resolve().parents[2]


def import_bundle(src, passphrase: str, dest_dir, force: bool = False,
                  ctx=None) -> dict:
    """Decrypt → verify → restore → verify_deep → rebuild records/FTS."""
    if not passphrase:
        raise ImportError_("passphrase is mandatory (floor F3)")
    if _crypto is None or not hasattr(_crypto, "export_decrypt"):
        raise ImportError_("crypto.export_decrypt unavailable")
    dest = Path(dest_dir)
    if dest.exists() and any(dest.iterdir()) and not force:
        raise ImportError_(
            f"import destination {dest} is not empty; pass force=True "
            f"(CLI --force-reimport) to overwrite")
    dest.mkdir(parents=True, exist_ok=True)

    blob = _crypto.export_decrypt(passphrase, Path(src).read_bytes())
    if len(blob) > MAX_BYTES:
        raise ImportError_("bundle exceeds 4 GiB uncompressed cap")
    try:
        tf = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
    except tarfile.TarError as exc:
        raise ImportError_(f"bundle is not a valid tar.gz: {exc}")

    members = tf.getmembers()
    if len(members) > MAX_ENTRIES:
        raise ImportError_("bundle exceeds 10,000-entry cap")
    contents = {}
    for m in members:
        if not m.isfile():
            continue
        _check_safe_path(m.name)
        contents[m.name] = tf.extractfile(m).read()
    tf.close()

    if "manifest.json" not in contents:
        raise ImportError_("manifest.json missing from bundle")
    manifest = json.loads(contents["manifest.json"].decode())
    mac = manifest.get("mac", "")
    expected = _compute_mac(passphrase,
                            {k: v for k, v in manifest.items()
                             if k != "mac"}, manifest.get("files", []))
    if not _hmac.compare_digest(mac, expected):
        raise ImportError_("manifest MAC mismatch — bundle tampered or wrong "
                           "passphrase")
    for fmeta in manifest.get("files", []):
        blob_f = contents.get(fmeta["path"])
        if blob_f is None:
            raise ImportError_(f"manifest file missing: {fmeta['path']}")
        if _sha256_bytes(blob_f) != fmeta["sha256"]:
            raise ImportError_(f"checksum mismatch: {fmeta['path']}")

    events = [json.loads(ln) for ln in
              contents.get("events/events.jsonl", b"").decode().splitlines()
              if ln.strip()]
    records = [json.loads(ln) for ln in
               contents.get("records/records.jsonl", b"").decode().splitlines()
               if ln.strip()]

    # --- restore policy + checkpoint documents ------------------------------
    (dest / "policy.yaml").write_bytes(contents.get("policy.yaml", b""))
    (dest / "checkpoint.json").write_bytes(
        contents.get("checkpoint.json", b"{}"))

    # --- restore spine (re-append finalized events in seq order) ------------
    events_dir = dest / "spine"
    events_dir.mkdir(parents=True, exist_ok=True)
    restored_events = 0
    spine = None
    try:
        from . import spine as _spine_mod
    except Exception:  # noqa: BLE001
        try:
            import spine as _spine_mod  # type: ignore
        except Exception:  # noqa: BLE001
            _spine_mod = None
    if _spine_mod is not None:
        new_spine_key = None
        if _crypto is not None and hasattr(_crypto, "InstanceKey"):
            try:
                new_spine_key = _crypto.InstanceKey.generate(
                    str(events_dir / "instance.key"))
                if isinstance(new_spine_key, tuple):
                    new_spine_key = new_spine_key[0]
            except Exception:  # noqa: BLE001
                new_spine_key = None
        try:
            spine = _spine_mod.Spine(str(events_dir),
                                     instance_key=new_spine_key)
        except TypeError:
            try:
                spine = _spine_mod.Spine(str(events_dir), new_spine_key)
            except TypeError:
                spine = _spine_mod.Spine(str(events_dir))
        for ev in sorted(events, key=lambda e: e.get("seq", 0)):
            try:
                spine.append(ev)
            except TypeError:
                deferred = {k: v for k, v in ev.items()
                            if k not in ("seq", "prev_hash", "hash", "sig")}
                spine.append(deferred)
            restored_events += 1
    else:
        (events_dir / "events.jsonl").write_bytes(
            contents.get("events/events.jsonl", b""))
        restored_events = len(events)

    # --- restore records (indexes rebuilt from upserts; §M.3) ---------------
    restored_records = 0
    store_err = None
    try:
        from . import store as _store_mod
    except Exception:  # noqa: BLE001
        try:
            import store as _store_mod  # type: ignore
        except Exception:  # noqa: BLE001
            _store_mod = None
    if _store_mod is not None:
        schema = _package_root() / "04_STORAGE" / "SCHEMA.sql"
        db_path = dest / "state" / "lamf.sqlite3"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # §M.3: records are re-encrypted with NEW local data keys — the
        # destination gets a fresh instance key (never the exporter's).
        new_key = None
        if _crypto is not None and hasattr(_crypto, "InstanceKey"):
            try:
                new_key = _crypto.InstanceKey.generate(
                    str(db_path.parent / "instance.key"))
                if isinstance(new_key, tuple):
                    new_key = new_key[0]
            except Exception:  # noqa: BLE001
                new_key = None
        st = None
        try:
            st = _store_mod.Store.open(str(db_path), str(schema),
                                       instance_key=new_key)
        except TypeError:
            try:
                st = _store_mod.Store.open(str(db_path), str(schema))
            except Exception as exc:  # noqa: BLE001
                store_err = str(exc)
        except Exception as exc:  # noqa: BLE001
            store_err = str(exc)
        if st is not None:
            try:
                _seed_import_actors(db_path, events, records)
                pending = [dict(r) for r in records]
                for r in pending:
                    r.pop("history", None)
                    r.pop("superseded_chain", None)
                done: set = set()
                # supersedes FK: insert parents before children (fixpoint)
                for _pass in range(len(pending) + 1):
                    progressed = False
                    for rec in list(pending):
                        sup = rec.get("supersedes")
                        if sup and sup not in done:
                            continue
                        try:
                            st.upsert_record(rec)
                        except (TypeError, KeyError):
                            slim = {k: rec[k] for k in
                                    ("id", "type", "title", "body", "scope",
                                     "owner_actor", "sensitivity", "taint",
                                     "state", "version") if k in rec}
                            st.upsert_record(slim)
                        done.add(rec.get("id"))
                        pending.remove(rec)
                        restored_records += 1
                        progressed = True
                    if not pending or not progressed:
                        break
                for rec in pending:  # FK cycle fallback: strip the pointer
                    rec["supersedes"] = None
                    st.upsert_record(rec)
                    restored_records += 1
            finally:
                try:
                    st.close()
                except Exception:  # noqa: BLE001
                    pass

    verify_deep = None
    if spine is not None:
        try:
            verify_deep = bool(spine.verify_deep())
        except Exception:  # noqa: BLE001
            verify_deep = None

    return {"imported": True, "events": restored_events,
            "records": restored_records, "verify_deep": verify_deep,
            "store_error": store_err,
            "chain_head_hash":
                manifest.get("checkpoint", {}).get("chain_head_hash"),
            "seq_range": manifest.get("seq_range"),
            "dest": str(dest)}
