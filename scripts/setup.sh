#!/bin/bash
# One-time setup for the Canvas connector. Run from the repository root:  bash scripts/setup.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/.canvas-mcp"
DEFAULT_HOST="canvas.uw.edu"

# 0. Canvas host
read -p "Canvas host [${CANVAS_HOST:-$DEFAULT_HOST}]: " HOST
HOST="${HOST:-${CANVAS_HOST:-$DEFAULT_HOST}}"
HOST="${HOST#https://}"; HOST="${HOST#http://}"; HOST="${HOST%%/*}"
echo "Using Canvas host: $HOST"

mkdir -p "$DEST" && chmod 700 "$DEST"
cp "$ROOT/server/canvas_mcp_server.py" "$DEST/"

# 1. Python environment with the MCP library (needs Python 3.10+)
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v $c >/dev/null && $c -c 'import sys; sys.exit(sys.version_info < (3,10))'; then PY=$(command -v $c); break; fi
done
if [ -z "$PY" ]; then echo "Need Python 3.10+. Install with: brew install python"; exit 1; fi
"$PY" -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install -q --upgrade pip "mcp>=1.10,<2" httpx "tomli; python_version < '3.11'"
echo "Installed connector in $DEST"

# 2. Token into Keychain (you'll be prompted to paste it; input is hidden).
#    The Keychain account label is the Canvas host.
if security find-generic-password -s canvas-api >/dev/null 2>&1; then
  read -p "A Canvas token is already in Keychain. Replace it? [y/N] " a
  if [[ "$a" =~ ^[Yy] ]]; then
    security delete-generic-password -s canvas-api >/dev/null
    echo "Paste your NEW Canvas token at the prompt (twice):"
    security add-generic-password -s canvas-api -a "$HOST" -w
  fi
else
  echo "Paste your NEW Canvas token at the prompt (twice):"
  security add-generic-password -s canvas-api -a "$HOST" -w
fi

# 3. Quick check (prints your name, never the token)
CANVAS_HOST="$HOST" "$DEST/venv/bin/python" -c "
import sys, json; sys.path.insert(0, '$DEST')
import canvas_mcp_server as s
r = json.loads(s.canvas_get('users/self'))
print('Canvas check:', r['status'], r['data'].get('name') if isinstance(r['data'], dict) else r['data'])
"

# 4. Claude desktop config
read -p "Add the connector to the Claude desktop app config now? [Y/n] " a
if [[ ! "$a" =~ ^[Nn] ]]; then
  "$PY" "$ROOT/scripts/add_to_config.py" --host "$HOST"
else
  echo "To add it later, run:  python3 scripts/add_to_config.py --host $HOST"
fi
