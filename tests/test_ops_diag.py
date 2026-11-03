"""运维排查：相似经验和工单、只读查业务数据（写语句一律拒绝）、记下结论，不改代码的结论可以沉淀为经验候选（人工采用后生效）。"""
import json
import sqlite3
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from test_run_steer import RunSteerTest

from tmh.platform import learn, ops_diag
from tmh.platform.errors import ApiError


class OpsDiagTest(RunSteerTest):
    test_hint_only_for_working_modes = test_say_reaches_notes_log_and_ticket = test_finished_run_refuses = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        db = cls.data / "bid.db"
        c = sqlite3.connect(db)
        c.executescript("CREATE TABLE bid(no TEXT, amount REAL, unit TEXT);"
                        "INSERT INTO bid VALUES('ZB-001', 356.5, '万元'), ('ZB-002', 3565000, '元'), ('ZB-003', 128, '万元');")
        c.commit()
        c.close()
        (cls.data / "datasources.json").write_text(json.dumps({"ST": {"kind": "sqlite", "path": str(db)}}), encoding="utf-8")
        code, t = cls.call(cls, "POST", "/api/tickets", {"project": "ST", "title": "标书 ZB-002 投标金额异常偏大", "type": "ops",
                                                          "body": "客户反馈评标报告里 ZB-002 的投标金额大了一万倍"})
        assert code == 200, t
        cls.ops = t["key"]

    def test_only_reads(self):
        for bad in ("UPDATE bid SET unit='万元'", "select 1; drop table bid", "DELETE FROM bid", "PRAGMA writable_schema=1",
                    "WITH x AS (SELECT 1) INSERT INTO bid SELECT * FROM bid", ""):
            with self.assertRaises(ApiError, msg=bad):
                ops_diag.clean_sql(bad)
        self.assertEqual(self.call("POST", "/api/tickets/%s/ops" % self.ops, {"action": "query", "sql": "update bid set amount=0"})[0], 400)
        c = sqlite3.connect(self.data / "bid.db")
        self.assertEqual(c.execute("SELECT count(*) FROM bid WHERE amount>0").fetchone()[0], 3)
        c.close()

    def test_query_conclude_and_distill(self):
        code, r = self.call("POST", "/api/tickets/%s/ops" % self.ops,
                            {"action": "query", "sql": "-- 金额单位\nSELECT no, amount, unit FROM bid WHERE unit <> '万元';"})
        self.assertEqual(code, 200, r)
        self.assertEqual(r["columns"], ["no", "amount", "unit"])
        self.assertEqual(r["rows"], [["ZB-002", 3565000, "元"]])
        t = self.P.store.ticket(self.ops)
        self.assertIn("ops_query", [e["kind"] for e in self.P.store.events(t["id"])])
        self.assertEqual(self.call("POST", "/api/tickets/%s/ops" % self.ops, {"action": "conclude", "cause": "x", "text": "a"})[0], 400)
        code, r = self.call("POST", "/api/tickets/%s/ops" % self.ops,
                            {"action": "conclude", "cause": "data", "text": "单位把万元填成了元，金额放大一万倍", "fix": "请客户改正单位", "distill": True})
        self.assertEqual(code, 200, r)
        card = learn.lesson(self.data, r["lesson"])
        self.assertEqual(card["status"], "candidate")
        self.assertIn("不改代码", card["fix"])
        self.assertEqual(self.P.store.ticket(self.ops)["status"], t["status"])  # recording a cause does not close it for anyone
        code, t2 = self.call("POST", "/api/tickets", {"project": "ST", "title": "标书 ZB-009 投标金额异常", "type": "ops", "body": "金额大了一万倍"})
        look = self.call("GET", "/api/tickets/%s/ops" % t2["key"])[1]
        self.assertEqual(look["datasource"], {"kind": "sqlite"})
        self.assertIn(r["lesson"], [x["id"] for x in look["lessons"]])
        hit = next(x for x in look["tickets"] if x["key"] == self.ops)
        self.assertIn("万元填成了元", hit["conclusion"])

    def test_no_source_configured(self):
        self.assertEqual(ops_diag.source(self.data, "NOPE"), {})


if __name__ == "__main__":
    unittest.main()
