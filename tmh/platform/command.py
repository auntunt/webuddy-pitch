"""The assistant's command mode: one sentence in the side panel turns into a short plan of UI steps.

"给这单写评论：需要前方去现场取日志" becomes: open the ticket, fill the comment box, click 评论 (after the
person confirms). The browser runs the steps with the page's own controls, so nothing here bypasses the
normal API or permissions; the server only plans.

Planning is rules first (common phrasings, works offline without a model), then the routing model when
one is configured (fuzzy requests: "让前方去现场拿日志，记到这单上"), else the sentence is treated as a
question for the assistant. A plan only touches what exists: page routes from PAGES, fields and buttons
from the page snapshot the browser sends, and the known ticket controls. Anything that saves or submits
is marked `confirm` and waits for the person.

Step ops:
  nav     {to}                      go to a page (reversible)
  open    {what: new_ticket}        open a dialog
  fill    {target, value}           type into a field (reversible, the person sees it)
  pick    {target, value, text}     choose an option; confirm when the field saves on change
  click   {target}                  press a button; always confirm
  session {action: new|switch, title, id}
  project {key}
"""
from __future__ import annotations

import json
import re

from .store import PRIORITIES, STATUSES, TYPES

# route, name, aliases
PAGES = [("#/reform", "改造计划", ("改造计划", "重构服务", "重构升级", "重构", "升级计划", "改造")),
         ("#/rtickets", "改造工单", ("改造工单", "重构工单")),
         ("#/rdeps", "依赖清单", ("依赖清单", "依赖", "版本清单")),
         ("#/", "今天", ("今天", "首页", "主页", "工作台")),
         ("#/clients", "客户", ("客户", "客户列表", "所有客户")),
         ("#/reqs", "需求", ("需求", "需求看板", "所有需求")),
         ("#/versions", "版本", ("版本", "出的版本", "当前版本", "版本说明")),
         ("#/board", "工单看板", ("工单看板", "看板", "运维服务", "工程")),
         ("#/lead", "运维成效", ("运维成效", "成效")),
         ("#/learn", "闭环改进", ("闭环改进", "教训", "评测集", "告警")),
         ("#/atlas", "项目图谱", ("项目图谱", "图谱")),
         ("#/tickets", "工单列表", ("工单列表", "所有工单", "全部工单", "工单")),
         ("#/overview", "监控总览", ("监控总览", "监控", "总览")),
         ("#/eff", "提效报告", ("提效报告", "报告", "提效", "效率报告")),
         ("#/kb", "知识库", ("知识库", "业务知识", "知识")),
         ("#/map", "架构与依据", ("架构与依据", "架构", "依据", "业务全景", "架构图")),
         ("#/runs", "智能体运行", ("智能体运行", "运行记录", "运行")),
         ("#/int", "外部系统", ("外部系统", "集成", "jira", "禅道")),
         ("#/settings", "设置", ("设置", "配置", "个人设置"))]

# controls on the ticket page and the new-ticket dialog, so a plan can target them before they are on screen
TICKET_FIELDS = {"cm": ("评论", "textarea", False), "fs": ("状态", "select", True), "fy": ("类型", "select", True),
                 "fp": ("优先级", "select", True), "fa": ("经办人", "text", True), "accNote": ("验收说明", "textarea", False)}
TICKET_BUTTONS = {"cb": "评论", "accOk": "验收通过", "accNo": "验收不通过"}
NEW_FIELDS = {"nt": ("标题", "text"), "nb": ("描述", "textarea"), "ny": ("类型", "select"), "np": ("优先级", "select"), "na": ("经办人", "text")}
OPTIONS = {"fs": STATUSES, "fy": TYPES, "fp": PRIORITIES, "ny": TYPES, "np": PRIORITIES}
# Status, type and priority wait for the person like any save, and the card can put them back afterwards.
UNDOABLE = {"fs", "fy", "fp"}


def _pick(tg: str, o: tuple, label: str, autosave: bool) -> dict:
    step = {"op": "pick", "target": tg, "value": o[0], "text": o[1], "label": label, "confirm": autosave}
    if tg in UNDOABLE:
        step["undo"] = True
    return step

KEY = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]{1,9}-\d+)(?![0-9])")
THIS = re.compile(r"(这单|这张单|这张工单|这个工单|当前工单|本工单|这一单|该工单)")
NAV = re.compile(r"^(请|帮我|麻烦)?\s*(打开|进入|去|跳到|跳转到|转到|切到|切换到|看看|看一下|查看|显示|回到|返回)\s*(到)?\s*")
CHANGE = r"(改成|改为|改到|设为|设成|设置为|标记为|标成|转为|转到|置为|调成|调为|调到|变成)"
QUESTION = re.compile(r"(\?|？)\s*$|^(为什么|为啥|怎么|如何|哪些|哪个|哪里|什么|是否|是不是|有没有|能不能|可以吗)")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).strip("，, ")


def _content(text: str, after: str) -> str:
    """What follows the intent word: after a colon, or after 说/写/内容是."""
    i = text.find(after)
    rest = text[i + len(after):] if i >= 0 else text
    m = re.search(r"[：:]\s*(.+)$", rest, re.S) or re.search(r"(?:说|写上?|内容是|内容为|填上?)\s*[，,]?\s*(.+)$", rest, re.S)
    return (m.group(1) if m else "").strip().strip("“”\"'「」")


def _ticket_of(text: str, page: dict) -> tuple[str, bool]:
    """(ticket key, named explicitly). 这单 means the ticket on screen."""
    m = KEY.search(text)
    if m:
        return m.group(1).upper(), True
    return (page.get("ticket") or "").upper(), False


def _on_ticket(page: dict, key: str) -> bool:
    return bool(key) and (page.get("route") or "").upper().rstrip("/") == "#/T/" + key


def _goto_ticket(page: dict, key: str) -> list:
    return [] if _on_ticket(page, key) else [{"op": "nav", "to": "#/t/" + key, "label": "打开工单 " + key}]


def _opt(pairs, word: str):
    word = word.strip().strip("「」“”\"'")
    for k, l in pairs:
        if word in (k, l) or word.lower() == k:
            return k, l
    for k, l in pairs:
        if l in word or word in l:
            return k, l
    return None


def _plan(summary: str, steps: list, source: str = "rule", note: str = "") -> dict:
    return {"kind": "command", "summary": summary, "steps": steps, "source": source, "note": note}


def _question(note: str = "") -> dict:
    return {"kind": "question", "summary": "", "steps": [], "source": "rule", "note": note}


def _field_label(f: dict) -> str:
    return re.sub(r"[（(].*?[)）]|[*：:]", "", f.get("label") or "").strip()


def rules(text: str, page: dict, sessions: list, projects: list) -> dict | None:
    t = _clean(text)
    if not t:
        return None
    key, named = _ticket_of(t, page)

    # sessions: 新建会话 / 切换到 xx 会话
    m = re.match(r"^(新建|新开|开一个|开个|开)(一个)?(新)?(会话|对话)[：:\s]*(.*)$", t)
    if m:
        title = m.group(5).strip() or "项目咨询"
        return _plan("新建会话「%s」" % title, [{"op": "session", "action": "new", "title": title[:40], "label": "新建会话「%s」" % title[:40]}])
    m = re.match(r"^(切换到|切到|打开|回到|进入)(.+?)(的)?(会话|对话)$", t)
    if m:
        want = m.group(2).strip("「」“” ")
        hit = _best(want, sessions, lambda s: "%s %s" % (s.get("title", ""), (s.get("ticket") or {}).get("key", "")))
        if hit:
            return _plan("切换到会话「%s」" % hit["title"], [{"op": "session", "action": "switch", "id": hit["id"], "label": "切换到会话「%s」" % hit["title"]}])
        return _plan("没有找到会话「%s」" % want, [], note="可以在“历史”里搜索会话标题")

    # project switch
    m = re.match(r"^(切换到|切到|打开|进入)(项目)\s*(.+)$", t) or re.match(r"^(切换到|切到)(.+?)(项目)$", t)
    if m:
        want = (m.group(3) if m.group(2) == "项目" else m.group(2)).strip()
        hit = _best(want, projects, lambda p: "%s %s" % (p.get("key", ""), p.get("name", "")))
        if hit:
            return _plan("切换到项目 %s" % hit["key"], [{"op": "project", "key": hit["key"], "label": "切换到项目 %s · %s" % (hit["key"], hit.get("name", ""))}])

    # new ticket: 新建工单：标题。描述……
    m = re.match(r"^(请|帮我)?\s*(新建|新开|创建|建|提|开|起)(一张|一个|个|张)?(新)?(的)?(工单|单子|缺陷单|需求单|bug|需求|缺陷)", t, re.I)
    if m:
        body = _content(t, m.group(0)) or re.sub(r"^[，,\s]+", "", t[m.end():])
        parts = re.split(r"(?<=[。！？!?\n])", body, maxsplit=1)
        title, rest = parts[0].strip("。 "), (parts[1].strip() if len(parts) > 1 else "")
        steps = [{"op": "open", "what": "new_ticket", "label": "打开新建工单"}]
        if title:
            steps.append({"op": "fill", "target": "nt", "value": title[:80], "label": "标题"})
        if rest or len(body) > 80:
            steps.append({"op": "fill", "target": "nb", "value": rest or body, "label": "描述"})
        ty = {"需求": "feature", "需求单": "feature", "缺陷": "bug", "缺陷单": "bug", "bug": "bug"}.get(m.group(6).lower())
        if ty:
            steps.append({"op": "pick", "target": "ny", "value": ty, "text": dict(TYPES)[ty], "label": "类型"})
        if title:
            steps.append({"op": "click", "target": "ns", "label": "创建", "confirm": True})
        return _plan("新建工单" + ("「%s」" % title[:30] if title else "，标题还没说，已打开表单"), steps)

    # comment on a ticket
    m = re.search(r"(写|加|添加|发|留|补充|追加)?(一条|个|一下)?(评论|留言|备注|回复)", t)
    if m and not QUESTION.search(t):
        if not key:
            return _plan("没有可评论的工单", [], note="先打开一张工单，或在指令里写工单号，例如“给 OA-12 写评论：……”")
        body = _content(t, m.group(0))
        steps = _goto_ticket(page, key)
        if body:
            steps += [{"op": "fill", "target": "cm", "value": body, "label": "评论"},
                      {"op": "click", "target": "cb", "label": "评论", "confirm": True}]
            return _plan("给 %s 写评论" % key, steps)
        steps.append({"op": "fill", "target": "cm", "value": "", "label": "评论"})
        return _plan("打开 %s 的评论框" % key, steps, note="评论内容没说，已把光标放到评论框")

    # acceptance
    m = re.search(r"验收(不通过|没通过|未通过|通过)", t)
    if m and key and not QUESTION.search(t):
        ok = m.group(1) == "通过"
        note = re.sub(r"^[，,：:\s]+", "", t[m.end():]).strip()
        note = re.sub(r"^(原因|理由|说明)(是|为)?[：:，,\s]*", "", note)
        if not ok and not note:
            return _plan("验收不通过要写说明", _goto_ticket(page, key) + [{"op": "fill", "target": "accNote", "value": "", "label": "验收说明"}],
                         note="不通过时验收说明必填，请写上原因")
        steps = _goto_ticket(page, key)
        if note:
            steps.append({"op": "fill", "target": "accNote", "value": note, "label": "验收说明"})
        steps.append({"op": "click", "target": "accOk" if ok else "accNo", "label": "验收通过" if ok else "验收不通过", "confirm": True})
        return _plan("%s 验收%s" % (key, "通过" if ok else "不通过"), steps)

    # ticket fields: 状态/优先级/类型/经办人
    if key:
        for fid, field, pairs in (("fs", "状态", STATUSES), ("fp", "优先级", PRIORITIES), ("fy", "类型", TYPES)):
            m = re.search(r"(%s)\s*%s\s*(\S{1,6})" % (field, CHANGE), t)
            loose = fid == "fs" and not m and re.search(r"^(把|将)?\s*(%s)?\s*%s\s*(\S{1,6})$" % (THIS.pattern + "|" + KEY.pattern, CHANGE), t)
            if loose and not any(loose.groups()[-1].startswith(l) for _, l in pairs):
                loose = None
            m = m or loose
            if m:
                o = _opt(pairs, m.groups()[-1])
                if o:
                    return _plan("把 %s 的%s改成「%s」" % (key, field, o[1]), _goto_ticket(page, key) + [_pick(fid, o, field, True)])
        m = re.search(r"(指派给|分配给|转给|交给|经办人\s*%s?)\s*([^\s，,。]{1,16})" % CHANGE, t)
        if m and "智能体" not in t and "助手" not in t:
            who = m.groups()[-1]
            return _plan("把 %s 指派给 %s" % (key, who), _goto_ticket(page, key) + [
                {"op": "fill", "target": "fa", "value": who, "label": "经办人", "confirm": True}])

    # any field on screen: 把<字段>改成/填成<值>
    m = re.match(r"^(把|将)?\s*([^，,：:]{1,12}?)\s*(改成|改为|填成|填为|填写为|填写成|写成|设为|设置为|填上|写上|填|写)\s*[：:]?\s*(.+)$", t)
    if m:
        f = _find_field(m.group(2), page)
        if f:
            v = m.group(4).strip().strip("「」“”")
            if f.get("type") == "select":
                o = _opt([(x[0], x[1]) for x in f.get("options") or []], v)
                if o:
                    return _plan("把「%s」选成「%s」" % (_field_label(f), o[1]), [
                        {"op": "pick", "target": f["key"], "value": o[0], "text": o[1], "label": _field_label(f), "confirm": bool(f.get("autosave"))}])
            else:
                return _plan("在「%s」里填写" % _field_label(f), [
                    {"op": "fill", "target": f["key"], "value": v, "label": _field_label(f), "confirm": bool(f.get("autosave"))}])

    # press a button on screen: 提交 / 点创建 / 保存
    m = re.match(r"^(点|点击|按|按下)?\s*「?(提交|保存|创建|确定|确认|评论|添加|导入|发送)」?(一下|吧)?$", t) or \
        re.match(r"^(点|点击|按)\s*「?(.{1,12}?)」?(按钮)?$", t)
    if m:
        b = _find_button(m.group(2), page)
        if b:
            return _plan("点击「%s」" % b["label"], [{"op": "click", "target": b["key"], "label": b["label"], "confirm": True}])
        return _plan("这一页没有「%s」按钮" % m.group(2), [], note="先打开要提交的表单或页面，再说一次")

    # navigation
    m = NAV.match(t)
    target = t[m.end():] if m else t
    target = re.sub(r"(页面|页|界面|那一页|这一页)$", "", target.rstrip("。！!吧")).strip()
    if key and named and (m or KEY.fullmatch(t.strip())):
        prompt = "提示词" in t
        return _plan("打开工单 " + key, [{"op": "nav", "to": "#/t/%s%s" % (key, "/prompt" if prompt else ""), "label": "打开工单 " + key + (" 的提示词" if prompt else "")}])
    for route, name, aliases in PAGES:
        if target.lower() in [a.lower() for a in aliases] or (m and any(target.lower().startswith(a.lower()) for a in aliases if len(a) > 1)):
            if route == "#/kb" and m:
                q = target
                for a in aliases:
                    if q.startswith(a):
                        q = q[len(a):]
                        break
                q = re.sub(r"^(里|中|里面)?(的|关于)?", "", q).strip()
                if q:
                    return _plan("在知识库里找「%s」" % q, [{"op": "nav", "to": "#/kb", "label": "打开知识库"},
                                                       {"op": "fill", "target": "kbq", "value": q, "label": "搜索"}])
            return _plan("打开" + name, [{"op": "nav", "to": route, "label": "打开" + name}])
    if m:
        q = re.sub(r"^(知识页|知识|业务流|业务)\s*", "", target).strip()
        if q and m.group(2) in ("打开", "查看", "看看", "看一下", "显示"):
            return _plan("在知识库里找「%s」" % q, [{"op": "nav", "to": "#/kb", "label": "打开知识库"},
                                               {"op": "fill", "target": "kbq", "value": q, "label": "搜索"}])
    return None


def _best(want: str, items: list, text) -> dict | None:
    want = want.strip().lower()
    if not want:
        return None
    for it in items:
        if want == text(it).lower() or want in text(it).lower().split():
            return it
    hits = [it for it in items if want in text(it).lower()]
    return hits[0] if hits else None


def _find_field(word: str, page: dict) -> dict | None:
    word = word.strip().strip("「」“”")
    fs = page.get("fields") or []
    for f in fs:
        if _field_label(f) == word:
            return f
    for f in fs:
        lb = _field_label(f)
        if lb and (word in lb or lb in word) and len(lb) >= 2:
            return f
    return None


def _find_button(word: str, page: dict) -> dict | None:
    bs = page.get("buttons") or []
    for b in bs:
        if (b.get("label") or "").strip() == word:
            return b
    for b in bs:
        if word in (b.get("label") or ""):
            return b
    return None


# ---------------------------------------------------------------- model planner
PLANNER = """你是“闭环工作台”运维平台侧边栏里的操作助手。用户用一句话说想做什么，你把它翻译成界面操作步骤。
只输出一个 JSON 对象，不要解释，不要代码块：
{"kind": "command" 或 "question", "summary": "一句话说明要做什么", "steps": [步骤…]}
- 用户在提问、要解释或分析（而不是要你在界面上做事）时，kind 写 question，steps 为空。
- 步骤只能用这些 op：
  {"op":"nav","to":"<页面路由>"}  页面路由只能用下面列出的，或 "#/t/<工单号>"
  {"op":"open","what":"new_ticket"}  打开新建工单表单，之后可填 nt(标题) nb(描述) ny(类型) np(优先级) na(经办人)，点 ns(创建)
  {"op":"fill","target":"<字段key>","value":"<内容>"}
  {"op":"pick","target":"<下拉框key>","value":"<选项值>"}
  {"op":"click","target":"<按钮key>"}
- 字段和按钮 key 只能用“当前页面”里列出的，或工单页固定控件：cm(评论框) cb(评论按钮) fs(状态) fy(类型) fp(优先级) fa(经办人) accNote(验收说明) accOk(验收通过) accNo(验收不通过)。
- 代填的内容用用户的意思写成通顺、专业的中文，不编造用户没说的事实（时间、人名、结论）。
- 最多 6 步。不确定用户要做什么时，kind 写 question。"""


def _snapshot_text(page: dict) -> str:
    lines = ["当前页面：%s %s" % (page.get("route") or "#/", page.get("title") or "")]
    if page.get("ticket"):
        lines.append("当前工单：%s（“这单”指它）" % page["ticket"])
    for f in (page.get("fields") or [])[:30]:
        o = " 选项=" + "/".join("%s:%s" % (x[0], x[1]) for x in (f.get("options") or [])[:12]) if f.get("options") else ""
        lines.append("字段 %s「%s」%s%s" % (f["key"], f.get("label", ""), f.get("type", ""), o))
    for b in (page.get("buttons") or [])[:30]:
        lines.append("按钮 %s「%s」" % (b["key"], b.get("label", "")))
    lines.append("页面路由：" + "；".join("%s %s" % (r, n) for r, n, _ in PAGES))
    lines.append("状态选项：" + "/".join("%s:%s" % x for x in STATUSES) + "；优先级：" + "/".join("%s:%s" % x for x in PRIORITIES) +
                 "；类型：" + "/".join("%s:%s" % x for x in TYPES))
    return "\n".join(lines)


def model_plan(conf: dict, text: str, page: dict) -> dict | None:
    from ..kbqa import _post
    data = _post(conf, {"model": conf["model"], "temperature": 0, "max_tokens": 700,
                        "messages": [{"role": "system", "content": PLANNER},
                                     {"role": "user", "content": _snapshot_text(page) + "\n\n用户说：" + text}]}, timeout=40)
    raw = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        out = json.loads(m.group(0))
    except ValueError:
        return None
    if out.get("kind") != "command":
        return _question()
    steps = validate(out.get("steps") or [], page)
    if not steps:
        return None
    return _plan(_clean(out.get("summary") or "")[:80] or "按你的话操作界面", steps, source="model")


def validate(steps: list, page: dict) -> list:
    """Keep only steps that point at something real; mark every save or submit as needing confirmation."""
    fields = {f["key"]: f for f in page.get("fields") or [] if f.get("key")}
    buttons = {b["key"]: b for b in page.get("buttons") or [] if b.get("key")}
    routes = {r for r, _, _ in PAGES}
    opened_new, on_ticket, out = False, bool(page.get("ticket")), []
    for s in steps[:8]:
        if not isinstance(s, dict):
            continue
        op = s.get("op")
        if op == "nav":
            to = str(s.get("to") or "")
            km = re.fullmatch(r"#/t/([A-Za-z][A-Za-z0-9]{1,9}-\d+)(/prompt)?", to)
            if to in routes or km:
                on_ticket = bool(km)
                fields, buttons = ({}, {}) if to != page.get("route") else (fields, buttons)
                name = next((n for r, n, _ in PAGES if r == to), "工单 " + km.group(1).upper() if km else to)
                out.append({"op": "nav", "to": to if not km else "#/t/" + km.group(1).upper() + (km.group(2) or ""), "label": "打开" + name})
        elif op == "open" and s.get("what") == "new_ticket":
            opened_new = True
            out.append({"op": "open", "what": "new_ticket", "label": "打开新建工单"})
        elif op in ("fill", "pick", "click"):
            tg = str(s.get("target") or "")
            known_t = on_ticket and (tg in TICKET_FIELDS or tg in TICKET_BUTTONS)
            known_n = opened_new and (tg in NEW_FIELDS or tg == "ns")
            if op == "click":
                b = buttons.get(tg)
                if b or known_t or known_n:
                    lb = b["label"] if b else TICKET_BUTTONS.get(tg) or "创建"
                    out.append({"op": "click", "target": tg, "label": lb, "confirm": True})
                continue
            f = fields.get(tg)
            if not (f or known_t or known_n):
                continue
            label = _field_label(f) if f else (TICKET_FIELDS.get(tg) or NEW_FIELDS.get(tg))[0]
            autosave = bool(f.get("autosave")) if f else (tg in TICKET_FIELDS and TICKET_FIELDS[tg][2])
            v = str(s.get("value") or "")
            if op == "pick":
                opts = [(x[0], x[1]) for x in f.get("options") or []] if f else OPTIONS.get(tg) or []
                o = _opt(opts, v)
                if not o:
                    continue
                out.append(_pick(tg, o, label, autosave) if tg in TICKET_FIELDS else
                           {"op": "pick", "target": tg, "value": o[0], "text": o[1], "label": label, "confirm": autosave})
            else:
                out.append({"op": "fill", "target": tg, "value": v[:4000], "label": label, "confirm": autosave})
    return out


def plan(text: str, page: dict, sessions: list | None = None, projects: list | None = None, conf: dict | None = None) -> dict:
    page = page if isinstance(page, dict) else {}
    r = rules(text, page, sessions or [], projects or [])
    if r:
        return r
    if QUESTION.search(_clean(text)):
        return _question()
    if conf and conf.get("ready"):
        try:
            m = model_plan(conf, text, page)
            if m:
                return m
        except Exception as e:  # the model is optional: a failure means "answer it as a question"
            return _question("操作模型暂不可用：%s" % str(e)[:80])
    return _question()
