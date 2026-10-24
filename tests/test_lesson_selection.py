"""Frozen retrieval uses the production selector without usage or holdout writes."""
import copy
import importlib
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tmh.platform import learn


class LessonSelectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.ticket = {"title": "事务提交以后刷新列表", "body": "transaction callback", "links": {"flows": ["save"]}}

    def card(self, **values):
        return learn.add_lesson(self.data, {"project": "APP", "title": "事务提交以后刷新列表", "ticket": "APP-1",
            "fix": "transaction callback", "flows": ["save"], **values})

    def test_current_selector_accepts_legal_null_title_and_note(self):
        for field in ("title", "note"):
            card = self.card(**{field: None})
            self.assertIn(card["id"], [c["id"] for c in learn.relevant(self.data, "APP", self.ticket)])
            self.assertIsNone(learn.lesson(self.data, card["id"])[field])

    def test_pool_and_pure_selection_do_not_create_or_write(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        missing = self.data / "absent"
        empty = learn.lesson_selection_pool(missing, "APP")
        self.assertEqual(module.select_lessons(empty, self.ticket)["selected"], [])
        self.assertFalse(missing.exists())
        on = self.card()
        self.card(fix="每次开工前先扫描全部文件。")
        before = {p.name: p.read_bytes() for p in self.data.iterdir()}
        pool = learn.lesson_selection_pool(self.data, "APP")
        snapshot = copy.deepcopy(pool)
        selected = module.select_lessons(pool, dict(self.ticket, id=33, key="APP-9"))
        self.assertEqual(selected["selected"], [{"scope": "local", "id": on["id"]}])
        self.assertTrue(selected["overhead"])
        self.assertEqual(pool, snapshot)
        self.assertEqual({p.name: p.read_bytes() for p in self.data.iterdir()}, before)

    def test_pool_cas_does_not_change_on_usage_but_snapshot_does(self):
        card = self.card()
        before = learn.lesson_selection_pool(self.data, "APP")
        learn.note_used(self.data, {"key": "APP-20"}, [card], "fix")
        after = learn.lesson_selection_pool(self.data, "APP")
        self.assertEqual(before["binding"], after["binding"])
        self.assertNotEqual(before["local"][0]["stats"], after["local"][0]["stats"])

    def test_original_500_pool_is_cut_before_status_and_not_refilled(self):
        rows = [{"id": "L%d" % i, "project": "APP", "ticket": "APP-%d" % i, "title": "事务提交以后刷新列表",
                 "fix": "transaction callback", "flows": ["save"], "status": "active" if i <= 3 else "candidate"}
                for i in range(1, 502)]
        (self.data / learn.LESSONS).write_text("".join(json.dumps(row) + "\n" for row in rows))
        pool = learn.lesson_selection_pool(self.data, "APP")
        self.assertEqual([c["id"] for c in pool["local"]], ["L%d" % i for i in range(501, 1, -1)])
        self.assertEqual([c["id"] for c in learn.relevant(self.data, "APP", self.ticket)], ["L3", "L2"])

    def test_body_and_extra_windows_and_anchors_use_the_original_rules(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        card = self.card(title="transaction", fix="transaction", flows=[], anchors=["gone.py"], files=["exists.py"])
        (self.data / "exists.py").write_text("present")
        self.assertFalse(learn.lesson_selection_pool(self.data, "APP", root=self.data)["anchors"][card["id"]])
        pool = learn.lesson_selection_pool(self.data, "APP")
        task = {"title": "", "body": "x " * 750 + "transaction", "links": {}}
        self.assertEqual(module.select_lessons(pool, task)["selected"], [])
        task["body"] = "transaction " + "x " * 750
        self.assertEqual(module.select_lessons(pool, task)["selected"], [{"scope": "local", "id": card["id"]}])
        task["body"] = ""
        self.assertEqual(module.select_lessons(pool, task, "x " * 1500 + "transaction")["selected"], [])
        self.assertEqual(module.select_lessons(pool, task, "transaction " + "x " * 1500)["selected"], [{"scope": "local", "id": card["id"]}])

    def test_public_lifecycle_detects_same_second_aba_but_not_other_consumers_or_usage(self):
        source = self.card(project="OWNER", note="PRIVATE_NOTE", applicability="PRIVATE_CONDITION")
        with patch.object(learn, "now", return_value="2026-10-24 12:00:00"):
            learn.set_shared(self.data, source["id"], True, "owner", "公开事务刷新", {"fix": "transaction callback"})
            learn.take_shared(self.data, source["id"], "APP", True, "reader")
            card = learn.shared(self.data, "APP")[0]
            original = learn.public_lesson_binding(self.data, "APP", card)
            self.assertEqual(original, learn.lesson_selection_pool(self.data, "APP")["binding"]["public_bindings"][card["id"]])
            learn.take_shared(self.data, source["id"], "OTHER", True, "someone")
            learn.take_shared(self.data, source["id"], "OTHER", False, "someone")
            learn.note_used(self.data, {"key": "APP-8", "project_key": "APP"}, [card], "fix")
            self.assertEqual(original, learn.public_lesson_binding(self.data, "APP", card))
            learn.take_shared(self.data, source["id"], "APP", False, "reader")
            self.assertIsNone(learn.public_lesson_binding(self.data, "APP", card))
            learn.take_shared(self.data, source["id"], "APP", True, "reader")
            changed = learn.public_lesson_binding(self.data, "APP", card)
            self.assertEqual(original["take_fingerprint"], changed["take_fingerprint"])
            self.assertNotEqual(original["lifecycle_sha256"], changed["lifecycle_sha256"])
            learn.set_status(self.data, source["id"], "retired", "owner")
            learn.set_status(self.data, source["id"], "active", "owner")
            self.assertNotEqual(changed["lifecycle_sha256"], learn.public_lesson_binding(self.data, "APP", card)["lifecycle_sha256"])
        public_pool = learn.lesson_selection_pool(self.data, "APP")
        for secret in ("PRIVATE_NOTE", "PRIVATE_CONDITION", "OWNER"):
            self.assertNotIn(secret, json.dumps(public_pool))

    def test_public_helper_rejects_changed_snapshot_and_private_card(self):
        source = self.card(project="OWNER")
        learn.set_shared(self.data, source["id"], True, "owner", "公开事务刷新", {"fix": "transaction callback"})
        learn.take_shared(self.data, source["id"], "APP", True, "reader")
        card = learn.shared(self.data, "APP")[0]
        self.assertIsNone(learn.public_lesson_binding(self.data, "APP", source))
        self.assertIsNone(learn.public_lesson_binding(self.data, "APP", dict(card, fix="changed")))

    def test_existing_public_binding_survives_discovery_window_displacement(self):
        source = self.card(project="OWNER", note="PRIVATE_NOTE", applicability="PRIVATE_CONDITION")
        learn.set_shared(self.data, source["id"], True, "owner", "公开事务刷新", {"fix": "transaction callback"})
        learn.take_shared(self.data, source["id"], "APP", True, "reader")
        card = learn.shared(self.data, "APP")[0]
        binding = learn.public_lesson_binding(self.data, "APP", card)
        material = learn._read_material(self.data)
        # These irrelevant newer cards displace the captured public source from
        # the discovery window; they cannot revoke its existing authorization.
        material["cards"] += [{"id": "L%d" % n, "project": "APP", "shared": None} for n in range(2, 100002)]
        self.assertEqual(learn._shared_cards(material["cards"][::-1][:100000], "APP"), [])
        with patch.object(learn, "_read_material", return_value=material):
            self.assertEqual(learn.public_lesson_binding(self.data, "APP", card), binding)
            self.assertEqual(learn.shared_lesson(self.data, "APP", card["id"]), card)
            self.assertIsNone(learn.shared_lesson(self.data, "OWNER", card["id"]))
            self.assertIsNone(learn.shared_lesson(self.data, "APP", "L2"))
        view = learn.shared_lesson(self.data, "APP", card["id"])
        for secret in ("PRIVATE_NOTE", "PRIVATE_CONDITION", "OWNER"):
            self.assertNotIn(secret, json.dumps(view))
        learn.set_shared(self.data, source["id"], False, "owner")
        self.assertIsNone(learn.shared_lesson(self.data, "APP", card["id"]))

    def test_single_id_read_does_not_use_the_list_discovery_window(self):
        source = self.card()
        material = learn._read_material(self.data)
        expected = material["cards"][0]
        material["cards"] += [{"id": "L%d" % n, "project": "OTHER", "shared": None} for n in range(2, 100002)]
        with patch.object(learn, "_read_material", return_value=material), patch.object(learn, "_fold", return_value=material["cards"]):
            self.assertNotIn(source["id"], [card["id"] for card in learn.lessons(self.data, "", 100000)])
            self.assertEqual(learn.lesson(self.data, source["id"]), expected)
            self.assertIsNone(learn.lesson(self.data, "absent"))

    def test_take_shared_returns_the_written_id_even_outside_discovery_window(self):
        source = self.card(project="OWNER")
        learn.set_shared(self.data, source["id"], True, "owner", "公开事务刷新", {"fix": "transaction callback"})
        learn.take_shared(self.data, source["id"], "APP", True, "reader")
        material = learn._read_material(self.data)
        current = material["cards"][0]
        public = learn.shared_lesson(self.data, "APP", source["id"])
        material["cards"] += [{"id": "L%d" % n, "project": "OTHER", "shared": None} for n in range(2, 100002)]
        before = (self.data / learn.LOG).read_bytes()
        with patch.object(learn, "lesson", return_value=current), patch.object(learn, "_fold", return_value=material["cards"]):
            try:
                result = learn.take_shared(self.data, source["id"], "APP", True, "reader")
            finally:
                rows = [json.loads(line) for line in (self.data / learn.LOG).read_bytes()[len(before):].splitlines()]
                self.assertEqual(len(rows), 1)
                self.assertEqual((rows[0]["kind"], rows[0]["id"], rows[0]["project"], rows[0]["on"]),
                                 ("take", source["id"], "APP", True))
            self.assertEqual(result, public)

    @unittest.skipUnless(os.name == "posix", "人工经验决定在 Windows 明确拒绝写入")
    def test_public_lifecycle_tracks_human_status_and_fixed_revision_without_private_content(self):
        source = self.card(project="OWNER", fix="PRIVATE_SOURCE_A")
        learn.set_shared(self.data, source["id"], True, "owner", "公开事务刷新", {"fix": "transaction callback"})
        learn.take_shared(self.data, source["id"], "APP", True, "reader")
        card = learn.shared(self.data, "APP")[0]
        before = learn.public_lesson_binding(self.data, "APP", card)
        for action in ("retire", "restore"):
            snapshot = learn.lesson_snapshot(self.data, "OWNER", source["id"])
            learn.human_decision(self.data, "OWNER", source["id"], "owner", action, snapshot["expected_token"],
                                 "synthetic-" + action, reason="合成授权核对")
        after = learn.public_lesson_binding(self.data, "APP", card)
        self.assertEqual(before["shared_fingerprint"], after["shared_fingerprint"])
        self.assertNotEqual(before["lifecycle_sha256"], after["lifecycle_sha256"])
        learn.project_revision(self.data, "OWNER", source["id"], "fixed-revision", {"fix": "PRIVATE_SOURCE_B"},
                               "owner", "synthetic-adopt", learn.revision_token(self.data, source["id"]),
                               content_schema="lesson-content-v2")
        projected = learn.public_lesson_binding(self.data, "APP", card)
        self.assertEqual(projected["revision_id"], "fixed-revision")
        self.assertEqual(after["shared_fingerprint"], projected["shared_fingerprint"])
        self.assertNotEqual(after["lifecycle_sha256"], projected["lifecycle_sha256"])
        for secret in ("PRIVATE_SOURCE_A", "PRIVATE_SOURCE_B"):
            self.assertNotIn(secret, json.dumps(projected))

    def test_local_priority_ties_and_only_one_public_card(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        local = [self.card(ticket="APP-%d" % i) for i in range(3)]
        for i in range(2):
            source = self.card(project="OWNER", ticket="OWNER-%d" % i)
            learn.set_shared(self.data, source["id"], True, "owner", "事务提交以后刷新列表", {"fix": "transaction callback"})
            learn.take_shared(self.data, source["id"], "APP", True, "reader")
        pool = learn.lesson_selection_pool(self.data, "APP")
        expected_local = [{"scope": "local", "id": card["id"]} for card in local[::-1]]
        self.assertEqual(module.select_lessons(pool, self.ticket, limit=3)["selected"], expected_local)
        selected = module.select_lessons(pool, self.ticket, limit=10)["selected"]
        self.assertEqual(selected[:3], expected_local)
        self.assertEqual(selected[3:], [{"scope": "public-legacy", "id": pool["public"][0]["id"]}])

    def test_legal_null_is_only_a_matching_view_and_bad_types_are_not_stringified(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        self.card(title=None, note=None, cause=None)
        pool = learn.lesson_selection_pool(self.data, "APP")
        before = copy.deepcopy(pool)
        self.assertEqual(len(module.select_lessons(pool, self.ticket)["selected"]), 1)
        self.assertEqual(pool, before)
        for value in (False, {"x": "transaction"}, ["transaction"]):
            bad = copy.deepcopy(pool)
            bad["local"][0]["title"] = value
            with self.assertRaises(ValueError):
                module.select_lessons(bad, self.ticket)

    def test_valid_string_selection_matches_frozen_previous_algorithm(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        for i in range(8):
            self.card(ticket="APP-%d" % i, title=("事务刷新" if i % 2 else "billing invoice"),
                      flows=["save"] if i % 3 else [], files=["service.py"] if i % 4 else [],
                      fix="每次开工前先扫描全部文件。" if i == 7 else "transaction callback")
        pool = learn.lesson_selection_pool(self.data, "APP")
        # Frozen old algorithm, independent of the extracted selector. Scores,
        # equal-score ordering and local priority must not drift during extraction.
        def previous(task, extra, limit):
            flows = set((task.get("links") or {}).get("flows") or [])
            body = learn.own_words(task.get("body") or "")
            text = "%s %s %s" % (task.get("title", ""), body[:1500], extra[:3000])
            words, low = learn._grams(text), text.lower()
            scored = []
            for card in pool["local"]:
                if card.get("ticket") == task.get("key") or card["status"] != "active" or not pool["anchors"][card["id"]]:
                    continue
                score = 3 * len(flows & set(card.get("flows") or []))
                score += 2 * sum(1 for f in card.get("files") or [] if f.lower() in low or f.rsplit("/", 1)[-1].lower() in low)
                lw = learn._grams(" ".join([card.get("title", ""), card.get("note", "")] + [card.get(f) or "" for f in learn.FIELDS]))
                if lw and words:
                    score += 4 * len(words & lw) / math.sqrt(len(words) * len(lw))
                st = card["stats"]
                score += 0.5 * (st["passed"] - st["failed"]) / (1 + st["passed"] + st["failed"])
                if score >= 1.5 and not learn.overhead_flags(card):
                    scored.append((score, card["id"]))
            scored.sort(key=lambda item: -item[0])
            return [lid for _, lid in scored[:limit]]
        checked = 0
        for title in ("", "事务刷新", "billing invoice", "transaction callback"):
            for body in ("", "service.py", "transaction", "## 验收标准（从描述推出\n事务刷新"):
                for extra in ("", "billing", "service.py"):
                    for limit in (0, 1, 2, 3, 9):
                        task = {"key": "APP-0", "title": title, "body": body, "links": {"flows": ["save"]}}
                        self.assertEqual([ref["id"] for ref in module.select_lessons(pool, task, extra, limit)["selected"]], previous(task, extra, limit))
                        checked += 1
        self.assertEqual(checked, 240)


if __name__ == "__main__":
    unittest.main()
