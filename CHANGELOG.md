# Changelog

## 1.2.0 (2026-10-03)

- **Claude desktop extension.** The connector now installs as a `.mcpb` extension: download it, double-click it, and enter your Canvas host and token in Claude Desktop. Claude Desktop keeps the token in your Mac's Keychain and manages the Python environment itself. This is now the recommended install; the setup script remains for Claude Code and for organizations that have turned extensions off.
- The server also reads the token from the `CANVAS_API_TOKEN` environment variable (which the extension sets) before Keychain and `~/.canvas/token`.
- `scripts/build_mcpb.sh` builds the extension and a zip of the skill for release downloads.
- Tests for the token sources.
- README rewritten around the extension, with a section on what the connector can do and example prompts.

## 1.1.0 (2026-10-03)

**Breaking:** the Canvas host no longer defaults to `canvas.uw.edu`. You must set it, or every tool call fails with a message saying so.

- Set the host with the `CANVAS_HOST` environment variable (in the connector's `env` entry in the Claude config) or `host` in `~/.config/canvas-mcp/config.toml`. `CANVAS_HOST` wins if both are set.
- `setup.sh` now requires a host. `add_to_config.py` requires `--host` and always writes `CANVAS_HOST` into the config entry.
- **If you installed before 1.1.0 with the old default host:** re-run `python3 scripts/add_to_config.py --host your.canvas.host`, or add `"env": {"CANVAS_HOST": "your.canvas.host"}` to the `canvas` entry by hand, then restart Claude.

## 1.0.1 (2026-10-03)

- Audit log: `result_id` is now filled in for pages, which Canvas returns with `page_id` instead of `id`.

## 1.0.0 (2026-10-03)

**Breaking:** `canvas_write` and `canvas_upload_file` now require a `course` argument. Calls without it fail. Update the skill along with the connector (see "Updating" in the README).

- Course guard on every write: the `course` label or ID must resolve to exactly one of your courses, the path must belong to that course, and the course must be live (active teacher enrollment, not concluded, not `ARCHIVED:`, not in `deny_ids`). Refusals return `COURSE_NOT_FOUND`, `COURSE_AMBIGUOUS`, `COURSE_MISMATCH`, `COURSE_NOT_WRITABLE` or `UNSCOPED_WRITE`, with the candidate courses and an instruction to ask the user.
- The course is resolved for `files/:id`, `folders/:id`, `sections/:id` and `groups/:id` paths, and from `context_code` for `calendar_events` and `conversations`. `users/self/...` needs no course. Other paths without a course are refused.
- Every write result starts with a line naming the course, method, path and status.
- New read-only tool `canvas_courses` lists your courses with labels and whether each can be written to.
- Audit log of every write attempt, with key paths but no values, at `~/Library/Logs/canvas-mcp/writes.jsonl` (macOS) or `$XDG_STATE_HOME/canvas-mcp/writes.jsonl`.
- Optional config file `~/.config/canvas-mcp/config.toml` with `CANVAS_MCP_*` environment overrides: `writable_roles`, `archived_prefix`, `allow_ids`, `deny_ids`, `unscoped_allow_prefixes`, `course_cache_seconds`, `audit_log_path`.
- `setup.sh` installs `tomli` on Python 3.10.
- The connector no longer logs request URLs, which can include search terms (httpx INFO logging turned off).
- Tests with a mocked Canvas API in `tests/`.
- Skill: documents the `course` argument and tells the agent to ask rather than infer the course, and to use the live course list rather than stored IDs.

## 0.1.0 (2026-10-02)

First public release.

- MCP server with three tools: `canvas_get`, `canvas_write`, `canvas_upload_file`.
- Token stored in macOS Keychain (service `canvas-api`), never returned to Claude.
- Requests, pagination links and redirects limited to the configured Canvas host.
- `scripts/setup.sh` asks for the Canvas host, installs to `~/.canvas-mcp`, stores the token and checks the connection.
- `scripts/add_to_config.py` adds the connector to the Claude desktop config, with a backup, and sets `CANVAS_HOST` for non-default hosts.
- `skill/canvas-api/SKILL.md` with working rules for Claude.
