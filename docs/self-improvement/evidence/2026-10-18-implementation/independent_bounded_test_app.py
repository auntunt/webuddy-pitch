import http.client
import json
import re
import sqlite3
import socket
import tempfile
import threading
import unittest
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from app import make_server


class Page(HTMLParser):
    """Read the controls a browser receives, including decoded attribute values."""

    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.forms = []
        self.controls = []
        self.links = []
        self.labels = []
        self.elements = []
        self.text = []
        self.form = None
        self.textarea = None
        self.textarea_first_data = False
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == "form":
            self.form = {"action": attrs.get("action"),
                         "method": attrs.get("method", "get").lower(), "controls": []}
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
        elif tag == "label":
            self.labels.append(attrs.get("for"))

    def handle_endtag(self, tag):
        if tag == "form":
            self.form = None
        elif tag == "textarea":
            self.textarea = None

    def handle_data(self, data):
        self.text.append(data)
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

    def call_response(self, method, path, data=None):
        body = urlencode(data).encode("ascii") if data is not None else None
        return self.call_raw_response(method, path, body)

    def call_raw_response(self, method, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            conn.request(method, path, body,
                         {"Content-Type": "application/x-www-form-urlencoded"})
            r = conn.getresponse()
            headers = dict(r.getheaders())
            response = r.read()
            self.assertEqual(int(headers["Content-Length"]), len(response))
            return r.status, headers, response.decode("utf-8")
        finally:
            conn.close()

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
        return self.rows()[-1][0]

    def edit_path(self, item_id):
        return self.prefix + "/items/%d/edit" % item_id

    def edit_form(self, page, item_id, title):
        parsed = Page(page)
        forms = [form for form in parsed.forms
                 if form["action"] == self.edit_path(item_id)]
        self.assertEqual(len(forms), 1, page)
        form = forms[0]
        self.assertEqual(form["method"], "post")
        fields = {control["name"]: control["value"] for control in form["controls"]
                  if "name" in control and "disabled" not in control}
        self.assertEqual(fields.get("title"), title)
        self.assertTrue(fields.get("csrf"))
        title_controls = [control for control in form["controls"]
                          if control.get("name") == "title"]
        self.assertEqual(len(title_controls), 1)
        self.assertIn(title_controls[0].get("id"), parsed.labels)
        self.assertIn(self.prefix + "/", parsed.links)
        return form["action"], fields

    def assert_safe_markup(self, page):
        for tag, attrs in Page(page).elements:
            self.assertNotEqual(tag, "script", page)
            self.assertFalse(any(name.lower().startswith("on") for name in attrs), page)

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
                status, headers, _ = self.call_response("POST", action, fields)
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), self.prefix + "/")
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
                self.assertEqual(self.call("POST", action, fields)[0], 303)
                self.assertEqual(self.rows(), [(i, fields["title"] if i == item_id else text, done)
                                               for i, text, done in before])

    def test_edit_accepts_boundary_lengths_and_preserves_original_text(self):
        item_id = self.create("原始标题")
        for title in ("字", "字" * 200, "  留下首尾空白  ", "\n换行\r\n标题\n"):
            with self.subTest(title=repr(title[:30])):
                status, _, _ = self.call_response("POST", self.edit_path(item_id),
                                                 {"csrf": self.csrf(), "title": title})
                self.assertEqual(status, 303)
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
        status, headers, _ = self.call_response("POST", action, fields)
        self.assertEqual(status, 303)
        self.assertEqual(headers.get("Location"), self.prefix + "/")
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
                status, headers, _ = self.call_response("POST", action, fields)
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), prefix + "/")
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
                status, headers, _ = self.call_response("POST", action, fields)
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), prefix + "/")
                self.assertEqual(self.rows(), other_rows + [(item_id, title, 0)])

    def test_oversized_edit_keeps_complete_input_and_retries_original_item(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        other_id = self.create("保持另一条事项")
        item_id = self.create("保留原始标题")
        token = self.csrf()
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                   {"csrf": token, "done": "1"})[0], 303)
        suffix = '\n"\' & % + </textarea><script>alert("长文本")</script>🙂\r\n'
        # Exercise encoded text crossing the save limit without losing any input.
        cases = [("exact_1000", "字" * 1000)]
        cases.extend(("offset_" + str(len(offset)), offset + "字" * 1000 + suffix)
                     for offset in ("", "a", "ab"))
        for label, title in cases:
            with self.subTest(case=label):
                submitted = [("title", title), ("csrf", token)]
                encoded = urlencode(submitted).encode("ascii")
                self.assertGreater(len(encoded), 8192)
                if label == "exact_1000":
                    self.assertEqual(len(token), 43)
                    self.assertEqual(len(title), 1000)
                    self.assertEqual(len(encoded), 9055)
                self.assertTrue(encoded.startswith(b"title="))
                self.assertGreater(encoded.index(b"&csrf="), 8192)
                before = self.rows()
                status, page = self.call("POST", self.edit_path(item_id), submitted)
                self.assertEqual(status, 413)
                action, fields = self.edit_form(page, item_id, title)
                self.assert_safe_markup(page)
                self.assertEqual(self.rows(), before)
                fields["title"] = "纠正后的标题 " + label
                status, headers, _ = self.call_response("POST", action, fields)
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), self.prefix + "/")
                self.assertEqual(self.rows(), [(other_id, "保持另一条事项", 0),
                                               (item_id, fields["title"], 1)])

    def test_oversized_body_cannot_save_valid_edit_or_create(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        item_id = self.create("原文保持不变")
        self.create("不应修改的事项")
        before = self.rows()
        token = self.csrf()
        title = "字" * 200
        submitted = [("title", title), ("padding", "x" * 9000), ("csrf", token)]
        self.assertEqual(len(title), 200)
        self.assertGreater(len(urlencode(submitted).encode("ascii")), 8192)
        status, page = self.call("POST", self.edit_path(item_id), submitted)
        self.assertEqual(status, 413)
        self.edit_form(page, item_id, title)
        self.assert_safe_markup(page)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.call("POST", self.prefix + "/items", submitted)[0], 413)
        self.assertEqual(self.rows(), before)

    def test_oversized_edit_checks_csrf_and_retains_full_input(self):
        item_id = self.create("未经授权不得修改")
        self.create("保留其他行")
        before = self.rows()
        title = "字" * 1000 + '\" onfocus=\"alert(1)\"></textarea><script>alert(1)</script>'
        for csrf in (None, "非法令牌"):
            with self.subTest(csrf=csrf):
                submitted = [("title", title)]
                if csrf is not None:
                    submitted.append(("csrf", csrf))
                self.assertGreater(len(urlencode(submitted).encode("ascii")), 8192)
                status, page = self.call("POST", self.edit_path(item_id), submitted)
                self.assertEqual(status, 403)
                self.assert_retained_input(page, title)
                self.assertEqual(self.rows(), before)

    def test_oversized_edit_missing_item_and_database_failure_keep_recovery(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        item_id = self.create("保存前标题")
        self.create("不能改变的其他事项")
        token = self.csrf()
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                   {"csrf": token, "done": "1"})[0], 303)
        before = self.rows()
        title = "\n" + "字" * 1000 + '\" & </textarea><script>alert(1)</script>\r\n'
        submitted = [("title", title), ("csrf", token)]
        self.assertGreater(len(urlencode(submitted).encode("ascii")), 8192)
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
        status, page = self.call("POST", action, fields)
        self.assertEqual(status, 413)
        action, fields = self.edit_form(page, item_id, title)
        self.assert_safe_markup(page)
        self.assertEqual(self.rows(), before)
        fields["title"] = "恢复后修正为可保存标题"
        status, headers, _ = self.call_response("POST", action, fields)
        self.assertEqual(status, 303)
        self.assertEqual(headers.get("Location"), self.prefix + "/")
        self.assertEqual(self.rows(), [(i, fields["title"] if i == item_id else text, done)
                                       for i, text, done in before])

    def test_oversized_edit_uses_first_values_and_decodes_field_names(self):
        item_id = self.create("不可变的原文")
        before = self.rows()
        token = self.csrf()
        title = "字" * 1000 + '\" & % + </textarea><script>alert(1)</script>'
        cases = (
            ([("title", title), ("title", "忽略后值"), ("csrf", token), ("csrf", "非法")], 413, title),
            ([("title", ""), ("title", title), ("csrf", token)], 413, ""),
            ([("title", title), ("csrf", ""), ("csrf", token)], 403, title),
            ([("title", title), ("csrf", "非法"), ("csrf", token)], 403, title),
        )
        for submitted, expected_status, expected_title in cases:
            with self.subTest(status=expected_status, empty_first=not expected_title):
                encoded = urlencode(submitted).encode("ascii")
                encoded = encoded.replace(b"title=", b"%74%69%74%6C%65=", 1)
                encoded = encoded.replace(b"csrf=", b"%63%73%72%66=", 1)
                self.assertGreater(len(encoded), 8192)
                status, _, page = self.call_raw_response("POST", self.edit_path(item_id), encoded)
                self.assertEqual(status, expected_status)
                self.edit_form(page, item_id, expected_title)
                self.assert_safe_markup(page)
                self.assertEqual(self.rows(), before)

    def test_edit_body_limit_preserves_exact_8192_byte_boundary(self):
        item_id = self.create("边界前标题")
        self.create("边界测试保留其他事项")
        token = self.csrf()
        for size in (8191, 8192, 8193):
            with self.subTest(body_bytes=size):
                title = str(size) + "界" * 196
                self.assertEqual(len(title), 200)
                submitted = [("title", title), ("csrf", token), ("padding", "")]
                base_size = len(urlencode(submitted).encode("ascii"))
                submitted[-1] = ("padding", "x" * (size - base_size))
                self.assertEqual(len(urlencode(submitted).encode("ascii")), size)
                before = self.rows()
                status, page = self.call("POST", self.edit_path(item_id), submitted)
                if size <= 8192:
                    self.assertEqual(status, 303)
                    self.assertEqual(self.rows(), [(i, title if i == item_id else text, done)
                                                   for i, text, done in before])
                else:
                    self.assertEqual(status, 413)
                    self.edit_form(page, item_id, title)
                    self.assertEqual(self.rows(), before)

    def test_edit_recovery_window_retains_complete_input_at_boundary(self):
        item_id = self.create("恢复边界不应修改原文")
        self.create("保留其他事项")
        before = self.rows()
        title = "字" * 1000 + '\n🙂" & % + </textarea><script>alert(1)</script>\r\n'
        for size in (65535, 65536):
            for csrf, expected in ((self.csrf(), 413), ("非法令牌", 403)):
                with self.subTest(size=size, status=expected):
                    submitted = [("title", title), ("csrf", csrf), ("padding", "")]
                    base = len(urlencode(submitted).encode("ascii"))
                    submitted[-1] = ("padding", "x" * (size - base))
                    encoded = urlencode(submitted).encode("ascii")
                    self.assertEqual(len(encoded), size)
                    status, _, page = self.call_raw_response("POST", self.edit_path(item_id), encoded)
                    self.assertEqual(status, expected)
                    self.edit_form(page, item_id, title)
                    self.assert_safe_markup(page)
                    self.assertEqual(self.rows(), before)

    def test_edit_above_recovery_window_rejects_headers_without_reading_body(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        item_id = self.create("未经接收不得修改")
        self.create("另一条仍在")
        before = self.rows()
        # No request body is sent. Waiting for body bytes would time out this test.
        for size in (65537, 2**40):
            for target in (item_id, item_id + 1000):
                with self.subTest(size=size, target=target):
                    connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=2)
                    try:
                        connection.putrequest("POST", self.edit_path(target))
                        connection.putheader("Content-Type", "application/x-www-form-urlencoded")
                        connection.putheader("Content-Length", str(size))
                        connection.endheaders()
                        response = connection.getresponse()
                        page = response.read().decode("utf-8")
                        self.assertEqual(response.status, 413)
                        self.assertEqual(response.getheader("Connection"), "close")
                        self.assertEqual(int(response.getheader("Content-Length")), len(page.encode("utf-8")))
                        self.assertIn("正文未接收", page)
                        self.assertIn("编辑未保存", page)
                        self.assertIn(self.edit_path(target), Page(page).links)
                        self.assertFalse(any(control.get("name") == "title" for control in Page(page).controls))
                        self.assert_safe_markup(page)
                    finally:
                        connection.close()
                    self.assertEqual(self.rows(), before)

    def test_edit_recovery_rejects_malformed_or_incomplete_body_without_write(self):
        item_id = self.create("错误正文不能修改")
        before = self.rows()
        invalid = b"title=" + b"x" * 9000 + b"\xff&csrf=invalid"
        status, _, _ = self.call_raw_response("POST", self.edit_path(item_id), invalid)
        self.assertEqual(status, 400)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=2)
        try:
            connection.putrequest("POST", self.edit_path(item_id))
            connection.putheader("Content-Type", "application/x-www-form-urlencoded")
            connection.putheader("Content-Length", "9000")
            connection.endheaders(b"title=incomplete&csrf=invalid")
            connection.sock.shutdown(socket.SHUT_WR)
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 400)
        finally:
            connection.close()
        self.assertEqual(self.rows(), before)


if __name__ == "__main__":
    unittest.main()
