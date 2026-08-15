#!/usr/bin/env bash
# Rebuild the venv if its imports fail — e.g. after an OS upgrade bumps the
# system Python minor version and orphans the old site-packages.
# Wired as ExecStartPre in both aquarium units. flock serialises the two services.
set -euo pipefail

VENV=/home/ian/tuya-env
DIR="$(cd "$(dirname "$0")" && pwd)"

exec 9>/tmp/aquarium-venv.lock
flock 9

if "$VENV/bin/python" -c 'import flask, pandas, requests, tinytuya, openpyxl' 2>/dev/null; then
    exit 0
fi

echo "aquarium: venv broken or missing — rebuilding from requirements.txt"
rm -rf "$VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$DIR/requirements.txt"
