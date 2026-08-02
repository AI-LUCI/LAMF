# Troubleshooting

- **Python is too old:** install Python 3.10+ and rerun the installer.
- **Virtual environment creation fails:** install the platform venv package (for example `python3-venv` on Debian/Ubuntu).
- **Agent cannot see LAMF:** restart it after configuration, verify the generated harness registration, then run the harness doctor.
- **Web UI asks for a token:** use the local operator access token, not the protected instance identity key. Do not print or commit either.
- **Memory is not recalled:** verify scope, active data directory, supersession state, and search terms. A missing result is not proof that data was deleted.
- **Optimization commands show no modules:** core is still operational. Install the separate optional pack or leave it absent.
- **Port 8734 is busy:** stop the conflicting local service or configure a reviewed alternative; do not expose LAMF publicly as a shortcut.

Bug reports must contain sanitized, synthetic reproductions only.
