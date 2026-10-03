# Changelog

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
