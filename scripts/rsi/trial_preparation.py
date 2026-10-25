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
PROVIDER_VERSION = "trial-budget-provider-v2"
PROPOSAL_VERSION = "trial-budget-proposal-v3"
BINDING_VERSION = "trial-proposal-candidate-binding-v1"
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
    keys = {"schema", "tenant_id", "project_id", "root_family", "application_commit", "candidate_sha256", "baseline_sha256", "training_family", "followup_family", "holdout_cases", "model", "price", "limits"}
    if isinstance(c, dict) and c.get("schema") == PROVIDER_VERSION:
        keys.add("provider_binding")
    fields(c, keys)
    if c["schema"] not in {VERSION, PROVIDER_VERSION, PROPOSAL_VERSION} or not isinstance(c["application_commit"], str) or not re.fullmatch("[0-9a-f]{40}", c["application_commit"]):
        raise ValueError("fixed application/schema required")
    if c["schema"] == PROVIDER_VERSION:
        binding = c["provider_binding"]
        fields(binding, {"profile_id", "profile_sha256", "protocol_sha256", "code_sha256"})
        text(binding["profile_id"]); sha(binding["profile_sha256"]); sha(binding["protocol_sha256"])
        fields(binding["code_sha256"], {"ledger", "adapter", "transport"})
        for value in binding["code_sha256"].values():
            sha(value)
    for key in ("tenant_id", "root_family", "training_family", "followup_family"):
        text(c[key])
    integer(c["project_id"], 1)
    if c["schema"] == PROPOSAL_VERSION:
        if c["candidate_sha256"] is not None:
            raise ValueError("proposal root keeps its original pending candidate; bind separately")
    else:
        sha(c["candidate_sha256"])
    sha(c["baseline_sha256"])
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
        if c["schema"] == PROPOSAL_VERSION:
            self._consumed(db, key, c)
            binding = self._candidate_binding(db, key, c)
            for attempt in db.execute("SELECT request_id FROM rsi_prepare_attempts WHERE pool=?", (key,)):
                self._proposal_attempt(c, binding, self._attempt(db, key, attempt["request_id"]))
        if dispatch:
            if any(item['result'] is None for item in self._isolations(db, key).values()):
                raise Conflict("registered isolation still unresolved")
            now = self._time()
            if row["generation"] != self.generation:
                raise Conflict("new process generation cannot resume old dispatch")
            unresolved_history = db.execute("SELECT 1 FROM rsi_prepare_events WHERE pool=? AND kind IN ('cancel_unknown','unknown')", (key,)).fetchone()
            if row["blocked"] or unresolved_history or now < row["last_us"] or now >= c["limits"]["deadline_us"]:
                raise Conflict("pool blocked or original deadline expired")
            db.execute("UPDATE rsi_prepare_pools SET last_us=? WHERE pool=?", (now, key))
        return c

    def _isolations(self, db, key):
        """Root events serialize execution without inventing provider usage."""
        items = {}
        for event in db.execute("SELECT request_id,kind,payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind IN ('isolation_intent','isolation_finished') ORDER BY id", (key,)):
            value = json.loads(event['payload'])
            if event['request_id'] or digest(value) != event['payload_hash']:
                raise Conflict('corrupt isolation root anchor')
            if event['kind'] == 'isolation_intent':
                fields(value, {'request_id', 'execution_id', 'intent', 'binding_sha256'})
                text(value['request_id']); text(value['intent']); sha(value['execution_id']); sha(value['binding_sha256'])
                if value['execution_id'] != digest([key, value['request_id'], value['binding_sha256']]) or self._attempt(db, key, value['request_id'])['intent'] != value['intent']:
                    raise Conflict('isolation original provider intent differs')
                if value['request_id'] in items:
                    raise Conflict('provider request cannot own two executions')
                if any(item['result'] is None for item in items.values()):
                    raise Conflict('overlapping isolated execution history')
                items[value['request_id']] = {'anchor': value, 'result': None}
            else:
                fields(value, {'execution_id', 'status', 'receipt_sha256'})
                sha(value['receipt_sha256'])
                if value['status'] not in {'evaluated', 'unknown'}:
                    raise Conflict('unsupported isolation result')
                matches = [item for item in items.values() if item['anchor']['execution_id'] == value['execution_id']]
                if len(matches) != 1 or matches[0]['result'] is not None:
                    raise Conflict('isolation result has no unique original intent')
                matches[0]['result'] = value
        return items

    def isolation_snapshot(self, key, request):
        with transaction(self.store) as db:
            self._pool(db, key)
            self._totals(db, key)
            return self._isolations(db, key).get(request)

    def begin_isolation(self, key, request, binding_sha256):
        sha(binding_sha256)
        with transaction(self.store) as db:
            self._pool(db, key)
            old = self._isolations(db, key).get(request)
            if old:
                if old['anchor']['binding_sha256'] != binding_sha256:
                    raise Conflict('execution cannot change registered provenance')
                return dict(old, new_execution=False)
            self._pool(db, key, dispatch=True)
            attempt = self._attempt(db, key, request)
            if attempt['state'] != 'settled':
                raise Conflict('complete original provider receipt required')
            self._settled_receipt(db, key, attempt)
            value = {'request_id': request, 'execution_id': digest([key, request, binding_sha256]),
                     'intent': attempt['intent'], 'binding_sha256': binding_sha256}
            self._event(db, key, '', 'isolation_intent', value)
            return {'anchor': value, 'result': None, 'new_execution': True}

    def finish_isolation(self, key, request, binding_sha256, *, verified, receipt_sha256):
        sha(binding_sha256); sha(receipt_sha256)
        if type(verified) is not bool:
            raise ValueError('explicit verified outcome required')
        with transaction(self.store) as db:
            contract = self._pool(db, key)
            item = self._isolations(db, key).get(request)
            if not item or item['anchor']['binding_sha256'] != binding_sha256:
                raise Conflict('isolation does not match original intent')
            value = {'execution_id': item['anchor']['execution_id'],
                     'status': 'evaluated' if verified else 'unknown', 'receipt_sha256': receipt_sha256}
            if item['result']:
                if item['result'] != value:
                    raise Conflict('immutable isolation result differs')
                return item['result']
            attempt = self._attempt(db, key, request)
            if attempt['intent'] != item['anchor']['intent'] or attempt['state'] != 'settled':
                raise Conflict('original settled provider intent changed')
            self._settled_receipt(db, key, attempt)
            if verified and self._time() >= contract['limits']['deadline_us']:
                raise Conflict('verified isolation exceeded original root deadline')
            if not verified:
                # Preserve the known usage receipt/history, but conservatively
                # restore its original maximum reservation. Late settlement is
                # already fenced by the original settled->unknown history gate.
                db.execute("UPDATE rsi_prepare_attempts SET state='unknown' WHERE pool=? AND request_id=?", (key, request))
                db.execute("UPDATE rsi_prepare_pools SET blocked=1 WHERE pool=?", (key,))
                self._event(db, key, request, 'unknown', {'intent': attempt['intent'],
                    'reason': 'registered_isolation_unverifiable', 'prior_receipt_sha256': attempt['receipt_hash']})
            self._event(db, key, '', 'isolation_finished', value)
            return value

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
        keys = {r["pool"] for r in db.execute("SELECT pool FROM rsi_prepare_pools UNION SELECT pool FROM rsi_prepare_events WHERE kind IN ('create','consume_holdout','bind_candidate')")}
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

    def _proposal_attempt(self, c, binding, row):
        body = row["body"]
        try:
            fields(body, {"phase", "input_limit", "output_limit", "reserved_micro_cny", "contract_hash", "material_sha256", "candidate_binding_sha256"})
            integer(body["input_limit"], 1); integer(body["output_limit"], 1); integer(body["reserved_micro_cny"]); sha(body["material_sha256"])
            if body["phase"] not in PHASES or body["contract_hash"] != digest(c):
                raise Conflict("proposal attempt changed its original root or phase")
            expected = None if body["phase"] == "propose" else digest(binding) if binding else None
            if (body["phase"] != "propose" and binding is None) or body["candidate_binding_sha256"] != expected:
                raise Conflict("attempt changed its original candidate binding")
            if body["reserved_micro_cny"] != body["input_limit"] * c["price"]["input_micro_cny_per_token"] + body["output_limit"] * c["price"]["output_micro_cny_per_token"]:
                raise Conflict("proposal reservation changed its original quote")
        except (ValueError, TypeError, KeyError) as exc:
            raise Conflict("unverifiable proposal reservation") from exc

    def _candidate_binding(self, db, key, c):
        """Verify an append-only declaration; this is not output/semantic attestation."""
        anchors = list(db.execute("SELECT request_id,payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='bind_candidate'", (key,)))
        if not anchors:
            return None
        if c["schema"] != PROPOSAL_VERSION or len(anchors) != 1 or anchors[0]["request_id"]:
            raise Conflict("candidate has no unique proposal-root anchor")
        try:
            value = json.loads(anchors[0]["payload"])
            fields(value, {"schema", "contract_hash", "proposal_request", "proposal_intent", "proposal_body_sha256", "proposal_receipt_sha256", "raw_response_sha256", "candidate_text", "candidate_sha256", "cases"})
            if (value["schema"] != BINDING_VERSION or digest(value) != anchors[0]["payload_hash"]
                    or value["contract_hash"] != digest(c) or value["cases"] != c["holdout_cases"]
                    or not isinstance(value["candidate_text"], str) or not value["candidate_text"].strip()
                    or hashlib.sha256(value["candidate_text"].encode("utf-8")).hexdigest() != value["candidate_sha256"]
                    or value["candidate_sha256"] == c["baseline_sha256"]):
                raise Conflict("candidate declaration differs from its original root")
            row = self._attempt(db, key, value["proposal_request"])
            receipt = self._settled_receipt(db, key, row)
            # A later unknown keeps the original binding/history, while the
            # root fence retains the maximum reservation and denies dispatch.
            if (row["state"] not in {"settled", "unknown"} or row["body"]["phase"] != "propose"
                    or row["body"]["contract_hash"] != digest(c) or not row["intent"]
                    or value["proposal_intent"] != row["intent"]
                    or value["proposal_body_sha256"] != row["body_hash"]
                    or value["proposal_receipt_sha256"] != row["receipt_hash"]
                    or value["raw_response_sha256"] != receipt["raw_response_sha256"]):
                raise Conflict("candidate belongs to another original proposal")
            return value
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise Conflict("unverifiable original candidate binding") from exc

    def bind_candidate(self, key, proposal_request, candidate_text, raw_response_sha256):
        """Bind once and consume the presealed B/C set atomically, without a new root.

        The trusted caller must separately verify actual output derivation. A
        metering-receipt reference alone never grants execution or RSI credit.
        """
        text(proposal_request); sha(raw_response_sha256)
        if not isinstance(candidate_text, str) or not candidate_text.strip():
            raise ValueError("complete nonempty candidate policy text required")
        candidate_sha = hashlib.sha256(candidate_text.encode("utf-8")).hexdigest()
        with transaction(self.store) as db:
            c = self._pool(db, key)
            if c["schema"] != PROPOSAL_VERSION or candidate_sha == c["baseline_sha256"]:
                raise Conflict("binding requires a pending proposal root and a distinct policy")
            previous = self._candidate_binding(db, key, c)
            if previous:
                if (previous["proposal_request"], previous["candidate_text"], previous["raw_response_sha256"]) != (proposal_request, candidate_text, raw_response_sha256):
                    raise Conflict("the original candidate and terminal set cannot be rebound")
                return {"new_binding": False, "binding_sha256": digest(previous), "candidate_sha256": candidate_sha}
            self._pool(db, key, dispatch=True)
            if db.execute("SELECT 1 FROM rsi_prepare_attempts WHERE pool=? AND state IN ('reserved','intent','unknown')", (key,)).fetchone():
                raise Conflict("proposal attempts must finish before candidate binding")
            row = self._attempt(db, key, proposal_request)
            if row["state"] != "settled" or row["body"]["phase"] != "propose" or self._framing_invalid(db, key, proposal_request):
                raise Conflict("an original settled proposal is required")
            receipt = self._settled_receipt(db, key, row)
            if receipt["raw_response_sha256"] != raw_response_sha256:
                raise Conflict("candidate reference differs from the original proposal response")
            self._scope_consumptions(db, c)
            value = {"schema": BINDING_VERSION, "contract_hash": digest(c), "proposal_request": proposal_request,
                     "proposal_intent": row["intent"], "proposal_body_sha256": row["body_hash"],
                     "proposal_receipt_sha256": row["receipt_hash"], "raw_response_sha256": raw_response_sha256,
                     "candidate_text": candidate_text, "candidate_sha256": candidate_sha, "cases": c["holdout_cases"]}
            scope = digest([c["tenant_id"], c["project_id"]])
            for case in c["holdout_cases"]:
                if db.execute("SELECT 1 FROM rsi_prepare_holdouts WHERE scope=? AND input_hash=?", (scope, case["input_sha256"])).fetchone():
                    raise Conflict("holdout already consumed in this project")
                db.execute("INSERT INTO rsi_prepare_holdouts VALUES(?,?,?,?)", (scope, case["input_sha256"], key, case["source_family"]))
            self._event(db, key, "", "bind_candidate", value)
            self._event(db, key, "", "consume_holdout", {"candidate_sha256": candidate_sha, "cases": c["holdout_cases"]})
            self._consumed(db, key, c)
            return {"new_binding": True, "binding_sha256": digest(value), "candidate_sha256": candidate_sha}

    def _consumed(self, db, key, c):
        scope = digest([c["tenant_id"], c["project_id"]])
        existing = list(db.execute("SELECT scope,input_hash,family FROM rsi_prepare_holdouts WHERE pool=?", (key,)))
        anchors = list(db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND kind='consume_holdout'", (key,)))
        binding = self._candidate_binding(db, key, c) if c["schema"] == PROPOSAL_VERSION else None
        if not anchors and not existing:
            if binding:
                raise Conflict("candidate binding lost its original terminal consumption")
            return False
        if c["schema"] == PROPOSAL_VERSION and binding is None:
            raise Conflict("terminal consumption lost its original candidate binding")
        value = {"candidate_sha256": binding["candidate_sha256"] if binding else c["candidate_sha256"], "cases": c["holdout_cases"]}
        expected = {(scope, r["input_sha256"], r["source_family"]) for r in c["holdout_cases"]}
        if (len(anchors) != 1 or anchors[0]["payload_hash"] != digest(value) or encoded(json.loads(anchors[0]["payload"])) != encoded(value)
                or {(r["scope"], r["input_hash"], r["family"]) for r in existing} != expected):
            raise Conflict("incomplete or corrupt holdout consumption")
        return True

    def consume_holdout(self, key):
        with transaction(self.store) as db:
            c = self._pool(db, key, dispatch=True)
            if c["schema"] == PROPOSAL_VERSION:
                if not self._consumed(db, key, c):
                    raise Conflict("pending candidate requires atomic candidate/terminal binding")
                return False
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
        isolations = self._isolations(db, key)
        for row in db.execute("SELECT request_id FROM rsi_prepare_attempts WHERE pool=?", (key,)):
            attempt = self._attempt(db, key, row["request_id"])
            calls += 1  # Even proved pre-intent cancellation does not refresh attempt count.
            body = attempt["body"]
            if attempt["state"] == "cancelled":
                continue
            if attempt["state"] == "settled":
                receipt = self._settled_receipt(db, key, attempt)
                isolation = isolations.get(row['request_id'])
                if isolation and isolation['result'] is None:
                    tokens += body['input_limit'] + body['output_limit']
                    cost += body['reserved_micro_cny']
                else:
                    tokens += receipt["input_tokens"] + receipt["output_tokens"]
                    cost += receipt["accounted_micro_cny"]
            elif attempt["state"] in {"reserved", "intent", "unknown"}:
                tokens += body["input_limit"] + body["output_limit"]
                cost += body["reserved_micro_cny"]
            else:
                raise Conflict("unrecognized attempt state")
        return {"calls": calls, "billed_tokens": tokens, "cost_micro_cny": cost}

    def reserve(self, key, request, phase, input_limit, output_limit, *, material_sha256=None):
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
            if c["schema"] in {PROVIDER_VERSION, PROPOSAL_VERSION}:
                body["material_sha256"] = sha(material_sha256)
            elif material_sha256 is not None:
                raise ValueError("provider material requires v2 contract")
            if c["schema"] == PROPOSAL_VERSION:
                binding = self._candidate_binding(db, key, c)
                body["candidate_binding_sha256"] = None if phase == "propose" else digest(binding) if binding else None
            if db.execute("SELECT 1 FROM rsi_prepare_attempts WHERE pool=? AND request_id=?", (key, request)).fetchone():
                old = self._attempt(db, key, request)
                if old["body_hash"] != digest(body):
                    raise Conflict("request already binds another attempt")
                return old
            self._pool(db, key, dispatch=True)
            if c["schema"] == PROPOSAL_VERSION:
                bound = self._candidate_binding(db, key, c)
                if (phase == "propose") == bool(bound):
                    raise Conflict("only proposal before binding; no new proposal after terminal exposure")
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
            if c["schema"] == PROPOSAL_VERSION and (row["body"]["phase"] == "propose") == bool(self._candidate_binding(db, key, c)):
                raise Conflict("proposal binding phase changed before dispatch")
            if row["body"]["phase"] in {"baseline", "candidate", "terminal"}:
                self._scope_consumptions(db, c)
                if not self._consumed(db, key, c):
                    raise Conflict("original terminal consumption missing")
            if c["schema"] in {PROVIDER_VERSION, PROPOSAL_VERSION}:
                sync = next(iter(db.execute("PRAGMA synchronous").fetchone().values()))
                journal = next(iter(db.execute("PRAGMA journal_mode").fetchone().values()))
                if sync not in {2, 3} or journal not in {"delete", "truncate", "persist", "wal"}:
                    raise Conflict("durable provider intent requires FULL SQLite synchronization")
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

    def snapshot(self, key, request=None):
        """Validate original anchors in one snapshot; never authorize dispatch."""
        with transaction(self.store) as db:
            c = self._pool(db, key)
            self._totals(db, key)
            row = self._attempt(db, key, request) if request is not None else None
            if row and row["state"] == "settled":
                self._settled_receipt(db, key, row)
            result = {"contract": c, "attempt": row}
            if c["schema"] == PROPOSAL_VERSION:
                result["candidate_binding"] = self._candidate_binding(db, key, c)
                result["candidate_derivation_verified"] = False
            return result

    def unknown(self, key, request, intent, reason):
        """An uncertain remote request retains its worst-case reservation forever."""
        text(reason)
        with transaction(self.store) as db:
            self._pool(db, key)
            row = self._attempt(db, key, request)
            if not intent or row["intent"] != intent or row["state"] not in {"intent", "unknown"}:
                raise Conflict("unknown result belongs to no active intent")
            db.execute("UPDATE rsi_prepare_attempts SET state='unknown' WHERE pool=? AND request_id=?", (key, request))
            db.execute("UPDATE rsi_prepare_pools SET blocked=1 WHERE pool=?", (key,))
            self._event(db, key, request, "unknown", {"intent": intent, "reason": reason})
        return "unknown"

    def _framing_invalid(self, db, key, request):
        invalid = False
        for event in db.execute("SELECT payload,payload_hash FROM rsi_prepare_events WHERE pool=? AND request_id=? AND kind='unknown'", (key, request)):
            value = json.loads(event["payload"])
            if not isinstance(value, dict) or digest(value) != event["payload_hash"]:
                raise Conflict("corrupt original unknown history")
            invalid |= value.get("reason") == "invalid_original_http_framing"
        return invalid

    def invalidate_framing(self, key, request, intent):
        """Quarantine a bound original response; retain immutable settlements.

        Stricter response validation can invalidate a prior apparent settlement.
        This restores its original worst-case hold, never refunds or redispatches.
        """
        with transaction(self.store) as db:
            self._pool(db, key)
            row = self._attempt(db, key, request)
            if not intent or row["intent"] != intent or row["state"] not in {"intent", "unknown", "settled"}:
                raise Conflict("invalid framing belongs to no committed intent")
            if row["state"] == "settled":
                self._settled_receipt(db, key, row)
            db.execute("UPDATE rsi_prepare_pools SET blocked=1 WHERE pool=?", (key,))
            if row["state"] != "unknown":
                db.execute("UPDATE rsi_prepare_attempts SET state='unknown' WHERE pool=? AND request_id=?", (key, request))
            if not self._framing_invalid(db, key, request):
                self._event(db, key, request, "unknown", {"intent": intent, "reason": "invalid_original_http_framing", "prior_receipt_sha256": row["receipt_hash"]})
        return "unknown"

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
            if self._framing_invalid(db, key, request) or (row["state"] == "unknown" and db.execute("SELECT 1 FROM rsi_prepare_events WHERE pool=? AND request_id=? AND kind='settled'", (key, request)).fetchone()):
                raise Conflict("invalidated original response cannot be settled again")
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
                result = {"contract_hash": digest(c), "totals": self._totals(db, key), "blocked": bool(row["blocked"]), "current_generation": row["generation"] == self.generation, "execution_authorized": False, "provider_evidence_verified": False, "os_holdout_isolation_verified": False}
                if c["schema"] == PROPOSAL_VERSION:
                    binding = self._candidate_binding(db, key, c)
                    result.update(candidate_bound=bool(binding), candidate_binding_sha256=digest(binding) if binding else None, candidate_derivation_verified=False)
                return result
            finally:
                db.rollback()
