#!/bin/bash
# Builds the Claude desktop extension: dist/canvas-mcp-<version>.mcpb
# Run from the repository root:  bash scripts/build_mcpb.sh
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$ROOT/build/mcpb"
VERSION="$(python3 -c "import json; print(json.load(open('$ROOT/mcpb/manifest.json'))['version'])")"
rm -rf "$STAGE" && mkdir -p "$STAGE/server" "$ROOT/dist"
cp "$ROOT/mcpb/manifest.json" "$ROOT/mcpb/icon.png" "$ROOT/mcpb/pyproject.toml" "$ROOT/mcpb/.mcpbignore" "$ROOT/LICENSE" "$STAGE/"
cp "$ROOT/server/canvas_mcp_server.py" "$STAGE/server/"
npx -y @anthropic-ai/mcpb validate "$STAGE/manifest.json"
npx -y @anthropic-ai/mcpb pack "$STAGE" "$ROOT/dist/canvas-mcp-$VERSION.mcpb"
# The skill is uploaded to Claude separately; zip the folder for release downloads.
rm -f "$ROOT/dist/canvas-api-skill.zip"
(cd "$ROOT/skill" && zip -qr "$ROOT/dist/canvas-api-skill.zip" canvas-api -x '*.DS_Store')
cp "$ROOT/dist/canvas-mcp-$VERSION.mcpb" "$ROOT/dist/canvas-mcp.mcpb"
echo "Built dist/canvas-mcp-$VERSION.mcpb, dist/canvas-mcp.mcpb (same file, stable name for the download link) and dist/canvas-api-skill.zip"
