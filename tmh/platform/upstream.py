"""External pull requests: a change we propose to someone else's project, tracked until a maintainer merges or
closes it.

A merge by a maintainer who does not know us is third-party acceptance, harder evidence than any internal sign-off;
their review comments are real rework and their reasons for closing are real lessons. So an external PR is an
ordinary ticket with `links.upstream` = {"system": "github", "repo", "issue", "pr", "url"} and everything that
happens to it goes into the ticket's evidence package (tmh/evidence.py): the draft, the person who approved
submitting it, every state change, every review round with its text, and the outcome.

Submitting is publishing under a person's account, so it is gated: a draft (title, body, branch) is approved by a
person, the approval names the draft's hash, and only that exact draft can be submitted. Before approving and
again before submitting, the ticket's verification gates (tmh/platform/gates.py) are read: a failed gate stops the
PR, an unknown one needs the approver's written reason. Without `confirm` the
adapter only records what it would send.

The tracker's own state is in <data>/upstream/<KEY>.json (the last status read from GitHub); metrics over all
external PRs replace "person-days saved": merge rate, review rounds, time to merge, maintainer commits on top of
ours, reasons for closing, AI cost per merged PR. All of it can be checked on GitHub by anyone.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from statistics import median

from .. import evidence as ev
from .errors import ApiError

REASONS = [("direction", "方向不对"), ("style", "风格或规范"), ("scope", "范围太大"), ("duplicate", "重复或已修"),
           ("stale", "没人理、过期"), ("policy", "项目规则（如不收 AI 贡献）"), ("other", "其他")]
STATES = {"draft": "草稿待审", "approved": "已批准提交", "open": "等评审", "changes": "要求修改", "merged": "已合并", "closed": "已关闭未合并"}
ASK = ("CHANGES_REQUESTED", "COMMENTED")


def client(repo: str, dry_run: bool = True):
    """The GitHub adapter for one repository; GITHUB_TOKEN when set (writes need it), anonymous reads otherwise."""
    from ..integrations.github import GitHub
    conf = {"repo": repo}
    if os.environ.get("GITHUB_TOKEN"):
        conf["auth"] = {"type": "bearer", "token_env": "GITHUB_TOKEN"}
    return GitHub("github", conf, dry_run=dry_run)


def _file(data_dir: Path, key: str) -> Path:
    return Path(data_dir) / "upstream" / ("%s.json" % key.upper())


def load(data_dir: Path, key: str) -> dict:
    f = _file(data_dir, key)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        return {}


def _save(data_dir: Path, key: str, d: dict) -> None:
    f = _file(data_dir, key)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def _rec(P, t: dict, kind: str, by: str, data: dict) -> dict:
    from .signoff import _add, epath
    return _add(epath(P.data_dir, t["key"]), kind, by, data)


def _draft_hash(d: dict) -> str:
    return hashlib.sha256(ev.canon({k: d.get(k, "") for k in ("repo", "head", "base", "title", "body")}).encode("utf-8")).hexdigest()


def link(P, t: dict, by: str, repo: str, issue: str = "", pr: str = "") -> dict:
    repo = (repo or "").strip().strip("/")
    if not re.match(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$", repo):
        raise ApiError(400, "仓库写成 所有者/仓库名，如 apache/ofbiz-framework")
    up = dict((t.get("links") or {}).get("upstream") or {}, system="github", repo=repo)
    if issue:
        up["issue"] = str(issue).lstrip("#")
    if pr:
        up["pr"] = str(pr).lstrip("#")
        up["url"] = "https://github.com/%s/pull/%s" % (repo, up["pr"])
    links = dict(t.get("links") or {}, upstream=up)
    P.store.update_ticket(t["id"], by, links=links)
    P.store.event(t["id"], by, "link", "关联上游 %s%s%s" % (repo, " issue #" + up["issue"] if up.get("issue") else "", " PR #" + up["pr"] if up.get("pr") else ""))
    return up


def draft(P, t: dict, by: str, title: str, body: str, head: str, base: str) -> dict:
    up = (t.get("links") or {}).get("upstream") or {}
    if not up.get("repo"):
        raise ApiError(409, "先关联上游仓库")
    if up.get("pr"):
        raise ApiError(409, "已经提交过 PR #%s" % up["pr"])
    d = {"repo": up["repo"], "title": (title or "").strip()[:200], "body": (body or "").strip()[:20000],
         "head": (head or "").strip(), "base": (base or "").strip() or "trunk"}
    if not d["title"] or not d["head"]:
        raise ApiError(400, "PR 要有标题和分支（head，如 auntunt:fix-order-permission）")
    d["hash"] = _draft_hash(d)
    st = load(P.data_dir, t["key"])
    st.update({"draft": d, "approved": None, "state": "draft"})
    _save(P.data_dir, t["key"], st)
    _rec(P, t, "upstream_draft", by, d)
    P.store.event(t["id"], by, "evidence", "起草上游 PR：%s（待人审）" % d["title"])
    return st


def gate_check(P, t: dict, note: str = "") -> str:
    """The verification gates must pass before a PR goes upstream: any gate that failed stops it; gates that could
    not tell (or no evidence package at all) need the approver's written reason. Returns the gate state."""
    from . import gates as G
    from .signoff import state
    s = state(P.data_dir, t["key"])
    gs = s.get("gates")
    if gs is None:
        if len((note or "").strip()) < 4:
            raise ApiError(409, "这单没有带验证门的证据包。先让改动走完验证门，或在批准时写明为什么不需要")
        return "none"
    st = G.overall(gs)
    if st == G.FAIL:
        raise ApiError(409, "验证门没过，不能提交上游：%s" % G.summary([g for g in gs if g["state"] == G.FAIL]))
    if st == G.UNKNOWN and len((note or "").strip()) < 4:
        raise ApiError(409, "有验证门结果未知（%s）。补齐，或在批准时写明为什么仍然提交" % "、".join(g["name"] for g in gs if g["state"] == G.UNKNOWN))
    return st


def approve(P, t: dict, by: str, note: str = "") -> dict:
    from .signoff import human
    if not human(by):
        raise ApiError(403, "提交上游 PR 要由人批准")
    st = load(P.data_dir, t["key"])
    d = st.get("draft")
    if not d:
        raise ApiError(409, "还没有 PR 草稿")
    gst = gate_check(P, t, note)
    st["approved"] = {"by": by, "at": ev.now(), "hash": d["hash"], "note": (note or "")[:500], "gates": gst}
    st["state"] = "approved"
    _save(P.data_dir, t["key"], st)
    _rec(P, t, "upstream_approve", by, st["approved"])
    P.store.event(t["id"], by, "evidence", "批准提交上游 PR" + ("：" + note if note else ""))
    return st


def submit(P, t: dict, by: str, confirm: bool = False) -> dict:
    """Open the approved draft upstream. Only the exact draft a person approved; without confirm, a dry run."""
    st = load(P.data_dir, t["key"])
    d, a = st.get("draft"), st.get("approved")
    if not d or not a:
        raise ApiError(409, "PR 草稿还没有人批准，不能提交")
    if a["hash"] != _draft_hash(d) or a["hash"] != d.get("hash"):
        raise ApiError(409, "草稿在批准后改过，要重新批准")
    gate_check(P, t, a.get("note", ""))  # a re-fix after approval may have broken a gate
    if confirm and not os.environ.get("GITHUB_TOKEN"):
        raise ApiError(409, "没有设置 GITHUB_TOKEN，不能真的提交")
    r = client(d["repo"], dry_run=not confirm).open_pr(d["head"], d["base"], d["title"], d["body"])
    if r.get("dry_run"):
        return {"dry_run": True, "would_send": {k: d[k] for k in ("repo", "head", "base", "title")}}
    link(P, P.store.ticket(t["id"]), by, d["repo"], (t["links"].get("upstream") or {}).get("issue", ""), str(r["number"]))
    st["state"] = "open"
    st["submitted"] = {"by": by, "at": ev.now(), "number": r["number"], "url": r["url"]}
    _save(P.data_dir, t["key"], st)
    _rec(P, t, "upstream_submit", by, st["submitted"])
    return st


def _state(s: dict) -> str:
    if s["state"] in ("merged", "closed"):
        return s["state"]
    asks = [r for r in s["reviews"] if r["by"] != s["author"] and r["state"] in ASK]
    if asks:
        last_ask = max(r["at"] for r in asks)
        mine = [c for c in s["commits"] if c["author"] == s["author"] and c["at"] > last_ask]
        if not mine:
            return "changes"
    return "open"


def summarize(s: dict) -> dict:
    """The numbers one PR contributes: rounds, maintainer commits on top, hours to merge."""
    others = [r for r in s["reviews"] if r["by"] != s["author"]]
    rounds = sum(1 for r in others if r["state"] in ASK)
    theirs = [c for c in s["commits"] if c["author"] and c["author"] != s["author"]]
    hours = None
    if s.get("merged") and s.get("created"):
        try:
            a, b = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in (s["created"], s["merged"]))
            hours = round((b - a).total_seconds() / 3600, 1)
        except ValueError:
            pass
    return {"rounds": rounds, "maintainer_commits": len(theirs), "hours_to_merge": hours, "approved_by": sorted({r["by"] for r in others if r["state"] == "APPROVED"})}


def sync(P, t: dict, by: str = "平台", status: dict | None = None) -> dict:
    """Read the PR from GitHub, record what changed in the evidence package, and move the ticket when it ends."""
    up = (t.get("links") or {}).get("upstream") or {}
    if not up.get("pr"):
        raise ApiError(409, "这张工单还没有上游 PR")
    s = status or client(up["repo"]).pr_status(up["pr"])
    st = load(P.data_dir, t["key"])
    last = st.get("last") or {}
    new_state = _state(s)
    changed = []
    if new_state != st.get("state"):
        changed.append(("upstream_state", {"from": st.get("state", ""), "to": new_state, "ci": s["ci"]["state"]}))
    seen = {(r["by"], r["at"]) for r in last.get("reviews") or []}
    for r in s["reviews"]:
        if (r["by"], r["at"]) not in seen and r["by"] != s["author"]:
            changed.append(("upstream_review", r))
    if (last.get("ci") or {}).get("state") != s["ci"]["state"] and s["ci"]["state"] != "none":
        changed.append(("upstream_ci", s["ci"]))
    for kind, data in changed:
        _rec(P, t, kind, "GitHub", data)
    st.update({"last": s, "state": new_state, "synced": ev.now(), "summary": summarize(s)})
    if new_state in ("merged", "closed") and not st.get("outcome"):
        st["outcome"] = {"state": new_state, "at": s["merged"] or s["closed"], "by": s["merged_by"], "reason": "", **st["summary"]}
        _rec(P, t, "upstream_outcome", "GitHub", st["outcome"])
        fresh = P.store.ticket(t["id"])
        if new_state == "merged":
            who = "%s（上游维护者）" % (s["merged_by"] or "维护者")
            P.store.event(t["id"], who, "accept", "上游合并了 PR #%s：%s" % (up["pr"], s["url"]), {"result": "pass", "via": "上游合并"})
            if fresh["status"] != "closed":
                P.store.update_ticket(t["id"], who, status="closed")
        else:
            P.store.event(t["id"], "GitHub", "reject", "上游关闭了 PR #%s，没有合并；请补记原因" % up["pr"], {"result": "fail", "via": "上游关闭"})
            if fresh["status"] == "verify":
                P.store.update_ticket(t["id"], "GitHub", status="doing")
    elif changed:
        P.store.event(t["id"], "GitHub", "sync", "上游 PR #%s：%s" % (up["pr"], STATES.get(new_state, new_state)))
    _save(P.data_dir, t["key"], st)
    return view(P, t)


def outcome_reason(P, t: dict, by: str, reason: str, note: str = "") -> dict:
    if reason not in dict(REASONS):
        raise ApiError(400, "原因只能是：" + "、".join("%s(%s)" % kv for kv in REASONS))
    st = load(P.data_dir, t["key"])
    if not st.get("outcome"):
        raise ApiError(409, "PR 还没有结局")
    st["outcome"]["reason"], st["outcome"]["note"] = reason, (note or "")[:1000]
    _save(P.data_dir, t["key"], st)
    _rec(P, t, "upstream_reason", by, {"reason": reason, "note": note})
    return st


def view(P, t: dict) -> dict:
    st = load(P.data_dir, t["key"])
    up = (P.store.ticket(t["id"]).get("links") or {}).get("upstream") or {}
    last = st.get("last") or {}
    return {"upstream": up, "state": st.get("state", ""), "label": STATES.get(st.get("state", ""), "未开始"), "draft": st.get("draft"),
            "approved": st.get("approved"), "submitted": st.get("submitted"), "synced": st.get("synced"), "summary": st.get("summary"),
            "outcome": st.get("outcome"), "ci": (last.get("ci") or {}).get("state"),
            "reviews": [r for r in last.get("reviews") or [] if r["by"] != last.get("author")]}


def metrics(P, p: dict, month: str = "") -> dict:
    """What replaces "person-days saved": numbers anyone can check on GitHub."""
    rows = []
    pts = {}
    for x in P.store.q("SELECT ticket_id, -SUM(delta) AS n FROM points WHERE project_id=? AND delta<0 AND ticket_id IS NOT NULL GROUP BY ticket_id", (p["id"],)):
        pts[x["ticket_id"]] = x["n"]
    for t in P.store.tickets(project_id=p["id"], limit=100000):
        up = (t.get("links") or {}).get("upstream") or {}
        if not up.get("pr"):
            continue
        st = load(P.data_dir, t["key"])
        last = st.get("last") or {}
        if month and not ((last.get("created") or "").startswith(month) or ((st.get("outcome") or {}).get("at") or "").startswith(month)):
            continue
        rows.append({"key": t["key"], "title": t["title"], "repo": up["repo"], "pr": up["pr"], "url": up.get("url", ""), "state": st.get("state", ""),
                     "label": STATES.get(st.get("state", ""), ""), "summary": st.get("summary") or {}, "outcome": st.get("outcome"),
                     "lines": (last.get("additions") or 0) + (last.get("deletions") or 0), "points": pts.get(t["id"], 0)})
    merged = [r for r in rows if r["state"] == "merged"]
    ended = [r for r in rows if r["state"] in ("merged", "closed")]
    hrs = [r["summary"].get("hours_to_merge") for r in merged if r["summary"].get("hours_to_merge") is not None]
    reasons = {}
    for r in ended:
        if r["state"] == "closed":
            k = (r["outcome"] or {}).get("reason") or "unknown"
            reasons[k] = reasons.get(k, 0) + 1
    rl = dict(REASONS, unknown="未补记")
    return {"rows": rows, "submitted": len(rows), "merged": len(merged), "closed": len(ended) - len(merged), "open": len(rows) - len(ended),
            "merge_rate": round(len(merged) * 100 / len(ended), 1) if ended else None,
            "rounds_avg": round(sum(r["summary"].get("rounds", 0) for r in merged) / len(merged), 1) if merged else None,
            "hours_to_merge_median": round(median(hrs), 1) if hrs else None,
            "maintainer_edited": sum(1 for r in merged if r["summary"].get("maintainer_commits")),
            "reasons": [{"key": k, "label": rl.get(k, k), "n": n} for k, n in sorted(reasons.items(), key=lambda kv: -kv[1])],
            "points_per_merged": round(sum(r["points"] for r in merged) / len(merged), 1) if merged else None}
