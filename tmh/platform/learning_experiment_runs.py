"""Serial fixed-A synthetic dispatch on the existing process supervisor.

Only server-owned code/cassettes can execute. A committed dispatch intent is
never retried, including after crashes; unknown intent retains its reservation.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import sqlite3
import tempfile
import threading
import time
import uuid
from pathlib import Path

from . import learning as L, learning_eval as E, learning_runs as R
from . import learning_experiments as X, tenant_policy as TP, filelock
from .errors import ApiError
from .store import now

LEASE_SECONDS = 20.0
WATCH_INTERVAL = .1


def _folder(P, eid):
    if not isinstance(eid, str) or len(eid) != 32 or any(c not in "0123456789abcdef" for c in eid):
        raise ApiError(404, "没有这个实验")
    return Path(P.data_dir) / "learning-experiments" / eid


def _owned(db, p, eid, token, fence):
    exp = X._row(db, p, eid)
    if exp["owner"] != token or exp["fence"] != fence:
        raise ApiError(409, "实验所有权已变化，旧工作者不能发布结果")
    return exp


def _budget(db, eid):
    return db.execute("""SELECT COALESCE(SUM(reserved_calls+settled_calls),0) AS used,
                        SUM(CASE WHEN state IN ('reserved','intent') THEN 1 ELSE 0 END) AS active
                        FROM learning_experiment_slots WHERE experiment_id=?""", (eid,)).fetchone()


def _slot_material(exp, assets, slot):
    by_id = {a["id"]: a for a in assets}
    task = next(t for t in exp["contract"]["tasks"] if t["task_asset_id"] == slot["task_asset_id"])
    f = by_id[exp["contract"]["evaluation_asset_id"]]["content"]
    row = f["inputs"][task["case_id"]]
    side = row[slot["arm"]]
    oracle = by_id[task["oracle_asset_id"]]["content"]
    cassette = by_id[task["cassette_asset_id"]]["content"]["outputs"][slot["arm"]]
    prompt = side["prompt"]
    binding = {"schema": X.VERSION, "contract_hash": exp["contract_hash"], "task_asset_id": task["task_asset_id"],
               "arm": slot["arm"], "repeat": slot["repeat"], "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
               "renderer": exp["contract"]["renderer"], "executor": X.digest(exp["contract"]["executor"]),
               "cassette_asset_id": task["cassette_asset_id"], "cassette_sha256": by_id[task["cassette_asset_id"]]["content_hash"]}
    return prompt, oracle, cassette, binding, row["preflight"]["execute_pair"]


def start_sealed(P, p, eid, actor, request_id, launch=True):
    p = L.project(P, p)
    should_launch = False
    with TP.experiment_guard(P, actor, p, "manager"), X.mutation(P.store, decision_key=(eid, actor, request_id)) as db:
        exp = X._row(db, p, eid)
        X.current_authority(P, p, exp, actor, manager=True, execution=True)
        replay, h = X._replay(db, exp, actor, request_id, "start", {})
        if replay:
            receipt = X._receipt(exp, True, action="start", request_id=request_id)
            should_launch = exp["state"] == "running"
        else:
            if exp["state"] != "sealed" or not exp["job_id"]:
                raise ApiError(409, "只有已封存且未启动的固定实验可以启动")
            if X.remaining_in_tx(db, exp) <= 0:
                raise ApiError(409, "原实验期限已到；不能重建预算起点")
            X.material_current(P, p, exp)
            principals = dict(exp["principals"])
            principals[actor] = TP.experiment_identity(P, actor, p, "manager")["account_epoch"]
            db.execute("UPDATE learning_experiments SET state='running',started=?,principals=? WHERE id=?", (now(), X.encoded(principals), eid))
            db.execute("UPDATE learning_jobs SET actor=? WHERE id=?", (actor, exp["job_id"]))
            X._event(db, eid, "start", actor, {"deadline": exp["deadline"], "contract_hash": exp["contract_hash"]}, request_id, h)
            receipt = X._receipt(X._row(db, p, eid), action="start", request_id=request_id)
            should_launch = True
    if launch and should_launch:
        context = contextvars.copy_context()
        threading.Thread(target=lambda: context.run(work, P, p, eid), name="experiment-" + eid[:8], daemon=True).start()
    return receipt


class _Worker:
    def __init__(self, P, p, eid, actor, token, fence, deadline, remaining):
        self.P, self.p, self.eid, self.actor = P, p, eid, actor
        self.token, self.fence, self.deadline = token, fence, deadline
        self.start_mono = time.monotonic()
        self.initial_remaining = max(0.0, remaining)
        self.runner = R.IndependentRunner(P.store, P.data_dir)
        self.rid = None
        self.stop = threading.Event()
        self.stop_reason = ""

    def remaining(self):
        return max(0.0, min(self.deadline - time.time(), self.initial_remaining - (time.monotonic() - self.start_mono)))

    def _current(self, db, *, allow_stopping=False):
        exp = _owned(db, self.p, self.eid, self.token, self.fence)
        X.current_authority(self.P, self.p, exp, self.actor, manager=True, execution=True)
        if not allow_stopping:
            if exp["state"] != "running" or exp["cancel_requested"]:
                raise R._Stopped("cancelled", "实验已请求停止")
            if self.remaining() <= 0:
                raise R._Stopped("timed_out", "实验原始总期限已到")
            if exp["lease_until"] <= time.time():
                raise R._Stopped("unknown", "实验工作者租约已过期")
        return exp

    def watch(self):
        while not self.stop.wait(WATCH_INTERVAL):
            reason = ""
            try:
                with TP.experiment_guard(self.P, self.actor, self.p, "manager"), L.transaction(self.P.store) as db:
                    exp = self._current(db, allow_stopping=True)
                    if exp["cancel_requested"] or exp["state"] != "running":
                        reason = "cancelled"
                    elif self.remaining() <= 0:
                        reason = "timed_out"
                    else:
                        db.execute("UPDATE learning_experiments SET lease_until=? WHERE id=? AND owner=? AND fence=?",
                                   (time.time() + LEASE_SECONDS, self.eid, self.token, self.fence))
                        db.execute("UPDATE learning_jobs SET lease_until=? WHERE id=? AND owner=?",
                                   (time.time() + LEASE_SECONDS, exp["job_id"], self.token))
            except Exception:
                reason = "stale"
            if reason:
                self.stop_reason = reason
                rid = self.rid
                if rid is not None:
                    self.runner._stopped(rid, "timeout" if reason == "timed_out" else "cancelled")
                return

    def register_step(self, slot_id):
        """T2: registration, frozen input, classification and budget share commit."""
        with TP.experiment_guard(self.P, self.actor, self.p, "manager"), L.transaction(self.P.store) as db:
            exp = self._current(db)
            assets = X.assets_in_tx(db, self.eid)
            X.material_current(self.P, self.p, exp, assets)
            slot = db.execute("SELECT * FROM learning_experiment_slots WHERE experiment_id=? AND id=?", (self.eid, slot_id)).fetchone()
            if not slot or slot["state"] != "planned":
                raise ApiError(409, "槽已登记或不属于此实验，不能重复调用")
            first = db.execute("SELECT id FROM learning_experiment_slots WHERE experiment_id=? AND state='planned' ORDER BY ordinal LIMIT 1", (self.eid,)).fetchone()
            if not first or first["id"] != slot_id:
                raise ApiError(409, "必须按预登记顺序执行")
            budget = _budget(db, self.eid)
            if budget["used"] >= exp["contract"]["max_calls"] or budget["active"]:
                raise ApiError(409, "实验调用预算或并发额度已占用")
            prompt, oracle, cassette, binding, execute = _slot_material(exp, assets, slot)
            if not execute:
                X._unexecuted(db, self.eid, "input_limit")
                X._event(db, self.eid, "input_limit", self.actor, {"slot_id": slot_id})
                return None
            rid = self.P.store._create_run_in_tx(self.p["id"], None, X.EXECUTOR_ID, "ask", self.actor, prompt,
                    target=slot["step_role"], batch="experiment:" + self.eid + ":" + slot_id,
                    model="synthetic-no-paid-model", expected_root=self.p["root"], reference_inputs=exp["contract"]["source_binding"]["references"])
            db.execute("""INSERT INTO learning_steps(job_id,seq,role,prompt,prompt_hash,status,run_id,created)
                         VALUES(?,?,?,?,?,'reserved',?,?)""",
                       (exp["job_id"], slot["ordinal"], slot["step_role"], prompt, binding["prompt_sha256"], rid, now()))
            db.execute("UPDATE learning_jobs SET calls=calls+1 WHERE id=?", (exp["job_id"],))
            db.execute("""UPDATE learning_experiment_slots SET state='reserved',run_id=?,owner=?,fence=?,prompt_hash=?,input_binding=?,reserved_calls=1
                          WHERE experiment_id=? AND id=? AND state='planned'""",
                       (rid, self.token, self.fence, binding["prompt_sha256"], X.encoded(binding), self.eid, slot_id))
            X._event(db, self.eid, "reserve_bind", self.actor, {"slot_id": slot_id, "run_id": rid, "calls": 1})
            # Source validation itself can consume remaining time. Check again
            # before committing, so a late validation cannot register a new run.
            self._current(db)
            return {"slot": dict(slot, run_id=rid), "prompt": prompt, "oracle": oracle, "cassette": cassette, "binding": binding,
                    "executor": exp["contract"]["executor"]}

    def intent(self, material):
        slot = material["slot"]
        with TP.experiment_guard(self.P, self.actor, self.p, "manager"), L.transaction(self.P.store) as db:
            exp = self._current(db)
            assets = X.assets_in_tx(db, self.eid)
            X.material_current(self.P, self.p, exp, assets)
            current = db.execute("SELECT * FROM learning_experiment_slots WHERE experiment_id=? AND id=?", (self.eid, slot["id"])).fetchone()
            if (not current or current["state"] != "reserved" or current["run_id"] != slot["run_id"]
                    or current["owner"] != self.token or current["fence"] != self.fence or current["dispatch_id"]):
                raise ApiError(409, "槽已经派发或所有权已变化")
            _, _, _, binding, execute = _slot_material(exp, assets, current)
            if not execute or binding != material["binding"] or json.loads(current["input_binding"]) != binding:
                raise ApiError(409, "派发前完整输入发生变化")
            self._current(db)
            dispatch = uuid.uuid4().hex
            db.execute("UPDATE learning_experiment_slots SET state='intent',dispatch_id=? WHERE experiment_id=? AND id=?", (dispatch, self.eid, slot["id"]))
            db.execute("UPDATE learning_steps SET status='running' WHERE job_id=? AND role=?", (slot["job_id"], slot["step_role"]))
            db.execute("UPDATE runs SET status='running',started=? WHERE id=?", (now(), slot["run_id"]))
            X._event(db, self.eid, "dispatch_intent", self.actor, {"slot_id": slot["id"], "run_id": slot["run_id"], "dispatch_id": dispatch,
                                                                  "input_binding": binding})
        return dispatch

    def settle(self, material, life, output, raw):
        slot = material["slot"]
        with TP.experiment_guard(self.P, self.actor, self.p, "manager"), L.transaction(self.P.store) as db:
            exp = self._current(db, allow_stopping=True)
            # The last invocation has no later registration to detect a changed
            # source. Recheck the sealed material before publishing its result.
            X.material_current(self.P, self.p, exp)
            current = db.execute("SELECT * FROM learning_experiment_slots WHERE experiment_id=? AND id=?", (self.eid, slot["id"])).fetchone()
            if (not current or current["state"] != "intent" or current["owner"] != self.token
                    or current["fence"] != self.fence or current["run_id"] != slot["run_id"]):
                raise ApiError(409, "不能重复结算或由旧所有者发布")
            owner = X.run_owner(db, slot["run_id"])
            if owner is None or owner["experiment_id"] != self.eid:
                raise ApiError(409, "结算过程归属不可核验")
            run = db.execute("SELECT * FROM runs WHERE id=?", (slot["run_id"],)).fetchone()
            attempt = life["attempts"][0]
            if (attempt.get("prompt_sha256") != material["binding"]["prompt_sha256"]
                    or life.get("finished") is not True or attempt["cleanup"].get("complete") is not True
                    or run["status"] in ("queued", "running")):
                raise ApiError(409, "真实停止回执或完整输入不能核验")
            clean_success = run["status"] == "done" and run["exit_code"] == 0 and not life["stopped_reason"]
            passed = clean_success and E.check(material["oracle"], output)
            result = {"passed": passed, "executed": True, "output": output, "raw_output": raw,
                      "output_sha256": X.digest(output), "input_binding": material["binding"],
                      "stopped_reason": life["stopped_reason"], "exit_code": run["exit_code"],
                      "rsi_qualified": False, "synthetic": True, "finished_in_deadline": self.remaining() > 0}
            db.execute("""UPDATE learning_experiment_slots SET state=?,reserved_calls=0,settled_calls=1,synthetic_units=1,
                         result=?,cleanup=?,ended=? WHERE experiment_id=? AND id=?""",
                       ("completed" if clean_success else "failed", X.encoded(result), X.encoded(life), now(), self.eid, slot["id"]))
            db.execute("""UPDATE learning_steps SET status=?,output=?,raw_output=?,exit_code=?,ended=?,elapsed_seconds=?,usage=?
                         WHERE job_id=? AND role=?""",
                       ("completed" if clean_success else "failed", output, raw, run["exit_code"], now(), life["elapsed_seconds"],
                        X.encoded({"status": "unavailable", "synthetic_units": 1}), slot["job_id"], slot["step_role"]))
            X._event(db, self.eid, "settle", self.actor, {"slot_id": slot["id"], "run_id": slot["run_id"], "result_sha256": X.digest(result)})
            return passed

    def run_slot(self, material):
        rid = material["slot"]["run_id"]
        self.rid = rid
        # After intent, cancellation means in-flight/unknown until the existing
        # supervisor confirms cleanup. Never claim no PID can appear here.
        code, output = 1, ""
        try:
            self.intent(material)
            remaining = self.remaining()
            if self.stop_reason or remaining <= 0:
                raise R._Stopped(self.stop_reason or "timed_out", "派发意图后停止；未假定没有副作用")
            conf = {X.EXECUTOR_ID: {"run_timeout": remaining}}
            self.runner._control(rid, conf, X.EXECUTOR_ID)
            # watch may have latched a stop before _control existed. Replaying
            # it after creation closes that window; later stops reach control.
            if self.stop_reason:
                self.runner._stopped(rid, "timeout" if self.stop_reason == "timed_out" else "cancelled")
            with tempfile.TemporaryDirectory(prefix="tmh-experiment-") as workdir:
                with TP.experiment_guard(self.P, self.actor, self.p, "manager"), L.transaction(self.P.store) as db:
                    self._current(db)
                    db.execute("UPDATE runs SET workdir=? WHERE id=?", (workdir, rid))
                packet = {"prompt": material["prompt"], "prompt_sha256": material["binding"]["prompt_sha256"], "output": material["cassette"]}
                process, _ = self.runner.run_command(rid, [material["executor"]["python"], "-c", material["executor"]["code"]],
                        workdir, timeout=remaining, stdin=X.encoded(packet), kind="synthetic-fixed-a",
                        prompt=material["prompt"], prompt_transport=["stdin_json.prompt"])
                code, output = process.returncode, process.output
                self.runner.finish_invocation(rid, code, output)
            life = R._sealed_run(self.P, rid)
            return self.settle(material, life, output, R._raw_output(self.P, rid))
        except BaseException:
            run = self.P.store.run(rid)
            if run and run["status"] in ("queued", "running"):
                try:
                    self.runner.finish_invocation(rid, code, output)
                except Exception:
                    pass
            raise
        finally:
            self.rid = None

    def run(self):
        while True:
            with TP.experiment_guard(self.P, self.actor, self.p, "manager"), L.transaction(self.P.store) as db:
                exp = self._current(db)
                slot = db.execute("SELECT * FROM learning_experiment_slots WHERE experiment_id=? AND state='planned' ORDER BY ordinal LIMIT 1", (self.eid,)).fetchone()
                if not slot:
                    X.material_current(self.P, self.p, exp)
                    # Validation can outlive the remaining budget while the
                    # watcher waits on this writer; recheck before publishing.
                    exp = self._current(db)
                    X.finalize_in_tx(db, exp)
                    return
                sid = slot["id"]
            material = self.register_step(sid)
            if material is None:
                break
            if not self.run_slot(material):
                break
        with TP.experiment_guard(self.P, self.actor, self.p, "manager"), L.transaction(self.P.store) as db:
            exp = self._current(db, allow_stopping=True)
            X.material_current(self.P, self.p, exp)
            X._unexecuted(db, self.eid, "fixed_stop_rule")
            X.finalize_in_tx(db, exp, reason=self.stop_reason or ("timed_out" if self.remaining() <= 0 else ""))


def _recover_registered(P, p, eid, token, fence, previous_owner=None, *, wait_seconds=3):
    """Recover only fenced, registered intents; no authority to start work."""
    with P.tenant_context.registry.authorization_guard(), P.store.lock:
        exp = X._row(P.store.db, p, eid)
        if (exp["owner"], exp["fence"]) != (token, fence):
            return
        run_ids = []
        for slot in P.store.db.execute("SELECT * FROM learning_experiment_slots WHERE experiment_id=? AND state='intent'", (eid,)):
            if (slot["owner"], slot["fence"]) not in ((token, fence), previous_owner):
                raise ApiError(409, "恢复不得停止另一代工作者的过程")
            owner = X.run_owner(P.store.db, slot["run_id"])
            if not owner or owner["experiment_id"] != eid:
                raise ApiError(409, "恢复过程归属不可核验")
            run_ids.append(slot["run_id"])
    # Existing per-run kernel leases and owner proofs decide whether recovery
    # is safe; there is no kill of a historical PID inferred from the database.
    for rid in run_ids:
        try:
            from .crash_recovery import reconcile
            reconcile(P.store, P.data_dir, rid, wait_seconds=wait_seconds)
        except (OSError, ValueError, KeyError):
            pass  # the following report must retain unknown cleanup evidence


def _safety_finalize(P, p, eid, token, fence, reason, previous_owner=None):
    """Authorization-lock first, fenced stop-only bookkeeping after revocation.

    Complete saved output is retained, but this path cannot publish passed or
    create execution. Missing stop evidence retains the intent's reservation.
    """
    proof = {}
    for slot in P.store.q("SELECT * FROM learning_experiment_slots WHERE experiment_id=? AND state IN ('intent','reserved')", (eid,)):
        if slot["run_id"] is None:
            continue
        raw = R._raw_output(P, slot["run_id"])
        run = P.store.run(slot["run_id"])
        try:
            life = R._sealed_run(P, slot["run_id"])
        except (OSError, ValueError, KeyError):
            life = None
        proof[slot["id"]] = {"life": life, "raw": raw, "run": run}
    with P.tenant_context.registry.authorization_guard(), L.transaction(P.store) as db:
        exp = X._row(db, p, eid)
        if exp["owner"] != token or exp["fence"] != fence:
            return
        for slot in db.execute("SELECT * FROM learning_experiment_slots WHERE experiment_id=? AND state IN ('intent','reserved')", (eid,)).fetchall():
            if (slot["owner"], slot["fence"]) not in ((token, fence), previous_owner):
                raise ApiError(409, "安全停止不能接管不属于此代所有者的槽")
            ownership = X.run_owner(db, slot["run_id"])
            if not ownership or ownership["experiment_id"] != eid:
                raise ApiError(409, "安全停止的过程归属矛盾")
            saved = proof.get(slot["id"], {})
            life, run = saved.get("life"), saved.get("run")
            stopped = bool(life and run and life["attempts"][0].get("prompt_sha256") == slot["prompt_hash"]
                           and run["status"] not in ("queued", "running"))
            no_intent = slot["state"] == "reserved"
            state = "not_executed" if no_intent else "failed" if stopped else "unknown"
            result = {"reason": reason, "executed": False if no_intent else True if stopped else None,
                      "passed": False, "rsi_qualified": False,
                      "output": (run or {}).get("result", ""), "raw_output": saved.get("raw", ""),
                      "cleanup_status": "not_started" if no_intent else "confirmed" if stopped else "not_proven"}
            db.execute("UPDATE learning_experiment_slots SET state=?,reserved_calls=?,settled_calls=?,synthetic_units=?,result=?,cleanup=?,ended=? WHERE experiment_id=? AND id=?",
                       (state, 0 if no_intent or stopped else 1, 1 if stopped else 0, 1 if stopped else 0,
                        X.encoded(result), X.encoded(life or {}), now(), eid, slot["id"]))
            db.execute("UPDATE learning_steps SET status='failed',error=?,output=?,raw_output=?,ended=? WHERE job_id=? AND role=?",
                       (reason, result["output"], result["raw_output"], now(), slot["job_id"], slot["step_role"]))
            if no_intent:
                db.execute("UPDATE runs SET status='failed',exit_code=125,result=?,ended=? WHERE id=? AND status='queued'", (reason, now(), slot["run_id"]))
            X._event(db, eid, "safety_stop", "system:experiment-supervisor", {"initiated_by": exp["creator"], "slot_id": slot["id"], "run_id": slot["run_id"], "reason": reason, "cleanup_status": result["cleanup_status"]})
        X._unexecuted(db, eid, reason)
        X.finalize_in_tx(db, exp, reason=reason)


def work(P, p, eid):
    """Internal dispatcher; a DB owner/fence and OS lease exclude all rivals."""
    p = L.project(P, p)
    exp = X.get_internal(P, p, eid)
    if exp["state"] in X.TERMINAL or exp["state"] not in ("running", "cancelling"):
        return
    job = P.store.one("SELECT actor FROM learning_jobs WHERE id=?", (exp["job_id"],))
    actor = job["actor"]
    folder = _folder(P, eid)
    folder.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    worker, watcher, fence = None, None, None
    with (folder / "owner.lock").open("a+b") as stream:
        try:
            filelock.try_lock(stream)
        except BlockingIOError:
            return
        try:
            # Inspect interrupted work under the kernel lease before changing
            # generation. A new owner cannot inherit an old intent through an
            # in-memory tuple: another crash would lose that relationship.
            with P.tenant_context.registry.authorization_guard(), P.store.lock:
                exp = X._row(P.store.db, p, eid)
                if exp["state"] not in ("running", "cancelling"):
                    return
                interrupted = P.store.db.execute(
                    "SELECT 1 FROM learning_experiment_slots WHERE experiment_id=? AND state IN ('intent','reserved')", (eid,)).fetchone()
                interrupted_reason = "interrupted_intent_or_reservation"
                if interrupted:
                    try:
                        X.remaining_in_tx(P.store.db, exp)
                    except ApiError as exc:
                        interrupted_reason = "restart_deadline_unproven" if "时钟锚" in str(exc) else "stale"
            if interrupted:
                # This stop-only branch intentionally needs no still-authorized
                # human. The original durable owner/fence remain retryable if
                # reconciliation or bookkeeping is interrupted again.
                _recover_registered(P, p, eid, exp["owner"], exp["fence"])
                _safety_finalize(P, p, eid, exp["owner"], exp["fence"], interrupted_reason)
                return
            try:
                with TP.experiment_guard(P, actor, p, "manager"), L.transaction(P.store) as db:
                    exp = X._row(db, p, eid)
                    X.current_authority(P, p, exp, actor, manager=True, execution=True)
                    if exp["state"] not in ("running", "cancelling"):
                        return
                    next_fence = exp["fence"] + 1
                    db.execute("UPDATE learning_experiments SET owner=?,fence=?,lease_until=? WHERE id=?",
                               (token, next_fence, time.time() + LEASE_SECONDS, eid))
                    db.execute("UPDATE learning_jobs SET status='running',owner=?,lease_until=?,started=CASE WHEN started='' THEN ? ELSE started END WHERE id=?",
                               (token, time.time() + LEASE_SECONDS, now(), exp["job_id"]))
                    initial_remaining = X.remaining_in_tx(db, exp)
                fence = next_fence  # only a committed generation may settle
                worker = _Worker(P, p, eid, actor, token, fence, exp["deadline"], initial_remaining)
                context = contextvars.copy_context()
                watcher = threading.Thread(target=lambda: context.run(worker.watch), name="experiment-watch-" + eid[:8], daemon=True)
                watcher.start()
                worker.run()
            except BaseException as exc:
                if fence is not None:
                    reason = getattr(exc, "status", None) or (worker.stop_reason if worker else "") or "stale"
                    _recover_registered(P, p, eid, token, fence)
                    _safety_finalize(P, p, eid, token, fence, reason)
                else:
                    # Claim failed before commit; only the prior durable owner
                    # may be reconciled, including revoked or expired work.
                    _recover_registered(P, p, eid, exp["owner"], exp["fence"])
                    _safety_finalize(P, p, eid, exp["owner"], exp["fence"], "restart_deadline_unproven" if "时钟锚" in str(exc) else "stale")
        finally:
            if worker:
                worker.stop.set()
            if watcher:
                watcher.join(2)
            filelock.unlock(stream)


def recovery_candidates(P):
    """Read-only startup snapshot, taken before the worker accepts requests."""
    context = getattr(P, "tenant_context", None)
    if context is None:
        return []
    with P.store.lock:
        if X.schema_state(P.store) == "absent":
            return []
        return [r["id"] for r in P.store.db.execute(
            "SELECT id FROM learning_experiments WHERE tenant_id=? AND state IN ('running','cancelling') ORDER BY created,id",
            (str(context.tenant_id),))]


def _recover_one(P, eid):
    """Stop one exact saved generation; callers isolate expected record faults."""
    folder = _folder(P, eid)
    with P.store.lock:
        row = P.store.db.execute("SELECT project_id FROM learning_experiments WHERE id=?", (eid,)).fetchone()
        p = P.store.project(row["project_id"]) if row else None
    if not p:
        return "skipped"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "owner.lock").open("a+b") as stream:
        try:
            filelock.try_lock(stream)
        except BlockingIOError:
            return "skipped"  # a live generation remains responsible
        try:
            with P.tenant_context.registry.authorization_guard(), P.store.lock:
                exp = X._row(P.store.db, p, eid)
                if exp["tenant_id"] != str(P.tenant_context.tenant_id):
                    raise ApiError(409, "恢复实验不属于此租户")
                if exp["state"] not in ("running", "cancelling"):
                    return "skipped"
                token, fence = exp["owner"], exp["fence"]
            _recover_registered(P, p, eid, token, fence, wait_seconds=0)
            _safety_finalize(P, p, eid, token, fence, "stale")
            return "processed"
        finally:
            filelock.unlock(stream)


def recover(P, experiment_ids=None, stop_event=None):
    """Stop-only recovery with safe per-record diagnostics, never dispatch.

    The pre-readiness snapshot excludes newly submitted work. Expected damaged
    records do not strand later independent experiments. No error message or
    task material enters this report. ``processed`` means bookkeeping finished,
    not that cleanup was proven: its durable report can still be unknown.
    """
    ids = recovery_candidates(P) if experiment_ids is None else list(experiment_ids)
    report = {"processed": [], "failed": [], "skipped": [], "stopped": False}
    for eid in ids:
        if stop_event is not None and stop_event.is_set():
            report["stopped"] = True
            break
        try:
            outcome = _recover_one(P, eid)
        except (ApiError, ValueError, KeyError, TypeError) as exc:
            code = "experiment_recovery_invalid"
        except OSError as exc:
            code = "experiment_recovery_io"
        except sqlite3.DatabaseError as exc:
            code = "experiment_recovery_storage"
        else:
            report[outcome].append(eid)
            continue
        # Even a damaged identifier must not echo arbitrary stored text into
        # logs. Successful identifiers were already checked by _folder.
        safe_id = eid if isinstance(eid, str) and len(eid) == 32 and all(c in "0123456789abcdef" for c in eid) else None
        report["failed"].append({"experiment_id": safe_id, "code": code})
    return report
