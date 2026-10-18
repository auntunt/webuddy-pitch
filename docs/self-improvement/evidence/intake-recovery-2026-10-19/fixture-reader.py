"""Deterministic process fixture, never a real model or customer's response."""
import json
import subprocess
import sys
import time
from pathlib import Path

prompt = Path(sys.argv[2]).read_text(encoding="utf-8")
control = Path(sys.argv[3]).read_text(encoding="utf-8").strip()
answered = "<<<答复开始" in prompt
if answered and control == "timeout":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    print("SYNTHETIC timeout fixture; child PID %s; original answer remains in prompt" % child.pid, flush=True)
    time.sleep(120)
if answered:
    time.sleep(3)  # makes the real browser's running state observable

item = {
    "title": "事项编辑后保留原编号", "quote": "编辑已有事项后保存失败，希望修改完成后还能找到原事项",
    "kind": "缺陷", "restated": "编辑已有事项后应能保存，并保留原事项编号和完成状态", "flow": "新模块",
    "said": {"trigger": "编辑已有事项后", "expected": "保存并保留原事项", "who": "所有用户", "since": "昨天"},
    "questions": [] if answered else [{"q": "保存遇到故障时，希望保留什么，恢复后怎么操作？", "options": [], "blocks": ["A1"]}],
    "ac": [
        {"id": "A1", "text": "当保存遇到故障时，系统应当" + ("完整保留输入；恢复后重试保存到原事项" if answered else "【待确认：如何恢复】"),
         "check": "模拟保存失败，核对输入保留，恢复后重试并检查原事项编号及完成状态"},
        {"id": "A2", "text": "当用户取消编辑时，系统应当保留原事项内容", "check": "修改输入后取消，重新打开事项并核对原内容"},
    ],
    "keep": ["原事项编号、完成状态和其他事项保持不变"],
}
print("```tmh-intake\n" + json.dumps({"title": "事项编辑故障恢复 · SYNTHETIC", "items": [item]}, ensure_ascii=False) + "\n```")
