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
        d = Path(tempfile.mkdtemp())
        self.assertIsNone(bv.conf(d, "JB"))
        (d / bv.CONF).write_text(json.dumps({"projects": {"JB": {"ssh": "u@h", "app": "web"}, "X": {"ssh": "u@h"}}}), encoding="utf-8")
        self.assertEqual(bv.conf(d, "JB")["app"], "web")
        self.assertIsNone(bv.conf(d, "X"))
        b1, b2 = bv.binding("a" * 40, "d", "s"), bv.binding("a" * 40, "d2", "s")
        self.assertNotEqual(b1["diff_sha256"], b2["diff_sha256"])


if __name__ == "__main__":
    unittest.main()
