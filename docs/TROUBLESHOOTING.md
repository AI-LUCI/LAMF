# Troubleshooting

- **Python is too old:** install Python 3.10+ and rerun the installer.
- **Virtual environment creation fails:** install the platform venv package (for example `python3-venv` on Debian/Ubuntu).
- **Agent cannot see LAMF:** restart it after configuration, verify the generated harness registration, then run the harness doctor.
- **Web UI asks for a token:** use the local operator access token, not the protected instance identity key. Do not print or commit either.
- **Memory is not recalled:** verify scope, active data directory, supersession state, and search terms. A missing result is not proof that data was deleted.
- **Optimization commands show no modules:** core is still operational. Install the separate optional pack or leave it absent.
- **Port 8734 is busy:** stop the conflicting local service or configure a reviewed alternative; do not expose LAMF publicly as a shortcut.

Bug reports must contain sanitized, synthetic reproductions only.

## Privacy-safe issue report

Generate a small allowlist-only report from the repository root:

```bash
python installer/collect_issue_report.py --profile controlled --mode core --harness codex
```

Select only the public flags that describe the affected setup. The JSON report
contains the LAMF version, bounded platform and Python facts, those explicit
flags, and boolean dependency/layout checks. The helper does not accept or read
a LAMF data directory and does not enumerate environment variables or files.
It therefore excludes databases, payloads, tokens, keys, logs, vaults, exports,
absolute personal paths, and memory content by construction. Inspect the short
JSON output before attaching it to an issue. Use only synthetic text when
describing the steps that caused the problem.
