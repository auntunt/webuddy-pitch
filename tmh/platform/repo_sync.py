"""The project's code on the team's own GitHub repository: what the platform commits also goes there.

Without this, candidate branches, versions and rollbacks live only in the checkout on the platform's machine. Bound
to a repository, the platform pushes each unattended change's branch (tmh/<ticket>-r<run>), the delivery line after
a merge or a rollback, and the version tag, so every change can be read, compared and checked out on GitHub.

Access is one SSH deploy key per project, made here (<data>/keys/<KEY>-deploy, owner-only): the private half never
leaves this machine; a person adds the public half to the repository with write access. github.com's published host
key is pinned, so the push cannot be talked to by anyone else. Pushes are plain fast-forwards (no force, no deletes):
the platform only ever adds to the line (a rollback is a revert commit). A push that fails leaves the local result as
it is and is said on the ticket; nothing waits on it.

Settings in autoflow.json "repos": {"JB": {"url", "host", "owner", "repo", "on", "checked", "by", "ts"}}.

Besides GitHub, a team's own machine can hold the repository: ssh://user@host[:port]/path/repo.git (kind "ssh").
Its host key is read once when the project is bound (or given) and pinned from then on ("hostkey"); there are no
web pages to link to, and the deploy key goes into that account's authorized_keys, limited to git-shell.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

REMOTE = "webuddy"
PUSH_S = 120
# https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints
HOSTS = {"github.com": "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"}
_NAME = r"[A-Za-z0-9_.-]+"
_SSH = re.compile(r"ssh://([a-z_][a-z0-9_-]*)@([A-Za-z0-9.-]+)(?::(\d{1,5}))?(/[A-Za-z0-9_./-]+?)(?:\.git)?/?")
_HOSTKEY = re.compile(r"(\S+) (ssh-ed25519|ecdsa-sha2-nistp256|ssh-rsa) ([A-Za-z0-9+/=]+)")


def parse(url: str) -> dict:
    """{"host", "owner", "repo"} from git@github.com:o/r.git, https://github.com/o/r, ssh://git@github.com/o/r or o/r."""
    u = (url or "").strip()
    s = _SSH.fullmatch(u)
    if s and s.group(2).lower() != "github.com":
        if ".." in s.group(4) or (s.group(3) and not 0 < int(s.group(3)) < 65536):
            raise ValueError("仓库路径不合法")
        return {"kind": "ssh", "host": s.group(2).lower(), "port": int(s.group(3) or 22), "user": s.group(1),
                "path": s.group(4) + ".git", "owner": s.group(1), "repo": s.group(4).rsplit("/", 1)[-1]}
    m = (re.fullmatch(r"git@([\w.-]+):(%s)/(%s?)(?:\.git)?/?" % (_NAME, _NAME), u) or
         re.fullmatch(r"(?:ssh://git@|https://)([\w.-]+)/(%s)/(%s?)(?:\.git)?/?" % (_NAME, _NAME), u) or
         re.fullmatch(r"()(%s)/(%s?)(?:\.git)?" % (_NAME, _NAME), u))
    if not m or not m.group(3):
        raise ValueError("仓库地址要像 git@github.com:团队/仓库.git、https://github.com/团队/仓库，"
                         "或自己机器上的 ssh://用户@主机:端口/路径/仓库.git（不要带密码或令牌）")
    host = (m.group(1) or "github.com").lower()
    if host not in HOSTS:
        raise ValueError("https 地址目前只支持 GitHub（github.com）；自己的机器请用 ssh://用户@%s/路径/仓库.git" % host)
    return {"host": host, "owner": m.group(2), "repo": m.group(3)}


def ssh_url(c: dict) -> str:
    if c.get("kind") == "ssh":
        return "ssh://%s@%s%s%s" % (c["user"], c["host"], "" if c["port"] == 22 else ":%d" % c["port"], c["path"])
    return "git@%s:%s/%s.git" % (c["host"], c["owner"], c["repo"])


def name(c: dict) -> str:
    return c.get("label") or ("%s:%s" % (c["host"], c["path"]) if c.get("kind") == "ssh" else "%s/%s" % (c["owner"], c["repo"]))


def web(c: dict, kind: str = "", ref: str = "") -> str:
    if c.get("kind") == "ssh":
        return ""
    base = "https://%s/%s/%s" % (c["host"], c["owner"], c["repo"])
    return base + {"": "", "branch": "/tree/", "commit": "/commit/", "tag": "/releases/tag/"}[kind] + ref


def _all(data_dir: Path) -> dict:
    try:
        v = json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("repos")
    except (OSError, ValueError, AttributeError):
        v = None
    return v if isinstance(v, dict) else {}


def conf(data_dir: Path, key: str) -> dict:
    c = _all(data_dir).get(key)
    if not isinstance(c, dict):
        return {}
    ok = _HOSTKEY.fullmatch(c.get("hostkey") or "") if c.get("kind") == "ssh" else c.get("host") in HOSTS
    return c if ok else {}


def _put(data_dir: Path, key: str, c: dict | None) -> None:
    from .util_conf import update_autoflow
    repos = {k: v for k, v in _all(data_dir).items() if k != key}
    if c:
        repos[key] = c
    update_autoflow(data_dir, {"repos": repos})


def key_file(data_dir: Path, key: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key or ""):
        raise ValueError("项目代号不合法")
    return Path(data_dir) / "keys" / ("%s-deploy" % key)


def public_key(data_dir: Path, key: str) -> str:
    f = key_file(data_dir, key).with_suffix(".pub")
    return f.read_text(encoding="utf-8").strip() if f.exists() else ""


def _keygen(data_dir: Path, key: str) -> None:
    f = key_file(data_dir, key)
    if f.exists():
        return
    f.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(f.parent, 0o700)
    r = subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "webuddy-%s" % key, "-f", str(f)],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise ValueError("生成部署密钥没做成：%s" % (r.stderr or r.stdout).strip()[:200])
    os.chmod(f, 0o600)


def _hostkey(c: dict, given: str = "") -> str:
    """The host's key as a known_hosts line: as given, or read once from the host (ed25519 preferred)."""
    want = "[%s]:%d" % (c["host"], c["port"]) if c["port"] != 22 else c["host"]
    lines = [given.strip()] if given.strip() else []
    if not lines:
        try:
            r = subprocess.run(["ssh-keyscan", "-T", "10", "-p", str(c["port"]), "-t", "ed25519,ecdsa,rsa", c["host"]],
                               capture_output=True, text=True, timeout=30)
            lines = [x for x in r.stdout.splitlines() if x and not x.startswith("#")]
        except (OSError, subprocess.TimeoutExpired):
            lines = []
    for kind in ("ssh-ed25519", "ecdsa-sha2-nistp256", "ssh-rsa"):
        for x in lines:
            m = _HOSTKEY.fullmatch(x.strip())
            if m and m.group(2) == kind:
                return "%s %s %s" % (want, kind, m.group(3))
    raise ValueError("读不到 %s 的主机密钥（机器开着吗？端口对吗？）" % want)


def fingerprint(line: str) -> str:
    try:
        r = subprocess.run(["ssh-keygen", "-lf", "-"], input=line + "\n", capture_output=True, text=True, timeout=10)
        return r.stdout.split()[1] if r.returncode == 0 and r.stdout.split()[1:] else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _env(data_dir: Path, key: str, c: dict) -> dict:
    kh = Path(data_dir) / "keys" / ("%s-known_hosts" % key_file(data_dir, key).name[:-len("-deploy")])
    kh.parent.mkdir(parents=True, exist_ok=True)
    pin = c["hostkey"] if c.get("kind") == "ssh" else HOSTS[c["host"]]
    if not kh.exists() or kh.read_text(encoding="utf-8").strip() != pin:
        kh.write_text(pin + "\n", encoding="utf-8")
    ssh = "ssh -i %s -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=%s" % (
        _q(key_file(data_dir, key)), _q(kh))
    return dict(os.environ, GIT_SSH_COMMAND=ssh, GIT_TERMINAL_PROMPT="0")


def _q(p: Path) -> str:
    s = str(p)
    return s if re.fullmatch(r"[\w./-]+", s) else "'%s'" % s.replace("'", "'\\''")


def _git(root: Path, env: dict, *args, timeout: int = PUSH_S) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "超过 %d 秒没有完成" % timeout)


def _said(r: subprocess.CompletedProcess) -> str:
    text = re.sub(r"https?://[^@\s/]+@", "https://", (r.stderr or r.stdout or "").strip())  # never echo a credential
    return text.splitlines()[-1][:300] if text else "git 退出码 %d" % r.returncode


def setup(P, p: dict, url: str, by: str, hostkey: str = "", label: str = "") -> dict:
    """Bind the project to a repository: a deploy key (made once), the remote `webuddy`, pushing off until checked.
    For a team's own machine the host key is pinned here: `hostkey` as given, or read from the host now."""
    c = parse(url)
    if c.get("kind") == "ssh":
        c["hostkey"] = _hostkey(c, hostkey)
        if label.strip():
            c["label"] = label.strip()[:60]
    root = Path(p["root"])
    if not (root / ".git").exists() and _git(root, None, "rev-parse", "--git-dir", timeout=10).returncode != 0:
        raise ValueError("项目目录不是 git 仓库")
    _keygen(P.data_dir, p["key"])
    has = _git(root, None, "remote", "get-url", REMOTE, timeout=10).returncode == 0
    r = _git(root, None, "remote", "set-url" if has else "add", REMOTE, ssh_url(c), timeout=10)
    if r.returncode != 0:
        raise ValueError("设置远程仓库没做成：%s" % _said(r))
    _put(P.data_dir, p["key"], dict(c, url=ssh_url(c), on=False, checked="", by=by, ts=time.strftime("%Y-%m-%d %H:%M:%S")))
    return view(P, p)


def check(P, p: dict) -> dict:
    """Can the platform reach the repository with its deploy key? Pushing can be turned on only after this passed."""
    c = conf(P.data_dir, p["key"])
    if not c:
        raise ValueError("这个项目还没绑定代码仓库")
    r = _git(Path(p["root"]), _env(P.data_dir, p["key"], c), "ls-remote", "--heads", REMOTE, timeout=30)
    c = dict(c, checked="ok" if r.returncode == 0 else _said(r), checked_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    if r.returncode != 0:
        c["on"] = False
    _put(P.data_dir, p["key"], c)
    return view(P, p)


def switch(P, p: dict, on: bool, by: str) -> dict:
    c = conf(P.data_dir, p["key"])
    if not c:
        raise ValueError("这个项目还没绑定代码仓库")
    if on and c.get("checked") != "ok":
        raise ValueError("先“测试连接”通过（部署密钥要加到仓库并允许写入），再打开推送")
    _put(P.data_dir, p["key"], dict(c, on=bool(on), by=by, ts=time.strftime("%Y-%m-%d %H:%M:%S")))
    return view(P, p)


def unbind(P, p: dict, by: str) -> dict:
    _git(Path(p["root"]), None, "remote", "remove", REMOTE, timeout=10)
    _put(P.data_dir, p["key"], None)
    return view(P, p)


def view(P, p: dict) -> dict:
    c = conf(P.data_dir, p["key"])
    if not c:
        return {"bound": False}
    own = c.get("kind") == "ssh"
    return {"bound": True, "kind": c.get("kind") or "github", "url": c["url"], "web": web(c), "name": name(c), "on": bool(c.get("on")),
            "checked": c.get("checked") or "", "checked_at": c.get("checked_at") or "", "by": c.get("by") or "",
            "ts": c.get("ts") or "", "deploy_key": public_key(P.data_dir, p["key"]),
            "deploy_keys_page": "" if own else web(c) + "/settings/keys/new",
            "hostkey": fingerprint(c["hostkey"]) if own else ""}


def push(P, p: dict, refs: list) -> dict:
    """Push branches and tags (names, not expressions) to the bound repository. {"state": "off"|"pushed"|"failed"}."""
    c = conf(P.data_dir, p["key"])
    if not c or not c.get("on"):
        return {"state": "off"}
    root = Path(p["root"])
    spec, links = [], []
    for ref in dict.fromkeys(x for x in refs if x):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", ref) or ".." in ref:
            continue
        full = ref if ref.startswith("refs/") else "refs/heads/" + ref
        if _git(root, None, "show-ref", "--verify", "--quiet", full, timeout=10).returncode != 0:
            full = "refs/tags/" + ref
            if _git(root, None, "show-ref", "--verify", "--quiet", full, timeout=10).returncode != 0:
                continue
        spec.append("%s:%s" % (full, full))
        links.append(web(c, "tag" if full.startswith("refs/tags/") else "branch", full.split("/", 2)[2]))
    links = [x for x in links if x]
    if not spec:
        return {"state": "off", "why": "没有要推送的分支或标签"}
    r = _git(root, _env(P.data_dir, p["key"], c), "push", "--porcelain", REMOTE, *spec)
    if r.returncode != 0:
        return {"state": "failed", "why": _said(r), "repo": name(c), "refs": spec}
    return {"state": "pushed", "repo": name(c), "refs": [s.split(":")[0] for s in spec], "links": links}
