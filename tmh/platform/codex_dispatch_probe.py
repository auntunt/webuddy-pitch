"""Explicit internal synthetic dispatch. No public route, model or adoption authority.

Authenticated host code supplies P/actor; a request carries identifiers only.
FS and SQL are separate evidence domains: an interrupted intent is never retried.
"""
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import stat
import sys
import threading
import time

from scripts.rsi.codex_ledger import Ledger, Conflict, Stopped, _encoded
from scripts.rsi import codex_protocol as C
from . import (agent_routes, filelock, learn, learning as L, learning_eval as E,
               learning_decisions as D, lesson_input as I, lesson_context,
               learning_runs, tenant_policy)
from . import project_library

PROTOCOL = "synthetic-probe-input-v1"
BINDING = "codex-dispatch-binding-v1"
DDL = """CREATE TABLE IF NOT EXISTS codex_learning_dispatch (
 root_id TEXT NOT NULL, request_id TEXT NOT NULL, input BLOB NOT NULL,
 binding TEXT NOT NULL, binding_sha256 TEXT NOT NULL, run_id INTEGER NOT NULL UNIQUE,
 launch_claim TEXT NOT NULL DEFAULT '', producer_observation TEXT,
 PRIMARY KEY(root_id,request_id))"""
# Server code only. Tree mode is an internal cleanup fixture, never request data.
WORKER = r'''
import hashlib,json,os,sys,time
raw=sys.stdin.buffer.read()
print(json.dumps({'kind':'synthetic_stdin','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}),flush=True)
if sys.argv[1]=='tree':
    read,write=os.pipe()
    child=os.fork()
    if child==0:
        os.close(read)
        grandchild=os.fork()
        if grandchild==0:
            os.write(write,(str(os.getpid())+'\n').encode());os.close(write)
            while True: time.sleep(3600)
        os.write(write,(str(os.getpid())+'\n').encode());os.close(write)
        while True: time.sleep(3600)
    os.close(write)
    with os.fdopen(read,'rb') as stream: descendants=[int(x) for x in stream.read().splitlines()]
    print(json.dumps({'kind':'synthetic_tree_ready','pids':[os.getpid()]+descendants}),flush=True)
    while True: time.sleep(3600)
'''
_ENTRY_LOCK = threading.Lock()
_ENTRIES = {}


class _OwnerLost(Conflict):
    pass


class _ProbeRunner(learning_runs.IndependentRunner):
    """Retain Runner supervision while forbidding a post-ticket owner reclaim."""
    _first_owner = None

    def _claim(self, rid):
        with self.lock:
            if self._first_owner is None:
                return super()._claim(rid)
            lease = self.owners.get(rid)
            _require(lease is not None and not lease.stream.closed and lease.owner == self._first_owner,
                     "first owner lease lost; reclaim forbidden")
            return lease.owner


def _require(value, message):
    if not value:
        raise Conflict(message)


def _bytes(value):
    return _encoded(value).encode("utf-8")


def _request(value):
    C.fields(value, ("root_id", "request_id", "project_id", "ticket_id",
                     "baseline_revision_id", "candidate_revision_id", "arm"))
    C.sha(value["root_id"])
    for key in ("request_id", "baseline_revision_id", "candidate_revision_id"):
        C.text(value[key])
    C.integer(value["project_id"], 1)
    C.integer(value["ticket_id"], 1)
    _require(value["arm"] in ("baseline", "candidate"), "synthetic arms only; no B/C/D source routing")
    return copy.deepcopy(value)


class Probe:
    """One trusted host controller. Explicit construction alone initializes schema."""
    def __init__(self, P, actor, *, fixture_mode="echo"):
        _require(fixture_mode in ("echo", "tree"), "fixed synthetic fixture required")
        self.P, self.actor, self.mode = P, actor, fixture_mode
        self.store = P.store
        self.ledger = Ledger.for_store(P.store)
        with self.store.lock, self._mixed():
            self.ledger._execute(DDL)
            sql = self.ledger._execute("SELECT sql FROM sqlite_master WHERE name='codex_learning_dispatch'").fetchone()[0]
            _require(sql == DDL.replace(" IF NOT EXISTS", "", 1), "unsupported dispatch schema")
        from .agents import git
        root = Path(__file__).resolve().parents[2]
        self.build = {"commit": git(root, "rev-parse", "HEAD").strip(),
                      "code": {str(p.relative_to(root)): C.digest(p.read_bytes()) for p in (
                          Path(__file__).resolve(), root / "scripts/rsi/codex_ledger.py",
                          root / "tmh/platform/lesson_input.py", root / "tmh/platform/learning_eval.py")}}
        self.runner = _ProbeRunner(self.store, Path(P.data_dir))
        self._stop_lock = threading.Lock()
        self._reason = ""
        self._done = threading.Event()
        self.rid = None
        self._request_value = None

    @contextmanager
    def _mixed(self):
        """Never use Ledger._transaction's commit-on-Stopped for business writes."""
        _require(not self.store.db.in_transaction, "mixed transaction cannot nest")
        try:
            self.ledger._execute("BEGIN IMMEDIATE")
            self.ledger._durability()
            yield
            self.store.db.commit()
        except BaseException:
            self.store.db.rollback()
            raise

    @contextmanager
    def _data(self, req):
        p = self.store.project(req["project_id"])
        _require(p is not None, "unknown project")
        with tenant_policy.experiment_guard(self.P, self.actor, p, "manager") as who:
            tenant_policy.require_execution(self.P, self.actor)
            with self.store.lock:
                try:
                    with self._mixed(), learn.ledger_lock(self.P.data_dir, create=False):
                        path = Path(self.P.data_dir) / "lessons.lock"
                        meta = path.lstat()
                        _require(lesson_context._lease_matches(self.P.data_dir, (meta.st_dev, meta.st_ino)),
                                 "actual named lesson lease required")
                        yield self.store.project(req["project_id"]), who
                except Stopped as error:
                    # The mixed context has fully rolled back. Only these bounded
                    # lifecycle writes may survive, never a new run/input/slot.
                    _require(not self.store.db.in_transaction, "business rollback incomplete")
                    with self.ledger._transaction():
                        row = self.ledger._sync(self.ledger._root(req["root_id"]))
                        reason = str(error)
                        _require(reason in ("cancelled", "expired", "generation_lost", "clock_reversed",
                                            "execution_unknown", "reported_failure"), "unknown stop reason")
                        self.ledger._stop(row, reason)
                    raise

    def _row(self, req):
        row = self.ledger._execute("SELECT * FROM codex_learning_dispatch WHERE root_id=? AND request_id=?",
                                   (req["root_id"], req["request_id"])).fetchone()
        if row is None:
            return None
        row = dict(row)
        _require(C.digest(row["binding"].encode()) == row["binding_sha256"], "dispatch binding changed")
        binding = C.strict(row["binding"])
        attempt = self.ledger._attempt(req["root_id"], req["request_id"])
        _require(C.digest(row["input"]) == attempt["input_sha256"] and binding["run_id"] == row["run_id"], "dispatch input changed")
        run = self.store.run(row["run_id"])
        _require(run and run["project_id"] == req["project_id"] and run["ticket_id"] == req["ticket_id"]
                 and run["prompt"].encode() == row["input"], "run input binding changed")
        row["binding_value"] = binding
        return row

    def _capture(self, req, p, who):
        contract = C.strict(self.ledger._root(req["root_id"])["contract"])
        _require(contract["tenant"] == self.P.tenant_context.tenant_id and contract["project_id"] == p["id"], "root scope changed")
        _require(contract["application_commit"] == self.build["commit"], "host build differs from contract")
        t = self.store.ticket(req["ticket_id"])
        _require(t and t["project_id"] == p["id"], "ticket outside project")
        base, candidate = (L.revision(self.P, p, req[key]) for key in ("baseline_revision_id", "candidate_revision_id"))
        _require(base["kind"] == candidate["kind"] == "lesson" and base["origin_id"] == candidate["origin_id"], "same lesson revision pair required")
        for name, revision in (("baseline", base), ("candidate", candidate)):
            _require(C.digest(revision["content"].encode("utf-8")) == contract[name + "_sha256"], "stored revision UTF-8 hash differs from contract")
            _require(L.digest({"content": revision["content"], "source": revision["source"]}) == revision["fingerprint"], "revision content/source changed")
        _require(L.revision_current(self.P, p, candidate), "candidate source no longer current")
        source = L.binding(self.P, p)
        _require(source["workflow"] == "development" and all(x["available"] for x in source["references"]), "source not executable")
        referenced_material = []
        for ref in project_library.reference_state(self.store, p):
            _, data, allowed = project_library._read_scope(self.store, p, ref["revision_id"])
            names = sorted(set(data["source_manifest"]) | set(data["knowledge_manifest"]))
            referenced_material.append({"reference": ref, "files": [
                project_library.read(self.store, p, ref["revision_id"], name)
                for name in names if project_library._inside(name, allowed)]})
        pool = learn.lesson_selection_pool(self.P.data_dir, p["key"], root=Path(p["root"]))
        pool["binding"]["eligibility"] = E._eligibility(self.P, p, pool)
        runtime_baseline = E._baseline(self.P, p, candidate)
        case = {"id": "synthetic", "generation": False, "input": t["title"] + "\n" + t["body"]}
        pair = E._build_lesson_inputs(pool, candidate["origin_id"], candidate["content"], [case],
                                       candidate["source"]["evidence"])["synthetic"]
        authority = {"actor": self.actor, "tenant": self.P.tenant_context.tenant_id,
                     "account_epoch": who["account_epoch"], "role": who["role"],
                     "project_role": tenant_policy._effective(who, p["key"]),
                     "platform_owner": who["platform_owner"], "execution": who["capabilities"]["execution"]}
        root = self.ledger._root(req["root_id"])
        frozen = {"schema": BINDING, "request": req, "authority": authority, "host_build": self.build,
                  "source": source, "ticket": t, "baseline_revision": base, "candidate_revision": candidate,
                  "referenced_material": referenced_material,
                  "runtime_baseline": runtime_baseline, "pool": pool, "pair": pair,
                  "route": agent_routes.route(self.P.data_dir, p), "protocol": PROTOCOL,
                  "selector": I.SELECTOR_VERSION, "renderer": I.RENDERER_VERSION,
                  "worker_sha256": C.digest(WORKER.encode()), "fixture_mode": self.mode,
                  "window": {k: root[k] for k in ("starts_us", "deadline_us", "owner_generation", "contract_sha256")}}
        raw = _bytes({"schema": PROTOCOL, "scope": "fixed synthetic probe only; no production prompt equivalence",
                      "frozen": frozen, "selected_arm": req["arm"]})
        _require(len(raw) <= 8 * 1024 * 1024, "complete synthetic input exceeds limit; no truncation")
        return frozen, raw

    def _live(self, req):
        row = self.ledger._sync(self.ledger._root(req["root_id"]))
        self.ledger._open(row)
        if self._reason:
            raise Stopped("expired" if self._reason == "timeout" else "cancelled")
        if hasattr(self, "_begin") and self.remaining() <= 0:
            raise Stopped("expired")
        if self.rid is not None:
            _require(self.store.run(self.rid)["status"] != "cancelled", "run cancelled")
        return row

    def prepare(self, request):
        req = _request(request)
        if self.rid is not None:
            _require(req == self._request_value, "one prepared slot per controller")
        if req != self._request_value:
            self._request_value = req
            self._begin = time.monotonic()
            self._entry_wall = time.time()
        with self._data(req) as (p, who):
            root = self.ledger._root(req["root_id"])
            self._initial_remaining = max(0, root["deadline_us"] / 1e6 - self._entry_wall)
            old = self._row(req)
            frozen, raw = self._capture(req, p, who)
            if old:
                _require(old["input"] == raw, "existing request has different authoritative input")
                self.rid = old["run_id"]
                return self._view(old)
            self._live(req)  # lifecycle checks precede every ordinary business write
            self.ledger._reserve_in_tx(req["root_id"], req["request_id"], phase="A", input_sha256=C.digest(raw))
            rid = self.store._create_run_in_tx(p["id"], req["ticket_id"], "synthetic-codex-probe", "ask", self.actor,
                        raw.decode("utf-8"), expected_root=p["root"], reference_inputs=frozen["source"]["references"])
            binding = _encoded({"capture": frozen, "run_id": rid})
            self.ledger._execute("INSERT INTO codex_learning_dispatch(root_id,request_id,input,binding,binding_sha256,run_id) VALUES(?,?,?,?,?,?)",
                (req["root_id"], req["request_id"], raw, binding, C.digest(binding.encode()), rid))
            self._live(req)  # late Stopped rolls back run, inputs, reservation and blob
            self.rid = rid
            return self._view(self._row(req))

    def remaining(self):
        req = self._request_value
        with self.store.lock:
            root = self.ledger._root(req["root_id"])
        return max(0, min(root["deadline_us"] / 1e6 - time.time(),
                          self._initial_remaining - (time.monotonic() - self._begin)))

    @contextmanager
    def _entry(self, req):
        key = C.digest(_bytes([self.P.tenant_context.tenant_id, req["project_id"], req["root_id"], req["request_id"]]))
        with _ENTRY_LOCK:
            mutex = _ENTRIES.setdefault((str(Path(self.P.data_dir).resolve()), key), threading.Lock())
        with mutex:
            folder = Path(self.P.data_dir) / "codex-dispatch-locks"
            folder.mkdir(mode=0o700, exist_ok=True)
            _require(not folder.is_symlink() and folder.stat().st_uid == os.getuid() and not folder.stat().st_mode & 0o077, "private dispatch lock directory required")
            _require(hasattr(os, "O_NOFOLLOW"), "safe named entry lock unavailable")
            path = folder / (key + ".lock")
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "r+b") as stream:
                filelock.try_lock(stream, blocking=True)
                try:
                    opened, named = os.fstat(stream.fileno()), path.lstat()
                    _require(stat.S_ISREG(named.st_mode) and named.st_nlink == 1 and
                             (opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), "entry lock object changed")
                    yield
                finally:
                    filelock.unlock(stream)

    def _view(self, row):
        folder = Path(self.P.data_dir) / "runs" / str(row["run_id"])
        originals = folder.exists() and any(folder.iterdir())
        return {"run_id": row["run_id"], "claimed": bool(row["launch_claim"]),
                "observation": C.strict(row["producer_observation"]) if row["producer_observation"] else None,
                "needs_reconcile": bool((row["launch_claim"] or originals) and not row["producer_observation"]),
                "producer_authenticated": False, "execution_admitted": False, "adoptable": False,
                "actual_codex_exec_count": None, "task_acceptance": None, "actual_cost": None}

    def _stop(self, reason):
        with self._stop_lock:
            if not self._reason:
                self._reason = reason
        if self.rid is not None:
            self.runner._stopped(self.rid, self._reason)  # no Registry/Store locks here

    def _lease(self, owner):
        lease = self.runner.owners.get(self.rid)
        _require(lease is not None and not lease.stream.closed and lease.owner == owner, "first owner lease lost")
        path = Path(self.P.data_dir) / "runs" / str(self.rid)
        _require(C.strict((path / "owner.json").read_text()) == owner, "owner original changed")
        opened, named = os.fstat(lease.stream.fileno()), (path / "owner.lock").stat()
        _require((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), "owner lock changed")

    def _check(self, req, owner=None):
        with self._data(req) as (p, who):
            self._live(req)
            row = self._row(req)
            if owner is not None:
                _require(row["launch_claim"] == _encoded(owner), "durable launch owner changed")
            frozen, raw = self._capture(req, p, who)
            _require(raw == row["input"] and frozen == row["binding_value"]["capture"], "frozen input or authority changed")
        if owner is not None:
            try:
                self._lease(owner)
            except (Conflict, OSError, ValueError) as error:
                raise _OwnerLost(str(error)) from error

    def _watch(self, req, owner):
        while not self._done.wait(.05):
            try:
                self._check(req, owner)
            except BaseException as error:
                self._stop("owner_lost" if isinstance(error, _OwnerLost) else
                           "timeout" if isinstance(error, Stopped) and str(error) == "expired" else "cancelled")
                return

    def launch(self, request):
        req = _request(request)
        _require(req == self._request_value and self.rid is not None, "prepare this request first")
        owner = None
        token = None
        watcher = None
        setup_started = False
        try:
            with self._entry(req):
                # Read latest under the entry protection, never cached empty state.
                with self._data(req):
                    row = self._row(req)
                    folder = Path(self.P.data_dir) / "runs" / str(self.rid)
                    originals = folder.exists() and any(folder.iterdir())
                    if row["launch_claim"] or originals:
                        return self._view(row)
                    self._live(req)
                setup_started = True
                control = self.runner._control(self.rid, {"synthetic": {"run_timeout": max(self.remaining(), .000001)}}, "synthetic")
                owner = control["owner"]
                self.runner._first_owner = owner
                if self._reason:
                    self.runner._stopped(self.rid, self._reason)  # replay an early stop
                with self._data(req) as (p, who):
                    self._live(req)
                    row = self._row(req)
                    frozen, raw = self._capture(req, p, who)
                    _require(raw == row["input"] and frozen == row["binding_value"]["capture"], "T2 authoritative input changed")
                    self._lease(owner)
                    claim = _encoded(owner)
                    attempt = self.ledger._intent_in_tx(req["root_id"], req["request_id"])
                    _require(attempt["new_intent"], "one fresh intent required")
                    token = attempt["intent_token"]
                    changed = self.ledger._execute("UPDATE codex_learning_dispatch SET launch_claim=? WHERE root_id=? AND request_id=? AND launch_claim=''",
                                                  (claim, req["root_id"], req["request_id"])).rowcount
                    _require(changed == 1, "launch already claimed")
                    self._live(req)
            self._check(req, owner)  # no data/entry locks cross into run_command
            watcher = threading.Thread(target=self._watch, args=(req, owner), daemon=True)
            watcher.start()
            result, folder = self.runner.run_command(self.rid, [sys.executable, "-I", "-c", WORKER, self.mode],
                Path(self.P.data_dir), timeout=self.remaining(), env={"PYTHONIOENCODING": "utf-8"},
                stdin=row["input"], kind="fixed-synthetic-probe", prompt=row["input"].decode(), prompt_transport=["stdin"])
            self._done.set()
            watcher.join()
            self.runner.finish_invocation(self.rid, result.returncode, result.output)
            life = learning_runs._sealed_run(self.P, self.rid)
            _require(result.reason == "exited" and result.returncode == 0 and not self._reason, "probe stopped; no successful observation")
            from .supervised_process import read_receipt
            supervised = read_receipt(folder, owner)
            _require(supervised is not None and result.pid is not None and supervised["pid"] == result.pid,
                     "actual target receipt missing")
            lines = [C.strict(line) for line in result.output.splitlines()]
            receipt = lines[0]
            _require(receipt == {"kind": "synthetic_stdin", "bytes": len(row["input"]), "sha256": C.digest(row["input"])}, "actual probe stdin differs")
            observation = {"schema": "live-synthetic-probe-v1", "owner": owner, "run_id": self.rid,
                "stdin_delivery_to_fixed_probe": receipt, "synthetic_probe_starts": 1,
                "processes": {"controller_pid": os.getpid(), "supervisor_pid": supervised["supervisor_pid"],
                              "target_pid": result.pid, "target_pgid": result.pgid},
                "supervised_attempts": len(life["attempts"]), "cleanup": result.cleanup,
                "production_prompt_equivalent": False, "official_client_provenance_verified": False,
                "producer_authenticated": False, "execution_admitted": False, "adoptable": False,
                "actual_codex_exec_count": None, "http_count": None, "task_acceptance": None, "actual_cost": None}
            with self._data(req) as (p, who):
                self._live(req)
                current = self._row(req)
                frozen, raw = self._capture(req, p, who)
                _require(raw == current["input"] and current["launch_claim"] == _encoded(owner), "completion binding changed")
                self.ledger._execute("UPDATE codex_learning_dispatch SET producer_observation=? WHERE root_id=? AND request_id=?",
                                     (_encoded(observation), req["root_id"], req["request_id"]))
                self.ledger._settle_in_tx(req["root_id"], req["request_id"], token,
                    observation_sha256=C.digest(_bytes(observation)), reported_outcome="completed")
                self._live(req)
            return self._view(self._row(req))
        except BaseException as error:
            # Preserve the first runtime/DB/file exception and all original files.
            # A rollback leaves reserved/intent blocking further slots regardless
            # of whether this best-effort stop-only record can commit.
            if token:
                try:
                    self.ledger.unknown(req["root_id"], req["request_id"], token, reason=type(error).__name__ + ": " + str(error))
                except Stopped:
                    pass
                except BaseException as stop_error:
                    error.add_note("stop-only recording failed: " + repr(stop_error))
            raise
        finally:
            if setup_started:
                self._done.set()
            if watcher is not None:
                watcher.join()
            if setup_started:
                self.runner._release(self.rid)

    def run(self, request):
        self.prepare(request)
        return self.launch(request)
