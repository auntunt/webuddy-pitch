"""Per-task test-environment values (e.g. database address, account, password).

Stored in a private file under the data directory, never in ticket text, prompts,
logs or exports. Injected only as `TMH_ENV_<NAME>` into the subprocess environment
of that task. Agents see names, not values; stored output is redacted.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .errors import ApiError
from .executor_setup import _write_private

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")


def _path(data_dir, ticket_key):
    if not re.fullmatch(r"[A-Za-z0-9_-]+-\d+", ticket_key or ""):
        raise ApiError(400, "任务编号不正确")
    return Path(data_dir) / "task-secrets" / (ticket_key + ".json")


def env_name(name: str) -> str:
    if not NAME.match(name or ""):
        raise ApiError(400, "测试环境项名称只能是字母、数字和下划线，且以字母开头")
    return "TMH_ENV_" + name.upper()


def save(data_dir, ticket_key, items):
    """items: [{name, value}]. Returns the non-secret names that were stored."""
    seen, clean = set(), {}
    for item in items or []:
        name, value = str(item.get("name", "")).strip(), str(item.get("value", ""))
        env_name(name)
        if name.upper() in seen:
            raise ApiError(400, "测试环境项名称重复：" + name)
        seen.add(name.upper())
        if value:
            clean[name] = value
    path = _path(data_dir, ticket_key)
    if clean:
        _write_private(path, json.dumps(clean, ensure_ascii=False, indent=1) + "\n")
    elif path.exists():
        path.unlink()
    return sorted(clean)


def names(data_dir, ticket_key):
    path = _path(data_dir, ticket_key)
    return sorted(json.loads(path.read_text(encoding="utf-8-sig"))) if path.exists() else []


def environment(data_dir, ticket_key) -> dict:
    """Environment variables for this task's commands and agent run."""
    path = _path(data_dir, ticket_key)
    if not path.exists():
        return {}
    return {env_name(k): v for k, v in json.loads(path.read_text(encoding="utf-8-sig")).items()}


def redact(text: str, data_dir, ticket_key) -> str:
    """Replace every stored value in text before it is stored or shown."""
    for value in sorted(set(environment(data_dir, ticket_key).values()), key=len, reverse=True):
        if value:
            text = text.replace(value, "[已隐藏]")
    return text
