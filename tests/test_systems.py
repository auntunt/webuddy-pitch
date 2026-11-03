"""客户 → 项目 → 系统三级归档：系统挂在项目下；需求对话和工单归到本项目的一个系统；从对话建的单、大需求的子单跟着走。"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from test_run_steer import RunSteerTest

from tmh.platform import workbench


class SystemsTest(RunSteerTest):
    test_hint_only_for_working_modes = test_say_reaches_notes_log_and_ticket = test_finished_run_refuses = None

    def test_system_belongs_to_project_and_files_tickets(self):
        code, s = self.call("POST", "/api/projects/ST/systems", {"name": "开评标系统（私有化）"})
        self.assertEqual(code, 200, s)
        self.assertEqual(self.call("POST", "/api/projects/ST/systems", {"name": "开评标系统（私有化）"})[0], 409)
        self.assertEqual(self.call("POST", "/api/projects/ST/systems", {"name": " "})[0], 400)
        key = self.ticket["key"]
        code, r = self.call("POST", "/api/tickets/%s/system" % key, {"system": s["id"]})
        self.assertEqual(code, 200, r)
        t = self.P.store.ticket(key)
        self.assertEqual(t["links"]["system"], s["id"])
        self.assertIn("system", [e["kind"] for e in self.P.store.events(t["id"])])
        # a write from an older copy of the ticket keeps the system
        self.P.store.update_ticket(t["id"], "x", links={})
        self.assertEqual(self.P.store.ticket(key)["links"].get("system"), s["id"])
        self.assertEqual({x["id"]: x["tickets"] for x in self.call("GET", "/api/projects/ST/systems")[1]["systems"]}[s["id"]], 1)
        cols = self.call("GET", "/api/requirements?project=ST")[1]["columns"]
        self.assertIn("开评标系统（私有化）", [i.get("system_name") for c in cols for i in c["items"]])
        self.assertEqual(self.call("POST", "/api/tickets/%s/system" % key, {"system": None})[0], 200)
        self.assertNotIn("system", self.P.store.ticket(key)["links"])

    def test_other_projects_system_refused(self):
        other = workbench.create_system(self.P, "ST", "别的", "")
        self.P.store.x("UPDATE systems SET project='ZZ' WHERE id=?", (other["id"],))
        self.assertEqual(self.call("POST", "/api/tickets/%s/system" % self.ticket["key"], {"system": other["id"]})[0], 409)

    def test_intake_with_new_system_and_client(self):
        code, s = self.call("POST", "/api/workbench/intake", {"project": "ST", "text": "评标报告新增投标报价按万元汇总的导出项",
                                                               "client_name": "北京某公共资源交易中心", "system_name": "开评标系统（演示）", "model": False})
        self.assertEqual(code, 200, s)
        self.assertTrue(s["system"])
        self.assertEqual(workbench.system_of(self.P, "intake", s["id"]), s["system"])
        view = self.call("GET", "/api/clients/%d" % s["client"])[1]
        self.assertIn("开评标系统（演示）", [x["name"] for p in view["tree"] for x in p["systems"]])


if __name__ == "__main__":
    unittest.main()
