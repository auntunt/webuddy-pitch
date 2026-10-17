"""After acceptance, the change goes out: merged into the project's main line, given a version, written down.

A ticket that passed acceptance used to stop at "closed" with its branch left aside, so nothing a client could get
ever changed. Here the accepted branch is merged into whatever the project's checkout is on (its main line), the
merge commit is tagged with a version, and the version goes into the project's release log with what it holds.
Nothing leaves this machine: no push, no deploy (those wait for a person).

When the merge cannot be made cleanly the main line is left exactly as it was: a conflict sends the ticket back to
the agent to redo the change on top of the current main line; a checkout with uncommitted work, or not on a branch,
waits for a person, who is told why.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .agents import git, is_git

LOG = "releases.jsonl"
_LOCK = threading.Lock()  # one merge at a time per platform: two acceptances must not race on one checkout


MERGE = "auto"  # unless autoflow.json says "merge": "off"


def settings(data_dir: Path) -> dict:
    """{"merge": "auto" | "off"}: auto merges an accepted change into the main line; off leaves it for a person."""
    conf = {"merge": MERGE}
    try:
        v = json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("merge")
        if v in ("auto", "off"):
            conf["merge"] = v
    except (OSError, ValueError, AttributeError):
        pass
    return conf


def releases(data_dir: Path, project: str = "", limit: int = 50) -> list:
    f = Path(data_dir) / LOG
    out = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not project or r.get("project") == project:
                out.append(r)
    return out[::-1][:limit]


def _version(data_dir: Path, project: str) -> str:
    """2026.10.17-3: the third version of the day for this project. Dates read better to a client than counters."""
    day = time.strftime("%Y.%m.%d")
    n = sum(1 for r in releases(data_dir, project, 100000) if r.get("version", "").startswith(day + "-"))
    return "%s-%d" % (day, n + 1)


def _adopted_branch(P, t: dict) -> tuple[str, str]:
    from .learn import _adopted
    ad, _ = _adopted(P.store, t["id"])
    return ((ad or {}).get("branch") or "", (ad or {}).get("commit") or "")


def ship(P, p: dict, t: dict, by: str) -> dict:
    """Merge an accepted ticket's branch. Returns {"state": "merged" | "conflict" | "waiting" | "none", ...}."""
    if settings(P.data_dir)["merge"] != "auto":
        return {"state": "waiting", "why": "设置为不自动合并"}
    branch, commit = _adopted_branch(P, t)
    if not branch:
        return {"state": "none", "why": "这张工单没有平台提交的代码改动"}
    root = Path(p["root"])
    if not is_git(root):
        return {"state": "waiting", "why": "项目目录不是 git 仓库"}
    with _LOCK:
        if not git(root, "rev-parse", "--verify", "--quiet", branch + "^{commit}", check=False).strip():
            return {"state": "none", "why": "分支 %s 已经不在了" % branch}
        main = git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
        if not main or main == "HEAD":
            return {"state": "waiting", "why": "项目目录没有停在某个分支上，不知道合并到哪"}
        if main == branch:
            return {"state": "waiting", "why": "项目目录现在就停在这次改动的分支上"}
        dirty = [line for line in git(root, "status", "--porcelain", "--untracked-files=no", check=False).splitlines() if line.strip()]
        if dirty:
            return {"state": "waiting", "why": "主干 %s 上有 %d 个文件没提交，先处理掉再合并，免得混在一起" % (main, len(dirty))}
        if _run_ok(root, "merge-base", "--is-ancestor", branch, "HEAD"):
            return {"state": "none", "why": "这次改动已经在主干 %s 里了" % main}
        version = _version(P.data_dir, p["key"])
        msg = "合并 %s %s（版本 %s）\n\n验收：%s\n分支：%s（提交 %s）\nTicket: %s" % (t["key"], t["title"], version, by, branch, commit, t["key"])
        r = _run(root, "-c", "user.name=webuddy", "-c", "user.email=webuddy@localhost", "merge", "--no-ff", "-m", msg, branch)
        if r.returncode != 0:
            files = [line.split(None, 1)[-1] for line in git(root, "diff", "--name-only", "--diff-filter=U", check=False).splitlines() if line.strip()]
            _run(root, "merge", "--abort")
            return {"state": "conflict", "branch": branch, "main": main, "files": files[:20],
                    "why": "和主干 %s 上后来的改动冲突%s" % (main, "：" + "、".join(files[:6]) if files else "")}
        sha = git(root, "rev-parse", "--short", "HEAD").strip()
        tag = "webuddy-%s-%s" % (p["key"], version)
        _run(root, "tag", "-a", tag, "-m", "%s %s" % (t["key"], t["title"]), "HEAD")
        _run(root, "branch", "-d", branch)  # merged: -d refuses anything not fully in
        rec = {"project": p["key"], "version": version, "tag": tag, "commit": sha, "main": main, "by": by,
               "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "tickets": [{"key": t["key"], "title": t["title"], "type": t.get("type", ""),
                                                                      "branch": branch, "commit": commit}]}
        f = Path(P.data_dir) / LOG
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return dict(rec, state="merged")


def _run(root: Path, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True)


def _run_ok(root: Path, *args) -> bool:
    return _run(root, *args).returncode == 0
