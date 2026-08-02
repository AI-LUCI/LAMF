#!/bin/bash
# LAMF installer — macOS double-click entry point.
# A .command file opens in Terminal when double-clicked from Finder.
# It cds to its own folder so it works no matter where Finder launches it,
# then runs the normal installer and keeps the window open at the end.

cd "$(dirname "$0")" || exit 1

# Use `bash` explicitly so this still works if the archive lost exec bits.
bash ./install.sh "$@"
status=$?

echo
if [ $status -eq 0 ]; then
  echo "  LAMF is set up. You can close this window."
else
  echo "  The installer needs attention (scroll up — every problem lists its fix)."
  echo "  You can simply double-click this file again after fixing it."
fi
echo
read -r -p "  Press Return to close this window..."
exit $status
