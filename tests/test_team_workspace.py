"""Real identity/team responsibility and synthetic candidate-boundary tests.

Temporary Git repositories are real. Verification/preview evidence is explicitly
synthetic: these tests prove authorization and state transitions, not a customer's
business acceptance or a deployed application.
"""
import concurrent.futures
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import agent_api, candidates, login, preview, team
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform, make_handler
from tmh.platform.store import Store


class TeamWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-team-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Team fixture")
        self.git("config", "user.email", "fixture@localhost")
        (self.repo / "app.txt").write_text("baseline\n")
        self.git("add", ".")
        self.git("commit", "-m", "baseline")
        self.base = self.git("rev-parse", "HEAD")
        self.P = Platform(self.root / "data", user="untrusted-display")
        self.addCleanup(self.P.store.db.close)
        # Password material never appears in a team API response.
        for name in ("alice", "bob", "charlie"):
            login.set_user(self.P.data_dir, name, "temporary-fixture-password")
        self.project = self.P.store.add_project("TEAM", "Team fixture", str(self.repo))
        self.ticket = self.P.store.create_ticket(self.project["id"], "保存后刷新仍可查看", "alice",
                                               body="要求：记录必须持久保存", assignee="alice", links={"hold": "alice"})
        team.schema(self.P)
        self.sequence = 0

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True, check=True).stdout.strip()

    def action(self, action, user="alice", **args):
        self.sequence += 1
        return team.dispatch_action(self.P, {"action": action, "ticket": self.ticket["key"],
                                            "request_id": "test-%d" % self.sequence, **args}, user)

    def assign(self, owner="alice", reviewer="bob", **args):
        current = team.assignment(self.P, self.P.store.ticket(self.ticket["id"]))
        return self.action("assign", assignee=owner, reviewer=reviewer, revision=current["revision"],
                           previous_assignee=current["assignee"], **args)

    def candidate(self):
        self.assign()
        self.git("checkout", "-b", "candidate")
        (self.repo / "app.txt").write_text("candidate\n")
        self.git("commit", "-am", "candidate")
        self.commit = self.git("rev-parse", "HEAD")
        self.git("checkout", "main")
        self.args = {"base_commit": self.base, "commit": self.commit,
                     "requirement_hash": agent_api._requirement(self.P.store.ticket(self.ticket["id"]), self.P.store),
                     "criteria": [{"id": "AC1", "text": "保存后仍存在", "check": "创建并刷新核对"}],
                     "summary": "临时测试候选，不是业务验收证据"}
        result = self.action("candidate_submit", **self.args)
        self.cid = result["result"]["candidate_id"]
        return result

    def synthetic_checks(self):
        run = self.P.store.run(candidates._row(self.P, self.cid)["run_id"])
        self.verification = {"verification_current": True, "check": "pass", "checked_commit": self.commit,
                             "checked_base": self.base, "checked_diff": run["diff"],
                             "commands": [{"kind": "test", "exit_code": 0, "output": "SYNTHETIC identity boundary fixture"}]}
        self.pv = {"state": "up", "commit_full": self.commit,
                   "prefix": preview.bound_prefix(self.ticket["key"], self.commit)}
        for target, value in (("tmh.platform.fixloop.verified", self.verification), ("tmh.platform.preview.status", self.pv)):
            mock = patch(target, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_partial_vue_diagnostic_is_not_formal_verification(self):
        self.candidate()
        report={'kind':'partial_vue_diagnostic','candidate_id':self.cid,'commit':self.commit,
                'actor':'alice','scope':'部分诊断，不代表验收','vue_files':1,'templates_checked':1,
                'skipped':[],'bad':['example.vue [模板]']}
        before=candidates.view(self.P,self.cid)
        with patch('tmh.platform.project_vue_diagnostic.run',return_value=report):
            response=self.action('candidate_diagnostic',candidate_id=self.cid)
        self.assertEqual(response['item']['candidate']['partial_diagnostic']['bad'],report['bad'])
        after=candidates.view(self.P,self.cid)
        self.assertEqual(after['verification_hash'],before['verification_hash'])
        self.assertEqual(after['verification_passed'],before['verification_passed'])
        self.assertEqual(after['human_accepted'],before['human_accepted'])

    def assess(self):
        current = candidates.view(self.P, self.cid)
        return self.action("candidate_assess", "bob", candidate_id=self.cid,
                           verification_hash=current["verification_hash"], preview_hash=current["preview_hash"],
                           results=[{"id": "AC1", "status": "pass", "evidence": "SYNTHETIC boundary fixture"}], note="合成检查")

    def approve(self):
        self.candidate()
        self.synthetic_checks()
        self.assess()
        current = candidates.view(self.P, self.cid)
        return self.action("review", "bob", candidate_id=self.cid, evidence_hash=current["evidence_hash"],
                           decision="accept", note="合成状态测试的人工确认")

    def test_member_directory_exposes_names_only_and_mine_is_actual_owner(self):
        self.assign()
        other = self.P.store.create_ticket(self.project["id"], "其他人的任务", "charlie", assignee="charlie", links={"hold": "charlie"})
        data = team.dispatch_read(self.P, {"view": ["mine"]}, "alice")
        self.assertEqual([x["ticket"]["key"] for x in data["items"]], [self.ticket["key"]])
        self.assertNotIn(other["key"], [x["ticket"]["key"] for x in data["items"]])
        self.assertEqual(data["members"], [{"id": x, "name": x} for x in ("alice", "bob", "charlie")])
        self.assertNotIn("pbkdf2", json.dumps(data))
        self.assertEqual(team.dispatch_read(self.P, {"view": "mine", "user": "alice"}, "invented")["items"], [])

    def test_invalid_member_and_self_reviewer_rejected_without_changes(self):
        for owner, reviewer in (("invented", "bob"), ("alice", "alice")):
            with self.assertRaises(ApiError):
                self.assign(owner, reviewer)
        self.assertEqual(self.P.store.q("SELECT * FROM ticket_team"), [])

    def test_assignment_conflict_does_not_overwrite_new_owner(self):
        self.assign()
        with self.assertRaises(ApiError) as caught:
            self.action("assign", assignee="charlie", reviewer="bob", revision=0, previous_assignee="alice")
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.P.store.ticket(self.ticket["id"])["assignee"], "alice")
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='team_assignment'")), 1)

    def test_concurrent_assignment_has_one_winner_across_connections(self):
        other_store = Store(self.P.store.path)
        self.addCleanup(other_store.db.close)
        other = SimpleNamespace(store=other_store, data_dir=self.P.data_dir)
        barrier = threading.Barrier(2)
        def assign(P, owner):
            barrier.wait()
            try:
                with team._guard(P, self.ticket["id"]):
                    return team._assign(P, self.ticket, {"assignee": owner, "reviewer": "bob", "revision": 0, "previous_assignee": "alice"}, "alice")
            except ApiError as exc:
                return exc.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pair: assign(*pair), [(self.P, "alice"), (other, "charlie")]))
        self.assertEqual(sum(isinstance(r, dict) for r in results), 1)
        self.assertIn(409, results)
        self.assertEqual(team.assignment(self.P, self.P.store.ticket(self.ticket["id"]))["revision"], 1)

    def test_display_identity_or_deleted_account_cannot_mutate(self):
        with self.assertRaises(ApiError) as caught:
            self.action("comment", "untrusted-display", body="forged")
        self.assertEqual(caught.exception.code, 403)
        login.del_user(self.P.data_dir, "alice")
        with self.assertRaises(ApiError):
            self.action("comment", body="removed account")
        self.assertFalse(any(e["kind"] == "comment" for e in self.P.store.events(self.ticket["id"])))

    def test_deleted_owner_invalidates_active_team_review_until_reassigned(self):
        approved = self.approve()
        self.assertEqual(approved["item"]["human"], "accepted")
        login.del_user(self.P.data_dir, "alice")
        current = team.item(self.P, self.P.store.ticket(self.ticket["id"]), "bob")
        self.assertFalse(candidates.browser_review_current(self.P, self.cid))
        self.assertEqual(current["human"], "pending")
        self.assertFalse(current["can_review"])
        with self.assertRaises(ApiError):
            self.action("candidate_merge", "bob", candidate_id=self.cid, evidence_hash=current["candidate"]["evidence_hash"])

    def test_external_agent_assignment_is_unassigned_member_not_fake_person(self):
        self.P.store.update_ticket(self.ticket["id"], "system", assignee="agent:codex")
        data = team.dispatch_read(self.P, {"view": "unassigned"}, "alice")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["assignment"]["assignee"], "agent:codex")
        self.assertFalse(data["items"][0]["assignment"]["assignee_active"])

    def test_submission_is_owned_version_bound_and_idempotent(self):
        self.candidate()
        with self.assertRaises(ApiError):
            self.action("candidate_submit", "charlie", **self.args)
        retry = self.action("candidate_submit", **self.args)
        self.assertEqual(retry["result"]["candidate_id"], self.cid)
        self.assertFalse(retry["item"]["candidate"]["human_accepted"])
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_exact_request_replay_does_not_duplicate_comment(self):
        body = {"action": "comment", "ticket": self.ticket["key"], "request_id": "fixed", "body": "完整交接\n第二行"}
        first = team.dispatch_action(self.P, body, "alice")
        second = team.dispatch_action(self.P, body, "alice")
        self.assertEqual(first["result"], second["result"])
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='comment'")), 1)
        with self.assertRaises(ApiError):
            team.dispatch_action(self.P, dict(body, body="不同内容"), "alice")

    def test_candidate_without_checks_cannot_be_approved(self):
        self.candidate()
        current = candidates.view(self.P, self.cid)
        with self.assertRaises(ApiError) as caught:
            self.action("review", "bob", candidate_id=self.cid, evidence_hash=current["evidence_hash"], decision="accept", note="不能跳过检查")
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.P.store.q("SELECT * FROM candidate_decisions"), [])

    def test_owner_and_other_member_cannot_review(self):
        self.candidate()
        self.synthetic_checks()
        self.assess()
        current = candidates.view(self.P, self.cid)
        for user in ("alice", "charlie"):
            with self.assertRaises(ApiError) as caught:
                self.action("review", user, candidate_id=self.cid, evidence_hash=current["evidence_hash"], decision="accept", note="越权")
            self.assertEqual(caught.exception.code, 403)
        self.assertEqual(self.P.store.q("SELECT * FROM candidate_decisions"), [])

    def test_team_state_distinguishes_checks_review_and_merge(self):
        self.candidate()
        self.assertEqual(team.item(self.P, self.P.store.ticket(self.ticket["id"]), "bob")["state"], "verification")
        self.synthetic_checks()
        self.assertEqual(team.item(self.P, self.P.store.ticket(self.ticket["id"]), "bob")["state"], "assessment")
        self.assess()
        self.assertEqual(team.dispatch_read(self.P, {"view": "review"}, "bob")["counts"]["review"], 1)
        current = candidates.view(self.P, self.cid)
        accepted = self.action("review", "bob", candidate_id=self.cid, evidence_hash=current["evidence_hash"], decision="accept", note="人工确认")
        self.assertEqual(accepted["item"]["state"], "approved")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.assertNotEqual(self.P.store.ticket(self.ticket["id"])["status"], "closed")

    def test_changed_requirement_invalidates_approval_and_blocks_merge(self):
        approved = self.approve()
        self.action("comment", body="新增业务要求")
        with self.assertRaises(ApiError) as caught:
            self.action("candidate_merge", "bob", candidate_id=self.cid, evidence_hash=approved["item"]["candidate"]["evidence_hash"])
        self.assertEqual(caught.exception.code, 409)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)

    def test_candidate_author_cannot_gain_self_review_or_merge_by_reassignment(self):
        self.candidate()
        self.synthetic_checks()
        self.assess()
        self.assign(owner="charlie", reviewer="alice")
        current = candidates.view(self.P, self.cid)
        body = {"candidate_id": self.cid, "evidence_hash": current["evidence_hash"], "decision": "accept", "note": "试图自审"}
        with self.assertRaises(ApiError) as caught:
            self.action("review", "alice", **body)
        self.assertEqual(caught.exception.code, 403)
        self.assertFalse(team.item(self.P, self.P.store.ticket(self.ticket["id"]), "alice")["can_review"])
        # Model an old database row written before this guard existed. Merely
        # blocking new decisions is insufficient; it must never authorize merge.
        identity = team.assignment(self.P, self.P.store.ticket(self.ticket["id"]))
        candidates.execute(self.P, "alice", "candidate_decide", dict(body, _team_identity=identity))
        self.assertFalse(candidates.browser_review_current(self.P, self.cid))
        with self.assertRaises(ApiError):
            self.action("candidate_merge", "alice", candidate_id=self.cid, evidence_hash=current["evidence_hash"])
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.assertIsNone(candidates.merge_receipt(self.P, self.cid))

    def test_ineligible_recheck_refusal_never_blocks_following_task_work(self):
        run = self.P.store.create_run(self.project["id"], self.ticket["id"], "fixture", "fix", "alice", "synthetic")
        variants = [{"status": "queued", "diff": "synthetic diff", "decision": ""},
                    {"status": "failed", "diff": "synthetic diff", "decision": ""},
                    {"status": "done", "diff": "", "decision": ""},
                    {"status": "done", "diff": "synthetic diff", "decision": "rejected:alice"}]
        for changes in variants:
            with self.subTest(changes=changes):
                self.P.store.update_run(run["id"], **changes)
                self.assertFalse(team.item(self.P, self.P.store.ticket(self.ticket["id"]), "alice")["run"]["can_recheck"])
                with self.assertRaises(ApiError) as caught:
                    self.action("run_recheck", run_id=run["id"])
                self.assertEqual(caught.exception.code, 409)
                receipt = self.P.store.one("SELECT * FROM team_requests ORDER BY rowid DESC LIMIT 1")
                self.assertEqual(receipt["state"], "failed")
                self.action("comment", body="拒绝不合格复检后仍可继续交接")
        self.assertFalse(self.P.store.q("SELECT * FROM team_requests WHERE state IN ('pending','uncertain')"))

    def test_reassignment_invalidates_team_review_even_when_code_same(self):
        approved = self.approve()
        self.assign("alice", "charlie")
        current = team.item(self.P, self.P.store.ticket(self.ticket["id"]), "charlie")
        self.assertEqual(current["human"], "pending")
        self.assertEqual(current["state"], "review")
        with self.assertRaises(ApiError):
            self.action("candidate_merge", "charlie", candidate_id=self.cid, evidence_hash=approved["item"]["candidate"]["evidence_hash"])

    def test_merge_writes_only_local_exact_commit_and_no_fake_acceptance(self):
        approved = self.approve()
        body = {"action": "candidate_merge", "ticket": self.ticket["key"], "candidate_id": self.cid,
                "evidence_hash": approved["item"]["candidate"]["evidence_hash"], "request_id": "merge-once"}
        result = team.dispatch_action(self.P, body, "bob")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.commit)
        self.assertEqual(result["item"]["state"], "merged")
        self.assertFalse(result["result"]["pushed"])
        self.assertFalse(result["result"]["deployed"])
        self.assertNotEqual(self.P.store.ticket(self.ticket["id"])["status"], "closed")
        self.assertFalse(self.P.store.q("SELECT * FROM events WHERE kind IN ('adopt','accept','release')"))
        second = team.dispatch_action(self.P, body, "bob")
        self.assertEqual(result["result"], second["result"])
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='candidate_merge'")), 1)

    def test_moved_main_and_dirty_workspace_block_merge(self):
        approved = self.approve()
        (self.repo / "unrelated.txt").write_text("local untracked work\n")
        args = {"candidate_id": self.cid, "evidence_hash": approved["item"]["candidate"]["evidence_hash"]}
        with self.assertRaises(ApiError):
            self.action("candidate_merge", "bob", **args)
        self.git("add", ".")
        self.git("commit", "-m", "new main")
        head = self.git("rev-parse", "HEAD")
        with self.assertRaises(ApiError) as caught:
            self.action("candidate_merge", "bob", **args)
        self.assertIn("主干", str(caught.exception))
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_prepared_merge_recovers_after_git_write_before_receipt(self):
        approved = self.approve()
        original = candidates._git
        crashed = False
        def lose_receipt(root, *args, **kwargs):
            nonlocal crashed
            value = original(root, *args, **kwargs)
            if args[:1] == ("merge",) and not crashed:
                crashed = True
                raise RuntimeError("synthetic service death after git mutation")
            return value
        body = {"action": "candidate_merge", "ticket": self.ticket["key"], "candidate_id": self.cid,
                "evidence_hash": approved["item"]["candidate"]["evidence_hash"], "request_id": "recover-merge"}
        with patch.object(candidates, "_git", side_effect=lose_receipt):
            with self.assertRaises(RuntimeError):
                team.dispatch_action(self.P, body, "bob")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.commit)
        self.assertEqual(candidates.merge_receipt(self.P, self.cid)["state"], "prepared")
        recovered = team.dispatch_action(self.P, body, "bob")
        self.assertEqual(recovered["result"]["state"], "merged")
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='candidate_merge'")), 1)

    def test_concurrent_merge_cannot_duplicate_git_or_event(self):
        approved = self.approve()
        started, release = threading.Event(), threading.Event()
        original = candidates._git
        def slow(root, *args, **kwargs):
            if args[:1] == ("merge",):
                started.set()
                self.assertTrue(release.wait(4))
            return original(root, *args, **kwargs)
        args = {"candidate_id": self.cid, "evidence_hash": approved["item"]["candidate"]["evidence_hash"]}
        with patch.object(candidates, "_git", side_effect=slow), concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.action, "candidate_merge", "bob", **args)
            self.assertTrue(started.wait(4))
            # Same data folder, another service connection; schema must not wait
            # behind the first writer before the per-ticket lock is attempted.
            try:
                with self.assertRaises(ApiError):
                    with team._guard(self.P, self.ticket["id"]):
                        self.fail("second writer acquired the task lock")
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5)["result"]["state"], "merged")
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='candidate_merge'")), 1)

    def test_ticket_deep_link_and_pagination_never_hide_target(self):
        for i in range(3):
            self.P.store.create_ticket(self.project["id"], "task %s" % i, "charlie", assignee="charlie", links={"hold": "charlie"})
        data = team.dispatch_read(self.P, {"view": "team", "limit": "2"}, "alice")
        self.assertTrue(data["has_more"])
        self.assertEqual(data["total"], 4)
        direct = team.dispatch_read(self.P, {"view": "team", "ticket": self.ticket["key"]}, "alice")
        self.assertEqual(len(direct["items"]), 1)
        self.assertEqual(direct["items"][0]["ticket"]["key"], self.ticket["key"])

    def start_http(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.P, token="shared-script-token"))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join, 3)
        self.addCleanup(server.shutdown)
        return server

    def http(self, server, method, path, body=None, user=None, headers=None):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        self.addCleanup(connection.close)
        hdrs = {"Content-Type": "application/json", "X-TMH": "1", "X-TMH-Token": "shared-script-token"}
        if user:
            hdrs["Cookie"] = "tmh_session=" + login.make_session(self.P.data_dir, user)
        hdrs.update(headers or {})
        connection.request(method, path, json.dumps(body) if body is not None else None, hdrs)
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def test_http_shared_token_cannot_impersonate_team_actor_or_personal_read(self):
        self.assign()
        server = self.start_http()
        body = {"action": "comment", "ticket": self.ticket["key"], "body": "spoof", "request_id": "spoof"}
        status, result = self.http(server, "POST", "/api/team", body, headers={"X-TMH-User": "alice"})
        self.assertEqual(status, 403, result)
        status, result = self.http(server, "GET", "/api/team?view=mine&user=alice", headers={"X-TMH-User": "alice"})
        self.assertEqual(status, 200)
        self.assertEqual(result["viewer"], "")
        self.assertEqual(result["items"], [])
        status, result = self.http(server, "POST", "/api/team", body, user="alice", headers={"X-Webuddy-Agent": "codex"})
        self.assertEqual(status, 403, result)
        self.assertFalse(self.P.store.q("SELECT * FROM events WHERE kind='comment'"))

    def test_http_session_identity_wins_over_forged_display_header(self):
        self.assign()
        server = self.start_http()
        status, result = self.http(server, "POST", "/api/team", {"action": "comment", "ticket": self.ticket["key"], "body": "真实登录人的交接", "request_id": "real"},
                                   user="alice", headers={"X-TMH-User": "bob"})
        self.assertEqual(status, 200, result)
        self.assertEqual(self.P.store.q("SELECT author FROM events WHERE kind='comment'")[0]["author"], "alice")
        status, result = self.http(server, "GET", "/api/team?view=mine", user="alice", headers={"X-TMH-User": "bob"})
        self.assertEqual(result["viewer"], "alice")
        self.assertEqual(len(result["items"]), 1)

    def test_http_old_human_routes_reject_shared_token_and_agent_header(self):
        self.assign()
        run = self.P.store.create_run(self.project["id"], self.ticket["id"], "codex", "fix", "alice", "fixture")
        server = self.start_http()
        routes = [
            ("/api/tickets/%s/accept" % self.ticket["key"], {"result": "pass", "note": "forged"}),
            ("/api/tickets/%s/evidence" % self.ticket["key"], {"kind": "review", "note": "forged"}),
            ("/api/tickets/%s/release" % self.ticket["key"], {}),
            ("/api/runs/%d/decide" % run["id"], {"decision": "accept"}),
        ]
        for path, body in routes:
            for user, headers in ((None, {"X-TMH-User": "bob"}), ("bob", {"X-Webuddy-Agent": "codex"}), ("alice", {})):
                with self.subTest(path=path, user=user, headers=headers):
                    status, result = self.http(server, "POST", path, body, user=user, headers=headers)
                    self.assertEqual(status, 403, result)
        self.assertFalse(self.P.store.q("SELECT * FROM events WHERE kind IN ('accept','adopt','release')"))

    def test_http_assigned_reviewer_can_use_old_routes_after_authentication(self):
        self.assign()
        run = self.P.store.create_run(self.project["id"], self.ticket["id"], "codex", "fix", "alice", "fixture")
        server = self.start_http()
        with patch.object(self.P.runner, "decide", return_value={"checked": True}) as decide:
            status, result = self.http(server, "POST", "/api/runs/%d/decide" % run["id"], {"decision": "accept"}, user="bob", headers={"X-TMH-User": "alice"})
            self.assertEqual(status, 200, result)
            decide.assert_called_once_with(run["id"], "accept", "bob")
        with patch.object(self.P.flow, "ship_again", return_value={"state": "waiting"}) as ship:
            status, result = self.http(server, "POST", "/api/tickets/%s/release" % self.ticket["key"], {}, user="bob")
            self.assertEqual(status, 200, result)
            self.assertEqual(ship.call_args.args[-1], "bob")

    def test_http_legacy_assignment_and_claim_cannot_bypass_team_revision(self):
        self.assign()
        server = self.start_http()
        status, result = self.http(server, "POST", "/api/tickets/" + self.ticket["key"], {"assignee": "charlie"}, user="charlie")
        self.assertEqual(status, 409, result)
        for user, headers in (("charlie", {}), (None, {"X-TMH-User": "alice"}), ("alice", {"X-Webuddy-Agent": "codex"})):
            status, result = self.http(server, "POST", "/api/tickets/%s/claim" % self.ticket["key"], {}, user=user, headers=headers)
            self.assertEqual(status, 403, result)
        status, result = self.http(server, "POST", "/api/tickets/%s/claim" % self.ticket["key"], {}, user="alice")
        self.assertEqual(status, 200, result)
        self.assertEqual(self.P.store.ticket(self.ticket["id"])["assignee"], "alice")
        self.assertEqual(team.assignment(self.P, self.P.store.ticket(self.ticket["id"]))["revision"], 1)

    def test_legacy_assignment_and_team_assignment_share_the_same_task_lock(self):
        server = self.start_http()
        entered, release = threading.Event(), threading.Event()
        original = self.P.store.update_ticket
        def waiting_update(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("fixture update did not resume")
            return original(*args, **kwargs)
        with patch.object(self.P.store, "update_ticket", side_effect=waiting_update):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.http, server, "POST", "/api/tickets/" + self.ticket["key"], {"assignee": "charlie"}, user="charlie")
                try:
                    self.assertTrue(entered.wait(5))
                    with self.assertRaises(ApiError) as caught:
                        self.assign()
                    self.assertEqual(caught.exception.code, 409)
                finally:
                    release.set()
                status, result = pending.result(timeout=5)
        self.assertEqual(status, 200, result)
        self.assertEqual(self.P.store.ticket(self.ticket["id"])["assignee"], "charlie")
        self.assign()
        self.assertEqual(self.P.store.ticket(self.ticket["id"])["assignee"], "alice")
        self.assertEqual(team.assignment(self.P, self.P.store.ticket(self.ticket["id"]))["revision"], 1)

    def test_http_external_candidate_cannot_be_closed_through_legacy_accept(self):
        self.candidate()
        server = self.start_http()
        for body in ({"result": "pass", "note": "skip checks"}, {"result": "pass", "note": "skip checks", "candidate_id": self.cid,
                     "evidence_hash": candidates.view(self.P, self.cid)["evidence_hash"]}):
            status, result = self.http(server, "POST", "/api/tickets/%s/accept" % self.ticket["key"], body, user="bob")
            self.assertEqual(status, 409, result)
        self.assertNotEqual(self.P.store.ticket(self.ticket["id"])["status"], "closed")

    def test_business_acceptance_requires_review_and_merge_then_records_exact_evidence(self):
        approved = self.approve()
        evidence = approved["item"]["candidate"]["evidence_hash"]
        with self.assertRaises(ApiError):
            self.action("business_accept", "bob", candidate_id=self.cid, evidence_hash=evidence, result="pass", note="尚未合并")
        self.action("candidate_merge", "bob", candidate_id=self.cid, evidence_hash=evidence)
        result = self.action("business_accept", "bob", candidate_id=self.cid, evidence_hash=evidence, result="pass", note="合成夹具的显式业务验收记录")
        self.assertEqual(result["item"]["state"], "closed")
        event = self.P.store.one("SELECT * FROM events WHERE kind='accept'")
        self.assertEqual(event["data"]["commit"], self.commit)
        self.assertEqual(event["data"]["evidence_hash"], evidence)
        self.assertFalse(event["data"]["customer_signature"])
        self.assertFalse(self.P.store.q("SELECT * FROM events WHERE kind='adopt'"))

    def test_preview_restart_requires_fresh_review_but_retains_original_merge_evidence(self):
        approved = self.approve()
        original = approved["item"]["candidate"]["evidence_hash"]
        self.action("candidate_merge", "bob", candidate_id=self.cid, evidence_hash=original)
        self.pv["started"] = "restarted-preview-fixture"
        current = candidates.view(self.P, self.cid)
        with self.assertRaises(ApiError):
            self.action("business_accept", "bob", candidate_id=self.cid, evidence_hash=current["evidence_hash"], result="pass", note="缺少新复核")
        self.assess()
        current = candidates.view(self.P, self.cid)
        self.action("review", "bob", candidate_id=self.cid, evidence_hash=current["evidence_hash"], decision="accept", note="重新核对当前预览")
        self.action("business_accept", "bob", candidate_id=self.cid, evidence_hash=current["evidence_hash"], result="pass", note="合成版本的业务确认")
        event = self.P.store.one("SELECT * FROM events WHERE kind='accept'")
        self.assertNotEqual(original, current["evidence_hash"])
        self.assertEqual(event["data"]["evidence_hash"], current["evidence_hash"])
        self.assertEqual(event["data"]["merge_evidence_hash"], original)
        self.assertEqual(candidates.merge_receipt(self.P, self.cid)["evidence_hash"], original)
        self.assertEqual(len(self.P.store.q("SELECT * FROM events WHERE kind='candidate_merge'")), 1)

    def test_http_fixed_candidate_business_acceptance_is_available_only_after_merge(self):
        approved = self.approve()
        evidence = approved["item"]["candidate"]["evidence_hash"]
        self.action("candidate_merge", "bob", candidate_id=self.cid, evidence_hash=evidence)
        server = self.start_http()
        status, result = self.http(server, "POST", "/api/tickets/%s/accept" % self.ticket["key"],
                                   {"result": "pass", "note": "业务验收合成边界测试", "candidate_id": self.cid, "evidence_hash": evidence}, user="bob")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "closed")

    def test_review_queue_retains_merge_and_business_acceptance_until_closed(self):
        approved = self.approve()
        evidence = approved["item"]["candidate"]["evidence_hash"]
        def queue():
            return team.dispatch_read(self.P, {"view": "review"}, "bob")["items"]
        self.assertEqual(queue()[0]["state"], "approved")
        self.action("candidate_merge", "bob", candidate_id=self.cid, evidence_hash=evidence)
        self.assertEqual(queue()[0]["state"], "merged")
        self.action("business_accept", "bob", candidate_id=self.cid, evidence_hash=evidence, result="pass", note="合成边界验收")
        self.assertEqual(queue(), [])

    def test_request_receipt_is_scoped_to_authenticated_original_actor(self):
        self.action("comment", body="合成回执归属测试")
        self.assertEqual(team.dispatch_read(self.P, {"request_id": "test-1"}, "alice")["request"]["state"], "complete")
        self.assertIsNone(team.dispatch_read(self.P, {"request_id": "test-1"}, "bob")["request"])
        with self.assertRaises(ApiError):
            team.dispatch_read(self.P, {"request_id": "test-1", "user": "alice"}, "")

    @unittest.skipUnless(shutil.which("node"), "Node is needed to execute the team UI behavior")
    def test_ui_refresh_preserves_loaded_range_updates_counts_and_ignores_stale_scope(self):
        from tmh.platform.ui_team import TEAM_JS
        fixture = r"""
const assert=require('node:assert/strict');
let scope='TEAM',queries=[],rows=Array.from({length:140},(_,i)=>({ticket:{key:'TEAM-'+i,title:'Task '+i,type:'bug'},assignment:{assignee:'alice',assignee_active:true,reviewer:'bob'},state:'working',label:'待提交'}));
globalThis.location={hash:'#/team/team'};
globalThis.scopeQ=()=>scope;
globalThis.h=value=>String(value);
const list={innerHTML:'old-list',querySelectorAll:()=>[]},more={hidden:false},count={textContent:'old-count'},tab={dataset:{teamView:'team'},querySelector:()=>count};
globalThis.document={querySelector:s=>s==='#team-list'?list:s==='#team-more'?more:null,querySelectorAll:()=>[tab]};
globalThis.get=async url=>{queries.push(url);const q=new URLSearchParams(url.split('?')[1]),offset=Number(q.get('offset')),limit=Number(q.get('limit'));return{items:rows.slice(offset,offset+limit),counts:{team:140},has_more:offset+limit<rows.length,next_offset:offset+limit}};
teamState.project='TEAM';teamState.view='team';teamState.data={items:rows.slice(0,120)};
(async()=>{
 await teamRefreshList();
 assert.equal(teamState.data.items.length,120);assert.equal(teamState.data.next_offset,120);assert.equal(queries.length,2);assert.equal(count.textContent,140);assert.match(list.innerHTML,/bob/);assert.equal(more.hidden,false);
 const prior=teamState.data,html=list.innerHTML;
 globalThis.get=async()=>{scope='OTHER';return{items:[],counts:{team:0},has_more:false}};
 await teamRefreshList();assert.equal(teamState.data,prior);assert.equal(list.innerHTML,html);
})().catch(error=>{console.error(error);process.exitCode=1});
"""
        result = subprocess.run(["node", "-e", TEAM_JS + fixture], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_account_legacy_local_workflow_is_preserved(self):
        for name in ("alice", "bob", "charlie"):
            login.del_user(self.P.data_dir, name)
        server = self.start_http()
        with patch.object(self.P.flow, "accepted", return_value={}):
            status, result = self.http(server, "POST", "/api/tickets/%s/accept" % self.ticket["key"], {"result": "pass", "note": "旧本地模式"}, headers={"X-TMH-User": "local-owner"})
        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "closed")


if __name__ == "__main__":
    unittest.main()
