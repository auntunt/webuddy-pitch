"""What the outcomes teach: lessons from acceptance, and an eval set built from accepted tickets.

Lessons (<data>/lessons.jsonl). A ticket that fails acceptance leaves a lesson: why it was sent back and which
files the rejected change touched. A ticket that passes after people added commits on top of the automatic one
leaves a lesson too: what they changed by hand (the files and a slice of their diff). The next prompts on
related tickets (same business flows, same files, similar words) carry the closest lessons, and the prompt of
the ticket itself carries its own acceptance notes.

Eval set (<data>/evals/<项目代号>.json). Every ticket accepted after an automatic change becomes a case: the
commit the change started from, the ticket text, and the files that really had to change (from that commit to
the tip of the branch, so later human fixes count). Cases can also be added by hand. Running the set checks
out each case's starting commit in a detached worktree, has the agent draft a change plan exactly as for a
real ticket, and scores which of the right files it named (recall) and how many of the files it named were
right (precision). Results go to <data>/evals/results.jsonl, one line per case, grouped by batch.

Cases from history. A ticket already closed in Jira/禅道 and imported here becomes a case when the project's commit
messages name it (TOG-12, bug#123, #123): the case starts at the parent of its earliest fix commit, the text is
only the title and description people wrote then (no later comments, no resolution note), and the right files
are what the fix commits changed, minus lock files, generated files and whitespace-only edits. Tickets no commit
names are skipped, never guessed by date. Fixes touching more than 15 files, or only config and SQL, are flagged
and left out unless asked for. Their source is "history", so their scores can be read apart.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .agents import git, pick_model, load_config, build_prompt
from .store import now

LESSONS = "lessons.jsonl"
_LOCK = threading.Lock()


# ---------------------------------------------------------------- lessons

def _grams(text: str) -> set:
    t = (text or "").lower()
    out = set(w for w in re.findall(r"[a-z][a-z0-9_]{2,}", t))
    for run in re.findall(r"[一-鿿]+", t):
        out.update(run[i:i + 2] for i in range(len(run) - 1))
    return out


def changed_files(diff: str) -> list:
    return list(dict.fromkeys(re.findall(r"^diff --git a/(\S+) b/", diff or "", re.M)))


def lessons(data_dir: Path, project: str = "", limit: int = 200) -> list:
    f = Path(data_dir) / LESSONS
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not project or d.get("project") == project:
            out.append(d)
    return out[::-1][:limit]


def add_lesson(data_dir: Path, d: dict) -> dict:
    d = dict(d, ts=now())
    with _LOCK:
        f = Path(data_dir) / LESSONS
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    return d


def relevant(data_dir: Path, project: str, ticket: dict, extra: str = "", limit: int = 3) -> list:
    """The lessons from other tickets closest to this one: shared business flows, shared files, similar words."""
    flows = set((ticket.get("links") or {}).get("flows") or [])
    text = "%s %s %s" % (ticket.get("title", ""), (ticket.get("body") or "")[:1500], extra[:3000])
    words, low = _grams(text), text.lower()
    scored = []
    for l in lessons(data_dir, project, 500):
        if l.get("ticket") == ticket.get("key"):
            continue
        s = 3 * len(flows & set(l.get("flows") or []))
        s += 2 * sum(1 for f in l.get("files") or [] if f.lower() in low or f.rsplit("/", 1)[-1].lower() in low)
        lw = _grams("%s %s" % (l.get("title", ""), l.get("note", "")))
        if lw and words:
            s += 4 * len(words & lw) / math.sqrt(len(words) * len(lw))
        if s >= 1.5:
            scored.append((s, l))
    scored.sort(key=lambda x: -x[0])
    return [l for _, l in scored[:limit]]


KIND = {"reject": "验收没通过", "human-fix": "人工在自动提交之后又改过", "review": "对照官方修复复盘"}


def lessons_text(ls: list) -> str:
    if not ls:
        return ""
    out = ["## 以往的教训（相近工单的验收结果，避免重犯）"]
    for l in ls:
        out.append("- %s %s「%s」：%s%s" % (l.get("ticket", ""), KIND.get(l.get("kind"), l.get("kind", "")), l.get("title", "")[:60],
                                         (l.get("note") or "").strip()[:400], "（涉及 %s）" % "、".join(l["files"][:6]) if l.get("files") else ""))
        if l.get("diff"):
            out += ["  人工改动片段：", "  ```diff", "  " + l["diff"][:1200].replace("\n", "\n  "), "  ```"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- acceptance

def _adopted(store, tid: int) -> tuple[dict | None, dict | None]:
    """The latest adopt event of a ticket and its run."""
    ev = [e for e in store.events(tid) if e["kind"] == "adopt" and (e.get("data") or {}).get("commit")]
    if not ev:
        return None, None
    d = ev[-1]["data"]
    return d, store.run(d.get("run")) if d.get("run") else None


def _resolve(root: Path, ref: str) -> str:
    try:
        return git(root, "rev-parse", "--verify", "-q", ref + "^{commit}").strip()
    except RuntimeError:
        return ""


def on_accept(P, p: dict, t: dict, passed: bool, note: str, by: str) -> dict:
    """Turn one acceptance into lessons and eval cases. Never raises: learning must not block acceptance."""
    out = {}
    try:
        ad, run = _adopted(P.store, t["id"])
        files = changed_files(run.get("diff") or "") if run else []
        base = {"project": p["key"], "ticket": t["key"], "title": t["title"], "flows": (t.get("links") or {}).get("flows") or [], "by": by}
        if not passed:
            out["lesson"] = add_lesson(P.data_dir, dict(base, kind="reject", note=note, files=files, run=ad.get("run") if ad else None))
            return out
        if not ad:
            return out
        root = P.root(p)
        sha = _resolve(root, ad["commit"])
        tip = _resolve(root, ad.get("branch") or "") or sha
        if not sha:
            return out
        later = git(root, "log", "--format=%s", "%s..%s" % (sha, tip), check=False).strip()
        if later:
            d = git(root, "diff", sha, tip, check=False)
            out["lesson"] = add_lesson(P.data_dir, dict(base, kind="human-fix", note="自动提交之后人工又提交了：" + "；".join(later.splitlines()[:5]) + ("。验收说明：" + note if note else ""),
                                                        files=changed_files(d), diff=d[:2000]))
        parent = ""
        for e in P.store.events(t["id"]):  # a change redone after a rejection builds on the first one: start before that
            c = _resolve(root, (e.get("data") or {}).get("commit") or "") if e["kind"] == "adopt" else ""
            if c and subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", c, tip]).returncode == 0:
                parent = _resolve(root, c + "^")
                break
        if parent:
            gold = [f for f in git(root, "diff", "--name-only", parent, tip, check=False).split("\n") if f.strip()]
            if gold:
                out["case"] = add_case(P.data_dir, p["key"], {"ticket": t["key"], "title": t["title"], "body": t.get("body") or "",
                                                              "flows": base["flows"], "base": parent, "gold": gold[:40], "source": "accepted"})
    except Exception as e:  # noqa: BLE001
        out["error"] = "%s: %s" % (type(e).__name__, e)
    return out


# ---------------------------------------------------------------- eval set

def _edir(data_dir: Path) -> Path:
    return Path(data_dir) / "evals"


def cases(data_dir: Path, key: str) -> list:
    f = _edir(data_dir) / ("%s.json" % key)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return []


def _save(data_dir: Path, key: str, cs: list) -> None:
    d = _edir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.json" % key)).write_text(json.dumps(cs, ensure_ascii=False, indent=1), encoding="utf-8")


def add_case(data_dir: Path, key: str, c: dict) -> dict:
    if not (c.get("title") or "").strip():
        raise ValueError("评测用例需要标题")
    gold = [x.strip().strip("/") for x in c.get("gold") or [] if str(x).strip()]
    if not gold:
        raise ValueError("评测用例需要写出该改的文件")
    with _LOCK:
        cs = cases(data_dir, key)
        if c.get("ticket"):
            cs = [x for x in cs if x.get("ticket") != c["ticket"]]  # the latest acceptance of a ticket wins
        n = max([int(x["id"][1:]) for x in cs if re.match(r"^c\d+$", x.get("id", ""))] + [0]) + 1
        case = {"id": "c%d" % n, "ticket": c.get("ticket", ""), "title": c["title"].strip()[:200], "body": (c.get("body") or "")[:6000],
                "flows": list(c.get("flows") or []), "base": c.get("base") or "", "gold": gold, "source": c.get("source", "manual"), "added": now()}
        cs.append(case)
        _save(data_dir, key, cs)
    return case


# ---------------------------------------------------------------- cases from history

BIG = 15
_JIRA = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*-\d+)(?![\d])")
_ZT = re.compile(r"(?i)(?<![A-Za-z0-9_])(bug|story|task)\s*[-#_:：]?\s*(\d+)(?!\d)")
_HASH = re.compile(r"(?:(?<![A-Za-z0-9_&])#|(?<![A-Za-z0-9_])issues/)(\d+)(?!\d)")  # #123, 【issues/123】, …/issues/123
_CLOSING = re.compile(r"(?i)(?:\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\b|修复|解决|关闭)\s*[:：]?\s*\(?\s*(?:[A-Za-z][A-Za-z0-9_]*-\d+|#\d+|\S*issues/\d+|(?:bug|story|task)\s*[-#_:：]?\s*\d+)")
_LOCKS = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "pipfile.lock", "go.sum", "cargo.lock", "composer.lock", "gemfile.lock"}
_GEN = re.compile(r"(^|/)(dist|build|target|out|node_modules|generated|__generated__)/|\.min\.(js|css)$|\.map$|\.pyc$")
_CONF = re.compile(r"\.(sql|properties|ya?ml|ini|conf|cfg|toml|env)$", re.I)
DONE = ("closed", "done", "resolved", "关闭", "已关闭", "已解决", "已完成", "完成", "已验收")


def refs(msg: str) -> set:
    """Ticket ids a commit message names, normalised: tog-12, bug-123, #123 (also written issues/123 or as the issue URL)."""
    out = {m.lower() for m in _JIRA.findall(msg)}
    out |= {"%s-%s" % (k.lower(), n) for k, n in _ZT.findall(msg)}
    out |= {"#" + n for n in _HASH.findall(msg)}
    return out


def _ids(t: dict, bare: dict) -> set:
    ids = {t["key"].lower()}
    ids |= {x.lower() for x in (t.get("external") or {}).get("prs") or []}  # the merged pull requests that closed it
    k = ((t.get("external") or {}).get("key") or "").strip().lower()
    if k:
        ids.add(k)
        m = re.match(r"(bug|story|task)-(\d+)$", k)
        if m and bare.get(m.group(2)) == 1:  # a bare #123 counts only when one ticket has that number
            ids.add("#" + m.group(2))
    return ids


def _done(t: dict) -> str:
    """When a ticket was finished: the tool's resolve date, else its last update if it is closed. Empty if open."""
    x = t.get("external") or {}
    if x.get("resolved"):
        return x["resolved"]
    if t.get("status") == "closed" or (x.get("status") or "").lower() in DONE:
        return x.get("updated") or t.get("updated") or ""
    return ""


def _kept(root: Path, sha: str, parent: str) -> list:
    """Files a commit really changed against its first parent (a merge: the whole pull request):
    no lock files, generated files, binaries or whitespace-only edits."""
    out = []
    for line in git(root, "diff", "-w", "--ignore-blank-lines", "--numstat", parent, sha, check=False).splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-" or (parts[0] == "0" and parts[1] == "0"):
            continue
        f = parts[2]
        if "=>" in f:  # a rename: keep the new name
            f = re.sub(r"\{[^{}]*=> ([^{}]*)\}", r"\1", f) if "{" in f else f.split("=>")[-1]
            f = f.strip().replace("//", "/")
        if f.rsplit("/", 1)[-1].lower() in _LOCKS or _GEN.search(f):
            continue
        out.append(f)
    return out


def from_history(P, p: dict, since: str = "", until: str = "", apply: bool = False, flagged: bool = False) -> dict:
    """Match closed tickets to the commits that fixed them. Preview by default; apply=True writes the cases."""
    root = P.root(p)
    log = git(root, "log", "--format=%H%x1f%P%x1f%B%x1e", "HEAD", check=False)  # merges too: "Merge pull request #N"
    by = {}  # ticket id -> commits naming it, newest first
    order = []
    for rec in log.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) != 3:
            continue
        sha, parents, msg = parts
        order.append(sha)
        for r in refs(msg):
            by.setdefault(r, []).append((sha, parents.split()[0] if parents.strip() else ""))
    pos = {sha: i for i, sha in enumerate(order)}
    ts = [t for t in P.store.tickets(project_id=p["id"], limit=20000) if (t.get("external") or {}).get("key") and _done(t)]
    ts = [t for t in ts if (not since or _done(t)[:10] >= since) and (not until or _done(t)[:10] <= until)]
    bare = {}
    for t in ts:
        m = re.match(r"(?i)(bug|story|task)-(\d+)$", (t.get("external") or {}).get("key") or "")
        if m:
            bare[m.group(2)] = bare.get(m.group(2), 0) + 1
    have = {c.get("ticket") for c in cases(P.data_dir, p["key"])}
    out = {"tickets": len(ts), "commits": len(order), "matched": [], "flagged": [], "unmatched": 0, "existing": 0, "added": []}
    for t in ts:
        hits = {}
        for i in _ids(t, bare):
            for sha, parent in by.get(i, []):
                hits[sha] = parent
        if not hits:
            out["unmatched"] += 1
            continue
        if t["key"] in have:
            out["existing"] += 1
            continue
        first = sorted(hits, key=pos.get)[-1]  # the log is newest first: the earliest fix is last
        base = hits[first]
        gold = list(dict.fromkeys(f for sha in sorted(hits, key=pos.get, reverse=True) for f in _kept(root, sha, hits[sha]) if hits[sha]))
        if not base or not gold:
            out["unmatched"] += 1
            continue
        why = "改了 %d 个文件" % len(gold) if len(gold) > BIG else "只改配置或 SQL" if all(_CONF.search(f) for f in gold) else ""
        row = {"ticket": t["key"], "external": t["external"]["key"], "title": t["title"], "commits": [s[:10] for s in hits],
               "base": base, "gold": gold, "why": why, "done": _done(t)[:10]}
        (out["flagged"] if why else out["matched"]).append(row)
    if apply:
        for row in out["matched"] + (out["flagged"] if flagged else []):
            t = next(x for x in ts if x["key"] == row["ticket"])
            c = add_case(P.data_dir, p["key"], {"ticket": t["key"], "title": t["title"], "body": t.get("body") or "", "base": row["base"],
                                                "gold": row["gold"][:40], "flows": (t.get("links") or {}).get("flows") or [], "source": "history"})
            out["added"].append(c["id"])
    return out


def ref_log(root: Path, since: str = "", until: str = "") -> list:
    """Ticket ids named in commit messages, those after a closing word ("fixes #12", "close TOG-3") first,
    then the rest; newest first within each. For importing the closed tickets that history replay needs."""
    args = ["log", "--format=%B%x1e"] + (["--since", since] if since else []) + (["--until", until + " 23:59:59"] if until else [])
    strong, weak = [], []
    for msg in git(root, *args, "HEAD", check=False).split("\x1e"):
        hot = set()
        for m in _CLOSING.finditer(msg):
            hot |= refs(m.group(0))
        for r in sorted(refs(msg)):
            (strong if r in hot else weak).append(r)
    return list(dict.fromkeys(strong + weak))


def seen_refs(data_dir: Path, key: str) -> set:
    """Ids already asked about and not importable (a pull request that closed nothing, an open issue): not asked again."""
    f = _edir(data_dir) / ("%s.refs.json" % key)
    try:
        return set(json.loads(f.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def save_seen(data_dir: Path, key: str, seen: set) -> None:
    d = _edir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / ("%s.refs.json" % key)).write_text(json.dumps(sorted(seen)), encoding="utf-8")


def remove_case(data_dir: Path, key: str, cid: str) -> bool:
    with _LOCK:
        cs = cases(data_dir, key)
        keep = [x for x in cs if x["id"] != cid]
        _save(data_dir, key, keep)
    return len(keep) != len(cs)


def _norm(path: str, roots: list) -> str:
    p = str(path).strip().strip("`").replace("\\", "/")
    for r in roots:
        r = str(r).replace("\\", "/").rstrip("/") + "/"
        if p.startswith(r):
            p = p[len(r):]
    while p.startswith("./"):
        p = p[2:]
    return p.strip("/")


def predicted(text: str, roots: list) -> list:
    from .fixloop import plan_files
    from .orchestra import Orchestra
    named = list(plan_files(text, 40)) + [f for f, _ in Orchestra.FILE_LINE.findall(text or "")]
    return list(dict.fromkeys(x for x in (_norm(f, roots) for f in named) if x))


def _same(a: str, b: str) -> bool:
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def score(pred: list, gold: list) -> dict:
    hit = [g for g in gold if any(_same(p, g) for p in pred)]
    right = [p for p in pred if any(_same(p, g) for g in gold)]
    return {"recall": round(len(hit) / len(gold), 3) if gold else None, "precision": round(len(right) / len(pred), 3) if pred else 0.0,
            "hit": hit, "missed": [g for g in gold if g not in hit], "extra": [p for p in pred if p not in right]}


def results(data_dir: Path, key: str) -> list:
    f = _edir(data_dir) / "results.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("project") == key:
            out.append(d)
    return out


def batches(data_dir: Path, key: str, limit: int = 10) -> list:
    by = {}
    for r in results(data_dir, key):
        b = by.setdefault(r["batch"], {"batch": r["batch"], "ts": r["ts"], "agent": r.get("agent"), "model": r.get("model"), "rows": []})
        b["rows"].append(r)
    out = []
    for b in by.values():
        ok = [r for r in b["rows"] if r.get("recall") is not None]
        avg = lambda k: round(sum(r[k] for r in ok) / len(ok), 3) if ok else None  # noqa: E731
        src = {}
        for r in ok:
            src.setdefault(r.get("source") or "manual", []).append(r)
        part = {k: {"n": len(v), "recall": round(sum(r["recall"] for r in v) / len(v), 3), "precision": round(sum(r["precision"] for r in v) / len(v), 3)}
                for k, v in src.items()}
        out.append(dict(b, n=len(b["rows"]), scored=len(ok), recall=avg("recall"), precision=avg("precision"), sources=part))
    out.sort(key=lambda b: b["ts"], reverse=True)
    return out[:limit]


def _record(data_dir: Path, row: dict) -> None:
    with _LOCK:
        d = _edir(data_dir)
        d.mkdir(parents=True, exist_ok=True)
        with (d / "results.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


RUNNING = {}  # project key -> batch id while a batch runs


def run_evals(P, p: dict, agent: str, model, by: str, ids: list | None = None, wait: bool = False) -> dict:
    key = p["key"]
    cs = [c for c in cases(P.data_dir, key) if not ids or c["id"] in ids]
    if not cs:
        raise ValueError("还没有评测用例：验收通过的自动改动会自动成为用例，也可以手动添加")
    conf = load_config(P.data_dir)
    if agent not in conf:
        raise ValueError("没有这个智能体：%s" % agent)
    if RUNNING.get(key):
        raise ValueError("这个项目的评测还在跑（批次 %s）" % RUNNING[key])
    model = pick_model(conf[agent], "plan", model)
    batch = "eval-" + time.strftime("%m%d%H%M%S")
    RUNNING[key] = batch
    th = threading.Thread(target=_run_batch, args=(P, p, cs, agent, model, conf, by, batch), daemon=True)
    th.start()
    if wait:
        th.join()
    return {"batch": batch, "cases": len(cs)}


def _run_batch(P, p, cs, agent, model, conf, by, batch) -> None:
    try:
        for c in cs:
            try:
                row = _run_case(P, p, c, agent, model, conf, by, batch)
            except Exception as e:  # noqa: BLE001 - one broken case must not stop the batch
                row = {"case": c["id"], "error": "%s: %s" % (type(e).__name__, e), "recall": None, "precision": None}
            _record(P.data_dir, dict(row, project=p["key"], batch=batch, ts=now(), agent=agent, model=model, title=c["title"], ticket=c.get("ticket", ""),
                                     source=c.get("source", "manual")))
    finally:
        RUNNING.pop(p["key"], None)


def _run_case(P, p, c, agent, model, conf, by, batch) -> dict:
    st, root = P.store, P.root(p)
    wt = None
    if c.get("base"):
        if not _resolve(root, c["base"]):
            return {"case": c["id"], "error": "起点提交 %s 在仓库里找不到了" % c["base"][:10], "recall": None, "precision": None}
        wt = Path(P.data_dir) / "evals" / "wt" / ("%s-%s" % (p["key"], c["id"]))
        if wt.exists():
            git(root, "worktree", "remove", "--force", str(wt), check=False)
            shutil.rmtree(wt, ignore_errors=True)
        wt.parent.mkdir(parents=True, exist_ok=True)
        git(root, "worktree", "add", "--detach", str(wt), c["base"])
    try:
        fake = {"key": c.get("ticket") or "EVAL-" + c["id"], "title": c["title"], "body": c.get("body", ""), "type": "bug", "priority": "normal",
                "reporter": "", "links": {"flows": c.get("flows") or []}}
        prompt = build_prompt(st, p, fake, "plan")
        if wt:
            prompt = prompt.replace("（目录 %s）" % root, "（代码在 %s，是这张工单修改之前的版本，只看这里的代码；知识库和 tmh 工具仍在 %s）" % (wt, root), 1)
        run = st.create_run(p["id"], None, agent, "plan", by, prompt, "评测 %s：%s" % (c["id"], c["title"][:60]), batch=batch, model=model)
        st.update_run(run["id"], status="running", started=now(), workdir=str(wt or root))
        code, result = P.runner.invoke(run["id"], p, None, agent, conf, "plan", prompt, wt or root, model)
        st.update_run(run["id"], status="done" if code == 0 else "failed", ended=now(), exit_code=code, result=(result or "").strip())
        pred = predicted(result, [wt or root, root])
        return dict(score(pred, c["gold"]), case=c["id"], run=run["id"], predicted=pred[:40], gold=c["gold"], ok=code == 0)
    finally:
        if wt:
            git(root, "worktree", "remove", "--force", str(wt), check=False)
