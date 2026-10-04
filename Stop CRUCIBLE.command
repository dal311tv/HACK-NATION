#!/bin/zsh
# Shut down CRUCIBLE: the Lab Console (and any run it started) and the Omnigent runtime.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
echo "== Stopping CRUCIBLE =="
pkill -INT -f "scripts/lab_console.py" && echo "Lab Console stopped." || echo "Lab Console was not running."
sleep 2
omnigent stop
echo "Done. You can close this window."
