#!/usr/bin/env bash
# LAMF installer — macOS / Linux entry point.
# Thin wrapper: resolves its own directory and hands off to install.py,
# which does all the real work (and explains itself as it goes).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo
  echo "  LAMF needs Python 3.10 or newer, and we couldn't find it."
  if [ "$(uname -s)" = "Darwin" ]; then
    echo "  Install it with this one line (needs Homebrew, https://brew.sh):"
    echo "    brew install python@3.12"
  else
    echo "  Install it with the one line for your distribution:"
    echo "    Debian/Ubuntu : sudo apt update && sudo apt install -y python3 python3-venv"
    echo "    Fedora        : sudo dnf install -y python3"
    echo "    Arch          : sudo pacman -S --needed python"
  fi
  echo
  echo "  Then double-click / run this installer again."
  exit 1
fi

exec "$PY" "$DIR/install.py" "$@"
