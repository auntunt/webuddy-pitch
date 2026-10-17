"""Turning what a client says into tickets that can be accepted: a short conversation, not a form.

Clients often cannot say what they need. They give a symptom ("审批不对了"), a solution ("加个按钮"), or three
things in one breath. The conversation goes:

1. Split: one message that asks for several things becomes several items, each its own ticket later.
2. Classify each item: defect, new requirement, question, data problem. A question is answered from the
   knowledge base (the same pre-check as 需求预判) and never becomes a ticket.
3. Restate it on the business map: "我理解的是：…，涉及业务流「审批通过」和表 OA_LEAVE。对吗？" The person picks
   the flow it is about (or says none of them).
4. Ask only what is missing, at most three questions a round, each with options where options make sense.
   What the message already says is not asked again (when it started, who is affected, what they did, what
   they expected).
5. Ask for one concrete example ("比如 张三 提交 3 天年假，审批通过后列表应该显示什么？"): criteria confirmed
   with a real case are the ones that hold up at acceptance.
6. Write acceptance criteria in EARS form (当……时，系统应当……), with at least one "must keep" criterion.
   Whatever is still unknown is written as 待确认, never guessed.
7. Only when the person confirms does each item become a ticket. Who confirmed and when goes into the ticket's
   evidence package, and the ticket enters the usual flow (no criteria, no implementation).

A message that splits into several items may be one feature that is accepted as a whole. The person can say so
(or start with "大需求"): then the conversation also writes a 规格卡 for the whole — goal, done conditions,
what must stay, what is out, and the evidence — asking only what is missing, and confirming it makes a parent
ticket with child tickets released in batches (epic.py).

Classification uses the routing model when one is configured (one typed choice, never free text), otherwise
keywords. Everything the criteria say comes from the person's own words.

Conversations are kept in <data>/intake/<id>.json.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from .errors import ApiError

KINDS = {"bug": "缺陷", "feature": "新需求", "question": "咨询", "data": "数据问题"}
TICKET_TYPE = {"bug": "bug", "feature": "feature", "data": "ops"}
MAX_Q = 3
UNSURE = "不清楚"
# the 规格卡 of a big requirement: what is asked about the whole, once its items are known
SPEC_Q = [
    ("goal", "整体做完以后，要达到什么效果？一句话说清，最后整体验收就按它判断。", []),
    ("keep", "做的过程中，哪些现有的东西必须保持不变？", ["现有功能和数据都不变", "对外接口和数据格式不变", "页面和操作方式不变"]),
    ("out", "这次明确不做什么？没有就说“没有”。", []),
    ("evidence", "最后用什么证明整体做好了？", ["每个子单的验收记录和版本号", "按一个完整的业务例子从头走一遍", "两样都要"]),
]

# words that tell the kinds apart; the first kind with a hit wins, in this order
KIND_WORDS = [
    ("data", re.compile(r"数据(不对|错了|有误|丢了|重复)|改一下数据|删掉这条|导错|录错|金额错|多了一条|少了一条|修正数据")),
    ("bug", re.compile(r"不对|错误|报错|出错|失败|卡住|卡死|不显示|显示不出|没有变|没变|空白|异常|打不开|点不了|不生效|bug|BUG|崩|500|白屏|乱码|不更新")),
    ("feature", re.compile(r"加一个|加个|增加|新增|希望|需要能|支持|导出|改成|能不能加|做一个|上线一个|优化")),
    ("question", re.compile(r"怎么|如何|是否|能不能|可以吗|为什么|是什么|在哪|吗[？?]?$|[？?]$")),
]
SPLIT = re.compile(r"(?:^|(?<=[\s；;。，,]))\s*(?:\d+[.、)）](?!\d)|[一二三四五六七八九十][、.]|另外|还有|此外|顺便|以及)\s*")
HAS = {
    "since": re.compile(r"今天|昨天|前天|上周|这周|本周|上个月|这个月|最近|从.{1,12}(开始|起)|\d+月\d+[日号]|一直|升级后|上线后"),
    "who": re.compile(r"所有人|大家|全部(用户|人)|都(这样|不行|有问题)|.{1,8}(部门|角色|岗位|分公司)|只有.{1,10}(会|才)|个别|有些人|某些人"),
    "trigger": re.compile(r"当[^，,。；;]{2,30}时|[^，,。；;]{0,6}(点击|点了|提交|保存|打开|进入|审批|导入|导出|查询|搜索|选了|选择|登录|上传|下载)[^，,。；;]{0,10}?(以后|之后|的时候|时|后)"),
    "expected": re.compile(r"应该|应当|希望|要求|正确的是|本来是|期望|需要显示|要能"),
}


def idir(data_dir: Path) -> Path:
    return Path(data_dir) / "intake"


def load(data_dir: Path, sid: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{12}", sid or ""):
        raise ApiError(404, "没有这段需求对话")
    f = idir(data_dir) / ("%s.json" % sid)
    if not f.exists():
        raise ApiError(404, "没有这段需求对话")
    return json.loads(f.read_text(encoding="utf-8"))


def _save(data_dir: Path, s: dict) -> dict:
    f = idir(data_dir) / ("%s.json" % s["id"])
    f.parent.mkdir(parents=True, exist_ok=True)
    s["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = f.with_name(f.name + ".%d.tmp" % threading.get_ident())  # a reader never sees half a file
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return s


# ---------------------------------------------------------------- reading the message

def split(text: str) -> list:
    """The separate asks in one message ("1. … 2. …", "另外…", "还有…"); a single ask stays whole."""
    text = (text or "").strip()
    parts = [p.strip(" ，,；;。\n") for p in SPLIT.split(text)]
    parts = [p for p in parts if len(p) >= 4]
    return parts if len(parts) > 1 else [text]


def classify(text: str, chooser=None) -> tuple[str, str]:
    """(kind, how it was decided). `chooser(text, question, options) -> index` is the routing model when configured."""
    if chooser:
        try:
            i = chooser(text, "这句话属于哪一类？", ["缺陷：现有功能不对了", "新需求：要加或改功能", "咨询：问规则或用法，不用改系统", "数据问题：要改正某几条数据"])
            return ["bug", "feature", "question", "data"][i], "转发模型"
        except Exception:  # noqa: BLE001 - the keywords still decide
            pass
    for kind, rx in KIND_WORDS:
        if rx.search(text):
            return kind, "关键词"
    return "bug", "默认"


def _flows(P, p: dict, text: str) -> list:
    """The business flows (and their tables) the words point at, best first."""
    try:
        from ..graph import Graph
        from ..kbqa import chain
        root = P.root(p)
        c = chain(root, text, budget=4000, flows=3)
        g = Graph(root)
    except Exception:  # noqa: BLE001 - a project without a knowledge base still gets the conversation
        return []
    out = []
    for fid in c["flows"]:
        n = g.node(fid) or {}
        tables = [(g.node(e["dst"]) or {}).get("name") or e["dst"].split(":", 1)[-1] for e in g.out(fid, "uses")][:4]
        out.append({"id": fid, "name": n.get("name") or fid, "domain": n.get("domain", ""), "tables": tables})
    return out


# ---------------------------------------------------------------- the conversation

def _item(P, p: dict, text: str, chooser) -> dict:
    kind, how = classify(text, chooser)
    it = {"text": text, "kind": kind, "kind_by": how, "flows": _flows(P, p, text), "flow": None, "slots": {}, "asked": [], "answer": ""}
    for k, rx in HAS.items():
        m = rx.search(text)
        if not m:
            continue
        val = m.group(0)
        if k == "expected":  # what follows "应该/希望…" up to the end of that clause
            val = re.split(r"[，,。；;！!？?\n]", text[m.end():])[0].strip()
        if val:
            it["slots"][k] = {"value": val, "from": "原话"}
    if kind == "question":
        it["answer"] = _consult(P, p, text)
    return it


def _consult(P, p: dict, text: str) -> str:
    try:
        from ..kbqa import triage, triage_text
        return triage_text(triage(P.root(p), text, use_model=True, channel="intake"))
    except Exception as e:  # noqa: BLE001
        return "知识库没能回答（%s），转人工答复。" % type(e).__name__


def start(P, p: dict, text: str, by: str, channel: str = "web", chooser=None, pin: dict | None = None, big: bool = False) -> dict:
    text = (text or "").strip()
    m = re.match(r"^大需求\s*[：:，,]?\s*", text)
    if m:  # said in so many words: one feature, accepted as a whole
        text, big = text[m.end():], True
    if len(text) < 4:
        raise ApiError(400, "说一句发生了什么或想要什么")
    s = {"id": uuid.uuid4().hex[:12], "project": p["key"], "by": by, "channel": channel, "text": text[:4000],
         "created": time.strftime("%Y-%m-%d %H:%M:%S"), "state": "asking", "rounds": 0,
         "items": [_item(P, p, x, chooser) for x in split(text)[:6]], "tickets": []}
    if pin:  # started from a box drawn on the page: where it is travels with every ticket
        s["pin"] = pin
    s["suggest_big"] = sum(1 for it in s["items"] if it["kind"] != "question") > 1
    if big:
        s["big"], s["spec_slots"] = True, {}
    _plan(s)
    return _save(P.data_dir, s)


def understanding(it: dict) -> str:
    """The restatement put to the person: what we think they mean, on the business map."""
    f = it.get("flow")
    where = ""
    if f:
        where = "，涉及业务流「%s」%s" % (f["name"], "和表 %s" % "、".join(f["tables"][:3]) if f.get("tables") else "")
    elif it["flows"]:
        where = "，可能涉及业务流「%s」" % it["flows"][0]["name"]
    return "我理解的是：%s（%s）%s。" % (it["text"], KINDS[it["kind"]], where)


def _questions(it: dict) -> list:
    """What is still missing for this item, the most useful first."""
    if it["kind"] == "question":
        return []
    sl = it["slots"]
    qs = []
    if it["flow"] is None and it["flows"] and "flow" not in it["asked"]:
        qs.append({"slot": "flow", "q": understanding(it) + "说的是下面哪一块？", "options": [f["name"] for f in it["flows"]] + ["都不是"]})
    if "trigger" not in sl:
        qs.append({"slot": "trigger", "q": "在哪个页面、做了什么操作的时候出现？" if it["kind"] == "bug" else "在哪个页面、什么情况下要用到？",
                   "options": []})
    if "expected" not in sl:
        qs.append({"slot": "expected", "q": "正确的结果应该是什么样？" if it["kind"] != "feature" else "希望系统具体做到什么？", "options": []})
    if it["kind"] == "bug" and "who" not in sl:
        qs.append({"slot": "who", "q": "是所有人都这样，还是只有部分人？", "options": ["所有人", "某个部门或角色", "个别人"]})
    if it["kind"] == "bug" and "since" not in sl:
        qs.append({"slot": "since", "q": "从什么时候开始的？", "options": ["今天才出现", "这周", "更早", "一直这样"]})
    if it["kind"] == "data" and "record" not in sl:
        qs.append({"slot": "record", "q": "是哪几条数据？给单号或能找到它的信息。", "options": []})
    if "example" not in sl and ("expected" in sl or len(qs) < MAX_Q):
        qs.append({"slot": "example", "q": "举一个具体例子：谁、做了什么、用的什么数据，结果应该是什么？（例如：张三提交 3 天年假，审批通过后列表显示“已通过”）",
                   "options": []})
    return [q for q in qs if q["slot"] not in it["asked"] or q["slot"] == "flow"][:MAX_Q]


def _plan(s: dict) -> None:
    """Next round's questions; when nothing is missing any more, the criteria are drafted."""
    for i, it in enumerate(s["items"]):
        it["questions"] = _questions(it)
        it["ac"] = criteria(it)
    open_q = sum(len(it["questions"]) for it in s["items"])
    if s.get("big"):
        sl = s.setdefault("spec_slots", {})
        s["spec_q"] = [{"slot": k, "q": q, "options": o} for k, q, o in SPEC_Q if k not in sl][:MAX_Q]
        s["spec"] = spec(s)
        open_q += len(s["spec_q"])
    s["state"] = "asking" if open_q else "ready"


def mark_big(P, sid: str, by: str, on: bool = True) -> dict:
    """The person says these asks are one feature (or not after all): the spec questions join the conversation."""
    s = load(P.data_dir, sid)
    if s["state"] in ("confirmed", "dropped"):
        raise ApiError(409, "这段对话已经结束")
    if on:
        s["big"], s["big_by"] = True, by
        s.setdefault("spec_slots", {})
    else:
        s.pop("big", None)
        s.pop("spec", None)
        s.pop("spec_q", None)
    _plan(s)
    return _save(P.data_dir, s)


def spec(s: dict) -> dict:
    """The 规格卡: the whole's done conditions are each item's main criterion plus the goal itself, in the person's
    words; what nobody said yet is 待确认."""
    sl = s.get("spec_slots") or {}
    v = lambda k: "" if not sl.get(k) or sl[k].get("unsure") else sl[k]["value"]
    goal, keep, out, ev = v("goal"), v("keep"), v("out"), v("evidence")
    done = []
    for it in s["items"]:
        if it["kind"] == "question" or not it.get("ac"):
            continue
        a = it["ac"][0]
        done.append({"id": "D%d" % (len(done) + 1), "text": "「%s」：%s" % (re.sub(r"\s+", " ", it["text"])[:40], a["text"]), "layer": a["layer"],
                     "check": a["check"], "open": a["open"]})
    done.append({"id": "D%d" % (len(done) + 1), "text": "当全部子单验收通过并合入主干时，%s" % (goal or "【待确认：整体要达到什么效果】"), "layer": "L3",
                 "check": ev or "【待确认：用什么证明整体做好了】", "open": not (goal and ev)})
    done.append({"id": "D%d" % (len(done) + 1), "text": "必须保持：%s" % (keep or "其他环节和其他用户的现有行为不变"), "layer": "L1",
                 "check": "跑现有测试，并抽查相邻功能", "open": False})
    return {"goal": goal or "【待确认：整体要达到什么效果】", "done": done, "keep": keep or "【待确认：哪些必须保持不变】",
            "out": out or "【待确认：这次不做什么】", "evidence": ev or "【待确认：用什么证明做好了】",
            "open": [k for k, _, _ in SPEC_Q if not v(k)]}


def answer(P, sid: str, by: str, answers: dict) -> dict:
    """answers: {"<item index>": {"<slot>": "value"}}; "不清楚" leaves it as 待确认."""
    s = load(P.data_dir, sid)
    if s["state"] in ("confirmed", "dropped"):
        raise ApiError(409, "这段对话已经结束")
    for k, slots in (answers or {}).items():
        if k == "spec":  # about the whole of a big requirement
            if not s.get("big"):
                raise ApiError(400, "这段对话没有标成大需求")
            for slot, val in (slots or {}).items():
                val = str(val or "").strip()[:600]
                if slot not in dict((x[0], 1) for x in SPEC_Q):
                    raise ApiError(400, "不认识的问题：%s" % slot)
                if val:
                    s["spec_slots"][slot] = {"value": val, "from": by, "unsure": val == UNSURE}
            continue
        try:
            it = s["items"][int(k)]
        except (ValueError, IndexError):
            raise ApiError(400, "没有第 %s 件事" % k)
        for slot, val in (slots or {}).items():
            val = str(val or "").strip()[:600]
            if slot == "flow":
                it["asked"].append("flow")
                it["flow"] = next((f for f in it["flows"] if f["name"] == val), None) or ({"id": "", "name": val, "tables": []} if val and val != "都不是" else None)
                if val == "都不是":
                    it["flows"] = []
                continue
            if slot == "kind":
                if val not in KINDS:
                    raise ApiError(400, "类型只能是：%s" % "、".join(KINDS))
                it["kind"], it["kind_by"] = val, by
                continue
            if slot not in ("trigger", "expected", "who", "since", "record", "example"):
                raise ApiError(400, "不认识的问题：%s" % slot)
            if not val:
                continue
            it["asked"].append(slot)
            it["slots"][slot] = {"value": val, "from": by, "unsure": val == UNSURE}
    s["rounds"] += 1
    _plan(s)
    return _save(P.data_dir, s)


def _v(it: dict, k: str) -> str:
    x = it["slots"].get(k)
    return "" if not x or x.get("unsure") else x["value"]


def criteria(it: dict) -> list:
    """EARS criteria from the person's own words; gaps are written as 待确认."""
    if it["kind"] == "question":
        return []
    trig, exp, who, ex = _v(it, "trigger"), _v(it, "expected"), _v(it, "who"), _v(it, "example")
    flow = (it.get("flow") or {}).get("name", "")
    trig = re.sub(r"^当", "", trig)
    if trig and not trig.endswith(("时", "后", "的时候")):
        trig += "时"
    head = "当%s%s" % ("%s的用户" % who if who and who not in ("所有人", "个别人") else "", trig or "【待确认：在什么操作或情况下】时")
    out = [{"id": "A1", "text": "%s，系统应当%s" % (head, exp or "【待确认：正确结果是什么】"), "layer": "L2",
            "check": "按例子操作并核对：%s" % ex if ex else "【待确认：用一个具体例子核对】", "open": not (trig and exp and ex)}]
    if it["kind"] == "data":
        rec = _v(it, "record")
        out.append({"id": "A2", "text": "当修正完成时，%s 应当和正确值一致，并留下修改前后的记录" % (rec or "【待确认：哪几条数据】"),
                    "layer": "L4", "check": "逐条核对修正前后的值", "open": not rec})
    out.append({"id": "A%d" % (len(out) + 1), "text": "必须保持：%s其他环节和其他用户的现有行为不变" % ("「%s」的" % flow if flow else ""),
                "layer": "L1", "check": "跑现有测试，并抽查相邻功能", "open": False})
    return out


def ticket_body(s: dict, it: dict) -> str:
    L = ["## 原话", it["text"], "", "## 理解", understanding(it)]
    facts = [("since", "从什么时候"), ("who", "影响谁"), ("trigger", "什么操作时"), ("expected", "期望结果"), ("record", "涉及数据"), ("example", "例子")]
    got = ["- %s：%s%s" % (n, it["slots"][k]["value"], "（%s）" % ("原话" if it["slots"][k]["from"] == "原话" else "%s 补充" % it["slots"][k]["from"]))
           for k, n in facts if k in it["slots"]]
    if got:
        L += ["", "## 补充的信息"] + got
    if s.get("pin"):
        L += ["", "## 位置（框选定位，第 2、3 层是推断）", s["pin"]["summary"], "框选记录：%s" % s["pin"]["id"]]
    L += ["", "## 验收标准（EARS，待确认的不得进入实现）"]
    L += ["- %s %s%s；怎么验：%s" % (a["id"], a["text"], "【待确认】" if a["open"] else "", a["check"]) for a in it["ac"]]
    L += ["", "来源：需求对话 %s（%s，%s 发起，%d 轮）" % (s["id"], s["channel"], s["by"], s["rounds"])]
    return "\n".join(L)


_CONFIRM = threading.Lock()  # a double click must not make every ticket twice (and start every agent twice)


def confirm(P, sid: str, by: str, items: list | None = None, deps: dict | None = None, wave: int | None = None) -> dict:
    """The person confirms: each chosen item becomes a ticket, the confirmation goes into its evidence package.
    A big requirement becomes a parent with its children instead (deps and wave say how they are released)."""
    with _CONFIRM:
        return _confirm(P, sid, by, items, deps, wave)


def _confirm(P, sid: str, by: str, items: list | None = None, deps: dict | None = None, wave: int | None = None) -> dict:
    from .signoff import _add, epath
    s = load(P.data_dir, sid)
    if s["state"] in ("confirmed", "dropped"):
        raise ApiError(409, "这段对话已经结束")
    p = P.project(s["project"])
    if s.get("big"):
        from . import epic
        try:
            r = epic.create(P, p, s, by, deps, wave)
        except ValueError as e:
            raise ApiError(400, str(e))
        s["tickets"] += [r["parent"]]
        s["epic"], s["children"] = r["parent"], r["children"]
        s["state"] = "confirmed"
        s["confirmed_by"], s["confirmed_at"] = by, time.strftime("%Y-%m-%d %H:%M:%S")
        return _save(P.data_dir, s)
    pick = range(len(s["items"])) if items is None else [int(i) for i in items]
    made = []
    for i in pick:
        it = s["items"][i]
        if it["kind"] == "question":
            continue
        title = re.sub(r"\s+", " ", it["text"])[:60]
        links = {"flows": [it["flow"]["id"]]} if it.get("flow") and it["flow"].get("id") else {}
        t = P.store.create_ticket(p["id"], title, by, body=ticket_body(s, it), type=TICKET_TYPE[it["kind"]], links=links)
        _add(epath(P.data_dir, t["key"]), "intake", by, {"session": s["id"], "text": it["text"], "understanding": understanding(it),
                                                         "ac": it["ac"], "open": [a["id"] for a in it["ac"] if a["open"]],
                                                         "confirmed_by": by, "requested_by": s["by"], "channel": s["channel"],
                                                         "pin": (s.get("pin") or {}).get("id", "")})
        P.store.event(t["id"], by, "evidence", "需求对话确认后建单：%d 条验收标准%s" % (
            len(it["ac"]), "，%d 条待确认" % len([a for a in it["ac"] if a["open"]]) if any(a["open"] for a in it["ac"]) else ""))
        it["ticket"] = t["key"]
        made.append(t["key"])
        if any(a["open"] for a in it["ac"]):  # the ticket itself says open criteria must not be built: they wait for a person
            P.store.update_ticket(t["id"], by, links=dict(links, open_ac=len([a for a in it["ac"] if a["open"]])))
            P.store.event(t["id"], by, "flow", "有验收标准还待确认，先不自动开始；和客户确认后点“交给自动处理”")
        else:
            P.flow.submit(p, P.store.ticket(t["id"]))  # like any new ticket: the line picks it up (or says why it waits)
    if not made:
        raise ApiError(409, "没有要建单的事：咨询类已经直接答复")
    s["tickets"] += made
    s["state"] = "confirmed"
    s["confirmed_by"], s["confirmed_at"] = by, time.strftime("%Y-%m-%d %H:%M:%S")
    _save(P.data_dir, s)
    return s


def drop(P, sid: str, by: str) -> dict:
    s = load(P.data_dir, sid)
    s["state"], s["dropped_by"] = "dropped", by
    return _save(P.data_dir, s)
