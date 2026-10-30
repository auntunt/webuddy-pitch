"""Ops-tool integrations against in-process mock servers (no real Jira/Jenkins needed)."""
import base64
import io
import json
import os
import subprocess
import sys
import threading
import unittest
import urllib.parse
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tmh import config as cfgmod  # noqa: E402
from tmh import integrations as I  # noqa: E402
from tmh.cli import main  # noqa: E402

JAVA = HERE.parent / "examples" / "legacy-java-oa"


def copy_repo(src: Path) -> Path:
    import shutil
    import tempfile
    dst = Path(tempfile.mkdtemp(prefix="tmh-int-")) / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", ".tmh", "target"))
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(["git"] + cmd, cwd=dst, check=True)
    return dst


class Mock:
    """routes: {(METHOD, path): body | (status, body) | callable(req) -> (status, body)}; records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        mock_ = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _do(self):
                u = urllib.parse.urlsplit(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                req = {"method": self.command, "path": u.path, "query": dict(urllib.parse.parse_qsl(u.query)),
                       "headers": dict(self.headers), "body": json.loads(body) if body[:1] in (b"{", b"[") else body.decode()}
                mock_.calls.append(req)
                r = mock_.routes.get((self.command, u.path))
                if r is None:
                    status, out = 404, {"error": "no route %s %s" % (self.command, u.path)}
                elif callable(r):
                    status, out = r(req)
                elif isinstance(r, tuple):
                    status, out = r
                else:
                    status, out = 200, r
                data = out.encode() if isinstance(out, str) else json.dumps(out).encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/plain" if isinstance(out, str) else "application/json")
                self.send_header("Content-Length", str(len(data)))
                if status == 201 and u.path.endswith("/build"):
                    self.send_header("Location", "http://x/queue/item/7/")
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = _do

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()

    def writes(self):
        return [c for c in self.calls if c["method"] != "GET"]


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


JIRA_ISSUE = {"key": "OA-7", "fields": {
    "summary": "报销审核增加驳回原因必填", "status": {"name": "待处理"}, "issuetype": {"name": "需求"}, "priority": {"name": "高"},
    "assignee": {"displayName": "张三"}, "reporter": {"displayName": "李四"},
    "description": "财务审核报销单时，驳回必须填写原因，原因写入审批日志。", "labels": ["财务"],
    "issuelinks": [{"type": {"outward": "blocks"}, "outwardIssue": {"key": "OA-8", "fields": {"summary": "报表口径"}}}],
    "comment": {"comments": [{"author": {"displayName": "王五"}, "created": "2026-10-01T10:00:00", "body": "注意老数据没有原因字段"}]}}}


class IntegrationBase(unittest.TestCase):
    def setUp(self):
        self.repo = copy_repo(JAVA)
        cfgmod.save(self.repo, cfgmod.load(self.repo))
        self.env = mock.patch.dict(os.environ, {"JIRA_TOKEN": "s3cret", "JENKINS_TOKEN": "jt", "GITLAB_TOKEN": "gt", "SONAR_TOKEN": "st",
                                                "ZENTAO_PASSWORD": "zp", "WIKI_TOKEN": "wt", "DING_HOOK": "", "TAPD_PASSWORD": "tp"})
        self.env.start()
        self.servers = []

    def tearDown(self):
        self.env.stop()
        for s in self.servers:
            s.close()

    def serve(self, routes):
        m = Mock(routes)
        self.servers.append(m)
        return m

    def add_tool(self, name, conf, default=False):
        cfg = cfgmod.load(self.repo)
        cfg["integrations"]["tools"][name] = conf
        if default:
            for c in I.make(self.repo, name, conf).CAPABILITIES:
                cfg["integrations"]["defaults"][c] = name
        cfgmod.save(self.repo, cfg)

    def kb(self):
        from tmh import kb
        kb.build(self.repo)


class FrameworkTest(IntegrationBase):
    def test_literal_secret_rejected_and_env_required(self):
        with self.assertRaises(I.IntegrationError) as e:
            I.make(self.repo, "j", {"type": "jira", "url": "http://x", "auth": {"type": "bearer", "token": "abc"}})
        self.assertIn("token_env", str(e.exception))
        rc, out = run(["int", "add", "j", "--type", "jira", "--url", "http://x", "--set", "password=abc", "--repo", str(self.repo)])
        self.assertEqual(rc, 2)
        self.assertNotIn("abc", (self.repo / ".tmh" / "config.json").read_text())
        inst = I.make(self.repo, "j", {"type": "jira", "url": "http://x", "auth": {"type": "bearer", "token_env": "NOPE_TOKEN"}})
        with self.assertRaises(I.IntegrationError) as e:
            inst.get_issue("OA-1")
        self.assertIn("NOPE_TOKEN", str(e.exception))

    def test_add_list_and_pick_by_capability(self):
        rc, out = run(["int", "add", "jira", "--type", "jira", "--url", "https://jira.example.com", "--token-env", "JIRA_TOKEN",
                       "--set", "project=OA", "--repo", str(self.repo)])
        self.assertEqual(rc, 0, out)
        conf = cfgmod.load(self.repo)["integrations"]["tools"]["jira"]
        self.assertEqual(conf["auth"], {"type": "bearer", "token_env": "JIRA_TOKEN"})
        self.assertEqual(conf["project"], "OA")
        rc, out = run(["int", "list", "--repo", str(self.repo)])
        self.assertIn("JIRA_TOKEN", out)
        self.assertNotIn("s3cret", out)
        self.assertEqual(I.pick(self.repo, "issues").name, "jira")
        with self.assertRaises(I.IntegrationError):
            I.pick(self.repo, "builds")

    def test_http_errors_explained_and_retried(self):
        n = {"c": 0}

        def flaky(req):
            n["c"] += 1
            return (503, {}) if n["c"] < 2 else (200, {"displayName": "Li"})
        m = self.serve({("GET", "/rest/api/2/myself"): flaky, ("GET", "/rest/api/2/issue/OA-404"): (404, {"errorMessages": ["不存在"]})})
        self.add_tool("jira", {"type": "jira", "url": m.url, "auth": {"type": "bearer", "token_env": "JIRA_TOKEN"}})
        inst = I.make(self.repo, "jira")
        self.assertIn("Li", inst.ping())
        self.assertEqual(n["c"], 2)
        self.assertEqual(m.calls[-1]["headers"]["Authorization"], "Bearer s3cret")
        with self.assertRaises(I.IntegrationError) as e:
            inst.get_issue("OA-404")
        self.assertIn("404", str(e.exception))
        self.assertIn("工单号", str(e.exception))

    def test_plugin_is_loaded_from_repo(self):
        d = self.repo / ".tmh" / "integrations"
        d.mkdir(parents=True, exist_ok=True)
        src = (HERE.parent / "templates" / "integration_plugin_example.py").read_text(encoding="utf-8")
        (d / "myissues.py").write_text(src, encoding="utf-8")
        m = self.serve({("GET", "/api/requirements/REQ-1"): {"title": "导出 Excel", "state": "开发中", "content": "列表页加导出"}})
        self.add_tool("mine", {"type": "myissues", "url": m.url, "auth": {"type": "bearer", "token_env": "JIRA_TOKEN"}})
        rc, out = run(["issue", "get", "REQ-1", "--repo", str(self.repo)])
        self.assertEqual(rc, 0, out)
        self.assertIn("导出 Excel", out)
        self.assertIn("myissues", run(["int", "types", "--repo", str(self.repo)])[1])


class AdapterTest(IntegrationBase):
    def test_jira_issue_search_and_writes_are_dry_run_by_default(self):
        m = self.serve({
            ("GET", "/rest/api/2/issue/OA-7"): JIRA_ISSUE,
            ("GET", "/rest/api/2/search"): lambda r: (200, {"issues": [JIRA_ISSUE], "jql": r["query"]["jql"]}),
            ("POST", "/rest/api/2/issue/OA-7/comment"): (201, {"id": "1001"}),
            ("GET", "/rest/api/2/issue/OA-7/transitions"): {"transitions": [{"id": "31", "name": "开始处理", "to": {"name": "处理中"}}]},
            ("POST", "/rest/api/2/issue/OA-7/transitions"): (204, ""),
        })
        self.add_tool("jira", {"type": "jira", "url": m.url, "project": "OA", "auth": {"type": "basic", "user": "li", "password_env": "JIRA_TOKEN"}})
        rc, out = run(["issue", "get", "OA-7", "--repo", str(self.repo)])
        self.assertIn("驳回原因", out)
        self.assertIn("老数据", out)
        self.assertEqual(m.calls[0]["headers"]["Authorization"], "Basic " + base64.b64encode(b"li:s3cret").decode())
        run(["issue", "search", "驳回", "--repo", str(self.repo)])
        self.assertIn('project = "OA"', m.calls[-1]["query"]["jql"])
        self.assertIn('text ~ "驳回"', m.calls[-1]["query"]["jql"])
        rc, out = run(["issue", "comment", "OA-7", "已定位到", "ExpenseService.audit", "--repo", str(self.repo)])
        self.assertIn("演练", out)
        self.assertEqual(m.writes(), [])
        rc, out = run(["issue", "comment", "OA-7", "已定位", "--confirm", "--repo", str(self.repo)])
        self.assertEqual(m.writes()[-1]["body"], {"body": "已定位"})
        rc, out = run(["issue", "transition", "OA-7", "处理中", "--confirm", "--repo", str(self.repo)])
        self.assertEqual(m.writes()[-1]["body"], {"transition": {"id": "31"}})
        rc, out = run(["issue", "transition", "OA-7", "已关闭", "--confirm", "--repo", str(self.repo)])
        self.assertEqual(rc, 2)
        self.assertIn("开始处理", out)
        acts = (self.repo / ".tmh" / "activity.jsonl").read_text(encoding="utf-8")
        self.assertIn("在 OA-7 评论", acts)

    def test_readonly_instance_refuses_confirmed_writes(self):
        m = self.serve({("POST", "/rest/api/2/issue/OA-7/comment"): (201, {"id": "1"})})
        self.add_tool("jira", {"type": "jira", "url": m.url, "readonly": True, "auth": {"type": "bearer", "token_env": "JIRA_TOKEN"}})
        rc, out = run(["issue", "comment", "OA-7", "x", "--confirm", "--repo", str(self.repo)])
        self.assertEqual(rc, 2)
        self.assertIn("只读", out)
        self.assertEqual(m.writes(), [])

    def test_zentao_token_login_and_bug(self):
        m = self.serve({
            ("POST", "/api.php/v1/tokens"): (201, {"token": "tk1"}),
            ("GET", "/api.php/v1/bugs/12"): lambda r: (200 if r["headers"].get("Token") == "tk1" else 401,
                                                      {"id": 12, "title": "请假列表分页错乱", "status": "active", "pri": 2,
                                                       "steps": "<p>第二页<b>重复</b>数据</p>", "openedBy": {"realname": "测试"},
                                                       "actions": [{"actor": "dev", "date": "2026-10-01", "comment": "<p>Oracle ROWNUM</p>"}]}),
        })
        self.add_tool("zentao", {"type": "zentao", "url": m.url, "auth": {"type": "zentao", "account": "li", "password_env": "ZENTAO_PASSWORD"}})
        i = I.pick(self.repo, "issues").get_issue("bug-12")
        self.assertEqual((i.key, i.type, i.reporter), ("bug-12", "缺陷", "测试"))
        self.assertEqual(i.description, "第二页重复数据")
        self.assertEqual(i.comments[0]["body"], "Oracle ROWNUM")
        self.assertEqual(m.calls[0]["body"], {"account": "li", "password": "zp"})

    def test_gitlab_mr_files_map_to_flows(self):
        self.kb()
        p = "/api/v4/projects/oa%2Foa-web"
        m = self.serve({
            ("GET", p + "/merge_requests"): [{"iid": 3, "title": "报销审核驳回原因", "state": "opened", "source_branch": "feat/reason",
                                               "target_branch": "master", "author": {"name": "张三"}, "web_url": "http://gl/mr/3"}],
            ("GET", p + "/merge_requests/3"): {"iid": 3, "title": "报销审核驳回原因", "state": "opened", "web_url": "http://gl/mr/3"},
            ("GET", p + "/merge_requests/3/changes"): {"changes": [{"new_path": "src/main/java/com/acme/oa/service/ExpenseService.java"}]},
        })
        self.add_tool("gitlab", {"type": "gitlab", "url": m.url, "project": "oa/oa-web"})
        self.assertEqual(m.url and I.make(self.repo, "gitlab").http.auth["name"], "PRIVATE-TOKEN")
        rc, out = run(["change", "list", "--repo", str(self.repo)])
        self.assertIn("!3", out)
        self.assertEqual(m.calls[-1]["headers"]["Private-Token"], "gt")
        rc, out = run(["change", "get", "!3", "--repo", str(self.repo)])
        self.assertIn("涉及业务流", out)
        self.assertIn("expense", out.lower())

    def test_sonar_issues_grouped_by_flow_and_gate(self):
        self.kb()
        m = self.serve({
            ("GET", "/api/issues/search"): {"paging": {"total": 2}, "issues": [
                {"key": "AX1", "rule": "java:S2077", "severity": "CRITICAL", "type": "VULNERABILITY", "line": 60,
                 "component": "oa:src/main/java/com/acme/oa/service/ExpenseService.java", "message": "SQL 拼接"},
                {"key": "AX2", "rule": "java:S106", "severity": "MINOR", "type": "CODE_SMELL", "line": 3,
                 "component": "oa:src/main/java/com/acme/oa/util/PasswordUtil.java", "message": "System.out"}]},
            ("GET", "/api/qualitygates/project_status"): {"projectStatus": {"status": "ERROR", "conditions": [
                {"status": "ERROR", "metricKey": "new_coverage", "actualValue": "41", "errorThreshold": "80"}]}},
        })
        self.add_tool("sonar", {"type": "sonarqube", "url": m.url, "project": "oa", "auth": {"type": "bearer", "token_env": "SONAR_TOKEN"}})
        rc, out = run(["quality", "--repo", str(self.repo)])
        self.assertEqual(rc, 0, out)
        self.assertIn("SQL 拼接", out)
        self.assertIn("不在任何业务流上", out)
        first_group = out.split("## ")[1]
        self.assertIn("ExpenseService.java:60", first_group)
        rc, out = run(["quality", "--gate", "--repo", str(self.repo)])
        self.assertIn("new_coverage", out)

    def test_confluence_search_and_get(self):
        m = self.serve({
            ("GET", "/rest/api/content/search"): {"results": [{"id": "88", "title": "报销流程说明", "excerpt": "财务<b>审核</b>",
                                                               "_links": {"webui": "/pages/88"}, "space": {"key": "OA"}}]},
            ("GET", "/rest/api/content/88"): {"id": "88", "title": "报销流程说明", "body": {"storage": {"value": "<p>审核通过后进入<b>待付款</b></p>"}}},
        })
        self.add_tool("wiki", {"type": "confluence", "url": m.url, "space": "OA", "auth": {"type": "bearer", "token_env": "WIKI_TOKEN"}})
        rc, out = run(["doc", "search", "报销", "--repo", str(self.repo)])
        self.assertIn("报销流程说明", out)
        self.assertIn('space="OA"', m.calls[-1]["query"]["cql"])
        rc, out = run(["doc", "get", "88", "--repo", str(self.repo)])
        self.assertIn("审核通过后进入待付款", out)

    def test_dingtalk_needs_env_signs_and_dry_runs(self):
        m = self.serve({("POST", "/robot/send"): {"errcode": 0}})
        self.add_tool("group", {"type": "dingtalk", "webhook_env": "DING_HOOK", "secret_env": "DING_SECRET"})
        rc, out = run(["notify", "构建失败", "oa-web #12", "--repo", str(self.repo)])
        self.assertEqual(rc, 2)
        self.assertIn("DING_HOOK", out)
        with mock.patch.dict(os.environ, {"DING_HOOK": m.url + "/robot/send?access_token=abc", "DING_SECRET": "SEC"}):
            rc, out = run(["notify", "构建失败", "oa-web #12", "--repo", str(self.repo)])
            self.assertIn("演练", out)
            self.assertNotIn("access_token=abc", out)
            self.assertEqual(m.writes(), [])
            rc, out = run(["notify", "构建失败", "oa-web #12", "--confirm", "--repo", str(self.repo)])
            self.assertEqual(rc, 0, out)
            w = m.writes()[-1]
            self.assertEqual(w["body"]["msgtype"], "markdown")
            self.assertIn("sign", w["query"])
            self.assertIn("timestamp", w["query"])

    def test_generic_adapter_maps_tapd_like_api(self):
        m = self.serve({
            ("GET", "/bugs"): lambda r: (200, {"status": 1, "data": [{"Bug": {"id": r["query"].get("id", "1"), "title": "导出乱码", "status": "new",
                                                                              "description": "GBK"}}]}),
        })
        conf = {"type": "generic", "url": m.url, "auth": {"type": "basic", "user": "api", "password_env": "TAPD_PASSWORD"},
                "issues": {
                    "get": {"path": "/bugs", "params": {"workspace_id": "9", "id": "{key}"}, "root": "data.0.Bug",
                            "map": {"key": "id", "title": "title", "status": "status", "description": "description",
                                    "url": "https://www.tapd.cn/9/bugtrace/bugs/view?bug_id={id}"}},
                    "search": {"path": "/bugs", "params": {"workspace_id": "9", "title": "{query}", "limit": "{limit}"}, "root": "data", "item": "Bug",
                               "map": {"key": "id", "title": "title", "status": "status"}}}}
        self.add_tool("tapd", conf)
        inst = I.pick(self.repo, "issues")
        self.assertEqual(inst.CAPABILITIES, ("issues",))
        i = inst.get_issue("1001")
        self.assertEqual((i.key, i.title, i.url), ("1001", "导出乱码", "https://www.tapd.cn/9/bugtrace/bugs/view?bug_id=1001"))
        rows = inst.search_issues("导出", 5)
        self.assertEqual(rows[0].title, "导出乱码")
        self.assertEqual(m.calls[-1]["query"]["limit"], "5")


class KnowledgeLinkTest(IntegrationBase):
    LOG = """[INFO] Building oa-web
[ERROR] Tests run: 3, Failures: 1, Errors: 0
java.lang.IllegalStateException: 预算不足
\tat com.acme.oa.service.ExpenseService.audit(ExpenseService.java:60)
\tat com.acme.oa.controller.ExpenseController.audit(ExpenseController.java:40)
\tat org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:897)
[ERROR] /work/oa/src/main/java/com/acme/oa/service/LeaveService.java:[40,9] cannot find symbol
BUILD FAILURE
"""

    def jenkins(self):
        return self.serve({
            ("GET", "/job/oa/job/oa-web/api/json"): {"builds": [
                {"number": 12, "result": "FAILURE", "building": False, "timestamp": 1790000000000, "duration": 81000, "url": "http://ci/12/",
                 "actions": [{"causes": [{"shortDescription": "由 GitLab push 触发"}]}, {"lastBuiltRevision": {"SHA1": "abcdef1234567", "branch": [{"name": "origin/master"}]}}]},
                {"number": 11, "result": "SUCCESS", "building": False, "timestamp": 1789990000000, "duration": 75000, "url": "http://ci/11/"}]},
            ("GET", "/job/oa/job/oa-web/lastFailedBuild/api/json"): {"number": 12, "result": "FAILURE", "url": "http://ci/12/"},
            ("GET", "/job/oa/job/oa-web/12/consoleText"): self.LOG,
            ("GET", "/crumbIssuer/api/json"): {"crumbRequestField": "Jenkins-Crumb", "crumb": "c1"},
            ("POST", "/job/oa/job/oa-web/buildWithParameters"): (201, ""),
        })

    def test_build_failure_maps_stack_and_compile_errors_to_flows(self):
        self.kb()
        m = self.jenkins()
        self.add_tool("ci", {"type": "jenkins", "url": m.url, "job": "oa/oa-web", "auth": {"type": "basic", "user": "li", "password_env": "JENKINS_TOKEN"}})
        rc, out = run(["build", "status", "--repo", str(self.repo)])
        self.assertIn("#12", out)
        self.assertIn("failed", out)
        self.assertIn("abcdef12", out)
        rc, out = run(["build", "failure", "--json", "--repo", str(self.repo)])
        self.assertEqual(rc, 0, out)
        r = json.loads(out)
        files = {(x["file"], x["line"]) for x in r["locations"]}
        self.assertIn(("src/main/java/com/acme/oa/service/ExpenseService.java", 60), files)
        self.assertIn(("src/main/java/com/acme/oa/service/LeaveService.java", 40), files)
        self.assertFalse(any("FrameworkServlet" in x["file"] for x in r["locations"]))
        audit = [x for x in r["locations"] if x["line"] == 60][0]
        self.assertEqual(audit["method"], "ExpenseService.audit")
        self.assertTrue(audit["flows"])
        self.assertTrue(r["flows"])
        self.assertTrue(any("预算不足" in e or "BUILD FAILURE" in e for e in r["errors"]))

    def test_trigger_uses_crumb_only_when_confirmed(self):
        m = self.jenkins()
        self.add_tool("ci", {"type": "jenkins", "url": m.url, "job": "oa/oa-web", "auth": {"type": "basic", "user": "li", "password_env": "JENKINS_TOKEN"}})
        rc, out = run(["build", "trigger", "--param", "ENV=test", "--repo", str(self.repo)])
        self.assertIn("演练", out)
        self.assertEqual(m.writes(), [])
        rc, out = run(["build", "trigger", "--param", "ENV=test", "--confirm", "--repo", str(self.repo)])
        self.assertEqual(rc, 0, out)
        w = m.writes()[-1]
        self.assertEqual(w["headers"]["Jenkins-Crumb"], "c1")
        self.assertEqual(w["query"], {"ENV": "test"})

    def test_ticket_brief_and_task_contract(self):
        self.kb()
        m = self.serve({("GET", "/rest/api/2/issue/OA-7"): JIRA_ISSUE})
        self.add_tool("jira", {"type": "jira", "url": m.url, "auth": {"type": "bearer", "token_env": "JIRA_TOKEN"}})
        rc, out = run(["ticket", "OA-7", "--repo", str(self.repo)])
        self.assertEqual(rc, 0, out)
        self.assertIn("报销审核增加驳回原因必填", out)
        self.assertIn("知识库", out)
        self.assertIn("expense", out.lower())
        rc, out = run(["ticket", "OA-7", "--task", "--repo", str(self.repo)])
        p = next((self.repo / ".tmh" / "tasks").glob("T001-*.md"))
        text = p.read_text(encoding="utf-8")
        self.assertIn("- 工单：OA-7", text)
        self.assertIn(m.url + "/browse/OA-7", text)
        self.assertIn("驳回必须填写原因", text)
        self.assertIn("知识库给出的相关内容", text)
        self.assertIn("新需求", text)

    def test_trace_ticket_key_through_git(self):
        self.kb()
        f = self.repo / "src/main/java/com/acme/oa/service/ExpenseService.java"
        f.write_text(f.read_text(encoding="utf-8") + "\n// reason\n", encoding="utf-8")
        g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=self.repo, check=True, capture_output=True)
        g("commit", "-qam", "OA-7 驳回原因必填")
        rc, out = run(["trace", "OA-7", "--json", "--repo", str(self.repo)])
        r = json.loads(out)
        self.assertEqual(len(r["commits"]), 1)
        self.assertIn("src/main/java/com/acme/oa/service/ExpenseService.java", r["files"])
        self.assertTrue(r["flows"])


class McpAndInstallTest(IntegrationBase):
    def rpc(self, *msgs):
        from tmh.mcp import serve
        inp = io.StringIO("\n".join(json.dumps(m) for m in msgs) + "\n")
        out = io.StringIO()
        serve(self.repo, inp, out)
        return [json.loads(l) for l in out.getvalue().splitlines()]

    def test_mcp_lists_tools_by_capability_and_guards_writes(self):
        m = self.serve({("GET", "/rest/api/2/issue/OA-7"): JIRA_ISSUE, ("POST", "/rest/api/2/issue/OA-7/comment"): (201, {"id": "9"})})
        r = self.rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
                     {"jsonrpc": "2.0", "method": "notifications/initialized"},
                     {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0]["result"]["protocolVersion"], "2025-03-26")
        names = {t["name"] for t in r[1]["result"]["tools"]}
        self.assertIn("context", names)
        self.assertNotIn("issue_get", names)
        self.add_tool("jira", {"type": "jira", "url": m.url, "auth": {"type": "bearer", "token_env": "JIRA_TOKEN"}})
        r = self.rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
                     {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "issue_get", "arguments": {"key": "OA-7"}}},
                     {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "issue_comment", "arguments": {"key": "OA-7", "body": "hi", "confirm": True}}},
                     {"jsonrpc": "2.0", "id": 6, "method": "nope"})
        self.assertIn("issue_get", {t["name"] for t in r[0]["result"]["tools"]})
        self.assertNotIn("build_status", {t["name"] for t in r[0]["result"]["tools"]})
        self.assertIn("驳回原因", r[1]["result"]["content"][0]["text"])
        self.assertFalse(r[1]["result"]["isError"])
        self.assertIn("agent_writes=false", r[2]["result"]["content"][0]["text"])
        self.assertEqual(m.writes(), [])
        self.assertEqual(r[3]["error"]["code"], -32601)
        cfg = cfgmod.load(self.repo)
        cfg["integrations"]["agent_writes"] = True
        cfgmod.save(self.repo, cfg)
        self.rpc({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "issue_comment", "arguments": {"key": "OA-7", "body": "hi", "confirm": True}}})
        self.assertEqual(m.writes()[-1]["body"], {"body": "hi"})

    def test_mcp_subprocess_roundtrip(self):
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "integrations", "arguments": {}}}]
        p = subprocess.run([sys.executable, "-m", "tmh", "mcp", "--repo", str(self.repo)], cwd=str(HERE.parent),
                           input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, timeout=60)
        lines = [json.loads(l) for l in p.stdout.splitlines()]
        self.assertEqual(lines[0]["result"]["serverInfo"]["name"], "tmh")
        self.assertIn("还没有接入", lines[1]["result"]["content"][0]["text"])

    def test_install_writes_mcp_configs_with_env_passthrough(self):
        from tmh import install
        install.install(self.repo, ["claude", "codex"])
        mcp = json.loads((self.repo / ".mcp.json").read_text())
        self.assertIn("tmh.py mcp", mcp["mcpServers"]["tmh"]["args"][1])
        st = json.loads((self.repo / ".claude" / "settings.json").read_text())
        self.assertIn("tmh", st["enabledMcpjsonServers"])
        toml = (self.repo / ".codex" / "config.toml").read_text()
        self.assertIn("[mcp_servers.tmh]", toml)
        self.assertIn("env_vars = []", toml)
        self.assertTrue((self.repo / ".tmh" / "integrations" / "_example.py").exists())
        rc, out = run(["int", "add", "jira", "--type", "jira", "--url", "https://j", "--token-env", "JIRA_TOKEN", "--repo", str(self.repo)])
        toml = (self.repo / ".codex" / "config.toml").read_text()
        self.assertIn('env_vars = ["JIRA_TOKEN"]', toml)
        self.assertEqual(toml.count("[mcp_servers.tmh]"), 1)
        if sys.version_info >= (3, 11):
            import tomllib
            self.assertEqual(tomllib.loads(toml)["mcp_servers"]["tmh"]["command"], "sh")
        # vendored copy runs the server too
        p = subprocess.run([sys.executable, str(self.repo / ".tmh" / "tool" / "tmh.py"), "mcp", "--repo", str(self.repo)],
                           input=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n", capture_output=True, text=True, timeout=60)
        self.assertIn("issue_get", p.stdout)


if __name__ == "__main__":
    unittest.main()
