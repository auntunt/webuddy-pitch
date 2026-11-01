import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tmh.platform import announce, chat, repo_sync


def git(root, *a):
    return subprocess.run(["git", "-C", str(root)] + list(a), capture_output=True, text=True, check=True).stdout.strip()


class ParseTest(unittest.TestCase):
    def test_forms(self):
        want = {"host": "github.com", "owner": "auntunt", "repo": "JeecgBoot"}
        for u in ("git@github.com:auntunt/JeecgBoot.git", "https://github.com/auntunt/JeecgBoot", "ssh://git@github.com/auntunt/JeecgBoot.git",
                  "auntunt/JeecgBoot", "https://github.com/auntunt/JeecgBoot.git/"):
            self.assertEqual(repo_sync.parse(u), want, u)

    def test_refuses_credentials_and_other_hosts(self):
        for u in ("https://user:tok@github.com/a/b", "https://gitlab.com/a/b", "", "a", "git@github.com:a/b;rm -rf"):
            with self.assertRaises(ValueError):
                repo_sync.parse(u)

    def test_links(self):
        c = repo_sync.parse("a/b")
        self.assertEqual(repo_sync.ssh_url(c), "git@github.com:a/b.git")
        self.assertEqual(repo_sync.web(c, "branch", "webuddy/JB"), "https://github.com/a/b/tree/webuddy/JB")


@unittest.skipUnless(shutil.which("ssh-keygen"), "needs ssh-keygen")
class PushTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tmh-rs-"))
        self.root, self.bare, self.data = self.tmp / "proj", self.tmp / "remote.git", self.tmp / "data"
        self.data.mkdir()
        (self.data / "autoflow.json").write_text('{"on": false}', encoding="utf-8")
        subprocess.run(["git", "init", "-q", "--bare", str(self.bare)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.root)], check=True)
        (self.root / "a.txt").write_text("1\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        self.P = SimpleNamespace(data_dir=self.data)
        self.p = {"key": "JB", "root": str(self.root)}

    def test_bind_makes_a_private_key_and_pushing_waits_for_a_passed_check(self):
        v = repo_sync.setup(self.P, self.p, "https://github.com/auntunt/JeecgBoot", "li")
        self.assertEqual((v["name"], v["on"], v["url"]), ("auntunt/JeecgBoot", False, "git@github.com:auntunt/JeecgBoot.git"))
        self.assertTrue(v["deploy_key"].startswith("ssh-ed25519 "))
        key = repo_sync.key_file(self.data, "JB")
        if os.name == "posix":
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("PRIVATE", json.dumps(v))
        self.assertEqual(git(self.root, "config", "--get", "remote.webuddy.url"), "git@github.com:auntunt/JeecgBoot.git")
        with self.assertRaises(ValueError):
            repo_sync.switch(self.P, self.p, True, "li")
        self.assertEqual(repo_sync.push(self.P, self.p, ["main"])["state"], "off")
        again = repo_sync.setup(self.P, self.p, "git@github.com:auntunt/JeecgBoot.git", "li")
        self.assertEqual(again["deploy_key"], v["deploy_key"])  # one key per project, made once

    def test_push_is_a_plain_fast_forward_of_named_refs(self):
        repo_sync.setup(self.P, self.p, "auntunt/JeecgBoot", "li")
        git(self.root, "remote", "set-url", "webuddy", str(self.bare))  # a local stand-in for GitHub
        self.assertEqual(repo_sync.check(self.P, self.p)["checked"], "ok")
        self.assertTrue(repo_sync.switch(self.P, self.p, True, "li")["on"])
        git(self.root, "branch", "tmh/JB-1-r1")
        git(self.root, "tag", "-a", "webuddy-JB-1", "-m", "v")
        r = repo_sync.push(self.P, self.p, ["main", "tmh/JB-1-r1", "webuddy-JB-1", "", "missing", "main..x"])
        self.assertEqual(r["state"], "pushed", r)
        self.assertEqual(r["refs"], ["refs/heads/main", "refs/heads/tmh/JB-1-r1", "refs/tags/webuddy-JB-1"])
        self.assertEqual(git(self.bare, "rev-parse", "main"), git(self.root, "rev-parse", "main"))
        self.assertIn("https://github.com/auntunt/JeecgBoot/tree/tmh/JB-1-r1", r["links"])
        # history rewritten here is never forced over the remote
        (self.root / "a.txt").write_text("2\n", encoding="utf-8")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "x")
        git(self.root, "reset", "-q", "--hard", "HEAD~1")
        (self.root / "a.txt").write_text("3\n", encoding="utf-8")
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "y")
        before = git(self.bare, "rev-parse", "main")
        git(self.root, "push", "-q", str(self.bare), "HEAD~1:refs/heads/side")
        git(self.bare, "update-ref", "refs/heads/main", git(self.bare, "rev-parse", "side"))
        git(self.bare, "commit-tree", "-m", "other", git(self.bare, "rev-parse", "main^{tree}"))
        other = git(self.bare, "commit-tree", "-p", "main", "-m", "theirs", git(self.bare, "rev-parse", "main^{tree}"))
        git(self.bare, "update-ref", "refs/heads/main", other)
        r = repo_sync.push(self.P, self.p, ["main"])
        self.assertEqual(r["state"], "failed", r)
        self.assertEqual(git(self.bare, "rev-parse", "main"), other)
        self.assertNotEqual(before, other)

    def test_failed_check_turns_pushing_off(self):
        repo_sync.setup(self.P, self.p, "auntunt/JeecgBoot", "li")
        git(self.root, "remote", "set-url", "webuddy", str(self.tmp / "nowhere.git"))
        v = repo_sync.check(self.P, self.p)
        self.assertNotEqual(v["checked"], "ok")
        self.assertFalse(v["on"])


class AnnounceTest(unittest.TestCase):
    def setUp(self):
        from tmh import bots
        self.tmp = Path(tempfile.mkdtemp(prefix="tmh-an-"))
        self.data, self.root = self.tmp / "data", self.tmp / "proj"
        self.data.mkdir()
        (self.root / ".tmh").mkdir(parents=True)
        (self.root / ".tmh" / "config.json").write_text(json.dumps({"bots": {"feishu": {"app_id_env": "X"}}}), encoding="utf-8")
        (self.data / "autoflow.json").write_text("{}", encoding="utf-8")
        chat._save(self.data, "convs.json", {
            "JB:feishu:oc_abcdef123456": {"project": "JB", "channel": "feishu", "tickets": [], "seen": "2026-10-31 10:00:00",
                                          "dest": {"kind": "feishu", "chat_id": "oc_abcdef123456"}},
            "JB:api:x": {"project": "JB", "channel": "api", "dest": {"kind": "api"}},
            "OA:feishu:oc_other": {"project": "OA", "channel": "feishu", "dest": {"kind": "feishu", "chat_id": "oc_other"}}})
        self.sent, self.events = [], []
        self._send, self._async = bots.send, bots.ASYNC
        bots.send, bots.ASYNC = (lambda root, dest, text: self.sent.append((dest["chat_id"], text)) or True), False
        self.addCleanup(setattr, bots, "send", self._send)
        self.addCleanup(setattr, bots, "ASYNC", self._async)
        store = SimpleNamespace(event=lambda tid, by, kind, body, data=None: self.events.append((tid, kind, body)))
        self.P = SimpleNamespace(data_dir=self.data, root=lambda p: self.root, store=store, public_url="https://webuddy.example")
        self.p = {"key": "JB", "root": str(self.root)}

    def test_only_the_projects_own_reachable_groups_can_be_bound(self):
        self.assertEqual([x["id"] for x in announce.targets(self.P, self.p)], ["JB:feishu:oc_abcdef123456"])
        for bad in ("OA:feishu:oc_other", "JB:api:x", "nope"):
            with self.assertRaises(ValueError):
                announce.bind(self.P, self.p, bad, "li")
        self.assertFalse(announce.say(self.P, self.p, "x"))
        self.assertEqual(self.sent, [])

    def test_bound_group_hears_with_a_link_and_the_ticket_notes_it(self):
        v = announce.bind(self.P, self.p, "JB:feishu:oc_abcdef123456", "li")
        self.assertTrue(v["bound"])
        self.assertTrue(announce.say(self.P, self.p, "**JB-1 标题** 验收通过", {"id": 7, "key": "JB-1"}))
        self.assertEqual(self.sent, [("oc_abcdef123456", "**JB-1 标题** 验收通过\n[打开工单](https://webuddy.example/#/t/JB-1)")])
        self.assertEqual(self.events, [(7, "chat", "已告知项目群：**JB-1 标题** 验收通过")])
        self.assertFalse(announce.bind(self.P, self.p, "", "li")["bound"])

    def test_a_failing_send_never_raises(self):
        from tmh import bots
        announce.bind(self.P, self.p, "JB:feishu:oc_abcdef123456", "li")

        def boom(*a):
            raise RuntimeError("飞书取 token 失败")
        bots.send = boom
        self.assertTrue(announce.say(self.P, self.p, "x", {"id": 1, "key": "JB-1"}))
        self.assertIn("没能告知项目群", self.events[-1][2])


if __name__ == "__main__":
    unittest.main()
