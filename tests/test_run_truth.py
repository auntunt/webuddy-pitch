"""The ticket page and run records say what really happened: which engine ran, whether a change exists."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh.platform.agents import configured_model
from tmh.platform.ui import JS


def _fn(name):
    return f"function {name}(" + JS.split(f"function {name}(", 1)[1].split("\nfunction ", 1)[0]


@unittest.skipUnless(shutil.which("node"), "Node.js is needed for UI behavior checks")
class RunTruthUiTest(unittest.TestCase):
    def check(self, checks):
        src = "const assert=require('node:assert/strict');\n" + _fn("runStatus") + "\n" + _fn("secOf") + "\n" + checks
        r = subprocess.run([shutil.which("node"), "-"], input=src, encoding="utf-8", errors="replace", capture_output=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_finished_change_run_says_when_nothing_changed_or_the_check_failed(self):
        self.check(r"""
const fx=(o)=>({mode:'fix',status:'done',...o});
assert.equal(runStatus(fx({diff_bytes:0})),'完成 · 没有改动');
assert.equal(runStatus(fx({diff:''})),'完成 · 没有改动');
assert.equal(runStatus(fx({diff_bytes:9,verify:{check:'skip',verdict:'fail'}})),'完成 · 验证没通过');
assert.equal(runStatus(fx({diff_bytes:9,verify:{check:'skip',verdict:'unknown'}})),'完成 · 未验证');
assert.equal(runStatus(fx({diff_bytes:9,verify:{check:'skip',verdict:'pass'}})),'完成');
assert.equal(runStatus({mode:'analyze',status:'done'}),'完成');
assert.equal(runStatus({mode:'fix',status:'failed'}),'失败');
""")

    def test_root_cause_skips_the_prompt_hint_in_the_heading(self):
        self.check(r"""
assert.equal(secOf('## 结论（3 句以内）\n取消时没有清空 tempSave。\n\n## 代码位置\nx',['结论']),'取消时没有清空 tempSave。');
assert.equal(secOf('**结论**：快照没复原',['结论']),'快照没复原');
""")

    def test_shipped_js_parses(self):
        r = subprocess.run([shutil.which("node"), "--check", "-"], input=JS, encoding="utf-8", capture_output=True, check=False)
        self.assertEqual(r.returncode, 0, r.stderr)


class ConfiguredModelTest(unittest.TestCase):
    def test_an_official_profile_records_the_model_it_runs(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"CODEX_HOME": d}):
            Path(d, "config.toml").write_text('model = "gpt-base"\n', encoding="utf-8")
            c = {"engine": "codex", "profile": "wb"}
            self.assertEqual(configured_model(c), "gpt-base")
            Path(d, "wb.config.toml").write_text('model = "gpt-6-luna"\n', encoding="utf-8")
            self.assertEqual(configured_model(c), "gpt-6-luna")
            self.assertEqual(configured_model({"engine": "codex"}), "")
            self.assertEqual(configured_model({"engine": "codex", "profile": "wb", "cmd": ["x"]}), "")
            Path(d, "wb.config.toml").write_text("model = [", encoding="utf-8")
            self.assertEqual(configured_model(c), "")


if __name__ == "__main__":
    unittest.main()
