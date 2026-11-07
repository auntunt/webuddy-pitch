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

    def test_lists_the_tables_that_can_be_queried(self):
        code, d = self.call("GET", f"/api/tickets/{self.ops}/ops")
        self.assertEqual(code, 200, d)
        self.assertEqual(d["datasource"]["tables"], [{"name": "bid", "columns": ["no", "amount", "unit"]}])
        self.assertEqual(ops_diag.tables({"kind": "sqlite", "path": str(self.data / "missing.db")}), [])

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
        self.assertEqual(look["datasource"], {"kind": "sqlite", "tables": [{"name": "bid", "columns": ["no", "amount", "unit"]}]})
        self.assertIn(r["lesson"], [x["id"] for x in look["lessons"]])
        hit = next(x for x in look["tickets"] if x["key"] == self.ops)
        self.assertIn("万元填成了元", hit["conclusion"])

    def test_auto_line_leaves_ops_tickets_alone(self):
        on = dict(self.P.flow.autoflow(), on=True)
        t = self.P.store.ticket(self.ops)
        self.assertEqual(self.P.flow.next_step(t, on)[0], "")
        (self.data / "autoflow.json").write_text(json.dumps({"on": ["ST"], "plan": True, "fix": True}), encoding="utf-8")
        try:
            self.P.flow._intake(self.P.project("ST"), t)
        finally:
            (self.data / "autoflow.json").unlink()
        self.assertFalse(self.P.store.runs(ticket_id=t["id"]))
        self.assertIn("运维工单不自动改代码", self.P.store.events(t["id"])[-1]["body"])

    def test_an_ops_ticket_with_open_criteria_does_not_promise_to_start_on_the_answer(self):
        from tmh.platform import intake
        self.assertIn("运维工单不自动改代码", intake.open_ac_note({"type": "ops"}))
        self.assertIn("答复回来就自动开始", intake.open_ac_note({"type": "feature"}))

    def test_no_source_configured(self):
        self.assertEqual(ops_diag.source(self.data, "NOPE"), {})


if __name__ == "__main__":
    unittest.main()


class OpsDiagUiTest(unittest.TestCase):
    def test_a_rerender_keeps_the_typed_query_and_its_result(self):
        import re as _re
        import shutil
        import subprocess
        from tmh.platform import ui_work
        if not shutil.which("node"):
            self.skipTest("node not installed")
        src = Path(ui_work.__file__).read_text(encoding="utf-8")
        fn = _re.search(r"async function opsDiag\(key\)\{.*?\n(?=async function ticketTopWire)", src, _re.S).group(0)
        js = r"""
const assert=require('node:assert/strict');const h=s=>String(s??'');const S={};let toastMsg='';const toast=m=>{toastMsg=m};
const els={};const mk=id=>els[id]||(els[id]={id,value:'',innerHTML:'',disabled:false});
const box={set innerHTML(v){this._h=v;for(const k of Object.keys(els))if(k!=='opsDiag')delete els[k];for(const m of v.matchAll(/id="(\w+)"/g))mk(m[1])},get innerHTML(){return this._h}};
els.opsDiag=box;const $=q=>els[q.slice(1)]||null;
const d={lessons:[],tickets:[],datasource:{kind:'sqlite'},queries:[],conclusion:null,causes:{data:'数据问题'}};
const get=async()=>d;const post=async(u,b)=>({count:1,ms:2,more:false,columns:['no'],rows:[['ZB-002']]});
%s
(async()=>{await opsDiag('ST-1');$('#opsSql').value='SELECT no FROM bid';$('#opsSql').oninput();await $('#opsRun').onclick();
assert.match($('#opsOut').innerHTML,/ZB-002/);
await opsDiag('ST-1');
assert.equal($('#opsSql').value,'SELECT no FROM bid');assert.match($('#opsOut').innerHTML,/ZB-002/);
})().catch(e=>{console.error(e);process.exit(1)});
""" % fn
        r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
