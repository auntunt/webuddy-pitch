#!/usr/bin/env python3
"""Exercise the real bootstrap entry point in an owned temporary data directory.

All persistent outputs are review evidence beside this script. Existing platform
state, projects, services and production are not used or changed.
"""
import ast
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace


EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[3]
sys.path.insert(0, str(ROOT))
from tmh.platform import project_bootstrap
from tmh.platform.store import Store


def sha(data):
    return hashlib.sha256(data).hexdigest()


def test_methods(source):
    tree = ast.parse(source)
    case = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ApplicationTest")
    return {node.name: ast.get_source_segment(source, node) for node in case.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def main():
    bootstrap_path = Path(project_bootstrap.__file__)
    bootstrap_before = bootstrap_path.read_bytes()
    previous = json.loads((ROOT / "docs/self-improvement/evidence/runtime-2026-10-18/bootv2/independent-review-run6.json").read_text())
    before_methods = test_methods((EVIDENCE / "before-tests.py").read_text())
    report = {"reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Isolated temporary Store/data_dir; real project_bootstrap.create; no existing service or data",
              "bootstrap_sha256": sha(bootstrap_before)}
    with tempfile.TemporaryDirectory(prefix="webuddy-independent-bootstrap-review-") as temp:
        data = Path(temp)
        store = Store(data / "platform.db")
        try:
            platform = SimpleNamespace(data_dir=data, store=store)
            receipt = project_bootstrap.create(platform, {"key": "INDCREATE", "name": "独立模板验收临时项目",
                                              "brief": "只验证新项目创建后的编辑、保存及失败重试，不代表业务交付。"},
                                               "独立技术验证")
            root = Path(receipt["project"]["root"])
            (EVIDENCE / "independent-create-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
            for kind, result in receipt["checks"].items():
                (EVIDENCE / ("independent-create-" + kind + ".log")).write_text(result["output"])
                assert result["exit_code"] == 0, (kind, result)
            assert root == (data / "projects" / "INDCREATE").resolve()
            saved_receipt = json.loads((data / "project-bootstrap/INDCREATE.json").read_text())
            assert saved_receipt == receipt
            assert receipt["commit"] == git(root, "rev-parse", "HEAD").decode().strip()
            assert not git(root, "status", "--porcelain")
            generated_app = (root / "app.py").read_bytes()
            generated_tests = (root / "tests/test_app.py").read_bytes()
            (EVIDENCE / "independent-generated-app.py").write_bytes(generated_app)
            (EVIDENCE / "independent-generated-tests.py").write_bytes(generated_tests)
            current_methods = test_methods(generated_tests.decode())
            assert len(before_methods) == 23 and len(current_methods) == 26
            changed_old = [name for name, source in before_methods.items() if current_methods.get(name) != source]
            assert not changed_old, changed_old
            assert generated_app == project_bootstrap.APP.encode()
            assert generated_tests == project_bootstrap.TESTS.encode()
            assert sha(generated_app) == previous["source_sha256"]["app.py"]
            assert sha(generated_tests) == previous["source_sha256"]["tests/test_app.py"]
            added = sorted(set(current_methods) - set(before_methods))
            assert added == previous["added_test_methods"]
            files = git(root, "ls-tree", "-r", "--name-only", "HEAD").decode().splitlines()
            manifest = {name: {"bytes": (root / name).stat().st_size, "sha256": sha((root / name).read_bytes())}
                        for name in files}
            script = ROOT / "docs/self-improvement/evidence/runtime-2026-10-18/bootv2/independent_acceptance.py"
            command = [sys.executable, str(script), str(root)]
            acceptance = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
            (EVIDENCE / "independent-acceptance-green.log").write_bytes(acceptance.stdout)
            assert acceptance.returncode == 0, acceptance.stdout.decode()
            summary = json.loads(acceptance.stdout.decode().splitlines()[-1])
            assert summary == {"tests": 12, "failures": 0, "errors": 0, "successful": True, "source_unchanged": True}
            assert not git(root, "status", "--porcelain"), "Independent acceptance changed the generated checkout"
            assert not (root / "app.db").exists(), "Acceptance must use temporary databases, not the generated project's data"
            assert bootstrap_path.read_bytes() == bootstrap_before, "Template changed during review"
            report.update({"create_receipt": "independent-create-receipt.json", "generated_commit": receipt["commit"],
                           "build_exit_code": receipt["checks"]["build"]["exit_code"],
                           "app_tests_exit_code": receipt["checks"]["test"]["exit_code"], "app_test_count": 26,
                           "source_sha256": {"app.py": sha(generated_app), "tests/test_app.py": sha(generated_tests)},
                           "generated_files": manifest, "original_test_methods_unchanged": len(before_methods),
                           "removed_or_modified_original_methods": changed_old, "added_methods": added,
                           "entire_source_matches_previously_verified_BOOTV2_run6": True,
                           "independent_acceptance": {**summary, "command": command, "exit_code": acceptance.returncode,
                                                       "log": "independent-acceptance-green.log"},
                           "created_checkout_remained_clean": True, "project_app_db_created": False,
                           "browser_performed_by_this_reviewer": False,
                           "review_decision": "No blocking finding in the frozen template change or its generated app."})
        finally:
            store.db.close()
    report["temporary_data_removed"] = not data.exists()
    (EVIDENCE / "independent-create-review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
