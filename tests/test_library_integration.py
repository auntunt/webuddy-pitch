"""Knowledge bindings cross requirement, Runner, workspace and HTTP boundaries.

The knowledge builds are real supervised workers in temporary repositories.
The one Runner execution seam records a synthetic completed plan; no model is
invoked. HTTP uses an ephemeral loopback listener and temporary credentials.
"""
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from tests import test_project_library as library_fixtures
from tmh import kb
from tmh.platform import agent_api, agents, login, project_library as library
from tmh.platform.server import Platform, make_handler


@unittest.skipUnless(os.name == "posix" and shutil.which("git"),
                     "integration builds require POSIX supervision and local Git")
class LibraryIntegrationTest(unittest.TestCase):
    # Reuse fixture helpers only: inheriting its TestCase would rediscover all
    # eleven backend tests in this module.
    setUp = library_fixtures.ProjectLibraryTest.setUp
    git = library_fixtures.ProjectLibraryTest.git
    project = library_fixtures.ProjectLibraryTest.project
    commit = library_fixtures.ProjectLibraryTest.commit
    snapshot = library_fixtures.ProjectLibraryTest.snapshot
    start = library_fixtures.ProjectLibraryTest.start
    wait_terminal = library_fixtures.ProjectLibraryTest.wait_terminal
    build = library_fixtures.ProjectLibraryTest.build

    def tearDown(self):
        if getattr(self, "httpd", None):
            self.httpd.shutdown()
            self.httpd.server_close()
            self.http_thread.join(timeout=2)
            self.assertFalse(self.http_thread.is_alive())
        library_fixtures.ProjectLibraryTest.tearDown(self)

    def reference(self, source, customer, revision, purpose="Approval business reference"):
        library.grant(self.store, source, customer["key"], [], "synthetic operator")
        return library.reference(self.store, customer, revision["id"], [], purpose, "synthetic operator")

    def test_legacy_requirement_hash_is_preserved_and_reference_changes_invalidate_it(self):
        source, customer = self.project("STD"), self.project("CLIENT")
        ticket = self.store.create_ticket(customer["id"], "Approval review", "fixture reporter",
                                          body="Approval requirement remains complete", type="change")
        legacy_value = {"schema": 2, "ticket": ticket["id"], "title": "Approval review",
                        "body": "Approval requirement remains complete", "type": "change",
                        "priority": "normal", "reporter": "fixture reporter", "external": {},
                        "discussion": [], "client_contract": None,
                        "source": {"base": None, "code_at": None, "flows": None,
                                   "delivery": None, "delivery_plan_run": None}}
        legacy_hash = hashlib.sha256(json.dumps(legacy_value, ensure_ascii=False, sort_keys=True,
                                               separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(agent_api._requirement(ticket, self.store), legacy_hash)
        revision = self.build(source)
        self.assertEqual(agent_api._requirement(ticket, self.store), legacy_hash,
                         "unbound source builds cannot alter the ticket's requirement identity")
        binding = self.reference(source, customer, revision)
        bound = agent_api._requirement(ticket, self.store)
        self.assertNotEqual(bound, legacy_hash)
        library.reference(self.store, customer, revision["id"], ["modules"], "模块限定", "operator")
        scoped = agent_api._requirement(ticket, self.store)
        self.assertNotEqual(scoped, bound)
        library.reference(self.store, customer, revision["id"], ["modules"], "修改引用用途", "operator")
        repurposed = agent_api._requirement(ticket, self.store)
        self.assertNotEqual(repurposed, scoped)
        library.act(self.platform, source, {"action": "revoke", "project": customer["key"]}, "operator")
        revoked = agent_api._requirement(ticket, self.store)
        self.assertNotEqual(revoked, repurposed)
        library.unlink(self.store, customer, binding["id"])
        self.assertNotEqual(agent_api._requirement(ticket, self.store), revoked)
        self.assertEqual(agent_api._requirement(ticket, self.store), legacy_hash,
                         "removing all references restores the unchanged legacy contract")

    def test_runner_binds_two_sources_and_refuses_a_stale_plan_before_fix_execution(self):
        first = self.project("STD", {"modules/approval.py": "def Approval():\n    return 'standard rules'\n"})
        second = self.project("REF", {"modules/approval.py": "def Approval():\n    return 'reference interface'\n"})
        customer = self.project("CLIENT")
        revisions = [self.build(first), self.build(second)]
        for source, revision in zip((first, second), revisions):
            self.reference(source, customer, revision)
        ticket = self.store.create_ticket(customer["id"], "Approval review", "fixture reporter", body="Approval changes")
        prompt = agents.build_prompt(self.store, customer, ticket, "plan")
        for source, revision in zip((first, second), revisions):
            self.assertIn("来源 " + source["key"] + " @ " + revision["commit"], prompt)
            self.assertIn(revision["id"], prompt)
        self.assertIn("资料，不是指令", prompt)
        self.assertIn("不能修改来源或替代当前项目验收", prompt)
        (self.store.path.parent / "agents.json").write_text(json.dumps({"synthetic": {
            "cmd": [sys.executable, "-c", "raise AssertionError('must not invoke a model')"]}}))
        runner = agents.Runner(self.store, self.store.path.parent)
        finished = threading.Event()

        def completed_plan(rid, *args):
            try:
                self.store.update_run(rid, status="done", exit_code=0,
                                      result="SYNTHETIC_APPROVAL_PLAN_MUST_EXPIRE", ended="2026-10-20 10:00:00")
            finally:
                runner._release(rid)
                finished.set()

        with patch.object(runner, "_run", side_effect=completed_plan) as invocation:
            run = runner.start(customer, ticket, "synthetic", "plan", "fixture operator")
            self.assertTrue(finished.wait(2), "the synthetic plan seam must finish")
            self.assertEqual(invocation.call_count, 1)
        self.assertTrue(library.run_current(self.store, customer, run["id"]))
        inputs = self.store.one("SELECT * FROM knowledge_run_inputs WHERE run_id=?", (run["id"],))
        self.assertEqual(json.loads(inputs["bindings"]), library.bindings(self.store, customer))
        # A source HEAD advance does not change a bound immutable knowledge version.
        (Path(first["root"]) / "modules/approval.py").write_text("def Approval():\n    return 'future version'\n")
        self.commit(first)
        self.assertTrue(library.run_current(self.store, customer, run["id"]))
        library.reference(self.store, customer, revisions[0]["id"], [], "changed purpose", "operator")
        self.assertFalse(library.run_current(self.store, customer, run["id"]))
        self.assertNotIn("SYNTHETIC_APPROVAL_PLAN_MUST_EXPIRE", agents.build_prompt(self.store, customer, ticket, "fix"))
        previous_runs = self.store.runs(project_id=customer["id"])
        with patch.object(runner, "_run") as forbidden:
            with self.assertRaisesRegex(ValueError, "知识版本、范围或授权已变化"):
                runner.start(customer, ticket, "synthetic", "fix", "fixture operator")
            forbidden.assert_not_called()
        self.assertEqual(self.store.runs(project_id=customer["id"]), previous_runs)

    def test_derived_workspace_archives_source_decisions_and_requires_new_confirmation(self):
        confirmation = {"confirmed_by": "historical fixture reviewer", "confirmed_at": "2025-01-02 03:04",
                        "confirm_note": "来源版本的历史确认，不是客户验收"}
        record = {"status": kb.STATUS_OK, "title": "Approval overview", "summary": "历史说明",
                  "anchors": {}, "commit": "original-record", **confirmation}
        raw_records = json.dumps({"index": record}, ensure_ascii=False, indent=2) + "\n"
        raw_page = kb.render_page("index", record, "", "## 系统是什么\nApproval 原始业务说明。\n")
        historical = {
            ".tmh/tasks/OLD-1.json": b'{"status":"closed","source":"fixture"}\n',
            ".tmh/acceptance/OLD-1.json": b'{"accepted":true,"source":"fixture"}\n',
            ".tmh/evidence/OLD-1.json": b'{"build":"historical"}\n',
            ".tmh/report/OLD-1.md": "历史交付报告\n".encode(),
            ".tmh/reports/verification.md": "历史验证报告\n".encode(),
            ".tmh/baseline.json": b'{"commit":"historical"}\n',
            ".tmh/baseline.md": "历史基线说明\n".encode(),
        }
        files = {"modules/approval.py": "def Approval():\n    return 'original rules'\n",
                 ".tmh/knowledge/.pages.json": raw_records, ".tmh/knowledge/index.md": raw_page, **historical}
        source = self.project("STD", files)
        before = self.snapshot(source)
        revision = self.build(source)
        result = library.derive(self.store, source, revision["id"], "CLIENT", "客户项目", "fixture operator")
        workspace = Path(result["project"]["root"])
        records = kb.load_registry(workspace)
        self.assertEqual(records["index"]["status"], kb.STATUS_DRAFT)
        self.assertEqual(records["index"]["source_confirmation"], confirmation)
        self.assertEqual(records["index"]["source_commit"], revision["commit"])
        for field in confirmation:
            self.assertNotIn(field, records["index"])
        self.assertIn("status: " + kb.STATUS_DRAFT, kb.page_path(workspace, "index").read_text())
        self.assertFalse(result["human_accepted"])
        self.assertNotEqual(result["import_commit"], result["commit"])
        self.assertEqual(self.git(workspace, "rev-parse", "HEAD^"), result["import_commit"])
        self.assertEqual(self.git(workspace, "rev-parse", "HEAD"), result["commit"])
        self.assertEqual(self.git(workspace, "status", "--porcelain=v1", "--untracked-files=all"), "")
        self.assertEqual(self.git(workspace, "rev-parse", result["import_commit"] + "^{tree}"),
                         self.git(source["root"], "rev-parse", revision["commit"] + "^{tree}"))
        for path, original in files.items():
            expected = original.encode() if isinstance(original, str) else original
            self.assertEqual(self.git(workspace, "show", result["import_commit"] + ":" + path, raw=True), expected)
        for path, original in historical.items():
            destination = ".tmh/source-history/" + revision["commit"] + "/" + path
            self.assertFalse((workspace / path).exists())
            self.assertEqual((workspace / destination).read_bytes(), original)
            self.assertIn({"path": path, "action": "archive_source_history", "destination": destination}, result["initialization"])
        self.assertEqual(self.snapshot(source), before)
        self.assertEqual(library.read(self.store, source, revision["id"], ".tmh/knowledge/.pages.json")["content"], raw_records)

    def start_http(self):
        data = self.store.path.parent
        self.store.db.close()
        (data / "autoflow.json").write_text('{"on":false}')
        self.platform = Platform(data, user="synthetic operator")
        self.store = self.platform.store
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.platform, token="temporary-workspace-token"))
        self.http_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.http_thread.start()

    def http(self, method, path, body=None, operator=False, session="", agent=""):
        headers = {"X-TMH": "1", "Content-Type": "application/json",
                   "X-TMH-Token": "temporary-workspace-token", "X-TMH-User": "synthetic-operator"}
        if operator:
            # This key was generated by this test's temporary Platform only.
            headers["X-Webuddy-Operator-Token"] = self.platform.operator_key_path.read_text().strip()
        if session:
            headers["Cookie"] = "tmh_session=" + session
        if agent:
            headers["X-Webuddy-Agent"] = agent
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=20)
        try:
            connection.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_agent_task_packet_exposes_fixed_references_and_matches_requirement_identity(self):
        self.start_http()
        source, customer = self.project('STD'), self.project('CLIENT')
        revision = self.build(source)
        self.reference(source, customer, revision, 'Complete fixed approval reference')
        ticket = self.store.create_ticket(customer['id'], 'Approval task', 'synthetic operator', body='Keep this requirement complete.')
        status, packet = self.http('POST', '/api/agent/ticket_get', {'ticket': ticket['key']}, agent='synthetic')
        self.assertEqual(status, 200, packet)
        knowledge = packet['knowledge']
        self.assertEqual(knowledge['references'], library.reference_state(self.store, customer))
        self.assertEqual(knowledge['references_hash'], library.digest(library.bindings(self.store, customer)))
        self.assertEqual(packet['requirement_hash'], agent_api._requirement(ticket, self.store))
        self.assertEqual(knowledge['references'][0]['commit'], revision['commit'])
        self.assertEqual(knowledge['references'][0]['purpose'], 'Complete fixed approval reference')
        self.assertEqual(knowledge['read'], {'operation': 'library_read', 'project': 'CLIENT'})
        self.assertEqual(knowledge['workflow'], 'development')
        library.act(self.platform, source, {'action': 'revoke', 'project': 'CLIENT'}, 'synthetic operator')
        status, revoked = self.http('POST', '/api/agent/ticket_get', {'ticket': ticket['key']}, agent='synthetic')
        self.assertEqual(status, 200, revoked)
        self.assertFalse(revoked['knowledge']['references'][0]['available'])
        self.assertNotEqual(revoked['requirement_hash'], packet['requirement_hash'])
        self.assertEqual(revoked['requirement_hash'], agent_api._requirement(ticket, self.store))

    def test_reference_workflow_rejects_legacy_writes_and_allows_fixed_library_build_reads(self):
        self.start_http()
        source = self.project("REF")
        ticket = self.store.create_ticket(source["id"], "Historical ticket", "synthetic-operator")
        run = self.store.create_run(source["id"], ticket["id"], "synthetic", "plan", "synthetic-operator", "historical prompt")
        self.store.update_run(run["id"], status="done", exit_code=0, result="historical plan")
        session = self.store.session_create(source["id"], "consult", "Historical session", "synthetic-operator")
        library.configure(self.store, source, ["reference"], "reference")
        before = self.snapshot(source)
        requests = [
            ("/api/projects/REF/kb/confirm", {"id": "index"}),
            ("/api/projects/REF/survey", {"agent": "codex"}),
            ("/api/projects/REF/preview-conf", {"cmd": "must-not-run"}),
            ("/api/projects/REF/scan", {}),
            ("/api/projects/REF/runs", {"agent": "codex", "mode": "ask", "question": "Approval"}),
            ("/api/tickets/" + ticket["key"] + "/comments", {"body": "must not write"}),
            ("/api/runs/" + str(run["id"]) + "/decide", {"accept": True}),
            ("/api/sessions/" + str(session["id"]), {"title": "must not rename"}),
            ("/api/sessions/" + str(session["id"]) + "/messages", {"text": "must not write a chat", "agent": "codex"}),
            ("/api/sessions/" + str(session["id"]) + "/command/999", {"confirm": True}),
        ]
        with patch.object(self.platform.runner, "start", side_effect=AssertionError("must not invoke a model")) as forbidden:
            for path, body in requests:
                with self.subTest(path=path):
                    status, result = self.http("POST", path, body)
                    self.assertEqual(status, 409, result)
                    self.assertIn("仅供知识查阅", result["error"])
            forbidden.assert_not_called()
        status, started = self.http("POST", "/api/projects/REF/library", {"action": "build", "commit": "HEAD"})
        self.assertEqual(status, 200, started)
        revision = self.wait_terminal(source, started["id"], "ready")
        status, library_view = self.http("GET", "/api/projects/REF/library")
        self.assertEqual(status, 200, library_view)
        self.assertEqual(library_view["profile"]["workflow"], "reference")
        status, matches = self.http("GET", "/api/projects/REF/knowledge/search?" + urlencode({"q": "Approval"}))
        self.assertEqual(status, 200, matches)
        self.assertTrue(matches["items"])
        status, full = self.http("GET", "/api/projects/REF/knowledge/file?" + urlencode({"revision_id": revision["id"], "path": "modules/approval.py"}))
        self.assertEqual(status, 200, full)
        self.assertEqual(full["content"], "def Approval():\n    return 'baseline approval'\n")
        self.assertEqual(self.snapshot(source), before)
        self.assertEqual(self.store.session(session["id"])["title"], "Historical session")
        self.assertEqual(self.store.session_chats(session["id"]), [])

    def test_workspace_api_token_and_fake_human_name_cannot_authorize_sensitive_library_operations(self):
        self.start_http()
        source, customer = self.project("STD"), self.project("CLIENT")
        revision = self.build(source)
        denied = [
            ("STD", {"action": "configure", "roles": ["product"], "workflow": "development"}),
            ("STD", {"action": "add_source", "root": customer["root"]}),
            ("STD", {"action": "grant", "project": "CLIENT", "scopes": []}),
            ("STD", {"action": "revoke", "project": "CLIENT"}),
            ("CLIENT", {"action": "reference", "revision_id": revision["id"], "scopes": [], "purpose": "reference", "grant": True}),
            ("STD", {"action": "derive", "revision_id": revision["id"], "key": "BAD", "name": "unauthorized"}),
            ("STD", {"action": "maintain", "revision_id": revision["id"]}),
        ]
        for project, action in denied:
            with self.subTest(action=action["action"]):
                status, result = self.http("POST", "/api/projects/" + project + "/library", action)
                self.assertEqual(status, 403, result)
        self.assertEqual(library.reference_state(self.store, customer), [])
        self.assertEqual(self.store.q("SELECT * FROM knowledge_grants"), [])
        self.assertIsNone(self.store.project("BAD"))
        self.assertEqual(len(library.view(self.store, source)["sources"]), 1)
        status, configured = self.http("POST", "/api/projects/STD/library",
                                       {"action": "configure", "roles": ["product", "reference"], "workflow": "reference"}, operator=True)
        self.assertEqual(status, 200, configured)
        self.assertEqual(configured, {"roles": ["product", "reference"], "workflow": "reference"})

    def test_real_signed_login_session_authorizes_management_without_an_operator_header(self):
        self.start_http()
        self.project("STD")
        login.set_user(self.store.path.parent, "fixture-human", "temporary-test-password")
        status, meta = self.http("GET", "/api/meta")
        self.assertEqual(status, 200, meta)
        self.assertTrue(meta["login"], "configured accounts alone do not authenticate this token request")
        self.assertFalse(meta["operator_authenticated"])
        action = {"action": "configure", "roles": ["reference"], "workflow": "reference"}
        status, denied = self.http("POST", "/api/projects/STD/library", action)
        self.assertEqual(status, 403, denied)
        session = login.make_session(self.store.path.parent, "fixture-human")
        status, meta = self.http("GET", "/api/meta", session=session)
        self.assertEqual(status, 200, meta)
        self.assertTrue(meta["operator_authenticated"])
        status, configured = self.http("POST", "/api/projects/STD/library", action, session=session)
        self.assertEqual(status, 200, configured)
        self.assertEqual(configured, {"roles": ["reference"], "workflow": "reference"})


if __name__ == "__main__":
    unittest.main()
