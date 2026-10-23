"""Owner-only, endpoint-bound credentials for a member's CLI/MCP connection.

These files carry delegated tool credentials, never passwords or browser cookies.
Reads and publication are anchored to a checked directory descriptor. Publication
uses a hard link to a fully written private temporary file, so an existing path
is never overwritten and readers never see a partly written credential.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import stat
import urllib.parse


class CredentialError(ValueError):
    def __init__(self, message, code="invalid_credential"):
        super().__init__(message)
        self.code = code


def endpoint(value):
    """Allow only a root legacy URL or one canonical tenant prefix."""
    if not isinstance(value, str) or not value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise CredentialError("工作台地址格式不正确", "invalid_endpoint")
    value = value.rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(value)
        parsed.port
    except ValueError as exc:
        raise CredentialError("工作台地址或端口格式不正确", "invalid_endpoint") from exc
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or "?" in value or "#" in value or "\\" in value
            or (parsed.path and not re.fullmatch(r"/t/[a-z0-9][a-z0-9_-]{0,63}", parsed.path))):
        raise CredentialError("工作台地址仅允许 http(s)://host:port 或 /t/<租户>；不得带凭据、其他路径或查询参数", "invalid_endpoint")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise CredentialError("远程连接必须使用 HTTPS；本地可使用 127.0.0.1/localhost", "insecure_endpoint")
    return value, parsed


def document(value):
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != 1:
        raise CredentialError("凭据必须是 schema=1 的 JSON 对象")
    url, parsed = endpoint(value.get("endpoint"))
    token = value.get("token")
    if not parsed.path:
        raise CredentialError("个人工具凭据必须绑定 /t/<租户> 地址", "invalid_endpoint")
    if not isinstance(token, str) or not re.fullmatch(r"wbt_[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
        raise CredentialError("工具凭据格式不正确；请在个人工具连接页面重新生成")
    # Metadata does not grant permission. The server returns the current scope.
    return dict(value, endpoint=url)


@contextmanager
def _parent(path):
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise CredentialError("此平台无法验证 owner-only 凭据文件；请使用支持 POSIX 权限的环境", "credential_platform_unsupported")
    path = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    if not path.name or path.name in (".", ".."):
        raise CredentialError("请选择凭据文件路径", "unsafe_credential_path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(path.anchor, flags)
    try:
        parts = path.parent.parts[1:]
        for part in parts:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            info = os.fstat(fd)
            # System sticky temporary roots are traversal-only. The immediate
            # parent must still be private against writes by other accounts.
            if info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
                raise CredentialError("凭据路径经过可被其他账号改写的目录", "unsafe_credential_path")
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise CredentialError("凭据父目录必须属于当前账号且不可被组或其他账号写入", "unsafe_credential_path")
        yield path, fd
    except OSError as exc:
        raise CredentialError("无法安全访问凭据文件；父目录必须存在且不得使用符号链接", "unsafe_credential_path") from exc
    finally:
        os.close(fd)


def load(path):
    with _parent(path) as (_path, parent_fd):
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(_path.name, flags, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_uid != os.getuid() or info.st_nlink != 1):
                raise CredentialError("凭据必须是当前账号独占的普通 0600 文件；不接受链接或特殊文件", "unsafe_credential_file")
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                fd = None
                try:
                    value = json.load(stream)
                except (ValueError, UnicodeError) as exc:
                    raise CredentialError("凭据文件不是有效 UTF-8 JSON") from exc
            return document(value)
        finally:
            if fd is not None:
                os.close(fd)


def save(path, value):
    value = document(value)
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with _parent(path) as (target, parent_fd):
        temp = ".webuddy-credential-" + secrets.token_hex(16)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp, target.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
            except FileExistsError as exc:
                raise CredentialError("目标凭据文件已存在；请选择新路径，原文件保持不变", "credential_exists") from exc
        finally:
            os.unlink(temp, dir_fd=parent_fd)
        os.fsync(parent_fd)
        return str(target)
