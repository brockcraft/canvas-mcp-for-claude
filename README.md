# Canvas Connector for Claude

A small local MCP connector that gives Claude access to the full Canvas LMS REST API with your personal access token. The token stays in macOS Keychain; Claude never sees it.

Author: Brock Craft, Human Centered Design & Engineering, University of Washington

## Why it exists

Claude's sandboxed environments (Cowork and cloud sessions) send network traffic through an allowlist. At many institutions the Canvas host is not on that list, and administrators may not add it. Programs running on your own computer are not subject to that allowlist. This connector runs on your Mac as part of the Claude desktop app, so any Claude session linked to that Mac can reach Canvas through it.

```
Claude session  ──MCP──▶  connector on your Mac  ──HTTPS + token──▶  Canvas
                           (token read from Keychain)
```

## What Claude gets

Three general-purpose tools instead of one tool per endpoint. Claude picks endpoints from the [Canvas API documentation](https://canvas.instructure.com/doc/api/), so anything the API supports is available.

| Tool | Purpose |
|---|---|
| `canvas_get` | Any GET request, with optional automatic pagination |
| `canvas_write` | Any POST, PUT, PATCH or DELETE request |
| `canvas_upload_file` | Canvas's three-step file upload, from a file on your Mac |

## Security design

- The token is stored in macOS Keychain and read at request time. It is never returned to Claude, logged, or written to a file.
- Requests go only to the configured Canvas host. Requests, pagination links and redirects pointing anywhere else are refused.
- During file uploads, the storage server receives the file but not the token.
- `canvas_get` is marked read-only, so the desktop app can allow it automatically while still asking before each `canvas_write`.

## Requirements

- macOS with the Claude desktop app
- Python 3.10 or later
- A Canvas access token (see "Getting a Canvas access token" below)

## Getting a Canvas access token

The connector signs in to Canvas with a personal access token, sometimes called an API key. You create it in Canvas yourself, and it acts with your account's permissions.

1. Sign in to Canvas in a web browser.
2. Click **Account** in the left navigation, then **Settings**.
3. Scroll to **Approved Integrations** and click **+ New Access Token**.
4. Enter a purpose, such as "Claude connector", and set an expiration date. A term's length is a reasonable choice.
5. Click **Generate Token**, then copy the token. Canvas shows it only once; if you lose it, delete it and generate a new one.
6. Run setup right away and paste the token when prompted. Don't save it in a file, email or chat, including a chat with Claude.

When the token expires, generate a new one and run `bash scripts/setup.sh` again to replace it in Keychain. To revoke a token, open the same Approved Integrations list and click the trash icon next to it.

Some institutions turn off personal access tokens. If you don't see **+ New Access Token**, ask your Canvas administrator.

## Setup

1. Clone or download this repository and open a terminal in its folder.
2. Run `bash scripts/setup.sh`. It asks for your Canvas host (default `canvas.uw.edu`), installs the connector in `~/.canvas-mcp`, creates a Python environment (MCP SDK 1.x and httpx), prompts for the token (input is hidden) and stores it in Keychain, then confirms Canvas responds with your name.
3. When asked, let it add the connector to the Claude desktop config. It backs up `claude_desktop_config.json` first. To do this step later, run `python3 scripts/add_to_config.py --host your.canvas.host`.
4. Quit the Claude desktop app (Cmd+Q) and reopen it.
5. Test it by asking Claude: "List the pages in Canvas course *course ID*."

**Other Canvas instances.** Enter your institution's host (for example `canvas.example.edu`) when setup asks. The host is used as the Keychain account label, and `add_to_config.py` adds `"env": {"CANVAS_HOST": "canvas.example.edu"}` to the connector's config entry. No `env` entry is added for the default host.

**Claude Code (terminal).** It uses its own config:
`claude mcp add canvas -- ~/.canvas-mcp/venv/bin/python ~/.canvas-mcp/canvas_mcp_server.py`
For a host other than the default, add `-e CANVAS_HOST=canvas.example.edu` before `--`.

## Installing the skill

`skill/canvas-api/SKILL.md` sets working rules for Claude when it uses Canvas: confirm the course before the first change, create content unpublished, and ask before deletions, grade changes, messages to students, and bulk edits.

- **Claude app:** open Settings → Capabilities → Skills, choose to upload a skill, and select `skill/canvas-api/SKILL.md` (or a zip of the `canvas-api` folder).
- **Claude Code:** copy the folder to your skills directory:
  `cp -R skill/canvas-api ~/.claude/skills/`

## Recommended safeguards

- In the desktop app, set `canvas_get` to always allow and `canvas_write` to ask each time.
- Install the included skill (see above).
- The token carries your account's full permissions in every course you teach. Set an expiration, regenerate it periodically, and revoke it in Canvas if you think it has been exposed.
- Data Claude reads from Canvas, including student names, grades and submissions, enters the conversation. Check your institution's guidance on using AI tools with student records before working with them.

## Limitations

- The Mac must be awake with the Claude desktop app open.
- macOS only as written. On other systems the connector falls back to a token file at `~/.canvas/token` (set permissions to 600).
- Sessions opened before installation may need to refresh their tool list before the Canvas tools appear.
- Responses longer than 150,000 characters are truncated; narrow requests with `per_page`, `include[]` or `search_term`.
- Built on MCP Python SDK 1.x. Version 2 renamed `FastMCP`, so the setup script pins `mcp<2`.

## Uninstall

1. Remove the `"canvas"` entry from `mcpServers` in `~/Library/Application Support/Claude/claude_desktop_config.json` (Settings → Developer → Edit Config), then restart Claude. For Claude Code, run `claude mcp remove canvas`.
2. Delete the token from Keychain: `security delete-generic-password -s canvas-api`
3. Delete the installed connector: `rm -rf ~/.canvas-mcp`
4. Optionally, revoke the token in Canvas (Account → Settings → Approved Integrations) and remove the skill.

## Files

| File | Purpose |
|---|---|
| `server/canvas_mcp_server.py` | The connector |
| `scripts/setup.sh` | One-time install and Keychain setup |
| `scripts/add_to_config.py` | Adds the connector to the Claude desktop config, with a backup |
| `skill/canvas-api/SKILL.md` | Working rules for Claude when using Canvas |

## License

MIT. See [LICENSE](LICENSE).
