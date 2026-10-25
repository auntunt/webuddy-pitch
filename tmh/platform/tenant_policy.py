"""Fail-closed policy for server-selected tenants, independent of HTTP adapters.

The trusted gateway fixes tenant and actor. This module never accepts an actor
or tenant from business payloads, never substitutes project ACL for human
acceptance, and never treats a process group as an execution sandbox.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
import re
from urllib.parse import unquote

from .errors import ApiError

# Deliberately frozen inventory. A new server route needs an explicit policy
# review; the inventory test must fail rather than silently granting admin access.
API_ROUTES = frozenset(tuple(line.split(" ", 1)) for line in """
GET /api/meta
POST /api/agent/<operation>
GET /api/workspace
GET /api/projects/<key>/pilots
POST /api/projects/<key>/pilots
GET /api/projects/<key>/pilots/<pid>
POST /api/projects/<key>/pilots/<pid>
GET /api/projects/<key>/meetings
POST /api/projects/<key>/meetings
GET /api/projects/<key>/meetings/<mid>
POST /api/projects/<key>/meetings/<mid>
GET /api/tickets/<key>/brief
POST /api/tickets/<key>/brief
POST /api/delivery-content
GET /api/deliveries/<did>/content
POST /api/deliveries/<did>/content
GET /api/deliveries/<did>/coverage
POST /api/deliveries/<did>/coverage
GET /api/team
GET /api/handoffs
POST /api/handoffs
POST /api/team
GET /api/memory
GET /api/memory/brief
POST /api/memory
GET /api/learning
POST /api/learning
GET /api/projects
POST /api/projects
GET /api/projects/<key>/library
POST /api/projects/<key>/library
GET /api/projects/<key>/knowledge/search
GET /api/projects/<key>/knowledge/file
GET /api/org/knowledge
GET /api/projects/<key>/habits
GET /api/projects/<key>
POST /api/projects/bootstrap
GET /api/delivery/catalog
GET /api/deliveries
POST /api/deliveries
GET /api/deliveries/<did>
POST /api/deliveries/<did>
GET /api/projects/<key>/related
GET /api/projects/<key>/flows/<fid>
GET /api/projects/<key>/kb
GET /api/projects/<key>/kb/tree
GET /api/projects/<key>/atlas
GET /api/projects/<key>/atlas/flow/<fid>
GET /api/projects/<key>/arch
GET /api/projects/<key>/arch/<did>
GET /api/projects/<key>/kb/page
POST /api/projects/<key>/kb/confirm
GET /api/projects/<key>/kb/questions
POST /api/projects/<key>/kb/ask
POST /api/projects/<key>/kb/answer
POST /api/projects/<key>/kb/triage
POST /api/projects/<key>/intake
GET /api/intake/<sid>
POST /api/intake/<sid>
POST /api/tickets/<key>/ask-client
POST /api/tickets/<key>/client-change
POST /api/tickets/<key>/intake-retry
GET /api/tickets/<key>/path-map
POST /api/tickets/<key>/path-map
POST /api/projects/<key>/pins
GET /api/projects/<key>/pins
POST /api/projects/<key>/capture-token
GET /api/pins/<pid>
POST /api/pins/<pid>/intake
GET /api/projects/<key>/kb/metrics
GET /api/tickets/<key>/similar
POST /api/projects/<key>/similar
GET /api/projects/<key>/bots
POST /api/projects/<key>/kb/overrule
GET /api/projects/<key>/integrations
POST /api/projects/<key>/import
GET /api/projects/<key>/survey
POST /api/projects/<key>/survey
POST /api/projects/<key>/survey/stop
GET /api/lead
POST /api/projects/<key>/catchup
GET /api/projects/<key>/loop
GET /api/projects/<key>/inbox
GET /api/projects/<key>/points
POST /api/projects/<key>/points
GET /api/assist
POST /api/assist
GET /api/projects/<key>/sessions
POST /api/projects/<key>/sessions
GET /api/sessions/<sid>
POST /api/sessions/<sid>
POST /api/sessions/<sid>/messages
POST /api/projects/<key>/command
POST /api/sessions/<sid>/command/<mid>
POST /api/sessions/<sid>/ticket-draft
POST /api/sessions/<sid>/ticket
POST /api/tickets/<key>/accept
GET /api/projects/<key>/learn
POST /api/learn/holdout
GET /api/projects/<key>/lessons/<lid>
GET /api/projects/<key>/lessons/<lid>/share
POST /api/projects/<key>/lessons/<lid>
POST /api/projects/<key>/evals/run
POST /api/projects/<key>/evals/cases
POST /api/projects/<key>/evals/history
POST /api/projects/<key>/evals/history/import
POST /api/projects/<key>/alerts
GET /api/projects/<key>/reforms
GET /api/projects/<key>/reforms/deps
POST /api/projects/<key>/reforms
POST /api/projects/<key>/reforms/<pid>
GET /api/tickets
POST /api/tickets
GET /api/tickets/<key>
GET /api/tickets/<key>/epic
POST /api/tickets/<key>/epic
GET /api/tickets/<key>/evidence
POST /api/tickets/<key>/evidence
GET /api/tickets/<key>/upstream
POST /api/tickets/<key>/upstream
GET /api/projects/<key>/upstream
GET /api/projects/<key>/baseline
POST /api/projects/<key>/baseline/seal
GET /api/projects/<key>/ledger
POST /api/tickets/<key>
GET /api/testbox
GET /api/projects/<key>/releases
POST /api/tickets/<key>/release
GET /api/tickets/<key>/preview
POST /api/tickets/<key>/preview
GET /api/projects/<key>/preview-conf
POST /api/projects/<key>/preview-conf
GET /api/tickets/<key>/starter
POST /api/tickets/<key>/claim
POST /api/tickets/<key>/handwork
POST /api/projects/<key>/scan
GET /api/readiness
POST /api/testbox
POST /api/testbox/<action>
POST /api/tickets/<key>/comments
GET /api/tickets/<key>/related
GET /api/tickets/<key>/context
POST /api/tickets/<key>/runs
POST /api/tickets/<key>/push
POST /api/projects/<key>/runs
GET /api/runs
GET /api/runs/<rid>
POST /api/runs/<rid>/cancel
POST /api/runs/<rid>/retry
POST /api/runs/<rid>/recover
POST /api/runs/<rid>/decide
POST /api/runs/<rid>/recheck
GET /api/runs/<rid>/recheck
POST /api/runs/<rid>/recheck/recover
GET /api/projects/<key>/metrics
GET /api/projects/<key>/report
GET /api/tickets/<key>/prompt
POST /api/tickets/<key>/prompt
GET /api/stats
GET /api/clients
POST /api/clients
GET /api/clients/<cid>
POST /api/clients/<cid>
POST /api/workbench/intake
GET /api/requirements
GET /api/projects/<key>/versions
POST /api/projects/<key>/standing
POST /api/projects/<key>/shares
POST /api/projects/<key>/shares/<sid>/revoke
GET /api/today
GET /api/chats
""".strip().splitlines())

LEVELS = {"viewer": 1, "contributor": 2, "manager": 3}
FILTERED_LISTS = frozenset(("/api/projects", "/api/workspace", "/api/tickets", "/api/runs"))
PUBLIC_CAPABILITIES = ("/bot/", "/hook/alert/", "/capture/", "/pv/", "/v/", "/sign/", "/ask/")
# These projections still read across projects, even when their UI shows a
# project selector. They remain admin-only until their query layer is scoped.
ADMIN_GLOBAL = frozenset(("/api/org/knowledge", "/api/lead", "/api/readiness", "/api/testbox",
                         "/api/today", "/api/chats", "/api/clients", "/api/requirements"))
AGENT_OPERATIONS = frozenset("""status projects_list tickets_list ticket_get ticket_create message_send
messages_list request_get run_get run_start run_cancel run_retry run_recheck preview_get preview_start
candidates_list candidate_get candidate_submit candidate_verify candidate_cancel candidate_preview
candidate_assess candidate_decide harness_recipes harness_probe_start harness_probe_get harness_probe_cancel
harness_library library_get library_search library_read library_build library_cancel library_resume
library_reference library_unlink""".split())
SAFE_POSTS = frozenset((
    # Personal trial records only: no models, process launch or task moves.
    "/api/projects/<key>/pilots", "/api/projects/<key>/pilots/<pid>",
    "/api/projects/<key>/meetings", "/api/projects/<key>/meetings/<mid>",
    "/api/tickets/<key>/brief", "/api/deliveries/<did>/coverage",
    "/api/delivery-content", "/api/deliveries/<did>/content",
    "/api/handoffs", "/api/tickets/<key>/comments",
    "/api/projects/<key>/sessions", "/api/sessions/<sid>", "/api/sessions/<sid>/ticket-draft",
    "/api/projects/<key>/similar", "/api/projects/<key>/capture-token",
    "/api/projects/<key>/kb/confirm", "/api/projects/<key>/kb/answer",
    "/api/projects/<key>/kb/overrule", "/api/tickets/<key>/path-map",
    "/api/projects/<key>/evals/cases", "/api/projects/<key>/shares/<sid>/revoke",
    "/api/clients", "/api/clients/<cid>", "/api/projects/<key>/points", "/api/learn/holdout",
))
SPECIAL_ROUTES = (
    ("GET", "/e/<key>.intoto.json", r"/e/(?P<key>[A-Za-z0-9]+-\d+)\.intoto\.json"),
    ("GET", "/e/<key>", r"/e/(?P<key>[A-Za-z0-9]+-\d+)(?:/f/[0-9a-f]{64}\.[a-z]+)?"),
    ("GET", "/p/<key>/code.bundle", r"/p/(?P<key>[A-Za-z0-9]+)/code\.bundle"),
    ("GET", "/p/<key>/report/<path>", r"/p/(?P<key>[^/]+)/report/.*"),
    ("GET", "/p/<key>/efficiency", r"/p/(?P<key>[^/]+)/efficiency"),
)


def enabled(P):
    return getattr(P, "tenant_context", None) is not None


def identity(P, actor):
    """Read current authority; absence and malformed registry data fail closed."""
    if not enabled(P):
        return {"legacy": True, "actor": actor}
    if not isinstance(actor, str) or not actor:
        raise ApiError(401, "需要有效的租户身份")
    value = P.tenant_context.current_actor(actor)
    if not isinstance(value, dict) or value.get("role") not in ("admin", "member", "viewer"):
        raise ApiError(403, "当前账号没有此租户的有效成员权限")
    grants = value.get("project_grants")
    if not isinstance(grants, dict) or any(not isinstance(k, str) or v not in LEVELS for k, v in grants.items()):
        raise ApiError(403, "项目授权配置不可用")
    if not isinstance(value.get("authz_revision"), int) or isinstance(value["authz_revision"], bool):
        raise ApiError(403, "权限修订不可用")
    return dict(value, actor=actor, tenant_id=P.tenant_context.tenant_id,
                platform_owner=value.get("platform_owner") is True, project_grants=dict(grants))


def _effective(who, key):
    if who["role"] == "admin":
        return "manager"
    level = who["project_grants"].get(key)
    return "viewer" if level and who["role"] == "viewer" else level


def visible_projects(P, actor):
    """Current readable projects; apply this before counts and pagination."""
    if not enabled(P):
        return P.store.projects()
    who = identity(P, actor)
    return [p for p in P.store.projects() if _effective(who, p["key"])]


def _project(P, key):
    if not isinstance(key, (str, int)) or isinstance(key, bool) or key in ("", "*", "all", None):
        raise ApiError(404, "没有这个项目")
    p = P.store.project(key)
    if not p:
        raise ApiError(404, "没有这个项目")
    return p


def _check(P, who, project, level="viewer"):
    p = project if isinstance(project, dict) else _project(P, project)
    actual = _effective(who, p["key"])
    if not actual or LEVELS[actual] < LEVELS[level]:
        raise ApiError(403, "当前账号没有此项目所需权限")
    return p


def require_member(P, actor, project=None, level="contributor"):
    if not enabled(P):
        return actor
    who = identity(P, actor)
    if project is not None:
        _check(P, who, project, level)
    return actor


def experiment_identity(P, actor, project, level="viewer"):
    """Current personal authority for a managed experiment; never legacy names.

    HTTP adapters obtain actor from their authenticated session. A tool's
    delegated read/content scope cannot grant experiment custody or approval.
    """
    from .signoff import human
    who = identity(P, actor)
    if who.get("legacy") or who.get("tool_connection") or not human(actor):
        raise ApiError(403, "受管实验需要当前租户的个人账号；工具连接与显示名不能代替")
    _check(P, who, project, level)
    account = P.tenant_context.registry.one("SELECT active,epoch FROM accounts WHERE name=?", (actor,))
    if not account or not account["active"] or not isinstance(account["epoch"], str) or not account["epoch"]:
        raise ApiError(403, "实验成员账号已变化")
    return dict(who, account_epoch=account["epoch"])


@contextmanager
def experiment_guard(P, actor, project, level="viewer"):
    """Acquire before Store/ledger locks; never hold across a child invocation."""
    if not enabled(P):
        raise ApiError(403, "受管实验需要已启用租户的个人账号")
    with P.tenant_context.registry.authorization_guard():
        yield experiment_identity(P, actor, project, level)


def directory(P, project=None, level="viewer"):
    """The registry owns tenant identities; worker-local users are not authority."""
    if not enabled(P):
        from .login import load_users
        return load_users(P.data_dir)
    values = P.tenant_context.directory()
    if not isinstance(values, dict):
        raise ApiError(403, "租户成员目录不可用")
    result = {}
    for name, record in values.items():
        try:
            require_member(P, name, project, level)
        except ApiError:
            continue
        result[name] = record
    return result


def eligible_members(P, project, level="contributor"):
    from .signoff import human
    return sorted(name for name in directory(P, project, level) if human(name))


def require_execution(P, actor):
    if enabled(P):
        identity(P, actor)
        if P.tenant_context.runtime_allowed(actor) is not True:
            raise ApiError(403, "此租户尚未配置独立执行隔离，不能运行模型、构建、脚本或预览")


def require_workspace(P, actor, path):
    if not enabled(P):
        return
    if not identity(P, actor)["platform_owner"]:
        raise ApiError(403, "工作区和命令配置只能由平台管理员管理")
    check = getattr(P.tenant_context, "workspace_allowed", None)
    if not path or not callable(check) or check(path) is not True:
        raise ApiError(403, "工作区不属于此租户批准的目录")


def _match(method, path):
    for verb, template in API_ROUTES:
        if verb != method:
            continue
        pattern = re.sub(r"<([a-z]+)>", r"(?P<\1>[^/]+)", template)
        found = re.fullmatch(pattern, path)
        if found:
            return template, {k: unquote(v) for k, v in found.groupdict().items()}
    for verb, template, pattern in SPECIAL_ROUTES:
        found = re.fullmatch(pattern, path) if verb == method else None
        if found:
            return template, {k: unquote(v) for k, v in found.groupdict().items()}
    raise ApiError(403, "此接口尚未登记租户权限策略")


def _arg(query, name):
    value = query.get(name)
    if isinstance(value, list):
        if len(value) != 1:
            raise ApiError(400, "权限相关参数不能重复")
        return value[0]
    return value


def _row(P, table, value):
    if not P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)):
        raise ApiError(404, "没有这个资源")
    row = P.store.one("SELECT * FROM " + table + " WHERE id=?", (value,))
    if not row:
        raise ApiError(404, "没有这个资源")
    return row


def _resource_project(P, kind, value):
    if (not isinstance(value, (str, int)) or isinstance(value, bool) or
            isinstance(value, int) and not 0 < value < 2 ** 63):
        raise ApiError(404, "没有这个资源")
    if kind == "project":
        return _project(P, value)
    if kind == "ticket":
        row = P.store.ticket(value)
        if not row:
            raise ApiError(404, "没有这个资源")
    elif kind in ("intake", "pin"):
        # Do not call intake.load: even a read can sweep/write an expired job.
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{12}", value):
            raise ApiError(404, "没有这个资源")
        folder = Path(P.data_dir) / ("intake" if kind == "intake" else "pins")
        file = folder / (value + ".json")
        if folder.is_symlink() or file.is_symlink():
            raise ApiError(404, "没有这个资源")
        try:
            row = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise ApiError(404, "没有这个资源") from None
        if not isinstance(row, dict):
            raise ApiError(404, "没有这个资源")
        return _project(P, row.get("project"))
    elif kind == "probe":
        return _resource_project(P, "candidate", _row(P, "harness_probe_runs", value)["candidate_id"])
    elif kind == "candidate":
        return _resource_project(P, "ticket", _row(P, "code_candidates", value)["ticket_id"])
    else:
        table = {"run": "runs", "session": "sessions", "matter": "matters", "delivery": "delivery_items", "revision": "knowledge_revisions", "source": "project_sources"}[kind]
        row = _row(P, table, value)
    return _project(P, row["project_id"])


def _agent(P, who, operation, body):
    from ..agent_contract import SPECS, validate
    if operation not in AGENT_OPERATIONS or operation not in SPECS:
        raise ApiError(403, "此智能体操作尚未登记权限策略")
    try:
        args = validate(operation, body)
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    if operation in ("preview_start", "candidate_preview"):
        raise ApiError(403, "租户预览入口尚未隔离，暂不启动预览服务")
    spec = SPECS[operation]
    tool = who.get('tool_connection')
    if tool:
        from .tool_access import allowed_operations
        if operation not in allowed_operations(tool['scope']):
            raise ApiError(403, '此工具连接未获准执行该操作')
    level = "manager" if operation in ("library_reference", "library_unlink") else "contributor" if spec.get("write") else "viewer"
    projects = []
    for field, kind in (("project", "project"), ("ticket", "ticket"), ("run_id", "run"),
                        ("candidate_id", "candidate"), ("probe_id", "probe")):
        if field in args:
            projects.append(_check(P, who, _resource_project(P, kind, args[field]), level))
    if len({p["id"] for p in projects}) > 1:
        raise ApiError(400, "请求中的资源不属于同一项目")
    if operation == "request_get":
        if tool:
            from .agent_api import member_actor
            if not P.store.one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_requests'"):
                raise ApiError(404, '此成员没有这个请求回执')
            row = P.store.one('SELECT * FROM agent_requests WHERE agent=? AND request_id=?',
                              (member_actor(who['actor']), args['request_id']))
            if not row or row.get('principal') != who['actor']:
                raise ApiError(404, '此成员没有这个请求回执')
            parts = row['resource'].split(':')
            if len(parts) < 2 or parts[0] not in ('project', 'ticket', 'run'):
                raise ApiError(403, '原回执未绑定可核对项目，不能通过工具连接读取')
            _check(P, who, _resource_project(P, parts[0], parts[1]))
            return
        # Agent connection names are not personal principals. Until receipts
        # are bound to the gateway principal, only tenant admins may read them.
        if who["role"] != "admin":
            raise ApiError(403, "跨项目操作回执仅租户管理员可读取")
    elif not projects and operation not in ("status", "harness_recipes") and who["role"] != "admin" and not (
            tool and operation in ('projects_list', 'tickets_list', 'messages_list')):
        raise ApiError(403, "请明确选择获准的项目或工单")
    if spec.get("execution"):
        require_execution(P, who["actor"])
    if operation == "library_build":
        require_workspace(P, who["actor"], projects[0]["root"])
    return projects


def authorize(P, method, path, query, body, actor):
    """Return scope before invoking handlers; unknown routes never inherit admin.

    The adapter MUST apply allowed_project_keys to FILTERED_LISTS before reads,
    counts and pagination. Other global projections are intentionally admin-only.
    Public capability endpoints need their separate tenant-bound ticket check;
    this function refuses to authorize them with an ordinary session.
    """
    if not enabled(P):
        return {"legacy": True, "actor": actor, "filter_required": False}
    who = identity(P, actor)
    method = "GET" if method == "HEAD" else method
    if not isinstance(query, dict) or not isinstance(body, dict):
        raise ApiError(400, "请求参数必须是对象")
    template, params = _match(method, path)
    projects = P.store.projects()
    allowed = {p["key"]: _effective(who, p["key"]) for p in projects if _effective(who, p["key"])}
    scope = {"tenant_id": who["tenant_id"], "actor": actor, "tenant_role": who["role"],
             "platform_owner": who["platform_owner"], "authz_revision": who["authz_revision"],
             "allowed_project_keys": sorted(allowed), "project_roles": allowed,
             "filter_required": method == "GET" and template in FILTERED_LISTS,
             "route": template}
    if template == "/api/agent/<operation>":
        _agent(P, who, params["operation"], body)
        return scope
    if method == "POST" and who["role"] == "viewer":
        raise ApiError(403, "只读成员不能修改项目")
    if method == "POST" and (
            template in ("/api/projects/<key>/shares", "/api/projects/<key>/capture-token", "/api/tickets/<key>/ask-client") or
            template in ("/api/tickets/<key>/preview", "/api/projects/<key>/standing") and body.get("action") == "start" or
            template == "/api/team" and body.get("action") == "candidate_preview" or
            template == "/api/tickets/<key>/evidence" and body.get("kind") == "link" or
            template == "/api/intake/<sid>" and body.get("action") == "ask_client"):
        raise ApiError(403, "公开链接和预览尚未接入租户隔离，暂不签发票据或启动服务")
    if template in ADMIN_GLOBAL or template.startswith("/api/clients/") or template == "/api/learn/holdout" or template.startswith("/api/testbox/"):
        if who["role"] != "admin":
            raise ApiError(403, "此汇总或配置接口仅租户管理员可用")
    if (method == "GET" and template == "/api/memory" or template == "/api/workbench/intake" and (body.get("client") or body.get("client_name"))) and who["role"] != "admin":
        # Memory returns the unfiltered project picker; clients have tenant-wide
        # links. A supplied project field does not scope either projection.
        raise ApiError(403, "此目录或客户关联尚未提供项目权限过滤")
    # The legacy assistant GET creates a default session when one is missing.
    level = "viewer" if method == "GET" and template != "/api/assist" else "contributor"
    if method == "POST" and (template == "/api/team" and body.get("action") == "assign" or
            template.endswith("/library") or template.endswith("/shares") or template.endswith("/capture-token") or
            template.endswith("/lessons/<lid>") or template.endswith("/preview-conf") or
            template == "/api/tickets/<key>" and "assignee" in body or
            template == "/api/memory" and body.get("action") in ("lesson_share", "lesson_unshare", "lesson_take", "lesson_untake")):
        level = "manager"
    targets = []
    def add(kind, value):
        if value not in (None, ""):
            targets.append(_check(P, who, _resource_project(P, kind, value), level))
    if "key" in params:
        add("ticket" if template.startswith(("/api/tickets/", "/e/")) else "project", params["key"])
    for prefix, name, kind in (("/api/runs/", "rid", "run"), ("/api/sessions/", "sid", "session"),
                               ("/api/intake/", "sid", "intake"), ("/api/pins/", "pid", "pin"),
                               ("/api/deliveries/", "did", "delivery")):
        if template.startswith(prefix):
            add(kind, params[name])
    values = body if method == "POST" else {key: _arg(query, key) for key in query}
    if template == "/api/team" and method == "GET" and values.get("request_id"):
        if P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='team_requests'"):
            receipt = P.store.one("SELECT ticket_id FROM team_requests WHERE actor=? AND request_id=?", (actor, values["request_id"]))
            if receipt:
                add("ticket", receipt["ticket_id"])
    for field, kind in (("project", "project"), ("ticket", "ticket"), ("run_id", "run"), ("session", "session"),
                        ("candidate_id", "candidate"), ("probe_id", "probe"), ("matter_id", "matter"), ("source_id", "source")):
        value = values.get(field)
        if field == "project" and value in ("*", "all"):
            if template not in FILTERED_LISTS and who["role"] != "admin":
                raise ApiError(403, "此汇总尚未提供项目权限过滤")
        else:
            add(kind, value)
    cross_project = template == "/api/projects/<key>/library" and values.get("action") in ("grant", "revoke")
    if not cross_project and len({p["id"] for p in targets}) > 1:
        raise ApiError(400, "请求中的资源不属于同一项目")
    if not targets and template not in FILTERED_LISTS and template not in ("/api/meta", "/api/delivery/catalog", "/api/projects/bootstrap"):
        if who["role"] != "admin":
            raise ApiError(403, "请明确选择获准的项目或工单")
    if method == "GET":
        if template in ("/p/<key>/report/<path>", "/p/<key>/code.bundle"):
            # Reports are active same-origin content; bundles invoke Git.
            require_execution(P, actor)
        return scope
    action = body.get("action")
    path_config = template in ("/api/projects", "/api/projects/bootstrap", "/api/projects/<key>/preview-conf", "/api/testbox") or (
        template.endswith("/library") and action in ("configure", "add_source", "derive", "maintain"))
    if path_config:
        if not who["platform_owner"]:
            raise ApiError(403, "工作区和命令配置只能由平台管理员管理")
        roots = [body["root"]] if body.get("root") else [p["root"] for p in targets]
        if template == "/api/projects/bootstrap":
            key = body.get("key")
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,9}", key):
                raise ApiError(400, "项目代号不正确")
            roots = [str(Path(P.data_dir) / "projects" / key.upper())]
        if not roots and template != "/api/testbox":
            raise ApiError(403, "没有获准的工作区")
        for root in roots:
            require_workspace(P, actor, root)
        if template.endswith("/library") and action in ("derive", "maintain"):
            require_workspace(P, actor, Path(P.data_dir) / "project-library" / "workspaces")
    if template.endswith("/library") and action == "reference" and body.get("grant") is True:
        _check(P, who, _resource_project(P, "revision", body.get("revision_id")), "manager")
    if template.endswith("/library") and action == "build":
        root = _row(P, "project_sources", body["source_id"])["root"] if body.get("source_id") else targets[0]["root"]
        require_workspace(P, actor, root)
    for field in ("assignee", "reviewer", "receiver"):
        if body.get(field):
            for p in targets:
                require_member(P, body[field], p, "contributor")
    safe = template in SAFE_POSTS
    safe |= template == "/api/tickets" and (body.get("handwork") is True or body.get("auto") is False and not (body.get("agent") and body.get("mode"))) and not body.get("code_at")
    safe |= template == "/api/team" and action == "assign"
    safe |= template == "/api/team" and action == "comment"
    safe |= template == "/api/tickets/<key>/evidence" and body.get("kind") in ("attach", "review", "link")
    safe |= template == "/api/memory" and action in ("lesson_create", "lesson_edit", "lesson_share", "lesson_unshare", "lesson_take", "lesson_untake", "lesson_confirm", "lesson_restore", "lesson_retire", "cluster_scan", "cluster_confirm", "cluster_exclude")
    # Version-bound personal decisions only write the tenant lesson ledger.
    # The existing manager requirement above and strict session check remain.
    safe |= template == "/api/projects/<key>/lessons/<lid>" and (
        action in ("edit", "confirm", "restore", "retire") or ("action" not in body or action == "") and "fields" in body)
    safe |= template == "/api/learning" and action in ("capture", "propose", "policy_create", "adopt", "revoke", "retry_decision", "abandon_decision")
    # Contract custody/approval writes no process. The experiment module checks
    # current personal authority under its guard; start retains execution policy.
    safe |= template == "/api/learning" and action in (
        "experiment_create", "experiment_seal", "experiment_cancel", "experiment_expose")
    safe |= template.endswith("/library") and action in ("grant", "revoke", "reference", "remove_reference", "configure", "add_source")
    safe |= template == "/api/projects"  # registration only; workspace policy checked above
    safe |= template == "/api/tickets/<key>" and not (set(body) - {"title", "body", "type", "priority", "assignee"})
    safe |= template == "/api/projects/<key>/intake" and body.get("model") is False
    safe |= template == "/api/workbench/intake" and body.get("model") is False
    safe |= template == "/api/pins/<pid>/intake" and body.get("model") is False
    safe |= template == "/api/projects/<key>/kb/triage" and body.get("model") is False
    if not safe:
        require_execution(P, actor)
    return scope
