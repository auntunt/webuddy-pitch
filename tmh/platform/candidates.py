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


def _git(root, *args, raw=False):
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
    return _hash({"commands": config.load(Path(project["root"])).get("commands"),
                  "checks": settings(P.data_dir), "testbox": box_settings(P.data_dir),
                  "preview": command(P.data_dir, project)})


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
        fp = _hash({"ticket": t["id"], "base": args["base_commit"], "commit": args["commit"],
                    "requirement": args["requirement_hash"], "configuration": conf, "criteria": args["criteria"]})
        old = st.one("SELECT * FROM code_candidates WHERE fingerprint=?", (fp,))
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
            if _requirement(t, st) != args["requirement_hash"]:
                raise ApiError(409, "需求在提交期间变化，请重新核对")
            _check_baseline(root, t, args["base_commit"])
            if configuration(P, st.project(t["project_id"])) != conf:
                raise ApiError(409, "执行配置在提交期间变化，请重新核对")
            stamp = now()
            run = st.db.execute("""INSERT INTO runs(project_id,ticket_id,agent,mode,status,author,created,ended,exit_code,
                 prompt,result,diff,target) VALUES(?,?,?,'fix','done',?,?,?,0,?,?,?,?)""",
                 (p["id"], t["id"], "external:" + actor.removeprefix("agent:"), actor, stamp, stamp,
                  "外部候选登记；不是平台模型执行或人工采纳", args["summary"], diff, args["base_commit"])).lastrowid
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
    pv = preview.status(P.data_dir, t["key"])
    preview_ok = pv.get("state") == "up" and preview.bound_matches(pv, t["key"], row["commit_sha"])
    ph = _hash({k: pv.get(k) for k in ("commit_full", "prefix", "started", "pid", "log", "cmd", "ready")}) if preview_ok else ""
    assessment = st.one("SELECT * FROM candidate_assessments WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (cid,))
    results = json.loads(assessment["results"]) if assessment else []
    technical_ok = bool(verification_ok and probe_ok and preview_ok and assessment and assessment["verification_hash"] == vh
                        and assessment["preview_hash"] == ph
                        and assessment["author"] != row["agent"] and all(r["status"] == "pass" for r in results))
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
            "preview_url": getattr(P, "public_url", "") + preview.bound_prefix(t["key"], row["commit_sha"]) + "/" if preview_ok else "",
            "preview_entry_path": preview.bound_prefix(t["key"], row["commit_sha"]) + "/" if preview_ok else "",
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
        return submit(P, actor, a, mutation)
    row = _row(P, a["candidate_id"])
    with guard(P, row["ticket_id"]):
        v = view(P, row["id"])
        if op == "candidate_cancel":
            operation = P.flow.rechecks.status(row["run_id"])
            if not operation or not operation.get("running"):
                raise ApiError(409, "当前没有正在验证的候选")
            mutation()
            return P.flow.rechecks.runner.cancel(operation["id"], actor)
        if not v["current"]:
            raise ApiError(409, "；".join(v["blocked"]))
        if op == "candidate_verify":
            previous = P.flow.rechecks.status(row["run_id"])
            if previous and not previous.get("can_retry"):
                raise ApiError(409, "；".join(previous.get("blocked") or ["原验证尚未结束"]))
            mutation()
            return P.flow.recheck(row["run_id"], actor)
        # Serialize decisions and preview publication against rechecks.
        from .recheck_operations import source_guard
        with source_guard(P.data_dir, row["run_id"]):
            v = view(P, row["id"])
            if op == "candidate_preview":
                if not v["verification_passed"]:
                    raise ApiError(409, "平台独立构建/测试尚未通过，不启动候选预览")
                from . import preview
                t = P.store.ticket(row["ticket_id"])
                p = P.store.project(t["project_id"])
                mutation()
                state = preview.start(P, p, t, row["commit_sha"], actor, expected_commit=row["commit_sha"])
                P.store.event(t["id"], actor, "preview", "启动独立验证后的外部候选预览", {"candidate": row["id"], "commit": row["commit_sha"]})
                return {"candidate_id": row["id"], "preview": state}
            if op == "candidate_assess":
                if not v["verification_passed"] or a["verification_hash"] != v["verification_hash"] or not v["preview_ready"] or a["preview_hash"] != v["preview_hash"]:
                    raise ApiError(409, "验证或预览依据已变化，先读取当前候选并重新验证")
                if actor == row["agent"]:
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
                kind, body = "candidate_decision", "操作者确认候选：" + a["decision"]
            st.db.execute("INSERT INTO events(ticket_id,ts,author,kind,body,data) VALUES(?,?,?,?,?,?)",
                (row["ticket_id"], now(), actor, kind, body, _json({"candidate": row["id"], "record": item})))
            st.db.commit()
        except BaseException:
            st.db.rollback()
            raise
