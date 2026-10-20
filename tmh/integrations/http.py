"""Small stdlib HTTP client shared by all adapters.

- auth from environment variables only: basic / bearer / header / query / none
- per-instance timeout, retries with backoff on 429/5xx and network errors
- proxy: system default, an explicit URL, or "none"; loopback hosts never use a proxy
- TLS: verify by default; `cafile` for an internal CA; `verify: false` only if asked
- dry run: non-GET requests are recorded in `planned` and not sent
"""
from __future__ import annotations

import base64
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from .base import IntegrationError, env_value

RETRY_STATUS = {429, 502, 503, 504}
SECRET_PARAM = re.compile(r"(?i)([?&](?:access_token|private_token|token|key|secret|sign|password|apikey|api_key)=)[^&#]+")


def redact(url: str) -> str:
    """Hide credential-looking query values (webhook access_token, sign …) in anything printed or logged."""
    return SECRET_PARAM.sub(r"\1***", url)
LOOPBACK = {"localhost", "127.0.0.1", "::1"}


class Response:
    def __init__(self, status: int, headers: dict, body: bytes):
        self.status = status
        self.headers = headers
        self.body = body

    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self):
        if not self.body:
            return None
        try:
            return json.loads(self.text())
        except ValueError:
            raise IntegrationError("返回的不是 JSON（HTTP %d）：%s" % (self.status, self.text()[:200]))


class HttpClient:
    def __init__(self, base: str, conf: dict, dry_run: bool = True):
        self.base = (base or "").rstrip("/")
        self.conf = conf
        self.auth = conf.get("auth") or {"type": "none"}
        self.timeout = float(conf.get("timeout", 20))
        self.retries = int(conf.get("retries", 2))
        self.dry_run = dry_run
        self.planned: list = []
        self.extra_headers: dict = dict(conf.get("headers") or {})  # non-secret headers only
        self._opener = None

    # -- plumbing ------------------------------------------------------------
    def _ssl(self):
        if self.conf.get("verify", True) is False:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return ssl.create_default_context(cafile=self.conf.get("cafile") or None)

    def opener(self, host: str):
        proxy = self.conf.get("proxy", "")
        if host in LOOPBACK or proxy == "none":
            ph = urllib.request.ProxyHandler({})
        elif proxy:
            ph = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        else:
            ph = urllib.request.ProxyHandler()
        return urllib.request.build_opener(ph, urllib.request.HTTPSHandler(context=self._ssl()))

    def auth_headers(self) -> tuple[dict, dict]:
        """(headers, query params) for the configured auth. Reads secrets from env at call time."""
        a = self.auth
        t = (a.get("type") or "none").lower()
        if t == "none":
            return {}, {}
        if t == "basic":
            user = a.get("user") or (env_value(a["user_env"], "用户名") if a.get("user_env") else "")
            pw = env_value(a["password_env"], "密码/API token") if a.get("password_env") else ""
            if not user and not pw:
                raise IntegrationError("basic 认证需要 user/user_env 和 password_env")
            tok = base64.b64encode(("%s:%s" % (user, pw)).encode()).decode()
            return {"Authorization": "Basic " + tok}, {}
        if t == "bearer":
            return {"Authorization": "Bearer " + env_value(a.get("token_env", ""), "token")}, {}
        if t == "header":
            return {a.get("name", "PRIVATE-TOKEN"): env_value(a.get("token_env", ""), "token")}, {}
        if t == "query":
            return {}, {a.get("param", "token"): env_value(a.get("token_env", ""), "token")}
        raise IntegrationError("不认识的认证方式 %s（可选 none/basic/bearer/header/query）" % t)

    def full_url(self, path: str, params: dict | None = None) -> str:
        url = path if path.startswith(("http://", "https://")) else self.base + "/" + path.lstrip("/")
        if params:
            q = urllib.parse.urlencode([(k, v) for k, v in params.items() if v not in (None, "")], doseq=True)
            if q:
                url += ("&" if "?" in url else "?") + q
        return url

    # -- requests ------------------------------------------------------------
    def request(self, method: str, path: str, params: dict | None = None, json_body=None, data: bytes | None = None,
                headers: dict | None = None, auth: bool = True, ok=(200, 201, 202, 204), read_only: bool = False) -> Response | None:
        """read_only=True marks a non-GET call that changes nothing (login, search by POST); it runs even in dry run."""
        method = method.upper()
        h = {"Accept": "application/json", "User-Agent": "tmh"}
        h.update(self.extra_headers)
        q = dict(params or {})
        if auth:
            ah, aq = self.auth_headers()
            h.update(ah)
            q.update(aq)
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            h["Content-Type"] = "application/json; charset=utf-8"
        h.update(headers or {})
        url = self.full_url(path, q)
        if method != "GET" and self.dry_run and not read_only:
            shown = self.full_url(path, params)  # never show query-string credentials
            self.planned.append({"method": method, "url": redact(shown), "body": json_body if json_body is not None else (data or b"").decode("utf-8", "replace")[:500]})
            return None
        host = urllib.parse.urlsplit(url).hostname or ""
        opener = self.opener(host)
        last = None
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, data=data, headers=h, method=method)
            try:
                with opener.open(req, timeout=self.timeout) as r:
                    return Response(r.status, dict(r.headers), r.read())
            except urllib.error.HTTPError as e:
                body = e.read() if hasattr(e, "read") else b""
                if e.code in RETRY_STATUS and attempt < self.retries:
                    time.sleep(min(8, 0.5 * 2 ** attempt))
                    continue
                if e.code in ok:
                    return Response(e.code, dict(e.headers or {}), body)
                raise IntegrationError(_explain(e.code, method, self.full_url(path, params), body))
            except (urllib.error.URLError, OSError) as e:
                last = e
                if attempt < self.retries:
                    time.sleep(min(8, 0.5 * 2 ** attempt))
                    continue
        raise IntegrationError("连不上 %s：%s（检查 url、网络、代理 proxy、内网证书 cafile）" % (redact(self.base or url), getattr(last, "reason", last)))

    def get(self, path: str, params: dict | None = None, **kw):
        r = self.request("GET", path, params, **kw)
        return r.json() if r is not None else None

    def get_text(self, path: str, params: dict | None = None, **kw) -> str:
        r = self.request("GET", path, params, **kw)
        return r.text() if r is not None else ""

    def post(self, path: str, json_body=None, params: dict | None = None, **kw):
        r = self.request("POST", path, params, json_body=json_body, **kw)
        if r is None:
            return {"dry_run": True}
        return r.json() if r.body else {"status": r.status}


def _explain(code: int, method: str, url: str, body: bytes) -> str:
    hint = {
        400: "请求参数不对",
        401: "认证失败：检查环境变量里的账号/token 是否正确、是否过期",
        403: "没有权限：token 对应的账号缺少这个项目/操作的权限（或需要 CSRF crumb）",
        404: "地址或对象不存在：检查 url、项目 key、job 名、工单号",
        405: "接口不支持这个方法（可能是工具版本太老）",
        429: "被限流，稍后再试",
    }.get(code, "")
    snippet = body.decode("utf-8", "replace")[:300].replace("\n", " ") if body else ""
    return "HTTP %d %s %s%s%s" % (code, method, redact(url), "：" + hint if hint else "", "｜" + snippet if snippet else "")
