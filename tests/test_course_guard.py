"""Course guard tests. Canvas is mocked with httpx.MockTransport; nothing touches the network or Keychain.

Run from the repository root:  python -m unittest discover -s tests
"""
import json, logging, os, sys, tempfile, unittest
from unittest import mock

os.environ["CANVAS_HOST"] = "canvas.example.edu"
os.environ["CANVAS_MCP_CONFIG"] = os.path.join(tempfile.gettempdir(), "canvas-mcp-test-no-such-config.toml")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

import httpx
import canvas_mcp_server as s

HOST = "canvas.example.edu"
SENTINEL = "SENTINEL-do-not-log-7f3a"


def course(cid, name, code, term, role="teacher", state="active", concluded=False, published=True):
    return {"id": cid, "name": name, "course_code": code, "term": {"name": term},
            "workflow_state": "available" if published else "unpublished", "concluded": concluded,
            "enrollments": [{"type": role, "enrollment_state": state}]}


COURSES = [
    course(1001, "ABC 101 A Au 26: Introduction to Things", "ABC 101 A", "Autumn 2026"),
    course(1002, "ABC 205 A Wi 26: Data Methods", "ABC 205 A", "Winter 2026"),
    course(1003, "ABC 205 A Sp 26: Data Methods", "ABC 205 A", "Spring 2026", published=False),
    course(1004, "ABC 300 A Su 25: Old Seminar", "ABC 300 A", "Summer 2025", concluded=True),
    course(1005, "ARCHIVED: ABC 310 A Au 26: Retired Studio", "ABC 310 A", "Autumn 2026"),
    course(1006, "XYZ 400 A Au 26: Someone Else's Course", "XYZ 400 A", "Autumn 2026", role="student"),
    course(1007, "ABC 320 A Au 26: Denied Course", "ABC 320 A", "Autumn 2026"),
    course(1008, "Instructor Sandbox", "Sandbox-Instructor", "Default Term", concluded=True),
]


class FakeCanvas:
    """Minimal Canvas API. Records every request; fails loudly on anything unexpected."""

    def __init__(self, courses=None):
        self.courses = list(courses if courses is not None else COURSES)
        self.requests = []
        self.course_list_calls = 0
        self.objects = {
            "files/555": {"id": 555, "folder_id": 77},
            "folders/77": {"id": 77, "context_type": "Course", "context_id": 1002},
            "folders/78": {"id": 78, "context_type": "Course", "context_id": 1001},
            "folders/79": {"id": 79, "context_type": "User", "context_id": 9},
            "sections/88": {"id": 88, "course_id": 1001},
            "groups/66": {"id": 66, "context_type": "Course", "course_id": 1002},
            "calendar_events/44": {"id": 44, "context_code": "course_1001"},
            "courses/sis_course_id:ABC101": {"id": 1001},
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == HOST, f"unexpected host {request.url.host}"
        self.requests.append((request.method, request.url.path))
        path = request.url.path.removeprefix("/api/v1/")
        if request.method == "GET" and path == "courses":
            self.course_list_calls += 1
            half = len(self.courses) // 2
            if request.url.params.get("page") == "2":
                return httpx.Response(200, json=self.courses[half:])
            nxt = f'<https://{HOST}/api/v1/courses?page=2&per_page=100>; rel="next"'
            return httpx.Response(200, json=self.courses[:half], headers={"Link": nxt})
        if request.method == "GET" and path in self.objects:
            return httpx.Response(200, json=self.objects[path])
        if request.method == "GET":
            return httpx.Response(404, json={"errors": [{"message": "not found"}]})
        if path.endswith("/files") and request.method == "POST":  # upload step 1
            return httpx.Response(200, json={"upload_url": "https://storage.example.net/up", "upload_params": {"k": "v"}})
        # any other write succeeds and echoes a sensitive value back
        return httpx.Response(200, json={"id": 42, "html_url": f"https://{HOST}/{path}", "body": SENTINEL})

    def writes(self):
        return [r for r in self.requests if r[0] != "GET"]


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "logs", "writes.jsonl")
        self.configure()
        self.canvas = FakeCanvas()
        self.clock = [1000.0]
        s._cache.update(at=None, raw=None)
        patches = [
            mock.patch.object(s, "_client", lambda: httpx.Client(transport=httpx.MockTransport(self.canvas))),
            mock.patch.object(s, "_token", side_effect=AssertionError("tests must not read the token")),
            mock.patch.object(s, "_now", lambda: self.clock[0]),
            mock.patch.object(s, "_storage_post", self.fake_storage),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def configure(self, **env):
        base = {"CANVAS_MCP_CONFIG": os.path.join(self.tmp.name, "none.toml"),
                "CANVAS_MCP_AUDIT_LOG_PATH": self.log, "CANVAS_MCP_DENY_IDS": "1007"}
        s.CFG, s.CONFIG_ERROR = s.load_config(env={**base, **env}), None

    def fake_storage(self, url, data, files):
        assert url.startswith("https://storage.example.net/")
        return httpx.Response(201, json={"id": 900, "display_name": "x.pdf"})

    def call(self, fn, *args):
        """Run a write tool and note whether it sent a write to Canvas."""
        before = len(self.canvas.writes())
        out = fn(*args)
        self.last_call_wrote = len(self.canvas.writes()) > before
        return out

    def write(self, course, path, method="PUT", body=None):
        body = body if body is not None else {"wiki_page": {"title": "T"}}
        return self.call(s.canvas_write, course, method, path, body)

    def upload(self, course, endpoint, local_path):
        return self.call(s.canvas_upload_file, course, endpoint, local_path)

    def log_lines(self):
        with open(self.log) as f:
            return [json.loads(line) for line in f]

    def assertRefused(self, out, code):
        self.assertIn(f"REFUSED ({code})", out)
        self.assertIn("Ask the user", out)
        self.assertIn("Do not guess", out)
        self.assertFalse(self.last_call_wrote, "a refused write must not reach Canvas")


class LabelResolution(GuardTest):
    def test_every_spelling_resolves(self):
        for label in ["ABC 101 Au26", "abc 101 autumn 2026", "ABC 101 A Au 26", "ABC 101 A Autumn 2026",
                      "ABC 101 Fall 2026", "1001", "  abc   101   aut 26 "]:
            with self.subTest(label=label):
                out = self.write(label, "courses/1001/pages/week-1")
                self.assertTrue(out.startswith("[ABC 101 A Au 26: Introduction to Things (1001), Autumn 2026] "
                                               "PUT courses/1001/pages/week-1 -> 200"), out)

    def test_same_code_in_two_terms_is_ambiguous(self):
        out = self.write("ABC 205", "courses/1002/pages/x")
        self.assertRefused(out, "COURSE_AMBIGUOUS")
        self.assertIn("1002", out)
        self.assertIn("1003", out)
        self.assertIn("Winter 2026", out)
        self.assertIn("Spring 2026", out)

    def test_term_disambiguates(self):
        self.assertIn("-> 200", self.write("ABC 205 Wi26", "courses/1002/pages/x"))

    def test_section_must_match(self):
        self.assertRefused(self.write("ABC 101 B Au26", "courses/1001/pages/x"), "COURSE_NOT_FOUND")

    def test_unknown_label_lists_writable_courses(self):
        out = self.write("QQQ 999 Au26", "courses/1001/pages/x")
        self.assertRefused(out, "COURSE_NOT_FOUND")
        self.assertIn("ABC 101 A Au 26: Introduction to Things", out)
        for readonly in ("1004", "1005", "1006", "1007"):
            self.assertNotIn(readonly, out)

    def test_empty_course_is_refused(self):
        out = self.write("", "courses/1001/pages/x")
        self.assertRefused(out, "COURSE_NOT_FOUND")
        self.assertIn("No course was given", out)

    def test_unparseable_term_matches_term_name_verbatim(self):
        self.configure(CANVAS_MCP_ALLOW_IDS="1008")
        self.assertIn("-> 200", self.write("Sandbox-Instructor", "courses/1008/pages/x"))
        self.canvas.courses.append(course(1009, "BIO 101: Cells", "BIO 101", "2026-27 Academic Year"))
        self.assertIn("-> 200", self.write("BIO 101 2026-27 Academic Year", "courses/1009/pages/x"))


class PathChecks(GuardTest):
    def test_mismatch_names_both_courses(self):
        out = self.write("ABC 101 Au26", "courses/1002/pages/x")
        self.assertRefused(out, "COURSE_MISMATCH")
        self.assertIn("ABC 101 A Au 26: Introduction to Things (1001)", out)
        self.assertIn("ABC 205 A Wi 26: Data Methods (1002)", out)

    def test_full_url_and_api_prefix(self):
        self.assertIn("-> 200", self.write("1001", f"https://{HOST}/api/v1/courses/1001/pages/x"))
        self.assertRefused(self.write("1001", "/api/v1/courses/1002/pages/x"), "COURSE_MISMATCH")

    def test_files_and_folders_resolve_to_owner(self):
        self.assertRefused(self.write("ABC 101 Au26", "files/555", "DELETE", {}), "COURSE_MISMATCH")
        self.assertIn("-> 200", self.write("ABC 205 Wi26", "files/555", "DELETE", {}))
        self.assertIn("-> 200", self.write("ABC 101 Au26", "folders/78", body={"name": "Week 1"}))
        self.assertRefused(self.write("ABC 205 Wi26", "folders/78", body={"name": "Week 1"}), "COURSE_MISMATCH")

    def test_sections_groups_and_sis_ids(self):
        self.assertIn("-> 200", self.write("ABC 101 Au26", "sections/88", body={"course_section": {"name": "Lab"}}))
        self.assertRefused(self.write("ABC 101 Au26", "groups/66", body={"name": "G"}), "COURSE_MISMATCH")
        self.assertIn("-> 200", self.write("ABC 101 Au26", "courses/sis_course_id:ABC101/pages/x"))

    def test_non_course_folder_is_unscoped(self):
        self.assertRefused(self.write("ABC 101 Au26", "folders/79", body={"name": "x"}), "UNSCOPED_WRITE")

    def test_users_self_allowed(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            out = self.upload("self", "users/self/files", f.name)
        self.assertTrue(out.startswith("[no course check: allowed path] POST users/self/files -> 201"), out)

    def test_accounts_path_is_unscoped(self):
        self.assertRefused(self.write("ABC 101 Au26", "accounts/1/courses", "POST", {"course": {"name": "x"}}),
                           "UNSCOPED_WRITE")
        self.assertRefused(self.write("ABC 101 Au26", "users/12/files", "POST", {}), "UNSCOPED_WRITE")

    def test_calendar_events_and_conversations_use_context_code(self):
        ev = {"calendar_event": {"context_code": "course_1001", "title": "Office hours"}}
        self.assertIn("-> 200", self.write("ABC 101 Au26", "calendar_events", "POST", ev))
        self.assertRefused(self.write("ABC 205 Wi26", "calendar_events", "POST", ev), "COURSE_MISMATCH")
        self.assertIn("-> 200", self.write("ABC 101 Au26", "calendar_events/44", "PUT", {"calendar_event": {"title": "x"}}))
        moved = {"calendar_event": {"context_code": "course_1002"}}
        self.assertRefused(self.write("ABC 101 Au26", "calendar_events/44", "PUT", moved), "UNSCOPED_WRITE")
        msg = {"recipients": ["1"], "body": "hi", "context_code": "course_1001"}
        self.assertIn("-> 200", self.write("ABC 101 Au26", "conversations", "POST", msg))
        del msg["context_code"]
        self.assertRefused(self.write("ABC 101 Au26", "conversations", "POST", msg), "UNSCOPED_WRITE")

    def test_upload_endpoint_is_checked(self):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            out = self.upload("ABC 101 Au26", "courses/1002/files", f.name)
            self.assertRefused(out, "COURSE_MISMATCH")
            out = self.upload("ABC 101 Au26", "courses/1001/files", f.name)
        self.assertIn("-> 201", out)


class WritableCourses(GuardTest):
    def test_readonly_courses_refused_with_reason(self):
        cases = {"1004": "course is concluded", "1005": 'name starts with "ARCHIVED:"',
                 "1006": "your role is student", "1007": "listed in deny_ids"}
        for cid, reason in cases.items():
            with self.subTest(course=cid):
                out = self.write(cid, f"courses/{cid}/pages/x")
                self.assertRefused(out, "COURSE_NOT_WRITABLE")
                self.assertIn(reason, out)

    def test_archived_course_resolves_by_label(self):
        out = self.write("ABC 310 Au26", "courses/1005/pages/x")
        self.assertRefused(out, "COURSE_NOT_WRITABLE")

    def test_inactive_enrollment(self):
        self.canvas.courses.append(course(1010, "ABC 330 A Au 26: X", "ABC 330 A", "Autumn 2026", state="invited"))
        self.assertIn("your enrollment is invited", self.write("1010", "courses/1010/pages/x"))

    def test_allow_ids(self):
        self.configure(CANVAS_MCP_ALLOW_IDS="1004")
        self.assertIn("-> 200", self.write("ABC 300 Su25", "courses/1004/pages/x"))

    def test_deny_beats_allow(self):
        self.configure(CANVAS_MCP_ALLOW_IDS="1007", CANVAS_MCP_DENY_IDS="1007")
        self.assertIn("listed in deny_ids", self.write("1007", "courses/1007/pages/x"))

    def test_extra_roles_and_empty_archived_prefix(self):
        self.configure(CANVAS_MCP_WRITABLE_ROLES="teacher,student", CANVAS_MCP_ARCHIVED_PREFIX="")
        self.assertIn("-> 200", self.write("1006", "courses/1006/pages/x"))
        self.assertIn("-> 200", self.write("1005", "courses/1005/pages/x"))


class EchoCacheLog(GuardTest):
    def test_echo_on_success_and_refusal(self):
        ok = self.write("ABC 101 Au26", "courses/1001/pages/x")
        self.assertEqual(ok.splitlines()[0],
                         "[ABC 101 A Au 26: Introduction to Things (1001), Autumn 2026] PUT courses/1001/pages/x -> 200")
        self.assertEqual(json.loads(ok.split("\n", 1)[1])["data"]["id"], 42)
        bad = self.write("ABC 101 Au26", "courses/1002/pages/x")
        self.assertEqual(bad.splitlines()[0], "[ABC 101 A Au 26: Introduction to Things (1001), Autumn 2026] "
                                              "PUT courses/1002/pages/x -> REFUSED (COURSE_MISMATCH)")
        nf = self.write("nope", "courses/1001/pages/x")
        self.assertTrue(nf.startswith('[course "nope" not resolved] PUT courses/1001/pages/x -> REFUSED'), nf)

    def test_course_list_is_paginated_and_cached(self):
        self.write("1001", "courses/1001/pages/x")
        self.write("1001", "courses/1001/pages/y")
        self.assertEqual(self.canvas.course_list_calls, 2)  # two pages, fetched once
        self.clock[0] += 601
        self.write("1001", "courses/1001/pages/z")
        self.assertEqual(self.canvas.course_list_calls, 4)  # cache expired: refetched

    def test_miss_refetches_once(self):
        self.write("1001", "courses/1001/pages/x")
        calls = self.canvas.course_list_calls
        self.canvas.courses.append(course(1011, "ABC 401 A Au 26: New", "ABC 401 A", "Autumn 2026"))
        self.assertIn("-> 200", self.write("ABC 401 Au26", "courses/1011/pages/x"))
        self.assertEqual(self.canvas.course_list_calls, calls + 2)
        calls = self.canvas.course_list_calls
        self.assertRefused(self.write("ABC 999 Au26", "courses/1011/pages/x"), "COURSE_NOT_FOUND")
        self.assertEqual(self.canvas.course_list_calls, calls + 2)  # one refetch, then refuse

    def test_audit_log_has_no_values(self):
        body = {"wiki_page": {"title": SENTINEL, "body": f"<p>{SENTINEL}</p>", "published": False},
                "grade_data": {"12345": {"posted_grade": SENTINEL}}}
        self.write("ABC 101 Au26", f"courses/1001/pages/x?search_term={SENTINEL}", body=body)
        self.write("ABC 101 Au26", "courses/1002/pages/x", body=body)
        self.write(SENTINEL, "courses/1001/pages/x", body={"x": 1})  # label is logged as passed
        with open(self.log) as f:
            text = f.read()
        self.assertEqual(text.count(SENTINEL), 1)
        ok, refused, _ = self.log_lines()
        self.assertEqual(ok["outcome"], "ok")
        self.assertEqual(ok["body_keys"], ["wiki_page.title", "wiki_page.body", "wiki_page.published",
                                           "grade_data.*.posted_grade"])
        self.assertEqual((ok["course_id"], ok["status"], ok["result_id"]), (1001, 200, 42))
        self.assertEqual(ok["path"], "courses/1001/pages/x")
        self.assertIsNone(ok["error_code"])
        self.assertEqual((refused["outcome"], refused["error_code"]), ("refused", "COURSE_MISMATCH"))
        for key in ("ts", "outcome", "error_code", "course_label", "course_id", "course_name", "method",
                    "path", "status", "body_keys", "result_id", "html_url"):
            self.assertIn(key, ok)

    def test_page_id_logged_as_result_id(self):
        def handler(req):  # Canvas returns pages with page_id rather than id
            if req.method == "POST":
                return httpx.Response(200, json={"page_id": 77, "url": "week-1", "html_url": f"https://{HOST}/x"})
            return self.canvas(req)
        with mock.patch.object(s, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))):
            self.write("ABC 101 Au26", "courses/1001/pages", "POST")
        self.assertEqual(self.log_lines()[-1]["result_id"], 77)

    def test_http_error_outcome(self):
        def handler(req):
            return httpx.Response(403, json={"errors": "no"}) if req.method == "PUT" else self.canvas(req)
        with mock.patch.object(s, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))):
            self.assertIn("-> 403", self.write("ABC 101 Au26", "courses/1001/pages/x"))
        line = self.log_lines()[-1]
        self.assertEqual((line["outcome"], line["status"]), ("http_error", 403))


class HttpxLogging(GuardTest):
    def test_request_urls_are_not_logged(self):
        # a plain handler, not assertLogs/assertNoLogs: those lower the logger's level themselves
        records = []
        handler = logging.Handler()
        handler.emit = records.append
        httpx_log = logging.getLogger("httpx")
        httpx_log.addHandler(handler)
        self.addCleanup(httpx_log.removeHandler, handler)
        s.canvas_get("courses/1001/users", {"search_term": SENTINEL})
        self.write("ABC 101 Au26", f"courses/1001/pages/x?search_term={SENTINEL}")
        self.assertEqual([r.getMessage() for r in records], [])


class CoursesTool(GuardTest):
    def test_lists_writable_by_default(self):
        out = s.canvas_courses()
        self.assertIn("Courses you can write to (3 of 8)", out)
        self.assertIn("ABC 101 A Au26", out)
        self.assertIn("unpublished", out)
        self.assertNotIn("1004", out)

    def test_include_readonly(self):
        out = s.canvas_courses(include_readonly=True)
        self.assertIn("read-only: course is concluded", out)
        self.assertIn("read-only: listed in deny_ids", out)


class Config(GuardTest):
    def test_toml_file_and_env_override(self):
        path = os.path.join(self.tmp.name, "config.toml")
        with open(path, "w") as f:
            f.write('allow_ids = [1008]\nwritable_roles = ["teacher", "ta"]\ncourse_cache_seconds = 60\n')
        cfg = s.load_config(env={"CANVAS_MCP_CONFIG": path, "CANVAS_MCP_COURSE_CACHE_SECONDS": "30"})
        self.assertEqual(cfg["allow_ids"], {1008})
        self.assertEqual(cfg["writable_roles"], ["teacher", "ta"])
        self.assertEqual(cfg["course_cache_seconds"], 30)

    def test_bad_config_refuses_writes(self):
        path = os.path.join(self.tmp.name, "config.toml")
        with open(path, "w") as f:
            f.write("allow_id = [1]\n")
        with self.assertRaises(s.ConfigError):
            s.load_config(env={"CANVAS_MCP_CONFIG": path})
        s.CONFIG_ERROR = "test error"
        self.assertRefused(self.write("1001", "courses/1001/pages/x"), "CONFIG_ERROR")

    def test_default_log_path(self):
        if sys.platform == "darwin":
            self.assertTrue(s._default_log_path({}).endswith("Library/Logs/canvas-mcp/writes.jsonl"))
        self.assertEqual(s.load_config(env={"CANVAS_MCP_CONFIG": "/nonexistent"})["audit_log_path"],
                         s._default_log_path({}))


class ToolSignatures(unittest.TestCase):
    def test_course_is_required(self):
        import asyncio
        tools = {t.name: t for t in asyncio.run(s.mcp.list_tools())}
        self.assertEqual(set(tools), {"canvas_get", "canvas_courses", "canvas_write", "canvas_upload_file"})
        for name in ("canvas_write", "canvas_upload_file"):
            self.assertIn("course", tools[name].inputSchema["required"])
            self.assertIn("ask them", tools[name].description)
        self.assertTrue(tools["canvas_courses"].annotations.readOnlyHint)


if __name__ == "__main__":
    unittest.main()
