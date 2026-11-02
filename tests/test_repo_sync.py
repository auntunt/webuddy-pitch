import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tmh.platform import announce, chat, repo_sync


ID = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(root, *a):
    return subprocess.run(["git", "-C", str(root)] + list(a), capture_output=True, text=True, check=True,
                          env=dict(os.environ, **ID)).stdout.strip()


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

    def test_own_machine_over_ssh(self):
        c = repo_sync.parse("ssh://auntu@127.0.0.1:12122/home/auntu/git/JeecgBoot.git")
        self.assertEqual((c["kind"], c["host"], c["port"], c["user"], c["path"], c["repo"]),
                         ("ssh", "127.0.0.1", 12122, "auntu", "/home/auntu/git/JeecgBoot.git", "JeecgBoot"))
        self.assertEqual(repo_sync.ssh_url(c), "ssh://auntu@127.0.0.1:12122/home/auntu/git/JeecgBoot.git")
        self.assertEqual(repo_sync.web(c, "branch", "x"), "")
        self.assertEqual(repo_sync.ssh_url(repo_sync.parse("ssh://git@box/srv/r")), "ssh://git@box/srv/r.git")
        for u in ("ssh://a@box/srv/../etc/r.git", "ssh://a@box:0/r.git", "ssh://a:pw@box/r.git", "ssh://a@box/r;x"):
            with self.assertRaises(ValueError, msg=u):
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
        git(self.root, "-c", "user.name=t", "-c", "user.email=t@t", "tag", "-a", "webuddy-JB-1", "-m", "v")
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
        other = git(self.bare, "commit-tree", "-p", "main", "-m", "theirs", git(self.bare, "rev-parse", "main^{tree}"))
        git(self.bare, "update-ref", "refs/heads/main", other)
        r = repo_sync.push(self.P, self.p, ["main"])
        self.assertEqual(r["state"], "failed", r)
        self.assertEqual(git(self.bare, "rev-parse", "main"), other)
        self.assertNotEqual(before, other)

    def test_own_machine_pins_its_host_key_and_pushes_without_links(self):
        line = "box ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEksQiCERg4aRfId+z7zWMp0bLWR28PNyM4RFs9HSozk"
        with self.assertRaises(ValueError):
            repo_sync.setup(self.P, self.p, "ssh://git@box:2222/srv/JB.git", "li", hostkey="not a key")
        v = repo_sync.setup(self.P, self.p, "ssh://git@box:2222/srv/JB.git", "li", hostkey=line, label="测试机")
        self.assertEqual((v["kind"], v["name"], v["web"], v["deploy_keys_page"]), ("ssh", "测试机", "", ""))
        self.assertTrue(v["hostkey"].startswith("SHA256:"))
        conf = json.loads((self.data / "autoflow.json").read_text(encoding="utf-8"))["repos"]["JB"]
        self.assertEqual(conf["hostkey"], "[box]:2222 " + line.split(" ", 1)[1])  # pinned for that port only
        env = repo_sync._env(self.data, "JB", conf)
        self.assertIn("StrictHostKeyChecking=yes", env["GIT_SSH_COMMAND"])
        self.assertEqual((self.data / "keys" / "JB-known_hosts").read_text(encoding="utf-8").strip(), conf["hostkey"])
        git(self.root, "remote", "set-url", "webuddy", str(self.bare))
        self.assertEqual(repo_sync.check(self.P, self.p)["checked"], "ok")
        repo_sync.switch(self.P, self.p, True, "li")
        r = repo_sync.push(self.P, self.p, ["main"])
        self.assertEqual((r["state"], r["repo"], r["links"]), ("pushed", "测试机", []))

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
        bots.send, bots.ASYNC = (lambda root, dest, text, **kw: self.sent.append((dest["chat_id"], text, kw)) or True), False
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
        self.assertEqual(self.sent, [("oc_abcdef123456", "**JB-1 标题** 验收通过", {
            "title": "JB · 项目通知", "url": "https://webuddy.example/#/t/JB-1", "button": "打开工单", "tone": "blue"})])
        self.assertEqual(self.events, [(7, "chat", "已告知项目群：**JB-1 标题** 验收通过")])
        self.assertFalse(announce.bind(self.P, self.p, "", "li")["bound"])

    def test_without_a_ticket_the_card_opens_webuddy(self):
        announce.bind(self.P, self.p, "JB:feishu:oc_abcdef123456", "li")
        announce.say(self.P, self.p, "回滚了", title="版本已回滚", tone="red")
        self.assertEqual(self.sent[-1][2], {"title": "JB · 版本已回滚", "url": "https://webuddy.example/", "button": "打开 Webuddy", "tone": "red"})

    def test_a_failing_send_never_raises(self):
        from tmh import bots
        announce.bind(self.P, self.p, "JB:feishu:oc_abcdef123456", "li")

        def boom(*a):
            raise RuntimeError("飞书取 token 失败")
        bots.send = boom
        self.assertTrue(announce.say(self.P, self.p, "x", {"id": 1, "key": "JB-1"}))
        self.assertIn("没能告知项目群", self.events[-1][2])


class CardTest(unittest.TestCase):
    def setUp(self):
        from tmh import bots
        self.tmp = Path(tempfile.mkdtemp(prefix="tmh-card-"))
        (self.tmp / ".tmh").mkdir()
        (self.tmp / ".tmh" / "config.json").write_text(json.dumps({"bots": {
            "feishu": {"app_id_env": "X"}, "dingtalk": {"secret_env": "Y"}}}), encoding="utf-8")
        self.calls = []
        self._http, self._tok = bots._http, bots._feishu_token
        bots._http = lambda url, body=None, headers=None, timeout=15: self.calls.append((url, body)) or {"code": 0}
        bots._feishu_token = lambda c: "t"
        self.addCleanup(setattr, bots, "_http", self._http)
        self.addCleanup(setattr, bots, "_feishu_token", self._tok)

    def test_feishu_card_has_a_title_and_a_button_to_webuddy(self):
        from tmh import bots
        self.assertTrue(bots.send(self.tmp, {"kind": "feishu", "chat_id": "oc_1"}, "**JB-1** 通过", title="JB · 已出版本",
                                  url="https://w.example/#/t/JB-1", button="打开工单", tone="green"))
        card = json.loads(self.calls[0][1]["content"])
        self.assertEqual(self.calls[0][1]["msg_type"], "interactive")
        self.assertEqual(card["header"], {"title": {"tag": "plain_text", "content": "JB · 已出版本"}, "template": "green"})
        self.assertEqual(card["elements"][0], {"tag": "markdown", "content": "**JB-1** 通过"})
        btn = card["elements"][1]["actions"][0]
        self.assertEqual((btn["text"]["content"], btn["url"]), ("打开工单", "https://w.example/#/t/JB-1"))

    def test_plain_card_without_title_or_link(self):
        from tmh import bots
        card = bots.feishu_card("hi")
        self.assertNotIn("header", card)
        self.assertEqual(len(card["elements"]), 1)

    def test_other_channels_get_the_link_as_markdown(self):
        from tmh import bots
        bots.send(self.tmp, {"kind": "dingtalk", "hook": "https://oapi.example/x"}, "正文", title="标题", url="https://w.example/")
        self.assertEqual(self.calls[0][1]["markdown"]["text"], "**标题**\n\n正文\n\n[打开 Webuddy](https://w.example/)")

    def test_intake_may_answer_with_a_card(self):
        from tmh import bots
        old = bots.INTAKE
        self.addCleanup(setattr, bots, "INTAKE", old)
        bots.INTAKE = lambda root, text, channel, sender, conv: {"kind": "brief", "title": "简报", "reply": "2 个项目", "url": "https://w.example/"}
        r = bots.handle(self.tmp, "@_user_1 简报", "feishu", "ou_1", use_model=False, conv={"id": "oc_1"})
        self.assertEqual((r["kind"], r["title"], r["reply"], r["url"]), ("brief", "简报", "2 个项目", "https://w.example/"))


class BriefTest(unittest.TestCase):
    def test_platform_questions_are_told_apart_from_requirements(self):
        for t in ("简报", "概况。", "帮我看看我们有多少项目在你管理下", "平台上接入了哪些项目？"):
            self.assertTrue(chat.wants_brief(t), t)
        for t in ("项目状态显示错了", "这个部门有多少项目", "导出项目列表时报错", "简报页面打不开"):
            self.assertFalse(chat.wants_brief(t), t)

    def test_brief_counts_each_project(self):
        import time
        today = time.strftime("%Y-%m-%d")
        ps = [{"id": 1, "key": "JB", "name": "JeecgBoot"}, {"id": 2, "key": "OA", "name": ""}]
        ib = {1: {"mine": [{"key": "JB-5", "title": "登录页", "label": "改好了，等你验收"}], "open": 3, "running": 1},
              2: {"mine": [], "open": 0, "running": 0}}
        store = SimpleNamespace(projects=lambda: ps, one=lambda sql, a: {"n": 2 if a[0] == 1 and a[1] == today else 0})
        P = SimpleNamespace(store=store, inbox=lambda p: ib[p["id"]], public_url="https://w.example")
        r = chat.brief(P)
        self.assertEqual((r["kind"], r["url"], r["button"]), ("brief", "https://w.example/", "打开 Webuddy"))
        self.assertIn("管理 **2** 个项目", r["reply"])
        self.assertIn("**JB** JeecgBoot：等你处理 1 · 未关单 3 · 进行中 1 · 今天关单 2", r["reply"])
        self.assertIn("JB-5 登录页（改好了，等你验收）", r["reply"])


if __name__ == "__main__":
    unittest.main()
