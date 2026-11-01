"""A project's team group (飞书, 钉钉, 企业微信): told when something happens that a person should know about.

A requirement raised in a group already hears back in that group (chat.py). The team is told separately, in the one
group bound to the project: a version merged, a merge waiting for a person, AI acceptance leaving a ticket for a
person, a rollback, a push to the code repository that failed, an analysis that needs a person's answer.

The group is chosen from the conversations the project's robot has already been in (someone @-mentioned it there),
so the platform only ever writes where its robot was added; binding it is a platform administrator's step. Telling
is a courtesy: it never raises and never holds anything up, and each message is noted on its ticket.

Settings in autoflow.json "notify": {"JB": {"conv": "<conversation key>", "dest": {...}, "title", "by", "ts"}}.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def _all(data_dir: Path) -> dict:
    try:
        v = json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("notify")
    except (OSError, ValueError, AttributeError):
        v = None
    return v if isinstance(v, dict) else {}


def conf(data_dir: Path, key: str) -> dict:
    c = _all(data_dir).get(key)
    return c if isinstance(c, dict) and isinstance(c.get("dest"), dict) else {}


def _put(data_dir: Path, key: str, c: dict | None) -> None:
    from .util_conf import update_autoflow
    v = {k: x for k, x in _all(data_dir).items() if k != key}
    if c:
        v[key] = c
    update_autoflow(data_dir, {"notify": v})


def _title(ck: str, c: dict) -> str:
    from ..bots import CHANNEL
    cid = ck.split(":", 2)[-1]
    return "%s 群 %s…%s（最近 %s）" % (CHANNEL.get(c.get("channel"), c.get("channel") or "聊天"), cid[:6], cid[-4:], c.get("seen") or "-")


def targets(P, p: dict) -> list:
    """The conversations this project's robot has been in and could speak in first."""
    from .. import bots
    from .chat import _load
    root = P.root(p)
    out = []
    for ck, c in _load(P.data_dir, "convs.json").items():
        if c.get("project") != p["key"] or not isinstance(c.get("dest"), dict):
            continue
        try:
            ok = bots.can_tell(root, c["dest"])
        except Exception:  # noqa: BLE001
            ok = False
        if ok:
            out.append({"id": ck, "title": _title(ck, c), "seen": c.get("seen") or "", "tickets": len(c.get("tickets") or [])})
    return sorted(out, key=lambda x: x["seen"], reverse=True)


def bind(P, p: dict, ck: str, by: str) -> dict:
    if not ck:
        _put(P.data_dir, p["key"], None)
        return view(P, p)
    from .chat import _load
    c = _load(P.data_dir, "convs.json").get(ck)
    if not c or ck not in {x["id"] for x in targets(P, p)}:
        raise ValueError("只能选这个项目的机器人待过、而且能主动发消息的群（先把机器人拉进群，在群里 @ 它说一句话）")
    _put(P.data_dir, p["key"], {"conv": ck, "dest": c["dest"], "title": _title(ck, c), "by": by, "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
    return view(P, p)


def view(P, p: dict) -> dict:
    c = conf(P.data_dir, p["key"])
    return {"bound": bool(c), "conv": c.get("conv") or "", "title": c.get("title") or "", "by": c.get("by") or "",
            "ts": c.get("ts") or "", "targets": targets(P, p)}


def link(P, key: str) -> str:
    base = os.environ.get("TMH_PUBLIC_URL", "").rstrip("/") or getattr(P, "public_url", "") or ""
    return "%s/#/t/%s" % (base, key) if base else ""


def say(P, p: dict, text: str, t: dict | None = None) -> bool:
    """Tell the project's group `text` (markdown), with a link to ticket `t`. Never raises."""
    c = conf(P.data_dir, p["key"])
    if not c:
        return False
    from .chat import _later

    def go():
        from .. import bots
        body = text + ("\n[打开工单](%s)" % link(P, t["key"]) if t and link(P, t["key"]) else "")
        try:
            ok, why = bots.send(P.root(p), c["dest"], body), ""
        except Exception as e:  # noqa: BLE001
            ok, why = False, str(e)[:120]
        if t:
            P.store.event(t["id"], "群消息", "chat", ("已告知项目群：" if ok else "没能告知项目群（%s）：" % (why or "发不出去")) + text.split("\n")[0][:120])
        return ok
    _later(go)
    return True
