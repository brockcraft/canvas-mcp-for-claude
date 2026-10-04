# Changelog

## 1.4.0 (2026-10-03)

**The separate skill is retired. Installing the extension is now the whole setup.**

- The request patterns that lived in the skill (pages, assignments, module items, announcements, calendar events, messages, submissions) and the rule for refused writes are now in the `canvas_write` tool description. Everything the skill said is built into the extension, and it applies in Claude Code too, since the tool descriptions travel with the server.
- Claude is now told to say in the chat what it is about to do (the course by name, the action and a short summary of the content) and wait for your go-ahead *before* the app's approval prompt appears, for the first write in a conversation and for anything on the "ask first" list.
- Removed `skill/canvas-api/` and the `canvas-api-skill.zip` release download. If you uploaded the skill earlier, you can delete it under Settings → Customize → Skills; leaving it does no harm.
- Tests keep the rules and patterns in the tool descriptions.

## 1.3.0 (2026-10-03)

- **The working rules now travel with the extension.** The essential rules from the skill are in the tool descriptions Claude receives: read before writing, create content unpublished, ask before deletes, publishing, grade or due-date changes, messages to students and bulk edits, verify each write's response before reporting success, and keep student data in the conversation. Installing or updating the extension is enough; the separate skill upload is now optional. (The skill still holds the longer workflows and examples.)
- Claude Desktop does not show an MCP server's `instructions` to the model in chat, so the rules live in the tool descriptions instead.
- Test that keeps those rules in the descriptions.

## 1.2.1 (2026-10-03)

The connector and extension code are unchanged. If you already have 1.2.0 installed, you only need the updated skill.

- **Skill:** Claude now verifies each write's response against what it asked for before reporting success (for example that an announcement really came back as `is_announcement: true`), and says so plainly if Canvas did something different. The skill also describes the Canvas extension as the normal install.
- Added `SECURITY.md` with private vulnerability reporting, bug and feature issue forms, and a GitHub Actions workflow that runs the tests on Python 3.10, 3.12 and 3.13, validates and builds the extension, and checks that the versions in the manifest, `pyproject.toml` and this file agree.
- README: a note about the install warning Claude Desktop shows for extensions from outside Anthropic's directory, a "Related projects" section, and badges.

## 1.2.0 (2026-10-03)

- **Canvas extension for Claude Desktop.** It now installs as a `.mcpb` extension: download it, double-click it, and enter your Canvas host and token in Claude Desktop. Claude Desktop keeps the token in your Mac's Keychain and manages the Python environment itself. This is now the recommended install; the setup script remains for Claude Code and for organizations that have turned extensions off.
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
