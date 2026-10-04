# Security Policy

This connector holds a Canvas access token and can change course content, so security reports are taken seriously.

## Supported versions

Only the [latest release](https://github.com/brockcraft/canvas-mcp-for-claude/releases/latest) receives security fixes. If you are on an older version, update first and check whether the problem still happens.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Use GitHub's private reporting instead:

1. Go to the [Security tab](https://github.com/brockcraft/canvas-mcp-for-claude/security) of this repository.
2. Choose **Report a vulnerability**, or use [this direct link](https://github.com/brockcraft/canvas-mcp-for-claude/security/advisories/new).
3. Describe what you found, the steps to reproduce it, and what an attacker could do with it.

Do not include a real Canvas token, student names, grades or other student data in a report. A description or a redacted example is enough.

This is a one-person, volunteer project. I will aim to acknowledge a report within 7 days and to tell you what I plan to do within 30 days, but I cannot promise a fix by a given date. If a report is valid, I will credit you in the release notes unless you prefer not to be named.

## What counts as a vulnerability

Examples of problems I want to hear about:

- The token appearing anywhere it should not: tool results returned to Claude, logs, the audit log, error messages, or any request sent to a host other than your Canvas host (including during file uploads).
- A way to make the connector send requests to a host other than the configured Canvas host, such as through a redirect, a pagination link, or a crafted path or URL.
- A way around the course guard: a write that goes to a different course than the one named, to an archived, concluded or read-only course, or that skips the check altogether.
- The audit log recording values (such as page text or grades) that it is documented not to record.
- A way to read or send local files other than the one a user asked Claude to upload.

## What is out of scope

- Vulnerabilities in Canvas, Claude Desktop, Claude Code, `uv`, or the MCP SDK. Please report those to their maintainers.
- Anything that requires an attacker to already control your computer or your Canvas account.
- Actions you or Claude are allowed to take with your own token. The connector acts with your account's permissions; the course guard and the approval prompts reduce mistakes, but they are not a substitute for limiting your token.
- Prompt injection in general. Text that comes from Canvas (page content, discussion posts, student submissions) reaches Claude and could contain instructions. The defenses are the approval prompt on each write and the course guard, which limits where a write can go. If you find a way around those two, that is in scope.

## Reducing your own risk

The README's "Security design" and "Recommended safeguards" sections describe the protections. In short:

- Give your Canvas token an expiration date, and revoke it in Canvas if you think it was exposed.
- Keep the write tools set to ask for approval each time.
- Put old or shared courses in `deny_ids`.
- Install the extension only from this repository's [releases page](https://github.com/brockcraft/canvas-mcp-for-claude/releases).
- Check your institution's guidance on using AI tools with student records.
