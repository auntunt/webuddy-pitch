"""The read-only assertions must keep detecting any database change."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from tests.sqlite_snapshot import dump_store
from tmh.platform.store import Store


class SQLiteSnapshotTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / "platform.db")
        self.addCleanup(self.store.db.close)

    def test_complete_schema_and_values_survive_without_changing_live_factory(self):
        self.store.db.executescript("""
            CREATE TABLE sample(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT, raw BLOB);
            CREATE INDEX sample_text ON sample(text);
            CREATE VIEW sample_view AS SELECT * FROM sample;
            CREATE TABLE audit(id INTEGER);
            CREATE TRIGGER sample_added AFTER INSERT ON sample
                BEGIN INSERT INTO audit VALUES(new.id); END;
        """)
        self.store.x("INSERT INTO sample(text,raw) VALUES(?,?)", ("完整\n文本'🙂", b"\x00\xff"))
        self.store.x("INSERT INTO sample(text,raw) VALUES(?,?)", (None, b""))
        factory = self.store.db.row_factory
        before = dump_store(self.store)
        self.assertIs(self.store.db.row_factory, factory)
        self.assertIsInstance(self.store.one("SELECT * FROM sample WHERE id=1"), dict)
        with closing(sqlite3.connect(":memory:")) as restored:
            restored.executescript("\n".join(before))
            self.assertEqual(restored.execute("SELECT * FROM sample_view ORDER BY id").fetchall(),
                             [(1, "完整\n文本'🙂", b"\x00\xff"), (2, None, b"")])
            self.assertEqual(restored.execute("SELECT * FROM audit ORDER BY id").fetchall(), [(1,), (2,)])
            self.assertEqual(restored.execute("SELECT seq FROM sqlite_sequence WHERE name='sample'").fetchone(), (2,))
            self.assertEqual(tuple(restored.iterdump()), before)
            restored.execute("INSERT INTO sample(text) VALUES('trigger still present')")
            self.assertEqual(restored.execute("SELECT id FROM audit ORDER BY id DESC LIMIT 1").fetchone(), (3,))
        self.store.x("UPDATE sample SET text=? WHERE id=1", ("changed",))
        changed = dump_store(self.store)
        self.assertNotEqual(changed, before)
        self.store.x("CREATE TABLE added_schema(value TEXT)")
        self.assertNotEqual(dump_store(self.store), changed)

    def test_pending_writes_fail_without_committing_or_hiding_them(self):
        self.store.x("CREATE TABLE pending(value TEXT)")
        before = dump_store(self.store)
        self.store.db.execute("INSERT INTO pending VALUES('uncommitted')")
        with self.assertRaisesRegex(AssertionError, "committed fixture"):
            dump_store(self.store)
        self.assertTrue(self.store.db.in_transaction)
        self.assertEqual(self.store.one("SELECT value FROM pending"), {"value": "uncommitted"})
        self.store.db.rollback()
        self.assertEqual(dump_store(self.store), before)
