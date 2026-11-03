import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tmh.platform import browser_verify as bv

ACS = [{"id": "A1", "text": "a"}, {"id": "A2", "text": "b"}, {"id": "A3", "text": "c"}, {"id": "A4", "text": "d"}]
PNG = b"\x89PNG..."


def spec(title, status, shots=(), msg=""):
    res = {"status": status, "attachments": [{"name": s, "path": "/x/out/shots/" + s, "contentType": "image/png"} for s in shots]}
    if msg:
        res["error"] = {"message": msg}
    return {"title": title, "tests": [{"results": [res]}]}


class BrowserVerifyTest(unittest.TestCase):
    def test_only_a_failed_assertion_is_a_reproduced_defect_and_only_all_pass_with_screenshots_proves(self):
        report = {"suites": [{"specs": [spec("A1 ok", "passed", ["A1-a.png"]), spec("A2 nopic", "passed")],
                              "suites": [{"specs": [spec("A3 bad", "failed", ["A3-a.png"], "expect(locator).toHaveText(expected)")]}]}]}
        items = {i["id"]: i for i in bv.results(report, ACS, {"A1-a.png": PNG, "A3-a.png": PNG})}
        self.assertEqual([items[k]["result"] for k in ("A1", "A2", "A3", "A4")], ["pass", "unverified", "fail", "unverified"])
        self.assertEqual(items["A1"]["shots"], {"A1-a.png": PNG})
        self.assertEqual(bv.overall(list(items.values())), "fail")
        self.assertEqual(bv.overall([items["A1"], items["A2"]]), "unverified")
        self.assertEqual(bv.overall([items["A1"]]), "pass")
        self.assertEqual(bv.overall([]), "unverified")

    def test_timeouts_setup_errors_and_skips_are_unverified_not_failures(self):
        report = {"suites": [{"specs": [
            spec("A1 t", "timedOut", msg="Test timeout of 240000ms exceeded."),
            spec("A2 l", "failed", ["A2-a.png"], "locator.click: Timeout 30000ms exceeded."),
            spec("A3 s", "failed", msg="TMH_SETUP captcha not found\n expect(x)"),
            spec("A4 k", "skipped")]}]}
        self.assertEqual({i["result"] for i in bv.results(report, ACS, {"A2-a.png": PNG})}, {"unverified"})
        self.assertEqual({i["result"] for i in bv.results({"setup": "app did not start"}, ACS, {})}, {"unverified"})

    def test_short_commit_ids_resolve_to_the_full_id_only_when_they_name_it(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            git = ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t"]
            subprocess.run(git + ["init", "-q"], check=True)
            subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "x"], check=True)
            full = subprocess.run(git + ["rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(bv.full_sha(Path(d), full[:8]), full)
            self.assertEqual(bv.full_sha(Path(d), full), full)
            for bad in ("", "HEAD", full[:4], "0" * 8, "main"):
                self.assertEqual(bv.full_sha(Path(d), bad), "")

    def test_spec_and_config(self):
        self.assertEqual(bv.spec_from("x\n```tmh-spec\nimport a\n```\n"), "import a\n")
        self.assertEqual(bv.spec_from("no block"), "")
        out = bv.spec_from("```tmh-spec\nimport { test, expect } from '@playwright/test';\nimport { login } from './tmh-helpers.mjs';\n```")
        self.assertEqual(out, "import { test, expect } from './tmh-helpers.mjs';\nimport { login } from './tmh-helpers.mjs';\n")
        d = Path(tempfile.mkdtemp())
        self.assertIsNone(bv.conf(d, "JB"))
        (d / bv.CONF).write_text(json.dumps({"projects": {"JB": {"ssh": "u@h", "app": "web"}, "X": {"ssh": "u@h"}}}), encoding="utf-8")
        self.assertEqual(bv.conf(d, "JB")["app"], "web")
        self.assertIsNone(bv.conf(d, "X"))
        b1, b2 = bv.binding("a" * 40, "d", "s"), bv.binding("a" * 40, "d2", "s")
        self.assertNotEqual(b1["diff_sha256"], b2["diff_sha256"])


if __name__ == "__main__":
    unittest.main()


class DriverBundleTest(unittest.TestCase):
    def test_the_host_fetches_the_candidate_under_the_ref_the_bundle_carries(self):
        import subprocess
        root = Path(tempfile.mkdtemp(prefix="tmh-bundle-"))
        g = lambda repo, *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["git", "init", "-q", str(root / "src")], check=True)
        g(root / "src", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "a")
        have = g(root / "src", "rev-parse", "HEAD")
        subprocess.run(["git", "clone", "-q", str(root / "src"), str(root / "host")], check=True)
        g(root / "src", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "candidate")
        cand = g(root / "src", "rev-parse", "HEAD")
        g(root / "src", "update-ref", "refs/tmh-verify/j1", cand)
        (root / "in.bundle").write_bytes(subprocess.run(["git", "-C", str(root / "src"), "bundle", "create", "-", "refs/tmh-verify/j1", "^" + have],
                                                        capture_output=True, check=True).stdout)
        line = next(x for x in bv.DRIVER.splitlines() if "fetch -q" in x)
        cmd = line.split("||")[0].strip().replace("$REPO", str(root / "host")).replace("$D", str(root)).replace("$J", "j1")
        subprocess.run(cmd, shell=True, check=True, executable="/bin/bash")
        self.assertEqual(g(root / "host", "rev-parse", "refs/tmh/j1"), cand)


class RepairTest(unittest.TestCase):
    STRICT = "Error: expect(locator).toBeVisible() failed\nstrict mode violation: locator('input') resolved to 2 elements"

    def run_verify(self, first, second, fixed="```tmh-spec\nB\n```"):
        from types import SimpleNamespace
        from unittest import mock
        P = SimpleNamespace(data_dir=Path("."), store=SimpleNamespace(run=lambda rid: {"diff": "d"}))
        asked, ran, rec = [], [], []
        replies = iter(["```tmh-spec\nA\n```", fixed])

        def ask(P, p, t, prompt):
            asked.append(prompt)
            return next(replies)

        def remote(c, root, base, diff, spec, job, port):
            ran.append((spec, job))
            return (first if len(ran) == 1 else second), {"A1-x.png": PNG, "A2-x.png": PNG}
        with mock.patch.object(bv, "conf", return_value={"ssh": "h", "app": "a"}), \
                mock.patch.object(bv, "full_sha", return_value="a" * 40), \
                mock.patch.object(bv, "run_remote", side_effect=remote), \
                mock.patch.object(bv, "_record", side_effect=lambda *a: rec.append(a)):
            out = bv.verify(P, {"key": "JB", "root": "."}, {"title": "t"}, 3, ACS[:2], commit="abc", ask=ask)
        return out, asked, ran

    def test_strict_mode_is_a_script_fault_not_a_reproduced_defect(self):
        items = bv.results({"suites": [{"specs": [spec("A1 x", "failed", msg=self.STRICT)]}]}, ACS[:1], {})
        self.assertEqual(items[0]["result"], "unverified")
        self.assertTrue(bv.repairable(items))

    def test_a_missing_prerequisite_anchor_is_a_script_fault_but_a_criterion_assertion_is_a_defect(self):
        anchor = "Error: TMH_ANCHOR 登录按钮: expect(locator).toBeVisible() failed\nLocator: locator('button')"
        items = bv.results({"suites": [{"specs": [spec("A1 x", "failed", msg=anchor),
                                                  spec("A2 y", "failed", msg="expect(locator).toHaveCount(expected)")]}]}, ACS[:2],
                           {"A2-01-页面.png": b"png"})
        self.assertEqual([i["result"] for i in items], ["unverified", "fail"])
        self.assertTrue(bv.repairable(items[:1]))
        blind = bv.results({"suites": [{"specs": [spec("A2 y", "failed", msg="expect(locator).toBeVisible() failed")]}]}, ACS[1:2], {})
        self.assertEqual(blind[0]["result"], "unverified")
        self.assertTrue(bv.repairable(blind))
        self.assertIn("export async function anchor", bv.HELPERS)
        self.assertIn("anchor(", bv.SPEC_RULES)

    def test_the_page_a_failed_test_saw_reaches_the_reviewer_and_a_review_cannot_drop_what_is_checked(self):
        files = {"A1-01-页面.png": PNG, "A1-page.txt": "- checkbox \"记住账号\"".encode()}
        items = bv.results({"suites": [{"specs": [spec("A1 x", "failed", msg="expect(locator).toBeVisible() failed")]}]}, ACS[:1], files)
        self.assertEqual((items[0]["result"], list(items[0]["shots"])), ("fail", ["A1-01-页面.png"]))
        self.assertIn('checkbox "记住账号"', bv.repair_prompt("A", items))
        acs = [{"id": "A1", "text": "复选框旁显示「记住账号」，不再显示“记住我”"}]
        draft = "expect(page.locator('label', {hasText: '记住账号'})).toBeVisible(); expect(page.getByText('记住我')).toHaveCount(0)"
        self.assertTrue(bv.keeps(draft, "expect(page.getByText('记住账号', {exact: true})).toBeVisible(); getByText('记住我')", acs))
        self.assertFalse(bv.keeps(draft, "expect(page.getByText('记住我')).toHaveCount(0)", acs))
        self.assertIn("ariaSnapshot", bv.HELPERS)

    def test_a_broken_script_gets_one_corrected_run_bound_to_the_new_script(self):
        broken = {"suites": [{"specs": [spec("A1 x", "failed", msg=self.STRICT), spec("A2 y", "passed", ["A2-x.png"])]}]}
        good = {"suites": [{"specs": [spec("A1 x", "passed", ["A1-x.png"]), spec("A2 y", "passed", ["A2-x.png"])]}]}
        out, asked, ran = self.run_verify(broken, good)
        self.assertEqual(out["result"], "pass")
        self.assertEqual([s for s, _ in ran], ["A\n", "B\n"])
        self.assertNotEqual(ran[0][1], ran[1][1])
        self.assertEqual(out["spec_sha256"], bv.binding("", "", "B\n")["spec_sha256"])
        self.assertEqual(out["repaired_from"], bv.binding("", "", "A\n")["spec_sha256"])
        self.assertIn("不许删掉、跳过或放松断言", asked[1])
        self.assertIn("strict mode violation", asked[1])

    def test_a_failure_gets_one_review_and_stands_when_the_reviewer_keeps_the_script_or_setup_broke(self):
        failed = {"suites": [{"specs": [spec("A1 x", "failed", msg="expect(locator).toHaveText(expected)"),
                                        spec("A2 y", "failed", msg=self.STRICT)]}]}
        out, asked, ran = self.run_verify(failed, None, fixed="```tmh-spec\nA\n```")
        self.assertEqual((out["result"], len(asked), len(ran)), ("fail", 2, 1))
        out, asked, ran = self.run_verify({"setup": "vite did not start"}, None)
        self.assertEqual((out["result"], len(asked), len(ran)), ("unverified", 1, 1))
        broken = {"suites": [{"specs": [spec("A1 x", "failed", msg=self.STRICT), spec("A2 y", "passed", ["A2-x.png"])]}]}
        out, asked, ran = self.run_verify(broken, broken)
        self.assertEqual((out["result"], len(asked), len(ran)), ("unverified", 2, 2))


class StartCommandTest(unittest.TestCase):
    """A project that is not the JeecgBoot front end says how it starts; the host runs that from its own checkout."""

    def test_the_host_gets_the_project_checkout_and_start_command(self):
        sent = []

        def fake(c, remote, data=None, timeout=120):
            sent.append(remote)
            return 1, b""
        c = {"ssh": "u@h", "app": ".", "repo": "pv/PETS/base", "start": "mvn spring-boot:run"}
        with mock.patch.object(bv, "_ssh", side_effect=fake):
            report, _ = bv.run_remote(c, Path("."), "a" * 40, "", "spec", "j1", 23001)
        self.assertEqual(report, {"setup": "verification host unreachable"})
        self.assertIn("git -C pv/PETS/base rev-parse HEAD", sent[0])
        self.assertIn("git -C pv/PETS/base init -q", sent[1])
        self.assertIn('[ -n "$START" ]', bv.DRIVER)
        self.assertIn("REPO=${8:-pv/base}; START=${9:-}", bv.DRIVER)

    def test_login_opens_the_home_page_when_there_is_no_jeecg_config(self):
        self.assertIn("if (!process.env.TMH_JB_YML) { await page.goto(base); await ready(page); return; }", bv.HELPERS)


class PageCheckTest(unittest.TestCase):
    def _p(self, run, hosts=None):
        d = Path(tempfile.mkdtemp())
        if hosts:
            (d / bv.CONF).write_text(json.dumps({"projects": hosts}), encoding="utf-8")
        store = mock.Mock()
        store.run.return_value = run
        store.project.return_value = {"key": "PETS", "root": "."}
        store.ticket.return_value = {"id": 1, "key": "PETS-2"}
        return mock.Mock(data_dir=d, store=store)

    def test_a_project_without_a_host_shows_no_page_check(self):
        P = self._p({"project_id": 1, "mode": "fix"})
        self.assertEqual(bv.page_state(P, 7)["available"], False)

    def test_only_a_finished_change_is_checked(self):
        P = self._p({"project_id": 1, "ticket_id": 1, "mode": "fix", "status": "failed", "diff": "x"},
                    {"PETS": {"ssh": "u@h", "app": "."}})
        with self.assertRaises(ValueError):
            bv.page_check(P, 7, "li")
        self.assertTrue(bv.page_state(P, 7)["available"])

    def test_the_result_is_recorded_on_the_run(self):
        P = self._p({"project_id": 1, "ticket_id": 1, "mode": "fix", "status": "done", "diff": "x"},
                    {"PETS": {"ssh": "u@h", "app": "."}})
        res = {"result": "pass", "ac": [{"id": "A1", "result": "pass", "how": "看到了", "shots": {"a.png": b"x"}}]}
        with mock.patch.object(bv, "page_criteria", return_value=[{"id": "A1", "text": "t"}]), \
                mock.patch.object(bv, "verify", return_value=res) as v, \
                mock.patch.object(bv.threading, "Thread") as th:
            bv.page_check(P, 7, "li")
            th.call_args.kwargs["target"]()
        self.assertEqual(v.call_args.kwargs["by"], bv.PAGE_BY)
        s = bv.page_state(P, 7)
        self.assertEqual((s["status"], s["result"], s["ac"]), ("done", "pass", [{"id": "A1", "result": "pass", "how": "看到了"}]))
        self.assertFalse(s["running"])

    def test_the_client_criteria_come_before_the_plan(self):
        P = self._p({})
        client = [{"id": "A1", "text": "主人详情页不再有 Add New Pet 按钮"}, {"id": "A2", "text": "测试通过", "keep": True}]
        with mock.patch("tmh.platform.signoff.state", return_value={"snapshot": {}}), \
                mock.patch("tmh.platform.signoff.client_ac", return_value=client):
            self.assertEqual(bv.page_criteria(P, {"id": 1, "key": "PETS-2"}), client[:1])
        P.store.runs.assert_not_called()


class AskAgentTest(unittest.TestCase):
    def test_without_a_diagnose_step_the_script_is_written_by_the_route_agent(self):
        d = Path(tempfile.mkdtemp())
        (d / "agent-routes.json").write_text(json.dumps({"schema": 1, "default": {"agent": "cloudwave-codex", "allowed_agents": ["cloudwave-codex"]}}), encoding="utf-8")
        P = mock.Mock(data_dir=d)
        P.flow.autoflow.return_value = {"agent": "codex"}
        P.runner.start.return_value = {"id": 9}
        P.store.run.return_value = {"status": "done", "result": "spec"}
        with mock.patch("tmh.platform.agents.available", return_value=[{"name": "cloudwave-codex", "available": True}]):
            self.assertEqual(bv._ask(P, {"key": "PETS"}, {"key": "PETS-2"}, "q"), "spec")
        self.assertEqual(P.runner.start.call_args.args[2], "cloudwave-codex")


class DriverStartTest(unittest.TestCase):
    def test_a_host_checkout_without_head_gets_the_base_and_a_dead_app_ends_the_wait(self):
        self.assertIn("rev-parse -q --verify HEAD >/dev/null || git -C $REPO update-ref --no-deref HEAD $BASE", bv.DRIVER)
        self.assertIn('kill -0 $VP 2>/dev/null || { say "app exited before it was ready"; finish; }', bv.DRIVER)

    def test_a_screenshot_without_test_info_still_lands(self):
        self.assertIn("if (typeof testInfo === 'string' || !testInfo) { name = testInfo; testInfo = base.info(); }", bv.HELPERS)



class ReviewTest(unittest.TestCase):
    NOT_FOUND = ("Error: Timed out 5000ms waiting for expect(locator).toBeVisible()\n\n"
                 "Locator: locator('#owners').getByRole('columnheader', { name: 'Pet Count' })\n"
                 "Expected: visible\nReceived: <element(s) not found>")

    def test_a_locator_that_found_nothing_the_page_shows_is_the_scripts_fault(self):
        seen = {"A1-01.png": PNG, "A1-page.txt": b'- text "Pets"\n- text "Pet Count"\n'}
        items = bv.results({"suites": [{"specs": [spec("A1 x", "failed", msg=self.NOT_FOUND)]}]}, ACS[:1], seen)
        self.assertEqual(items[0]["result"], "unverified")
        self.assertIn("「Pet Count」", items[0]["how"])
        self.assertTrue(bv.repairable(items))
        absent = {"A1-01.png": PNG, "A1-page.txt": b'- text "Pets"\n'}
        items = bv.results({"suites": [{"specs": [spec("A1 x", "failed", msg=self.NOT_FOUND)]}]}, ACS[:1], absent)
        self.assertEqual(items[0]["result"], "fail")

    def test_the_reviewer_sees_the_change_and_always_returns_a_script(self):
        prompt = bv.repair_prompt("S", [{"id": "A1", "result": "fail", "how": "x"}], "+<th>Pet Count</th>")
        self.assertIn("+<th>Pet Count</th>", prompt)
        self.assertIn("仓库目录里还没有这份改动", prompt)
        self.assertIn("不管改没改，都输出完整脚本", prompt)
        self.assertNotIn("仓库目录里还没有这份改动", bv.repair_prompt("S", [], ""))


class NoSpecTest(unittest.TestCase):
    def test_a_reply_without_a_script_is_asked_once_more(self):
        from types import SimpleNamespace
        from unittest import mock
        P = SimpleNamespace(data_dir=Path("."), store=SimpleNamespace(run=lambda rid: {"diff": "d"}))
        replies, asked = iter(["读不到代码，没法写", "读不到代码，没法写"]), []

        def ask(P, p, t, prompt):
            asked.append(prompt)
            return next(replies)
        with mock.patch.object(bv, "conf", return_value={"ssh": "h", "app": "a"}), \
                mock.patch.object(bv, "full_sha", return_value="a" * 40), \
                mock.patch.object(bv, "run_remote") as remote, \
                mock.patch.object(bv, "_record"):
            out = bv.verify(P, {"key": "PETS", "root": "."}, {"title": "t"}, 3, ACS[:1], commit="abc", ask=ask)
        self.assertEqual(len(asked), 2)
        self.assertIn("上一次没有交回脚本", asked[1])
        self.assertEqual(out["why"], "没有写出实测脚本")
        remote.assert_not_called()

    def test_flows_answer_in_a_read_only_checkout(self):
        from unittest import mock
        from tmh import cli
        with mock.patch("tmh.flow.build_flows", return_value={"flows": []}), \
                mock.patch.object(Path, "write_text", side_effect=OSError(30, "Read-only file system")):
            self.assertEqual(cli._load_flows(Path(".")), {"flows": []})
