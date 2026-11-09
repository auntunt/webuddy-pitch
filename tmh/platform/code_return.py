"""Read-only ways to take a task's committed change back out of the platform.

The change lives on the ticket branch `tmh/<TICKET>-r<run>` in the project's git
repository. Every function here only reads: it never fetches, checks out, merges
or writes to the project folder.
"""
from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path

from .errors import ApiError


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=text)
    if proc.returncode != 0:
        raise ApiError(409, "git 读取失败：%s" % (proc.stderr if text else b"").strip()[:200])
    return proc.stdout


def task_branch(root: Path, ticket_key: str) -> str:
    refs = _git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/tmh/%s-r*" % ticket_key).split()
    if not refs:
        raise ApiError(404, "这个任务还没有可取回的代码分支")
    return sorted(refs, key=lambda r: int(r.rsplit("-r", 1)[1]))[-1]


def _base(root: Path, branch: str) -> str:
    return _git(root, "merge-base", branch, "HEAD").strip()


def patch(root: Path, ticket_key: str) -> bytes:
    branch = task_branch(root, ticket_key)
    base = _base(root, branch)
    return _git(root, "format-patch", "--stdout", "%s..%s" % (base, branch), text=False)


def changed(root: Path, ticket_key: str):
    branch = task_branch(root, ticket_key)
    base = _base(root, branch)
    rows = _git(root, "diff", "--name-status", "--no-renames", base, branch).splitlines()
    added_or_changed, deleted = [], []
    for row in rows:
        status, _, name = row.partition("\t")
        (deleted if status.startswith("D") else added_or_changed).append(name)
    return branch, base, added_or_changed, deleted


def changed_files_zip(root: Path, ticket_key: str) -> bytes:
    branch, base, keep, deleted = changed(root, ticket_key)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in keep:
            zf.writestr(name, _git(root, "show", "%s:%s" % (branch, name), text=False))
        zf.writestr("DELETED_FILES.txt", "\n".join(deleted) + ("\n" if deleted else ""))
    return buf.getvalue()


def full_archive(root: Path, ticket_key: str) -> bytes:
    branch = task_branch(root, ticket_key)
    return _git(root, "archive", "--format=zip", branch, text=False)
