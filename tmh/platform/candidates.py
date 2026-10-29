"""Immutable external code candidates and version-bound technical acceptance.

Registration is not adoption. Build/test runs use the existing independent
verification supervisor. Agent assessments remain attributed assertions; only
the operator endpoint records a human decision, without merging or deploying.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess

from .errors import ApiError
from . import filelock
from .store import now


SCHEMA = """
CREATE TABLE IF NOT EXISTS code_candidates (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER NOT NULL,
 run_id INTEGER NOT NULL UNIQUE, agent TEXT NOT NULL,
 base_commit TEXT NOT NULL, commit_sha TEXT NOT NULL,
 requirement_hash TEXT NOT NULL, configuration_hash TEXT NOT NULL,
 criteria TEXT NOT NULL, summary TEXT NOT NULL, fingerprint TEXT NOT NULL UNIQUE,
 ref TEXT NOT NULL, artifact_dir TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_assessments (
 id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL,
 author TEXT NOT NULL, verification_hash TEXT NOT NULL, preview_hash TEXT NOT NULL DEFAULT '', results TEXT NOT NULL,
 note TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL,
 author TEXT NOT NULL, decision TEXT NOT NULL, evidence_hash TEXT NOT NULL,
 note TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_team_decisions (
 decision_id INTEGER PRIMARY KEY, reviewer TEXT NOT NULL, assignee TEXT NOT NULL,
 assignment_revision INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS candidate_merges (
 candidate_id INTEGER PRIMARY KEY, author TEXT NOT NULL, request_id TEXT NOT NULL,
 evidence_hash TEXT NOT NULL, main TEXT NOT NULL, before_commit TEXT NOT NULL,
 commit_sha TEXT NOT NULL, state TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
"""


def schema(store):
    with store.lock:
        store.db.executescript(SCHEMA)
        if "preview_hash" not in {r["name"] for r in store.q("PRAGMA table_info(candidate_assessments)")}:
            store.db.execute("ALTER TABLE candidate_assessments ADD COLUMN preview_hash TEXT NOT NULL DEFAULT ''")
        store.db.commit()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def implementation_author(author, user):
    """Only the server-reserved member namespace identifies an initiating user."""
    from .agent_api import member_actor
    return author in (user, member_actor(user))


def _git(root, *args, raw=False):
    from .project_git import read
    p = read(root,args)
    if p is None:
        p = subprocess.run(["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args],
                           capture_output=True, timeout=30)
    if p.returncode:
        raise ApiError(409, "Git候选检查失败：" + p.stderr.decode("utf-8", "replace"))
    return p.stdout if raw else p.stdout.decode("utf-8", "strict")


def configuration(P, project):
    from .. import config
    from .fixloop import settings
    from .testbox import settings as box_settings
    from .preview import command
    value = {"commands": config.load(Path(project["root"])).get("commands"),
                  "checks": settings(P.data_dir), "testbox": box_settings(P.data_dir),
                  "preview": command(P.data_dir, project)}
    from .static_preview import profile
    static = profile(P.data_dir, project["key"])
    if static:value["static_preview"] = static
    return _hash(value)


def _check_baseline(root, ticket, base):
    links = ticket.get("links") or {}
    for key in ("code_at", "base"):
        if links.get(key) and _git(root, "rev-parse", "--verify", "--end-of-options", str(links[key]) + "^{commit}").strip() != base:
            raise ApiError(409, "候选基线与工单固定的%s版本不一致" % key)


@contextmanager
def guard(P, ticket_id):
    folder = Path(P.data_dir) / "candidates" / "locks"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (str(int(ticket_id)) + ".lock")).open("a+b") as stream:
        try:
            filelock.try_lock(stream)
        except BlockingIOError as exc:
            raise ApiError(409, "此工单的候选操作正在处理，请稍后读取回执") from exc
        try:
            yield
        finally:
            filelock.unlock(stream)


def for_run(store, rid):
    if not store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='code_candidates'"):
        return None
    return store.one("SELECT * FROM code_candidates WHERE run_id=?", (rid,))


def _row(P, cid):
    row = P.store.one("SELECT * FROM code_candidates WHERE id=?", (cid,))
    if not row:
        raise ApiError(404, "没有这个外部候选")
    return row


def submit(P, actor, args, mutation):
    from .agent_api import _ready, _requirement
    from .project_library import bindings, _write_run_inputs, run_current
    st = P.store
    t = st.ticket(args["ticket"])
    if not t:
        raise ApiError(404, "没有这个工单")
    p = st.project(t["project_id"])
    root = Path(p["root"])
    with guard(P, t["id"]), st.lock:
        _ready(P, t)
        if _requirement(t, st) != args["requirement_hash"]:
            raise ApiError(409, "需求版本已变化，请重新读取完整任务后提交")
        for key in ("base_commit", "commit"):
            if _git(root, "rev-parse", "--verify", args[key] + "^{commit}").strip() != args[key]:
                raise ApiError(409, "必须提交已登记项目仓库中的完整Git提交编号")
        _git(root, "merge-base", "--is-ancestor", args["base_commit"], args["commit"])
        _check_baseline(root, t, args["base_commit"])
        diff = _git(root, "diff", "--no-ext-diff", "--no-textconv", args["base_commit"], args["commit"])
        if not diff.strip():
            raise ApiError(409, "候选相对基线没有代码改动")
        ids = [a["id"] for a in args["criteria"]]
        if len(ids) != len(set(ids)):
            raise ApiError(400, "验收条件编号不能重复")
        conf = configuration(P, p)
        identity = {"ticket": t["id"], "base": args["base_commit"], "commit": args["commit"],
                    "requirement": args["requirement_hash"], "configuration": conf, "criteria": args["criteria"]}
        fp = _hash(dict(identity, project_root=p["root"]))
        old = st.one("SELECT * FROM code_candidates WHERE fingerprint=?", (fp,))
        if not old:
            # Keep unchanged legacy submissions idempotent, without relabeling
            # their evidence. An unknown/replaced workspace must register anew.
            legacy = st.one("SELECT * FROM code_candidates WHERE fingerprint=?", (_hash(identity),))
            if legacy and run_current(st, p, legacy["run_id"]):
                old = legacy
        if old:
            return {"candidate_id": old["id"], "run_id": old["run_id"], "commit": old["commit_sha"], "reused": True}
        mutation()
        # Keep the full binary patch and source binding even if later DB writes
        # fail. No caller-controlled paths, refs, URLs or shell commands.
        folder = Path(P.data_dir) / "candidates" / fp
        folder.mkdir(parents=True, exist_ok=True)
        patch = _git(root, "diff", "--binary", "--no-ext-diff", "--no-textconv", args["base_commit"], args["commit"], raw=True)
        file = folder / "change.patch"
        if file.exists() and file.read_bytes() != patch:
            raise ApiError(409, "候选原始产物不一致，已保留现场")
        if not file.exists():
            with file.open("xb") as stream:
                stream.write(patch)
        ref = "refs/webuddy/candidates/" + fp
        existing = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", ref], capture_output=True, text=True)
        if existing.returncode == 0:
            if existing.stdout.strip() != args["commit"]:
                raise ApiError(409, "候选固定引用被改变，拒绝覆盖")
        else:
            _git(root, "update-ref", ref, args["commit"], "0" * 40)
        try:
            st.db.execute("BEGIN IMMEDIATE")
            t = st.ticket(t["id"])
            _ready(P, t)
            current = st.project(t["project_id"])
            if current['id'] != p['id'] or current['root'] != p['root']:
                raise ApiError(409, "准备候选期间项目工作区已变化，请重新读取任务并提交")
            inputs = bindings(st, current)
            if _requirement(t, st, reference_inputs=inputs) != args["requirement_hash"]:
                raise ApiError(409, "需求在提交期间变化，请重新核对")
            if any(not value['available'] for value in inputs):
                raise ApiError(409, "参考知识授权已变化，请先处理不可用引用")
            _check_baseline(root, t, args["base_commit"])
            if configuration(P, current) != conf:
                raise ApiError(409, "执行配置在提交期间变化，请重新核对")
            stamp = now()
            run = st.db.execute("""INSERT INTO runs(project_id,ticket_id,agent,mode,status,author,created,ended,exit_code,
                 prompt,result,diff,target) VALUES(?,?,?,'fix','done',?,?,?,0,?,?,?,?)""",
                 (p["id"], t["id"], "external:" + actor.removeprefix("agent:"), actor, stamp, stamp,
                  "外部候选登记；不是平台模型执行或人工采纳", args["summary"], diff, args["base_commit"])).lastrowid
            _write_run_inputs(st, current, run, inputs)
            cid = st.db.execute("""INSERT INTO code_candidates(ticket_id,run_id,agent,base_commit,commit_sha,
                 requirement_hash,configuration_hash,criteria,summary,fingerprint,ref,artifact_dir,created)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (t["id"], run, actor, args["base_commit"], args["commit"],
                 args["requirement_hash"], conf, _json(args["criteria"]), args["summary"], fp, ref, str(folder), stamp)).lastrowid
            st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,'candidate',?,?)",
                          (t["id"], stamp, actor, "登记外部代码候选，等待平台独立验证", _json({"candidate": cid, "run": run, "commit": args["commit"]})))
            st.db.execute("UPDATE tickets SET status='doing',updated=? WHERE id=?", (stamp, t["id"]))
            st.db.commit()
        except BaseException:
            st.db.rollback()
            raise
    return {"candidate_id": cid, "run_id": run, "commit": args["commit"], "execution_started": False, "human_acceptance": False}


def view(P, cid, *, include_probe=True):
    from .agent_api import _requirement
    from .fixloop import verified
    from . import preview
    row = _row(P, cid)
    st = P.store
    t = st.ticket(row["ticket_id"])
    p = st.project(t["project_id"])
    run = st.run(row["run_id"])
    blocked = []
    from .project_library import run_current
    if not run_current(st, p, row['run_id']):
        blocked.append("候选的工作区或参考知识证据已变化，请在当前工作区重新登记并验证")
    if _requirement(t, st) != row["requirement_hash"]:
        blocked.append("需求或沟通已变化，需要重新提交与当前需求绑定的候选")
    if configuration(P, p) != row["configuration_hash"]:
        blocked.append("验证配置已变化，需要重新登记并验证候选")
    latest = st.one("SELECT id FROM code_candidates WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (t["id"],))
    if latest["id"] != cid:
        blocked.append("已有更新候选，当前记录仅保留为历史")
    if t["status"] == "closed":
        blocked.append("工单已关闭")
    try:
        _check_baseline(Path(p["root"]), t, row["base_commit"])
        if _git(Path(p["root"]), "rev-parse", row["ref"]).strip() != row["commit_sha"]:
            blocked.append("候选引用与固定提交不一致")
    except (ApiError, OSError, ValueError) as exc:
        blocked.append("候选版本不可核对：" + str(exc))
    v = verified(P.data_dir, row["run_id"])
    verification_ok = bool(v.get("verification_current") is True and v.get("check") == "pass"
        and v.get("checked_commit") == row["commit_sha"] and v.get("checked_base") == row["base_commit"]
        and v.get("checked_diff") == run["diff"] and v.get("commands")
        and all(c.get("exit_code") == 0 for c in v["commands"])
        and any(c.get("kind") == "test" for c in v["commands"]))
    from .harness_probes import current
    probe = current(P, cid) if include_probe else None
    # Probe failures and unknowns block technical acceptance. Starting a new
    # probe also invalidates earlier observations, even before it finishes.
    probe_ok = probe is None or probe["passed"]
    vh = _hash({"verification": v, "probe_id": probe["id"], "probe_evidence": probe["evidence_hash"]}) if verification_ok and probe else _hash(v) if verification_ok else ""
    from . import static_preview
    static = static_preview.profile(P.data_dir, p["key"])
    pv = static_preview.view(P, row, v) if static else preview.status(P.data_dir, t["key"])
    preview_ok = pv.get("state") == "up" and (pv.get("commit_full") == row["commit_sha"] if static else preview.bound_matches(pv, t["key"], row["commit_sha"]))
    ph = _hash({k: pv.get(k) for k in ("commit_full", "prefix", "started", "pid", "log", "cmd", "ready")}) if preview_ok else ""
    if static and preview_ok:ph = pv["digest"]
    entry = pv.get("entry", "") if static else preview.bound_prefix(t["key"], row["commit_sha"]) + "/"
    assessment = st.one("SELECT * FROM candidate_assessments WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (cid,))
    results = json.loads(assessment["results"]) if assessment else []
    technical_ok = bool(verification_ok and probe_ok and preview_ok and assessment and assessment["verification_hash"] == vh
                        and assessment["preview_hash"] == ph
                        and not implementation_author(row["agent"],assessment["author"]) and all(r["status"] == "pass" for r in results))
    evidence = {"candidate": cid, "commit": row["commit_sha"], "base": row["base_commit"],
                "requirement_hash": row["requirement_hash"], "configuration_hash": row["configuration_hash"],
                "criteria": json.loads(row["criteria"]), "verification_hash": vh, "preview_hash": ph, "assessment": assessment}
    eh = _hash(evidence)
    decision = st.one("SELECT * FROM candidate_decisions WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (cid,))
    accepted = bool(not blocked and technical_ok and decision and decision["decision"] == "accept" and decision["evidence_hash"] == eh)
    needs = list(blocked)
    if not verification_ok:
        needs.append("缺少当前固定提交的独立构建/测试通过记录")
    if not probe_ok:
        needs.append("业务探测尚未通过、仍有未知项或证据已失效；读取harness_probe_get核对")
    if not preview_ok:
        needs.append("固定版本预览尚未就绪" + ("：" + pv["why"] if pv.get("why") else ""))
    if not technical_ok:
        needs.append("缺少当前验证对应的独立逐项技术验收，或仍有失败/未知项")
    return {"id": cid, "ticket": t["key"], "run_id": row["run_id"], "author": row["agent"],
            "base_commit": row["base_commit"], "commit": row["commit_sha"], "ref": row["ref"],
            "requirement_hash": row["requirement_hash"], "criteria": json.loads(row["criteria"]), "summary": row["summary"],
            "current": not blocked, "blocked": blocked, "verification": v, "verification_passed": verification_ok,
            "verification_hash": vh, "harness_probe": probe, "preview": pv, "preview_ready": preview_ok, "preview_hash": ph,
            # Enter through the authenticated workbench, which grants a scoped
            # cookie before redirecting to the separate preview origin.
            "preview_url": getattr(P, "public_url", "") + entry if preview_ok else "",
            "preview_entry_path": entry if preview_ok else "",
            "assessment": dict(assessment, results=results) if assessment else None,
            "technical_acceptance": technical_ok and not blocked,
            "ready_for_human": not needs, "missing": needs, "evidence_hash": eh,
            "human_decision": decision, "human_accepted": accepted,
            "state": "accepted" if accepted else "stale" if blocked else "awaiting_human" if not needs else "needs_verification",
            "boundary": "Agent observations are attributed evidence, not human approval. Acceptance does not merge or deploy."}


def execute(P, actor, op, a, mutation=lambda: None):
    if op == "candidates_list":
        t = P.store.ticket(a["ticket"])
        if not t:
            raise ApiError(404, "没有这个工单")
        rows = P.store.q("SELECT id FROM code_candidates WHERE ticket_id=? AND id>? ORDER BY id LIMIT ?",
                          (t["id"], a["after"], a["limit"] + 1))
        return {"items": [view(P, r["id"]) for r in rows[:a["limit"]]], "has_more": len(rows) > a["limit"],
                "next_after": rows[min(len(rows), a["limit"]) - 1]["id"] if rows else a["after"]}
    if op == "candidate_get":
        return view(P, a["candidate_id"])
    if op == "candidate_submit":
        result = submit(P, actor, a, mutation)
        if not result.get('reused'):
            from .static_preview import auto_verify
            result['auto_verification'] = auto_verify(P, actor, result['candidate_id'])
        return result
    row = _row(P, a["candidate_id"])
    with guard(P, row["ticket_id"]):
        v = view(P, row["id"])
        if op == "candidate_cancel":
            operation = P.flow.rechecks.status(row["run_id"])
            if not operation or not operation.get("running"):
                raise ApiError(409, "当前没有正在验证的候选")
            ctx=getattr(P,'tenant_context',None)
            if ctx and not ctx.runtime_allowed(actor) and operation.get('author')!=actor:
                raise ApiError(403, '只能停止自己发起的隔离验证')
            mutation()
            return P.flow.rechecks.runner.cancel(operation["id"], actor)
        if not v["current"]:
            raise ApiError(409, "；".join(v["blocked"]))
        if op == "candidate_verify":
            previous = P.flow.rechecks.status(row["run_id"])
            if previous and not previous.get("can_retry"):
                raise ApiError(409, "；".join(previous.get("blocked") or ["原验证尚未结束"]))
            ctx=getattr(P,'tenant_context',None)
            if ctx and not ctx.runtime_allowed(actor):
                from . import project_verify
                try: project_verify.commands(P,P.store.project(P.store.ticket(row['ticket_id'])['project_id']))
                except ValueError as exc: raise ApiError(409,str(exc)) from exc
                mutation()
                try:return project_verify.start(P,actor,row['id'])
                except ValueError as exc:raise ApiError(409,str(exc)) from exc
            mutation()
            return P.flow.recheck(row["run_id"], actor)
        # Serialize decisions and preview publication against rechecks.
        from .recheck_operations import source_guard
        with source_guard(P.data_dir, row["run_id"]):
            v = view(P, row["id"])
            if not v["current"]:
                raise ApiError(409, "；".join(v["blocked"]))
            if op == "candidate_preview":
                if not v["verification_passed"]:
                    raise ApiError(409, "平台独立构建/测试尚未通过，不启动候选预览")
                from . import preview, static_preview
                t = P.store.ticket(row["ticket_id"])
                p = P.store.project(t["project_id"])
                if static_preview.profile(P.data_dir, p["key"]):
                    if not v["preview_ready"]:raise ApiError(409, "当前静态产物不可用，请重新构建")
                    mutation()
                    return {"candidate_id":row["id"], "preview":v["preview"], "url":v["preview_entry_path"]}
                mutation()
                state = preview.start(P, p, t, row["commit_sha"], actor, expected_commit=row["commit_sha"])
                P.store.event(t["id"], actor, "preview", "启动独立验证后的外部候选预览", {"candidate": row["id"], "commit": row["commit_sha"]})
                return {"candidate_id": row["id"], "preview": state}
            if op == "candidate_assess":
                if not v["verification_passed"] or a["verification_hash"] != v["verification_hash"] or not v["preview_ready"] or a["preview_hash"] != v["preview_hash"]:
                    raise ApiError(409, "验证或预览依据已变化，先读取当前候选并重新验证")
                if implementation_author(row["agent"],actor):
                    raise ApiError(409, "实现者不能替代独立验收者；使用实际独立复核会话记录")
                ids = [r["id"] for r in a["results"]]
                if len(ids) != len(set(ids)) or set(ids) != {c["id"] for c in v["criteria"]}:
                    raise ApiError(400, "必须逐项记录全部验收条件，不得重复、遗漏或加入未知编号")
                _record(P, row, actor, op, a, mutation)
                return view(P, row["id"])
            if op == "candidate_decide":
                if a["evidence_hash"] != v["evidence_hash"]:
                    raise ApiError(409, "验收包已变化，请重新查看再确认")
                if a["decision"] == "accept" and not v["ready_for_human"]:
                    raise ApiError(409, "当前候选不能签收：" + "；".join(v["missing"]))
                _record(P, row, actor, op, a, mutation)
                return view(P, row["id"])
    raise ApiError(400, "未知候选操作")


def _record(P, row, actor, op, a, mutation):
    """Commit the verdict and its event against the same requirement snapshot.

    The SQLite write transaction excludes comments from other service processes;
    the caller also holds the candidate and verification source locks.
    """
    st = P.store
    with st.lock:
        try:
            st.db.execute("BEGIN IMMEDIATE")
            v = view(P, row["id"])
            if not v["current"]:
                raise ApiError(409, "；".join(v["blocked"]))
            if op == "candidate_assess":
                if not v["verification_passed"] or not v["preview_ready"] or v["verification_hash"] != a["verification_hash"] or v["preview_hash"] != a["preview_hash"]:
                    raise ApiError(409, "技术验收依据已变化")
                mutation()
                item = st.db.execute("INSERT INTO candidate_assessments(candidate_id,author,verification_hash,preview_hash,results,note,created) VALUES(?,?,?,?,?,?,?)",
                    (row["id"], actor, a["verification_hash"], a["preview_hash"], _json(a["results"]), a["note"], now())).lastrowid
                kind, body = "candidate_assessment", "记录逐项技术验收（不是人工签收）"
            else:
                if v["evidence_hash"] != a["evidence_hash"] or a["decision"] == "accept" and not v["ready_for_human"]:
                    raise ApiError(409, "人工验收依据已变化或仍有失败/未知项")
                mutation()
                item = st.db.execute("INSERT INTO candidate_decisions(candidate_id,author,decision,evidence_hash,note,created) VALUES(?,?,?,?,?,?)",
                    (row["id"], actor, a["decision"], a["evidence_hash"], a["note"], now())).lastrowid
                if a.get("_team_identity"):
                    identity = a["_team_identity"]
                    st.db.execute("INSERT INTO candidate_team_decisions VALUES(?,?,?,?)",
                                  (item, actor, identity["assignee"], identity["revision"]))
                kind, body = "candidate_decision", "操作者确认候选：" + a["decision"]
            st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                (row["ticket_id"], now(), actor, kind, body, _json({"candidate": row["id"], "record": item})))
            st.db.commit()
        except BaseException:
            st.db.rollback()
            raise


def browser_decide(P, user, args, mutation=lambda: None):
    """A session-authenticated human decision; never accepts a display identity.

    The HTTP adapter proves the session. Account and assignment are rechecked
    inside the same transaction that records the decision and evidence hash.
    """
    from . import team
    row = _row(P, args["candidate_id"])
    if implementation_author(row["agent"],user):
        raise ApiError(403, "固定候选的提交者不能复核自己的交付；重新分配任务不会改变提交作者")
    t = team.require_reviewer(P, row["ticket_id"], user)
    identity = team.assignment(P, t)
    def checked():
        current_ticket = team.require_reviewer(P, row["ticket_id"], user)
        if team.assignment(P, current_ticket) != identity:
            raise ApiError(409, "复核责任已变化，请重新查看任务")
        mutation()
    return execute(P, user, "candidate_decide", dict(args, _team_identity=identity), checked)


def browser_review_current(P, cid):
    """Whether the current human verdict belongs to the current team assignment."""
    from . import team
    decision = P.store.one("SELECT * FROM candidate_decisions WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (cid,))
    if not decision:
        return False
    identity = P.store.one("SELECT * FROM candidate_team_decisions WHERE decision_id=?", (decision["id"],))
    if not identity:
        return False
    row = _row(P, cid)
    if implementation_author(row["agent"],decision["author"]):
        return False
    t = P.store.ticket(row["ticket_id"])
    current = team.assignment(P, t)
    from .tenant_policy import directory
    members = directory(P, P.store.project(t["project_id"]), "contributor")
    return bool(identity["reviewer"] in members and current["assignee"] in members
                and identity["reviewer"] == current["reviewer"] == decision["author"]
                and identity["assignee"] == current["assignee"]
                and identity["assignment_revision"] == current["revision"]
                and current["assignee"] != current["reviewer"])


def merge_receipt(P, cid):
    exists = P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='candidate_merges'")
    return P.store.one("SELECT * FROM candidate_merges WHERE candidate_id=?", (cid,)) if exists else None


@contextmanager
def _merge_guard(root):
    # A repository can be registered in two platform data directories. Use its
    # common Git directory, not the data directory, to serialize our writers.
    common = Path(_git(root, "rev-parse", "--git-common-dir").strip())
    if not common.is_absolute():
        common = root / common
    with (common / "webuddy-candidate-merge.lock").open("a+b") as stream:
        try:
            filelock.try_lock(stream)
        except BlockingIOError as exc:
            raise ApiError(409, "这个仓库正在合并其他候选，请稍后重试") from exc
        try:
            yield
        finally:
            filelock.unlock(stream)


def browser_merge(P, cid, user, evidence_hash, request_id, mutation=lambda: None):
    """Fast-forward the exact approved commit; no invented adoption or closure.

    A moved main branch requires a fresh candidate and verification. The journal
    reconciles a crash between Git's atomic ref update and its SQLite receipt.
    Neither remote pushes nor deployments are performed here.
    """
    from . import team, release
    from .project_library import require_development
    from .recheck_operations import source_guard
    row = _row(P, cid)
    t = team.require_reviewer(P, row["ticket_id"], user)
    p = P.store.project(t["project_id"])
    try:
        require_development(P.store, p)
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc
    root = Path(p["root"])
    with guard(P, t["id"]), source_guard(P.data_dir, row["run_id"]), _merge_guard(root), P.store.lock:
        st = P.store
        # Keep this transaction through the short local Git fast-forward: other
        # service processes cannot append requirements or change responsibility.
        try:
            st.db.execute("BEGIN IMMEDIATE")
            team.require_reviewer(P, t["id"], user)
            v = view(P, cid)
            if not isinstance(evidence_hash, str) or evidence_hash != v["evidence_hash"]:
                raise ApiError(409, "证据包已变化，请重新查看后合并")
            if not v["human_accepted"] or not browser_review_current(P, cid):
                raise ApiError(409, "当前版本尚未由当前指定复核人确认，不能合并")
            main = release.main_branch(root, P.data_dir, p["key"])
            if not main or _git(root, "symbolic-ref", "--quiet", "--short", "HEAD").strip() != main:
                raise ApiError(409, "项目工作区必须停在已配置的主干分支上")
            head = _git(root, "rev-parse", "HEAD").strip()
            previous = merge_receipt(P, cid)
            if previous and previous["state"] == "merged":
                if previous["commit_sha"] != row["commit_sha"]:
                    raise ApiError(409, "历史合并回执与固定候选不一致")
                _git(root, "merge-base", "--is-ancestor", row["commit_sha"], head)
                st.db.commit()
                return dict(previous, pushed=False, deployed=False, replayed=True)
            if _git(root, "status", "--porcelain", "--untracked-files=all").strip():
                raise ApiError(409, "主干工作区有未提交文件，请先处理再合并")
            gd = release._gitdir(root)
            if any((gd / name).exists() for name in release.IN_PROGRESS + ("index.lock",)):
                raise ApiError(409, "仓库有未完成的 Git 操作，请先处理")
            if head != row["base_commit"]:
                if not (previous and previous["state"] == "prepared" and head == row["commit_sha"]
                        and previous["evidence_hash"] == evidence_hash and previous["before_commit"] == row["base_commit"]):
                    raise ApiError(409, "主干已偏离已验证基线，请基于当前主干重新提交、检查和复核")
            if _git(root, "rev-parse", row["ref"]).strip() != row["commit_sha"]:
                raise ApiError(409, "候选固定引用已变化")
            stamp = now()
            if not previous:
                st.db.execute("INSERT INTO candidate_merges VALUES(?,?,?,?,?,?,?,'prepared',?,?)",
                              (cid, user, request_id, evidence_hash, main, head, row["commit_sha"], stamp, stamp))
            elif previous["evidence_hash"] != evidence_hash or previous["main"] != main:
                if head != row["base_commit"]:
                    raise ApiError(409, "原合并操作尚未确认且依据已变化，请人工核对回执")
                st.db.execute("UPDATE candidate_merges SET author=?,request_id=?,evidence_hash=?,main=?,before_commit=?,updated=? WHERE candidate_id=?",
                              (user, request_id, evidence_hash, main, head, stamp, cid))
            # Persist intent before touching Git, then regain a writer transaction
            # and repeat evidence/identity checks before the mutation.
            st.db.commit()
            st.db.execute("BEGIN IMMEDIATE")
            team.require_reviewer(P, t["id"], user)
            current = view(P, cid)
            if current["evidence_hash"] != evidence_hash or not current["human_accepted"] or not browser_review_current(P, cid):
                raise ApiError(409, "准备合并期间证据或复核责任变化，尚未合并")
            if _git(root, "rev-parse", "HEAD").strip() != head:
                raise ApiError(409, "准备合并期间主干发生变化，尚未合并")
            mutation()
            if head != row["commit_sha"]:
                _git(root, "merge", "--ff-only", "--no-edit", row["commit_sha"])
            if _git(root, "rev-parse", "HEAD").strip() != row["commit_sha"]:
                raise ApiError(409, "合并后的版本与固定候选不一致，请核对仓库")
            st.db.execute("UPDATE candidate_merges SET state='merged',updated=? WHERE candidate_id=?", (now(), cid))
            st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,'candidate_merge',?,?)",
                          (t["id"], now(), user, "已合并固定候选到本地主干；尚未推送或部署",
                           _json({"candidate": cid, "commit": row["commit_sha"], "main": main, "evidence_hash": evidence_hash})))
            st.db.commit()
            return dict(merge_receipt(P, cid), pushed=False, deployed=False, replayed=False)
        except BaseException:
            st.db.rollback()
            raise


def _acceptance_memory(P, event_id):
    from . import learn
    try:
        card = learn.on_candidate_accept(P, event_id)
        return {"lesson_id": card["id"], "status": card["status"], "project": card["project"], "pending": False}
    except Exception:  # learning must not undo an already committed human verdict
        return {"pending": True, "event_id": event_id,
                "message": "业务验收已保存，记忆暂未写入。请用相同结果和说明再次提交业务验收以补写，原验收不会重复。"}


def browser_accept(P, cid, user, evidence_hash, passed, note, mutation=lambda: None):
    """Explicit business verdict on the already-reviewed, already-merged version.

    This is a team member's acceptance, not an external customer's signature.
    No legacy adoption is synthesized and no release/deployment is launched.
    """
    from . import team, release, learn
    from .recheck_operations import source_guard
    row = _row(P, cid)
    if implementation_author(row["agent"],user):
        raise ApiError(403,"固定候选的实现者不能验收自己的交付；重新分配任务不会改变提交作者")
    team.require_reviewer(P, row["ticket_id"], user)
    if not isinstance(note, str) or not note.strip():
        raise ApiError(400, "请记录实际业务验收操作、结果及限制")
    with guard(P, row["ticket_id"]), source_guard(P.data_dir, row["run_id"]), P.store.lock:
        st = P.store
        team.require_reviewer(P, row["ticket_id"], user)
        previous = st.one("SELECT * FROM events WHERE ticket_id=? AND kind IN ('accept','reject') ORDER BY id DESC LIMIT 1", (row["ticket_id"],))
        old = previous and previous["data"] or {}
        # A replay only projects the original verdict's snapshot. It neither
        # re-accepts current evidence nor changes a closed/reopened ticket.
        if (previous and old.get("memory_snapshot") and previous["author"] == user and
                old.get("candidate") == cid and old.get("evidence_hash") == evidence_hash and
                old.get("result") == ("pass" if passed else "fail") and old.get("note") == note):
            mutation()
            return dict(st.ticket(row["ticket_id"]), memory=_acceptance_memory(P, previous["id"]), replayed=True)
        try:
            st.db.execute("BEGIN IMMEDIATE")
            t = team.require_reviewer(P, row["ticket_id"], user)
            v = view(P, cid)
            merged = merge_receipt(P, cid)
            if evidence_hash != v["evidence_hash"] or not v["human_accepted"] or not browser_review_current(P, cid):
                raise ApiError(409, "请先在团队工作台复核当前固定版本；当前证据或责任已变化")
            if not merged or merged["state"] != "merged" or merged["commit_sha"] != row["commit_sha"]:
                raise ApiError(409, "当前候选尚未完成与固定版本一致的本地合并")
            # The preview may be restarted after merging. Current evidence still
            # needs a fresh independent human approval; the immutable merge
            # receipt keeps the evidence used when that exact commit was merged.
            # Preserve both hashes instead of rewriting history or demanding a
            # second Git merge for the same version.
            p = st.project(t["project_id"])
            main = release.main_branch(Path(p["root"]), P.data_dir, p["key"])
            if not main or main != merged["main"]:
                raise ApiError(409, "主干配置已变化，请先核对版本")
            _git(Path(p["root"]), "merge-base", "--is-ancestor", row["commit_sha"], "refs/heads/" + main)
            stamp, status = now(), "closed" if passed else "doing"
            run = st.run(row["run_id"])
            snapshot = {"project": p["key"], "ticket": {"id": t["id"], "key": t["key"], "title": t["title"],
                        "body": t.get("body") or "", "flows": (t.get("links") or {}).get("flows") or []},
                        "base_commit": row["base_commit"], "requirement_hash": row["requirement_hash"],
                        "memory_uses": learn.credit_snapshot(P, t),
                        "criteria": v["criteria"], "assessment": v["assessment"], "review": v["human_decision"],
                        "merge": merged, "summary": row["summary"], "files": learn.changed_files(run.get("diff") or "")}
            mutation()
            accepted = st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                          (t["id"], stamp, user, "accept" if passed else "reject", ("业务验收通过：" if passed else "业务验收不通过：") + note,
                           _json({"result": "pass" if passed else "fail", "candidate": cid, "commit": row["commit_sha"],
                                  "evidence_hash": evidence_hash, "merge_evidence_hash": merged["evidence_hash"],
                                  "main": main, "via": "团队工作台", "customer_signature": False,
                                  "note": note, "memory_snapshot": snapshot})))
            if t["status"] != status:
                st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,'status',?,?)",
                              (t["id"], stamp, user, "团队业务验收：%s → %s" % (t["status"], status), _json({"from": t["status"], "to": status})))
            st.db.execute("UPDATE tickets SET status=?,updated=? WHERE id=?", (status, stamp, t["id"]))
            st.db.commit()
            return dict(st.ticket(t["id"]), memory=_acceptance_memory(P, accepted.lastrowid))
        except BaseException:
            st.db.rollback()
            raise
