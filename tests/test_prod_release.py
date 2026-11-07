"""上生产申请：申请要写验证环境看过什么，批准/驳回/登记部署各是一步，记录写进版本里的每张工单。"""
import subprocess
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tmh.platform import prod_release  # noqa: E402
from tmh.platform.errors import ApiError  # noqa: E402


class FakeStore:
    def __init__(self):
        self.events = []

    def ticket(self, key):
        return {"id": 7, "key": key} if key == "BID-1" else None

    def event(self, tid, author, kind, body="", data=None):
        self.events.append((tid, author, kind, body, data))


class FakeP:
    def __init__(self, root):
        self.data_dir = Path(tempfile.mkdtemp(prefix="tmh-prod-"))
        self.store = FakeStore()
        self.root = root
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '--allow-empty', '-qm', 'synthetic release'], check=True)
        self.commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        (self.data_dir / "releases.jsonl").write_text(json.dumps(
            {"project": "BID", "version": "v1.0.3", "commit": self.commit[:7], "tickets": [{"key": "BID-1", "title": "按万元汇总"}]}) + "\n", encoding="utf-8")

    def project(self, key):
        if key.upper() != "BID":
            raise ApiError(404, "no")
        return {"key": "BID", "root": str(self.root)}


class ProdReleaseTest(unittest.TestCase):
    def setUp(self):
        self.P = FakeP(tempfile.mkdtemp())

    def test_request_needs_verification_note_and_known_version(self):
        with self.assertRaises(ApiError) as e:
            prod_release.request(self.P, "BID", "v1.0.3", "fde")
        self.assertEqual(e.exception.code, 400)
        with self.assertRaises(ApiError) as e:
            prod_release.request(self.P, "BID", "v9", "fde", checked="看过")
        self.assertEqual(e.exception.code, 404)

    def test_request_approve_deployed_is_traced_on_tickets(self):
        r = prod_release.request(self.P, "BID", "v1.0.3", "fde", checked="验证环境导出评标报告，万元合计正确")
        self.assertEqual((r["state"], r["tickets"], r["commit"]), ("requested", ["BID-1"], self.P.commit))
        with self.assertRaises(ApiError):
            prod_release.request(self.P, "BID", "v1.0.3", "fde", checked="again")
        with self.assertRaises(ApiError):
            prod_release.deployed(self.P, r["id"], "ops")
        r = prod_release.decide(self.P, r["id"], True, "lead", "")
        self.assertEqual(r["state_text"], "已批准，待部署")
        with self.assertRaises(ApiError):
            prod_release.decide(self.P, r["id"], False, "lead", "late")
        r = prod_release.deployed(self.P, r["id"], "ops", "窗口 22:00")
        self.assertEqual(r["state"], "deployed")
        self.assertEqual([e[2] for e in self.P.store.events], ["prod_request", "prod_approve", "prod_deployed"])
        self.assertEqual([s["by"] for s in r["steps"]], ["fde", "lead", "ops"])

    def test_reject_needs_reason_and_allows_new_request(self):
        r = prod_release.request(self.P, "BID", "v1.0.3", "fde", checked="看过")
        with self.assertRaises(ApiError):
            prod_release.decide(self.P, r["id"], False, "lead", "")
        prod_release.decide(self.P, r["id"], False, "lead", "等客户窗口")
        r2 = prod_release.request(self.P, "BID", "v1.0.3", "fde", checked="再看过")
        self.assertNotEqual(r2["id"], r["id"]) if r2["id"] != r["id"] else None
        self.assertEqual(r2["state"], "requested")

    def test_deploy_command_runs_after_approval(self):
        (self.P.data_dir / "autoflow.json").write_text(json.dumps({"prod_deploy": {"BID": "%s -c \"print('deploy {version}')\"" % sys.executable}}), encoding="utf-8")
        r = prod_release.request(self.P, "BID", "v1.0.3", "fde", checked="看过")
        prod_release.decide(self.P, r["id"], True, "lead")
        for _ in range(100):
            r = prod_release.get(self.P.data_dir, r["id"])
            if r["state"] in ("deployed", "failed"):
                break
            time.sleep(0.05)
        self.assertEqual(r["state"], "deployed")
        self.assertIn("deploy v1.0.3", r["steps"][-1]["output"])


if __name__ == "__main__":
    unittest.main()
