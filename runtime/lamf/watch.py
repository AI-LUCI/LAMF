"""LAMF reference runtime — projection watcher (DECISIONS.md §W-01).

Polling watcher (default 1 s). Governed files (``00 Home.md`` + ``01 Memory/``
… ``06 Security/`` + ``99 System/``) are hash-compared against the
``projection_hash`` values recorded in ``<data_dir>/.projection_state.json``
by project.py. A changed or deleted governed file is:

  1. restored from the authority (LAMF is the source of truth, never the
     vault);
  2. the tampered version (when present) is copied to
     ``07 Review Queue/External Edit - <name>.md``;
  3. an audit event is appended to the witness spine.

External edits are NEVER silently imported (W-01, floor F5). The watcher never
touches ``08 Drafts/``, ``09 Operator Notes/`` or ``.obsidian/``.

``ctx`` is duck-typed: ``store``, ``policy``, ``spine``, ``data_dir``
(optional), ``actor`` (optional).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

try:  # pragma: no cover - import shim
    from . import project as _project
except Exception:  # noqa: BLE001
    try:
        import project as _project  # type: ignore
    except Exception:  # noqa: BLE001
        _project = None

try:
    from . import api as _api
except Exception:  # noqa: BLE001
    try:
        import api as _api  # type: ignore
    except Exception:  # noqa: BLE001
        _api = None

NEVER_TOUCH = ("08 Drafts", "09 Operator Notes", ".obsidian")


def _data_dir(ctx, store, vault: Path) -> Path:
    d = getattr(ctx, "data_dir", None)
    if d:
        return Path(d)
    if _project is not None:
        return _project._data_dir(store, vault)
    return vault.parent


def _load_state(ctx, vault: Path) -> dict:
    store = getattr(ctx, "store", None)
    if _project is not None and store is not None:
        return _project.load_state(store, vault)
    p = _data_dir(ctx, store, vault) / ".projection_state.json"
    if not p.exists():
        return {}
    import json
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _hash_file(path: Path) -> str:
    if _project is not None:
        return _project.content_hash(
            path.read_text(encoding="utf-8", errors="replace"))
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _audit(ctx, payload: dict):
    spine = getattr(ctx, "spine", None)
    if spine is None or _api is None:
        return None
    ev = _api.make_event(ctx, "recovery", payload, scope="system",
                         sensitivity="ordinary", taint="system",
                         actor=getattr(ctx, "actor", None) or "lamf-system")
    _, _, event_id = _api.spine_append(spine, ev, getattr(ctx, "store", None))
    return event_id


def _review_copy(vault: Path, rel: str, original: Path) -> Path:
    """Save the tampered version into 07 Review Queue (atomic write)."""
    rq = vault / "07 Review Queue"
    rq.mkdir(parents=True, exist_ok=True)
    name = f"External Edit - {Path(rel).name}"
    dest = rq / name
    n = 1
    while dest.exists():
        n += 1
        dest = rq / f"External Edit - {Path(rel).stem} ({n}){Path(rel).suffix}"
    tmp = dest.with_name(dest.name + ".lamf-tmp")
    tmp.write_bytes(original.read_bytes())
    os.replace(tmp, dest)
    return dest


def _restore(ctx, vault: Path, rel: str, entry: dict) -> bool:
    """Restore one governed file from the authority."""
    store = getattr(ctx, "store", None)
    policy = getattr(ctx, "policy", None)
    if _project is None or store is None:
        return False
    record_id = entry.get("record_id")
    if entry.get("kind") == "record" and record_id:
        try:
            _project.project_record(store, policy, vault, record_id)
            return True
        except Exception:  # noqa: BLE001
            return False
    # dashboard/activity/system/rollup/base: regenerate the full projection
    try:
        _project.project_all(store, policy, vault)
        return True
    except Exception:  # noqa: BLE001
        return False


def _protected(rel: str) -> bool:
    parts = Path(rel).parts
    if not parts:
        return False
    top = parts[0]
    if top in NEVER_TOUCH:
        return False
    if ".obsidian" in parts:
        return False
    return True


def watch_pass(vault, ctx) -> dict:
    """One watcher pass. Returns {checked, restored, deleted_restored,
    review_copies, audit_events}."""
    vault = Path(vault)
    stats = {"checked": 0, "restored": 0, "deleted_restored": 0,
             "review_copies": [], "audit_events": []}
    state = _load_state(ctx, vault)
    for rel, entry in list(state.items()):
        if not _protected(rel):
            continue
        if not isinstance(entry, dict):
            entry = {"projection_hash": entry, "kind": "unknown",
                     "record_id": None}
        stats["checked"] += 1
        path = vault / rel
        tampered = False
        deleted = False
        if not path.exists():
            deleted = True
        else:
            try:
                if _hash_file(path) != entry.get("projection_hash"):
                    tampered = True
            except OSError:
                deleted = True
        if not (tampered or deleted):
            continue

        review_path = None
        if tampered:
            review_path = _review_copy(vault, rel, path)
            stats["review_copies"].append(str(review_path))
        restored = _restore(ctx, vault, rel, entry)
        if restored:
            stats["restored" if tampered else "deleted_restored"] += 1
        event_id = _audit(ctx, {
            "reason": "external_edit" if tampered else "governed_file_deleted",
            "path": rel,
            "action": "restored" if restored else "restore_failed",
            "review_copy": str(review_path) if review_path else None,
            "record_id": entry.get("record_id"),
        })
        if event_id:
            stats["audit_events"].append(event_id)
    return stats


def watch_loop(vault, ctx, interval: float = 1.0, stop_event=None) -> None:
    """Blocking polling watcher (W-01: ``watch_loop(vault, ctx)``)."""
    vault = Path(vault)
    while True:
        try:
            watch_pass(vault, ctx)
        except Exception:  # noqa: BLE001 — the watcher must never die loudly
            pass
        if stop_event is not None and stop_event.is_set():
            return
        time.sleep(interval)
