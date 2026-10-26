"""Operator-owned project routes; selecting an engine never grants execution.

Optional <data>/agent-routes.json uses schema 1, an optional ``default`` route,
and ``projects`` keyed by project code. Project fields override default fields.
Routes contain ``agent``, ``allowed_agents`` and/or ``direct_api``. No secrets,
shell commands or user identities belong here. Invalid configuration fails
closed instead of silently sending a task to another model provider.
"""
from __future__ import annotations

import json
from pathlib import Path
import re


AGENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
PROJECT = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,9}$")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("执行器路由包含重复字段：%s" % key)
        result[key] = value
    return result


def _validate(route):
    if not isinstance(route, dict) or set(route) - {"agent", "allowed_agents", "direct_api"}:
        raise ValueError("执行器路由仅支持 agent、allowed_agents 和 direct_api")
    if "agent" in route and (not isinstance(route["agent"], str) or not AGENT.fullmatch(route["agent"])):
        raise ValueError("执行器路由的 agent 名称不合法")
    if "allowed_agents" in route:
        values = route["allowed_agents"]
        if (not isinstance(values, list) or not values or
                any(not isinstance(v, str) or not AGENT.fullmatch(v) for v in values) or
                len(set(values)) != len(values)):
            raise ValueError("执行器路由的 allowed_agents 必须是不重复的执行器名称列表")
        if route.get("agent") and route["agent"] not in values:
            raise ValueError("路由默认执行器不在 allowed_agents 中")
    if "direct_api" in route and type(route["direct_api"]) is not bool:
        raise ValueError("执行器路由的 direct_api 必须是布尔值")
    return route


def route(data_dir, project=None):
    """Return a validated effective route, or {} for unchanged legacy behavior."""
    path = Path(data_dir) / "agent-routes.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError) as exc:
        raise ValueError("执行器路由配置无法读取，未选择其他执行器") from exc
    try:
        value = json.loads(raw, object_pairs_hook=_object)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("执行器路由配置不是有效 JSON，未选择其他执行器") from exc
    if (not isinstance(value, dict) or set(value) - {"schema", "default", "projects"} or
            type(value.get("schema")) is not int or value["schema"] != 1):
        raise ValueError("执行器路由配置需要 schema: 1，且仅支持 default 和 projects")
    default = _validate(value.get("default", {}))
    projects = value.get("projects", {})
    if not isinstance(projects, dict):
        raise ValueError("执行器路由 projects 必须是项目代号到路由的对象")
    normalized = {}
    for key, setting in projects.items():
        if not PROJECT.fullmatch(key) or key.upper() in normalized:
            raise ValueError("执行器路由项目代号无效或重复")
        normalized[key.upper()] = _validate(dict(default, **_validate(setting)))
    key = project.get("key", "") if isinstance(project, dict) else project or ""
    return dict(normalized.get(str(key).upper(), default))


def resolve(data_dir, project=None, requested=None, fallback=""):
    """Explicit engine wins within the route allowlist; configured routes never fail over."""
    selected_route = route(data_dir, project)
    chosen = requested or selected_route.get("agent") or fallback
    if not selected_route:
        return chosen
    allowed = selected_route.get("allowed_agents")
    if allowed is not None and chosen not in allowed:
        raise ValueError("此项目仅允许执行器：%s；未启动其他执行器" % "、".join(allowed))
    if not chosen:
        raise ValueError("此项目没有可用的执行器路由，请配置 agent")
    from .agents import available
    if not any(item["name"] == chosen and item["available"] for item in available(data_dir)):
        raise ValueError("项目指定执行器 %s 不可用，未切换到其他执行器" % chosen)
    return chosen


def direct_api_allowed(data_dir, project=None):
    """Keep legacy API routing unless an operator explicitly disables it here."""
    return route(data_dir, project).get("direct_api", True)
