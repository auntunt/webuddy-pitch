import json
import tempfile
import unittest
from pathlib import Path

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
        cmd = line.split("||")[0].strip().replace("~/pv/base", str(root / "host")).replace("$D", str(root)).replace("$J", "j1")
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
                                                  spec("A2 y", "failed", msg="expect(locator).toHaveCount(expected)")]}]}, ACS[:2], {})
        self.assertEqual([i["result"] for i in items], ["unverified", "fail"])
        self.assertTrue(bv.repairable(items[:1]))
        self.assertFalse(bv.repairable(items))
        self.assertIn("export async function anchor", bv.HELPERS)
        self.assertIn("anchor(", bv.SPEC_RULES)

    def test_a_broken_script_gets_one_corrected_run_bound_to_the_new_script(self):
        broken = {"suites": [{"specs": [spec("A1 x", "failed", msg=self.STRICT), spec("A2 y", "passed", ["A2-x.png"])]}]}
        good = {"suites": [{"specs": [spec("A1 x", "passed", ["A1-x.png"]), spec("A2 y", "passed", ["A2-x.png"])]}]}
        out, asked, ran = self.run_verify(broken, good)
        self.assertEqual(out["result"], "pass")
        self.assertEqual([s for s, _ in ran], ["A\n", "B\n"])
        self.assertNotEqual(ran[0][1], ran[1][1])
        self.assertEqual(out["spec_sha256"], bv.binding("", "", "B\n")["spec_sha256"])
        self.assertEqual(out["repaired_from"], bv.binding("", "", "A\n")["spec_sha256"])
        self.assertIn("不许删掉或放松断言", asked[1])
        self.assertIn("strict mode violation", asked[1])

    def test_a_reproduced_failure_or_setup_error_is_never_rewritten_and_only_one_repair_happens(self):
        failed = {"suites": [{"specs": [spec("A1 x", "failed", msg="expect(locator).toHaveText(expected)"),
                                        spec("A2 y", "failed", msg=self.STRICT)]}]}
        out, asked, ran = self.run_verify(failed, None)
        self.assertEqual((out["result"], len(asked), len(ran)), ("fail", 1, 1))
        out, asked, ran = self.run_verify({"setup": "vite did not start"}, None)
        self.assertEqual((out["result"], len(asked), len(ran)), ("unverified", 1, 1))
        broken = {"suites": [{"specs": [spec("A1 x", "failed", msg=self.STRICT), spec("A2 y", "passed", ["A2-x.png"])]}]}
        out, asked, ran = self.run_verify(broken, broken)
        self.assertEqual((out["result"], len(asked), len(ran)), ("unverified", 2, 2))
