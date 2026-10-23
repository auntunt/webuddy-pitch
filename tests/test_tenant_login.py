"""Session credentials bind an account version in legacy and tenant modes."""
from pathlib import Path
import json
import tempfile
import unittest

from tmh.platform import login, tenancy


class TenantLoginTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="tmh-tenant-login-")
        self.addCleanup(tmp.cleanup)
        self.data = Path(tmp.name)
        login.set_user(self.data, "owner", "synthetic-password")
        login.set_user(self.data, "alice", "synthetic-password")

    def test_legacy_password_change_and_removal_invalidate_sessions(self):
        cookie = login.make_session(self.data, "alice")
        self.assertEqual(login.read_session(self.data, cookie), "alice")
        login.set_user(self.data, "alice", "new-synthetic-password")
        self.assertEqual(login.read_session(self.data, cookie), "")
        cookie = login.make_session(self.data, "alice")
        login.del_user(self.data, "alice")
        self.assertEqual(login.read_session(self.data, cookie), "")
        login.set_user(self.data, "alice", "new-synthetic-password")
        self.assertEqual(login.read_session(self.data, cookie), "")

    def test_legacy_disable_invalidate_session_and_password_verification(self):
        cookie = login.make_session(self.data, "alice")
        users = login.load_users(self.data)
        users["alice"]["disabled"] = True
        login._save_users(self.data, users)
        self.assertEqual(login.read_session(self.data, cookie), "")
        self.assertFalse(login.verify(self.data, "alice", "synthetic-password"))

    def test_disabled_accounts_do_not_disable_authentication_or_get_dropped(self):
        users = login.load_users(self.data)
        for record in users.values():
            record["disabled"] = True
        login._save_users(self.data, users)
        self.assertEqual(login.load_users(self.data), {})
        self.assertTrue(login.has_accounts(self.data))
        login.set_user(self.data, "owner", "reset-synthetic-password")
        saved = json.loads((self.data / "users.json").read_text())
        self.assertIn("alice", saved)
        self.assertTrue(saved["alice"]["disabled"])
        self.assertNotIn("alice", login.load_users(self.data))

    def test_registry_password_disable_enable_and_cli_reset_never_restore_old_cookie(self):
        reg = tenancy.Registry(self.data, bootstrap_owner="owner")
        self.addCleanup(reg.close)
        def action(name, **args):
            rev = reg.context("owner")["revision"]
            return reg.dispatch("owner", {"action": name, "tenant": "default", "revision": rev, "request_id": "r-%s" % rev, "user": "alice", **args})
        cookie = login.make_session(self.data, "alice")
        action("password_reset", password="new-synthetic-password")
        self.assertEqual(login.read_session(self.data, cookie), "")
        cookie = login.make_session(self.data, "alice")
        action("account_disable")
        self.assertEqual(login.read_session(self.data, cookie), "")
        action("account_enable")
        self.assertEqual(login.read_session(self.data, cookie), "")
        cookie = login.make_session(self.data, "alice")
        login.set_user(self.data, "alice", "cli-synthetic-password")
        self.assertEqual(login.read_session(self.data, cookie), "")
        self.assertTrue(login.verify(self.data, "alice", "cli-synthetic-password"))
        self.assertTrue(login.del_user(self.data, "alice"))
        self.assertFalse(login.del_user(self.data, "alice"))

    def test_bootstrap_invalidates_legacy_cookies_without_touching_legacy_file(self):
        cookie = login.make_session(self.data, "alice")
        before = (self.data / "users.json").read_bytes()
        reg = tenancy.Registry(self.data, bootstrap_owner="owner")
        self.addCleanup(reg.close)
        self.assertEqual(login.read_session(self.data, cookie), "")
        self.assertEqual((self.data / "users.json").read_bytes(), before)
        self.assertEqual(login.read_session(self.data, login.make_session(self.data, "alice")), "alice")

    def test_cookie_for_one_control_plane_is_not_valid_in_another(self):
        other = self.data / "other"
        other.mkdir()
        login.set_user(other, "alice", "synthetic-password")
        self.assertEqual(login.read_session(other, login.make_session(self.data, "alice")), "")


if __name__ == "__main__":
    unittest.main()
