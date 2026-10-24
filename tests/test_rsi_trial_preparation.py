"""Transactional preparation is not evidence of a metered or isolated provider."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

from tmh.platform.store import Store
from tmh.platform import supervised_process

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts/rsi/trial_preparation.py"
spec = importlib.util.spec_from_file_location("trial_preparation", MODULE)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
h = lambda v: hashlib.sha256(v.encode()).hexdigest()


def contract():
    return {"schema": M.VERSION, "tenant_id": "fixture-tenant", "project_id": 1, "root_family": "fixture-root",
            "application_commit": "a" * 40, "candidate_sha256": h("candidate"), "baseline_sha256": h("baseline"),
            "training_family": "A", "followup_family": "D", "holdout_cases": [{"input_sha256": h(str(i)), "source_family": f} for i, f in enumerate(["B", "B", "C"])],
            "model": {"provider": "fixture-provider", "requested_model": "fixture-alias", "response_model": "fixture-response-v1"},
            "price": {"reference_sha256": h("fixture-price"), "input_micro_cny_per_token": 10, "cached_micro_cny_per_token": 2, "output_micro_cny_per_token": 20},
            "limits": {"calls": 8, "billed_tokens": 10000, "cost_micro_cny": 10000, "deadline_us": 999999999999999}}


def receipt(**kwargs):
    return dict({"provider_request_id": "fixture-request", "response_model": "fixture-response-v1", "input_tokens": 4, "cached_input_tokens": 1,
                 "output_tokens": 2, "provider_charge_micro_cny": None, "raw_response_sha256": h("fixture-response")}, **kwargs)


CHILD = r'''
import importlib.util,json,socket,sys
from pathlib import Path
from tmh.platform.store import Store
spec=importlib.util.spec_from_file_location('trial_preparation',sys.argv[1]);M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
s=Store(Path(sys.argv[2]));ledger=M.Ledger(s,wall_us=lambda:1000);gate=socket.socket(fileno=int(sys.argv[4]))
try:
 gate.sendall(b'R')
 if gate.recv(1)!=b'S':raise RuntimeError('barrier')
 try:
  key=ledger.create(json.loads(Path(sys.argv[3]).read_text()))
  if sys.argv[5]=='consume':out={'won':ledger.consume_holdout(key)}
  else:
   ledger.reserve(key,'same-request','propose',10,10);out={'won':ledger.intent(key,'same-request')['new_intent']}
 except M.Conflict:out={'won':False}
 print(json.dumps(out),flush=True)
finally:gate.close();s.db.close()
'''


class TrialPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "store.db")
        self.addCleanup(self.store.db.close)
        self.clock, self.mono = [1000], [0.0]
        self.ledger = M.Ledger(self.store, wall_us=lambda: self.clock[0], monotonic=lambda: self.mono[0])
        self.c = contract()
        self.key = self.ledger.create(self.c)

    def start(self, phase="propose", request="request"):
        self.ledger.reserve(self.key, request, phase, 10, 10)
        return self.ledger.intent(self.key, request)["intent"]

    def test_store_startup_does_not_install_preparation_schema(self):
        s = Store(self.root / "unrelated.db")
        try:
            self.assertEqual(s.q("SELECT name FROM sqlite_master WHERE name LIKE 'rsi_prepare_%'"), [])
        finally:
            s.db.close()

    def test_same_root_cannot_refresh_candidate_deadline_or_budget(self):
        for field in ("candidate_sha256", "deadline", "calls"):
            c = copy.deepcopy(self.c)
            if field == "candidate_sha256":c[field] = h("other")
            else:c["limits"]["deadline_us" if field == "deadline" else "calls"] += 1
            with self.subTest(field=field), self.assertRaises(M.Conflict):self.ledger.create(c)
        self.assertEqual(self.ledger.create(self.c), self.key)

    def test_calls_all_phases_and_full_chain_limit(self):
        for i, phase in enumerate(["propose", "probe", "judge", "retry", "terminal", "baseline", "candidate", "followup"]):
            if phase == "terminal":self.assertTrue(self.ledger.consume_holdout(self.key))
            req = str(i)
            self.ledger.reserve(self.key, req, phase, 1, 1)
            token = self.ledger.intent(self.key, req)["intent"]
            self.assertEqual(self.ledger.settle(self.key, req, token, receipt(input_tokens=1, cached_input_tokens=0, output_tokens=1)), "settled")
        self.assertEqual(self.ledger.inspect(self.key)["totals"], {"calls": 8, "billed_tokens": 16, "cost_micro_cny": 240})
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "extra", "propose", 1, 1)

    def test_token_and_money_limits_deny_before_intent(self):
        for limit, amount in (("billed_tokens", 19), ("cost_micro_cny", 299)):
            c = copy.deepcopy(self.c);c["root_family"] += limit;c["limits"][limit] = amount
            key = self.ledger.create(c)
            with self.subTest(limit=limit), self.assertRaises(M.Conflict):self.ledger.reserve(key, "no-intent", "propose", 10, 10)
            self.assertEqual(self.ledger.inspect(key)["totals"]["calls"], 0)

    def test_intent_replay_never_authorizes_second_dispatch(self):
        token = self.start()
        self.assertEqual(self.ledger.intent(self.key, "request"), {"new_intent": False, "intent": token, "state": "intent"})
        self.assertEqual(self.ledger.reserve(self.key, "request", "propose", 10, 10)["state"], "intent")
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "request", "propose", 11, 10)
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "other", "retry", 10, 10)

    def test_cancel_unknown_keeps_maximum_hold_and_blocks_new_calls(self):
        token = self.start()
        self.assertEqual(self.ledger.cancel(self.key, "request"), "unknown")
        info = self.ledger.inspect(self.key)
        self.assertTrue(info["blocked"])
        self.assertEqual(info["totals"], {"calls": 1, "billed_tokens": 20, "cost_micro_cny": 300})
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "replacement", "retry", 10, 10)
        self.assertEqual(self.ledger.settle(self.key, "request", token, receipt()), "settled")
        self.assertTrue(self.ledger.inspect(self.key)["blocked"])

    def test_preintent_cancel_releases_tokens_but_not_attempt_count(self):
        self.ledger.reserve(self.key, "request", "propose", 10, 10)
        self.assertEqual(self.ledger.cancel(self.key, "request"), "cancelled")
        self.assertEqual(self.ledger.inspect(self.key)["totals"], {"calls": 1, "billed_tokens": 0, "cost_micro_cny": 0})
        self.assertFalse(self.ledger.intent(self.key, "request")["new_intent"])

    def test_unknown_identity_or_overage_never_refunds_or_claims_success(self):
        for change in ({"response_model": "other-model"}, {"input_tokens": 11}, {"output_tokens": 11}, {"provider_charge_micro_cny": 301}):
            c = copy.deepcopy(self.c);c["root_family"] += h(json.dumps(change));key = self.ledger.create(c)
            self.ledger.reserve(key, "request", "propose", 10, 10);token = self.ledger.intent(key, "request")["intent"]
            with self.subTest(change=change):self.assertEqual(self.ledger.settle(key, "request", token, receipt(**change)), "unknown")
            self.assertEqual(self.ledger.inspect(key)["totals"]["cost_micro_cny"], 300)
            self.assertTrue(self.ledger.inspect(key)["blocked"])

    def test_receipt_replay_and_actual_vs_calculated_cost_distinct(self):
        token = self.start();raw = receipt();self.ledger.settle(self.key, "request", token, raw)
        self.assertEqual(self.ledger.settle(self.key, "request", token, raw), "settled")
        self.assertEqual(self.ledger.inspect(self.key)["totals"], {"calls": 1, "billed_tokens": 6, "cost_micro_cny": 72})
        row = self.store.one("SELECT receipt FROM rsi_prepare_attempts WHERE pool=?", (self.key,))
        self.assertEqual(json.loads(row["receipt"])["cost_source"], "frozen_rate_calculation")
        with self.assertRaises(M.Conflict):self.ledger.settle(self.key, "request", token, receipt(provider_charge_micro_cny=71))
        self.ledger.reserve(self.key, "second", "followup", 10, 10);token = self.ledger.intent(self.key, "second")["intent"]
        self.ledger.settle(self.key, "second", token, receipt(provider_charge_micro_cny=71))
        row = self.store.one("SELECT receipt FROM rsi_prepare_attempts WHERE request_id='second'")
        self.assertEqual(json.loads(row["receipt"])["cost_source"], "provider_receipt")

    def test_malformed_or_wrong_attempt_receipts_keep_reservation(self):
        token = self.start()
        for bad in (receipt(input_tokens=True), receipt(cached_input_tokens=5), receipt(provider_charge_micro_cny=float('nan'))):
            with self.subTest(receipt=bad), self.assertRaises(ValueError):self.ledger.settle(self.key, "request", token, bad)
        with self.assertRaises(M.Conflict):self.ledger.settle(self.key, "request", "wrong-token", receipt())
        self.assertEqual(self.ledger.inspect(self.key)["totals"]["cost_micro_cny"], 300)

    def test_original_deadline_and_monotonic_clock_are_not_refreshed(self):
        self.ledger.reserve(self.key, "request", "propose", 10, 10)
        self.clock[0] = self.c["limits"]["deadline_us"]
        with self.assertRaises(M.Conflict):self.ledger.intent(self.key, "request")
        self.clock[0] = 500
        self.mono[0] = self.c["limits"]["deadline_us"] / 1000000
        with self.assertRaises(M.Conflict):self.ledger.intent(self.key, "request")

    def test_new_process_generation_cannot_resume_pending_dispatch(self):
        self.ledger.reserve(self.key, "request", "propose", 10, 10)
        other = M.Ledger(self.store, wall_us=lambda: 1000)
        self.assertEqual(other.create(self.c), self.key)
        with self.assertRaises(M.Conflict):other.intent(self.key, "request")
        with self.assertRaises(M.Conflict):other.reserve(self.key, "other", "propose", 10, 10)
        self.assertFalse(other.inspect(self.key)["current_generation"])

    def test_terminal_consumption_is_once_even_after_unknown(self):
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "baseline", "baseline", 10, 10)
        self.assertTrue(self.ledger.consume_holdout(self.key))
        self.assertFalse(self.ledger.consume_holdout(self.key))
        self.start("baseline");self.ledger.cancel(self.key, "request")
        c = copy.deepcopy(self.c);c["root_family"] = "new-request-or-family"
        key = self.ledger.create(c)
        before = len(self.store.q("SELECT * FROM rsi_prepare_holdouts"))
        with self.assertRaises(M.Conflict):self.ledger.consume_holdout(key)
        self.assertEqual(len(self.store.q("SELECT * FROM rsi_prepare_holdouts")), before)

    def test_consume_collision_rolls_back_all_earlier_inputs(self):
        self.ledger.consume_holdout(self.key)
        c = copy.deepcopy(self.c);c["root_family"] = "second"
        c["holdout_cases"][0]["input_sha256"] = h("unused")
        key = self.ledger.create(c)
        with self.assertRaises(M.Conflict):self.ledger.consume_holdout(key)
        self.assertEqual(self.store.q("SELECT * FROM rsi_prepare_holdouts WHERE pool=?", (key,)), [])

    def test_no_provider_or_os_isolation_claim_from_metadata(self):
        value = self.ledger.inspect(self.key)
        for field in ("execution_authorized", "provider_evidence_verified", "os_holdout_isolation_verified"):
            self.assertIs(value[field], False)

    def test_independent_original_create_and_reserve_anchors(self):
        changed = copy.deepcopy(self.c);changed["limits"]["calls"] += 1
        self.store.x("UPDATE rsi_prepare_pools SET contract=?,contract_hash=? WHERE pool=?", (M.encoded(changed), M.digest(changed), self.key))
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "request", "propose", 10, 10)
        self.store.x("UPDATE rsi_prepare_pools SET contract=?,contract_hash=? WHERE pool=?", (M.encoded(self.c), M.digest(self.c), self.key))
        row = self.ledger.reserve(self.key, "request", "propose", 10, 10)
        body = row["body"];body["reserved_micro_cny"] = 0
        self.store.x("UPDATE rsi_prepare_attempts SET body=?,body_hash=? WHERE pool=?", (M.encoded(body), M.digest(body), self.key))
        with self.assertRaises(M.Conflict):self.ledger.intent(self.key, "request")

    def test_deleting_claims_does_not_refresh_consumed_holdout(self):
        self.ledger.consume_holdout(self.key)
        self.store.x("DELETE FROM rsi_prepare_holdouts WHERE pool=?", (self.key,))
        with self.assertRaises(M.Conflict):self.ledger.consume_holdout(self.key)
        c = copy.deepcopy(self.c);c["root_family"] = "replacement"
        other = self.ledger.create(c)
        with self.assertRaises(M.Conflict):self.ledger.consume_holdout(other)
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "baseline", "baseline", 10, 10)

    def test_deleting_attempt_or_forging_cancel_cannot_refund(self):
        self.start()
        self.store.x("UPDATE rsi_prepare_attempts SET state='cancelled' WHERE pool=?", (self.key,))
        with self.assertRaises(M.Conflict):self.ledger.inspect(self.key)
        self.store.x("DELETE FROM rsi_prepare_attempts WHERE pool=?", (self.key,))
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "replacement", "probe", 10, 10)

    def test_invalid_contract_does_not_create_partial_pool(self):
        before = self.store.q("SELECT * FROM rsi_prepare_pools")
        for value in (True, 0, -1, 2.5, float('nan'), 2 ** 61):
            c = copy.deepcopy(self.c);c["root_family"] = "invalid";c["limits"]["calls"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):self.ledger.create(c)
        c = copy.deepcopy(self.c);c["holdout_cases"][0]["source_family"] = "A"
        with self.assertRaises(ValueError):self.ledger.create(c)
        self.assertEqual(self.store.q("SELECT * FROM rsi_prepare_pools"), before)

    def test_damaged_schema_is_not_repaired(self):
        self.store.x("DROP TABLE rsi_prepare_attempts")
        before = self.store.q("SELECT name,sql FROM sqlite_master WHERE name LIKE 'rsi_prepare_%'")
        with self.assertRaises(M.Conflict):M.Ledger(self.store)
        self.assertEqual(self.store.q("SELECT name,sql FROM sqlite_master WHERE name LIKE 'rsi_prepare_%'"), before)

    def race(self, contracts, mode):
        children, gates = [], []
        try:
            for i, c in enumerate(contracts):
                path = self.root / ("contract-%s.json" % i);path.write_text(json.dumps(c))
                parent, child = socket.socketpair();parent.settimeout(15)
                try:p = subprocess.Popen([sys.executable, "-c", CHILD, str(MODULE), str(self.store.path), str(path), str(child.fileno()), mode],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(child.fileno(),))
                finally:child.close()
                children.append(p);gates.append(parent)
            for gate in gates:self.assertEqual(gate.recv(1), b"R")
            for gate in gates:gate.sendall(b"S")
            results = []
            for p in children:
                out, err = p.communicate(timeout=15);self.assertEqual(p.returncode, 0, err);results.append(json.loads(out))
            return results
        finally:
            for gate in gates:gate.close()
            for p in children:
                if p.poll() is None:p.kill()
                p.communicate(timeout=10)

    @unittest.skipUnless(os.name == "posix", "real inherited-fd process competition requires POSIX")
    def test_two_real_interpreters_cannot_open_duplicate_root_budget(self):
        c = contract();c["root_family"] = "competition"
        results = self.race([c, c], "intent")
        self.assertEqual(sum(v["won"] for v in results), 1)
        self.assertEqual(len(self.store.q("SELECT * FROM rsi_prepare_attempts")), 1)
        self.assertEqual(len(self.store.q("SELECT * FROM rsi_prepare_events WHERE kind='intent'")), 1)

    @unittest.skipUnless(os.name == "posix", "real inherited-fd process competition requires POSIX")
    def test_two_real_interpreters_cannot_consume_the_same_holdout(self):
        a, b = contract(), contract();a["root_family"] = "competition-a";b["root_family"] = "competition-b"
        results = self.race([a, b], "consume")
        self.assertEqual(sum(v["won"] for v in results), 1)
        self.assertEqual(len(self.store.q("SELECT * FROM rsi_prepare_holdouts")), 3)
        self.assertEqual(len(self.store.q("SELECT * FROM rsi_prepare_events WHERE kind='consume_holdout'")), 1)

    @unittest.skipUnless(os.name == "posix", "existing supervisor requires POSIX")
    def test_real_timeout_keeps_unknown_budget_and_reaps_child(self):
        self.start()
        owner = {"token": "fixture-timeout-owner", "run_id": 2, "data_dir": str(self.root)}
        result = supervised_process.run_supervised([sys.executable, "-u", "-c", "import time;print('READY',flush=True);time.sleep(30)"],folder=self.root/'timeout-process',owner=owner,cwd=self.root,timeout=3)
        self.assertIsNotNone(result.pid)
        self.assertIn(b"READY", result.output_bytes)
        self.assertEqual(result.returncode, 124)
        self.assertEqual(result.reason, "timeout")
        self.assertTrue(result.cleanup["complete"])
        self.assertEqual(self.ledger.cancel(self.key, "request"), "unknown")
        self.assertEqual(self.ledger.inspect(self.key)["totals"]["cost_micro_cny"], 300)

    @unittest.skipUnless(os.name == "posix", "existing supervisor requires POSIX")
    def test_real_ready_then_cancel_keeps_unknown_and_reaps_child(self):
        self.start();cancel = threading.Event()
        owner = {"token": "fixture-cancel-owner", "run_id": 3, "data_dir": str(self.root)}
        def output(text):
            if "READY" in text:cancel.set()
        result = supervised_process.run_supervised([sys.executable, "-u", "-c", "import time;print('READY',flush=True);time.sleep(30)"],folder=self.root/'cancel-process',owner=owner,cwd=self.root,timeout=3,cancel_event=cancel,on_output=output)
        self.assertTrue(cancel.is_set())
        self.assertIsNotNone(result.pid)
        self.assertIn(b"READY", result.output_bytes)
        self.assertEqual(result.returncode, 130)
        self.assertEqual(result.reason, "cancelled")
        self.assertTrue(result.cleanup["complete"])
        self.assertEqual(self.ledger.cancel(self.key, "request"), "unknown")
        with self.assertRaises(M.Conflict):self.ledger.reserve(self.key, "retry", "retry", 10, 10)

    @unittest.skipUnless(os.name == "posix", "existing supervisor requires POSIX")
    def test_reuses_original_supervisor_for_a_fixed_non_model_fixture(self):
        token = self.start()
        owner = {"token": "fixture-owner", "run_id": 1, "data_dir": str(self.root)}
        result = supervised_process.run_supervised([sys.executable, "-c", "print('fixed-fixture')"],folder=self.root/'process',owner=owner,cwd=self.root,timeout=3)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.cleanup["complete"])
        self.assertEqual(result.output_bytes, b"fixed-fixture\n")
        self.assertFalse(self.ledger.intent(self.key, "request")["new_intent"])
        self.assertEqual(self.ledger.settle(self.key, "request", token, receipt(raw_response_sha256=hashlib.sha256(result.output_bytes).hexdigest())), "settled")


if __name__ == "__main__":unittest.main()
