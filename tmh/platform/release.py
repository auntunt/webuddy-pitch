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
import subprocess
import threading
import time
from pathlib import Path

from .agents import git, is_git

LOG = "releases.jsonl"
_LOCK = threading.Lock()  # one merge at a time per platform: two acceptances must not race on one checkout


MERGE = ""  # tests force "off"; otherwise autoflow.json decides


def settings(data_dir: Path) -> dict:
    """{"merge": "auto" | "off"}: auto merges an accepted change into the main line; off leaves it for a person.
    Unless autoflow.json says "merge", it follows "on": a platform set to hand-only work does not start writing
    merge commits into a checkout after an upgrade."""
    try:
        conf = json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8"))
        conf = conf if isinstance(conf, dict) else {}
    except (OSError, ValueError):
        conf = {}
    v = conf.get("merge")
    if v not in ("auto", "off"):
        v = MERGE or ("auto" if conf.get("on", True) else "off")
    return {"merge": v, "main": conf.get("main") if isinstance(conf.get("main"), dict) else {}}


def main_branch(root: Path, data_dir: Path, project: str) -> str:
    """The project's main line: set in autoflow.json ("main": {"OA": "develop"}), else what origin calls its default,
    else main or master. "" when none of those exists: then nothing is merged until a person names it."""
    named = settings(data_dir)["main"].get(project) or settings(data_dir)["main"].get("*") or ""
    if named:
        return named
    ref = git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False).strip()
    if ref.startswith("origin/"):
        return ref[len("origin/"):]
    for b in ("main", "master"):
        if _run_ok(root, "show-ref", "--verify", "--quiet", "refs/heads/" + b):
            return b
    return ""


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


def _version(data_dir: Path, project: str, root: Path) -> str:
    """2026.10.17-3: the third version of the day for this project. Dates read better to a client than counters.
    A number whose tag is already in the repository (a restored data folder, a second platform) is skipped."""
    day = time.strftime("%Y.%m.%d")
    n = sum(1 for r in releases(data_dir, project, 100000) if r.get("version", "").startswith(day + "-")) + 1
    while _run_ok(root, "show-ref", "--verify", "--quiet", "refs/tags/webuddy-%s-%s-%d" % (project, day, n)):
        n += 1
    return "%s-%d" % (day, n)


def _adopted(P, t: dict) -> dict:
    from .learn import _adopted
    ad, _ = _adopted(P.store, t["id"])
    return ad or {}


IN_PROGRESS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer")


def _gitdir(root: Path) -> Path:
    d = Path(git(root, "rev-parse", "--git-dir", check=False).strip() or ".git")
    return d if d.is_absolute() else root / d


def unsettled(P, t: dict, ad: dict) -> str:
    """Why the adopted change is not the one to ship now, or "": a newer attempt is running or waiting for review."""
    from . import handwork
    if handwork.busy(t["key"]):
        return "这张工单有一次人工提交正在检查，等它定下来再合并"
    fixes = [r for r in P.store.runs(ticket_id=t["id"]) if r["mode"] == "fix"]
    if any(r["status"] in ("queued", "running") for r in fixes):
        return "这张工单还有一次修改正在进行，等它定下来再合并"
    if fixes:
        last = max(fixes, key=lambda r: r["id"])
        if ad.get("run") and last["id"] != ad["run"] and last["status"] == "done" and last.get("diff") and not last.get("decision"):
            return "这张工单有一次更新的修改还没定下来（运行 #%d），先采纳或放弃它" % last["id"]
    return ""


def ship(P, p: dict, t: dict, by: str) -> dict:
    """Merge an accepted ticket's change. Returns {"state": "merged" | "conflict" | "waiting" | "none", ...}.
    Only "conflict" means the change itself has to be redone; "waiting" is something about this machine a person fixes."""
    if settings(P.data_dir)["merge"] != "auto":
        return {"state": "waiting", "why": "设置为不自动合并（autoflow.json 里 merge 为 off，或自动处理关着）"}
    ad = _adopted(P, t)
    branch, commit = ad.get("branch") or "", ad.get("commit") or ""
    if not commit:
        return {"state": "none", "why": "这张工单没有经平台提交的代码改动，合并由改的人自己做"}
    why = unsettled(P, t, ad)
    if why:
        return {"state": "waiting", "why": why}
    root = Path(p["root"])
    if not is_git(root):
        return {"state": "waiting", "why": "项目目录不是 git 仓库"}
    with _LOCK:
        sha = git(root, "rev-parse", "--verify", "--quiet", commit + "^{commit}", check=False).strip()
        if not sha:
            return {"state": "none", "why": "验收的提交 %s 在仓库里找不到了" % commit}
        if branch:  # someone committed on top after it was accepted: that part nobody looked at
            tip = git(root, "rev-parse", "--verify", "--quiet", branch + "^{commit}", check=False).strip()
            if tip and tip != sha:
                return {"state": "waiting", "why": "分支 %s 在验收之后又有新提交，合并哪个要人来定：重新验收，或者手动合并 %s" % (branch, commit)}
        main = main_branch(root, P.data_dir, p["key"])
        if not main:
            return {"state": "waiting", "why": "找不到主干分支（没有 main、master，也没有 origin 的默认分支）：在 autoflow.json 的 main 里写上它"}
        cur = git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
        if cur != main:
            return {"state": "waiting", "why": "项目目录现在停在 %s，不在主干 %s 上，不往别的分支里合" % (cur or "（游离）", main)}
        gd = _gitdir(root)
        busy = [x for x in IN_PROGRESS if (gd / x).exists()]
        if busy:
            return {"state": "waiting", "why": "项目目录里有一个没做完的 git 操作（%s），等它做完" % busy[0]}
        if (gd / "index.lock").exists():
            return {"state": "waiting", "why": "项目目录被别的 git 程序占着（index.lock），稍后再合并"}
        dirty = [line for line in git(root, "status", "--porcelain", "--untracked-files=no", check=False).splitlines() if line.strip()]
        if dirty:
            return {"state": "waiting", "why": "主干 %s 上有 %d 个文件没提交，先处理掉再合并，免得混在一起" % (main, len(dirty))}
        if _run_ok(root, "merge-base", "--is-ancestor", sha, "HEAD"):
            return {"state": "none", "why": "这次改动已经在主干 %s 里了" % main}
        # work out the merge without touching the checkout first: a conflict leaves nothing behind to clean up
        mt = _run(root, "merge-tree", "--write-tree", "--name-only", "--no-messages", "HEAD", sha)
        if mt.returncode == 1:
            files = [x for x in mt.stdout.splitlines()[1:] if x.strip()]
            return {"state": "conflict", "branch": branch or sha[:10], "main": main, "files": files[:20],
                    "why": "和主干 %s 上后来的改动冲突%s" % (main, "：" + "、".join(files[:6]) if files else "")}
        old_git = mt.returncode == 129 or "usage" in (mt.stderr or "").lower()  # git before 2.38 (Ubuntu 22.04, Kylin V10)
        if mt.returncode != 0 and not old_git:
            return {"state": "waiting", "why": "算不出合并结果：%s" % (mt.stderr.strip()[:300] or "git merge-tree 失败")}
        head = git(root, "rev-parse", "HEAD").strip()
        version = _version(P.data_dir, p["key"], root)
        msg = "合并 %s %s（版本 %s）\n\n验收：%s\n分支：%s（提交 %s）\nTicket: %s" % (t["key"], t["title"], version, by, branch or "-", sha[:10], t["key"])
        try:
            r = _run(root, "-c", "user.name=webuddy", "-c", "user.email=webuddy@localhost", "merge", "--no-ff", "-m", msg, sha, timeout=MERGE_S)
            failed, err = r.returncode != 0, (r.stderr or r.stdout).strip()
        except subprocess.TimeoutExpired:
            failed, err = True, "合并超过 %d 秒没做完（多半是仓库的 git hook 卡住了）" % MERGE_S
        if failed:
            ours = (gd / "MERGE_HEAD").exists() and git(root, "rev-parse", "MERGE_HEAD", check=False).strip() == sha
            clash = [x for x in git(root, "diff", "--name-only", "--diff-filter=U", check=False).splitlines() if x.strip()] if ours else []
            if ours:
                _run(root, "merge", "--abort")
            if old_git and clash and git(root, "rev-parse", "HEAD", check=False).strip() == head and not (gd / "MERGE_HEAD").exists():
                return {"state": "conflict", "branch": branch or sha[:10], "main": main, "files": clash[:20],
                        "why": "和主干 %s 上后来的改动冲突：%s" % (main, "、".join(clash[:6]))}
            back = git(root, "rev-parse", "HEAD", check=False).strip() == head and not (gd / "MERGE_HEAD").exists()
            return {"state": "waiting", "why": ("合并没做成：%s" % err[:300]) if back else
                    "合并没做成，而且项目目录没能恢复原样，请人马上看一下（git status）：%s" % err[:300]}
        new = git(root, "rev-parse", "--short", "HEAD").strip()
        tag = "webuddy-%s-%s" % (p["key"], version)
        tagged = _run_ok(root, "tag", "-a", tag, "-m", "%s %s" % (t["key"], t["title"]), "HEAD")
        if branch and branch.startswith("tmh/"):
            _run(root, "branch", "-d", branch)  # merged: -d refuses anything not fully in
        rec = {"project": p["key"], "version": version, "tag": tag if tagged else "", "commit": new, "main": main, "by": by,
               "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "tickets": [{"key": t["key"], "title": t["title"], "type": t.get("type", ""),
                                                                      "branch": branch, "commit": sha[:10]}]}
        f = Path(P.data_dir) / LOG
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return dict(rec, state="merged")


MERGE_S = 180


def _run(root: Path, *args, timeout=None):
    return subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True, timeout=timeout)


def _run_ok(root: Path, *args) -> bool:
    return _run(root, *args).returncode == 0
