"""Account login for the platform: a sign-in page, accounts in <data>/users.json, signed session cookies.

Off until the first account exists (`tmh user add <名字>`); until then the token-only access stays as it was.
With accounts, the browser signs in at /login and gets a 7-day `tmh_session` cookie (HMAC-signed with
<data>/session.key, so restarts keep people signed in and deleting that file signs everyone out).
`X-TMH-Token` / `?token=` keep working for scripts. Passwords are stored as PBKDF2-SHA256 hashes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import threading
import time
from pathlib import Path

ITER = 240_000
SESSION_DAYS = 7
MAX_FAILS, FAIL_WINDOW = 5, 600  # per client: 5 wrong passwords in 10 minutes locks it for the rest of the window


def _users_file(data: Path) -> Path:
    return Path(data) / "users.json"


def _legacy_users(data: Path) -> dict:
    try:
        users = json.loads(_users_file(data).read_text(encoding="utf-8"))
        return users if isinstance(users, dict) else {}
    except (OSError, ValueError):
        return {}


def load_users(data: Path) -> dict:
    from .tenancy import account_users
    accounts = account_users(data)
    if accounts is not None:
        return accounts
    return {name: record for name, record in _legacy_users(data).items() if not record.get("disabled", False)}


def has_accounts(data: Path) -> bool:
    """Authentication stays enabled even when every account is disabled."""
    from .tenancy import has_accounts as registered
    present = registered(data)
    if present is not None:
        return present
    return bool(_legacy_users(data))


def _save_users(data: Path, users: dict) -> None:
    f = _users_file(data)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, ensure_ascii=False, indent=1), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, f)


def hash_password(pw: str, salt: str = "") -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), ITER)
    return "pbkdf2_sha256$%d$%s$%s" % (ITER, salt, dk.hex())


def _check(pw: str, stored: str) -> bool:
    try:
        algo, it, salt, want = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), int(it))
    except (ValueError, TypeError):
        return False
    return algo == "pbkdf2_sha256" and hmac.compare_digest(dk.hex(), want)


def set_user(data: Path, name: str, pw: str) -> None:
    name = name.strip()
    if not name or len(name) > 40 or any(c in name for c in " .:$/\\"):
        raise ValueError("用户名 1-40 个字符，不能有空格和 . : $ / \\")
    if len(pw) < 8:
        raise ValueError("密码至少 8 位")
    if (Path(data) / "control" / "access.db").exists():
        from .tenancy import local_set_user
        local_set_user(data, name, pw)
        return
    users = _legacy_users(data)
    users[name] = {"pw": hash_password(pw), "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save_users(data, users)


def del_user(data: Path, name: str) -> bool:
    if (Path(data) / "control" / "access.db").exists():
        from .tenancy import local_del_user
        return local_del_user(data, name)
    users = _legacy_users(data)
    if name not in users:
        return False
    del users[name]
    _save_users(data, users)
    return True


def verify(data: Path, name: str, pw: str) -> bool:
    u = load_users(data).get(name)
    if not u:
        _check(pw, hash_password("x"))  # same cost either way, so timing doesn't reveal which names exist
        return False
    return _check(pw, u.get("pw", ""))


def _key(data: Path) -> bytes:
    f = Path(data) / "session.key"
    try:
        return bytes.fromhex(f.read_text().strip())
    except (OSError, ValueError):
        k = secrets.token_bytes(32)
        fd = os.open(str(f), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(k.hex())
        return k


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_session(data: Path, name: str) -> str:
    account = load_users(data).get(name)
    if not account:
        raise ValueError("账号不存在或已停用")
    epoch = hashlib.sha256(json.dumps(account, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    body = "%s.%d.%s" % (_b64(name.encode("utf-8")), int(time.time()) + SESSION_DAYS * 86400, epoch)
    return body + "." + _b64(hmac.new(_key(data), body.encode(), hashlib.sha256).digest())


def read_session(data: Path, cookie: str) -> str:
    """The signed-in user's name, or "" when the cookie is missing, forged, expired or the account was removed."""
    try:
        n, exp, epoch, sig = cookie.split(".")
        body = n + "." + exp + "." + epoch
        good = _b64(hmac.new(_key(data), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good) or int(exp) < time.time():
            return ""
        name = base64.urlsafe_b64decode(n + "=" * (-len(n) % 4)).decode("utf-8")
    except (ValueError, TypeError):
        return ""
    account = load_users(data).get(name)
    current = hashlib.sha256(json.dumps(account, sort_keys=True, ensure_ascii=False).encode()).hexdigest() if account else ""
    return name if account and hmac.compare_digest(epoch, current) else ""


class Throttle:
    def __init__(self):
        self.fails: dict = {}
        self.lock = threading.Lock()

    def blocked(self, who: str) -> bool:
        with self.lock:
            now = time.time()
            ts = [t for t in self.fails.get(who, []) if now - t < FAIL_WINDOW]
            self.fails[who] = ts
            return len(ts) >= MAX_FAILS

    def fail(self, who: str) -> None:
        with self.lock:
            self.fails.setdefault(who, []).append(time.time())

    def ok(self, who: str) -> None:
        with self.lock:
            self.fails.pop(who, None)


LOGO = ('<svg width="44" height="44" viewBox="-13 -13 26 26" fill="none" stroke="#5CDBD3" stroke-width="2.2" stroke-linecap="round">'
        '<path d="M-9 4a10 10 0 1 1 18 0"/><path d="M0 2l5-6"/><circle r="1.6" cy="2" fill="#5CDBD3"/></svg>')

PAGE = r"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 · {brand}</title>
<style>
:root{--navy:#1D2939;--navy2:#26334A;--teal:#5CDBD3;--blue:#1677FF;--fg:#1F2733;--mut:#667085;--line:#D0D5DD;--bad:#E5484D;--bad-s:#FDECEC;color-scheme:light}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;font:14px/1.55 -apple-system,"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;color:var(--fg);background:#F2F4F7;display:flex}
.side{flex:1.1;background:radial-gradient(1200px 600px at 10% 110%,#13A3A333,transparent 60%),radial-gradient(900px 500px at 90% -10%,#1677FF40,transparent 60%),var(--navy);color:#fff;display:flex;flex-direction:column;justify-content:space-between;padding:48px 56px;position:relative;overflow:hidden}
.side::after{content:"";position:absolute;right:-160px;bottom:-160px;width:520px;height:520px;border:1px solid #ffffff14;border-radius:50%;box-shadow:0 0 0 70px #ffffff06,0 0 0 140px #ffffff04}
.mark{display:flex;align-items:center;gap:12px;font-size:22px;font-weight:700;letter-spacing:.5px}
.pitch h1{font-size:34px;line-height:1.3;margin:0 0 14px;font-weight:700;letter-spacing:.5px}
.pitch p{margin:0;color:#AEB7C4;font-size:15px;max-width:30em}
.pills{display:flex;gap:10px;flex-wrap:wrap;margin-top:26px}
.pills span{border:1px solid #ffffff24;background:#ffffff0d;border-radius:999px;padding:5px 14px;font-size:13px;color:#D6DCE5}
.foot{color:#7D8BA1;font-size:12px}
.main{flex:1;display:flex;align-items:center;justify-content:center;padding:32px 20px}
.card{width:100%;max-width:380px;background:#fff;border:1px solid #E4E7EC;border-radius:16px;padding:36px 32px 30px;box-shadow:0 12px 40px #1D293914}
.card h2{margin:0 0 4px;font-size:22px}
.card .sub{margin:0 0 26px;color:var(--mut)}
label{display:block;font-size:13px;color:#344054;font-weight:600;margin-bottom:6px}
.f{margin-bottom:18px}
input{width:100%;height:44px;border:1px solid var(--line);border-radius:10px;padding:0 14px;font:inherit;font-size:15px;color:var(--fg);background:#fff;transition:border-color .15s,box-shadow .15s}
input:focus{outline:none;border-color:var(--blue);box-shadow:0 0 0 4px #1677FF1f}
.pw{position:relative}.pw input{padding-right:58px}
.pw button{position:absolute;right:6px;top:6px;height:32px;border:0;background:none;color:var(--mut);font:inherit;font-size:13px;cursor:pointer;padding:0 10px;border-radius:8px}
.pw button:hover{background:#F2F4F7}
.go{width:100%;height:46px;border:0;border-radius:10px;background:var(--blue);color:#fff;font:inherit;font-size:16px;font-weight:600;cursor:pointer;margin-top:6px;transition:background .15s}
.go:hover{background:#0958D9}.go:disabled{opacity:.6;cursor:default}
.err{background:var(--bad-s);color:#B42318;border:1px solid #F9C6C6;border-radius:10px;padding:10px 14px;margin-bottom:18px;font-size:13px}
.hint{margin:22px 0 0;text-align:center;color:#98A2B3;font-size:12px}
.mmark{display:none}
@media (max-width:860px){body{display:block;background:var(--navy)}.side{display:none}.main{min-height:100%;padding:28px 16px}
.mmark{display:flex;justify-content:center;align-items:center;gap:10px;color:#fff;font-size:20px;font-weight:700;margin-bottom:22px}
.wrap{width:100%;max-width:380px}.card{padding:30px 22px 26px}}
</style></head>
<body>
<section class="side" aria-hidden="true">
  <div class="mark">{logo}<span>{brand}</span></div>
  <div class="pitch"><h1>让 AI 接住每一张工单<br>从需求到交付全程闭环</h1>
  <p>工单分析、方案确认、编码修改、测试验证，智能体与工程师在同一张工作台上协作，每一步都留痕可查。</p>
  <div class="pills"><span>运维服务</span><span>重构服务</span><span>业务全景</span><span>知识库</span></div></div>
  <div class="foot">© {year} {brand}</div>
</section>
<main class="main"><div class="wrap">
  <div class="mmark">{logo}<span>{brand}</span></div>
  <form class="card" method="post" action="/login" onsubmit="this.querySelector('.go').disabled=true">
    <h2>欢迎回来</h2><p class="sub">登录 {brand} 工作台</p>
    {err}
    <div class="f"><label for="u">账号</label><input id="u" name="username" autocomplete="username" value="{name}" required autofocus></div>
    <div class="f"><label for="p">密码</label><div class="pw"><input id="p" name="password" type="password" autocomplete="current-password" required>
      <button type="button" onclick="const i=document.getElementById('p');const s=i.type==='password';i.type=s?'text':'password';this.textContent=s?'隐藏':'显示'">显示</button></div></div>
    <input type="hidden" name="next" value="{next}">
    <button class="go" type="submit">登 录</button>
    <p class="hint">忘记密码请联系管理员重置</p>
  </form>
</div></main>
</body></html>"""


def page(brand: str, err: str = "", name: str = "", next_: str = "/") -> str:
    e = '<div class="err" role="alert">%s</div>' % html.escape(err) if err else ""
    b = html.escape(brand)
    return (PAGE.replace("{logo}", LOGO).replace("{brand}", b).replace("{err}", e).replace("{year}", time.strftime("%Y"))
            .replace("{name}", html.escape(name)).replace("{next}", html.escape(safe_next(next_))))


def safe_next(n: str) -> str:
    """Only same-site paths, so the login page can't be used to bounce people elsewhere."""
    return n if n.startswith("/") and not n.startswith("//") and "\\" not in n else "/"
