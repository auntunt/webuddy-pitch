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


    def test_edit_rejects_invalid_percent_encoded_utf8_without_changing_records(self):
        item_id = self.create("百分号解码前的完整原文")
        self.create("另一条事项保持原样")
        before = self.rows()
        csrf = self.csrf().encode("ascii")
        for encoded_title in (b"%FF", b"%E4%B8"):
            for padding in (0, 9000):
                with self.subTest(title=encoded_title, padding=padding):
                    body = b"title=" + encoded_title + b"&csrf=" + csrf + b"&padding=" + b"x" * padding
                    status, _, page = self.call_raw_response("POST", self.edit_path(item_id), body)
                    self.assertEqual(status, 400)
                    self.assertIn("表单格式错误", page)
                    self.assertEqual(self.rows(), before)


    def test_edit_crlf_logical_length_boundaries(self):
        item_id = self.create("换行边界前标题")
        self.create("其他事项保持原样")
        accepted = "事" * 100 + "\r\n" + "项" * 99
        cases = (
            ("native_200", accepted, 303),
            ("native_201", accepted + "项", 400),
            ("lf_200", "事" * 100 + "\n" + "项" * 99, 303),
            ("cr_200", "事" * 100 + "\r" + "项" * 99, 303),
            ("two_crlf_200", "事" * 99 + "\r\n" + "项" * 99 + "\r\n", 303),
            ("separate_cr_and_crlf_201", "事" * 199 + "\r\r\n", 400),
            # Keep Python's existing code-point semantics beyond the CRLF fix.
            ("supplementary_200", "🙂" * 200, 303),
            ("supplementary_201", "🙂" * 201, 400),
            ("combining_200", "e\u0301" * 100, 303),
            ("combining_201", "e\u0301" * 100 + "e", 400),
        )
        for label, title, expected_status in cases:
            with self.subTest(case=label):
                before = self.rows()
                body = urlencode({"csrf": self.csrf(), "title": title}).encode("ascii")
                if label.startswith("native_"):
                    # These are the bytes a native textarea form sends for its LF value.
                    self.assertIn(b"%0D%0A", body)
                    self.assertEqual(len(title), 201 if expected_status == 303 else 202)
                self.assertLessEqual(len(body), 8192)
                status, headers, page = self.call_raw_response("POST", self.edit_path(item_id), body)
                self.assertEqual(status, expected_status)
                if expected_status == 400:
                    self.assertIn("200", "".join(Page(page).text))
                    action, fields = self.edit_form(page, item_id, title)
                    self.assertEqual(self.rows(), before)
                    fields["title"] = accepted
                    status, headers, _ = self.call_response("POST", action, fields)
                    self.assertEqual(status, 303)
                    title = accepted
                self.assertEqual(headers.get("Location"), self.prefix + "/")
                self.assertEqual(self.rows(), [(i, title if i == item_id else text, done)
                                               for i, text, done in before])
                self.edit_form(self.call("GET", self.edit_path(item_id))[1], item_id, title)

    def test_edit_crlf_preserves_record_across_restart_and_prefixes(self):
        self.create("其他事项保持原样")
        title = "事" * 100 + "\r\n" + "项" * 99
        for prefix in ("", "/demo", "/pv/BOOTV2/session"):
            self.stop()
            self.start(prefix)
            for done in (0, 1):
                with self.subTest(prefix=prefix, done=done):
                    item_id = self.create("换行编辑前标题")
                    self.assertEqual(self.call("POST", prefix + "/items/%d" % item_id,
                                               {"csrf": self.csrf(), "done": str(done)})[0], 303)
                    before = self.rows()
                    path = self.edit_path(item_id)
                    self.assertIn(path, Page(self.call("GET", prefix + "/")[1]).links)
                    status, page = self.call("GET", path)
                    self.assertEqual(status, 200)
                    action, fields = self.edit_form(page, item_id, "换行编辑前标题")
                    fields["title"] = title
                    status, headers, _ = self.call_response("POST", action, fields)
                    self.assertEqual(status, 303)
                    self.assertEqual(headers.get("Location"), prefix + "/")
                    expected = [(i, title if i == item_id else text, state)
                                for i, text, state in before]
                    self.assertEqual(self.rows(), expected)
                    self.assertIn(title, self.call("GET", prefix + "/")[1])
                    self.stop()
                    self.start()
                    self.assertIn(title, self.call("GET", prefix + "/")[1])
                    self.edit_form(self.call("GET", path)[1], item_id, title)
                    self.assertEqual(self.rows(), expected)

    def test_edit_crlf_database_failure_retries_original_item(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        self.create("故障期间其他事项保持原样")
        accepted = "事" * 100 + "\r\n" + "项" * 99
        for done in (0, 1):
            item_id = self.create("换行故障前标题")
            token = self.csrf()
            self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                       {"csrf": token, "done": str(done)})[0], 303)
            for title in (accepted, accepted + "项"):
                with self.subTest(done=done, raw_length=len(title)):
                    before = self.rows()
                    with self.unavailable_database():
                        status, page = self.call("POST", self.edit_path(item_id),
                                                 {"csrf": token, "title": title})
                        self.assertEqual(status, 503)
                        action, fields = self.edit_form(page, item_id, title)
                    self.assertEqual(self.rows(), before)
                    status, headers, page = self.call_response("POST", action, fields)
                    if title != accepted:
                        self.assertEqual(status, 400)
                        action, fields = self.edit_form(page, item_id, title)
                        self.assertEqual(self.rows(), before)
                        fields["title"] = accepted
                        status, headers, _ = self.call_response("POST", action, fields)
                    self.assertEqual(status, 303)
                    self.assertEqual(headers.get("Location"), self.prefix + "/")
                    self.assertEqual(self.rows(), [(i, accepted if i == item_id else text, state)
                                                   for i, text, state in before])
                    self.edit_form(self.call("GET", self.edit_path(item_id))[1], item_id, accepted)


    def filter_url(self, path, q="", status="all"):
        query = []
        if q:
            query.append(("q", q))
        if status in ("pending", "completed"):
            query.append(("status", status))
        return path + ("?" + urlencode(query) if query else "")

    def filtered_item_ids(self, markup):
        pattern = re.escape(self.prefix) + r"/items/([0-9]+)(?:\?.*)?"
        matches = [re.fullmatch(pattern, form["action"] or "")
                   for form in Page(markup).forms if form["method"] == "post"]
        return [int(match[1]) for match in matches if match]

    def assert_filter_controls(self, markup, q="", status="all"):
        parsed = Page(markup)
        forms = [form for form in parsed.forms if form["method"] == "get"]
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0]["action"], self.prefix + "/")
        get_markup = [fragment for fragment in re.findall(r"<form\b[^>]*>.*?</form>", markup, re.S)
                      if Page(fragment).forms[0]["method"] == "get"]
        self.assertEqual(len(get_markup), 1)
        self.assertTrue(any((tag == "button" and attrs.get("type", "submit") == "submit")
                            or (tag == "input" and attrs.get("type") == "submit")
                            for tag, attrs in Page(get_markup[0]).elements))
        keywords = [control for control in forms[0]["controls"]
                    if control.get("name") == "q"]
        self.assertEqual(len(keywords), 1)
        self.assertEqual(keywords[0]["value"], q)
        self.assertIn(keywords[0].get("id"), parsed.labels)
        selects = [attrs for tag, attrs in parsed.elements
                   if tag == "select" and attrs.get("name") == "status"]
        self.assertEqual(len(selects), 1)
        self.assertIn(selects[0].get("id"), parsed.labels)
        options = [attrs for tag, attrs in parsed.elements if tag == "option"]
        self.assertEqual({attrs.get("value") for attrs in options},
                         {"all", "pending", "completed"})
        selected = [attrs["value"] for attrs in options if "selected" in attrs]
        self.assertEqual(selected or [options[0]["value"]], [status])
        self.assertIn(self.prefix + "/", parsed.links)
        self.assertIn("清除筛选", "".join(parsed.text))
        self.assert_safe_markup(markup)
        return parsed

    def filtered_post_form(self, markup, action, title=None):
        parsed = Page(markup)
        forms = [form for form in parsed.forms if form["action"] == action]
        self.assertEqual(len(forms), 1, markup)
        form = forms[0]
        self.assertEqual(form["method"], "post")
        fields = {control["name"]: control["value"] for control in form["controls"]
                  if "name" in control and "disabled" not in control}
        self.assertTrue(fields.get("csrf"))
        if title is not None:
            self.assertEqual(fields.get("title"), title)
            controls = [control for control in form["controls"]
                        if control.get("name") == "title"]
            self.assertEqual(len(controls), 1)
            self.assertIn(controls[0].get("id"), parsed.labels)
        self.assert_safe_markup(markup)
        return fields

    def test_filter_form_and_distinct_empty_states(self):
        status, markup = self.call("GET", self.prefix + "/")
        self.assertEqual(status, 200)
        self.assert_filter_controls(markup)
        self.assertEqual(self.filtered_item_ids(markup), [])
        self.assertIn("还没有内容，添加第一项开始。", "".join(Page(markup).text))
        for q, state in (("没有匹配", "all"), ("", "pending"), ("", "completed")):
            with self.subTest(q=q, state=state):
                status, markup = self.call("GET", self.filter_url(self.prefix + "/", q, state))
                self.assertEqual(status, 200)
                self.assert_filter_controls(markup, q, state)
                self.assertEqual(self.filtered_item_ids(markup), [])
                self.assertIn("没有符合条件的事项", "".join(Page(markup).text))
                self.assertNotIn("还没有内容，添加第一项开始。", "".join(Page(markup).text))
        self.assertEqual(self.rows(), [])

    def test_filter_keyword_is_literal_unicode_casefold_without_truncation(self):
        first = self.create("Alpha 发布")
        second = self.create("BETA alpha 回归")
        street = self.create("Straße 验证")
        symbols = self.create("字面量 %_ ' \" \\ + & ? # <script> 示例")
        unrelated = self.create("完全不同的事项")
        before = self.rows()
        cases = (
            ("", [unrelated, symbols, street, second, first]),
            ("ALPHA", [second, first]), ("发布", [first]),
            ("STRASSE", [street]), ("ß", [street]),
            ("%", [symbols]), ("_", [symbols]), ("%_", [symbols]),
            ("'", [symbols]), ('"', [symbols]), ("\\", [symbols]),
            ("+ & ? #", [symbols]), ("<script>", [symbols]),
            ("  Alpha  ", []), ("' OR 1=1 --", []),
            ('\" onfocus=\"alert(1)\"><script>alert(1)</script>', []),
            ("字" * 300, []),
        )
        for q, expected in cases:
            with self.subTest(q=q):
                status, markup = self.call("GET", self.filter_url(self.prefix + "/", q))
                self.assertEqual(status, 200)
                self.assert_filter_controls(markup, q)
                self.assertEqual(self.filtered_item_ids(markup), expected)
                self.assertEqual(self.rows(), before)

    def test_filter_status_and_keyword_intersection_preserve_descending_ids(self):
        alpha_pending = self.create("Alpha 待处理")
        beta_completed = self.create("Beta 已完成")
        alpha_completed = self.create("ALPHA 已完成")
        beta_pending = self.create("Beta 待处理")
        token = self.csrf()
        for item_id in (beta_completed, alpha_completed):
            self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
                                       {"csrf": token, "done": "1"})[0], 303)
        before = self.rows()
        cases = (
            ("", "all", [beta_pending, alpha_completed, beta_completed, alpha_pending]),
            ("", "pending", [beta_pending, alpha_pending]),
            ("", "completed", [alpha_completed, beta_completed]),
            ("alpha", "all", [alpha_completed, alpha_pending]),
            ("alpha", "pending", [alpha_pending]),
            ("alpha", "completed", [alpha_completed]),
            ("已完成", "pending", []),
        )
        for q, state, expected in cases:
            with self.subTest(q=q, state=state):
                status, markup = self.call("GET", self.filter_url(self.prefix + "/", q, state))
                self.assertEqual(status, 200)
                parsed = self.assert_filter_controls(markup, q, state)
                self.assertEqual(self.filtered_item_ids(markup), expected)
                for item_id in expected:
                    self.assertIn(self.filter_url(self.edit_path(item_id), q, state), parsed.links)
                self.assertEqual(self.rows(), before)

    def test_filter_unknown_and_duplicate_values_generate_canonical_urls(self):
        first = self.create("Alpha")
        second = self.create("Beta")
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % second,
                                   {"csrf": self.csrf(), "done": "1"})[0], 303)
        before = self.rows()
        cases = (
            ([], "", "all", [second, first]),
            ([("q", ""), ("status", "all")], "", "all", [second, first]),
            ([("status", "unknown")], "", "all", [second, first]),
            ([("status", "COMPLETED")], "", "all", [second, first]),
            ([("q", "Alpha"), ("status", "unknown")], "Alpha", "all", [first]),
            ([("q", "Alpha"), ("q", "Beta"), ("status", "pending"),
              ("status", "completed")], "Alpha", "pending", [first]),
            ([("q", ""), ("q", "Alpha"), ("status", ""),
              ("status", "completed")], "", "all", [second, first]),
        )
        for pairs, q, state, expected in cases:
            with self.subTest(pairs=pairs):
                query = urlencode(pairs).replace("q=", "%71=", 1).replace("status=", "%73tatus=", 1)
                status, markup = self.call("GET", self.prefix + "/" + ("?" + query if query else ""))
                self.assertEqual(status, 200)
                parsed = self.assert_filter_controls(markup, q, state)
                self.assertEqual(self.filtered_item_ids(markup), expected)
                for form in parsed.forms:
                    if form["method"] == "post":
                        self.assertEqual(form["action"],
                                         self.filter_url(form["action"].split("?")[0], q, state))
                for item_id in expected:
                    self.assertIn(self.filter_url(self.edit_path(item_id), q, state), parsed.links)
                self.assertEqual(self.rows(), before)

    def test_filter_refresh_clear_and_restart_leave_sqlite_unchanged(self):
        first = self.create("刷新保留 Alpha")
        second = self.create("刷新保留 Beta")
        self.assertEqual(self.call("POST", self.prefix + "/items/%d" % second,
                                   {"csrf": self.csrf(), "done": "1"})[0], 303)
        before = self.rows()
        database_bytes = self.db.read_bytes()
        path = self.filter_url(self.prefix + "/", "ALPHA", "pending")
        for _ in range(3):
            status, markup = self.call("GET", path)
            self.assertEqual(status, 200)
            self.assert_filter_controls(markup, "ALPHA", "pending")
            self.assertEqual(self.filtered_item_ids(markup), [first])
            self.assertEqual(self.call("GET", self.filter_url(self.edit_path(first), "ALPHA", "pending"))[0], 200)
            self.assertEqual(self.rows(), before)
            self.assertEqual(self.db.read_bytes(), database_bytes)
        self.stop()
        self.start()
        self.assertEqual(self.filtered_item_ids(self.call("GET", path)[1]), [first])
        status, markup = self.call("GET", self.prefix + "/")
        self.assertEqual(status, 200)
        self.assert_filter_controls(markup)
        self.assertEqual(self.filtered_item_ids(markup), [second, first])
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.db.read_bytes(), database_bytes)

    def test_filter_create_toggle_edit_and_cancel_keep_context_for_all_prefixes(self):
        for index, prefix in enumerate(("", "/demo", "/pv/BOOTV2/session")):
            with self.subTest(prefix=prefix):
                self.stop()
                self.start(prefix)
                q = "筛选%d & + %%_" % index
                title = q + " 原文"
                item_id = self.create(title)
                pending = self.filter_url(prefix + "/", q, "pending")
                completed = self.filter_url(prefix + "/", q, "completed")
                edit = self.filter_url(self.edit_path(item_id), q, "pending")
                status, markup = self.call("GET", pending)
                self.assertEqual(status, 200)
                self.assertEqual(self.filtered_item_ids(markup), [item_id])
                self.assertIn(edit, Page(markup).links)
                status, markup = self.call("GET", edit)
                self.assertEqual(status, 200)
                fields = self.filtered_post_form(markup, edit, title)
                self.assertIn(pending, Page(markup).links)
                self.assertIn("取消", "".join(Page(markup).text))
                before = self.rows()
                self.assertEqual(self.call("GET", pending)[0], 200)
                self.assertEqual(self.rows(), before)
                fields["title"] = q + " 修改后"
                status, headers, _ = self.call_response("POST", edit, fields)
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), pending)
                self.assertEqual(self.rows(), [(i, fields["title"] if i == item_id else text, state)
                                               for i, text, state in before])
                markup = self.call("GET", pending)[1]
                toggle = self.filter_url(prefix + "/items/%d" % item_id, q, "pending")
                fields = self.filtered_post_form(markup, toggle)
                fields["done"] = "1"
                status, headers, _ = self.call_response("POST", toggle, fields)
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), pending)
                self.assertEqual(self.filtered_item_ids(self.call("GET", pending)[1]), [])
                markup = self.call("GET", completed)[1]
                self.assertEqual(self.filtered_item_ids(markup), [item_id])
                create = self.filter_url(prefix + "/items", q, "completed")
                fields = self.filtered_post_form(markup, create, "")
                fields["title"] = q + " 新增"
                status, headers, _ = self.call_response("POST", create, fields)
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), completed)
                new_id = self.rows()[-1][0]
                self.assertNotEqual(new_id, item_id)
                self.assertEqual(self.rows()[-1], (new_id, fields["title"], 0))
                self.assertEqual(self.filtered_item_ids(self.call("GET", completed)[1]), [item_id])
                self.assertEqual(self.filtered_item_ids(self.call("GET", pending)[1]), [new_id])
                toggle = self.filter_url(prefix + "/items/%d" % item_id, q, "completed")
                fields = self.filtered_post_form(self.call("GET", completed)[1], toggle)
                fields["done"] = "0"
                status, headers, _ = self.call_response("POST", toggle, fields)
                self.assertEqual(status, 303)
                self.assertEqual(headers.get("Location"), completed)
                self.assertEqual(self.filtered_item_ids(self.call("GET", completed)[1]), [])
                self.assertEqual(self.filtered_item_ids(self.call("GET", pending)[1]), [new_id, item_id])

    def test_filter_edit_validation_csrf_and_missing_item_preserve_context(self):
        item_id = self.create("不能意外修改")
        self.create("保留另一条")
        before = self.rows()
        q = '\" & %_ + \\ <script>alert(1)</script>'
        home = self.filter_url(self.prefix + "/", q, "completed")
        edit = self.filter_url(self.edit_path(item_id), q, "completed")
        cases = ((None, "未经验证", 403), ("非法令牌", "未经验证", 403),
                 (self.csrf(), "", 400), (self.csrf(), " \t\r\n ", 400),
                 (self.csrf(), "字" * 201, 400))
        for token, title, expected in cases:
            with self.subTest(status=expected, title=repr(title)):
                submitted = {"title": title}
                if token is not None:
                    submitted["csrf"] = token
                status, markup = self.call("POST", edit, submitted)
                self.assertEqual(status, expected)
                self.filtered_post_form(markup, edit, title)
                self.assertIn(home, Page(markup).links)
                self.assertEqual(self.rows(), before)
        missing = self.filter_url(self.edit_path(item_id + 1000), q, "completed")
        for method, data in (("GET", None), ("POST", {"csrf": self.csrf(), "title": "未保存原文"})):
            with self.subTest(method=method):
                status, markup = self.call(method, missing, data)
                self.assertEqual(status, 404)
                self.assertIn(home, Page(markup).links)
                self.assertFalse(Page(markup).forms)
                self.assert_safe_markup(markup)
                self.assertEqual(self.rows(), before)
        # A filter never grants permission to create or toggle without a valid CSRF token.
        for action, fields in ((self.prefix + "/items", {"title": "未授权新增"}),
                               (self.prefix + "/items/%d" % item_id, {"done": "1"})):
            self.assertEqual(self.call("POST", self.filter_url(action, q, "completed"), fields)[0], 403)
            self.assertEqual(self.rows(), before)

    def test_filter_database_failures_retain_create_edit_and_return_links(self):
        self.stop()
        self.start("/pv/BOOTV2/session")
        item_id = self.create("故障前事项")
        self.create("不应改变的事项")
        before = self.rows()
        token = self.csrf()
        q = "故障 & %_"
        home = self.filter_url(self.prefix + "/", q, "pending")
        edit = self.filter_url(self.edit_path(item_id), q, "pending")
        create = self.filter_url(self.prefix + "/items", q, "pending")
        edited = '\n故障 & %_ 编辑 "原文"\r\n'
        created = "故障 & %_ 新增"
        with self.unavailable_database():
            for path in (home, edit):
                status, markup = self.call("GET", path)
                self.assertEqual(status, 503)
                self.assertIn(home, Page(markup).links)
            status, markup = self.call("POST", edit, {"csrf": token, "title": edited})
            self.assertEqual(status, 503)
            edit_fields = self.filtered_post_form(markup, edit, edited)
            self.assertIn(home, Page(markup).links)
            status, markup = self.call("POST", create, {"csrf": token, "title": created})
            self.assertEqual(status, 503)
            create_fields = self.filtered_post_form(markup, create, created)
            self.assertIn(home, Page(markup).links)
            status, markup = self.call("POST", self.filter_url(self.prefix + "/items/%d" % item_id, q, "pending"),
                                      {"csrf": token, "done": "1"})
            self.assertEqual(status, 503)
            self.assertIn(home, Page(markup).links)
        self.assertEqual(self.rows(), before)
        for action, fields in ((edit, edit_fields), (create, create_fields)):
            status, headers, _ = self.call_response("POST", action, fields)
            self.assertEqual(status, 303)
            self.assertEqual(headers.get("Location"), home)
        new_id = self.rows()[-1][0]
        self.assertEqual(self.rows(), [(i, edited if i == item_id else text, state)
                                       for i, text, state in before] + [(new_id, created, 0)])
        self.assertEqual(self.filtered_item_ids(self.call("GET", home)[1]), [new_id, item_id])

    def test_filter_edit_recovery_limits_and_retry_keep_full_context(self):
        item_id = self.create("原文保持不变")
        self.create("另一条仍保留")
        before = self.rows()
        token = self.csrf()
        q = "空格 & %_ + \\"
        home = self.filter_url(self.prefix + "/", q, "pending")
        edit = self.filter_url(self.edit_path(item_id), q, "pending")
        title = "字" * 1000 + '\n" & </textarea><script>alert(1)</script>\r\n'
        self.assertGreater(len(urlencode({"csrf": token, "title": title}).encode("ascii")), 8192)
        status, markup = self.call("POST", edit, {"csrf": token, "title": title})
        self.assertEqual(status, 413)
        fields = self.filtered_post_form(markup, edit, title)
        self.assertIn(home, Page(markup).links)
        self.assertEqual(self.rows(), before)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=2)
        try:
            connection.putrequest("POST", edit)
            connection.putheader("Content-Length", "65537")
            connection.endheaders()
            response = connection.getresponse()
            markup = response.read().decode("utf-8")
            self.assertEqual(response.status, 413)
            self.assertEqual(response.getheader("Connection"), "close")
            self.assertIn(edit, Page(markup).links)
            self.assertFalse(Page(markup).forms)
        finally:
            connection.close()
        self.assertEqual(self.rows(), before)
        fields["title"] = "事" * 100 + "\r\n" + "项" * 99
        status, headers, _ = self.call_response("POST", edit, fields)
        self.assertEqual(status, 303)
        self.assertEqual(headers.get("Location"), home)
        self.assertEqual(self.rows(), [(i, fields["title"] if i == item_id else text, state)
                                       for i, text, state in before])
        self.filtered_post_form(self.call("GET", edit)[1], edit, fields["title"])


if __name__ == "__main__":
    unittest.main()
