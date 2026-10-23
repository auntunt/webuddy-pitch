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
from pathlib import Path
import re
import signal
import sqlite3
import threading
from urllib.parse import parse_qs, quote, urlsplit

from . import login, tenancy
from .errors import ApiError


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
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code, value):
            return self._send(code, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _session(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                value = cookie["tmh_session"].value if "tmh_session" in cookie else ""
                return login.read_session(reg.data_dir, value)
            except (ValueError, TypeError, CookieError):
                return ""

        def _cookie(self, value, age):
            secure = "; Secure" if self._scheme() == "https" else ""
            return "tmh_session=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax%s" % (value, age, secure)

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
                return self._send(200, login.page(brand, next_=nxt).encode(), "text/html; charset=utf-8")
            self._origin()
            fields = parse_qs(self._body(8192).decode("utf-8"))
            name = (fields.get("username") or [""])[0].strip()
            password = (fields.get("password") or [""])[0]
            nxt = login.safe_next((fields.get("next") or ["/"])[0])
            client = self.client_address[0]
            if client in ("127.0.0.1", "::1") and self.headers.get("X-Forwarded-For"):
                client = self.headers["X-Forwarded-For"].split(",")[-1].strip()
            if throttle.blocked(client):
                return self._send(429, login.page(brand, "密码错误次数太多，请稍后重试", name, nxt).encode(), "text/html; charset=utf-8")
            with reg.authorization_guard():
                if not login.verify(reg.data_dir, name, password):
                    throttle.fail(client)
                    return self._send(401, login.page(brand, "账号或密码不正确", name, nxt).encode(), "text/html; charset=utf-8")
                cookie = login.make_session(reg.data_dir, name)
            throttle.ok(client)
            return self._send(303, headers={"Location": nxt, "Set-Cookie": self._cookie(cookie, login.SESSION_DAYS * 86400)})

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

        def _dispatch(self, method):
            try:
                url = urlsplit(self.path)
                if not self.path.startswith("/") or url.netloc or "\\" in url.path or any("%" in part for part in url.path.split("/", 3)[:3]):
                    raise error(400, "请求路径无效", "invalid_request")
                query = parse_qs(url.query)
                if url.path == "/login":
                    return self._login(method, query)
                if method == "POST":
                    self._origin()
                    if self.headers.get("X-TMH") != "1":
                        raise error(403, "缺少 X-TMH 请求头", "csrf_denied")
                user = self._session()
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
                local = path in ("/", "/index.html", "/api/access") or path == "/api/meta" and (not initial["role"] or initial["tenant"]["status"] != "active")
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
                    headers = {k: v for k, v in headers.items() if k.lower() != "x-webuddy-context"}
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
