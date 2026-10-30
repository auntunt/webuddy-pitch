import contextlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tmh.platform import ai_accept

ACS = [{"id": "A1", "text": "取消后恢复原值"}, {"id": "A2", "text": "重置清空"}]
GOOD = {"check": "pass", "verdict": "pass",
        "diagnosis": {"verdict": "pass", "blocking": [], "ac": [{"id": "A1", "result": "pass", "how": "a.vue:10"},
                                                               {"id": "A2", "result": "pass", "how": "a.vue:20"}]}}


class AiAcceptGateTest(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="tmh-ai-"))

    def verify(self, v, rid=7):
        d = self.data / "runs" / str(rid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "verify.json").write_text(json.dumps(v), encoding="utf-8")
        return rid

    def test_switch_is_per_project(self):
        self.assertTrue(ai_accept.enabled({"ai_accept": ["JB"]}, "JB"))
        self.assertFalse(ai_accept.enabled({"ai_accept": ["JB"]}, "CWWEB"))
        self.assertFalse(ai_accept.enabled({}, "JB"))
        self.assertTrue(ai_accept.enabled({"ai_accept": "*"}, "RW"))

    def test_full_evidence_lets_ai_accept(self):
        self.assertEqual(ai_accept.why_not(self.data, self.verify(GOOD), ACS), "")

    def test_anything_short_of_full_evidence_stays_with_people(self):
        cases = {
            "没跑构建测试": dict(GOOD, check="skip", skip="基线不通过"),
            "构建测试没通过": dict(GOOD, check="fail"),
            "独立诊断没有判通过": dict(GOOD, verdict="unknown", diagnosis=dict(GOOD["diagnosis"], verdict="unknown")),
            "阻断项": dict(GOOD, diagnosis=dict(GOOD["diagnosis"], blocking=[{"ac": "A1", "scenario": "x"}])),
            "没有逐条核对验收标准 A2": dict(GOOD, diagnosis=dict(GOOD["diagnosis"], ac=GOOD["diagnosis"]["ac"][:1])),
            "A2 诊断没能确认": dict(GOOD, diagnosis=dict(GOOD["diagnosis"], ac=[GOOD["diagnosis"]["ac"][0], {"id": "A2", "result": "unverified"}])),
            "已失效": dict(GOOD, verification_current=False),
            "方案没列": dict(GOOD, beyond_plan=["b.vue"]),
        }
        for want, v in cases.items():
            with self.subTest(want):
                self.assertIn(want, ai_accept.why_not(self.data, self.verify(v), ACS))
        self.assertIn("没有验收标准", ai_accept.why_not(self.data, self.verify(GOOD), []))
        self.assertIn("待确认", ai_accept.why_not(self.data, self.verify(GOOD), [dict(ACS[0], open=True), ACS[1]]))


class AiAcceptFlowTest(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="tmh-ai-"))
        d = self.data / "runs" / "7"
        d.mkdir(parents=True)
        (d / "verify.json").write_text(json.dumps(GOOD), encoding="utf-8")
        self.ticket = {"id": 1, "key": "JB-1", "status": "verify", "links": {}, "project_id": 1}
        store = mock.MagicMock()
        store.ticket.side_effect = lambda tid: dict(self.ticket)
        store.one.return_value = None
        store.update_ticket.side_effect = lambda tid, by, **kv: self.ticket.update(kv)
        flow = mock.MagicMock()
        flow.autoflow.return_value = {"ai_accept": ["JB"]}
        flow.held.return_value = False
        self.P = mock.MagicMock(store=store, flow=flow, data_dir=self.data)
        self.pack = {"packed": True, "intact": True, "snapshot": {"ac": ACS, "change": {"run": 7}}}

    def run_it(self):
        from tmh.platform import signoff
        with mock.patch.object(signoff, "state", return_value=self.pack), \
                mock.patch.object(signoff, "verification_guard", lambda P, key: contextlib.nullcontext()), \
                mock.patch.object(signoff, "_record_accept", return_value="h" * 64) as rec:
            return ai_accept.after_commit(self.P, {"key": "JB"}, 1, 7), rec

    def test_signs_closes_and_ships_with_the_basis(self):
        out, rec = self.run_it()
        self.assertTrue(out["accepted"])
        self.assertEqual(self.ticket["status"], "closed")
        args, kw = rec.call_args
        self.assertEqual((args[2], args[3], kw["via"]), ("AI 验收", True, "AI 验收"))
        self.assertEqual(kw["basis"]["ac"], {"A1": "a.vue:10", "A2": "a.vue:20"})
        self.P.flow.accepted.assert_called_once()
        kinds = [c.args[2] for c in self.P.store.event.call_args_list]
        self.assertEqual(kinds, ["accept"])

    def real(self, result, ac, why=""):
        from tmh.platform import browser_verify
        items = [{"id": k, "result": v, "how": "实测 " + k, "shots": {}} for k, v in ac.items()]
        return mock.patch.object(browser_verify, "conf", return_value={"ssh": "u@h", "app": "web"}), \
            mock.patch.object(browser_verify, "verify", return_value={"result": result, "why": why, "ac": items})

    def test_with_a_verification_host_only_a_real_all_pass_signs_and_its_basis_is_the_real_run(self):
        a, b = self.real("pass", {"A1": "pass", "A2": "pass"})
        with a, b as v:
            out, rec = self.run_it()
        self.assertTrue(out["accepted"])
        v.assert_called_once()
        basis = rec.call_args.kwargs["basis"]
        self.assertEqual((basis["real"], basis["ac"]["A1"]), ("pass", "实测 A1"))
        self.assertIn("在页面上逐条实测", rec.call_args.args[4])

    def test_the_page_check_runs_on_the_commit_adopted_from_this_run(self):
        a, b = self.real("pass", {"A1": "pass", "A2": "pass"})
        self.pack["snapshot"]["adopted"] = {"branch": "tmh/JB-1-r7", "commit": "1c021d9f"}
        with a, b as v:
            self.run_it()
        self.assertEqual(v.call_args.kwargs["commit"], "1c021d9f")
        self.assertEqual(ai_accept.committed({"adopted": {"branch": "tmh/JB-1-r70", "commit": "x"}}, 7), "")
        self.assertEqual(ai_accept.committed({"change": {"commit": "f" * 40}, "adopted": {"branch": "tmh/JB-1-r7", "commit": "x"}}, 7), "f" * 40)

    def test_what_must_keep_working_is_proven_by_the_tests_not_driven_on_the_page(self):
        keep = {"id": "A3", "text": "必须保持：其他环节和其他用户的现有行为不变", "keep": True}
        self.pack["snapshot"]["ac"] = ACS + [keep]
        a, b = self.real("pass", {"A1": "pass", "A2": "pass"})
        with a, b as v:
            out, rec = self.run_it()
        self.assertTrue(out["accepted"])
        self.assertEqual([x["id"] for x in v.call_args.args[4]], ["A1", "A2"])
        self.assertEqual(rec.call_args.kwargs["basis"]["ac"]["A3"], ai_accept.KEPT_BUILD)
        self.setUp()
        self.pack["snapshot"]["ac"] = ACS + [keep]
        self.pack["snapshot"]["gates"] = [{"id": "test", "state": "pass"}]
        a, b = self.real("pass", {"A1": "pass", "A2": "pass"})
        with a, b:
            out, rec = self.run_it()
        self.assertEqual(rec.call_args.kwargs["basis"]["ac"]["A3"], ai_accept.KEPT)
        self.setUp()
        self.pack["snapshot"]["ac"] = [keep]
        a, b = self.real("pass", {})
        with a, b as v:
            out, rec = self.run_it()
        self.assertFalse(out["accepted"])
        v.assert_not_called()
        self.assertIn("没有要在页面上实测的验收标准", out["why"])

    def test_with_a_verification_host_a_reproduced_failure_or_anything_unproven_leaves_it_for_people(self):
        for result, ac, why, want in (("fail", {"A1": "pass", "A2": "fail"}, "", "复现了问题（A2）"),
                                      ("unverified", {"A1": "pass", "A2": "unverified"}, "", "A2 未验证"),
                                      ("unverified", {}, "app did not start", "app did not start"),
                                      ("pass", {"A1": "pass"}, "", "A2")):
            with self.subTest(want):
                self.setUp()
                a, b = self.real(result, ac, why)
                with a, b:
                    out, rec = self.run_it()
                self.assertFalse(out["accepted"])
                self.assertIn("页面实测", out["why"])
                if want != "A2":
                    self.assertIn(want, out["why"])
                rec.assert_not_called()
                self.assertEqual(self.ticket["status"], "verify")

    def test_with_a_verification_host_an_unverified_diagnosis_criterion_no_longer_blocks_but_a_failed_one_does(self):
        for diag, ok in (("unverified", True), ("fail", False)):
            with self.subTest(diag):
                self.setUp()
                v = dict(GOOD, diagnosis=dict(GOOD["diagnosis"], ac=[{"id": "A1", "result": "pass"}, {"id": "A2", "result": diag}]))
                (self.data / "runs" / "7" / "verify.json").write_text(json.dumps(v), encoding="utf-8")
                a, b = self.real("pass", {"A1": "pass", "A2": "pass"})
                with a, b:
                    out, rec = self.run_it()
                self.assertEqual(out["accepted"], ok)

    def test_leaves_it_for_people_when_off_taken_over_or_package_is_for_another_run(self):
        for setup, want in ((lambda: self.P.flow.autoflow.return_value.update(ai_accept=[]), "没开"),
                            (lambda: setattr(self.P.flow.held, "return_value", True), "接手"),
                            (lambda: self.pack["snapshot"].update(change={"run": 6}), "不是这次改动"),
                            (lambda: self.pack.update(intact=False, problem="x"), "改动过")):
            with self.subTest(want):
                self.setUp()
                setup()
                out, rec = self.run_it()
                self.assertFalse(out["accepted"])
                self.assertIn(want, out["why"])
                rec.assert_not_called()
                self.assertEqual(self.ticket["status"], "verify")
                self.P.flow.accepted.assert_not_called()



class AutoflowPerProjectTest(unittest.TestCase):
    def test_on_can_name_projects(self):
        from tmh.platform.orchestra import Orchestra
        o = Orchestra.__new__(Orchestra)
        o.store = mock.MagicMock()
        o.store.project.side_effect = lambda pid: {1: {"key": "JB"}, 2: {"key": "CWWEB"}}.get(pid)
        self.assertTrue(o.switched_on({"on": ["JB"]}, 1))
        self.assertFalse(o.switched_on({"on": ["JB"]}, 2))
        self.assertFalse(o.switched_on({"on": ["JB"]}, 3))
        self.assertTrue(o.switched_on({"on": ["JB"]}, {"key": "JB"}))
        self.assertTrue(o.switched_on({"on": True}, 2))
        self.assertFalse(o.switched_on({"on": False}, 1))


    def test_the_switches_survive_reading_autoflow_json(self):
        from tmh.platform.orchestra import Orchestra
        data = Path(tempfile.mkdtemp(prefix="tmh-ai-"))
        (data / "autoflow.json").write_text(json.dumps({"on": ["JB"], "ai_accept": ["JB"]}), encoding="utf-8")
        o = Orchestra.__new__(Orchestra)
        o.data_dir = data
        conf = o.autoflow()
        self.assertEqual((conf["on"], conf["ai_accept"]), (["JB"], ["JB"]))
        (data / "autoflow.json").write_text("{}", encoding="utf-8")
        self.assertFalse(ai_accept.enabled(o.autoflow(), "JB"))


    def test_a_managed_worker_runs_the_line_only_for_the_trusted_default_tenant_and_never_merges(self):
        from tmh.platform.orchestra import Orchestra
        data = Path(tempfile.mkdtemp(prefix="tmh-ai-"))
        (data / "autoflow.json").write_text(json.dumps({"on": ["JB"], "ai_accept": ["JB"]}), encoding="utf-8")
        (data / "release.json").write_text(json.dumps({"merge": True}), encoding="utf-8")
        o = Orchestra.__new__(Orchestra)
        o.data_dir = data
        for trusted, on in ((True, ["JB"]), (False, False)):
            o.tenant_context = type("Ctx", (), {"trusted_host": lambda self, v=trusted: v})()
            conf = o.autoflow()
            self.assertEqual((conf["on"], conf["merge"], conf["ai_accept"]), (on, False, ["JB"]))
        o.tenant_context = object()
        self.assertFalse(o.autoflow()["on"])
        (data / "autoflow.json").write_text(json.dumps({"on": True}), encoding="utf-8")
        o.tenant_context = type("Ctx", (), {"trusted_host": lambda self: True})()
        self.assertFalse(o.autoflow()["on"])


if __name__ == "__main__":
    unittest.main()
