#!/bin/bash
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
echo "Installing/checking GLUCOLAB dependencies..."
"$PY" -m pip install -r requirements.txt || { echo 'Dependencies could not be installed.'; read -r -p 'Press Enter to close...'; exit 1; }
echo "Open http://127.0.0.1:8000 in your browser. Keep this terminal open."
"$PY" app.py
read -r -p 'GLUCOLAB stopped. Press Enter to close...'
