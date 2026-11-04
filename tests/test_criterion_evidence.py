"""D6: suite success cannot stand in for per-criterion evidence."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh import evidence as ev
from tmh.platform import ai_accept, browser_verify, signoff
from tmh.platform.errors import ApiError


class CriterionEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.acs = [{"id": "A1", "text": "金额按分计算", "check": "1.01 + 2.02 = 3.03", "keep": True}]
        self.environment = {"ssh": "synthetic-host", "app": "fixture"}
        (self.data / browser_verify.CONF).write_text(json.dumps({"projects": {"APP": self.environment}}))
        self.snap = {"project": {"key": "APP"}, "ticket": {"key": "APP-1"}, "ac": self.acs,
                     "change": {"run": 7, "commit": "a" * 40, "files": ["x.py"]},
                     "check": {"result": "pass"}, "scope": {"beyond_plan": []}, "path": {"ok": True},
                     "gates": [{"id": "test", "state": "unknown"}]}
        self.pack = signoff._add(signoff.epath(self.data, "APP-1"), "pack", "fixture", {"snapshot": self.snap})
        self.context = {"ticket": "APP-1", "project": "APP", "run": 7, "pack_hash": self.pack["hash"],
                        "base": "a" * 40, "diff_sha256": hashlib.sha256(b"").hexdigest(),
                        "criteria_sha256": signoff.criteria_digest(self.acs),
                        "environment_sha256": hashlib.sha256(ev.canon(self.environment).encode()).hexdigest(),
                        "result": "pass", "ac": [{"id": "A1", "result": "pass", "how": "assert total == 3.03"}]}

    def record(self, **changes):
        return signoff._add(signoff.epath(self.data, "APP-1"), "criterion_check", "页面实测", dict(self.context, **changes))

    def state(self):
        return signoff.state(self.data, "APP-1")

    def test_suite_and_screenshot_do_not_prove_unmapped_criterion(self):
        for test in ("pass", "unknown"):
            proof = signoff.proofs(self.snap, [{"id": "test", "state": test}], [{"ac": "A1", "file": "picture.png"}], None)[0]
            self.assertEqual(proof["state"], "todo")
            self.assertEqual(next(p for p in proof["proofs"] if p["kind"] == "shot")["state"], "unknown")
        self.assertEqual(self.state()["proofs"][0]["state"], "todo")

    def test_current_page_evidence_is_proven_and_failed_rerun_replaces_it(self):
        self.record()
        self.assertEqual(self.state()["proofs"][0]["state"], "proven")
        self.record(result="fail", ac=[{"id": "A1", "result": "fail", "how": "3.02 != 3.03"}])
        self.assertEqual(self.state()["proofs"][0]["state"], "fail")
        self.assertEqual(len(signoff.records(self.data, "APP-1")), 3)
        self.record(result="running", ac=[], check_id="new")
        self.assertEqual(self.state()["proofs"][0]["state"], "todo")

    def test_wrong_identity_or_changed_environment_never_reuses_success(self):
        for changed in ({"run": 8}, {"ticket": "APP-2"}, {"project": "OTHER"}, {"pack_hash": "old"},
                        {"criteria_sha256": signoff.criteria_digest([dict(self.acs[0], text="new condition")])},
                        {"base": "b" * 40}, {"diff_sha256": hashlib.sha256(b"other patch").hexdigest()},
                        {"environment_sha256": "old"}):
            with self.subTest(changed):
                self.record(**changed)
                self.assertEqual(self.state()["proofs"][0]["state"], "todo")
        self.record()
        (self.data / browser_verify.CONF).write_text(json.dumps({"projects": {"APP": dict(self.environment, app="another")}}))
        self.assertEqual(self.state()["proofs"][0]["state"], "todo")

    def test_new_pack_with_reused_ac_id_invalidates_old_evidence(self):
        self.record()
        snap = copy.deepcopy(self.snap)
        snap["ac"][0]["text"] = "changed business rule"
        signoff._add(signoff.epath(self.data, "APP-1"), "pack", "fixture", {"snapshot": snap})
        self.assertEqual(self.state()["proofs"][0]["state"], "todo")

    def test_failed_recheck_does_not_display_old_signed_green(self):
        self.record()
        signoff._add(signoff.epath(self.data, "APP-1"), "sign", "person", {"ac": {"A1": "pass"}})
        self.record(result="fail", ac=[{"id": "A1", "result": "fail", "how": "failed"}])
        current = self.state()
        self.assertIsNone(current["decision"])
        self.assertEqual(current["previous_decision"]["ac"], {"A1": "pass"})
        self.assertEqual(current["proofs"][0]["state"], "fail")

    def test_ai_record_checks_current_evidence_instead_of_caller_claim(self):
        P = SimpleNamespace(data_dir=self.data)
        ticket = {"key": "APP-1"}
        with self.assertRaisesRegex(ApiError, "逐项实测"):
            signoff._record_accept(P, ticket, ai_accept.BY, True, "fixture", via=ai_accept.BY, basis={"ac": {"A1": "pass"}})
        self.record()
        self.assertTrue(signoff._record_accept(P, ticket, ai_accept.BY, True, "fixture", via=ai_accept.BY, basis={"run": 7, "pack_hash": self.pack["hash"]}))

    def test_browser_result_is_persisted_with_binding_and_can_be_consumed(self):
        P = SimpleNamespace(data_dir=self.data, store=SimpleNamespace(
            run=lambda rid: {"diff": "", "workdir": ""}, event=mock.Mock()))
        t = {"id": 1, "key": "APP-1", "title": "金额"}
        report = {"suites": [{"specs": [{"title": "A1 计算正确", "tests": [{"results": [{"status": "passed",
                  "attachments": [{"name": "A1-result.png", "path": "/out/shots/A1-result.png", "contentType": "image/png"}]}]}]}]}]}
        with mock.patch.object(browser_verify, "full_sha", return_value="a" * 40), \
                mock.patch.object(browser_verify, "run_remote", return_value=(report, {"A1-result.png": b"original fixture image"})):
            result = browser_verify.verify(P, {"key": "APP", "root": str(self.data)}, t, 7, self.acs,
                                           commit="a" * 40, ask=lambda *args: "```tmh-spec\nfixture\n```")
        self.assertEqual(result["result"], "pass")
        current = self.state()
        self.assertEqual(current["proofs"][0]["state"], "proven")
        self.assertEqual(current["criterion_evidence"]["A1"]["result"], "pass")
        image = next((self.data / "evidence" / "files").iterdir())
        self.assertEqual(image.read_bytes(), b"original fixture image")
        # An unsuccessful new attempt supersedes the former pass immediately.
        with mock.patch.object(browser_verify, "full_sha", return_value=""):
            result = browser_verify.verify(P, {"key": "APP", "root": str(self.data)}, t, 7, self.acs, commit="a" * 40)
        self.assertEqual(result["result"], "unverified")
        self.assertEqual(self.state()["proofs"][0]["state"], "todo")

    def test_old_concurrent_response_cannot_restore_previous_green(self):
        self.record(result="running", ac=[], check_id="first")
        self.record(result="running", ac=[], check_id="second")
        self.record(check_id="first")
        self.assertEqual(self.state()["proofs"][0]["state"], "todo")
        self.record(check_id="second", result="fail", ac=[{"id": "A1", "result": "fail", "how": "wrong total"}])
        self.record(check_id="first")
        self.assertEqual(self.state()["proofs"][0]["state"], "fail")

    def test_signed_link_requires_explicit_decision_without_item_evidence(self):
        P = SimpleNamespace(data_dir=self.data, store=SimpleNamespace(ticket=lambda key: {"key": key, "status": "verify", "id": 1}))
        token = "a" * 24
        signoff._save_links(self.data, {signoff._th(token): {"key": "APP-1", "signer": "客户", "role": "", "expires": "9999", "used": "", "pack_hash": self.pack["hash"]}})
        with self.assertRaisesRegex(ApiError, "A1 没确认通过"):
            signoff._decide(P, token, "sign", "客户", {}, "")


    def test_history_does_not_hide_current_or_new_human_decision(self):
        self.record()
        signoff._add(signoff.epath(self.data,'APP-1'),'sign','person',{'ac':{'A1':'pass'}})
        decision=self.state()['decision']
        self.record(run=6,result='running',ac=[],check_id='history')
        self.record(run=6,check_id='history')
        self.assertEqual(self.state()['decision'],decision)
        self.assertEqual(self.state()['criterion_evidence']['A1']['result'],'pass')
        self.record(result='running',ac=[],check_id='current')
        self.assertIsNone(self.state()['decision'])
        signoff._add(signoff.epath(self.data,'APP-1'),'sign','person',{'ac':{'A1':'pass'}})
        self.assertIsNotNone(self.state()['decision'])
        self.record(check_id='history')
        self.assertIsNotNone(self.state()['decision'])

    def test_partial_results_preserve_independent_pass_but_block_ai_accept(self):
        self.acs.append({'id':'A2','text':'另一项','check':'独立检查','keep':True})
        self.pack=signoff._add(signoff.epath(self.data,'APP-1'),'pack','fixture',{'snapshot':self.snap})
        self.context.update(pack_hash=self.pack['hash'],criteria_sha256=signoff.criteria_digest(self.acs))
        self.record(result='unverified',ac=[{'id':'A1','result':'pass','how':'valid assertion'},{'id':'A2','result':'unverified','how':'missing'}])
        self.assertEqual(self.state()['criterion_evidence']['A1']['result'],'pass')
        with self.assertRaises(ApiError):
            signoff._record_accept(SimpleNamespace(data_dir=self.data),{'key':'APP-1'},ai_accept.BY,True,'fixture',via=ai_accept.BY,basis={'run':7,'pack_hash':self.pack['hash']})

    def test_changed_environment_invalidates_ai_decision(self):
        self.record()
        signoff._record_accept(SimpleNamespace(data_dir=self.data),{'key':'APP-1'},ai_accept.BY,True,'fixture',via=ai_accept.BY,basis={'run':7,'pack_hash':self.pack['hash']})
        (self.data/browser_verify.CONF).write_text(json.dumps({'projects':{'APP':dict(self.environment,app='changed')}}))
        self.assertIsNone(self.state()['decision'])

    def test_historical_browser_attempt_is_not_bound_to_latest_pack(self):
        self.record()
        P=SimpleNamespace(data_dir=self.data,store=SimpleNamespace(run=lambda rid:{'diff':'','workdir':''},event=mock.Mock()))
        with mock.patch.object(browser_verify,'full_sha',return_value=''):
            browser_verify.verify(P,{'key':'APP','root':str(self.data)},{'id':1,'key':'APP-1','title':'fixture'},6,self.acs,commit='b'*40)
        self.assertEqual(self.state()['criterion_evidence']['A1']['result'],'pass')
        self.assertEqual(len(signoff.records(self.data,'APP-1')),2)


if __name__ == "__main__":
    unittest.main()
