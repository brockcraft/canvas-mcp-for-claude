# Canvas Connector for Claude

A small local MCP connector that gives Claude access to the full Canvas LMS REST API with your personal access token. The token stays in macOS Keychain; Claude never sees it.

In practice, it lets you use Claude to edit your Canvas course content by asking in plain language: change due dates, publish or unpublish items, reorganize modules, attach rubrics, draft pages and more. See "What you can do with it" for examples.

Author: Brock Craft, Human Centered Design & Engineering, University of Washington

## What you can do with it

Ask Claude, in plain language, to read and change your Canvas courses: pages, assignments, modules, rubrics, dates, files, announcements and more. Claude does the clicking for you. You still approve each change, and every write goes only to the course you name (see "Course guard").

Example prompts (name the course, for example "ABC 101 Au26", or set it in the project's instructions):

- **Edit in bulk.** "In ABC 101 Au26, change every assignment due date to 10:00pm Pacific, keeping the same days."
- **Unpublish.** "Unpublish every assignment in ABC 101 Au26 with 'video' in its name."
- **Reorganize.** "Rename each module to start with the day of the week we meet. Use the dates and topics in my syllabus."
- **Rubrics.** "Create a rubric from this template and attach it to every assignment in the Projects group. Template: ..."
- **Find broken links.** "Run Canvas's link validator on ABC 101 Au26 and list the broken links. Suggest a replacement for each, but change nothing until I approve."
- **Draft content.** "Draft a Week 3 overview page from my syllabus. Leave it unpublished so I can review it."
- **Upload files.** "Upload ~/Documents/week3-slides.pdf to ABC 101 Au26 and add it to the Week 3 module."
- **Audit without changing anything.** "List every assignment with no due date or no points, and every module with nothing in it."

Reading is never restricted, so an audit like the last one is a good first try. For anything with many edits, ask Claude to list what it plans to change before it starts.

## Why it exists

Claude's sandboxed environments (Cowork and cloud sessions) send network traffic through an allowlist. At many institutions the Canvas host is not on that list, and administrators may not add it. Programs running on your own computer are not subject to that allowlist. This connector runs on your Mac as part of the Claude desktop app, so any Claude session linked to that Mac can reach Canvas through it.

```
Claude session  ──MCP──▶  connector on your Mac  ──HTTPS + token──▶  Canvas
                           (token read from Keychain)
```

## What Claude gets

A few general-purpose tools instead of one tool per endpoint. Claude picks endpoints from the [Canvas API documentation](https://canvas.instructure.com/doc/api/), so anything the API supports is available.

| Tool | Purpose |
|---|---|
| `canvas_get` | Any GET request, with optional automatic pagination |
| `canvas_courses` | Your courses, with which ones can be written to |
| `canvas_write` | Any POST, PUT, PATCH or DELETE request, for a named course |
| `canvas_upload_file` | Canvas's three-step file upload, from a file on your Mac, for a named course |

Every write names its course and goes through the course guard (see below).

## Security design

- The token is stored in macOS Keychain and read at request time. It is never returned to Claude, logged, or written to a file.
- Requests go only to the configured Canvas host. Requests, pagination links and redirects pointing anywhere else are refused.
- During file uploads, the storage server receives the file but not the token.
- `canvas_get` and `canvas_courses` are marked read-only, so the desktop app can allow them automatically while still asking before each write.
- Writes go only to the course they name, and only to live courses. Each attempt is recorded in a local audit log without any values.

## Requirements

- macOS with the Claude desktop app
- Python 3.10 or later (only for the setup script; Homebrew installs its own)
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

Install it one of two ways: with the setup script (easier; it asks for what it needs and does the rest) or with Homebrew (for people who already use it). For either, first get your Canvas access token (above) and know your Canvas host: the address you sign in to Canvas at, without `https://` (for example `canvas.example.edu`). **The connector has no default host, so you must give it yours.**

### Option 1: Setup script (easier)

1. Clone or download this repository and open a terminal in its folder.
2. Know your Canvas host: the address you sign in to Canvas at, without `https://` (for example `canvas.example.edu`). **The connector has no default host, so you must give it yours.** Run `bash scripts/setup.sh`. It asks for your Canvas host, installs the connector in `~/.canvas-mcp`, creates a Python environment (MCP SDK 1.x and httpx, plus tomli on Python 3.10), prompts for the token (input is hidden) and stores it in Keychain, then confirms Canvas responds with your name.
3. When asked, let it add the connector to the Claude desktop config. It backs up `claude_desktop_config.json` first. To do this step later, run `python3 scripts/add_to_config.py --host your.canvas.host`.
4. Quit the Claude desktop app (Cmd+Q) and reopen it.
5. Test it by asking Claude: "List the pages in Canvas course *course ID*."

### Option 2: Homebrew (macOS or Linux)

1. Install it:
   ```
   brew install brockcraft/canvas-mcp/canvas-mcp
   ```
   Use the full name: Homebrew 6 and later won't load formulae from third-party taps until you trust them, and installing by full name trusts only this one formula. If you tapped first and see "Refusing to load formula from untrusted tap", run `brew trust --formula brockcraft/canvas-mcp/canvas-mcp`. Homebrew puts the connector in its own private Python environment, so it doesn't touch your system Python.
2. Store your token in Keychain. Replace `canvas.example.edu` with your host. Input is hidden:
   ```
   security add-generic-password -s canvas-api -a canvas.example.edu -w
   ```
   On Linux, save the token to `~/.canvas/token` and run `chmod 600 ~/.canvas/token`.
3. Add the connector to the Claude desktop config. Print the full path to the installed command:
   ```
   echo "$(brew --prefix)/bin/canvas-mcp"
   ```
   Claude doesn't use your shell's `PATH`, so the config needs the full path. Open `~/Library/Application Support/Claude/claude_desktop_config.json` (or Settings → Developer → Edit Config) and add this under `mcpServers`, keeping any servers already there. Use your host, and the path printed above (shown here for Apple Silicon; on Intel Macs it is `/usr/local/bin/canvas-mcp`):
   ```json
   {
     "mcpServers": {
       "canvas": {
         "command": "/opt/homebrew/bin/canvas-mcp",
         "env": { "CANVAS_HOST": "canvas.example.edu" }
       }
     }
   }
   ```
4. Quit the Claude desktop app (Cmd+Q) and reopen it.
5. Test it by asking Claude: "List the pages in Canvas course *course ID*."

For Claude Code, use: `claude mcp add canvas -e CANVAS_HOST=canvas.example.edu -- "$(brew --prefix)/bin/canvas-mcp"`

The tap's source is at [brockcraft/homebrew-canvas-mcp](https://github.com/brockcraft/homebrew-canvas-mcp).

**Your Canvas host (required).** The connector will not run without one: every tool call fails with a message asking you to set it. Setup uses the host as the Keychain account label, and `add_to_config.py` writes `"env": {"CANVAS_HOST": "canvas.example.edu"}` into the connector's config entry. If you install another way (Homebrew, or editing the config by hand), set `CANVAS_HOST` in that `env` entry yourself, or set `host = "canvas.example.edu"` in `~/.config/canvas-mcp/config.toml`. `CANVAS_HOST` wins if both are set.

**Claude Code (terminal).** It uses its own config:
`claude mcp add canvas -e CANVAS_HOST=canvas.example.edu -- ~/.canvas-mcp/venv/bin/python ~/.canvas-mcp/canvas_mcp_server.py`
Replace `canvas.example.edu` with your host.

## Installing the skill

`skill/canvas-api/SKILL.md` sets working rules for Claude when it uses Canvas: name the course on every write and ask rather than guess when it isn't known, confirm the course before the first change, create content unpublished, and ask before deletions, grade changes, messages to students, and bulk edits.

- **Claude app:** open Settings → Customize → Skills, choose to upload a skill, and select `skill/canvas-api/SKILL.md` (or a zip of the `canvas-api` folder).
- **Installed with Homebrew:** the skill is at `$(brew --prefix canvas-mcp)/share/canvas-mcp/skill/canvas-api/SKILL.md`. Upload that file as above.
- **Claude Code:** copy the folder to your skills directory:
  `cp -R skill/canvas-api ~/.claude/skills/`

## Updating

**Homebrew:** run `brew update && brew upgrade canvas-mcp`, upload the skill again (it's at the path above), and quit and reopen Claude.

**Setup script:** to install a new version over an existing one:

1. Get the new code: `git pull` in your copy of this repository, or download it again.
2. Run `bash scripts/setup.sh`. Enter your Canvas host (or press Enter to keep the one in `CANVAS_HOST`), answer **N** when asked to replace the token (your Keychain entry is kept), and answer **N** to the config question unless your host changed. Upgrading from before 1.1.0? Your config needs a host now; see the CHANGELOG.
3. Update the skill as described in "Installing the skill".
4. Quit the Claude desktop app (Cmd+Q) and reopen it.

Check the CHANGELOG for breaking changes before updating. Version 1.0.0 added a required `course` argument to the write tools.

## Course guard

The connector can't tell which course you mean from a path like `courses/12345/pages/x`. An agent without context might pick a plausible course, reuse an old ID from notes, or confuse two terms of the same course. The course guard stops these mistakes before anything is sent to Canvas.

**What's checked.** `canvas_write` and `canvas_upload_file` take a required `course` argument: a label such as `"ABC 101 Au26"`, `"abc 101 autumn 2026"` or `"ABC 101 A Au 26"`, or a numeric course ID. Before sending a write, the connector:

1. Resolves `course` against your course list (cached for 10 minutes, and refreshed once before giving up). Labels match on subject, number and term, plus the section if you give one. Season names and abbreviations (Au, Aut, Autumn, Fall and so on) and 2- or 4-digit years are interchangeable. A label without a term works only if it matches a single course. An exact course code or full course name also works. The label must match exactly one course.
2. Works out which course the path targets. `courses/:id/...` names it directly. For `files/:id`, `folders/:id`, `sections/:id` and `groups/:id`, the connector looks up the owner. For `calendar_events` and `conversations`, it reads `context_code` from the body. `users/self/...` needs no course. Any other path is refused unless it's in `unscoped_allow_prefixes`.
3. Refuses the write if the two courses differ.
4. Refuses the write unless the course is live: you have an active `teacher` enrollment (or another role in `writable_roles`), the course isn't concluded, its name doesn't start with `ARCHIVED:`, and its ID isn't in `deny_ids`. Courses in `allow_ids` skip these checks, except `deny_ids`.

Refusals explain the problem, list the candidate courses when the course is unknown or ambiguous, and tell the agent to ask you rather than guess. Nothing is sent to Canvas. Reads are never restricted.

Every write result starts with a line naming the course, so a mistake is visible in the conversation:

```
[ABC 101 A Au 26: Introduction to Things (12345), Autumn 2026] PUT courses/12345/pages/week-1 -> 200
```

**Term names.** Labels are matched against term names of the form "Season YYYY". If your institution names terms differently, use the term name exactly as Canvas shows it (for example `"ABC 101 2026-27 Academic Year"`), the full course code, or the course ID.

**Configuration.** All settings are optional. Put them in `~/.config/canvas-mcp/config.toml`, or set `CANVAS_MCP_<KEY>` environment variables (comma-separated for lists). Use `CANVAS_MCP_CONFIG` to point to a different file. For the desktop app, environment variables go in the connector's `env` entry in the Claude config, but `add_to_config.py` replaces that entry when it runs, so the config file is the safer place. Settings are read when the connector starts, so restart Claude after changing them. If the file is invalid, reads still work and every write is refused until it's fixed.

| Key | Default | Purpose |
|---|---|---|
| `host` | none (required) | Your Canvas host, e.g. `canvas.example.edu`; the `CANVAS_HOST` environment variable overrides it |
| `writable_roles` | `["teacher"]` | Enrollment types that may write, e.g. add `"ta"` or `"designer"` |
| `archived_prefix` | `"ARCHIVED:"` | Name prefix that marks a course read-only; `""` turns this check off |
| `allow_ids` | `[]` | Courses that are always writable, such as a sandbox course |
| `deny_ids` | `[]` | Courses that are never writable; overrides `allow_ids` |
| `unscoped_allow_prefixes` | `["users/self/"]` | Paths that may be written without a course |
| `course_cache_seconds` | `600` | How long the course list is cached |
| `audit_log_path` | see below | Where the audit log is written |

**Adding a sandbox course.** Sandbox and development courses often have no term, or a concluded one. Find the course ID (it's in the course URL, or ask Claude to list your courses including read-only ones) and add it to `allow_ids`. Then write to it using its ID or course code:

```toml
# ~/.config/canvas-mcp/config.toml
allow_ids = [12345]
```

**Audit log.** Each write attempt, including refusals, adds one JSON line to `~/Library/Logs/canvas-mcp/writes.jsonl` on macOS, or `$XDG_STATE_HOME/canvas-mcp/writes.jsonl` (default `~/.local/state/...`) elsewhere. A line records the time, outcome (`ok`, `refused` or `http_error`), error code, the course as passed and as resolved, method, path (without the query string), HTTP status, the body's key paths (for example `wiki_page.body`), and the ID and `html_url` of the result. It never records values, tokens or headers, and numeric keys such as student IDs in grade data are replaced with `*`. If the log can't be written, the write still goes ahead and the error is reported in Claude's MCP log.

## Recommended safeguards

- In the desktop app, set the read-only tools (`canvas_get`, `canvas_courses`) to always allow, and the write tools (`canvas_write`, `canvas_upload_file`) to ask each time. The course guard checks which course a write goes to; asking each time lets you check what is being written.
- Install the included skill (see above).
- In each Claude project that works on a course, state the course in the project's instructions, for example "Canvas course: ABC 101 Au26". The agent then passes it on every write without asking you.
- To keep an old or shared course from ever being changed, add its ID to `deny_ids`.
- The token carries your account's full permissions in every course you teach. Set an expiration, regenerate it periodically, and revoke it in Canvas if you think it has been exposed.
- Data Claude reads from Canvas, including student names, grades and submissions, enters the conversation. Check your institution's guidance on using AI tools with student records before working with them.

## Limitations

- The Mac must be awake with the Claude desktop app open.
- macOS only as written. On other systems the connector falls back to a token file at `~/.canvas/token` (set permissions to 600).
- Sessions opened before installation may need to refresh their tool list before the Canvas tools appear.
- Responses longer than 150,000 characters are truncated; narrow requests with `per_page`, `include[]` or `search_term`.
- Built on MCP Python SDK 1.x. Version 2 renamed `FastMCP`, so the setup script pins `mcp<2`.
- Writes to paths the course guard can't attribute to a course are refused, including replies to existing conversations (`conversations/:id/...`) and account-level paths. Add a prefix to `unscoped_allow_prefixes` only if you accept that those writes skip the course check.
- The course list comes from Canvas's default course listing. A course that isn't in it can't be written to.

## Uninstall

1. Remove the `"canvas"` entry from `mcpServers` in `~/Library/Application Support/Claude/claude_desktop_config.json` (Settings → Developer → Edit Config), then restart Claude. For Claude Code, run `claude mcp remove canvas`.
2. Delete the token from Keychain: `security delete-generic-password -s canvas-api`
3. Delete the installed connector: `rm -rf ~/.canvas-mcp` (setup script), or `brew uninstall canvas-mcp && brew untap brockcraft/canvas-mcp` (Homebrew)
4. Delete the optional config file and the audit log: `rm -rf ~/.config/canvas-mcp ~/Library/Logs/canvas-mcp`
5. Optionally, revoke the token in Canvas (Account → Settings → Approved Integrations) and remove the skill.

## Files

| File | Purpose |
|---|---|
| `server/canvas_mcp_server.py` | The connector |
| `scripts/setup.sh` | One-time install and Keychain setup |
| `scripts/add_to_config.py` | Adds the connector to the Claude desktop config, with a backup |
| `skill/canvas-api/SKILL.md` | Working rules for Claude when using Canvas |
| `tests/test_course_guard.py` | Course guard tests, against a mocked Canvas API |

## Running tests

The tests use a mocked Canvas API: no network access, no token, no Keychain. From the repository root, with the connector's Python environment:

```
~/.canvas-mcp/venv/bin/python -m unittest discover -s tests
```

## License

MIT. See [LICENSE](LICENSE).
