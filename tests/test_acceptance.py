import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tmh import acceptance as acc, guard, task
from tmh.path import path_check
from tmh.verify import take_baseline, verify

HERE = Path(__file__).resolve().parent
JAVA = HERE.parent / "examples" / "legacy-java-oa"
SVC = "src/main/java/com/acme/oa/service/LeaveService.java"
CTL = "src/main/java/com/acme/oa/controller/LeaveController.java"
AC = """| # | 验收条款 | 层级 | 检查方式（自动化测试 / 命令 / 人工） | 结果 |
|---|---|---|---|---|
| A1 | 传 status 只返回该状态的请假单 | L2 | LeaveListFilterTest | 未验证 |
| A2 | 真实库上筛选结果正确 | L4 | 业务方在测试环境查一次 | 未验证 |
"""
NO_AGENT = {k: "" for k in acc.AGENT_ENV}


class AcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()) / "oa"
        shutil.copytree(JAVA, self.root)
        g = lambda *a: subprocess.run(["git", *a], cwd=self.root, check=True, capture_output=True)
        g("init", "-q")
        g("add", "-A")
        g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
        take_baseline(self.root)
        self.c = task.new_task(self.root, "请假列表按审批状态筛选", "feature", "按状态筛选")
        self.addCleanup(shutil.rmtree, self.root.parent, True)

    def fill(self, table=AC, entry="`LeaveController.list`"):
        t = self.c.read_text(encoding="utf-8")
        t = re.sub(r"\| # \| 验收条款.*?\n(?:\|.*\n)*", table, t)
        t = re.sub(r"^- 入口：.*$", "- 入口：%s" % entry, t, flags=re.M)
        self.c.write_text(t, encoding="utf-8")

    def edit(self, rel, fn):
        p = self.root / rel
        p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")

    def test_a_new_contract_starts_as_a_draft_and_shows_its_state(self):
        self.assertIn("- 验收状态：draft_contract（草拟契约）", self.c.read_text(encoding="utf-8"))
        self.assertEqual(acc.load(self.root, "T001")["state"], "draft_contract")
        self.assertEqual(task.list_tasks(self.root)[0]["acceptance"], "draft_contract")

    def test_no_acceptance_criteria_no_implementation(self):
        with self.assertRaisesRegex(acc.Refused, "没有写验收条款"):
            acc.advance(self.root, "T001", "implementing")
        # an old contract (no layer column) is told how to migrate
        self.fill(AC.replace("| 层级 ", "").replace("|---|---|---|---|---|", "|---|---|---|---|").replace("| L2 ", "").replace("| L4 ", ""))
        with self.assertRaisesRegex(acc.Refused, "层级"):
            acc.advance(self.root, "T001", "implementing")
        self.fill()
        self.assertEqual(acc.advance(self.root, "T001", "implementing")["state"], "implementing")
        self.assertIn("- 验收状态：implementing（实现中）", self.c.read_text(encoding="utf-8"))

    def test_a_parallel_implementation_does_not_pass_the_path_check(self):
        self.fill()
        acc.advance(self.root, "T001", "implementing")
        # a new method nobody calls: tests could pass against it, the endpoint never reaches it
        self.edit(SVC, lambda s: s.rstrip().rstrip("}") + "\n    public List<Map<String, Object>> listByStatus(int page, String status) {\n"
                                 "        return mapper.selectPage((page - 1) * 20, page * 20);\n    }\n}\n")
        r = path_check(self.root, "T001")
        self.assertFalse(r["ok"])
        self.assertTrue(any("listByStatus" in b and "平行实现" in b for b in r["breaks"]), r)
        self.assertFalse(verify(self.root, run_tests=False, task="T001")["passed"])
        with self.assertRaisesRegex(acc.Refused, "verify"):
            acc.advance(self.root, "T001", "verify_local")
        # wired into the endpoint, the same method is on the path
        self.edit(CTL, lambda s: s.replace("return leaveService.list(page);", "return leaveService.listByStatus(page, null);"))
        r = path_check(self.root, "T001")
        self.assertTrue(r["ok"], r)
        self.assertTrue(verify(self.root, run_tests=False, task="T001")["passed"])
        rec = acc.advance(self.root, "T001", "verify_local")
        self.assertEqual(rec["state"], "verify_local")
        self.assertEqual(rec["evidence"][-1]["type"], "tmh_verify")

    def test_only_tests_or_config_do_not_reach_the_entry(self):
        self.fill()
        t = self.root / "src/test/java/com/acme/oa/LeaveFilterTest.java"
        t.write_text("class LeaveFilterTest {}\n", encoding="utf-8")
        self.edit("src/main/resources/application.yml", lambda s: s + "\nleave.filter: true\n")
        r = path_check(self.root, "T001")
        self.assertFalse(r["ok"])
        self.assertTrue(any("application.yml" in m for m in r["manual"]))  # config goes to a person, not counted either way
        self.assertTrue(any("没有一处产品代码改动" in p for p in r["problems"]))
        self.assertFalse(path_check(self.root, entry_names=["NoSuch.entry"])["ok"])

    def test_only_a_person_confirms_and_closes(self):
        self.fill()
        acc.advance(self.root, "T001", "implementing")
        self.edit(SVC, lambda s: s.replace("return mapper.selectPage((page - 1) * 20, page * 20);",
                                           "return mapper.selectPage((page - 1) * 20, page * 20); // status"))
        verify(self.root, run_tests=False, task="T001")
        acc.advance(self.root, "T001", "verify_local")
        with self.assertRaisesRegex(acc.Refused, "--ref"):
            acc.advance(self.root, "T001", "merged")
        acc.advance(self.root, "T001", "merged", ref="abc123")
        acc.advance(self.root, "T001", "deployed_awaiting_verify", build="jenkins-42")
        with self.assertRaisesRegex(acc.Refused, "L4"):  # A2 needs a person: no auto_verified
            acc.advance(self.root, "T001", "auto_verified")
        acc.advance(self.root, "T001", "needs_human", note="A2 要业务方在测试环境确认")
        with self.assertRaisesRegex(acc.Refused, "不能从"):  # closing skips nobody's confirmation
            acc.advance(self.root, "T001", "closed", who="张三")
        with mock.patch.dict(os.environ, dict(NO_AGENT, CLAUDECODE="1")):
            with self.assertRaisesRegex(acc.Refused, "只能由人"):
                acc.advance(self.root, "T001", "user_confirmed_fix", who="张三")
        with mock.patch.dict(os.environ, NO_AGENT):
            with self.assertRaisesRegex(acc.Refused, "--who"):
                acc.advance(self.root, "T001", "user_confirmed_fix", who="agent")
            rec = acc.advance(self.root, "T001", "user_confirmed_fix", who="张三", note="测试环境查过")
            self.assertEqual((rec["confirmed_by"], rec["state"]), ("张三", "user_confirmed_fix"))
            self.assertEqual(acc.advance(self.root, "T001", "closed", who="张三")["state"], "closed")
        self.assertEqual([r["task"] for r in acc.by_build(self.root, "jenkins-42")], ["T001"])
        self.assertEqual([h["to"] for h in acc.load(self.root, "T001")["history"]],
                         ["draft_contract", "implementing", "verify_local", "merged", "deployed_awaiting_verify", "needs_human",
                          "user_confirmed_fix", "closed"])

    def test_a_failed_check_goes_back_with_its_reason(self):
        self.fill()
        acc.advance(self.root, "T001", "implementing")
        self.edit(SVC, lambda s: s.replace("page * 20);", "page * 20); // x", 1))
        verify(self.root, run_tests=False, task="T001")
        acc.advance(self.root, "T001", "verify_local")
        with self.assertRaisesRegex(acc.Refused, "原因"):
            acc.advance(self.root, "T001", "implementing")
        self.assertEqual(acc.advance(self.root, "T001", "implementing", note="A1 空白 status 没去掉")["state"], "implementing")

    def test_agents_are_stopped_before_they_confirm_or_close(self):
        for cmd in ("python3 .tmh/tool/tmh.py accept confirm T001 --who 张三", "tmh accept close T001 --who 张三",
                    "tmh accept advance T001 --to user_confirmed_fix --who 张三"):
            self.assertEqual(guard.pre_bash({"tool_input": {"command": cmd}, "cwd": str(self.root)}), 2, cmd)
        self.assertEqual(guard.pre_bash({"tool_input": {"command": "tmh accept advance T001 --to verify_local"}, "cwd": str(self.root)}), 0)

    def test_corrections_that_recur_ask_for_a_reviewed_skill_change(self):
        for i in range(3):
            r = acc.correct(self.root, "T001", "too-big", "改了 %d 个无关文件" % (i + 2))
        self.assertTrue(r["due"])
        self.assertEqual(r["count"], 3)


if __name__ == "__main__":
    unittest.main()
