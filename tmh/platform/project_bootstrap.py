"""Create an owned, runnable project with a real Git baseline and executable tests.

The starter is a development foundation, not a claim that the user's business requirements are implemented.
Only fixed, bundled code is executed here; request fields never become commands or filesystem paths.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
import threading
from pathlib import Path

from .. import config
from .errors import ApiError

_LOCK = threading.RLock()

APP = r'''"""Local web starter: persistent items, accessible forms and a health endpoint."""
import hmac
import html
import json
import re
import secrets
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SAVE_BODY_LIMIT = 8192
EDIT_RECOVERY_LIMIT = 64 * 1024


def make_server(address, database, prefix="", title="我的应用"):
    database = str(database)
    prefix = "/" + prefix.strip("/") if prefix.strip("/") else ""
    token = secrets.token_urlsafe(32)
    style = ('body{font:16px system-ui;color:#20242b;background:#f5f6f8;margin:0}main{max-width:720px;margin:64px auto;padding:24px}'
             'h1{font-size:36px;letter-spacing:-1px}p{color:#596270;line-height:1.7}form{display:flex;flex-wrap:wrap;gap:12px;align-items:center}'
             'input,textarea{font:inherit;padding:12px;border:1px solid #b8c0cc;border-radius:6px;flex:1;min-width:0;box-sizing:border-box}'
             'textarea{width:100%;max-width:100%;resize:vertical}.edit-form{display:block}.edit-form label,.edit-form textarea{display:block;margin-bottom:12px}'
             'button{font:inherit;background:#20242b;color:white;border:0;border-radius:6px;padding:12px;cursor:pointer}'
             'button:focus-visible,input:focus-visible,textarea:focus-visible,a:focus-visible{outline:3px solid #386bd6;outline-offset:3px}'
             'ul{padding:0;list-style:none}li{padding:16px 0;border-bottom:1px solid #d9dee5}li span{flex:1;min-width:0;overflow-wrap:anywhere}'
             'small{color:#697383}@media(max-width:600px){main{margin:16px auto}h1{font-size:28px}}')
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, kind="text/html; charset=utf-8", close=False):
            parts = (body,) if isinstance(body, str) else body
            body = b"".join(part.encode("utf-8") if isinstance(part, str) else part for part in parts)
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if close:
                self.close_connection = True
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def page(self, status, heading, content, close=False):
            parts = (content,) if isinstance(content, str) else content
            return self.send(status, ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                             '<title>' + html.escape(heading) + '</title><style>' + style + '</style><main><h1>' + html.escape(heading) + '</h1>', *parts, '</main></html>'), close=close)

        def edit_id(self, path):
            match = re.fullmatch(re.escape(prefix) + r'/items/([0-9]{1,19})/edit', path)
            if match and 0 < int(match[1]) <= 2**63 - 1:
                return int(match[1])

        def edit_page(self, item_id, raw_title, status=200, error=""):
            # The extra leading newline is consumed by HTML; preserve the user's first newline.
            value = html.escape(raw_title, quote=True).replace('\r', '&#13;')
            field = ('<label for="edit-title">事项标题</label><textarea id="edit-title" name="title" rows="2" maxlength="200" required' + (' readonly' if status == 404 else '') + (' aria-describedby="edit-error"' if error else '') + '>\n', value, '</textarea>')
            message = '<p id="edit-error" role="alert">' + html.escape(error) + '</p>' if error else ''
            back = '<a href="' + html.escape(prefix + '/', quote=True) + '">' + ('返回应用' if error else '取消') + '</a>'
            if status == 404:
                content = (message + '<div class="edit-form">', *field, back + '</div>')
            else:
                action = html.escape(prefix + '/items/%d/edit' % item_id, quote=True)
                content = (message + '<form class="edit-form" method="post" action="' + action + '"><input type="hidden" name="csrf" value="' + token + '">', *field, '<button>' + ('重试保存' if error else '保存') + '</button> ' + back + '</form>')
            return self.page(status, '编辑事项', content)

        def unavailable(self):
            if urlsplit(self.path).path == prefix + "/health":
                return self.send(503, '{"status":"unavailable"}', "application/json")
            retry = ""
            if self.pending_save is not None:
                operation, item_id, raw_title = self.pending_save
                if operation == 'edit':
                    return self.edit_page(item_id, raw_title, 503, '数据暂时不可用，请稍后重试；此次编辑尚未保存。')
                retry = '<form method="post" action="' + html.escape(prefix + '/items', quote=True) + '"><input type="hidden" name="csrf" value="' + token + '"><label for="retry-title">未保存的内容</label><input id="retry-title" name="title" maxlength="200" value="' + html.escape(raw_title, quote=True) + '"><button>重试保存</button></form>'
            return self.page(503, '数据暂时不可用', '<p>请稍后重试，当前操作未完成。</p>' + retry + '<p><a href="' + html.escape(prefix + '/', quote=True) + '">返回应用</a></p>')

        def do_GET(self):
            self.pending_save = None
            try:
                return self.get()
            except sqlite3.Error:
                return self.unavailable()

        def get(self):
            path = urlsplit(self.path).path
            if path == prefix + "/health":
                with sqlite3.connect(database) as db:
                    db.execute("SELECT id FROM items LIMIT 1").fetchall()
                return self.send(200, '{"status":"ok"}', "application/json")
            item_id = self.edit_id(path)
            if item_id is not None:
                with sqlite3.connect(database) as db:
                    row = db.execute('SELECT title FROM items WHERE id=?', (item_id,)).fetchone()
                if row is None:
                    return self.edit_page(item_id, '', 404, '事项不存在')
                return self.edit_page(item_id, row[0])
            if path != prefix + "/":
                return self.send(404, "页面不存在")
            with sqlite3.connect(database) as db:
                rows = db.execute("SELECT id,title,done FROM items ORDER BY id DESC").fetchall()
            esc = html.escape
            items = "".join('<li><form method="post" action="%s/items/%d"><input type="hidden" name="csrf" value="%s"><span>%s</span><button name="done" value="%d">%s</button><a href="%s/items/%d/edit">编辑</a></form></li>' %
                            (esc(prefix, quote=True), i, token, esc(text), 0 if done else 1, "重新打开" if done else "完成", esc(prefix, quote=True), i) for i, text, done in rows)
            self.send(200, '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                      '<title>' + esc(title) + '</title><style>' + style + '</style><main>'
                      '<small>WEB 应用起点</small><h1>' + esc(title) + '</h1><p>应用已经可以运行。先添加一项内容，刷新后仍会保留。具体业务能力将在交付流程中实现和验证。</p>'
                      '<form method="post" action="' + prefix + '/items"><input type="hidden" name="csrf" value="' + token + '"><label for="title">新事项</label><input id="title" name="title" required maxlength="200" placeholder="写下一件要做的事"><button>添加</button></form>'
                      '<ul>' + (items or '<li>还没有内容，添加第一项开始。</li>') + '</ul><p><small>仅用于本地开发；正式发布前需要按实际业务配置身份验证、数据保护和部署环境。</small></p></main></html>')

        def do_POST(self):
            self.pending_save = None
            try:
                return self.post()
            except sqlite3.Error:
                return self.unavailable()

        def post(self):
            path = urlsplit(self.path).path
            item_id = self.edit_id(path)
            try:
                n = int(self.headers.get("Content-Length", "0"))
                # The recovery window is finite and never grants permission to save.
                # Refuse larger bodies before reading any bytes or opening the database.
                if item_id is not None and n > EDIT_RECOVERY_LIMIT:
                    back = html.escape(prefix + '/items/%d/edit' % item_id, quote=True)
                    return self.page(413, '请求内容过大', '<p>本次请求超过 64 KiB，正文未接收，编辑未保存。请返回编辑页，将标题改为 1 到 200 字后重试。</p><a href="' + back + '">返回编辑页</a>', close=True)
                if n <= 0 or (n > SAVE_BODY_LIMIT and item_id is None):
                    return self.send(413, "表单内容过大或为空", close=True)
                body = self.rfile.read(n)
                if len(body) != n:
                    raise ValueError('incomplete form')
                values = parse_qs(body.decode("utf-8"), keep_blank_values=True, errors="strict")
            except (ValueError, UnicodeError):
                return self.send(400, "表单格式错误")
            raw_title = values.get("title", [""])[0]
            if not hmac.compare_digest(values.get("csrf", [""])[0].encode("utf-8"), token.encode("ascii")):
                if item_id is not None:
                    return self.edit_page(item_id, raw_title, 403, '页面已过期，请确认内容后重试')
                return self.send(403, "页面已过期，请刷新后重试")
            if item_id is not None:
                self.pending_save = ('edit', item_id, raw_title)
            elif path.startswith(prefix + '/items/') and path.endswith('/edit'):
                return self.send(404, '事项不存在')
            elif path == prefix + '/items':
                self.pending_save = ('create', None, raw_title)
            with sqlite3.connect(database) as db:
                if item_id is not None:
                    if db.execute('SELECT id FROM items WHERE id=?', (item_id,)).fetchone() is None:
                        return self.edit_page(item_id, raw_title, 404, '事项不存在')
                    if n > SAVE_BODY_LIMIT:
                        return self.edit_page(item_id, raw_title, 413, '表单内容超过 8192 字节，事项应为 1 到 200 字；请修改后重试。')
                    # Native textarea forms encode one line break as CRLF.
                    title_length = len(raw_title) - raw_title.count("\r\n")
                    if not raw_title.strip() or title_length > 200:
                        return self.edit_page(item_id, raw_title, 400, '事项应为 1 到 200 字，不能全为空白')
                    cur = db.execute('UPDATE items SET title=? WHERE id=?', (raw_title, item_id))
                    if not cur.rowcount:
                        return self.edit_page(item_id, raw_title, 404, '事项不存在')
                elif path == prefix + "/items":
                    text = values.get("title", [""])[0].strip()
                    if not text or len(text) > 200:
                        return self.send(400, "事项应为 1 到 200 字")
                    db.execute("INSERT INTO items(title) VALUES(?)", (text,))
                elif path.startswith(prefix + "/items/") and path.rsplit("/", 1)[1].isdigit():
                    done = values.get("done", [""])[0]
                    if done not in ("0", "1"):
                        return self.send(400, "状态不正确")
                    cur = db.execute("UPDATE items SET done=? WHERE id=?", (int(done), int(path.rsplit("/", 1)[1])))
                    if not cur.rowcount:
                        return self.send(404, "事项不存在")
                else:
                    return self.send(404, "页面不存在")
            self.send_response(303)
            self.send_header("Location", prefix + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

    return ThreadingHTTPServer(address, Handler)


if __name__ == "__main__":
    project = json.loads(Path("project.json").read_text(encoding="utf-8"))
    server = make_server(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8000),
                         sys.argv[3] if len(sys.argv) > 3 else "app.db",
                         sys.argv[2] if len(sys.argv) > 2 else "", project["name"])
    print("Ready on http://127.0.0.1:%d" % server.server_address[1], flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
'''

TESTS = r'''import http.client
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


if __name__ == "__main__":
    unittest.main()
'''


def create(P, body: dict, by: str) -> dict:
    if not isinstance(body, dict):
        raise ApiError(400, "项目内容必须是对象")
    key = str(body.get("key") or "").strip().upper()
    name = str(body.get("name") or "").strip()
    brief = str(body.get("brief") or "").strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,9}", key):
        raise ApiError(400, "项目代号需为字母开头的 1–10 位字母数字")
    if not name or len(name) > 120 or len(brief) > 20000:
        raise ApiError(400, "填写项目名称（最多 120 字），目标最多 20000 字")
    if body.get("template", "web") != "web":
        raise ApiError(400, "目前支持轻量 Web 应用起点，其他技术栈请接入已有仓库")
    # The path is wholly server-owned. Never accept a request-supplied shell command or destination.
    with _LOCK:
        parent = P.data_dir / "projects"
        if parent.is_symlink():
            raise ApiError(409, "项目目录不能是符号链接")
        root = parent / key
        if P.store.project(key) or root.exists() or root.is_symlink():
            raise ApiError(409, "项目代号或目录已存在，请选一个新代号；原内容没有被覆盖")
        root.mkdir(parents=True)
        (root / "tests").mkdir()
        (root / "app.py").write_text(APP, encoding="utf-8")
        (root / "tests" / "test_app.py").write_text(TESTS, encoding="utf-8")
        (root / "project.json").write_text(json.dumps({"name": name, "brief": brief}, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / ".gitignore").write_text("__pycache__/\n*.pyc\n*.db\n.env\n.venv/\n", encoding="utf-8")
        (root / "README.md").write_text("# %s\n\n%s\n\n## 运行\n\n`python3 app.py 8000`\n\n## 测试\n\n`python3 -m unittest discover -s tests -v`\n\n这是可运行的开发起点，具体业务目标仍需实现并验收。\n" % (name, brief), encoding="utf-8")
        cfg = config.load(root)
        py = shlex.quote(sys.executable)
        cfg["project"] = {"name": name, "description": brief}
        cfg["commands"].update(build=py + " -m py_compile app.py", test=py + " -m unittest discover -s tests -v")
        config.save(root, cfg)
        checks = {}
        try:
            for label, argv in (("build", [sys.executable, "-m", "py_compile", "app.py"]),
                                ("test", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])):
                r = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=30)
                checks[label] = {"exit_code": r.returncode, "output": r.stdout + r.stderr, "command": argv}
                if r.returncode:
                    raise RuntimeError("%s 检查失败" % label)
            for args in (("init", "-b", "main"), ("add", "."),
                         ("-c", "user.name=Webuddy", "-c", "user.email=webuddy@localhost", "commit", "-m", "Create runnable web foundation")):
                subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=15)
            commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.SubprocessError, RuntimeError) as e:
            (root / "bootstrap-diagnostic.json").write_text(json.dumps({"error": str(e), "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
            raise ApiError(500, "创建检查未完成，已保留目录和诊断：%s" % root) from e
        p = P.store.add_project(key, name, str(root), brief)
        from . import preview
        configured, warnings = False, []
        try:
            # Preview worktrees are replaceable; the app's data belongs to the stable owned project.
            preview.set_conf(P.data_dir, key, py + " app.py {port} {prefix} " + shlex.quote(str(root / "app.db")), "/health", by)
            configured = True
        except (OSError, ValueError, AttributeError) as e:
            warnings.append("项目已创建；预览配置失败，可在项目的预览设置中修复：%s" % e)
        receipt = {"project": p, "template": "web", "commit": commit, "checks": checks, "preview_configured": configured,
                   "warnings": warnings,
                   "note": "基础应用和测试已就绪；业务目标仍需按交付阶段实现，未部署生产。"}
        receipts = P.data_dir / "project-bootstrap"
        try:
            receipts.mkdir(exist_ok=True)
            (receipts / (key + ".json")).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            warnings.append("项目已创建；创建回执未能写入磁盘，请保留本次响应：%s" % e)
        return receipt
