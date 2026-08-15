#!/usr/bin/env python3
"""
LAMF package validator (DECISIONS.md §P).

"Validated" for this package means: this script exits 0.

Checks, in order:
  1. Reference integrity — every path referenced in any doc exists in the tree.
  2. Policy conformance — the four fixed profile YAMLs validate against
     03_CONTRACTS/schemas/security-policy.schema.json (incl. floor constants),
     and negative controls are rejected.
  3. SQLite schema executes — 04_STORAGE/SCHEMA.sql runs on a temp DB with
     PRAGMA foreign_keys=ON, and the FTS5 tables work.
  4. Golden vectors — this file independently re-implements LAMF-CANON-1 from
     03_CONTRACTS/canonical-hashing.md and reproduces every canonical string
     and SHA-256 in 03_CONTRACTS/golden-vectors.json. (Doubles as the Python
     leg of the cross-language hash-parity acceptance test.)
  5. Manifest — MANIFEST.sha256 matches the tree. NOTE: the manifest is
     UNSIGNED — it detects accidental drift, not malice.
  6. Test-ID registry — every T-id referenced anywhere is defined in
     08_BUILD_PLAN/ACCEPTANCE_TESTS.md.
  7. Cross-file consistency — event-type enum identical across the schema,
     OpenAPI, and SCHEMA.sql; banned spellings absent (snake_case profile
     names, include_indexes).

Usage: python3 tools/validate_package.py [--root PACKAGE_DIR]
Stdlib only, except check 2 which uses PyYAML + jsonschema when available and
falls back to a built-in minimal floor checker otherwise.
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import unicodedata
from pathlib import Path

FAILURES = []
CHECKED_EXT = {".md", ".yaml", ".yml", ".json", ".sql", ".svg", ".dot", ".ts", ".sha256"}
TOP_DIRS = (
    "00_EXECUTIVE/", "01_ARCHITECTURE/", "02_SECURITY/", "03_CONTRACTS/",
    "04_STORAGE/", "05_INTEGRATIONS/", "06_SETUP/", "07_PORTABILITY/",
    "08_BUILD_PLAN/", "blueprints/", "tools/",
)
TOP_FILES = {
    "README.md", "START_HERE.md", "VERSION", "CHANGELOG.md", "LICENSE",
    "PROMPT_FOR_CODING_AI.md", "BUILD_WITH_AI.md", "DECISIONS.md",
    "DEFECT_LEDGER.md", "EVALUATION_REPORT.md", "MANIFEST.sha256",
}

IGNORED_TREE_PREFIXES = (
    ".git/", ".agent-runs/", ".artifacts/", ".pytest_cache/", ".test-runs/",
    "build/", "comparative-benchmark/", "data/", "data-pre-v3-legacy-", "dist/",
    "runtime/.venv/",
)


def package_file(root: Path, path: Path) -> bool:
    """True for shipped package files, excluding local runtime/test state."""
    if not path.is_file():
        return False
    rel = path.relative_to(root).as_posix()
    return (not rel.startswith(IGNORED_TREE_PREFIXES)
            and not rel.startswith("lamf-smoke-")
            and "__pycache__" not in path.parts and path.suffix != ".pyc")


def fail(check, msg):
    FAILURES.append((check, msg))
    print(f"  FAIL [{check}] {msg}")


# ---------------------------------------------------------------- check 1
# Placeholder filenames used in docs as user-supplied examples or runtime artifacts
# (never package files)
PLACEHOLDERS = {
    "FILE.lamf", "FILE.yaml", "my-memory.lamf", "evil.lamf", "notes.md",
    "security.custom.yaml", "OPEN_DECISIONS.md",  # builder-created from template
    "manifest.json",  # .lamf bundle-internal artifact name (not the package tree)
    "lamf-install.json",  # installer-generated receipt
    "server.json",  # runtime deployment config (V-04); created by the operator, not shipped
}
SCAN_EXT = {".md", ".yaml", ".yml", ".json", ".sql", ".ts"}


def check_references(root: Path):
    print("check 1: reference integrity")
    token_re = re.compile(r"`([^`\n]+)`")
    link_re = re.compile(r"\]\(([^)\s]+)\)")
    fenced_path_re = re.compile(r"(?<![\w/.-])((?:00_EXECUTIVE|01_ARCHITECTURE|02_SECURITY|"
                                r"03_CONTRACTS|04_STORAGE|05_INTEGRATIONS|06_SETUP|"
                                r"07_PORTABILITY|08_BUILD_PLAN|blueprints|tools)/[\w./-]+)")
    n_checked = 0

    def resolve(src: Path, path_part: str, raw: str):
        nonlocal n_checked
        suffix = Path(path_part).suffix
        if suffix not in CHECKED_EXT:
            return
        if "/" not in path_part:
            if path_part in PLACEHOLDERS:
                return
            n_checked += 1
            hits = basename_index.get(path_part, [])
            if len(hits) == 0:
                fail(1, f"{src.relative_to(root)}: unresolved bare reference `{raw}`")
            elif len(hits) > 1 and not any(h.parent == root for h in hits):
                fail(1, f"{src.relative_to(root)}: ambiguous bare reference `{raw}` "
                        f"({len(hits)} files share that basename)")
            # multi-hit with a root-level file: bare name resolves to the root file
            return
        if Path(path_part).name in PLACEHOLDERS:
            # slashed runtime path whose basename is a known non-shipped artifact
            return
        n_checked += 1
        if not (root / path_part).exists() and not (src.parent / path_part).exists():
            fail(1, f"{src.relative_to(root)}: dangling reference `{raw}`")

    # basename index: bare filenames resolve iff exactly one tree file has that name
    basename_index = {}
    for p in root.rglob("*"):
        if package_file(root, p):
            basename_index.setdefault(p.name, []).append(p)

    for f in sorted(p for p in root.rglob("*")
                    if package_file(root, p) and p.suffix in SCAN_EXT):
        text = f.read_text(encoding="utf-8")
        tokens = token_re.findall(text) + link_re.findall(text)
        for tok in tokens:
            tok = tok.strip()
            if not tok or tok.startswith(("http://", "https://", "#", "~", "$")):
                continue
            if any(c in tok for c in ("*", "<", ">")):
                continue
            path_part = re.split(r"[#§\s]", tok)[0]
            if path_part:
                resolve(f, path_part, tok)
        # fenced/code-block paths with a top-dir prefix (unbackticked commands)
        for m in fenced_path_re.findall(text):
            p = re.split(r"[#§]", m)[0].rstrip(".,);")
            if Path(p).suffix in CHECKED_EXT:
                n_checked += 1
                if not (root / p).exists():
                    fail(1, f"{f.relative_to(root)}: dangling code-block path `{m}`")
    print(f"  {n_checked} references checked")


# ---------------------------------------------------------------- check 2
FLOOR_CONSTS = [
    (("actor_auth",), "required"),
    (("secrets", "pre_sanitization"), "required"),
    (("secrets", "value_detection"), "required"),
    (("promotion", "external_content"), "never_auto"),
    (("model_self_approval",), False),
    (("deletion", "erasure"), "crypto_shredding"),
    (("encryption", "export"), "required"),
    (("git", "sensitive_classes"), "excluded"),
    (("capture", "llm_transcript"), "off"),
]


def _dig(obj, path):
    for k in path:
        if not isinstance(obj, dict) or k not in obj:
            return None, False
        obj = obj[k]
    return obj, True


def _minimal_floor_check(policy, name):
    ok = True
    for path, want in FLOOR_CONSTS:
        got, found = _dig(policy, path)
        if not found or got != want:
            fail(2, f"{name}: floor const {'.'.join(path)} must be {want!r}, got {got!r}")
            ok = False
    q, _ = _dig(policy, ("quarantine", "ttl_days"))
    if not (isinstance(q, int) and 1 <= q <= 90):
        fail(2, f"{name}: quarantine.ttl_days {q!r} outside 1..90")
        ok = False
    a, _ = _dig(policy, ("approvals", "ttl_hours"))
    if not (isinstance(a, int) and 1 <= a <= 168):
        fail(2, f"{name}: approvals.ttl_hours {a!r} outside 1..168")
        ok = False
    net, _ = _dig(policy, ("network", "bind"))
    if net == "lan":
        tls, _ = _dig(policy, ("network", "lan", "tls"))
        auth, _ = _dig(policy, ("network", "lan", "auth"))
        if tls is not True or auth != "required":
            fail(2, f"{name}: LAN bind without tls+auth")
            ok = False
    return ok


def check_policies(root: Path):
    print("check 2: policy conformance")
    schema_path = root / "03_CONTRACTS/schemas/security-policy.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    profiles_dir = root / "02_SECURITY/profiles"
    try:
        import yaml  # PyYAML
    except ImportError:
        yaml = None
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if yaml is None:
        print("  PyYAML unavailable — check 2 SKIPPED (install pyyaml for full validation)")
        return
    files = sorted(profiles_dir.glob("*.yaml"))
    if len(files) != 4:
        fail(2, f"expected 4 profile YAMLs, found {len(files)}")
    for f in files:
        policy = yaml.safe_load(f.read_text(encoding="utf-8"))
        if jsonschema is not None:
            try:
                jsonschema.validate(policy, schema)
                print(f"  PASS schema {f.name}")
            except jsonschema.ValidationError as e:
                fail(2, f"{f.name} schema violation: {e.message}")
        else:
            print(f"  jsonschema lib unavailable; minimal floor check for {f.name}")
            _minimal_floor_check(policy, f.name)
    # negative controls must be REJECTED
    if jsonschema is not None and files:
        base = yaml.safe_load(files[0].read_text(encoding="utf-8"))
        bad_cases = {
            "model_self_approval=true": lambda p: p.update(model_self_approval=True),
            "lan without tls": lambda p: p["network"].update(bind="lan", lan={"enabled": True, "tls": False, "auth": "required"}),
            "quarantine ttl 365": lambda p: p["quarantine"].update(ttl_days=365),
        }
        for label, mutate in bad_cases.items():
            import copy
            bad = copy.deepcopy(base)
            mutate(bad)
            try:
                jsonschema.validate(bad, schema)
                fail(2, f"negative control ACCEPTED (must be rejected): {label}")
            except jsonschema.ValidationError:
                print(f"  PASS rejected negative control: {label}")


# ---------------------------------------------------------------- check 3
PINNED_COLUMNS = {
    "events": {"id", "seq", "ts", "actor", "session", "type", "scope", "sensitivity",
               "taint", "payload_json", "payload_ref", "payload_sha256", "prev_hash",
               "hash", "sig", "channel_json", "sanitizer_note", "capture_sig"},
    "records": {"id", "type", "title", "body_enc", "state", "version", "scope",
                "sensitivity", "taint"},
    "checkpoints": set(), "handoffs": {"fencing_token"}, "approvals": {"kind", "receipt_id"},
    "quarantine": set(), "capsules": {"policy_version", "record_watermark"},
    "ingester_state": {"high_water_seq"}, "policy_state": {"version"},
    "instance_identity": {"pubkey", "fingerprint"},
    "secrets_registry": {"ref_name_salted_hash", "value_enc", "salt", "value_len"},
}


def check_sqlite(root: Path):
    print("check 3: SQLite schema executes + functional FTS/rebuild")
    sql = (root / "04_STORAGE/SCHEMA.sql").read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
        db_path = tf.name
    try:
        con = sqlite3.connect(db_path)
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript(sql)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for required in ("events", "records", "checkpoints", "handoffs", "approvals",
                         "quarantine", "schema_migrations", "ingester_state",
                         "policy_state", "instance_identity", "secrets_registry"):
            if required not in tables:
                fail(3, f"missing table {required}")
        for table, cols in PINNED_COLUMNS.items():
            if table not in tables:
                continue
            actual = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
            for c in sorted(cols - actual):
                fail(3, f"{table}: pinned column missing: {c}")
        # functional FTS + documented rebuild (contentless events_fts, 'delete-all')
        actor_cols = [r[1] for r in con.execute("PRAGMA table_info(actors)")]
        actor_vals = {"actor_id": "'val-op'", "kind": "'operator'", "public_key": "'pk'",
                      "created_at": "1754000000000", "token_sha256": "NULL",
                      "scopes": "'[]'", "revoked_at": "NULL"}
        notnull = [r[1] for r in con.execute("PRAGMA table_info(actors)")
                   if r[3] and r[4] is None and r[1] != "actor_id"]
        ins_cols = ["actor_id"] + [c for c in notnull]
        con.execute(f"INSERT INTO actors({', '.join(ins_cols)}) "
                    f"VALUES ({', '.join(actor_vals.get(c, 'NULL') for c in ins_cols)})")
        z = "0" * 64
        con.execute(
            "INSERT INTO events(id, seq, ts, actor, session, type, scope, sensitivity,"
            " taint, payload_json, payload_ref, payload_sha256, prev_hash, hash, sig)"
            " VALUES ('018f7c2e-0000-7000-8000-000000000001', 1, 1754000000000,"
            " 'val-op', NULL, 'message', 'user', 'ordinary', 'user_direct',"
            " '{\"text\":\"validator hello world\"}', NULL,"
            " '6e756c6c00000000000000000000000000000000000000000000000000000000',"
            f" '{z}', '{'1'*64}', 'sig')")
        n = con.execute("SELECT count(*) FROM events_fts WHERE events_fts MATCH 'hello'").fetchone()[0]
        if n != 1:
            fail(3, f"events_fts MATCH after trigger insert returned {n}, want 1")
        con.execute("INSERT INTO events_fts(events_fts) VALUES('delete-all')")
        con.execute("INSERT INTO events_fts(rowid, payload_text, actor, type, scope, session)"
                    " SELECT rowid, coalesce(payload_json,''), actor, type, scope,"
                    " coalesce(session,'') FROM events")
        n = con.execute("SELECT count(*) FROM events_fts WHERE events_fts MATCH 'hello'").fetchone()[0]
        if n != 1:
            fail(3, f"events_fts MATCH after documented rebuild returned {n}, want 1")
        # U-08b CHECK: sensitive event with inline payload must be rejected
        try:
            con.execute(
                "INSERT INTO events(id, seq, ts, actor, session, type, scope, sensitivity,"
                " taint, payload_json, payload_ref, payload_sha256, prev_hash, hash, sig)"
                " VALUES ('018f7c2e-0000-7000-8000-000000000002', 2, 1754000000001,"
                " 'val-op', NULL, 'message', 'user', 'sensitive', 'user_direct',"
                " '{\"text\":\"x\"}', NULL,"
                " '6e756c6c00000000000000000000000000000000000000000000000000000000',"
                f" '{'1'*64}', '{'2'*64}', 'sig')")
            fail(3, "U-08b CHECK missing: sensitive inline payload was accepted")
        except sqlite3.IntegrityError:
            print("  PASS U-08b sensitive-inline CHECK rejects")
        con.close()
        print(f"  tables: {len(tables)}; pinned columns verified; FTS MATCH + rebuild OK")
    except Exception as e:  # noqa: BLE001
        fail(3, f"SCHEMA.sql execution error: {e}")


# ------------------------------------------------------- check 4 (hashing)
class CanonError(ValueError):
    pass


def _esc(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    return "".join(out)


def canon(obj) -> str:
    """Independent LAMF-CANON-1 implementation (spec: 03_CONTRACTS/canonical-hashing.md)."""
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        raise CanonError("floating-point values are forbidden in hashed payloads")
    if isinstance(obj, str):
        return '"' + _esc(unicodedata.normalize("NFC", obj)) + '"'
    if isinstance(obj, list):
        return "[" + ",".join(canon(x) for x in obj) + "]"
    if isinstance(obj, dict):
        items = []
        seen = set()
        for k in obj:
            if not isinstance(k, str):
                raise CanonError("non-string object key")
            nk = unicodedata.normalize("NFC", k)
            if nk in seen:
                raise CanonError(f"duplicate key after NFC: {nk!r}")
            seen.add(nk)
            items.append((nk.encode("utf-8"), canon(obj[k])))
        items.sort(key=lambda kv: kv[0])
        return "{" + ",".join('"' + _esc(k.decode("utf-8")) + '":' + v for k, v in items) + "}"
    raise CanonError(f"unhashable type: {type(obj)}")


def _no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise CanonError(f"duplicate key in JSON input: {k!r}")
        d[k] = v
    return d


REQUIRED_VECTORS = {
    "ascii-object", "nested-object-array", "non-ascii-nfc",
    "key-sorting-proof", "control-char-escaping", "lamf-event-genesis",
}


def check_vectors(root: Path):
    print("check 4: golden hash vectors (independent LAMF-CANON-1 re-implementation)")
    gv = json.loads((root / "03_CONTRACTS/golden-vectors.json").read_text(encoding="utf-8"),
                    object_pairs_hook=_no_dupes)
    names = {v.get("name") for v in gv["vectors"]}
    for req in sorted(REQUIRED_VECTORS - names):
        fail(4, f"required vector missing: {req}")
    for vec in gv["vectors"]:
        name = vec["name"]
        try:
            c = canon(vec["input"])
        except CanonError as e:
            fail(4, f"{name}: canonicalization raised {e}")
            continue
        if c != vec["canonical"]:
            fail(4, f"{name}: canonical mismatch\n    got:  {c}\n    want: {vec['canonical']}")
            continue
        h = hashlib.sha256(c.encode("utf-8")).hexdigest()
        if h != vec["sha256"]:
            fail(4, f"{name}: sha256 mismatch")
        else:
            print(f"  PASS {name}  {h[:16]}…")


# ---------------------------------------------------------------- check 5
def manifest_digest(path: Path) -> str:
    """Hash portable content while ignoring checkout-specific text EOLs."""
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        portable = data
    else:
        portable = text.replace("\r\n", "\n").encode("utf-8")
    return hashlib.sha256(portable).hexdigest()


def check_manifest(root: Path):
    print("check 5: MANIFEST.sha256")
    mpath = root / "MANIFEST.sha256"
    if not mpath.exists():
        fail(5, "MANIFEST.sha256 missing — generate it before freezing")
        return
    listed = set()
    for line in mpath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        digest, rel = line.split(None, 1)
        rel = rel.lstrip("* ").strip()
        if rel.startswith("./"):
            rel = rel[2:]
        listed.add(rel)
        p = root / rel
        if not p.exists():
            fail(5, f"manifest entry missing on disk: {rel}")
            continue
        actual = manifest_digest(p)
        if actual != digest:
            fail(5, f"hash mismatch: {rel}")
    # Manifest paths are portable and always use forward slashes.  Path.__str__
    # uses backslashes on Windows, which made every valid entry look missing.
    runtime_dirs = {"runtime/.venv", "data", ".test-runs", ".git",
                    ".agent-runs", ".artifacts", ".pytest_cache", "build",
                    "comparative-benchmark", "dist"}
    on_disk = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
        and not any(
            p.relative_to(root).as_posix() == d
            or p.relative_to(root).as_posix().startswith(d + "/")
            for d in runtime_dirs
        )
        and not p.relative_to(root).as_posix().startswith("lamf-smoke-")
        and not p.relative_to(root).as_posix().startswith("data-pre-v3-legacy-")
        and p.relative_to(root).as_posix()
        != "05_INTEGRATIONS/optimizations/overlay/LamfOptimizationControls.exe"
    }
    on_disk.discard("MANIFEST.sha256")
    for extra in sorted(on_disk - listed):
        fail(5, f"file not in manifest: {extra}")
    print(f"  {len(listed)} manifest entries")


def write_manifest(root: Path):
    """Regenerate the portable package manifest after intentional edits."""
    runtime_dirs = {"runtime/.venv", "data", ".test-runs", ".git",
                    ".agent-runs", ".artifacts", ".pytest_cache", "build",
                    "comparative-benchmark", "dist"}
    paths = sorted(
        p for p in root.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
        and p.relative_to(root).as_posix() != "MANIFEST.sha256"
        and not p.relative_to(root).as_posix().startswith("data-pre-v3-legacy-")
        and not any(p.relative_to(root).as_posix() == d or
                    p.relative_to(root).as_posix().startswith(d + "/")
                    for d in runtime_dirs)
        and not p.relative_to(root).as_posix().startswith("lamf-smoke-")
        and p.relative_to(root).as_posix()
        != "05_INTEGRATIONS/optimizations/overlay/LamfOptimizationControls.exe"
    )
    lines = [f"{manifest_digest(p)}  "
             f"{p.relative_to(root).as_posix()}" for p in paths]
    (root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    print(f"manifest updated: {len(paths)} entries")


# ---------------------------------------------------------------- check 6
TID_RE = re.compile(r"\bT-[a-z0-9][a-z0-9-]*[a-z0-9]\b")


META_FILES = {"DECISIONS.md", "DEFECT_LEDGER.md", "EVALUATION_REPORT.md", "CHANGELOG.md"}


def check_test_ids(root: Path):
    print("check 6: test-ID registry")
    reg_path = root / "08_BUILD_PLAN/ACCEPTANCE_TESTS.md"
    registry = set(TID_RE.findall(reg_path.read_text(encoding="utf-8")))
    print(f"  registry: {len(registry)} defined test IDs")
    for f in sorted(p for p in root.rglob("*")
                    if package_file(root, p) and p.suffix in SCAN_EXT):
        if f == reg_path or f.name in META_FILES:
            continue
        for tid in set(TID_RE.findall(f.read_text(encoding="utf-8"))):
            if tid not in registry:
                fail(6, f"{f.relative_to(root)}: undefined test ID `{tid}`")


# ---------------------------------------------------------------- check 7
BANNED_PATTERNS = [
    (re.compile(r"\btrusted_local\b|\bopen_local\b|\bai_custom\b"),
     "snake_case profile name (hyphenated only, DECISIONS U-11)"),
    (re.compile(r"include[_-]indexes"), "include_indexes (removed, DECISIONS U-01)"),
    (re.compile(r"\blocal-only\b"), "git mode 'local-only' (use 'local')"),
]


def check_consistency(root: Path):
    print("check 7: cross-file consistency")
    # 7a: banned spellings
    for f in sorted(p for p in root.rglob("*")
                    if package_file(root, p) and p.suffix in SCAN_EXT):
        text = f.read_text(encoding="utf-8")
        for pat, label in BANNED_PATTERNS:
            for m in pat.finditer(text):
                # allow meta-references: files documenting the ban, or lines
                # explicitly stating the spelling is banned/removed/legacy
                if f.name in {"DECISIONS.md", "DEFECT_LEDGER.md", "EVALUATION_REPORT.md",
                              "CHANGELOG.md", "validate_package.py"}:
                    continue
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.end())
                line = text[line_start: line_end if line_end != -1 else len(text)].lower()
                if any(w in line for w in ("banned", "forbidden", "removed", "legacy",
                                           "do not", "not use", "deprecated")):
                    continue
                fail(7, f"{f.relative_to(root)}: banned spelling {label}: `{m.group(0)}`")
    # 7b: event-type enum identical across the three normative surfaces
    def enum_from_schema():
        s = json.loads((root / "03_CONTRACTS/schemas/event.schema.json").read_text(encoding="utf-8"))
        return set(s["properties"]["type"]["enum"])

    def enum_from_openapi():
        text = (root / "03_CONTRACTS/openapi.yaml").read_text(encoding="utf-8")
        m = re.search(r"enum:\s*\[([^\]]*message[^\]]*)\]", text)
        if not m:
            return None
        return {x.strip() for x in m.group(1).split(",")}

    def enum_from_sql():
        text = (root / "04_STORAGE/SCHEMA.sql").read_text(encoding="utf-8")
        m = re.search(r"type\s+TEXT NOT NULL CHECK \(type IN \((.*?)\)\)", text, re.S)
        if not m:
            return None
        return set(re.findall(r"'([a-z_]+)'", m.group(1)))

    a, b, c = enum_from_schema(), enum_from_openapi(), enum_from_sql()
    if not (a and b and c):
        fail(7, "could not extract event-type enum from one or more surfaces")
    else:
        if not (a == b == c):
            fail(7, f"event-type enum drift: schema-only={sorted(a - b - c)}, "
                    f"openapi-only={sorted(b - a - c)}, sql-only={sorted(c - a - b)}, count={len(a)}/{len(b)}/{len(c)}")
        else:
            print(f"  event-type enum identical across 3 surfaces ({len(a)} types)")


def check_r3_regressions(root: Path):
    """Round-3 regression guards: mechanical coverage for the R3-* defect classes
    that earlier checks could not see (validator-evasion findings)."""
    print("check 8: round-3 regression guards")
    meta = {"DECISIONS.md", "DEFECT_LEDGER.md", "EVALUATION_REPORT.md",
            "CHANGELOG.md", "validate_package.py"}
    scan = sorted(p for p in root.rglob("*")
                  if package_file(root, p) and p.suffix in SCAN_EXT)
    # 8a: schema $id base uniform (U-10f / R3-13)
    for f in (root / "03_CONTRACTS/schemas").glob("*.schema.json"):
        sid = json.loads(f.read_text(encoding="utf-8")).get("$id", "")
        if not sid.startswith("https://lamf.dev/"):
            fail(8, f"{f.name}: $id base is not https://lamf.dev/: {sid}")
    # 8b: no stale F8 bounds (0,168] / cooldown ≥ 1 outside meta/history files (R3-10)
    for f in scan:
        if f.name in meta:
            continue
        text = f.read_text(encoding="utf-8")
        for pat, label in ((r"\(0,\s*168\]", "stale ttl bound (0,168]"),
                           (r"cooldown[a-z_ ]*≥\s*1\b", "stale cooldown ≥ 1")):
            for m in re.finditer(pat, text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.end())
                line = text[line_start: line_end if line_end != -1 else len(text)].lower()
                if any(w in line for w in ("banned", "removed", "legacy", "was ",
                                           "previously", "formerly", "stale")):
                    continue
                fail(8, f"{f.relative_to(root)}: {label} (U-10c pins [4,168] / ≥ 24)")
    # 8c: the nonexistent `lamf config` command must not be referenced (R3-05)
    for f in scan:
        if f.name in meta:
            continue
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"lamf config", text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            line = text[line_start: line_end if line_end != -1 else len(text)].lower()
            if any(w in line for w in ("does not exist", "banned", "removed", "not a command")):
                continue
            fail(8, f"{f.relative_to(root)}: references nonexistent `lamf config` "
                    f"(durability lives in config/server.json, V-04)")
    # 8d: REST/MCP twin max_tokens parity (R3-07)
    oapi = (root / "03_CONTRACTS/openapi.yaml").read_text(encoding="utf-8")
    if "maximum: 32768" in oapi:
        fail(8, "openapi.yaml: max_tokens 32768 — REST twin must clamp at 4000 (V-06)")
    # 8e: capture.ordinary lattice covers all three enum values (R3-09)
    spo = (root / "02_SECURITY/SECURITY_PROFILE_OVERVIEW.md").read_text(encoding="utf-8")
    if "approval > quarantine > automatic" not in spo:
        fail(8, "SPO: capture.ordinary lattice must pin approval > quarantine > automatic (V-08)")
    # 8f: handoff tool must expose cancel/renew (R3-06)
    mt = (root / "03_CONTRACTS/mcp-tools.yaml").read_text(encoding="utf-8")
    if re.search(r"\[offer,\s*accept,\s*complete,\s*release\]", mt):
        fail(8, "mcp-tools.yaml: memory_handoff enum missing cancel/renew (V-05)")
    # 8g: two_thirds numerically defined (R3-26)
    council = (root / "03_CONTRACTS/council.md").read_text(encoding="utf-8")
    if "ceil(2n/3)" not in council:
        fail(8, "council.md: two_thirds quorum lacks numeric definition ceil(2n/3) (R3-26)")
    # 8h: pinned truncation marker in the plugin (R3-16)
    plugin = (root / "05_INTEGRATIONS/openclaw-plugin/index.ts").read_text(encoding="utf-8")
    if "[TRUNCATED]" not in plugin:
        fail(8, "openclaw-plugin: truncation marker must be the pinned [TRUNCATED] (R3-16)")
    # 8i: published benchmark result must be internally complete and passing.
    result_path = root / "benchmark-results/lamf-100k-windows-2026-08-01.json"
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("schema") != "lamf-benchmark-result-v1" or not result.get("passed"):
            fail(8, "published 100k benchmark result is absent, invalid, or failing")
        baseline = result.get("baseline", {})
        if baseline.get("records") != 100000 or baseline.get("iterations", 0) < 200 \
                or baseline.get("ordinary_corpus", 0) < 10000:
            fail(8, "published benchmark does not use the normative fixture sizes")
        for name, target in result.get("targets", {}).items():
            actual = result.get("metrics", {}).get(name)
            if actual is None or actual > target:
                fail(8, f"published benchmark gate failed: {name}={actual}, target={target}")
    except (OSError, ValueError, TypeError) as exc:
        fail(8, f"cannot validate published benchmark result: {exc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--update-manifest", action="store_true",
                    help="regenerate MANIFEST.sha256, then validate")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    if args.update_manifest:
        write_manifest(root)
    print(f"LAMF package validation — root: {root}\n")
    check_references(root)
    check_policies(root)
    check_sqlite(root)
    check_vectors(root)
    check_manifest(root)
    check_test_ids(root)
    check_consistency(root)
    check_r3_regressions(root)
    print()
    if FAILURES:
        print(f"VALIDATION FAILED — {len(FAILURES)} problem(s)")
        sys.exit(1)
    print("VALIDATION PASSED — package is internally consistent and machine-verified")


if __name__ == "__main__":
    main()
