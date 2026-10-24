"""Offline transactional preparation for a future real-trial adapter.

Uses the existing Store/learning transaction, never installed by Store startup.
No HTTP, provider call, oracle reader, execution permission or adoption route.
Pool keys, scopes and provider evidence still need trusted server-side binding.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid

from tmh.platform.learning import transaction

VERSION = "trial-budget-preparation-v1"
MAX = 2 ** 60
PHASES = {"propose", "baseline", "candidate", "judge", "probe", "retry", "terminal", "followup"}
DDL = (
    "CREATE TABLE rsi_prepare_pools (pool TEXT PRIMARY KEY, contract TEXT NOT NULL, contract_hash TEXT NOT NULL, generation TEXT NOT NULL, created_us INTEGER NOT NULL, last_us INTEGER NOT NULL, blocked INTEGER NOT NULL)",
    "CREATE TABLE rsi_prepare_attempts (pool TEXT NOT NULL, request_id TEXT NOT NULL, body TEXT NOT NULL, body_hash TEXT NOT NULL, state TEXT NOT NULL, intent TEXT NOT NULL, receipt TEXT NOT NULL, receipt_hash TEXT NOT NULL, PRIMARY KEY(pool,request_id))",
    "CREATE TABLE rsi_prepare_holdouts (scope TEXT NOT NULL, input_hash TEXT NOT NULL, pool TEXT NOT NULL, family TEXT NOT NULL, PRIMARY KEY(scope,input_hash))",
    "CREATE TABLE rsi_prepare_events (id INTEGER PRIMARY KEY AUTOINCREMENT, pool TEXT NOT NULL, request_id TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL)",
)


class Conflict(ValueError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def fields(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("exact public fields required")


def integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX:
        raise ValueError("bounded integer required")
    return value


def text(value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("nonempty exact identifier required")
    return value


def sha(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("SHA256 required")
    return value


def validate_contract(c):
    fields(c, {"schema", "tenant_id", "project_id", "root_family", "application_commit", "candidate_sha256", "baseline_sha256", "training_family", "followup_family", "holdout_cases", "model", "price", "limits"})
    if c["schema"] != VERSION or not isinstance(c["application_commit"], str) or not re.fullmatch("[0-9a-f]{40}", c["application_commit"]):
        raise ValueError("fixed application/schema required")
    for key in ("tenant_id", "root_family", "training_family", "followup_family"):
        text(c[key])
    integer(c["project_id"], 1)
    sha(c["candidate_sha256"]); sha(c["baseline_sha256"])
    if c["candidate_sha256"] == c["baseline_sha256"] or c["training_family"] == c["followup_family"]:
        raise ValueError("distinct candidate/baseline and source families required")
    fields(c["model"], {"provider", "requested_model", "response_model"})
    for value in c["model"].values():
        text(value)
    fields(c["price"], {"reference_sha256", "input_micro_cny_per_token", "cached_micro_cny_per_token", "output_micro_cny_per_token"})
    sha(c["price"]["reference_sha256"])
    for key in ("input_micro_cny_per_token", "cached_micro_cny_per_token", "output_micro_cny_per_token"):
        integer(c["price"][key])
    if c["price"]["cached_micro_cny_per_token"] > c["price"]["input_micro_cny_per_token"]:
        raise ValueError("cached price cannot exceed input upper bound")
    fields(c["limits"], {"calls", "billed_tokens", "cost_micro_cny", "deadline_us"})
    for value in c["limits"].values():
        integer(value, 1)
    cases = c["holdout_cases"]
    if not isinstance(cases, list) or len(cases) < 3:
        raise ValueError("three or more holdouts required")
    inputs, families = set(), set()
    for row in cases:
        fields(row, {"input_sha256", "source_family"})
        ih, family = sha(row["input_sha256"]), text(row["source_family"])
        if ih in inputs or family in {c["training_family"], c["followup_family"]}:
            raise ValueError("duplicate or exposed source")
        inputs.add(ih); families.add(family)
    if len(families) < 2 or c["limits"]["calls"] < 2 * len(cases) + 2:
        raise ValueError("two holdout families and full-chain calls required")
    # Round-trip ensures caller mutations cannot change the persisted contract.
    return json.loads(encoded(c))


class Ledger:
    def __init__(self, store, *, wall_us=None, monotonic=None):
        self.store = store
        self.wall = wall_us or (lambda: time.time_ns() // 1000)
        self.mono = monotonic or time.monotonic
        self.start_wall, self.start_mono = self.wall(), self.mono()
        self.generation = uuid.uuid4().hex
        with transaction(store) as db:
            present = {r["name"]: r["sql"] for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name LIKE 'rsi_prepare_%'")}
            if present:
                if present != {s.split()[2]: s for s in DDL}:
                    raise Conflict("unverifiable preparation schema")
            else:
                for statement in DDL:
                    db.execute(statement)

    def _time(self):
        return max(self.wall(), self.start_wall + int((self.mono() - self.start_mono) * 1000000))

    def _pool(self, db, key, *, dispatch=False):
        row = db.execute("SELECT * FROM rsi_prepare_pools WHERE pool=?", (key,)).fetchone()
        if row is None or digest(json.loads(row["contract"])) != row["contract_hash"]:
            raise Conflict("missing or corrupt original pool contract")
        c = json.loads(row["contract"])
        validate_contract(c)
        anchors = list(db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='create'", (key,)))
        original = {"contract": c, "generation": row["generation"], "created_us": row["created_us"]}
        if len(anchors) != 1 or anchors[0]["payload_hash"] != digest(original) or encoded(json.loads(anchors[0]["payload"])) != encoded(original):
            raise Conflict("original create anchor mismatch")
        if dispatch:
            now = self._time()
            if row["generation"] != self.generation:
                raise Conflict("new process generation cannot resume old dispatch")
            unresolved_history = db.execute("SELECT 1 FROM rsi_prepare_events WHERE pool=? AND kind IN ('cancel_unknown','unknown')", (key,)).fetchone()
            if row["blocked"] or unresolved_history or now < row["last_us"] or now >= c["limits"]["deadline_us"]:
                raise Conflict("pool blocked or original deadline expired")
            db.execute("UPDATE rsi_prepare_pools SET last_us=? WHERE pool=?", (now, key))
        return c

    def _event(self, db, key, request, kind, value):
        db.execute("INSERT INTO rsi_prepare_events(pool,request_id,kind,payload,payload_hash) VALUES(?,?,?,?,?)", (key, request, kind, encoded(value), digest(value)))

    def _attempt(self, db, key, request):
        row = db.execute("SELECT * FROM rsi_prepare_attempts WHERE pool=? AND request_id=?", (key, request)).fetchone()
        if row is None:
            raise Conflict("missing attempt")
        row = dict(row)
        row["body"] = json.loads(row["body"])
        anchors = list(db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND request_id=? AND kind='reserve'", (key, request)))
        if digest(row["body"]) != row["body_hash"] or len(anchors) != 1 or anchors[0]["payload_hash"] != row["body_hash"] or encoded(json.loads(anchors[0]["payload"])) != encoded(row["body"]):
            raise Conflict("corrupt original reservation")
        latest = db.execute("SELECT kind,payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND request_id=? ORDER BY id DESC LIMIT 1", (key, request)).fetchone()
        states = {"reserve": "reserved", "intent": "intent", "cancel_before_intent": "cancelled", "cancel_unknown": "unknown", "unknown": "unknown", "settled": "settled"}
        if latest is None or states.get(latest["kind"]) != row["state"] or digest(json.loads(latest["payload"])) != latest["payload_hash"]:
            raise Conflict("attempt state contradicts original events")
        if row["intent"]:
            anchors = list(db.execute("SELECT payload FROM rsi_prepare_events WHERE pool=? AND request_id=? AND kind='intent'", (key, request)))
            if len(anchors) != 1 or json.loads(anchors[0]["payload"]) != {"intent": row["intent"], "body_hash": row["body_hash"]}:
                raise Conflict("original dispatch intent mismatch")
        return row

    def _settled_receipt(self, db, key, attempt):
        try:
            receipt = json.loads(attempt["receipt"])
            anchors = list(db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND request_id=? AND kind='settled'", (key, attempt["request_id"])))
            if (digest(receipt) != attempt["receipt_hash"] or len(anchors) != 1
                    or anchors[0]["payload_hash"] != attempt["receipt_hash"]
                    or encoded(json.loads(anchors[0]["payload"])) != encoded(receipt)):
                raise Conflict("corrupt settlement")
            return receipt
        except (ValueError, TypeError, KeyError) as error:
            raise Conflict("unverifiable original settlement") from error

    def _scope_consumptions(self, db, c):
        # Original events drive the scan too: a missing mutable pool/claim row
        # cannot erase a still-present original consumption. Known other scopes
        # remain independent; an event without a verifiable create has no scope.
        keys = {r["pool"] for r in db.execute("SELECT pool FROM rsi_prepare_pools UNION SELECT pool FROM rsi_prepare_events WHERE kind IN ('create','consume_holdout')")}
        scope = digest([c["tenant_id"], c["project_id"]])
        keys.update(r["pool"] for r in db.execute("SELECT pool FROM rsi_prepare_holdouts WHERE scope=?", (scope,)))
        for key in keys:
            anchors = list(db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='create'", (key,)))
            if len(anchors) != 1:
                raise Conflict("orphan consumption scope cannot be verified")
            try:
                original = json.loads(anchors[0]["payload"])
                fields(original, {"contract", "generation", "created_us"})
                prior = validate_contract(original["contract"])
                if digest(original) != anchors[0]["payload_hash"] or digest([prior["tenant_id"], prior["project_id"], prior["root_family"]]) != key:
                    raise Conflict("original scope anchor mismatch")
            except (ValueError, TypeError, KeyError) as error:
                raise Conflict("original consumption scope cannot be verified") from error
            if prior["tenant_id"] == c["tenant_id"] and prior["project_id"] == c["project_id"]:
                self._pool(db, key)
                self._consumed(db, key, prior)

    def create(self, contract):
        c = validate_contract(contract)
        key = digest([c["tenant_id"], c["project_id"], c["root_family"]])
        with transaction(self.store) as db:
            old = db.execute("SELECT contract_hash FROM rsi_prepare_pools WHERE pool=?", (key,)).fetchone()
            if old:
                self._pool(db, key)
                if old["contract_hash"] != digest(c):
                    raise Conflict("same root family cannot refresh contract or budget")
                return key
            dangling = db.execute("SELECT 1 FROM rsi_prepare_events WHERE pool=? UNION SELECT 1 FROM rsi_prepare_attempts WHERE pool=? UNION SELECT 1 FROM rsi_prepare_holdouts WHERE pool=? LIMIT 1", (key, key, key)).fetchone()
            if dangling:
                raise Conflict("missing pool with original history cannot be recreated")
            now = self._time()
            if now >= c["limits"]["deadline_us"]:
                raise Conflict("original deadline expired")
            db.execute("INSERT INTO rsi_prepare_pools VALUES(?,?,?,?,?,?,0)", (key, encoded(c), digest(c), self.generation, now, now))
            self._event(db, key, "", "create", {"contract": c, "generation": self.generation, "created_us": now})
        return key

    def _consumed(self, db, key, c):
        scope = digest([c["tenant_id"], c["project_id"]])
        existing = list(db.execute("SELECT scope,input_hash,family FROM rsi_prepare_holdouts WHERE pool=?", (key,)))
        anchors = list(db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='consume_holdout'", (key,)))
        if not anchors and not existing:
            return False
        value = {"candidate_sha256": c["candidate_sha256"], "cases": c["holdout_cases"]}
        expected = {(scope, r["input_sha256"], r["source_family"]) for r in c["holdout_cases"]}
        if (len(anchors) != 1 or anchors[0]["payload_hash"] != digest(value) or encoded(json.loads(anchors[0]["payload"])) != encoded(value)
                or {(r["scope"], r["input_hash"], r["family"]) for r in existing} != expected):
            raise Conflict("incomplete or corrupt holdout consumption")
        return True

    def consume_holdout(self, key):
        with transaction(self.store) as db:
            c = self._pool(db, key, dispatch=True)
            self._scope_consumptions(db, c)
            if self._consumed(db, key, c):
                return False
            scope = digest([c["tenant_id"], c["project_id"]])
            for row in c["holdout_cases"]:
                if db.execute("SELECT 1 FROM rsi_prepare_holdouts WHERE scope=? AND input_hash=?", (scope, row["input_sha256"])).fetchone():
                    raise Conflict("holdout already consumed in this project")
                db.execute("INSERT INTO rsi_prepare_holdouts VALUES(?,?,?,?)", (scope, row["input_sha256"], key, row["source_family"]))
            self._event(db, key, "", "consume_holdout", {"candidate_sha256": c["candidate_sha256"], "cases": c["holdout_cases"]})
        return True

    def _totals(self, db, key):
        calls, tokens, cost = 0, 0, 0
        ids = [r["request_id"] for r in db.execute("SELECT request_id FROM rsi_prepare_attempts WHERE pool=?", (key,))]
        anchors = [r["request_id"] for r in db.execute("SELECT request_id FROM rsi_prepare_events WHERE pool=? AND kind='reserve'", (key,))]
        if set(ids) != set(anchors) or len(anchors) != len(ids):
            raise Conflict("original attempts cannot be removed or duplicated")
        for row in db.execute("SELECT request_id FROM rsi_prepare_attempts WHERE pool=?", (key,)):
            attempt = self._attempt(db, key, row["request_id"])
            calls += 1  # Even proved pre-intent cancellation does not refresh attempt count.
            body = attempt["body"]
            if attempt["state"] == "cancelled":
                continue
            if attempt["state"] == "settled":
                receipt = self._settled_receipt(db, key, attempt)
                tokens += receipt["input_tokens"] + receipt["output_tokens"]
                cost += receipt["accounted_micro_cny"]
            elif attempt["state"] in {"reserved", "intent", "unknown"}:
                tokens += body["input_limit"] + body["output_limit"]
                cost += body["reserved_micro_cny"]
            else:
                raise Conflict("unrecognized attempt state")
        return {"calls": calls, "billed_tokens": tokens, "cost_micro_cny": cost}

    def reserve(self, key, request, phase, input_limit, output_limit):
        text(request)
        if not isinstance(phase, str) or phase not in PHASES:
            raise ValueError("unknown phase")
        integer(input_limit, 1); integer(output_limit, 1)
        with transaction(self.store) as db:
            c = self._pool(db, key)
            price = c["price"]
            cost = input_limit * price["input_micro_cny_per_token"] + output_limit * price["output_micro_cny_per_token"]
            integer(cost)
            body = dict(phase=phase, input_limit=input_limit, output_limit=output_limit, reserved_micro_cny=cost, contract_hash=digest(c))
            if db.execute("SELECT 1 FROM rsi_prepare_attempts WHERE pool=? AND request_id=?", (key, request)).fetchone():
                old = self._attempt(db, key, request)
                if old["body_hash"] != digest(body):
                    raise Conflict("request already binds another attempt")
                return old
            self._pool(db, key, dispatch=True)
            if db.execute("SELECT 1 FROM rsi_prepare_attempts WHERE pool=? AND state IN ('reserved','intent','unknown')", (key,)).fetchone():
                raise Conflict("serial attempt or unresolved reservation exists")
            if phase in {"baseline", "candidate", "terminal"}:
                self._scope_consumptions(db, c)
                if not self._consumed(db, key, c):
                    raise Conflict("holdout must be consumed before first terminal arm")
            total = self._totals(db, key)
            if any(total[k] + n > c["limits"][k] for k, n in (("calls", 1), ("billed_tokens", input_limit + output_limit), ("cost_micro_cny", cost))):
                raise Conflict("cumulative root budget exceeded")
            db.execute("INSERT INTO rsi_prepare_attempts VALUES(?,?,?,?,'reserved','','','')", (key, request, encoded(body), digest(body)))
            self._event(db, key, request, "reserve", body)
            return self._attempt(db, key, request)

    def intent(self, key, request):
        with transaction(self.store) as db:
            row = self._attempt(db, key, request)
            self._pool(db, key)
            if row["state"] != "reserved":
                return {"new_intent": False, "intent": row["intent"], "state": row["state"]}
            c = self._pool(db, key, dispatch=True)
            if row["body"]["phase"] in {"baseline", "candidate", "terminal"}:
                self._scope_consumptions(db, c)
                if not self._consumed(db, key, c):
                    raise Conflict("original terminal consumption missing")
            token = uuid.uuid4().hex
            db.execute("UPDATE rsi_prepare_attempts SET state='intent',intent=? WHERE pool=? AND request_id=?", (token, key, request))
            self._event(db, key, request, "intent", {"intent": token, "body_hash": row["body_hash"]})
            return {"new_intent": True, "intent": token, "state": "intent"}

    def cancel(self, key, request):
        with transaction(self.store) as db:
            self._pool(db, key)
            row = self._attempt(db, key, request)
            if row["state"] == "reserved":
                db.execute("UPDATE rsi_prepare_attempts SET state='cancelled' WHERE pool=? AND request_id=?", (key, request))
                self._event(db, key, request, "cancel_before_intent", {})
            elif row["state"] == "intent":
                db.execute("UPDATE rsi_prepare_attempts SET state='unknown' WHERE pool=? AND request_id=?", (key, request))
                db.execute("UPDATE rsi_prepare_pools SET blocked=1 WHERE pool=?", (key,))
                self._event(db, key, request, "cancel_unknown", {"intent": row["intent"]})
            return self._attempt(db, key, request)["state"]

    def settle(self, key, request, intent, receipt):
        fields(receipt, {"provider_request_id", "response_model", "input_tokens", "cached_input_tokens", "output_tokens", "provider_charge_micro_cny", "raw_response_sha256"})
        text(receipt["provider_request_id"]); text(receipt["response_model"]); sha(receipt["raw_response_sha256"])
        for k in ("input_tokens", "cached_input_tokens", "output_tokens"):
            integer(receipt[k])
        if receipt["provider_charge_micro_cny"] is not None:
            integer(receipt["provider_charge_micro_cny"])
        frozen = json.loads(encoded(receipt))
        with transaction(self.store) as db:
            c = self._pool(db, key)
            row = self._attempt(db, key, request)
            if not intent or row["intent"] != intent or row["state"] not in {"intent", "unknown", "settled"}:
                raise Conflict("receipt belongs to no committed intent")
            usage, price, body = frozen, c["price"], row["body"]
            if usage["cached_input_tokens"] > usage["input_tokens"]:
                raise ValueError("cached input is part of total input")
            calculated = ((usage["input_tokens"] - usage["cached_input_tokens"]) * price["input_micro_cny_per_token"] + usage["cached_input_tokens"] * price["cached_micro_cny_per_token"] + usage["output_tokens"] * price["output_micro_cny_per_token"])
            charged = usage["provider_charge_micro_cny"]
            result = dict(frozen, accounted_micro_cny=calculated if charged is None else charged, cost_source="frozen_rate_calculation" if charged is None else "provider_receipt", pricing_sha256=price["reference_sha256"])
            if row["state"] == "settled":
                persisted = self._settled_receipt(db, key, row)
                if encoded(persisted) != encoded(result):
                    raise Conflict("settlement replay cannot rewrite original receipt")
                return "settled"
            valid = (usage["response_model"] == c["model"]["response_model"] and usage["input_tokens"] <= body["input_limit"] and usage["output_tokens"] <= body["output_limit"] and result["accounted_micro_cny"] <= body["reserved_micro_cny"])
            state = "settled" if valid else "unknown"
            db.execute("UPDATE rsi_prepare_attempts SET state=?,receipt=?,receipt_hash=? WHERE pool=? AND request_id=?", (state, encoded(result), digest(result), key, request))
            if not valid:
                db.execute("UPDATE rsi_prepare_pools SET blocked=1 WHERE pool=?", (key,))
            self._event(db, key, request, state, result)
            return state

    def inspect(self, key):
        with self.store.lock:
            db = self.store.db
            if db.in_transaction:
                raise RuntimeError("inspection cannot nest")
            db.execute("BEGIN")
            try:
                c = self._pool(db, key)
                self._consumed(db, key, c)
                row = db.execute("SELECT blocked,generation FROM rsi_prepare_pools WHERE pool=?", (key,)).fetchone()
                return {"contract_hash": digest(c), "totals": self._totals(db, key), "blocked": bool(row["blocked"]), "current_generation": row["generation"] == self.generation, "execution_authorized": False, "provider_evidence_verified": False, "os_holdout_isolation_verified": False}
            finally:
                db.rollback()
