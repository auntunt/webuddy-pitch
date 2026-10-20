"""Isolated browser fixture: real Platform SIGKILL, synthetic local worker only.

Run once from the repository. The restarted service stays alive for browser review.
Only this script's first Popen service is killed. Never signals historical PIDs.
The second record is explicitly synthetic missing-proof data, not a second crash.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

REPO = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
DATA = REPO / "data" / "crash-browser-2026-10-19"
ROOT = DATA / "project"
PORT = 8797
URL = f"http://127.0.0.1:{PORT}"
sys.path.insert(0, str(REPO))

WORKER = r'''
import json,os,pathlib,signal,subprocess,sys,time
root=pathlib.Path(sys.argv[1]); control=pathlib.Path(sys.argv[2]); mode=sys.argv[3]
if mode=='child':
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    (control/'child.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'script':__file__}))
    print('SYNTHETIC CHILD READY: inherits stdout and ignores TERM',flush=True)
    while True: time.sleep(.1)
before=(root/'draft.py').read_text()
if 'VALUE = 1' in before:
    note=(root/'retained-note.txt').read_text()
    print('SYNTHETIC RETRY OBSERVED '+json.dumps({'draft':before,'note':note,'workdir':str(root)},ensure_ascii=False),flush=True)
    assert before=='VALUE = 1\n# preserved unfinished synthetic implementation\n'
    assert note=='完整未跟踪说明：服务中断前已写入，续跑必须保留。\n'
    (root/'draft.py').write_text('VALUE = 2\n# synthetic retry continued preserved draft\n')
    print('本地合成检查器读回保留改动并继续完成。没有调用模型，没有执行客户验收；check:none。',flush=True)
    raise SystemExit(0)
assert before=='VALUE = 0\n',before
signal.signal(signal.SIGTERM,signal.SIG_IGN)
(root/'draft.py').write_text('VALUE = 1\n# preserved unfinished synthetic implementation\n')
(root/'retained-note.txt').write_text('完整未跟踪说明：服务中断前已写入，续跑必须保留。\n')
child=subprocess.Popen([sys.executable,__file__,str(root),str(control),'child'])
(control/'leader.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'child':child.pid,'workdir':str(root),'script':__file__}))
print('SYNTHETIC ORIGINAL OUTPUT: 中断前完整输出。保留代码、未跟踪文件和该输出；这不是完成或验收。',flush=True)
while True: time.sleep(.1)
'''


def save(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def json_read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True, stderr=subprocess.STDOUT).strip()


def api(path, body=None):
    request = urllib.request.Request(URL + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-TMH": "1"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=12) as response:
        return json.loads(response.read())


def wait(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (OSError, ValueError):
            pass
        time.sleep(.05)
    raise RuntimeError("Fixture readiness timeout")


def process(pid):
    result = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "pid=,ppid=,pgid=,stat=,lstart=,command="],
                            capture_output=True, text=True)
    raw = result.stdout.strip()
    parts = raw.split(None, 4)
    return {"pid": pid, "alive": bool(len(parts) >= 4 and not parts[3].startswith("Z")), "ps": raw}


def start_service(label):
    env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONUNBUFFERED="1", NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
    for key in ("TMH_TOKEN", "TMH_PREVIEW_PORT", "TMH_PREVIEW_BASE", "TMH_PUBLIC_URL"):
        env.pop(key, None)
    log = (EVIDENCE / f"browser-service-{label}.log").open("ab", buffering=0)
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve"], cwd=REPO, env=env,
                             stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    log.close()
    wait(lambda: child.poll() is None and api("/api/meta").get("data_dir") == str(DATA), 20)
    return child


def setup():
    from tmh.platform.store import Store, now
    reuse = "--resume-empty-fixture" in sys.argv
    if DATA.exists() and not reuse:
        raise RuntimeError("Refusing to overwrite existing fixture data: " + str(DATA))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", PORT))
    if not reuse:
        ROOT.mkdir(parents=True)
        (ROOT / "draft.py").write_text("VALUE = 0\n")
        (ROOT / "README.md").write_text("# 服务崩溃恢复合成验收夹具\n\n只用于验证运行生命周期，不是客户项目。\n")
        git("init", "-q")
        git("config", "user.name", "Webuddy synthetic fixture")
        git("config", "user.email", "fixture@localhost")
        git("add", ".")
        git("commit", "-qm", "Synthetic browser fixture baseline")
    (DATA / "worker.py").write_text(WORKER, encoding="utf-8")
    (DATA / "autoflow.json").write_text(json.dumps({"on": False, "commit": False, "check": "none", "rounds": 0, "max_agents": 1}))
    (DATA / "agents.json").write_text(json.dumps({"crash-fixture": {
        "title": "本地合成崩溃检查器（不调用模型）", "timeout": 120,
        "cmd": [sys.executable, str(DATA / "worker.py"), "{workdir}", str(DATA), "worker", "{prompt_file}"]}}, ensure_ascii=False))
    store = Store(DATA / "platform.db")
    if reuse:
        assert store.runs() == [], "Cannot reuse fixture after a run has started"
        assert (ROOT / "draft.py").read_text() == "VALUE = 0\n"
    project = store.project("CRASH") if reuse else store.add_project("CRASH", "服务中断恢复 · 合成验收", str(ROOT))
    body = ("本工单是隔离的合成验证，不是真实客户需求。\n"
            "目标：服务被真实 SIGKILL 后保留 draft.py 的 VALUE = 1、完整未跟踪说明、原始提示词和中断前输出；"
            "重启时核对独立监管回执。安全收尾后再由浏览器人工点击续跑，新工作树读回原内容并改为 VALUE = 2。\n"
            "边界：check:none，没有模型调用、客户复核、签收、合并或发布。\n")
    ticket = store.ticket("CRASH-1") if reuse else store.create_ticket(project["id"], "服务中断后保留草稿并继续（合成验收）", "合成验收", body=body, auto=False)
    service = start_service("before-kill")
    print("Started owned Platform", service.pid, flush=True)
    started = api("/api/tickets/CRASH-1/runs", {"agent": "crash-fixture", "mode": "fix"})
    rid = started["id"]
    assert rid == 1, started
    def ready():
        leader, child = json_read(DATA / "leader.json"), json_read(DATA / "child.json")
        current = api(f"/api/runs/{rid}?prompt=1")
        raw = DATA / "runs" / str(rid) / "attempts" / "0001" / "output.bin"
        return (leader and child and current.get("lifecycle", {}).get("attempts") and
                raw.exists() and b"SYNTHETIC ORIGINAL OUTPUT" in raw.read_bytes() and current)
    wait(ready)
    leader, child = json_read(DATA / "leader.json"), json_read(DATA / "child.json")
    worktree = Path(leader["workdir"])
    assert worktree != ROOT and worktree.is_relative_to(DATA / "worktrees")
    # Labelled fixture state: preserve a nonempty unfinished result through recovery.
    original_result = "【合成未完成记录】已写入 VALUE = 1 和完整说明，子进程仍在运行。不得视为业务完成。\n原始中间说明全文末尾。"
    store.update_run(rid, result=original_result)
    before = api(f"/api/runs/{rid}?prompt=1")
    save("browser-before-kill.json", {"service": process(service.pid), "run": before,
        "workers": [process(leader["pid"]), process(child["pid"])], "main_head": git("rev-parse", "HEAD"),
        "worktree_status": subprocess.check_output(["git", "-C", str(worktree), "status", "--porcelain=v1"], text=True),
        "draft": (worktree / "draft.py").read_text(), "note": (worktree / "retained-note.txt").read_text(),
        "original_result_is_labelled_synthetic_fixture": True})
    service.kill()
    assert service.wait(timeout=5) == -signal.SIGKILL
    print("SIGKILL owned Platform", service.pid, flush=True)
    wait(lambda: not process(leader["pid"])["alive"] and not process(child["pid"])["alive"], 10)
    finish_after_kill(store, project, rid, before, service.pid, leader, child, worktree, original_result)


def finish_after_kill(store, project, rid, before, service_pid, leader, child, worktree, original_result):
    from tmh.platform.store import now
    # Missing proof record: no synthetic PID is invented or signalled.
    ticket2 = store.create_ticket(project["id"], "缺失停止回执时禁止续跑（合成记录）", "合成验收",
        body="这是手工构造的缺失回执记录，仅验证 blocked UI 和显式 POST recover；不是第二次真实服务强杀。", auto=False)
    blocked = store.create_run(project["id"], ticket2["id"], "crash-fixture", "fix", "合成验收", "合成缺失回执：不要推定进程已停止。")
    bid = blocked["id"]
    blocked_wt = DATA / "worktrees" / f"CRASH-2-r{bid}"
    git("worktree", "add", "-b", f"tmh/CRASH-2-r{bid}", str(blocked_wt), "HEAD")
    store.update_run(bid, status="running", started=now(), workdir=str(blocked_wt),
        result="合成缺失回执夹具；没有真实进程，没有业务成功。", output="合成记录原始说明：等待缺失的独立监管最终回执。\n")
    folder = DATA / "runs" / str(bid)
    (folder / "attempts" / "0001").mkdir(parents=True)
    owner = {"token": uuid.uuid4().hex, "run_id": bid, "data_dir": str(DATA)}
    (folder / "owner.json").write_text(json.dumps(owner))
    (folder / "lifecycle.json").write_text(json.dumps({"owner": owner, "finished": False,
        "timeout_seconds": 120, "stopped_reason": "recovery_pending", "attempts": [
            {"attempt": 1, "kind": "synthetic-missing-proof", "supervised": True}]}))
    restarted = start_service("restarted")
    recovered = api(f"/api/runs/{rid}?prompt=1")
    blocked_api = api(f"/api/runs/{bid}?prompt=1")
    assert recovered["status"] == "failed" and recovered["lifecycle"]["finished"] is True
    assert recovered["lifecycle"]["stopped_reason"] == "owner_lost"
    assert recovered["lifecycle"]["recovery"]["state"] == "complete" and recovered["can_retry"]
    assert recovered["prompt"] == before["prompt"] and original_result in recovered["result"]
    assert "SYNTHETIC ORIGINAL OUTPUT" in recovered["output"]
    assert (worktree / "draft.py").read_text() == "VALUE = 1\n# preserved unfinished synthetic implementation\n"
    assert blocked_api["lifecycle"]["recovery"]["state"] == "blocked" and not blocked_api["can_retry"]
    save("browser-after-restart.json", {"service": process(restarted.pid), "run": recovered,
        "workers": [process(leader["pid"]), process(child["pid"])], "blocked_run": blocked_api,
        "original_worktree": str(worktree), "draft": (worktree / "draft.py").read_text(),
        "note": (worktree / "retained-note.txt").read_text(), "main_head": git("rev-parse", "HEAD")})
    manifest = {"synthetic_only": True, "url": URL + "/#/t/CRASH-1", "health_api": URL + "/api/meta",
        "first_run_api": URL + f"/api/runs/{rid}?prompt=1", "blocked_ticket": URL + "/#/t/CRASH-2",
        "blocked_run_api": URL + f"/api/runs/{bid}?prompt=1", "data_dir": str(DATA),
        "service_pid": restarted.pid, "killed_service_pid": service_pid, "worker_pids": [leader["pid"], child["pid"]],
        "worker_pgid": leader["pgid"], "original_worktree": str(worktree), "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "source_sha256": {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            REPO / "tmh/platform/agents.py", REPO / "tmh/platform/crash_recovery.py", REPO / "tmh/platform/supervised_process.py", REPO / "tmh/platform/ui.py"]}}
    save("browser-fixture-manifest.json", manifest)
    (DATA / "browser-fixture-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    store.db.close()
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        from tmh.platform.server import serve
        raise SystemExit(serve(DATA, host="127.0.0.1", port=PORT, user="合成验收", brand="Webuddy · 隔离崩溃验收"))
    if "--resume-killed-fixture" in sys.argv:
        from tmh.platform.store import Store
        snapshot = json_read(EVIDENCE / "browser-before-kill.json")
        assert snapshot and not process(snapshot["service"]["pid"])["alive"]
        store = Store(DATA / "platform.db")
        assert len(store.runs()) == 1
        leader, child = json_read(DATA / "leader.json"), json_read(DATA / "child.json")
        assert not process(leader["pid"])["alive"] and not process(child["pid"])["alive"]
        finish_after_kill(store, store.project("CRASH"), 1, snapshot["run"], snapshot["service"]["pid"],
                          leader, child, Path(leader["workdir"]), snapshot["run"]["result"])
    else:
        setup()
