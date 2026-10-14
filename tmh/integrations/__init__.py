"""Ops-tool integrations: one adapter per tool, one normalized model, drop-in plugins.

Configuration lives in .tmh/config.json:

    "integrations": {
      "tools": {
        "jira":  {"type": "jira", "url": "https://jira.corp", "project": "OA",
                  "auth": {"type": "bearer", "token_env": "JIRA_TOKEN"}},
        "ci":    {"type": "jenkins", "url": "https://ci.corp", "job": "oa/oa-web/master",
                  "auth": {"type": "basic", "user": "li", "password_env": "JENKINS_TOKEN"}}
      },
      "defaults": {"issues": "jira", "builds": "ci"},   # optional; else the first tool that can
      "agent_writes": false                             # MCP write tools only dry-run unless true
    }

Adding a tool type: drop a module into <repo>/.tmh/integrations/<name>.py that
subclasses `tmh.integrations.Integration` and sets TYPE; or describe its API
with the `generic` type in config, no code at all.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .. import config as cfgmod
from .base import (CAPABILITIES, Build, Change, Doc, Integration, IntegrationError, Issue, NotSupported,  # noqa: F401
                   QualityIssue, strip_html, norm_status)
from .confluence import Confluence
from .generic import Generic
from .github import GitHub
from .gitlab import GitLab
from .jenkins import Jenkins
from .jira import Jira
from .notify import DingTalk, Feishu, WeCom, Webhook
from .sonarqube import SonarQube
from .zentao import ZenTao

BUILTIN = [Jira, ZenTao, GitHub, GitLab, Jenkins, SonarQube, Confluence, DingTalk, Feishu, WeCom, Webhook, Generic]
CAP_CN = {"issues": "工单", "builds": "构建", "changes": "合并请求", "quality": "代码质量", "docs": "文档", "notify": "通知"}


def plugin_dir(root: Path) -> Path:
    return cfgmod.tmh_dir(root) / "integrations"


def registry(root: Path | None = None) -> dict:
    """TYPE -> class: built-ins, then plugins from <repo>/.tmh/integrations/*.py (plugins may override)."""
    reg = {c.TYPE: c for c in BUILTIN}
    if root is None:
        return reg
    d = plugin_dir(root)
    if d.is_dir():
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("_"):
                continue
            modname = "tmh_plugin_" + f.stem
            spec = importlib.util.spec_from_file_location(modname, str(f))
            mod = importlib.util.module_from_spec(spec)
            try:
                sys.modules[modname] = mod
                spec.loader.exec_module(mod)
            except Exception as e:  # a broken plugin must not take the CLI down
                print("插件 %s 加载失败：%s" % (f.name, e), file=sys.stderr)
                continue
            for obj in vars(mod).values():
                if isinstance(obj, type) and issubclass(obj, Integration) and obj is not Integration and getattr(obj, "TYPE", ""):
                    reg[obj.TYPE] = obj
    return reg


def settings(root: Path) -> dict:
    return cfgmod.load(root).get("integrations") or {}


def tools(root: Path) -> dict:
    return settings(root).get("tools") or {}


def make(root: Path, name: str, conf: dict | None = None, dry_run: bool = True) -> Integration:
    conf = conf if conf is not None else tools(root).get(name)
    if conf is None:
        raise IntegrationError("没有名为 %s 的接入，先用 tmh int add 配置（tmh int list 查看已有的）" % name)
    t = conf.get("type", name)
    reg = registry(root)
    if t not in reg:
        raise IntegrationError("不认识的工具类型 %s。内置：%s；或在 .tmh/integrations/ 放插件" % (t, "、".join(sorted(reg))))
    return reg[t](name, conf, dry_run=dry_run)


def pick(root: Path, capability: str, via: str = "", dry_run: bool = True) -> Integration:
    """The instance that serves a capability: --via, then defaults, then the first configured tool that can."""
    if via:
        inst = make(root, via, dry_run=dry_run)
        if capability not in inst.CAPABILITIES:
            raise NotSupported("%s（%s）不提供%s能力" % (via, inst.TYPE, CAP_CN.get(capability, capability)))
        return inst
    s = settings(root)
    d = (s.get("defaults") or {}).get(capability)
    if d:
        return make(root, d, dry_run=dry_run)
    for name, conf in (s.get("tools") or {}).items():
        if conf.get("disabled"):
            continue
        try:
            inst = make(root, name, conf, dry_run=dry_run)
        except IntegrationError:
            continue
        if capability in inst.CAPABILITIES:
            return inst
    raise IntegrationError("还没有接入能提供%s的工具。用 tmh int add 配置，例如：%s" % (CAP_CN.get(capability, capability), EXAMPLES.get(capability, "")))


def available(root: Path, capability: str) -> bool:
    try:
        pick(root, capability)
        return True
    except IntegrationError:
        return False


def all_env_names(root: Path) -> list:
    out = []
    for name in tools(root):
        try:
            out += make(root, name).env_names()
        except IntegrationError:
            pass
    return list(dict.fromkeys(out))


EXAMPLES = {
    "issues": "tmh int add jira --type jira --url https://jira.example.com --auth bearer --token-env JIRA_TOKEN",
    "builds": "tmh int add ci --type jenkins --url https://jenkins.example.com --user 账号 --auth basic --password-env JENKINS_TOKEN --set job=oa/master",
    "changes": "tmh int add gitlab --type gitlab --url https://gitlab.example.com --token-env GITLAB_TOKEN --set project=oa/oa-web",
    "quality": "tmh int add sonar --type sonarqube --url https://sonar.example.com --auth bearer --token-env SONAR_TOKEN --set project=oa",
    "docs": "tmh int add wiki --type confluence --url https://wiki.example.com --auth bearer --token-env CONFLUENCE_TOKEN",
    "notify": "tmh int add group --type dingtalk --set webhook_env=DINGTALK_WEBHOOK",
}
