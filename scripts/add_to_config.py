#!/usr/bin/env python3
"""Adds the Canvas connector to Claude's desktop config. Backs up the original first.

Usage: python3 scripts/add_to_config.py --host canvas.example.edu
"""
import argparse, json, os, shutil, sys
from datetime import datetime

ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
ap.add_argument("--host", default=os.environ.get("CANVAS_HOST"),
                help="your Canvas host, e.g. canvas.example.edu (required; or set CANVAS_HOST)")
host = (ap.parse_args().host or "").strip()
for prefix in ("https://", "http://"):
    if host.lower().startswith(prefix):
        host = host[len(prefix):]
host = host.split("/")[0]
if not host:
    ap.error("--host is required, e.g. --host canvas.example.edu")

cfg = os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")
home = os.path.expanduser("~")
entry = {
    "command": f"{home}/.canvas-mcp/venv/bin/python",
    "args": [f"{home}/.canvas-mcp/canvas_mcp_server.py"],
    "env": {"CANVAS_HOST": host},
}

data = {}
if os.path.exists(cfg):
    raw = open(cfg).read().strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            sys.exit(f"Your config file isn't valid JSON right now ({e}). Nothing was changed. "
                     "Undo any partial edits (Cmd+Z) and run this again.")
    backup = cfg + ".backup-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(cfg, backup)
    print("Backup saved:", backup)
else:
    os.makedirs(os.path.dirname(cfg), exist_ok=True)

data.setdefault("mcpServers", {})["canvas"] = entry
with open(cfg, "w") as f:
    json.dump(data, f, indent=2)
json.load(open(cfg))  # confirm it's valid
print(f"Added the Canvas connector for {host}. Servers now configured:", ", ".join(data["mcpServers"]))
print("Quit Claude completely (Cmd+Q) and reopen it.")
