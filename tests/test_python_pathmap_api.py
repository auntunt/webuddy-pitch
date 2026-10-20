"""Actual HTTP/Git evidence binding; no model, real customer or signing action."""
import json
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from tests.sqlite_snapshot import dump_store
from tmh.platform import gates, pathmap, signoff
from tmh.platform.server import Platform, make_handler
from tests import test_python_pathmap_independent as fixture


class PythonPathMapApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tmh-python-api-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"; self.repo.mkdir()
        self.git("init", "-q"); self.git("config", "user.email", "fixture@localhost"); self.git("config", "user.name", "fixture")
        (self.repo / "app.py").write_text(fixture.BASE)
        self.git("add", "."); self.git("commit", "-qm", "base")
        self.old = self.git("rev-parse", "HEAD")
        (self.repo / "app.py").write_text(fixture.BASE.replace("SAVED_BASE", "SAVED_CANDIDATE"))
        self.git("add", "."); self.git("commit", "-qm", "candidate")
        self.sha = self.git("rev-parse", "HEAD")
        self.diff = self.git("diff", self.old, self.sha) + "\n"
        data = self.base / "data"; data.mkdir()
        (data / "autoflow.json").write_text('{"on":false}')
        self.P = Platform(data, "technical-fixture")
        self.addCleanup(self.P.store.db.close)
        self.project = self.P.store.add_project("PYAPI", "合成路径验收", str(self.repo))
        self.t = self.P.store.create_ticket(self.project["id"], "保存记录", "技术验收")
        self.run = self.P.store.create_run(self.project["id"], self.t["id"], "synthetic", "fix", "技术验收", "")
        self.P.store.update_run(self.run["id"], status="done", decision="accepted:fixture@" + self.sha[:7], diff=self.diff)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.P))
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": .02}, daemon=True); self.thread.start()
        self.addCleanup(self.stop)
        self.url = "http://127.0.0.1:%s/api/tickets/%s/path-map" % (self.httpd.server_port, self.t["key"])
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def stop(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.thread.join(2)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True, stderr=subprocess.PIPE).strip()

    def call(self, body=None, write=True):
        headers = {"Content-Type": "application/json"}
        if write:
            headers["X-TMH"] = "1"
        req = urllib.request.Request(self.url, headers=headers, data=json.dumps(body).encode() if body is not None else None)
        try:
            with self.opener.open(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def record(self):
        code, value = self.call(); self.assertEqual(code, 200)
        body = {"commit": value["source"]["commit"], "digest": value["digest"], "flows": value["suggested"]}
        self.assertEqual(self.call(body)[0], 200)
        return body

    def test_read_is_pure_and_record_is_technical_not_human_confirmation(self):
        before = "\n".join(dump_store(self.P.store))
        code, value = self.call(); self.assertEqual((code, value["status"]), (200, "mapped"))
        self.assertEqual(before, "\n".join(dump_store(self.P.store)))
        self.assertFalse((self.repo / ".tmh").exists())
        self.record()
        t = self.P.store.ticket(self.t["id"])
        self.assertEqual(t["links"]["flows"], value["suggested"])
        self.assertFalse(t["links"].get("flows_ok"))
        self.assertFalse(any(e["kind"] in ("review", "accept", "sign") for e in self.P.store.events(t["id"])))
        self.assertEqual(t["links"]["code_path"]["commit"], self.sha)

    def test_candidate_path_does_not_read_stale_main_graph(self):
        self.record()
        with patch.object(signoff, "_flows", side_effect=RuntimeError("main graph is corrupt")):
            snap = signoff.snapshot(self.P, self.P.store.ticket(self.t["id"]))
        self.assertTrue(snap["path"]["ok"])
        self.assertEqual(snap["path"]["source"]["commit"], self.sha)

    def test_write_header_bad_entry_stale_digest_and_closed_are_rejected(self):
        _, value = self.call()
        body = {"commit": self.sha, "digest": value["digest"], "flows": value["suggested"]}
        self.assertEqual(self.call(body, write=False)[0], 403)
        self.assertEqual(self.call(dict(body, flows=["flow:invented"]))[0], 400)
        self.assertEqual(self.call(dict(body, digest="old"))[0], 409)
        self.P.store.update_ticket(self.t["id"], "fixture", status="closed")
        self.assertEqual(self.call(body)[0], 409)

    def test_changed_candidate_invalidates_previous_association_without_overwriting_history(self):
        body = self.record()
        t = self.P.store.ticket(self.t["id"])
        self.assertTrue(signoff.snapshot(self.P, t)["path"]["ok"])
        (self.repo / "app.py").write_text(fixture.BASE.replace("SAVED_BASE", "NEWER_CANDIDATE"))
        self.git("add", "."); self.git("commit", "-qm", "newer")
        newer = self.git("rev-parse", "HEAD")
        self.P.store.update_run(self.run["id"], decision="accepted:fixture@" + newer, diff=self.git("diff", self.old, newer) + "\n")
        self.assertEqual(self.call(body)[0], 409)
        self.assertEqual(self.P.store.ticket(t["id"])["links"]["code_path"]["commit"], self.sha)
        snap = signoff.snapshot(self.P, self.P.store.ticket(t["id"]))
        self.assertFalse(snap["path"]["ok"])
        self.assertIn("过期", snap["path"]["why"])
        self.assertEqual(next(g for g in snap["gates"] if g["id"] == "path")["state"], "unknown")

    def test_unparsed_product_file_prevents_legacy_file_match_from_passing(self):
        raw = signoff._path_by_file(["app.java", "routing.json"], [{"files": ["app.java"]}])
        self.assertEqual(gates.path(raw)["state"], "unknown")

    def test_diff_content_forgery_and_other_product_file_cannot_be_hidden(self):
        fix = self.P.store.run(self.run["id"])
        forged = dict(fix, diff=fix["diff"].replace('+            return "SAVED_CANDIDATE"', '+            return "UNRELATED"'))
        self.assertFalse(pathmap.path_result(pathmap.for_change(self.project, forged), self.call()[1]["suggested"])["ok"])
        extra = fix["diff"] + 'diff --git a/routing.json b/routing.json\n@@ -1 +1 @@\n-{}\n+{"route":"elsewhere"}\n'
        mapped = pathmap.for_change(self.project, dict(fix, diff=extra))
        self.assertEqual(mapped["status"], "partial")
        self.assertFalse(pathmap.path_result(mapped, mapped["suggested"])["ok"])
