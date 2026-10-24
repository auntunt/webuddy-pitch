"""Learning HTTP route contracts with real requests and a real temporary Store.

The outer HTTP login/cookie machinery has its own tests. These tests start at
Req, where _who is the server-authenticated identity and display headers remain
untrusted. Model launches are mocked; this suite makes no model-quality claim.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.sqlite_snapshot import dump_store
from tmh import kb
from tmh.platform import learning as L, learning_decisions as D, learning_runs as R
from tmh.platform import server
from tmh.platform.errors import ApiError
from tmh.platform.store import Store, now


class LearningAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-learning-api-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.data = self.home / "runtime"
        self.store = Store(self.data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.root = self.home / "repo"
        self.root.mkdir()
        self.other_root = self.home / "other"
        self.other_root.mkdir()
        self.p = self.store.add_project("APP", "测试项目", str(self.root))
        self.other = self.store.add_project("OTHER", "另一个项目", str(self.other_root))
        self.page = self.root / ".tmh" / "knowledge" / "index.md"
        self.page.parent.mkdir(parents=True)
        self.body = ("---\nid: index\ntitle: 项目知识\nstatus: 已确认\n---\n"
                     "# 项目知识\n\n状态是 OPEN，依据 `app.py:1`。\n" + "保留完整业务说明。" * 700)
        self.page.write_text(self.body, encoding="utf-8")
        (self.root / "app.py").write_text('STATUS = "OPEN"\n', encoding="utf-8")
        kb.save_registry(self.root, {"index": {"status": kb.STATUS_OK, "title": "项目知识",
                                               "confirmed_by": "原始确认人", "confirmed_at": "2026-10-01",
                                               "confirm_note": "原始确认说明"}})

    def request(self, body=None, query=None, *, who="", headers=None, display="伪造显示名"):
        return server.Req(SimpleNamespace(_who=who, headers=dict(headers or {})),
                          query or {}, body, display)

    def read(self, **query):
        return server.api_learning(self.P, self.request(query={k: [v] for k, v in query.items()}))

    def post(self, action, *, who="alice", headers=None, project="APP", **body):
        return server.api_learning_action(self.P, self.request(
            body={"action": action, "project": project, **body}, who=who, headers=headers))

    def capture(self, *, who="alice", headers=None):
        item = self.read(project="APP", kind="fact")["items"][0]
        return self.post("capture", who=who, headers=headers, key=item["key"],
                         expected_fingerprint=item["fingerprint"])

    def files(self):
        return {str(p.relative_to(self.home)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.home.rglob("*") if p.is_file()}

    def snapshot(self):
        return dump_store(self.store), self.files()

    def assert_error(self, code, call):
        with self.assertRaises(ApiError) as caught:
            call()
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception

    def recorded_job(self, revision, *, status="failed", jid=None):
        """A deliberately failed receipt fixture; no synthetic pass is adopted."""
        jid = jid or "api-job-" + revision["id"]
        with L.transaction(self.store) as db:
            db.execute("""INSERT INTO learning_jobs
                (id,project_id,kind,revision_id,current_revision_id,request_id,request_hash,
                 actor,status,options,binding,created,deadline,result,error)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (jid, self.p["id"], "review", revision["id"], revision["id"], jid,
                        "fixture-hash", "agent:reviewer", status, "{}", L.encoded(revision["source"]["binding"]),
                        now(), 0, '{"passed":false}', "合成入口测试回执，未执行模型"))
        return jid

    def recorded_decision(self, revision):
        did = "api-decision-" + revision["id"]
        with L.transaction(self.store) as db:
            db.execute("""INSERT INTO learning_decisions
                (id,project_id,kind,origin_id,revision_id,action,actor,request_id,payload,status,created)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                       (did, self.p["id"], "fact", "index", revision["id"], "adopt", "alice", did,
                        L.encoded({"request": {"reason": "完整人工理由", "expected_active": None},
                                   "content": revision["content"], "source": revision["source"]}),
                        "pending", now()))
        return did

    def test_catalog_get_is_pure_and_preserves_legacy_confirmation(self):
        before = self.snapshot()
        with patch.object(L, "schema") as core_schema, patch.object(R, "schema") as run_schema, \
                patch.object(R, "start") as launch, patch.object(R, "recover") as recover, \
                patch.object(D, "project_decision") as project:
            result = self.read(project="APP", kind="fact", q="项目知识")
            self.assertEqual(result["items"][0]["content"], self.body)
            self.assertEqual(result["items"][0]["human"]["status"], "已确认")
            self.assertEqual(result["items"][0]["machine"]["status"], "unreviewed")
            self.assertEqual(result["items"][0]["revision_id"], "")
            self.assertIsNone(result["items"][0]["active_revision_id"])
            self.assertTrue(result["readonly"])
            self.assertEqual(self.read(project="OTHER")["items"], [])
            for operation in (core_schema, run_schema, launch, recover, project):
                operation.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_get_does_not_recreate_missing_run_schema(self):
        revision = self.capture()
        with L.transaction(self.store) as db:
            for table in ("learning_steps", "learning_rounds", "learning_jobs"):
                db.execute("DROP TABLE " + table)
        before = self.snapshot()
        with patch.object(L, "schema") as core_schema, patch.object(R, "schema") as run_schema:
            self.assertEqual(self.read(project="APP")["jobs"], [])
            self.assertEqual(self.read(project="APP", revision=revision["id"])["jobs"], [])
            core_schema.assert_not_called()
            run_schema.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_query_repetition_is_rejected_without_side_effects(self):
        before = self.snapshot()
        for key in ("project", "revision", "job", "kind", "q", "unexpected"):
            with self.subTest(key=key):
                query = {"project": ["APP"], key: ["APP", "OTHER"]}
                self.assert_error(400, lambda: server.api_learning(self.P, self.request(query=query)))
        self.assert_error(400, lambda: server.api_learning(self.P, self.request(query={"project": []})))
        self.assertEqual(self.snapshot(), before)

    def test_cross_project_and_missing_revisions_are_404_before_execution(self):
        revision = self.capture()
        before = self.snapshot()
        with patch.object(R, "_configuration") as config, patch.object(R, "_launch") as launch:
            for rid in (revision["id"], "missing-revision"):
                with self.subTest(revision=rid):
                    self.assert_error(404, lambda: self.read(project="OTHER", revision=rid))
                    self.assert_error(404, lambda: self.post("propose", project="OTHER", revision_id=rid,
                                                             content=self.body + "\n修订正文"))
                    for kind in ("review", "evaluate"):
                        self.assert_error(404, lambda: self.post(kind, project="OTHER", revision_id=rid,
                                                               request_id="cross-" + kind))
            config.assert_not_called()
            launch.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_cross_project_and_missing_jobs_are_404_without_mutation(self):
        jid = self.recorded_job(self.capture(), status="queued")
        before = self.snapshot()
        with patch.object(R, "_launch") as launch:
            for job_id in (jid, "missing-job"):
                with self.subTest(job=job_id):
                    self.assert_error(404, lambda: self.read(project="OTHER", job=job_id))
                    for action in ("cancel", "resume"):
                        self.assert_error(404, lambda: self.post(action, project="OTHER", job_id=job_id))
            launch.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_detail_and_job_get_return_complete_outputs_and_never_recover(self):
        revision = self.capture()
        jid = self.recorded_job(revision)
        did = self.recorded_decision(revision)
        output = "完整结果开始\n" + "所有正文均保留。\n" * 4096 + "\n完整结果结束"
        raw = "stdout 开始\n" + "独立进程原始事件\n" * 4096 + "\nstdout 结束"
        prompt, error = "完整提示词\n" + self.body, "完整错误\n" + "诊断。" * 2000
        with L.transaction(self.store) as db:
            db.execute("""INSERT INTO learning_steps
                (job_id,seq,role,prompt,prompt_hash,status,output,raw_output,error,created)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       (jid, 1, "review:0", prompt, "fixture", "failed", output, raw, error, now()))
        before = self.snapshot()
        with patch.object(R, "_launch") as launch, patch.object(R, "recover") as recover, \
                patch.object(D, "project_decision") as project:
            detail = self.read(project="APP", revision=revision["id"])
            direct = self.read(project="APP", job=jid)
            self.assertEqual(detail["decisions"][0]["id"], did)
            self.assertEqual(detail["decisions"][0]["status"], "pending")
            self.assertEqual(detail["decisions"][0]["payload"]["content"], revision["content"])
            for job in (detail["jobs"][0], direct):
                # Also exercise the same lossless JSON representation sent by HTTP.
                step = json.loads(json.dumps(job, ensure_ascii=False))["steps"][0]
                self.assertEqual(step["output"], output)
                self.assertEqual(step["raw_output"], raw)
                self.assertEqual(step["prompt"], prompt)
                self.assertEqual(step["error"], error)
                self.assertIsNone(step["usage"])
                self.assertEqual(job["cost"], {"amount": None, "currency": None, "status": "unknown"})
            launch.assert_not_called()
            recover.assert_not_called()
            project.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_agent_capture_and_propose_are_audited_without_implicit_adoption(self):
        original_files = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        headers = {"X-Webuddy-Agent": "reviewer", "X-TMH-User": "假冒人工", "X-Webuddy-User": "假冒人工"}
        with patch.object(R, "start") as start, patch.object(D, "decide") as decide, \
                patch.object(D, "project_decision") as project:
            revision = self.capture(who="alice", headers=headers)
            proposal = self.post("propose", who="alice", headers=headers, revision_id=revision["id"],
                                 content=self.body + "\n待审修订的完整正文。", actor="假冒人工")
            self.assertEqual(revision["author"], "agent:reviewer")
            self.assertEqual(proposal["author"], "agent:reviewer")
            self.assertEqual(proposal["parent_id"], revision["id"])
            self.assertEqual(proposal["content"], self.body + "\n待审修订的完整正文。")
            detail = self.read(project="APP", revision=proposal["id"])
            self.assertIsNone(detail["active_revision_id"])
            self.assertEqual(detail["decisions"], [])
            self.assertEqual(detail["jobs"], [])
            for operation in (start, decide, project):
                operation.assert_not_called()
        self.assertEqual(original_files, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(self.store.q("SELECT * FROM learning_policy_active"), [])
        self.assertEqual(kb.load_registry(self.root)["index"]["confirmed_by"], "原始确认人")

    def test_capture_idempotency_and_stale_fingerprint_are_exposed_by_api(self):
        revision = self.capture()
        before = self.snapshot()
        self.assertEqual(self.capture()["id"], revision["id"])
        # Same content is idempotent and does not rewrite a human confirmation.
        self.assertEqual(dump_store(self.store), before[0])
        self.assert_error(409, lambda: self.post("capture", key="fact:index", expected_fingerprint="stale"))
        self.assertEqual(dump_store(self.store), before[0])

    def test_agent_identity_validation_cannot_be_replaced_by_display_or_session(self):
        before = self.snapshot()
        for label in ("agent:reviewer", "名字", "has space", "x" * 33):
            with self.subTest(label=label):
                self.assert_error(400, lambda: self.post("capture", who="alice", key="fact:index",
                                                       expected_fingerprint=L.digest(self.body),
                                                       headers={"X-Webuddy-Agent": label, "X-TMH-User": "alice"}))
        for headers in ({}, {"X-TMH-User": "alice"}, {"X-Webuddy-User": "alice"},
                        {"X-TMH-Token": "shared-token"}):
            with self.subTest(headers=headers):
                self.assert_error(403, lambda: self.post("capture", who="", key="fact:index",
                                                       expected_fingerprint=L.digest(self.body), headers=headers))
        self.assertEqual(self.snapshot(), before)

    def test_agent_review_evaluate_and_resume_require_exact_execution_opt_in(self):
        revision = self.capture()
        before = self.snapshot()
        with patch.object(R, "start") as start, patch.object(R, "resume") as resume:
            for action in ("review", "evaluate", "resume"):
                for flag in (None, "", "0", "true", "01", " 1"):
                    with self.subTest(action=action, flag=flag):
                        headers = {"X-Webuddy-Agent": "reader"}
                        if flag is not None:
                            headers["X-Webuddy-Execution"] = flag
                        self.assert_error(403, lambda: self.post(action, headers=headers, who="alice",
                                                               revision_id=revision["id"], job_id="job",
                                                               request_id="request"))
            start.assert_not_called()
            resume.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_agent_execution_preserves_kind_budget_request_and_agent_actor(self):
        revision = self.capture()
        # Scheduling is mocked here to test forwarding only. Its return IDs
        # must still identify recorded jobs for the real ownership projection.
        self.recorded_job(revision, jid="queued")
        self.recorded_job(revision, jid="resumed")
        options = {"agent": "claude", "model": "synthetic-model", "max_calls": 6,
                   "max_revisions": 2, "timeout_seconds": 600}
        headers = {"X-Webuddy-Agent": "reviewer", "X-Webuddy-Execution": "1", "X-TMH-User": "alice"}
        with patch.object(R, "start", return_value={"id": "queued"}) as start:
            for kind in ("review", "evaluate"):
                result = self.post(kind, who="alice", headers=headers, revision_id=revision["id"],
                                   request_id="request-" + kind, **options)
                self.assertEqual(result, {"id": "queued"})
                start.assert_called_with(self.P, self.p, kind, revision["id"], options,
                                         "agent:reviewer", "request-" + kind)
        with patch.object(R, "resume", return_value={"id": "resumed"}) as resume:
            self.assertEqual(self.post("resume", who="alice", headers=headers, job_id="job"), {"id": "resumed"})
            resume.assert_called_once_with(self.P, self.p, "job", "agent:reviewer")

    @unittest.skipUnless(os.name == "posix", "合成 --help 可执行夹具使用 POSIX shebang；不声称 Windows 执行器已验证")
    def test_real_start_returns_the_registered_ordinary_job(self):
        revision = self.capture()
        executable = self.home / "synthetic-help-only"
        # This executable accepts only capability discovery. The real start
        # validates it and records a job; _launch is the only mocked boundary.
        executable.write_text(
            "#!/bin/sh\n"
            '[ "$#" -eq 1 ] && [ "$1" = "--help" ] || exit 97\n'
            "printf '%s\\n' '" + "\n".join(R._REQUIRED_FLAGS) + "'\n", encoding="utf-8")
        executable.chmod(0o700)
        (self.data / "agents.json").write_text(
            json.dumps({"claude": {"bin": str(executable)}}), encoding="utf-8")
        options = {"agent": "claude", "model": "synthetic-model", "max_calls": 6,
                   "max_revisions": 2, "timeout_seconds": 600}
        headers = {"X-Webuddy-Agent": "reviewer", "X-Webuddy-Execution": "1"}
        with patch.object(R, "_launch") as launch:
            result = self.post("review", headers=headers, revision_id=revision["id"],
                               request_id="real-registration", **options)
            launch.assert_called_once_with(self.P, self.p, result["id"])
        row = self.store.one("SELECT * FROM learning_jobs WHERE id=?", (result["id"],))
        self.assertIsNotNone(row)
        self.assertEqual(result, R.get(self.P, self.p, result["id"]))
        self.assertEqual((row["project_id"], row["kind"], row["revision_id"], row["actor"],
                          row["request_id"], row["status"]),
                         (self.p["id"], "review", revision["id"], "agent:reviewer", "real-registration", "queued"))
        self.assertEqual({key: json.loads(row["options"])[key] for key in options}, options)
        self.assertEqual(result["options"]["configuration"]["capabilities"], list(R._REQUIRED_FLAGS))
        self.assertNotIn("managed", result)
        self.assertEqual(result["steps"], [])
        self.assertEqual(self.store.q("SELECT * FROM runs"), [])

    def test_execution_response_requires_a_persisted_job_before_returning(self):
        revision = self.capture()
        before = self.snapshot()
        headers = {"X-Webuddy-Agent": "reviewer", "X-Webuddy-Execution": "1"}
        with patch.object(R, "start", return_value={"id": "missing-job"}):
            for kind in ("review", "evaluate"):
                with self.subTest(action=kind):
                    self.assert_error(404, lambda: self.post(
                        kind, headers=headers, revision_id=revision["id"], request_id="missing-" + kind))
        with patch.object(R, "resume", return_value={"id": "missing-job"}):
            self.assert_error(404, lambda: self.post("resume", headers=headers, job_id="missing-job"))
        self.assertEqual(self.snapshot(), before)

    def test_agent_cancel_is_allowed_without_launch_opt_in_and_preserves_evidence(self):
        revision = self.capture()
        jid = self.recorded_job(revision, status="queued")
        with patch.object(R, "_launch") as launch:
            result = self.post("cancel", who="alice", headers={"X-Webuddy-Agent": "reviewer"}, job_id=jid)
            self.assertEqual(result["status"], "cancelled")
            self.assertIn("agent:reviewer", result["error"])
            self.assertEqual(result["revision_id"], revision["id"])
            launch.assert_not_called()
        self.assertEqual(self.store.q("SELECT * FROM learning_decisions"), [])

    def test_human_decisions_reject_agent_shared_token_and_display_impersonation(self):
        revision = self.capture()
        before = self.snapshot()
        with patch.object(D, "decide") as decide, patch.object(D, "project_decision") as project, \
                patch.object(D, "abandon") as abandon:
            for action in ("adopt", "revoke", "retry_decision", "abandon_decision"):
                for who, headers in (("", {}), ("", {"X-TMH-User": "alice"}),
                                     ("", {"X-Webuddy-User": "alice"}),
                                     ("", {"X-TMH-Token": "shared-token"}),
                                     ("alice", {"X-Webuddy-Agent": "reviewer", "X-Webuddy-Execution": "1"})):
                    with self.subTest(action=action, who=who, headers=headers):
                        self.assert_error(403, lambda: self.post(action, who=who, headers=headers,
                                                               revision_id=revision["id"], request_id="request",
                                                               expected_active=None, reason="本人已确认", actor="alice",
                                                               decision_id="decision", job_id="job"))
            decide.assert_not_called()
            project.assert_not_called()
            abandon.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_reserved_nonhuman_sessions_cannot_reach_any_decision_mutation(self):
        revision = self.capture()
        before = self.snapshot()
        with patch.object(D, "decide") as decide, patch.object(D, "project_decision") as project, \
                patch.object(D, "abandon") as abandon:
            for action in ("adopt", "revoke", "retry_decision", "abandon_decision"):
                for who in ("system", "agent", "agent:reviewer", "external:token", "自动流转"):
                    with self.subTest(action=action, who=who):
                        self.assert_error(403, lambda: self.post(action, who=who, revision_id=revision["id"],
                                                               expected_active=None, request_id="request",
                                                               reason="伪造确认", decision_id="decision", job_id="job"))
            decide.assert_not_called()
            project.assert_not_called()
            abandon.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_authenticated_personal_decision_uses_session_not_supplied_actor(self):
        revision = self.capture()
        headers = {"X-TMH-User": "forged-display", "X-Webuddy-User": "forged-display"}
        with patch.object(D, "decide", return_value={"status": "pending"}) as decide:
            for action, active in (("adopt", None), ("revoke", revision["id"])):
                result = self.post(action, who="alice", headers=headers, revision_id=revision["id"],
                                   expected_active=active, request_id="request-" + action,
                                   reason="本人核对完整证据", job_id="job", actor="forged-body")
                self.assertEqual(result, {"status": "pending"})
                decide.assert_called_with(self.P, self.p, action, revision["id"], "alice", "request-" + action,
                                          active, "本人核对完整证据", "job")
        with patch.object(D, "project_decision", return_value={"status": "applied"}) as project:
            result = self.post("retry_decision", who="alice", headers=headers, decision_id="decision", actor="forged-body")
            self.assertEqual(result, {"status": "applied"})
            project.assert_called_once_with(self.P, self.p, "decision")

    def test_personal_abandon_forwards_exact_token_reason_and_session_actor(self):
        with patch.object(D, "abandon", return_value={"status": "abandoned"}) as abandon:
            result = self.post("abandon_decision", who="alice", decision_id="decision",
                               expected_token="observed-content-token", reason="保留完整人工处理理由。\n第二行。",
                               actor="forged-body", headers={"X-TMH-User": "forged-display"})
            self.assertEqual(result, {"status": "abandoned"})
            abandon.assert_called_once_with(self.P, self.p, "decision", "alice", "observed-content-token",
                                            "保留完整人工处理理由。\n第二行。")

    def test_cross_project_decision_retry_and_abandon_are_404(self):
        did = self.recorded_decision(self.capture())
        before = self.snapshot()
        for action in ("retry_decision", "abandon_decision"):
            for decision_id in (did, "missing-decision"):
                with self.subTest(action=action, decision=decision_id):
                    self.assert_error(404, lambda: self.post(action, project="OTHER", decision_id=decision_id,
                                                           expected_token="token", reason="本人确认"))
        self.assertEqual(self.snapshot(), before)

    def test_personal_decisions_require_explicit_expected_active_even_when_empty(self):
        revision = self.capture()
        before = self.snapshot()
        with patch.object(D, "decide") as decide:
            for action in ("adopt", "revoke"):
                self.assert_error(400, lambda: self.post(action, revision_id=revision["id"],
                                                       request_id="request", reason="本人确认", job_id="job"))
            decide.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_invalid_request_shapes_actions_and_projects_do_not_mutate(self):
        before = self.snapshot()
        for body in (None, [], "capture", 1):
            self.assert_error(400, lambda: server.api_learning_action(self.P, self.request(body=body, who="alice")))
        self.assert_error(400, lambda: self.post("unknown"))
        self.assert_error(404, lambda: self.read(project="MISSING"))
        self.assert_error(404, lambda: self.post("capture", project="MISSING"))
        self.assert_error(400, lambda: self.read(project="APP", kind="unexpected"))
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
