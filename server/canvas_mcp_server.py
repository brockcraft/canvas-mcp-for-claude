#!/usr/bin/env python3
"""Generic Canvas LMS connector (MCP server).

Exposes the whole Canvas REST API through three tools instead of one tool
per endpoint:
  canvas_get          any GET request, with optional auto-pagination (read-only)
  canvas_write        any POST / PUT / PATCH / DELETE request
  canvas_upload_file  uploads a local file via Canvas's 3-step file upload

The Canvas host comes from the CANVAS_HOST environment variable (default
canvas.uw.edu). The token is read from macOS Keychain (service "canvas-api")
at request time and is never returned to Claude, logged, or sent to any host
but Canvas.
"""
import json, os, subprocess
from urllib.parse import urlparse
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

HOST = os.environ.get("CANVAS_HOST", "canvas.uw.edu")
BASE = f"https://{HOST}/api/v1"
KEYCHAIN_SERVICE = "canvas-api"
MAX_CHARS = 150_000  # keep responses within what Claude can read

mcp = FastMCP("canvas")


def _token() -> str:
    try:
        t = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                           capture_output=True, text=True, check=True).stdout.strip()
        if t:
            return t
    except Exception:
        pass
    p = os.path.expanduser("~/.canvas/token")
    if os.path.exists(p):
        return "".join(open(p).read().split())
    raise RuntimeError("No Canvas token found. Run scripts/setup.sh to store one in Keychain.")


def _url(path: str) -> str:
    """Accept 'courses/1/pages', '/api/v1/courses/1/pages' or a full canvas URL; refuse other hosts."""
    path = path.strip()
    if path.startswith("http"):
        u = urlparse(path)
        if u.hostname != HOST:
            raise ValueError(f"Refusing request to {u.hostname}: only {HOST} is allowed.")
        return path
    if path.startswith("/api/v1"):
        path = path[len("/api/v1"):]
    return BASE + "/" + path.lstrip("/")


def _client() -> httpx.Client:
    return httpx.Client(headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"},
                        timeout=60, follow_redirects=False)


def _out(status: int, data, extra: dict | None = None) -> str:
    res = {"status": status, **(extra or {}), "data": data}
    s = json.dumps(res, indent=1, ensure_ascii=False)
    if len(s) > MAX_CHARS:
        s = s[:MAX_CHARS] + f"\n... [truncated at {MAX_CHARS} chars; narrow the request with params such as per_page, include[], or search_term]"
    return s


def _body(r: httpx.Response):
    try:
        return r.json()
    except Exception:
        return r.text[:5000]


@mcp.tool(annotations=ToolAnnotations(title="Canvas GET", readOnlyHint=True, openWorldHint=True))
def canvas_get(path: str, params: dict | None = None, all_pages: bool = False, max_pages: int = 20) -> str:
    """GET any Canvas REST API endpoint (read-only).

    path: endpoint relative to /api/v1, e.g. "courses/12345/pages" or "users/self".
    params: query parameters, e.g. {"per_page": 100, "include[]": ["items"]}.
    all_pages: follow Canvas pagination (Link rel="next") and return one combined list.
    max_pages: safety cap on pages fetched when all_pages is true.
    Reference: https://canvas.instructure.com/doc/api/
    """
    with _client() as c:
        r = c.get(_url(path), params=params)
        if not all_pages or r.status_code != 200 or not isinstance(_body(r), list):
            return _out(r.status_code, _body(r))
        items, pages = list(r.json()), 1
        while "next" in r.links and pages < max_pages:
            nxt = r.links["next"]["url"]
            if urlparse(nxt).hostname != HOST:
                break
            r = c.get(nxt)
            if r.status_code != 200:
                break
            items.extend(r.json()); pages += 1
        more = "next" in r.links
        return _out(200, items, {"pages_fetched": pages, "count": len(items), "more_pages_available": more})


@mcp.tool(annotations=ToolAnnotations(title="Canvas write", readOnlyHint=False, destructiveHint=True, openWorldHint=True))
def canvas_write(method: str, path: str, body: dict | None = None, params: dict | None = None) -> str:
    """Send a POST, PUT, PATCH or DELETE request to any Canvas REST API endpoint.

    method: "POST", "PUT", "PATCH" or "DELETE".
    path: endpoint relative to /api/v1, e.g. "courses/12345/pages".
    body: JSON body using Canvas's nested names, e.g.
          {"wiki_page": {"title": "Week 1", "body": "<p>Hi</p>", "published": false}}.
    params: optional query parameters.
    Changes are live in Canvas. Create content unpublished unless told otherwise.
    """
    method = method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return _out(0, f"Unsupported method {method}; use canvas_get for reads.")
    with _client() as c:
        r = c.request(method, _url(path), json=body, params=params)
        return _out(r.status_code, _body(r))


@mcp.tool(annotations=ToolAnnotations(title="Canvas file upload", readOnlyHint=False, destructiveHint=False, openWorldHint=True))
def canvas_upload_file(endpoint: str, local_path: str, parent_folder_path: str | None = None,
                       name: str | None = None, on_duplicate: str = "rename") -> str:
    """Upload a file from this Mac to Canvas.

    endpoint: upload endpoint relative to /api/v1, e.g. "courses/12345/files"
              (course files) or "users/self/files". Assignment submission and
              other upload endpoints also work.
    local_path: absolute path on this Mac, e.g. "/Users/you/Documents/syllabus.pdf".
    parent_folder_path: Canvas folder, e.g. "course files/week1" (created if missing).
    on_duplicate: "rename" (default) or "overwrite".
    """
    p = os.path.expanduser(local_path)
    if not os.path.isfile(p):
        return _out(0, f"File not found: {p}")
    meta = {"name": name or os.path.basename(p), "size": os.path.getsize(p), "on_duplicate": on_duplicate}
    if parent_folder_path:
        meta["parent_folder_path"] = parent_folder_path
    with _client() as c:
        r = c.post(_url(endpoint), data=meta)
        if r.status_code != 200:
            return _out(r.status_code, _body(r))
        step = r.json()
        with open(p, "rb") as f:
            # upload_url is a storage host; it must NOT receive the token
            up = httpx.post(step["upload_url"], data=step.get("upload_params", {}),
                            files={"file": (meta["name"], f)}, timeout=300, follow_redirects=False)
        if up.status_code in (301, 302, 303) and "location" in up.headers:
            loc = up.headers["location"]
            if urlparse(loc).hostname == HOST:
                up = c.get(loc)
        return _out(up.status_code, _body(up))


if __name__ == "__main__":
    mcp.run()
