"""大需求: a feature too big for one ticket, from the conversation to versions without anyone orchestrating it.

需求对话 turns a message into tickets one ask at a time. Some asks belong together: "请假要支持按小时请，审批要
能看余额，报表要按小时统计" is one feature, accepted as a whole, and a client cares that the whole works. So when
intake splits a message into several items (or the person says it is one big requirement), it also writes a
规格卡 (spec): the goal, falsifiable done conditions for the whole, what must stay unchanged, what is out of scope,
and the evidence that will prove it; only what is missing is asked, the same way as for an item.

Confirming the spec makes one parent ticket (the spec and the overall criteria; it never goes on the coding line)
and one ordinary child ticket per item, each with its own criteria, linked links.parent / links.children. The
children are released in batches like the waves of a reform plan (reform.py): a batch goes on the line, and when
every child in it has passed acceptance the next batch goes by itself. A child can depend on earlier ones: it waits
for them and starts from their code (the main line once they merged, else the commit the dependency ended on).
A rejection that nothing will redo automatically pauses the feature until a person resumes it.

When every child is closed the parent goes to 待验证 with an evidence summary (each child's key, version and
verdict) next to the overall criteria. Accepting it closes the feature; rejecting it with a reason opens a
follow-up child that carries the reason onto the line, and the parent comes back for acceptance when that child
is done. Merging still follows release.py, acceptance is still a person's.

State lives on the parent ticket (links.epic); unreleased children and the parent carry links.later, which keeps
the coding line off them (orchestra.next_step).
"""
from __future__ import annotations

import re
import threading

from pathlib import Path

from .store import now

WAVE = 2
_LOCK = threading.RLock()
HELD = "等大需求「%s」的前一批验收通过再开工"
DEP = "在 %s 之后做：从它的改动开始，不要重做它已经做的。"
PARENT_HELD = "大需求的父单：由子单分批完成，最后整体验收"


def _clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def is_parent(t: dict | None) -> bool:
    return bool(t and (t.get("links") or {}).get("epic"))


def _parent_of(P, t: dict) -> dict | None:
    k = (t.get("links") or {}).get("parent")
    p = P.store.ticket(k) if k else None
    return p if is_parent(p) else None


def _log(e: dict, text: str) -> None:
    e.setdefault("log", []).append({"at": now(), "text": text})
    e["log"] = e["log"][-60:]


def _edit(P, parent: dict, fn) -> dict:
    """Change the feature's state on its parent ticket; fn(epic, links) mutates them in place."""
    with _LOCK:
        cur = P.store.ticket(parent["id"])
        links = dict(cur.get("links") or {})
        e = dict(links.get("epic") or {})
        fn(e, links)
        links["epic"] = e
        return P.store.update_ticket(cur["id"], P.flow.BY, links=links)


def _md(text: str) -> str:
    from .chat import _md
    return _md(text)


def _tell(P, parent: dict, text: str) -> None:
    """Into the group chat the feature came from, if it came from one (the chat is a courtesy, never the record)."""
    from . import chat
    chat._later(chat.tell, P, parent["key"], text)


# ---------------------------------------------------------------- bodies

def spec_md(spec: dict) -> list:
    L = ["## 目标", spec["goal"], "", "## 整体验收标准（每条都要能判断真假）"]
    L += ["- %s %s%s；怎么验：%s" % (d["id"], d["text"], "【待确认】" if d["open"] else "", d["check"]) for d in spec["done"]]
    L += ["", "## 必须保持不变", spec["keep"], "", "## 这次不做", spec["out"], "", "## 用什么证明做好了", spec["evidence"]]
    return L


def parent_body(s: dict, spec: dict, items: list) -> str:
    L = ["## 原话", s["text"], ""] + spec_md(spec) + ["", "## 拆成的子单（按顺序，分批放出）"]
    L += ["%d. %s%s" % (n, _clip(it["text"], 80), "（在第 %s 件之后）" % "、".join(str(a + 1) for a in it.get("after_n") or []) if it.get("after_n") else "")
          for n, it in enumerate(items, 1)]
    L += ["", "来源：需求对话 %s（%s，%s 发起，%d 轮）" % (s["id"], s["channel"], s["by"], s["rounds"])]
    return "\n".join(L)


def child_head(parent_title: str, pkey: str, n: int, total: int, spec: dict) -> list:
    return ["大需求「%s」（父单 %s）的第 %d/%d 个子单。只做这一件，别的子单各有各的单；整体目标是为了让你知道它放在哪儿。" % (parent_title, pkey, n, total), "",
            "## 整体目标", spec["goal"], "", "## 整体必须保持不变", spec["keep"], "", "## 整体不做", spec["out"], ""]


# ---------------------------------------------------------------- creating

def create(P, p: dict, s: dict, by: str, deps: dict | None = None, wave: int | None = None) -> dict:
    """The confirmed spec becomes a parent ticket and its children; the first batch goes on the line at once.
    deps: {"<item index>": [earlier item indices]}. Returns {"parent": key, "children": [keys]}."""
    from . import intake
    from .signoff import _add, epath
    work = [(i, it) for i, it in enumerate(s["items"]) if it["kind"] != "question"]
    if not work:
        raise ValueError("没有要做的事：咨询类已经直接答复")
    pos = {i: n for n, (i, _) in enumerate(work)}
    after = {}
    if deps is not None and not isinstance(deps, dict):
        raise ValueError("依赖要写成 {第几件: [它依赖的第几件]}")
    for k, v in (deps or {}).items():
        try:
            i = int(k)
            ds = [int(x) for x in (v if isinstance(v, list) else [v]) if str(x).strip() != ""]
        except (TypeError, ValueError):
            raise ValueError("依赖要写成 {第几件: [它依赖的第几件]}")
        if i not in pos or any(d not in pos or pos[d] >= pos[i] for d in ds):
            raise ValueError("第 %d 件只能依赖排在它前面的事" % (i + 1))
        if len(set(ds)) > 1:  # a change starts from one commit: two unmerged dependencies cannot both be its start
            raise ValueError("第 %d 件最多依赖一件事；要等几件都做完，就把它排在最后一批" % (i + 1))
        after[i] = sorted(set(ds), key=lambda d: pos[d])
    spec = s["spec"]
    title = "大需求：" + _clip(spec["goal"] if "待确认" not in spec["goal"] else s["text"], 50)
    items = [dict(it, after_n=[pos[d] for d in after.get(i, [])]) for i, it in work]
    w = max(1, min(10, int(wave or WAVE)))
    parent = P.store.create_ticket(p["id"], title, by, body=parent_body(s, spec, items), type="feature",
                                   links={"later": PARENT_HELD, "children": [],
                                          "epic": {"spec": spec, "wave": w, "auto": True, "batch": 0, "intake": s["id"], "by": by, "log": []}})
    _add(epath(P.data_dir, parent["key"]), "intake", by, {"session": s["id"], "text": s["text"], "understanding": "大需求规格卡：" + spec["goal"],
                                                          "ac": spec["done"], "open": [d["id"] for d in spec["done"] if d["open"]],
                                                          "confirmed_by": by, "requested_by": s["by"], "channel": s["channel"], "spec": spec})
    keys, held = [], HELD % _clip(title[4:], 30)
    for n, (i, it) in enumerate(work, 1):
        dep_keys = [keys[pos[d]] for d in after.get(i, [])]
        own = intake.ticket_body(s, it)
        m = re.search(r"\n## 验收标准[^\n]*\n(?:- [^\n]*\n?)*", own)
        ac, rest = (m.group(0).strip(), own[:m.start()] + own[m.end():]) if m else ("", own)
        L = ["大需求「%s」（父单 %s）的第 %d/%d 个子单。" % (title[4:], parent["key"], n, len(work)), "", ac]  # its own criteria first: they survive truncation
        if dep_keys:
            L += ["", "## 依赖", DEP % "、".join(dep_keys)]
        body = "\n".join(L + [""] + child_head(title[4:], parent["key"], n, len(work), spec)[2:]) + "\n" + rest.strip()
        links = {"parent": parent["key"], "order": n, "after": dep_keys, "later": held}
        if it.get("flow") and it["flow"].get("id"):
            links["flows"] = [it["flow"]["id"]]
        opened = [a for a in it["ac"] if a["open"]]
        if opened:
            links["open_ac"] = len(opened)
        t = P.store.create_ticket(p["id"], re.sub(r"\s+", " ", it["text"])[:60], by, body=body, type=intake.TICKET_TYPE[it["kind"]], links=links)
        _add(epath(P.data_dir, t["key"]), "intake", by, {"session": s["id"], "text": it["text"], "understanding": intake.understanding(it),
                                                         "ac": it["ac"], "open": [a["id"] for a in opened], "confirmed_by": by,
                                                         "requested_by": s["by"], "channel": s["channel"], "parent": parent["key"]})
        P.store.event(t["id"], by, "evidence", "大需求 %s 的第 %d 个子单，按规格卡建单：%d 条验收标准%s" % (
            parent["key"], n, len(it["ac"]), "，%d 条待确认" % len(opened) if opened else ""))
        it["ticket"] = t["key"]
        keys.append(t["key"])

    def put(e, links):
        links["children"] = keys
        _log(e, "%s 确认规格卡，拆成 %d 个子单，每批 %d 个" % (by, len(keys), w))
    parent = _edit(P, parent, put)
    P.store.event(parent["id"], by, "evidence", "规格卡确认：%d 条整体验收标准，拆成 %d 个子单（%s）" % (len(spec["done"]), len(keys), "、".join(keys)))
    release(P, p, parent, by)
    return {"parent": parent["key"], "children": keys}


# ---------------------------------------------------------------- batches

def _last(evs: list, *kinds) -> int:
    return max([e["id"] for e in evs if e["kind"] in kinds] or [0])


def _accepted_commit(P, proj: dict, t: dict) -> str:
    """The commit a person accepted on this ticket ("" when the latest change was not accepted, or none was made
    on the platform). Never a later commit on its branch: nobody looked at that."""
    from . import learn
    evs = P.store.events(t["id"])
    if _last(evs, "accept") <= max(_last(evs, "adopt"), _last(evs, "reject")):
        return ""
    ad, _ = learn._adopted(P.store, t["id"])
    return learn._resolve(Path(proj["root"]), (ad or {}).get("commit") or "") if ad else ""


def _merged(P, proj: dict, t: dict) -> bool:
    """On the main line already: merged by release.py, or its accepted commit is in main however it got there."""
    from . import release
    evs = P.store.events(t["id"])
    if _last(evs, "release") > max(_last(evs, "reject"), _last(evs, "adopt")):
        return True
    sha = _accepted_commit(P, proj, t)
    root = Path(proj["root"])
    main = release.main_branch(root, P.data_dir, proj["key"]) if sha else ""
    return bool(main) and release._run_ok(root, "merge-base", "--is-ancestor", sha, main)


def start_of(P, proj: dict, t: dict) -> tuple[str | None, str]:
    """Where a child's change starts: (commit, why). None for "no opinion" (not a child with a dependency), ""
    for the main line: its dependency merged, or was not accepted (its commits must not reach main through here)."""
    after = (t.get("links") or {}).get("after") or []
    if not after:
        return None, ""
    d = P.store.ticket(after[-1])
    if not d:
        return "", "依赖的 %s 找不到了，从主干当前的代码开始" % after[-1]
    if _merged(P, proj, d):
        return "", "依赖的 %s 已经合入主干，从主干当前的代码开始" % d["key"]
    sha = _accepted_commit(P, proj, d)
    if sha:
        return sha, "%s 还没合入主干，这次从它验收通过的提交 %s 开始" % (d["key"], sha[:10])
    return "", "依赖的 %s 没有验收通过的平台提交，从主干当前的代码开始" % d["key"]


def _settled(P, c: dict) -> bool:
    """Closed and done with: its merge was tried after the last acceptance and did not conflict."""
    evs = P.store.events(c["id"])
    acc = _last(evs, "accept")
    tried = max([e["id"] for e in evs if e["kind"] in ("release", "conflict") or (e["kind"] == "flow" and (e.get("data") or {}).get("release"))] or [0])
    return c["status"] == "closed" and tried > acc and _last(evs, "conflict") < acc


def _version(P, t: dict) -> str:
    rel = [e for e in P.store.events(t["id"]) if e["kind"] == "release"]
    return ((rel[-1].get("data") or {}).get("version") or "") if rel else ""


def _verdict(P, t: dict) -> str:
    v = [e for e in P.store.events(t["id"]) if e["kind"] in ("accept", "reject")]
    return v[-1]["body"] if v else ""


def _notes(P, kids: list) -> list:
    """What acceptance said about the children already done, so later ones avoid the same trouble."""
    out = []
    for c in kids:
        for e in P.store.events(c["id"]):
            if e["kind"] in ("reject", "accept") and "：" in (e.get("body") or ""):
                out.append("%s「%s」%s" % (c["key"], _clip(c["title"], 30), e["body"][:300]))
    return out[-8:]


def _open(kids: list) -> bool:
    """A released child is still open: the batch is not done."""
    return any(c and not (c.get("links") or {}).get("later") and c["status"] != "closed" for c in kids)


def release(P, proj: dict, parent: dict, by: str, n: int | None = None, when_done: bool = False, only: str = "") -> list:
    """Put the next batch on the line: children not yet released whose dependencies are all closed, up to the
    wave size (`when_done`: only if every released child is closed, checked under the lock so two acceptances at
    once release one batch, not two). Returns the keys released."""
    with _LOCK:
        parent = P.store.ticket(parent["id"])
        e = parent["links"]["epic"]
        kids = [P.store.ticket(k) for k in parent["links"].get("children") or []]
        kids = [c for c in kids if c]
        if when_done and _open(kids):
            return []
        closed = {c["key"] for c in kids if c["status"] == "closed"}
        ready = [c for c in kids if (c.get("links") or {}).get("later") and all(d in closed for d in c["links"].get("after") or [])]
        todo = [c for c in ready if c["key"] == only] if only else ready[: (n or e.get("wave") or WAVE)]
        if not todo:
            return []
        batch = int(e.get("batch") or 0) + 1
        notes = _notes(P, [c for c in kids if c["key"] in closed])
        made = []
        for c in todo:
            links = dict(c["links"])
            links.pop("later", None)
            links["batch"] = batch
            body = c.get("body") or ""
            base, why = start_of(P, proj, c)
            if base is not None:  # said here for the reader; the line asks again when the change starts (base_for)
                links["base"] = base
                dl = DEP % "、".join(links["after"])
                body = body.replace(dl, dl + "\n起点：%s。" % why, 1) if dl in body else body + "\n\n## 起点\n%s。" % why
            if notes:
                body += "\n\n## 前面子单验收时说的（照着避开同样的问题）\n" + "\n".join("- " + x for x in notes)
            P.store.update_ticket(c["id"], by, links=links, body=body)
            made.append(P.store.ticket(c["id"]))
        keys = [c["key"] for c in made]

        def put(e, links):
            e["batch"] = batch
            e.pop("paused", None)
            _log(e, ("上一批全部验收通过，自动放出第 %d 批：" if by == P.flow.BY else by + " 放出第 %d 批：") % batch + "、".join(keys))
        parent = _edit(P, parent, put)
        if parent["status"] in ("new", "analyzing", "confirm"):
            P.store.update_ticket(parent["id"], P.flow.BY, status="doing")
    P.store.event(parent["id"], P.flow.BY, "flow", "放出第 %d 批子单：%s" % (batch, "、".join(keys)))
    for c in made:
        P.store.event(c["id"], by, "comment", "由大需求 %s 放出，第 %d 批" % (parent["key"], batch))
        if c["links"].get("open_ac"):
            P.store.event(c["id"], by, "flow", "有验收标准还待确认，先不自动开始；和客户确认后点“交给自动处理”")
        else:
            P.flow.submit(proj, c)
    total = len(parent["links"].get("children") or [])
    _tell(P, parent, "大需求 **%s** 第 %d 批开工（共 %d 个子单）：\n%s" % (
        parent["key"], batch, total, "\n".join("- %s %s%s" % (c["key"], _md(_clip(c["title"], 40)), "（验收标准还待确认，确认后开工）" if c["links"].get("open_ac") else "")
                                             for c in made)))
    return keys


def _finish(P, proj: dict, parent: dict) -> None:
    """Every child is closed: the whole goes to a person, with what each child shipped next to the overall criteria."""
    from .signoff import _add, epath
    kids = [P.store.ticket(k) for k in parent["links"].get("children") or []]
    rows = [{"key": c["key"], "title": c["title"], "version": _version(P, c), "verdict": _verdict(P, c),
             "rejects": sum(1 for x in P.store.events(c["id"]) if x["kind"] == "reject")} for c in kids if c]
    spec = parent["links"]["epic"]["spec"]
    text = "全部 %d 个子单已完成，等整体验收：\n%s\n\n整体验收标准：\n%s" % (
        len(rows), "\n".join("- %s %s：%s；%s%s" % (r["key"], _clip(r["title"], 30), "版本 " + r["version"] if r["version"] else "未合并出版本",
                                                   r["verdict"] or "验收通过", "（退回过 %d 次）" % r["rejects"] if r["rejects"] else "") for r in rows),
        "\n".join("- %s %s" % (d["id"], d["text"]) for d in spec["done"]))
    _add(epath(P.data_dir, parent["key"]), "epic", P.flow.BY, {"children": rows, "done": spec["done"]})

    def put(e, links):
        e["summary"] = rows
        _log(e, "全部子单完成，转整体验收")
    parent = _edit(P, parent, put)
    P.store.event(parent["id"], P.flow.BY, "evidence", text, {"children": rows})
    P.store.update_ticket(parent["id"], P.flow.BY, status="verify")
    _tell(P, parent, "大需求 **%s** 的 %d 个子单都做完了，等整体验收：\n%s" % (  # keys and versions only: nothing to escape
        parent["key"], len(rows), "\n".join("- %s %s" % (r["key"], "版本 " + r["version"] if r["version"] else "已验收") for r in rows)))


def _follow_up(P, proj: dict, parent: dict, note: str, by: str) -> str:
    """The whole was rejected: the reason becomes a child of its own, on the line at once."""
    spec = parent["links"]["epic"]["spec"]
    kids = list(parent["links"].get("children") or [])
    n = len(kids) + 1
    body = "\n".join(child_head(parent["title"].replace("大需求：", "", 1), parent["key"], n, n, spec) + [
        "## 整体验收没通过（%s 退回）" % by, note, "", "这是整体验收退回后开的跟进子单：只解决上面说的问题，前面子单已经验收的行为不要改坏。", "",
        "## 验收标准（EARS）",
        "- A1 当按退回原因里说的情况操作时，系统应当不再出现这个问题；怎么验：按退回原因复现一遍并核对",
        "- A2 必须保持：已经验收通过的子单（%s）的行为不变；怎么验：跑现有测试，并抽查这些子单的验收例子" % "、".join(kids)])
    t = P.store.create_ticket(proj["id"], "跟进：%s（整体验收退回）" % _clip(parent["title"].replace("大需求：", "", 1), 40), by, body=body,
                              type="bug", links={"parent": parent["key"], "order": n, "after": [], "later": "跟进子单，马上放出", "follow_up": True})

    def put(e, links):
        links["children"] = list(links.get("children") or []) + [t["key"]]  # the current list, not the one read above
        _log(e, "%s 整体验收没通过，开跟进子单 %s：%s" % (by, t["key"], _clip(note, 80)))
    parent = _edit(P, parent, put)
    release(P, proj, parent, P.flow.BY, only=t["key"])
    return t["key"]


def outcome(P, proj: dict, t: dict, v: dict) -> list:
    """A verdict on a child or on the parent: move the feature on. Returns the keys of tickets it opened."""
    if is_parent(t):
        if v["passed"]:
            _edit(P, t, lambda e, links: _log(e, "%s 整体验收通过，大需求完成" % v["by"]))
            vers = [r["version"] for r in (t["links"]["epic"].get("summary") or []) if r.get("version")]
            _tell(P, t, "大需求 **%s** 整体验收通过，全部完成%s。" % (t["key"], "：版本 " + "、".join(vers) if vers else ""))
            return []
        k = _follow_up(P, proj, t, v["note"] or "没写原因", v["by"])
        _tell(P, t, "大需求 **%s** 整体验收没通过：%s\n已开跟进子单 %s 按这个原因重改，改完再整体验收。" % (t["key"], _md(_clip(v["note"], 200)), k))
        return [k]
    parent = _parent_of(P, t)
    if not parent:
        return []
    name = "子单 %s" % t["key"]
    if not v["passed"]:
        if v.get("gave_up"):
            why = "%s验收没通过，%s。退回原因：%s" % (name, v["gave_up"], _clip(v["note"], 200))
            _edit(P, parent, lambda e, links: (e.update(paused=why), _log(e, "暂停自动推进：" + why)))
            _tell(P, parent, "大需求 **%s** 暂停：%s" % (parent["key"], _md(why)))
        else:
            _edit(P, parent, lambda e, links: _log(e, "%s验收没通过，正在自动重改" % name))
        return []
    ver = _version(P, t)
    with _LOCK:
        t = P.store.ticket(t["id"])
        if t["status"] != "closed":  # accepted, but the merge conflicted: it is being redone, the whole is not done
            parent = _edit(P, parent, lambda e, links: _log(e, "%s验收通过但合并冲突，正在主干上重做" % name))
            if parent["status"] == "verify":
                P.store.update_ticket(parent["id"], P.flow.BY, status="doing")
                P.store.event(parent["id"], P.flow.BY, "flow", "子单 %s 合并时冲突，退回重做：整体验收等它重新完成" % t["key"])
            return []
        parent = _edit(P, parent, lambda e, links: _log(e, "%s验收通过%s" % (name, "，版本 " + ver if ver else "")))
        kids = [P.store.ticket(k) for k in parent["links"].get("children") or []]
        if all(c and c["status"] == "closed" for c in kids):
            if parent["status"] not in ("verify", "closed") and all(_settled(P, c) for c in kids):
                _finish(P, proj, parent)  # a child whose merge is still under way finishes it when its own verdict lands
            return []
    e = parent["links"]["epic"]
    if not e.get("auto") or e.get("paused"):
        return []
    return release(P, proj, parent, P.flow.BY, when_done=True)


def configure(P, parent: dict, by: str, auto: bool | None = None, resume: bool = False, wave: int | None = None) -> dict:
    def put(e, links):
        if auto is not None:
            e["auto"] = bool(auto)
            _log(e, "%s %s自动放下一批" % (by, "打开" if auto else "关闭"))
        if wave:
            try:
                e["wave"] = max(1, min(10, int(wave)))
            except (TypeError, ValueError):
                raise ValueError("每批数量要是 1 到 10 的数")
            _log(e, "%s 把每批改成 %d 个" % (by, e["wave"]))
        if resume and e.pop("paused", None):
            _log(e, "%s 恢复自动推进" % by)
    return _edit(P, parent, put)


def act(P, parent: dict, b: dict, by: str) -> dict:
    """{"action": "release" | "resume" | "auto" (on) | "wave" (n)}: what a person can do on the parent's page."""
    if not is_parent(parent):
        raise ValueError("这张工单不是大需求的父单")
    proj = P.store.project(parent["project_id"])
    a = b.get("action")
    if parent["status"] == "closed":
        raise ValueError("这个大需求已经整体验收通过了")
    if a == "release":
        try:
            n = max(1, min(10, int(b["n"]))) if b.get("n") else None
        except (TypeError, ValueError):
            raise ValueError("n 要是 1 到 10 的数")
        keys = release(P, proj, parent, by, n)
        if not keys:
            raise ValueError("没有能放出的子单：要么都放出了，要么在等依赖的子单验收通过")
        return dict(view(P, P.store.ticket(parent["id"])), opened=keys)
    if a == "auto" and not isinstance(b.get("on"), bool):
        raise ValueError("on 只能是 true 或 false")
    if a in ("resume", "auto", "wave"):
        parent = configure(P, parent, by, bool(b.get("on")) if a == "auto" else None, a == "resume", b.get("n") if a == "wave" else None)
        if a == "resume" and parent["links"]["epic"].get("auto"):  # a batch that finished while paused moves on now
            release(P, proj, parent, by, when_done=True)
        return view(P, P.store.ticket(parent["id"]))
    raise ValueError("action 只能是 release、resume、auto 或 wave")


def view(P, parent: dict) -> dict:
    """The parent with the live state of every child, for its page."""
    e = parent["links"]["epic"]
    kids = []
    for k in parent["links"].get("children") or []:
        c = P.store.ticket(k)
        if not c:
            continue
        lk = c.get("links") or {}
        kids.append({"key": c["key"], "title": c["title"], "status": c["status"], "order": lk.get("order"), "after": lk.get("after") or [],
                     "batch": lk.get("batch") or 0, "released": not lk.get("later"), "version": _version(P, c), "follow_up": bool(lk.get("follow_up")),
                     "rejects": sum(1 for x in P.store.events(c["id"]) if x["kind"] == "reject"), "open_ac": lk.get("open_ac") or 0})
    c = {"total": len(kids), "released": sum(1 for x in kids if x["released"]), "closed": sum(1 for x in kids if x["status"] == "closed"),
         "verify": sum(1 for x in kids if x["status"] == "verify")}
    return {"key": parent["key"], "status": parent["status"], "spec": e["spec"], "wave": e.get("wave") or WAVE, "auto": e.get("auto", True),
            "batch": e.get("batch") or 0, "paused": e.get("paused", ""), "log": e.get("log") or [], "children": kids, "counts": c,
            "summary": e.get("summary") or []}


def brief(P, parent: dict) -> str:
    """One line on where a feature stands, for 进度 in the chat."""
    v = view(P, parent)
    c = v["counts"]
    if parent["status"] == "closed":
        return "整体验收通过，已完成"
    if parent["status"] == "verify":
        return "%d 个子单都做完了，等整体验收" % c["total"]
    return "第 %d 批进行中，子单完成 %d/%d%s" % (v["batch"], c["closed"], c["total"], "（已暂停：%s）" % _clip(v["paused"], 60) if v["paused"] else "")


def refuse(t: dict, what: str) -> str:
    """Why `what` cannot be done on this ticket ("" when it can): a parent is only accepted as a whole once its
    children are done, and is never changed or merged itself; a child waiting for its batch is not accepted yet."""
    lk = t.get("links") or {}
    if lk.get("epic"):
        if what == "accept":
            return "" if t["status"] == "verify" else "大需求的父单要等全部子单完成、转到待验证后才能整体验收"
        return "大需求的父单不直接改代码，也不合并：%s请在子单上做" % {"run": "运行智能体", "handwork": "手写的改动", "ship": "合并",
                                                                      "status": "改状态"}.get(what, what)
    if lk.get("parent") and lk.get("later") and what == "accept":
        return "这个子单还没放出（%s），不能验收" % lk["later"]
    return ""


def base_for(P):
    """Asked by the coding line when a child's change starts: its dependency's code as it stands now."""
    def fn(p: dict, t: dict):
        return start_of(P, p, t)[0] if (t.get("links") or {}).get("parent") else None
    return fn


def listener(P):
    """How a feature hears the coding line's verdicts: a passed batch releases the next, the last child sends the
    whole to acceptance, a rejected whole opens a follow-up child."""
    def heard(proj: dict, t: dict, v: dict) -> dict | None:
        opened = outcome(P, proj, t, v)
        if opened and not is_parent(t):
            P.store.event(t["id"], P.flow.BY, "flow", "这一批全部验收通过，大需求自动放出下一批：%s" % "、".join(opened))
        return {"opened": opened} if opened else None
    heard.app = "大需求"
    return heard
