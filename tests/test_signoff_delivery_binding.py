"""Delivery sign-off uses reviewed source identities, never ticket recency.

The contract tests isolate sign-off from the delivery resolver using real stored
runs and append-only evidence. Delivery's resolver has its own integration tests.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tmh import evidence as ev
from tmh.platform import delivery, preview, signoff
from tmh.platform.agents import git
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tests.test_delivery import RecordingRunner


DIFF = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old = 1\n+new = 2\n"


class SignoffDeliveryBindingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-signoff-binding-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("APP", "绑定测试", str(self.data))
        self.ticket = self.store.create_ticket(self.project["id"], "保存记录", "测试人员", links={"delivery": "a" * 12})
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, root=lambda p: Path(p["root"]),
                                 flow=SimpleNamespace(accepted=mock.Mock()))
        self.plan = self.make_run("plan", "原始验收标准", file="app.py")
        self.fix = self.make_run("fix", "实际实现", commit="a" * 40)
        self.store.event(self.ticket["id"], "自动流转", "adopt", "采纳对应实现",
                         {"run": self.fix, "commit": "a" * 40, "branch": "tmh/original"})
        self.binding = {"delivery_id": "a" * 12, "valid": True, "blocked": [], "plan_run": self.plan,
                        "fix_run": self.fix, "commit": "a" * 40,
                        "identity": {"develop": {"artifact": 2, "review": 2, "execution": "verified-a"},
                                     "quality": {"artifact": 3, "review": 3, "source_run": 3},
                                     "security": {"artifact": 4, "review": 4, "source_run": 4}}}
        resolver = mock.patch.object(delivery, "signoff_binding", side_effect=lambda *_: copy.deepcopy(self.binding), create=True)
        resolver.start()
        self.addCleanup(resolver.stop)
        self.store.update_ticket(self.ticket["id"], "测试人员", status="verify")
        self.ticket = self.store.ticket(self.ticket["id"])

    def make_run(self, mode, text, file="app.py", commit=""):
        r = self.store.create_run(self.project["id"], self.ticket["id"], "test-agent", mode, "测试人员", "本地契约测试")
        result = "```tmh-plan\n" + json.dumps({"files": [{"path": file, "goal": text}],
                 "ac": [{"id": "A1", "text": text, "check": "读回保存记录", "layer": "L4"}]}, ensure_ascii=False) + "\n```" if mode == "plan" else text
        self.store.update_run(r["id"], status="done", exit_code=0, result=result, diff=DIFF if mode == "fix" else "",
                              decision="accepted:tmh/test@" + commit if commit else "")
        if mode == "fix":
            root = self.data / "runs" / str(r["id"])
            root.mkdir(parents=True)
            (root / "verify.json").write_text(json.dumps({"check": "pass", "verdict": "pass", "files": ["app.py"],
                "commands": [{"cmd": "python3 -m unittest", "exit_code": 0}], "beyond_plan": []}), encoding="utf-8")
        return r["id"]

    def packed(self):
        return signoff.pack(self.P, self.ticket, "测试人员")

    def link(self):
        return signoff.issue(self.P, self.ticket, "测试人员", "测试签收人", note="测试明确保留未通过的其他验证门")

    def refused(self, operation, *args, **kwargs):
        with self.assertRaises(ApiError) as caught:
            operation(*args, **kwargs)
        self.assertEqual(caught.exception.code, 409)
        return str(caught.exception)

    def test_unrelated_later_plan_fix_and_adoption_do_not_replace_reviewed_sources(self):
        later_plan = self.make_run("plan", "不相关的新方案", file="other.py")
        later_fix = self.make_run("fix", "不相关的新实现", commit="b" * 40)
        self.store.event(self.ticket["id"], "后来的复核人", "adopt", "无关采纳",
                         {"run": later_fix, "commit": "b" * 40, "branch": "tmh/unrelated"})
        snap = signoff.snapshot(self.P, self.ticket)
        self.assertEqual(snap["plan_run"], self.plan)
        self.assertNotEqual(snap["plan_run"], later_plan)
        self.assertEqual(snap["change"]["run"], self.fix)
        self.assertEqual(snap["change"]["commit"], "a" * 40)
        self.assertEqual(snap["ac"][0]["text"], "原始验收标准")
        self.assertEqual(snap["contract"], [{"path": "app.py", "goal": "原始验收标准"}])
        self.assertEqual(snap["adopted"]["by"], "自动流转")
        self.assertEqual(snap["delivery_binding"]["identity"]["security"]["source_run"], 4)

    def test_invalid_delivery_never_falls_back_to_ordinary_runs(self):
        self.binding.update(valid=False, plan_run=None, fix_run=None, commit="", blocked=["当前实现未复核"])
        snap = signoff.snapshot(self.P, self.ticket)
        self.assertIsNone(snap["plan_run"])
        self.assertIsNone(snap["change"])
        self.assertIsNone(snap["adopted"])
        self.packed()
        self.assertIn("当前实现未复核", self.refused(self.link))

    def test_upstream_or_verification_invalidation_removes_current_signoff_without_erasing_history(self):
        self.packed()
        seal = signoff.record_accept(self.P, self.ticket, "测试签收人", True, "已按当前版本验收")
        self.assertEqual(signoff.state(self.data, self.ticket["key"])["status"], "signed")
        self.binding.update(valid=False, blocked=["实现验证已变化，质量与安全复核失效"])
        self.binding["identity"]["develop"]["execution"] = "verified-b"
        state = signoff.state(self.data, self.ticket["key"])
        self.assertTrue(state["stale"])
        self.assertFalse(state["complete"])
        self.assertEqual(state["status"], "incomplete")
        self.assertIsNone(state["decision"])
        self.assertEqual(state["previous_decision"]["hash"], seal)
        self.assertTrue(ev.check(signoff.records(self.data, self.ticket["key"]))[0])
        self.refused(self.link)
        self.refused(signoff.record_accept, self.P, self.ticket, "测试签收人", True, "不能沿用旧版本")

    def test_quality_revision_invalidates_live_link_and_hides_sign_form(self):
        self.packed()
        link = self.link()
        self.binding["identity"]["quality"]["artifact"] = 30
        self.binding.update(valid=False, blocked=["质量产物需要重新复核"])
        self.refused(signoff.decide, self.P, link["token"], "sign", "测试签收人", {"A1": "pass"}, "")
        page = signoff.sign_page(self.P, link["token"])
        self.assertNotIn("name=action value=sign", page)
        self.assertIn("不能继续签收", page)

    def test_old_link_cannot_sign_new_package_even_after_current_chain_is_reviewed(self):
        self.packed()
        link = self.link()
        self.binding["identity"]["security"]["review"] = 40
        self.assertTrue(signoff.state(self.data, self.ticket["key"])["stale"])
        self.packed()
        self.assertFalse(signoff.state(self.data, self.ticket["key"])["stale"])
        self.assertIn("证据包版本已变化", self.refused(signoff.decide, self.P, link["token"], "sign", "测试签收人", {"A1": "pass"}, ""))
        fresh = self.link()
        result = signoff.decide(self.P, fresh["token"], "sign", "测试签收人", {"A1": "pass"}, "当前版本已验证")
        self.assertTrue(result["ok"])
        self.assertEqual(self.store.ticket(self.ticket["id"])["status"], "closed")

    def test_removed_delivery_binding_cannot_reuse_an_existing_signature(self):
        self.packed()
        link = self.link()
        self.binding = None
        self.assertIn("交付关联已变化", "；".join(signoff.state(self.data, self.ticket["key"])["binding_blocked"]))
        self.refused(signoff.decide, self.P, link["token"], "sign", "测试签收人", {"A1": "pass"}, "")

    def test_ordinary_ticket_keeps_latest_run_behavior_and_legacy_compatibility(self):
        self.binding = None
        latest = self.make_run("plan", "普通工单的当前方案")
        snap = signoff.snapshot(self.P, self.ticket)
        self.assertNotIn("delivery_binding", snap)
        self.assertEqual(snap["plan_run"], latest)
        self.packed()
        self.assertNotIn("binding_blocked", signoff.state(self.data, self.ticket["key"]))
        self.assertTrue(self.link()["token"])

    def test_delivery_without_current_package_cannot_be_accepted_from_internal_button(self):
        self.refused(signoff.record_accept, self.P, self.ticket, "测试签收人", True, "没有包也不能通过")
        self.assertEqual(signoff.records(self.data, self.ticket["key"]), [])

    def test_corrupt_delivery_package_cannot_be_accepted_from_internal_button(self):
        self.packed()
        path = signoff.epath(self.data, self.ticket["key"])
        records = signoff.records(self.data, self.ticket["key"])
        records[0]["by"] = "包已被改动"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
        self.assertFalse(signoff.state(self.data, self.ticket["key"])["intact"])
        self.assertIn("证据包被改动过", self.refused(signoff.record_accept, self.P, self.ticket, "测试签收人", True, "不能绕过证据损坏"))

    def test_sign_page_only_offers_the_exact_bound_preview(self):
        self.packed()
        link = self.link()
        key = self.ticket["key"]
        expected = {"state": "up", "commit_full": "a" * 40, "prefix": preview.bound_prefix(key, "a" * 40)}
        for status in (dict(expected, commit_full="b" * 40), dict(expected, prefix="/pv/" + key)):
            with self.subTest(status=status), mock.patch.object(preview, "status", return_value=status):
                page = signoff.sign_page(self.P, link["token"])
                self.assertIn("当前预览版本与这次签收的实现不匹配", page)
                self.assertNotIn("/sign/%s/pv/" % link["token"], page)
        with mock.patch.object(preview, "status", return_value=expected):
            self.assertIn("/sign/%s/pv/" % link["token"], signoff.sign_page(self.P, link["token"]))


class SignoffDeliveryIntegrationTest(unittest.TestCase):
    """Real delivery rows, Git objects and receipts; model/test output is an explicit fixture."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-signoff-chain-")
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        self.root = self.data / "project"
        self.root.mkdir()
        git(self.root, "init", "-q")
        (self.root / "app.py").write_text("value = 1\n")
        git(self.root, "add", "app.py")
        git(self.root, "-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", "baseline")
        (self.root / "app.py").write_text("value = 2\n")
        self.diff = git(self.root, "diff", "HEAD")
        git(self.root, "add", "app.py")
        git(self.root, "-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", "candidate")
        self.commit = git(self.root, "rev-parse", "HEAD").strip()
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.project = self.store.add_project("APP", "本地交付链测试", str(self.root))
        self.P = SimpleNamespace(data_dir=self.data, store=self.store, root=lambda p: Path(p["root"]),
                                 runner=RecordingRunner(self.store), project=self.store.project,
                                 flow=SimpleNamespace(accepted=mock.Mock()))
        (self.data / "agents.json").write_text(json.dumps({"local-test": {"cmd": [sys.executable, "-c", "pass"]}}))
        created = delivery.create(self.P, {"project": "APP", "title": "保存记录", "goal": "读取保存后的值",
                 "stages": ["requirements", "design", "develop", "quality", "security"]}, "本地测试人员")
        self.did = created["delivery"]["id"]
        self.ticket = self.store.ticket(created["delivery"]["ticket_id"])
        for stage in ("requirements", "design"):
            self.act("save_artifact", stage, body="当前需求及数据设计：读取保存后的值必须为 2。")
            self.review(stage)
        self.plan = self.complete("develop", "plan")
        self.fix = self.complete("develop", "fix")
        self.quality = self.complete("quality", "ask")
        self.security = self.complete("security", "ask")
        self.store.update_ticket(self.ticket["id"], "本地测试人员", status="verify")
        self.ticket = self.store.ticket(self.ticket["id"])
        self.assertTrue(delivery.signoff_binding(self.data, self.ticket["key"])["valid"])

    def act(self, action, stage, **body):
        return delivery.act(self.P, self.did, dict(action=action, stage=stage, **body), "本地测试人员")

    def review(self, stage):
        row = next(r for r in delivery.view(self.P, self.did)["stages"] if r["key"] == stage)
        self.act("review_artifact", stage, version=row["artifact"]["version"], confirm=True,
                 evidence="测试夹具：已核对当前版本及运行记录，不代表真实模型或产品验证。")

    def complete(self, stage, mode):
        rid = self.act("start", stage, agent="local-test", mode=mode)["started_run"]
        result = "```tmh-plan\n" + json.dumps({"files": [{"path": "app.py", "goal": "读回保存值"}],
                 "ac": [{"id": "A1", "text": "读取保存值为 2", "check": "读回值", "layer": "L4"}]}, ensure_ascii=False) + "\n```"
        self.store.update_run(rid, status="done", exit_code=0, result=result if mode == "plan" else "测试夹具产物")
        folder = self.data / "runs" / str(rid)
        folder.mkdir(parents=True, exist_ok=True)
        if mode == "fix":
            self.store.update_run(rid, diff=self.diff, decision="accepted:fixture@" + self.commit)
            (folder / "verify.json").write_text(json.dumps({"check": "pass", "verdict": "pass", "files": ["app.py"],
                "beyond_plan": [], "commands": [{"cmd": "fixture", "exit_code": 0}],
                "checked_commit": self.commit, "checked_diff": self.diff}))
        elif mode == "ask":
            binding = self.P.runner.calls[-1]["ticket"]["links"]["delivery_source"]
            (folder / "source.json").write_text(json.dumps({"actual_commit": self.commit, "code_unchanged": True, "binding": binding}))
        self.act("collect", stage, run_id=rid)
        self.review(stage)
        return rid

    def packed_link(self):
        signoff.pack(self.P, self.ticket, "本地测试人员")
        return signoff.issue(self.P, self.ticket, "本地测试人员", "验收测试人", note="集成测试保留未通过的其他验证门")

    def test_real_delivery_sources_ignore_a_later_ordinary_plan(self):
        binding = delivery.signoff_binding(self.data, self.ticket["key"])
        ordinary = self.store.create_run(self.project["id"], self.ticket["id"], "local-test", "plan", "测试", "普通方案")
        self.store.update_run(ordinary["id"], status="done", exit_code=0, result="普通工单后续计划")
        snap = signoff.snapshot(self.P, self.ticket)
        self.assertEqual((snap["plan_run"], snap["change"]["run"], snap["change"]["commit"]),
                         (self.plan, self.fix, self.commit))
        self.assertEqual(snap["delivery_binding"], binding)
        self.assertEqual(snap["ac"][0]["text"], "读取保存值为 2")
        self.assertEqual(binding["stages"]["quality"]["source_run"], self.quality)
        self.assertEqual(binding["stages"]["security"]["source_run"], self.security)

    def test_parse_gate_reads_the_resolved_object_even_with_a_hex_named_branch(self):
        # A newer unrelated branch whose name is the old abbreviated SHA must not
        # supply files to the old implementation's verification gates.
        (self.root / "app.py").write_text("def invalid syntax\n")
        git(self.root, "add", "app.py")
        git(self.root, "-c", "user.name=fixture", "-c", "user.email=fixture@localhost", "commit", "-qm", "unrelated invalid code")
        short = self.commit[:10]
        for name in (short, self.commit):
            git(self.root, "branch", name)
        self.store.update_run(self.fix, decision="accepted:fixture@" + short)
        self.assertIn("invalid syntax", git(self.root, "show", short + ":app.py"))
        snap = signoff.snapshot(self.P, self.ticket)
        self.assertEqual(snap["change"]["commit"], self.commit)
        self.assertTrue(snap["delivery_binding"]["valid"])
        parse_gate = next(g for g in snap["gates"] if g["id"] == "parse")
        self.assertEqual(parse_gate["state"], "pass", parse_gate)

    def test_changed_quality_receipt_invalidates_the_existing_signature(self):
        self.packed_link()
        seal = signoff.record_accept(self.P, self.ticket, "验收测试人", True, "本地签收测试")
        receipt = self.data / "runs" / str(self.quality) / "source.json"
        data = json.loads(receipt.read_text())
        data["actual_commit"] = "b" * 40
        receipt.write_text(json.dumps(data))
        state = signoff.state(self.data, self.ticket["key"])
        self.assertTrue(state["stale"])
        self.assertEqual(state["status"], "incomplete")
        self.assertIsNone(state["decision"])
        self.assertEqual(state["previous_decision"]["hash"], seal)
        self.assertFalse(state["delivery_binding"]["valid"])
        self.assertTrue(ev.check(signoff.records(self.data, self.ticket["key"]))[0])

    def test_failed_verification_prevents_old_link_signing_and_source_fallback(self):
        link = self.packed_link()
        path = self.data / "runs" / str(self.fix) / "verify.json"
        result = json.loads(path.read_text())
        result["commands"][0]["exit_code"] = 1
        result["check"] = "fail"
        path.write_text(json.dumps(result))
        snap = signoff.snapshot(self.P, self.ticket)
        self.assertIsNone(snap["change"])
        self.assertIsNone(snap["plan_run"])
        with self.assertRaises(ApiError) as caught:
            signoff.decide(self.P, link["token"], "sign", "验收测试人", {"A1": "pass"}, "")
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.store.ticket(self.ticket["id"])["status"], "verify")

    def test_upstream_revision_invalidates_current_reviewed_chain(self):
        self.packed_link()
        self.act("save_artifact", "requirements", body="新需求：读取值改为 3。")
        state = signoff.state(self.data, self.ticket["key"])
        self.assertTrue(state["binding_blocked"])
        self.assertFalse(state["delivery_binding"]["valid"])
        with self.assertRaises(ApiError) as caught:
            signoff.record_accept(self.P, self.ticket, "验收测试人", True, "不能绕过重新验证")
        self.assertEqual(caught.exception.code, 409)


if __name__ == "__main__":
    unittest.main()
