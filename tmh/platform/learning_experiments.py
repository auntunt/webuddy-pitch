"""Fixed, synthetic experiments: one ledger, one immutable plan, no paid path.

Public receipts deliberately contain no experimental material. HTTP callers
must use learning_experiment_views for authorized projections. Internal rows
are not a security boundary against arbitrary code in the host process.
"""
from __future__ import annotations

from contextlib import contextmanager

import hashlib
import json
import math
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

from . import learning as L, learning_eval as E, tenant_policy as TP
from .errors import ApiError
from .store import now

VERSION = "fixed-a-synthetic-v1"
PROCESS_EPOCH = uuid.uuid4().hex  # restarted workers cannot prove a prior monotonic anchor
EXECUTOR_ID = "synthetic-fixed-a-v1"
TASK_SET = "synthetic-three-families-v1"
TERMINAL = {"mechanism_passed", "not_passed", "cancelled", "timed_out", "stale", "unknown"}
SLOT_TERMINAL = {"completed", "failed", "not_executed", "unknown"}
TABLES = ("learning_experiments", "learning_experiment_assets", "learning_experiment_slots", "learning_experiment_events")
DDL = (
    """CREATE TABLE learning_experiments (
    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, project_id INTEGER NOT NULL,
    creator TEXT NOT NULL, approver TEXT NOT NULL DEFAULT '', curator TEXT NOT NULL,
    optimizer TEXT NOT NULL, selector TEXT NOT NULL, principals TEXT NOT NULL,
    request_id TEXT NOT NULL, request_hash TEXT NOT NULL, contract_version TEXT NOT NULL,
    contract TEXT NOT NULL, contract_hash TEXT NOT NULL, state TEXT NOT NULL,
    job_id TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, sealed TEXT NOT NULL DEFAULT '',
    started TEXT NOT NULL DEFAULT '', ended TEXT NOT NULL DEFAULT '', deadline REAL NOT NULL DEFAULT 0,
    owner TEXT NOT NULL DEFAULT '', fence INTEGER NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0, report TEXT NOT NULL DEFAULT '{}',
    report_hash TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
    UNIQUE(tenant_id,project_id,creator,request_id))""",
    "CREATE UNIQUE INDEX ix_experiment_job ON learning_experiments(job_id) WHERE job_id!=''",
    """CREATE TABLE learning_experiment_assets (
    experiment_id TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
    content_hash TEXT NOT NULL, family TEXT NOT NULL, lineage TEXT NOT NULL,
    revision_id TEXT NOT NULL DEFAULT '', visibility TEXT NOT NULL, known_to TEXT NOT NULL,
    PRIMARY KEY(experiment_id,id))""",
    "CREATE INDEX ix_experiment_revision ON learning_experiment_assets(revision_id,kind,experiment_id)",
    """CREATE TABLE learning_experiment_slots (
    experiment_id TEXT NOT NULL, id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    task_asset_id TEXT NOT NULL, arm TEXT NOT NULL, repeat INTEGER NOT NULL,
    job_id TEXT NOT NULL, step_role TEXT NOT NULL, run_id INTEGER, state TEXT NOT NULL,
    owner TEXT NOT NULL DEFAULT '', fence INTEGER NOT NULL DEFAULT 0,
    dispatch_id TEXT NOT NULL DEFAULT '', prompt_hash TEXT NOT NULL DEFAULT '',
    input_binding TEXT NOT NULL DEFAULT '{}', reserved_calls INTEGER NOT NULL DEFAULT 0,
    settled_calls INTEGER NOT NULL DEFAULT 0, synthetic_units INTEGER NOT NULL DEFAULT 0,
    result TEXT NOT NULL DEFAULT '{}', cleanup TEXT NOT NULL DEFAULT '{}',
    created TEXT NOT NULL, ended TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(experiment_id,id), UNIQUE(experiment_id,ordinal), UNIQUE(job_id,step_role))""",
    "CREATE UNIQUE INDEX ix_experiment_run ON learning_experiment_slots(run_id) WHERE run_id IS NOT NULL",
    "CREATE UNIQUE INDEX ix_experiment_dispatch ON learning_experiment_slots(dispatch_id) WHERE dispatch_id!=''",
    """CREATE TABLE learning_experiment_events (
    experiment_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL,
    request_id TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL,
    PRIMARY KEY(experiment_id,seq))""",
    "CREATE UNIQUE INDEX ix_experiment_request ON learning_experiment_events(experiment_id,actor,request_id) WHERE request_id!=''",
)
COLUMNS = {
    TABLES[0]: set("id tenant_id project_id creator approver curator optimizer selector principals request_id request_hash contract_version contract contract_hash state job_id created sealed started ended deadline owner fence lease_until cancel_requested report report_hash error".split()),
    TABLES[1]: set("experiment_id id kind content content_hash family lineage revision_id visibility known_to".split()),
    TABLES[2]: set("experiment_id id ordinal task_asset_id arm repeat job_id step_role run_id state owner fence dispatch_id prompt_hash input_binding reserved_calls settled_calls synthetic_units result cleanup created ended".split()),
    TABLES[3]: set("experiment_id seq kind actor request_id request_hash payload created".split()),
}
INDEXES = {"ix_experiment_job", "ix_experiment_revision", "ix_experiment_run", "ix_experiment_dispatch", "ix_experiment_request"}

# Server-owned materials are explicitly synthetic and publicly known examples,
# not independent real-world evidence. Cassettes do not inspect the oracle.
_TASKS = (
    {"id": "source-a", "family": "synthetic-family-a", "input": "合成流程 A：检查变更后输出固定标记 ALPHA。", "expected": "ALPHA"},
    {"id": "source-b", "family": "synthetic-family-b", "input": "合成流程 B：检查交付后输出固定标记 BETA。", "expected": "BETA"},
    {"id": "source-c", "family": "synthetic-family-c", "input": "合成流程 C：检查回滚后输出固定标记 GAMMA。", "expected": "GAMMA"},
)
_CASSETTES = {"source-a": {"baseline": "ALPHA", "candidate": "ALPHA"},
              "source-b": {"baseline": "BETA", "candidate": "BETA"},
              "source-c": {"baseline": "GAMMA", "candidate": "GAMMA"}}
SYNTHETIC_CODE = ("import sys,json,hashlib;d=json.loads(sys.stdin.read());"
                  "assert hashlib.sha256(d['prompt'].encode('utf-8')).hexdigest()==d['prompt_sha256'];"
                  "sys.stdout.write(d['output']);sys.stdout.flush()")


def encoded(value):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        text.encode("utf-8")
        return text
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ApiError(400, "实验材料必须可以无损编码为有限 UTF-8 JSON") from exc


def digest(value):
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def _db(value):
    return value.db if hasattr(value, "db") else value


def schema_state(value):
    db = _db(value)
    found = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'") if r["name"] in TABLES}
    if not found:
        return "absent"
    if found != set(TABLES):
        raise ApiError(409, "实验账本结构不完整，不能降级为手工运行")
    for table in TABLES:
        cols = {r["name"] for r in db.execute("PRAGMA table_info(" + table + ")")}
        if not COLUMNS[table] <= cols:
            raise ApiError(409, "实验账本字段不完整")
    indexes = {r["name"]: r["sql"] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type='index'")}
    if not INDEXES <= set(indexes):
        raise ApiError(409, "实验账本约束不完整")
    # The predicate is part of each uniqueness contract. A same-name index
    # with WHERE 0 must not silently turn ownership into an unconstrained table.
    for statement in DDL:
        match = re.match(r"CREATE (?:UNIQUE )?INDEX (\w+) ", statement)
        if match:
            expected = re.sub(r"\s+", "", statement).lower()
            actual = re.sub(r"\s+", "", indexes.get(match[1]) or "").lower()
            if actual != expected:
                raise ApiError(409, "实验账本索引定义与冻结约束不符")
    required = {
        TABLES[0]: {("id",), ("tenant_id", "project_id", "creator", "request_id"), ("job_id",)},
        TABLES[1]: {("experiment_id", "id")},
        TABLES[2]: {("experiment_id", "id"), ("experiment_id", "ordinal"), ("job_id", "step_role"), ("run_id",), ("dispatch_id",)},
        TABLES[3]: {("experiment_id", "seq"), ("experiment_id", "actor", "request_id")},
    }
    for table, expected in required.items():
        actual = set()
        for idx in db.execute("PRAGMA index_list(" + table + ")"):
            if idx["unique"]:
                actual.add(tuple(c["name"] for c in db.execute("PRAGMA index_info(" + idx["name"] + ")")))
        if not expected <= actual:
            raise ApiError(409, "实验账本唯一约束不可核验")
    return "ready"


def schema(store):
    with L.transaction(store) as db:
        if schema_state(db) == "ready":
            return
        for statement in DDL:
            db.execute(statement)
        schema_state(db)


@contextmanager
def mutation(store, *, create_key=None, decision_key=None):
    """Classify only a proven absent request whose body was rolled back.

    Unknown/prior committed requests remain unknown on any error. BEGIN,
    commit and rollback failures are never represented as safe-to-replace.
    The outer authorization guard is deliberately outside this boundary.
    """
    body_error, prior, db = None, None, None
    with store.lock:
        try:
            with L.transaction(store) as db:
                try:
                    if create_key is not None and decision_key is None:
                        prior = db.execute("SELECT 1 FROM learning_experiments WHERE tenant_id=? AND project_id=? AND creator=? AND request_id=?", create_key).fetchone() is not None
                    elif decision_key is not None and create_key is None:
                        prior = db.execute("SELECT 1 FROM learning_experiment_events WHERE experiment_id=? AND actor=? AND request_id=?", decision_key).fetchone() is not None
                    else:
                        raise RuntimeError("one experiment request identity is required")
                    yield db
                except (ApiError, ValueError) as exc:
                    body_error = exc
                    raise
        except (ApiError, ValueError) as exc:
            if exc is body_error and prior is False and db is not None and not db.in_transaction:
                exc.reason = "experiment_not_written"
            raise


def _require_tx(db):
    if not db.in_transaction:
        raise RuntimeError("experiment write requires caller transaction")


def _request(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ApiError(400, "实验操作需要不超过 200 字符的幂等编号")
    encoded(value)
    return value


def _decode(row):
    item = dict(row)
    for key in ("principals", "contract", "report"):
        item[key] = json.loads(item[key])
    return item


def _row(db, p, eid):
    if not isinstance(eid, str) or not re.fullmatch(r"[0-9a-f]{32}", eid):
        raise ApiError(404, "没有这个项目的实验")
    if schema_state(db) != "ready":
        raise ApiError(404, "没有这个项目的实验")
    row = db.execute("SELECT * FROM learning_experiments WHERE id=? AND project_id=?", (eid, p["id"])).fetchone()
    if row is None:
        raise ApiError(404, "没有这个项目的实验")
    return _decode(row)


def get_internal(P, p, eid):
    with P.store.lock:
        return _row(P.store.db, L.project(P, p), eid)


def assets_in_tx(db, eid):
    values = []
    for row in db.execute("SELECT * FROM learning_experiment_assets WHERE experiment_id=? ORDER BY id", (eid,)):
        item = dict(row)
        try:
            item.update(content=json.loads(item["content"]), lineage=json.loads(item["lineage"]), known_to=json.loads(item["known_to"]))
            if digest(item["content"]) != item["content_hash"]:
                raise ValueError("asset digest")
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ApiError(409, "实验完整材料不可核验") from exc
        values.append(item)
    return values


def _receipt(exp, replayed=False, *, action="", request_id=""):
    return {"experiment_id": exp["id"], "job_id": exp["job_id"], "contract_hash": exp["contract_hash"],
            "state": exp["state"], "replayed": replayed, "action": action, "request_id": request_id}


def _event(db, eid, kind, actor, payload, request_id="", request_hash=""):
    _require_tx(db)
    seq = db.execute("SELECT COALESCE(MAX(seq),0)+1 AS next_seq FROM learning_experiment_events WHERE experiment_id=?", (eid,)).fetchone()["next_seq"]
    db.execute("INSERT INTO learning_experiment_events VALUES(?,?,?,?,?,?,?,?)",
               (eid, seq, kind, actor, request_id, request_hash, encoded(payload), now()))
    return seq


def _replay(db, exp, actor, request_id, kind, payload):
    _request(request_id)
    h = digest({"kind": kind, "payload": payload, "actor": actor})
    old = db.execute("SELECT * FROM learning_experiment_events WHERE experiment_id=? AND actor=? AND request_id=?",
                     (exp["id"], actor, request_id)).fetchone()
    if old and old["request_hash"] != h:
        raise ApiError(409, "幂等编号已用于不同实验操作")
    return old is not None, h


def _roles(P, p, names):
    # The enclosing experiment_guard owns the registry lease before Store.
    result = {}
    for name in set(names):
        who = TP.experiment_identity(P, name, p, "viewer")
        result[name] = who["account_epoch"]
    return result


def current_authority(P, p, exp, actor, *, manager=False, execution=False, participants=True):
    who = TP.experiment_identity(P, actor, p, "manager" if manager else "viewer")
    if str(who["tenant_id"]) != exp["tenant_id"]:
        raise ApiError(403, "实验不属于当前租户")
    for person, epoch in (exp["principals"].items() if participants else []):
        active = TP.experiment_identity(P, person, p, "viewer")
        if active["account_epoch"] != epoch:
            raise ApiError(403, "实验参与成员账号已变化，旧合同不能重新生效")
    if execution:
        TP.require_execution(P, actor)
    return who


def _executor_binding():
    exe = Path(sys.executable).resolve()
    stat = exe.stat()
    return {"id": EXECUTOR_ID, "code_sha256": digest(SYNTHETIC_CODE), "python": str(exe),
            "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "code": SYNTHETIC_CODE,
            "paid_dispatch": False, "actual_tokens": {"status": "unavailable", "value": None},
            "actual_cost": {"status": "unavailable", "amount": None, "currency": None}}


def _validate_body(body):
    allowed = {"candidate_revision_id", "repeats", "max_calls", "timeout_seconds", "curator", "optimizer", "selector", "executor_id", "task_set"}
    if not isinstance(body, dict) or set(body) != allowed:
        raise ApiError(400, "实验合同字段不完整或包含未允许字段")
    encoded(body)
    if body["executor_id"] != EXECUTOR_ID or body["task_set"] != TASK_SET:
        raise ApiError(403, "仅开放服务器登记的合成闭环；真实付费和任意执行器关闭")
    if type(body["repeats"]) is not int or not 1 <= body["repeats"] <= 10:
        raise ApiError(400, "固定重复次数必须是 1–10 的整数")
    if type(body["max_calls"]) is not int or body["max_calls"] != 6 * body["repeats"]:
        raise ApiError(400, "调用预算必须等于全部预登记双臂重复槽数")
    timeout = body["timeout_seconds"]
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise ApiError(400, "实验总期限必须大于零且不超过 3600 秒")
    for key in ("candidate_revision_id", "curator", "optimizer", "selector"):
        if not isinstance(body[key], str) or not body[key].strip():
            raise ApiError(400, "实验角色和修订必须有真实非空标识")
    return json.loads(encoded(body))


def _material(P, p, body, actor, principals):
    r = L.revision(P, p, body["candidate_revision_id"])
    if r["kind"] != "lesson":
        raise ApiError(400, "首批固定 A 仅支持经验规则")
    cases = [{"id": x["id"], "input": x["input"], "expected": x["expected"], "validator": "exact", "generation": False,
              "scenario": "server-owned synthetic fixture"} for x in _TASKS]
    f = E.validate_options(P, p, r, {"cases": cases, "max_calls": body["max_calls"]})["evaluation"]
    values = []
    def add(kind, content, family="", revision_id="", lineage=None):
        aid = uuid.uuid4().hex
        values.append({"id": aid, "kind": kind, "content": content, "content_hash": digest(content), "family": family,
                       "lineage": lineage or [], "revision_id": revision_id or "", "visibility": "custody", "known_to": sorted({actor, body["curator"]})})
        return aid
    add("baseline", f["baseline"], "lesson:" + r["origin_id"], f["baseline"]["revision_id"])
    add("candidate", {"revision_id": r["id"], "content": r["content"], "source": r["source"], "fingerprint": r["fingerprint"]},
        "lesson:" + r["origin_id"], r["id"], [r["parent_id"]] if r["parent_id"] else [])
    evaluation = add("evaluation", f)
    task_assets = []
    for task in _TASKS:
        aid = add("task", {"case_id": task["id"], "input": task["input"]}, task["family"], lineage=[TASK_SET, task["family"]])
        oracle = add("oracle", {"case_id": task["id"], "validator": "exact", "expected": task["expected"]}, task["family"])
        cassette = add("cassette", {"case_id": task["id"], "outputs": _CASSETTES[task["id"]]}, task["family"])
        task_assets.append({"task_asset_id": aid, "oracle_asset_id": oracle, "cassette_asset_id": cassette, "case_id": task["id"], "family": task["family"]})
    contract = {"schema": VERSION, "experiment_type": "fixed_a", "synthetic": True,
                "candidate_revision_id": r["id"], "candidate_fingerprint": r["fingerprint"],
                "baseline": {k: f["baseline"][k] for k in ("revision_id", "token")},
                "baseline_content_sha256": digest(f["baseline"]["content"]), "source_binding": L.binding(P, p),
                "repeats": body["repeats"], "max_calls": body["max_calls"], "timeout_seconds": body["timeout_seconds"], "concurrency": 1,
                "roles": {k: body[k] for k in ("curator", "optimizer", "selector")}, "evaluation_asset_id": evaluation,
                "task_set": TASK_SET, "tasks": task_assets, "executor": _executor_binding(),
                "renderer": f["contract"], "asset_commitments": {v["id"]: v["content_hash"] for v in values},
                "stop_rule": "first_failure_or_unknown_stops_remaining_slots", "order": "repeat_then_task_then_baseline_candidate",
                "knowledge_block_same_renderer": True, "production_prompt_equivalence": False,
                "rsi_qualified": False, "independent_real_sources": 0, "synthetic_source_families": 3,
                "known_custodians": sorted({actor, body["curator"]})}
    return contract, values


def create_draft(P, p, body, actor, request_id):
    p, body, request_id = L.project(P, p), _validate_body(body), _request(request_id)
    request_hash = digest({"body": body, "actor": actor})
    with TP.experiment_guard(P, actor, p, "manager") as who, mutation(P.store, create_key=(str(who["tenant_id"]), p["id"], actor, request_id)) as db:
        prior = db.execute("SELECT * FROM learning_experiments WHERE tenant_id=? AND project_id=? AND creator=? AND request_id=?",
                           (str(who["tenant_id"]), p["id"], actor, request_id)).fetchone()
        if prior:
            exp = _decode(prior)
            current_authority(P, p, exp, actor, manager=True)
            if exp["request_hash"] != request_hash:
                raise ApiError(409, "请求编号已用于不同实验草稿")
            return _receipt(exp, True, action="create", request_id=request_id)
        assert_unmanaged_revision_in_tx(db, p["id"], body["candidate_revision_id"])
        principals = _roles(P, p, [actor, body["curator"], body["optimizer"], body["selector"]])
        contract, assets = _material(P, p, body, actor, principals)
        eid = uuid.uuid4().hex
        db.execute("""INSERT INTO learning_experiments(id,tenant_id,project_id,creator,curator,optimizer,selector,principals,
                   request_id,request_hash,contract_version,contract,contract_hash,state,created)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'draft',?)""",
                   (eid, str(who["tenant_id"]), p["id"], actor, body["curator"], body["optimizer"], body["selector"], encoded(principals),
                    request_id, request_hash, VERSION, encoded(contract), digest(contract), now()))
        for a in assets:
            db.execute("INSERT INTO learning_experiment_assets VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (eid, a["id"], a["kind"], encoded(a["content"]), a["content_hash"], a["family"], encoded(a["lineage"]),
                        a["revision_id"], a["visibility"], encoded(a["known_to"])))
        _event(db, eid, "create", actor, {"contract_hash": digest(contract)})
        return _receipt(_row(db, p, eid), action="create", request_id=request_id)


def material_current(P, p, exp, assets=None):
    """Validate the experiment's own sealed material, never a fake manual job."""
    try:
        contract = exp["contract"]
        if digest(contract) != exp["contract_hash"] or exp["contract_version"] != VERSION:
            raise ValueError("contract digest")
        anchors = {}
        for row in P.store.db.execute("SELECT kind,payload FROM learning_experiment_events WHERE experiment_id=? AND kind IN ('create','seal')", (exp["id"],)):
            if row["kind"] in anchors:
                raise ValueError("duplicate preparation anchor")
            anchors[row["kind"]] = json.loads(row["payload"])["contract_hash"]
        if anchors.get("create") != exp["contract_hash"] or (exp["sealed"] and anchors.get("seal") != exp["contract_hash"]):
            raise ValueError("independent preparation anchor")
        assets = assets if assets is not None else assets_in_tx(P.store.db, exp["id"])
        if {a["id"]: a["content_hash"] for a in assets} != contract["asset_commitments"]:
            raise ValueError("asset commitments")
        by_id = {a["id"]: a for a in assets}
        f = by_id[contract["evaluation_asset_id"]]["content"]
        revision = L.revision(P, p, contract["candidate_revision_id"])
        if (revision["kind"] != "lesson" or not E._valid_lesson_frozen(f)
                or not E._matches_revision(f, revision) or not E._lesson_inputs_current(P, p, f)
                or E._baseline(P, p, revision) != f["baseline"]
                or contract["source_binding"] != L.binding(P, p)
                or contract["candidate_fingerprint"] != revision["fingerprint"]
                or contract["baseline"] != {k: f["baseline"][k] for k in ("revision_id", "token")}
                or contract["baseline_content_sha256"] != digest(f["baseline"]["content"])
                or contract["renderer"] != f["contract"]):
            raise ValueError("current source and full selected lesson material")
        expected_candidate = {"revision_id": revision["id"], "content": revision["content"],
                              "source": revision["source"], "fingerprint": revision["fingerprint"]}
        if ([a["content"] for a in assets if a["kind"] == "candidate"] != [expected_candidate]
                or [a["content"] for a in assets if a["kind"] == "baseline"] != [f["baseline"]]):
            raise ValueError("candidate or baseline ownership")
        if len(contract["tasks"]) != len(_TASKS) or len(f["cases"]) != len(_TASKS):
            raise ValueError("complete server-owned task plan")
        for task, fixed, case in zip(contract["tasks"], _TASKS, f["cases"]):
            if (task["case_id"] != fixed["id"] or task["family"] != fixed["family"]
                    or case["id"] != fixed["id"] or case["input"] != fixed["input"]
                    or case["expected"] != fixed["expected"] or case["validator"] != "exact" or case["generation"] is not False
                    or by_id[task["task_asset_id"]]["content"] != {"case_id": fixed["id"], "input": fixed["input"]}
                    or by_id[task["oracle_asset_id"]]["content"] != {"case_id": fixed["id"], "validator": "exact", "expected": fixed["expected"]}
                    or by_id[task["cassette_asset_id"]]["content"] != {"case_id": fixed["id"], "outputs": _CASSETTES[fixed["id"]]}):
                raise ValueError("task/oracle/cassette lineage")
        if contract["executor"] != _executor_binding():
            raise ValueError("executor identity")
        return f
    except (KeyError, ValueError, TypeError, OSError, AttributeError) as exc:
        raise ApiError(409, "冻结实验的独立准备锚、完整材料或当前来源不可核验") from exc


def _declared_ancestors(db, project_id, revision_id):
    """Only persisted parent links establish ancestry; shared text does not."""
    ancestors, current = set(), revision_id
    while current not in (None, ""):
        if not isinstance(current, str) or current in ancestors:
            raise ApiError(409, "人工运行修订谱系存在循环或无效声明")
        row = db.execute("SELECT project_id,parent_id FROM learning_revisions WHERE id=?", (current,)).fetchone()
        if not row or row["project_id"] != project_id:
            raise ApiError(409, "人工运行修订谱系缺失或跨项目")
        ancestors.add(current)
        current = row["parent_id"]
    if not ancestors:
        raise ApiError(409, "人工运行缺少修订谱系")
    return ancestors


def _assert_no_active_manual_overlap(db, project_id, revision_id):
    """Seal cannot reclassify an already running manual experiment lineage."""
    _require_tx(db)
    from . import learning_runs as R
    ancestors = _declared_ancestors(db, project_id, revision_id)
    terminal = sorted(R.TERMINAL)
    jobs = db.execute("SELECT id,revision_id,current_revision_id FROM learning_jobs WHERE project_id=? AND status NOT IN ("
                      + ",".join("?" for _ in terminal) + ")", (project_id, *terminal)).fetchall()
    for job in jobs:
        if job_owner(db, job["id"]):
            continue
        for rid in {job["revision_id"], job["current_revision_id"]}:
            prior = _declared_ancestors(db, project_id, rid)
            # Siblings may share an ancestor without either being an ancestor
            # of the other. Do not mistake that for a declared overlap.
            if rid in ancestors or revision_id in prior:
                raise ApiError(409, "同一修订或显式祖先/后代仍有人工运行；请先结束原运行再封存实验")


def seal(P, p, eid, expected_hash, actor, request_id):
    p = L.project(P, p)
    with TP.experiment_guard(P, actor, p, "manager"), mutation(P.store, decision_key=(eid, actor, request_id)) as db:
        exp = _row(db, p, eid)
        current_authority(P, p, exp, actor, manager=True)
        replay, h = _replay(db, exp, actor, request_id, "seal", {"expected_hash": expected_hash})
        if replay:
            return _receipt(exp, True, action="seal", request_id=request_id)
        if exp["state"] != "draft" or expected_hash != exp["contract_hash"]:
            raise ApiError(409, "实验草稿已变化或已封存")
        assert_unmanaged_revision_in_tx(db, p["id"], exp["contract"]["candidate_revision_id"])
        _assert_no_active_manual_overlap(db, p["id"], exp["contract"]["candidate_revision_id"])
        material_current(P, p, exp)
        contract = exp["contract"]
        jid = uuid.uuid4().hex
        monotonic_anchor = time.monotonic()
        deadline = time.time() + contract["timeout_seconds"]
        opaque = {"schema": VERSION, "managed_experiment_id": eid, "contract_hash": exp["contract_hash"]}
        db.execute("""INSERT INTO learning_jobs(id,project_id,kind,revision_id,current_revision_id,request_id,request_hash,actor,
                    status,options,binding,created,deadline) VALUES(?,?,'evaluate',?,?,?,?,?,'queued',?,?,?,?)""",
                   (jid, p["id"], contract["candidate_revision_id"], contract["candidate_revision_id"], "experiment:" + eid,
                    exp["contract_hash"], actor, encoded(opaque), encoded(opaque), now(), deadline))
        ordinal = 0
        for repeat in range(1, contract["repeats"] + 1):
            for task in contract["tasks"]:
                for arm in ("baseline", "candidate"):
                    ordinal += 1
                    sid = uuid.uuid4().hex
                    db.execute("""INSERT INTO learning_experiment_slots(experiment_id,id,ordinal,task_asset_id,arm,repeat,job_id,
                               step_role,state,created) VALUES(?,?,?,?,?,?,?,?,'planned',?)""",
                               (eid, sid, ordinal, task["task_asset_id"], arm, repeat, jid, "slot:" + sid, now()))
        principals = dict(exp["principals"])
        principals[actor] = TP.experiment_identity(P, actor, p, "manager")["account_epoch"]
        db.execute("UPDATE learning_experiments SET state='sealed',job_id=?,approver=?,principals=?,sealed=?,deadline=? WHERE id=?",
                   (jid, actor, encoded(principals), now(), deadline, eid))
        _event(db, eid, "seal", actor, {"contract_hash": exp["contract_hash"], "planned_slots": ordinal, "deadline": deadline,
                                                   "clock_session": PROCESS_EPOCH, "monotonic_anchor": monotonic_anchor,
                                                   "timeout_seconds": contract["timeout_seconds"]}, request_id, h)
        return _receipt(_row(db, p, eid), action="seal", request_id=request_id)


def cancel(P, p, eid, actor, request_id):
    p = L.project(P, p)
    with TP.experiment_guard(P, actor, p, "viewer"), mutation(P.store, decision_key=(eid, actor, request_id)) as db:
        exp = _row(db, p, eid)
        current_authority(P, p, exp, actor, participants=False)
        if actor not in (exp["creator"], exp["curator"]):
            TP.experiment_identity(P, actor, p, "manager")
        replay, h = _replay(db, exp, actor, request_id, "cancel", {})
        if replay:
            return _receipt(exp, True, action="cancel", request_id=request_id)
        if exp["state"] not in TERMINAL:
            active = db.execute("SELECT 1 FROM learning_experiment_slots WHERE experiment_id=? AND state='intent'", (eid,)).fetchone()
            state = "cancelling" if active else "cancelled"
            db.execute("UPDATE learning_experiments SET cancel_requested=1,state=?,ended=CASE WHEN ?='cancelled' THEN ? ELSE ended END WHERE id=?",
                       (state, state, now(), eid))
            if exp["job_id"] and not active:
                db.execute("UPDATE learning_jobs SET status='cancelled',error='实验已请求取消',ended=? WHERE id=?", (now(), exp["job_id"]))
            if not active:
                _unexecuted(db, eid, "cancelled_before_intent")
                if exp["job_id"]:
                    finalize_in_tx(db, _row(db, p, eid), reason="cancelled")
        possible = db.execute("SELECT 1 FROM learning_experiment_slots WHERE experiment_id=? AND state IN ('intent','unknown')", (eid,)).fetchone() is not None
        _event(db, eid, "cancel", actor, {"intent_may_be_in_flight": possible}, request_id, h)
        return _receipt(_row(db, p, eid), action="cancel", request_id=request_id)


def expose(P, p, eid, asset_ids, expected_hash, actor, request_id):
    p = L.project(P, p)
    if not isinstance(asset_ids, list) or not asset_ids or any(not isinstance(a, str) for a in asset_ids) or len(set(asset_ids)) != len(asset_ids):
        raise ApiError(400, "曝光必须明确列出不重复的资产编号")
    with TP.experiment_guard(P, actor, p, "viewer") as who, mutation(P.store, decision_key=(eid, actor, request_id)) as db:
        exp = _row(db, p, eid)
        current_authority(P, p, exp, actor)
        if actor != exp["curator"]:
            TP.experiment_identity(P, actor, p, "manager")
        payload = {"asset_ids": sorted(asset_ids), "expected_hash": expected_hash}
        replay, h = _replay(db, exp, actor, request_id, "expose", payload)
        if replay:
            return _receipt(exp, True, action="expose", request_id=request_id)
        if expected_hash != exp["contract_hash"] or not set(asset_ids) <= set(exp["contract"]["asset_commitments"]):
            raise ApiError(409, "曝光的合同或资产已经变化")
        _event(db, eid, "expose", actor, dict(payload, recipient=actor, account_epoch=who["account_epoch"], rsi_qualified=False), request_id, h)
        return _receipt(exp, action="expose", request_id=request_id)


def remaining_in_tx(db, exp):
    row = db.execute("SELECT payload FROM learning_experiment_events WHERE experiment_id=? AND kind='seal' ORDER BY seq LIMIT 1", (exp["id"],)).fetchone()
    if not row:
        raise ApiError(409, "实验缺少原始期限回执")
    value = json.loads(row["payload"])
    if value.get("clock_session") != PROCESS_EPOCH or type(value.get("monotonic_anchor")) not in (int, float):
        raise ApiError(409, "重启后不能证明原始时钟锚；本批不恢复执行")
    return max(0.0, min(exp["deadline"] - time.time(), exp["contract"]["timeout_seconds"] - (time.monotonic() - value["monotonic_anchor"])))


def _owner(exp):
    return {"experiment_id": exp["id"], "project_id": exp["project_id"], "tenant_id": exp["tenant_id"],
            "job_id": exp["job_id"], "revision_id": exp["contract"]["candidate_revision_id"]}


def _marker_job(db, jid):
    row = db.execute("SELECT project_id,options FROM learning_jobs WHERE id=?", (jid,)).fetchone()
    if not row:
        return None
    try:
        opts = json.loads(row["options"])
    except (ValueError, TypeError):
        raise ApiError(409, "知识运行归属不可核验") from None
    return row, opts


def _managed_lookup(store, *, job_id=None, run_id=None, revision_id=None):
    if sum(x is not None for x in (job_id, run_id, revision_id)) != 1:
        raise ValueError("one ownership key is required")
    db = _db(store)
    ready = schema_state(db) == "ready"
    if revision_id is not None:
        if not ready:
            return []
        ancestors, seen, project_id = [], set(), None
        current = revision_id
        while current:
            if not isinstance(current, str) or current in seen:
                raise ApiError(409, "修订谱系存在循环或无效声明")
            seen.add(current)
            revision = db.execute("SELECT id,project_id,parent_id FROM learning_revisions WHERE id=?", (current,)).fetchone()
            if not revision:
                if not ancestors:
                    return []  # the ordinary revision lookup retains its 404
                raise ApiError(409, "修订谱系缺少已声明父修订")
            if project_id is None:
                project_id = revision["project_id"]
            if revision["project_id"] != project_id:
                raise ApiError(409, "修订谱系跨项目矛盾")
            ancestors.append(current)
            current = revision["parent_id"]
        # The sealed contract is an independent ownership claim. An inner
        # JOIN alone would turn a missing candidate asset into manual access.
        rows = db.execute("""SELECT DISTINCT e.* FROM learning_experiments e LEFT JOIN learning_experiment_assets a
             ON a.experiment_id=e.id AND a.kind='candidate' WHERE e.sealed!='' AND
             (e.project_id=? OR a.revision_id IN (""" + ",".join("?" for _ in ancestors) + "))", [project_id, *ancestors]).fetchall()
        owners = []
        for row in rows:
            try:
                exp = _decode(row)
                contract = exp["contract"]
                candidate_id = contract["candidate_revision_id"]
                if not isinstance(candidate_id, str) or not candidate_id:
                    raise ValueError("candidate revision declaration")
                candidates = [dict(a) for a in db.execute("SELECT * FROM learning_experiment_assets WHERE experiment_id=? AND kind='candidate'", (exp["id"],))]
                asset_claim = any(a["revision_id"] in ancestors for a in candidates)
                if candidate_id not in ancestors and not asset_claim:
                    continue
                if exp["project_id"] != project_id or candidate_id not in ancestors or len(candidates) != 1:
                    raise ValueError("candidate ownership")
                candidate = candidates[0]
                content = json.loads(candidate["content"])
                if (candidate["revision_id"] != candidate_id or content["revision_id"] != candidate_id
                        or digest(contract) != exp["contract_hash"]
                        or digest(content) != candidate["content_hash"]
                        or contract["asset_commitments"].get(candidate["id"]) != candidate["content_hash"]):
                    raise ValueError("candidate commitment")
                anchors = [(r["kind"], json.loads(r["payload"])["contract_hash"]) for r in db.execute(
                    "SELECT kind,payload FROM learning_experiment_events WHERE experiment_id=? AND kind IN ('create','seal') ORDER BY kind", (exp["id"],))]
                if anchors != [("create", exp["contract_hash"]), ("seal", exp["contract_hash"])]:
                    raise ValueError("sealed ownership anchor")
                owners.append(_owner(exp))
            except (ValueError, KeyError, TypeError, UnicodeError, AttributeError) as exc:
                raise ApiError(409, "封存实验与候选修订归属不可核验") from exc
        return owners
    if job_id is not None:
        marker = _marker_job(db, job_id)
        rows = db.execute("SELECT * FROM learning_experiments WHERE job_id=? AND job_id!=''", (job_id,)).fetchall() if ready else []
        if not rows:
            if marker and isinstance(marker[1], dict) and "managed_experiment_id" in marker[1]:
                raise ApiError(409, "受管运行缺少实验归属")
            return []
        if len(rows) != 1 or not marker:
            raise ApiError(409, "实验运行归属不唯一")
        exp = _decode(rows[0])
        if marker[0]["project_id"] != exp["project_id"] or marker[1] != {"schema": VERSION, "managed_experiment_id": exp["id"], "contract_hash": exp["contract_hash"]}:
            raise ApiError(409, "实验运行归属矛盾")
        return [_owner(exp)]
    run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    rows = db.execute("SELECT * FROM learning_experiment_slots WHERE run_id=?", (run_id,)).fetchall() if ready else []
    if not rows:
        if run and str(run["batch"]).startswith("experiment:"):
            raise ApiError(409, "受管过程缺少实验槽归属")
        return []
    if len(rows) != 1 or not run:
        raise ApiError(409, "实验过程归属不唯一")
    slot = rows[0]
    owners = managed_lookup(db, job_id=slot["job_id"])
    step = db.execute("SELECT * FROM learning_steps WHERE job_id=? AND role=?", (slot["job_id"], slot["step_role"])).fetchone()
    if (len(owners) != 1 or owners[0]["experiment_id"] != slot["experiment_id"] or run["project_id"] != owners[0]["project_id"]
            or run["ticket_id"] is not None or run["session_id"] is not None or run["target"] != slot["step_role"]
            or run["batch"] != "experiment:" + slot["experiment_id"] + ":" + slot["id"] or not step or step["run_id"] != run_id):
        raise ApiError(409, "实验过程与槽或步骤归属矛盾")
    return owners


def managed_lookup(store, *, job_id=None, run_id=None, revision_id=None):
    if hasattr(store, "lock"):
        with store.lock:
            return _managed_lookup(store, job_id=job_id, run_id=run_id, revision_id=revision_id)
    return _managed_lookup(store, job_id=job_id, run_id=run_id, revision_id=revision_id)


def job_owner(store, jid):
    values = managed_lookup(store, job_id=jid)
    return values[0] if values else None


def run_owner(store, rid):
    values = managed_lookup(store, run_id=rid)
    return values[0] if values else None


def assert_unmanaged_revision_in_tx(db, project_id, revision_id):
    _require_tx(db)
    owners = managed_lookup(db, revision_id=revision_id)
    if any(o["project_id"] != project_id for o in owners):
        raise ApiError(409, "受管修订项目归属矛盾")
    if owners:
        raise ApiError(409, "受管修订不能另起手工候选或评测绕过实验账本")


def assert_adoptable_in_tx(db, project_id, revision_id, report_binding=None):
    _require_tx(db)
    if managed_lookup(db, revision_id=revision_id):
        raise ApiError(409, "合成实验只验证机制，不能作为生产知识采用凭据")


def _unexecuted(db, eid, reason):
    _require_tx(db)
    # A reservation has no execution authority until intent is committed.
    # Finish all three registered records in this same transaction, otherwise
    # cancellation could leave a queued run that no recovery path owns.
    for slot in db.execute("SELECT * FROM learning_experiment_slots WHERE experiment_id=? AND state='reserved'", (eid,)).fetchall():
        owner = run_owner(db, slot["run_id"])
        run = db.execute("SELECT status FROM runs WHERE id=?", (slot["run_id"],)).fetchone()
        step = db.execute("SELECT status FROM learning_steps WHERE job_id=? AND role=?", (slot["job_id"], slot["step_role"])).fetchone()
        if (not owner or owner["experiment_id"] != eid or slot["dispatch_id"]
                or not run or run["status"] != "queued" or not step or step["status"] != "reserved"):
            raise ApiError(409, "无意图预约与过程登记矛盾，不能退款或假定未执行")
        db.execute("UPDATE runs SET status='failed',exit_code=125,result=?,ended=? WHERE id=?", (reason, now(), slot["run_id"]))
        db.execute("UPDATE learning_steps SET status='failed',exit_code=125,error=?,ended=? WHERE job_id=? AND role=?",
                   (reason, now(), slot["job_id"], slot["step_role"]))
    db.execute("""UPDATE learning_experiment_slots SET state='not_executed',reserved_calls=0,result=?,ended=?
                  WHERE experiment_id=? AND state IN ('planned','reserved')""",
               (encoded({"reason": reason, "executed": False, "passed": False, "cleanup_status": "not_started"}), now(), eid))


def finalize_in_tx(db, exp, *, reason=""):
    _require_tx(db)
    slots = [dict(r) for r in db.execute("SELECT * FROM learning_experiment_slots WHERE experiment_id=? ORDER BY ordinal", (exp["id"],))]
    if len(slots) != exp["contract"]["max_calls"]:
        raise ApiError(409, "实验预登记分母不完整")
    if any(s["state"] not in SLOT_TERMINAL for s in slots):
        raise ApiError(409, "实验仍有未结算槽")
    rows = [{"slot_id": s["id"], "ordinal": s["ordinal"], "arm": s["arm"], "repeat": s["repeat"],
             "task_asset_id": s["task_asset_id"], "state": s["state"], "run_id": s["run_id"],
             "reserved_calls": s["reserved_calls"], "settled_calls": s["settled_calls"], "result": json.loads(s["result"])} for s in slots]
    passed = all(s["state"] == "completed" and json.loads(s["result"]).get("passed") is True for s in slots)
    state = ("unknown" if reason in ("unknown", "restart_deadline_unproven") or any(s["state"] == "unknown" for s in slots) else "cancelled" if exp["cancel_requested"] or reason == "cancelled"
             else "timed_out" if reason == "timed_out" else "stale" if reason == "stale" else "mechanism_passed" if passed and not reason else "not_passed")
    report = {"schema": VERSION, "experiment_id": exp["id"], "contract_hash": exp["contract_hash"], "state": state,
              "mechanism_passed": passed and state == "mechanism_passed", "rsi_qualified": False, "production_prompt_equivalence": False,
              "exposures": [json.loads(r["payload"]) for r in db.execute(
                  "SELECT payload FROM learning_experiment_events WHERE experiment_id=? AND kind='expose' ORDER BY seq", (exp["id"],))],
              "synthetic": True, "planned_slots": len(slots), "slots": rows, "repeats": exp["contract"]["repeats"],
              "independent_real_sources": 0, "synthetic_source_families": 3,
              "budget": {"max_calls": exp["contract"]["max_calls"], "reserved_calls": sum(s["reserved_calls"] for s in slots),
                         "settled_calls": sum(s["settled_calls"] for s in slots), "synthetic_units": sum(s["synthetic_units"] for s in slots)},
              "actual_tokens": {"status": "unavailable", "value": None}, "actual_cost": {"status": "unavailable", "amount": None, "currency": None}}
    if exp["report_hash"]:
        # Previously sealed scientific output is never silently recomputed.
        return exp["report"]
    db.execute("UPDATE learning_experiments SET state=?,report=?,report_hash=?,ended=?,owner='',lease_until=0,error=? WHERE id=?",
               (state, encoded(report), digest(report), now(), reason, exp["id"]))
    job_state = state if state in ("cancelled", "timed_out", "stale") else "failed" if state == "unknown" else "not_passed"
    db.execute("UPDATE learning_jobs SET status=?,result=?,error=?,ended=?,owner='',lease_until=0 WHERE id=?",
               (job_state, encoded(report), reason, now(), exp["job_id"]))
    _event(db, exp["id"], "finalize", "system:experiment-supervisor", {"report_hash": digest(report), "state": state, "initiated_by": exp["creator"]})
    return report
