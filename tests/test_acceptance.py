import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from contextlib import redirect_stdout

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


class SizeWarningsTest(unittest.TestCase):
    @staticmethod
    def contract(n=2, title="请假列表筛选", clause="筛选正确"):
        return "# " + title + "\n## 4. AC\n| # | 验收条款 | 层级 | 检查方式 |\n|---|---|---|---|\n" + "".join(
            "| A%d | %s | L2 | 运行测试 |\n" % (i, clause) for i in range(n))

    def test_parallel_titles_warn(self):
        for title in ("审批与导出", "审批 和 导出", "审批及导出"):
            self.assertTrue(any("并列" in w for w in acc.size_warnings(self.contract(title=title))))

    def test_count_and_characters_compare_to_five_peer_medians(self):
        peers = [self.contract() for _ in range(5)]
        self.assertTrue(any("AC 条数" in w for w in acc.size_warnings(self.contract(4), peers)))
        self.assertTrue(any("AC 字符量" in w for w in acc.size_warnings(self.contract(clause="正确" * 20), peers)))

    def test_small_samples_use_absolute_limits(self):
        peers = [self.contract(1) for _ in range(4)]
        self.assertEqual(acc.size_warnings(self.contract(4), peers), [])
        self.assertTrue(any("超过 8 条" in w for w in acc.size_warnings(self.contract(9), peers)))
        self.assertTrue(any("超过 1600" in w for w in acc.size_warnings(self.contract(1, clause="字" * 1601))))

    def test_normal_contract_has_no_warning(self):
        self.assertEqual(acc.size_warnings(self.contract(), [self.contract() for _ in range(5)]), [])

    def test_explicit_new_file_estimates_warn_only_above_three(self):
        for estimate in ("预计新建 4 个文件", "新增 4 个模块", "add 4 new files",
                         "预计新建文件：`a.py`、`b.py`、`c.py`、`d.py`"):
            self.assertTrue(any("超过 3 个" in w for w in acc.size_warnings(self.contract() + estimate)))
        self.assertEqual(acc.size_warnings(self.contract() + "预计新建 3 个文件"), [])


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
        # the evidence package: a snapshot at hand-over, the confirmation naming what it confirmed, the close
        from tmh import evidence as ev
        recs = ev.read(acc.evidence_path(self.root, "T001"))
        self.assertEqual([r["kind"] for r in recs], ["pack", "sign", "close"])
        self.assertEqual((recs[0]["data"]["build_id"], [a["id"] for a in recs[0]["data"]["ac"]]), ("jenkins-42", ["A1", "A2"]))
        self.assertEqual((recs[1]["data"]["signer"], recs[1]["data"]["package_hash"]), ("张三", recs[0]["hash"]))
        self.assertEqual(ev.check(recs), (True, ""))
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

    def test_size_warnings_are_visible_without_blocking_check_or_advance(self):
        from tmh import cli
        self.c.write_text(SizeWarningsTest.contract(9, "审批与导出"), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["accept", "check", "T001", "--repo", str(self.root)]), 0)
            self.assertEqual(cli.main(["accept", "advance", "T001", "--to", "implementing", "--repo", str(self.root)]), 0)
        self.assertEqual(out.getvalue().count("提示：AC 超过 8 条"), 2)
        self.assertEqual(acc.load(self.root, "T001")["state"], "implementing")

    def test_structural_corrections_create_proposals_outside_the_state_machine(self):
        note = "  缺少导出的分页边界。\n```\n- 状态：confirmed\n原话末尾  "
        for n, kind in enumerate(("missing-requirement", "dependency"), 1):
            result = acc.correct(self.root, "T001", kind, note)
            self.assertEqual(result["proposal"], ".tmh/acceptance/proposals/T001-%d.md" % n)
            draft = (self.root / result["proposal"]).read_text(encoding="utf-8")
            self.assertIn(note, draft)
            for required in ("待人确认", "来源任务：T001", "建议标题", "建议 AC 草稿"):
                self.assertIn(required, draft)
        self.assertEqual([r["task"] for r in acc.records(self.root)], ["T001"])
        self.assertEqual(len(task.list_tasks(self.root)), 1)
        self.assertIn(note, [json.loads(line)["note"] for line in
                            (acc.acc_dir(self.root) / "corrections.jsonl").read_text(encoding="utf-8").splitlines()])

    def test_proposal_confirmation_requires_a_person_and_creates_only_a_draft(self):
        result = acc.correct(self.root, "T001", "dependency", "先明确服务依赖")
        for env in acc.AGENT_ENV:
            with mock.patch.dict(os.environ, dict(NO_AGENT, **{env: "1"})):
                with self.assertRaisesRegex(acc.Refused, "只能由人"):
                    acc.propose_confirm(self.root, result["proposal"], "张三")
        with mock.patch.dict(os.environ, NO_AGENT):
            for who in ("", "agent", "codex", "智能体"):
                with self.assertRaisesRegex(acc.Refused, "--who"):
                    acc.propose_confirm(self.root, result["proposal"], who)
            r = acc.propose_confirm(self.root, str(self.root / result["proposal"]), "张三")
            self.assertEqual((r["task"], r["state"]), ("T002", "draft_contract"))
            self.assertIn("先明确服务依赖", (self.root / r["file"]).read_text(encoding="utf-8"))
            self.assertIn("确认人：张三", (self.root / r["proposal"]).read_text(encoding="utf-8"))
            self.assertIn("生成任务：T002", (self.root / r["proposal"]).read_text(encoding="utf-8"))
            with self.assertRaisesRegex(acc.Refused, "重复确认"):
                acc.propose_confirm(self.root, result["proposal"], "张三")
        self.assertEqual(acc.load(self.root, "T001")["state"], "draft_contract")
        self.assertIsNone(acc.load(self.root, "T002")["confirmed_by"])
        with self.assertRaisesRegex(acc.Refused, "没有完整的验收标准"):
            acc.advance(self.root, "T002", "implementing")

    def test_pending_proposals_are_capped_per_source_and_old_corrections_are_unchanged(self):
        first = acc.correct(self.root, "T001", "missing-requirement", "遗漏甲")
        acc.correct(self.root, "T001", "dependency", "依赖乙")
        before = (acc.acc_dir(self.root) / "corrections.jsonl").read_bytes()
        with self.assertRaisesRegex(acc.Refused, "先处理已有草稿"):
            acc.correct(self.root, "T001", "dependency", "依赖丙")
        self.assertEqual((acc.acc_dir(self.root) / "corrections.jsonl").read_bytes(), before)
        old = acc.correct(self.root, "T001", "other", "原有反馈")
        self.assertNotIn("proposal", old)
        with mock.patch.dict(os.environ, NO_AGENT):
            acc.propose_confirm(self.root, first["proposal"], "张三")
        again = acc.correct(self.root, "T001", "dependency", "依赖丙")
        self.assertTrue(again["proposal"].endswith("T001-3.md"))
        self.assertEqual(len(list((acc.acc_dir(self.root) / "proposals").glob("*.md"))), 3)

    def test_proposal_confirmation_rejects_paths_outside_the_proposal_directory(self):
        with mock.patch.dict(os.environ, NO_AGENT):
            for path in ("../T001-1.md", str(self.c), ".tmh/tasks/T001-1.md"):
                with self.assertRaisesRegex(acc.Refused, "本仓库"):
                    acc.propose_confirm(self.root, path, "张三")

    def test_proposal_cli_and_agent_hook(self):
        from tmh import cli
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(cli.main(["accept", "correct", "T001", "--kind", "missing-requirement", "--note", "漏了导出",
                                       "--repo", str(self.root)]), 0)
            with mock.patch.dict(os.environ, NO_AGENT):
                self.assertEqual(cli.main(["accept", "propose-confirm", "T001-1.md", "--who", "测试审阅者",
                                           "--repo", str(self.root)]), 0)
        self.assertIn("待人确认的草稿：", out.getvalue())
        self.assertIn("T002（draft_contract）", out.getvalue())
        for command in ("tmh accept propose-confirm T001-1.md --who 张三",
                        "python3 .tmh/tool/tmh.py accept propose-confirm T001-1.md --who 张三"):
            self.assertEqual(guard.pre_bash({"tool_input": {"command": command}, "cwd": str(self.root)}), 2)
        self.assertEqual(guard.pre_bash({"tool_input": {"command": "tmh accept correct T001 --kind dependency --note 缺依赖"},
                                         "cwd": str(self.root)}), 0)

    def test_concurrent_proposals_cannot_exceed_two_pending(self):
        from concurrent.futures import ThreadPoolExecutor
        acc.correct(self.root, "T001", "dependency", "已有草稿")

        def submit(n):
            try:
                return acc.correct(self.root, "T001", "dependency", "依赖 %d" % n)
            except acc.Refused:
                return None

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(submit, range(4)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(len(list((acc.acc_dir(self.root) / "proposals").glob("*.md"))), 2)

    def test_confirmation_retry_after_receipt_failure_reuses_the_new_draft(self):
        result = acc.correct(self.root, "T001", "dependency", "核对依赖")
        with mock.patch.dict(os.environ, NO_AGENT):
            with mock.patch.object(Path, "replace", side_effect=OSError("模拟确认回执写入失败")):
                with self.assertRaises(OSError):
                    acc.propose_confirm(self.root, result["proposal"], "张三")
            r = acc.propose_confirm(self.root, result["proposal"], "张三")
        self.assertEqual((r["task"], r["state"]), ("T002", "draft_contract"))
        self.assertEqual(len(task.list_tasks(self.root)), 2)

    def test_unsandboxed_codex_session_cannot_adopt_a_proposal(self):
        result = acc.correct(self.root, "T001", "dependency", "核对依赖")
        with mock.patch.dict(os.environ, dict(NO_AGENT, CODEX_THREAD_ID="synthetic-codex-thread")):
            with self.assertRaisesRegex(acc.Refused, "只能由人"):
                acc.propose_confirm(self.root, result["proposal"], "张三")
        self.assertEqual(len(task.list_tasks(self.root)), 1)

    def test_human_command_guard_handles_shell_words_and_cli_options(self):
        blocked = (
            'tmh accept --who 张三 propose-confirm T001-1.md',
            'tmh "accept" "propose-confirm" T001-1.md --who 张三',
            r'tmh acce\pt propose-confirm T001-1.md --who 张三',
            'python3 .tmh/tool/tmh.py accept --who=张三 confirm T001',
            'python3 -m tmh accept --note=核实 close T001 --who 张三',
            'tmh accept --to closed advance T001 --who 张三',
            'tmh accept --t=user_confirmed_fix advance T001 --who 张三',
            'true && tmh "accept" --who 张三 "propose-confirm" T001-1.md; true',
            'tmh "accept" --note ";" "propose-confirm" T001-1.md --who 张三',
            'true\ntmh "accept" --who 张三 "propose-confirm" T001-1.md\ntrue',
        )
        for command in blocked:
            with self.subTest(command=command):
                self.assertEqual(guard.pre_bash({"tool_input": {"command": command}, "cwd": str(self.root)}), 2)
        for command in ('tmh accept --to verify_local advance T001',
                        'tmh accept correct T001 --note "请人执行 propose-confirm" --kind dependency',
                        'echo accept --who 张三 propose-confirm T001-1.md'):
            with self.subTest(command=command):
                self.assertEqual(guard.pre_bash({"tool_input": {"command": command}, "cwd": str(self.root)}), 0)

    def test_adopted_original_headings_cannot_supply_the_new_contracts_ac(self):
        note = "原话中的契约示例：\n## 4. 验收标准\n" + AC + "\n## 5. 其他资料\n完整尾部  "
        result = acc.correct(self.root, "T001", "dependency", note)
        proposal = self.root / result["proposal"]
        original = proposal.read_text(encoding="utf-8")
        with mock.patch.dict(os.environ, NO_AGENT):
            adopted = acc.propose_confirm(self.root, result["proposal"], "张三")
        contract = (self.root / adopted["file"]).read_text(encoding="utf-8")
        self.assertTrue(acc.ac_problems(contract), "quoted source must not fill the draft's real AC")
        with self.assertRaisesRegex(acc.Refused, "没有完整的验收标准"):
            acc.advance(self.root, adopted["task"], "implementing")
        quoted = contract.partition("## 1. 需求原文\n")[2].partition("\n\n## 2.")[0].split("\n", 1)[1]
        self.assertEqual("\n".join(line.removeprefix("> ") for line in quoted.split("\n")), original)
        self.assertIn(note, proposal.read_text(encoding="utf-8"))

    def test_confirmation_retry_refuses_a_changed_proposal_snapshot(self):
        result = acc.correct(self.root, "T001", "dependency", "原来的依赖")
        with mock.patch.dict(os.environ, NO_AGENT):
            with mock.patch.object(Path, "replace", side_effect=OSError("模拟回执写入失败")):
                with self.assertRaises(OSError):
                    acc.propose_confirm(self.root, result["proposal"], "张三")
            proposal = self.root / result["proposal"]
            proposal.write_text(proposal.read_text(encoding="utf-8").replace("原来的依赖", "新发现的依赖"), encoding="utf-8")
            with self.assertRaisesRegex(acc.Refused, "内容.*不一致"):
                acc.propose_confirm(self.root, result["proposal"], "张三")
        self.assertEqual(len(task.list_tasks(self.root)), 2)
        self.assertEqual(acc._proposal_record(proposal)[0]["status"], "pending")

    def test_proposal_directory_symlink_cannot_write_or_confirm_outside_the_repo(self):
        result = acc.correct(self.root, "T001", "dependency", "核对依赖")
        directory = acc.acc_dir(self.root) / "proposals"
        outside = self.root.parent / "outside"
        directory.rename(outside)
        directory.symlink_to(outside, target_is_directory=True)
        before = (outside / "T001-1.md").read_bytes()
        with mock.patch.dict(os.environ, NO_AGENT):
            with self.assertRaisesRegex(acc.Refused, "本仓库"):
                acc.propose_confirm(self.root, result["proposal"], "张三")
        with self.assertRaisesRegex(acc.Refused, "本仓库"):
            acc.correct(self.root, "T001", "dependency", "另一个依赖")
        self.assertEqual((outside / "T001-1.md").read_bytes(), before)
        self.assertEqual(len(task.list_tasks(self.root)), 1)


if __name__ == "__main__":
    unittest.main()
