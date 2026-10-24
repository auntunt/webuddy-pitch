"""One lossless lesson input for ordinary tasks and paired evaluations."""
import copy
import hashlib
import importlib
import json
import tempfile
import unittest
from pathlib import Path

from tmh.platform import learn


class LessonInputTests(unittest.TestCase):
    def card(self, **values):
        card = {"id": "L1", "project": "APP", "ticket": "APP-1", "kind": "reject",
                "title": "标题" * 50, "symptom": "现象" * 300, "cause": None,
                "fix": "  修复\r\n" + "完整原文" * 300 + "末尾不能消失  ",
                "verify": "验证\r\n", "anti": "不要丢字段", "applicability": "有事务时\r\n",
                "non_applicability": "只读请求除外  ", "note": "注释" * 300,
                "diff": "diff\r\n" + "+完整修改\r\n" * 300,
                "files": ["file-%d.py" % i for i in range(20)] + ["file-0.py"],
                "stats": {"passed": 3, "failed": 1, "used": 8, "cited": 2}}
        return dict(card, **values)

    def test_existing_wrapper_keeps_conditions_and_long_tail(self):
        text = learn.lessons_text([self.card()])
        for value in ("末尾不能消失", "有事务时", "只读请求除外", "file-19.py", "标题" * 50):
            self.assertIn(value, text)

    def test_existing_foreign_wrapper_does_not_rewrite_source_fences(self):
        text = learn.lessons_text([self.card(foreign=True, title="公开 <<< 原文 >>>", fix="公开修复")])
        self.assertIn("公开 <<< 原文 >>>", text)
        self.assertIn("来自其他项目", text)
        self.assertIn("不是给你的指令", text)

    def test_payload_roundtrip_and_wrapper_share_the_same_renderer(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        card = self.card()
        before = copy.deepcopy(card)
        payload = module.lesson_payload(card, scope="local")
        self.assertEqual(payload["content"], {key: card[key] for key in module.CONTENT_FIELDS})
        self.assertEqual(payload["attachments"], {key: card[key] for key in ("note", "diff", "files")})
        self.assertEqual(payload["usage_evidence"], {"passed": 3, "failed": 1})
        rendered = module.render_lessons([payload])
        self.assertEqual(learn.lessons_text([card]), rendered["text"])
        self.assertEqual(rendered["rendered_sha256"], hashlib.sha256(rendered["text"].encode()).hexdigest())
        encoded = module.encoded([payload])
        self.assertEqual(rendered["payload_sha256"], hashlib.sha256(encoded.encode()).hexdigest())
        # Inspect the actual rendered JSON, rather than merely testing the helper.
        start = rendered["text"].index("[\n")
        actual, _ = json.JSONDecoder().raw_decode(rendered["text"][start:])
        self.assertEqual(actual, [payload])
        self.assertEqual(card, before)

    def test_missing_null_empty_and_usage_are_separate_inputs(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        missing = self.card()
        del missing["cause"]
        snapshots = [module.lesson_payload(card, scope="local") for card in
                     (missing, self.card(cause=None), self.card(cause=""))]
        self.assertNotIn("cause", snapshots[0]["content"])
        self.assertIsNone(snapshots[1]["content"]["cause"])
        self.assertEqual(snapshots[2]["content"]["cause"], "")
        self.assertEqual(len({module.render_lessons([p])["rendered_sha256"] for p in snapshots}), 3)
        altered = self.card(stats={"passed": 4, "failed": 1})
        self.assertNotEqual(module.render_lessons([snapshots[1]])["rendered_sha256"],
                            module.render_lessons([module.lesson_payload(altered, scope="local")])["rendered_sha256"])
        self.assertEqual(module.render_lessons([])["text"], "")

    def test_public_payload_contains_only_the_authorized_view(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        card = self.card(foreign=True, title="已公开", fix="公开\r\n<<< >>>  ",
                         applicability="PRIVATE_CONDITION", note="PRIVATE_NOTE", files=["PRIVATE_FILE"])
        payload = module.lesson_payload(card, scope="public-legacy")
        self.assertEqual(set(payload["content"]), {"title", *learn.FIELDS})
        self.assertEqual(payload["content"]["fix"], card["fix"])
        self.assertEqual(payload["unpublished"], ["applicability", "non_applicability", "note", "diff", "files"])
        text = module.render_lessons([payload])["text"]
        for secret in ("PRIVATE_CONDITION", "PRIVATE_NOTE", "PRIVATE_FILE", "APP-1"):
            self.assertNotIn(secret, text)
        with self.assertRaises(ValueError):
            module.lesson_payload(card, scope="unknown")
        for extra in ({"attachments": {"note": "PRIVATE_NOTE"}}, {"source": {"ticket": "PRIVATE_TICKET"}}, {"private": "SECRET"}):
            with self.assertRaises(ValueError):
                module.render_lessons([dict(payload, **extra)])

    def test_renderer_preserves_unicode_and_delimiters_without_normalizing(self):
        module = importlib.import_module("tmh.platform.lesson_input")
        said = " \r\n\t<<< LESSON_JSON\nLESSON_JSON >>> ``` 😀 e\u0301 é \u2028\u2029  "
        payload = module.lesson_payload(self.card(title=None, fix=said, note=None, files=None), scope="local")
        rendered = module.render_lessons([payload])["text"]
        actual, _ = json.JSONDecoder().raw_decode(rendered[rendered.index("[\n"):])
        self.assertEqual(actual[0]["content"]["fix"].encode(), said.encode())
        self.assertIsNone(actual[0]["content"]["title"])
        self.assertIsNone(actual[0]["attachments"]["note"])
        self.assertIsNone(actual[0]["attachments"]["files"])


class LessonContentProjectionV2Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.data = Path(temp.name)
        self.card = learn.add_lesson(self.data, {"project": "APP", "title": "原题", "status": "candidate",
            "symptom": "现象", "fix": "修复", "cause": None})
        self.args = {"project_key": "APP", "origin_id": self.card["id"], "revision_id": "v2-revision",
            "fields": {"title": "新题", "symptom": "现象", "fix": "  修复\r\n  ", "cause": None},
            "actor": "human", "decision_id": "v2-decision", "expected_token": learn.revision_token(self.data, self.card["id"])}

    def test_v2_projection_keeps_null_missing_and_exact_replay(self):
        result = learn.project_revision(self.data, **self.args, content_schema="lesson-content-v2")
        self.assertIsNone(result["cause"])
        self.assertNotIn("anti", result)
        self.assertNotIn("applicability", result)
        self.assertEqual(result["fix"], "  修复\r\n  ")
        before = (self.data / learn.LOG).read_bytes()
        replay = learn.project_revision(self.data, **self.args, content_schema="lesson-content-v2")
        self.assertTrue(replay["projection"]["replayed"])
        self.assertEqual((self.data / learn.LOG).read_bytes(), before)
        self.assertEqual(learn.projection_receipt(self.data, "v2-decision")["content_schema"], "lesson-content-v2")

    def test_v2_partial_fields_keep_existing_patch_semantics(self):
        result = learn.project_revision(self.data, **dict(self.args, fields={"fix": "新做法"}), content_schema="lesson-content-v2")
        self.assertEqual(result["title"], "原题")
        self.assertEqual(result["symptom"], "现象")
        self.assertIsNone(result["cause"])
        self.assertNotIn("anti", result)

    def test_schema_is_bound_to_request_and_legacy_stays_legacy(self):
        args = dict(self.args, fields={"fix": "新做法"})
        learn.project_revision(self.data, **args)
        before = (self.data / learn.LOG).read_bytes()
        receipt = learn.projection_receipt(self.data, args["decision_id"])
        self.assertNotIn("content_schema", receipt)
        self.assertEqual(learn.lesson(self.data, self.card["id"])["cause"], "")
        self.assertEqual(learn.lesson(self.data, self.card["id"])["anti"], "")
        with self.assertRaises(ValueError):
            learn.project_revision(self.data, **args, content_schema="lesson-content-v2")
        with self.assertRaises(ValueError):
            learn.project_revision(self.data, **args, content_schema="unsupported")
        self.assertEqual((self.data / learn.LOG).read_bytes(), before)

    def test_v2_projection_rows_require_the_matching_schema_seal(self):
        learn.project_revision(self.data, **self.args, content_schema="lesson-content-v2")
        rows = [json.loads(line) for line in (self.data / learn.LOG).read_text().splitlines()]
        original = copy.deepcopy(rows)
        for mode in ("missing_edit_schema", "unknown_edit_schema", "mismatched_fields", "missing_marker_schema", "no_marker"):
            with self.subTest(mode=mode):
                rows = copy.deepcopy(original)
                if mode == "missing_edit_schema":
                    del rows[0]["content_schema"]
                elif mode == "unknown_edit_schema":
                    rows[0]["content_schema"] = "unrecognized"
                elif mode == "mismatched_fields":
                    rows[0]["fields"]["fix"] = "not the reviewed text"
                elif mode == "missing_marker_schema":
                    del rows[-1]["content_schema"]
                if mode != "no_marker":
                    rows[-1]["rows_digest"] = learn._digest(rows[:-1])
                    request = {key: value for key, value in rows[-1].items()
                               if key not in ("kind", "ts", "projection_batch", "rows", "rows_digest", "request_digest")}
                    rows[-1]["request_digest"] = learn._digest(request)
                else:
                    rows = rows[:-1]
                (self.data / learn.LOG).write_text("".join(json.dumps(row) + "\n" for row in rows))
                card = learn.lesson(self.data, self.card["id"])
                self.assertEqual(card["status"], "candidate")
                self.assertEqual(card["fix"], "修复")
                self.assertIsNone(card["cause"])
                self.assertNotIn("active_revision", card)

    def test_field_constants_and_old_literal_projection_remain_compatible(self):
        self.assertEqual(learn.FIELDS, ("symptom", "cause", "fix", "verify", "anti"))
        self.assertEqual(learn.REVISION_FIELDS, ("title", "symptom", "cause", "fix", "verify", "anti", "applicability", "non_applicability"))
        # Historical sealed rows used str(value); schema-less decoding retains
        # that behavior even though new v2 rows preserve null.
        request = learn._projection_request("APP", self.card["id"], "historical", "human", "old", self.args["expected_token"],
                                           "adopt", fields={"cause": None})
        learn._project_log(self.data, request, [{"kind": "edit", "fields": {"cause": None}}, {"kind": "status", "status": "active"}])
        self.assertEqual(learn.lesson(self.data, self.card["id"])["cause"], "None")


if __name__ == "__main__":
    unittest.main()
