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
        self.pack = {"packed": True, "intact": True, "snapshot": {"ac": ACS, "change": {"run": 7}},
                     "criterion_evidence": {a["id"]: {"id": a["id"], "result": "pass", "how": "实测 " + a["id"]} for a in ACS}}

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
        self.assertEqual(kw["basis"]["ac"], {"A1": "实测 A1", "A2": "实测 A2"})
        self.P.flow.accepted.assert_called_once()
        kinds = [c.args[2] for c in self.P.store.event.call_args_list]
        self.assertEqual(kinds, ["accept"])

    def test_suite_and_diagnosis_without_item_evidence_do_not_auto_accept(self):
        self.pack["criterion_evidence"] = {}
        self.pack["snapshot"]["gates"] = [{"id": "test", "state": "pass"}]
        out, rec = self.run_it()
        self.assertFalse(out["accepted"])
        self.assertIn("逐项实测依据", out["why"])
        rec.assert_not_called()
        self.assertEqual(self.ticket["status"], "verify")

    def test_a_page_only_change_needs_page_checks_to_be_signed(self):
        page = "diff --git a/src/main/resources/templates/v.html b/src/main/resources/templates/v.html\n+x\n"
        self.P.store.run.return_value = {"id": 7, "diff": page}
        out, rec = self.run_it()
        self.assertFalse(out["accepted"])
        self.assertIn("只改了页面文件", out["why"])
        rec.assert_not_called()
        a, b = self.real("pass", {"A1": "pass", "A2": "pass"})
        with a, b:
            out, rec = self.run_it()
        self.assertTrue(out["accepted"])
        self.P.store.run.return_value = {"id": 7, "diff": page.replace("templates/v.html", "java/V.java")}
        self.ticket["status"] = "verify"
        self.assertTrue(self.run_it()[0]["accepted"])

    def real(self, result, ac, why=""):
        from tmh.platform import browser_verify
        items = [{"id": k, "result": v, "how": "实测 " + k, "shots": {}} for k, v in ac.items()]
        self.pack["criterion_evidence"] = {i["id"]: i for i in items}
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

    def test_keep_criteria_need_their_own_page_evidence_even_when_suite_passes(self):
        keep = {"id": "A3", "text": "必须保持：其他环节和其他用户的现有行为不变", "keep": True}
        self.pack["snapshot"]["ac"] = ACS + [keep]
        self.pack["missing"] = ["验证门全部通过（没有没过或未知的）", "乙方复核人"]
        a, b = self.real("pass", {"A1": "pass", "A2": "pass"})
        with a, b as v:
            out, rec = self.run_it()
        self.assertFalse(out["accepted"])
        self.assertEqual([x["id"] for x in v.call_args.args[4]], ["A1", "A2", "A3"])
        self.assertIn("A3 未验证", out["why"])
        self.setUp()
        self.pack["snapshot"]["ac"] = ACS + [keep]
        self.pack["missing"] = ["验证门全部通过（没有没过或未知的）", "乙方复核人"]
        a, b = self.real("pass", {"A1": "pass", "A2": "pass", "A3": "pass"})
        with a, b:
            out, rec = self.run_it()
        self.assertTrue(out["accepted"])
        self.assertEqual(rec.call_args.kwargs["basis"]["ac"]["A3"], "实测 A3")
        note = rec.call_args.args[4]
        self.assertIn("构建通过（这个项目没跑自动测试）", note)
        self.assertIn("在页面上逐条实测 3 条验收标准（A1、A2、A3）", note)
        self.assertIn("证据包里还缺：验证门全部通过（没有没过或未知的）、乙方复核人", note)
        self.setUp()
        self.pack["snapshot"]["ac"] = ACS + [keep]
        self.pack["snapshot"]["gates"] = [{"id": "test", "state": "pass"}]
        a, b = self.real("pass", {"A1": "pass", "A2": "pass"})
        with a, b as v:
            out, rec = self.run_it()
        self.assertEqual([x["id"] for x in v.call_args.args[4]], ["A1", "A2", "A3"])
        self.assertFalse(out["accepted"])
        rec.assert_not_called()
        self.assertIn("A3 未验证", out["why"])
        self.setUp()
        self.pack["snapshot"]["ac"] = ACS + [keep]
        self.pack["snapshot"]["gates"] = [{"id": "test", "state": "pass"}]
        self.P.store.run.return_value = {"id": 7, "diff": "diff --git a/src/main/resources/templates/v.html b/src/main/resources/templates/v.html\n"}
        a, b = self.real("pass", {"A1": "pass", "A2": "pass", "A3": "pass"})
        with a, b as v:
            self.assertTrue(self.run_it()[0]["accepted"])
        self.assertEqual([x["id"] for x in v.call_args.args[4]], ["A1", "A2", "A3"])
        self.setUp()
        self.pack["snapshot"]["ac"] = [keep]
        self.pack["snapshot"]["gates"] = [{"id": "test", "state": "pass"}]
        a, b = self.real("pass", {})
        with a, b as v:
            out, rec = self.run_it()
        self.assertFalse(out["accepted"])
        v.assert_called_once()
        self.assertEqual(v.call_args.args[4], [keep])
        self.assertIn("A3 未验证", out["why"])

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


class ShadowAcceptTest(unittest.TestCase):
    """observe: the same checks run, AI says whether it would accept, signs nothing; a person's verdict is compared."""
    run_it, real = AiAcceptFlowTest.run_it, AiAcceptFlowTest.real

    def setUp(self):
        AiAcceptFlowTest.setUp(self)
        self.P.flow.autoflow.return_value = {"ai_accept": [], "ai_accept_observe": ["JB"]}

    def shadow(self):
        datas = [c.args[4] for c in self.P.store.event.call_args_list if len(c.args) > 4]
        return [d["shadow"] for d in datas if "shadow" in d]

    def test_full_evidence_is_said_but_not_signed(self):
        out, rec = self.run_it()
        self.assertEqual((out["accepted"], out["shadow"], out["would_accept"]), (False, True, True))
        rec.assert_not_called()
        self.P.flow.accepted.assert_not_called()
        self.P.store.update_ticket.assert_not_called()
        self.assertEqual(self.ticket["status"], "verify")
        [sh] = self.shadow()
        self.assertTrue(sh["would_accept"])
        self.assertEqual(sh["basis"]["ac"], {"A1": "实测 A1", "A2": "实测 A2"})

    def test_short_evidence_says_why_it_would_not(self):
        a, b = self.real("fail", {"A1": "fail", "A2": "pass"})
        with a, b:
            out, rec = self.run_it()
        self.assertEqual((out["accepted"], out["would_accept"]), (False, False))
        rec.assert_not_called()
        [sh] = self.shadow()
        self.assertIn("复现了问题", sh["why"])

    def test_on_wins_over_observe_and_neither_does_nothing(self):
        conf = {"ai_accept": ["JB"], "ai_accept_observe": ["JB"]}
        self.assertTrue(ai_accept.enabled(conf, "JB"))
        self.assertFalse(ai_accept.observing(conf, "JB"))
        self.P.flow.autoflow.return_value = {"ai_accept": [], "ai_accept_observe": []}
        out, _ = self.run_it()
        self.assertNotIn("shadow", out)
        self.assertEqual(self.shadow(), [])


class ShadowCompareTest(unittest.TestCase):
    def store(self, *datas):
        evs = [{"id": i, "kind": "flow", "data": json.dumps(d)} for i, d in enumerate(datas)]
        st = mock.MagicMock()
        st.events.return_value = evs
        st.event.side_effect = lambda tid, by, kind, body, data: evs.append({"id": len(evs), "kind": kind, "data": json.dumps(data)})
        return st, evs

    def test_a_person_s_verdict_is_set_against_the_last_shadow_once(self):
        st, evs = self.store({"run": 7, "shadow": {"would_accept": True, "why": ""}})
        c = ai_accept.compare(st, {"id": 1}, True, "li")
        self.assertEqual((c["ai"], c["person"], c["agree"]), (True, True, True))
        self.assertIn("一致", st.event.call_args.args[3])
        self.assertIsNone(ai_accept.compare(st, {"id": 1}, False, "li"))  # already compared
        self.assertEqual(len(evs), 2)

    def test_disagreement_is_said_and_ai_s_own_verdict_or_no_shadow_is_not_compared(self):
        st, _ = self.store({"run": 7, "shadow": {"would_accept": False, "why": "页面实测没能证明"}})
        self.assertIsNone(ai_accept.compare(st, {"id": 1}, True, ai_accept.BY))
        c = ai_accept.compare(st, {"id": 1}, True, "li")
        self.assertFalse(c["agree"])
        self.assertIn("不一致", st.event.call_args.args[3])
        st, _ = self.store({"run": 7})
        self.assertIsNone(ai_accept.compare(st, {"id": 1}, True, "li"))


class ShadowModeSwitchTest(unittest.TestCase):
    def test_observe_runs_the_line_without_ai_signing_or_merging(self):
        from tmh.platform.orchestra import Orchestra
        data = Path(tempfile.mkdtemp(prefix="tmh-ai-"))
        (data / "autoflow.json").write_text(json.dumps({"on": ["JB"], "ai_accept": ["JB"], "merge": ["JB"]}), encoding="utf-8")
        o = Orchestra.__new__(Orchestra)
        o.data_dir = data
        o.store = mock.MagicMock()
        o.store.projects.return_value = [{"key": "JB"}, {"key": "RW"}]
        p = {"key": "JB"}
        self.assertEqual(o.mode(p), "auto")
        self.assertEqual(o.set_mode(p, "observe", "li"), "observe")
        conf = json.loads((data / "autoflow.json").read_text(encoding="utf-8"))
        self.assertEqual((conf["on"], conf["ai_accept"], conf["merge"], conf["ai_accept_observe"]), (["JB"], [], [], ["JB"]))
        self.assertTrue(ai_accept.observing(o.autoflow(), "JB"))
        self.assertEqual(o.set_mode(p, "manual", "li"), "manual")
        conf = json.loads((data / "autoflow.json").read_text(encoding="utf-8"))
        self.assertEqual((conf["on"], conf["ai_accept_observe"]), ([], []))
        self.assertEqual(conf["modes_log"][-2]["mode"], "observe")
        with self.assertRaises(ValueError):
            o.set_mode(p, "shadow", "li")


class MandateTest(unittest.TestCase):
    def test_the_fingerprint_covers_only_this_project_s_switches_and_names_who_set_the_mode(self):
        data = Path(tempfile.mkdtemp(prefix="tmh-ai-"))
        (data / "autoflow.json").write_text(json.dumps({"on": ["JB", "RW"], "ai_accept": ["JB"], "merge": ["JB"], "modes_log": [
            {"project": "JB", "mode": "auto", "by": "li", "ts": "2026-11-01 10:00:00"}, {"project": "RW", "mode": "manual", "by": "wang", "ts": "x"}]}), encoding="utf-8")
        conf = {"on": ["JB", "RW"], "ai_accept": ["JB"], "plan": True, "fix": True, "commit": True, "max_lines": {"JB": 400, "*": 20}, "refix": 2}
        m = ai_accept.mandate(conf, "JB", data)
        self.assertEqual((m["mode"], m["switches"]["merge"], m["switches"]["max_lines"], m["set_by"]["by"]), ("auto", True, 400, "li"))
        self.assertIn("全自动", ai_accept.describe(m))
        self.assertIn("li 于 2026-11-01 10:00:00", ai_accept.describe(m))
        other = dict(conf, on=["JB"], ai_accept=["JB", "XX"])  # RW switched off, XX switched on: JB's policy is the same
        self.assertEqual(ai_accept.mandate(other, "JB", data)["policy"], m["policy"])
        self.assertNotEqual(ai_accept.mandate(dict(conf, ai_accept=[]), "JB", data)["policy"], m["policy"])
        self.assertEqual(ai_accept.mandate(conf, "RW", data)["mode"], "partial")
        self.assertEqual(ai_accept.mandate({"on": ["JB"], "ai_accept_observe": ["JB"]}, "JB")["mode"], "observe")
        self.assertEqual(ai_accept.mandate({}, "JB")["mode"], "manual")


class MandateOnVerdictTest(unittest.TestCase):
    run_it = AiAcceptFlowTest.run_it

    def setUp(self):
        AiAcceptFlowTest.setUp(self)

    def test_the_verdict_carries_the_mandate_and_says_when_it_changed_since_the_start(self):
        start = ai_accept.mandate({"on": ["JB"], "ai_accept_observe": ["JB"]}, "JB", self.data)
        self.P.store.events.return_value = [{"id": 1, "kind": "intake", "data": json.dumps({"mandate": start})}]
        out, rec = self.run_it()
        self.assertTrue(out["accepted"])
        m = rec.call_args.kwargs["basis"]["mandate"]
        self.assertEqual(m["changed_from"], start["policy"])
        self.assertTrue(m["switches"]["ai_accept"])
        self.assertIn("授权改过", rec.call_args.args[4])

    def test_an_unchanged_policy_is_not_called_changed(self):
        conf = self.P.flow.autoflow.return_value
        start = ai_accept.mandate(conf, "JB", self.data)
        self.P.store.events.return_value = [{"id": 1, "kind": "intake", "data": json.dumps({"mandate": start})}]
        _, rec = self.run_it()
        m = rec.call_args.kwargs["basis"]["mandate"]
        self.assertNotIn("changed_from", m)
        self.assertEqual(m["policy"], start["policy"])
        self.assertNotIn("授权改过", rec.call_args.args[4])


if __name__ == "__main__":
    unittest.main()
