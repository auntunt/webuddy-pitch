"""Create an isolated, clearly labelled browser verification conversation."""
import json
import subprocess
import sys
from pathlib import Path

evidence = Path(__file__).resolve().parent
root = evidence.parents[3]
sys.path.insert(0, str(root))
from tmh.platform import intake, signoff
from tmh.platform.server import Platform

data = root / "data/intake-recovery-verification-2026-10-19"
if (data / "platform.db").exists():
    raise SystemExit("Fixture already exists; preserve it instead of reinitializing")
data.mkdir(parents=True, exist_ok=True)
repo = data / "sample-project"
repo.mkdir()
(repo / "README.md").write_text("# SYNTHETIC intake recovery fixture\nNo customer data or production integration.\n", encoding="utf-8")
for args in (["init", "-b", "main"], ["add", "README.md"], ["-c", "user.name=Verification Fixture", "-c", "user.email=fixture@localhost", "commit", "-m", "Initialize isolated conversation fixture"]):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
control = data / "reader-control.txt"
control.write_text("timeout", encoding="utf-8")
(data / "agents.json").write_text(json.dumps({"intake-fixture": {"cmd": [sys.executable, str(evidence / "fixture-reader.py"), "{mode}", "{prompt_file}", str(control)]}}, ensure_ascii=False), encoding="utf-8")
(data / "autoflow.json").write_text(json.dumps({"on": False, "plan": False, "merge": "off", "preview": "off", "handwork": "off", "understand": "agent", "understand_agent": "intake-fixture", "understand_timeout": 10}), encoding="utf-8")
P = Platform(data, "自动流转", "Webuddy · SYNTHETIC 答复恢复验收")
p = P.store.add_project("INTREC", "事项编辑恢复 · 隔离技术验收", str(repo))
s = intake.start(P, p, "编辑已有事项后保存失败，希望修改完成后还能找到原事项。昨天开始的，所有用户都有此问题。", "自动流转", wait=True)
assert s["understood"]["by"] == "智能体", s
s = intake.confirm(P, s["id"], "自动流转")
key = s["tickets"][0]
ask = intake.ask_client(P, s["id"], "自动流转", tell=False)
for name, value in [("fixture-initial-session.json", s), ("fixture-initial-contract.json", signoff.client_ac(data, key)), ("fixture-initial-ticket.json", P.store.ticket(key)),
                    ("fixture-addresses.json", {"data": str(data), "ticket": key, "session": s["id"], "client_path": ask["path"], "base": "http://127.0.0.1:8797", "synthetic": True})]:
    (evidence / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"ticket": key, "session": s["id"], "client_path": ask["path"], "initial_run": s["understood"]["run"]}, ensure_ascii=False))
P.store.db.close()
