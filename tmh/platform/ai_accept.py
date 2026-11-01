"""AI acceptance (按项目开关): on a project listed in autoflow.json "ai_accept" ("*" or true for all), the platform
signs and closes a ticket itself right after the automatic line committed its change, but only when the evidence
holds — the build and tests passed on that change, an independent diagnosis named no blocker and passed every
criterion one by one, and the evidence package is intact and bound to this change. Anything short of that, or a
person who took the ticket over, leaves it for people with the reason said on the ticket. Nothing is guessed.

A project listed in "ai_accept_observe" instead (and not in "ai_accept") runs the same checks in the shadow: AI says on
the ticket whether it would have accepted and why, signs nothing, and the person's later verdict is set against it."""
from __future__ import annotations

import json
from pathlib import Path

BY = "AI 验收"


def enabled(conf: dict, key: str) -> bool:
    v = (conf or {}).get("ai_accept")
    return v is True or v == "*" or (isinstance(v, (list, tuple)) and key in v)


def observing(conf: dict, key: str) -> bool:
    v = (conf or {}).get("ai_accept_observe")
    return not enabled(conf, key) and (v is True or v == "*" or (isinstance(v, (list, tuple)) and key in v))


def _data(e: dict) -> dict:
    d = e["data"]
    try:
        d = json.loads(d) if isinstance(d, str) else d
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def compare(st, t: dict, passed: bool, by: str):
    """A person's verdict after an AI verdict given in the shadow: say on the ticket whether the two agree, once."""
    if by == BY:
        return None
    last = None
    for e in st.events(t["id"]):
        d = _data(e)
        if "shadow" in d:
            last = d
        elif "shadow_compare" in d:
            last = None
    if not last:
        return None
    ai = bool(last["shadow"].get("would_accept"))
    agree = ai == bool(passed)
    c = {"run": last.get("run"), "ai": ai, "person": bool(passed), "agree": agree, "by": by}
    st.event(t["id"], BY, "flow", "%s：人%s，AI 当时%s" % ("AI 影子验收和人一致" if agree else "AI 影子验收和人不一致",
                                                      "验收通过" if passed else "退回", "本会验收通过" if ai else "本不会验收（%s）" % (last["shadow"].get("why") or "")),
             {"shadow_compare": c})
    return c


def shadow_stats(st, project_id: int) -> dict:
    """How the shadow verdicts on a project's tickets compared with people's: the evidence for switching AI acceptance on."""
    rows = st.q("SELECT t.num, e.data FROM events e JOIN tickets t ON t.id=e.ticket_id WHERE t.project_id=? AND e.kind='flow' "
                "AND e.data LIKE '%shadow%' ORDER BY e.id", (project_id,))
    shadow, seen = 0, []
    for r in rows:
        d = _data(r)
        if "shadow" in d:
            shadow += 1
        elif "shadow_compare" in d:
            seen.append(dict(d["shadow_compare"], num=r["num"]))
    return {"shadow": shadow, "compared": len(seen), "agree": sum(1 for c in seen if c.get("agree")),
            "disagree": [c["num"] for c in seen if not c.get("agree")][-10:]}


def why_not(data_dir: Path, rid: int, acs: list, real: bool = False) -> str:
    """Why the evidence behind run `rid` does not let AI accept against criteria `acs` ("" when it does). With `real`
    the criteria are proven by driving the app, so the diagnosis only has to not find one undone."""
    from .fixloop import verified
    v = verified(data_dir, rid)
    d = v.get("diagnosis") or {}
    if v.get("verification_current") is False:
        return "当前验证已失效"
    if v.get("check") != "pass":
        return "构建测试没通过" if v.get("check") == "fail" else "没跑构建测试（%s），没有实测证据" % (v.get("skip") or "未配置")
    if v.get("verdict") != "pass" or str(d.get("verdict") or "").lower() != "pass":
        return "独立诊断没有判通过"
    if d.get("blocking"):
        return "诊断还列着阻断项"
    if v.get("beyond_plan"):
        return "改了方案没列的文件"
    if not acs:
        return "没有验收标准可以对照"
    if any(a.get("open") for a in acs):
        return "还有待确认的验收标准"
    said = {str(a.get("id")): a for a in d.get("ac") or [] if isinstance(a, dict) and a.get("id")}
    missing = [] if real else [a["id"] for a in acs if a["id"] not in said]
    if missing:
        return "诊断没有逐条核对验收标准 %s" % "、".join(missing[:5])
    bad = [a["id"] for a in acs if (str((said.get(a["id"]) or {}).get("result") or "").lower() == "fail" if real
                                    else str(said[a["id"]].get("result") or "").lower() != "pass")]
    if bad:
        return "验收标准 %s 诊断没能确认做到" % "、".join(bad[:5])
    return ""


KEPT = "必须保持项：构建测试在测试机上通过，由自动测试证明"
KEPT_BUILD = "必须保持项：测试机上构建通过（这个项目没跑自动测试，只证明改后能构建）"


def committed(snap: dict, rid: int) -> str:
    """The commit the automatic line made of run `rid`: the delivery binding's, else the adoption of that run's branch."""
    adopted = snap.get("adopted") or {}
    return ((snap.get("change") or {}).get("commit") or
            (adopted.get("commit") or "" if str(adopted.get("branch") or "").endswith("-r%d" % rid) else ""))


def after_commit(P, p: dict, tid: int, rid: int) -> dict:
    """Called once the automatic line committed run `rid` of ticket `tid`."""
    conf = P.flow.autoflow()
    shadow = observing(conf, p["key"])
    if not enabled(conf, p["key"]) and not shadow:
        return {"accepted": False, "why": "这个项目没开 AI 验收"}
    st = P.store
    t = st.ticket(tid)
    from . import browser_verify, epic, signoff
    from .errors import ApiError
    s = signoff.state(P.data_dir, t["key"])
    acs = (s.get("snapshot") or {}).get("ac") or []
    fixed = st.one("SELECT name FROM sqlite_master WHERE type='table' AND name='code_candidates'") and \
        st.one("SELECT id FROM code_candidates WHERE ticket_id=? LIMIT 1", (tid,))
    why = ("有人接手了这张工单" if P.flow.held(tid) else
           "工单不在待验收" if t["status"] != "verify" else
           "这张工单走固定候选，由人复核" if fixed else
           epic.refuse(t, "accept") or
           ("证据包还没生成" if not s.get("packed") else "") or
           ("证据包被改动过：%s" % s.get("problem") if not s.get("intact") else "") or
           ("证据包对应的不是这次改动" if ((s.get("snapshot") or {}).get("change") or {}).get("run") != rid else "") or
           why_not(P.data_dir, rid, acs, real=bool(browser_verify.conf(P.data_dir, p["key"]))))
    seen = {}
    if not why and browser_verify.conf(P.data_dir, p["key"]):
        commit = committed(s.get("snapshot") or {}, rid)
        # what must keep working is proven by the build and tests that passed above, as at the client's sign-off
        page = [a for a in acs if not a.get("keep")]
        res = browser_verify.verify(P, p, t, rid, page, commit=commit) if page else \
            {"result": "unverified", "why": "没有要在页面上实测的验收标准", "ac": []}
        seen = {i["id"]: i for i in res.get("ac") or []}
        tested = any(g.get("id") == "test" and g.get("state") == "pass" for g in (s.get("snapshot") or {}).get("gates") or [])
        seen.update({a["id"]: {"id": a["id"], "result": "pass", "how": KEPT if tested else KEPT_BUILD} for a in acs if a.get("keep")} if page else {})
        why = ("" if res["result"] == "pass" and all((seen.get(a["id"]) or {}).get("result") == "pass" for a in acs) else
               "页面实测复现了问题（%s）" % "、".join(k for k, i in seen.items() if i["result"] == "fail") if res["result"] == "fail" else
               "页面实测没能证明%s" % ("：" + res["why"] if res.get("why") else "（%s 未验证）" % "、".join(
                   k for k, i in seen.items() if i["result"] != "pass")))
        s = signoff.state(P.data_dir, t["key"])
        why = why or ("证据包被改动过：%s" % s.get("problem") if not s.get("intact") else "")
    if why and shadow:
        st.event(tid, BY, "flow", "AI 影子验收：本不会验收（%s）。观察模式，留给人验收" % why,
                 {"run": rid, "shadow": {"would_accept": False, "why": why}})
        return {"accepted": False, "shadow": True, "would_accept": False, "why": why}
    if why:
        st.event(tid, BY, "flow", "AI 没有验收：%s，留给人验收" % why, {"run": rid})
        return {"accepted": False, "why": why}
    from .fixloop import verified
    said = {str(a.get("id")): a for a in (verified(P.data_dir, rid).get("diagnosis") or {}).get("ac") or [] if isinstance(a, dict)}
    basis = {"run": rid, "check": "pass", "diagnosis": "pass",
             "ac": {a["id"]: str((seen.get(a["id"]) or said.get(a["id"]) or {}).get("how") or "")[:300] for a in acs}}
    if seen:
        basis["real"] = "pass"
    note = "AI 验收通过：构建测试通过，独立诊断没有阻断项，%s %d 条验收标准（%s）都做到了" % (
        "在页面上逐条实测" if seen else "逐条核对", len(acs), "、".join(a["id"] for a in acs))
    if shadow:
        st.event(tid, BY, "flow", "AI 影子验收：本会验收通过（%s）。观察模式不签收，留给人验收" % note,
                 {"run": rid, "shadow": {"would_accept": True, "why": "", "basis": basis}})
        return {"accepted": False, "shadow": True, "would_accept": True, "why": ""}
    try:
        with signoff.verification_guard(P, t["key"]):
            sealed = signoff._record_accept(P, t, BY, True, note, via=BY, basis=basis)
            st.event(tid, BY, "accept", note, dict({"result": "pass", "ai": True, "run": rid}, **({"evidence": sealed} if sealed else {})))
            st.update_ticket(tid, BY, status="closed")
            P.flow.accepted(p, st.ticket(tid), True, note, BY)
    except (ApiError, ValueError) as e:
        why = getattr(e, "msg", None) or str(e)
        st.event(tid, BY, "flow", "AI 没有验收：%s，留给人验收" % why, {"run": rid})
        return {"accepted": False, "why": why}
    return {"accepted": True, "evidence": sealed}
