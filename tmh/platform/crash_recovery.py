"""Reconcile a lost service owner using durable supervisor receipts, never old PIDs."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from .store import now
from . import filelock
from .supervised_process import _atomic_json, read_receipt


class OwnerLease:
    def __init__(self, stream, owner):
        self.stream, self.owner = stream, owner

    def close(self):
        self.stream.close()  # the kernel releases ownership when the handle/process closes

    def __del__(self):
        self.close()


def _lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    stream = (folder / "owner.lock").open("a+b")
    try:
        filelock.try_lock(stream)
    except BlockingIOError:
        stream.close()
        return None
    except BaseException:
        stream.close()
        raise
    return stream


def claim(data_dir, rid):
    folder = Path(data_dir) / "runs" / str(rid)
    stream = _lock(folder)
    if stream is None:
        raise ValueError("该运行仍由另一个服务实例持有")
    owner = {"token": uuid.uuid4().hex, "run_id": rid, "data_dir": str(Path(data_dir).resolve())}
    try:
        _atomic_json(folder / "owner.json", owner)
    except BaseException:
        stream.close()
        raise
    return OwnerLease(stream, owner)


def _json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("回执应为对象：" + path.name)
    return value


def _original_bytes(path, raw):
    """Publish a first raw snapshot atomically; a crash cannot leave half a backup."""
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        temporary.unlink(missing_ok=True)


def reconcile(store, data_dir, rid, wait_seconds=3):
    """A live kernel-lock owner is untouched. Unknown/mismatched evidence fails closed.

    The supervisor responds to its caller's pipe EOF independently. This code
    only waits for its receipt and hashes the original output; it sends no signal.
    """
    data_dir = Path(data_dir)
    folder = data_dir / "runs" / str(rid)
    if not (folder / "owner.json").is_file():
        raise ValueError("旧运行缺少服务所有权证明，不能自动回收或确认安全续跑")
    lock = _lock(folder)
    if lock is None:
        raise ValueError("运行仍由活跃服务持有，未修改它的状态")
    try:
        run = store.run(rid)
        owner = _json(folder / "owner.json")
        if (set(owner) != {"token", "run_id", "data_dir"} or not isinstance(owner["token"], str)
                or not owner["token"] or owner["run_id"] != rid or owner["data_dir"] != str(data_dir.resolve())):
            raise ValueError("服务所有权证明与当前运行不一致")
        life_path = folder / "lifecycle.json"
        current = None
        try:
            current = _json(life_path) if life_path.exists() else None
        except (OSError, ValueError, UnicodeError):
            pass
        if current and current.get("owner") == owner and current.get("finished") is True:
            return False

        # Preserve the first interrupted state byte-for-byte. Later checks are
        # append-only and cannot replace the original failure or user changes.
        history = folder / "restart-recovery"
        history.mkdir(exist_ok=True)
        original = history / "original-run.json"
        if not original.exists():
            _atomic_json(original, run)
        if life_path.exists() and not (history / "original-lifecycle.json").exists():
            _original_bytes(history / "original-lifecycle.json", life_path.read_bytes())
        original_run = _json(original)
        errors, recovered, raw_parts = [], [], []
        try:
            source = history / "original-lifecycle.json"
            life = _json(source) if source.exists() else {"owner": owner, "attempts": [], "finished": False}
            if life.get("owner") != owner:
                raise ValueError("生命周期与服务所有权证明不一致")
            attempts = life.get("attempts")
            if not isinstance(attempts, list) or any(not isinstance(a, dict) for a in attempts):
                raise ValueError("运行过程记录损坏，不能确认安全续跑")
        except (OSError, ValueError, UnicodeError) as exc:
            # The lease proves this known service owner is gone; unreadable
            # history is a visible block, not an indefinitely running spinner.
            errors.append("原始生命周期不可验证：%s" % exc)
            life = {"owner": owner, "attempts": [], "finished": False}
            attempts = []
        expected = set()
        deadline = time.monotonic() + wait_seconds
        for attempt in attempts:
            record = dict(attempt)
            index = record.get("attempt")
            if not isinstance(index, int) or isinstance(index, bool) or index <= 0 or index in expected:
                errors.append("过程编号缺失或重复")
                recovered.append(record)
                continue
            expected.add(index)
            part = folder / "attempts" / ("%04d" % index)
            try:
                if part.is_symlink() or part.resolve().parent != (folder / "attempts").resolve():
                    raise ValueError("过程证据路径不属于该运行")
                if not record.get("supervised"):
                    raise ValueError("旧执行缺少独立监管证明")
                receipt = read_receipt(part, owner=owner)
                while receipt is None and time.monotonic() < deadline:
                    time.sleep(.03)
                    receipt = read_receipt(part, owner=owner)
                if receipt is None:
                    raise ValueError("独立监管停止回执尚未到达；不能根据旧 PID 判断结束")
                record.update(pid=receipt.get("pid"), pgid=receipt.get("pgid"),
                              returncode=receipt["returncode"], reason=receipt["reason"],
                              elapsed_seconds=receipt["elapsed_seconds"], cleanup=receipt["cleanup"],
                              ended_at=receipt.get("ended_at"), supervisor_receipt=str(part.relative_to(data_dir) / "supervisor-result.json"))
                if receipt["cleanup"].get("complete") is not True:
                    raise ValueError("独立监管尚未证明进程组和输出均已收完")
                raw_parts.append((index, (part / "output.bin").read_bytes()))
            except (OSError, ValueError, UnicodeError) as exc:
                errors.append("过程 %s：%s" % (index, exc))
            recovered.append(record)
        attempt_root = folder / "attempts"
        if attempt_root.exists():
            actual = {p.name for p in attempt_root.iterdir()}
            if actual != {"%04d" % i for i in expected}:
                errors.append("发现生命周期之外的过程目录，不能确认全部进程已结束")
        complete = not errors
        message = ("平台服务中断；独立监管已停止全部受管进程并保留原始输出，可从保留工作树新建运行。"
                   if complete else "平台服务中断；尚无法确认全部进程和输出已收完，保留现场并阻止续跑。")
        evidence = str(history.relative_to(data_dir))
        recovery = {"state": "complete" if complete else "blocked", "reason": message,
                    "evidence": evidence, "output_complete": complete, "errors": errors}
        life.update(attempts=recovered, finished=complete, stopped_reason="owner_lost", recovery=recovery)
        if complete:
            life["ended_at"] = now()
        report = {"owner": owner, "recovery": recovery, "attempts": recovered, "checked_at": now()}
        # An unchanged blocked check must not spam output or rewrite its history.
        if current == life:
            return False
        _atomic_json(history / ("check-%s.json" % time.time_ns()), report)
        output = original_run.get("output") or ""
        for index, raw in raw_parts:
            output += "\n— 服务恢复核对：过程 %s 完整原始输出（可能与中断前流式日志重叠）\n" % index
            output += raw.decode("utf-8", "replace")
        output += "\n— " + message + ("\n" + "\n".join(errors) if errors else "") + "\n"
        result = (original_run.get("result") or "") + "\n" + message
        store.update_run(rid, status="failed", ended=now(), exit_code=125, result=result.strip(), output=output)
        # Seal last: a crash before this write leaves retry blocked and the next
        # recovery safely reconstructs the same output from the original snapshot.
        _atomic_json(life_path, life)
        return True
    finally:
        lock.close()
