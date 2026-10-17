"""Requirements straight from the group chat, and what became of them told back there.

A client writes in the project's group (钉钉, 飞书, 企业微信) what is wrong or what they want. The robot does not
hand them a form: it says what it understood, asks what is missing one question at a time (the same questions as
需求对话 on the platform, answered by a number or in their own words), shows the acceptance criteria it wrote, and
makes tickets only when someone in the chat replies 确认. From then on the chat hears about each ticket without
anyone asking: when a change is ready to try (with the preview link), when acceptance sends it back, when it is
accepted and in which version it went out.

A message that only asks something (no defect, no request) is not taken here: the knowledge-base answer the
robot always gave still answers it.

In a group each person has their own draft: only its author answers its questions, confirms it (确认) or drops it
(取消), so a passer-by's "好的" makes nothing. Criteria still 待确认 are settled with the provider's engineer, not
in the chat. A draft untouched for a day is forgotten. 进度 lists where this conversation's tickets stand.

Several asks that are one feature: the author replies 大需求 (or starts the message with it), the robot asks what
the 规格卡 still needs, shows it, and 确认 makes a parent with children released in batches (epic.py). The chat
then hears about the feature per batch and at its overall acceptance, not about every child.

Conversations and which ticket came from which are kept in <data>/chat/.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

from . import intake
from .errors import ApiError

PREVIEW_DAYS = 7  # how long a preview link posted in the chat opens the preview
DRAFT_H = 24  # a draft nobody touched for this long is forgotten
YES = ("确认", "确定", "确认建单")
NO = ("取消", "算了", "不用了", "先不用", "不建了")
BIG = ("大需求", "按大需求做", "是大需求")
_LOCK = threading.RLock()  # one message at a time: two answers at once must not overwrite each other


def _f(data_dir: Path, name: str) -> Path:
    return Path(data_dir) / "chat" / name


def _load(data_dir: Path, name: str) -> dict:
    try:
        return json.loads(_f(data_dir, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data_dir: Path, name: str, d: dict) -> None:
    f = _f(data_dir, name)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def _project(P, root: Path) -> dict | None:
    root = Path(root).resolve()
    return next((p for p in P.store.projects() if Path(p["root"]).resolve() == root), None)


def wire(P) -> None:
    from .. import bots
    bots.INTAKE = lambda root, text, channel, sender, conv: route(P, root, text, channel, sender, conv)
    P.store.on_status.append(lambda t, old, new, who: on_status(P, t, old, new))
    P.flow.listeners.append(_accepted(P))


# ---------------------------------------------------------------- the conversation

def route(P, root: Path, text: str, channel: str, sender: str, conv: dict) -> str | None:
    p = _project(P, root)
    if not p:
        return None
    with _LOCK:
        try:
            return _route(P, p, text.strip(), sender or "群成员", conv)
        except (ApiError, ValueError, KeyError) as e:
            return "这一步没处理成（%s），请再发一次。" % (e.args[0] if e.args else type(e).__name__)


def _route(P, p: dict, t: str, sender: str, conv: dict) -> str | None:
    kind = (conv.get("dest") or {}).get("kind") or "chat"  # the channel the message really came by, not what it says
    ck = "%s:%s:%s" % (p["key"], kind, conv["id"])
    cs = _load(P.data_dir, "convs.json")
    c = cs.setdefault(ck, {"project": p["key"], "channel": kind, "tickets": [], "drafts": {}})
    c["dest"], c["seen"] = conv.get("dest") or {}, time.strftime("%Y-%m-%d %H:%M:%S")
    _save(P.data_dir, "convs.json", cs)
    if t in ("进度", "进展", "到哪了"):
        return progress(P, c) if c["tickets"] else "这个群里还没有提过要做的事。直接说哪里不对、想要什么就行。"
    s = None
    sid = (c.get("drafts") or {}).get(sender)
    if sid:
        try:
            s = intake.load(P.data_dir, sid)
        except ApiError:
            s = None
        if s and (s["state"] in ("confirmed", "dropped") or
                  time.time() - time.mktime(time.strptime(s.get("updated") or s["created"], "%Y-%m-%d %H:%M:%S")) > DRAFT_H * 3600):
            s = None
        if not s:
            _draft(P, ck, sender, "")
    asks = t.endswith(("？", "?", "吗", "呢")) and all(intake.classify(x)[0] == "question" for x in intake.split(t))
    if s and not asks:
        if t in NO:
            intake.drop(P, s["id"], sender)
            _draft(P, ck, sender, "")
            return "好的，这件事先不建单。想好了随时再说。"
        if t.rstrip("。!！") in BIG:  # never an answer to a question
            if s.get("big"):
                return render(s, note="已经按大需求在理了。")
            return render(intake.mark_big(P, s["id"], sender), note="好的，按一个大需求来做：拆成子单分批上线，最后整体验收。")
        if s["state"] == "ready":
            if t.rstrip("。!！") in YES:
                return _confirm(P, ck, c, s, sender)
            if len(t) < 8:
                return "回复「确认」就建单开工，回复「取消」就先放着。要改哪里，直接把正确的说法发过来。"
            s = None  # a new message of its own: a new requirement replaces the one waiting for 确认
        else:
            idx, q = _pending(s)
            if q is not None:
                if t.rstrip("。!！") in YES:
                    return render(s, note="还有几个问题没问完，问完再确认；答不上来的回「不清楚」就跳过。")
                v = _value(t, q)
                if not q.get("options") and v != intake.UNSURE and (re.fullmatch(r"\d{1,2}", v) or len(v) < 2):
                    return render(s, note="这个问题要用一句话回答。")
                s = intake.answer(P, s["id"], sender, {"spec" if idx < 0 else str(idx): {q["slot"]: v}}, wait=True)
                return render(s)
    if asks or len(t) < 6:
        return None  # a question: the knowledge base answers it as before
    parts = intake.split(t)
    if not parts or all(intake.classify(x)[0] == "question" for x in parts):
        return None
    try:
        s = intake.start(P, p, t, sender, kind, wait=True)  # replies are composed off the callback thread
    except ApiError:
        return None
    _draft(P, ck, sender, s["id"])
    return render(s, first=True, note="（一次最多理 %d 件，其余的请再发一条）" % len(s["items"]) if len(parts) > len(s["items"]) else "")


def _draft(P, ck: str, who: str, sid: str) -> None:
    cs = _load(P.data_dir, "convs.json")
    d = cs.setdefault(ck, {}).setdefault("drafts", {})
    if sid:
        d[who] = sid
    else:
        d.pop(who, None)
    _save(P.data_dir, "convs.json", cs)


def _pending(s: dict) -> tuple[int, dict | None]:
    """The next question: about an item (its index), then about the whole of a big requirement (-1)."""
    for i, it in enumerate(s["items"]):
        if it.get("questions"):
            return i, it["questions"][0]
    if s.get("spec_q"):
        return -1, s["spec_q"][0]
    return -1, None


def _value(text: str, q: dict) -> str:
    t = text.strip()
    if t in ("不清楚", "不知道", "不确定", "跳过", "不好说"):
        return "都不是" if q.get("slot") == "flow" else intake.UNSURE
    opts = q.get("options") or []
    if opts and re.fullmatch(r"\d{1,2}", t) and 1 <= int(t) <= len(opts):
        return opts[int(t) - 1]
    return t


def render(s: dict, first: bool = False, note: str = "") -> str:
    """The robot's next message: the next question, or the criteria to confirm."""
    work = [it for it in s["items"] if it["kind"] != "question"]
    many = len(work) > 1
    L = [note] if note else []
    if first:
        if many:
            L.append("收到，我理解是 %d 件事：\n%s" % (len(work), "\n".join("%d. %s（%s）" % (n, intake.title_of(it), intake.KINDS[it["kind"]])
                                                                   for n, it in enumerate(work, 1))))
        elif work:
            L.append("收到。" + intake.understanding(work[0]))
        for it in s["items"]:
            if it["kind"] == "question":
                L.append("顺带问的「%s」：%s" % (it["text"], (it.get("answer") or "").strip()[:300]))
    idx, q = _pending(s)
    if q is not None:
        if idx < 0:
            text = "关于整体：" + q["q"]
        else:
            it = s["items"][idx]
            text = q["q"][len(intake.understanding(it)):] if q["q"].startswith(intake.understanding(it)) else q["q"]
            if many:
                text = "关于第 %d 件「%s」，%s" % (work.index(it) + 1, intake.title_of(it)[:20], text)
        L.append("**%s**" % text)
        if q.get("options"):
            L.append("\n".join("%d. %s" % (i + 1, o) for i, o in enumerate(q["options"])))
            L.append("回数字或直接说都行；不清楚就回「不清楚」，不想建单回「取消」。")
        else:
            L.append("用一句话说就行；不清楚就回「不清楚」，不想建单回「取消」。")
        return "\n\n".join(L)
    if not work:
        return "\n\n".join(L)
    if s.get("big"):
        from . import epic
        sp = s["spec"]
        L.append("问清楚了。这是一个大需求，规格卡如下：")
        L.append("**目标**：%s\n**整体验收标准**：\n%s\n**必须保持不变**：%s\n**这次不做**：%s\n**用什么证明**：%s" % (
            _md(sp["goal"]), "\n".join("- %s%s" % (_md(d["text"]), "（待确认）" if d["open"] else "") for d in sp["done"]),
            _md(sp["keep"]), _md(sp["out"]), _md(sp["evidence"])))
        L.append("拆成 %d 个子单，每个子单有自己的验收标准，分批开工（每批 %d 个），一批验收通过再开下一批：\n%s" % (
            len(work), epic.WAVE, "\n".join("%d. %s" % (n, _md(intake.title_of(it)[:40])) for n, it in enumerate(work, 1))))
        L.append("回复「确认」就建父单和子单、开工第一批，回复「取消」就先放着。")
        return "\n\n".join(L)
    L.append("问清楚了。下面是按您说的写的验收标准，做完就按这些来验：")
    for n, it in enumerate(work, 1):
        L.append("**%s%s**" % ("第 %d 件：" % n if many else "", intake.understanding(it)))
        L.append("\n".join("- %s%s" % (a["text"], "（待确认）" if a["open"] else "") for a in it.get("ac") or []))
    if any(a["open"] for it in work for a in it.get("ac") or []):
        L.append("标了「待确认」的先不开工，确认后回「开工 单号」。")
    if s.get("suggest_big"):
        L.append("这几件如果是一个整体、要一起验收，回复「大需求」：拆成子单分批上线，最后整体验收。")
    L.append("回复「确认」就建单开工，回复「取消」就先放着。")
    return "\n\n".join(L)


def _confirm(P, ck: str, c: dict, s: dict, sender: str) -> str:
    from .. import bots
    s = intake.confirm(P, s["id"], sender)
    _draft(P, ck, sender, "")
    cs, tk = _load(P.data_dir, "convs.json"), _load(P.data_dir, "tickets.json")
    cs[ck]["tickets"] = list(dict.fromkeys((cs[ck].get("tickets") or []) + s["tickets"]))
    for k in s["tickets"]:
        tk[k] = ck
    _save(P.data_dir, "convs.json", cs)
    _save(P.data_dir, "tickets.json", tk)
    later = bots.can_tell(P.root(P.project(c["project"])), c.get("dest") or {})
    if s.get("epic"):
        par = P.store.ticket(s["epic"])
        kids = [P.store.ticket(k) for k in s.get("children") or []]
        return "已建大需求 **%s** %s，拆成 %d 个子单：\n%s\n\n%s随时回「进度」看到哪了。" % (
            par["key"], _md(par["title"]), len(kids), "\n".join("- **%s** %s：%s" % (k["key"], _md(k["title"]), "排队" if k["links"].get("later") else
                                                         "已放出，有验收标准待确认，工程师先和您确认再开工" if k["links"].get("open_ac") else "已开工")
                                                         for k in kids),
            "每一批开工、做完和最后整体验收，我都会在这里说。" if later else "这个群我没法主动发消息，")
    L = []
    for k in s["tickets"]:
        t = P.store.ticket(k)
        waits = (t.get("links") or {}).get("open_ac")
        L.append("- **%s** %s：%s" % (k, _md(t["title"]), "有 %d 条标准还待确认，工程师会先和您确认再开工" % waits if waits else
                                     "已经开始处理" if P.flow.autoflow().get("on") else "已交给工程师"))
    return "已建单：\n" + "\n".join(L) + ("\n\n改好了我会在这里发一个能直接点开试的版本。随时回「进度」看到哪了。" if later else
                                        "\n\n这个群我没法主动发消息，进展请随时回「进度」查看。")


def _md(text: str) -> str:
    """A title shown in the chat: as text, not as markdown someone wrote into it."""
    return re.sub(r"([\\`*_\[\]()#>!|~])", r"\\\1", text or "")


STATUS = {"new": "刚建单", "analyzing": "正在分析", "confirm": "等确认", "doing": "正在改", "verify": "改好了，等验收", "closed": "已完成"}


def _label(status: str) -> str:
    return STATUS.get(status, status)


def progress(P, c: dict) -> str:
    L = []
    for k in (c.get("tickets") or [])[-10:]:
        t = P.store.ticket(k)
        if t:
            from . import epic
            L.append("- **%s** %s：%s" % (k, _md(t["title"]), epic.brief(P, t) if epic.is_parent(t) else _label(t["status"])))
    return "这个群里提的事：\n" + "\n".join(L)


# ---------------------------------------------------------------- telling the chat

def _conv_of(P, key: str) -> dict | None:
    ck = _load(P.data_dir, "tickets.json").get(key)
    return _load(P.data_dir, "convs.json").get(ck) if ck else None


def tell(P, key: str, text: str) -> bool:
    """Post into the conversation a ticket came from. Never raises: the chat is a courtesy, the ticket is the record."""
    c = _conv_of(P, key)
    if not c or not c.get("dest"):
        return False
    from .. import bots
    t = P.store.ticket(key)
    try:
        ok = bots.send(P.root(P.project(c["project"])), c["dest"], text)
    except Exception as e:  # noqa: BLE001
        ok, why = False, str(e)
    else:
        why = "" if ok else "这个渠道现在发不出去（钉钉的会话地址过期了就需要配置群机器人 Webhook）"
    if t:
        P.store.event(t["id"], "群消息", "chat", ("已在群里告知：" if ok else "没能告知群里（%s）：" % why) + text.split("\n")[0][:120])
    return ok


def _later(fn, *a) -> None:
    from .. import bots
    if bots.ASYNC:
        threading.Thread(target=fn, args=a, daemon=True).start()
    else:
        fn(*a)


def preview_link(P, key: str) -> str:
    """A link anyone in the chat can open the preview with, for PREVIEW_DAYS. Needs to know the address people use:
    TMH_PUBLIC_URL (or TMH_PREVIEW_BASE), else the one learnt from people who are logged in."""
    from . import preview
    t = P.store.ticket(key)
    p = P.store.project(t["project_id"]) if t else None
    if not p or not preview.command(P.data_dir, p)[2] or preview.settings(P.data_dir)["preview"] != "auto" or not preview.branch_of(P, t):
        return ""
    base = os.environ.get("TMH_PREVIEW_BASE", "").rstrip("/")
    if not base and getattr(P, "public_url", ""):
        host = re.sub(r"^https?://", "", P.public_url)
        base = "http://%s:%d" % (re.sub(r":\d+$", "", host), P.preview_port) if P.preview_port else P.public_url
    if not base:
        return ""
    g = preview.grant(P.data_dir, key, "", time.time() + PREVIEW_DAYS * 86400)
    return "%s/pv/%s/__open?g=%s" % (base, key, g)


def on_status(P, t: dict, old: str, new: str) -> None:
    if new == "verify" and not (t.get("links") or {}).get("epic") and _load(P.data_dir, "tickets.json").get(t["key"]):  # a feature tells its own
        link = preview_link(P, t["key"])
        _later(tell, P, t["key"], "**%s %s** 改好了，等验收。%s" % (
            t["key"], _md(t["title"]), "先点开试一试（%d 天内有效，请不要转给群外的人）：\n%s" % (PREVIEW_DAYS, link) if link
            else "我们验收后会出新版本。"))


def _accepted(P):
    def fn(p, t, v):
        if (t.get("links") or {}).get("epic") or not _load(P.data_dir, "tickets.json").get(t["key"]):
            return {}  # a feature's parent: epic.py says what its verdict led to
        head = "**%s %s**" % (t["key"], _md(t["title"]))
        if v.get("passed"):
            rel = [e for e in P.store.events(t["id"]) if e["kind"] == "release"]
            ver = (rel[-1].get("data") or {}).get("version") if rel else ""
            _later(tell, P, t["key"], "%s 验收通过%s。" % (head, "，已出新版本 %s" % ver if ver else ""))
        else:
            _later(tell, P, t["key"], "%s 验收没通过，%s。" % (head, "正在按退回的原因重改" if v.get("redo") else "工程师会按退回的原因处理"))
        return {}
    fn.app = "群消息"
    return fn
