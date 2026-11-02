"""Account-authenticated, fixed-tenant HTTP gateway for private workers.

No business Platform is constructed in this process. Gateway admission and
worker execution recheck the same context under the registry guard. The worker
owns the execution lock so gateway death cannot release an unfinished mutation.
"""
from contextlib import closing
from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import threading
from urllib.parse import parse_qs, quote, urlsplit

from . import feishu_login, login, tenancy
from .errors import ApiError
from .tenant_runtime import BOT_HEADERS


def error(code, message, reason="access_denied"):
    return tenancy._error(code, message, reason)


@dataclass(frozen=True)
class PendingProxy:
    tenant: str
    actor: str
    method: str
    path: str
    body: bytes
    headers: dict
    access: dict
    meta: bool


def projects(reg, tenant):
    """Read names/IDs for administration without starting a business runtime."""
    target = reg.one("SELECT * FROM tenants WHERE id=?", (tenant,))
    if not target:
        raise error(404, "没有这个租户", "tenant_not_found")
    root = Path(target["path"])
    expected = reg.data_dir if tenant == "default" else reg.data_dir / "tenants" / tenant / "data"
    if root != expected or any(p.is_symlink() for p in (root, *root.parents)):
        raise error(403, "租户存储路径无效", "storage_invalid")
    path = root / "platform.db"
    if path.is_symlink():
        raise error(403, "租户数据库路径无效", "storage_invalid")
    if not path.exists():
        return []
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT id,key,name FROM projects ORDER BY id")]


def access_meta(reg, user, context):
    rows = reg.q("SELECT t.id,t.name,t.status,m.role FROM tenants t JOIN memberships m ON t.id=m.tenant_id WHERE m.user=? AND t.status='active' ORDER BY t.created,t.id", (user,))
    for row in rows:
        row["url"] = "/t/" + row["id"] + "/"
    return {"tenant": {k: context["tenant"][k] for k in ("id", "name", "status", "runtime")},
            "user": user, "role": context["role"], "context_token": context["context_token"],
            "authz_revision": context["authz_revision"], "tenants": rows,
            "project_grants": context["project_grants"],
            "capabilities": context["capabilities"], "can_manage": context["can_manage"],
            "platform_owner": context["platform_owner"]}


def make_handler(registry, workers, *, brand="webuddy"):
    reg = registry
    throttle = login.Throttle()

    class Handler(BaseHTTPRequestHandler):
        server_version = "webuddy-gateway"

        def log_message(self, fmt, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def _send(self, code, body=b"", content_type="text/plain; charset=utf-8", headers=None):
            # Stage the response while authorization is held. Never write a
            # remote client socket under the global revocation guard.
            return code, body, content_type, headers

        def _flush(self, code, body, content_type, headers):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            for key, value in (headers or {}).items():
                for one in value if isinstance(value, list) else [value]:
                    self.send_header(key, one)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code, value):
            return self._send(code, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _read_cookie(self, name):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                return cookie[name].value if name in cookie else ""
            except (ValueError, TypeError, CookieError):
                return ""

        def _session(self):
            return login.read_session(reg.data_dir, self._read_cookie("tmh_session"))

        def _cookie(self, value, age, name="tmh_session", path="/"):
            secure = "; Secure" if self._scheme() == "https" else ""
            return "%s=%s; Path=%s; Max-Age=%d; HttpOnly; SameSite=Lax%s" % (name, value, path, age, secure)

        def _page(self, code, **kw):
            pending = feishu_login.read_pending(reg.data_dir, self._read_cookie(feishu_login.BIND_COOKIE)) if feishu_login.enabled() else {}
            if pending and not kw.get("notice"):
                kw["notice"] = "飞书账号「%s」还没绑定 Webuddy 账号。用账号密码登录一次就会绑定，以后可以直接用飞书登录。" % (pending.get("name") or "")
            return self._send(code, login.page(brand, feishu=feishu_login.enabled(), **kw).encode(), "text/html; charset=utf-8")

        def _base(self):
            return os.environ.get("TMH_PUBLIC_URL", "").rstrip("/") or self._scheme() + "://" + self.headers.get("Host", "")

        def _feishu(self, method, path, query):
            if method not in ("GET", "HEAD") or not feishu_login.enabled():
                raise error(404, "未开启飞书登录", "route_denied")
            if path == "/login/feishu":
                url, flow = feishu_login.start(reg.data_dir, self._base(), (query.get("next") or ["/"])[0])
                return self._send(303, headers={"Location": url, "Set-Cookie": self._cookie(flow, feishu_login.FLOW_SECONDS, feishu_login.FLOW_COOKIE, "/login")})
            done = self._cookie("", 0, feishu_login.FLOW_COOKIE, "/login")
            try:
                ident, nxt = feishu_login.identity(reg.data_dir, self._base(), self._read_cookie(feishu_login.FLOW_COOKIE),
                                                   (query.get("code") or [""])[0], (query.get("state") or [""])[0])
            except feishu_login.FeishuLoginError as e:
                code, body, kind, _ = self._page(401, err=str(e))
                return code, body, kind, {"Set-Cookie": done}
            with reg.authorization_guard():
                user = feishu_login.bound_user(reg, ident)
                session = login.make_session(reg.data_dir, user) if user else ""
            if not user:
                bind = self._cookie(feishu_login.pending(reg.data_dir, ident), feishu_login.BIND_SECONDS, feishu_login.BIND_COOKIE, "/login")
                return self._send(303, headers={"Location": "/login?next=" + quote(nxt, safe=""), "Set-Cookie": [done, bind]})
            return self._send(303, headers={"Location": nxt, "Set-Cookie": [done, self._cookie(session, login.SESSION_DAYS * 86400)]})

        def _scheme(self):
            # Forwarded transport is accepted only from the loopback reverse proxy.
            return "https" if self.client_address[0] in ("127.0.0.1", "::1") and self.headers.get("X-Forwarded-Proto") == "https" else "http"

        def _origin(self):
            origin = self.headers.get("Origin")
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise error(403, "拒绝跨站请求", "origin_denied")
            if origin:
                parsed = urlsplit(origin)
                if parsed.scheme != self._scheme() or parsed.netloc != self.headers.get("Host") or parsed.path not in ("", "/"):
                    raise error(403, "请求来源与当前站点不同", "origin_denied")

        def _body(self, maximum=5 * 1024 * 1024):
            if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) > 1:
                raise error(400, "不支持此请求传输格式", "invalid_request")
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise error(400, "请求长度无效", "invalid_request") from None
            if length < 0 or length > maximum:
                raise error(413, "请求大小不合适", "invalid_request")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise error(400, "请求未完整传输", "invalid_request")
            return raw

        def _login(self, method, query):
            nxt = login.safe_next((query.get("next") or ["/"])[0])
            if method == "GET":
                with reg.authorization_guard():
                    user = self._session()
                if user:
                    return self._send(303, headers={"Location": nxt})
                return self._page(200, next_=nxt)
            self._origin()
            fields = parse_qs(self._body(8192).decode("utf-8"))
            name = (fields.get("username") or [""])[0].strip()
            password = (fields.get("password") or [""])[0]
            nxt = login.safe_next((fields.get("next") or ["/"])[0])
            client = self.client_address[0]
            if client in ("127.0.0.1", "::1") and self.headers.get("X-Forwarded-For"):
                client = self.headers["X-Forwarded-For"].split(",")[-1].strip()
            if throttle.blocked(client):
                return self._page(429, err="密码错误次数太多，请稍后重试", name=name, next_=nxt)
            pending = feishu_login.read_pending(reg.data_dir, self._read_cookie(feishu_login.BIND_COOKIE)) if feishu_login.enabled() else {}
            with reg.authorization_guard():
                if not login.verify(reg.data_dir, name, password):
                    throttle.fail(client)
                    return self._page(401, err="账号或密码不正确", name=name, next_=nxt)
                cookie = login.make_session(reg.data_dir, name)
                if pending:
                    feishu_login.bind(reg, name, pending)
            throttle.ok(client)
            cookies = [self._cookie(cookie, login.SESSION_DAYS * 86400)]
            if pending:
                cookies.append(self._cookie("", 0, feishu_login.BIND_COOKIE, "/login"))
            return self._send(303, headers={"Location": nxt, "Set-Cookie": cookies if pending else cookies[0]})

        def _home(self, user):
            rows = reg.q("SELECT t.id,t.name FROM tenants t JOIN memberships m ON m.tenant_id=t.id WHERE m.user=? AND t.status='active' ORDER BY t.created,t.id", (user,))
            if len(rows) == 1:
                return self._send(303, headers={"Location": "/t/" + rows[0]["id"] + "/"})
            owner = reg.one("SELECT 1 FROM platform_owners WHERE name=?", (user,))
            if not rows and owner:
                return self._send(303, headers={"Location": "/t/default/#/access"})
            links = "".join('<li><a href="/t/%s/">%s</a></li>' % (html.escape(t["id"]), html.escape(t["name"])) for t in rows)
            content = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>选择组织</title><h1>选择组织</h1>' + ("<ul>" + links + "</ul>" if links else "<p>当前账号尚未加入有效组织，请联系管理员分配访问权限。</p>") + '<a href="/logout">退出账号</a></html>'
            return self._send(200, content.encode(), "text/html; charset=utf-8")

        def _tool(self, method, url):
            """Bearer credentials only admit the narrow agent API, never browser authority."""
            from . import tool_access
            if len(self.headers.get_all('Authorization', [])) != 1:
                raise error(401, '工具凭据无效', 'tool_invalid')
            match = re.fullmatch(r'/t/([A-Za-z0-9_-]+)/api/agent/([a-z_]+)', url.path)
            if method != 'POST' or not match or url.query or url.fragment:
                raise error(403, '工具凭据仅可使用获准的智能体接口', 'tool_route_denied')
            tenant, operation = match.groups()
            authorization = self.headers['Authorization']
            if not authorization.startswith('Bearer ') or authorization != authorization.strip():
                raise error(401, '工具凭据无效', 'tool_invalid')
            bearer = authorization[7:]
            raw = self._body()
            body = json.loads(raw) if raw else {}
            if not isinstance(body, dict):
                raise error(400, '请求必须是 JSON 对象', 'invalid_request')
            with reg.authorization_guard():
                connection = tool_access.authenticate(reg, tenant, bearer)
                if operation not in tool_access.allowed_operations(connection['scope']):
                    raise error(403, '此工具连接未获准执行该操作', 'tool_operation_denied')
            workers.ensure(tenant)
            with reg.authorization_guard():
                connection = tool_access.authenticate(reg, tenant, bearer)
                # The bearer never reaches the worker or application handlers.
                # The connection ID is authenticated by the private-worker proof.
                headers = {'Content-Type': 'application/json', 'X-TMH': '1',
                           'X-Webuddy-Context': tool_access.context_token(connection),
                           'X-Webuddy-Tool': connection['id'],
                           'X-Webuddy-Agent': self.headers.get('X-Webuddy-Agent', 'tool')}
                if connection['scope'] == 'execute' and self.headers.get('X-Webuddy-Execution') == '1':
                    headers['X-Webuddy-Execution'] = '1'
                return PendingProxy(tenant, connection['user'], method, '/api/agent/' + operation,
                                    raw, headers, {}, False)

        def _bot(self, method, tenant, path, kind, query):
            # A chat platform's callback: no session or X-TMH, the platform signs it.
            # It reaches only the tenant's bot handler, which checks that signature.
            if method != "POST" and kind != "wecom":
                raise error(405, "机器人回调只接受 POST", "method_denied")
            row = reg.one("SELECT status FROM tenants WHERE id=?", (tenant,))
            if not row or row["status"] != "active":
                raise error(404, "没有这个机器人地址", "route_denied")
            length = int(self.headers.get("Content-Length") or 0)
            if length < 0 or length > 1024 * 1024:
                raise error(413, "请求太大", "invalid_request")
            raw = self.rfile.read(length) if length else b""
            workers.ensure(tenant)
            headers = {k: v for k, v in self.headers.items() if k.lower() in ("content-type",) + BOT_HEADERS}
            headers["X-Webuddy-Public"] = "bot"
            return PendingProxy(tenant, "bot:" + kind, method, path + ("?" + query if query else ""), raw, headers, {}, False)

        def _dispatch(self, method):
            try:
                url = urlsplit(self.path)
                if not self.path.startswith("/") or url.netloc or "\\" in url.path or any("%" in part for part in url.path.split("/", 3)[:3]):
                    raise error(400, "请求路径无效", "invalid_request")
                query = parse_qs(url.query)
                if url.path == "/login":
                    return self._login(method, query)
                if url.path in ("/login/feishu", feishu_login.CALLBACK):
                    return self._feishu(method, url.path, query)
                bot = re.fullmatch(r"/t/([A-Za-z0-9_-]+)(/bot/(dingtalk|feishu|wecom|api)/[A-Za-z0-9_-]+)", url.path)
                if bot:
                    return self._bot(method, bot[1], bot[2], bot[3], url.query)
                if method == "POST":
                    self._origin()
                    if self.headers.get("X-TMH") != "1":
                        raise error(403, "缺少 X-TMH 请求头", "csrf_denied")
                if self.headers.get_all('Authorization'):
                    return self._tool(method, url)
                user = self._session()
                static = re.fullmatch(r"/t/([A-Za-z0-9_-]+)/static-preview/([1-9][0-9]*)/(.+)", url.path)
                # The index entry needs a personal login. Its readonly resource
                # grant works without ambient cookies inside the opaque preview.
                if static:
                    if method != 'GET':raise error(405, '静态预览仅支持读取', 'method_denied')
                    from .static_preview import response
                    return response(reg, static[1], int(static[2]), static[3], user,
                                    self._scheme()+'://'+self.headers.get('Host',''))
                if not user:
                    if method == "GET" and (url.path == "/" or re.fullmatch(r"/t/[A-Za-z0-9_-]+/?", url.path)):
                        return self._send(303, headers={"Location": "/login?next=" + quote(self.path, safe="")})
                    raise error(401, "请使用个人账号登录", "session_invalid")
                if url.path == "/logout":
                    return self._send(303, headers={"Location": "/login", "Set-Cookie": self._cookie("", 0)})
                if url.path == "/" and method == "GET":
                    with reg.authorization_guard():
                        if self._session() != user:
                            raise error(401, "登录已失效", "session_invalid")
                        return self._home(user)
                match = re.fullmatch(r"/t/([A-Za-z0-9_-]+)(/.*)?", url.path)
                if not match:
                    raise error(404, "请通过固定租户地址访问", "route_denied")
                tenant, path = match[1], match[2] or "/"
                if path == "/logout":
                    return self._send(303, headers={"Location": "/login", "Set-Cookie": self._cookie("", 0)})
                if path.startswith(("/bot/", "/hook/", "/capture/", "/pv/", "/v/", "/sign/", "/ask/")) or path == "/login":
                    raise error(403, "此入口尚未接入租户隔离", "route_denied")
                raw = self._body() if method == "POST" else b""
                body = json.loads(raw) if raw else {}
                if not isinstance(body, dict):
                    raise error(400, "请求必须是 JSON 对象", "invalid_request")
                if path == "/api/access" and method == "POST":
                    body.setdefault("tenant", tenant)
                initial = reg.context(user, tenant)
                local = path in ("/", "/index.html", "/api/access", "/tools", "/api/tool-connections") or path == "/api/meta" and (not initial["role"] or initial["tenant"]["status"] != "active")
                if not local:
                    if initial["tenant"]["status"] != "active" or not initial["role"]:
                        raise error(403, "当前租户未授权或已停用", "tenant_disabled" if initial["tenant"]["status"] != "active" else "membership_revoked")
                    workers.ensure(tenant)
                with reg.authorization_guard():
                    if self._session() != user:
                        raise error(401, "登录已失效", "session_invalid")
                    current = reg.context(user, tenant)
                    token = self.headers.get("X-Webuddy-Context", "")
                    if path.startswith("/api/") and path != "/api/meta" and token != current["context_token"]:
                        if not (path == "/api/access" and method == "POST" and tenancy.bound_receipt(reg, user, body, tenant, token)):
                            raise error(409, "成员身份或权限已变化，请重新读取", "context_changed")
                    if path in ("/", "/index.html"):
                        if method != "GET":
                            raise error(405, "此页面仅支持读取", "method_denied")
                        from .ui import page
                        return self._send(200, page().encode(), "text/html; charset=utf-8")
                    if path in ('/tools', '/api/tool-connections'):
                        from . import tool_access
                        if current['tenant']['status'] != 'active' or not current['role']:
                            raise error(403, '当前租户未授权或已停用', 'membership_revoked')
                        if self.headers.get('X-Webuddy-Agent') or self.headers.get('X-Webuddy-Operator'):
                            raise error(403, '请由本人在网页登录后管理工具连接', 'personal_session_required')
                        if path == '/tools':
                            if method != 'GET':
                                raise error(405, '此页面仅支持读取', 'method_denied')
                            from .ui_tool_access import page
                            return self._send(200, page().encode(), 'text/html; charset=utf-8')
                        visible = projects(reg, tenant)
                        grants = {g['project_id']: g['role'] for g in current['project_grants']}
                        visible = [dict(p, role='manager' if current['role'] == 'admin' else
                                        'viewer' if current['role'] == 'viewer' else grants[str(p['id'])])
                                   for p in visible if current['role'] == 'admin' or str(p['id']) in grants]
                        if method == 'GET':
                            return self._json(200, dict(tool_access.listing(reg, user, tenant),
                                                       projects=visible, context_token=current['context_token']))
                        if body.get('action') == 'create':
                            ids = body.get('project_ids')
                            if not isinstance(ids, list) or any(isinstance(i, bool) or not isinstance(i, int) or
                                    i not in {p['id'] for p in visible} for i in ids):
                                raise error(403, '只能授权当前可访问的项目', 'project_denied')
                            return self._json(200, tool_access.create(reg, user, tenant, body))
                        if body.get('action') == 'revoke':
                            return self._json(200, tool_access.revoke(reg, user, tenant, body))
                        raise error(400, '未知工具连接操作', 'invalid_request')
                    if path == "/api/access":
                        target = body.get("tenant", tenant) if method == "POST" else (query.get("tenant") or [tenant])[0]
                        if not isinstance(target, str):
                            raise error(400, "租户标识无效", "invalid_request")
                        if method == "GET":
                            data = reg.read(user, target)
                            data["projects"] = projects(reg, target)
                            return self._json(200, data)
                        if body.get("action") in ("project_grant", "project_revoke"):
                            reg.read(user, target)  # before disclosing target project existence
                            pid = body.get("project_id")
                            if isinstance(pid, bool) or not isinstance(pid, (str, int)) or not re.fullmatch(r"[1-9][0-9]*", str(pid)):
                                raise error(400, "请选择当前租户中的项目", "project_invalid")
                            if not any(p["id"] == int(pid) for p in projects(reg, target)):
                                raise error(404, "这个租户中不存在该项目", "project_not_found")
                        return self._json(200, reg.dispatch(user, dict(body, tenant=target), request_context={"tenant": tenant, "token": token}))
                    access = access_meta(reg, user, current)
                    if path == "/api/meta" and (not current["role"] or current["tenant"]["status"] != "active"):
                        return self._json(200, {"user": user, "login": True, "brand": brand, "access": access})
                    if current["tenant"]["status"] != "active" or not current["role"]:
                        raise error(403, "当前租户未授权或已停用", "membership_revoked")
                    forwarded = path + ("?" + url.query if url.query else "")
                    headers = dict(self.headers)
                    # The worker holds the authorization guard for the complete
                    # business operation, including when this gateway dies.
                    # Preserve this admitted version; never refresh it in transit.
                    headers = {k: v for k, v in headers.items() if k.lower() not in ("x-webuddy-context", "x-webuddy-tool")}
                    headers["X-Webuddy-Context"] = current["context_token"]
                    return PendingProxy(tenant, user, method, forwarded, raw, headers, access, path == "/api/meta")
            except ApiError as exc:
                return self._json(exc.code, {"error": str(exc), "code": getattr(exc, "reason", "access_denied")})
            except (ValueError, TypeError, UnicodeError):
                return self._json(400, {"error": "请求格式不正确", "code": "invalid_request"})
            except (OSError, sqlite3.Error):
                return self._json(503, {"error": "服务暂不可用，请稍后重试", "code": "service_unavailable"})

        def do_GET(self):
            self._handle("GET")

        def do_HEAD(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def _handle(self, method):
            response = self._dispatch(method)
            if isinstance(response, PendingProxy):
                request = response
                try:
                    status, headers, content = workers.request(request.tenant, request.actor, request.method, request.path,
                                                              body=request.body, headers=request.headers, require_live=True)
                    if request.meta and status == 200:
                        value = json.loads(content)
                        value.update(user=request.actor, login=True, access=request.access)
                        response = self._json(status, value)
                    else:
                        safe = {k: v for k, v in headers.items() if k.lower() in ("content-disposition", "content-encoding")}
                        response = self._send(status, content, headers.get("Content-Type", "application/octet-stream"), safe)
                except ApiError as exc:
                    response = self._json(exc.code, {"error": str(exc), "code": getattr(exc, "reason", "access_denied")})
                except (OSError, ValueError):
                    response = self._json(503, {"error": "租户服务暂不可用", "code": "worker_unavailable"})
            try:
                self._flush(*response)
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass  # The complete transaction/result remains retryable.

    return Handler


def serve(data_dir, host="127.0.0.1", port=8790):
    from .tenant_runtime import Workers
    reg = tenancy.Registry(data_dir)
    workers = None
    server = None
    saved_signals = {}
    try:
        workers = Workers(reg)
        if not reg.one("SELECT 1 FROM platform_owners"):
            raise ValueError("多租户模式需要先显式引导平台所有者")
        # Listening must mean the legacy data can initialize its private worker.
        # No user is impersonated and managed workers never resume background
        # execution on construction. New tenants remain demand-started.
        workers.ensure('default')
        server = ThreadingHTTPServer((host, port), make_handler(reg, workers))
        server.daemon_threads = True
        if threading.current_thread() is threading.main_thread():
            def stop(signum, frame):
                # shutdown waits for serve_forever: it must run off that thread.
                threading.Thread(target=server.shutdown, daemon=True).start()
            for signum in (signal.SIGTERM, signal.SIGINT):
                saved_signals[signum] = signal.signal(signum, stop)
        print("webuddy 租户入口：http://%s:%d" % (host, server.server_address[1]))
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for signum, handler in saved_signals.items():
            signal.signal(signum, handler)
        if server:
            server.server_close()
        if workers:
            workers.close()
        reg.close()
    return 0
