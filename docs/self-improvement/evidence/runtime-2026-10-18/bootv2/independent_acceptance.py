#!/usr/bin/env python3
"""Independently exercise a BOOTV2 app.py using real HTTP and temporary SQLite.

Usage: python3 independent_acceptance.py /path/to/candidate-or-app.py
Only the candidate source is read. Databases, servers and imported module state
belong to this process; no checkout, existing database or running app is changed.
These HTTP tests submit native-form CRLF values directly. Browser acceptance is
separate evidence, not inferred from this script's result.
"""
import argparse
import hashlib
import html
import http.client
import json
import re
import sqlite3
import sys
import tempfile
import threading
import types
import unittest
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode


class Controls(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.forms, self.links, self.labels, self.elements = [], [], [], []
        self.form, self.textarea = None, None
        self.first_textarea_data = False
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == "form":
            self.form = {"action": attrs.get("action"), "method": attrs.get("method", "get").lower(), "fields": []}
            self.forms.append(self.form)
        if tag in ("input", "textarea"):
            control = dict(attrs)
            control.setdefault("value", "")
            if self.form is not None:
                self.form["fields"].append(control)
            if tag == "textarea":
                self.textarea = control
                self.first_textarea_data = True
        if tag == "a":
            self.links.append(attrs.get("href"))
        if tag == "label":
            self.labels.append(attrs.get("for"))

    def handle_endtag(self, tag):
        if tag == "form":
            self.form = None
        if tag == "textarea":
            self.textarea = None

    def handle_data(self, data):
        if self.textarea is not None:
            if self.first_textarea_data:
                data = data[1:] if data.startswith("\n") else data
                self.first_textarea_data = False
            self.textarea["value"] += data


class Acceptance(unittest.TestCase):
    prefix = ""
    make_server = None
    # Exactly 200 textarea characters after CRLF is interpreted as one newline.
    boundary = "事" * 100 + "\r\n" + "项" * 99
    too_long = "事" * 100 + "\r\n" + "项" * 100

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bootv2-independent-acceptance-")
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / "test-only.db"
        self.server, self.thread = None, None
        self.addCleanup(self.stop)
        self.start()
        self.other = self.create("另一条事项不能变化")
        self.target = self.create("编辑前的标题")
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % self.target,
                                   {"csrf": self.csrf(), "done": "1"})[0], 303)

    def start(self):
        self.server = self.make_server(("127.0.0.1", 0), self.database, self.prefix, "独立临时验收")
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                raise RuntimeError("Owned temporary server did not stop")
            self.server = None

    def call(self, method, path, fields=None, raw=None):
        body = raw if raw is not None else urlencode(fields).encode("ascii") if fields is not None else None
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        try:
            connection.request(method, path, body, {"Content-Type": "application/x-www-form-urlencoded"})
            response = connection.getresponse()
            payload = response.read()
            self.assertEqual(int(response.getheader("Content-Length")), len(payload))
            return response.status, dict(response.getheaders()), payload.decode("utf-8")
        finally:
            connection.close()

    def csrf(self):
        status, _, page = self.call("GET", self.prefix + "/")
        self.assertEqual(status, 200)
        return re.search(r'name="csrf" value="([^"]+)"', page)[1]

    def rows(self):
        with sqlite3.connect(self.database) as db:
            return db.execute("SELECT id,title,done FROM items ORDER BY id").fetchall()

    def create(self, title):
        status, _, _ = self.call("POST", self.prefix + "/items", {"csrf": self.csrf(), "title": title})
        self.assertEqual(status, 303)
        return self.rows()[-1][0]

    def edit_path(self, item_id=None):
        return self.prefix + "/items/%d/edit" % (self.target if item_id is None else item_id)

    def form(self, page, title, item_id=None):
        parsed = Controls(page)
        forms = [form for form in parsed.forms if form["action"] == self.edit_path(item_id)]
        self.assertEqual(len(forms), 1, "Recovery must target the original item")
        form = forms[0]
        self.assertEqual(form["method"], "post")
        fields = {field["name"]: field["value"] for field in form["fields"]
                  if field.get("name") and "disabled" not in field}
        self.assertEqual(fields["title"], title, "Full title must survive without trimming or truncation")
        self.assertTrue(fields.get("csrf"))
        title_field = next(field for field in form["fields"] if field.get("name") == "title")
        self.assertIn(title_field.get("id"), parsed.labels)
        self.assertIn(self.prefix + "/", parsed.links)
        return form["action"], fields

    def assert_only_target_changed(self, before, title):
        self.assertEqual(self.rows(), [(row_id, title if row_id == self.target else prior, done)
                                       for row_id, prior, done in before])

    def assert_safe(self, page):
        for tag, attrs in Controls(page).elements:
            self.assertNotEqual(tag, "script", "Title text must not become executable markup")
            self.assertFalse(any(name.lower().startswith("on") for name in attrs))

    @contextmanager
    def unavailable_database(self):
        backup = self.database.with_suffix(".owned-backup")
        self.database.rename(backup)
        self.database.mkdir()
        try:
            yield
        finally:
            self.database.rmdir()
            backup.rename(self.database)

    def test_native_crlf_200_saves_exact_text_id_state_refresh_and_restart(self):
        before = self.rows()
        status, _, page = self.call("GET", self.edit_path())
        self.assertEqual(status, 200)
        action, fields = self.form(page, "编辑前的标题")
        fields["title"] = self.boundary
        status, headers, _ = self.call("POST", action, fields)
        self.assertEqual(status, 303, "200 textarea characters must save after native CRLF serialization")
        self.assertEqual(headers.get("Location"), self.prefix + "/")
        self.assert_only_target_changed(before, self.boundary)
        self.assertIn(html.escape(self.boundary), self.call("GET", self.prefix + "/")[2])
        self.stop()
        self.start()
        self.assert_only_target_changed(before, self.boundary)
        self.form(self.call("GET", self.edit_path())[2], self.boundary)

    def test_201_rejected_complete_input_retained_then_same_item_retried(self):
        before = self.rows()
        status, _, page = self.call("POST", self.edit_path(), {"csrf": self.csrf(), "title": self.too_long})
        self.assertEqual(status, 400)
        self.assertIn("200", page)
        action, fields = self.form(page, self.too_long)
        self.assertEqual(self.rows(), before)
        fields["title"] = "  改正后的标题\r\n尾部空白  "
        self.assertEqual(self.call("POST", action, fields)[0], 303)
        self.assert_only_target_changed(before, fields["title"])

    def test_database_failure_retains_boundary_input_and_retries_only_original(self):
        before = self.rows()
        fields = {"csrf": self.csrf(), "title": self.boundary}
        with self.unavailable_database():
            self.assertEqual(self.call("GET", self.prefix + "/health")[0], 503)
            status, _, page = self.call("POST", self.edit_path(), fields)
            self.assertEqual(status, 503)
            action, recovered = self.form(page, self.boundary)
        self.assertEqual(self.rows(), before)
        status, headers, _ = self.call("POST", action, recovered)
        self.assertEqual(status, 303, "Recovery must save the full 200-character title, not create another item")
        self.assertEqual(headers.get("Location"), self.prefix + "/")
        self.assert_only_target_changed(before, self.boundary)
        self.stop()
        self.start()
        self.assert_only_target_changed(before, self.boundary)

    def test_blank_csrf_and_missing_item_rejections_leave_database_unchanged(self):
        before = self.rows()
        for title in ("", " \t\r\n "):
            with self.subTest(blank=repr(title)):
                status, _, page = self.call("POST", self.edit_path(), {"csrf": self.csrf(), "title": title})
                self.assertEqual(status, 400)
                self.form(page, title)
                self.assertEqual(self.rows(), before)
        for csrf in (None, "invalid-token"):
            with self.subTest(csrf="missing" if csrf is None else "invalid"):
                fields = {"title": "无授权不能覆盖\r\n原文"}
                if csrf is not None:
                    fields["csrf"] = csrf
                status, _, page = self.call("POST", self.edit_path(), fields)
                self.assertEqual(status, 403)
                self.form(page, fields["title"])
                self.assertEqual(self.rows(), before)
        missing = self.target + 1000
        self.assertEqual(self.call("GET", self.edit_path(missing))[0], 404)
        self.assertEqual(self.call("POST", self.edit_path(missing), {"csrf": self.csrf(), "title": "不存在的事项"})[0], 404)
        self.assertEqual(self.rows(), before)

    def test_escape_cancel_and_existing_completion_behaviors_survive(self):
        before = self.rows()
        title = '\n"\' & </textarea><script>alert(1)</script>\r\n完整尾部'
        self.assertEqual(self.call("POST", self.edit_path(), {"csrf": self.csrf(), "title": title})[0], 303)
        self.assert_only_target_changed(before, title)
        status, _, page = self.call("GET", self.edit_path())
        self.assertEqual(status, 200)
        self.form(page, title)
        self.assert_safe(page)
        before_cancel = self.rows()
        status, _, home = self.call("GET", self.prefix + "/")
        self.assertEqual(status, 200)
        self.assert_safe(home)
        self.assertIn(self.edit_path(), Controls(home).links)
        self.assertEqual(self.rows(), before_cancel)
        for done in (0, 1):
            self.assertEqual(self.call("POST", self.prefix + "/items/%d" % self.target,
                                       {"csrf": self.csrf(), "done": str(done)})[0], 303)
            self.assertEqual(self.rows(), [(row_id, text, done if row_id == self.target else state)
                                           for row_id, text, state in before_cancel])

    def test_invalid_utf8_is_rejected_without_silent_replacement(self):
        before = self.rows()
        for title in (b"%FF", b"%E4%B8"):
            with self.subTest(encoded=title.decode("ascii")):
                body = b"title=" + title + b"&csrf=" + self.csrf().encode("ascii")
                self.assertEqual(self.call("POST", self.edit_path(), raw=body)[0], 400)
                self.assertEqual(self.rows(), before)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="Candidate directory containing app.py, or the exact source file")
    args = parser.parse_args()
    source_path = args.candidate / "app.py" if args.candidate.is_dir() else args.candidate
    source_path = source_path.resolve()
    source = source_path.read_bytes()
    module = types.ModuleType("bootv2_independent_candidate")
    module.__file__ = str(source_path)
    sys.modules[module.__name__] = module
    exec(compile(source, str(source_path), "exec"), module.__dict__)
    print(json.dumps({"candidate": str(source_path), "sha256": hashlib.sha256(source).hexdigest(),
                      "database": "temporary per test", "port": "random loopback per server",
                      "existing_services_used": False, "browser_acceptance_performed": False}, ensure_ascii=False), flush=True)
    suite = unittest.TestSuite()
    for name, prefix in (("NoPrefixAcceptance", ""), ("PreviewPrefixAcceptance", "/pv/BOOTV2-1/__commit/independent-candidate")):
        case = type(name, (Acceptance,), {"prefix": prefix, "make_server": staticmethod(module.make_server)})
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    unchanged = source_path.read_bytes() == source
    successful = result.wasSuccessful() and unchanged
    if not unchanged:
        print("Candidate source changed during validation; these results cannot validate the current file.", file=sys.stderr)
    print(json.dumps({"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                      "successful": successful, "source_unchanged": unchanged},
                     ensure_ascii=False), flush=True)
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
