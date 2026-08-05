# Executed benchmark results

These are immutable machine-readable result snapshots produced by
`tools/run_benchmarks.py`. A result is comparable only when its baseline,
dataset size, seed, and iteration count are reported. Re-run the normative gate:

```text
python tools/run_benchmarks.py --records 100000 --iterations 200 --ordinary-corpus 10000 --output result.json
```

The harness exits non-zero when any target fails. Fixture build time is reported
but is not currently a pass/fail target.
