"""Plain LLM calls: one request to an OpenAI-compatible chat endpoint, no tools, no files, no repository.

Work that only reads the words (and pictures) it is given — turning what a client said into ticket items,
rewriting criteria from answers — does not need a coding agent process. The endpoint is the project's routing
model (kbqa.router_conf: `router` in .tmh config or TMH_ROUTER_BASE_URL / TMH_ROUTER_MODEL / TMH_ROUTER_KEY);
`router.vision` (or TMH_ROUTER_VISION=1) says the model also reads images. A project whose route sets
`direct_api: false` never calls it.
"""
from __future__ import annotations

import os

from .. import kbqa
from . import agent_routes

NAME = "llm"


def conf(P, p: dict) -> dict:
    """The routing model for this project, with "ready" false when unconfigured or when the project forbids direct API."""
    try:
        c = kbqa.router_conf(P.root(p))
    except Exception:  # noqa: BLE001 - a project without config simply has no plain LLM
        return {"ready": False, "why": "没有读到项目配置"}
    try:
        allowed = agent_routes.direct_api_allowed(P.data_dir, p)
    except ValueError:
        allowed = False
    if c.get("ready") and not allowed:
        c = dict(c, ready=False, why="项目配置关闭了直接 API 调用")
    env = os.environ.get("TMH_ROUTER_VISION")
    c["vision"] = env == "1" if env in ("0", "1") else bool(c.get("vision"))
    return c


def chat(c: dict, system: str, text: str, images: list | None = None, timeout: int = 120, max_tokens: int = 4000) -> str:
    """The reply text. `images` are data URLs, sent only when the model reads images."""
    content = text
    if images and c.get("vision"):
        content = [{"type": "text", "text": text}] + [{"type": "image_url", "image_url": {"url": u}} for u in images]
    data = kbqa._post(c, {"model": c["model"], "temperature": 0, "max_tokens": max_tokens,
                          "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}]}, timeout=timeout)
    msg = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
    if not isinstance(msg, str) or not msg.strip():
        raise ValueError("模型没有返回内容")
    return msg
