"""Tenant policy tests use separate temporary stores, no runtime or network."""
import ast
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tmh.platform import tenant_policy as policy, handoffs, team
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tests.sqlite_snapshot import dump_store


class Context:
    tenant_id = "customer"

    def __init__(self, root):
        self.root = root
        self.revision = 1
        self.people = {
            "admin": {"role": "admin", "project_grants": {}},
            "owner": {"role": "admin", "project_grants": {}, "platform_owner": True},
            "alice": {"role": "member", "project_grants": {"ALPHA": "manager"}},
            "bob": {"role": "member", "project_grants": {"ALPHA": "contributor"}},
            "outsider": {"role": "member", "project_grants": {"BETA": "manager"}},
            "reader": {"role": "viewer", "project_grants": {"ALPHA": "manager"}},
        }

    def current_actor(self, actor):
        value = self.people.get(actor)
        return dict(copy.deepcopy(value), authz_revision=self.revision) if value else None

    def directory(self):
        return copy.deepcopy(self.people)

    def runtime_allowed(self, actor):
        return self.tenant_id == "default" and self.current_actor(actor).get("platform_owner") is True

    def workspace_allowed(self, path):
        return Path(path).resolve().is_relative_to(self.root.resolve())


class TenantPolicyTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-tenant-policy-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        data = self.root / "data"
        self.store = Store(data / "platform.db")
        self.addCleanup(self.store.db.close)
        self.context = Context(self.root / "approved")
        self.P = SimpleNamespace(store=self.store, data_dir=data, tenant_context=self.context)
        self.projects = {}
        self.tickets = {}
        self.runs = {}
        for key in ("ALPHA", "BETA"):
            folder = self.context.root / key
            folder.mkdir(parents=True)
            project = self.store.add_project(key, key, str(folder))
            self.projects[key] = project
            ticket = self.store.create_ticket(project["id"], key + " confidential", "alice", assignee="alice")
            self.tickets[key] = ticket
            self.runs[key] = self.store.create_run(project["id"], ticket["id"], "fixture", "analyze", "alice", "private prompt")

    def auth(self, path, actor="alice", method="GET", body=None, query=None):
        return policy.authorize(self.P, method, path, query or {}, body or {}, actor)

    def denied(self, path, **kw):
        before = dump_store(self.store)
        with self.assertRaises(ApiError) as caught:
            self.auth(path, **kw)
        self.assertIn(caught.exception.code, (401, 403, 404))
        self.assertEqual(dump_store(self.store), before)

    def test_inventory_is_exact_and_every_entry_matches(self):
        from tmh.platform import server
        tree = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))
        actual = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                for item in node.decorator_list:
                    if isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "route":
                        actual.add(tuple(ast.literal_eval(arg) for arg in item.args))
        self.assertEqual(actual, policy.API_ROUTES)
        self.assertEqual(len(actual), 171)  # Original 167 + four personal trial routes.
        import re
        for method, template in actual:
            with self.subTest(method=method, template=template):
                path = re.sub(r"<[a-z]+>", "fixture", template)
                self.assertEqual(policy._match(method, path)[0], template)
        from tmh.agent_contract import SPECS
        self.assertEqual(set(SPECS), policy.AGENT_OPERATIONS)

    def test_unknown_routes_and_methods_deny_even_platform_owner(self):
        for path, method in (("/api/new-admin-feature", "POST"), ("/api/projects/ALPHA", "DELETE"),
                             ("/api/projects/ALPHA/private-new", "GET"), ("/", "GET")):
            self.denied(path, actor="owner", method=method)

    def test_stale_removed_and_forged_members_are_rejected(self):
        self.denied("/api/projects", actor="not-a-member")
        self.context.people.pop("alice")
        self.denied("/api/tickets/ALPHA-1")
        self.denied("/api/tickets/ALPHA-1/comments", actor="bob", method="POST",
                    body={"actor": "admin", "project": "BETA", "body": "forged"})

    def test_filtered_lists_return_current_allowed_keys_not_all_projects(self):
        self.assertEqual([p["key"] for p in policy.visible_projects(self.P, "alice")], ["ALPHA"])
        self.assertEqual([p["key"] for p in policy.visible_projects(self.P, "reader")], ["ALPHA"])
        self.assertEqual({p["key"] for p in policy.visible_projects(self.P, "admin")}, {"ALPHA", "BETA"})
        for path in policy.FILTERED_LISTS:
            with self.subTest(path=path):
                scope = self.auth(path)
                self.assertTrue(scope["filter_required"])
                self.assertEqual(scope["allowed_project_keys"], ["ALPHA"])
                self.assertEqual(scope["project_roles"], {"ALPHA": "manager"})
        self.context.people["alice"]["project_grants"] = {}
        self.context.revision += 1
        scope = self.auth("/api/workspace")
        self.assertEqual(scope["allowed_project_keys"], [])
        self.assertEqual(scope["authz_revision"], 2)

    def test_global_aggregates_are_not_enabled_by_fake_project_filters(self):
        for path in policy.ADMIN_GLOBAL:
            with self.subTest(path=path):
                self.denied(path, query={"project": ["ALPHA"]})
                self.auth(path, actor="admin")
        self.denied("/api/stats")
        self.auth("/api/stats", query={"project": ["ALPHA"]})

    def test_direct_and_nested_resource_ids_use_the_same_tenant_store(self):
        for kind, ident in (("tickets", "BETA-1"), ("runs", self.runs["BETA"]["id"])):
            self.denied("/api/%s/%s" % (kind, ident))
        self.auth("/api/runs/%s" % self.runs["ALPHA"]["id"])
        self.denied("/api/tickets/ALPHA-1/preview", query={"run_id": [str(self.runs["BETA"]["id"])]})
        sid = self.store.session_create(self.projects["BETA"]["id"], "consult", "private", "alice")
        self.denied("/api/sessions/%s" % sid)
        self.denied("/api/assist", query={"project": ["ALPHA"], "session": [str(sid)]})

    def test_resource_relationship_cannot_cross_projects_even_for_admin(self):
        for path, query, body, method in (
            ("/api/assist", {"project": ["ALPHA"], "ticket": ["BETA-1"]}, {}, "GET"),
            ("/api/projects/ALPHA/sessions", {}, {"ticket": "BETA-1"}, "POST"),
            ("/api/agent/preview_get", {}, {"ticket": "ALPHA-1", "run_id": self.runs["BETA"]["id"]}, "POST"),
        ):
            with self.subTest(path=path), self.assertRaises(ApiError) as caught:
                self.auth(path, actor="admin", query=query, body=body, method=method)
            self.assertEqual(caught.exception.code, 400)

    def test_memory_and_client_links_do_not_trust_a_project_selector(self):
        self.denied("/api/memory", query={"project": ["ALPHA"]})
        self.auth("/api/memory", actor="admin", query={"project": ["ALPHA"]})
        for fields in ({"client": 1}, {"client_name": "foreign client"}):
            self.denied("/api/workbench/intake", method="POST", body={"project": "ALPHA", "model": False, **fields})

    def test_hidden_execution_is_not_marked_safe_by_a_data_route(self):
        for path, body in (
            ("/api/tickets", {"project": "ALPHA"}),
            ("/api/tickets", {"project": "ALPHA", "auto": False, "agent": "fixture", "mode": "fix"}),
            ("/api/tickets", {"project": "ALPHA", "auto": False, "code_at": "HEAD"}),
            ("/api/projects/ALPHA/kb/triage", {"request": "route"}),
            ("/api/projects/ALPHA/pins", {}),
            ("/api/tickets/ALPHA-1/claim", {}),
            ("/api/tickets/ALPHA-1/evidence", {"kind": "pack"}),
        ):
            with self.subTest(path=path, body=body):
                self.denied(path, method="POST", body=body)
        self.auth("/api/tickets", method="POST", body={"project": "ALPHA", "auto": False})
        self.auth("/api/tickets", method="POST", body={"project": "ALPHA", "handwork": True})
        self.auth("/api/projects/ALPHA/kb/triage", method="POST", body={"request": "route", "model": False})
        self.auth("/api/projects/ALPHA/intake", method="POST", body={"text": "route", "model": False})

    def test_new_agent_operation_does_not_automatically_inherit_permissions(self):
        from tmh.agent_contract import SPECS
        with patch.dict(SPECS, {"future_global_read": {"write": False, "properties": {}, "required": []}}):
            self.denied("/api/agent/future_global_read", actor="owner", method="POST")

    def test_old_team_receipt_is_not_readable_through_another_project(self):
        team.schema(self.P)
        self.store.x("INSERT INTO team_requests(actor,request_id,ticket_id,fingerprint,state,error,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                     ("alice", "old-beta", self.tickets["BETA"]["id"], "digest", "failed", "private path", "now", "now"))
        self.denied("/api/team", query={"project": ["ALPHA"], "request_id": ["old-beta"]})
        with self.assertRaises(ApiError):
            team.dispatch_read(self.P, {"request_id": "old-beta"}, "alice")
        self.denied("/api/team", query={"request_id": ["old-beta"]})

    def test_equal_ids_in_another_database_do_not_select_another_tenant(self):
        second = Store(self.root / "other" / "platform.db")
        self.addCleanup(second.db.close)
        project = second.add_project("ALPHA", "Other tenant", str(self.context.root / "ALPHA"))
        ticket = second.create_ticket(project["id"], "Other tenant secret", "alice")
        self.assertEqual(ticket["id"], self.tickets["ALPHA"]["id"])
        self.assertEqual(policy._resource_project(self.P, "ticket", ticket["id"])["name"], "ALPHA")
        self.assertNotIn("Other tenant secret", str(self.auth("/api/tickets/ALPHA-1")))

    def test_viewer_cannot_upgrade_with_manager_grant_or_agent_endpoint(self):
        self.auth("/api/tickets/ALPHA-1", actor="reader")
        self.denied("/api/tickets/ALPHA-1/comments", actor="reader", method="POST", body={"body": "no"})
        self.denied("/api/agent/message_send", actor="reader", method="POST",
                    body={"ticket": "ALPHA-1", "body": "no", "request_id": "x"})
        self.auth("/api/agent/ticket_get", actor="reader", method="POST", body={"ticket": "ALPHA-1"})
        self.context.people["bob"]["project_grants"]["ALPHA"] = "viewer"
        self.auth("/api/tickets/ALPHA-1", actor="bob")
        self.denied("/api/tickets/ALPHA-1/comments", actor="bob", method="POST", body={"body": "no"})
        self.denied("/api/assist", actor="reader", query={"project": ["ALPHA"]})
        self.denied("/api/assist", actor="bob", query={"project": ["ALPHA"]})

    def test_agent_lists_and_receipts_fail_closed_without_safe_filters(self):
        for operation in ("projects_list", "tickets_list", "messages_list"):
            self.denied("/api/agent/" + operation, method="POST")
        self.denied("/api/agent/request_get", method="POST", body={"request_id": "old"})
        self.auth("/api/agent/tickets_list", method="POST", body={"project": "ALPHA"})
        self.denied("/api/agent/ticket_get", method="POST", body={"ticket": "BETA-1"})
        self.denied("/api/agent/unknown", actor="owner", method="POST")

    def test_static_and_capability_routes_cannot_skip_policy(self):
        for path in ("/e/BETA-1", "/e/BETA-1.intoto.json", "/e/BETA-1/f/" + "a" * 64 + ".png",
                     "/p/BETA/code.bundle", "/p/BETA/report/index.html", "/p/BETA/efficiency"):
            self.denied(path)
        self.auth("/e/ALPHA-1")
        for prefix in policy.PUBLIC_CAPABILITIES:
            self.denied(prefix + "fixture", actor="owner")
        self.denied("/p/ALPHA/report/index.html", actor="admin")

    def test_managed_preview_and_public_tokens_deny_even_default_owner(self):
        self.context.tenant_id = "default"
        for path, body in (
            ("/api/tickets/ALPHA-1/preview", {"action": "start"}),
            ("/api/projects/ALPHA/standing", {"action": "start"}),
            ("/api/projects/ALPHA/shares", {}),
            ("/api/projects/ALPHA/capture-token", {}),
            ("/api/tickets/ALPHA-1/ask-client", {}),
            ("/api/tickets/ALPHA-1/evidence", {"kind": "link"}),
            ("/api/intake/abcdef012345", {"action": "ask_client"}),
            ("/api/team", {"action": "candidate_preview", "ticket": "ALPHA-1"}),
            ("/api/agent/preview_start", {"ticket": "ALPHA-1", "run_id": self.runs["ALPHA"]["id"], "request_id": "pv"}),
            ("/api/agent/candidate_preview", {"candidate_id": 1, "request_id": "cpv"}),
        ):
            with self.subTest(path=path):
                self.denied(path, actor="owner", method="POST", body=body)
        self.auth("/api/tickets/ALPHA-1/preview", actor="reader")
        self.auth("/api/tickets/ALPHA-1/preview", actor="owner", method="POST", body={"action": "stop"})

    def test_unsafe_execution_denied_before_any_registration(self):
        actions = [
            ("/api/tickets/ALPHA-1/runs", {}), ("/api/tickets/ALPHA-1/preview", {"action": "start"}),
            ("/api/projects/ALPHA/survey", {}), ("/api/projects/ALPHA/library", {"action": "build"}),
            ("/api/learning", {"project": "ALPHA", "action": "review"}),
            ("/api/projects/ALPHA/intake", {"text": "requirement"}),
            ("/api/assist", {"project": "ALPHA", "question": "execute"}),
            ("/api/testbox/check", {}), ("/api/tickets/ALPHA-1/handwork", {}),
        ]
        with patch("subprocess.Popen", side_effect=AssertionError("must not launch")):
            for path, body in actions:
                for actor in ("admin", "owner"):
                    with self.subTest(path=path, actor=actor):
                        self.denied(path, actor=actor, method="POST", body=body)
        self.context.tenant_id = "default"
        self.auth("/api/tickets/ALPHA-1/runs", actor="owner", method="POST")
        self.denied("/api/tickets/ALPHA-1/runs", actor="admin", method="POST")

    def test_path_registration_requires_platform_owner_and_approved_workspace(self):
        payload = {"key": "NEW", "root": str(self.context.root / "ALPHA")}
        self.denied("/api/projects", actor="admin", method="POST", body=payload)
        self.auth("/api/projects", actor="owner", method="POST", body=payload)
        self.denied("/api/projects", actor="owner", method="POST", body=dict(payload, root=str(self.root)))
        self.denied("/api/projects/ALPHA/library", actor="admin", method="POST", body={"action": "add_source", "root": payload["root"]})
        self.denied("/api/projects/bootstrap", actor="owner", method="POST", body={"key": "NEW"})

    def test_library_source_and_derived_destination_stay_in_approved_workspace(self):
        self.context.tenant_id = "default"
        project = self.projects["BETA"]
        source = self.store.one("SELECT * FROM project_sources WHERE project_id=? AND root=?",
                                (project["id"], project["root"]))
        self.assertIsNotNone(source)
        self.assertEqual(source["project_id"], project["id"])
        self.assertEqual(source["root"], project["root"])
        source_id = source["id"]
        with self.assertRaises(ApiError) as caught:
            self.auth("/api/projects/ALPHA/library", actor="owner", method="POST", body={"action": "build", "source_id": source_id})
        self.assertEqual(caught.exception.code, 400)
        self.store.x("INSERT INTO project_sources(project_id,root,label,created) VALUES(?,?,?,?)",
                     (self.projects["ALPHA"]["id"], str(self.root / "private"), "outside", "now"))
        source_id = self.store.one("SELECT id FROM project_sources WHERE label='outside'")["id"]
        self.denied("/api/projects/ALPHA/library", actor="owner", method="POST", body={"action": "build", "source_id": source_id})
        self.auth("/api/projects/ALPHA/library", actor="owner", method="POST", body={"action": "build"})
        self.denied("/api/projects/ALPHA/library", actor="owner", method="POST", body={"action": "derive", "key": "NEW"})

    def test_duplicate_acl_query_is_rejected_instead_of_choosing_first(self):
        with self.assertRaises(ApiError) as caught:
            self.auth("/api/tickets", query={"project": ["ALPHA", "BETA"]})
        self.assertEqual(caught.exception.code, 400)

    def test_file_resource_ownership_lookup_does_not_sweep_or_write(self):
        folder = self.P.data_dir / "intake"
        folder.mkdir()
        item = folder / "abcdef012345.json"
        raw = json.dumps({"project": "BETA", "state": "understanding", "understanding_job": {"t0": 1}})
        item.write_text(raw)
        self.denied("/api/intake/abcdef012345")
        self.assertEqual(item.read_text(), raw)
        item.write_text(json.dumps({"project": "ALPHA"}))
        self.auth("/api/intake/abcdef012345")

    def test_member_selection_uses_registry_project_permissions_without_local_users(self):
        self.assertFalse((self.P.data_dir / "users.json").exists())
        self.assertEqual(policy.eligible_members(self.P, "ALPHA"), ["admin", "alice", "bob", "owner"])
        self.auth("/api/team", method="POST", body={"ticket": "ALPHA-1", "action": "assign", "assignee": "bob"})
        self.denied("/api/team", actor="bob", method="POST", body={"ticket": "ALPHA-1", "action": "assign"})
        self.denied("/api/team", method="POST", body={"ticket": "ALPHA-1", "action": "assign", "assignee": "outsider"})
        self.denied("/api/tickets/ALPHA-1", actor="bob", method="POST", body={"assignee": "bob"})

    def test_handoff_member_revocation_prevents_replay_without_changing_history(self):
        ticket = self.tickets["ALPHA"]
        v = handoffs.read(self.P, ticket["key"], "alice")
        body = {"ticket": ticket["key"], "action": "send", "revision": 0, "request_id": "h1",
                "note": "full note", "materials": "full materials", "stage": "testing", "receiver": "bob", "source_token": v["source_token"]}
        result = handoffs.dispatch_action(self.P, body, "alice")
        self.assertEqual(result["current"]["receiver"], "bob")
        before = dump_store(self.store)
        self.context.people["alice"]["project_grants"] = {}
        with self.assertRaises(ApiError):
            handoffs.dispatch_action(self.P, body, "alice")
        self.assertEqual(dump_store(self.store), before)
        self.context.people["bob"]["project_grants"] = {}
        view = handoffs.read(self.P, ticket["key"], "admin")
        self.assertFalse(view["current"]["receiver_active"])
        self.assertNotIn("bob", [x["id"] for x in view["members"]])

    def test_handoff_cannot_send_to_another_projects_member(self):
        v = handoffs.read(self.P, "ALPHA-1", "alice")
        body = {"ticket": "ALPHA-1", "action": "send", "revision": 0, "request_id": "h1", "note": "full",
                "stage": "testing", "receiver": "outsider", "source_token": v["source_token"]}
        before = dump_store(self.store)
        with self.assertRaises(ApiError):
            handoffs.dispatch_action(self.P, body, "alice")
        self.assertEqual(dump_store(self.store), before)

    def test_assignment_checks_project_members_and_preserves_independent_review(self):
        ticket = self.tickets["ALPHA"]
        team.schema(self.P)
        body = {"action": "assign", "ticket": ticket["key"], "assignee": "alice", "reviewer": "outsider", "revision": 0, "previous_assignee": "alice"}
        before = dump_store(self.store)
        with self.assertRaises(ApiError):
            team._assign(self.P, ticket, body, "alice")
        self.assertEqual(dump_store(self.store), before)
        body["reviewer"] = "bob"
        team._assign(self.P, ticket, body, "alice")
        team.require_reviewer(self.P, ticket, "bob")
        with self.assertRaises(ApiError):
            team.require_reviewer(self.P, ticket, "owner")
        self.context.people["bob"]["project_grants"] = {}
        with self.assertRaises(ApiError):
            team.require_reviewer(self.P, ticket, "bob")

    def test_team_reads_and_mutation_recheck_current_grants(self):
        with self.assertRaises(ApiError):
            team.dispatch_read(self.P, {"project": "BETA"}, "alice")
        with self.assertRaises(ApiError):
            team.dispatch_read(self.P, {"view": "team"}, "alice")
        team.schema(self.P)
        def revoke_then_write(mutation):
            self.context.people["alice"]["project_grants"] = {}
            mutation()
            self.fail("revoked mutation was allowed")
        with self.assertRaises(ApiError):
            team._request(self.P, self.tickets["ALPHA"], "alice", {"action": "comment", "request_id": "revoked"}, revoke_then_write)
        self.assertEqual(self.store.one("SELECT state FROM team_requests WHERE request_id='revoked'")["state"], "failed")

    def test_legacy_mode_preserves_existing_authorization_contract(self):
        del self.P.tenant_context
        self.assertEqual(len(policy.visible_projects(self.P, "")), 2)
        self.assertTrue(self.auth("/legacy-unregistered", actor="", method="POST")["legacy"])
        policy.require_execution(self.P, "")


if __name__ == "__main__":
    unittest.main()
