"""Durable verification operations, isolated from the original agent run.

Commands reuse Runner's budgets, ownership leases and independent supervisor.
Only verification_operations rows and verification-operations evidence are
written here; the source run and its original artifacts are never rewritten.
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from .agents import Runner
from . import filelock
from .store import now
from .supervised_process import _atomic_json, read_receipt


SCHEMA = """
CREATE TABLE IF NOT EXISTS verification_operations (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source_run INTEGER NOT NULL, project_id INTEGER NOT NULL, ticket_id INTEGER,
 author TEXT NOT NULL, status TEXT NOT NULL,
 created TEXT NOT NULL, started TEXT DEFAULT '', ended TEXT DEFAULT '',
 exit_code INTEGER, result TEXT DEFAULT '', output TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_verification_source ON verification_operations(source_run,id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_verification_unfinished
 ON verification_operations(source_run) WHERE status IN ('queued','running');
"""


def _validate_source(source):
    if not isinstance(source, dict):
        raise ValueError("复检版本绑定必须为对象")
    for primary, alias in (("source_commit", "commit"), ("diffhash", "diff_sha256")):
        if primary in source and alias in source and source[primary] != source[alias]:
            raise ValueError("复检版本绑定字段相互矛盾：" + primary)
    commit = source.get("source_commit", source.get("commit"))
    diffhash = source.get("diffhash", source.get("diff_sha256"))
    # An unadopted working tree is identified by its base and full diff hash;
    # an empty candidate commit is explicit, never replaced by an invented SHA.
    if commit != "" or source.get("decision"):
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("复检版本绑定缺少完整 source_commit")
    for key, value, width in (("base", source.get("base"), 40), ("diffhash", diffhash, 64)):
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % width, value):
            raise ValueError("复检版本绑定缺少完整 " + key)


@contextmanager
def source_guard(data_dir, rid):
    """Exclude recheck/adoption decisions for one source, across processes.

    The descriptor is not inherited by subprocesses. Its kernel lock disappears
    on service death; durable operation evidence remains the restart gate.
    """
    rid = int(rid)
    if rid <= 0:
        raise ValueError("无效的来源运行编号")
    folder = Path(data_dir).resolve() / "verification-operations" / "source-locks"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (str(rid) + ".lock")).open("a+b") as stream:
        try:
            filelock.try_lock(stream)
        except BlockingIOError as exc:
            raise ValueError("该来源正在复检或处理采纳决定，请稍后再试") from exc
        try:
            yield
        finally:
            filelock.unlock(stream)


class _OperationStore:
    """The deliberately small Store protocol required by the managed runner."""
    def __init__(self, store):
        self.store = store
        self.lock = store.lock

    def run(self, rid):
        return self.store.one("SELECT * FROM verification_operations WHERE id=?", (rid,))

    def update_run(self, rid, **fields):
        allowed = {"status", "started", "ended", "exit_code", "result", "output"}
        if not fields or set(fields) - allowed:
            raise ValueError("unsupported verification operation update")
        if "status" in fields and fields["status"] not in ("queued", "running", "done", "failed", "cancelled"):
            raise ValueError("invalid verification operation status")
        self.store.x("UPDATE verification_operations SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?",
                     (*fields.values(), rid))

    def append_output(self, rid, text):
        self.store.x("UPDATE verification_operations SET output=output||? WHERE id=?", (text, rid))

    def q(self, sql, args=()):
        # Runner.recover is the sole SQL caller. Reject other queries rather
        # than accidentally falling through to the ordinary runs table.
        if not re.fullmatch(r"SELECT id FROM runs WHERE status IN \('[a-z]+(?:','[a-z]+)*'\)", sql):
            raise ValueError("unsupported verification runner query")
        return self.store.q(sql.replace(" FROM runs ", " FROM verification_operations "), args)


class Operations:
    def __init__(self, store, data_dir):
        self.store = store
        self.main_data_dir = Path(data_dir).resolve()
        self.data_dir = self.main_data_dir / "verification-operations"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with store.lock:
            store.db.executescript(SCHEMA)
            store.db.commit()
        self.adapter = _OperationStore(store)
        self.runner = Runner(self.adapter, self.data_dir)
        self.runner.evidence_root = self.main_data_dir
        self._source_guards = {}

    def folder(self, opid):
        return self.data_dir / "runs" / str(int(opid))

    def _read_json(self, path):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("回执必须为对象：" + path.name)
        return value

    def _owner_active(self, folder):
        lock_path = folder / "owner.lock"
        if not lock_path.exists():
            return False
        with lock_path.open("r+b" if os.name == "nt" else "rb") as stream:
            try:
                filelock.try_lock(stream)
            except BlockingIOError:
                return True
            filelock.unlock(stream)
        return False

    def _view(self, row):
        if row is None:
            return None
        if not {"id", "source_run", "status"}.issubset(row):
            raise ValueError("复检操作数据格式损坏")
        item = dict(row)
        folder = self.folder(row["id"])
        blocked, life, manifest = [], None, None
        owner_active = False
        try:
            owner_active = self._owner_active(folder)
            life = self._read_json(folder / "lifecycle.json")
            owner = self._read_json(folder / "owner.json")
            if (life.get("owner") != owner or owner.get("run_id") != row["id"] or
                    owner.get("data_dir") != str(self.data_dir) or not owner.get("token")):
                raise ValueError("复检生命周期与操作所有权不一致")
            attempts = life.get("attempts")
            if not isinstance(attempts, list) or any(not isinstance(a, dict) for a in attempts):
                raise ValueError("复检过程记录损坏")
            if life.get("finished") is not True:
                blocked.append("复检尚未封存停止回执，请等待完成或检查停止回执")
            elif not owner_active:
                expected = set()
                for attempt in attempts:
                    index = attempt.get("attempt")
                    if type(index) is not int or index <= 0 or index in expected:
                        raise ValueError("复检过程编号缺失或重复")
                    expected.add(index)
                    part = folder / "attempts" / ("%04d" % index)
                    if part.is_symlink():
                        raise ValueError("复检证据目录不允许指向其他位置")
                    if not attempt.get("supervised") or (attempt.get("cleanup") or {}).get("complete") is not True:
                        raise ValueError("复检仍有未证明回收的执行过程")
                    receipt = read_receipt(part, owner)
                    if receipt is None or receipt["cleanup"].get("complete") is not True:
                        raise ValueError("复检独立监管停止回执尚不完整")
                attempts_root = folder / "attempts"
                actual = {p.name for p in attempts_root.iterdir()} if attempts_root.exists() else set()
                if actual != {"%04d" % i for i in expected}:
                    raise ValueError("发现生命周期之外的复检过程")
            recovery = life.get("recovery")
            if recovery is not None and (not isinstance(recovery, dict) or recovery.get("state") != "complete"):
                blocked.append("中断复检尚未确认全部进程与输出已收完")
        except (OSError, ValueError, UnicodeError, TypeError, AttributeError) as exc:
            blocked.append("复检停止证据不可验证：" + str(exc))
        source_path = folder / "source.json"
        try:
            if source_path.exists():
                manifest = self._read_json(source_path)
                if (manifest.get("schema") != 1 or manifest.get("operation_id") != row["id"] or
                        manifest.get("source_run") != row["source_run"] or not isinstance(manifest.get("source"), dict)):
                    raise ValueError("复检代码版本绑定与操作不一致")
                _validate_source(manifest["source"])
                if "run" in manifest["source"] and manifest["source"]["run"] != row["source_run"]:
                    raise ValueError("复检版本绑定的来源运行不一致")
            elif row["status"] == "done":
                raise ValueError("成功复检缺少代码版本绑定")
        except (OSError, ValueError, UnicodeError) as exc:
            blocked.append("复检版本证据不可验证：" + str(exc))
        active_status = row["status"] in ("queued", "running")
        if active_status or owner_active:
            blocked.insert(0, "该来源已有进行中的复检")
        item.update(lifecycle=life or {}, source=manifest.get("source") if manifest else None,
                    source_manifest=manifest, owner_active=owner_active,
                    running=active_status or owner_active or bool(life and life.get("finished") is not True),
                    can_retry=not blocked, blocked=blocked, retry_blocked=list(blocked),
                    recovery=life.get("recovery") if isinstance(life, dict) else None,
                    evidence=str(folder.relative_to(self.main_data_dir)))
        return item

    def get(self, opid):
        return self._view(self.adapter.run(int(opid)))

    def status(self, source_run):
        row = self.store.one("SELECT * FROM verification_operations WHERE source_run=? ORDER BY id DESC LIMIT 1",
                             (int(source_run),))
        return self._view(row)

    def start(self, source_run, by, budget=1800):
        source_run = int(source_run)
        budget = float(budget)
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("复检总时限必须是正数秒")
        opid = None
        guard = source_guard(self.main_data_dir, source_run)
        guard.__enter__()
        try:
            return self._start_guarded(source_run, by, budget, guard)
        except BaseException:
            guard.__exit__(None, None, None)
            raise

    def _start_guarded(self, source_run, by, budget, guard):
        opid = None
        with self.store.lock:
            try:
                self.store.db.execute("BEGIN IMMEDIATE")
                source = self.store.run(source_run)
                if not source:
                    raise ValueError("没有这个来源运行")
                if source["mode"] != "fix" or source["status"] != "done" or not source["diff"]:
                    raise ValueError("来源运行没有已完成且可复检的代码改动")
                if source["decision"] and not source["decision"].startswith("accepted:"):
                    raise ValueError("来源改动已经放弃，不能独立复检")
                previous = self.status(source_run)
                if previous and not previous["can_retry"]:
                    raise ValueError("；".join(previous["blocked"]))
                stamp = now()
                cursor = self.store.db.execute("""INSERT INTO verification_operations
                    (source_run,project_id,ticket_id,author,status,created) VALUES(?,?,?,?,?,?)""",
                    (source_run, source["project_id"], source["ticket_id"], by, "queued", stamp))
                opid = cursor.lastrowid
                if self.folder(opid).exists():
                    raise ValueError("复检操作目录已存在，保留原始证据并阻止覆盖")
                self.runner._control(opid, {"verification": {"run_timeout": budget}}, "verification")
                self.store.db.execute("UPDATE verification_operations SET status='running',started=? WHERE id=?", (now(), opid))
                self.store.db.commit()
                self._source_guards[opid] = guard
            except BaseException as exc:
                if opid is not None:
                    try:
                        self.store.db.execute("UPDATE verification_operations SET status='failed',ended=?,exit_code=125,result=? WHERE id=?",
                                              (now(), "复检准备失败：" + str(exc), opid))
                        self.store.db.commit()
                    finally:
                        control = self.runner.controls.get(opid)
                        try:
                            if control:
                                control.update(finished=True, stopped_reason="error", ended_at=now())
                                self.runner._save_lifecycle(opid)
                        finally:
                            self.runner._release(opid)
                else:
                    self.store.db.rollback()
                if isinstance(exc, sqlite3.IntegrityError):
                    raise ValueError("该来源已有进行中的复检") from exc
                raise
        return self.get(opid)

    def bind(self, opid, source):
        opid = int(opid)
        row = self.adapter.run(opid)
        if not row:
            raise ValueError("没有这个复检操作")
        _validate_source(source)
        source = json.loads(json.dumps(source, ensure_ascii=False, allow_nan=False))
        if "run" in source and source["run"] != row["source_run"]:
            raise ValueError("复检版本绑定的来源运行不一致")
        path = self.folder(opid) / "source.json"
        with self.runner.lock:
            if path.exists():
                existing = self._read_json(path)
                if (existing.get("schema") != 1 or existing.get("operation_id") != opid or existing.get("source_run") != row["source_run"] or
                        existing.get("source") != source):
                    raise ValueError("复检代码版本已绑定，不能替换")
                return existing
            if opid not in self.runner.owners or self.runner.controls[opid]["finished"]:
                raise ValueError("只有当前运行的复检可以绑定代码版本")
            manifest = {"schema": 1, "operation_id": opid, "source_run": row["source_run"],
                        "source": source, "bound_at": now()}
            _atomic_json(path, manifest, exclusive=True)
            return manifest

    def finish(self, opid, code, result):
        opid = int(opid)
        try:
            with self.runner.lock:
                if opid not in self.runner.owners or self.runner.controls.get(opid, {}).get("finished"):
                    raise ValueError("当前服务未持有这个复检操作，不能替它封存")
                if code == 0:
                    try:
                        manifest = self._read_json(self.folder(opid) / "source.json")
                        row = self.adapter.run(opid)
                        if (manifest.get("schema") != 1 or manifest.get("operation_id") != opid or
                                manifest.get("source_run") != row["source_run"]):
                            raise ValueError("代码版本绑定与复检操作不一致")
                        _validate_source(manifest.get("source"))
                    except (OSError, ValueError, UnicodeError) as exc:
                        code, result = 125, "复检没有有效的代码版本绑定，不能报告成功：%s\n%s" % (exc, result or "")
                self.runner.finish_invocation(opid, code, result)
            return self.get(opid)
        finally:
            guard = self._source_guards.pop(opid, None)
            if guard:
                guard.__exit__(None, None, None)

    def recover(self):
        self.runner.recover()

    def recover_one(self, opid):
        self.runner.recover_run(int(opid))
        return self.get(opid)


def read_status(main_data_dir, source_run):
    """Read the latest operation without initializing Store, schema or recovery."""
    root = Path(main_data_dir).resolve()
    database = root / "platform.db"
    if not database.exists():
        return None
    connection = None
    try:
        connection = sqlite3.connect("file:" + quote(str(database), safe="/") + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='verification_operations'").fetchone() is None:
            return None
        row = connection.execute("SELECT * FROM verification_operations WHERE source_run=? ORDER BY id DESC LIMIT 1",
                                 (int(source_run),)).fetchone()
        if row is None:
            return None
        item = dict(row)
    except (sqlite3.Error, OSError, TypeError) as exc:
        raise ValueError("无法读取复检状态：" + str(exc)) from exc
    finally:
        if connection is not None:
            connection.close()
    # _view only reads files and checks the existing advisory lease. It never
    # requires a writable Store, creates a folder or implicitly recovers a run.
    reader = Operations.__new__(Operations)
    reader.main_data_dir = root
    reader.data_dir = root / "verification-operations"
    return reader._view(item)
