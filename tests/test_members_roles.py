"""Single-machine roles: first account is the owner; viewers read only; editors change except owner-only settings and members."""
import tempfile
import unittest
from pathlib import Path

from tmh.platform import login as L
from tmh.platform import members
from tmh.platform.errors import ApiError


class RolesTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-roles-")
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        L.set_user(self.data, "owner1", "owner-pass-1")
        L.set_user(self.data, "ed1", "editor-pass-1")
        L.set_user(self.data, "view1", "viewer-pass-1")
        L.set_role(self.data, "ed1", "editor")
        L.set_role(self.data, "view1", "viewer")

    def test_first_account_is_owner_and_legacy_single_account_becomes_owner(self):
        self.assertEqual(L.role_of(self.data, "owner1"), "owner")
        legacy = Path(tempfile.mkdtemp(prefix="tmh-legacy-"))
        L._save_users(legacy, {"only": {"pw": L.hash_password("x-pass-123")}})
        self.assertEqual(L.role_of(legacy, "only"), "owner")

    def test_viewer_reads_only(self):
        self.assertTrue(L.allowed("viewer", "GET", "/api/projects"))
        self.assertTrue(L.allowed("viewer", "HEAD", "/api/projects"))
        self.assertFalse(L.allowed("viewer", "POST", "/api/tickets"))
        self.assertFalse(L.allowed("viewer", "POST", "/api/projects/X/tasks"))

    def test_editor_changes_work_but_not_owner_only_routes(self):
        self.assertTrue(L.allowed("editor", "POST", "/api/projects/X/tasks"))
        self.assertTrue(L.allowed("editor", "POST", "/api/tickets"))
        for path in ("/api/agent-settings", "/api/agent-page", "/api/agent-test", "/api/agent-scan",
                     "/api/access-config", "/api/members"):
            with self.subTest(path=path):
                self.assertFalse(L.allowed("editor", "POST", path))
                self.assertFalse(L.allowed("editor", "GET", path))

    def test_owner_is_allowed_everything(self):
        self.assertTrue(L.allowed("owner", "POST", "/api/members"))
        self.assertTrue(L.allowed("owner", "POST", "/api/agent-settings"))

    def test_viewer_is_refused_owner_routes_too(self):
        self.assertFalse(L.allowed("viewer", "GET", "/api/members"))

    def test_owner_adds_removes_changes_roles_and_resets_password(self):
        members.add(self.data, "newbie", "newbie-pass-1", "viewer")
        self.assertEqual(L.role_of(self.data, "newbie"), "viewer")
        members.set_role(self.data, "newbie", "editor", "owner1")
        self.assertEqual(L.role_of(self.data, "newbie"), "editor")
        members.reset_password(self.data, "newbie", "reset-pass-99")
        self.assertTrue(L.verify(self.data, "newbie", "reset-pass-99"))
        self.assertFalse(L.verify(self.data, "newbie", "newbie-pass-1"))
        members.remove(self.data, "newbie", "owner1")
        self.assertEqual(L.role_of(self.data, "newbie"), "")

    def test_cannot_remove_yourself_or_the_last_owner_or_demote_yourself(self):
        with self.assertRaises(ValueError):
            members.remove(self.data, "owner1", "owner1")
        with self.assertRaises(ValueError):
            members.set_role(self.data, "owner1", "editor", "owner1")
        with self.assertRaises(ValueError):
            members.set_role(self.data, "owner1", "viewer", "ed1")

    def test_new_member_cannot_be_owner(self):
        with self.assertRaises(ValueError):
            members.add(self.data, "second", "second-pass-1", "owner")


if __name__ == "__main__":
    unittest.main()
