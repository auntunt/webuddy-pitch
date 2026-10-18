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
import secrets
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def make_server(address, database, prefix="", title="我的应用"):
    database = str(database)
    prefix = "/" + prefix.strip("/") if prefix.strip("/") else ""
    token = secrets.token_urlsafe(32)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, kind="text/html; charset=utf-8"):
            body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def unavailable(self):
            if urlsplit(self.path).path == prefix + "/health":
                return self.send(503, '{"status":"unavailable"}', "application/json")
            retry = ""
            if getattr(self, "pending_title", ""):
                retry = '<form method="post" action="' + prefix + '/items"><input type="hidden" name="csrf" value="' + token + '"><label for="retry-title">未保存的内容</label><input id="retry-title" name="title" maxlength="200" value="' + html.escape(self.pending_title, quote=True) + '"><button>重试保存</button></form>'
            return self.send(503, '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>暂时无法保存</title><h1>数据暂时不可用</h1><p>请稍后重试，当前操作未完成。</p>' + retry + '<p><a href="' + prefix + '/">返回应用</a></p></html>')

        def do_GET(self):
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
            if path != prefix + "/":
                return self.send(404, "页面不存在")
            with sqlite3.connect(database) as db:
                rows = db.execute("SELECT id,title,done FROM items ORDER BY id DESC").fetchall()
            esc = html.escape
            items = "".join('<li><form method="post" action="%s/items/%d"><input type="hidden" name="csrf" value="%s"><span>%s</span><button name="done" value="%d">%s</button></form></li>' %
                            (prefix, i, token, esc(text), 0 if done else 1, "重新打开" if done else "完成") for i, text, done in rows)
            self.send(200, '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                      '<title>' + esc(title) + '</title><style>body{font:16px system-ui;color:#20242b;background:#f5f6f8;margin:0}main{max-width:720px;margin:64px auto;padding:24px}h1{font-size:36px;letter-spacing:-1px}p{color:#596270;line-height:1.7}form{display:flex;gap:12px;align-items:center}input{font:inherit;padding:12px;border:1px solid #b8c0cc;border-radius:6px;flex:1;min-width:0}button{font:inherit;background:#20242b;color:white;border:0;border-radius:6px;padding:12px;cursor:pointer}button:focus-visible,input:focus-visible{outline:3px solid #386bd6;outline-offset:3px}ul{padding:0;list-style:none}li{padding:16px 0;border-bottom:1px solid #d9dee5}li span{flex:1;overflow-wrap:anywhere}small{color:#697383}@media(max-width:600px){main{margin:16px auto}h1{font-size:28px}}</style><main>'
                      '<small>WEB 应用起点</small><h1>' + esc(title) + '</h1><p>应用已经可以运行。先添加一项内容，刷新后仍会保留。具体业务能力将在交付流程中实现和验证。</p>'
                      '<form method="post" action="' + prefix + '/items"><input type="hidden" name="csrf" value="' + token + '"><label for="title">新事项</label><input id="title" name="title" required maxlength="200" placeholder="写下一件要做的事"><button>添加</button></form>'
                      '<ul>' + (items or '<li>还没有内容，添加第一项开始。</li>') + '</ul><p><small>仅用于本地开发；正式发布前需要按实际业务配置身份验证、数据保护和部署环境。</small></p></main></html>')

        def do_POST(self):
            try:
                return self.post()
            except sqlite3.Error:
                return self.unavailable()

        def post(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= 8192:
                    return self.send(413, "表单内容过大或为空")
                values = parse_qs(self.rfile.read(n).decode("utf-8"))
            except (ValueError, UnicodeError):
                return self.send(400, "表单格式错误")
            if not hmac.compare_digest(values.get("csrf", [""])[0].encode("utf-8"), token.encode("ascii")):
                return self.send(403, "页面已过期，请刷新后重试")
            path = urlsplit(self.path).path
            self.pending_title = values.get("title", [""])[0]
            with sqlite3.connect(database) as db:
                if path == prefix + "/items":
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
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode
from app import make_server


class ApplicationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "app.db"
        self.server = make_server(("127.0.0.1", 0), self.db, "/demo", "项目测试")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def call(self, method, path, data=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        try:
            conn.request(method, path, urlencode(data) if data is not None else None,
                         {"Content-Type": "application/x-www-form-urlencoded"})
            r = conn.getresponse()
            return r.status, r.read().decode()
        finally:
            conn.close()

    def csrf(self):
        code, page = self.call("GET", "/demo/")
        self.assertEqual(code, 200)
        return re.search('name="csrf" value="([^"]+)"', page)[1]

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
