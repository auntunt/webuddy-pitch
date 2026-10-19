import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from tmh import config as cfgmod  # noqa: E402
from tmh import activity, codeindex, discover, flow, guard, install, ledger, mapper, query, scanner, verify, webreport  # noqa: E402

JAVA = ROOT / "examples" / "legacy-java-oa"
DOTNET = ROOT / "examples" / "legacy-dotnet-erp"


def copy_repo(src: Path) -> Path:
    d = Path(tempfile.mkdtemp(prefix="tmh-test-"))
    dst = d / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    subprocess.run(["git", "init", "-q"], cwd=dst, check=True)
    subprocess.run(["git", "add", "-A"], cwd=dst, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], cwd=dst, check=True)
    return dst


def set_target(repo: Path, **target) -> dict:
    cfg = cfgmod.load(repo)
    cfg["target"].update(target)
    cfg["source"]["db"] = "oracle" if "java" in repo.name else "sqlserver"
    cfgmod.save(repo, cfg)
    return cfg


class ScannerTest(unittest.TestCase):
    def setUp(self):
        self.repo = copy_repo(JAVA)

    def rules_hit(self, cfg):
        res = scanner.scan_repo(self.repo, cfg)
        return {f["rule"]: f for f in res["findings"]}

    def test_java_findings_and_target_dependent_severity(self):
        cfg = set_target(self.repo, db="dm8", arch="arm64", crypto="sm")
        hits = self.rules_hit(cfg)
        for rid in ("DB-DRV-001", "DB-ORA-001", "DB-ORA-003", "MW-AS-001", "ARCH-DEP-001", "SM-HASH-001", "OS-PATH-001", "FE-IE-001"):
            self.assertIn(rid, hits)
        self.assertEqual(hits["DB-ORA-001"]["severity"], "low")  # 达梦 Oracle 兼容模式
        cfg = set_target(self.repo, db="opengauss")
        self.assertEqual(self.rules_hit(cfg)["DB-ORA-001"]["severity"], "medium")

    def test_rules_respect_target(self):
        cfg = set_target(self.repo, db="dm8", arch="x86_64", crypto="none")
        hits = self.rules_hit(cfg)
        self.assertNotIn("SM-HASH-001", hits)
        self.assertNotIn("ARCH-DEP-001", hits)

    def test_comment_lines_ignored(self):
        cfg = set_target(self.repo, db="dm8")
        rules = scanner.active_rules(scanner.load_rules(), cfg)
        found = scanner.scan_text("A.java", "// SELECT ROWNUM FROM DUAL\nclass A {}", rules, cfg)
        self.assertEqual(found, [])

    def test_all_rule_conditions_parse(self):
        cfg = cfgmod.load(self.repo)
        for r in scanner.load_rules():
            for c in r.get("requires", []):
                scanner._condition_holds(c, cfg)


class DotnetTest(unittest.TestCase):
    def test_dotnet_discovery_scan_and_map(self):
        repo = copy_repo(DOTNET)
        cfg = set_target(repo, db="kingbase", arch="arm64", crypto="sm", os="kylin")
        disc = discover.discover(repo)
        self.assertIn("dotnet", disc["stacks"])
        self.assertEqual(disc["dotnet"]["project_graph"]["Erp.Web/Erp.Web.csproj"], ["Erp.Core/Erp.Core.csproj"])
        rules = {f["rule"] for f in scanner.scan_repo(repo, cfg)["findings"]}
        for rid in ("NET-FW-001", "NET-WEB-001", "NET-WCF-001", "NET-WIN-001", "NET-DRAW-001", "DB-DRV-003", "DB-MS-001", "SM-ASYM-001"):
            self.assertIn(rid, rules)
        m = mapper.build_map(repo)
        paths = {(e["method"], e["path"]) for e in m["endpoints"]}
        self.assertIn(("GET", "/invoice/list"), paths)
        self.assertTrue(any(e["stack"] == "wcf/asmx" for e in m["endpoints"]))
        self.assertIn("CUSTOMER", m["tables"])


class MapAndQueryTest(unittest.TestCase):
    def setUp(self):
        self.repo = copy_repo(JAVA)

    def test_spring_endpoints_jobs_and_tables(self):
        m = mapper.build_map(self.repo)
        self.assertIn(("GET", "/leave/list"), {(e["method"], e["path"]) for e in m["endpoints"]})
        self.assertIn(("POST", "/leave/approve"), {(e["method"], e["path"]) for e in m["endpoints"]})
        self.assertEqual({j["kind"] for j in m["jobs"]}, {"@Scheduled"})
        self.assertIn("OA_LEAVE", m["tables"])
        self.assertTrue(any(o["name"] == "P_LEAVE_STAT" for o in m["db_objects"]))

    def test_impact_walks_table_to_endpoint(self):
        res = query.impact(self.repo, "OA_LEAVE")
        files = {r["file"] for r in res["referenced_by"]}
        self.assertIn("src/main/java/com/acme/oa/controller/LeaveController.java", files)
        self.assertIn("/leave/list", {e["path"] for e in res["entrypoints_in_referrers"]})

    def test_where_chinese_keyword(self):
        res = query.where(self.repo, ["请假"])
        self.assertEqual(res[0]["file"], "src/main/java/com/acme/oa/controller/LeaveController.java")


class LedgerTest(unittest.TestCase):
    def test_refresh_preserves_status_and_clears(self):
        repo = copy_repo(JAVA)
        cfg = set_target(repo, db="dm8")
        ledger.refresh(repo, scanner.scan_repo(repo, cfg))
        ledger.set_status(repo, "MW-AS-001", "doing", "开始")
        (repo / "src/main/webapp/WEB-INF/weblogic.xml").unlink()
        items = {i["id"]: i for i in ledger.refresh(repo, scanner.scan_repo(repo, cfg))}
        self.assertEqual(items["MW-AS-001"]["status"], "cleared")
        self.assertEqual(items["DB-DRV-001"]["status"], "todo")


def run_hook(fn, payload: dict, repo: Path):
    err = io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), redirect_stderr(err), \
            mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(repo)}):
        code = fn()
    return code, err.getvalue()


class GuardAndVerifyTest(unittest.TestCase):
    def setUp(self):
        self.repo = copy_repo(JAVA)
        set_target(self.repo, db="dm8", crypto="sm")
        verify.take_baseline(self.repo)

    def test_existing_test_is_locked_new_test_allowed(self):
        code, msg = run_hook(guard.pre_edit, {"tool_input": {"file_path": "src/test/java/com/acme/oa/LeaveServiceTest.java"}}, self.repo)
        self.assertEqual(code, 2)
        self.assertIn("基线", msg)
        code, _ = run_hook(guard.pre_edit, {"tool_input": {"file_path": str(self.repo / "src/test/java/com/acme/oa/NewTest.java")}}, self.repo)
        self.assertEqual(code, 0)
        code, _ = run_hook(guard.pre_edit, {"tool_input": {"file_path": ".tmh/baseline.json"}}, self.repo)
        self.assertEqual(code, 2)

    def test_post_edit_flags_new_incompatibility_only(self):
        p = self.repo / "src/main/java/com/acme/oa/util/Sign.java"
        p.write_text('class Sign { Object d() throws Exception { return java.security.MessageDigest.getInstance("MD5"); } }\n', encoding="utf-8")
        code, msg = run_hook(guard.post_edit, {"tool_input": {"file_path": str(p)}}, self.repo)
        self.assertEqual(code, 2)
        self.assertIn("SM-HASH-001", msg)
        # A pre-existing finding (in baseline) must not block an unrelated edit of that file.
        code, _ = run_hook(guard.post_edit, {"tool_input": {"file_path": "src/main/java/com/acme/oa/util/PasswordUtil.java"}}, self.repo)
        self.assertEqual(code, 0)

    def test_dangerous_bash(self):
        code, _ = run_hook(guard.pre_bash, {"tool_input": {"command": "git push -f origin main"}}, self.repo)
        self.assertEqual(code, 2)
        code, _ = run_hook(guard.pre_bash, {"tool_input": {"command": "disql SYSDBA/x@db"}}, self.repo)
        self.assertEqual(code, 2)
        code, _ = run_hook(guard.pre_bash, {"tool_input": {"command": "mvn -q test"}}, self.repo)
        self.assertEqual(code, 0)

    def test_shell_write_to_locked_test_blocked(self):
        cmd = "sed -i s/true/false/ src/test/java/com/acme/oa/LeaveServiceTest.java"
        code, _ = run_hook(guard.pre_bash, {"tool_input": {"command": cmd}}, self.repo)
        self.assertEqual(code, 2)

    def test_build_output_ignored(self):
        (self.repo / "target" / "classes").mkdir(parents=True)
        (self.repo / "target" / "classes" / "application.yml").write_text("url: jdbc:oracle:thin:@x\n", encoding="utf-8")
        r = verify.verify(self.repo, run_tests=False)
        self.assertEqual(r["changed_files"], [])
        self.assertTrue(r["passed"])

    def test_verify_catches_weakened_test(self):
        t = self.repo / "src/test/java/com/acme/oa/LeaveServiceTest.java"
        t.write_text(t.read_text(encoding="utf-8").replace("assertTrue(true)", "/* removed */"), encoding="utf-8")
        r = verify.verify(self.repo, run_tests=False)
        self.assertFalse(r["passed"])
        self.assertEqual(r["protected_violations"][0]["file"], "src/test/java/com/acme/oa/LeaveServiceTest.java")

    def test_verify_passes_clean_change(self):
        svc = self.repo / "src/main/java/com/acme/oa/service/LeaveService.java"
        svc.write_text(svc.read_text(encoding="utf-8") + "\n// tidy\n", encoding="utf-8")
        r = verify.verify(self.repo, run_tests=False)
        self.assertTrue(r["passed"], r)
        self.assertEqual(r["changed_files"], ["src/main/java/com/acme/oa/service/LeaveService.java"])


class InstallTest(unittest.TestCase):
    def test_agents_block_budget_keeps_hard_rules_and_command_reference(self):
        block = (ROOT / "templates/AGENTS.block.md").read_bytes()
        self.assertLessEqual(len(block), 3584)
        for rule in ("关单只认用户确认", "不改基线测试", "没有验收标准（AC）不进实现", "完成前必须 tmh verify"):
            self.assertIn(rule, block.decode("utf-8"))
        with tempfile.TemporaryDirectory(prefix="tmh-install-budget-") as tmp:
            repo = Path(tmp)
            install.install(repo, ["claude", "codex"])
            self.assertIn(block.decode("utf-8").strip(), (repo / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertEqual((repo / ".tmh/docs/agent-commands.md").read_bytes(),
                             (ROOT / "docs/agent-commands.md").read_bytes())

    def test_install_is_idempotent_and_keeps_user_content(self):
        repo = copy_repo(JAVA)
        (repo / "AGENTS.md").write_text("# 团队约定\n\n用 4 空格缩进。\n", encoding="utf-8")
        install.install(repo, ["claude", "codex"])
        install.install(repo, ["claude", "codex"])
        agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("用 4 空格缩进", agents)
        self.assertEqual(agents.count(install.BEGIN), 1)
        settings = json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 2)
        self.assertTrue((repo / ".agents/skills/legacy-feature/SKILL.md").exists())
        self.assertTrue((repo / ".claude/agents/impact-analyst.md").exists())
        out = subprocess.run([sys.executable, str(repo / ".tmh/tool/tmh.py"), "status", "--repo", str(repo)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_skills_have_frontmatter(self):
        for s in (ROOT / "skills").iterdir():
            text = (s / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\nname: %s\n" % s.name), s)
            self.assertIn("\ndescription: ", text)


class FlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.java = flow.build_flows(JAVA)
        cls.flows = {f["id"]: f for f in cls.java["flows"]}

    def test_flow_chain_crud_and_rules(self):
        f = self.flows["post-leave-approve"]
        self.assertEqual(f["name"], "审批通过：记录审批人与审批时间")
        self.assertEqual(f["crud"], {"OA_APPROVAL_LOG": "C", "OA_LEAVE": "U"})
        self.assertEqual([n["layer"] for n in f["nodes"][:3]], ["entry", "service", "dao"])
        self.assertEqual(f["states"][0]["from"], ["SUBMITTED"])
        self.assertEqual(f["states"][0]["to"], "APPROVED")
        sub = self.flows["post-leave-submit"]
        self.assertIn("请假天数必须在 1 到 30 天之间", [r["message"] for r in sub["rules"]])
        self.assertTrue(sub["transactions"])
        self.assertTrue(self.flows["reportjob-export"]["side_effects"])

    def test_state_machine(self):
        sm = next(s for s in self.java["state_machines"] if s["table"] == "OA_LEAVE")
        self.assertEqual((sm["table"], sm["column"]), ("OA_LEAVE", "STATUS"))
        pairs = {(t["from"], t["to"]) for t in sm["transitions"]}
        self.assertEqual(pairs, {("(新建)", "SUBMITTED"), ("SUBMITTED", "APPROVED"), ("SUBMITTED", "REJECTED"), ("SUBMITTED", "EXPIRED")})

    def test_dotnet_inline_sql_state(self):
        d = {f["id"]: f for f in flow.build_flows(DOTNET)["flows"]}
        s = d["post-invoice-submit"]["states"][0]
        self.assertEqual((s["table"], s["from"], s["to"]), ("INVOICE", ["Draft"], "Submitted"))

    def test_analyze_sql(self):
        a = flow.analyze_sql("UPDATE T_ORDER SET PAY_STATUS = 'PAID' WHERE ID = ? AND PAY_STATUS IN ('NEW','PENDING')")
        self.assertEqual(a["states"][0]["from"], ["NEW", "PENDING"])
        a = flow.analyze_sql("INSERT INTO T_ORDER (ID, STATUS) VALUES (seq.nextval, 'NEW')")
        self.assertEqual((a["op"], a["states"][0]["to"]), ("C", "NEW"))
        self.assertEqual(sorted(mapper._tables_in("SELECT * FROM T_A a, T_B b WHERE a.id = b.id")), ["T_A", "T_B"])

    def test_mask_keeps_structure(self):
        src = 'class A {\n  @RequestMapping(value = {"/a{"})\n  void m() { String s = "}"; /* { */ b.c(); }\n  void n() {}\n}\n'
        cls = codeindex.parse_source("A.java", src, "java")[0]
        self.assertEqual(sorted(cls["methods"]), ["m", "n"])

    def test_affected_flows_by_line(self):
        flows = self.java["flows"]
        svc = "src/main/java/com/acme/oa/service/LeaveService.java"
        approve = next(n for n in self.flows["post-leave-approve"]["nodes"] if n["key"] == "LeaveService.approve")
        hit = webreport.affected_flows(flows, [svc], {svc: [(approve["line"] + 2, approve["line"] + 2)]})
        self.assertEqual([f["id"] for f in hit], ["post-leave-approve"])
        self.assertEqual(len(webreport.affected_flows(flows, [svc], None)), 5)  # file-level fallback

    def test_report_renders(self):
        repo = copy_repo(JAVA)
        install.install(repo, ["claude", "codex"])
        activity.log(repo, "finding", "审批状态在 OA_LEAVE.STATUS")
        notes = repo / ".tmh/knowledge/flows"
        notes.mkdir(parents=True)
        (notes / "post-leave-approve.md").write_text("# 请假审批通过\n\n状态：已确认\n\n## 业务目的\n同意请假【待确认】\n", encoding="utf-8")
        page = webreport.render(repo, flow.build_flows(repo))
        for s in ("<svg class=\"flow\"", "<svg class=\"sm\"", "请假审批通过", "审批状态在 OA_LEAVE.STATUS", "业务说明：已确认", "tag-ask"):
            self.assertIn(s, page)
        self.assertNotIn("http://", page.replace("http://www.w3", ""))  # offline: no external resources


class AgentHookTest(unittest.TestCase):
    def setUp(self):
        self.repo = copy_repo(JAVA)
        install.install(self.repo, ["claude", "codex"])
        verify.take_baseline(self.repo)

    def test_codex_patch_to_locked_test_blocked(self):
        patch = "*** Begin Patch\n*** Update File: src/test/java/com/acme/oa/LeaveServiceTest.java\n@@\n-a\n+b\n*** End Patch"
        code, _ = run_hook(guard.agent_pre, {"tool_name": "apply_patch", "tool_input": {"input": patch}}, self.repo)
        self.assertEqual(code, 2)
        code, _ = run_hook(guard.agent_pre, {"tool_name": "shell", "tool_input": {"command": ["bash", "-lc", "git reset --hard"]}}, self.repo)
        self.assertEqual(code, 2)
        code, _ = run_hook(guard.agent_pre, {"tool_name": "shell", "tool_input": {"command": ["bash", "-lc", "mvn -q test"]}}, self.repo)
        self.assertEqual(code, 0)

    def test_tool_calls_logged(self):
        run_hook(guard.agent_post, {"tool_name": "Read", "tool_input": {"file_path": "pom.xml"}}, self.repo)
        self.assertEqual(activity.read(self.repo)[-1]["text"], "读取 pom.xml")

    def test_codex_files_installed(self):
        hooks = json.loads((self.repo / ".codex/hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(hooks["hooks"]), {"PreToolUse", "PostToolUse", "Stop"})
        install.install(self.repo, ["codex"])
        hooks = json.loads((self.repo / ".codex/hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(len(hooks["hooks"]["PreToolUse"]), 1)
        agent = (self.repo / ".codex/agents/impact-analyst.toml").read_text(encoding="utf-8")
        self.assertIn('name = "impact-analyst"', agent)
        try:
            import tomllib
        except ImportError:
            return
        self.assertIn("developer_instructions", tomllib.loads(agent))


if __name__ == "__main__":
    unittest.main()


class KnowledgeBaseTest(unittest.TestCase):
    """Whole-project knowledge base: graph, domains, pages, staleness, queue, context."""

    def setUp(self):
        from tmh import kb
        self.kb = kb
        self.repo = copy_repo(JAVA)
        self.res = kb.build(self.repo)

    def write_page(self, pid, extra_ref="src/main/java/com/acme/oa/service/ExpenseService.java:57"):
        p = self.kb.page_path(self.repo, pid)
        pg = self.kb.parse_page(p.read_text(encoding="utf-8"))
        meta = dict(pg["meta"], title="报销单财务审核", summary="财务审核报销单，驳回时释放冻结预算。")
        kind = self.kb.page_kind(pid)
        body = "\n".join("## %s\n内容，见 %s。\n" % (s, extra_ref) for s in self.kb.SECTIONS[kind])
        p.write_text(self.kb.render_page(pid, meta, pg["facts"], body), encoding="utf-8")

    def test_graph_domains_and_pages(self):
        from tmh.graph import Graph
        g = Graph(self.repo)
        self.assertEqual({d["id"] for d in g.nodes("dom")}, {"dom:leave", "dom:expense", "dom:user"})
        self.assertEqual(g.node("flow:reportjob-expire")["domain"], "leave")  # job joins the area that owns its table
        self.assertEqual(g.node("tbl:OA_BUDGET")["domain"], "expense")
        self.assertIn("UPDATE OA_EXPENSE", g.node("fn:ExpenseMapper.auditPass")["data"]["sql"])
        k = self.kb.kdir(self.repo)
        for rel_ in ("index.md", "domains/expense.md", "flows/post-expense-audit.md", "entities/OA_EXPENSE.md", "modules/root.md", "glossary.md"):
            self.assertTrue((k / rel_).exists(), rel_)
        self.assertNotIn("flow:get-expense-mine", self.kb.load_registry(self.repo))  # read-only query: facts only, not queued
        text = (k / "flows" / "post-expense-audit.md").read_text(encoding="utf-8")
        self.assertIn("ExpenseMapper.auditReject", text)
        self.assertIn("../entities/OA_BUDGET.md", text)

    def test_incremental_parse_cache(self):
        r = self.kb.build(self.repo)
        self.assertEqual(r["graph"]["parsed"], 0)
        p = self.repo / "src/main/java/com/acme/oa/service/UserService.java"
        p.write_text(p.read_text(encoding="utf-8") + "\n// note\n", encoding="utf-8")
        r = self.kb.build(self.repo)
        self.assertEqual(r["graph"]["parsed"], 1)

    def test_done_validates_then_code_change_marks_only_affected_pages_stale(self):
        pid = "flow:post-expense-audit"
        ok, errs = self.kb.done(self.repo, pid)
        self.assertFalse(ok)
        self.assertTrue(any("summary" in e for e in errs))
        self.write_page(pid, extra_ref="src/main/java/com/acme/oa/service/ExpenseService.java:9999")
        ok, errs = self.kb.done(self.repo, pid)
        self.assertFalse(ok)
        self.assertTrue(any("证据" in e for e in errs))
        self.write_page(pid)
        ok, errs = self.kb.done(self.repo, pid)
        self.assertTrue(ok, errs)
        self.write_page("flow:post-expense-pay")
        self.assertTrue(self.kb.done(self.repo, "flow:post-expense-pay")[0])
        reg = self.kb.load_registry(self.repo)
        self.assertEqual(reg[pid]["status"], "待确认")
        self.assertIn("fn:ExpenseService.audit", reg[pid]["anchors"])
        # change one method: only the flow that runs through it goes stale
        p = self.repo / "src/main/java/com/acme/oa/service/ExpenseService.java"
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace('budgetMapper.release((Long) e.get("DEPT_ID"), (BigDecimal) e.get("AMOUNT"));',
                               'if (e.get("FROZEN") != null) budgetMapper.release((Long) e.get("DEPT_ID"), (BigDecimal) e.get("AMOUNT"));'), encoding="utf-8")
        r = self.kb.build(self.repo)
        self.assertEqual(r["stale"], [pid])
        page = self.kb.page_path(self.repo, pid).read_text(encoding="utf-8")
        self.assertIn("status: 过期", page)
        self.assertIn("内容，见", page)  # understanding kept
        nxt = self.kb.next_jobs(self.repo)
        self.assertEqual(nxt["jobs"], [pid])  # stale pages first
        pack = self.kb.pack(self.repo, pid)
        self.assertIn("过去的说明", pack)
        self.assertIn("fn:ExpenseService.audit", pack)
        self.assertTrue(self.kb.done(self.repo, pid)[0])
        self.assertNotIn("stale", self.kb.load_registry(self.repo)[pid])
        self.kb.confirm(self.repo, pid, "张三")
        self.assertEqual(self.kb.load_registry(self.repo)[pid]["status"], "已确认")

    def test_queue_is_bottom_up_and_parallel_safe(self):
        a = self.kb.next_jobs(self.repo, who="w1")["jobs"]
        b = self.kb.next_jobs(self.repo, who="w2")["jobs"]
        self.assertTrue(a[0].startswith("flow:") and b[0].startswith("flow:"))
        self.assertNotEqual(a, b)
        # domain pages wait for their flows and tables
        r = self.kb.next_jobs(self.repo, n=100, who="w3")
        self.assertFalse(any(j.startswith("dom:") or j == "index" for j in r["jobs"]))
        self.assertIn("tbl:OA_EXPENSE", r["waiting"])  # written by flows still in the queue
        self.assertIn("tbl:OA_DEPT", r["jobs"])  # only read by a facts-only query flow, nothing to wait for

    def test_domain_assignment_is_sticky_and_editable(self):
        from tmh import domains
        st = domains.load(self.repo)
        st["assign"]["post-user-disable"] = "expense"
        st["domains"]["expense"]["title"] = "费用报销"
        domains.domains_path(self.repo).write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        self.kb.build(self.repo)
        from tmh.graph import Graph
        g = Graph(self.repo)
        self.assertEqual(g.node("flow:post-user-disable")["domain"], "expense")
        self.assertEqual(g.node("dom:expense")["name"], "费用报销")

    def test_context_finds_relevant_knowledge(self):
        from tmh.context import build_context, terms
        self.assertIn("报销", terms("报销单驳回"))
        self.assertIn("expense", terms("ExpenseService"))
        out = build_context(self.repo, "报销单财务审核驳回后预算")
        self.assertIn("post-expense-audit", out)
        self.assertIn("OA_BUDGET", out)
        self.assertLess(out.index("post-expense-audit"), out.index("post-leave") if "post-leave" in out else len(out))

    def test_report_has_knowledge_tab_and_cli(self):
        out = io.StringIO()
        from contextlib import redirect_stdout
        from tmh import cli
        with redirect_stdout(out):
            cli.main(["kb", "status", "--repo", str(self.repo)])
            cli.main(["context", "请假", "审批", "--repo", str(self.repo)])
            cli.main(["report", "--classic", "--repo", str(self.repo)])
            cli.main(["report", "--repo", str(self.repo)])
        self.assertIn("知识页", out.getvalue())
        html_ = (self.repo / ".tmh/report/classic.html").read_text(encoding="utf-8")
        self.assertIn('data-t="kb"', html_)
        self.assertIn('data-kb="domains/expense.md"', html_)

        ex = (self.repo / ".tmh/report/index.html").read_text(encoding="utf-8")
        ov = json.loads(ex.split("window.TMH_OVERVIEW=", 1)[1].split(";</script>", 1)[0])
        self.assertEqual({d["id"] for d in ov["domains"]}, {"leave", "expense", "user"})
        self.assertIn("MyBatis", [c["name"] for c in ov["build"]["components"]])
        self.assertEqual(ov["build"]["java"]["build"], "maven")
        exp = next(d for d in ov["domains"] if d["id"] == "expense")
        js = (self.repo / (".tmh/report/data/d%d.js" % exp["i"])).read_text(encoding="utf-8")
        self.assertTrue(js.startswith("TMH.loaded(%d," % exp["i"]))
        self.assertIn("post-expense-submit", js)
        self.assertIn("用户不存在或已停用", js)  # rule message reaches the flow card
        self.assertIn(["f", "post-expense-submit", exp["i"]], [x[:3] for x in ov["search"]])

    def test_build_facts_keep_no_secret_values(self):
        from tmh import buildinfo
        (self.repo / "src/main/resources/application.properties").write_text(
            "spring.datasource.url=jdbc:mysql://db.local:3306/oa?useSSL=false\nspring.datasource.password=S3cret!\n", encoding="utf-8")
        b = buildinfo.analyze(self.repo)
        self.assertNotIn("S3cret", json.dumps(b, ensure_ascii=False))
        c = next(c for c in b["configs"] if c["file"].endswith("application.properties"))
        self.assertEqual((c["plain_secrets"], c["jdbc"][0]["db"], c["jdbc"][0]["name"]), (1, "mysql", "oa"))
        self.assertTrue(any("明文密码" in r["title"] for r in b["risks"]))

    def test_install_ships_kb_writer_for_both_engines(self):
        install.install(self.repo, ["claude", "codex"])
        self.assertTrue((self.repo / ".claude/agents/kb-writer.md").exists())
        toml = (self.repo / ".codex/agents/kb-writer.toml").read_text(encoding="utf-8")
        self.assertIn('name = "kb-writer"', toml)
        self.assertIn("tmh context", (self.repo / "AGENTS.md").read_text(encoding="utf-8"))


class KnowledgeOriginalAndHumanLoopTest(unittest.TestCase):
    """The knowledge base is read as written; people answer questions; triage never says yes on its own for risky asks."""

    @classmethod
    def setUpClass(cls):
        from tmh import kb
        cls.kb = kb
        cls.src = copy_repo(JAVA)
        kb.build(cls.src)

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="tmh-kbqa-")) / "r"
        shutil.copytree(self.src, self.repo)
        from tmh import kbqa
        self.q = kbqa
        pid = "flow:post-expense-audit"
        p = self.kb.page_path(self.repo, pid)
        pg = self.kb.parse_page(p.read_text(encoding="utf-8"))
        body = "\n".join("## %s\n财务审核原文第 %d 段，见 src/main/java/com/acme/oa/service/ExpenseService.java:57。【推断】驳回释放预算。\n" % (s, i)
                         for i, s in enumerate(self.kb.SECTIONS["flow"]))
        p.write_text(self.kb.render_page(pid, dict(pg["meta"], title="报销单财务审核", summary="财务审核报销单，驳回时释放冻结预算。"), pg["facts"], body), encoding="utf-8")
        self.assertTrue(self.kb.done(self.repo, pid)[0])
        self.pid = pid

    def test_read_returns_pages_verbatim_and_never_cuts(self):
        on_disk = self.kb.page_path(self.repo, self.pid).read_text(encoding="utf-8")
        out = self.q.read(self.repo, [self.pid])
        self.assertIn(on_disk.rstrip("\n"), out)
        self.assertIn("待确认", out.splitlines()[0])
        two = self.q.read(self.repo, [self.pid, "dom:expense"], budget=len(on_disk) + 10)
        self.assertIn("超出预算未展开", two)
        self.assertNotIn("…（已按预算截断）", two)
        self.assertIn("术语表", self.q.read(self.repo, ["glossary.md"]))

    def test_chain_follows_domain_flow_tables_with_original_text(self):
        c = self.q.chain(self.repo, "报销单财务审核驳回")
        self.assertIn(self.pid, c["flows"])
        self.assertIn("dom:expense", c["domains"])
        self.assertIn("tbl:OA_EXPENSE", c["tables"])
        text = self.q.chain_text(self.repo, c)
        self.assertIn("财务审核原文第 3 段", text)
        self.assertIn("链路：", text)

    def test_question_answer_written_back_verbatim_and_queued(self):
        n = self.q.ask(self.repo, "驳回后预算是否全额释放？", [self.pid], "财务负责人")
        self.assertEqual(self.q.ask(self.repo, "驳回后预算是否全额释放？", [self.pid]), n)  # no duplicate
        self.assertIn("驳回后预算是否全额释放", self.q.chain_text(self.repo, self.q.chain(self.repo, "报销单财务审核驳回")))
        with self.assertRaises(ValueError):
            self.q.answer(self.repo, n, "是的", "agent")  # answers belong to a person
        said = "全额释放，但跨年的单据\n释放到新年度。"
        r = self.q.answer(self.repo, n, said, "王会计")
        self.assertEqual(r["pages"], [self.pid])
        page = self.kb.page_path(self.repo, self.pid).read_text(encoding="utf-8")
        self.assertIn("## 业务方答复", page)
        self.assertIn("王会计", page)
        self.assertIn("全额释放，但跨年的单据", page)
        self.assertIn("释放到新年度。", page)
        q = next(x for x in self.q.questions(self.repo) if x["n"] == n)
        self.assertFalse(q["open"])
        self.assertIn("已答复（王会计", q["answer"])
        nxt = self.kb.next_jobs(self.repo)
        self.assertEqual(nxt["jobs"], [self.pid])  # answered page is revised first
        self.assertIn("业务方答复", self.kb.instructions(self.repo, self.pid))
        self.assertTrue(self.kb.done(self.repo, self.pid)[0])  # the answer section does not break validation
        self.assertNotIn("revise", self.kb.load_registry(self.repo)[self.pid])
        self.assertEqual(self.q.stats(self.repo)["questions_answered"], 1)

    def test_existing_question_rows_are_numbered_and_kept(self):
        p = self.kb.kdir(self.repo) / "open-questions.md"
        p.write_text(p.read_text(encoding="utf-8") + "| 旧问题？ | dom:expense | 业务负责人 | 未答复；代码只能确认导出 |\n", encoding="utf-8")
        n = self.q.ask(self.repo, "新问题？", ["dom:expense"])
        self.assertEqual([x["n"] for x in self.q.questions(self.repo)], [1, n])
        self.q.answer(self.repo, 1, "旧问题的答复", "李四")
        txt = p.read_text(encoding="utf-8")
        self.assertIn("| 旧问题？ | dom:expense | 业务负责人 | 已答复（李四", txt)
        self.assertIn("| 新问题？ |", txt)

    def test_triage_rules_send_risky_or_unconfirmed_asks_to_people(self):
        r = self.q.triage(self.repo, "报销单财务审核驳回后能不能不释放预算", use_model=False)
        self.assertEqual(r["verdict"], "需要人判断")
        self.assertTrue(any("预算" in x for x in r["reasons"]))
        self.assertIn(r["confidence"], ("中", "低"))
        none = self.q.triage(self.repo, "火星基地排班", use_model=False)
        self.assertEqual(none["verdict"], "需要人判断")
        self.assertTrue(none["questions"])
        rec = self.q.record(self.repo, none)
        self.assertEqual(len(rec["questions"]), 1)
        self.assertTrue(any("火星基地排班" in q["question"] for q in self.q.questions(self.repo)))

    @staticmethod
    def _completion(letter, dist=None):
        top = [{"token": k, "logprob": v} for k, v in (dist or {}).items()]
        return {"choices": [{"message": {"content": letter}, "logprobs": {"content": [{"token": letter, "top_logprobs": top}]} if dist else None}]}

    def test_triage_model_picks_preset_options_with_probabilities(self):
        import math
        os.environ.update(TMH_ROUTER_BASE_URL="http://router.invalid/v1", TMH_ROUTER_MODEL="gpt-lunamax", TMH_ROUTER_KEY="k")
        try:
            sure = {"A": math.log(0.95), "D": math.log(0.04), "B": math.log(0.01)}
            calls = []

            def fake(conf, body, timeout=60):
                calls.append(body)
                return self._completion("A", sure if len(calls) == 1 else {"A": 0.0})
            with mock.patch.object(self.q, "_post", side_effect=fake):
                r = self.q.triage(self.repo, "报销单财务审核页面加一个备注字段")
            self.assertEqual((calls[0]["max_tokens"], calls[0]["logprobs"]), (1, True))  # one letter, not prose
            self.assertIn("财务审核原文第 0 段", calls[0]["messages"][1]["content"])  # the model reads the pages as written
            self.assertIn("A. 能直接答复", calls[0]["messages"][1]["content"])
            self.assertEqual((r["route"], round(r["route_p"], 2), r["model"]), ("answer", 0.95, "gpt-lunamax"))
            self.assertEqual(r["basis"][0], r["chain"]["flows"][0])
            self.assertIn("核对原文后可直接答复", r["answer"])  # preset wording, not generated
            self.assertNotEqual(r["confidence"], "高")  # evidence is only 待确认
            self.assertEqual((r["verdict"], r["draft_verdict"]), ("需要人判断", "可以做"))  # 审核 is sensitive

            # unsure model + ask route: a question is filed to someone picked from the preset list
            unsure = {"D": math.log(0.5), "A": math.log(0.3), "B": math.log(0.2)}
            seq = iter([self._completion("D", unsure), self._completion("A", {"A": 0.0}), self._completion("B", {"B": 0.0})])
            with mock.patch.object(self.q, "_post", side_effect=lambda *a, **k: next(seq)):
                r2 = self.q.triage(self.repo, "报销单备注字段长度")
            self.assertEqual((r2["route"], r2["confidence"]), ("ask", "低"))
            self.assertEqual(r2["questions"][0]["who"], "待指定")
            with mock.patch.object(self.q, "_post", return_value=self._completion("Z")):
                r3 = self.q.triage(self.repo, "报销单备注字段长度")
            self.assertTrue(any("调用失败" in x for x in r3["reasons"]))
            self.assertEqual(r3["verdict"], "需要人判断")
        finally:
            for k in ("TMH_ROUTER_BASE_URL", "TMH_ROUTER_MODEL", "TMH_ROUTER_KEY"):
                os.environ.pop(k, None)

    def test_cli_and_mcp_expose_reading_and_the_loop(self):
        from contextlib import redirect_stdout
        from tmh import cli, mcp
        out = io.StringIO()
        with redirect_stdout(out):
            cli.main(["kb", "read", self.pid, "--repo", str(self.repo)])
            cli.main(["kb", "ask", "审核人能否改金额？", "--pages", self.pid, "--to", "财务", "--repo", str(self.repo)])
            cli.main(["kb", "answer", "1", "不能改，只能驳回", "--who", "王会计", "--repo", str(self.repo)])
            cli.main(["kb", "questions", "--all", "--repo", str(self.repo)])
            cli.main(["kb", "triage", "报销", "审核", "--no-model", "--repo", str(self.repo)])
            cli.main(["kb", "status", "--repo", str(self.repo)])
        o = out.getvalue()
        self.assertIn("财务审核原文第 0 段", o)
        self.assertIn("已记录问题 #1 的答复", o)
        self.assertIn("需求预判", o)
        self.assertIn("业务方问题：未答复 0 个，已答复 1 个", o)
        names = {t["name"] for t in mcp.list_tools(self.repo)}
        self.assertTrue({"kb_chain", "kb_read", "kb_triage", "kb_questions", "kb_ask"} <= names)
        self.assertNotIn("kb_answer", names)  # answers come from people, not agents
        text, err = mcp.call_tool(self.repo, "kb_read", {"ids": self.pid + ", glossary.md"})
        self.assertFalse(err)
        self.assertIn("财务审核原文第 1 段", text)


class KnowledgeBaseValidateTest(unittest.TestCase):
    def test_appended_sections_with_skeleton_left_are_rejected(self):
        from tmh import kb
        repo = copy_repo(JAVA)
        kb.build(repo)
        p = kb.page_path(repo, "dom:expense")
        t = p.read_text(encoding="utf-8").replace("title: expense", "title: 费用报销\nsummary: 报销与预算。")
        t += "\n" + "\n".join("## %s\n内容 src/main/java/com/acme/oa/service/ExpenseService.java:57\n" % s for s in kb.SECTIONS["dom"])
        p.write_text(t, encoding="utf-8")
        errs, _ = kb.validate(repo, "dom:expense")
        self.assertTrue(any("重复" in e for e in errs), errs)
