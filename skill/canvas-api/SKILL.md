---
name: canvas-api
description: Read from and edit the user's Canvas LMS courses through the full Canvas REST API using the local Canvas connector tools.
---

# Canvas API

A local Canvas connector on the user's Mac exposes the whole Canvas REST API through three tools. Use them for any Canvas task: pages, assignments, modules, announcements, discussions, quizzes, files, rubrics, sections, enrollments, gradebook, analytics, calendar.

| Tool | Use for |
|---|---|
| `canvas_get(path, params, all_pages, max_pages)` | Any read. Set `all_pages=true` for lists. |
| `canvas_write(method, path, body, params)` | Any POST / PUT / PATCH / DELETE. JSON body with Canvas's nested names. |
| `canvas_upload_file(endpoint, local_path, parent_folder_path)` | Uploading a file from the user's Mac (absolute Mac path). |

The tools may appear with a prefix such as `mcp__remote-devices__canvas__`. If they are not in the tool list, refresh the MCP tool list once (or search deferred tools for "canvas") before concluding they are missing.

Paths are relative to `/api/v1`, e.g. `courses/12345/pages`. Endpoint reference: https://canvas.instructure.com/doc/api/ (fetch the relevant resource page when unsure of an endpoint or parameter name; do not guess).

If the tools are still missing, tell the user the Canvas connector is not running: the Mac must be awake with the Claude desktop app open and the `canvas` entry in its config. Do not try to reach Canvas from the shell, the browser, or with the token.

## Working rules

1. Confirm the course: GET `courses/:id` and state the course name before the first write in a session. `courses?enrollment_type=teacher&enrollment_state=active` lists the user's current courses.
2. Read before writing. GET the current object; for edits to existing content, show a short before/after summary.
3. New content is unpublished (`published: false`) unless the user says to publish.
4. Ask first, every time, before: any DELETE; publishing or unpublishing; changing grades, due dates or points on assignments with submissions; sending messages or posting announcements visible to students; changing enrollments or sections; bulk changes affecting more than about 10 objects (show the list first).
5. Prefer narrow reads: `per_page=100`, `include[]`, `search_term`, `only[]` and specific IDs. Responses over ~150k characters are truncated.
6. After writing, report what changed with the `html_url`.

## Common patterns

- Page: POST `courses/:id/pages` body `{"wiki_page": {"title": "...", "body": "<p>...</p>", "published": false}}`; edit with PUT `courses/:id/pages/:url_or_id`.
- Assignment: POST `courses/:id/assignments` body `{"assignment": {"name": "...", "points_possible": 10, "due_at": "2026-10-15T23:59:00-07:00", "submission_types": ["online_upload"], "published": false}}`.
- Module item: POST `courses/:id/modules/:module_id/items` body `{"module_item": {"type": "Page", "page_url": "..."}}`.
- Announcement (ask first): POST `courses/:id/discussion_topics` body `{"title": "...", "message": "<p>...</p>", "is_announcement": true, "published": false}`.
- Submissions: GET `courses/:id/assignments/:aid/submissions` with `include[]=user`.
- Dates use ISO 8601 with the local UTC offset.

Student data from Canvas stays in the conversation or in files the user asks for; never put it anywhere shareable without an explicit request.
