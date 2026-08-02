# Contributing

Start with `README.md`, `INSTALL.md`, `docs/ARCHITECTURE.md`, and `docs/THREAT_BOUNDARIES.md`. Small, focused changes with tests are easiest to review.

1. Fork and branch from `main`.
2. Use only synthetic test data. Never commit a LAMF data directory, database, token, key, log, vault, export, or personal information.
3. Run `python runtime/tests/run_final_tests.py`, `python runtime/tests/smoke_test.py`, `python runtime/tests/harness_test.py`, and `python runtime/tests/installer_scope_test.py` from the repository root.
4. If external code, research, documentation, benchmarks, workflows, or architectural ideas influenced the change, update `Credit.md`, identify the source and license, and explain whether material was copied or only synthesized.
5. Open a pull request using the template. Do not include private vulnerability details; use the process in `SECURITY.md`.

Good first contributions include documentation corrections, installer diagnostics, synthetic cross-platform fixtures, and reproducible demo improvements. By participating, you agree to follow `CODE_OF_CONDUCT.md`.
