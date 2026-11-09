"""Preview proxy: /pv/<ticket>/... on the main or the separate preview address."""
from __future__ import annotations

import http.client
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from ..errors import ApiError
from ..app import Platform
from .util import _cookie, _length


def _pvkey(s: str) -> str:
    """OA-12 for a ticket's preview, OA-main for the main line's standing one: one spelling each."""
    k, n = s.rsplit("-", 1)
    return k.upper() + "-" + n.lower()


def serve_preview(h, P, method: str, u, sandboxed: bool) -> None:
    """Answer one request for /pv/<ticket>/... on whichever address serves previews: a pass in the query (/__open)
    becomes a cookie for that one preview; anything else needs that cookie and is passed to the running app."""
    from .. import preview
    m = re.match(r"^/pv/([A-Za-z0-9]+-(?:\d+|[Mm][Aa][Ii][Nn]))(/.*)?$", u.path)
    if not m:
        return h._send(404, "这里只有预览版本".encode("utf-8"), "text/plain; charset=utf-8")
    key, rest = _pvkey(m.group(1)), m.group(2) or ""
    if m.group(1) != key or not rest:  # cookies are kept by exact path: one spelling only
        return h._send(308, b"", "text/plain", {"Location": "/pv/%s%s" % (key, rest or "/") + ("?" + u.query if u.query else "")})
    try:
        prefix, rest, expected = preview.route(key, rest)
        preview.require_bound(P.data_dir, key, expected)
    except ApiError as e:
        return h._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
    if not rest:
        return h._send(308, b"", "text/plain", {"Location": prefix + "/" + ("?" + u.query if u.query else "")})
    https = (h.headers.get("X-Forwarded-Proto") or "") == "https" or (h.headers.get("Host") or "").split(":")[0] in ("127.0.0.1", "localhost")
    opening = rest == "/__open"
    g = ((parse_qs(u.query).get("g") or [""])[0] if opening else
         _cookie(h.headers.get("Cookie", ""), preview.cookie_name(key, expected)))
    if not preview.granted(P.data_dir, key, g, expected_commit=expected):
        msg = "这个预览入口已经失效：回到工单页或签收链接重新打开" if opening else "请从 webuddy 的工单页或签收链接打开预览"
        return h._send(403 if opening else 401, msg.encode("utf-8"), "text/plain; charset=utf-8")
    if not expected and (opening or (rest == "/" and method in ("GET", "HEAD"))):
        # Legacy entries still open the current preview, even with a pre-existing
        # cookie. Preserve expiry and sign-off restrictions when pinning the entry.
        st = preview.status(P.data_dir, key)
        commit = st.get("commit_full") or ""
        if commit and preview.bound_matches(st, key, commit):
            exp, lh = g.split(".")[:2]
            pin = preview.grant(P.data_dir, key, lh, int(exp), expected_commit=commit)
            return h._send(303, b"", "text/plain", {"Location": preview.bound_prefix(key, commit) + "/__open?g=" + pin,
                                                   "Referrer-Policy": "no-referrer"})
    if opening:
        # sandboxed pages are an origin of their own, so their requests count as cross-site: the pass must go with them
        same = "SameSite=None; Secure" if sandboxed and https else "SameSite=Lax" + ("; Secure" if https else "")
        return h._send(303, b"", "text/plain", {"Location": prefix + "/", "Referrer-Policy": "no-referrer",
                                               "Set-Cookie": "%s=%s; Path=%s/; HttpOnly; %s" % (preview.cookie_name(key, expected), g, prefix, same)})
    if key.endswith(preview.STANDING):  # the main line's preview is in use: it keeps following new versions
        from .. import workbench
        workbench.touch(P.data_dir, key)
    n = _length(h)
    if n < 0:
        return h._send(400, b"bad length", "text/plain")
    if n > 20 * 1024 * 1024:
        return h._send(413, b"too large", "text/plain")
    body = h.rfile.read(n) if n else b""
    query = "&".join(x for x in u.query.split("&") if x and not x.startswith("token=")) if u.query else ""
    path = prefix + rest + ("?" + query if query else "")
    try:
        code, hdrs, resp, length = preview.forward(P.data_dir, key, method, path, h.headers, body, sandboxed, https, expected_commit=expected)
    except ApiError as e:
        return h._send(e.code, str(e).encode("utf-8"), "text/plain; charset=utf-8")
    except LookupError as e:
        st = preview.status(P.data_dir, key)
        msg = {"starting": "预览版本正在启动，稍等一会儿刷新这个页面", "failed": "预览没有起来：%s" % st.get("why", "")}.get(st.get("state"), str(e))
        return h._send(503, msg.encode("utf-8"), "text/plain; charset=utf-8", {"Retry-After": "10"})
    except (OSError, http.client.HTTPException) as e:
        return h._send(502, ("预览版本没有响应：%s" % e).encode("utf-8"), "text/plain; charset=utf-8")
    try:
        h.send_response(code)
        for k, v in hdrs:
            h.send_header(k, v)
        if method == "HEAD" or code in (204, 304):
            h.end_headers()
            return
        if length is not None:
            h.send_header("Content-Length", str(length))
        else:  # unknown length (a stream): it ends when the connection closes
            h.send_header("Connection", "close")
            h.close_connection = True
        h.end_headers()
        while True:
            chunk = resp.read1(64 * 1024) if hasattr(resp, "read1") else resp.read(64 * 1024)
            if not chunk:
                break
            h.wfile.write(chunk)
            h.wfile.flush()
    except (OSError, http.client.HTTPException):
        h.close_connection = True
    finally:
        resp.close()


def make_preview_handler(P: Platform):
    """The address of its own for previews (serve --preview-port): nothing of the platform is reachable here."""
    class PV(BaseHTTPRequestHandler):
        server_version = "webuddy-preview"

        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _go(self):
            serve_preview(self, P, self.command, urlparse(self.path), sandboxed=False)
        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _go
    return PV
