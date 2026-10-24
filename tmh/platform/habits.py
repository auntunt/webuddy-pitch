"""Development-habit signals derived read-only from the platform store (G9).

What this is: an *observation layer* over the data the platform already keeps
(tickets, runs, events, points, knowledge revisions). It answers "how does this
person / this team actually work" — which modes they use, which ticket types and
projects they touch, where acceptance comes back, what they write knowledge
about, what reviewers keep raising — with explicit sample sizes.

What this is **not**: a performance review. Sample size can be small, logging
is incomplete on a single-account deployment, and event semantics drifted over
time (see docs/design/habit-logging-v0.md). Rates below the sample floor are
deliberately withheld instead of being presented as facts — the same discipline
as ``learn.impact``'s ``fair`` flag.

Privacy contract (enforced by the code, not only by docs):

* **Read-only.** Only ``SELECT`` statements. Nothing here creates, migrates or
  writes a table, and no counter is bumped by looking at habits.
* **No raw text leaves this module.** Prompts, comments and acceptance notes are
  reduced to length + keyword category + a truncated one-way SHA-256 hash.
  Names are hidden by default (``redact=True``); even with ``redact=False`` only
  the identity of the person whose view it is may appear, never what they typed.
* **Team view has no people.** Team output aggregates per project and reports a
  participant *count*, never a per-person row.
"""
from __future__ import annotations

import hashlib

# Fewer than this many observations on the relevant side and a percentage says more
# about luck than about habits (same floor as learn.MIN_N / impact.fair).
MIN_SAMPLE = 5

MODES = ("ask", "analyze", "plan", "fix", "verify", "kb", "understand")
OTHER = "其他"
UNKNOWN_MODE = "未知"

# Keyword categories only: the note/prompt itself is never returned or stored.
REWORK_CATEGORIES = {
    "功能正确性": ("功能", "逻辑", "不对", "错误", "异常", "崩溃", "失败", "报错", "结果不符", "没生效"),
    "性能与稳定": ("性能", "慢", "超时", "卡顿", "内存", "稳定", "并发", "延迟"),
    "安全与权限": ("安全", "权限", "越权", "注入", "泄露", "审计", "登录"),
    "兼容与环境": ("兼容", "环境", "部署", "配置", "版本", "依赖", "浏览器", "操作系统"),
    "文档与说明": ("文档", "说明", "注释", "描述", "文案", "提示语"),
    "测试与证据": ("测试", "用例", "证据", "验证", "复现", "断言"),
    "流程与需求": ("流程", "需求", "评审", "确认", "沟通", "验收标准", "范围"),
}
PROMPT_CATEGORIES = {
    "问题定位": ("报错", "异常", "复现", "定位", "日志", "堆栈", "原因", "bug", "崩溃"),
    "方案设计": ("方案", "设计", "重构", "架构", "计划", "步骤", "权衡"),
    "改码执行": ("修改", "实现", "修复", "改成", "补充", "替换", "改造"),
    "验证测试": ("测试", "验证", "断言", "回归", "覆盖", "通过"),
    "知识整理": ("知识", "文档", "总结", "梳理", "规范", "页面"),
    "需求理解": ("需求", "验收", "用户", "客户", "目标", "范围"),
}
REVIEW_CATEGORIES = REWORK_CATEGORIES  # acceptance notes are classified the same way

REDACT = True  # default; raw identities never leave unless a caller asks for its own view
_RAW_TEXT_POLICY = "提示词/评论/验收备注只以长度、关键词类别与单向哈希出现，原文不出本模块"


def _classify(text, categories):
    """Map free text to keyword categories; the text itself is used only here."""
    text = (text or "").lower()
    hits = [name for name, words in categories.items() if any(w.lower() in text for w in words)]
    return hits or [OTHER]


def _bucket(length):
    if length < 120:
        return "短"
    if length < 600:
        return "中"
    return "长"


def _fingerprint(prompt):
    """One-way short hash + length + length bucket + keyword categories. Never the prompt."""
    raw = (prompt or "").encode("utf-8")
    return {
        "hash": hashlib.sha256(raw).hexdigest()[:12],
        "length": len(prompt or ""),
        "bucket": _bucket(len(prompt or "")),
        "categories": _classify(prompt, PROMPT_CATEGORIES),
    }


def _events(store, kind, project_id=None):
    sql = ("SELECT e.*, t.project_id AS tp FROM events e JOIN tickets t ON t.id=e.ticket_id "
           "WHERE e.kind IN (%s)" % ",".join("?" * len(kind)))
    args = list(kind)
    if project_id is not None:
        sql += " AND t.project_id=?"
        args.append(project_id)
    return store.q(sql + " ORDER BY e.id", args)


def _note_of(event):
    """The human note behind an acceptance event, as text, for classification only."""
    data = event.get("data") or {}
    if isinstance(data, dict) and "note" in data:
        return str(data.get("note") or "")  # an explicit empty note stays empty
    body = event.get("body") or ""
    for prefix in ("甲方退回：", "验收不通过：", "验收通过：", "甲方签收："):
        if body.startswith(prefix):
            rest = body[len(prefix):]
            return rest.split("；", 1)[0] if prefix in ("甲方签收：", "验收通过：") else rest
    return body


def _ratios(counts):
    total = sum(counts.values())
    return {k: round(v / total, 3) for k, v in sorted(counts.items())} if total else {}


def personal(store, author, project_id=None, *, redact=REDACT, min_sample=MIN_SAMPLE):
    """One person's habit signals, derived from their runs / their tickets' reviews.

    ``author`` matches ``runs.author`` and ``knowledge_revisions.author``. Counts are
    always returned; shares are withheld below ``min_sample`` so a handful of runs is
    not dressed up as a pattern. Raw prompt/comment/acceptance text is never returned.
    """
    author = author or ""
    from .learning_experiment_views import unmanaged_run_clause
    sql = ("SELECT r.id, r.mode, r.status, r.retry_of, r.ticket_id, r.prompt, r.project_id, p.key AS pkey "
           "FROM runs r JOIN projects p ON p.id=r.project_id WHERE r.author=? AND " + unmanaged_run_clause(store))
    args = [author]
    if project_id is not None:
        sql += " AND r.project_id=?"
        args.append(project_id)
    runs = store.q(sql + " ORDER BY r.id", args)

    ticket_ids = sorted({r["ticket_id"] for r in runs if r["ticket_id"]})
    tickets = [store.ticket(tid) for tid in ticket_ids]
    tickets = [t for t in tickets if t]
    modes = {}
    domains = {}
    failed = retries = 0
    for r in runs:
        mode = r["mode"] if r["mode"] in MODES else (r["mode"] or UNKNOWN_MODE)
        modes[mode] = modes.get(mode, 0) + 1
        domains[r["pkey"]] = domains.get(r["pkey"], 0) + 1
        failed += 1 if r["status"] == "failed" else 0
        retries += 1 if r["retry_of"] else 0

    ticket_types = {}
    for t in tickets:
        ticket_types[t["type"]] = ticket_types.get(t["type"], 0) + 1

    fingerprints = [_fingerprint(r["prompt"]) for r in runs if (r["prompt"] or "").strip()]

    # Rework signal belongs to the tickets the person worked on: a rejection is about
    # the change, not about who wrote the note.
    own_tickets = set(ticket_ids)
    relevant = [e for e in _events(store, ("accept", "reject"), project_id) if e.get("ticket_id") in own_tickets]
    rejects = [e for e in relevant if e.get("kind") == "reject"]
    rework_reasons = {}
    for e in rejects:
        note = _note_of(e)
        if not note.strip():
            continue
        for cat in _classify(note, REWORK_CATEGORIES):
            rework_reasons[cat] = rework_reasons.get(cat, 0) + 1

    notes = []
    classified_notes = 0
    for e in relevant:  # acceptance notes, accepted or rejected: what reviewers keep raising
        note = _note_of(e)
        if not note.strip():
            continue
        classified_notes += 1
        notes.extend(_classify(note, REVIEW_CATEGORIES))
    review_focus = {}
    for cat in notes:
        review_focus[cat] = review_focus.get(cat, 0) + 1

    kb_runs = sum(1 for r in runs if r["mode"] in ("kb", "knowledge"))
    if project_id is None:
        written = store.one("SELECT COUNT(*) n FROM knowledge_revisions WHERE author=?", (author,))["n"]
    else:
        written = store.one("SELECT COUNT(*) n FROM knowledge_revisions WHERE author=? AND project_id=?", (author, project_id))["n"]

    sample = {"runs": len(runs), "tickets": len(tickets), "reviews": len(relevant), "fingerprints": len(fingerprints)}
    fair = sample["runs"] >= min_sample
    if not fair:
        notes_block = ["个人运行样本 %d 次，少于 %d 次，比例不出（只给计数），不作结论"
                       % (sample["runs"], min_sample)]
    elif not relevant:
        notes_block = ["该成员暂无验收记录，返工与审查关注点为空"]
    else:
        notes_block = []
    out = {
        "view": "personal",
        "privacy": {"redact": bool(redact), "contains_raw_text": False, "raw_text_policy": _RAW_TEXT_POLICY},
        "sample": sample,
        "fair": fair,
        "notes": notes_block,
        "modes": dict(sorted(modes.items())),
        "ticket_types": dict(sorted(ticket_types.items())),
        "domains": dict(sorted(domains.items())),
        "rework": {
            "accept_fail": len(rejects),
            "failed_runs": failed,
            "retry_runs": retries,
            "reasons": dict(sorted(rework_reasons.items())),
            "reasons_share": _ratios(rework_reasons) if len(rejects) >= min_sample else None,
        },
        "prompt_fingerprints": {
            "total": len(fingerprints),
            "by_bucket": _counts(f["bucket"] for f in fingerprints),
            "by_category": _counts(cat for f in fingerprints for cat in f["categories"]),
            "hashes": fingerprints[:100],
            "notes": "只给长度/长度档/关键词类别与 sha256 前 12 位，不存也不返回原文",
        },
        "knowledge_writing": {"kb_runs": kb_runs, "pages_written": int(written or 0)},
        "review_focus": {"notes_classified": classified_notes, "categories": dict(sorted(review_focus.items()))},
    }
    out["modes_share"] = _ratios(modes) if fair else None
    # ticket-type proportions need their own ticket-level sample, not just run volume
    out["ticket_types_share"] = _ratios(ticket_types) if len(tickets) >= min_sample else None
    if not redact:
        out["person"] = author
    return out


def team(store, project_id=None, *, min_sample=MIN_SAMPLE):
    """Anonymous team view, aggregated per project. No per-person row, no names.

    ``fair`` follows ``learn.impact``: under ``min_sample`` tickets *and* decisions the
    view still reports counts but withholds shares; ``notes`` says what is missing.
    """
    from .learning_experiment_views import unmanaged_run_clause
    sql = ("SELECT r.mode, r.status, r.author, r.project_id, r.ticket_id, r.retry_of, p.key AS pkey "
           "FROM runs r JOIN projects p ON p.id=r.project_id WHERE " + unmanaged_run_clause(store))
    args = []
    if project_id is not None:
        sql += " AND r.project_id=?"
        args.append(project_id)
    runs = store.q(sql, args)

    tsql, targs = "SELECT * FROM tickets WHERE 1=1", []
    if project_id is not None:
        tsql += " AND project_id=?"
        targs.append(project_id)
    tickets = store.q(tsql, targs)

    modes, ticket_types, projects = {}, {}, {}
    for r in runs:
        mode = r["mode"] if r["mode"] in MODES else (r["mode"] or UNKNOWN_MODE)
        modes[mode] = modes.get(mode, 0) + 1
        projects[r["pkey"]] = projects.get(r["pkey"], 0) + 1
    for t in tickets:
        ticket_types[t["type"]] = ticket_types.get(t["type"], 0) + 1

    decisions = _events(store, ("accept", "reject"), project_id)
    rejects = [e for e in decisions if e.get("kind") == "reject"]
    review_focus = {}
    classified_notes = 0
    for e in decisions:
        note = _note_of(e)
        if not note.strip():  # an empty acceptance note says nothing about focus
            continue
        classified_notes += 1
        for cat in _classify(note, REVIEW_CATEGORIES):
            review_focus[cat] = review_focus.get(cat, 0) + 1
    rework_reasons = {}
    for e in rejects:
        note = _note_of(e)
        if not note.strip():
            continue
        for cat in _classify(note, REWORK_CATEGORIES):
            rework_reasons[cat] = rework_reasons.get(cat, 0) + 1

    if project_id is None:
        pages = store.one("SELECT COUNT(*) n FROM knowledge_revisions")["n"]
    else:
        pages = store.one("SELECT COUNT(*) n FROM knowledge_revisions WHERE project_id=?", (project_id,))["n"]

    sample = {
        "tickets": len(tickets),
        "runs": len(runs),
        "decisions": len(decisions),
        "participants": len({r["author"] for r in runs if (r["author"] or "").strip()}),
    }
    fair = sample["tickets"] >= min_sample and sample["decisions"] >= min_sample
    notes = []
    if sample["tickets"] < min_sample:
        notes.append("工单样本 %d 张，少于 %d 张，团队比例不出（只给计数）" % (sample["tickets"], min_sample))
    if sample["decisions"] < min_sample:
        notes.append("验收记录 %d 条，少于 %d 条，返工率不出（只给计数）" % (sample["decisions"], min_sample))
    if fair:
        notes.append("样本达到下限：比例可作团队习惯参考，仍不是绩效结论")
    out = {
        "view": "team",
        "privacy": {"redact": True, "contains_raw_text": False, "per_person": False, "raw_text_policy": _RAW_TEXT_POLICY},
        "sample": sample,
        "fair": fair,
        "notes": notes,
        "min_sample": min_sample,
        "modes": dict(sorted(modes.items())),
        "ticket_types": dict(sorted(ticket_types.items())),
        "projects": dict(sorted(projects.items())),
        "knowledge_pages": int(pages or 0),
        "rework": {"accept_fail": len(rejects), "reasons": dict(sorted(rework_reasons.items()))},
        "review_focus": {"notes_classified": classified_notes, "categories": dict(sorted(review_focus.items()))},
        "modes_share": _ratios(modes) if fair else None,
        "ticket_types_share": _ratios(ticket_types) if fair else None,
        "review_focus_share": _ratios(review_focus) if fair else None,
        "rework_rate": round(len(rejects) / len(decisions), 3) if fair and decisions else None,
    }
    return out


def _counts(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def available(store) -> dict:
    """Cheap, read-only readiness probe: which habit sources exist and how big they are."""
    def n(sql, args=()):
        row = store.one(sql, args)
        return int(row["n"]) if row else 0
    from .learning_experiment_views import unmanaged_run_clause
    return {
        "runs": n("SELECT COUNT(*) n FROM runs r WHERE " + unmanaged_run_clause(store)),
        "tickets": n("SELECT COUNT(*) n FROM tickets"),
        "acceptance_events": n("SELECT COUNT(*) n FROM events WHERE kind IN ('accept','reject')"),
        "knowledge_revisions": n("SELECT COUNT(*) n FROM knowledge_revisions"),
        "min_sample": MIN_SAMPLE,
        "raw_text_policy": _RAW_TEXT_POLICY,
    }
