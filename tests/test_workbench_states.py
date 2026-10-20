"""A requirement says the same thing on the client, requirements and ticket pages."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tmh.platform import handwork, signoff, workbench
from tmh.platform.server import Platform, api_ticket


class WorkbenchStatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-state-")
        self.data = Path(self.tmp.name)
        (self.data / "autoflow.json").write_text('{"on": false, "preview": "off"}', encoding="utf-8")
        self.P = Platform(self.data, "tester")
        self.project = self.P.store.add_project("STATE", "状态测试", str(self.data))
        self.client = workbench.create_client(self.P, {"name": "客户王总"}, "tester")

    def tearDown(self):
        self.P.store.db.close()
        self.tmp.cleanup()

    def ticket(self, **links):
        return self.P.store.create_ticket(
            self.project["id"], "审批页面显示剩余余额", "tester", type="feature",
            body="## 验收标准\n- A1 审批页面显示剩余余额；怎么验：打开审批页面核对余额\n",
            links=dict(links, client=self.client["id"]))

    def update(self, t, **values):
        return self.P.store.update_ticket(t["id"], "tester", **values)

    def record_run(self, t, status="running", mode="fix", agent="test-agent"):
        r = self.P.store.create_run(self.project["id"], t["id"], agent, mode, "tester", "测试运行记录")
        self.P.store.update_run(r["id"], status=status)
        return r

    def state(self, t):
        t = self.P.store.ticket(t["id"])
        return workbench.states(self.P, [t])[t["key"]]

    def same_everywhere(self, t, state, includes):
        wanted = self.state(t)
        self.assertEqual(wanted["state"], state)
        self.assertIn(includes, wanted["why"])
        self.assertEqual(api_ticket(self.P, None, t["key"])["plain_state"], wanted)
        cols = workbench.requirements(self.P, "STATE")["columns"]
        col, item = next((c, x) for c in cols for x in c["items"] if x.get("key") == t["key"])
        self.assertEqual((col["key"], item["why"], item["version"]), (state, wanted["why"], wanted["version"]))
        detail = workbench.client_view(self.P, self.client["id"])
        item = next(x for x in detail["requirements"] if x["key"] == t["key"])
        self.assertEqual({k: item[k] for k in wanted}, wanted)
        return wanted

    def test_claimed_work_is_owned_by_the_person_until_it_reaches_acceptance(self):
        t = self.ticket()
        handwork.claim(self.P, t, "李工")
        self.same_everywhere(t, "doing", "李工 在写")
        self.update(t, status="verify")
        self.same_everywhere(t, "you", "验收")

    def test_takeover_shows_the_running_step_then_the_pause(self):
        t = self.ticket()
        self.update(t, status="doing")
        r = self.record_run(t)
        self.P.flow.take_over(self.P.store.ticket(t["id"]), True, "李工")
        self.same_everywhere(t, "doing", "当前步骤结束后暂停")
        self.P.store.update_run(r["id"], status="done")
        self.same_everywhere(t, "you", "李工 已接管，自动处理暂停")

    def test_unconfirmed_criteria_and_a_change_to_the_contract_have_different_owners(self):
        t = self.ticket(open_ac=2)
        self.same_everywhere(t, "client", "2 条验收标准")
        links = dict(t["links"], client_change={"reason": "客户改了已确认的余额口径"})
        self.update(t, links=links)
        self.same_everywhere(t, "you", "等你决定")

    def test_failed_cancelled_queued_and_running_are_not_all_work_in_progress(self):
        t = self.ticket()
        self.update(t, status="doing")
        r = self.record_run(t, status="failed")
        self.same_everywhere(t, "you", "没跑成")
        self.P.store.update_run(r["id"], status="cancelled")
        self.same_everywhere(t, "you", "已取消")
        self.P.store.update_run(r["id"], status="queued")
        self.same_everywhere(t, "doing", "等待智能体")
        self.P.store.update_run(r["id"], status="running")
        self.same_everywhere(t, "doing", "AI 正在修改代码")
        self.P.store.update_run(r["id"], status="failed")
        self.record_run(t, mode="ask")  # an unrelated assistant answer must not hide the failed coding run
        self.same_everywhere(t, "you", "没跑成")

    def test_manual_submission_shows_its_check_and_failure_instead_of_still_saying_writing(self):
        t = self.ticket()
        handwork.claim(self.P, t, "李工")
        run = self.record_run(t, status="done", agent="人工")
        with mock.patch.object(handwork, "busy", side_effect=lambda key: key == t["key"]):
            self.same_everywhere(t, "doing", "构建和审查李工的提交")
        self.P.store.event(t["id"], "我来写", "flow", "构建测试没通过", {"run": run["id"], "verdict": "fail"})
        self.same_everywhere(t, "you", "检查没通过")
        self.P.store.event(t["id"], "我来写", "flow", "构建环境未就绪", {"run": run["id"], "verdict": "unknown"})
        self.same_everywhere(t, "you", "还没检查完")

    def test_a_reminder_cannot_hide_a_failed_check_or_carry_it_to_the_next_submission(self):
        t = self.ticket()
        handwork.claim(self.P, t, "李工")
        run = self.record_run(t, status="done", agent="人工")
        self.P.store.event(t["id"], "我来写", "flow", "构建测试没通过", {"run": run["id"], "verdict": "fail"})
        self.P.store.x("UPDATE events SET ts='2000-01-01 00:00:00' WHERE ticket_id=?", (t["id"],))
        self.assertEqual(handwork.remind(self.P, self.project, days=1), [t["key"]])
        self.same_everywhere(t, "you", "检查没通过")
        newer = self.record_run(t, status="done", agent="人工")
        self.P.store.event(t["id"], "我来写", "flow", "收到新提交，开始构建和审查", {"run": newer["id"]})
        with mock.patch.object(handwork, "busy", side_effect=lambda key: key == t["key"]):
            self.same_everywhere(t, "doing", "正在构建和审查")
        self.P.store.event(t["id"], "我来写", "flow", "新提交检查通过", {"run": newer["id"], "verdict": "pass"})
        self.same_everywhere(t, "doing", "李工 在写")
        self.P.store.event(t["id"], "我来写", "flow", "上一份提交迟到的失败结果", {"run": run["id"], "verdict": "fail"})
        self.same_everywhere(t, "doing", "李工 在写")

    def test_analysis_done_with_automatic_planning_disabled_waits_for_a_person(self):
        (self.data / "autoflow.json").write_text('{"on": true, "plan": false}', encoding="utf-8")
        t = self.update(self.ticket(), status="doing")
        run = self.record_run(t, status="done", mode="analyze")
        self.P.store.update_run(run["id"], result="LeaveService.java:12 提交时没有更新状态")
        with mock.patch.object(self.P.flow, "agent", return_value="test-agent"):
            self.assertEqual(self.P.flow.next_step(t)[0], "")
            self.same_everywhere(t, "you", "分析已完成，等你确认下一步")
            (self.data / "autoflow.json").write_text('{"on": true, "plan": true}', encoding="utf-8")
            self.assertEqual(self.P.flow.next_step(t)[0], "plan")
            self.same_everywhere(t, "doing", "等待自动处理继续")

    def test_signing_link_and_expiry_are_shared_with_the_ticket_header(self):
        t = self.ticket()
        t = self.update(t, status="verify")
        signoff.issue(self.P, t, "tester", "王总", note="由测试人员复核缺少的证据后签收")
        self.same_everywhere(t, "client", "等王总签收")
        with mock.patch("tmh.platform.server.now", return_value="2099-01-01 00:00:00"):
            self.same_everywhere(t, "you", "过期")

    def test_a_ticket_waiting_for_a_worker_is_not_reported_as_being_written(self):
        t = self.ticket()
        self.same_everywhere(t, "you", "自动处理关着")
        t = self.update(t, status="doing")
        self.same_everywhere(t, "you", "自动处理已关闭")

    def test_closed_ticket_and_a_released_version_stay_distinct_and_reads_do_not_write(self):
        t = self.update(self.ticket(), status="closed")
        self.same_everywhere(t, "done", "已关闭")
        self.P.store.event(t["id"], "自动流转", "release", "已出版本", {"version": "2026.10.18-1"})
        before = (self.P.store.ticket(t["id"]), self.P.store.events(t["id"]))
        self.same_everywhere(t, "shipped", "2026.10.18-1")
        self.assertEqual((self.P.store.ticket(t["id"]), self.P.store.events(t["id"])), before)


if __name__ == "__main__":
    unittest.main()
