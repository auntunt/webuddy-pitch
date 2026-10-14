"""Common shape of every ops-tool adapter.

An adapter turns one tool's API (Jira, Jenkins, 禅道 …) into a few normalized
records, so the rest of tmh, the agents and the MCP server never care which
tool a team uses. Adapters declare the capabilities they implement:

    issues   工单/需求/缺陷   get_issue, search_issues, add_comment*, transition*
    builds   构建/流水线      list_builds, get_build, build_log, trigger_build*
    changes  合并请求/评审    list_changes, get_change
    quality  代码质量         quality_issues, quality_gate
    docs     文档/知识        search_docs, get_doc
    notify   群通知           send*

Methods marked * write to the tool. They go through the HTTP client, which in
dry-run mode (the default for every write) records the request instead of
sending it; `--confirm` turns that off.

Credentials never appear in config: an instance names the environment
variables that hold them (token_env, password_env, webhook_env …).
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

CAPABILITIES = ("issues", "builds", "changes", "quality", "docs", "notify")

# Config keys that would hold a secret in plain text. Any of these with a value
# is rejected; the *_env form names an environment variable instead.
SECRET_KEYS = {"token", "password", "passwd", "secret", "api_key", "apikey", "private_token", "access_token", "webhook", "cookie"}


class IntegrationError(Exception):
    """A tool call failed in a way the user can act on (bad URL, missing env, 401 …)."""


class NotSupported(IntegrationError):
    pass


@dataclass
class Issue:
    key: str
    title: str = ""
    status: str = ""
    type: str = ""
    priority: str = ""
    assignee: str = ""
    reporter: str = ""
    description: str = ""
    url: str = ""
    created: str = ""
    updated: str = ""
    resolved: str = ""                               # when it was resolved/closed in the tool; empty while open
    labels: list = field(default_factory=list)
    links: list = field(default_factory=list)       # [{"key", "relation", "title"}]
    comments: list = field(default_factory=list)    # [{"author", "created", "body"}]
    source: str = ""                                 # instance name

    def to_dict(self):
        return asdict(self)


@dataclass
class Build:
    job: str
    number: str = ""
    status: str = ""          # success / failed / running / aborted / unstable / unknown
    started: str = ""
    duration_s: float = 0
    url: str = ""
    commit: str = ""
    branch: str = ""
    cause: str = ""
    source: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Change:
    id: str
    title: str = ""
    state: str = ""
    author: str = ""
    source_branch: str = ""
    target_branch: str = ""
    url: str = ""
    updated: str = ""
    description: str = ""
    source: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class QualityIssue:
    rule: str
    severity: str = ""
    type: str = ""
    file: str = ""
    line: int = 0
    message: str = ""
    url: str = ""
    source: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Doc:
    id: str
    title: str = ""
    url: str = ""
    space: str = ""
    excerpt: str = ""
    body: str = ""
    updated: str = ""
    source: str = ""

    def to_dict(self):
        return asdict(self)


def norm_status(s: str) -> str:
    s = (s or "").strip().lower()
    table = {
        "success": "success", "successful": "success", "passed": "success", "ok": "success", "stable": "success",
        "failure": "failed", "failed": "failed", "error": "failed", "broken": "failed",
        "unstable": "unstable", "aborted": "aborted", "canceled": "aborted", "cancelled": "aborted", "skipped": "aborted",
        "running": "running", "building": "running", "pending": "running", "created": "running", "in_progress": "running",
        "waiting_for_resource": "running", "preparing": "running", "manual": "running", "scheduled": "running",
    }
    return table.get(s, s or "unknown")


def strip_html(html: str) -> str:
    if not html:
        return ""
    t = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</tr>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    for a, b in (("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&amp;", "&")):
        t = t.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def env_value(name: str, what: str = "凭据") -> str:
    if not name:
        raise IntegrationError("没有配置%s对应的环境变量名" % what)
    v = os.environ.get(name, "")
    if not v:
        raise IntegrationError("环境变量 %s 未设置（%s）。在启动 Codex / Claude Code 的终端里 export %s=...，不要写进配置文件。" % (name, what, name))
    return v


def check_no_secrets(name: str, conf: dict, path: str = "") -> None:
    for k, v in conf.items():
        where = "%s.%s" % (path, k) if path else k
        if isinstance(v, dict):
            check_no_secrets(name, v, where)
        elif k.lower() in SECRET_KEYS and v:
            raise IntegrationError("integrations.%s.%s 直接写了凭据。改成 %s_env: \"环境变量名\"，凭据只放环境变量。" % (name, where, k))


class Integration:
    """Base class. Subclasses set TYPE, TITLE, CAPABILITIES and implement the methods they support."""

    TYPE = ""
    TITLE = ""
    CAPABILITIES: tuple = ()
    # Describes the config keys for `tmh int add` and docs: {key: help}
    OPTIONS: dict = {}

    def __init__(self, name: str, conf: dict, dry_run: bool = True):
        from .http import HttpClient
        check_no_secrets(name, conf)
        self.name = name
        self.conf = conf
        self.url = (conf.get("url") or "").rstrip("/")
        self.http = HttpClient(self.url, conf, dry_run=dry_run)

    # -- helpers -------------------------------------------------------------
    def opt(self, key: str, default=None):
        v = self.conf.get(key, default)
        return default if v in (None, "") else v

    def env_names(self) -> list:
        """Environment variable names this instance reads (for `tmh int list` and Codex MCP env passthrough)."""
        out = []

        def walk(d):
            for k, v in d.items():
                if isinstance(v, dict):
                    walk(v)
                elif k.endswith("_env") and isinstance(v, str) and v:
                    out.append(v)
        walk(self.conf)
        return list(dict.fromkeys(out))

    def unsupported(self, what: str):
        raise NotSupported("%s（%s）不支持 %s" % (self.name, self.TYPE, what))

    # -- every adapter -------------------------------------------------------
    def ping(self) -> str:
        """Cheap authenticated read proving URL + credentials work. Returns a short description."""
        self.unsupported("连通性检查")

    # -- issues --------------------------------------------------------------
    def get_issue(self, key: str, comments: int = 5) -> Issue:
        self.unsupported("查看工单")

    def search_issues(self, query: str, limit: int = 20) -> list:
        self.unsupported("搜索工单")

    def issues_for_ref(self, key: str) -> list:
        """What a ticket id written in a commit message stands for, as (Issue, via) pairs. Usually just that issue;
        a tool where commits name merge requests (GitHub) returns the issues the request closed, via = its key."""
        return [(self.get_issue(key), "")]

    def add_comment(self, key: str, body: str) -> dict:
        self.unsupported("评论工单")

    def transition(self, key: str, to: str) -> dict:
        self.unsupported("流转工单状态")

    # -- builds --------------------------------------------------------------
    def list_builds(self, job: str = "", limit: int = 10) -> list:
        self.unsupported("查看构建")

    def get_build(self, job: str = "", number: str = "last") -> Build:
        self.unsupported("查看构建")

    def build_log(self, job: str = "", number: str = "last", tail: int = 200) -> str:
        self.unsupported("查看构建日志")

    def trigger_build(self, job: str = "", params: dict | None = None) -> dict:
        self.unsupported("触发构建")

    # -- changes -------------------------------------------------------------
    def list_changes(self, state: str = "open", limit: int = 20) -> list:
        self.unsupported("查看合并请求")

    def get_change(self, cid: str) -> Change:
        self.unsupported("查看合并请求")

    def change_files(self, cid: str) -> list:
        self.unsupported("查看合并请求改动文件")

    # -- quality -------------------------------------------------------------
    def quality_issues(self, path: str = "", severity: str = "", limit: int = 100) -> list:
        self.unsupported("查看质量问题")

    def quality_gate(self) -> dict:
        self.unsupported("查看质量门禁")

    # -- docs ----------------------------------------------------------------
    def search_docs(self, query: str, limit: int = 10) -> list:
        self.unsupported("搜索文档")

    def get_doc(self, did: str) -> Doc:
        self.unsupported("查看文档")

    # -- notify --------------------------------------------------------------
    def send(self, title: str, text: str) -> dict:
        self.unsupported("发送通知")
