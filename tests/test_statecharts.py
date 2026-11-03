"""业务状态图: chart files are read back as drawn, checked, and flagged when cited code changed."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tmh.platform import statecharts

CHART = {
    "title": "主人与宠物", "domain": "dom:owner",
    "mermaid": 'stateDiagram-v2\n  state "主人详情" as detail\n  state "添加宠物" as addpet\n  state "宠物又多了一只" as more\n'
               '  [*] --> detail\n  detail --> addpet: 直接打开网址\n  addpet --> more: 保存',
    "rules": [{"text": "主人详情页上不能再添加宠物", "where": "Owner.java:3", "holds": True}, {"text": "电话 10 位", "where": "Owner.java:1"}],
    "paths": [{"rule": 0, "steps": [{"state": "detail"}, {"state": "addpet", "note": "GET 还在"}, {"state": "more"}]}],
}


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          check=True, capture_output=True, text=True).stdout.strip()


class StatechartTests(unittest.TestCase):
    def test_path_marks_rule_broken_and_maps_pele_edges(self):
        c = statecharts.check("owner", CHART)
        self.assertEqual(c["problems"], [])
        self.assertEqual(c["status"], "待确认", "an agent cannot mark its own chart confirmed")
        self.assertFalse(c["rules"][0]["holds"])
        self.assertTrue(c["rules"][1]["holds"])
        self.assertEqual(c["paths"][0]["edges"], ["edge1", "edge2"], "Pele numbers edges by transition order, [*] included")

    def test_bad_files_are_reported_not_hidden(self):
        bad = dict(CHART, mermaid="flowchart LR\n a --> b", paths=[{"rule": 5, "steps": []}, {"rule": 0, "steps": [{"state": "ghost"}]}])
        c = statecharts.check("x", bad)
        self.assertTrue(any("stateDiagram" in p for p in c["problems"]))
        self.assertTrue(any("规则" in p for p in c["problems"]))
        self.assertTrue(any("ghost" in p for p in c["problems"]))
        self.assertEqual(c["paths"], [])
        self.assertEqual(statecharts.check("x", [])["problems"], ["文件不是 JSON 对象"])

    def test_load_flags_charts_whose_cited_code_changed(self):
        root = Path(tempfile.mkdtemp(prefix="tmh-stc-"))
        git(root, "init", "-q")
        (root / "Owner.java").write_text("a\nb\nc\n", encoding="utf-8")
        (root / "Other.java").write_text("x\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "base")
        d = root / statecharts.DIR
        d.mkdir(parents=True)
        (d / "owner.json").write_text(json.dumps(dict(CHART, commit=git(root, "rev-parse", "HEAD")), ensure_ascii=False), encoding="utf-8")
        (d / "broken.json").write_text("{nope", encoding="utf-8")
        (d / "bad id!.json").write_text("{}", encoding="utf-8")
        charts = {c["id"]: c for c in statecharts.load(root)}
        self.assertEqual(sorted(charts), ["broken", "owner"])
        self.assertEqual(charts["owner"]["changed"], [])
        self.assertTrue(charts["broken"]["problems"])
        (root / "Other.java").write_text("y\n", encoding="utf-8")
        git(root, "commit", "-qam", "unrelated")
        self.assertEqual({c["id"]: c for c in statecharts.load(root)}["owner"]["changed"], [])
        (root / "Owner.java").write_text("a\nb\nC\n", encoding="utf-8")
        git(root, "commit", "-qam", "cited file")
        self.assertEqual({c["id"]: c for c in statecharts.load(root)}["owner"]["changed"], ["Owner.java"])

    def test_chart_mode_is_a_writing_run_with_the_format(self):
        from tmh.platform import agents
        from tmh.platform.store import RUN_MODES
        self.assertIn("chart", dict(RUN_MODES))
        self.assertIn(".tmh/knowledge/statecharts/", agents.MODE_TEXT["chart"])
        self.assertIn('"paths"', agents.MODE_TEXT["chart"])

    def test_page_has_the_states_route_and_lazy_renderer(self):
        from tmh.platform.ui import page
        html = page()
        self.assertIn("['states','业务状态图']", html)
        self.assertIn("states:()=>vStates(", html)
        self.assertIn("appPath('/ui/pele.js')", html)
        self.assertNotIn("var pele=", html, "the renderer is fetched by the page that needs it, not inlined")
        vendor = Path(statecharts.__file__).parent / "vendor"
        self.assertTrue((vendor / "pele.global.js").read_text(encoding="utf-8").startswith("/*! Pele"))
        self.assertIn("MIT", (vendor / "pele-LICENSE").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
