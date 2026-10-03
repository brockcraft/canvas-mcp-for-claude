# Changelog

## 0.1.0 (2026-10-02)

First public release.

- MCP server with three tools: `canvas_get`, `canvas_write`, `canvas_upload_file`.
- Token stored in macOS Keychain (service `canvas-api`), never returned to Claude.
- Requests, pagination links and redirects limited to the configured Canvas host.
- `scripts/setup.sh` asks for the Canvas host, installs to `~/.canvas-mcp`, stores the token and checks the connection.
- `scripts/add_to_config.py` adds the connector to the Claude desktop config, with a backup, and sets `CANVAS_HOST` for non-default hosts.
- `skill/canvas-api/SKILL.md` with working rules for Claude.
