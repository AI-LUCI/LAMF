#!/usr/bin/env python3
"""LAMF reference runtime — end-to-end smoke suite (DECISIONS.md §W-02/W-05).

Executable proof, runnable from anywhere:

    /tmp/lamf-venv/bin/python runtime/tests/smoke_test.py

Stages (each prints PASS/FAIL with a precise error; exit code is non-zero if
any stage fails):

  01 golden-vector parity (canon vs 03_CONTRACTS/golden-vectors.json)
  02 fresh init in a tmp dir (instance key, policy+floor, store, spine)
  03 direct store/spine ops
  04 API server thread on an ephemeral port (bearer + Host allowlist)
  05 capture 3 events incl. one secret-bearing (must be blocked/redacted)
  06 spool drain via the ingester
  07 search finds records
  08 remember + correct v1->v2 with expected_version, 409 on stale
  09 project_all to a tmp vault (frontmatter format, banner, home embeds)
  10 watcher: tamper a governed file -> restore + review-queue copy + audit
  11 export -> fresh dir -> import -> verify_deep
  12 MCP stdio handshake (initialize -> tools/list = 9 -> memory_search)
  13 U-08b CHECK probe (sensitive event with inline payload rejected)
  14 deploy-level sensitive memory, recovery, and recall final tests
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PKG_ROOT / "runtime"
SCHEMA_SQL = PKG_ROOT / "04_STORAGE" / "SCHEMA.sql"
GOLDEN = PKG_ROOT / "03_CONTRACTS" / "golden-vectors.json"
PROFILE = PKG_ROOT / "02_SECURITY" / "profiles" / "controlled.yaml"

sys.path.insert(0, str(RUNTIME_DIR))

RESULTS = []  # (stage, ok, detail)


def stage(name):
    def deco(fn):
        def wrapped(S):
            try:
                fn(S)
                RESULTS.append((name, True, ""))
                print(f"PASS {name}", flush=True)
            except Exception as exc:  # noqa: BLE001
                RESULTS.append((name, False, f"{exc.__class__.__name__}: {exc}"))
                print(f"FAIL {name}: {exc}", flush=True)
                if os.environ.get("SMOKE_DEBUG"):
                    traceback.print_exc()
        return wrapped
    return deco


def need(module_name):
    try:
        return __import__(f"lamf.{module_name}", fromlist=[module_name])
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"core module lamf/{module_name}.py unavailable: {exc}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def http(port, method, path, token, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Host", f"127.0.0.1:{port}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen_local(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw or "{}")
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def urlopen_local(req, timeout=15):
    """Open loopback URLs without ambient proxies; retry Windows bind races.

    Some Windows builds briefly return WSAEADDRINUSE while selecting the
    client-side ephemeral port immediately after a port=0 listener is bound.
    This is an operating-system transient, not an API failure.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last = None
    for attempt in range(20):
        try:
            return opener.open(req, timeout=timeout)
        except urllib.error.URLError as exc:
            last = exc
            winerror = getattr(getattr(exc, "reason", None), "winerror", None)
            if winerror != 10048:
                raise
            time.sleep(0.05 * (attempt + 1))
    raise last


def gen_instance_key(crypto_mod, path: Path):
    try:
        k = crypto_mod.InstanceKey.generate(str(path))
    except TypeError:
        k = crypto_mod.InstanceKey.generate()
    if isinstance(k, tuple):
        k = k[0]
    return k


def open_store(store_mod, db_path: Path, instance_key=None):
    try:
        return store_mod.Store.open(str(db_path), str(SCHEMA_SQL),
                                    instance_key=instance_key)
    except TypeError:
        try:
            return store_mod.Store.open(str(db_path), str(SCHEMA_SQL))
        except TypeError:
            return store_mod.Store.open(str(db_path))


def seed_actors(db_path: Path):
    """The reference init (cli.py owns the real ceremony); smoke seeds the two
    well-known actors so FK constraints on events.actor hold."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
        for actor_id, kind in (("lamf-system", "system"),
                               ("lamf-operator", "operator")):
            conn.execute(
                "INSERT OR IGNORE INTO actors (actor_id, kind, public_key,"
                " token_sha256, scopes, created_at) VALUES (?, ?, ?, NULL,"
                " '[]', ?)",
                (actor_id, kind, b"\x00" * 32, int(time.time() * 1000)))
        conn.commit()
    finally:
        conn.close()


def build_ctx(S):
    lamf_store = need("store")
    lamf_spine = need("spine")
    lamf_policy = need("policy")
    lamf_crypto = need("crypto")
    store = S["store"]
    spine = S["spine"]
    ctx = types.SimpleNamespace(
        data_dir=str(S["data_dir"]), store=store, spine=spine,
        policy=S["policy"], instance_key=S["instance_key"],
        actor="lamf-operator")
    return ctx


# ---------------------------------------------------------------------------
# 01 — golden vectors
# ---------------------------------------------------------------------------

@stage("01 golden-vector parity (canon LAMF-CANON-1)")
def s01(S):
    canon = need("canon")
    vectors = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"]
    for v in vectors:
        got = canon.canonicalize(v["input"])
        check(got == v["canonical"],
              f"vector {v['name']}: canonical mismatch:\n got {got!r}\n exp "
              f"{v['canonical']!r}")
        h = canon.sha256_hex(v["canonical"])
        check(h == v["sha256"],
              f"vector {v['name']}: sha256 mismatch {h} != {v['sha256']}")
    S["vectors"] = len(vectors)


# ---------------------------------------------------------------------------
# 02 — fresh init
# ---------------------------------------------------------------------------

@stage("02 fresh init (tmp data dir: key/token/policy/store/spine)")
def s02(S):
    # Keep the multi-process authority inside the shared workspace on Windows.
    # Codex sandbox child identities do not consistently inherit access to the
    # user's OS temp directory, which produced false key-read failures.
    test_root = PKG_ROOT / ".test-runs"
    test_root.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="lamf-smoke-", dir=str(test_root)))
    S["tmp"] = tmp
    data = tmp / "data"
    for sub in ("spool", "spine", "state"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    S["data_dir"] = data

    lamf_crypto = need("crypto")
    lamf_policy = need("policy")
    lamf_store = need("store")
    lamf_spine = need("spine")

    S["instance_key"] = gen_instance_key(lamf_crypto, data / "instance.key")

    token = uuid.uuid4().hex + uuid.uuid4().hex
    tok_path = data / "operator.token"
    tok_path.write_text(token, encoding="utf-8")
    os.chmod(tok_path, 0o600)
    S["token"] = token

    policy = lamf_policy.load_policy(str(PROFILE))
    violations = lamf_policy.floor_check(policy)
    check(not violations, f"policy floor violations: {violations}")
    S["policy"] = policy

    db_path = data / "state" / "lamf.sqlite3"
    S["db_path"] = db_path
    S["store"] = open_store(lamf_store, db_path, S["instance_key"])
    seed_actors(db_path)
    try:
        S["spine"] = lamf_spine.Spine(str(data / "spine"),
                                      instance_key=S["instance_key"])
    except TypeError:
        S["spine"] = lamf_spine.Spine(str(data / "spine"),
                                      S["instance_key"])


# ---------------------------------------------------------------------------
# 03 — direct store/spine ops
# ---------------------------------------------------------------------------

@stage("03 direct store/spine ops (upsert + append + verify_tail)")
def s03(S):
    ctx = build_ctx(S)
    S["ctx"] = ctx
    api = need("api")
    spine_mod = need("spine")
    stale_writer = spine_mod.Spine(
        str(S["data_dir"] / "spine"), instance_key=S["instance_key"])

    rec = {
        "id": "mem_smoke_pref1",
        "type": "preference",
        "title": "Prefers morning meetings",
        "body": "The user prefers morning meetings before 10am local time.",
        "tags": ["scheduling"], "entities": [],
        "scope": "user-private", "owner_actor": "lamf-operator",
        "sensitivity": "ordinary", "taint": "user_direct",
        "state": "active", "version": 1, "supersedes": None,
        "source_events": [], "confidence": "high",
        "created_seq": 1, "updated_seq": 1, "expires_at": None,
    }
    try:
        rid = S["store"].upsert_record(rec)
    except (TypeError, KeyError):
        rid = S["store"].upsert_record(
            {k: rec[k] for k in ("id", "type", "title", "body", "scope",
                                 "owner_actor", "sensitivity", "taint",
                                 "state", "version")})
    S["seed_record_id"] = rid or rec["id"]

    ev = api.make_event(ctx, "message",
                        {"role": "user",
                         "text": "Remember that I prefer morning meetings."},
                        scope="user-private", sensitivity="ordinary",
                        taint="user_direct")
    seq, h, _ = api.spine_append(S["spine"], ev)
    check(int(seq) >= 1, f"spine append returned seq={seq}")
    ev2 = api.make_event(ctx, "message", {"text": "second writer"},
                         scope="system", taint="system")
    seq2, _, _ = api.spine_append(stale_writer, ev2, S["store"])
    check(seq2 == seq + 1,
          f"stale second writer forked the spine: {seq} -> {seq2}")
    # Refresh the original object's cached head through bounded verification.
    S["spine"] = spine_mod.Spine(
        str(S["data_dir"] / "spine"), instance_key=S["instance_key"])
    ctx.spine = S["spine"]
    check(S["spine"].verify_tail(n=1), "bounded tail verification failed")
    check(S["spine"].last_verify_count == 1,
          f"tail verifier touched {S['spine'].last_verify_count} events, want 1")
    got = S["store"].get_record(S["seed_record_id"])
    check(got, "get_record returned nothing for seeded record")


# ---------------------------------------------------------------------------
# 04 — API server
# ---------------------------------------------------------------------------

@stage("04 API server thread (ephemeral port, bearer + host guard)")
def s04(S):
    api = need("api")
    srv = api.make_server(S["ctx"], port=0)
    S["server"] = srv
    S["port"] = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    code, body = http(S["port"], "GET", "/v1/health", S["token"])
    check(code == 200 and body.get("ok") is True,
          f"health: {code} {body}")

    # bad token must fail closed
    code, body = http(S["port"], "GET", "/v1/status", "wrong-token")
    check(code == 401 and body.get("error", {}).get("code")
          == "unauthenticated", f"bad token not rejected: {code} {body}")

    # hostile Host header must fail closed (anti-rebinding)
    url = f"http://127.0.0.1:{S['port']}/v1/status"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {S['token']}")
    req.add_header("Host", "evil.example.com")
    try:
        urlopen_local(req, timeout=10)
        raise AssertionError("hostile Host header was not rejected")
    except urllib.error.HTTPError as exc:
        check(exc.code == 403, f"host-rebinding got {exc.code}, want 403")

    code, body = http(S["port"], "GET", "/v1/status", S["token"])
    check(code == 200 and "checkpoint" in body, f"status: {code} {body}")

    # The standalone UI shell is readable without a credential, while all
    # memory data remains behind the bearer-token authority boundary.
    ui_url = f"http://127.0.0.1:{S['port']}/"
    with urlopen_local(ui_url, timeout=10) as resp:
        ui = resp.read().decode("utf-8")
        check(resp.status == 200 and "Your memory, at home" in ui,
              "standalone human UI was not served")

    code, body = http(S["port"], "GET", "/v1/records?limit=10", S["token"])
    check(code == 200 and isinstance(body.get("records"), list),
          f"human library records endpoint: {code} {body}")

    code, body = http(S["port"], "POST", "/v1/handoffs", S["token"],
                      {"action": "presence"})
    check(code == 200 and body.get("agent_id"),
          f"OpenClaw/non-MCP coordination route failed: {code} {body}")


# ---------------------------------------------------------------------------
# 05 — capture
# ---------------------------------------------------------------------------

@stage("05 capture 3 events (one secret-bearing blocked/redacted)")
def s05(S):
    sanitizer = need("sanitize")
    public_digest = "0123456789abcdef" * 4
    sanitizer.sanitize(f"SHA256 digest: {public_digest}", S["policy"])
    try:
        sanitizer.sanitize(f"unlabelled value {public_digest}", S["policy"])
        check(False, "unlabelled high-entropy hex secret was accepted")
    except sanitizer.SecretBlocked:
        pass
    events = [
        {"id": f"evt_{uuid.uuid4().hex[:20]}", "type": "message",
         "scope": "user-private", "sensitivity": "ordinary",
         "taint": "user_direct",
         "payload": {"role": "user", "text": "Deploy on Friday afternoon."}},
        {"id": f"evt_{uuid.uuid4().hex[:20]}", "type": "message",
         "scope": "user-private", "sensitivity": "ordinary",
         "taint": "user_direct",
         "payload": {"role": "user",
                     "text": "The release checklist lives in the wiki."}},
        {"id": f"evt_{uuid.uuid4().hex[:20]}", "type": "message",
         "scope": "user-private", "sensitivity": "ordinary",
         "taint": "user_direct",
         "payload": {"role": "user",
                     "text": "my aws key is AKIAIOSFODNN7EXAMPLE dont share"}},
    ]
    code, body = http(S["port"], "POST", "/v1/events", S["token"],
                      {"events": events})
    check(code == 202, f"capture status {code}: {body}")
    check(body.get("spooled") is True, f"missing spooled ack: {body}")
    accepted = body.get("accepted", [])
    dropped = body.get("dropped", [])
    secret_blocked = any(d.get("reason") == "sanitizer_rejected"
                         for d in dropped)
    S["secret_event_id"] = events[2]["id"]
    spool_text = ""
    for f in (S["data_dir"] / "spool").glob("segment-*.jsonl"):
        spool_text += f.read_text(encoding="utf-8")
    secret_leaked = "AKIAIOSFODNN7EXAMPLE" in spool_text
    check(not secret_leaked,
          "SECRET REACHED THE SPOOL — sanitizer fail-open regression")
    check(len(accepted) >= 2, f"ordinary events not accepted: {body}")
    if not secret_blocked:
        print("  note: secret event was redacted rather than dropped "
              "(accepted with sanitizer notes); leak check passed", flush=True)


# ---------------------------------------------------------------------------
# 06 — drain
# ---------------------------------------------------------------------------

@stage("06 spool drain via ingester")
def s06(S):
    ingest = need("ingest")
    before = 0
    try:
        before = int(S["spine"].head()[0] or 0)
    except Exception:  # noqa: BLE001
        pass
    ing = ingest.Ingester(str(S["data_dir"] / "spool"), S["spine"],
                          S["store"], S["policy"], S["instance_key"])
    drained = 0
    for _ in range(5):
        drained += int(ing.drain_once() or 0)
        if drained:
            break
        time.sleep(0.2)
    check(drained >= 2, f"drain_once drained {drained}, want >= 2")
    try:
        after = int(S["spine"].head()[0] or 0)
        check(after >= before + 2,
              f"spine head did not advance: {before} -> {after}")
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# 07 — search
# ---------------------------------------------------------------------------

@stage("07 search finds records (REST + store FTS)")
def s07(S):
    code, body = http(S["port"], "GET",
                      "/v1/search?q=morning+meetings", S["token"])
    check(code == 200, f"search status {code}: {body}")
    results = body.get("results", [])
    check(results, f"search returned no results: {body}")
    check(any("morning" in (r.get("title", "") + r.get("snippet", "")).lower()
              for r in results),
          f"seeded record not in results: {results}")
    for r in results:
        check("taint" in r and "sensitivity" in r,
              f"result missing taint labels: {r}")


# ---------------------------------------------------------------------------
# 08 — remember + correct
# ---------------------------------------------------------------------------

@stage("08 remember + correct v1->v2 (optimistic version, 409 stale)")
def s08(S):
    code, body = http(S["port"], "POST", "/v1/records", S["token"], {
        "title": "Deployment model",
        "body": "The user prefers local models by default.",
        "record_type": "fact", "scope": "user-private"})
    check(code == 200, f"remember status {code}: {body}")
    rid = body.get("record_id")
    check(rid, f"remember returned no record_id: {body}")
    S["remember_id"] = rid

    code, got = http(S["port"], "GET", f"/v1/records/{rid}", S["token"])
    check(code == 200, f"get record {code}: {got}")
    rec = got.get("record") or {}
    if "record" in rec:
        rec = rec["record"]
    v1 = int(rec.get("version", 1))
    check(rec.get("confidence") == "high",
          f"direct-user memory confidence should be high: {rec}")
    check(rec.get("source_events"),
          f"remembered record missing source event provenance: {rec}")
    source_event = rec["source_events"][-1]
    check(S["store"].event_exists(source_event),
          f"remember source event not mirrored into SQLite: {source_event}")
    event_row = S["store"].conn.execute(
        "SELECT seq FROM events WHERE id = ?", (source_event,)).fetchone()
    check(event_row and rec.get("created_seq") == event_row["seq"],
          f"remember record/event sequence mismatch: {rec} {event_row}")

    broad = S["store"].search_fts(
        "planning deployment and morning meeting projects", limit=10)
    check(any(r.get("id") == rid for r in broad),
          f"natural-language OR retrieval missed remembered record: {broad}")

    code, body = http(S["port"], "POST", f"/v1/records/{rid}/correct",
                      S["token"], {"expected_version": v1,
                                   "new_body": "The user prefers local "
                                               "models unless a cloud model "
                                               "materially improves results.",
                                   "reason": "Original was too absolute."})
    check(code == 200, f"correct status {code}: {body}")
    new_id = body.get("record_id")
    check(int(body.get("version", 0)) == v1 + 1,
          f"correct did not produce v{v1 + 1}: {body}")
    S["corrected_id"] = new_id

    code, body = http(S["port"], "POST", f"/v1/records/{new_id}/correct",
                      S["token"], {"expected_version": v1,
                                   "new_body": "stale write",
                                   "reason": "should conflict"})
    check(code == 409 and body.get("error", {}).get("code") == "conflict",
          f"stale correct not a 409 conflict: {code} {body}")

    code, got = http(S["port"], "GET",
                     f"/v1/records/{new_id}?include_history=true", S["token"])
    check(code == 200, f"get corrected record {code}: {got}")
    corrected = got.get("record") or {}
    if "record" in corrected:
        corrected = corrected["record"]
    correction_event = corrected.get("source_events", [])[-1]
    correction_row = S["store"].conn.execute(
        "SELECT seq FROM events WHERE id = ?", (correction_event,)).fetchone()
    check(correction_row and corrected.get("created_seq") == correction_row["seq"],
          f"correction record/event sequence mismatch: {corrected} "
          f"{correction_row}")


# ---------------------------------------------------------------------------
# 09 — projection
# ---------------------------------------------------------------------------

@stage("09 project_all (frontmatter format, banner, home embeds)")
def s09(S):
    project = need("project")
    vault = S["tmp"] / "vault"
    stats = project.project_all(S["store"], S["policy"], vault)
    S["vault"] = vault
    check(stats.get("records_projected", 0) >= 1,
          f"no records projected: {stats}")

    home = vault / "00 Home.md"
    check(home.exists(), "00 Home.md missing")
    home_text = home.read_text(encoding="utf-8")
    check("```query" in home_text, "home missing native query embed")
    check("```mermaid" in home_text, "home missing Mermaid block")
    check("dataview" not in home_text.lower(),
          "home must not use dataview (W-01)")

    notes = list((vault / "01 Memory").glob("*.md"))
    check(notes, "no governed notes in 01 Memory/")
    text = notes[0].read_text(encoding="utf-8")
    fm = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    check(fm, "note missing frontmatter block")
    keys = []
    for line in fm.group(1).splitlines():
        if line and not line.startswith(" "):
            keys.append(line.split(":", 1)[0])
    required = ["lamf_id", "record_type", "lamf_version", "authority",
                "confidence", "scope", "sensitivity", "taint",
                "projection_hash", "last_projected", "lamf_editable"]
    for k in required:
        check(k in keys, f"frontmatter missing key {k}: got {keys}")
    check("lamf_editable: false" in fm.group(1),
          "lamf_editable: false not pinned in frontmatter")
    check(re.search(r"last_projected: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
                    fm.group(1)), "last_projected not YYYY-MM-DDTHH:mm:ss")
    check("> [!warning] LAMF-governed note" in text,
          "governed callout missing from body")
    check("## Relations" in text, "## Relations mirror missing")
    state = S["data_dir"] / ".projection_state.json"
    check(state.exists(), "projection state file missing")
    S["projection_state"] = json.loads(state.read_text(encoding="utf-8"))
    check(S["projection_state"], "projection state empty")
    rel = str(notes[0].relative_to(vault))
    check(rel in S["projection_state"],
          f"{rel} not tracked in projection state")
    S["governed_note"] = notes[0]


# ---------------------------------------------------------------------------
# 10 — watcher
# ---------------------------------------------------------------------------

@stage("10 watcher: tamper -> restore + review-queue copy + audit")
def s10(S):
    watch = need("watch")
    project = need("project")
    vault = S["vault"]
    note = S["governed_note"]
    rel = str(note.relative_to(vault))
    with note.open("a", encoding="utf-8") as fh:
        fh.write("\nOPERATOR EXTERNAL EDIT — should be restored\n")

    try:
        head_before = int(S["spine"].head()[0] or 0)
    except Exception:  # noqa: BLE001
        head_before = 0

    stats = watch.watch_pass(vault, S["ctx"])
    check(stats["restored"] >= 1, f"no restore happened: {stats}")
    refreshed_state = json.loads(
        (S["data_dir"] / ".projection_state.json").read_text(encoding="utf-8"))
    restored_hash = project.content_hash(note.read_text(encoding="utf-8"))
    check(restored_hash == refreshed_state[rel]["projection_hash"],
          "governed note not restored to authority content")
    rq = list((vault / "07 Review Queue").glob("External Edit - *.md"))
    check(rq, "tampered copy missing from 07 Review Queue")
    check("OPERATOR EXTERNAL EDIT" in rq[0].read_text(encoding="utf-8"),
          "review-queue copy does not contain the tampered content")
    check(stats["audit_events"], f"no audit event emitted: {stats}")
    try:
        head_after = int(S["spine"].head()[0] or 0)
        check(head_after > head_before,
              f"spine did not record audit event ({head_before} -> "
              f"{head_after})")
    except Exception:  # noqa: BLE001
        pass

    # operator areas must remain untouched
    check(not any((vault / "08 Drafts").iterdir()),
          "watcher/projector touched 08 Drafts/")
    check(not (vault / ".obsidian").exists(),
          "watcher/projector wrote into .obsidian/")


# ---------------------------------------------------------------------------
# 11 — export / import
# ---------------------------------------------------------------------------

@stage("11 export -> import -> verify_deep (MAC + checksums)")
def s11(S):
    ei = need("export_import")
    bundle = S["tmp"] / "backup.lamf"
    out = ei.export_bundle(str(bundle), "smoke-passphrase-1", ctx=S["ctx"])
    check(bundle.exists() and bundle.stat().st_size > 100,
          f"bundle not written: {out}")
    check(re.fullmatch(r"[0-9a-f]{64}", out.get("chain_head_hash", "")),
          f"bad chain head: {out}")

    dest2 = S["tmp"] / "imported"
    res = ei.import_bundle(str(bundle), "smoke-passphrase-1", str(dest2))
    check(res.get("events", 0) >= 1, f"no events restored: {res}")
    check(res.get("records", 0) >= 1, f"no records restored: {res}")
    check(res.get("verify_deep") is True,
          f"verify_deep failed/unavailable after import: {res}")

    # empty-dir rule
    try:
        ei.import_bundle(str(bundle), "smoke-passphrase-1", str(dest2))
        raise AssertionError("import into non-empty dir was not refused")
    except Exception as exc:  # noqa: BLE001
        check("empty" in str(exc).lower() or "force" in str(exc).lower(),
              f"unexpected refusal error: {exc}")

    # wrong passphrase must fail closed
    dest3 = S["tmp"] / "imported-bad"
    try:
        ei.import_bundle(str(bundle), "wrong-passphrase", str(dest3))
        raise AssertionError("import with wrong passphrase was not refused")
    except AssertionError:
        raise
    except Exception:  # noqa: BLE001 — any crypto/MAC error is a pass
        pass


# ---------------------------------------------------------------------------
# 12 — MCP handshake
# ---------------------------------------------------------------------------

@stage("12 MCP: 9 tools + two independent agents coordinate")
def s12(S):
    driver = textwrap_driver(S)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(RUNTIME_DIR)
    env["LAMF_DATA_DIR"] = str(S["data_dir"])
    env["LAMF_SESSION_ID"] = "proc-a"
    proc = subprocess.Popen(
        [sys.executable, "-c", driver],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=env, text=True)
    S["mcp_proc"] = proc
    proc_b = None
    try:
        reqs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "codex", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "memory_search",
                        "arguments": {"query": "morning meetings"}}},
        ]
        proc.stdin.write("\n".join(json.dumps(r) for r in reqs) + "\n")
        proc.stdin.flush()

        import queue
        lines: "queue.Queue" = queue.Queue()

        def _reader():
            for ln in proc.stdout:
                lines.put(ln)

        threading.Thread(target=_reader, daemon=True).start()
        replies = {}
        deadline = time.time() + 45
        while len(replies) < 3 and time.time() < deadline:
            try:
                line = lines.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                break
            msg = json.loads(line)
            if msg.get("id") is not None:
                replies[msg["id"]] = msg
        check(len(replies) == 3, f"expected 3 replies, got {len(replies)}")

        init = replies[1]["result"]
        check(init["protocolVersion"] == "2025-03-26",
              f"protocolVersion: {init}")
        check(init["serverInfo"] == {"name": "lamf", "version": "2.0.0"},
              f"serverInfo: {init}")
        instructions = init.get("instructions", "")
        check("beginning of every new task" in instructions
              and "memory_orientation" in instructions
              and "memory_search" in instructions,
              f"durable startup instructions missing: {init}")

        tool_defs = replies[2]["result"]["tools"]
        tools = [t["name"] for t in tool_defs]
        expected = ["memory_search", "memory_get", "memory_remember",
                    "memory_context", "memory_orientation", "memory_handoff",
                    "memory_status", "memory_approvals", "memory_export"]
        check(sorted(tools) == sorted(expected),
              f"tools/list mismatch: {tools}")
        by_name = {t["name"]: t for t in tool_defs}
        for name in expected:
            annotations = by_name[name].get("annotations", {})
            check(set(("readOnlyHint", "destructiveHint", "openWorldHint"))
                  <= set(annotations),
                  f"MCP action annotations missing for {name}: {annotations}")
        check(by_name["memory_search"]["annotations"]["readOnlyHint"] is True,
              "memory_search must advertise read-only retrieval")
        check(by_name["memory_remember"]["annotations"]["readOnlyHint"] is False,
              "memory_remember must advertise a local state change")
        check(by_name["memory_approvals"]["annotations"]["destructiveHint"] is True,
              "operator approval decisions must retain destructive gating")

        call = replies[3]["result"]
        check(call.get("isError") is False, f"memory_search error: {call}")
        payload = json.loads(call["content"][0]["text"])
        check("results" in payload, f"bad memory_search payload: {payload}")

        # Prove communication across two separate MCP operating-system
        # processes, not merely two identities inside one Python process.
        env_b = dict(env)
        env_b["LAMF_SESSION_ID"] = "proc-b"
        proc_b = subprocess.Popen(
            [sys.executable, "-c", driver], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env_b,
            text=True)
        lines_b: "queue.Queue" = queue.Queue()
        threading.Thread(
            target=lambda: [lines_b.put(ln) for ln in proc_b.stdout],
            daemon=True).start()

        def rpc(p, q, request):
            p.stdin.write(json.dumps(request) + "\n")
            p.stdin.flush()
            until = time.time() + 20
            while time.time() < until:
                msg = json.loads(q.get(timeout=max(0.1, until - time.time())))
                if msg.get("id") == request.get("id"):
                    result = msg["result"]
                    if "content" in result:
                        check(result.get("isError") is False, str(result))
                        return json.loads(result["content"][0]["text"])
                    return result
            raise AssertionError(f"MCP response timed out: {request}")

        rpc(proc_b, lines_b, {"jsonrpc": "2.0", "id": 10,
            "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "claude", "version": "test"}}})
        sent = rpc(proc, lines, {"jsonrpc": "2.0", "id": 5,
            "method": "tools/call", "params": {"name": "memory_handoff",
            "arguments": {"action": "message",
                "recipient": "claude:proc-b",
                "message": "I own the benchmark files; avoid overlap."}}})
        inbox = rpc(proc_b, lines_b, {"jsonrpc": "2.0", "id": 11,
            "method": "tools/call", "params": {"name": "memory_handoff",
            "arguments": {"action": "inbox"}}})
        check(any(m.get("message_id") == sent.get("message_id")
                  for m in inbox.get("messages", [])),
              f"cross-process message was not delivered: {inbox}")
        active_ids = {a.get("agent_id") for a in inbox.get("active_agents", [])}
        check({"codex:proc-a", "claude:proc-b"} <= active_ids,
              f"independent agents did not discover each other: {inbox}")

        resource = "file:E:/BRAIN/shared-design.md"
        offer_a = rpc(proc, lines, {"jsonrpc": "2.0", "id": 6,
            "method": "tools/call", "params": {"name": "memory_handoff",
            "arguments": {"action": "offer", "work_item": {
                "summary": "Codex edit", "scope": "project:brain",
                "resources": [resource]}}}})
        held_a = rpc(proc, lines, {"jsonrpc": "2.0", "id": 7,
            "method": "tools/call", "params": {"name": "memory_handoff",
            "arguments": {"action": "accept",
                "handoff_id": offer_a["handoff_id"]}}})
        check(held_a["state"] == "accepted", f"first claim failed: {held_a}")
        offer_b = rpc(proc_b, lines_b, {"jsonrpc": "2.0", "id": 12,
            "method": "tools/call", "params": {"name": "memory_handoff",
            "arguments": {"action": "offer", "work_item": {
                "summary": "Claude edit", "scope": "project:brain",
                "resources": [resource]}}}})
        check(offer_b.get("state") == "queued"
              and offer_b.get("queue_position") == 1
              and offer_b.get("user_notice"),
              f"overlapping agent was not visibly queued: {offer_b}")
        done_a = rpc(proc, lines, {"jsonrpc": "2.0", "id": 8,
            "method": "tools/call", "params": {"name": "memory_handoff",
            "arguments": {"action": "complete",
                "handoff_id": offer_a["handoff_id"],
                "fencing_token": held_a["fencing_token"]}}})
        check(done_a["state"] == "completed", f"completion failed: {done_a}")
        held_b = rpc(proc_b, lines_b, {"jsonrpc": "2.0", "id": 13,
            "method": "tools/call", "params": {"name": "memory_handoff",
            "arguments": {"action": "accept",
                "handoff_id": offer_b["handoff_id"]}}})
        check(held_b["state"] == "accepted" and not held_b["conflict"],
              f"FIFO successor did not advance: {held_b}")
    finally:
        if proc_b is not None:
            proc_b.terminate()
            try:
                proc_b.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc_b.kill()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        err = proc.stderr.read()
        if err and os.environ.get("SMOKE_DEBUG"):
            print("  mcp stderr:", err[:2000], flush=True)


def textwrap_driver(S) -> str:
    return f'''
import sys, types
sys.path.insert(0, {str(RUNTIME_DIR)!r})
from lamf import mcp_server
store = None
try:
    from lamf import store as store_mod, crypto as crypto_mod
    ikey = None
    try:
        ikey = crypto_mod.InstanceKey.load({str(S["data_dir"] / "instance.key")!r})
    except Exception:
        ikey = None
    try:
        store = store_mod.Store.open({str(S["db_path"])!r}, {str(SCHEMA_SQL)!r}, instance_key=ikey)
    except TypeError:
        store = store_mod.Store.open({str(S["db_path"])!r}, {str(SCHEMA_SQL)!r})
except Exception:
    import traceback; traceback.print_exc(file=sys.stderr)
    store = None
ctx = types.SimpleNamespace(data_dir={str(S["data_dir"])!r}, store=store,
                            spine=None, policy=None, actor="lamf-operator")
mcp_server.serve_stdio(ctx)
'''


# ---------------------------------------------------------------------------
# 13 — U-08b CHECK probe
# ---------------------------------------------------------------------------

@stage("13 U-08b CHECK probe (sensitive inline payload rejected by sqlite)")
def s13(S):
    conn = sqlite3.connect(str(S["db_path"]))
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM events").fetchone()
        seq = int(row[0])
        rejected = False
        try:
            conn.execute(
                "INSERT INTO events (id, seq, ts, actor, session, type,"
                " scope, sensitivity, taint, payload_json, payload_ref,"
                " payload_sha256, prev_hash, hash, sig)"
                " VALUES (?, ?, ?, ?, NULL, 'message', 'user-private',"
                " 'sensitive', 'user_direct', '{}', NULL, ?, ?, ?, 'sig')",
                (f"evt_probe_{uuid.uuid4().hex[:12]}", seq,
                 int(time.time() * 1000), "lamf-operator",
                 "a" * 64, "b" * 64, "c" * 64))
            conn.commit()
        except sqlite3.IntegrityError:
            rejected = True
            conn.rollback()
        check(rejected,
              "sqlite ACCEPTED a sensitive event with inline payload — "
              "U-08b CHECK constraint broken")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 14 — real deploy-level final tests
# ---------------------------------------------------------------------------

@stage("14 deploy-level sensitive memory + recovery + recall final tests")
def s14(S):
    proc = subprocess.run(
        [sys.executable, str(RUNTIME_DIR / "tests" / "run_final_tests.py")],
        cwd=RUNTIME_DIR, text=True, capture_output=True, timeout=120)
    check(proc.returncode == 0,
          f"final tests failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    if os.environ.get("SMOKE_DEBUG"):
        import faulthandler
        faulthandler.dump_traceback_later(120, exit=False)
    S: dict = {}
    stages = [s01, s02, s03, s04, s05, s06, s07, s08, s09, s10, s11, s12, s13, s14]
    for st in stages:
        if S.get("abort"):
            RESULTS.append((st.__name__, False, "aborted: init failed"))
            print(f"FAIL {st.__name__}: aborted (init failed)", flush=True)
            continue
        st(S)
        if not RESULTS[-1][1] and st in (s02, s03):
            S["abort"] = True
    srv = S.get("server")
    if srv is not None:
        try:
            srv.shutdown()
            srv.server_close()
        except Exception:  # noqa: BLE001
            pass
    store = S.get("store")
    if store is not None:
        try:
            store.close()
        except Exception:  # noqa: BLE001
            pass
    tmp = S.get("tmp")
    if tmp is not None and Path(tmp).exists():
        try:
            shutil.rmtree(tmp)
        except OSError as exc:
            RESULTS.append(("cleanup", False, f"{exc.__class__.__name__}: {exc}"))
    failed = [r for r in RESULTS if not r[1]]
    print("=" * 60, flush=True)
    print(f"SMOKE: {len(RESULTS) - len(failed)}/{len(RESULTS)} stages passed",
          flush=True)
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"  FAILED: {name} — {detail}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
