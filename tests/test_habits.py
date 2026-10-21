"""Habit derivation is read-only, private by default, and honest about sample size (G9).

Fixture: the same bare-sqlite style as tests/test_platform.py (temp dir + Store + add_project),
with several people, tickets, runs, acceptance outcomes and knowledge revisions.
"""
import json
import tempfile
import unittest
from pathlib import Path

from tmh.platform import habits
from tmh.platform.store import Store, now


class HabitFixture(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="tmh-habits-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.store = Store(self.dir / "platform.db")
        self.app = self.store.add_project("APP", "示例应用", str(self.dir))
        self.erp = self.store.add_project("ERP", "业务系统", str(self.dir))

    # ---- builders (public Store methods only: the fixture must look like real data)
    def ticket(self, key="APP", title="工单", type="bug", author="李"):
        p = self.app if key == "APP" else self.erp
        return self.store.create_ticket(p["id"], title, author, type=type)

    def add_run(self, author, mode, ticket=None, prompt="", status="done", retry_of=None, project=None):
        p = project or self.app
        t = ticket or self.ticket()
        r = self.store.create_run(p["id"], t["id"], "codex", mode, author, prompt, retry_of=retry_of)
        self.store.update_run(r["id"], status=status, exit_code=0 if status == "done" else 1,
                              started=now(), ended=now(), result="done" if status == "done" else "")
        return self.store.run(r["id"])

    def accept(self, ticket, passed=True, note=""):
        self.store.event(ticket["id"], "甲方张工", "accept" if passed else "reject",
                         ("验收通过" if passed else "验收不通过") + ("：" + note if note else ""),
                         {"result": "pass" if passed else "fail", "note": note})

    def page(self, author, key="APP"):
        p = self.app if key == "APP" else self.erp
        self.store.x("INSERT INTO knowledge_revisions(id,project_id,source_id,commit_sha,root,analyzer,status,stage,created,author) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?)",
                     ("rev-%s-%s" % (key, author), p["id"], 1, "abc123", str(self.dir / key.lower()),
                      "analyzer", "ready", "done", now(), author))


class PersonalViewTest(HabitFixture):
    def test_aggregates_modes_ticket_types_and_domains(self):
        t1 = self.ticket(title="登录报错")
        t2 = self.ticket(title="导出需求", type="feature", key="ERP")
        self.add_run("alice", "ask", t1)
        self.add_run("alice", "analyze", t1)
        self.add_run("alice", "fix", t1)
        self.add_run("alice", "fix", t2, project=self.erp)
        self.add_run("alice", "verify", t1)
        self.add_run("bob", "ask", t2, project=self.erp)  # another person must not leak into alice's view

        out = habits.personal(self.store, "alice")
        self.assertEqual(out["view"], "personal")
        self.assertEqual(out["modes"], {"analyze": 1, "ask": 1, "fix": 2, "verify": 1})
        self.assertEqual(out["ticket_types"], {"bug": 1, "feature": 1})
        self.assertEqual(out["domains"], {"APP": 4, "ERP": 1})
        self.assertEqual(out["sample"]["runs"], 5)
        self.assertTrue(out["fair"])
        self.assertEqual(out["modes_share"], {"analyze": 0.2, "ask": 0.2, "fix": 0.4, "verify": 0.2})
        self.assertNotIn("bob", json.dumps(out))

    def test_small_sample_withholds_shares_and_says_why(self):
        self.add_run("carol", "ask")
        self.add_run("carol", "fix")
        out = habits.personal(self.store, "carol")
        self.assertFalse(out["fair"])
        self.assertIsNone(out["modes_share"])
        self.assertIsNone(out["ticket_types_share"])
        self.assertTrue(any("少于" in note and str(habits.MIN_SAMPLE) in note for note in out["notes"]))
        self.assertEqual(out["sample"]["runs"], 2)

    def test_project_filter_scopes_counts(self):
        t_app, t_erp = self.ticket(), self.ticket(key="ERP")
        self.add_run("alice", "fix", t_app)
        self.add_run("alice", "fix", t_erp, project=self.erp)
        out = habits.personal(self.store, "alice", project_id=self.erp["id"])
        self.assertEqual(out["modes"], {"fix": 1})
        self.assertEqual(out["domains"], {"ERP": 1})


class ReworkAndReviewTest(HabitFixture):
    def test_rework_counts_rejections_failures_and_retries_but_not_their_wording(self):
        t = self.ticket(title="报销单金额不对")
        self.add_run("alice", "fix", t)
        self.add_run("alice", "fix", t, status="failed")
        first = self.add_run("alice", "fix", t)
        self.add_run("alice", "fix", t, retry_of=first["id"])
        self.accept(t, passed=False, note="金额计算逻辑不对，功能结果不符")
        self.accept(t, passed=False, note="页面太慢，性能超时")

        out = habits.personal(self.store, "alice")
        self.assertEqual(out["rework"]["accept_fail"], 2)
        self.assertEqual(out["rework"]["failed_runs"], 1)
        self.assertEqual(out["rework"]["retry_runs"], 1)
        self.assertGreaterEqual(out["rework"]["reasons"].get("功能正确性", 0), 1)
        self.assertGreaterEqual(out["rework"]["reasons"].get("性能与稳定", 0), 1)
        dumped = json.dumps(out, ensure_ascii=False)
        self.assertNotIn("金额计算逻辑不对", dumped)  # note text never leaves
        self.assertNotIn("页面太慢", dumped)

    def test_review_focus_categories_come_from_acceptance_notes(self):
        t = self.ticket()
        self.add_run("alice", "fix", t)
        self.accept(t, passed=False, note="权限越权风险，安全需要再确认")
        self.accept(t, passed=True, note="测试用例和证据不完整")
        out = habits.personal(self.store, "alice")
        self.assertGreaterEqual(out["review_focus"]["categories"].get("安全与权限", 0), 1)
        self.assertGreaterEqual(out["review_focus"]["categories"].get("测试与证据", 0), 1)
        self.assertNotIn("权限越权风险", json.dumps(out, ensure_ascii=False))

    def test_rejection_on_a_ticket_the_person_never_touched_is_not_their_rework(self):
        mine, theirs = self.ticket(), self.ticket(title="别人的单")
        self.add_run("alice", "fix", mine)
        self.add_run("bob", "fix", theirs)
        self.accept(theirs, passed=False, note="功能逻辑不对")
        self.assertEqual(habits.personal(self.store, "alice")["rework"]["accept_fail"], 0)
        self.assertEqual(habits.personal(self.store, "bob")["rework"]["accept_fail"], 1)


class PromptFingerprintTest(HabitFixture):
    def test_only_hash_length_bucket_and_categories_are_returned(self):
        secret = "客户方内部代号 X-Plan，报销单金额按部门预算比例分摊，报错日志见 /opt/secret/app.log"
        self.add_run("alice", "analyze", prompt=secret)
        out = habits.personal(self.store, "alice")
        fp = out["prompt_fingerprints"]
        self.assertEqual(fp["total"], 1)
        item = fp["hashes"][0]
        self.assertEqual(set(item), {"hash", "length", "bucket", "categories"})
        self.assertEqual(len(item["hash"]), 12)
        self.assertEqual(item["length"], len(secret))
        self.assertIn(item["bucket"], ("短", "中", "长"))
        self.assertIn("问题定位", item["categories"])
        dumped = json.dumps(out, ensure_ascii=False)
        for raw in ("X-Plan", "/opt/secret", "分摊", "报错日志见"):
            self.assertNotIn(raw, dumped)
        self.assertNotIn("prompt", {k for k in out if k != "prompt_fingerprints"})

    def test_same_prompt_same_hash_without_storing_text(self):
        prompt = "请定位这个报错的原因"
        self.add_run("alice", "analyze", prompt=prompt)
        self.add_run("alice", "analyze", prompt=prompt)
        self.add_run("alice", "analyze", prompt=prompt + "（补充）")
        hashes = [f["hash"] for f in habits.personal(self.store, "alice")["prompt_fingerprints"]["hashes"]]
        self.assertEqual(hashes[0], hashes[1])
        self.assertNotEqual(hashes[0], hashes[2])

    def test_redact_default_hides_identity_but_never_needs_raw_text(self):
        self.add_run("alice", "fix")
        default = habits.personal(self.store, "alice")
        self.assertNotIn("person", default)
        self.assertFalse(default["privacy"]["contains_raw_text"])
        named = habits.personal(self.store, "alice", redact=False)
        self.assertEqual(named["person"], "alice")
        self.assertFalse(named["privacy"]["contains_raw_text"])


class TeamViewTest(HabitFixture):
    def _populate(self, people=("alice", "bob"), tickets=6, decisions=6):
        made = []
        modes = ["ask", "analyze", "plan", "fix", "verify", "understand"]
        for i in range(tickets):
            t = self.ticket(title="团队工单 %d" % i, type="bug" if i % 2 else "feature")
            made.append(t)
            self.add_run(people[i % len(people)], modes[i % len(modes)], t)
        for i in range(decisions):
            self.accept(made[i % len(made)], passed=bool(i % 3), note="性能太慢" if i % 2 else "功能逻辑不对")
        return made

    def test_withholds_ratios_below_the_sample_floor(self):
        made = self._populate(tickets=2, decisions=1)
        out = habits.team(self.store)
        self.assertEqual(out["view"], "team")
        self.assertFalse(out["fair"])
        self.assertIsNone(out["modes_share"])
        self.assertIsNone(out["ticket_types_share"])
        self.assertIsNone(out["rework_rate"])
        self.assertIsNone(out["review_focus_share"])
        self.assertTrue(any("%d" % habits.MIN_SAMPLE in n for n in out["notes"]))
        self.assertEqual(out["sample"]["tickets"], len(made))
        self.assertEqual(out["sample"]["decisions"], 1)
        # counts are still allowed: the floor withholds rates, not facts
        self.assertEqual(out["modes"], {"analyze": 1, "ask": 1})

    def test_team_sufficient_sample_gives_anonymous_ratios(self):
        made = self._populate(tickets=6, decisions=6)
        out = habits.team(self.store)
        self.assertTrue(out["fair"], out["notes"])
        self.assertEqual(out["sample"]["tickets"], 6)
        self.assertEqual(out["sample"]["decisions"], 6)
        self.assertEqual(out["sample"]["participants"], 2)
        self.assertAlmostEqual(sum(out["modes_share"].values()), 1.0, places=2)
        self.assertAlmostEqual(sum(out["ticket_types_share"].values()), 1.0, places=2)
        # 6 decisions: i=0/3 are failable (bool(i%3) false) -> 2 fails in 6
        self.assertEqual(out["rework_rate"], round(2 / 6, 3))
        dumped = json.dumps(out, ensure_ascii=False)
        self.assertNotIn("alice", dumped)  # no per-person rows
        self.assertNotIn("bob", dumped)
        self.assertNotIn("性能太慢", dumped)
        self.assertEqual(out["min_sample"], habits.MIN_SAMPLE)

    def test_project_scoped_team_view(self):
        self._populate(tickets=6, decisions=6)
        erp = self.ticket(key="ERP", title="ERP 工单")
        self.add_run("alice", "fix", erp, project=self.erp)
        self.accept(erp, passed=True, note="功能 OK")
        scoped = habits.team(self.store, project_id=self.erp["id"])
        self.assertEqual(scoped["sample"]["tickets"], 1)
        self.assertFalse(scoped["fair"])
        self.assertEqual(scoped["projects"], {"ERP": 1})
        self.assertNotIn("APP", scoped["projects"])


class ReadOnlyAndEmptyTest(HabitFixture):
    TABLES = ("projects", "tickets", "events", "runs", "points", "knowledge_revisions")

    def _snapshot(self):
        return {t: [dict(r) for r in self.store.q("SELECT * FROM %s ORDER BY rowid" % t)] for t in self.TABLES}

    def test_calls_change_no_row_and_no_sqlite_write_counter(self):
        t = self.ticket()
        self.add_run("alice", "fix", t, prompt="定位报错原因")
        self.accept(t, passed=False, note="功能逻辑不对")
        self.page("alice")
        before = self._snapshot()
        changes = self.store.db.total_changes

        habits.available(self.store)
        habits.personal(self.store, "alice")
        habits.personal(self.store, "alice", redact=False)
        habits.team(self.store)

        self.assertEqual(self._snapshot(), before)
        self.assertEqual(self.store.db.total_changes, changes, "habits must not write to the database")

    def test_empty_store_returns_zeros_instead_of_raising(self):
        empty = Store(self.dir / "empty.db")
        out = habits.personal(empty, "nobody")
        self.assertEqual(out["sample"]["runs"], 0)
        self.assertFalse(out["fair"])
        self.assertEqual(out["modes"], {})
        self.assertEqual(out["prompt_fingerprints"]["total"], 0)
        self.assertEqual(out["knowledge_writing"], {"kb_runs": 0, "pages_written": 0})
        self.assertIsNone(out["modes_share"])

        team = habits.team(empty)
        self.assertFalse(team["fair"])
        self.assertEqual(team["sample"], {"tickets": 0, "runs": 0, "decisions": 0, "participants": 0})
        self.assertIsNone(team["rework_rate"])

        probe = habits.available(empty)
        self.assertEqual((probe["runs"], probe["tickets"], probe["acceptance_events"], probe["knowledge_revisions"]),
                         (0, 0, 0, 0))

    def test_knowledge_writing_counts_kb_runs_and_pages(self):
        t = self.ticket()
        self.add_run("alice", "kb", t)
        self.add_run("alice", "kb", t)
        self.page("alice")
        self.page("alice", key="ERP")
        out = habits.personal(self.store, "alice")
        self.assertEqual(out["knowledge_writing"], {"kb_runs": 2, "pages_written": 2})
        self.assertEqual(habits.team(self.store)["knowledge_pages"], 2)


class AvailableProbeTest(HabitFixture):
    def test_probe_reports_source_sizes_and_the_privacy_policy(self):
        t = self.ticket()
        self.add_run("alice", "ask", t)
        self.accept(t, passed=True)
        self.page("alice")
        probe = habits.available(self.store)
        self.assertEqual(probe["runs"], 1)
        self.assertEqual(probe["tickets"], 1)
        self.assertEqual(probe["acceptance_events"], 1)
        self.assertEqual(probe["knowledge_revisions"], 1)
        self.assertEqual(probe["min_sample"], 5)
        self.assertIn("原文", probe["raw_text_policy"])
        self.assertEqual(habits.REDACT, True)


if __name__ == "__main__":
    unittest.main()
