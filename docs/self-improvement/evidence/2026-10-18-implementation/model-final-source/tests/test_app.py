import http.client
import json
import re
import sqlite3
import tempfile
import threading
import unittest
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from app import make_server


class Page(HTMLParser):
    """Read the controls a browser receives, including decoded attribute values."""

    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.controls = []
        self.links = []
        self.link_attrs = []
        self.labels = []
        self.elements = []
        self.frames = []
        self.element_stack = []
        self.scripts = []
        self.text = []
        self.form = None
        self.textarea = None
        self.textarea_first_data = False
        self.script = None
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == "iframe":
            self.frames.append({"attrs": attrs, "ancestors": list(self.element_stack)})
        if tag not in ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"):
            self.element_stack.append((tag, attrs))
        if tag == "form":
            self.form = {"action": attrs.get("action"),
                         "method": attrs.get("method", "get").lower(),
                         "target": attrs.get("target"), "controls": []}
            self.forms.append(self.form)
        elif tag in ("input", "textarea"):
            control = dict(attrs)
            control.setdefault("value", "")
            self.controls.append(control)
            if self.form is not None:
                self.form["controls"].append(control)
            if tag == "textarea":
                self.textarea = control
                self.textarea_first_data = True
        elif tag == "a":
            self.links.append(attrs.get("href"))
            self.link_attrs.append(attrs)
        elif tag == "label":
            self.labels.append(attrs.get("for"))
        elif tag == "script":
            self.script = {"attrs": attrs, "source": ""}
            self.scripts.append(self.script)

    def handle_endtag(self, tag):
        for index in range(len(self.element_stack) - 1, -1, -1):
            if self.element_stack[index][0] == tag:
                del self.element_stack[index:]
                break
        if tag == "form":
            self.form = None
        elif tag == "textarea":
            self.textarea = None
        elif tag == "script":
            self.script = None

    def handle_data(self, data):
        self.text.append(data)
        if self.script is not None:
            self.script["source"] += data
        if self.textarea is not None:
            if self.textarea_first_data:
                data = data[1:] if data.startswith("\n") else data
                self.textarea_first_data = False
            self.textarea["value"] += data


class ApplicationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "app.db"
        self.prefix = "/demo"
        self.edit_script_source = None
        self.start()
        self.addCleanup(self.stop)

    def start(self, prefix=None):
        if prefix is not None:
            self.prefix = prefix
        self.server = make_server(("127.0.0.1", 0), self.db, self.prefix, "项目测试")
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
            self.server = None

    def call(self, method, path, data=None):
        status, _, body = self.call_response(method, path, data)
        return status, body

    def call_response(self, method, path, data=None, headers=None):
        body = urlencode(data).encode("ascii") if data is not None else None
        return self.call_raw_response(method, path, body, headers)

    def call_raw_response(self, method, path, body, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
            request_headers.update(headers or {})
            conn.request(method, path, body, request_headers)
            return self.read_response(conn)
        finally:
            conn.close()

    def read_response(self, conn):
        response = conn.getresponse()
        headers = dict(response.getheaders())
        body = response.read()
        self.assertEqual(int(headers["Content-Length"]), len(body))
        return response.status, headers, body.decode("utf-8")

    def call_declared_body(self, path, size, headers=None):
        """Send only headers: an oversized request must be rejected without a body."""
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            conn.putrequest("POST", path)
            conn.putheader("Content-Type", "application/x-www-form-urlencoded")
            conn.putheader("Content-Length", str(size))
            for name, value in (headers or {}).items():
                conn.putheader(name, value)
            conn.endheaders()
            return self.read_response(conn)
        finally:
            conn.close()

    def call_json(self, path, data):
        status, headers, body = self.call_response("POST", path, data,
                                                 {"Accept": "application/json"})
        self.assertIn("application/json", headers["Content-Type"])
        return status, json.loads(body)

    def csrf(self):
        code, page = self.call("GET", self.prefix + "/")
        self.assertEqual(code, 200)
        return re.search('name="csrf" value="([^"]+)"', page)[1]

    def rows(self):
        with sqlite3.connect(self.db) as db:
            return db.execute("SELECT id,title,done FROM items ORDER BY id").fetchall()

    def create(self, title):
        self.assertEqual(self.call("POST", self.prefix + "/items",
                                   {"csrf": self.csrf(), "title": title})[0], 303)
        item_id = self.rows()[-1][0]
        if self.edit_script_source is None:
            page = Page(self.call("GET", self.edit_path(item_id))[1])
            self.assertEqual(len(page.scripts), 1)
            self.assertEqual(page.scripts[0]["attrs"].get("id"), "edit-script")
            self.edit_script_source = page.scripts[0]["source"]
            self.assertTrue(self.edit_script_source.strip())
        return item_id

    def edit_path(self, item_id):
        return self.prefix + "/items/%d/edit" % item_id

    def edit_form(self, page, item_id, title):
        parsed = Page(page)
        forms = [form for form in parsed.forms
                 if form["action"] == self.edit_path(item_id) + "?result=1"]
        self.assertEqual(len(forms), 1, page)
        form = forms[0]
        self.assertEqual(form["method"], "post")
        self.assertIn(form["target"], ("edit-result", "_self"))
        if form["target"] == "edit-result":
            self.assert_native_result_frame(parsed)
        else:
            self.assertEqual(parsed.frames, [])
            self.assertEqual(parsed.scripts, [])
        fields = {control["name"]: control["value"] for control in form["controls"]
                  if "name" in control and "disabled" not in control}
        self.assertEqual(fields.get("title"), title)
        self.assertTrue(fields.get("csrf"))
        title_controls = [control for control in form["controls"]
                          if control.get("name") == "title"]
        self.assertEqual(len(title_controls), 1)
        if form["target"] == "_self":
            self.assertIn("readonly", title_controls[0])
        else:
            self.assertNotIn("readonly", title_controls[0])
        self.assertIn(title_controls[0].get("id"), parsed.labels)
        self.assertIn(self.prefix + "/", parsed.links)
        return form["action"], fields

    def assert_native_result_frame(self, parsed):
        self.assertEqual(len(parsed.frames), 1)
        frame = parsed.frames[0]
        self.assertEqual(frame["attrs"].get("id"), "edit-result")
        self.assertEqual(frame["attrs"].get("name"), "edit-result")
        self.assertEqual(frame["attrs"].get("title"), "保存结果")
        self.assertTrue(any(attrs.get("role") == "region" for _, attrs in frame["ancestors"]))
        for tag, attrs in frame["ancestors"] + [("iframe", frame["attrs"])]:
            self.assertNotIn(tag, ("script", "noscript"))
            self.assertNotIn("hidden", attrs)
            self.assertNotEqual(attrs.get("aria-hidden"), "true")
            style = attrs.get("style", "").replace(" ", "").lower()
            self.assertNotIn("display:none", style)
            self.assertNotIn("visibility:hidden", style)

    def assert_inline_saved(self, response):
        status, headers, page = response
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        parsed = Page(page)
        self.assertIn("已保存", "".join(parsed.text))
        self.assertTrue(any(link.get("href") == self.prefix + "/" and link.get("target") == "_parent"
                            for link in parsed.link_attrs))
        self.assertEqual(parsed.frames, [])
        self.assertEqual(parsed.scripts, [])

    def assert_safe_markup(self, page):
        parsed = Page(page)
        self.assertLessEqual(len(parsed.scripts), 1)
        for script in parsed.scripts:
            self.assertEqual(script["attrs"].get("id"), "edit-script")
            self.assertNotIn("src", script["attrs"])
            self.assertEqual(script["source"], self.edit_script_source)
        for _, attrs in parsed.elements:
            self.assertFalse(any(name.lower().startswith("on") for name in attrs), page)

    def assert_oversized_rejection(self, status, headers, page, item_id):
        self.assertEqual(status, 413)
        self.assertEqual(headers.get("Connection", "").lower(), "close")
        parsed = Page(page)
        self.assertIn("未读取", "".join(parsed.text))
        self.assertIn("未修改", "".join(parsed.text))
        self.assertIn(self.edit_path(item_id), parsed.links)
        self.assertIn(self.prefix + "/", parsed.links)
        self.assert_safe_markup(page)

    def assert_retained_input(self, page, title):
        parsed = Page(page)
        self.assertIn(title, [control["value"] for control in parsed.controls
                              if control.get("name") == "title"])
        self.assertIn(self.prefix + "/", parsed.links)
        self.assert_safe_markup(page)

    @contextmanager
    def unavailable_database(self):
        backup = self.db.with_suffix(".backup")
        self.db.rename(backup)
        self.db.mkdir()
        try:
            yield
        finally:
            self.db.rmdir()
            backup.rename(self.db)

    def test_create_persist_and_complete(self):
        token = self.csrf()
        self.assertEqual(self.call("POST", "/demo/items", {"csrf": token, "title": "发布第一个版本"})[0], 303)
        self.assertIn("发布第一个版本", self.call("GET", "/demo/")[1])
        self.assertEqual(self.call("POST", "/demo/items/1", {"csrf": token, "done": "1"})[0], 303)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT title,done FROM items").fetchone(), ("发布第一个版本", 1))

    def test_validation_and_csrf(self):
        self.assertEqual(self.call("POST", "/demo/items", {"title": "禁止跨站提交"})[0], 403)
        self.assertEqual(self.call("POST", "/demo/items", {"csrf": "非法令牌", "title": "拒绝"})[0], 403)
        self.assertEqual(self.call("POST", "/demo/items", {"csrf": self.csrf(), "title": " "})[0], 400)

    def test_data_survives_server_restart(self):
        self.call("POST", "/demo/items", {"csrf": self.csrf(), "title": "重启后仍在"})
        self.stop()
        self.server = make_server(("127.0.0.1", 0), self.db, "/demo", "项目测试")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.assertIn("重启后仍在", self.call("GET", "/demo/")[1])

    def test_storage_failure_is_visible_and_keeps_pending_input(self):
        token = self.csrf()
        backup = self.db.with_suffix(".backup")
        self.db.rename(backup)
        self.db.mkdir()
        try:
            self.assertEqual(self.call("GET", "/demo/health")[0], 503)
            code, page = self.call("POST", "/demo/items", {"csrf": token, "title": "保留未保存的文字"})
            self.assertEqual(code, 503)
            self.assertIn("保留未保存的文字", page)
        finally:
            self.db.rmdir()
            backup.rename(self.db)

    def test_user_text_is_escaped_and_health_is_real(self):
        self.call("POST", "/demo/items", {"csrf": self.csrf(), "title": "<script>alert(1)</script>"})
        page = self.call("GET", "/demo/")[1]
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertEqual(json.loads(self.call("GET", "/demo/health")[1]), {"status": "ok"})
        self.assertEqual(self.call("GET", "/missing")[0], 404)

    def test_edit_preserves_id_state_and_other_items_across_restart(self):
        untouched = self.create("另一个事项")
        for done in (0, 1):
            with self.subTest(done=done):
                item_id = self.create("待编辑事项")
                self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                           {"csrf": self.csrf(), "done": str(done)})[0], 303)
                before = self.rows()
                path = self.edit_path(item_id)
                self.assertIn(path, Page(self.call("GET", self.prefix + "/")[1]).links)
                status, page = self.call("GET", path)
                self.assertEqual(status, 200)
                action, fields = self.edit_form(page, item_id, "待编辑事项")
                self.assertIn("取消", page)
                self.assertIn("保存", page)
                # Following the cancel link does not write anything.
                self.assertEqual(self.call("GET", self.prefix + "/")[0], 200)
                self.assertEqual(self.rows(), before)
                title = "  修改后的事项 %d  " % done
                fields["title"] = title
                self.assert_inline_saved(self.call_response("POST", action, fields))
                expected = [(i, title if i == item_id else text, state)
                            for i, text, state in before]
                self.assertEqual(self.rows(), expected)
                self.assertIn(title, self.call("GET", self.prefix + "/")[1])
                self.stop()
                self.start()
                self.assertIn(title, self.call("GET", self.prefix + "/")[1])
                self.assertEqual(self.rows(), expected)
                self.edit_form(self.call("GET", path)[1], item_id, title)
                for state in (1, 0):
                    self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                               {"csrf": self.csrf(), "done": str(state)})[0], 303)
                    self.assertIn((item_id, title, state), self.rows())
                self.assertIn((untouched, "另一个事项", 0), self.rows())

    def test_edit_rejects_invalid_input_and_retries_original_item(self):
        item_id = self.create("保留原文")
        self.create("其他事项")
        invalid_titles = ("", "   ", "\t\r\n ", "字" * 201,
                          '"</textarea><script>alert(1)</script>' + "字" * 201)
        for title in invalid_titles:
            with self.subTest(title=repr(title[:30])):
                before = self.rows()
                status, page = self.call("POST", self.edit_path(item_id),
                                         {"csrf": self.csrf(), "title": title})
                self.assertEqual(status, 400)
                self.assertIn("200", "".join(Page(page).text))
                action, fields = self.edit_form(page, item_id, title)
                self.assert_safe_markup(page)
                self.assertEqual(self.rows(), before)
                fields["title"] = "修正后的标题"
                self.assert_inline_saved(self.call_response("POST", action, fields))
                self.assertEqual(self.rows(), [(i, fields["title"] if i == item_id else text, done)
                                               for i, text, done in before])

    def test_edit_accepts_boundary_lengths_and_preserves_original_text(self):
        item_id = self.create("原始标题")
        for title in ("字", "字" * 200, "  留下首尾空白  ", "\n换行\r\n标题\n"):
            with self.subTest(title=repr(title[:30])):
                status, headers, _ = self.call_response("POST", self.edit_path(item_id),
                                                       {"csrf": self.csrf(), "title": title})
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), self.prefix + "/")
                self.assertEqual(self.rows(), [(item_id, title, 0)])
                self.edit_form(self.call("GET", self.edit_path(item_id))[1], item_id, title)
        # Raw submitted length is limited even if stripping would make it short enough.
        title = " " + "字" * 200
        status, page = self.call("POST", self.edit_path(item_id),
                                 {"csrf": self.csrf(), "title": title})
        self.assertEqual(status, 400)
        self.edit_form(page, item_id, title)
        self.assertEqual(self.rows(), [(item_id, "\n换行\r\n标题\n", 0)])

    def test_edit_csrf_and_missing_item_errors_keep_input_without_writes(self):
        item_id = self.create("不应改变")
        before = self.rows()
        title = '\" onfocus=\"alert(1)\"><script>alert(1)</script>'
        for csrf in (None, "非法令牌"):
            with self.subTest(csrf=csrf):
                fields = {"title": title}
                if csrf is not None:
                    fields["csrf"] = csrf
                status, page = self.call("POST", self.edit_path(item_id), fields)
                self.assertEqual(status, 403)
                self.assert_retained_input(page, title)
                self.assertEqual(self.rows(), before)
        missing_id = item_id + 1000
        self.assertEqual(self.call("GET", self.edit_path(missing_id))[0], 404)
        for submitted_title in (title, "", "字" * 201):
            with self.subTest(missing_title=repr(submitted_title[:30])):
                status, page = self.call("POST", self.edit_path(missing_id),
                                         {"csrf": self.csrf(), "title": submitted_title})
                self.assertEqual(status, 404)
                self.assert_retained_input(page, submitted_title)
                self.assertEqual(self.rows(), before)
        for invalid_id in ("0", "-1", "not-an-id", "9223372036854775808", "1/extra"):
            with self.subTest(invalid_id=invalid_id):
                path = self.prefix + "/items/" + invalid_id + "/edit"
                self.assertEqual(self.call("GET", path)[0], 404)
                self.assertEqual(self.call("POST", path,
                                           {"csrf": self.csrf(), "title": title})[0], 404)
                self.assertEqual(self.rows(), before)
        # Rejection must precede both the existence lookup and opening the database.
        with self.unavailable_database():
            for target in (item_id, missing_id):
                status, page = self.call("POST", self.edit_path(target),
                                         {"csrf": "非法令牌", "title": title})
                self.assertEqual(status, 403)
                self.assert_retained_input(page, title)
        self.assertEqual(self.rows(), before)

    def test_edit_storage_failure_keeps_actual_action_and_retries_only_target(self):
        other_id = self.create("保留另一条")
        item_id = self.create("故障前标题")
        token = self.csrf()
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                   {"csrf": token, "done": "1"})[0], 303)
        before = self.rows()
        title = '\n故障后保留 "引号" & </textarea><script>alert(1)</script>\r\n'
        with self.unavailable_database():
            self.assertEqual(self.call("GET", self.prefix + "/health")[0], 503)
            self.assertEqual(self.call("GET", self.edit_path(item_id))[0], 503)
            status, page = self.call("POST", self.edit_path(item_id),
                                     {"csrf": token, "title": title})
            self.assertEqual(status, 503)
            action, fields = self.edit_form(page, item_id, title)
            self.assert_safe_markup(page)
        self.assertEqual(self.rows(), before)
        self.assert_inline_saved(self.call_response("POST", action, fields))
        self.assertEqual(self.rows(), [(other_id, "保留另一条", 0), (item_id, title, 1)])
        self.assertEqual(json.loads(self.call("GET", self.prefix + "/health")[1]),
                         {"status": "ok"})

    def test_edit_failure_retains_empty_and_invalid_input_before_revalidation(self):
        item_id = self.create("未改变")
        before = self.rows()
        token = self.csrf()
        for title in ("", " \t\n ", "字" * 201):
            with self.subTest(title=repr(title[:30])):
                with self.unavailable_database():
                    status, page = self.call("POST", self.edit_path(item_id),
                                             {"csrf": token, "title": title})
                    self.assertEqual(status, 503)
                    action, fields = self.edit_form(page, item_id, title)
                status, page = self.call("POST", action, fields)
                self.assertEqual(status, 400)
                self.edit_form(page, item_id, title)
                self.assertEqual(self.rows(), before)

    def test_create_failure_form_still_retries_creation(self):
        item_id = self.create("原有事项")
        token = self.csrf()
        title = '恢复后新增 "标题" & <script>alert(1)</script>'
        with self.unavailable_database():
            status, page = self.call("POST", self.prefix + "/items",
                                     {"csrf": token, "title": title})
            self.assertEqual(status, 503)
            forms = [form for form in Page(page).forms
                     if form["action"] == self.prefix + "/items"]
            self.assertEqual(len(forms), 1)
            form = forms[0]
            fields = {control["name"]: control["value"] for control in form["controls"]
                      if "name" in control}
            self.assertEqual(form["method"], "post")
            self.assertEqual(fields["title"], title)
            self.assert_safe_markup(page)
        self.assertEqual(self.call("POST", form["action"], fields)[0], 303)
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], (item_id, "原有事项", 0))
        self.assertEqual(rows[1][1:], (title, 0))

    def test_edit_escaping_and_links_work_with_empty_and_preview_prefixes(self):
        title = '\"\' & </textarea><script>alert(1)</script>'
        for prefix in ("", "/demo", "/pv/BOOTV2/session"):
            with self.subTest(prefix=prefix):
                self.stop()
                self.start(prefix)
                item_id = self.create("等待编辑")
                other_rows = self.rows()[:-1]
                path = self.edit_path(item_id)
                home = Page(self.call("GET", prefix + "/")[1])
                self.assertIn(path, home.links)
                status, page = self.call("GET", path)
                self.assertEqual(status, 200)
                action, fields = self.edit_form(page, item_id, "等待编辑")
                fields["title"] = title
                self.assert_inline_saved(self.call_response("POST", action, fields))
                page = self.call("GET", prefix + "/")[1]
                self.assert_safe_markup(page)
                self.assertIn(title, "".join(Page(page).text))
                page = self.call("GET", path)[1]
                self.edit_form(page, item_id, title)
                self.assert_safe_markup(page)
                status, page = self.call("POST", path, {"csrf": self.csrf(), "title": ""})
                self.assertEqual(status, 400)
                self.edit_form(page, item_id, "")
                token = self.csrf()
                with self.unavailable_database():
                    status, page = self.call("POST", path, {"csrf": token, "title": title})
                    self.assertEqual(status, 503)
                    action, fields = self.edit_form(page, item_id, title)
                    self.assert_safe_markup(page)
                self.assert_inline_saved(self.call_response("POST", action, fields))
                self.assertEqual(self.rows(), other_rows + [(item_id, title, 0)])

    def test_edit_above_recovery_limit_rejects_without_body_or_storage(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        item_id = self.create("原始标题保持不变")
        self.create("其他事项保持不变")
        before = self.rows()
        reads = []
        handler_class = self.server.RequestHandlerClass
        original_setup = handler_class.setup

        class NoBodyReader:
            def __init__(self, stream):
                self.stream = stream

            def read(self, size=-1):
                reads.append(size)
                raise AssertionError("body above recovery limit must not be read")

            read1 = read
            readinto = read

            def __getattr__(self, name):
                return getattr(self.stream, name)

        def setup_without_body_reads(handler):
            original_setup(handler)
            handler.rfile = NoBodyReader(handler.rfile)

        for size in (65537, 1024 * 1024):
            for accept in (None, "application/json"):
                with self.subTest(declared_bytes=size, accept=accept):
                    with patch.object(handler_class, "setup", setup_without_body_reads), \
                         patch("app.sqlite3.connect", side_effect=AssertionError("must not open database")) as connect, \
                         patch("tempfile.TemporaryFile", side_effect=AssertionError("must not spool body")) as temporary, \
                         patch("tempfile.NamedTemporaryFile", side_effect=AssertionError("must not spool body")) as named, \
                         patch("tempfile.SpooledTemporaryFile", side_effect=AssertionError("must not spool body")) as spooled:
                        headers = {"Accept": accept} if accept else None
                        response = self.call_declared_body(self.edit_path(item_id), size, headers)
                    if accept:
                        status, headers, body = response
                        self.assertEqual(status, 413)
                        self.assertEqual(headers.get("Connection", "").lower(), "close")
                        self.assertIn("application/json", headers["Content-Type"])
                        self.assertTrue(json.loads(body)["error"])
                    else:
                        self.assert_oversized_rejection(*response, item_id)
                    connect.assert_not_called()
                    temporary.assert_not_called()
                    named.assert_not_called()
                    spooled.assert_not_called()
                    self.assertEqual(reads, [])
                    self.assertEqual(self.rows(), before)
        # No body or CSRF was sent, including for the declared 1 MiB request.
        # Browser-side retention is checked separately from this hard rejection.

    def test_edit_recovery_preserves_9055_byte_input_without_temporary_storage(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        other_id = self.create("其他事项保持不变")
        item_id = self.create("保留现有标题")
        token = self.csrf()
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                   {"csrf": token, "done": "1"})[0], 303)
        before = self.rows()
        title = "字" * 1000
        submitted = [("title", title), ("csrf", token)]
        self.assertEqual(len(token), 43)
        self.assertEqual(len(urlencode(submitted).encode("ascii")), 9055)
        with patch("tempfile.TemporaryFile", side_effect=OSError("temporary storage unavailable")) as temporary:
            status, page = self.call("POST", self.edit_path(item_id), submitted)
        temporary.assert_not_called()
        self.assertEqual(status, 400)
        self.assertIn("200", "".join(Page(page).text))
        action, fields = self.edit_form(page, item_id, title)
        self.assert_safe_markup(page)
        self.assertEqual(self.rows(), before)
        fields["title"] = "纠正后的可保存标题"
        self.assert_inline_saved(self.call_response("POST", action, fields))
        self.assertEqual(self.rows(), [(other_id, "其他事项保持不变", 0),
                                       (item_id, fields["title"], 1)])

    def test_edit_recovery_keeps_input_on_csrf_missing_item_and_database_errors(self):
        item_id = self.create("不能修改的标题")
        self.create("其他事项不变")
        before = self.rows()
        token = self.csrf()
        title = '\n' + "字" * 1000 + '\" & % + </textarea><script>alert(1)</script>🙂\r\n'
        submitted = [("title", title), ("csrf", token)]
        self.assertGreater(len(urlencode(submitted).encode("ascii")), 8192)
        self.assertLessEqual(len(urlencode(submitted).encode("ascii")), 65536)
        for csrf in (None, "非法令牌"):
            with self.subTest(csrf=csrf):
                fields = [("title", title)]
                if csrf is not None:
                    fields.append(("csrf", csrf))
                status, page = self.call("POST", self.edit_path(item_id), fields)
                self.assertEqual(status, 403)
                self.assert_retained_input(page, title)
                self.assertEqual(self.rows(), before)
        status, page = self.call("POST", self.edit_path(item_id + 1000), submitted)
        self.assertEqual(status, 404)
        self.assert_retained_input(page, title)
        self.assertEqual(self.rows(), before)
        with self.unavailable_database():
            status, page = self.call("POST", self.edit_path(item_id), submitted)
            self.assertEqual(status, 503)
            action, fields = self.edit_form(page, item_id, title)
            self.assert_safe_markup(page)
        self.assertEqual(self.rows(), before)
        parent_action, parent_fields = action, fields.copy()
        status, page = self.call("POST", action, fields)
        self.assertEqual(status, 400)
        self.edit_form(page, item_id, title)
        self.assertEqual(self.rows(), before)
        # The inline recovery control is readonly; corrections use the retained
        # parent form, not a fabricated edit to that readonly control.
        parent_fields["title"] = "恢复后修正标题"
        self.assert_inline_saved(self.call_response("POST", parent_action, parent_fields))
        self.assertEqual(self.rows(), [(i, parent_fields["title"] if i == item_id else text, done)
                                       for i, text, done in before])

    def test_edit_save_and_recovery_body_boundaries(self):
        item_id = self.create("边界前标题")
        self.create("边界测试保留其他事项")
        token = self.csrf()
        for size in (8191, 8192, 8193, 65536, 65537):
            with self.subTest(body_bytes=size):
                title = str(size) + "界" * (200 - len(str(size)))
                self.assertEqual(len(title), 200)
                submitted = [("title", title), ("csrf", token), ("padding", "")]
                base_size = len(urlencode(submitted).encode("ascii"))
                submitted[-1] = ("padding", "x" * (size - base_size))
                self.assertEqual(len(urlencode(submitted).encode("ascii")), size)
                before = self.rows()
                if size <= 8192:
                    status, _ = self.call("POST", self.edit_path(item_id), submitted)
                    self.assertEqual(status, 303)
                    self.assertEqual(self.rows(), [(i, title if i == item_id else text, done)
                                                   for i, text, done in before])
                elif size <= 65536:
                    status, page = self.call("POST", self.edit_path(item_id), submitted)
                    self.assertEqual(status, 413)
                    self.edit_form(page, item_id, title)
                    self.assert_safe_markup(page)
                    self.assertEqual(self.rows(), before)
                else:
                    response = self.call_declared_body(self.edit_path(item_id), size)
                    self.assert_oversized_rejection(*response, item_id)
                    self.assertEqual(self.rows(), before)
        status, headers, _ = self.call_declared_body(self.prefix + "/items", 8193)
        self.assertEqual(status, 413)
        self.assertEqual(headers.get("Connection", "").lower(), "close")
        self.assertEqual(self.rows(), before)

    def test_edit_request_body_reads_stay_within_recovery_budget(self):
        item_id = self.create("读取前标题")
        self.create("不应改变的另一行")
        token = self.csrf()
        title = "限额内更新"
        handler_class = self.server.RequestHandlerClass
        original_setup = handler_class.setup
        for size in (8192, 65536):
            with self.subTest(body_bytes=size):
                before = self.rows()
                submitted = [("title", title), ("csrf", token), ("padding", "")]
                base_size = len(urlencode(submitted).encode("ascii"))
                submitted[-1] = ("padding", "x" * (size - base_size))
                self.assertEqual(len(urlencode(submitted).encode("ascii")), size)
                requests, consumed = [], []

                class BudgetedReader:
                    def __init__(self, stream):
                        self.stream = stream

                    def read(self, requested=-1):
                        requests.append(requested)
                        if not 0 < requested <= 65536 or sum(consumed) + requested > 65536:
                            raise AssertionError("cumulative body reads must not exceed 65536 bytes")
                        data = self.stream.read(requested)
                        consumed.append(len(data))
                        return data

                    def __getattr__(self, name):
                        return getattr(self.stream, name)

                def setup_with_budget(handler):
                    original_setup(handler)
                    handler.rfile = BudgetedReader(handler.rfile)

                with patch.object(handler_class, "setup", setup_with_budget):
                    status, page = self.call("POST", self.edit_path(item_id), submitted)
                self.assertTrue(requests)
                self.assertEqual(sum(consumed), size)
                if size <= 8192:
                    self.assertEqual(status, 303)
                    self.assertEqual(self.rows(), [(i, title if i == item_id else text, done)
                                                   for i, text, done in before])
                else:
                    self.assertEqual(status, 413)
                    self.edit_form(page, item_id, title)
                    self.assertEqual(self.rows(), before)

    def test_form_decoder_preserves_first_values_and_encoded_names(self):
        item_id = self.create("原始标题")
        token = self.csrf()
        title = '保留首值 " & % + </textarea><script>alert(1)</script>'
        cases = (
            ([("title", title), ("title", "忽略后值"), ("csrf", token), ("csrf", "非法")], 303, title),
            ([("title", ""), ("title", title), ("csrf", token)], 400, ""),
            ([("title", title), ("csrf", ""), ("csrf", token)], 403, title),
            ([("title", title), ("csrf", "非法"), ("csrf", token)], 403, title),
        )
        for submitted, expected_status, expected_title in cases:
            with self.subTest(status=expected_status, empty_first=not expected_title):
                encoded = urlencode(submitted).encode("ascii")
                encoded = encoded.replace(b"title=", b"%74%69%74%6C%65=", 1)
                encoded = encoded.replace(b"csrf=", b"%63%73%72%66=", 1)
                self.assertLessEqual(len(encoded), 8192)
                before = self.rows()
                status, _, page = self.call_raw_response("POST", self.edit_path(item_id), encoded)
                self.assertEqual(status, expected_status)
                if status == 303:
                    self.assertEqual(self.rows(), [(item_id, expected_title, 0)])
                else:
                    self.edit_form(page, item_id, expected_title)
                    self.assert_safe_markup(page)
                    self.assertEqual(self.rows(), before)

    def test_edit_json_success_validation_and_missing_item(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        item_id = self.create("JSON编辑前")
        self.create("其他事项保持不变")
        token = self.csrf()
        title = '  JSON原文 " & <script>alert(1)</script>  '
        before = self.rows()
        status, result = self.call_json(self.edit_path(item_id), {"csrf": token, "title": title})
        self.assertEqual(status, 200)
        self.assertEqual(result, {"redirect": self.prefix + "/"})
        expected = [(i, title if i == item_id else text, done) for i, text, done in before]
        self.assertEqual(self.rows(), expected)
        for target, invalid_title, expected_status in ((item_id, "", 400),
                                                       (item_id, " \t\n", 400),
                                                       (item_id, "字" * 201, 400),
                                                       (item_id, "字" * 1000, 400),
                                                       (item_id + 1000, "未找到", 404)):
            with self.subTest(target=target, status=expected_status):
                status, result = self.call_json(self.edit_path(target),
                                                {"csrf": token, "title": invalid_title})
                self.assertEqual(status, expected_status)
                self.assertEqual(set(result), {"error", "csrf"})
                self.assertTrue(result["error"])
                self.assertEqual(result["csrf"], token)
                self.assertEqual(self.rows(), expected)

    def test_edit_json_csrf_error_supplies_current_token_for_retry(self):
        item_id = self.create("重启前标题")
        self.create("不得误改其他事项")
        old_token = self.csrf()
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                   {"csrf": old_token, "done": "1"})[0], 303)
        self.stop()
        self.start()
        current_token = self.csrf()
        self.assertNotEqual(current_token, old_token)
        for rejected_token in (None, "非法令牌", old_token):
            with self.subTest(token=rejected_token):
                before = self.rows()
                submitted = {"title": "用户仍持有的输入"}
                if rejected_token is not None:
                    submitted["csrf"] = rejected_token
                status, result = self.call_json(self.edit_path(item_id), submitted)
                self.assertEqual(status, 403)
                self.assertEqual(set(result), {"error", "csrf"})
                self.assertTrue(result["error"])
                self.assertEqual(result["csrf"], current_token)
                self.assertEqual(self.rows(), before)
                submitted["csrf"] = result["csrf"]
                status, result = self.call_json(self.edit_path(item_id), submitted)
                self.assertEqual(status, 200)
                self.assertEqual(result, {"redirect": self.prefix + "/"})
                self.assertEqual(self.rows(), [(i, submitted["title"] if i == item_id else text, done)
                                               for i, text, done in before])

    def test_edit_json_database_failure_retries_original_item_after_recovery(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        item_id = self.create("故障前标题")
        self.create("其他事项不变")
        token = self.csrf()
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                   {"csrf": token, "done": "1"})[0], 303)
        before = self.rows()
        title = '\n浏览器保留的输入 " & </textarea><script>alert(1)</script>\r\n'
        submitted = {"csrf": token, "title": title}
        with self.unavailable_database():
            status, result = self.call_json(self.edit_path(item_id), submitted)
            self.assertEqual(status, 503)
            self.assertEqual(set(result), {"error", "csrf"})
            self.assertTrue(result["error"])
            self.assertEqual(result["csrf"], token)
        self.assertEqual(self.rows(), before)
        submitted["csrf"] = result["csrf"]
        status, result = self.call_json(self.edit_path(item_id), submitted)
        self.assertEqual(status, 200)
        self.assertEqual(result, {"redirect": self.prefix + "/"})
        self.assertEqual(self.rows(), [(i, title if i == item_id else text, done)
                                       for i, text, done in before])
        page = self.call("GET", self.edit_path(item_id))[1]
        self.edit_form(page, item_id, title)
        self.assert_safe_markup(page)

    def test_native_edit_target_keeps_parent_available_for_72055_byte_retry(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        item_id = self.create("原生编辑前标题")
        self.create("其他事项不得改变")
        token = self.csrf()
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                   {"csrf": token, "done": "1"})[0], 303)
        before = self.rows()
        status, parent_page = self.call("GET", self.edit_path(item_id))
        self.assertEqual(status, 200)
        action, parent_fields = self.edit_form(parent_page, item_id, "原生编辑前标题")
        parsed_parent = Page(parent_page)
        self.assertEqual(parsed_parent.forms[0]["target"], "edit-result")
        self.assert_native_result_frame(parsed_parent)
        self.assert_safe_markup(parent_page)
        parent_fields["title"] = "字" * 8000
        self.assertEqual(len(parent_fields["csrf"]), 43)
        encoded = urlencode(parent_fields).encode("ascii")
        self.assertEqual(len(encoded), 72055)
        responses = (
            self.call_raw_response("POST", action, encoded),
            self.call_declared_body(action, len(encoded)),
        )
        for status, headers, page in responses:
            self.assertEqual(status, 413)
            self.assertEqual(headers.get("Connection", "").lower(), "close")
            parsed = Page(page)
            self.assertIn("上方", "".join(parsed.text))
            self.assertIn("编辑框", "".join(parsed.text))
            self.assertNotIn(self.edit_path(item_id), parsed.links)
            self.assertNotIn(action, parsed.links)
            self.assertEqual(parsed.frames, [])
            self.assertEqual(parsed.scripts, [])
            self.assertEqual(self.rows(), before)
        # HTTP verifies targeting and persistence; an actual no-JS browser must
        # separately verify that this original DOM still contains all 8000 chars.
        parent_fields["title"] = "原生编辑修正后标题"
        with self.unavailable_database():
            status, page = self.call("POST", action, parent_fields)
            self.assertEqual(status, 503)
            self.edit_form(page, item_id, parent_fields["title"])
            self.assertEqual(Page(page).forms[0]["target"], "_self")
        self.assertEqual(self.rows(), before)
        self.assert_inline_saved(self.call_response("POST", action, parent_fields))
        self.assertEqual(self.rows(), [(i, parent_fields["title"] if i == item_id else text, done)
                                       for i, text, done in before])

    def test_native_inline_csrf_retry_uses_new_token_without_nested_frame(self):
        item_id = self.create("令牌过期前标题")
        self.create("保留其他事项")
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                   {"csrf": self.csrf(), "done": "1"})[0], 303)
        before = self.rows()
        action, parent_fields = self.edit_form(self.call("GET", self.edit_path(item_id))[1],
                                               item_id, "令牌过期前标题")
        original_token = parent_fields["csrf"]
        title = '原生重试 " & </textarea><script>alert(1)</script>'
        parent_fields["title"] = title
        self.stop()
        self.start()
        status, page = self.call("POST", action, parent_fields)
        self.assertEqual(status, 403)
        retry_action, retry_fields = self.edit_form(page, item_id, title)
        self.assertEqual(retry_action, action)
        parsed = Page(page)
        self.assertEqual(parsed.forms[0]["target"], "_self")
        self.assertEqual(parsed.frames, [])
        self.assertEqual(parsed.scripts, [])
        self.assertIn("上方", "".join(parsed.text))
        self.assertIn("重试本次", "".join(parsed.text))
        self.assertNotEqual(retry_fields["csrf"], original_token)
        self.assertEqual(retry_fields["csrf"], self.csrf())
        self.assert_safe_markup(page)
        self.assertEqual(self.rows(), before)
        status, missing_page = self.call("POST", self.edit_path(item_id + 1000) + "?result=1",
                                         retry_fields)
        self.assertEqual(status, 404)
        self.assert_retained_input(missing_page, title)
        parsed_missing = Page(missing_page)
        self.assertEqual(parsed_missing.frames, [])
        self.assertEqual(parsed_missing.scripts, [])
        missing_titles = [control for control in parsed_missing.controls if control.get("name") == "title"]
        self.assertEqual(len(missing_titles), 1)
        self.assertIn("readonly", missing_titles[0])
        self.assertEqual(self.rows(), before)
        self.assert_inline_saved(self.call_response("POST", retry_action, retry_fields))
        self.assertEqual(self.rows(), [(i, title if i == item_id else text, done)
                                       for i, text, done in before])


if __name__ == "__main__":
    unittest.main()
