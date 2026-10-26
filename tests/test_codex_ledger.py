"""Real temporary SQLite connections; no model, real contract or trial window."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from scripts.rsi.codex_ledger import Ledger, Conflict, Stopped


def contract(limit=2):
    return {"schema": "codex-learning-finite-v1", "root_id": "a" * 64, "tenant": "synthetic",
            "project_id": 1, "application_commit": "b" * 40, "baseline_sha256": "c" * 64,
            "candidate_sha256": "d" * 64, "client": {"engine": "codex", "requested_model": "synthetic",
            "profile_sha256": "e" * 64, "executable_sha256": "f" * 64},
            "limits": {"max_outer_starts": limit, "total_timeout_seconds": 10},
            "accounting": {"unit": "cli_outer_start", "total_tokens_cap": None, "total_cost_cap": None}}


class Clock:
    wall = 1000000
    mono = 0.


class CodexLedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="codex-ledger-")
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.path = self.folder / "synthetic.sqlite"
        self.clock = Clock()
        self.ledger = self.connect()
        self.addCleanup(self.ledger.close)
        self.spec = contract()
        self.root = self.spec["root_id"]
        self.deadline = self.clock.wall + 10000000
        self.register()

    def connect(self):
        return Ledger(self.path, generation="synthetic-generation", wall_us=lambda: self.clock.wall,
                      monotonic=lambda: self.clock.mono)

    def register(self, ledger=None, spec=None, deadline=None):
        return (ledger or self.ledger).register(spec or self.spec, starts_us=1000000,
                                              deadline_us=self.deadline if deadline is None else deadline)

    def reserve(self, request="R1", ledger=None):
        return (ledger or self.ledger).reserve(self.root, request, phase="B", input_sha256="1" * 64)

    def intent(self, request="R1"):
        self.reserve(request)
        return self.ledger.intent(self.root, request)["intent_token"]

    def settle(self, token, request="R1", outcome="completed"):
        return self.ledger.settle(self.root, request, token, observation_sha256="2" * 64,
                                  reported_outcome=outcome)

    def snapshot(self):
        return self.ledger.snapshot(self.root)

    def test_fixed_registration_and_window_cannot_be_refreshed(self):
        before = self.snapshot()
        self.assertEqual(before, self.register())
        for spec, deadline in ((dict(self.spec, tenant="different"), self.deadline),
                               (self.spec, self.deadline + 1)):
            with self.assertRaises(ValueError):
                self.register(spec=spec, deadline=deadline)
        # Still ten seconds, so only the persisted fixed-window binding can reject it.
        with self.assertRaises(Conflict):
            self.ledger.register(self.spec, starts_us=1000001, deadline_us=self.deadline + 1)
        self.assertEqual(before, self.snapshot())

    def test_unknown_metering_does_not_mean_unknown_execution_or_zero(self):
        token = self.intent()
        result = self.settle(token)
        self.assertEqual(result["state"], "settled")
        self.assertIs(result["execution_admitted"], False)
        snapshot = self.snapshot()
        self.assertEqual(snapshot["root"]["status"], "open")
        self.assertEqual(snapshot["reserved_total"], 1)
        self.assertEqual(snapshot["intent_total"], 1)
        self.assertIsNone(snapshot["actual_outer_exec_count"])
        self.assertIsNone(snapshot["task_acceptance"])
        self.assertEqual(snapshot["usage"]["status"], "unknown")
        self.assertIsNone(snapshot["usage"]["input_tokens"])
        self.assertIsNone(snapshot["actual_cost"]["amount"])
        self.assertEqual(self.reserve("R2")["state"], "reserved")

    def test_request_replay_and_cumulative_limit_survive_new_connection(self):
        token = self.intent()
        self.assertFalse(self.ledger.intent(self.root, "R1")["new_intent"])
        self.settle(token)
        self.assertEqual(self.reserve()["intent_token"], token)
        other = self.connect()
        self.addCleanup(other.close)
        self.reserve("R2", other)
        second = other.intent(self.root, "R2")["intent_token"]
        other.settle(self.root, "R2", second, observation_sha256="2" * 64, reported_outcome="completed")
        for handle in (other, self.ledger):
            with self.assertRaises(Conflict):
                self.reserve("new-request", handle)
        self.assertEqual(self.snapshot()["reserved_total"], 2)
        self.assertEqual(self.snapshot()["intent_total"], 2)

    def test_input_and_settlement_replay_must_match(self):
        token = self.intent()
        before = self.snapshot()
        with self.assertRaises(Conflict):
            self.ledger.reserve(self.root, "R1", phase="B", input_sha256="3" * 64)
        with self.assertRaises(Conflict):
            self.settle("wrong-owner-token")
        self.assertEqual(before, self.snapshot())
        self.settle(token)
        before = self.snapshot()
        with self.assertRaises(Conflict):
            self.ledger.settle(self.root, "R1", token, observation_sha256="3" * 64, reported_outcome="completed")
        self.assertEqual(before, self.snapshot())

    def race(self, same_request):
        barrier = threading.Barrier(2, timeout=5)
        results, errors = [], []
        def worker(number):
            handle = self.connect()
            try:
                barrier.wait()
                request = "same" if same_request else "R" + str(number)
                self.reserve(request, handle)
                results.append(handle.intent(self.root, request))
            except BaseException as exc:
                errors.append(exc)
            finally:
                handle.close()
        threads = [threading.Thread(target=worker, args=(n,)) for n in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
            self.assertFalse(thread.is_alive())
        return results, errors

    def test_two_connections_same_slot_get_only_one_new_intent(self):
        results, errors = self.race(True)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(v["new_intent"] for v in results), 1)
        self.assertEqual(len({v["intent_token"] for v in results}), 1)
        self.assertEqual(self.snapshot()["reserved_total"], 1)

    def test_two_connections_different_requests_cannot_duplicate_active_slot(self):
        results, errors = self.race(False)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], Conflict)
        self.assertEqual(self.snapshot()["reserved_total"], 1)
        self.assertEqual(self.snapshot()["intent_total"], 1)

    def install_failure(self, kind):
        self.ledger.db.execute("CREATE TRIGGER synthetic_failure BEFORE INSERT ON codex_learning_events "
                               "WHEN NEW.kind='" + kind + "' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")

    def test_reservation_event_failure_rolls_back_slot_and_budget(self):
        before = self.snapshot()
        self.install_failure("reserved")
        with self.assertRaises(sqlite3.IntegrityError):
            self.reserve()
        self.assertEqual(before, self.snapshot())
        self.ledger.db.execute("DROP TRIGGER synthetic_failure")
        self.assertEqual(self.reserve()["state"], "reserved")
        self.assertEqual(self.snapshot()["reserved_total"], 1)

    def test_intent_event_failure_rolls_back_token(self):
        self.reserve()
        before = self.snapshot()
        self.install_failure("intent")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.intent(self.root, "R1")
        self.assertEqual(before, self.snapshot())
        self.ledger.db.execute("DROP TRIGGER synthetic_failure")
        self.assertTrue(self.ledger.intent(self.root, "R1")["new_intent"])

    def test_stop_event_failure_rolls_back_as_one_transaction(self):
        token = self.intent()
        before = self.snapshot()
        self.install_failure("stopped")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ledger.unknown(self.root, "R1", token, reason="synthetic lost result")
        self.assertEqual(before, self.snapshot())
        with self.assertRaises(Conflict):
            self.reserve("no-duplicate")
        self.ledger.db.execute("DROP TRIGGER synthetic_failure")
        self.assertEqual(self.ledger.unknown(self.root, "R1", token, reason="synthetic lost result")["root"]["status"], "execution_unknown")

    def test_cancel_before_intent_does_not_refund_or_reopen(self):
        self.reserve()
        result = self.ledger.cancel(self.root)
        self.assertEqual(result["attempts"][0]["state"], "cancelled")
        self.assertEqual(result["reserved_total"], 1)
        self.assertEqual(result["intent_total"], 0)
        with self.assertRaises(Stopped):
            self.reserve("replacement")
        self.assertEqual(self.snapshot()["root"]["status"], "cancelled")
        reopened = self.connect()
        self.addCleanup(reopened.close)
        self.assertEqual(self.register(ledger=reopened)["root"]["status"], "cancelled")
        self.assertEqual(reopened.snapshot(self.root)["reserved_total"], 1)
        with self.assertRaises(Stopped):
            self.reserve("reopened-no-refill", reopened)

    def test_cancel_after_intent_is_unknown_not_zero_starts(self):
        token = self.intent()
        result = self.ledger.cancel(self.root)
        self.assertEqual(result["attempts"][0]["state"], "unknown")
        self.assertEqual(result["intent_total"], 1)
        self.assertIsNone(result["actual_outer_exec_count"])
        with self.assertRaises(Stopped):
            self.settle(token)

    def test_unknown_cannot_be_resurrected_or_relabelled_by_metering(self):
        token = self.intent()
        self.ledger.unknown(self.root, "R1", token, reason="result unavailable")
        for request in ("R1", "replacement"):
            with self.assertRaises(Stopped):
                self.reserve(request)
        with self.assertRaises(Stopped):
            self.settle(token)
        result = self.ledger.reconcile(self.root)
        self.assertEqual(result["root"]["status"], "execution_unknown")
        self.assertEqual(result["reserved_total"], 1)
        self.assertEqual(result["usage"]["status"], "unknown")

    def test_deadline_stop_commits_despite_operation_denial(self):
        token = self.intent()
        self.clock.wall = self.deadline
        with self.assertRaises(Stopped):
            self.settle(token)
        result = self.snapshot()
        self.assertEqual(result["root"]["status"], "expired")
        self.assertEqual(result["attempts"][0]["state"], "unknown")
        self.assertEqual(result["root"]["deadline_us"], self.deadline)
        self.assertEqual(result["reserved_total"], 1)

    def test_monotonic_expiry_and_wall_rollback_stop(self):
        self.reserve()
        self.clock.mono = 11.
        with self.assertRaises(Stopped):
            self.ledger.intent(self.root, "R1")
        self.assertEqual(self.snapshot()["root"]["status"], "expired")
        second = dict(self.spec, root_id="9" * 64)
        self.clock.mono = 0.
        self.ledger.register(second, starts_us=1000000, deadline_us=self.deadline)
        self.clock.wall -= 1
        self.assertEqual(self.ledger.reconcile(second["root_id"])["root"]["status"], "clock_reversed")

    def test_new_process_preserves_intent_count_deadline_and_latches_generation_loss(self):
        token = self.intent()
        code = ("import json,sys;from scripts.rsi.codex_ledger import Ledger;"
                "l=Ledger(sys.argv[1]);print(json.dumps(l.reconcile(sys.argv[2])));l.close()")
        result = subprocess.run([sys.executable, "-c", code, str(self.path), self.root],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        snapshot = json.loads(result.stdout)
        self.assertEqual(snapshot["root"]["status"], "generation_lost")
        self.assertEqual(snapshot["root"]["deadline_us"], self.deadline)
        self.assertEqual(snapshot["reserved_total"], 1)
        self.assertEqual(snapshot["intent_total"], 1)
        self.assertEqual(snapshot["attempts"][0]["state"], "unknown")
        with self.assertRaises(Stopped):
            self.settle(token)
        with self.assertRaises(Stopped):
            self.reserve("new-process-no-refill")

    def test_reported_failure_latches_stop_without_claiming_task_acceptance(self):
        self.settle(self.intent(), outcome="failed")
        result = self.snapshot()
        self.assertEqual(result["root"]["status"], "reported_failure")
        self.assertEqual(result["attempts"][0]["state"], "settled")
        self.assertIsNone(result["task_acceptance"])
        with self.assertRaises(Stopped):
            self.reserve("replacement")

    def test_only_independent_namespace_and_no_implicit_caller_commit(self):
        self.ledger.db.execute("CREATE TABLE legacy_synthetic_sentinel(value TEXT)")
        self.ledger.db.execute("INSERT INTO legacy_synthetic_sentinel VALUES('original')")
        handle = self.connect()
        self.addCleanup(handle.close)
        self.assertEqual(handle.db.execute("SELECT * FROM legacy_synthetic_sentinel").fetchall()[0][0], "original")
        names = {r[0] for r in handle.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual({n for n in names if n.startswith('codex_learning_')},
                         {"codex_learning_roots", "codex_learning_attempts", "codex_learning_events"})
        self.assertFalse(any(n.startswith("rsi_prepare_") for n in names))
        self.ledger.db.execute("BEGIN")
        with self.assertRaises(Conflict):
            self.reserve()
        self.assertTrue(self.ledger.db.in_transaction)
        self.ledger.db.rollback()

    def test_unsafe_journal_or_sync_cannot_claim_durable_reservation(self):
        before = self.snapshot()
        for pragma in ("PRAGMA journal_mode=OFF", "PRAGMA synchronous=OFF"):
            self.ledger.db.execute("PRAGMA journal_mode=DELETE")
            self.ledger.db.execute("PRAGMA synchronous=FULL")
            self.ledger.db.execute(pragma)
            with self.subTest(pragma=pragma), self.assertRaises(Conflict):
                self.reserve()
            self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
