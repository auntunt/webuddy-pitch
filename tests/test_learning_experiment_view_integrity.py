"""Independent preparation anchors guard read visibility after direct DB corruption.

These are integrity faults injected through SQL, not simulated authorized API
writes. Fixtures use real personal registries, capture, create and seal; no
executor, service, model, or network is started.
"""
from contextlib import ExitStack, contextmanager
import copy
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.experiment_fixture import ExperimentFixture
from tmh.platform import learning as L, learning_runs as R
from tmh.platform import learning_experiments as X, learning_experiment_runs as XR
from tmh.platform import learning_experiment_views as V, server
from tmh.platform.errors import ApiError


class ExperimentViewIntegrityTests(ExperimentFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.P.project = self.store.project
        self.private_output = "SYNTHETIC-WITHHELD-OUTPUT-Ω\r\n" + "完整原文与尾空格  \r\n" * 30 + "END-WITHHELD"

    def prepare_run(self):
        # Keep the ordinary captured parent visible in mixed catalogs, matching
        # the independently observed private child-revision corruption case.
        self.revision = L.propose(self.P, self.p, self.revision["id"],
                                  L.encoded({"fix": self.private_output}), "owner")
        worker = self.worker()
        material = self.next_material(worker)
        self.assertIsNotNone(material)
        self.eid = worker.eid
        self.jid = self.exp(self.eid)["job_id"]
        self.rid = material["slot"]["run_id"]
        self.prompt = material["prompt"]
        # This saved string is a fixture, never claimed to be executor output.
        self.store.update_run(self.rid, output=self.private_output,
                              result=self.private_output, diff=self.private_output)
        return self.exp(self.eid)

    def req(self, actor, **query):
        return server.Req(SimpleNamespace(_who=actor, headers={}),
                          {key: [str(value)] for key, value in query.items()}, {}, actor)

    def routes(self, actor="alice"):
        return {
            "experiment": lambda: server.api_learning(self.P, self.req(actor, project=self.p["key"], experiment=self.eid)),
            "job": lambda: server.api_learning(self.P, self.req(actor, project=self.p["key"], job=self.jid)),
            "run": lambda: server.api_run(self.P, self.req(actor, prompt=1), str(self.rid)),
            "revision": lambda: server.api_learning(self.P, self.req(actor, project=self.p["key"], revision=self.revision["id"])),
            "catalog": lambda: server.api_learning(self.P, self.req(actor, project=self.p["key"], kind="lesson")),
        }

    def anchors(self, eid):
        return self.store.q("SELECT * FROM learning_experiment_events WHERE experiment_id=? AND kind IN ('create','seal') ORDER BY seq", (eid,))

    @contextmanager
    def corruption(self):
        # Respect the same authorization-before-Store order as the public read.
        with self.reg.authorization_guard(), self.store.lock:
            self.store.db.execute("SAVEPOINT view_integrity_fault")
            try:
                yield self.store.db
            finally:
                self.store.db.execute("ROLLBACK TO view_integrity_fault")
                self.store.db.execute("RELEASE view_integrity_fault")

    def read_snapshot(self):
        # The corruption is deliberately uncommitted. A separate connection's
        # backup cannot capture it, so read every schema object and every table
        # on this connection with a cursor-local tuple factory.
        cursor = self.store.db.cursor()
        cursor.row_factory = None
        try:
            schema = tuple(cursor.execute(
                "SELECT type,name,tbl_name,rootpage,sql FROM sqlite_master ORDER BY type,name").fetchall())
            tables = []
            for kind, name, _, _, _ in schema:
                if kind == "table":
                    quoted = '"' + name.replace('"', '""') + '"'
                    tables.append((name, tuple(cursor.execute("SELECT * FROM " + quoted).fetchall())))
            return schema, tuple(tables)
        finally:
            cursor.close()

    @contextmanager
    def readonly(self, *, mixed_catalog=False):
        before = self.read_snapshot()
        changes = self.store.db.total_changes
        attempted = []
        writes = {getattr(sqlite3, key) for key in (
            "SQLITE_INSERT", "SQLITE_UPDATE", "SQLITE_DELETE", "SQLITE_CREATE_TABLE",
            "SQLITE_CREATE_INDEX", "SQLITE_DROP_TABLE", "SQLITE_DROP_INDEX", "SQLITE_ALTER_TABLE")}
        def authorizer(code, first, second, database, trigger):
            if code in writes:
                attempted.append((code, first, second))
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        def forbidden(*args, **kwargs):
            raise AssertionError("read entered migration, recovery, live source or external execution")
        with ExitStack() as stack:
            for module, name in ((L, "schema"), (R, "schema"), (R, "get"), (R, "recover"),
                                 (X, "schema"), (X, "material_current"), (XR, "recover")):
                stack.enter_context(patch.object(module, name, side_effect=forbidden))
            if not mixed_catalog:
                stack.enter_context(patch.object(L, "binding", side_effect=forbidden))
                stack.enter_context(patch.object(L, "revision_current", side_effect=forbidden))
            # A mixed catalog may inspect an ordinary parent; it still cannot
            # write, recover, start a process or contact another service.
            stack.enter_context(patch("subprocess.Popen", side_effect=forbidden))
            stack.enter_context(patch("socket.create_connection", side_effect=forbidden))
            stack.enter_context(patch("socket.socket.connect", side_effect=forbidden))
            self.store.db.set_authorizer(authorizer)
            try:
                yield
            finally:
                self.store.db.set_authorizer(None)
        self.assertEqual(attempted, [])
        self.assertEqual(self.store.db.total_changes, changes)
        self.assertEqual(self.read_snapshot(), before)

    def rejected(self, call, *, mixed_catalog=False):
        with self.readonly(mixed_catalog=mixed_catalog):
            with self.assertRaises(ApiError) as caught:
                call()
            self.assertEqual(caught.exception.code, 409)

    def expose_except(self, withheld=None):
        assets = X.assets_in_tx(self.store.db, self.eid)
        ids = [asset["id"] for asset in assets if asset["id"] != withheld]
        return X.expose(self.P, self.p, self.eid, ids, self.exp(self.eid)["contract_hash"],
                        "alice", self.request("expose"))

    def replace_anchor(self, db, eid, kind, payload):
        db.execute("UPDATE learning_experiment_events SET payload=? WHERE experiment_id=? AND kind=?",
                   (X.encoded(payload), eid, kind))

    def duplicate_anchor(self, db, eid, kind):
        row = dict(db.execute("SELECT * FROM learning_experiment_events WHERE experiment_id=? AND kind=?", (eid, kind)).fetchone())
        row["seq"] = db.execute("SELECT MAX(seq)+1 AS n FROM learning_experiment_events WHERE experiment_id=?", (eid,)).fetchone()["n"]
        row["request_id"] = self.request("corrupt-anchor")
        db.execute("INSERT INTO learning_experiment_events(" + ",".join(row) + ") VALUES(" + ",".join("?" for _ in row) + ")", tuple(row.values()))

    def test_rehashed_missing_unexposed_oracle_rejected_by_all_read_routes(self):
        exp = self.prepare_run()
        assets = X.assets_in_tx(self.store.db, self.eid)
        withheld = next(asset for asset in assets if asset["kind"] == "oracle")
        self.expose_except(withheld["id"])
        before = V.run(self.P, self.p, self.rid, "alice", include_prompt=True)
        self.assertTrue(before["protected"])
        self.assertEqual(before["output"], "")
        original_anchors = self.anchors(self.eid)
        with self.corruption() as db:
            changed = copy.deepcopy(exp["contract"])
            del changed["asset_commitments"][withheld["id"]]
            changed_hash = X.digest(changed)
            db.execute("DELETE FROM learning_experiment_assets WHERE experiment_id=? AND id=?", (self.eid, withheld["id"]))
            db.execute("UPDATE learning_experiments SET contract=?,contract_hash=? WHERE id=?", (X.encoded(changed), changed_hash, self.eid))
            db.execute("UPDATE learning_jobs SET options=? WHERE id=?",
                       (X.encoded({"schema": X.VERSION, "managed_experiment_id": self.eid, "contract_hash": changed_hash}), self.jid))
            self.assertEqual(self.anchors(self.eid), original_anchors)
            for name, call in self.routes().items():
                with self.subTest(route=name):
                    self.rejected(call, mixed_catalog=name == "catalog")
            self.assertEqual(self.anchors(self.eid), original_anchors)
        self.assertEqual(self.exp(self.eid), exp)
        self.assertEqual(X.assets_in_tx(self.store.db, self.eid), assets)

    def test_rehashed_draft_also_requires_original_create_anchor(self):
        receipt = self.draft()
        eid = receipt["experiment_id"]
        exp = self.exp(eid)
        original = self.anchors(eid)
        with self.corruption() as db:
            changed = copy.deepcopy(exp["contract"])
            changed["roles"]["selector"] = "alice"
            db.execute("UPDATE learning_experiments SET contract=?,contract_hash=? WHERE id=?", (X.encoded(changed), X.digest(changed), eid))
            self.rejected(lambda: V.experiment(self.P, self.p, eid, "alice"))
            self.rejected(lambda: V.experiments(self.P, self.p, "alice"))
            self.assertEqual(self.anchors(eid), original)

    def test_missing_create_anchor_is_rejected_in_draft_and_sealed_reads(self):
        receipt = self.draft()
        eid = receipt["experiment_id"]
        for sealed in (False, True):
            if sealed:
                self.seal(receipt)
            with self.subTest(sealed=sealed), self.corruption() as db:
                db.execute("DELETE FROM learning_experiment_events WHERE experiment_id=? AND kind='create'", (eid,))
                self.rejected(lambda: V.experiment(self.P, self.p, eid, "curator"))

    def test_missing_or_duplicate_sealed_anchor_is_rejected(self):
        self.eid = self.seal()["experiment_id"]
        for kind in ("create", "seal"):
            with self.subTest(kind=kind, fault="duplicate"), self.corruption() as db:
                self.duplicate_anchor(db, self.eid, kind)
                self.rejected(lambda: V.experiment(self.P, self.p, self.eid, "curator"))
        with self.corruption() as db:
            db.execute("DELETE FROM learning_experiment_events WHERE experiment_id=? AND kind='seal'", (self.eid,))
            self.rejected(lambda: V.experiment(self.P, self.p, self.eid, "curator"))

    def test_anchor_payload_wrong_types_fail_with_409(self):
        eid = self.seal()["experiment_id"]
        for kind in ("create", "seal"):
            for payload in (None, [], "invalid", 7, True):
                with self.subTest(kind=kind, payload=payload), self.corruption() as db:
                    self.replace_anchor(db, eid, kind, payload)
                    self.rejected(lambda: V.experiment(self.P, self.p, eid, "curator"))

    def test_anchor_missing_or_wrong_hash_fails_with_409(self):
        eid = self.seal()["experiment_id"]
        for kind in ("create", "seal"):
            for payload in ({}, {"contract_hash": None}, {"contract_hash": []},
                            {"contract_hash": 7}, {"contract_hash": ""},
                            {"contract_hash": "A" * 64}, {"contract_hash": "0" * 64}):
                with self.subTest(kind=kind, payload=payload), self.corruption() as db:
                    self.replace_anchor(db, eid, kind, payload)
                    self.rejected(lambda: V.experiment(self.P, self.p, eid, "curator"))

    def test_anchor_noninteger_and_out_of_order_sequence_fails_with_409(self):
        eid = self.seal()["experiment_id"]
        for kind, seq in (("create", 0), ("create", 1000), ("create", "bad-seq"),
                          ("seal", 0), ("seal", "bad-seq")):
            with self.subTest(kind=kind, seq=seq), self.corruption() as db:
                db.execute("UPDATE learning_experiment_events SET seq=? WHERE experiment_id=? AND kind=?", (seq, eid, kind))
                self.rejected(lambda: V.experiment(self.P, self.p, eid, "curator"))

    def test_unsealed_draft_rejects_unexpected_seal_event(self):
        d = self.draft()
        with self.corruption() as db:
            db.execute("INSERT INTO learning_experiment_events VALUES(?,?,?,?,?,?,?,?)", (
                d["experiment_id"], 2, "seal", "owner", "corrupt-seal", "fault",
                X.encoded({"contract_hash": d["contract_hash"]}), "fixture"))
            self.rejected(lambda: V.experiment(self.P, self.p, d["experiment_id"], "curator"))

    def test_draft_and_cancelled_before_seal_are_valid_without_seal(self):
        d = self.draft()
        eid = d["experiment_id"]
        for cancelled in (False, True):
            if cancelled:
                X.cancel(self.P, self.p, eid, "owner", self.request("cancel"))
            for actor in ("alice", "curator"):
                with self.subTest(cancelled=cancelled, actor=actor), self.readonly():
                    value = V.experiment(self.P, self.p, eid, actor)
                    self.assertEqual(value["state"], "cancelled" if cancelled else "draft")
                    self.assertEqual(value["protected"], actor != "curator")
                    self.assertFalse(value["rsi_qualified"])
            self.assertEqual([event["kind"] for event in self.anchors(eid)], ["create"])
            self.assertEqual(self.anchors(eid)[0]["seq"], 1)

    def test_empty_partial_full_exposure_and_historical_sealed_reads_remain_lossless(self):
        self.prepare_run()
        for actor in ("alice", "curator"):
            for name, call in self.routes(actor).items():
                with self.subTest(actor=actor, route=name), self.readonly(mixed_catalog=name == "catalog"):
                    value = call()
                    if actor == "alice":
                        self.assertNotIn(self.private_output, json.dumps(value, ensure_ascii=False))
                    if name == "run":
                        self.assertEqual(value["protected"], actor != "curator")
                        self.assertEqual(value["output"], self.private_output if actor == "curator" else "")
                        self.assertEqual(value["prompt"], self.prompt if actor == "curator" else "")
        oracle = next(asset for asset in X.assets_in_tx(self.store.db, self.eid) if asset["kind"] == "oracle")
        self.expose_except(oracle["id"])
        with self.readonly():
            self.assertTrue(V.run(self.P, self.p, self.rid, "alice")["protected"])
            self.assertTrue(V.job(self.P, self.p, self.jid, "alice")["protected"])
        self.expose_except()
        X.cancel(self.P, self.p, self.eid, "owner", self.request("cancel-sealed"))
        with self.readonly():
            value = V.run(self.P, self.p, self.rid, "alice", include_prompt=True)
            self.assertFalse(value["protected"])
            self.assertEqual(value["output"], self.private_output)
            self.assertEqual(value["prompt"], self.prompt)
            self.assertEqual(value["currentness"], "not_checked")
            self.assertFalse(V.job(self.P, self.p, self.jid, "alice")["protected"])
            self.assertEqual(V.experiment(self.P, self.p, self.eid, "curator")["state"], "cancelled")

    def test_bad_anchor_json_is_rejected_without_writes_or_live_probes(self):
        eid = self.seal()["experiment_id"]
        with self.corruption() as db:
            db.execute("UPDATE learning_experiment_events SET payload=? WHERE experiment_id=? AND kind='create'", ("{incomplete", eid))
            self.rejected(lambda: V.experiment(self.P, self.p, eid, "alice"))


if __name__ == "__main__":
    unittest.main()
