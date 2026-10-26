"""Single-database, non-executing Codex bookkeeping; no adoption authority.

Only explicit construction initializes this independent namespace. Generations
are caller ownership labels, not authenticated process identity. Settlements
are recorded claims, not trusted execution or task-acceptance evidence.
"""
from contextlib import contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from . import codex_protocol as C

DDL = (
    "CREATE TABLE IF NOT EXISTS codex_learning_roots(root_id TEXT PRIMARY KEY,contract TEXT NOT NULL,contract_sha256 TEXT NOT NULL,starts_us INTEGER NOT NULL,deadline_us INTEGER NOT NULL,owner_generation TEXT NOT NULL,last_wall_us INTEGER NOT NULL,last_us INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('open','cancelled','expired','generation_lost','clock_reversed','execution_unknown','reported_failure')))",
    "CREATE TABLE IF NOT EXISTS codex_learning_attempts(root_id TEXT NOT NULL REFERENCES codex_learning_roots(root_id),request_id TEXT NOT NULL,phase TEXT NOT NULL,input_sha256 TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('reserved','intent','settled','unknown','cancelled')),intent_token TEXT NOT NULL DEFAULT '',settlement TEXT,PRIMARY KEY(root_id,request_id))",
    "CREATE TABLE IF NOT EXISTS codex_learning_events(id INTEGER PRIMARY KEY,root_id TEXT NOT NULL REFERENCES codex_learning_roots(root_id),request_id TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,payload_sha256 TEXT NOT NULL)",
)
_PROCESS = (os.getpid(), uuid.uuid4().hex)


class Conflict(ValueError):
    pass


class Stopped(Conflict):
    """A durable lifecycle stop, committed even though the operation is denied."""


def _require(condition, message):
    if not condition:
        raise Conflict(message)


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _generation():
    global _PROCESS
    if _PROCESS[0] != os.getpid():
        _PROCESS = (os.getpid(), uuid.uuid4().hex)
    return _PROCESS[1]


class Ledger:
    def __init__(self, path, *, generation=None, wall_us=None, monotonic=None):
        self.generation = _generation() if generation is None else generation
        C.text(self.generation)
        self.wall = wall_us or (lambda: time.time_ns() // 1000)
        self.mono = monotonic or time.monotonic
        self.base_wall, self.base_mono = self.wall(), self.mono()
        self.db = sqlite3.connect(str(Path(path).resolve()), isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        try:
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA synchronous=FULL")
            with self._transaction():
                for statement in DDL:
                    self.db.execute(statement)
                for statement in DDL:
                    name = statement.split()[5].split("(")[0]
                    actual = self.db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
                    _require(actual and actual[0] == statement.replace(" IF NOT EXISTS", "", 1), "unsupported Codex ledger schema")
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @contextmanager
    def _transaction(self, *, readonly=False):
        _require(not self.db.in_transaction, "nested ledger transaction refused")
        self.db.execute("BEGIN" if readonly else "BEGIN IMMEDIATE")
        try:
            if not readonly:
                sync = self.db.execute("PRAGMA synchronous").fetchone()[0]
                journal = self.db.execute("PRAGMA journal_mode").fetchone()[0]
                _require(sync in (2, 3) and journal in ("delete", "truncate", "persist", "wal"),
                         "durable SQLite synchronization and journal required")
            yield
        except Stopped:
            self.db.commit()  # Preserve only the fully recorded lifecycle stop.
            raise
        except BaseException:
            self.db.rollback()
            raise
        else:
            try:
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def _event(self, root, request, kind, payload):
        raw = _encoded(payload)
        self.db.execute("INSERT INTO codex_learning_events(root_id,request_id,kind,payload,payload_sha256) VALUES(?,?,?,?,?)",
                        (root, request, kind, raw, C.digest(raw.encode())))

    def _root(self, root):
        C.sha(root)
        row = self.db.execute("SELECT * FROM codex_learning_roots WHERE root_id=?", (root,)).fetchone()
        _require(row is not None, "unknown root")
        value = dict(row)
        C.validate_contract(C.strict(value["contract"]))
        _require(C.digest(value["contract"].encode()) == value["contract_sha256"], "contract binding changed")
        anchor = self.db.execute("SELECT payload,payload_sha256 FROM codex_learning_events WHERE root_id=? AND kind='registered'", (root,)).fetchall()
        expected = {k: value[k] for k in ("root_id", "contract", "contract_sha256", "starts_us", "deadline_us", "owner_generation")}
        _require(len(anchor) == 1 and anchor[0]["payload"] == _encoded(expected) and
                 anchor[0]["payload_sha256"] == C.digest(anchor[0]["payload"].encode()), "original registration changed")
        return value

    def _attempt(self, root, request):
        C.text(request)
        row = self.db.execute("SELECT * FROM codex_learning_attempts WHERE root_id=? AND request_id=?", (root, request)).fetchone()
        _require(row is not None, "unknown reservation")
        return dict(row, producer_authenticated=False, execution_admitted=False, adoptable=False,
                    actual_outer_exec_count=None, task_acceptance=None)

    def _stop(self, row, reason):
        if row["status"] != "open":
            return row
        root = row["root_id"]
        self.db.execute("UPDATE codex_learning_roots SET status=? WHERE root_id=?", (reason, root))
        self.db.execute("UPDATE codex_learning_attempts SET state=CASE state WHEN 'intent' THEN 'unknown' ELSE 'cancelled' END WHERE root_id=? AND state IN ('reserved','intent')", (root,))
        self._event(root, "", "stopped", {"reason": reason})
        return dict(row, status=reason)

    def _sync(self, row):
        if row["status"] != "open":
            return row
        wall, mono = self.wall(), self.mono()
        C.integer(wall)
        if wall < row["last_wall_us"] or mono < self.base_mono:
            return self._stop(row, "clock_reversed")
        if self.generation != row["owner_generation"]:
            return self._stop(row, "generation_lost")
        now = max(wall, self.base_wall + int((mono - self.base_mono) * 1000000), row["last_us"])
        self.db.execute("UPDATE codex_learning_roots SET last_wall_us=?,last_us=? WHERE root_id=?", (wall, now, row["root_id"]))
        row = dict(row, last_wall_us=wall, last_us=now)
        if now >= row["deadline_us"]:
            return self._stop(row, "expired")
        if self.db.execute("SELECT 1 FROM codex_learning_attempts WHERE root_id=? AND state='unknown'", (row["root_id"],)).fetchone():
            return self._stop(row, "execution_unknown")
        return row

    def _open(self, row):
        if row["status"] != "open":
            raise Stopped(row["status"])
        _require(row["last_us"] >= row["starts_us"], "fixed window has not started")

    def register(self, contract, *, starts_us, deadline_us):
        contract = C.strict(_encoded(contract))
        C.validate_contract(contract)
        C.integer(starts_us)
        C.integer(deadline_us)
        _require(deadline_us <= 2**63 - 1 and starts_us < deadline_us and
                 deadline_us - starts_us <= int(Decimal(str(contract["limits"]["total_timeout_seconds"])) * 1000000), "fixed finite window required")
        raw = _encoded(contract)
        with self._transaction():
            root = contract["root_id"]
            old = self.db.execute("SELECT 1 FROM codex_learning_roots WHERE root_id=?", (root,)).fetchone()
            if old:
                row = self._root(root)
                _require(row["contract"] == raw and row["starts_us"] == starts_us and row["deadline_us"] == deadline_us, "root cannot replace contract or refresh window")
            else:
                wall = self.wall()
                C.integer(wall)
                self.db.execute("INSERT INTO codex_learning_roots VALUES(?,?,?,?,?,?,?,?,?)",
                                (root, raw, C.digest(raw.encode()), starts_us, deadline_us, self.generation, wall, wall, "open"))
                row = dict(self.db.execute("SELECT * FROM codex_learning_roots WHERE root_id=?", (root,)).fetchone())
                self._event(root, "", "registered", {k: row[k] for k in ("root_id", "contract", "contract_sha256", "starts_us", "deadline_us", "owner_generation")})
            self._sync(row)
        return self.snapshot(root)

    def reserve(self, root, request, *, phase, input_sha256):
        C.text(request)
        C.sha(input_sha256)
        _require(phase in ("A", "B", "C", "D"), "unknown phase")
        with self._transaction():
            row = self._sync(self._root(root))
            self._open(row)
            old = self.db.execute("SELECT * FROM codex_learning_attempts WHERE root_id=? AND request_id=?", (root, request)).fetchone()
            if old:
                _require(old["phase"] == phase and old["input_sha256"] == input_sha256, "request binds another input")
            else:
                total = self.db.execute("SELECT COUNT(*) FROM codex_learning_attempts WHERE root_id=?", (root,)).fetchone()[0]
                limit = C.strict(row["contract"])["limits"]["max_outer_starts"]
                _require(total < limit, "cumulative outer reservation limit reached")
                active = self.db.execute("SELECT 1 FROM codex_learning_attempts WHERE root_id=? AND state IN ('reserved','intent','unknown')", (root,)).fetchone()
                _require(not active, "serial or unresolved attempt exists")
                self.db.execute("INSERT INTO codex_learning_attempts(root_id,request_id,phase,input_sha256,state) VALUES(?,?,?,?,'reserved')", (root, request, phase, input_sha256))
                self._event(root, request, "reserved", {"phase": phase, "input_sha256": input_sha256})
            return self._attempt(root, request)

    def intent(self, root, request):
        with self._transaction():
            row = self._sync(self._root(root))
            self._open(row)
            attempt = self._attempt(root, request)
            fresh = attempt["state"] == "reserved"
            if fresh:
                token = uuid.uuid4().hex
                self.db.execute("UPDATE codex_learning_attempts SET state='intent',intent_token=? WHERE root_id=? AND request_id=?", (token, root, request))
                self._event(root, request, "intent", {"token": token})
            return dict(self._attempt(root, request), new_intent=fresh)

    def settle(self, root, request, token, *, observation_sha256, reported_outcome):
        C.text(token)
        C.sha(observation_sha256)
        _require(reported_outcome in ("completed", "failed"), "explicit reported outcome required")
        claim = _encoded({"observation_sha256": observation_sha256, "reported_outcome": reported_outcome})
        with self._transaction():
            row = self._sync(self._root(root))
            self._open(row)
            attempt = self._attempt(root, request)
            _require(attempt["intent_token"] == token and attempt["state"] in ("intent", "settled"), "intent ownership or state changed")
            if attempt["state"] == "settled":
                _require(attempt["settlement"] == claim, "settlement replay changed")
            else:
                self.db.execute("UPDATE codex_learning_attempts SET state='settled',settlement=? WHERE root_id=? AND request_id=?", (claim, root, request))
                self._event(root, request, "settled", C.strict(claim))
                if reported_outcome == "failed":
                    self._stop(row, "reported_failure")
            return self._attempt(root, request)

    def unknown(self, root, request, token, *, reason):
        C.text(reason)
        with self._transaction():
            row = self._sync(self._root(root))
            self._open(row)
            attempt = self._attempt(root, request)
            _require(attempt["state"] == "intent" and attempt["intent_token"] == token, "intent ownership or state changed")
            self.db.execute("UPDATE codex_learning_attempts SET state='unknown' WHERE root_id=? AND request_id=?", (root, request))
            self._event(root, request, "execution_unknown", {"reason": reason, "token": token})
            self._stop(row, "execution_unknown")
        return self.snapshot(root)

    def cancel(self, root):
        with self._transaction():
            self._stop(self._sync(self._root(root)), "cancelled")
        return self.snapshot(root)

    def reconcile(self, root):
        """Latch deadline/generation/clock stops, never resume or dispatch."""
        with self._transaction():
            self._sync(self._root(root))
        return self.snapshot(root)

    def snapshot(self, root):
        """Read a DB snapshot only; does not refresh clocks or authorize work."""
        with self._transaction(readonly=True):
            row = self._root(root)
            attempts = [dict(v) for v in self.db.execute("SELECT * FROM codex_learning_attempts WHERE root_id=? ORDER BY rowid", (root,))]
            return {"root": row, "attempts": attempts, "reserved_total": len(attempts),
                    "intent_total": sum(bool(v["intent_token"]) for v in attempts),
                    "actual_outer_exec_count": None, "task_acceptance": None,
                    "usage": {"status": "unknown", "input_tokens": None, "cached_input_tokens": None, "output_tokens": None},
                    "actual_cost": {"status": "unknown", "amount": None},
                    "producer_authenticated": False, "execution_admitted": False, "adoptable": False,
                    "current_time_checked": False, "owner_generation_matches": row["owner_generation"] == self.generation,
                    "scope": "single selected database bookkeeping and unverified settlement claims only"}
