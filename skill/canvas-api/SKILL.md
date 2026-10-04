---
name: canvas-api
description: Read from and edit the user's Canvas LMS courses through the full Canvas REST API using the local Canvas connector tools.
---

# Canvas API

A local Canvas connector on the user's Mac exposes the whole Canvas REST API through a few tools. Use them for any Canvas task: pages, assignments, modules, announcements, discussions, quizzes, files, rubrics, sections, enrollments, gradebook, analytics, calendar.

| Tool | Use for |
|---|---|
| `canvas_get(path, params, all_pages, max_pages)` | Any read. Set `all_pages=true` for lists. |
| `canvas_courses(include_readonly)` | The user's courses, with IDs, labels and whether each can be written to. |
| `canvas_write(course, method, path, body, params)` | Any POST / PUT / PATCH / DELETE. JSON body with Canvas's nested names. |
| `canvas_upload_file(course, endpoint, local_path, parent_folder_path)` | Uploading a file from the user's Mac (absolute Mac path). |

The tools may appear with a prefix such as `mcp__remote-devices__canvas__`. If they are not in the tool list, refresh the MCP tool list once (or search deferred tools for "canvas") before concluding they are missing.

Paths are relative to `/api/v1`, e.g. `courses/12345/pages`. Endpoint reference: https://canvas.instructure.com/doc/api/ (fetch the relevant resource page when unsure of an endpoint or parameter name; do not guess).

If the tools are still missing, tell the user the Canvas connector is not running: the Mac must be awake with the Claude desktop app open, and the Canvas extension (Settings → Extensions) installed and enabled, or the `canvas` entry present in the Claude config if it was installed with the setup script. Do not try to reach Canvas from the shell, the browser, or with the token.

## The `course` argument

Every write names its course. `course` is a label with subject, number and term, such as `"ABC 101 Au26"` or `"ABC 101 A Autumn 2026"`, or a numeric course ID. Use `"self"` for `users/self/...` paths. The connector refuses the write unless the path belongs to exactly that course and the course is live (active teaching enrollment, not concluded, not archived).

- **Know the course before writing; never infer it.** The course is established when the user names it in this conversation or the project's instructions state it (for example "Canvas course: ABC 101 Au26"). If neither is true, ask the user which course they mean. Do not pick the most recent course, the only one that looks plausible, or one from earlier work.
- **Resolve courses through the live list, not stored IDs.** Course IDs change when a course is rebuilt, and old IDs still resolve to dead copies. Pass the label the user gave. When you need an ID or a list to show the user, call `canvas_courses`. Don't reuse IDs from notes, files or memory.
- **Treat a refusal as a question for the user.** `REFUSED (COURSE_NOT_FOUND | COURSE_AMBIGUOUS | COURSE_MISMATCH | COURSE_NOT_WRITABLE | UNSCOPED_WRITE)` means stop and ask. Show the user the candidates from the message. Don't retry with a different course, path or label on your own.
- **Check the echo line.** Each write result starts with `[course name (id), term] METHOD path -> status`. Make sure it is the course the user meant before continuing.
- The user can make a sandbox course writable or protect a course with `allow_ids` and `deny_ids` in the connector config. Don't edit that config yourself.

Suggest that the user state the course in each Claude project's instructions, e.g. "Canvas course: ABC 101 Au26", so writes need no extra questions.

## Working rules

1. Confirm the course: state the course name before the first write in a session. `canvas_courses` lists the user's courses.
2. Read before writing. GET the current object; for edits to existing content, show a short before/after summary.
3. New content is unpublished (`published: false`) unless the user says to publish.
4. Ask first, every time, before: any DELETE; publishing or unpublishing; changing grades, due dates or points on assignments with submissions; sending messages or posting announcements visible to students; changing enrollments or sections; bulk changes affecting more than about 10 objects (show the list first).
5. Prefer narrow reads: `per_page=100`, `include[]`, `search_term`, `only[]` and specific IDs. Responses over ~150k characters are truncated.
6. Verify, then report. A `200` does not prove Canvas did what you asked: it can ignore fields it doesn't accept or the account isn't allowed to set, and quietly create something different. Compare the returned object with the request before saying it worked: for example `is_announcement` is `true` for an announcement (otherwise a plain discussion topic was created), `published` matches what you asked for, and dates and points match. If anything differs, tell the user exactly what happened and what now exists in the course; don't call it a success and don't silently retry or clean up. When it matches, report what changed with the `html_url`.

## Common patterns

- Page: `canvas_write(course="ABC 101 Au26", method="POST", path="courses/:id/pages", body={"wiki_page": {"title": "...", "body": "<p>...</p>", "published": false}})`; edit with PUT `courses/:id/pages/:url_or_id`.
- Assignment: POST `courses/:id/assignments` body `{"assignment": {"name": "...", "points_possible": 10, "due_at": "2026-10-15T23:59:00-07:00", "submission_types": ["online_upload"], "published": false}}`.
- Module item: POST `courses/:id/modules/:module_id/items` body `{"module_item": {"type": "Page", "page_url": "..."}}`.
- Announcement (ask first): POST `courses/:id/discussion_topics` body `{"title": "...", "message": "<p>...</p>", "is_announcement": true, "published": false}`. Check the response says `is_announcement: true`.
- Calendar event: POST `calendar_events` with `"context_code": "course_:id"` inside `calendar_event`. Messages: POST `conversations` with a top-level `"context_code": "course_:id"` (ask first). The connector checks the course from `context_code`.
- Submissions: GET `courses/:id/assignments/:aid/submissions` with `include[]=user`.
- Dates use ISO 8601 with the local UTC offset.

Student data from Canvas stays in the conversation or in files the user asks for; never put it anywhere shareable without an explicit request.
