#!/usr/bin/env python3
"""Generic Canvas LMS connector (MCP server).

Exposes the whole Canvas REST API through a few general tools instead of one
tool per endpoint:
  canvas_get          any GET request, with optional auto-pagination (read-only)
  canvas_courses      your courses, with which ones can be written to (read-only)
  canvas_write        any POST / PUT / PATCH / DELETE request
  canvas_upload_file  uploads a local file via Canvas's 3-step file upload

Writes go through a course guard: each write names its course, the connector
checks that the path belongs to that course and that the course is live, and
every attempt is recorded (keys only, no values) in a local audit log.

The Canvas host is required: set the CANVAS_HOST environment variable, or `host`
in ~/.config/canvas-mcp/config.toml. There is no default. The token is read from macOS Keychain (service "canvas-api")
at request time and is never returned to Claude, logged, or sent to any host
but Canvas. Optional settings live in ~/.config/canvas-mcp/config.toml.
"""
import json, logging, os, re, subprocess, sys, time
from datetime import datetime
from urllib.parse import quote, unquote, urlparse
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None

KEYCHAIN_SERVICE = "canvas-api"
MAX_CHARS = 150_000  # keep responses within what Claude can read

# httpx logs each request URL at INFO, query strings included (e.g. search_term=<a student's name>),
# and those lines end up in Claude's MCP log. Keep only warnings and errors.
logging.getLogger("httpx").setLevel(logging.WARNING)

mcp = FastMCP("canvas")


# ---------------------------------------------------------------- config

class ConfigError(Exception):
    pass


CONFIG_DEFAULTS = {
    "host": "",  # Canvas host, e.g. canvas.example.edu; the CANVAS_HOST environment variable takes precedence
    "writable_roles": ["teacher"],
    "archived_prefix": "ARCHIVED:",
    "allow_ids": [],
    "deny_ids": [],
    "unscoped_allow_prefixes": ["users/self/"],
    "course_cache_seconds": 600,
    "audit_log_path": None,  # platform default, see _default_log_path
}


def _default_log_path(env) -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/canvas-mcp/writes.jsonl")
    state = env.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(state, "canvas-mcp", "writes.jsonl")


def load_config(env=None) -> dict:
    """Defaults, then the config file (CANVAS_MCP_CONFIG), then CANVAS_MCP_<KEY> env overrides."""
    env = os.environ if env is None else env
    cfg = dict(CONFIG_DEFAULTS, audit_log_path=_default_log_path(env))
    path = os.path.expanduser(env.get("CANVAS_MCP_CONFIG", "~/.config/canvas-mcp/config.toml"))
    if os.path.exists(path):
        if tomllib is None:
            raise ConfigError(f"{path} needs Python 3.11+ or the tomli package to read.")
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            raise ConfigError(f"{path} is not valid TOML ({e}).")
        unknown = set(data) - set(CONFIG_DEFAULTS)
        if unknown:
            raise ConfigError(f"{path} has unknown keys: {', '.join(sorted(unknown))}.")
        cfg.update(data)
    for key, default in CONFIG_DEFAULTS.items():
        raw = env.get("CANVAS_MCP_" + key.upper())
        if raw is None:
            continue
        if isinstance(default, list):
            cfg[key] = [x.strip() for x in raw.split(",") if x.strip()]
        elif isinstance(default, int):
            cfg[key] = raw.strip()
        else:
            cfg[key] = raw
    return _check_config(cfg)


def _check_config(cfg: dict) -> dict:
    def str_list(key):
        v = cfg[key]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ConfigError(f"{key} must be a list of strings.")
        return v

    def id_set(key):
        v = cfg[key]
        if not isinstance(v, list) or not all(str(x).strip().isdigit() for x in v):
            raise ConfigError(f"{key} must be a list of numeric course IDs.")
        return {int(str(x).strip()) for x in v}

    cfg["writable_roles"] = [r.strip().lower() for r in str_list("writable_roles")]
    cfg["unscoped_allow_prefixes"] = [p.strip().lstrip("/") for p in str_list("unscoped_allow_prefixes") if p.strip()]
    cfg["allow_ids"], cfg["deny_ids"] = id_set("allow_ids"), id_set("deny_ids")
    if not str(cfg["course_cache_seconds"]).isdigit():
        raise ConfigError("course_cache_seconds must be a whole number of seconds.")
    cfg["course_cache_seconds"] = int(cfg["course_cache_seconds"])
    for key in ("host", "archived_prefix", "audit_log_path"):
        if not isinstance(cfg[key], str):
            raise ConfigError(f"{key} must be a string.")
    cfg["audit_log_path"] = os.path.expanduser(cfg["audit_log_path"])
    return cfg


try:
    CFG, CONFIG_ERROR = load_config(), None
except ConfigError as e:  # reads still work; every write is refused until the config is fixed
    CFG, CONFIG_ERROR = _check_config(dict(CONFIG_DEFAULTS, audit_log_path=_default_log_path(os.environ))), str(e)


# ---------------------------------------------------------------- HTTP

def _normalize_host(raw: str) -> str:
    h = raw.strip()
    for prefix in ("https://", "http://"):
        if h.lower().startswith(prefix):
            h = h[len(prefix):]
    return h.split("/")[0].strip().lower()


HOST = _normalize_host(os.environ.get("CANVAS_HOST") or CFG["host"])  # "" until configured
BASE = f"https://{HOST}/api/v1"
NO_HOST_MESSAGE = ("No Canvas host is configured. Set CANVAS_HOST to your institution's Canvas host "
                   "(for example canvas.example.edu) in the connector's env entry in the Claude config, "
                   "or set host = \"canvas.example.edu\" in ~/.config/canvas-mcp/config.toml, "
                   "then restart Claude.")


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
    if not HOST:
        raise RuntimeError(NO_HOST_MESSAGE)
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
    if not HOST:
        raise RuntimeError(NO_HOST_MESSAGE)
    return httpx.Client(headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"},
                        timeout=60, follow_redirects=False)


def _storage_post(url: str, data: dict, files: dict) -> httpx.Response:
    # upload_url is a storage host; it must NOT receive the token
    return httpx.post(url, data=data, files=files, timeout=300, follow_redirects=False)


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


def _get_all(c: httpx.Client, path: str, params: dict | None = None, max_pages: int = 50):
    """GET a list endpoint, following pagination on this host. Returns (status, items)."""
    r = c.get(_url(path), params=params)
    if r.status_code != 200 or not isinstance(_body(r), list):
        return r.status_code, None
    items, pages = list(r.json()), 1
    while "next" in r.links and pages < max_pages:
        nxt = r.links["next"]["url"]
        if urlparse(nxt).hostname != HOST:
            break
        r = c.get(nxt)
        if r.status_code != 200:
            break
        items.extend(r.json()); pages += 1
    return 200, items


# ---------------------------------------------------------------- course list

_SEASONS = {"au": "autumn", "aut": "autumn", "autumn": "autumn", "fall": "autumn",
            "wi": "winter", "win": "winter", "winter": "winter",
            "sp": "spring", "spr": "spring", "spring": "spring",
            "su": "summer", "sum": "summer", "summer": "summer"}
_SEASON_SHORT = {"autumn": "Au", "winter": "Wi", "spring": "Sp", "summer": "Su"}

_now = time.monotonic
_cache = {"at": None, "raw": None}


def _fetch_courses(c: httpx.Client, force: bool = False):
    """Your courses from Canvas, cached for course_cache_seconds. Returns (raw list, fetched_now)."""
    fresh = _cache["at"] is not None and _now() - _cache["at"] < CFG["course_cache_seconds"]
    if fresh and not force:
        return _cache["raw"], False
    status, items = _get_all(c, "courses", {"include[]": ["term", "concluded"], "per_page": 100})
    if items is None:
        raise _Refusal("COURSE_LIST_UNAVAILABLE",
                       f"Could not load your Canvas course list (GET courses returned {status}).\n"
                       "Ask the user to check the Canvas connector. Do not guess a course.")
    _cache.update(at=_now(), raw=items)
    return items, True


def _norm(text) -> str:
    s = " ".join(str(text or "").lower().split())
    prefix = CFG["archived_prefix"].lower().strip()
    if prefix and s.startswith(prefix):
        s = s[len(prefix):].strip()
    return s


def _tokens(text) -> list:
    return re.findall(r"[a-z]+|\d+", _norm(text))


def _year(tok: str):
    if tok.isdigit() and len(tok) == 2:
        return 2000 + int(tok)
    if tok.isdigit() and len(tok) == 4:
        return int(tok)
    return None


def _term_of(tokens: list):
    """(season, year) from tokens such as ['autumn', '2026'] or ['au', '26']; None if absent."""
    season = next((_SEASONS[t] for t in tokens if t in _SEASONS), None)
    year = next((_year(t) for t in tokens if _year(t)), None)
    return (season, year) if season and year else None


def _parse_label(text):
    """Split 'ABC 101 A Au 26' into subject, number, optional section, term and the rest."""
    toks = _tokens(text)
    i = next((n for n, t in enumerate(toks) if t.isdigit()), None)
    if not i:  # no number, or no subject before it
        return None
    rest = toks[i + 1:]
    section = rest[0] if rest and rest[0].isalpha() and len(rest[0]) <= 2 and rest[0] not in _SEASONS else None
    return {"subject": " ".join(toks[:i]), "number": toks[i], "section": section,
            "term": _term_of(rest), "rest": rest[1:] if section else rest}


def _course_record(raw: dict) -> dict:
    term = (raw.get("term") or {}).get("name") or ""
    rec = {"id": raw.get("id"), "name": raw.get("name") or "", "course_code": raw.get("course_code") or "",
           "term": term, "published": raw.get("workflow_state") == "available"}
    rec["writable"], rec["reason"] = _writable(raw)
    # what labels can match: subject/number/section from the course code and the name before ':'
    code = _parse_label(rec["course_code"])
    rec["ids"] = [p for p in (code, _parse_label(_norm(rec["name"]).split(":")[0])) if p]
    term_key = _term_of(_tokens(term))
    rec["terms"] = {term_key} if term_key else {p["term"] for p in rec["ids"] if p["term"]}
    rec["term_text"] = " ".join(_tokens(term))
    short = f" {_SEASON_SHORT[term_key[0]]}{term_key[1] % 100:02d}" if term_key and not (code and code["term"]) else ""
    rec["label"] = (rec["course_code"] or rec["name"]) + short
    return rec


def _writable(raw: dict):
    """(True, None) or (False, reason) under the write allowlist rules."""
    cid = raw.get("id")
    if cid in CFG["deny_ids"]:
        return False, "listed in deny_ids"
    if cid in CFG["allow_ids"]:
        return True, None
    enrollments = [(str(e.get("type", "")).lower().replace("enrollment", ""), e.get("enrollment_state"))
                   for e in raw.get("enrollments") or []]
    states = [state for role, state in enrollments if role in CFG["writable_roles"]]
    if not states:
        roles = ", ".join(sorted({role for role, _ in enrollments})) or "unknown"
        return False, f"your role is {roles}, not {' or '.join(CFG['writable_roles'])}"
    if "active" not in states:
        return False, f"your enrollment is {states[0] or 'not active'}, not active"
    if raw.get("concluded"):
        return False, "course is concluded"
    prefix = CFG["archived_prefix"]
    if prefix and (raw.get("name") or "").lower().startswith(prefix.lower()):
        return False, f'name starts with "{prefix}"'
    return True, None


def _matches(label: str, recs: list) -> list:
    label = label.strip()
    if label.isdigit():
        return [r for r in recs if r["id"] == int(label)]
    want, lp = _norm(label), _parse_label(label)
    found = []
    for r in recs:
        if want and want in (_norm(r["course_code"]), _norm(r["name"]), _norm(r["label"])):
            found.append(r)
            continue
        if not lp:
            continue
        if not any(p["subject"] == lp["subject"] and p["number"] == lp["number"]
                   and (lp["section"] is None or p["section"] == lp["section"]) for p in r["ids"]):
            continue
        if not lp["rest"]:                        # no term given: matches every term
            found.append(r)
        elif lp["term"] and lp["term"] in r["terms"]:
            found.append(r)
        elif r["term_text"] and " ".join(lp["rest"]) == r["term_text"]:  # term names outside "Season YYYY"
            found.append(r)
    return found


def _resolve(c: httpx.Client, label: str) -> dict:
    """The one course a label or ID names. Raises _Refusal when there isn't exactly one."""
    raw, fetched = _fetch_courses(c)
    recs = [_course_record(x) for x in raw]
    found = _matches(label, recs) if label.strip() else []
    if not found and label.strip() and not fetched:   # maybe new since the cache was filled
        raw, _ = _fetch_courses(c, force=True)
        recs = [_course_record(x) for x in raw]
        found = _matches(label, recs)
    if len(found) == 1:
        return found[0]
    if not found:
        writable = [r for r in recs if r["writable"]]
        what = f'"{label.strip()}" doesn\'t match any course you teach.' if label.strip() else "No course was given."
        raise _Refusal("COURSE_NOT_FOUND",
                       f"{what}\nAsk the user which course they mean. Do not guess.\n"
                       f"Courses you can write to:\n{_table(writable)}\n"
                       "Retry with course set to one of the IDs or labels above.")
    raise _Refusal("COURSE_AMBIGUOUS",
                   f'"{label.strip()}" matches more than one course you teach.\n'
                   f"Ask the user which course they mean. Do not guess.\n{_table(found)}\n"
                   "Retry with course set to one of the IDs or labels above.")


def _table(recs: list) -> str:
    if not recs:
        return "  (none)"
    recs = sorted(recs, key=lambda r: (not r["writable"], r["label"].lower()))
    rows = [(str(r["id"]), r["label"], r["name"], r["term"] or "-",
             "published" if r["published"] else "unpublished",
             "writable" if r["writable"] else f"read-only: {r['reason']}") for r in recs]
    widths = [max(len(row[i]) for row in rows) for i in range(5)]
    return "\n".join("  " + "  ".join(row[i].ljust(widths[i]) for i in range(5)) + "  " + row[5] for row in rows)


def _describe(rec: dict) -> str:
    return f"{rec['name']} ({rec['id']})" + (f", {rec['term']}" if rec["term"] else "")


# ---------------------------------------------------------------- write guard

class _Refusal(Exception):
    def __init__(self, code: str, text: str, course: dict | None = None):
        super().__init__(code)
        self.code, self.text, self.course = code, text, course


def _api_path(path: str) -> str:
    """Path relative to the API root, without host, API prefix or query string."""
    p = path.strip()
    if p.startswith("http"):
        p = urlparse(p).path
    p = unquote(p.split("?", 1)[0]).lstrip("/")
    return re.sub(r"^api/(?:[a-z_]+/)?v\d+/", "", p)  # /api/v1/ and New Quizzes' /api/quiz/v1/


def _context_course(code, where: str):
    m = re.fullmatch(r"course_(\d+)", str(code or ""))
    return ("course", int(m.group(1))) if m else ("unscoped", f"{where} is not a course ({code or 'no context_code'})")


def _owner(c: httpx.Client, kind: str, oid: str):
    """Owning course of files/:id, folders/:id, sections/:id or groups/:id, with one or two GETs."""
    if kind == "files":
        r = c.get(_url(f"files/{oid}"))
        folder = _body(r).get("folder_id") if r.status_code == 200 and isinstance(_body(r), dict) else None
        if not folder:
            return "unscoped", f"could not find the folder of files/{oid} (GET returned {r.status_code})"
        kind, oid = "folders", folder
    r = c.get(_url(f"{kind}/{oid}"))
    d = _body(r)
    if r.status_code != 200 or not isinstance(d, dict):
        return "unscoped", f"could not look up {kind}/{oid} (GET returned {r.status_code})"
    if kind == "sections":
        cid = d.get("course_id")
    elif d.get("context_type") == "Course":
        cid = d.get("context_id") or d.get("course_id")
    else:
        return "unscoped", f"{kind}/{oid} belongs to a {d.get('context_type') or 'non-course context'}"
    return ("course", int(cid)) if cid else ("unscoped", f"{kind}/{oid} has no course")


def _target(c: httpx.Client, method: str, path: str, body):
    """Which course a write touches: ("course", id), ("allowed", prefix) or ("unscoped", reason)."""
    p = _api_path(path)
    body = body if isinstance(body, dict) else {}
    m = re.match(r"courses/([^/]+)", p)
    if m:
        ref = m.group(1)
        if ref.isdigit():
            return "course", int(ref)
        r = c.get(_url("courses/" + quote(ref, safe=":")))  # e.g. sis_course_id:XYZ
        d = _body(r)
        if r.status_code == 200 and isinstance(d, dict) and d.get("id"):
            return "course", int(d["id"])
        return "unscoped", f"could not look up courses/{ref} (GET returned {r.status_code})"
    for prefix in CFG["unscoped_allow_prefixes"]:
        if (p + "/").startswith(prefix if prefix.endswith("/") else prefix + "/"):
            return "allowed", prefix
    m = re.match(r"(files|folders|sections|groups)/(\d+)", p)
    if m:
        return _owner(c, *m.groups())
    ev = body.get("calendar_event") if isinstance(body.get("calendar_event"), dict) else {}
    m = re.match(r"calendar_events/(\d+)", p)
    if m:
        r = c.get(_url(f"calendar_events/{m.group(1)}"))
        current = _body(r).get("context_code") if r.status_code == 200 and isinstance(_body(r), dict) else None
        if ev.get("context_code") and ev["context_code"] != current:
            return "unscoped", "the body moves the event to a different calendar"
        return _context_course(current, f"calendar_events/{m.group(1)}")
    if p == "calendar_events":
        return _context_course(ev.get("context_code"), "calendar_event.context_code")
    if p == "conversations":
        return _context_course(body.get("context_code"), "context_code")
    return "unscoped", "the path doesn't name a course"


def _guard(c: httpx.Client, course: str, method: str, path: str, body):
    """Check a write before it is sent. Returns the course record (None for an allowed unscoped path)."""
    if CONFIG_ERROR:
        raise _Refusal("CONFIG_ERROR", f"The connector config is invalid: {CONFIG_ERROR}\n"
                                       "Ask the user to fix it. Do not guess.")
    kind, value = _target(c, method, path, body)
    if kind == "allowed":
        return None
    if kind == "unscoped":
        allowed = ", ".join(CFG["unscoped_allow_prefixes"]) or "nothing"
        raise _Refusal("UNSCOPED_WRITE",
                       f"{method} {_api_path(path)} can't be tied to one course: {value}.\n"
                       "Ask the user how to proceed. Do not guess a course or a different path.\n"
                       f"Writes outside a course are limited to: {allowed}. Only the user can change this, "
                       "with unscoped_allow_prefixes in the connector config.")
    rec = _resolve(c, course)
    if rec["id"] != value:
        others = [_course_record(x) for x in _cache["raw"] or [] if x.get("id") == value]
        other = _describe(others[0]) if others else f"course {value}, which is not in your course list"
        raise _Refusal("COURSE_MISMATCH",
                       f'course "{course.strip()}" is {_describe(rec)}, but the path targets {other}.\n'
                       "Ask the user which course they mean. Do not guess.\n"
                       "Retry with a course and path that name the same course.", rec)
    if not rec["writable"]:
        raise _Refusal("COURSE_NOT_WRITABLE",
                       f"{_describe(rec)} is read-only: {rec['reason']}.\n"
                       "Ask the user how to proceed. Do not guess another course.\n"
                       "Only the user can make a course writable, by adding its ID to allow_ids in the connector config.",
                       rec)
    return rec


def _echo(rec, course: str, method: str, path: str, result) -> str:
    if rec:
        who = _describe(rec)
    elif rec is None and result != "REFUSED":
        who = "no course check: allowed path"
    else:
        who = f'course "{course.strip()}" not resolved'
    return f"[{who}] {method} {_api_path(path)} -> {result}"


def _body_keys(body, prefix: str = "") -> list:
    """Key paths of a body, e.g. ['wiki_page.body']. Never values; numeric keys (user IDs) become '*'."""
    keys = []
    if isinstance(body, dict):
        for k, v in body.items():
            k = "*" if str(k).isdigit() else str(k)
            sub = _body_keys(v, f"{prefix}{k}.") if isinstance(v, (dict, list)) else []
            keys.extend(sub or [prefix + k])
    elif isinstance(body, list):
        for item in body:
            for k in _body_keys(item, prefix.rstrip(".") + "[]."):
                if k not in keys:
                    keys.append(k)
    return keys


def _audit(**entry) -> None:
    """Append one JSON line to the audit log. Logging failures never block the write."""
    line = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "outcome": None, "error_code": None,
            "course_label": None, "course_id": None, "course_name": None, "method": None, "path": None,
            "status": None, "body_keys": [], "result_id": None, "html_url": None}
    line.update(entry)
    try:
        path = CFG["audit_log_path"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"canvas-mcp: could not write audit log: {e}", file=sys.stderr)


def _guarded_write(course: str, method: str, path: str, body, send) -> str:
    """Run the course guard, then send(client) -> httpx.Response. Echoes the course and logs the attempt."""
    course = str(course or "")
    base = {"course_label": course, "method": method, "path": _api_path(path), "body_keys": _body_keys(body)}
    with _client() as c:
        try:
            rec = _guard(c, course, method, path, body)
        except _Refusal as e:
            if e.course:
                base.update(course_id=e.course["id"], course_name=e.course["name"])
            _audit(outcome="refused", error_code=e.code, **base)
            return _echo(e.course, course, method, path, "REFUSED") + f" ({e.code})\nREFUSED ({e.code}): {e.text}"
        r = send(c)
        data = _body(r)
        if rec:
            base.update(course_id=rec["id"], course_name=rec["name"])
        d = data if isinstance(data, dict) else {}
        _audit(outcome="ok" if r.status_code < 400 else "http_error", status=r.status_code,
               result_id=d.get("id", d.get("page_id")), html_url=d.get("html_url"), **base)
        return _echo(rec, course, method, path, r.status_code) + "\n" + _out(r.status_code, data)


# ---------------------------------------------------------------- tools

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


@mcp.tool(annotations=ToolAnnotations(title="Canvas courses", readOnlyHint=True, openWorldHint=True))
def canvas_courses(include_readonly: bool = False) -> str:
    """List your Canvas courses, one per line: ID, label, full name, term, published, writable.

    Use it when you need to ask the user which course they mean. Any ID or label
    shown can be passed as the `course` argument of canvas_write and canvas_upload_file.
    include_readonly: also list courses that can't be written to, with the reason.
    """
    with _client() as c:
        try:
            raw, _ = _fetch_courses(c)
        except _Refusal as e:
            return f"REFUSED ({e.code}): {e.text}"
    recs = [_course_record(x) for x in raw]
    shown = recs if include_readonly else [r for r in recs if r["writable"]]
    n_w = sum(r["writable"] for r in recs)
    head = (f"Your courses ({len(recs)}, {n_w} writable)." if include_readonly
            else f"Courses you can write to ({n_w} of {len(recs)}).")
    return head + " Pass an ID or label as `course` when writing.\n" + _table(shown)


@mcp.tool(annotations=ToolAnnotations(title="Canvas write", readOnlyHint=False, destructiveHint=True, openWorldHint=True))
def canvas_write(course: str, method: str, path: str, body: dict | None = None, params: dict | None = None) -> str:
    """Send a POST, PUT, PATCH or DELETE request to any Canvas REST API endpoint.

    course: REQUIRED. The course this write is for: a label with subject, number and
            term, e.g. "ABC 101 Au26" or "ABC 101 A Autumn 2026", or a numeric course ID.
            The connector refuses the write unless the path belongs to exactly this
            course and the course is live. If you don't know which course the user
            means, ask them. Never guess or pick a recent course; canvas_courses lists
            the options. For users/self/... paths, pass "self".
    method: "POST", "PUT", "PATCH" or "DELETE".
    path: endpoint relative to /api/v1, e.g. "courses/12345/pages".
    body: JSON body using Canvas's nested names, e.g.
          {"wiki_page": {"title": "Week 1", "body": "<p>Hi</p>", "published": false}}.
    params: optional query parameters.
    Changes are live in Canvas. Create content unpublished unless told otherwise.
    The result starts with a line naming the course written to; check it.
    """
    method = method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return _out(0, f"Unsupported method {method}; use canvas_get for reads.")
    url = _url(path)
    return _guarded_write(course, method, path, body,
                          lambda c: c.request(method, url, json=body, params=params))


@mcp.tool(annotations=ToolAnnotations(title="Canvas file upload", readOnlyHint=False, destructiveHint=False, openWorldHint=True))
def canvas_upload_file(course: str, endpoint: str, local_path: str, parent_folder_path: str | None = None,
                       name: str | None = None, on_duplicate: str = "rename") -> str:
    """Upload a file from this Mac to Canvas.

    course: REQUIRED. The course this upload is for: a label such as "ABC 101 Au26"
            or a numeric course ID. Same checks as canvas_write. If you don't know
            which course the user means, ask them; never guess. For users/self/files,
            pass "self".
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
    url = _url(endpoint)

    def send(c: httpx.Client) -> httpx.Response:
        r = c.post(url, data=meta)
        if r.status_code != 200:
            return r
        step = r.json()
        with open(p, "rb") as f:
            up = _storage_post(step["upload_url"], step.get("upload_params", {}), {"file": (meta["name"], f)})
        if up.status_code in (301, 302, 303) and "location" in up.headers:
            loc = up.headers["location"]
            if urlparse(loc).hostname == HOST:
                up = c.get(loc)
        return up

    return _guarded_write(course, "POST", endpoint, meta, send)


if __name__ == "__main__":
    mcp.run()
