"""Versioned behavioral probe recipes inspired by Harness²'s probe/evidence loop.

This adapter refines the verification surface, not model weights or safety
policy. It runs the same maintainer-owned probe against two immutable source
versions, keeps unknown separate from failure, and exposes evidence to future
agents. No candidate-controlled command, benchmark grader or upstream executor
is installed. See docs/harness2-integration.md for provenance and boundaries.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import threading
import time
import uuid

from .errors import ApiError
from . import filelock
from .store import now
from .supervised_process import _atomic_json, read_receipt, run_supervised


UPSTREAM = {"repository": "https://github.com/google-research/harness2",
            "commit": "1cfe254e8d25b15f37048c3730134686abe60335", "license": "Apache-2.0"}
TOTAL_SECONDS = 90
PROBE = Path(__file__).resolve().parents[1] / "probes" / "items_search.py"
SCHEMA = """
CREATE TABLE IF NOT EXISTS harness_probe_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id INTEGER NOT NULL,
 author TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL,
 created TEXT NOT NULL, ended TEXT NOT NULL DEFAULT '', result_hash TEXT NOT NULL DEFAULT '');
"""


def schema(store):
    with store.lock:
        store.db.executescript(SCHEMA)
        store.db.commit()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def recipes():
    from ..probes.items_search import RECIPE, CHECKS
    item = {"id": RECIPE, "name": "事项管理搜索、筛选及持久保存", "checks": CHECKS,
            "scope": "Python BOOTV2 starter app.py CLI with a fresh SQLite database; not a universal web app verifier",
            "source_sha256": hashlib.sha256(PROBE.read_bytes()).hexdigest(),
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "total_seconds": TOTAL_SECONDS, "upstream": UPSTREAM}
    return [dict(item, version=digest(item))]


def folder(P, pid):
    return Path(P.data_dir).resolve() / "harness-probes" / str(int(pid))


def row(P, pid):
    item = P.store.one("SELECT * FROM harness_probe_runs WHERE id=?", (pid,))
    if not item:
        raise ApiError(404, "没有这个业务探测实验")
    return item


def _active(path):
    if not path.is_file():
        return False
    try:
        with path.open("r+b" if os.name == "nt" else "rb") as stream:
            filelock.try_lock(stream)
            filelock.unlock(stream)
            return False
    except BlockingIOError:
        return True


@contextmanager
def _completion(root):
    # Serializes a stop receipt and publication across service/store instances.
    with (root / "completion.lock").open("a+b") as stream:
        filelock.try_lock(stream, blocking=True)
        try:
            yield
        finally:
            filelock.unlock(stream)


def _source_current(P, source):
    from .candidates import view as candidate_view
    # Exclude this probe to avoid a circular hash/check. The ordinary build
    # verification is the immutable prerequisite captured when we start.
    try:
        state = candidate_view(P, source["candidate_id"], include_probe=False)
        return bool(state["current"] and state["verification_passed"]
                    and digest(state["verification"]) == source["verification_digest"])
    except (ApiError, OSError, ValueError, KeyError, TypeError):
        return False


def view(P, pid):
    item = row(P, pid)
    source = json.loads(item["source"])
    root = folder(P, pid)
    active = _active(root / "owner.lock")
    status = item["status"]
    problems, result = [], None
    clean = True
    # Finished operations cannot become successful through a mere exit code or
    # missing child process. Validate the same supervisor receipts used by runs.
    attempts = [root / arm / "process" for arm in ("baseline", "candidate")]
    for path in attempts:
        if path.exists():
            try:
                owner = json.loads((root / "owner.json").read_text())
                receipt = read_receipt(path, owner)
                if not receipt or not receipt["cleanup"]["complete"]:
                    clean = False
            except (OSError, ValueError, TypeError, KeyError):
                clean = False
    if status == "running" and not active:
        status = "interrupted"
        problems.append("实验所有者已停止；保留原始探测结果，不能把中断当通过")
        # A crash between claim and process creation cannot prove no process
        # was created. Keep recovery conservative, including an empty folder.
        if not any(p.exists() for p in attempts):
            clean = False
    if item["result_hash"]:
        try:
            raw = (root / "result.json").read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["result_hash"]:
                raise ValueError("实验汇总哈希不匹配")
            result = json.loads(raw)
            if result["source"] != source:
                raise ValueError("实验汇总与登记来源不一致")
            for name, expected in result["artifacts"].items():
                path = root / name
                if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                    raise ValueError("探测证据被修改或缺失：" + name)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            problems.append(str(exc))
            result = None
    recipe = next((r for r in recipes() if r["id"] == source["recipe"]["id"]), None)
    if not recipe or recipe["version"] != source["recipe"]["version"]:
        problems.append("探测配方或执行器已更新，需要重新运行")
    if not clean:
        problems.append("受管进程的停止及完整输出回执尚未核对通过")
    observed_passed = bool(status == "done" and not problems and result and result["candidate_passed"])
    source_current = _source_current(P, source)
    if not source_current:
        problems.append("需求、配置、候选或独立验证已变化；历史观察保留，当前探测已失效")
    passed = observed_passed and source_current
    return dict(item, source=source, status=status, running=active, cleanup_complete=clean,
                passed=passed, observed_passed=observed_passed, source_current=source_current,
                blocked=problems, result=result,
                evidence_hash=digest({"source": source, "result_hash": item["result_hash"]}) if passed else "",
                artifact_dir=str(root), human_acceptance=False)


def current(P, cid):
    if not P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='harness_probe_runs'"):
        return None
    latest = P.store.one("SELECT id FROM harness_probe_runs WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (cid,))
    return view(P, latest["id"]) if latest else None


def start(P, actor, args, mutation):
    from . import candidates
    from .agent_api import _ready
    candidate = candidates._row(P, args["candidate_id"])
    recipe = next((r for r in recipes() if r["id"] == args["recipe"]), None)
    if not recipe:
        raise ApiError(400, "未知配方；先读取 harness_recipes")
    if set(a["id"] for a in json.loads(candidate["criteria"])) != set(recipe["checks"]):
        raise ApiError(409, "配方需要 A1–A4 验收编号；请核对检查说明是否覆盖实际需求")
    with candidates.guard(P, candidate["ticket_id"]), P.store.lock:
        _ready(P, P.store.ticket(candidate["ticket_id"]))
        state = candidates.view(P, candidate["id"])
        if not state["current"] or not state["verification_passed"]:
            raise ApiError(409, "先完成当前候选的独立构建与测试，再运行业务探测")
        old = current(P, candidate["id"])
        if old and (old["running"] or not old["cleanup_complete"]):
            raise ApiError(409, "已有探测仍在执行或停止回执不完整，拒绝重复启动")
        source = {"candidate_id": candidate["id"], "ticket_id": candidate["ticket_id"], "ticket": state["ticket"],
                  "project_id": P.store.ticket(candidate["ticket_id"])["project_id"],
                  "base": candidate["base_commit"], "commit": candidate["commit_sha"],
                  "requirement_hash": candidate["requirement_hash"], "criteria": json.loads(candidate["criteria"]),
                  "configuration_hash": candidate["configuration_hash"],
                  "verification_digest": digest(state["verification"]), "recipe": recipe}
        mutation()
        pid = P.store.x("INSERT INTO harness_probe_runs(candidate_id,author,source,status,created) VALUES(?,?,?,'running',?)",
                          (candidate["id"], actor, json.dumps(source, ensure_ascii=False), now()))
        # Store.x returns lastrowid; ownership is acquired before the worker can
        # be observed as abandoned by another process.
        root = folder(P, pid)
        root.mkdir(parents=True, exist_ok=True)
        lock = (root / "owner.lock").open("a+b")
        filelock.try_lock(lock)
        owner = {"token": uuid.uuid4().hex, "run_id": pid, "data_dir": str(root.parent)}
        _atomic_json(root / "owner.json", owner, exclusive=True)
        recipe_bytes = PROBE.read_bytes()
        if hashlib.sha256(recipe_bytes).hexdigest() != recipe["source_sha256"]:
            filelock.unlock(lock)
            lock.close()
            raise ApiError(409, "配方在启动时发生变化，请核对本次请求回执")
        (root / "recipe.py").write_bytes(recipe_bytes)
        _atomic_json(root / "source.json", source, exclusive=True)
        thread = threading.Thread(target=_run, args=(P, pid, source, lock, owner), daemon=True)
        thread.start()
        return {"probe_id": pid, "candidate_id": candidate["id"], "status": "running",
                "recipe_version": recipe["version"], "total_seconds": TOTAL_SECONDS,
                "human_acceptance": False}


def _snapshot(repo, commit, destination, timeout):
    # git archive honors export-ignore/export-subst and can change the exact
    # source under test. Read the actual tree and blob objects instead.
    deadline = time.monotonic() + max(.01, timeout)
    tree = subprocess.run(["git", "-C", str(repo), "ls-tree", "-rz", "--full-tree", commit],
                          capture_output=True, check=True, timeout=max(.01, deadline - time.monotonic())).stdout
    entries = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        meta, raw_name = record.split(b"\t", 1)
        mode, kind, oid = meta.split()
        name = raw_name.decode("utf-8", "strict")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("当前配方不支持符号链接或特殊源文件：" + name)
        entries.append((name, oid, mode))
    blobs = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"],
        input=b"".join(oid + b"\n" for _, oid, _ in entries), capture_output=True, check=True,
        timeout=max(.01, deadline - time.monotonic())).stdout
    destination.mkdir(parents=True)
    offset = 0
    for name, oid, mode in entries:
        end = blobs.index(b"\n", offset)
        actual, kind, size = blobs[offset:end].split()
        count = int(size)
        if actual != oid or kind != b"blob":
            raise ValueError("Git对象与固定版本不一致")
        data = blobs[end + 1:end + 1 + count]
        if len(data) != count or blobs[end + 1 + count:end + 2 + count] != b"\n":
            raise ValueError("Git对象输出不完整")
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o755 if mode == b"100755" else 0o644)
        offset = end + count + 2
    if offset != len(blobs):
        raise ValueError("Git对象输出包含未绑定的数据")
    return {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in destination.rglob("*") if p.is_file()}


def _run(P, pid, source, lock, owner):
    root = folder(P, pid)
    deadline = time.monotonic() + TOTAL_SECONDS
    result = {"schema": 1, "source": source, "arms": {}, "candidate_passed": False,
              "comparison": "unknown", "limitations": "One task, two source versions. This is behavioral evidence, not model improvement or a causal harness A/B estimate."}
    try:
        repo = Path(P.store.project(source["project_id"])["root"])
        class Cancel:
            def is_set(self):
                return (root / "cancel.json").exists()
        cancel = Cancel()
        for arm, commit in (("baseline", source["base"]), ("candidate", source["commit"])):
            if cancel.is_set():
                raise RuntimeError("cancelled: 操作者已请求停止本次实验")
            if not _source_current(P, source):
                raise RuntimeError("候选或验证来源在探测期间失效，停止后续执行")
            path = root / arm
            workspace = path / "workspace"
            before = _snapshot(repo, commit, workspace, min(20, deadline - time.monotonic()))
            _atomic_json(path / "source-files.json", before, exclusive=True)
            process = run_supervised([sys.executable, "-u", str(root / "recipe.py"), "--root", str(workspace), "--output", str(path / "observations")],
                                     folder=path / "process", owner=owner, cwd=workspace,
                                     timeout=max(.01, deadline - time.monotonic()), cancel_event=cancel)
            changed = [name for name, expected in before.items()
                       if not (workspace / name).is_file() or (workspace / name).is_symlink()
                       or hashlib.sha256((workspace / name).read_bytes()).hexdigest() != expected]
            report = None
            error = ""
            try:
                report = json.loads((path / "observations" / "report.json").read_text())
                checks = report["results"]
                expected = set(source["recipe"]["checks"])
                if len(checks) != len(expected) or {c["id"] for c in checks} != expected:
                    raise ValueError("业务探测结果缺项或重复")
                if any(c["status"] not in ("pass", "fail", "unknown") for c in checks):
                    raise ValueError("业务探测状态不正确")
                if not report.get("observations") or report.get("recipe") != source["recipe"]["id"]:
                    raise ValueError("没有真实HTTP观察或配方不匹配")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                report, error = None, str(exc)
            protocol_ok = process.returncode == 0 and process.cleanup["complete"] and not changed and report and not report["setup_error"]
            passed = bool(protocol_ok and all(c["status"] == "pass" for c in report["results"]))
            result["arms"][arm] = {"commit": commit, "passed": passed,
                "conclusive": bool(protocol_ok and all(c["status"] != "unknown" for c in report["results"])),
                "results": report["results"] if report else [], "error": error, "source_changed": changed,
                "process": {"exit_code": process.returncode, "reason": process.reason, "cleanup": process.cleanup,
                            "elapsed_seconds": process.elapsed}}
            if not process.cleanup["complete"]:
                raise RuntimeError("前一次探测进程尚未回收，不开始下一次")
        base, candidate = result["arms"]["baseline"], result["arms"]["candidate"]
        if not _source_current(P, source):
            raise RuntimeError("候选或独立验证来源在结果发布前失效，保留观察但不通过")
        result["candidate_passed"] = candidate["passed"]
        if base["conclusive"] and candidate["conclusive"]:
            before = {r["id"]: r["status"] for r in base["results"]}
            after = {r["id"]: r["status"] for r in candidate["results"]}
            result["improved_checks"] = [k for k in before if before[k] == "fail" and after[k] == "pass"]
            result["regressed_checks"] = [k for k in before if before[k] == "pass" and after[k] == "fail"]
            result["comparison"] = "regressed" if result["regressed_checks"] else "improved" if result["improved_checks"] else "unchanged"
    except BaseException as exc:
        result["error"] = "%s: %s" % (type(exc).__name__, exc)
        result["candidate_passed"] = False
    finally:
        try:
            with _completion(root):
                if (root / "cancel.json").exists():
                    result.update(error="cancelled: 操作者已请求停止本次实验", candidate_passed=False)
                elif time.monotonic() > deadline:
                    result.update(error="timeout: 整次探测预算已耗尽", candidate_passed=False)
                if any(p.is_symlink() for p in root.rglob("*")):
                    result.update(error="探测产物中出现符号链接，拒绝采纳", candidate_passed=False)
                result["artifacts"] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in root.rglob("*") if p.is_file() and not p.is_symlink() and p.name not in ("owner.lock", "completion.lock", "result.json")}
                _atomic_json(root / "result.json", result, exclusive=True)
                hash_ = hashlib.sha256((root / "result.json").read_bytes()).hexdigest()
                P.store.x("UPDATE harness_probe_runs SET status=?,ended=?,result_hash=? WHERE id=?",
                          ("failed" if result.get("error") else "done", now(), hash_, pid))
        finally:
            filelock.unlock(lock)
            lock.close()


def library(P, project):
    p = P.store.project(project)
    if not p:
        raise ApiError(404, "没有这个项目")
    if not P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='harness_probe_runs'"):
        return {"project": project, "entries": [], "automatic_policy_changes": False}
    values = P.store.q("SELECT h.id FROM harness_probe_runs h JOIN code_candidates c ON c.id=h.candidate_id JOIN tickets t ON t.id=c.ticket_id WHERE t.project_id=? ORDER BY h.id", (p["id"],))
    entries = []
    for value in values:
        item = view(P, value["id"])
        if item["observed_passed"]:
            source = item["source"]
            entries.append({"probe_id": item["id"], "recipe": source["recipe"], "ticket": source["ticket"],
                "commit": source["commit"], "base": source["base"],
                "evidence_hash": digest({"source": source, "result_hash": item["result_hash"]}),
                "source_current": item["source_current"],
                "comparison": item["result"]["comparison"],
                "lesson": "此版本通过候选外部的HTTP/SQLite检查。后续事项管理改动应复用该配方，并核对适用的验收标准；历史通过不能代替新版本重验。",
                "scope": "historical technical evidence, not human acceptance or a general success rate"})
    return {"project": project, "entries": entries, "automatic_policy_changes": False}


def execute(P, actor, operation, args, mutation):
    if operation == "harness_recipes":
        return {"recipes": recipes(), "upstream": UPSTREAM, "automatic_model_runs": False}
    if operation == "harness_probe_start":
        return start(P, actor, args, mutation)
    if operation == "harness_probe_get":
        return view(P, args["probe_id"])
    if operation == "harness_probe_cancel":
        item = row(P, args["probe_id"])
        root = folder(P, item["id"])
        if not root.is_dir():
            raise ApiError(409, "探测所有者记录不完整，不能确认停止")
        with _completion(root):
            item = row(P, item["id"])
            if item["status"] != "running" or not _active(root / "owner.lock"):
                raise ApiError(409, "当前没有正在执行的探测")
            mutation()
            if not (root / "cancel.json").exists():
                _atomic_json(root / "cancel.json", {"author": actor, "created": now()}, exclusive=True)
        return {"probe_id": item["id"], "stop_requested": True, "cleanup_confirmed": False}
    if operation == "harness_library":
        return library(P, args["project"])
    raise ApiError(400, "未知实验操作")
