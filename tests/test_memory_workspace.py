"""Memory workspace contracts: provenance, conservative reuse and immutable history."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from tmh.platform import learn, memory, org_knowledge
from tmh.platform.errors import ApiError
from tmh.platform.store import Store
from tmh.platform.ui_memory import MEMORY_JS


class MemoryWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tmh-memory-")
        self.data = Path(self.tmp.name)
        self.store = Store(self.data / "platform.db")
        self.P = SimpleNamespace(store=self.store, data_dir=self.data)
        self.roots = {}
        for key in ("APP", "OTHER"):
            root = self.data / key
            root.mkdir()
            self.roots[key] = root
            self.store.add_project(key, key + " 项目", str(root), "用于维护审批业务。")
        self.p = self.store.project("APP")

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def ticket(self, title="审批回调重复写入状态错误", body="审批回调重复写入状态导致重复通知和记录", project="APP", **kw):
        return self.store.create_ticket(self.store.project(project)["id"], title, "提交人", body=body,
                                        links=kw.pop("links", {"flows": ["flow:approval"]}), **kw)

    def act(self, action, **body):
        return memory.dispatch_action(self.P, {"action": action, "project": "APP", **body}, "reviewer")

    def page(self, text="审批通过后记录审批人。", project="APP"):
        path = self.roots[project] / ".tmh/knowledge/flows/approval.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\nid: flow:approval\ntitle: 审批通过\nstatus: 已确认\n---\n# 审批通过\n\n" + text, encoding="utf-8")
        return path

    def lesson(self, project="APP", status="active", **fields):
        return learn.add_lesson(self.data, {"project": project, "title": "审批回调重复写入状态错误", "status": status,
                                "symptom": "审批回调重复写入状态导致重复通知", "fix": "检查回调幂等键并加重复通知测试",
                                "verify": "同一回调两次只通知一次", "flows": ["flow:approval"], **fields})

    def test_read_only_preview_preserves_store_source_and_no_memory_files(self):
        self.page()
        t = self.ticket(body="原始需求" * 1000)
        before = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.data.rglob("*") if p.is_file()}
        result = memory.dispatch_read(self.P, {"project": "APP"}, "reader")
        brief = memory.read_brief(self.P, "APP")
        self.assertIn(t["body"], brief["markdown"])
        self.assertIn("审批通过后记录审批人", brief["markdown"])
        self.assertEqual(result["brief"]["status"], "preview")
        self.assertFalse((self.data / "memory").exists())
        after = {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in self.data.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_clusters_same_project_explainable_keep_full_tickets_and_stable_revision(self):
        t1, t2 = self.ticket(), self.ticket(body="审批回调重复写入状态导致重复通知和记录。请保留接口")
        self.ticket(project="OTHER")
        original = self.store.ticket(t1["id"])
        result = self.act("cluster_scan")
        self.assertEqual(len(result["items"]), 1)
        c = result["items"][0]
        self.assertEqual({m["key"] for m in c["members"]}, {t1["key"], t2["key"]})
        self.assertTrue(any("相同业务流" in r for r in c["matches"][0]["reasons"]))
        self.assertEqual(c["members"][0]["body"], t1["body"])
        self.assertEqual(self.store.ticket(t1["id"]), original)
        again = self.act("cluster_scan")["items"][0]
        self.assertEqual((c["id"], c["revision"]), (again["id"], again["revision"]))
        self.assertEqual(len(again["history"]), 1)
        self.assertEqual(again["history"][0]["by"], "reviewer")

    def test_cluster_exposes_only_member_lessons_as_reuse_evidence(self):
        a, b = self.ticket(), self.ticket()
        linked = self.lesson(ticket=a["key"])
        self.lesson(ticket="APP-999")
        self.lesson(project="OTHER", ticket="OTHER-1")
        c = memory.clusters(self.P, "APP")["items"][0]
        self.assertEqual([l["id"] for l in c["lessons"]], [linked["id"]])
        self.assertEqual(c["lessons"][0]["ticket"], a["key"])

    def test_http_query_shape_is_accepted_without_cross_project_fallback(self):
        self.lesson()
        self.lesson(project="OTHER", title="另一个项目的私有记忆")
        result = memory.dispatch_read(self.P, {"project": ["APP"], "section": ["lessons"], "q": [""]}, "reader")
        self.assertEqual(len(result["lessons"]), 1)
        self.assertEqual(result["project"]["key"], "APP")
        with self.assertRaises(ApiError):
            memory.dispatch_read(self.P, {"project": ["APP", "OTHER"]}, "reader")

    def test_generic_text_and_same_named_other_project_do_not_cluster(self):
        self.ticket("系统报错", "系统有问题需要修复", links={})
        self.ticket("系统报错", "系统有问题需要修复", links={})
        self.ticket("系统报错", "系统有问题需要修复", project="OTHER", links={})
        self.assertEqual(memory.clusters(self.P, "APP")["items"], [])

    def test_similarity_features_do_not_mutate_ticket_files(self):
        t = self.ticket(body="检查 src/Approval.java 回调审批幂等", links={"files": ["src/Existing.java"]})
        original = copy.deepcopy(t)
        memory._features(t)
        memory._features(t)
        self.assertEqual(t, original)

    def test_complete_link_does_not_chain_unrelated_endpoints(self):
        a = self.ticket(links={"flows": ["flow:a"]})
        b = self.ticket(links={"flows": ["flow:a", "flow:b"]})
        c = self.ticket("回调审批重复记录通知错误", links={"flows": ["flow:b"]})
        groups = memory.clusters(self.P, "APP")["items"]
        self.assertEqual(len(groups), 1)
        self.assertEqual({m["key"] for m in groups[0]["members"]}, {a["key"], b["key"]})
        self.assertNotIn(c["key"], {m["key"] for m in groups[0]["members"]})

    def test_confirm_exclusion_and_rescan_preserve_actor_history_and_exclusion(self):
        a, b, c = self.ticket(), self.ticket(), self.ticket()
        cluster = self.act("cluster_scan")["items"][0]
        confirmed = self.act("cluster_confirm", cluster_id=cluster["id"], expected_fingerprint=cluster["fingerprint"])
        self.assertEqual(confirmed["confirmed_by"], "reviewer")
        excluded = self.act("cluster_exclude", cluster_id=confirmed["id"], expected_fingerprint=confirmed["fingerprint"],
                            ticket_key=a["key"], reason="同名回调，实际是另一个根因")
        self.assertEqual(excluded["exclusions"][0]["by"], "reviewer")
        after = self.act("cluster_scan")["items"][0]
        self.assertEqual(after["id"], cluster["id"])
        self.assertNotIn(a["key"], {m["key"] for m in after["members"]})
        self.assertTrue(all(x["key"] != a["key"] for x in memory.similar_tickets(self.P, b)))
        self.assertEqual(self.store.ticket(a["id"])["status"], "new")
        self.assertGreaterEqual(len(after["history"]), 3)

    def test_changed_ticket_requires_new_confirmation_with_fresh_fingerprint(self):
        a, b = self.ticket(), self.ticket()
        c = self.act("cluster_scan")["items"][0]
        self.act("cluster_confirm", cluster_id=c["id"], expected_fingerprint=c["fingerprint"])
        self.store.update_ticket(b["id"], "editor", body=b["body"] + "，增加回归验证")
        with self.assertRaises(ApiError) as ctx:
            self.act("cluster_confirm", cluster_id=c["id"], expected_fingerprint=c["fingerprint"])
        self.assertEqual(ctx.exception.code, 409)
        current = memory.clusters(self.P, "APP")["items"][0]
        self.assertEqual(current["status"], "candidate")
        self.assertEqual(current["id"], c["id"])

    def test_brief_version_history_and_changed_page_cannot_be_confirmed_as_current(self):
        page = self.page("第一版说明\n\n" + "完整原文" * 500)
        first = self.act("brief_generate")
        self.assertIn("完整原文" * 500, first["markdown"])
        same = self.act("brief_generate")
        self.assertTrue(same["unchanged"])
        self.act("brief_confirm", revision=first["revision"], expected_fingerprint=first["fingerprint"])
        page.write_text(page.read_text() + "\n新增业务例外", encoding="utf-8")
        stale = memory.read_brief(self.P, "APP")
        self.assertTrue(stale["stale"])
        self.assertTrue(any(r["source_id"].startswith("page:") for r in stale["stale_reasons"]))
        with self.assertRaises(ApiError) as ctx:
            self.act("brief_confirm", revision=first["revision"], expected_fingerprint=first["fingerprint"])
        self.assertEqual(ctx.exception.code, 409)
        second = self.act("brief_generate")
        self.assertEqual(second["revision"], 2)
        self.assertIsNone(second["confirmed"])
        old = memory.read_brief(self.P, "APP", "1")
        self.assertEqual(old["markdown"], first["markdown"])
        self.assertEqual(old["confirmed"]["by"], "reviewer")
        self.assertNotIn("新增业务例外", old["markdown"])

    def test_brief_sections_preserve_source_page_as_one_complete_item(self):
        text = "## 当前待办与责任人\n\n这是原始业务页的标题，不能变成交接导航。\n\n## 完整来源清单\n仍属于这个知识页。"
        path = self.page(text)
        brief = self.act("brief_generate")
        self.assertEqual([s["id"] for s in brief["sections"]], ["overview", "knowledge", "work", "lessons", "references", "gaps", "sources"])
        knowledge = next(s for s in brief["sections"] if s["id"] == "knowledge")
        self.assertEqual(len(knowledge["items"]), 1)
        self.assertEqual(knowledge["items"][0]["body"], path.read_text())
        self.assertIn(path.read_text(), brief["markdown"])

    def test_old_brief_history_is_not_rebuilt_using_new_sources(self):
        page = self.page("旧版正文")
        first = self.act("brief_generate")
        with memory._write(self.P, self.p) as state:
            state["briefs"][0].pop("sections")
        page.write_text(page.read_text() + "\n新版知识", encoding="utf-8")
        old = memory.read_brief(self.P, "APP", "1")
        self.assertEqual(old["sections"][0]["id"], "archive")
        self.assertEqual(old["sections"][0]["items"][0]["body"], first["markdown"])
        self.assertNotIn("新版知识", old["markdown"])

    def test_ticket_responsibility_and_lesson_state_change_stale_brief(self):
        t = self.ticket(assignee="甲")
        l = self.lesson()
        first = self.act("brief_generate")
        self.store.update_ticket(t["id"], "lead", assignee="乙")
        learn.set_status(self.data, l["id"], "retired", "owner", "已有新做法")
        stale = memory.read_brief(self.P, "APP")
        ids = {r["source_id"] for r in stale["stale_reasons"]}
        self.assertIn("tickets", ids)
        self.assertIn("lessons", ids)
        self.assertIn("负责人：甲", first["markdown"])

    @unittest.skipUnless(shutil.which("git"), "Git needed")
    def test_second_dirty_edit_invalidates_even_same_git_status(self):
        root = self.roots["APP"]
        def git(*args):
            subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True)
        git("init")
        git("config", "user.email", "memory@example.invalid")
        git("config", "user.name", "Memory test")
        f = root / "App.java"
        f.write_text("class App {}\n")
        git("add", ".")
        git("commit", "-m", "initial")
        f.write_text("class App { int x; }\n")
        first = self.act("brief_generate")
        f.write_text("class App { int y; }\n")
        current = memory.read_brief(self.P, "APP")
        self.assertNotEqual(first["fingerprint"], current["current_fingerprint"])
        self.assertIn("code", {r["source_id"] for r in current["stale_reasons"]})

    def test_symlink_knowledge_outside_project_is_not_included(self):
        outside = self.data / "private.md"
        outside.write_text("不可跨界读取的秘密", encoding="utf-8")
        kd = self.roots["APP"] / ".tmh/knowledge"
        kd.mkdir(parents=True)
        (kd / "bad.md").symlink_to(outside)
        brief = memory.read_brief(self.P, "APP")
        self.assertNotIn("不可跨界读取的秘密", brief["markdown"])
        self.assertTrue(any("符号链接" in w for w in brief["warnings"]))

    def test_manual_memory_is_candidate_until_confirmed_and_actor_recorded(self):
        text = "完整经验" * 500
        l = self.act("lesson_create", title="并发审批重复写入", fields={"symptom": "审批回调重复写入状态导致重复通知", "fix": text})
        self.assertEqual(l["status"], "candidate")
        self.assertEqual(l["fix"], text)
        self.assertEqual(learn.relevant(self.data, "APP", self.ticket()), [])
        self.act("lesson_confirm", lesson_id=l["id"], expected_token=l["snapshot"]["expected_token"], request_id="manual-confirm")
        card = learn.lesson(self.data, l["id"])
        self.assertEqual(card["history"][-1]["by"], "reviewer")
        self.assertEqual(card["status"], "active")

    def test_foreign_memory_requires_share_and_take_and_actual_use_is_recorded(self):
        own = self.lesson(project="OTHER", note="仅来源项目可见客户详情")
        t = self.ticket()
        global_before = memory.dispatch_read(self.P, {"section": "lessons"}, "reader")
        self.assertEqual(global_before["lessons"], [])
        self.assertEqual(learn.relevant(self.data, "APP", t), [])
        memory.dispatch_action(self.P, {"action": "lesson_share", "project": "OTHER", "lesson_id": own["id"],
                                        "title": "审批回调重复写入状态错误", "fields": {"symptom": "审批回调重复写入状态导致重复通知和记录", "fix": "检查幂等键", "verify": "重复回调验证"}}, "publisher")
        shared = memory.dispatch_read(self.P, {"section": "lessons", "project": "APP"}, "reader")["lessons"][0]
        self.assertFalse(shared["auto_use"])
        self.assertNotIn("仅来源项目可见客户详情", json.dumps(shared, ensure_ascii=False))
        self.assertEqual(learn.relevant(self.data, "APP", t), [])
        self.act("lesson_take", lesson_id=own["id"])
        matched = learn.relevant(self.data, "APP", t)
        self.assertEqual([l["id"] for l in matched], [own["id"]])
        learn.note_used(self.data, t, matched, "plan")
        self.assertEqual(learn.shared(self.data, "APP")[0]["here"]["used"], 1)
        memory.dispatch_action(self.P, {"action": "lesson_unshare", "project": "OTHER", "lesson_id": own["id"]}, "publisher")
        self.assertEqual(learn.relevant(self.data, "APP", t), [])

    def test_cannot_edit_another_project_or_silently_clip_shared_copy(self):
        l = self.lesson(project="OTHER")
        with self.assertRaises(ApiError) as ctx:
            self.act("lesson_retire", lesson_id=l["id"], reason="不适用", expected_token=learn.revision_token(self.data, l["id"]), request_id="foreign-retire")
        self.assertEqual(ctx.exception.code, 404)
        l2 = self.lesson()
        with self.assertRaises(ApiError):
            self.act("lesson_share", lesson_id=l2["id"], title="共享", fields={"fix": "x" * 801})
        self.assertIsNone(learn.lesson(self.data, l2["id"])["shared"])

    def test_corrupted_memory_is_not_overwritten(self):
        path = memory._path(self.P, self.p)
        path.parent.mkdir()
        path.write_text("{unfinished", encoding="utf-8")
        with self.assertRaises(ApiError):
            self.act("brief_generate")
        self.assertEqual(path.read_text(), "{unfinished")

    def test_org_knowledge_uses_edited_active_state_and_full_content_identity(self):
        l = self.lesson()
        learn.edit_lesson(self.data, l["id"], {"fix": "修改后的正确办法"}, "editor")
        self.assertTrue(org_knowledge.search(self.store, "正确办法"))
        learn.set_status(self.data, l["id"], "retired", "editor", "失效")
        self.assertFalse(org_knowledge.search(self.store, "正确办法"))
        common = "相同的长段落" * 100
        self.page(common + "\n\n只在甲项目的规则", "APP")
        self.page(common + "\n\n只在乙项目的规则", "OTHER")
        items = org_knowledge.build(self.store)["items"]
        self.assertEqual(len(items), 2)
        self.assertNotEqual(items[0]["dedup_key"], items[1]["dedup_key"])
        self.assertEqual([x["id"] for x in items], [x["id"] for x in org_knowledge.build(self.store)["items"]])

    def test_stale_registry_does_not_keep_old_frontmatter_confirmation(self):
        path = self.page()
        (path.parent.parent / ".pages.json").write_text(json.dumps({"flow:approval": {"stale": True, "status": "已确认"}}))
        self.assertEqual(org_knowledge.build(self.store)["items"], [])
        brief = memory.read_brief(self.P, "APP")
        self.assertTrue(any("需更新" in warning for warning in brief["warnings"]))

    def test_project_knowledge_can_browse_drafts_without_promoting_org_or_memory(self):
        from tmh import kb
        from tmh.platform.knowledge import Knowledge
        root = self.roots["APP"]
        kb.build(root)
        body = "\n\n".join("## " + section + "\n代码来源已核对，业务含义仍待项目成员确认。" for section in kb.SECTIONS["index"])
        path = kb.page_path(root, "index")
        previous = kb.parse_page(path.read_text())
        path.write_text(kb.render_page("index", {"id": "index", "title": "待确认的项目总览", "summary": "有来源的项目知识草稿"}, previous["facts"], body))
        self.assertEqual(kb.done(root, "index", "agent:import-test"), (True, []))
        global_before = memory.dispatch_read(self.P, {"section": "knowledge"}, "reader")
        self.assertEqual(global_before["knowledge"], [])
        result = memory.dispatch_read(self.P, {"project": "APP", "section": "knowledge"}, "reader")
        self.assertEqual(len(result["knowledge"]), 1)
        item = result["knowledge"][0]
        self.assertEqual(item["status"], "待确认")
        self.assertFalse(item["reviewed"])
        self.assertEqual(item["provenance"][0]["id"], "index")
        # This is the same domain reader used by /api/projects/<key>/kb/page.
        knowledge = Knowledge(self.store, None)
        self.assertTrue(knowledge.kb_tree(self.p)["built"])
        page = knowledge.kb_page(self.p, item["provenance"][0]["id"])
        self.assertEqual(page["text"], path.read_text())
        self.assertEqual(page["status"], "待确认")
        self.assertEqual(page["confirmed_by"], "")
        self.assertEqual(learn.lessons(self.data, "APP"), [])
        self.assertEqual(org_knowledge.search(self.store, "项目知识草稿"), [])
        self.assertEqual(len(memory.dispatch_read(self.P, {"project": "APP", "section": "knowledge", "q": "项目知识草稿"}, "reader")["knowledge"]), 1)

    def test_concurrent_generations_keep_single_identical_revision(self):
        from concurrent.futures import ThreadPoolExecutor
        self.page()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.act("brief_generate"), range(2)))
        self.assertEqual([r["revision"] for r in results], [1, 1])
        self.assertEqual(len(memory.read_brief(self.P, "APP")["history"]), 1)

    @unittest.skipUnless(shutil.which("node"), "Node needed")
    def test_shipped_ui_parses(self):
        result = subprocess.run([shutil.which("node"), "--check"], input=MEMORY_JS, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
