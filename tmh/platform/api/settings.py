"""Routes: agent settings and access config, testbox, releases, project tests, preview configuration, readiness."""
from __future__ import annotations

import json
import os
import re
from ..errors import ApiError
from ..store import now
from . import route
from ._common import _human_action, _platform_admin


@route("GET", "/api/agent-settings")
def api_agent_settings(P, req):
    from .. import agent_settings
    data = agent_settings.view(P.data_dir)
    try:
        _platform_admin(P, req, "配置智能体")
        data["can_edit"] = True
    except ApiError:
        data["can_edit"] = False
    return data


@route("GET", "/api/access-config")
def api_access_config(P, req):
    _platform_admin(P, req, "配置访问方式")
    from .. import access_config
    return access_config.view()


@route("POST", "/api/access-config")
def api_access_config_save(P, req):
    _platform_admin(P, req, "配置访问方式")
    from .. import access_config
    return access_config.save(req.body)


@route("GET", "/api/agent-scan")
def api_agent_scan(P, req):
    """Local executor discovery: paths, versions, non-secret config, credential booleans."""
    _platform_admin(P, req, "扫描本机执行器")
    from .. import executor_setup
    return executor_setup.scan()


@route("POST", "/api/agent-test")
def api_agent_test(P, req):
    """One no-tools marker request through a configured executor; PASS only on the marker."""
    _platform_admin(P, req, "测试执行器连接")
    from .. import agents, executor_setup
    name = str(req.body.get("name") or "")
    conf = agents.load_config(P.data_dir)
    if name not in conf:
        raise ApiError(404, "没有这个执行器")
    c = conf[name]
    engine = agents.engine_name(name, c)
    if engine not in ("codex", "claude", "cursor") or "cmd" in c:
        raise ApiError(400, "这个执行器暂不支持连接测试")
    exe = c.get("bin") or agents.executable(engine, c)
    env = dict(os.environ)
    env.update(executor_setup.spawn_env(P.data_dir, name, c))
    from .. import agent_page
    result = executor_setup.probe(engine, exe, env)
    agent_page.record_test(P.data_dir, name, result)
    return result


@route("GET", "/api/agent-page")
def api_agent_page(P, req):
    _platform_admin(P, req, "查看智能体页面")
    from .. import agent_page
    return agent_page.view(P)


@route("POST", "/api/agent-settings")
def api_agent_settings_save(P, req):
    _platform_admin(P, req, "配置智能体")
    from .. import agent_settings
    agent_settings.save(P.data_dir, req.body)
    return api_agent_settings(P, req)


@route("GET", "/api/testbox")
def api_testbox(P, req):
    from .. import testbox
    f = P.data_dir / "testbox-check.json"
    last = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    conf = testbox.settings(P.data_dir)
    if last and last.get("configuration") != conf:
        last = None
    return {"conf": conf, "executor": "testbox" if conf else "local", "last": last}


@route("GET", "/api/projects/<key>/releases")
def api_releases(P, req, key):
    """Versions that went out: what each merged into the main line, newest first ("*": every project)."""
    from .. import release
    if key != "*":
        P.project(key)
    k = "" if key == "*" else key.upper()
    undone = {(r.get("project"), r["of"]): r["version"] for r in release.releases(P.data_dir, k, 100000) if r.get("kind") == "rollback" and r.get("of")}
    rels = [dict(r, undone_by=undone.get((r.get("project"), r.get("version")), "")) for r in release.releases(P.data_dir, k, 20)]
    return {"releases": rels, "merge": release.settings(P.data_dir, k)["merge"], "mode": P.flow.mode(P.project(key)) if k else ""}


@route("GET", "/api/projects/<key>/tests")
def api_project_tests(P, req, key):
    from .. import project_tests
    p = P.project(key)
    result = project_tests.view(P.data_dir, p["key"])
    try:
        _platform_admin(P, req, "配置项目测试命令")
        result['can_edit'] = True
    except ApiError as exc:
        if exc.code != 403:
            raise
        result['can_edit'] = False
    result['managed_by'] = '平台管理员'
    result['recent_cases'] = []
    from ..fixloop import _verification
    for run in P.store.runs(project_id=p['id'], limit=30):
        reports = [c['project_tests'] for c in _verification(P.data_dir, run['id']).get('commands', []) if c.get('project_tests')]
        if reports:
            result['recent_cases'] = [{'stage': stage['id'], 'id': case['id'], 'run': run['id']} for report in reports for stage in report['stages'] for case in stage['cases']]
            break
    return result


@route("GET", "/api/runs/<rid>/test-report")
def api_project_test_report(P, req, rid):
    from .. import project_tests
    return project_tests.artifact(P.data_dir, int(rid), req.arg('stage'), req.arg('artifact'))


@route("POST", "/api/projects/<key>/tests")
def api_project_tests_save(P, req, key):
    from .. import project_tests
    p = P.project(key)
    _platform_admin(P, req, "配置项目测试命令")
    return project_tests.save(P.data_dir, p["key"], req.body)


@route("GET", "/api/projects/<key>/mode")
def api_mode(P, req, key):
    p = P.project(key)
    from .. import release
    from ..ai_accept import shadow_stats
    return {"project": p["key"], "mode": P.flow.mode(p), "main": release.settings(P.data_dir)["main"].get(p["key"], ""),
            "shadow": shadow_stats(P.store, p["id"])}


@route("POST", "/api/projects/<key>/mode")
def api_mode_set(P, req, key):
    """{"mode": "auto" | "observe" | "manual"}: run the project fully automatically (AI fixes, accepts, closes, merges with a
    version), let AI only say how it would accept while people accept, or have a person do every step."""
    p = P.project(key)
    actor = _platform_admin(P, req, "切换项目的自动化模式")
    try:
        P.flow.set_mode(p, req.body.get("mode"), actor)
    except ValueError as e:
        raise ApiError(409, str(e))
    return api_mode(P, req, key)


@route("GET", "/api/projects/<key>/channels")
def api_channels(P, req, key):
    """The project's code repository (GitHub) and team group (飞书 / 钉钉 / 企业微信)."""
    p = P.project(key)
    from .. import announce, repo_sync
    return {"project": p["key"], "repo": repo_sync.view(P, p), "notify": announce.view(P, p)}


@route("POST", "/api/projects/<key>/repo")
def api_repo_set(P, req, key):
    """{"url": "git@github.com:团队/仓库.git" | "ssh://用户@主机:端口/路径.git", "hostkey"?, "label"?} binds the project
    (makes its deploy key; pins a own machine's host key); {"check": true} tests the
    connection; {"on": true|false} turns pushing on or off; {"url": ""} unbinds."""
    p = P.project(key)
    actor = _platform_admin(P, req, "设置项目的代码仓库")
    from .. import repo_sync
    b = req.body
    try:
        if "url" in b:
            if b["url"]:
                repo_sync.setup(P, p, b["url"], actor, str(b.get("hostkey") or ""), str(b.get("label") or ""))
            else:
                repo_sync.unbind(P, p, actor)
        if b.get("check"):
            repo_sync.check(P, p)
        if "on" in b:
            repo_sync.switch(P, p, bool(b["on"]), actor)
    except ValueError as e:
        raise ApiError(409, str(e))
    return api_channels(P, req, key)


@route("POST", "/api/projects/<key>/notify")
def api_notify_set(P, req, key):
    """{"target": "<conversation key>"} binds the project's team group; "" unbinds; {"test": true} sends a test line."""
    p = P.project(key)
    actor = _platform_admin(P, req, "设置项目的通知群")
    from .. import announce
    try:
        if "target" in req.body:
            announce.bind(P, p, str(req.body["target"] or ""), actor)
        if req.body.get("test"):
            if not announce.conf(P.data_dir, p["key"]):
                raise ValueError("还没绑定项目群")
            announce.say(P, p, "这是 Webuddy 的测试消息：%s 的通知会发到这个群（%s 设置）。" % (p["key"], actor), title="测试消息")
    except ValueError as e:
        raise ApiError(409, str(e))
    return api_channels(P, req, key)


@route("POST", "/api/projects/<key>/releases/<version>/rollback")
def api_rollback(P, req, key, version):
    """A person undoes a version: a revert commit on the main line as a new version; its tickets reopen for a person."""
    p = P.project(key)
    actor = _platform_admin(P, req, "回滚版本")
    try:
        return P.flow.rollback(p, version, actor)
    except ValueError as e:
        raise ApiError(409, str(e))


@route("POST", "/api/tickets/<key>/release")
def api_release_again(P, req, key):
    """Try the merge again after a person cleared what held it up."""
    from .. import epic
    t = P.ticket(key)
    _human_action(P, req, t)
    if epic.refuse(t, "ship"):
        raise ApiError(409, epic.refuse(t, "ship"))
    try:
        return P.flow.ship_again(P.store.project(t["project_id"]), t, req.user)
    except ValueError as e:
        raise ApiError(409, str(e))


@route("GET", "/api/tickets/<key>/preview")
def api_preview(P, req, key):
    """The ticket's preview, optionally bound to one adopted fix run with ?run_id=N."""
    from .. import preview
    return preview.ticket_view(P, P.ticket(key), req.arg("run_id") if "run_id" in req.query else None)


@route("POST", "/api/tickets/<key>/preview")
def api_preview_do(P, req, key):
    """{"action": "start" | "stop", "run_id": N?}: preview the specified run's exact adopted commit."""
    from .. import preview
    t = P.ticket(key)
    act, run_id = req.body.get("action"), req.body.get("run_id")
    if act == "stop":
        return preview.stop_for_ticket(P, t, req.user, run_id)
    elif act == "start":
        return preview.start_for_ticket(P, t, req.user, run_id)
    else:
        raise ApiError(400, "action 只能是 start 或 stop")


@route("GET", "/api/projects/<key>/preview-conf")
def api_preview_conf(P, req, key):
    from .. import preview
    p = P.project(key)
    cmd, ready, mine = preview.command(P.data_dir, p)
    return {"cmd": cmd if mine else "", "detected": "" if mine else cmd, "ready": ready}


@route("POST", "/api/projects/<key>/preview-conf")
def api_preview_conf_set(P, req, key):
    """{"cmd": "...", "ready": "/"}: how this project starts; {port} and {prefix} are filled in. Empty cmd: back to detection."""
    from .. import preview
    p = P.project(key)
    cmd, ready = req.body.get("cmd", ""), req.body.get("ready", "/")
    if not isinstance(cmd, str) or not isinstance(ready, str) or len(cmd) > 2000:
        raise ApiError(400, "命令要是一行文字")
    if cmd.strip() and "{port}" not in cmd and "PORT" not in cmd:
        raise ApiError(400, "命令里要用 {port}（或环境变量 PORT）指定端口，平台才知道去哪里找它")
    try:
        preview.set_conf(P.data_dir, p["key"], cmd, ready, req.user)
    except ValueError as e:
        raise ApiError(400, str(e))
    return api_preview_conf(P, req, key)


@route("GET", "/api/tickets/<key>/starter")
def api_starter(P, req, key):
    """我来写: the ticket as a starter pack (Markdown) for writing it by hand or with one's own tools."""
    from .. import handwork
    t = P.ticket(key)
    p = P.store.project(t["project_id"])
    return {"markdown": handwork.starter(P, t), "branch": handwork.PREFIX + t["key"], "remote": bool(handwork._origin(P.root(p))),
            "heartbeat": handwork.settings(P.data_dir)["handwork"]}


@route("POST", "/api/tickets/<key>/claim")
def api_claim(P, req, key):
    """我来写: a person takes the ticket before (or instead of) the agents; queued or running automatic steps stop."""
    from .. import epic, handwork, team
    t = P.ticket(key)
    actor = _human_action(P, req)
    if epic.refuse(t, "handwork"):
        raise ApiError(409, epic.refuse(t, "handwork"))
    with team._guard(P, t["id"]):
        t = P.ticket(key)
        if team.assignment(P, t)["revision"] and t.get("assignee") != actor:
            raise ApiError(403, "团队任务只能由当前负责人接管；调整负责人请使用团队分配")
        return handwork.claim(P, t, actor, req.body.get("on", True) is not False)


@route("POST", "/api/tickets/<key>/handwork")
def api_handwork(P, req, key):
    """{"patch": "<git format-patch output>"}: a hand-written change from someone who cannot push."""
    from .. import epic, handwork
    t = P.ticket(key)
    if epic.refuse(t, "handwork"):
        raise ApiError(409, epic.refuse(t, "handwork"))
    patch = req.body.get("patch")
    if not isinstance(patch, str) or len(patch) > 4 * 1024 * 1024:
        raise ApiError(400, "patch 要是补丁文件的文本，不超过 4MB")
    return handwork.upload(P, t, patch, req.user)


@route("POST", "/api/projects/<key>/scan")
def api_handwork_scan(P, req, key):
    """Look at wb/* branches now instead of waiting for the heartbeat."""
    from .. import handwork
    return {"taken": handwork.scan(P, P.project(key))}


@route("GET", "/api/readiness")
def api_readiness(P, req):
    """上线体检: what on this machine would let a pilot down, each with its next step."""
    from .. import readiness
    return readiness.check(P)


@route("POST", "/api/testbox")
def api_testbox_save(P, req):
    """Where the test machine is: {host: "user@host" or an ~/.ssh/config alias, port (empty: the alias's own), dir}; an empty host turns it off. Key login only."""
    host = str(req.body.get("host") or "").strip()
    executor = req.body.get("executor", "testbox" if host else "local")
    if executor not in ("local", "testbox"):
        raise ApiError(400, "执行位置只能是 local 或 testbox")
    if executor == "testbox" and not host:
        raise ApiError(400, "选择远程测试机时需要填写 SSH 地址")
    if executor == "local":
        host = ""
    if host and (not re.fullmatch(r"[\w.-]+(?:@[\w.-]+)?", host) or host.startswith("-")):
        raise ApiError(400, "地址写成 用户名@主机，比如 user@build-host.example.invalid")
    from ..util_conf import update_autoflow
    try:
        if host:
            update_autoflow(P.data_dir, {"testbox": {"host": host, "port": int(req.body.get("port") or 0), "dir": str(req.body.get("dir") or "").strip()}})
        else:
            update_autoflow(P.data_dir, {}, drop=("testbox",))
    except ValueError as e:
        raise ApiError(400, str(e))
    return api_testbox(P, req)


@route("POST", "/api/testbox/<action>")
def api_testbox_act(P, req, action):
    """check: what the machine has; install: unpack the missing tools there (a person asked for it on the page)."""
    from .. import testbox
    conf = testbox.settings(P.data_dir)
    box = testbox.TestBox(conf, P.data_dir) if conf else None
    if action == "check":
        r = box.check() if box else testbox.local_check()
    elif action == "install":
        if not box:
            raise ApiError(400, "本机依赖请按项目要求安装；远程安装入口只用于已配置的 SSH 测试机")
        r = box.install(req.body.get("tools") or None)
        r = dict(r["check"], log=r["log"]) if r.get("check") else r
    else:
        raise ApiError(404, "没有这个操作")
    r["at"] = now()
    r["configuration"] = conf
    (P.data_dir / "testbox-check.json").write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    return r


@route("GET", "/api/members")
def api_members(P, req):
    from .. import members
    return {"members": members.view(P.data_dir)}


@route("POST", "/api/members")
def api_members_save(P, req):
    from .. import members
    b = req.body or {}
    action = b.get("action")
    try:
        if action == "add":
            members.add(P.data_dir, str(b.get("name") or ""), str(b.get("password") or ""), str(b.get("role") or ""))
        elif action == "remove":
            members.remove(P.data_dir, str(b.get("name") or ""), req.user)
        elif action == "role":
            members.set_role(P.data_dir, str(b.get("name") or ""), str(b.get("role") or ""), req.user)
        elif action == "reset_password":
            members.reset_password(P.data_dir, str(b.get("name") or ""), str(b.get("password") or ""))
        else:
            raise ApiError(400, "操作只能是 add、remove、role 或 reset_password")
    except ValueError as e:
        raise ApiError(400, str(e))
    return {"members": members.view(P.data_dir)}
