"""Separate local operator credential; never expose it to Agent/MCP responses.

This separates remote workspace clients, not processes running as the same OS
user. The terminal confirmation remains an explicit human action, not proof
that a bearer token holder is a person.

Cross-platform note (roadmap G5): POSIX protections here are symlink refusal
(``O_NOFOLLOW``), "regular file owned by the current user" and mode ``0600``.
Windows has neither ``os.O_NOFOLLOW`` nor ``os.getuid()``; its real protection
is the NTFS ACL inherited from the (per-user) data directory, so the Windows
branch verifies the equivalent properties it *can* observe and fails closed
whenever a check cannot be established:

* the final path component must not be a symlink/reparse point (checked before
  opening; NTFS junctions are directories and are rejected by the regular-file
  check);
* the open handle must be a regular file (same ``S_ISREG`` check as POSIX);
* the file must be readable for the current user (``os.access``); if that
  cannot be established the key is refused rather than trusted;
* POSIX ``st_uid``/``0600`` mode bits are not synthesized on Windows, so they
  cannot be asserted there and are skipped instead of being faked.

The POSIX branch keeps the exact previous checks, so Linux semantics (and the
CI Linux job) are unchanged.
"""
from __future__ import annotations

import hmac
import os
from pathlib import Path
import secrets
import stat

from .errors import ApiError

# Windows exposes neither of these; branch once at import rather than per call.
_HAS_GETUID = hasattr(os, "getuid")
_HAS_NOFOLLOW = hasattr(os, "O_NOFOLLOW")


def _no_follow_flags(flags):
    """Add O_NOFOLLOW where the platform has it (POSIX); Windows has no equivalent flag."""
    return flags | os.O_NOFOLLOW if _HAS_NOFOLLOW else flags


def _reject_symlink(path):
    """Fail closed on symlinks/reparse points on platforms without O_NOFOLLOW."""
    try:
        if Path(path).is_symlink():
            raise ValueError("操作者凭据不能是符号链接")
    except OSError as exc:  # unreadable path metadata: deny, do not trust
        raise ValueError("操作者凭据路径不可验证") from exc


def _check_owner_and_mode(info, path):
    """POSIX: owner==current user and mode==0600. Windows: ACL-based equivalent."""
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("操作者凭据必须是当前用户拥有、权限为0600的普通文件")
    if _HAS_GETUID:
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("操作者凭据必须是当前用户拥有、权限为0600的普通文件")
        return
    # Windows: NTFS ACLs (inherited from the per-user data directory) are the
    # access control, not POSIX mode bits, so only assert what is observable.
    # Readability is checked because the key is useless if it cannot be read;
    # an unverifiable ACL (os.access false/error) refuses the key.
    if not os.access(str(path), os.R_OK):
        raise ValueError("操作者凭据不可读或访问权限无法验证")


def read_key(path):
    path = Path(path)
    if not _HAS_NOFOLLOW:
        _reject_symlink(path)
    fd = os.open(path, _no_follow_flags(os.O_RDONLY))
    try:
        info = os.fstat(fd)
        _check_owner_and_mode(info, path)
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
        fd = os.open(path, _no_follow_flags(os.O_WRONLY | os.O_CREAT | os.O_EXCL), 0o600)
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
