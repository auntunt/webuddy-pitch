"""Read-only ways to take a task's change back out of the platform.

The change is the task branch `tmh/<TICKET>-r<run>` plus any uncommitted edits in
its worktree. The worktree is read through a temporary index (GIT_INDEX_FILE), so
the real index, refs and the project folder are never changed. Every download says
whether it is committed or not, in its filename and in a status line inside it.
"""
from __future__ import annotations

import io
import os
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .errors import ApiError

COMMITTED = ("committed", "已提交")
UNCOMMITTED = ("uncommitted", "未提交（未通过检查或待人工审阅，不是已接受的代码）")


def _git(root: Path, *args: str, text: bool = True, env=None, cwd=None):
    proc = subprocess.run(["git", "-C", str(cwd or root), *args], capture_output=True, text=text, env=env)
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace") if not text else proc.stderr
        raise ApiError(409, "git 读取失败：%s" % (err or "").strip()[:200])
    return proc.stdout


@dataclass
class State:
    branch: str
    commit: str
    base: str
    tree: str
    kind: tuple
    ref: str
    worktree: Path | None


def task_branch(root: Path, ticket_key: str) -> str:
    refs = _git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/tmh/%s-r*" % ticket_key).split()
    if not refs:
        raise ApiError(404, "这个任务还没有可取回的代码分支")
    return sorted(refs, key=lambda r: int(r.rsplit("-r", 1)[1]))[-1]


def _worktree_of(root: Path, branch: str):
    out = _git(root, "worktree", "list", "--porcelain")
    for block in out.strip().split("\n\n"):
        lines = block.splitlines()
        path = next((l[9:] for l in lines if l.startswith("worktree ")), None)
        ref = next((l[7:] for l in lines if l.startswith("branch ")), None)
        if ref == "refs/heads/" + branch and path and Path(path).is_dir():
            return Path(path)
    return None


def state(root: Path, ticket_key: str) -> State:
    branch = task_branch(root, ticket_key)
    commit = _git(root, "rev-parse", branch).strip()
    base = _git(root, "merge-base", branch, "HEAD").strip()
    wt = _worktree_of(root, branch)
    tree = _git(root, "rev-parse", commit + "^{tree}").strip()
    if wt is not None:
        fd, index = tempfile.mkstemp(prefix="tmh-idx-")
        os.close(fd)
        os.unlink(index)
        env = dict(os.environ, GIT_INDEX_FILE=index)
        try:
            _git(root, "read-tree", commit, env=env, cwd=wt)
            _git(root, "add", "-A", env=env, cwd=wt)
            tree = _git(root, "write-tree", env=env, cwd=wt).strip()
        finally:
            if os.path.exists(index):
                os.unlink(index)
    committed = tree == _git(root, "rev-parse", commit + "^{tree}").strip()
    kind = COMMITTED if committed else UNCOMMITTED
    ref = commit[:12] if committed else commit[:12] + " + 工作区未提交改动"
    return State(branch, commit, base, tree, kind, ref, wt)


def _header(ticket_key: str, st: State) -> str:
    if st.kind is COMMITTED:
        return "Webuddy 任务 %s：已提交 %s（分支 %s）\n" % (ticket_key, st.commit[:12], st.branch)
    return "Webuddy 任务 %s：未提交（未通过检查或待人工审阅，不是已接受的代码）；基于分支 %s 的 %s 加工作区改动\n" % (
        ticket_key, st.branch, st.commit[:12])


def _changed(root: Path, st: State):
    rows = _git(root, "diff", "--name-status", "--no-renames", st.base, st.tree).splitlines()
    keep, deleted = [], []
    for row in rows:
        status, _, name = row.partition("\t")
        (deleted if status.startswith("D") else keep).append(name)
    return keep, deleted


def download(root: Path, ticket_key: str, kind: str):
    """Returns (bytes, content type, filename) for patch, files or archive."""
    st = state(root, ticket_key)
    tag = st.kind[0]
    if kind == "patch":
        body = _git(root, "diff", "--binary", "--no-renames", st.base, st.tree, text=False)
        return (_header(ticket_key, st).encode("utf-8") + body, "text/x-patch; charset=utf-8",
                "%s-%s.patch" % (ticket_key, tag))
    status = (_header(ticket_key, st)).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("STATUS.txt", status)
        if kind == "files":
            keep, deleted = _changed(root, st)
            for name in keep:
                zf.writestr(name, _git(root, "show", "%s:%s" % (st.tree, name), text=False))
            zf.writestr("DELETED_FILES.txt", "\n".join(deleted) + ("\n" if deleted else ""))
            name = "%s-changed-%s.zip" % (ticket_key, tag)
        elif kind == "archive":
            listing = _git(root, "ls-tree", "-r", "-z", "--full-tree", st.tree, text=False)
            for row in listing.split(b"\0"):
                if not row:
                    continue
                meta, _, name = row.partition(b"\t")
                blob = meta.split()[2].decode()
                zf.writestr(name.decode("utf-8"), _git(root, "cat-file", "blob", blob, text=False))
            name = "%s-%s.zip" % (ticket_key, tag)
        else:
            raise ApiError(404, "没有这种取回方式")
    return buf.getvalue(), "application/zip", name
