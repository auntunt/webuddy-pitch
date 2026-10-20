"""The knowledge base as the one source of project knowledge: read it as written, ask people, write their answers back.

Nothing here summarizes or rewrites a page. Every extra LLM pass over the
knowledge loses information, and a second copy (a digest, a skill) drifts from
the original, so agents and people read the page files themselves:

- `read`   page files verbatim, whole pages only, in the order asked.
- `chain`  for a request: the business chain it touches, domain → flows → tables,
           as the original pages, plus the open questions and glossary rows on them.
- `ask` / `answer`  the human loop. Questions go to open-questions.md; a person's
           answer is written word for word into the page under “业务方答复” and
           into the question row, and the page is queued for revision. A page only
           becomes 已确认 when a person confirms it (`tmh kb confirm`).
- `triage` a feasibility pre-check of a request (see triage below).
- `metrics` how much the pre-check saved people: answered without a person,
           overruled later, handoffs per week, how long business answers take.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import time
import uuid
from pathlib import Path

from . import activity, kb
from .config import load as load_cfg, tmh_dir
from .graph import Graph

ANSWER_HEAD = "## 业务方答复"
QFILE = "open-questions.md"
# Requests touching money, approval or the books never get an automatic yes.
SENSITIVE = re.compile(r"资金|银行|支付|付款|收款|审批|凭证|总账|结算|结账|税|发票|预算|融资|计息|还款|删除|作废|口径|报表|状态")


def status_of(reg: dict, pid: str) -> str:
    r = reg.get(pid) or {}
    if r.get("stale"):
        return "过期"
    return r.get("status", kb.STATUS_NEW)


def _rel(root: Path, pid: str) -> str:
    return kb.page_path(root, pid).relative_to(root).as_posix()


# ---- reading --------------------------------------------------------------------------
def read(root: Path, pids: list[str], budget: int = 30000) -> str:
    """Pages exactly as they are on disk. Whole pages; what does not fit is listed, not cut."""
    reg = kb.load_registry(root)
    out, used, rest = [], 0, []
    for pid in dict.fromkeys(pids):
        p = kb.page_path(root, pid) if (pid == "index" or ":" in pid) else kb.kdir(root) / pid
        if not p.exists():
            out.append("<!-- %s：没有这个知识页 -->" % pid)
            continue
        text = p.read_text(encoding="utf-8")
        head = "<!-- 知识页 %s · %s · %s -->" % (pid, status_of(reg, pid) if pid in reg else "自由页", p.relative_to(root).as_posix())
        if out and used + len(text) > budget:
            rest.append("%s（%s，%d 字）" % (pid, p.relative_to(root).as_posix(), len(text)))
            continue
        out += [head, text.rstrip("\n"), ""]
        used += len(text)
    if rest:
        out.append("<!-- 超出预算未展开（原文未截断，需要时再按 id 读取）：%s -->" % "、".join(rest))
    return "\n".join(out).rstrip("\n") + "\n"


def chain(root: Path, query: str, budget: int = 30000, flows: int = 4) -> dict:
    """The business chain a request touches, ranked by `tmh context` search, with page statuses."""
    from .context import glossary, search
    g = Graph(root)
    reg = kb.load_registry(root)
    hits = search(root, query, limit=40)
    flow_ids, dom_ids, tbl_ids = [], [], []
    for s, d in hits:
        nid = d["id"]
        if nid.startswith("fn:"):
            nid = next((e["src"] for e in g.inn(nid, "step")), nid)
        if nid.startswith("flow:") and nid not in flow_ids and len(flow_ids) < flows:
            flow_ids.append(nid)
        elif nid.startswith("dom:") and nid not in dom_ids:
            dom_ids.append(nid)
        elif nid.startswith("tbl:") and nid not in tbl_ids:
            tbl_ids.append(nid)
    for fid in flow_ids:
        n = g.node(fid)
        if n and n.get("domain") and "dom:" + n["domain"] not in dom_ids:
            dom_ids.append("dom:" + n["domain"])
        for e in g.out(fid, "uses"):
            if set(e.get("op") or "") & set("CUD") and e["dst"] not in tbl_ids:
                tbl_ids.append(e["dst"])
    dom_ids, tbl_ids = dom_ids[:3], tbl_ids[:6]
    # reading order: the flows the request is about first, then their domains, then tables; whole pages until the budget is used
    pages = [p for p in flow_ids + dom_ids + tbl_ids if kb.page_path(root, p).exists()]
    qs = [q for q in questions(root) if q["open"] and any(p in q["pages"] for p in pages)]
    gl = [(w, c) for w, c in glossary(root) if w in query]
    return {"query": query, "domains": dom_ids, "flows": flow_ids, "tables": tbl_ids, "pages": pages,
            "status": {p: status_of(reg, p) for p in pages}, "questions": qs, "glossary": gl, "budget": budget}


def chain_text(root: Path, c: dict) -> str:
    reg = kb.load_registry(root)
    g = Graph(root)
    out = ["# 与“%s”相关的业务链路（知识库原文）" % c["query"], ""]
    if not c["pages"]:
        return out[0] + "\n\n知识库里没有找到相关页面。换个业务词、URL、类名或表名再试。\n"
    out.append("链路：" + " → ".join(
        "、".join("%s[%s]" % (reg.get(p, {}).get("title") or (g.node(p) or {}).get("name") or p, c["status"].get(p, "无页")) for p in grp)
        for grp in (c["domains"], c["flows"], c["tables"]) if grp))
    out.append("读法：页面按原文给出。“已确认”经人确认；“待确认”是智能体写的、未经人看；“未分析”只有代码事实；“过期”说明代码已变，以代码为准。【推断】【待确认】不能当事实答复业务方。")
    if c["questions"]:
        out += ["", "## 这些页面上还没答复的问题"]
        out += ["- #%d %s（问：%s）" % (q["n"], q["question"], q["who"] or "未指定") for q in c["questions"]]
    if c["glossary"]:
        out += ["", "## 术语"] + ["- %s：%s" % wc for wc in c["glossary"]]
    out += ["", read(root, c["pages"], c["budget"])]
    return "\n".join(out)


# ---- the human loop ---------------------------------------------------------------------------
def _qpath(root: Path) -> Path:
    return kb.kdir(root) / QFILE


def _cells(line: str) -> list[str]:
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return []
    return [c.strip() for c in re.split(r"(?<!\\)\|", s[1:-1])]


def questions(root: Path) -> list[dict]:
    """Rows of open-questions.md, numbered in file order (#1 is the first row; rows are only ever appended)."""
    p = _qpath(root)
    if not p.exists():
        return []
    out, n = [], 0
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
        c = _cells(line)
        if len(c) < 4 or c[0] in ("问题", "") or set(c[0]) <= set("-: "):
            continue
        n += 1
        ans = c[3]
        out.append({"n": n, "line": i, "question": c[0], "pages": re.findall(r"(?:dom|flow|tbl|mod):[\w.\-一-鿿]+|\bindex\b", c[1]),
                    "pages_text": c[1], "who": c[2], "answer": ans, "open": not ans.startswith("已答复")})
    return out


def _esc(s: str) -> str:
    return " ".join((s or "").replace("|", "\\|").split())


def ask(root: Path, question: str, pages: list[str], who: str = "", by: str = "agent") -> int:
    """Append a question for the business side; returns its number. Same open question twice is not added again."""
    question = _esc(question)
    for q in questions(root):
        if q["open"] and q["question"] == question:
            return q["n"]
    p = _qpath(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text(encoding="utf-8") if p.exists() else kb.FREE_PAGES[QFILE]
    row = "| %s | %s | %s | 未答复（%s 提出，%s） |" % (question, "、".join(pages) or "—", _esc(who) or "待指定", _esc(by), time.strftime("%Y-%m-%d"))
    p.write_text(text.rstrip("\n") + "\n" + row + "\n", encoding="utf-8")
    activity.log(root, "question", question, detail="涉及：%s；要问：%s" % ("、".join(pages) or "—", who or "待指定"))
    n = len(questions(root))
    _event(root, "ask", n=n, question=question, by=by, who=who)
    return n


def answer(root: Path, n: int, text: str, by: str) -> dict:
    """Record a person's answer verbatim: in the question row and on every page it concerns; queue those pages for revision."""
    if not by or by == "agent":
        raise ValueError("答复要记在具体的人名下（--who 姓名）")
    qs = questions(root)
    q = next((x for x in qs if x["n"] == n), None)
    if not q:
        raise KeyError("没有第 %d 个问题" % n)
    day = time.strftime("%Y-%m-%d")
    p = _qpath(root)
    lines = p.read_text(encoding="utf-8").splitlines()
    c = _cells(lines[q["line"]])
    c[3] = "已答复（%s，%s）：%s" % (_esc(by), day, _esc(text))
    lines[q["line"]] = "| " + " | ".join(c) + " |"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    entry = "- %s %s 答复（问题 #%d：%s）：\n\n  %s\n" % (day, by, n, q["question"], text.strip().replace("\n", "\n  "))
    written = []
    with kb._Lock(tmh_dir(root) / "cache" / "kb.lock"):
        reg = kb.load_registry(root)
        for pid in q["pages"]:
            pp = kb.page_path(root, pid)
            if not pp.exists():
                continue
            t = pp.read_text(encoding="utf-8")
            if ANSWER_HEAD in t:
                t = t.rstrip("\n") + "\n" + entry
            else:
                t = t.rstrip("\n") + "\n\n" + ANSWER_HEAD + "\n\n" + "（业务方的原话，修订页面时据此改正文和【待确认】标记；本节保留，不要改写。）\n\n" + entry
            pp.write_text(t, encoding="utf-8")
            r = reg.setdefault(pid, {"status": kb.STATUS_NEW, "scope": "答复"})
            r["revise"] = "问题 #%d 已答复" % n
            r["pinned"] = True
            written.append(pid)
        kb.save_registry(root, reg)
    activity.log(root, "decision", "%s 答复了问题 #%d" % (by, n), detail="%s\n\n%s" % (q["question"], text))
    _event(root, "answer", n=n, question=q["question"], by=by)
    return {"n": n, "pages": written}


def stats(root: Path) -> dict:
    qs = questions(root)
    reg = kb.load_registry(root)
    t = _tlog(root)
    rows = [json.loads(x) for x in t.read_text(encoding="utf-8").splitlines() if x.strip()] if t.exists() else []
    return {"questions_open": sum(q["open"] for q in qs), "questions_answered": sum(not q["open"] for q in qs),
            "confirmed": sum(1 for r in reg.values() if r.get("status") == kb.STATUS_OK and not r.get("stale")),
            "revise": sum(1 for r in reg.values() if r.get("revise")),
            "triage": len(rows), "triage_auto": sum(1 for r in rows if r.get("verdict") != "需要人判断")}


# ---- triage ----------------------------------------------------------------------------
# A request (“能不能加个…”, “为什么…”) is checked against the knowledge base before anyone
# opens code. A routing model may draft the answer, but the rules below decide whether a
# person must look: the model can lower confidence, never raise it.
VERDICTS = ("可以做", "不能做", "需要人判断")
LEVELS = ("高", "中", "低")


def router_conf(root: Path) -> dict:
    """Routing model: any OpenAI-compatible chat endpoint. Key only from the environment."""
    r = dict(load_cfg(root).get("router") or {})
    r["base_url"] = os.environ.get("TMH_ROUTER_BASE_URL") or r.get("base_url", "")
    r["model"] = os.environ.get("TMH_ROUTER_MODEL") or r.get("model", "")
    r["key_env"] = r.get("key_env") or "TMH_ROUTER_KEY"
    r["ready"] = bool(r["base_url"] and r["model"] and os.environ.get(r["key_env"]))
    return r


def _post(conf: dict, body: dict, timeout: int = 60) -> dict:
    import urllib.request
    req = urllib.request.Request(conf["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ[conf["key_env"]]})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHOOSER = ("你是分诊分类器，不是聊天助手。只依据给出的知识库原文，从选项里选一个，只输出选项字母。"
           "原文没写到的不要用常识补，选“要问业务方”一类的选项；标【推断】【待确认】的内容不算写明。")


def choose(conf: dict, state: str, question: str, options: list[str]) -> dict:
    """One typed decision (the System One idea, e.g. Jev): pick one of preset options, never free text.

    With an OpenAI-compatible endpoint the model answers one letter; when the endpoint returns
    logprobs, the option probabilities are the softmax over the option letters, so “how sure” is
    measured instead of asked. Without logprobs the probability is unknown (None)."""
    import math
    opts = options[:len(LETTERS)]
    user = "%s\n\n问题：%s\n%s\n只回答一个字母。" % (state, question, "\n".join("%s. %s" % (LETTERS[i], o) for i, o in enumerate(opts)))
    data = _post(conf, {"model": conf["model"], "temperature": 0, "max_tokens": 1, "logprobs": True, "top_logprobs": 20,
                        "messages": [{"role": "system", "content": CHOOSER}, {"role": "user", "content": user}]})
    ch = data["choices"][0]
    text = (ch.get("message") or {}).get("content") or ""
    m = re.search(r"[A-Z]", text.upper())
    idx = LETTERS.index(m.group(0)) if m and LETTERS.index(m.group(0)) < len(opts) else None
    probs = None
    lp = ((ch.get("logprobs") or {}).get("content") or [{}])[0].get("top_logprobs") or []
    if lp:
        w = [0.0] * len(opts)
        for t in lp:
            k = (t.get("token") or "").strip().upper()
            if len(k) == 1 and k in LETTERS[:len(opts)]:
                w[LETTERS.index(k)] = max(w[LETTERS.index(k)], math.exp(t.get("logprob", -99)))
        if sum(w):
            probs = [x / sum(w) for x in w]
            idx = max(range(len(opts)), key=lambda i: probs[i])
    if idx is None:
        raise ValueError("模型没有给出有效选项：%r" % text[:40])
    return {"index": idx, "choice": opts[idx], "p": probs[idx] if probs else None, "probs": probs}


# Preset routes. The model only picks one; what each means and what is said is fixed here.
ROUTES = [("answer", "能直接答复：相关规则在知识库原文里已经写明（不是【推断】）"),
          ("build", "能做，但要改代码或配置：原文写明了现有做法，需求是在此基础上改"),
          ("reject", "不能或不应这样做：与原文写明的现有业务规则冲突"),
          ("ask", "要问业务方：原文没写清、只有【推断】【待确认】，或涉及口径和规则取舍"),
          ("none", "知识库里没有这个业务，或需求说得不清楚、无法对应到具体功能")]
ROUTE_VERDICT = {"answer": "可以做", "build": "可以做", "reject": "不能做", "ask": "需要人判断", "none": "需要人判断"}
ROUTE_ANSWER = {"answer": "知识库「{t}」已写明这部分规则，核对原文后可直接答复。",
                "build": "可以做：现有做法见「{t}」，需要改代码，进入排期评估。",
                "reject": "按「{t}」写明的现有规则，这样做会冲突，建议和业务方确认是否调整规则。",
                "ask": "知识库对「{t}」这部分没写清，已转给{w}确认。",
                "none": "知识库里没有找到对应的业务，请补充是哪个功能或哪类单据。"}


def triage(root: Path, request: str, use_model: bool = True, budget: int = 24000, channel: str = "cli", sender: str = "") -> dict:
    c = chain(root, request, budget=budget)
    st = c["status"]
    reasons, must_human = [], False
    if not c["pages"]:
        reasons.append("知识库里没有找到相关页面")
        must_human = True
    unconfirmed = [p for p in c["pages"] if st[p] != kb.STATUS_OK]
    weak = [p for p in c["pages"] if st[p] in (kb.STATUS_NEW, "过期")]
    if c["questions"]:
        must_human = True
        reasons.append("相关页面上有 %d 个业务方还没答复的问题" % len(c["questions"]))
    g = Graph(root)
    names = " ".join([request] + [(g.node(p) or {}).get("name", "") for p in c["domains"]])
    sens = SENSITIVE.findall(names)
    if sens:
        must_human = True
        reasons.append("涉及%s，需要人确认" % "、".join(dict.fromkeys(sens)))
    marks = 0
    for p in c["pages"]:
        marks += len(re.findall(r"【推断】|【待确认】", kb.page_path(root, p).read_text(encoding="utf-8")))
    cap = "低" if (weak or not c["pages"]) else ("中" if unconfirmed or marks else "高")
    if weak:
        reasons.append("%d 个相关页面还没有业务说明或已过期" % len(weak))
    elif unconfirmed:
        reasons.append("相关页面还没有人确认（%d 页待确认）" % len(unconfirmed))
    if marks:
        reasons.append("相关原文里有 %d 处【推断】/【待确认】" % marks)
    res = {"id": uuid.uuid4().hex[:8], "request": request, "chain": {k: c[k] for k in ("domains", "flows", "tables")}, "status": st, "open_questions": c["questions"],
           "verdict": "需要人判断", "confidence": cap, "answer": "", "basis": [], "questions": [], "reasons": reasons,
           "model": "", "must_human": must_human, "to_write": [p for p in c["flows"] if st.get(p) in (kb.STATUS_NEW, "过期")]}
    conf = router_conf(root)
    if use_model and conf["ready"] and c["pages"]:
        try:
            state = "需求：%s\n\n%s" % (request, chain_text(root, c))
            r = choose(conf, state, "这个需求应该怎么处理？", [x[1] for x in ROUTES])
            route = ROUTES[r["index"]][0]
            titles = [kb.load_registry(root).get(p, {}).get("title") or p for p in c["pages"]]
            b = choose(conf, state, "结论主要依据哪一页？", titles + ["以上都不是"])
            res["basis"] = [c["pages"][b["index"]]] if b["index"] < len(c["pages"]) else []
            t = titles[b["index"]] if res["basis"] else (titles[0] if titles else request)
            who = ""
            if route == "ask":
                cands = list(dict.fromkeys([q["who"] for q in questions(root) if q["who"] and q["who"] != "待指定"]))[:20] + ["需求提出人", "待指定"]
                who = choose(conf, state, "这个问题应该问谁？", cands)["choice"]
                res["questions"].append({"question": "需求“%s”：「%s」相关的业务规则是什么？" % (request, t), "pages": res["basis"] or c["pages"][:1], "who": who})
            res["model"] = conf["model"]
            res["route"], res["route_p"] = route, r["p"]
            res["verdict"] = ROUTE_VERDICT[route]
            mc = "中" if r["p"] is None else ("高" if r["p"] >= 0.85 else "中" if r["p"] >= 0.6 else "低")
            res["confidence"] = max(mc, cap, key=LEVELS.index)  # the lower of the two
            res["answer"] = ROUTE_ANSWER[route].format(t=t, w=who or "业务方")
            if r["p"] is not None:
                res["reasons"].append("转发模型选“%s”的概率 %.0f%%" % (ROUTES[r["index"]][1].split("：")[0], r["p"] * 100))
        except Exception as e:  # the rules still give a usable answer
            res["reasons"].append("转发模型调用失败（%s），只按规则判断" % type(e).__name__)
    elif use_model and not conf["ready"]:
        res["reasons"].append("没有配置转发模型，只按规则判断")
    if must_human or res["confidence"] == "低" or res["questions"]:
        res["draft_verdict"] = res["verdict"] if res["model"] else ""
        res["verdict"] = "需要人判断"
    if not c["pages"]:
        res["questions"].append({"question": "知识库里没有找到和这个需求相关的内容：%s。它属于哪个业务、现在怎么处理？" % request, "pages": [], "who": "需求提出人"})
    with open(_tlog(root), "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": res["id"], "at": time.strftime("%Y-%m-%d %H:%M"), "ts": int(time.time()), "request": request[:200],
                            "verdict": res["verdict"], "confidence": res["confidence"], "model": res["model"], "pages": c["pages"],
                            "channel": channel, "sender": sender[:80]}, ensure_ascii=False) + "\n")
    return res


def record(root: Path, res: dict, by: str = "agent") -> dict:
    """Write a triage's questions to open-questions.md and queue the unwritten flows it touched."""
    nums = [ask(root, q["question"], [p for p in q.get("pages") or [] if isinstance(p, str)] or res["chain"]["flows"][:2] or res["chain"]["domains"][:1],
                q.get("who", ""), by) for q in res["questions"]]
    if res["to_write"]:
        kb.add_pages(root, res["to_write"], "需求预判")
    return {"questions": nums, "queued": res["to_write"]}


def _tlog(root: Path) -> Path:
    p = tmh_dir(root) / "cache" / "triage.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def triage_text(res: dict) -> str:
    out = ["# 需求预判：%s" % res["request"], "",
           "结论：**%s**（把握：%s）%s" % (res["verdict"], res["confidence"], "；转发模型 %s 的初判是“%s”" % (res["model"], res["draft_verdict"]) if res.get("draft_verdict") else "")]
    if res["answer"]:
        out += ["", "答复草稿（需人核对后再发给业务方）：" if res["verdict"] == "需要人判断" else "答复：", res["answer"]]
    out += ["", "依据链路：" + " → ".join("、".join("%s[%s]" % (p, res["status"].get(p, "无页")) for p in grp)
                                       for grp in (res["chain"]["domains"], res["chain"]["flows"], res["chain"]["tables"]) if grp) or "（无）"]
    if res["reasons"]:
        out += ["", "为什么%s：" % ("要人判断" if res["verdict"] == "需要人判断" else "可以直接答")] + ["- " + r for r in res["reasons"]]
    if res["open_questions"]:
        out += ["", "已有未答复的问题："] + ["- #%d %s（问：%s）" % (q["n"], q["question"], q["who"]) for q in res["open_questions"]]
    if res["questions"]:
        out += ["", "需要问业务方："] + ["- %s（问：%s）" % (q["question"], q.get("who") or "待指定") for q in res["questions"]]
    if res["to_write"]:
        out += ["", "这些业务流还没有业务说明，弄清后补上：" + "、".join(res["to_write"])]
    return "\n".join(out)


# ---- 少找人 metrics ------------------------------------------------------------------------
# Every pre-check, every question asked and answered, and every time a person overrules an
# automatic answer is appended to a log, so the numbers below are counted, not estimated.
def _jsonl(root: Path, name: str) -> list[dict]:
    p = tmh_dir(root) / "cache" / name
    if not p.exists():
        return []
    out = []
    for x in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(x))
        except ValueError:
            continue
    return out


def _append(root: Path, name: str, row: dict) -> None:
    p = tmh_dir(root) / "cache" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _event(root: Path, ev: str, **kw) -> None:
    _append(root, "questions.jsonl", dict(ev=ev, ts=int(time.time()), at=time.strftime("%Y-%m-%d %H:%M"), **kw))


def triages(root: Path, limit: int = 50) -> list[dict]:
    over = {o["id"]: o for o in _jsonl(root, "triage-overrule.jsonl")}
    rows = _jsonl(root, "triage.jsonl")[-limit:][::-1]
    for r in rows:
        if r.get("id") in over:
            r["overruled"] = over[r["id"]]
    return rows


def overrule(root: Path, tid: str, who: str, reason: str, verdict: str = "") -> dict:
    """A person says a pre-check was wrong. Counted against the adoption rate."""
    if not who or who == "agent":
        raise ValueError("改判要记在具体的人名下（--who 姓名）")
    row = next((r for r in _jsonl(root, "triage.jsonl") if r.get("id") == tid), None)
    if not row:
        raise KeyError("没有编号为 %s 的预判" % tid)
    o = {"id": tid, "ts": int(time.time()), "at": time.strftime("%Y-%m-%d %H:%M"), "by": who, "reason": reason, "verdict": verdict}
    _append(root, "triage-overrule.jsonl", o)
    activity.log(root, "decision", "%s 改判了预判 %s" % (who, tid), detail="原结论：%s\n需求：%s\n理由：%s" % (row.get("verdict"), row.get("request"), reason))
    return o


def _week(ts: int) -> str:
    y, w, _ = datetime.date.fromtimestamp(ts).isocalendar()
    return "%d-W%02d" % (y, w)


def metrics(root: Path, days: int = 0, month: str = "") -> dict:
    """少找人: share of requests answered without a person, how many of those stood, handoffs per week, answer wait.
    `month` (2026-10) limits everything to that calendar month, `days` to the last N days."""
    since = time.time() - days * 86400 if days else 0
    inside = lambda r: (r.get("at") or "").startswith(month) if month else ((r.get("ts") or 0) >= since or (not r.get("ts") and not days))
    rows = [r for r in _jsonl(root, "triage.jsonl") if inside(r)]
    over = {o["id"] for o in _jsonl(root, "triage-overrule.jsonl")}
    auto = [r for r in rows if r.get("verdict") != "需要人判断"]
    bad = [r for r in auto if r.get("id") in over]
    weeks: dict = {}
    for r in rows:
        if r.get("ts"):
            k = _week(r["ts"])
            w = weeks.setdefault(k, {"week": k, "triage": 0, "handoff": 0})
            w["triage"] += 1
            w["handoff"] += r.get("verdict") == "需要人判断"
    asked, waits = {}, []
    for e in _jsonl(root, "questions.jsonl"):
        if e.get("ev") == "ask":
            asked.setdefault(e.get("question"), e["ts"])
        elif e.get("ev") == "answer" and e.get("question") in asked:
            w = e["ts"] - asked.pop(e["question"])
            if inside(e):
                waits.append(w)
    chans: dict = {}
    for r in rows:
        chans[r.get("channel") or "cli"] = chans.get(r.get("channel") or "cli", 0) + 1
    n = len(rows)
    return {"days": days, "month": month, "triage": n, "auto": len(auto), "overruled": len(bad), "handoff": n - len(auto),
            "auto_rate": round(len(auto) / n, 3) if n else None,
            "adopted_rate": round((len(auto) - len(bad)) / n, 3) if n else None,
            "answer_wait_hours": round(sum(waits) / len(waits) / 3600, 1) if waits else None, "answered": len(waits),
            "waiting": sum(q["open"] for q in questions(root)), "weeks": sorted(weeks.values(), key=lambda w: w["week"])[-12:], "channels": chans}


def metrics_text(m: dict) -> str:
    pct = lambda x: "—" if x is None else "%.0f%%" % (x * 100)
    out = ["少找人统计%s：需求预判 %d 次，不用找人直接答 %d 次（%s），其中被人改判 %d 次，采纳率 %s；转人工 %d 次。"
           % ("（近 %d 天）" % m["days"] if m["days"] else "", m["triage"], m["auto"], pct(m["auto_rate"]), m["overruled"], pct(m["adopted_rate"]), m["handoff"])]
    out.append("业务方答复：已答 %d 个，平均等 %s 小时；还在等 %d 个。" % (m["answered"], "—" if m["answer_wait_hours"] is None else m["answer_wait_hours"], m["waiting"]))
    if m["channels"]:
        out.append("来源：" + "，".join("%s %d" % (k, v) for k, v in sorted(m["channels"].items(), key=lambda x: -x[1])))
    if m["weeks"]:
        out.append("每周转人工：" + "，".join("%s %d/%d" % (w["week"], w["handoff"], w["triage"]) for w in m["weeks"]))
    return "\n".join(out)
