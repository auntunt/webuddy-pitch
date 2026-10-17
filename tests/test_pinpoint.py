import subprocess
import tempfile
import unittest
from pathlib import Path

from tmh.platform import pinpoint

LABELS = """<?xml version="1.0" encoding="UTF-8"?>
<resource>
    <property key="CommonRequest">
        <value xml:lang="de">Anfrage</value>
        <value xml:lang="en">Request</value>
        <value xml:lang="zh">请求</value>
    </property>
    <property key="HumanResTrainingDate">
        <value xml:lang="en">Training Date</value>
        <value xml:lang="zh">培训日期</value>
    </property>
</resource>
"""
FORMS = """<forms>
    <form name="EditEmployeeTraining" type="single" target="updateEmployeeTraining">
        <field name="trainingDate" title="${uiLabelMap.HumanResTrainingDate}"><date-time/></field>
        <field name="submitButton" title="${uiLabelMap.CommonRequest}"><submit/></field>
    </form>
</forms>
"""
OTHER = """<forms>
    <form name="ListPartyRequests">
        <field name="requestId" title="${uiLabelMap.CommonRequest}"><display/></field>
    </form>
</forms>
"""
VUE = "<template>\n  <div class=\"leave\">\n    <el-button>导出</el-button>\n  </div>\n</template>\n"


def repo() -> Path:
    d = Path(tempfile.mkdtemp(prefix="tmh-pin-"))
    files = {"applications/humanres/config/HumanResUiLabels.xml": LABELS,
             "applications/humanres/widget/forms/EmployeeTrainingForms.xml": FORMS,
             "applications/party/widget/partymgr/PartyRequestForms.xml": OTHER,
             "web/src/views/Leave.vue": VUE}
    for p, t in files.items():
        (d / p).parent.mkdir(parents=True, exist_ok=True)
        (d / p).write_text(t, encoding="utf-8")
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(["git"] + cmd, cwd=d, check=True)
    return d


class FakeGraph:
    def nodes(self, kind):
        return [{"id": "ep:POST /leave/submit", "name": "POST /leave/submit", "file": "LeaveController.java", "line": 26}] if kind == "ep" else []

    def inn(self, nid, kind):
        return [{"src": "flow:leave", "dst": nid}] if kind == "entry" else []

    def out(self, nid, kind):
        return [{"src": nid, "dst": "tbl:OA_LEAVE"}] if kind == "uses" else []

    def node(self, nid):
        return {"flow:leave": {"name": "请假提交"}, "tbl:OA_LEAVE": {"name": "OA_LEAVE"}}.get(nid)


class PinpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = repo()

    def test_old_templates_found_through_the_label_file(self):
        """OFBiz shows "培训日期", not the key: the label file leads back to the form that uses the key."""
        cap = pinpoint.clean_capture({"url": "https://erp/humanres/control/EditEmployeeTraining?x=1",
                                      "texts": ["培训日期", "请求"], "elements": [{"tag": "input", "name": "trainingDate"}]})
        r = pinpoint.locate(self.root, cap)
        top = r["layer2"][0]
        self.assertEqual(top["file"], "applications/humanres/widget/forms/EmployeeTrainingForms.xml", r["layer2"])
        self.assertTrue(any("HumanResTrainingDate" in m["match"] for m in top["matches"]), top)
        self.assertGreater(top["line"], 0)
        # "请求" is used in two forms; the rarer "培训日期", the field name and the page address put the training form first
        other = [x for x in r["layer2"] if x["file"].endswith("PartyRequestForms.xml")]
        self.assertTrue(other and other[0]["score"] < top["score"])
        self.assertFalse(any(x["file"].endswith("UiLabels.xml") for x in r["layer2"]))  # a label file is the way, not the answer

    def test_markers_requests_and_nothing_found(self):
        cap = pinpoint.clean_capture({"url": "http://oa/leave", "texts": ["导出"],
                                      "elements": [{"tag": "button", "marker": "src/views/Leave.vue:3:5"}],
                                      "requests": ["http://oa/api/leave/submit?draft=0", "http://oa/static/x.js"]})
        r = pinpoint.locate(self.root, cap, FakeGraph())
        self.assertEqual((r["layer1"][0]["file"], r["layer1"][0]["line"], r["layer1"][0]["exists"]), ("web/src/views/Leave.vue", 3, True))
        self.assertEqual(r["layer3"][0]["flows"], ["请假提交"])
        self.assertEqual(r["layer3"][0]["tables"], ["OA_LEAVE"])
        r = pinpoint.locate(self.root, pinpoint.clean_capture({"texts": ["完全不存在的文字"]}))
        self.assertFalse(r["layer1"] or r["layer2"] or r["layer3"])
        self.assertIn("转人工", r["basis"][-1])

    def test_bookmarklet_and_tokens(self):
        d = Path(tempfile.mkdtemp())
        t1 = pinpoint.issue_token(d, "OA", "李")
        self.assertEqual(pinpoint.token_project(d, t1), "OA")
        self.assertNotIn(t1, (d / "pins" / "tokens.json").read_text(encoding="utf-8"))  # kept hashed
        t2 = pinpoint.issue_token(d, "OA", "李")
        self.assertEqual((pinpoint.token_project(d, t1), pinpoint.token_project(d, t2)), ("", "OA"))  # a new one switches the old off
        js = pinpoint.bookmarklet("https://webuddy.example/", t2)
        self.assertTrue(js.startswith("javascript:(function(){"))
        self.assertIn("https://webuddy.example/capture/" + t2, js)
        self.assertNotIn("\n", js)


if __name__ == "__main__":
    unittest.main()
