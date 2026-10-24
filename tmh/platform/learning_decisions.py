"""Human decisions with CAS and a durable, idempotent projection outbox."""
from __future__ import annotations

import json
import uuid
from contextlib import nullcontext
from pathlib import Path

from . import learning as L, learn, signoff
from .errors import ApiError
from .store import now


def _active(P, p, r):
    if r["kind"] == "lesson":
        return learn.active_revision(P.data_dir, r["origin_id"])
    if r["kind"] == "fact":
        from . import learning_facts as F
        return F.active_revision(P, p, r["origin_id"])
    row = P.store.one("SELECT revision_id FROM learning_policy_active WHERE project_id=?", (p["id"],))
    return row["revision_id"] if row else None


def _token(P, p, r):
    if r["kind"] == "lesson":
        return learn.revision_token(P.data_dir, r["origin_id"])
    if r["kind"] == "fact":
        from . import learning_facts as F
        return F.revision_token(P, p, r["origin_id"])
    return _active(P, p, r)


def source_current(P, p, r):
    """Adoption can change original content; source commits/grants still must match."""
    try:
        s = r["source"]
        return (L.binding(P, p) == s["binding"] and
                all(L.digest(L.safe_read(p["root"], e["path"])) == e["sha256"] for e in s["evidence"]))
    except (ApiError, OSError, ValueError, KeyError):
        return False


def adopted_current(P, p, r):
    if _active(P, p, r) != r["id"] or not source_current(P, p, r):
        return False
    if r["kind"] == "lesson":
        card = learn.lesson(P.data_dir, r["origin_id"])
        return (card and card.get("project") == p["key"] and card["status"] == "active" and
                L.encoded(L.lesson_content(card, r["source"].get("lesson_content_schema"))) == r["content"])
    return True


def _decode(row):
    return dict(row, payload=json.loads(row["payload"]), result=json.loads(row["result"]))


def _job(P, p, r, job_id):
    from . import learning_runs, learning_eval
    job = learning_runs.get(P, p, job_id)
    if (job["status"] != "passed" or job["current_revision_id"] != r["id"] or
            job.get("result", {}).get("passed") is not True):
        raise ApiError(409, "需要对应确切修订的机器通过回执")
    if job["kind"] == "evaluate" and not learning_eval.current(P, p, job):
        raise ApiError(409, "基线或评测来源已变化，需要重新评测")
    if (r["kind"] == "fact") != (job["kind"] == "review"):
        raise ApiError(409, "验证类型与条目不匹配")
    return job


def decide(P, p, action, revision_id, actor, request_id, expected_active, reason, job_id=""):
    if not signoff.human(actor):
        raise ApiError(403, "只有个人操作者可以采用或撤销")
    if action not in ("adopt", "revoke"):
        raise ApiError(400, "未知人工决定")
    if not isinstance(reason, str) or not reason.strip():
        raise ApiError(400, "需要完整记录采用或撤销原因")
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 200:
        raise ApiError(400, "需要请求幂等编号")
    if expected_active is not None and not isinstance(expected_active, str):
        raise ApiError(400, "预期采用版本格式不正确")
    p = L.project(P, p)
    r = L.revision(P, p, revision_id)
    request = {"action": action, "revision_id": revision_id, "expected_active": expected_active,
               "reason": reason, "job_id": job_id}
    with L.transaction(P.store) as db, (learn.ledger_lock(P.data_dir) if r["kind"] == "lesson" else nullcontext()):
        old = db.execute("SELECT * FROM learning_decisions WHERE project_id=? AND actor=? AND request_id=?",
                         (p["id"], actor, request_id)).fetchone()
        if old:
            d = _decode(old)
            if d["payload"]["request"] != request:
                raise ApiError(409, "同一请求编号不能用于另一项人工决定")
        else:
            expected_token = _token(P, p, r)
            if _active(P, p, r) != expected_active:
                raise ApiError(409, "采用版本已被其他人更改，请刷新")
            if action == "revoke":
                if expected_active != r["id"]:
                    raise ApiError(409, "只能撤销当前确切修订")
            else:
                if not L.revision_current(P, p, r):
                    raise ApiError(409, "修订来源已过期，请重新固定版本")
                _job(P, p, r, job_id)
            # Policy parameters occupy one slot for the project, regardless of candidate name.
            pending = db.execute("SELECT id FROM learning_decisions WHERE project_id=? AND kind=? AND status='pending' AND (?='policy' OR origin_id=?)",
                                 (p["id"], r["kind"], r["kind"], r["origin_id"])).fetchone()
            if pending:
                raise ApiError(409, "已有待完成投影：" + pending["id"])
            if _token(P, p, r) != expected_token:
                raise ApiError(409, "登记人工决定期间正文或状态发生变化")
            payload = {"request": request, "expected_token": expected_token, "source": r["source"],
                       "content": r["content"]}
            did = uuid.uuid4().hex
            db.execute("INSERT INTO learning_decisions(id,project_id,kind,origin_id,revision_id,action,actor,request_id,payload,status,created) VALUES(?,?,?,?,?,?,?,?,?,'pending',?)",
                       (did, p["id"], r["kind"], r["origin_id"], r["id"], action, actor, request_id, L.encoded(payload), now()))
            d = _decode(db.execute("SELECT * FROM learning_decisions WHERE id=?", (did,)).fetchone())
    return project_decision(P, p, d["id"])


def project_decision(P, p, did):
    """Explicit mutation/retry only. Pure GET never drains this outbox."""
    p = L.project(P, p)
    row = P.store.one("SELECT * FROM learning_decisions WHERE id=? AND project_id=?", (did, p["id"]))
    if not row:
        raise ApiError(404, "人工决定不存在")
    d = _decode(row)
    if d["status"] != "pending":
        return d
    r = L.revision(P, p, d["revision_id"])
    payload = d["payload"]
    req = payload["request"]
    try:
        # Serialize retries across Store instances before inspecting the file-side
        # receipt. Otherwise one retry can mistake another's successful projection
        # for a conflicting baseline change. No model is invoked in this scope.
        with L.transaction(P.store) as db:
            fresh = db.execute("SELECT status FROM learning_decisions WHERE id=?", (did,)).fetchone()
            if fresh["status"] != "pending":
                return _decode(db.execute("SELECT * FROM learning_decisions WHERE id=?", (did,)).fetchone())
            if r["kind"] == "policy":
                if _active(P, p, r) != req["expected_active"]:
                    raise ApiError(409, "投影前采用版本已变化")
                if d["action"] == "adopt":
                    if not L.revision_current(P, p, r):
                        raise ApiError(409, "投影前策略来源已变化")
                    _job(P, p, r, req["job_id"])
                    L.policy_content(r["content"])
                    db.execute("INSERT INTO learning_policy_active VALUES(?,?,?) ON CONFLICT(project_id) DO UPDATE SET revision_id=excluded.revision_id,decision_id=excluded.decision_id",
                               (p["id"], r["id"], did))
                else:
                    db.execute("DELETE FROM learning_policy_active WHERE project_id=? AND revision_id=?", (p["id"], r["id"]))
                result = {"revision_id": r["id"], "active_revision_id": r["id"] if d["action"] == "adopt" else None}
            elif r["kind"] == "lesson":
                receipt = learn.projection_receipt(P.data_dir, did)
                if not receipt and d["action"] == "adopt":
                    if not L.revision_current(P, p, r):
                        raise ApiError(409, "投影前经验来源已变化")
                    _job(P, p, r, req["job_id"])
                if d["action"] == "adopt":
                    result = learn.project_revision(P.data_dir, p["key"], r["origin_id"], r["id"],
                                                    json.loads(payload["content"]), d["actor"], did, payload["expected_token"],
                                                    **({"content_schema": r["source"]["lesson_content_schema"]}
                                                       if r["source"].get("lesson_content_schema") else {}))
                else:
                    result = learn.revoke_revision(P.data_dir, p["key"], r["origin_id"], r["id"],
                                                   d["actor"], did, payload["expected_token"], req["reason"])
            else:
                from . import learning_facts as F
                fn = F.project_revision if d["action"] == "adopt" else F.revoke_revision
                result = fn(P, p, r, d["actor"], did, payload["expected_token"], req["reason"])
            # File bytes can survive a DB rollback. The already committed intent
            # remains pending and its next retry only supplements the DB receipt.
            db.execute("UPDATE learning_decisions SET status='applied',result=? WHERE id=? AND status='pending'",
                       (L.encoded(result), did))
    except (ApiError, ValueError) as exc:
        # Conflicts are terminal. I/O/DB failures stay pending for idempotent retry.
        with L.transaction(P.store) as db:
            db.execute("UPDATE learning_decisions SET status='conflict',result=? WHERE id=? AND status='pending'",
                       (L.encoded({"error": str(exc)}), did))
        raise ApiError(409, str(exc)) from exc
    return _decode(P.store.one("SELECT * FROM learning_decisions WHERE id=?", (did,)))


def abandon(P, p, did, actor, expected_token, reason):
    if not signoff.human(actor):
        raise ApiError(403, "放弃发布只允许个人操作者")
    if not isinstance(reason, str) or not reason.strip():
        raise ApiError(400, "需要记录放弃原因")
    p = L.project(P, p)
    with L.transaction(P.store) as db:
        row = db.execute("SELECT * FROM learning_decisions WHERE id=? AND project_id=?", (did, p["id"])).fetchone()
        if not row:
            raise ApiError(404, "人工决定不存在")
        d = _decode(row)
        if d["status"] == "abandoned":
            return d
        if d["kind"] != "fact" or d["status"] not in ("pending", "conflict"):
            raise ApiError(409, "只能放弃未完成的事实发布；已采用的修订需要撤销")
        from . import learning_facts as F
        r = L.revision(P, p, d["revision_id"])
        result = F.abandon(P, p, r, actor, did, expected_token, reason)
        db.execute("UPDATE learning_decisions SET status='abandoned',result=? WHERE id=?", (L.encoded(result), did))
    return _decode(P.store.one("SELECT * FROM learning_decisions WHERE id=?", (did,)))


def runtime_policy(store, project):
    """One exact, still-authorized human-adopted budget; fallback is the old default."""
    P = type("LearningContext", (), {"store": store, "data_dir": store.path.parent})()
    row = store.one("SELECT revision_id FROM learning_policy_active WHERE project_id=?", (project["id"],))
    if not row:
        return {"context_budget": 6000, "revision_id": None, "status": "default"}
    r = L.revision(P, project, row["revision_id"])
    if (str(Path(project['root']).resolve()) != r['source']['binding']['root'] or
            not adopted_current(P, project, r)):
        return {"context_budget": 6000, "revision_id": r["id"], "status": "stale"}
    val = json.loads(L.policy_content(r["content"]))
    return {"context_budget": val["parameters"]["context_budget"], "revision_id": r["id"], "status": "active"}


def filter_fact_pack(store, p, pack):
    """Reconcile rendered page snapshots with exact human publication receipts.

    The pack was collected earlier. Recheck its excerpt under DB -> KB locking,
    so a replaced/revoked page cannot inherit the old revision's use receipt.
    Original bytes stay in the knowledge store; every exclusion has a full-text
    handle and a structured reason in the run's context sidecar.
    """
    from .. import kb, context_pack as cp
    from . import learning_facts as F
    P = type("LearningContext", (), {"store": store, "data_dir": store.path.parent})()
    root = Path(p["root"]).resolve()
    source = next((s for s in pack.get("sources", []) if s.get("current")), {})
    regpath = kb._reg_path(root)
    receipts, kept = [], []
    cache = root / ".tmh" / "cache"
    if cache.is_symlink() or (cache / "kb.lock").is_symlink():
        raise ValueError("知识锁路径不能经过符号链接")
    with store.lock:
        cache.mkdir(exist_ok=True)
        with kb._Lock(cache / "kb.lock"):
            # Both classification and provenance belong to this locked view.
            # Otherwise a removed learning marker could become a legacy bypass.
            raw = json.loads(L.safe_read(root, regpath.relative_to(root).as_posix())) if regpath.exists() else {}
            if source.get("knowledge_revision") != cp._knowledge_revision(root):
                raise ValueError("知识登记在检索之后发生变化，请重新读取")
            if not isinstance(raw, dict):
                raise ValueError("知识登记不可读")
            reg = kb.load_registry(root)
            by_path = {kb.page_path(root, pid).relative_to(root).as_posix(): pid
                       for pid, record in raw.items() if isinstance(record, dict) and "learning" in record}
            for item in pack["items"]:
                pid = by_path.get(item.get("path")) if item.get("section") == "pages" else None
                if pid is None:
                    kept.append(item)
                    continue
                state = raw[pid].get("learning")
                state = state if isinstance(state, dict) else {}
                rid = state.get("active_revision")
                reason, included = "pending_or_changed", False
                fresh = cp._page_item(root, reg, pid, item["score"])
                snapshot_matches = fresh and all(item.get(k) == v for k, v in fresh.items() if k != "id")
                if snapshot_matches and rid:
                    try:
                        r = L.revision(P, p, rid)
                        included = (str(root) == r["source"]["binding"]["root"] and
                                    F.active_revision(P, p, pid) == rid and source_current(P, p, r))
                        reason = "active" if included else "source_or_confirmation_changed"
                    except ApiError:
                        reason = "revision_unavailable"
                elif snapshot_matches and not state.get("pending") and not rid:
                    # A later explicit legacy human confirmation is its own
                    # decision; never claim it used a machine-reviewed revision.
                    history = state.get("manual_confirmations") or []
                    included = bool(history and reg[pid].get("status") == kb.STATUS_OK and
                                    history[-1].get("confirmed_sha256") == state.get("confirmed_sha256"))
                    reason = "manual_confirmation" if included else "not_adopted"
                elif not snapshot_matches:
                    reason = "page_changed_after_retrieval"
                receipts.append({"kind": "fact", "origin_id": pid, "item_id": item["id"],
                                 "revision_id": rid, "included": bool(included), "reason": reason})
                if included:
                    kept.append(item)
                else:
                    pack["omissions"].append(cp._omission(item, "知识采用已失效：" + reason))
                    pack["complete"] = False
            pack["items"] = kept
    return receipts


def usable_lessons(store, p, cards):
    P = type("LearningContext", (), {"store": store, "data_dir": store.path.parent})()
    result, receipts = [], []
    # relevant() selected snapshots earlier. Reconcile them while holding the same
    # ledger view so a revoked managed card cannot fall back to the legacy path.
    with store.lock, learn.ledger_lock(P.data_dir, create=False):
        for card in cards:
            current = learn.lesson(P.data_dir, card["id"])
            rid = current.get("active_revision") if current else None
            usable = bool(current and current["status"] == "active")
            foreign = bool(card.get("foreign"))
            if foreign:
                public = learn.shared_lesson(P.data_dir, p["key"], card["id"]) or {}
                usable = usable and public.get("taken", False) and all(
                    card.get(f) == public.get(f) for f in ("title", *learn.FIELDS, "shared_ts"))
                owner = store.project(current["project"]) if current else None
            else:
                owner = p
                usable = usable and current.get("project") == p["key"] and all(
                    card.get(f, "") == current.get(f, "") for f in L.LESSON_FIELDS)
                usable = usable and card.get("active_revision") == rid
            if usable and rid:
                try:
                    usable = bool(owner and adopted_current(P, owner, L.revision(P, owner, rid)))
                except ApiError:
                    usable = False
            if rid or card.get("active_revision"):
                receipts.append({"kind": "shared_lesson" if foreign else "lesson", "origin_id": card["id"],
                                 "revision_id": rid or card.get("active_revision"), "included": bool(usable),
                                 **({"consumer_project": p["key"], "explicit_take": bool((current or {}).get("taken", {}).get(p["key"])),
                                     "shared_ts": card.get("shared_ts"),
                                     "shared_fingerprint": L.digest({f: card.get(f) for f in ("title", *learn.FIELDS, "shared_ts")}),
                                     "take": (current or {}).get("taken", {}).get(p["key"])} if foreign else {})})
            if usable:
                result.append(card)
    return result, receipts
