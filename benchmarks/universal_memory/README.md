# Universal Memory Benchmark

This suite compares an unmodified LAMF baseline with isolated memory adapters
using the same disposable encrypted store and deterministic fixture.

```powershell
python benchmarks/universal_memory/runner.py --output benchmark-results/umb-latest.json
```

`budgeted-consolidation-v1` is the first experimental adapter. It builds a
read-only retrieval shadow from explicit `memory-key:` and `value:` metadata.
It never rewrites, supersedes, or merges authoritative records. Review the JSON
result and implementation before considering any product integration.
