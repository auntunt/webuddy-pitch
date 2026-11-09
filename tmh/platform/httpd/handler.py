"""The request handler: authentication, routing to ROUTES, static pages and error mapping."""
from __future__ import annotations

from ..http_encoding import encode_json
import hmac
import json
import mimetypes
import os
import re
import secrets
import time
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from ... import __version__
from ..metrics import md_html, report_md
from ..errors import ApiError
from ..store import now
from ..api import ROUTES
from ..api._common import _private
from ..app import Platform
from .preview import _pvkey, serve_preview
from .util import _cookie


class Req:
    def __init__(self, h, query: dict, body: dict, user: str):
        self.h, self.query, self.body, self.user = h, query, body, user

    def arg(self, k: str) -> str:
        return (self.query.get(k) or [""])[0]


WEB_DIST = Path(__file__).resolve().parent.parent / "web_dist"


def make_handler(P: Platform, token: str = "", web_prefix: str = ""):
    from .. import login as L
    from ..ui import page
    throttle = L.Throttle()

    class H(BaseHTTPRequestHandler):
        server_version = "tmh/" + __version__

        def log_message(self, fmt, *args):  # quiet; errors are printed below
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            body, extra = encode_json(body, ctype, self.headers.get("Accept-Encoding", ""), extra)
            extra = extra or {}
            cache = next((v for k, v in extra.items() if k.lower() == "cache-control"), "no-store")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")  # no page (a preview's, say) may frame the platform and click for a person
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            for k, v in extra.items():
                if k.lower() != "cache-control":
                    self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code: int, obj):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _authorized(self, q: dict) -> bool:
            self._who = ""
            accounts = L.has_accounts(P.data_dir)
            if accounts:
                self._who = L.read_session(P.data_dir, _cookie(self.headers.get("Cookie", ""), "tmh_session"))
                if self._who:
                    return True
            if not token:
                return not accounts
            got = self.headers.get("X-TMH-Token") or (q.get("token") or [""])[0] or _cookie(self.headers.get("Cookie", ""), "tmh_token")
            return hmac.compare_digest(got.encode("utf-8"), token.encode("utf-8"))

        def _next_spa(self, method: str, path: str, q: dict, u):
            extra = {}
            if token and (q.get("token") or [""])[0] == token:
                extra["Set-Cookie"] = "tmh_token=%s; Path=/; HttpOnly; SameSite=Strict" % token
            if not self._authorized(q):
                if L.has_accounts(P.data_dir):
                    nxt = (web_prefix + path) + (("?" + u.query) if u.query else "")
                    return self._send(303, b"", "text/plain", {"Location": "/login?next=" + quote(nxt, safe="")})
                return self._send(401, "需要访问令牌：在地址后加 ?token=…".encode("utf-8"), "text/plain; charset=utf-8")
            if path.startswith("/next/assets/"):
                m = re.fullmatch(r"/next/assets/([A-Za-z0-9._-]+)", path)
                f = WEB_DIST / "assets" / m.group(1) if m else None
                if not f or not f.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "image/svg+xml"):
                    ctype += "; charset=utf-8"
                return self._send(200, f.read_bytes(), ctype,
                                  {"Cache-Control": "public, max-age=31536000, immutable"})
            index = WEB_DIST / "index.html"
            if not index.is_file():
                return self._send(503, "新版界面尚未构建，请先运行 web 构建".encode("utf-8"), "text/plain; charset=utf-8")
            html = index.read_text("utf-8")
            base = (web_prefix + "/next/") if web_prefix else "/next/"
            tag = '<base href="%s">' % base
            if "<head>" in html:
                html = html.replace("<head>", "<head>" + tag, 1)
            elif "</head>" in html:
                html = html.replace("</head>", tag + "</head>", 1)
            else:
                html = tag + html
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", extra)

        def _client(self) -> str:
            ip = self.client_address[0]
            fwd = self.headers.get("X-Forwarded-For") or ""
            if ip in ("127.0.0.1", "::1") and fwd:  # behind our own Caddy/nginx: it appends the real client last
                ip = fwd.split(",")[-1].strip()
            return ip

        def _session_cookie(self, value: str, age: int) -> str:
            secure = "; Secure" if (self.headers.get("X-Forwarded-Proto") or "") == "https" else ""
            return "tmh_session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax%s" % (value, age, secure)

        def _login(self, method: str, q: dict):
            if method == "GET":
                if self._authorized(q) and self._who:
                    return self._send(303, b"", "text/plain", {"Location": L.safe_next((q.get("next") or ["/"])[0])})
                return self._send(200, L.page(P.brand, next_=(q.get("next") or ["/"])[0]).encode("utf-8"), "text/html; charset=utf-8")
            n = int(self.headers.get("Content-Length") or 0)
            if n > 8192:
                return self._send(413, b"too large", "text/plain")
            f = parse_qs(self.rfile.read(n).decode("utf-8", "replace") if n else "")
            name, pw = (f.get("username") or [""])[0].strip(), (f.get("password") or [""])[0]
            nxt = (f.get("next") or ["/"])[0]
            who = self._client()
            if throttle.blocked(who):
                return self._send(429, L.page(P.brand, "密码错误次数太多，请 10 分钟后再试", name, nxt).encode("utf-8"), "text/html; charset=utf-8")
            if not L.verify(P.data_dir, name, pw):
                throttle.fail(who)
                return self._send(401, L.page(P.brand, "账号或密码不正确", name, nxt).encode("utf-8"), "text/html; charset=utf-8")
            throttle.ok(who)
            return self._send(303, b"", "text/plain", {"Location": L.safe_next(nxt),
                                                       "Set-Cookie": self._session_cookie(L.make_session(P.data_dir, name), L.SESSION_DAYS * 86400)})

        def _local_host(self) -> bool:
            # without a token, only answer requests addressed to this machine (blocks DNS rebinding)
            if token:
                return True
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return host in ("127.0.0.1", "localhost", "::1", "")

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):  # only a preview's own app uses these; the platform's API is GET and POST
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def do_OPTIONS(self):
            self._dispatch("OPTIONS")

        def _preview(self, method: str, u, q: dict):
            """/pv/ on the platform's own address. With a preview address of its own, a person who is logged in is
            sent there with a pass; without one, the preview is served here, sandboxed by the browser."""
            from .. import preview
            m = re.match(r"^/pv/([A-Za-z0-9]+-(?:\d+|[Mm][Aa][Ii][Nn]))(/.*)?$", u.path)
            if not m:
                return self._send(404, b"not found", "text/plain")
            key = _pvkey(m.group(1))
            try:
                prefix, rest, expected = preview.route(key, m.group(2) or "")
                preview.require_bound(P.data_dir, key, expected)
            except ApiError as e:
                return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
            g = _cookie(self.headers.get("Cookie", ""), preview.cookie_name(key, expected))
            if not P.preview_port and (rest == "/__open" or preview.granted(P.data_dir, key, g, expected_commit=expected)):
                return serve_preview(self, P, method, u, sandboxed=True)
            if not self._authorized(q):
                return self._send(401, "请从 webuddy 的工单页或签收链接打开预览".encode("utf-8"), "text/plain; charset=utf-8")
            return self._send(303, b"", "text/plain", {"Location": "%s%s/__open?g=%s" % (
                preview.base_url(self.headers, P.preview_port), prefix, preview.grant(P.data_dir, key, expected_commit=expected)),
                "Referrer-Policy": "no-referrer"})

        def _bot(self, method: str, path: str, q: dict):
            from ... import bots
            m = re.match(r"^/bot/(dingtalk|feishu|wecom|api)/([^/]+)$", path)
            if not m:
                return self._json(404, {"error": "没有这个机器人地址"})
            kind = m.group(1)
            if method != "POST" and kind != "wecom":
                return self._json(405, {"error": "method"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1024 * 1024:
                return self._json(413, {"error": "请求太大"})
            raw = self.rfile.read(n) if n else b""
            try:
                root = P.root(P.project(unquote(m.group(2))))
                if kind == "wecom":
                    code, text = bots.wecom(root, method, {k: v[0] for k, v in q.items()}, raw)
                    return self._send(code, text.encode("utf-8"), "text/plain; charset=utf-8")
                code, obj = getattr(bots, kind)(root, self.headers, raw)
                return self._json(code, obj)
            except bots.BotError as e:
                return self._json(e.code, {"error": str(e)})
            except ApiError as e:
                return self._json(e.code, {"error": str(e)})
            except ValueError:
                return self._json(400, {"error": "请求格式不对"})
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {"error": type(e).__name__})

        def _alert(self, method: str, path: str, q: dict):
            from .. import alerts
            m = re.match(r"^/hook/alert/([^/]+)$", path)
            if not m or method != "POST":
                return self._json(404 if not m else 405, {"error": "告警地址是 POST /hook/alert/<项目代号>"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 2 * 1024 * 1024:
                return self._json(413, {"error": "请求太大"})
            raw = self.rfile.read(n) if n else b""
            try:
                p = P.project(unquote(m.group(1)))
                c = alerts.check(P.data_dir, p["key"], self.headers, q)
                return self._json(200, alerts.receive(P, p, alerts.parse(raw), int(c.get("per_hour") or 20)))
            except alerts.AlertError as e:
                return self._json(e.code, {"error": str(e)})
            except ApiError as e:
                return self._json(e.code, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                return self._json(500, {"error": type(e).__name__})

        def _dispatch(self, method: str):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            path = u.path
            if path.startswith("/bot/"):  # chat-platform callbacks: signed by the platform, not by our token
                return self._bot(method, path, q)
            if path.startswith("/hook/alert/"):  # monitoring webhooks: their own key, not our token
                return self._alert(method, path, q)
            if path.startswith("/capture/"):  # the bookmarklet on the client's page: its token can only add a capture
                return self._capture(method, path)
            if not self._local_host():
                return self._send(403, "只接受本机访问；对局域网开放请设置 TMH_TOKEN".encode("utf-8"), "text/plain; charset=utf-8")
            if path == "/login":
                return self._login(method, q)
            if path.startswith("/pv/"):  # a change waiting for acceptance, running: people logged in, or the client's link
                return self._preview(method, u, q)
            if path.startswith("/v/"):  # a client's link to a project's current version: the link is the credential
                return self._version_link(method, path)
            if path.startswith("/sign/"):  # the client's sign-off page: the one-time link is the credential, no account
                return self._sign(method, path)
            if path.startswith("/ask/"):  # the client answers open questions: the link is the credential, no account
                return self._ask(method, path)
            if path == "/logout":
                return self._send(303, b"", "text/plain", {"Location": "/login", "Set-Cookie": self._session_cookie("", 0)})
            if not path.startswith("/api/"):
                if method != "GET":
                    return self._json(405, {"error": "method"})
                if path == "/next":
                    return self._send(303, b"", "text/plain", {"Location": "/next/" + (("?" + u.query) if u.query else "")})
                if path == "/next/" or path.startswith("/next/"):
                    return self._next_spa(method, path, q, u)
                if path in ("/", "/index.html"):
                    extra = {}
                    if token and (q.get("token") or [""])[0] == token:
                        extra["Set-Cookie"] = "tmh_token=%s; Path=/; HttpOnly; SameSite=Strict" % token
                    if not self._authorized(q):
                        if L.has_accounts(P.data_dir):
                            return self._send(303, b"", "text/plain", {"Location": "/login"})
                        return self._send(401, "需要访问令牌：在地址后加 ?token=…".encode("utf-8"), "text/plain; charset=utf-8")
                    return self._send(200, page().encode("utf-8"), "text/html; charset=utf-8", extra)
                m = re.match(r"^/p/([^/]+)/efficiency$", path)
                if m:
                    if not self._authorized(q):
                        return self._send(401, b"unauthorized", "text/plain")
                    try:
                        p = P.project(unquote(m.group(1)))
                        mt = P.metrics(p, (q.get("month") or [""])[0])
                    except ApiError as e:
                        return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                    return self._send(200, md_html(report_md(mt), "AI 提效报告 %s %s" % (p["key"], mt["period"])).encode("utf-8"), "text/html; charset=utf-8")
                m = re.match(r"^/e/([A-Za-z0-9]+-\d+)\.intoto\.json$", path)
                if m:  # the same package, as an in-toto Statement a client keeps and checks with `tmh evidence-verify`
                    if not self._authorized(q):
                        return self._send(401, b"unauthorized", "text/plain")
                    from .. import signoff
                    try:
                        body = json.dumps(signoff.export(P, m.group(1)), ensure_ascii=False, indent=1).encode("utf-8")
                    except ApiError as e:
                        return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                    return self._send(200, body, "application/json; charset=utf-8",
                                      {"Content-Disposition": "attachment; filename=\"%s.intoto.json\"" % m.group(1).upper()})
                m = re.match(r"^/e/([A-Za-z0-9]+-\d+)(?:/f/([0-9a-f]{64}\.[a-z]+))?$", path)
                if m:  # a ticket's evidence package as one page (for the provider and the client's auditors)
                    if not self._authorized(q):
                        return self._send(401, b"unauthorized", "text/plain")
                    from .. import signoff
                    try:
                        if m.group(2):
                            signoff.owns(P.data_dir, m.group(1).upper(), m.group(2))
                            data, ctype = signoff.file_bytes(P.data_dir, m.group(2))
                            return self._send(200, data, ctype)
                        return self._send(200, signoff.package_page(P, m.group(1)).encode("utf-8"), "text/html; charset=utf-8")
                    except ApiError as e:
                        return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                m = re.match(r"^/p/([A-Za-z0-9]+)/code\.bundle$", path)
                if m:  # 我来写 without access to the repository: the main line as one file
                    if not self._authorized(q):
                        return self._send(401, b"unauthorized", "text/plain")
                    from .. import handwork
                    try:
                        f = handwork.bundle(P, P.project(m.group(1).upper()))
                    except ApiError as e:
                        return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                    try:
                        data = f.read_bytes()
                    finally:
                        f.unlink(missing_ok=True)
                    return self._send(200, data, "application/octet-stream",
                                      {"Content-Disposition": "attachment; filename=\"%s.bundle\"" % m.group(1).upper()})
                m = re.match(r"^/p/([^/]+)/report/(.*)$", path)
                if m:
                    if not self._authorized(q):
                        return self._send(401, b"unauthorized", "text/plain")
                    return self._report(unquote(m.group(1)), unquote(m.group(2)) or "index.html")
                return self._send(404, b"not found", "text/plain")
            if not self._authorized(q):
                return self._json(401, {"error": "需要访问令牌"})
            if not os.environ.get("TMH_PUBLIC_URL"):  # where people reach us (learnt from them, not from strangers): chat links
                host = (self.headers.get("Host") or "").strip()
                if host and re.fullmatch(r"[A-Za-z0-9.\-\[\]:]+", host) and not _private(host):
                    P.public_url = "%s://%s" % ("https" if (self.headers.get("X-Forwarded-Proto") or "") == "https" else "http", host)
            if urlparse(self.headers.get("Referer") or "").path.startswith("/pv/"):  # an extra check only: the boundary is the sandbox or the preview's own address
                return self._json(403, {"error": "预览里的页面不能调用平台接口"})
            if method == "POST" and self.headers.get("X-TMH") != "1":
                return self._json(403, {"error": "缺少 X-TMH 请求头"})
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 5 * 1024 * 1024:
                    return self._json(413, {"error": "请求太大"})
                raw = self.rfile.read(n) if n else b""
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except ValueError:
                    return self._json(400, {"error": "请求不是 JSON"})
            user = self._who or unquote(self.headers.get("X-TMH-User") or "") or P.user or "我"
            m = re.fullmatch(r"/api/projects/([^/]+)/tasks/([^/]+)/return/(patch|files|archive)", path)
            if m and method == "GET":  # read-only downloads of a task's committed change; nothing is written
                from .. import code_return
                from pathlib import Path as _P
                try:
                    data, ctype, name = code_return.download(_P(P.project(unquote(m.group(1)))["root"]), unquote(m.group(2)), m.group(3))
                except ApiError as e:
                    return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                return self._send(200, data, ctype, {"Content-Disposition": 'attachment; filename="%s"' % name})
            for mth, rx, fn in ROUTES:
                if mth != method:
                    continue
                m = rx.match(path)
                if m:
                    try:
                        # Reference-only repositories are never executable or
                        # writable through legacy project/ticket/run endpoints.
                        if method == 'POST':
                            from ..project_library import require_development
                            target = None
                            project_path = re.fullmatch(r'/api/projects/([^/]+)/(.*)', path)
                            ticket_path = re.match(r'^/api/tickets/([^/]+)(?:/|$)', path)
                            run_path = re.match(r'^/api/runs/(\d+)(?:/|$)', path)
                            session_path = re.match(r'^/api/sessions/(\d+)(?:/|$)', path)
                            if project_path and project_path[2] != 'library':
                                target = P.store.project(unquote(project_path[1]))
                            elif ticket_path:
                                ticket = P.store.ticket(unquote(ticket_path[1]))
                                target = P.store.project(ticket['project_id']) if ticket else None
                            elif run_path:
                                run = P.store.run(int(run_path[1]))
                                target = P.store.project(run['project_id']) if run else None
                            elif session_path:
                                session = P.store.session(int(session_path[1]))
                                target = P.store.project(session['project_id']) if session else None
                            if target:
                                try:
                                    require_development(P.store, target)
                                except ValueError as exc:
                                    raise ApiError(409, str(exc)) from exc
                        res = fn(P, Req(self, q, body, user[:40]), **{k: unquote(v) for k, v in m.groupdict().items()})
                        return self._json(200, res)
                    except ApiError as e:
                        return self._json(e.code, {"error": str(e), **({"code": e.reason} if getattr(e, "reason", "") else {})})
                    except FileNotFoundError as e:
                        return self._json(404, {"error": str(e)})
                    except Exception as e:  # noqa: BLE001 - report, keep serving
                        if isinstance(e, PermissionError) and getattr(P, "tenant_context", None):
                            return self._json(403, {"error": "此步骤需要独立执行环境；未获得可核对的结果", "code": "execution_disabled"})
                        # the person gets what to do and a reference to quote; the exception stays in the log
                        ref = now()[5:19].replace("-", "").replace(" ", "-").replace(":", "") + "-" + secrets.token_hex(2)
                        print("[error %s] %s %s %s: %s" % (ref, method, path, type(e).__name__, e), flush=True)
                        traceback.print_exc()
                        return self._json(500, {"error": "服务器处理这一步时出错了，这一步没有完成。刷新看看结果再决定要不要重试；还不行请把编号 %s 告诉管理员。" % ref,
                                                "ref": ref})
            return self._json(404, {"error": "没有这个接口：%s %s" % (method, path)})

        def _capture(self, method: str, path: str):
            from .. import pinpoint
            cors = {"Access-Control-Allow-Origin": "*"}
            m = re.match(r"^/capture/([A-Za-z0-9_\-]{20,64})$", path)
            if not m:
                return self._send(404, b'{"error":"no"}', "application/json", cors)
            if method != "POST":
                return self._send(405, b'{"error":"method"}', "application/json", cors)
            key = pinpoint.token_project(P.data_dir, m.group(1))
            n = int(self.headers.get("Content-Length") or 0)
            reply = lambda code, obj: self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cors)
            if not key:
                return reply(401, {"message": "这个书签已经失效，请到 webuddy 重新拖一个"})
            if n > 512 * 1024:
                return reply(413, {"message": "框得太大了，框小一点再试"})
            try:
                cap = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                pin = pinpoint.save(P, P.project(key), cap if isinstance(cap, dict) else {}, "页面框选", "bookmarklet")
            except ValueError:
                return reply(400, {"message": "发送的内容不对"})
            except ApiError as e:
                return reply(e.code, {"message": str(e)})
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return reply(500, {"message": "webuddy 出错了：%s" % type(e).__name__})
            n1, n2 = len(pin["found"]["layer1"]) + len(pin["found"]["layer2"]), len(pin["found"]["layer3"])
            return reply(200, {"id": pin["id"], "message": "已发送到 webuddy：找到 %d 个候选文件、%d 个后端入口" % (n1, n2)})

        def _ask(self, method: str, path: str):
            from .. import intake
            html_t = "text/html; charset=utf-8"
            m = re.match(r"^/ask/([A-Za-z0-9_\-]{20,64})$", path)
            if not m:
                return self._send(404, "链接不对".encode("utf-8"), "text/plain; charset=utf-8")
            token = m.group(1)
            if method == "GET":
                return self._send(200, intake.client_page(P, token).encode("utf-8"), html_t)
            if method != "POST":
                return self._send(405, b"method", "text/plain")
            n = int(self.headers.get("Content-Length") or 0)
            if n > 64 * 1024:
                return self._send(413, b"too large", "text/plain")
            form = parse_qs(self.rfile.read(n).decode("utf-8", "replace") if n else "")
            try:
                intake.client_answer(P, token, intake.form_answers(form), (form.get("name") or [""])[0])
            except ApiError as e:
                return self._send(e.code if e.code != 409 else 409, intake.client_page(P, token, msg=str(e)).encode("utf-8"), html_t)
            return self._send(200, intake.client_page(P, token, done=True).encode("utf-8"), html_t)

        def _sign(self, method: str, path: str):
            from .. import signoff
            m = re.match(r"^/sign/([A-Za-z0-9_\-]{20,64})/pv/?$", path)
            if m and method == "GET":  # the client opens the change itself: a pass to this one preview, valid as long as the link
                from .. import preview
                from ... import evidence as ev
                try:
                    x = signoff.link_of(P.data_dir, m.group(1))
                    if x.get("used") or x["expires"] < ev.now():
                        raise ApiError(410, "这个签收链接已经用过、被替换或者过期了，预览也跟着关闭")
                    state = signoff.state(P.data_dir, x["key"])
                    signoff._require_current_binding(state)
                    if not state.get("intact") or state.get("stale"):
                        raise ApiError(409, "签收依据已经变化或损坏，请联系乙方重新核对并发送链接")
                    if not signoff._link_matches(x, state):
                        raise ApiError(409, "证据包版本已变化，这个签收链接不能打开新版本；请联系乙方重新发送")
                    binding = (state.get("snapshot") or {}).get("delivery_binding")
                    expected = ""
                    if binding is not None:
                        expected = binding.get("commit") if isinstance(binding, dict) else ""
                        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", expected):
                            raise ApiError(409, "这次签收尚未绑定可预览的完整代码提交")
                        preview.require_bound(P.data_dir, x["key"], expected)
                except ApiError as e:
                    return self._send(e.code, signoff.message_page(str(e)).encode("utf-8"), "text/html; charset=utf-8")
                until = time.mktime(time.strptime(x["expires"][:19], "%Y-%m-%d %H:%M:%S"))
                g = preview.grant(P.data_dir, x["key"], signoff._th(m.group(1)), until, expected_commit=expected)
                prefix = preview.bound_prefix(x["key"], expected) if expected else "/pv/" + x["key"]
                return self._send(303, b"", "text/plain", {"Location": "%s%s/__open?g=%s" % (preview.base_url(self.headers, P.preview_port), prefix, g),
                                                           "Referrer-Policy": "no-referrer"})
            m = re.match(r"^/sign/([A-Za-z0-9_\-]{20,64})/package\.intoto\.json$", path)
            if m and method == "GET":  # the signer keeps their own copy, with the same link as the credential
                try:
                    key = signoff.link_of(P.data_dir, m.group(1))["key"]
                    body = json.dumps(signoff.export(P, key), ensure_ascii=False, indent=1).encode("utf-8")
                except ApiError as e:
                    return self._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                return self._send(200, body, "application/json; charset=utf-8",
                                  {"Content-Disposition": "attachment; filename=\"%s.intoto.json\"" % key})
            m = re.match(r"^/sign/([A-Za-z0-9_\-]{20,64})(?:/f/([0-9a-f]{64}\.[a-z]+))?$", path)
            html_t = "text/html; charset=utf-8"
            if not m:
                return self._send(404, "签收链接不对".encode("utf-8"), "text/plain; charset=utf-8")
            token, f = m.group(1), m.group(2)
            try:
                if method == "GET" and f:
                    signoff.owns(P.data_dir, signoff.link_of(P.data_dir, token)["key"], f)
                    data, ctype = signoff.file_bytes(P.data_dir, f)
                    return self._send(200, data, ctype)
                if method == "GET":
                    return self._send(200, signoff.sign_page(P, token).encode("utf-8"), html_t)
                if method != "POST" or f:
                    return self._send(405, b"method", "text/plain")
                n = int(self.headers.get("Content-Length") or 0)
                if n > 64 * 1024:
                    return self._send(413, b"too large", "text/plain")
                form = parse_qs(self.rfile.read(n).decode("utf-8", "replace") if n else "")
                g = lambda k: (form.get(k) or [""])[0]
                verdicts = {k[3:]: v[0] for k, v in form.items() if k.startswith("ac_")}
                try:
                    done = signoff.decide(P, token, g("action"), g("name"), verdicts, g("note"), self._client())
                except ApiError as e:
                    if e.code in (400,):
                        return self._send(400, signoff.sign_page(P, token, msg=str(e)).encode("utf-8"), html_t)
                    raise
                return self._send(200, signoff.sign_page(P, token, done=done).encode("utf-8"), html_t)
            except ApiError as e:
                return self._send(e.code, signoff.message_page(str(e)).encode("utf-8"), html_t)

        def _version_link(self, method: str, path: str):
            """/v/<token>: the version and what changed, for the client; /v/<token>/open: into the running version."""
            from .. import preview, workbench
            m = re.match(r"^/v/([A-Za-z0-9_\-]{20,64})(/open)?/?$", path)
            html_t = "text/html; charset=utf-8"
            if not m or method not in ("GET", "HEAD"):
                return self._send(404, "链接不对".encode("utf-8"), "text/plain; charset=utf-8")
            try:
                if m.group(2):
                    key, g = workbench.share_grant(P, m.group(1))
                    return self._send(303, b"", "text/plain", {"Location": "%s/pv/%s/__open?g=%s" % (preview.base_url(self.headers, P.preview_port), key, g),
                                                               "Referrer-Policy": "no-referrer"})
                return self._send(200, workbench.share_page(P, m.group(1)).encode("utf-8"), html_t, {"Referrer-Policy": "no-referrer"})
            except ApiError as e:
                return self._send(e.code, workbench.message_page(str(e)).encode("utf-8"), html_t)

        def _report(self, key: str, rel: str):
            p = P.store.project(key)
            if not p:
                return self._send(404, b"no project", "text/plain")
            base = (Path(p["root"]) / ".tmh" / "report").resolve()
            f = (base / rel).resolve()
            if base not in f.parents and f != base or not f.is_file():
                return self._send(404, "还没有业务全景报告，在项目目录运行 tmh report 生成".encode("utf-8"), "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            return self._send(200, f.read_bytes(), ctype)

    return H
