"""Separate local operator credential; never expose it to Agent/MCP responses.

This separates remote workspace clients, not processes running as the same OS
user. The terminal confirmation remains an explicit human action, not proof
that a bearer token holder is a person.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
import secrets
import stat

from .errors import ApiError


def read_key(path):
    fd = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("操作者凭据必须是当前用户拥有、权限为0600的普通文件")
        with os.fdopen(fd, "r", encoding="ascii", closefd=False) as stream:
            value = stream.read().strip()
        if len(value) < 40:
            raise ValueError("操作者凭据不完整")
        return value
    finally:
        os.close(fd)


def initialize(data_dir):
    path = Path(data_dir) / "operator-approval.key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(secrets.token_urlsafe(48) + "\n")
    read_key(path)
    return path


def require(P, headers):
    supplied = headers.get("X-Webuddy-Operator-Token", "")
    if not supplied or not hmac.compare_digest(supplied.encode(), read_key(P.operator_key_path).encode()):
        raise ApiError(403, "需要独立操作者凭据；工作区Agent令牌不能提交人工决定")
