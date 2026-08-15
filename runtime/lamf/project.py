"""LAMF reference runtime — Obsidian vault projection (DECISIONS.md §W-01).

The vault is a PROJECTION, never the database. This module regenerates the
governed areas from the LAMF authority (Store/Spine):

  ``00 Home.md``          dashboard (native base/query embeds + Mermaid only)
  ``01 Memory/``          one note per memory record            [governed]
  ``02 Activity/``        recent spine activity digest          [governed]
  ``03 Projects/``        project-scoped record rollups         [governed]
  ``04 Agents/``          known-actor notes                     [governed]
  ``05 Council/``         council record rollups                [governed]
  ``06 Security/``        policy/profile summary                [governed]
  ``07 Review Queue/``    controlled-action area (created; watcher writes here)
  ``08 Drafts/``          operator-editable — NEVER written
  ``09 Operator Notes/``  operator-editable — NEVER written
  ``99 System/``          system status + dashboard base        [governed]

Note format (W-01, pinned): FLAT first-level YAML frontmatter only —
``lamf_id``, ``record_type``, ``lamf_version``, ``authority``, ``confidence``,
``scope``, ``sensitivity``, ``taint``, ``projection_hash``,
``last_projected`` (YYYY-MM-DDTHH:mm:ss), ``lamf_editable: false`` — plus one
first-level list property PER relation type with QUOTED wikilinks. Body
carries a ``> [!warning] LAMF-governed note`` callout and a ``## Relations``
mirror list. Nested YAML maps are forbidden (Obsidian Properties contract).

All writes are temp-file + ``os.replace``. ``.obsidian/`` is never written.
Locked profile ⇒ sensitive records project as metadata-only stubs; restricted
records never project content in any profile (floor F11).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path

try:  # pragma: no cover - import shim
    from . import canon as _canon
except Exception:  # noqa: BLE001
    try:
        import canon as _canon  # type: ignore
    except Exception:  # noqa: BLE001
        _canon = None

HOME_FILE = "00 Home.md"
GOVERNED_DIRS = ["01 Memory", "02 Activity", "03 Projects", "04 Agents",
                 "05 Council", "06 Security", "99 System"]
CONTROLLED_DIR = "07 Review Queue"
OPERATOR_DIRS = ["08 Drafts", "09 Operator Notes"]
ALL_AREAS = GOVERNED_DIRS + [CONTROLLED_DIR] + OPERATOR_DIRS

GOVERNED_BANNER = "> [!warning] LAMF-governed note"
STUB_TEXT = "Content: request access via `lamf`"

RECORD_TYPE_ICONS = {
    "fact": "Fact", "preference": "Preference", "identity": "Identity",
    "relationship": "Relationship", "decision": "Decision", "task": "Task",
    "procedure": "Procedure", "failure_lesson": "Failure lesson",
    "episode": "Episode", "handoff_record": "Handoff",
    "council_record": "Council",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _canonical(obj) -> str:
    if _canon is not None and hasattr(_canon, "canonicalize"):
        return _canon.canonicalize(obj)
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(text: str) -> str:
    """Hash of a governed file's content with the volatile lines
    (``projection_hash:`` itself and ``last_projected:``) normalised away, so
    the watcher can recompute the expected value from the on-disk file."""
    lines = [ln for ln in text.splitlines()
             if not ln.startswith("projection_hash:")
             and not ln.startswith("last_projected:")]
    return _sha256_text("\n".join(lines))


def _now_stamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _safe_name(title: str, fallback: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|#^[\]]", "", title or "").strip()
    name = re.sub(r"\s+", " ", name)[:80].strip(" .")
    return name or fallback


def _yaml_scalar(value) -> str:
    s = str(value)
    if s == "" or re.search(r"[:#\[\]{}\n\"']", s) or s != s.strip() \
            or s.lower() in ("true", "false", "null", "yes", "no", "off",
                             "on"):
        return json.dumps(s, ensure_ascii=False)
    return s


def _atomic_write(path: Path, text: str) -> None:
    """temp file + os.replace; never writes into .obsidian/."""
    path = Path(path)
    if ".obsidian" in path.parts:
        raise ValueError(f"refusing to write inside .obsidian/: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / (path.name + ".lamf-tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _policy_profile(policy) -> str:
    name = getattr(policy, "name", None)
    if name:
        return str(name)
    raw = getattr(policy, "raw", None) or {}
    return str(raw.get("profile", "controlled"))


def _data_dir(store, vault_path: Path) -> Path:
    env = os.environ.get("LAMF_DATA_DIR")
    if env:
        return Path(env)
    db_path = None
    for attr in ("db_path", "path", "db_file", "database"):
        p = getattr(store, attr, None)
        if p:
            db_path = Path(p)
            break
    if db_path is not None:
        # db typically lives at <data_dir>/state/lamf.sqlite3; pick the
        # nearest ancestor that looks like the data dir (holds spool/ or
        # operator.token), else the db's parent.
        for cand in (db_path.parent, *db_path.parents):
            if (cand / "spool").exists() or (cand / "operator.token").exists():
                return cand
        return db_path.parent
    return Path(vault_path).parent


def state_path(store, vault_path: Path) -> Path:
    return _data_dir(store, vault_path) / ".projection_state.json"


def load_state(store, vault_path: Path) -> dict:
    p = state_path(store, vault_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_state(store, vault_path: Path, state: dict) -> None:
    p = state_path(store, vault_path)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _ro_conn(store):
    """Read-only SQLite connection for record/event enumeration.

    The pinned Store contract has no list API; we attach read-only to the
    same database file (WAL allows concurrent readers)."""
    db_path = None
    for attr in ("db_path", "path", "db_file", "database"):
        p = getattr(store, attr, None)
        if p and Path(p).exists():
            db_path = str(p)
            break
    if db_path is None:
        conn = getattr(store, "conn", None) or getattr(store, "db", None) \
            or getattr(store, "_conn", None)
        if conn is not None:
            return conn, False
        return None, False
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    return conn, True


def _table_columns(conn, table: str) -> set:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _all_records(store) -> list:
    """Enumerate current active records as plain dicts.

    Superseded versions remain available through record history, but the
    Obsidian top layer represents the current governed view only.
    """
    conn, owned = _ro_conn(store)
    if conn is None:
        return []
    try:
        cols = _table_columns(conn, "records")
        if not cols:
            return []
        select = [c for c in ("id", "type", "title", "tags", "entities",
                              "scope", "owner_actor", "sensitivity", "taint",
                              "state", "version", "supersedes",
                              "source_events", "confidence", "expires_at",
                              "created_seq", "updated_seq")
                  if c in cols]
        # ``select`` is selected exclusively from the fixed tuple above.
        rows = conn.execute(  # nosec B608
            f"SELECT {', '.join(select)} FROM records "  # nosec B608
            f"WHERE state = 'active' ORDER BY updated_seq DESC").fetchall()
        out = []
        for row in rows:
            rec = dict(zip(select, row))
            # Protocol 3 encrypts all user-visible record metadata.  Raw SQL
            # supplies only ordering/identity; projection plaintext must come
            # from the authority boundary.
            try:
                full = store.get_record(rec["id"])
                if isinstance(full, dict):
                    full = full.get("record", full)
                    if isinstance(full, dict):
                        rec = full
            except Exception:  # noqa: BLE001
                continue
            out.append(rec)
        return out
    except sqlite3.Error:
        return []
    finally:
        if owned:
            conn.close()


def _recent_events(store, limit: int = 50) -> list:
    conn, owned = _ro_conn(store)
    if conn is None:
        return []
    try:
        cols = _table_columns(conn, "events")
        if not cols:
            return []
        select = [c for c in ("id", "seq", "ts", "actor", "type", "scope",
                              "sensitivity", "taint") if c in cols]
        # ``select`` is selected exclusively from the fixed tuple above.
        rows = conn.execute(  # nosec B608
            f"SELECT {', '.join(select)} FROM events "  # nosec B608
            f"ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [dict(zip(select, row)) for row in rows]
    except sqlite3.Error:
        return []
    finally:
        if owned:
            conn.close()


def _record_stats(store) -> dict:
    try:
        return store.stats() or {}
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# note rendering
# ---------------------------------------------------------------------------

def _record_relations(rec: dict, titles: dict) -> dict:
    """First-level list property per relation type, QUOTED wikilinks."""
    rels: dict = {}
    sup = rec.get("supersedes")
    if sup:
        rels["supersedes"] = [f'"[[{titles.get(sup, sup)}]]"']
    mentions = [e for e in (rec.get("entities") or []) if e]
    if mentions:
        rels["mentions"] = [f'"[[{_safe_name(e, e)}]]"' for e in mentions[:16]]
    return rels


def render_note(rec: dict, profile: str, titles: dict,
                projected_at: str = None) -> str:
    """Render one governed memory note (W-01 note format, exact)."""
    projected_at = projected_at or _now_stamp()
    sensitivity = rec.get("sensitivity", "ordinary")
    stub = sensitivity == "restricted" or (
        sensitivity == "sensitive" and profile == "locked")

    fm = [
        "---",
        f"lamf_id: {_yaml_scalar(rec.get('id'))}",
        f"record_type: {_yaml_scalar(rec.get('type', 'fact'))}",
        f"lamf_version: {int(rec.get('version', 1))}",
        f"authority: {_yaml_scalar(rec.get('owner_actor', 'lamf'))}",
        f"confidence: {_yaml_scalar(rec.get('confidence', 'medium'))}",
        f"scope: {_yaml_scalar(rec.get('scope', 'general'))}",
        f"sensitivity: {_yaml_scalar(sensitivity)}",
        f"taint: {_yaml_scalar(rec.get('taint', 'user_direct'))}",
        "projection_hash: PROJECTION_HASH_PLACEHOLDER",
        f"last_projected: {projected_at}",
        "lamf_editable: false",
    ]
    rels = _record_relations(rec, titles)
    for rel_type, targets in sorted(rels.items()):
        fm.append(f"{rel_type}: [{', '.join(targets)}]")
    fm.append("---")

    title = rec.get("title", rec.get("id", "untitled"))
    body_lines = [
        GOVERNED_BANNER,
        "> This file is regenerated from the LAMF memory authority. Direct "
        "edits are restored by the watcher and copied to `07 Review Queue/`; "
        "use a controlled action or `lamf` to propose a change.",
        "",
        f"# {title}",
        "",
    ]
    if stub:
        body_lines += [
            f"**{RECORD_TYPE_ICONS.get(rec.get('type'), 'Record')} — protected "
            f"({sensitivity})**",
            "",
            STUB_TEXT,
            "",
        ]
    else:
        body_lines += [str(rec.get("body", "") or ""), ""]
        if rec.get("tags"):
            body_lines += ["Tags: " + ", ".join(f"`{t}`"
                                                for t in rec["tags"]), ""]
    body_lines += ["## Relations", ""]
    if rels:
        for rel_type, targets in sorted(rels.items()):
            for t in targets:
                body_lines.append(f"- **{rel_type}**: {t.strip(chr(34))}")
    else:
        body_lines.append("- (none)")
    body_lines.append("")
    text = "\n".join(fm) + "\n\n" + "\n".join(body_lines)
    return text.replace("PROJECTION_HASH_PLACEHOLDER", content_hash(text))


def render_home(stats: dict, profile: str, head, projected_at: str) -> str:
    """00 Home.md — native base/query embeds + Mermaid ONLY (no dataview)."""
    seq, head_hash = head
    return f"""---
lamf_id: lamf-home
record_type: dashboard
lamf_version: 1
authority: lamf
confidence: high
scope: system
sensitivity: ordinary
taint: system
projection_hash: {content_hash('home:' + str(seq))}
last_projected: {projected_at}
lamf_editable: false
---

{GOVERNED_BANNER}
> LAMF dashboard. Regenerated from the memory authority; do not edit.

# LAMF Home

- Profile: **{profile}**
- Records: **{stats.get('records', stats.get('record_count', 0))}**
- Spine events: **{stats.get('events', stats.get('event_count', seq))}**
- Chain head (seq {seq}): `{str(head_hash)[:16]}…`

## Memory

![[99 System/LAMF.base#All memory]]

## Search the vault

```query
path:"01 Memory"
```

## Recent activity

```query
path:"02 Activity"
```

## Review queue

```query
path:"07 Review Queue"
```

## Memory map

```mermaid
graph LR
    LAMF[LAMF authority]
    VAULT[Obsidian vault]
    MEM["01 Memory ({stats.get('records', stats.get('record_count', 0))} records)"]
    ACT[02 Activity]
    SEC[06 Security]
    RQ[07 Review Queue]
    LAMF --> VAULT
    VAULT --> MEM
    VAULT --> ACT
    VAULT --> SEC
    LAMF -. external edits .-> RQ
```
"""


BASE_FILE = """# LAMF.base — Obsidian native base (core feature, no community plugins).
filters:
  and:
    - 'file.folder == "01 Memory"'
views:
  - type: table
    name: All memory
    order:
      - file.name
      - record_type
      - sensitivity
      - taint
      - confidence
      - lamf_version
      - last_projected
  - type: table
    name: Sensitive
    filters:
      and:
        - 'sensitivity != "ordinary"'
    order:
      - file.name
      - sensitivity
      - last_projected
"""


def render_activity(events: list, projected_at: str) -> str:
    lines = [
        "---",
        "lamf_id: lamf-activity-recent",
        "record_type: activity",
        "lamf_version: 1",
        "authority: lamf",
        "confidence: high",
        "scope: system",
        "sensitivity: ordinary",
        "taint: system",
        "projection_hash: " + content_hash("activity:" + _canonical(events)),
        f"last_projected: {projected_at}",
        "lamf_editable: false",
        "---",
        "",
        GOVERNED_BANNER,
        "",
        "# Recent activity",
        "",
        "| seq | type | actor | scope | sensitivity | taint |",
        "|---|---|---|---|---|---|",
    ]
    for ev in events:
        lines.append(
            f"| {ev.get('seq')} | {ev.get('type')} | {ev.get('actor')} "
            f"| {ev.get('scope')} | {ev.get('sensitivity')} "
            f"| {ev.get('taint')} |")
    if not events:
        lines.append("| - | (no events yet) | | | | |")
    lines.append("")
    return "\n".join(lines)


def render_system(store, profile: str, head, projected_at: str) -> str:
    stats = _record_stats(store)
    seq, head_hash = head
    return f"""---
lamf_id: lamf-system-status
record_type: system
lamf_version: 1
authority: lamf
confidence: high
scope: system
sensitivity: ordinary
taint: system
projection_hash: {content_hash('system:' + str(seq))}
last_projected: {projected_at}
lamf_editable: false
---

{GOVERNED_BANNER}

# System status

- Profile: **{profile}**
- Records: **{stats.get('records', stats.get('record_count', 0))}**
- Events: **{stats.get('events', stats.get('event_count', seq))}**
- Chain head: seq **{seq}**, hash `{head_hash}`
- Regenerate: `lamf project --rebuild`
"""


def render_rollup(area_id: str, title: str, records: list,
                  projected_at: str) -> str:
    lines = [
        "---",
        f"lamf_id: lamf-{area_id.lower().replace(' ', '-')}",
        "record_type: rollup",
        "lamf_version: 1",
        "authority: lamf",
        "confidence: high",
        "scope: system",
        "sensitivity: ordinary",
        "taint: system",
        "projection_hash: " + content_hash(area_id + _canonical(
            [r.get("id") for r in records])),
        f"last_projected: {projected_at}",
        "lamf_editable: false",
        "---",
        "",
        GOVERNED_BANNER,
        "",
        f"# {title}",
        "",
    ]
    if records:
        for r in records:
            name = _safe_name(r.get("title", ""), r.get("id", "?"))
            lines.append(f"- [[{name}]] — {r.get('type')} "
                         f"(v{r.get('version', 1)}, {r.get('sensitivity')})")
    else:
        lines.append("- (nothing yet)")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def _spine_head(store):
    # project_all has no spine handle; the events table seq is the same
    # ordering authority, so derive the head from storage.
    conn, owned = _ro_conn(store)
    if conn is None:
        return 0, "0" * 64
    try:
        row = conn.execute(
            "SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        if row:
            return int(row[0]), row[1]
        return 0, "0" * 64
    except sqlite3.Error:
        return 0, "0" * 64
    finally:
        if owned:
            conn.close()


def project_record(store, policy, vault_path, record_id) -> dict:
    """(Re)project a single record note. Returns {path, projection_hash}."""
    vault = Path(vault_path)
    rec_full = store.get_record(record_id)
    if isinstance(rec_full, dict):
        rec_full = rec_full.get("record", rec_full)
    if not rec_full:
        raise KeyError(f"record {record_id} not found")
    rec = {"id": record_id}
    for k in ("type", "title", "body", "tags", "entities", "scope",
              "owner_actor", "sensitivity", "taint", "state", "version",
              "supersedes", "source_events", "confidence"):
        if isinstance(rec_full, dict) and k in rec_full:
            rec[k] = rec_full[k]
    titles = {}
    if rec.get("supersedes"):
        try:
            old = store.get_record(rec["supersedes"])
            if isinstance(old, dict):
                old = old.get("record", old)
                titles[rec["supersedes"]] = _safe_name(
                    old.get("title", ""), rec["supersedes"])
        except Exception:  # noqa: BLE001
            pass
    profile = _policy_profile(policy)
    text = render_note(rec, profile, titles)
    name = _safe_name(rec.get("title", ""), record_id)
    path = vault / "01 Memory" / f"{name}.md"
    _atomic_write(path, text)
    phash = content_hash(text)
    state = load_state(store, vault)
    state[str(path.relative_to(vault))] = {
        "projection_hash": phash, "kind": "record", "record_id": record_id}
    _save_state(store, vault, state)
    return {"path": str(path), "projection_hash": phash}


def project_all(store, policy, vault_path) -> dict:
    """Full (re)projection of the governed vault areas. Returns stats."""
    vault = Path(vault_path)
    vault.mkdir(parents=True, exist_ok=True)
    for area in ALL_AREAS:
        (vault / area).mkdir(parents=True, exist_ok=True)

    profile = _policy_profile(policy)
    projected_at = _now_stamp()
    stats = {"records_projected": 0, "stubs": 0, "files_written": 0,
             "files_removed": 0, "skipped": 0}
    new_state: dict = {}

    records = _all_records(store)
    titles = {_r.get("id"): _safe_name(_r.get("title", ""), _r.get("id", "?"))
              for _r in records}

    # 01 Memory — one note per record
    memory_paths = set()
    for rec in records:
        text = render_note(rec, profile, titles, projected_at)
        name = titles[rec["id"]]
        path = vault / "01 Memory" / f"{name}.md"
        _atomic_write(path, text)
        rel = str(path.relative_to(vault))
        memory_paths.add(rel)
        new_state[rel] = {"projection_hash": content_hash(text),
                          "kind": "record", "record_id": rec["id"]}
        stats["files_written"] += 1
        stats["records_projected"] += 1
        if rec.get("sensitivity") == "restricted" or (
                rec.get("sensitivity") == "sensitive" and profile == "locked"):
            stats["stubs"] += 1

    head = _spine_head(store)
    stats_summary = _record_stats(store)

    generated = {
        HOME_FILE: ("home", render_home(stats_summary, profile, head,
                                        projected_at)),
        "02 Activity/Recent Activity.md": (
            "activity", render_activity(_recent_events(store), projected_at)),
        "03 Projects/Projects.md": (
            "rollup", render_rollup(
                "03-projects", "Projects",
                [r for r in records if str(r.get("scope", "")).startswith(
                    ("project", "proj"))], projected_at)),
        "04 Agents/Agents.md": (
            "rollup", render_rollup(
                "04-agents", "Agents",
                [r for r in records if r.get("taint") == "agent_generated"],
                projected_at)),
        "05 Council/Council.md": (
            "rollup", render_rollup(
                "05-council", "Council",
                [r for r in records if r.get("type") == "council_record"],
                projected_at)),
        "06 Security/Security Profile.md": (
            "rollup", render_rollup(
                "06-security", f"Security profile: {profile}",
                [r for r in records
                 if r.get("sensitivity") != "ordinary"], projected_at)),
        "99 System/Status.md": (
            "system", render_system(store, profile, head, projected_at)),
        "99 System/LAMF.base": ("base", BASE_FILE),
    }
    for rel, (kind, text) in generated.items():
        _atomic_write(vault / rel, text)
        new_state[rel] = {"projection_hash": content_hash(text),
                          "kind": kind, "record_id": None}
        stats["files_written"] += 1

    # remove stale governed files from a previous projection
    old_state = load_state(store, vault)
    for rel in old_state:
        if rel not in new_state:
            stale = vault / rel
            try:
                if stale.is_file() and stale.parts and \
                        (rel.split("/")[0] in GOVERNED_DIRS
                         or rel == HOME_FILE):
                    stale.unlink()
                    stats["files_removed"] += 1
            except OSError:
                pass

    _save_state(store, vault, new_state)
    stats["vault"] = str(vault)
    return stats
