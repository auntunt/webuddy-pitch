"""飞书登录: sign in with the company's 飞书 account instead of a password.

Uses the same 企业自建应用 as the bot (TMH_FEISHU_APP_ID / TMH_FEISHU_APP_SECRET) and the
standard OAuth authorization-code flow with state and PKCE. A 飞书 identity only signs in to a
Webuddy account it was bound to; binding happens once, when the person finishes the 飞书 step
and then signs in with that account's password. 飞书 never creates accounts or grants access.
Inside the 飞书 client the authorization is silent, so links in bot cards open straight in.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import login

AUTHORIZE = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
OPEN_API = "https://open.feishu.cn"
CALLBACK = "/login/feishu/callback"
FLOW_COOKIE, BIND_COOKIE = "tmh_feishu", "tmh_feishu_bind"
FLOW_SECONDS, BIND_SECONDS = 600, 600


class FeishuLoginError(Exception):
    pass


def app() -> tuple[str, str]:
    return os.environ.get("TMH_FEISHU_APP_ID", ""), os.environ.get("TMH_FEISHU_APP_SECRET", "")


def enabled() -> bool:
    return all(app())


def _sign(data, value: dict) -> str:
    body = login._b64(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode())
    return body + "." + login._b64(hmac.new(login._key(data), b"feishu-login." + body.encode(), hashlib.sha256).digest())


def _unsign(data, token: str) -> dict:
    try:
        body, sig = token.split(".")
        good = login._b64(hmac.new(login._key(data), b"feishu-login." + body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return {}
        value = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (ValueError, TypeError, AttributeError):
        return {}
    return value if isinstance(value, dict) and value.get("exp", 0) > time.time() else {}


def redirect_uri(base: str) -> str:
    return base.rstrip("/") + CALLBACK


def start(data, base: str, next_: str) -> tuple[str, str]:
    """(authorize URL, signed flow cookie value)."""
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    challenge = login._b64(hashlib.sha256(verifier.encode()).digest())
    query = urllib.parse.urlencode({"client_id": app()[0], "response_type": "code", "redirect_uri": redirect_uri(base),
                                    "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})
    flow = {"s": state, "v": verifier, "n": login.safe_next(next_), "exp": int(time.time()) + FLOW_SECONDS}
    return AUTHORIZE + "?" + query, _sign(data, flow)


def _call(url: str, body: dict | None = None, token: str = "") -> dict:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8") or "{}") or {"code": e.code}
        except ValueError:
            return {"code": e.code}
    except (OSError, ValueError) as e:
        raise FeishuLoginError("连不上飞书：%s" % type(e).__name__) from None


def identity(data, base: str, flow_cookie: str, code: str, state: str) -> tuple[dict, str]:
    """Exchange the callback's code for the person's 飞书 identity; returns (identity, next)."""
    flow = _unsign(data, flow_cookie)
    if not flow or not state or not hmac.compare_digest(flow.get("s", ""), state):
        raise FeishuLoginError("飞书登录已过期，请重新点「飞书登录」")
    if not code:
        raise FeishuLoginError("飞书没有给出授权，请重试")
    app_id, secret = app()
    tok = _call(OPEN_API + "/open-apis/authen/v2/oauth/token",
                {"grant_type": "authorization_code", "client_id": app_id, "client_secret": secret, "code": code,
                 "redirect_uri": redirect_uri(base), "code_verifier": flow["v"]})
    if tok.get("code") or not tok.get("access_token"):
        raise FeishuLoginError("飞书授权没有通过（%s）" % (tok.get("code") or tok.get("error") or "无令牌"))
    info = _call(OPEN_API + "/open-apis/authen/v1/user_info", token=tok["access_token"])
    u = info.get("data") or {}
    if info.get("code") or not u.get("open_id"):
        raise FeishuLoginError("读不到飞书账号信息（%s）" % (info.get("code") or "无 open_id"))
    return {"app_id": app_id, "open_id": u["open_id"], "tenant_key": u.get("tenant_key") or "",
            "name": (u.get("name") or "")[:60]}, flow["n"]


def bound_user(reg, ident: dict) -> str:
    """The active Webuddy account this 飞书 identity is bound to, or ""."""
    allowed = os.environ.get("TMH_FEISHU_TENANT_KEY", "")
    if allowed and ident.get("tenant_key") != allowed:
        return ""
    row = reg.one("SELECT f.user,f.tenant_key FROM feishu_identities f JOIN accounts a ON a.name=f.user "
                  "WHERE f.app_id=? AND f.open_id=? AND a.active=1", (ident["app_id"], ident["open_id"]))
    return row["user"] if row and row["tenant_key"] == ident.get("tenant_key", "") else ""


def pending(data, ident: dict) -> str:
    return _sign(data, dict(ident, exp=int(time.time()) + BIND_SECONDS))


def read_pending(data, token: str) -> dict:
    v = _unsign(data, token)
    return v if v.get("open_id") and v.get("app_id") else {}


def bind(reg, user: str, ident: dict) -> None:
    """Bind after the person proved the account with its password; rebinding moves the identity."""
    from .tenancy import encoded, now
    with reg.transaction() as db:
        db.execute("INSERT INTO feishu_identities VALUES(?,?,?,?,?,?) ON CONFLICT(app_id,open_id) DO UPDATE SET "
                   "tenant_key=excluded.tenant_key,user=excluded.user,name=excluded.name,created=excluded.created",
                   (ident["app_id"], ident["open_id"], ident.get("tenant_key", ""), user, ident.get("name", ""), now()))
        rev = db.execute("SELECT revision FROM access_meta").fetchone()[0]
        db.execute("INSERT INTO access_audit(actor,action,tenant_id,payload,revision,created) VALUES(?,?,?,?,?,?)",
                   (user, "feishu_bind", "", encoded({"user": user, "feishu": ident.get("name", "")}), rev, now()))
