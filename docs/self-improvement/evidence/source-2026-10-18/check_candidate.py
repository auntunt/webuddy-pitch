"""Deterministic fixture checker; not an AI or a general security scanner."""
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
