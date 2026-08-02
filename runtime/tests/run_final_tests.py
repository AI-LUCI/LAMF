#!/usr/bin/env python3
"""Run every deploy-level final test in an isolated real LAMF instance."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    runners = sorted(HERE.glob("final_*/run_final_test.py"))
    if not runners:
        raise SystemExit("no final test runners found")
    for runner in runners:
        marker = runner.with_name("FINAL_TEST.txt")
        expected_prefix = "I am the final test for "
        if not marker.exists() or not marker.read_text(encoding="utf-8").startswith(expected_prefix):
            raise SystemExit(f"missing required final-test marker: {marker}")
        print(f"RUN {runner.parent.name}: {marker.read_text(encoding='utf-8').strip()}")
        subprocess.run([sys.executable, str(runner)], check=True)
    print(f"FINAL TESTS PASSED: {len(runners)}/{len(runners)}")


if __name__ == "__main__":
    main()

