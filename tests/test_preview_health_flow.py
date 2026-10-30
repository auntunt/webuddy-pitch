"""Real starter HTTP/SQLite failure, candidate gating, and same-process recovery.

The candidate is an explicit test fixture, not a new model-written feature or a
human acceptance. Its bundled application tests and preview run for real.
"""
import http.client
from pathlib import Path
import re
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from urllib.parse import urlencode

from tmh.platform import agent_api, candidates, preview, project_bootstrap
from tmh.platform.errors import ApiError
from tmh.platform.server import Platform, Req


def call(P, op, args, actor="health-fixture"):
    return agent_api.dispatch(P, Req(SimpleNamespace(headers={
        "X-Webuddy-Agent": actor, "X-Webuddy-Execution": "1"}), {}, args, "health-fixture"), op)


def prepare(P):
    created = project_bootstrap.create(P, {"key": "HP", "name": "预览健康恢复夹具",
        "brief": "隔离的 HTTP/SQLite 验收场景，不计新业务实现或人工签收。"}, "health-fixture")
    repo = Path(created["project"]["root"])
    with (repo / "README.md").open("a") as f:
        f.write("\nThis candidate is a preview health regression fixture.\n")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Health fixture", "-c",
        "user.email=health@localhost", "commit", "-qam", "Add health scenario provenance"], check=True, capture_output=True)
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    ticket = call(P, "ticket_create", {"project": "HP", "title": "预览健康失效和恢复验收夹具",
        "body": "保存事项后模拟数据库临时不可用。预览不可用时不能验收，恢复后同一进程读回原数据。",
        "request_id": "health-create"})["ticket"]
    packet = call(P, "ticket_get", {"ticket": ticket["key"]})
    sub = call(P, "candidate_submit", {"ticket": ticket["key"], "base_commit": created["commit"],
        "commit": sha, "requirement_hash": packet["requirement_hash"], "request_id": "health-submit",
        "criteria": [{"id": "A1", "text": "数据库故障阻止就绪，恢复后原事项保持", "check": "真实 HTTP/SQLite 故障与恢复"}],
        "summary": "Fixture only: same starter application, documented health regression."})
    started = call(P, "candidate_verify", {"candidate_id": sub["candidate_id"], "request_id": "health-verify"})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = P.flow.rechecks.status(started["run"])
        if state and not state["running"]:
            break
        time.sleep(.02)
    v = candidates.view(P, sub["candidate_id"])
    if not v["verification_passed"]:
        raise AssertionError(v["verification"])
    call(P, "candidate_preview", {"candidate_id": sub["candidate_id"], "request_id": "health-preview"})
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if preview.status(P.data_dir, ticket["key"]).get("state") == "up":
            return {"project": created, "ticket": ticket, "candidate": sub, "commit": sha}
        time.sleep(.05)
    raise AssertionError(preview.status(P.data_dir, ticket["key"]))


def request(rec, path="/", method="GET", fields=None, cookie=""):
    conn = http.client.HTTPConnection("127.0.0.1", rec["port"], timeout=5)
    try:
        conn.request(method, rec["prefix"] + path,
            body=urlencode(fields).encode() if fields is not None else None,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie})
        r = conn.getresponse()
        return r.status, dict(r.getheaders()), r.read()
    finally:
        conn.close()


class PreviewHealthFlowTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="webuddy-health-flow-")
        self.addCleanup(tmp.cleanup)
        data = Path(tmp.name) / "data"
        data.mkdir()
        (data / "autoflow.json").write_text('{"on":false,"preview":"off"}')
        self.P = Platform(data, "health-fixture")
        self.addCleanup(self.P.store.db.close)
        self.addCleanup(lambda: preview.stop(self.P, "HP-1"))

    def test_real_database_failure_blocks_assessment_and_recovers_same_preview(self):
        fixture = prepare(self.P)
        cid, key = fixture["candidate"]["candidate_id"], fixture["ticket"]["key"]
        db = Path(fixture["project"]["project"]["root"]) / "app.db"
        rec = preview.status(self.P.data_dir, key)
        code, headers, body = request(rec)
        self.assertEqual(code, 200)
        token = re.search(rb'name="csrf" value="([^"]+)"', body)[1].decode()
        cookie = headers.get("Set-Cookie", "").split(";", 1)[0]
        title = "故障恢复后仍保留：中文、% 与完整内容"
        self.assertEqual(request(rec, "/items", "POST", {"csrf": token, "title": title}, cookie)[0], 303)
        before = db.read_bytes()
        v = candidates.view(self.P, cid)
        assessment = {"candidate_id": cid, "verification_hash": v["verification_hash"],
            "preview_hash": v["preview_hash"], "results": [{"id": "A1", "status": "pass",
                "evidence": "Explicit test fixture observation; no human approval."}],
            "note": "Test fixture only", "request_id": "health-assess"}
        call(self.P, "candidate_assess", assessment, "independent-fixture")
        healthy = candidates.view(self.P, cid)
        self.assertTrue(healthy["technical_acceptance"])
        self.assertFalse(healthy["human_accepted"])
        saved_state = (self.P.data_dir / "previews/state.json").read_bytes()
        saved_rows = {t: self.P.store.q("SELECT * FROM " + t) for t in
            ("events", "runs", "candidate_assessments", "candidate_decisions")}
        backup = db.with_suffix(".held")
        db.rename(backup)
        db.mkdir()
        try:
            broken = candidates.view(self.P, cid)
            self.assertEqual(broken["preview"]["health"]["status_code"], 503)
            self.assertEqual(broken["preview"]["state"], "unhealthy")
            self.assertFalse(broken["preview_ready"])
            self.assertFalse(broken["technical_acceptance"])
            self.assertFalse(broken["ready_for_human"])
            self.assertEqual(broken["preview_url"], "")
            with self.assertRaises(ApiError) as rejected:
                call(self.P, "candidate_assess", dict(assessment, request_id="health-refuse"), "independent-fixture")
            self.assertEqual(rejected.exception.code, 409)
        finally:
            db.rmdir()
            backup.rename(db)
        recovered = candidates.view(self.P, cid)
        self.assertTrue(recovered["preview_ready"])
        self.assertTrue(recovered["technical_acceptance"])
        self.assertEqual(recovered["evidence_hash"], healthy["evidence_hash"])
        self.assertEqual(recovered["preview"]["pid"], rec["pid"])
        self.assertIn(title.encode(), request(rec)[2])
        self.assertEqual(db.read_bytes(), before)
        self.assertEqual((self.P.data_dir / "previews/state.json").read_bytes(), saved_state)
        self.assertEqual({t: self.P.store.q("SELECT * FROM " + t) for t in saved_rows}, saved_rows)
        self.assertNotEqual(recovered["preview"]["health"]["checked_at"], healthy["preview"]["health"]["checked_at"])


if __name__ == "__main__":
    unittest.main()
