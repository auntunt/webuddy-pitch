import unittest

from tmh.platform import gates as G


def diff(path, removed=(), added=(), deleted=False, new=False):
    head = ["diff --git a/%s b/%s" % (path, path)]
    if deleted:
        head.append("deleted file mode 100644")
    if new:
        head.append("new file mode 100644")
    head += ["--- a/%s" % path, "+++ b/%s" % path, "@@ -1 +1 @@"]
    return "\n".join(head + ["-" + x for x in removed] + ["+" + x for x in added]) + "\n"


def by_id(gs):
    return {g["id"]: g for g in gs}


GREEN = {"commands": [{"kind": "build", "command": "mvn -q compile", "exit_code": 0}, {"kind": "test", "command": "mvn -q test", "exit_code": 0}],
         "diagnosis": {"match": "equivalent", "match_why": "A1 做到了"}}
SVC = "src/main/java/a/LeaveService.java"
ON_FLOW = {"ok": True, "covered": [SVC], "off": []}


class GatesTest(unittest.TestCase):
    def test_a_clean_change_passes_every_gate(self):
        gs = G.evaluate(diff(SVC, ["int a=1;"], ["int a=2;"]), GREEN, ON_FLOW, True)
        self.assertEqual([g["id"] for g in gs], G.ORDER)
        self.assertEqual(G.overall(gs), G.PASS, G.summary(gs))

    def test_whitespace_only_is_no_change(self):
        g = by_id(G.evaluate(diff(SVC, ["int a = 1;"], ["int  a=1;"]), GREEN, ON_FLOW, True))["changed"]
        self.assertEqual(g["state"], G.FAIL)

    def test_weakened_tests_are_caught(self):
        t = "src/test/java/a/LeaveServiceTest.java"
        cases = [
            diff(t, deleted=True, removed=["assertEquals(1, x);"]),
            diff(t, ["    assertEquals(\"审批中\", s);", "    assertTrue(ok);"], ["    // checked by hand"]),
            diff(t, ["  @Test"], ["  @Test", "  @Disabled"]),
            diff("web/src/leave.spec.ts", ["it('submits', () => {"], ["it.skip('submits', () => {"]),
            diff(".github/workflows/ci.yml", ["run: mvn test"], ["run: mvn test || true"]),
            diff("pom.xml", ["<skipTests>false</skipTests>"], ["<skipTests>true</skipTests>"]),
            diff("jest.config.js", ["  branches: 80,"], ["  branches: 60,"]),
        ]
        for d in cases:
            g = by_id(G.evaluate(diff(SVC, ["a"], ["b"]) + d, GREEN, ON_FLOW, True))["weaken"]
            self.assertEqual(g["state"], G.FAIL, d)
            self.assertTrue(g["detail"]["hits"])
        # adding a test, or moving an assertion, is not weakening
        ok = diff(t, ["assertEquals(1, x);"], ["assertEquals(1, x );", "assertNotNull(y);"])
        self.assertEqual(by_id(G.evaluate(ok, GREEN, ON_FLOW, True))["weaken"]["state"], G.PASS)

    def test_parse_reads_the_changed_file(self):
        files = {"conf/app.json": '{"a": 1,}', "tools/x.py": "def f(:\n", "web/form.xml": "<form><field/></form>"}
        d = "".join(diff(p, ["old"], ["new"]) for p in files)
        g = by_id(G.evaluate(d, {}, ON_FLOW, True, read=files.get))["parse"]
        self.assertEqual(g["state"], G.FAIL)
        self.assertEqual(len(g["detail"]["errors"]), 2)
        # Java has no parser here: a green build vouches for it, otherwise it is unknown
        self.assertEqual(by_id(G.evaluate(diff(SVC, ["a"], ["b"]), GREEN, ON_FLOW, True))["parse"]["state"], G.PASS)
        self.assertEqual(by_id(G.evaluate(diff(SVC, ["a"], ["b"]), {}, ON_FLOW, True))["parse"]["state"], G.UNKNOWN)

    def test_baseline_build_test_and_match(self):
        red = dict(GREEN, commands=[{"kind": "build", "command": "mvn compile", "exit_code": 0}, {"kind": "test", "command": "mvn test", "exit_code": 1}])
        gs = by_id(G.evaluate(diff(SVC, ["a"], ["b"]), red, ON_FLOW, True))
        self.assertEqual((gs["build"]["state"], gs["test"]["state"]), (G.PASS, G.FAIL))
        broken_base = {"skip": "原代码在这台机器上跑 `mvn test` 就失败（退出码 1）", "diagnosis": {"match": "partial"}}
        gs = by_id(G.evaluate(diff(SVC, ["a"], ["b"]), broken_base, ON_FLOW, True))
        self.assertEqual((gs["baseline"]["state"], gs["build"]["state"], gs["match"]["state"]), (G.UNKNOWN, G.UNKNOWN, G.UNKNOWN))
        self.assertIn("推断", gs["match"]["why"])
        for m, st in (("different", G.FAIL), ("wrong", G.FAIL), ("equivalent", G.PASS)):
            self.assertEqual(G.match({"match": m})["state"], st)

    def test_scope_and_path(self):
        v = dict(GREEN, beyond_plan=["src/main/java/a/UserController.java"])
        gs = by_id(G.evaluate(diff(SVC, ["a"], ["b"]), v, {"ok": False, "off": ["x.java"], "why": "不在业务流上"}, True))
        self.assertEqual((gs["scope"]["state"], gs["path"]["state"]), (G.FAIL, G.FAIL))
        gs = by_id(G.evaluate(diff(SVC, ["a"], ["b"]), GREEN, {"ok": False, "off": []}, False))
        self.assertEqual((gs["scope"]["state"], gs["path"]["state"]), (G.UNKNOWN, G.UNKNOWN))

    def test_a_person_can_let_a_gate_through_but_not_a_red_build(self):
        red = dict(GREEN, commands=[{"kind": "build", "command": "mvn compile", "exit_code": 1}], beyond_plan=["b.java"])
        gs = G.evaluate(diff(SVC, ["a"], ["b"]), red, ON_FLOW, True)
        w = G.waived(gs, {"scope": {"by": "王工", "reason": "配置文件必须一起改"}, "build": {"by": "王工", "reason": "测试机坏了"}})
        w = by_id(w)
        self.assertEqual((w["scope"]["state"], w["scope"]["waived"]["was"]), (G.PASS, G.FAIL))
        self.assertEqual(w["build"]["state"], G.FAIL)
        # an unknown build (no build environment) can be let through with a reason
        gs = G.evaluate(diff(SVC, ["a"], ["b"]), {"diagnosis": {"match": "equivalent"}}, ON_FLOW, True)
        w = by_id(G.waived(gs, {"build": {"by": "王工", "reason": "老系统没有构建环境，人工部署验证"}}))
        self.assertEqual(w["build"]["state"], G.PASS)


if __name__ == "__main__":
    unittest.main()
