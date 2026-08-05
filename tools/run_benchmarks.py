#!/usr/bin/env python3
"""Reproducible LAMF runtime benchmark gates from 08_BUILD_PLAN/BENCHMARKS.md.

The default run builds the normative 100,000-record fixture and executes at
least 200 measured operations per latency metric. Results are JSON so claims
can be checked by machines instead of copied into prose.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import random
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
sys.path.insert(0, str(RUNTIME))

from lamf import api, cli, ingest, sanitize  # noqa: E402


TARGETS = {
    "capture_ack_p95_ms": 200.0,
    "exact_id_lookup_p95_ms": 50.0,
    "exact_hash_lookup_p95_ms": 50.0,
    "warm_fts_p95_ms": 300.0,
    "capsule_p95_ms": 2000.0,
    "startup_events_verified_max": 1000,
    "sanitizer_false_positive_rate_max": 0.001,
}

TYPES = ("fact", "fact", "preference", "decision", "task",
         "procedure", "failure_lesson", "episode", "relationship",
         "handoff_record")


def p95_ms(samples_ns):
    ordered = sorted(samples_ns)
    index = max(0, int(len(ordered) * 0.95 + 0.999999) - 1)
    return ordered[index] / 1_000_000


def timed(fn, iterations):
    fn()  # unmeasured warm-up
    samples = []
    for _ in range(iterations):
        start = time.perf_counter_ns()
        fn()
        samples.append(time.perf_counter_ns() - start)
    return {"p50_ms": statistics.median(samples) / 1_000_000,
            "p95_ms": p95_ms(samples), "iterations": len(samples)}


def init_context(data_dir):
    args = SimpleNamespace(data_dir=str(data_dir), profile="controlled")
    with contextlib.redirect_stdout(open(os.devnull, "w", encoding="utf-8")):
        if cli.cmd_init(args) != 0:
            raise RuntimeError("LAMF benchmark instance initialization failed")
    ctx = cli._open_ctx(data_dir)
    ctx.actor = "lamf-operator"
    return ctx


def fixture_record(i, planted):
    rec_type = TYPES[i % len(TYPES)]
    scope = f"project:bench-{i % 4}"
    marker = f" target_{i:06d}" if planted else ""
    body = (f"Synthetic durable {rec_type} number {i}. The copper vessel uses "
            f"module {i % 997}, revision {i % 31}, and stable local storage."
            f"{marker}")
    return {
        "id": f"bench_{i:08d}", "type": rec_type,
        "title": f"Benchmark {rec_type} {i}", "body": body,
        "tags": [rec_type, f"group-{i % 100}"], "entities": [],
        "scope": scope, "owner_actor": "lamf-operator",
        "sensitivity": "ordinary", "taint": "user_direct",
        "state": "active", "version": 1, "source_events": [],
        "confidence": "high", "created_seq": 1, "updated_seq": 1,
    }


def build_records(ctx, count):
    stride = max(1, count // 200)
    planted = []
    started = time.perf_counter()
    for i in range(count):
        is_planted = i % stride == 0 and len(planted) < 200
        ctx.store.upsert_record(fixture_record(i, is_planted))
        if is_planted:
            planted.append((f"target_{i:06d}", f"bench_{i:08d}"))
    return planted, time.perf_counter() - started


def ordinary_corpus(size):
    templates = (
        "Meeting {i}: review module alpha and update the ordinary checklist.",
        "Documentation URL https://example.test/guides/{i}?mode=local is public.",
        "UUID near miss 123e4567-e89b-12d3-a456-{i:012d} belongs to a fixture.",
        "Digest {digest} identifies public test content and is not a credential.",
        "Code sample: function item_{i}(value) {{ return value + {n}; }}",
        "Base64 example SGVsbG8sIHdvcmxkIQ== appears in an encoding tutorial {i}.",
        "Marcel discussed the council schedule and LUCI architecture item {i}.",
    )
    for i in range(size):
        digest = hashlib.sha256(f"public-{i}".encode()).hexdigest()
        yield templates[i % len(templates)].format(i=i, n=i % 17, digest=digest)


def append_startup_events(ctx, count=1200):
    for i in range(count):
        ev = api.make_event(ctx, "message", {"text": f"startup fixture {i}"},
                            scope="project:benchmark", taint="system")
        api.spine_append(ctx.spine, ev, ctx.store)


def run(args):
    owned = args.data_dir is None
    data_dir = Path(args.data_dir) if args.data_dir else Path(
        tempfile.mkdtemp(prefix="lamf-benchmark-")) / "data"
    ctx = init_context(data_dir)
    rng = random.Random(args.seed)

    planted, build_seconds = build_records(ctx, args.records)
    ids = [f"bench_{rng.randrange(args.records):08d}" for _ in range(args.iterations)]
    id_iter = iter(ids * 2)
    id_lookup = timed(lambda: ctx.store.get_record(next(id_iter)), args.iterations)

    payload = b"LAMF exact content-addressed benchmark payload"
    owner_event = api.make_event(
        ctx, "message", {"text": "payload lookup owner"},
        scope="project:benchmark", taint="system")
    payload_hash = ctx.store.put_payload(
        payload, owner_event["id"], created_seq=1)
    owner_event["payload_ref"] = payload_hash
    owner_event["payload_sha256"] = payload_hash
    owner_event.pop("payload", None)
    api.spine_append(ctx.spine, owner_event, ctx.store)
    hash_lookup = timed(lambda: ctx.store.get_payload(payload_hash), args.iterations)

    queries = [planted[i % len(planted)][0] for i in range(args.iterations)]
    q_iter = iter(queries * 2)
    fts = timed(lambda: ctx.store.search_fts(next(q_iter), limit=10), args.iterations)
    misses = 0
    for query, expected in planted:
        if not any(r["id"] == expected for r in ctx.store.search_fts(query, limit=5)):
            misses += 1

    c_iter = iter(queries * 2)
    capsule = timed(lambda: api.build_capsule(
        ctx, next(c_iter), max_tokens=1200), args.iterations)

    capture_dir = data_dir / "benchmark-spool"
    capture_counter = iter(range(args.iterations * 2 + 1))
    capture = timed(lambda: ingest.capture_event(
        capture_dir, ctx.store,
        {"actor": "lamf-operator", "session": "benchmark", "type": "message",
         "scope": "project:benchmark", "sensitivity": "ordinary",
         "taint": "user_direct",
         "payload": {"text": f"ordinary capture {next(capture_counter)}"}},
        ctx.policy), args.iterations)

    append_startup_events(ctx)
    startup_start = time.perf_counter_ns()
    startup_ok = ctx.spine.verify_tail(1000)
    startup_ms = (time.perf_counter_ns() - startup_start) / 1_000_000

    false_positives = 0
    for text in ordinary_corpus(args.ordinary_corpus):
        try:
            sanitize.sanitize(text, ctx.policy)
        except sanitize.SecretBlocked:
            false_positives += 1
    fp_rate = false_positives / args.ordinary_corpus

    metrics = {
        "capture_ack_p95_ms": capture["p95_ms"],
        "exact_id_lookup_p95_ms": id_lookup["p95_ms"],
        "exact_hash_lookup_p95_ms": hash_lookup["p95_ms"],
        "warm_fts_p95_ms": fts["p95_ms"],
        "capsule_p95_ms": capsule["p95_ms"],
        "startup_events_verified_max": ctx.spine.last_verify_count,
        "sanitizer_false_positive_rate_max": fp_rate,
    }
    gates = {name: {"target": target, "actual": metrics[name],
                    "pass": metrics[name] <= target}
             for name, target in TARGETS.items()}
    result = {
        "schema": "lamf-benchmark-result-v1", "passed": all(
            item["pass"] for item in gates.values()) and startup_ok and misses == 0,
        "baseline": {"cpu": platform.processor() or os.environ.get(
            "PROCESSOR_IDENTIFIER", "unknown"), "cores": os.cpu_count(),
            "os": platform.platform(), "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version, "filesystem": "Windows local volume",
            "dataset_seed": args.seed, "records": args.records,
            "iterations": args.iterations, "ordinary_corpus": args.ordinary_corpus},
        "fixture_build_seconds": build_seconds, "retrieval_misses": misses,
        "startup_verify_ms": startup_ms, "startup_chain_ok": startup_ok,
        "sanitizer_false_positives": false_positives,
        "details": {"capture_ack": capture, "exact_id_lookup": id_lookup,
                    "exact_hash_lookup": hash_lookup, "warm_fts": fts,
                    "capsule": capsule},
        "gates": gates,
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    ctx.store.close()
    if owned and not args.keep:
        shutil.rmtree(data_dir.parent, ignore_errors=True)
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--ordinary-corpus", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260801)
    parser.add_argument("--data-dir")
    parser.add_argument("--output")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if args.records < 200 or args.iterations < 200 or args.ordinary_corpus < 10_000:
        parser.error("normative run requires >=200 records, >=200 iterations, and >=10000 corpus items")
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
