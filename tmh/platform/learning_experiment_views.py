"""Read-only projections for managed experiments and every legacy copy.

The ledger is internal material. Public readers use this module before returning
any run, job, revision or decision. These reads never recover a worker, migrate a
schema, probe a process, or claim that recorded success is currently usable.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import re

from . import learning as L, learning_experiments as X, tenant_policy as TP
from .errors import ApiError

SCOPE = {"kind": "synthetic_mechanism", "synthetic": True,
         "rsi_qualified": False, "production_prompt_equivalence": False,
         "independent_real_sources": 0, "currentness": "not_checked"}
STATES = frozenset("draft sealed running cancelling mechanism_passed not_passed cancelled timed_out stale unknown".split())
SLOT_STATES = frozenset("planned reserved intent completed failed not_executed unknown".split())


def _copy(value):
    return deepcopy(value)


def _json(value):
    try:
        return json.loads(value) if isinstance(value, str) else _copy(value)
    except (ValueError, TypeError) as exc:
        raise ApiError(409, "实验记录不能完整读取") from exc


def _pick(row, keys):
    return {key: _copy(row[key]) for key in keys if key in row}


@contextmanager
def _read(P, p, actor):
    """Authorization lease precedes Store. Tools never acquire custody."""
    p = L.project(P, p)
    if TP.enabled(P):
        with P.tenant_context.registry.authorization_guard():
            who = TP.identity(P, actor)
            TP._check(P, who, p, "viewer")
            if not who.get("tool_connection") and not who.get("legacy"):
                who = TP.experiment_identity(P, actor, p)
            with P.store.lock:
                yield p, who
    else:
        with P.store.lock:
            yield p, {"legacy": True, "actor": actor}


def job_owner(store, job_id):
    return X.job_owner(store, job_id)


def run_owner(store, run_id):
    return X.run_owner(store, run_id)


def unmanaged_run_clause(store, alias="r"):
    """SQL filter applied before limits or derived analytics, never after them.

    Verify every marked/registered run first: a damaged relation must not leak
    through an otherwise ordinary operational aggregate. No experimental text
    is selected by the caller until this check succeeds.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", alias):
        raise ValueError("invalid SQL alias")
    with store.lock:
        ready = X.schema_state(store) == "ready"
        ids = {r["id"] for r in store.q("SELECT id FROM runs WHERE batch LIKE 'experiment:%'")}
        if ready:
            ids.update(r["run_id"] for r in store.q("SELECT run_id FROM learning_experiment_slots WHERE run_id IS NOT NULL"))
        for rid in ids:
            if X.run_owner(store, rid) is None:
                raise ApiError(409, "实验过程归属不能核验")
        marker = "COALESCE(" + alias + ".batch,'') NOT LIKE 'experiment:%'"
        if not ready:
            return marker
        return marker + " AND NOT EXISTS (SELECT 1 FROM learning_experiment_slots ev WHERE ev.run_id=" + alias + ".id)"


def _bound(exp, p, who):
    if exp["project_id"] != p["id"] or (not who.get("legacy") and str(who.get("tenant_id")) != exp["tenant_id"]):
        raise ApiError(409, "实验租户或项目归属矛盾")
    if exp["contract_version"] != X.VERSION or X.digest(exp["contract"]) != exp["contract_hash"]:
        raise ApiError(409, "冻结实验合同不可核验")
    return exp


def _preparation_anchors(exp, events):
    """Bind read visibility to the original preparation events, without live I/O."""
    anchors = {kind: [event for event in events if event["kind"] == kind]
               for kind in ("create", "seal")}
    if len(anchors["create"]) != 1 or len(anchors["seal"]) != bool(exp["sealed"]):
        raise ApiError(409, "实验独立创建或封存锚缺失或重复")
    created = anchors["create"][0]
    if not events or events[0] is not created or type(created["seq"]) is not int or created["seq"] != 1:
        raise ApiError(409, "实验首次创建锚顺序不可核验")
    for kind in ("create", "seal"):
        for event in anchors[kind]:
            payload = event["payload"]
            if (not isinstance(payload, dict) or not isinstance(payload.get("contract_hash"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", payload["contract_hash"])
                    or payload["contract_hash"] != exp["contract_hash"]):
                raise ApiError(409, "实验当前合同与独立准备锚不一致")
            if kind == "seal" and (type(event["seq"]) is not int or event["seq"] <= created["seq"]):
                raise ApiError(409, "实验封存锚顺序不可核验")


def _load(P, p, eid, who):
    exp = _bound(X.get_internal(P, p, eid), p, who)
    events = [dict(row, payload=_json(row["payload"])) for row in P.store.q(
        "SELECT * FROM learning_experiment_events WHERE experiment_id=? ORDER BY seq", (eid,))]
    _preparation_anchors(exp, events)
    assets = X.assets_in_tx(P.store.db, eid)
    if {a["id"]: a["content_hash"] for a in assets} != exp["contract"].get("asset_commitments"):
        raise ApiError(409, "实验资产与冻结合同不一致")
    slots = [dict(row) for row in P.store.q(
        "SELECT * FROM learning_experiment_slots WHERE experiment_id=? ORDER BY ordinal", (eid,))]
    if exp["sealed"] and len(slots) != exp["contract"]["max_calls"]:
        raise ApiError(409, "实验预登记计划不完整")
    if exp["job_id"]:
        owner = X.job_owner(P.store, exp["job_id"])
        if not owner or owner["experiment_id"] != eid:
            raise ApiError(409, "实验任务归属不能核验")
    for slot in slots:
        if slot["job_id"] != exp["job_id"]:
            raise ApiError(409, "实验计划槽归属矛盾")
        if slot["run_id"] is not None:
            owner = X.run_owner(P.store, slot["run_id"])
            if not owner or owner["experiment_id"] != eid:
                raise ApiError(409, "实验过程归属不能核验")
    if exp["report_hash"] and X.digest(exp["report"]) != exp["report_hash"]:
        raise ApiError(409, "实验报告不可核验")
    return exp, assets, events, slots


def _visible_assets(exp, assets, events, who):
    if who.get("legacy") or who.get("tool_connection") or not who.get("account_epoch"):
        return set()
    actor, epoch = who["actor"], who["account_epoch"]
    if exp["curator"] == actor and exp["principals"].get(actor) == epoch:
        return {a["id"] for a in assets}
    visible = set()
    for event in events:
        payload = event["payload"]
        if (event["kind"] == "expose" and event["actor"] == actor and isinstance(payload, dict)
                and payload.get("recipient") == actor and payload.get("account_epoch") == epoch):
            values = payload.get("asset_ids")
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise ApiError(409, "实验曝光授权不可核验")
            visible.update(values)
    return visible & {a["id"] for a in assets}


def _all_visible(assets, visible):
    return bool(assets) and {a["id"] for a in assets} <= visible


def _scientific(exp, assets):
    c = exp["contract"]
    # This is a complete decision summary of the fixed server protocol, not a
    # generic recursive filter: new contract fields need an explicit review.
    return {
        "schema": c["schema"], "experiment_type": c["experiment_type"], "synthetic": True,
        "candidate_revision_id": c["candidate_revision_id"],
        "baseline_revision_id": c["baseline"]["revision_id"],
        "source": _pick(c["source_binding"], ("project_id", "commit")),
        "roles": _pick(c["roles"], ("curator", "optimizer", "selector")),
        "known_custodians": _copy(c["known_custodians"]),
        "task_set": c["task_set"], "task_families": [_pick(t, ("task_asset_id", "family")) for t in c["tasks"]],
        "fixed_sources": [_pick(a, ("id", "kind", "family", "lineage", "revision_id")) for a in assets],
        "selection": {"kind": "fixed_a", "candidate_count": 1, "baseline": "frozen_current_relevant_selection",
                      "initial_local_pool": 500, "body_budget_characters": 1500, "extra_budget_characters": 3000,
                      "initial_public_pool": 100000, "maximum_lessons": 3, "maximum_public_lessons": 1,
                      "local_minimum_score": 1.5, "public_minimum_score": 2.0,
                      "ranking": "flows*3 + file_matches*2 + term_cosine*4 + bounded_historical_outcomes*0.5; stable ties",
                      "eligibility": "active_local_with_anchors_or_active_taken_public; no same-ticket; exclude unconditional overhead",
                      "qualification": "check_selected_sources_and_holdout_after_selection_without_refill",
                      "rendering": "complete_authorized_payload_without_truncation",
                      "holdout": "server_owned_synthetic_only", "order": c["order"], "stop_rule": c["stop_rule"]},
        "repeats": c["repeats"], "planned_slots": c["max_calls"], "task_count": len(c["tasks"]), "arms": ["baseline", "candidate"],
        "budget": _pick(c, ("max_calls", "timeout_seconds", "concurrency")),
        "executor": _pick(c["executor"], ("id", "code_sha256", "paid_dispatch")),
        "renderer": _copy(c["renderer"]), "knowledge_block_same_renderer": c["knowledge_block_same_renderer"],
        "rsi_qualified": False, "production_prompt_equivalence": False, "independent_real_sources": 0,
        "synthetic_source_families": c["synthetic_source_families"],
        "actual_tokens": {"status": "unavailable", "value": None},
        "actual_cost": {"status": "unavailable", "amount": None, "currency": None},
    }


def _slot(slot):
    out = _pick(slot, ("id", "ordinal", "task_asset_id", "arm", "repeat", "job_id", "run_id", "created", "ended",
                       "reserved_calls", "settled_calls", "synthetic_units"))
    out["state"] = slot["state"] if slot["state"] in SLOT_STATES else "unknown"
    return out


def _request_identity(who):
    """Stable personal namespace, distinct from changing authorization context.

    This is only a browser receipt-recovery identity. It grants no permission;
    every GET and explicit retry still reauthorizes the current account.
    """
    if who.get("legacy") or who.get("tool_connection") or not who.get("account_epoch"):
        return None
    return {"tenant_id": str(who["tenant_id"]), "actor": who["actor"], "account_epoch": who["account_epoch"]}


def _summary(P, p, eid, who):
    exp, assets, events, slots = _load(P, p, eid, who)
    visible = _visible_assets(exp, assets, events, who)
    full = _all_visible(assets, visible)
    out = _pick(exp, ("id", "project_id", "tenant_id", "creator", "approver", "curator", "optimizer", "selector",
                      "job_id", "created", "sealed", "started", "ended", "deadline", "cancel_requested", "contract_hash", "report_hash"))
    out.update(managed=True, protected=not full, evidence_scope=_copy(SCOPE),
               state=exp["state"] if exp["state"] in STATES else "unknown",
               scientific_contract=_scientific(exp, assets), slots=[_slot(s) for s in slots],
               planned_slots=exp["contract"]["max_calls"], recorded_slots=len(slots),
               slot_counts={state: sum(s["state"] == state for s in slots) for state in sorted(SLOT_STATES)},
               budget={"max_calls": exp["contract"]["max_calls"],
                       **{key: sum(s[key] for s in slots) for key in ("reserved_calls", "settled_calls", "synthetic_units")}},
               assets=[dict(_pick(a, ("id", "kind", "family", "lineage", "revision_id", "known_to")),
                            protected=a["id"] not in visible,
                            **({"content": _copy(a["content"]), "content_hash": a["content_hash"]} if a["id"] in visible else {})) for a in assets],
               events=[_pick(e, ("seq", "kind", "actor", "created")) for e in events],
               rsi_qualified=False, production_prompt_equivalence=False,
               exposure_recorded=any(e["kind"] == "expose" for e in events),
               can_adopt=False, currentness="not_checked", request_identity=_request_identity(who),
               capabilities=_capabilities(p, who, exp))
    if full:
        out.update(contract=_copy(exp["contract"]), report=_copy(exp["report"]), error=exp["error"],
                   events=_copy(events), slots=[dict(s, input_binding=_json(s["input_binding"]), result=_json(s["result"]), cleanup=_json(s["cleanup"])) for s in slots])
    return out


def experiment(P, p, eid, actor):
    with _read(P, p, actor) as (p, who):
        return _summary(P, p, eid, who)


def experiments(P, p, actor):
    with _read(P, p, actor) as (p, who):
        if X.schema_state(P.store) == "absent":
            return {"experiments": [], "evidence_scope": _copy(SCOPE), "can_create": _capabilities(p, who)["create"], "request_identity": _request_identity(who)}
        ids = P.store.q("SELECT id FROM learning_experiments WHERE project_id=? ORDER BY rowid DESC", (p["id"],))
        return {"experiments": [_summary(P, p, row["id"], who) for row in ids], "evidence_scope": _copy(SCOPE), "can_create": _capabilities(p, who)["create"], "request_identity": _request_identity(who)}


def _capabilities(p, who, exp=None):
    personal = bool(who.get("account_epoch")) and not who.get("tool_connection") and not who.get("legacy")
    manager = personal and TP._effective(who, p["key"]) == "manager"
    writable = personal and who.get("role") != "viewer" and TP._effective(who, p["key"]) in ("contributor", "manager")
    custodian = bool(exp) and personal and who["actor"] == exp["curator"] and exp["principals"].get(who["actor"]) == who["account_epoch"]
    return {"create": bool(manager), "seal": bool(manager and exp and exp["state"] == "draft"),
            "start": bool(manager and who.get("capabilities", {}).get("execution") is True and exp and exp["state"] == "sealed"),
            "cancel": bool(exp and exp["state"] not in X.TERMINAL and writable and (manager or custodian or who["actor"] == exp["creator"])),
            "expose": bool(exp and writable and (manager or custodian)), "adopt": False}


def _revision_owners(P, p, rid):
    values = X.managed_lookup(P.store, revision_id=rid) if rid else []
    if any(owner["project_id"] != p["id"] for owner in values):
        raise ApiError(409, "实验修订项目归属矛盾")
    return values


def _job_owners(P, p, row):
    direct = X.job_owner(P.store, row["id"])
    # A later seal cannot retroactively turn an earlier manual job into an
    # experiment, hide its already exposed material, or invent holdout status.
    values = [direct] if direct else []
    if row["project_id"] != p["id"] or any(owner["project_id"] != p["id"] for owner in values):
        raise ApiError(409, "实验运行项目归属矛盾")
    return list({owner["experiment_id"]: owner for owner in values}.values())


def _owners_full(P, p, owners, who):
    all_full = True
    for owner in owners:
        exp, assets, events, _ = _load(P, p, owner["experiment_id"], who)
        all_full = _all_visible(assets, _visible_assets(exp, assets, events, who)) and all_full
    return all_full


def _job(P, p, jid, who):
    row = P.store.one("SELECT * FROM learning_jobs WHERE id=? AND project_id=?", (jid, p["id"]))
    if row is None:
        raise ApiError(404, "没有这个项目的知识运行")
    owners = _job_owners(P, p, row)
    if not owners:
        return None
    full = _owners_full(P, p, owners, who)
    out = _pick(row, ("id", "project_id", "kind", "revision_id", "current_revision_id", "actor", "status", "created", "started", "ended", "deadline", "calls"))
    out.update(managed=True, protected=not full, experiment_ids=[o["experiment_id"] for o in owners],
               evidence_scope=_copy(SCOPE), currentness="not_checked", can_adopt=False,
               options={}, result={}, steps=[], rounds=[], error="")
    if full:
        out = dict(_copy(row), options=_json(row["options"]), binding=_json(row["binding"]), result=_json(row["result"]), **{k: out[k] for k in ("managed", "protected", "experiment_ids", "evidence_scope", "currentness", "can_adopt")})
        slots = {s["step_role"]: s for s in P.store.q("SELECT * FROM learning_experiment_slots WHERE job_id=?", (jid,))}
        steps = P.store.q("SELECT * FROM learning_steps WHERE job_id=? ORDER BY seq", (jid,))
        if any(s["role"] not in slots or slots[s["role"]]["run_id"] != s["run_id"] for s in steps):
            raise ApiError(409, "实验步骤与计划槽归属矛盾")
        out["steps"] = [dict(s, usage=_json(s["usage"])) for s in steps]
        out["rounds"] = [dict(r, claims=_json(r["claims"]), result=_json(r["result"])) for r in P.store.q("SELECT * FROM learning_rounds WHERE job_id=? ORDER BY round", (jid,))]
    return out


def job(P, p, job_id, actor):
    with _read(P, p, actor) as (p, who):
        return _job(P, p, job_id, who)


def _recorded_job(P, p, row, who, *, detail=False):
    """Classify before any manual annotation; both branches read the ledger."""
    managed = _job(P, p, row["id"], who)
    if managed is not None:
        return managed
    item = dict(_copy(row), **{key: _json(row[key]) for key in ("options", "binding", "result")})
    if detail:
        item["steps"] = [dict(s, usage=_json(s["usage"])) for s in P.store.q(
            "SELECT * FROM learning_steps WHERE job_id=? ORDER BY seq", (row["id"],))]
        item["rounds"] = [dict(r, claims=_json(r["claims"]), result=_json(r["result"])) for r in P.store.q(
            "SELECT * FROM learning_rounds WHERE job_id=? ORDER BY round", (row["id"],))]
        item["cost"] = {"amount": None, "currency": None, "status": "unknown"}
    # This existing helper describes immutable input schemas, without checking
    # live sources. Never run it for an experiment, including curator reads.
    from .learning_runs import _input_description
    return _input_description(P, p, item)


def _job_rows(P, p, rid=""):
    if not P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='learning_jobs'"):
        return []
    sql, args = "SELECT * FROM learning_jobs WHERE project_id=?", [p["id"]]
    if rid:
        sql += " AND (revision_id=? OR current_revision_id=?)"
        args.extend([rid, rid])
    return P.store.q(sql + " ORDER BY rowid DESC", args)


def catalog_jobs(P, p, actor, rid="", *, detail=False):
    """Read catalog jobs without sending managed records through legacy reads."""
    with _read(P, p, actor) as (p, who):
        # A partial experiment schema is not evidence that all jobs are manual.
        X.schema_state(P.store)
        return [_recorded_job(P, p, row, who, detail=detail) for row in _job_rows(P, p, rid)]


def catalog_revision(P, p, rid, actor):
    """Return managed metadata before catalog source/currentness checks."""
    with _read(P, p, actor) as (p, who):
        row = L.revision(P, p, rid)  # SQL-only; retains the ordinary 404.
        projected = _revision(P, p, row, who)
        rows = _job_rows(P, p, rid)
        job_managed = any([bool(_job_owners(P, p, job)) for job in rows])
        if not projected.get("managed"):
            if job_managed:
                raise ApiError(409, "实验修订与运行归属矛盾")
            return None
        jobs = [_recorded_job(P, p, job, who) for job in rows]
        return {"revision_id": rid, "managed": True, "protected": projected["protected"],
                "experiment_ids": projected["experiment_ids"], "evidence_scope": _copy(SCOPE),
                "currentness": "not_checked", "current": False, "stale": None,
                "machine": {"status": "managed", "job_id": jobs[0]["id"] if jobs else ""}, "jobs": jobs}


def managed_detail(P, p, rid, actor):
    """Return a recorded detail before L.detail can inspect a workspace.

    None proves only that the requested target is unmanaged. Its ordinary
    detail still needs classified jobs and the final history projection; a
    sealed sibling must not disable this target's existing manual workflow.
    """
    with _read(P, p, actor) as (p, who):
        row = L.revision(P, p, rid)
        history = [dict(r, source=_json(r["source"])) for r in P.store.q(
            "SELECT * FROM learning_revisions WHERE project_id=? AND kind=? AND origin_id=? ORDER BY rowid",
            (p["id"], row["kind"], row["origin_id"]))]
        decisions = [dict(d, payload=_json(d["payload"]), result=_json(d["result"])) for d in P.store.q(
            "SELECT * FROM learning_decisions WHERE project_id=? AND kind=? AND origin_id=? ORDER BY rowid",
            (p["id"], row["kind"], row["origin_id"]))]
        job_rows = _job_rows(P, p, rid)
        target_managed = bool(_revision_owners(P, p, rid))
        for r in history:
            _revision_owners(P, p, r["id"])
        for j in job_rows:
            _job_owners(P, p, j)
        for d in decisions:
            _revision_owners(P, p, d.get("revision_id"))
            nested = d.get("revision")
            if isinstance(nested, dict):
                _revision_owners(P, p, nested.get("id"))
        if not target_managed:
            return None
        revision = _revision(P, p, row, who)
        history = [_revision(P, p, r, who) for r in history]
        jobs = [_recorded_job(P, p, j, who, detail=True) for j in job_rows]
        decisions = [_decision(P, p, d, who) for d in decisions]
        return {"revision": revision, "history": history, "jobs": jobs, "decisions": decisions,
                "managed": True, "protected": any(v.get("protected") for v in [revision, *history, *jobs, *decisions]),
                "current": False, "expected_token": None, "expected_active": None, "active_revision_id": None,
                "currentness": "not_checked", "active_state": "not_checked", "recorded_only": True,
                "evidence_scope": _copy(SCOPE), "can_adopt": False}


def _run(P, p, rid, who, since=0, include_prompt=False):
    owner = X.run_owner(P.store, rid)
    if owner is None:
        return None
    row = P.store.run(rid)
    if not row or row["project_id"] != p["id"] or owner["project_id"] != p["id"] or row["ticket_id"] is not None or row["session_id"] is not None:
        raise ApiError(409, "实验过程项目或工单归属矛盾")
    full = _owners_full(P, p, [owner], who)
    out = _pick(row, ("id", "project_id", "ticket_id", "session_id", "agent", "mode", "status", "author", "created", "started", "ended", "exit_code"))
    out.update(managed=True, protected=not full, experiment_id=owner["experiment_id"], evidence_scope=_copy(SCOPE),
               currentness="not_checked", prompt="", output="", result="", diff="", output_len=None,
               target="", decision="", model="", can_retry=False, retry_blocked=["受管实验只允许通过实验入口操作"],
               verification=None, recheck=None, lifecycle=None, lifecycle_error="", recorded_only=True)
    if full:
        out.update(_copy(row))
        out["output_len"] = len(row["output"])
        out["output"] = row["output"][max(0, int(since)):]
        out["prompt"] = row["prompt"] if include_prompt else ""
    return out


def run(P, p, run_id, actor, since=0, include_prompt=False):
    with _read(P, p, actor) as (p, who):
        return _run(P, p, run_id, who, since, include_prompt)


def runs(P, actor, project_id=None, limit=200, allowed_projects=None):
    # Preserve SQL pagination and existing manual fields, project before reading.
    visible = {p["id"] for p in TP.visible_projects(P, actor)}
    allowed = visible if allowed_projects is None else visible & set(allowed_projects)
    if project_id is not None and project_id not in allowed:
        raise ApiError(403, "当前账号没有此项目所需权限")
    rows = P.store.runs(project_id=project_id, limit=limit, allowed_projects=sorted(allowed))
    out = []
    for row in rows:
        projected = run(P, P.store.project(row["project_id"]), row["id"], actor)
        out.append(_copy(row) if projected is None else projected)
    return out


def _revision(P, p, row, who):
    owners = _revision_owners(P, p, row.get("id"))
    if not owners:
        return _copy(row)
    full = _owners_full(P, p, owners, who)
    out = _copy(row) if full else dict(_pick(row, ("id", "project_id", "kind", "origin_id", "parent_id", "author", "created")), title="受管实验修订", content=None, source={})
    out.update(managed=True, protected=not full, experiment_ids=[o["experiment_id"] for o in owners], evidence_scope=_copy(SCOPE))
    return out


def revision(P, p, payload, actor):
    """Project direct capture replies through the same managed revision gate."""
    with _read(P, p, actor) as (p, who):
        return _revision(P, p, payload, who)


def _decision(P, p, payload, who):
    if not isinstance(payload, dict):
        raise ApiError(409, "人工决定记录不可读取")
    owners = _revision_owners(P, p, payload.get("revision_id"))
    for key in ("revision",):
        if isinstance(payload.get(key), dict):
            owners += _revision_owners(P, p, payload[key].get("id"))
    # D returns the recorded decision plus related copies. Managed content is
    # all-or-nothing here; old unknown keys cannot become an escape channel.
    if owners and not _owners_full(P, p, owners, who):
        out = _pick(payload, ("id", "project_id", "kind", "origin_id", "revision_id", "action", "actor", "status", "created", "replayed"))
        out.update(managed=True, protected=True, evidence_scope=_copy(SCOPE), payload={}, result={})
        return out
    return _copy(payload)


def decision(P, p, payload, actor):
    with _read(P, p, actor) as (p, who):
        return _decision(P, p, payload, who)


def learning_detail(P, p, payload, actor):
    with _read(P, p, actor) as (p, who):
        revision = _revision(P, p, payload["revision"], who)
        history = [_revision(P, p, r, who) for r in payload.get("history", [])]
        jobs = [_job(P, p, j["id"], who) or _copy(j) for j in payload.get("jobs", [])]
        decisions = [_decision(P, p, d, who) for d in payload.get("decisions", [])]
        if not any(value.get("managed") for value in [revision, *history, *jobs, *decisions]):
            return _copy(payload)
        # Retain only established outer metadata; arbitrary copies must not leak
        # the raw revision, job options, outputs, or old decision result.
        out = _pick(payload, ("current", "expected_token", "expected_active", "active_revision_id"))
        out.update(revision=revision, history=history, jobs=jobs, decisions=decisions)
        if revision.get("managed"):
            out.update(managed=True, protected=revision["protected"], current=False, expected_token=None,
                       evidence_scope=_copy(SCOPE), can_adopt=False)
        return out


def catalog(P, p, payload, actor):
    with _read(P, p, actor) as (p, who):
        out = _copy(payload)
        out["jobs"] = [_job(P, p, j["id"], who) or _copy(j) for j in payload.get("jobs", [])]
        return out
