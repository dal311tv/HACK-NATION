#!/bin/zsh
# Start CRUCIBLE: Omnigent runtime + Lab Console, then open the console in the browser.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
export PYTHONPATH="$(pwd)"
echo "== Starting CRUCIBLE =="
echo "Restarting Omnigent so it can load the lab's policies..."
omnigent stop >/dev/null 2>&1
omnigent
echo ""
echo "Starting the Lab Console. Keep this window open while you use the lab."
echo "To shut everything down, run 'Stop CRUCIBLE.command'."
(sleep 3 && open "http://127.0.0.1:8765") &
uv run --python 3.12 scripts/lab_console.py
