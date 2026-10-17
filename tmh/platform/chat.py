"""Requirements straight from the group chat, and what became of them told back there.

A client writes in the project's group (钉钉, 飞书, 企业微信) what is wrong or what they want. The robot does not
hand them a form: it says what it understood, asks what is missing one question at a time (the same questions as
需求对话 on the platform, answered by a number or in their own words), shows the acceptance criteria it wrote, and
makes tickets only when someone in the chat replies 确认. From then on the chat hears about each ticket without
anyone asking: when a change is ready to try (with the preview link), when acceptance sends it back, when it is
accepted and in which version it went out.

A message that only asks something (no defect, no request) is not taken here: the knowledge-base answer the
robot always gave still answers it.

Commands in a conversation: 取消 (drop what is being clarified), 确认 (make the tickets), 进度 (where each ticket
of this conversation stands), 开工 <单号> (start a ticket whose criteria were still 待确认 once they are settled).

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
YES = ("确认", "确定", "确认建单", "建单", "可以", "好的", "没问题", "对", "是的")
NO = ("取消", "算了", "不用了", "先不用", "不建了")
_LOCK = threading.Lock()


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
    ck = "%s:%s:%s" % (p["key"], channel, conv["id"])
    with _LOCK:
        cs = _load(P.data_dir, "convs.json")
        c = cs.setdefault(ck, {"project": p["key"], "channel": channel, "tickets": []})
        c["dest"], c["seen"] = conv.get("dest") or {}, time.strftime("%Y-%m-%d %H:%M:%S")
        _save(P.data_dir, "convs.json", cs)
    t = text.strip()
    if t in ("进度", "进展", "到哪了"):
        return progress(P, c) if c["tickets"] else None
    m = re.match(r"^开工\s*([A-Za-z]+-\d+)$", t)
    if m:
        return _go(P, ck, c, m.group(1).upper(), sender)
    s = None
    if c.get("session"):
        try:
            s = intake.load(P.data_dir, c["session"])
        except ApiError:
            s = None
        if s and s["state"] in ("confirmed", "dropped"):
            s = None
    if s:
        if t in NO:
            intake.drop(P, s["id"], sender or "群成员")
            _set(P, ck, session="")
            return "好的，这件事先不建单。想好了随时再说。"
        if s["state"] == "ready":
            if t in YES or t.rstrip("。!！") in YES:
                return _confirm(P, ck, s, sender)
            if len(t) < 8:
                return "回复「确认」就建单开工，回复「取消」就先放着。要改哪里，直接把正确的说法发过来。"
            s = None  # a new message of its own: a new requirement replaces the one waiting for 确认
        else:
            idx, q = _pending(s)
            if q is not None:
                if t in YES:
                    return render(s, note="还有几个问题没问完，问完再确认；答不上来的回「不清楚」就跳过。")
                v = _value(t, q)
                if not q.get("options") and v != intake.UNSURE and (re.fullmatch(r"\d{1,2}", v) or len(v) < 2):
                    return render(s, note="这个问题要用一句话回答。")
                s = intake.answer(P, s["id"], sender or "群成员", {str(idx): {q["slot"]: v}})
                return render(s)
    kinds = [intake.classify(x)[0] for x in intake.split(t)]
    if not kinds or all(k == "question" for k in kinds) or len(t) < 6:
        return None  # a question: the knowledge base answers it as before
    try:
        s = intake.start(P, p, t, sender or "群成员", channel)
    except ApiError:
        return None
    _set(P, ck, session=s["id"])
    return render(s, first=True)


def _set(P, ck: str, **kv) -> dict:
    with _LOCK:
        cs = _load(P.data_dir, "convs.json")
        cs.setdefault(ck, {}).update(kv)
        _save(P.data_dir, "convs.json", cs)
        return cs[ck]


def _pending(s: dict) -> tuple[int, dict | None]:
    for i, it in enumerate(s["items"]):
        if it.get("questions"):
            return i, it["questions"][0]
    return -1, None


def _value(text: str, q: dict) -> str:
    t = text.strip()
    if t in ("不清楚", "不知道", "不确定", "跳过", "不好说"):
        return intake.UNSURE
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
            L.append("收到，我理解是 %d 件事：\n%s" % (len(work), "\n".join("%d. %s（%s）" % (n, it["text"], intake.KINDS[it["kind"]])
                                                                   for n, it in enumerate(work, 1))))
        elif work:
            L.append("收到。" + intake.understanding(work[0]))
        for it in s["items"]:
            if it["kind"] == "question":
                L.append("顺带问的「%s」：%s" % (it["text"], (it.get("answer") or "").strip()[:300]))
    idx, q = _pending(s)
    if q is not None:
        it = s["items"][idx]
        text = q["q"][len(intake.understanding(it)):] if q["q"].startswith(intake.understanding(it)) else q["q"]
        if many:
            text = "关于第 %d 件「%s」，%s" % (work.index(it) + 1, it["text"][:20], text)
        L.append("**%s**" % text)
        if q.get("options"):
            L.append("\n".join("%d. %s" % (i + 1, o) for i, o in enumerate(q["options"])))
            L.append("回数字或直接说都行；不清楚就回「不清楚」，不想建单回「取消」。")
        else:
            L.append("用一句话说就行；不清楚就回「不清楚」，不想建单回「取消」。")
        return "\n\n".join(L)
    if not work:
        return "\n\n".join(L)
    L.append("问清楚了。下面是按您说的写的验收标准，做完就按这些来验：")
    for n, it in enumerate(work, 1):
        L.append("**%s%s**" % ("第 %d 件：" % n if many else "", intake.understanding(it)))
        L.append("\n".join("- %s%s" % (a["text"], "（待确认）" if a["open"] else "") for a in it.get("ac") or []))
    if any(a["open"] for it in work for a in it.get("ac") or []):
        L.append("标了「待确认」的先不开工，确认后回「开工 单号」。")
    L.append("回复「确认」就建单开工，回复「取消」就先放着。")
    return "\n\n".join(L)


def _confirm(P, ck: str, s: dict, sender: str) -> str:
    try:
        s = intake.confirm(P, s["id"], sender or "群成员")
    except ApiError as e:
        return str(e)
    c = _set(P, ck, session="")
    with _LOCK:
        cs, tk = _load(P.data_dir, "convs.json"), _load(P.data_dir, "tickets.json")
        cs[ck]["tickets"] = list(dict.fromkeys((cs[ck].get("tickets") or []) + s["tickets"]))
        for k in s["tickets"]:
            tk[k] = ck
        _save(P.data_dir, "convs.json", cs)
        _save(P.data_dir, "tickets.json", tk)
    L = []
    for k in s["tickets"]:
        t = P.store.ticket(k)
        waits = (t.get("links") or {}).get("open_ac")
        L.append("- **%s** %s：%s" % (k, t["title"], "有 %d 条标准待确认，确认后回「开工 %s」" % (waits, k) if waits else
                                     "已经开始处理" if P.flow.autoflow().get("on") else "已交给工程师"))
    return "已建单：\n" + "\n".join(L) + "\n\n改好了我会在这里发一个能直接点开试的版本。随时回「进度」看到哪了。"


def _go(P, ck: str, c: dict, key: str, sender: str) -> str:
    if key not in (c.get("tickets") or []):
        return "这个群里没有建过 %s。" % key
    t = P.store.ticket(key)
    if not t or t["status"] in ("verify", "closed"):
        return "%s 已经不需要开工了（%s）。" % (key, _label(t["status"]) if t else "找不到")
    lk = dict(t.get("links") or {})
    lk.pop("open_ac", None)
    P.store.update_ticket(t["id"], sender or "群成员", links=lk)
    P.store.event(t["id"], sender or "群成员", "flow", "在群里确认了待确认的验收标准，开工")
    P.flow.resume(P.store.project(t["project_id"]), P.store.ticket(t["id"]))
    return "%s 开工了。改好了我在这里说。" % key


STATUS = {"new": "刚建单", "analyzing": "正在分析", "confirm": "等确认", "doing": "正在改", "verify": "改好了，等验收", "closed": "已完成"}


def _label(status: str) -> str:
    return STATUS.get(status, status)


def progress(P, c: dict) -> str:
    L = []
    for k in (c.get("tickets") or [])[-10:]:
        t = P.store.ticket(k)
        if t:
            L.append("- **%s** %s：%s" % (k, t["title"], _label(t["status"])))
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
    """A link anyone in the chat can open the preview with, for PREVIEW_DAYS."""
    from . import preview
    t = P.store.ticket(key)
    p = P.store.project(t["project_id"]) if t else None
    if not p or not preview.command(P.data_dir, p)[2] or preview.settings(P.data_dir)["preview"] != "auto":
        return ""
    base = os.environ.get("TMH_PREVIEW_BASE", "").rstrip("/") or getattr(P, "public_url", "")
    if not base:
        return ""
    if P.preview_port and not os.environ.get("TMH_PREVIEW_BASE"):
        base = re.sub(r":\d+$", "", base) + ":%d" % P.preview_port
    g = preview.grant(P.data_dir, key, "", time.time() + PREVIEW_DAYS * 86400)
    return "%s/pv/%s/__open?g=%s" % (base, key, g)


def on_status(P, t: dict, old: str, new: str) -> None:
    if not _load(P.data_dir, "tickets.json").get(t["key"]):
        return
    if new == "verify":
        link = preview_link(P, t["key"])
        _later(tell, P, t["key"], "**%s %s** 改好了，等验收。%s" % (
            t["key"], t["title"], "先点开试一试（%d 天内有效）：\n%s" % (PREVIEW_DAYS, link) if link else "我们验收后会出新版本。"))
    elif old == "verify" and new == "doing":
        _later(tell, P, t["key"], "**%s %s** 验收没通过，正在按退回的原因重改。" % (t["key"], t["title"]))


def _accepted(P):
    def fn(p, t, v):
        if v.get("passed") and _load(P.data_dir, "tickets.json").get(t["key"]):
            rel = [e for e in P.store.events(t["id"]) if e["kind"] == "release"]
            ver = (rel[-1].get("data") or {}).get("version") if rel else ""
            _later(tell, P, t["key"], "**%s %s** 验收通过%s。" % (t["key"], t["title"], "，已出新版本 %s" % ver if ver else ""))
        return {}
    fn.app = "群消息"
    return fn
