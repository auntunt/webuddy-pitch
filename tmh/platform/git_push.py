"""Push a finished task branch to the project's own remote. Never the default branch, never forced.

The machine's existing git credentials are used as they are. A refused push or a missing credential is returned as
the git error text; nothing else changes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from ..platform.errors import ApiError


def default_branch(root: Path) -> str:
    out = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                         capture_output=True, text=True)
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip().split("/", 1)[1]
    return "main"


def push_task_branch(root: Path, ticket_key: str, run_id: int) -> dict:
    branch = "tmh/%s-r%d" % (ticket_key, run_id)
    if branch == default_branch(root) or ticket_key == default_branch(root):
        raise ApiError(400, "不推送默认分支，只推送任务分支")
    exists = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "refs/heads/" + branch],
                            capture_output=True, text=True)
    if exists.returncode != 0:
        raise ApiError(404, "没有这个任务分支：%s" % branch)
    proc = subprocess.run(["git", "-C", str(root), "push", "origin", "%s:refs/heads/%s" % (branch, branch)],
                          capture_output=True, text=True)
    text = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0:
        return {"ok": False, "branch": branch, "error": text[-800:]}
    return {"ok": True, "branch": branch, "remote_branch": branch, "output": text[-800:]}
