"""Fixed-version human verdicts feed memory without legacy adoption or release.

Git changes are real temporary repositories; independent verification is the
explicitly synthetic fixture used by the team authorization tests.
"""
import unittest
from unittest.mock import patch

import test_team_workspace as team_fixture
from tmh.platform import candidates, learn, memory, team
from tmh.platform.errors import ApiError


class CandidateMemoryTests(unittest.TestCase):
    setUp = team_fixture.TeamWorkspaceTest.setUp
    git = team_fixture.TeamWorkspaceTest.git
    action = team_fixture.TeamWorkspaceTest.action
    assign = team_fixture.TeamWorkspaceTest.assign
    candidate = team_fixture.TeamWorkspaceTest.candidate
    synthetic_checks = team_fixture.TeamWorkspaceTest.synthetic_checks
    assess = team_fixture.TeamWorkspaceTest.assess
    approve = team_fixture.TeamWorkspaceTest.approve

    def ready(self):
        approved = self.approve()
        evidence = approved["item"]["candidate"]["evidence_hash"]
        self.action("candidate_merge", "bob", candidate_id=self.cid, evidence_hash=evidence)
        return evidence

    def verdict(self, evidence, passed=True, note="创建记录并刷新后仍能查看；合成测试数据"):
        return self.action("business_accept", "bob", candidate_id=self.cid, evidence_hash=evidence,
                           result="pass" if passed else "fail", note=note)

    def test_explicit_success_creates_full_draft_with_exact_candidate_and_human_sources(self):
        evidence = self.ready()
        note = "创建记录并刷新后仍能查看。" * 500
        with patch.object(self.P.flow, "accepted", side_effect=AssertionError("must not trigger release")):
            response = self.verdict(evidence, note=note)
        cards = learn.lessons(self.P.data_dir, "TEAM")
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual(card["status"], "candidate")
        self.assertIsNone(card["shared"])
        self.assertIn(note, card["verify"])
        source = card["provenance"]
        self.assertEqual(source["kind"], "fixed_candidate")
        self.assertEqual(source["commit"], self.commit)
        self.assertEqual(source["base_commit"], self.base)
        self.assertEqual(source["candidate_id"], self.cid)
        self.assertEqual(source["evidence_hash"], evidence)
        self.assertEqual(source["assessment"]["results"][0]["id"], "AC1")
        self.assertEqual(source["acceptance"]["by"], "bob")
        self.assertFalse(source["acceptance"]["customer_signature"])
        self.assertEqual(response["result"]["memory"]["lesson_id"], card["id"])
        self.assertFalse(response["item"]["acceptance_memory"]["pending"])
        self.assertFalse(response["item"]["acceptance_memory"]["can_retry"])
        self.assertFalse(self.P.store.q("SELECT * FROM events WHERE kind='adopt'"))
        self.assertEqual(memory.dispatch_read(self.P, {"project": "TEAM", "section": "lessons"}, "bob")["lessons"][0]["id"], card["id"])

    def test_failure_is_a_draft_counterexample_and_retries_do_not_duplicate_it(self):
        evidence = self.ready()
        note = "刷新后记录消失；不能把接口返回成功当作持久保存成功。"
        self.verdict(evidence, False, note)
        self.verdict(evidence, False, note)
        cards = learn.lessons(self.P.data_dir, "TEAM")
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["kind"], "reject")
        self.assertEqual(cards[0]["status"], "candidate")
        self.assertIn(note, cards[0]["anti"])
        self.assertEqual(cards[0]["provenance"]["acceptance"]["result"], "fail")
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='reject'")), 1)
        self.assertEqual(self.P.store.ticket(self.ticket["id"])["status"], "doing")

    def test_success_replay_after_close_reuses_the_original_acceptance_and_memory(self):
        evidence = self.ready()
        first = self.verdict(evidence)
        second = self.verdict(evidence)
        self.assertEqual(first["result"]["memory"]["lesson_id"], second["result"]["memory"]["lesson_id"])
        self.assertEqual(len(learn.lessons(self.P.data_dir, "TEAM")), 1)
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='accept'")), 1)

    def test_review_and_merge_are_not_business_verdicts(self):
        self.ready()
        self.assertEqual(learn.lessons(self.P.data_dir, "TEAM"), [])
        with self.assertRaises(ApiError):
            self.verdict("stale-evidence")
        self.assertEqual(learn.lessons(self.P.data_dir, "TEAM"), [])

    def test_failed_memory_write_keeps_verdict_and_explicit_retry_recovers_once(self):
        evidence = self.ready()
        with patch("tmh.platform.learn.add_lesson", side_effect=OSError("synthetic disk failure")):
            result = self.verdict(evidence)
        self.assertEqual(result["result"]["status"], "closed")
        self.assertTrue(result["result"]["memory"]["pending"])
        pending = result["item"]["acceptance_memory"]
        self.assertTrue(pending["can_retry"])
        self.assertEqual(pending["candidate_id"], self.cid)
        self.assertEqual(pending["evidence_hash"], evidence)
        self.assertFalse(team.item(self.P, self.P.store.ticket(self.ticket["id"]), "alice")["acceptance_memory"]["can_retry"])
        self.assertEqual(learn.lessons(self.P.data_dir, "TEAM"), [])
        repaired = self.verdict(evidence)
        self.assertFalse(repaired["result"]["memory"].get("pending", False))
        self.assertEqual(len(learn.lessons(self.P.data_dir, "TEAM")), 1)
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='accept'")), 1)

    def test_reused_memory_outcome_is_credited_once_by_the_human_verdict(self):
        evidence = self.ready()
        prior = learn.add_lesson(self.P.data_dir, {"project": "TEAM", "title": "刷新持久化", "status": "active", "fix": "保存后刷新检查"})
        learn.note_used(self.P.data_dir, self.ticket, [prior], "fix")
        self.verdict(evidence)
        self.verdict(evidence)
        self.assertEqual(learn.lesson(self.P.data_dir, prior["id"])["stats"]["passed"], 1)

    def test_later_failure_pauses_only_success_memory_for_the_same_fixed_candidate(self):
        evidence = self.ready()
        response = self.verdict(evidence)
        success_id = response["result"]["memory"]["lesson_id"]
        learn.set_status(self.P.data_dir, success_id, "active", "bob", "核对本次成功经验")
        unrelated = learn.add_lesson(self.P.data_dir, {"project": "TEAM", "title": "其他问题", "status": "active", "fix": "另一办法"})
        self.P.store.update_ticket(self.ticket["id"], "bob", status="doing")
        self.verdict(evidence, False, "重新打开工单检查，刷新后数据丢失")
        prior = learn.lesson(self.P.data_dir, success_id)
        self.assertEqual(prior["status"], "probation")
        self.assertEqual(prior["history"][-1]["provenance"]["result"], "fail")
        self.assertEqual(learn.lesson(self.P.data_dir, unrelated["id"])["status"], "active")
        # An explicit later restoration is not undone by transport retries.
        learn.set_status(self.P.data_dir, success_id, "active", "bob", "人工复核并恢复")
        self.verdict(evidence, False, "重新打开工单检查，刷新后数据丢失")
        self.assertEqual(learn.lesson(self.P.data_dir, success_id)["status"], "active")

    def test_partial_projection_stays_pending_until_credit_is_recovered(self):
        evidence = self.ready()
        with patch("tmh.platform.learn._credit", side_effect=OSError("synthetic log failure")):
            result = self.verdict(evidence)
        self.assertEqual(len(learn.lessons(self.P.data_dir, "TEAM")), 1)
        self.assertTrue(result["item"]["acceptance_memory"]["pending"])
        repaired = self.verdict(evidence)
        self.assertFalse(repaired["item"]["acceptance_memory"]["pending"])
        self.assertEqual(len(learn.lessons(self.P.data_dir, "TEAM")), 1)

    def test_delayed_memory_retry_cannot_credit_memory_used_after_the_verdict(self):
        evidence = self.ready()
        with patch("tmh.platform.learn.add_lesson", side_effect=OSError("synthetic disk failure")):
            self.verdict(evidence)
        later = learn.add_lesson(self.P.data_dir, {"project": "TEAM", "title": "验收后的新工作", "status": "active", "fix": "另一办法"})
        learn.note_used(self.P.data_dir, self.ticket, [later], "fix")
        self.assertEqual([x["id"] for x in learn.credit_snapshot(self.P, self.ticket)], [later["id"]])
        self.verdict(evidence)
        self.assertEqual(learn.lesson(self.P.data_dir, later["id"])["stats"]["passed"], 0)
        self.assertEqual([x["id"] for x in learn.credit_snapshot(self.P, self.ticket)], [later["id"]])
        learn.note_used(self.P.data_dir, self.ticket, [later], "fix")
        self.assertEqual(learn.lesson(self.P.data_dir, later["id"])["stats"]["used"], 1)
        learn._credit(self.P, self.ticket, True, "bob")
        self.assertEqual(learn.lesson(self.P.data_dir, later["id"])["stats"]["passed"], 1)

    def test_same_second_new_injection_of_same_memory_survives_delayed_verdict(self):
        evidence = self.ready()
        card = learn.add_lesson(self.P.data_dir, {"project": "TEAM", "title": "同一经验再次使用", "status": "active", "fix": "核对持久保存"})
        with patch("tmh.platform.learn.now", return_value="2026-10-22 12:00:00"):
            learn.note_used(self.P.data_dir, self.ticket, [card], "fix")
            with patch("tmh.platform.learn.add_lesson", side_effect=OSError("synthetic card failure")):
                self.verdict(evidence)
            learn.note_used(self.P.data_dir, self.ticket, [card], "fix")
            self.assertEqual(learn.lesson(self.P.data_dir, card["id"])["stats"]["used"], 2)
            self.verdict(evidence)
            self.assertEqual(learn.lesson(self.P.data_dir, card["id"])["stats"]["passed"], 1)
            self.assertEqual([x["id"] for x in learn.credit_snapshot(self.P, self.ticket)], [card["id"]])
            learn._credit(self.P, self.ticket, True, "bob")
            self.assertEqual(learn.lesson(self.P.data_dir, card["id"])["stats"]["passed"], 2)

    def test_delayed_older_verdict_does_not_consume_newer_same_memory_use(self):
        card = learn.add_lesson(self.P.data_dir, {"project": "TEAM", "title": "跨验收的同一经验", "status": "active", "fix": "核对持久保存"})
        learn.note_used(self.P.data_dir, self.ticket, [card], "fix")
        old = learn.credit_snapshot(self.P, self.ticket)
        # A traditional verdict consumes the first injection. The same card's
        # subsequent use is a distinct append position even in the same second.
        learn._credit(self.P, self.ticket, True, "bob")
        learn.note_used(self.P.data_dir, self.ticket, [card], "fix")
        learn._credit(self.P, self.ticket, True, "bob", source_key="delayed-original", uses=old)
        self.assertEqual([x["id"] for x in learn.credit_snapshot(self.P, self.ticket)], [card["id"]])
