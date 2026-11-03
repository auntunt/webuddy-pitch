"""Bring an existing project's code in from a Git address or an uploaded zip.

The destination is server-owned (<data>/repositories/<KEY>); request fields never become
paths or commands. A zip's .git directory and symlinks are dropped and a fresh baseline
commit is made, so no uploaded Git config or hook is ever honoured.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import threading
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit

from ..install import vendor_tool
from .errors import ApiError

CHUNK = 3 * 1024 * 1024
MAX_ZIP = 1024 * 1024 * 1024
MAX_UNPACKED = 4 * 1024 * 1024 * 1024
MAX_ENTRIES = 300_000
CLONE_SECONDS = 1800
GIT_SECONDS = 900
_LOCK = threading.RLock()
_SCP = re.compile(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[A-Za-z0-9._~/-]+")
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}")
_JOB = re.compile(r"[a-f0-9]{24}")


def destination(data_dir, key: str) -> Path:
    return Path(data_dir) / "repositories" / key


def _jobs(data_dir) -> Path:
    return Path(data_dir) / "project-imports"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def clean_url(url: str) -> str:
    """The address without any password or token, as stored and shown."""
    if url.startswith(("https://", "ssh://")):
        u = urlsplit(url)
        host = u.hostname or ""
        if u.port:
            host += f":{u.port}"
        if u.username and url.startswith("ssh://"):
            host = u.username + "@" + host
        return urlunsplit((u.scheme, host, u.path, "", ""))
    return url


def check_url(url) -> str:
    url = str(url or "").strip()
    if not url or len(url) > 2000 or any(c.isspace() or ord(c) < 32 for c in url) or url.startswith("-"):
        raise ApiError(400, "请填写 Git 仓库地址")
    if url.startswith(("https://", "ssh://")):
        u = urlsplit(url)
        if not u.hostname or not u.path.strip("/") or u.query or u.fragment:
            raise ApiError(400, "Git 地址不完整，例如 https://github.com/组织/仓库.git")
        return url
    if _SCP.fullmatch(url):
        return url
    raise ApiError(400, "只支持 https:// 或 ssh 地址（例如 git@github.com:组织/仓库.git）")


def _state(data_dir, job: str) -> dict:
    if not isinstance(job, str) or not _JOB.fullmatch(job):
        raise ApiError(404, "没有这个导入任务")
    f = _jobs(data_dir) / job / "state.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ApiError(404, "没有这个导入任务") from None


def _save(data_dir, st: dict) -> dict:
    folder = _jobs(data_dir) / st["job"]
    tmp = folder / "state.json.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, folder / "state.json")
    return st


def _public(st: dict) -> dict:
    return {k: v for k, v in st.items() if k not in ("secret_url",)}


def _owned(st: dict, by: str):
    if st.get("by") != by:
        raise ApiError(403, "只能由发起导入的人继续操作")


def start(P, body: dict, by: str) -> dict:
    if not isinstance(body, dict):
        raise ApiError(400, "导入内容必须是对象")
    key = str(body.get("key") or "").strip().upper()
    name = str(body.get("name") or "").strip() or key
    source = body.get("source")
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,9}", key):
        raise ApiError(400, "项目代号需为字母开头的 1–10 位字母数字，例如 OA")
    if len(name) > 120:
        raise ApiError(400, "项目名称最多 120 字")
    if source not in ("git", "zip"):
        raise ApiError(400, "代码来源只能是 Git 地址或 zip 包")
    st = {"job": secrets.token_hex(12), "key": key, "name": name, "source": source, "by": by, "created": _now(),
          "updated": _now(), "status": "uploading" if source == "zip" else "running", "step": "", "received": 0, "chunks": 0}
    if source == "git":
        url = check_url(body.get("url"))
        branch = str(body.get("branch") or "").strip()
        if branch and not _BRANCH.fullmatch(branch):
            raise ApiError(400, "分支名不正确")
        st.update(url=clean_url(url), branch=branch, step="正在拉取代码")
    else:
        size = body.get("size")
        if not isinstance(size, int) or size <= 0 or size > MAX_ZIP:
            raise ApiError(400, "zip 包大小需在 1 GB 以内")
        st.update(size=size, filename=str(body.get("filename") or "")[:200])
    with _LOCK:
        dest = destination(P.data_dir, key)
        if P.store.project(key) or dest.exists() or dest.is_symlink():
            raise ApiError(409, "项目代号或目录已存在，请换一个代号；原内容没有被覆盖")
        for f in _jobs(P.data_dir).glob("*/state.json") if _jobs(P.data_dir).is_dir() else []:
            try:
                other = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if other.get("key") == key and other.get("status") in ("uploading", "running"):
                raise ApiError(409, "这个代号已经在导入中")
        folder = _jobs(P.data_dir) / st["job"]
        folder.mkdir(parents=True)
        _save(P.data_dir, st)
    if source == "git":
        threading.Thread(target=_guard, args=(P, st["job"], _clone, url), daemon=True).start()
    return _public(st)


def chunk(P, job: str, body: dict, by: str) -> dict:
    with _LOCK:
        st = _state(P.data_dir, job)
        _owned(st, by)
        if st["status"] != "uploading":
            raise ApiError(409, "这个导入已经不在上传阶段")
        if body.get("seq") != st["chunks"]:
            raise ApiError(409, f"分片顺序不对，应上传第 {st['chunks']} 片")
        try:
            data = base64.b64decode(str(body.get("data") or ""), validate=True)
        except (binascii.Error, ValueError):
            raise ApiError(400, "分片内容不是 base64") from None
        if not data or len(data) > CHUNK or st["received"] + len(data) > st["size"]:
            raise ApiError(400, "分片大小不对")
        with open(_jobs(P.data_dir) / job / "upload.zip", "ab") as f:
            f.write(data)
        st.update(received=st["received"] + len(data), chunks=st["chunks"] + 1, updated=_now())
        return _public(_save(P.data_dir, st))


def finish(P, job: str, by: str) -> dict:
    with _LOCK:
        st = _state(P.data_dir, job)
        _owned(st, by)
        if st["status"] != "uploading":
            raise ApiError(409, "这个导入已经不在上传阶段")
        if st["received"] != st["size"]:
            raise ApiError(409, f"zip 还没传完：{st['received']} / {st['size']} 字节")
        st.update(status="running", step="正在解压", updated=_now())
        _save(P.data_dir, st)
    threading.Thread(target=_guard, args=(P, job, _unzip, None), daemon=True).start()
    return _public(st)


def status(P, job: str) -> dict:
    return _public(_state(P.data_dir, job))


def _step(P, job: str, **kw):
    with _LOCK:
        st = _state(P.data_dir, job)
        st.update(kw, updated=_now())
        _save(P.data_dir, st)
        return st


def _guard(P, job: str, work, arg):
    tmp = Path(P.data_dir) / "repositories" / (".importing-" + job)
    try:
        st = _state(P.data_dir, job)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        info = work(P, job, st, tmp, arg)
        _step(P, job, step="正在安装项目工具")
        vendor_tool(tmp, strict=False)
        exclude = tmp / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as f:
            f.write("\n/.tmh/\n")
        _step(P, job, step="正在登记项目")
        with _LOCK:
            dest = destination(P.data_dir, st["key"])
            if P.store.project(st["key"]) or dest.exists():
                raise ApiError(409, "项目代号或目录在导入期间被占用")
            os.replace(tmp, dest)
            P.store.add_project(st["key"], st["name"], str(dest), "")
        commit = _git(dest, "rev-parse", "HEAD").strip()
        _step(P, job, status="done", step="已导入", project=st["key"], root=str(dest), commit=commit, **info)
    except Exception as e:  # noqa: BLE001 - the job records any failure; the request thread is long gone
        msg = e.args[0] if isinstance(e, ApiError) and e.args else str(e)
        try:
            _step(P, job, status="failed", step="导入失败", error=str(msg)[:2000])
        except ApiError:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    finally:
        (_jobs(P.data_dir) / job / "upload.zip").unlink(missing_ok=True)


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new")
    return env


def _git(cwd, *args, timeout=GIT_SECONDS) -> str:
    r = subprocess.run(["git", "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never", *args],
                       cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=_env(), check=False)
    if r.returncode:
        raise ApiError(500, f"git {args[0]} 失败：{(r.stderr or r.stdout).strip()[-800:]}")
    return r.stdout


def _clone(P, job, st, tmp: Path, url: str) -> dict:
    args = ["clone", "--no-recurse-submodules"] + (["--branch", st["branch"]] if st.get("branch") else []) + ["--", url, str(tmp)]
    try:
        _git(tmp.parent, *args, timeout=CLONE_SECONDS)
    except ApiError as e:
        raise ApiError(500, str(e.args[0]).replace(url, st["url"])) from None
    if clean_url(url) != url:
        _git(tmp, "remote", "set-url", "origin", st["url"])
    return {"files": _count(tmp)}


def _count(root: Path) -> int:
    return sum(len(files) for d, _, files in os.walk(root) if "/.git" not in d.replace(os.sep, "/") + "/" and not d.endswith(".git"))


def _vendored(p: PurePosixPath) -> bool:
    return any(p.parts[k:k + 2] == (".tmh", "tool") for k in range(len(p.parts)))


def _members(z: zipfile.ZipFile) -> list:
    infos = z.infolist()
    if len(infos) > MAX_ENTRIES:
        raise ApiError(400, f"zip 里文件太多（超过 {MAX_ENTRIES} 个）")
    out, total = [], 0
    for i in infos:
        name = i.filename.replace("\\", "/")
        p = PurePosixPath(name)
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in p.parts:
            raise ApiError(400, f"zip 里有越界路径：{name[:200]}")
        if i.is_dir() or stat.S_ISLNK(i.external_attr >> 16) or ".git" in p.parts or "__MACOSX" in p.parts or _vendored(p):
            continue
        total += i.file_size
        if total > MAX_UNPACKED:
            raise ApiError(400, "zip 解压后超过 4 GB")
        out.append((p, i))
    if not out:
        raise ApiError(400, "zip 里没有文件")
    tops = {p.parts[0] for p, _ in out}
    strip = len(tops) == 1 and all(len(p.parts) > 1 for p, _ in out)
    return [(PurePosixPath(*p.parts[1:]) if strip else p, i) for p, i in out]


def _unzip(P, job, st, tmp: Path, _arg) -> dict:
    upload = _jobs(P.data_dir) / job / "upload.zip"
    try:
        z = zipfile.ZipFile(upload)
    except (OSError, zipfile.BadZipFile):
        raise ApiError(400, "上传的文件不是有效的 zip") from None
    with z:
        members = _members(z)
        tmp.mkdir()
        base = tmp.resolve()
        written = 0
        for rel, info in members:
            target = (tmp / Path(*rel.parts)).resolve()
            if base not in target.parents:
                raise ApiError(400, f"zip 里有越界路径：{info.filename[:200]}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                while True:
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    written += len(block)
                    if written > MAX_UNPACKED:
                        raise ApiError(400, "zip 解压后超过 4 GB")
                    dst.write(block)
    _step(P, job, step="正在建立代码基线")
    _git(tmp, "init", "-b", "main")
    _git(tmp, "add", "-A")
    _git(tmp, "-c", "user.name=Webuddy", "-c", "user.email=webuddy@localhost", "commit", "-q", "-m",
         "导入代码包 %s" % (st.get("filename") or st["key"]))
    return {"files": len(members)}
