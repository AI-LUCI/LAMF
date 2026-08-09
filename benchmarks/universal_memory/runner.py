#!/usr/bin/env python3
"""Run reproducible A/B memory benchmarks against disposable LAMF stores."""
from __future__ import annotations

import argparse, contextlib, hashlib, json, math, os, platform, statistics, sys, tempfile, time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "runtime"))
from lamf import api, cli  # noqa: E402


def percentile(values, q):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * q) - 1)]


def init_store(path):
    args = SimpleNamespace(data_dir=str(path), profile="controlled")
    with open(os.devnull, "w", encoding="utf-8") as sink, contextlib.redirect_stdout(sink):
        if cli.cmd_init(args) != 0:
            raise RuntimeError("could not initialize disposable LAMF store")
    return cli._open_ctx(path)


def record_for_lamf(item, seq, event_id):
    return {**item, "owner_actor":"lamf-operator", "taint":"system", "state":"active",
            "version":1, "source_events":[event_id], "confidence":"high",
            "created_seq":seq, "updated_seq":seq, "entities":[]}


class LamfBaseline:
    name = "lamf-baseline"
    def __init__(self, root): self.root, self.ctx = Path(root), None
    def load(self, records):
        self.ctx = init_store(self.root)
        self.ctx.actor = "lamf-operator"
        self.write_latencies = []
        for rec in records:
            started = time.perf_counter_ns()
            event = api.make_event(self.ctx, "import", {"record_id":rec["id"], "benchmark":True},
                                   scope=rec["scope"], sensitivity=rec["sensitivity"], taint="system")
            seq, _, event_id = api.spine_append(self.ctx.spine, event, self.ctx.store)
            self.ctx.store.upsert_record(record_for_lamf(rec, seq, event_id))
            self.write_latencies.append((time.perf_counter_ns()-started)/1e6)
    def search(self, query, k, filters):
        rows = self.ctx.store.search_fts(query, limit=k, filters=filters)
        return [{"source_ids":[r["id"]], "text":r["title"]+"\n"+r["body"],
                 "scope":r["scope"], "sensitivity":r["sensitivity"], "score":r["score"]}
                for r in rows]
    def close(self): self.ctx.store.close()
    def reopen(self): self.ctx = cli._open_ctx(self.root)


def tag_value(tags, prefix):
    found = [x[len(prefix):] for x in tags if x.startswith(prefix)]
    return found[0] if len(found) == 1 else None


class BudgetedConsolidation(LamfBaseline):
    """Read-only shadow consolidation; authoritative LAMF records stay intact."""
    name = "budgeted-consolidation-v1"
    def load(self, records):
        super().load(records)
        groups = {}
        for rec in records:
            key, value = tag_value(rec["tags"], "memory-key:"), tag_value(rec["tags"], "value:")
            identity = (key, value, rec["scope"], rec["sensitivity"], rec["type"])
            groups.setdefault(identity if key and value else (rec["id"],), []).append(rec)
        self.shadow = {}
        for members in groups.values():
            for rec in members:
                self.shadow[rec["id"]] = members
    def search(self, query, k, filters):
        raw = super().search(query, k * 3, filters)
        out, seen = [], set()
        for hit in raw:
            members = self.shadow[hit["source_ids"][0]]
            ids = tuple(sorted(r["id"] for r in members))
            if ids in seen: continue
            seen.add(ids)
            canonical = min(members, key=lambda r: (len(r["body"]), r["id"]))
            out.append({**hit, "source_ids":list(ids),
                        "text":canonical["title"]+"\n"+canonical["body"]})
            if len(out) == k: break
        return out
    def reopen(self):
        super().reopen()
        records = self.ctx.store.list_records(limit=200)
        groups = {}
        for rec in records:
            key, value = tag_value(rec["tags"], "memory-key:"), tag_value(rec["tags"], "value:")
            identity = (key, value, rec["scope"], rec["sensitivity"], rec["type"])
            groups.setdefault(identity if key and value else (rec["id"],), []).append(rec)
        self.shadow = {r["id"]: members for members in groups.values() for r in members}


def relevance_metrics(results, relevant, k):
    gains = [len(set(r["source_ids"]) & relevant) for r in results[:k]]
    found = set().union(*(set(r["source_ids"]) for r in results[:k])) if results else set()
    recall = len(found & relevant) / len(relevant) if relevant else 1.0
    precision = sum(1 for g in gains if g) / len(gains) if gains else (1.0 if not relevant else 0.0)
    rr = next((1/(i+1) for i,g in enumerate(gains) if g), 0.0)
    dcg = sum(g / math.log2(i+2) for i,g in enumerate(gains))
    ideal = sum(g / math.log2(i+2) for i,g in enumerate(sorted(gains, reverse=True)))
    return recall, precision, rr, dcg/ideal if ideal else 1.0


def evaluate(adapter, fixture, iterations, k):
    started = time.perf_counter(); adapter.load(fixture["records"]); load_s = time.perf_counter()-started
    rows, latencies = [], []
    for i in range(iterations):
        case = fixture["queries"][i % len(fixture["queries"])]
        start = time.perf_counter_ns()
        results = adapter.search(case["query"], k, {"scope":case["scope"], "sensitivity_max":"ordinary"})
        latencies.append((time.perf_counter_ns()-start)/1e6)
        if i < len(fixture["queries"]): rows.append((case, results))
    scores, bytes_, leakage, scope_errors, provenance, query_results = [], [], 0, 0, [], []
    false_merges = 0; contradiction_ok = True
    for case, results in rows:
        relevant = set(case["relevant"])
        if relevant: scores.append(relevance_metrics(results, relevant, k))
        bytes_.append(sum(len(r["text"].encode("utf-8")) for r in results))
        ids = set().union(*(set(r["source_ids"]) for r in results)) if results else set()
        query_results.append({"query":case["query"], "relevant":sorted(relevant),
                              "returned_source_ids":[r["source_ids"] for r in results],
                              "utf8_bytes":bytes_[-1]})
        leakage += len(ids & set(case.get("must_not_return", [])))
        scope_errors += sum(r["scope"] != case["scope"] for r in results)
        if relevant: provenance.append(len(ids & relevant)/len(relevant))
        for result in results:
            vals = {tag_value(next(r for r in fixture["records"] if r["id"] == rid)["tags"], "value:") for rid in result["source_ids"]}
            false_merges += len(vals) > 1
        for group in case.get("must_retain_groups", []): contradiction_ok &= bool(ids & set(group))
    before = [[r["source_ids"] for r in results] for _,results in rows]
    adapter.close(); adapter.reopen()
    after = [[r["source_ids"] for r in adapter.search(c["query"], k, {"scope":c["scope"],"sensitivity_max":"ordinary"})] for c,_ in rows]
    adapter.close()
    avg = lambda n: sum(x[n] for x in scores)/len(scores)
    return {"adapter":adapter.name, "load_records_per_second":len(fixture["records"])/load_s,
            "write_latency_ms":{"p50":statistics.median(adapter.write_latencies),"p95":percentile(adapter.write_latencies,.95),"p99":percentile(adapter.write_latencies,.99)},
            "search_latency_ms":{"p50":statistics.median(latencies),"p95":percentile(latencies,.95),"p99":percentile(latencies,.99)},
            "retrieval":{"recall_at_k":avg(0),"precision_at_k":avg(1),"mrr":avg(2),"ndcg_at_k":avg(3)},
            "context":{"mean_utf8_bytes":sum(bytes_)/len(bytes_),"mean_token_proxy":sum(math.ceil(x/4) for x in bytes_)/len(bytes_)},
            "governance":{"scope_isolation":scope_errors==0,"sensitive_leakage_rate":leakage/max(1,len(rows))},
            "fidelity":{"provenance_coverage":sum(provenance)/len(provenance),"false_consolidations":false_merges,"contradictions_retained":contradiction_ok},
            "durability":{"equivalent_after_reopen":before==after},
            "query_results":query_results}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--fixture",default=str(HERE/"fixtures/core-v1.json")); p.add_argument("--iterations",type=int,default=250); p.add_argument("--k",type=int,default=5); p.add_argument("--seed",type=int,default=20260809); p.add_argument("--output")
    a=p.parse_args(); raw=Path(a.fixture).read_bytes(); fixture=json.loads(raw)
    with tempfile.TemporaryDirectory(prefix="umb-") as tmp:
        base=evaluate(LamfBaseline(Path(tmp)/"base"),fixture,a.iterations,a.k)
        candidate=evaluate(BudgetedConsolidation(Path(tmp)/"candidate"),fixture,a.iterations,a.k)
    quality=lambda x: x["retrieval"]["recall_at_k"]==1 and x["governance"]["scope_isolation"] and x["governance"]["sensitive_leakage_rate"]==0 and x["fidelity"]["provenance_coverage"]==1 and x["fidelity"]["false_consolidations"]==0 and x["fidelity"]["contradictions_retained"] and x["durability"]["equivalent_after_reopen"]
    result={"schema":"umb-result-v1","fixture_sha256":hashlib.sha256(raw).hexdigest(),"seed":a.seed,"iterations":a.iterations,"k":a.k,"environment":{"os":platform.platform(),"python":platform.python_version(),"cpu_count":os.cpu_count()},"baseline":base,"candidate":candidate,
            "comparison":{"context_bytes_change_percent":100*(candidate["context"]["mean_utf8_bytes"]/base["context"]["mean_utf8_bytes"]-1),"p95_latency_change_percent":100*(candidate["search_latency_ms"]["p95"]/base["search_latency_ms"]["p95"]-1),"quality_preserved":quality(base) and quality(candidate)}}
    text=json.dumps(result,indent=2)+"\n"; print(text,end="")
    if a.output: Path(a.output).write_text(text,encoding="utf-8")
    return 0 if result["comparison"]["quality_preserved"] else 1
if __name__=="__main__": raise SystemExit(main())
