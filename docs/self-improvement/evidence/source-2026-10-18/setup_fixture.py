"""Build isolated SI-007 browser data, never customer approvals or model evidence.

Run once against a NEW data directory. Requirements/design/plan/fix and their
review rows are explicitly synthetic setup. Candidate tests are real subprocesses.
The quality/security checks are left unstarted for browser operation with Runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from tmh.platform import delivery
from tmh.platform.agents import git
from tmh.platform.store import Store, now

MARK = "SYNTHETIC · 版本绑定回归夹具（非客户数据、非真人审批）"
AUTHOR = "自动流转"
AGENT = "fixture-checker"

BASE_APP = '''"""SYNTHETIC regression fixture, deliberately incorrect main branch."""
VERSION = "main-broken"
def quote_total(quantity, unit_price):
    return quantity + unit_price
def public_profile(record):
    return dict(record)
'''
CANDIDATE_APP = '''"""SYNTHETIC regression fixture, verified candidate commit."""
VERSION = "candidate-verified"
def quote_total(quantity, unit_price):
    return quantity * unit_price
def public_profile(record):
    return {key: record[key] for key in ("id", "name") if key in record}
'''
MOVED_APP = '''"""SYNTHETIC regression fixture, deliberately broken moved branch."""
VERSION = "candidate-branch-moved"
def quote_total(quantity, unit_price):
    return quantity * unit_price + 1
def public_profile(record):
    return dict(record)
'''
QUALITY_TEST = '''import unittest
from app import quote_total
class QualityBehavior(unittest.TestCase):
    def test_total_multiplies_quantity_and_price(self):
        self.assertEqual(quote_total(3, 7), 21)
    def test_zero_quantity_has_zero_total(self):
        self.assertEqual(quote_total(0, 7), 0)
if __name__ == "__main__":
    unittest.main(verbosity=2)
'''
SECURITY_TEST = '''import unittest
from app import public_profile
class PublicProfileBoundary(unittest.TestCase):
    def test_secret_fields_are_not_exposed(self):
        source = {"id": 4, "name": "fixture", "token": "synthetic-not-a-secret", "role": "admin"}
        self.assertEqual(public_profile(source), {"id": 4, "name": "fixture"})
    def test_unknown_fields_are_not_exposed(self):
        self.assertEqual(public_profile({"extra": "private fixture data"}), {})
if __name__ == "__main__":
    unittest.main(verbosity=2)
'''

CHECKER = r'''"""Deterministic fixture checker; not an AI or a general security scanner."""
import hashlib, json, os, subprocess, sys
from pathlib import Path
data = Path(__file__).resolve().parent
manifest = json.loads((data / "fixture.json").read_text())
mode, prompt_path = sys.argv[1:3]
prompt = Path(prompt_path).read_text(encoding="utf-8")
cwd = Path.cwd()
def git(*args):
    return subprocess.check_output(["git", "-C", str(cwd), *args], text=True).strip()
stage = "quality" if "「测试与质量」阶段" in prompt else "security" if "「安全检查」阶段" in prompt else "unknown"
assert mode == "ask" and stage != "unknown", "This fixture only checks quality/security"
actual_commit = git("rev-parse", "HEAD")
content = (cwd / "app.py").read_bytes()
test = "test_quality.py" if stage == "quality" else "test_security.py"
cmd = [sys.executable, "-B", test]
result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
receipt = {
    "kind": "deterministic synthetic-fixture behavior check; not model or customer acceptance",
    "run_id": os.environ.get("TMH_RUN"), "stage": stage, "cwd": str(cwd),
    "expected_commit": manifest["candidate_commit"], "actual_commit": actual_commit,
    "expected_file_sha256": manifest["candidate_file_sha256"],
    "actual_file_sha256": hashlib.sha256(content).hexdigest(),
    "command": cmd, "exit_code": result.returncode,
    "stdout": result.stdout, "stderr": result.stderr,
    "source_status_after": git("status", "--porcelain", "--untracked-files=all"),
}
receipt["matches_candidate"] = (receipt["actual_commit"] == receipt["expected_commit"]
    and receipt["actual_file_sha256"] == receipt["expected_file_sha256"])
out = data / "checks" / ("run-" + str(receipt["run_id"]) + ".json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
print("# SYNTHETIC 回归夹具的实际行为检查\n")
print("这是真实本地 Python 测试进程，不是模型审查、全量安全扫描、真人审批或客户签收。\n")
print("阶段：" + stage + "；受检完整提交：`" + actual_commit + "`。\n")
print("读取 app.py 的 SHA256：`" + receipt["actual_file_sha256"] + "`。\n")
print("```json\n" + json.dumps(receipt, ensure_ascii=False, indent=2) + "\n```")
print("\n客户签收：尚未进行。安全检查仅覆盖示例公开资料的字段白名单边界。")
sys.exit(0 if result.returncode == 0 and receipt["matches_candidate"] and not receipt["source_status_after"] else 1)
'''


class RecordingRunner:
    """Create only the explicitly synthetic setup plan/fix run rows."""
    def __init__(self, store):
        self.store = store

    def start(self, project, ticket, agent, mode, by, **kwargs):
        if mode not in ("plan", "fix"):
            raise AssertionError("Quality/security must execute through the real Runner")
        return self.store.create_run(project["id"], ticket["id"], agent, mode, by,
                                     MARK + "\n" + kwargs["question"])


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=REPO / "data/source-verification")
    args = parser.parse_args()
    data = args.data.expanduser().resolve()
    if data.exists():
        raise SystemExit("Refusing to overwrite existing data: " + str(data))
    data.mkdir(parents=True)
    repo = data / "fixture-repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "SYNTHETIC fixture builder")
    git(repo, "config", "user.email", "synthetic-fixture@localhost")
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    (repo / "app.py").write_text(BASE_APP, encoding="utf-8")
    (repo / "test_quality.py").write_text(QUALITY_TEST, encoding="utf-8")
    (repo / "test_security.py").write_text(SECURITY_TEST, encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "SYNTHETIC incorrect main baseline")
    main_sha = git(repo, "rev-parse", "HEAD").strip()
    baseline_checks = check(repo)
    assert all(c["exit_code"] != 0 for c in baseline_checks)
    git(repo, "switch", "-qc", "fixture/candidate")
    (repo / "app.py").write_text(CANDIDATE_APP, encoding="utf-8")
    git(repo, "commit", "-qam", "SYNTHETIC candidate fixes totals and public fields")
    candidate = git(repo, "rev-parse", "HEAD").strip()
    candidate_checks = check(repo)
    assert all(c["exit_code"] == 0 for c in candidate_checks)
    diff = git(repo, "diff", candidate + "^", candidate)
    (repo / "app.py").write_text(MOVED_APP, encoding="utf-8")
    git(repo, "commit", "-qam", "SYNTHETIC branch moves after candidate was fixed")
    moved = git(repo, "rev-parse", "HEAD").strip()
    moved_checks = check(repo)
    assert all(c["exit_code"] != 0 for c in moved_checks)
    git(repo, "switch", "-q", "main")
    (data / "check_candidate.py").write_text(CHECKER, encoding="utf-8")
    dump(data / "agents.json", {"codex": {"bin": "fixture-disabled-codex"},
        "claude": {"bin": "fixture-disabled-claude"}, AGENT: {
            "title": "本地确定性检查器（非模型）", "timeout": 30,
            "cmd": [sys.executable, "-B", str(data / "check_candidate.py"), "{mode}", "{prompt_file}"]}})
    dump(data / "autoflow.json", {"on": False, "merge": "off", "preview": "off", "plan": "off", "handwork": "off", "resume": False})
    store = Store(data / "platform.db")
    project = store.add_project("SRCFIX", MARK, str(repo))
    P = SimpleNamespace(data_dir=data, store=store, runner=RecordingRunner(store), project=store.project)
    created = delivery.create(P, {"project": "SRCFIX", "type": "feature", "title": MARK,
        "goal": "只证明质量/安全检查读取指定候选提交；所有预置复核为 synthetic，不代表真人或客户审批。",
        "stages": ["requirements", "design", "develop", "quality", "security", "release"]}, AUTHOR)
    did = created["delivery"]["id"]
    tid = created["delivery"]["ticket_id"]

    def act(action, stage, **body):
        return delivery.act(P, did, dict(action=action, stage=stage, **body), AUTHOR)

    def synthetic_review(stage):
        # Seed explicit test-state directly; never impersonate a person through the review API.
        d = delivery._item(P, did)
        rows = delivery._rows(P, d)
        row = rows[stage]
        assert row["can_review"], row
        store.x("INSERT INTO delivery_reviews(artifact_id,evidence,author,created,inputs) VALUES(?,?,?,?,?)",
                (row["artifact"]["id"], MARK + "；程序直接预置测试状态，没有真人审批。", "SYNTHETIC fixture (not human)",
                 now(), json.dumps(delivery._review_inputs(rows, stage, d["stages"]), sort_keys=True)))

    for stage, body in (("requirements", "A1 数量乘单价得到总额；A2 公开资料仅包含 id/name 字段。"),
                        ("design", "app.py 维护两个纯函数；质量和安全测试分别验证 A1/A2；不得读取分支最新提交替代候选。")):
        act("save_artifact", stage, body=MARK + "\n\n" + body)
        synthetic_review(stage)
    plan = {"files": [{"path": "app.py", "goal": "修正总额并过滤公开资料字段", "role": "改动"}],
            "ac": [{"id": "A1", "text": "数量乘单价得到总额", "layer": "L2", "check": "python3 -B test_quality.py"},
                   {"id": "A2", "text": "公开资料仅包含 id/name 字段", "layer": "L2", "check": "python3 -B test_security.py"}]}
    plan_body = MARK + "\n\n这是确定性的夹具方案，不是模型生成。\n```tmh-plan\n" + json.dumps(plan, ensure_ascii=False) + "\n```"
    plan_id = act("start", "develop", agent=AGENT, mode="plan")["started_run"]
    store.update_run(plan_id, status="done", exit_code=0, ended=now(), result=plan_body, output=plan_body)
    act("collect", "develop", run_id=plan_id)
    synthetic_review("develop")
    fix_id = act("start", "develop", agent=AGENT, mode="fix")["started_run"]
    run_dir = data / "runs" / str(fix_id)
    run_dir.mkdir(parents=True)
    verification = {"check": "pass", "verdict": "pass", "files": ["app.py"], "beyond_plan": [],
        "commands": candidate_checks, "checked_commit": candidate, "checked_diff": diff,
        "fixture_notice": MARK + "；诊断 verdict 是 synthetic 设置，commands 来自真实 subprocess 执行。"}
    dump(run_dir / "verify.json", verification)
    fix_body = MARK + "\n\n夹具生成器写入候选代码；两个实际 Python 检查进程均通过。此结论不代表模型表现。\n\n" + json.dumps(candidate_checks, ensure_ascii=False, indent=2)
    store.update_run(fix_id, status="done", exit_code=0, ended=now(), result=fix_body, output=fix_body, diff=diff,
                     decision="accepted:fixture/candidate@" + candidate)
    store.event(tid, AUTHOR, "adopt", MARK + "；预置技术采纳事件，无真人审批。", {"run": fix_id, "branch": "fixture/candidate", "commit": candidate})
    act("collect", "develop", run_id=fix_id)
    synthetic_review("develop")
    other = store.create_run(project["id"], tid, AGENT, "plan", AUTHOR, "SYNTHETIC unrelated newer plan")
    store.update_run(other["id"], status="done", exit_code=0, ended=now(),
                     result='SYNTHETIC 未复核普通方案，不应替换已绑定方案。\n```tmh-plan\n{"files":[{"path":"unrelated.py","goal":"不应出现"}],"ac":[{"id":"WRONG","text":"不应使用该方案","layer":"L1","check":"none"}]}\n```')
    view = delivery.view(P, did)
    rows = {row["key"]: row for row in view["stages"]}
    source = rows["quality"]["source"]
    assert source["commit"] == candidate and source["implementation_run"] == fix_id and source["plan_run"] == plan_id
    assert rows["quality"]["can_start"] and rows["security"]["can_start"]
    binding = delivery.signoff_binding(data, store.ticket(tid)["key"])
    assert binding["plan_run"] == plan_id and not binding["valid"]
    manifest = {"notice": MARK, "data": str(data), "project_root": str(repo), "delivery_id": did,
        "ticket": store.ticket(tid)["key"], "main_commit": main_sha, "candidate_commit": candidate,
        "moved_branch_commit": moved, "candidate_file_sha256": hashlib.sha256(CANDIDATE_APP.encode()).hexdigest(),
        "plan_run": plan_id, "implementation_run": fix_id, "newer_unreviewed_plan_run": other["id"],
        "source": source, "signoff_binding": binding, "baseline_checks": baseline_checks,
        "candidate_checks": candidate_checks, "moved_branch_checks": moved_checks,
        "browser_url": "http://127.0.0.1:8795/#/delivery/" + did + "/quality"}
    dump(data / "fixture.json", manifest)
    dump(data / "setup-view.json", view)
    (data / "README.md").write_text("# " + MARK + "\n\n仅隔离技术回归。全部已有复核均为生成器预置的 synthetic 数据。\n质量、安全运行留待浏览器启动。不要以真人名义审批。\n", encoding="utf-8")
    store.db.close()
    print(json.dumps({k: manifest[k] for k in ("notice", "data", "delivery_id", "ticket", "candidate_commit", "main_commit", "moved_branch_commit", "plan_run", "implementation_run", "newer_unreviewed_plan_run", "browser_url")}, ensure_ascii=False, indent=2))


def check(repo):
    results = []
    for test in ("test_quality.py", "test_security.py"):
        cmd = [sys.executable, "-B", test]
        r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
        results.append({"name": test, "cmd": " ".join(cmd), "exit_code": r.returncode,
                        "output": r.stdout + r.stderr, "commit": git(repo, "rev-parse", "HEAD").strip()})
    return results


if __name__ == "__main__":
    main()
