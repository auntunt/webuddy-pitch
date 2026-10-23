"""Legacy receipt migration preserves all evidence and assigns no new owner."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from tmh.platform import agent_api, candidates, harness_probes
from tmh.platform.store import Store


LEGACY_COLUMNS = ("agent", "request_id", "operation", "fingerprint", "arguments", "resource",
                  "state", "result", "error", "created", "updated")
LEGACY_SCHEMA = """
CREATE TABLE agent_requests (
  agent TEXT NOT NULL, request_id TEXT NOT NULL, operation TEXT NOT NULL,
  fingerprint TEXT NOT NULL, arguments TEXT NOT NULL, resource TEXT NOT NULL,
  state TEXT NOT NULL, result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
  created TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(agent, request_id));
CREATE TABLE agent_run_sources (
  run_id INTEGER PRIMARY KEY, ticket_id INTEGER NOT NULL, requirement_hash TEXT NOT NULL,
  agent TEXT NOT NULL, created TEXT NOT NULL);
"""


class AgentReceiptMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-agent-receipt-migration-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "platform.db"
        self.stores = []
        self.addCleanup(self.close_stores)
        self.store = self.open_store()
        # Existing prerequisite schemas are real. This migration test does not
        # depend on unrelated candidate/probe schema changes being pending.
        candidates.schema(self.store)
        harness_probes.schema(self.store)
        self.store.db.executescript(LEGACY_SCHEMA)
        for index, state in enumerate(("complete", "failed", "pending", "uncertain")):
            for agent in ("agent:claude", "agent:member:alice"):
                # Preserve exact JSON serialization, CRLF, trailing whitespace,
                # unknown outcomes and even a legacy label resembling a person.
                args = json.dumps({"ticket": "SAME-1", "body": "  原文\r\n记录\t \r\n" * 70,
                                   "request_id": "same-request-%d" % index}, ensure_ascii=False, indent=2)
                row = (agent, "same-request-%d" % index, "message_send", "a" * 64, args,
                       "ticket:1", state,
                       '{ "event_id": 13, "body": "完整结果" }' if state == "complete" else "",
                       '{ "code": 409, "message": "原样保留" }' if state == "failed" else "",
                       "2026-10-19 01:02:03", "2026-10-20 04:05:06")
                self.store.db.execute("INSERT INTO agent_requests VALUES (%s)" % ",".join("?" for _ in row), row)
        self.store.db.execute("INSERT INTO agent_run_sources VALUES(?,?,?,?,?)",
                              (17, 1, "b" * 64, "agent:claude", "2026-10-19 01:02:03"))
        self.store.db.commit()
        self.before_rows = self.legacy_rows(self.store)
        self.before_sources = self.store.q("SELECT * FROM agent_run_sources ORDER BY run_id")

    def open_store(self):
        store = Store(self.path)
        self.stores.append(store)
        return store

    def close_stores(self):
        for store in self.stores:
            store.db.close()

    def legacy_rows(self, store):
        return store.q("SELECT %s FROM agent_requests ORDER BY agent,request_id" % ",".join(LEGACY_COLUMNS))

    def assert_preserved(self, store):
        self.assertEqual(self.legacy_rows(store), self.before_rows)
        self.assertEqual(store.q("SELECT * FROM agent_run_sources ORDER BY run_id"), self.before_sources)
        self.assertEqual(store.q("PRAGMA integrity_check"), [{"integrity_check": "ok"}])

    def test_all_legacy_fields_preserved_without_inferred_personal_identity(self):
        agent_api._schema(self.store)
        self.assert_preserved(self.store)
        rows = self.store.q("SELECT * FROM agent_requests ORDER BY agent,request_id")
        self.assertEqual(len(rows), 8)
        self.assertTrue(any(row["agent"] == "agent:member:alice" for row in rows))
        self.assertEqual({(row["principal"], row["connection_id"]) for row in rows}, {("", "")})
        columns = {row["name"]: row for row in self.store.q("PRAGMA table_info(agent_requests)")}
        for column in ("principal", "connection_id"):
            self.assertEqual(columns[column]["notnull"], 1)
            self.assertEqual(columns[column]["dflt_value"], "''")
        for row in rows:
            receipt = agent_api._receipt(row)
            self.assertEqual(receipt["principal"], "")
            self.assertEqual(receipt["connection_id"], "")
            self.assertEqual(receipt["needs_reconcile"], row["state"] in ("pending", "uncertain"))
        migrated = self.store.q("SELECT * FROM agent_requests ORDER BY agent,request_id")
        agent_api._schema(self.store)
        self.assertEqual(self.store.q("SELECT * FROM agent_requests ORDER BY agent,request_id"), migrated)
        reopened = self.open_store()
        self.assert_preserved(reopened)
        self.assertEqual(reopened.q("SELECT * FROM agent_requests ORDER BY agent,request_id"), migrated)

    def test_two_independent_store_connections_migrate_concurrently(self):
        second = self.open_store()
        self.assertIsNot(second.db, self.store.db)
        self.assertIsNot(second.lock, self.store.lock)
        start = threading.Barrier(2)
        def migrate(store):
            start.wait(timeout=3)
            agent_api._schema(store)
            return store.q("SELECT * FROM agent_requests ORDER BY agent,request_id")
        with ThreadPoolExecutor(max_workers=2) as workers:
            first_job = workers.submit(migrate, self.store)
            second_job = workers.submit(migrate, second)
            first_rows, second_rows = first_job.result(timeout=10), second_job.result(timeout=10)
        self.assertEqual(first_rows, second_rows)
        for store in (self.store, second):
            self.assert_preserved(store)
            names = [row["name"] for row in store.q("PRAGMA table_info(agent_requests)")]
            self.assertEqual(names, list(LEGACY_COLUMNS) + ["principal", "connection_id"])
            self.assertTrue(all(row["principal"] == row["connection_id"] == "" for row in first_rows))
            self.assertFalse(store.db.in_transaction)

    def test_real_sqlite_failure_before_second_alter_rolls_back_first_alter(self):
        alters = []
        def authorizer(action, table_database, table, *_rest):
            if action == sqlite3.SQLITE_ALTER_TABLE and table == "agent_requests":
                alters.append((table_database, table))
                if len(alters) == 2:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        self.store.db.set_authorizer(authorizer)
        try:
            with self.assertRaises(sqlite3.DatabaseError) as caught:
                agent_api._schema(self.store)
            self.assertIn("authorized", str(caught.exception))
        finally:
            self.store.db.set_authorizer(None)
        self.assertEqual(alters, [("main", "agent_requests"), ("main", "agent_requests")])
        self.assertFalse(self.store.db.in_transaction)
        self.assertEqual([row["name"] for row in self.store.q("PRAGMA table_info(agent_requests)")], list(LEGACY_COLUMNS))
        self.assert_preserved(self.store)
        observer = self.open_store()
        self.assertEqual([row["name"] for row in observer.q("PRAGMA table_info(agent_requests)")], list(LEGACY_COLUMNS))
        self.assert_preserved(observer)
        # A real retry after removing the fault can finish, with no data repair,
        # dropped receipts or fictitious ownership assigned to the historical rows.
        agent_api._schema(observer)
        self.assert_preserved(observer)
        self.assertTrue(all(row["principal"] == row["connection_id"] == ""
                            for row in observer.q("SELECT * FROM agent_requests")))

    def test_existing_new_receipt_ownership_survives_repeated_schema_checks(self):
        agent_api._schema(self.store)
        self.store.db.execute("UPDATE agent_requests SET principal=?,connection_id=? WHERE agent=? AND request_id=?",
                              ("alice", "c" * 32, "agent:member:alice", "same-request-0"))
        self.store.db.commit()
        before = self.store.q("SELECT * FROM agent_requests ORDER BY agent,request_id")
        agent_api._schema(self.store)
        other = self.open_store()
        agent_api._schema(other)
        self.assertEqual(other.q("SELECT * FROM agent_requests ORDER BY agent,request_id"), before)
        self.assert_preserved(other)
