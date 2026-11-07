"""上生产申请：版本在验证环境验收后，由人申请发布到生产，另一个人工确认节点批准或驳回，部署后登记。

A version (release.py) is only on the project's main line. Going to the client's production is a separate, human
step: someone who checked the version in the verification environment asks for it, a person approves or rejects,
and the deployment is recorded once done. If the project has a deploy command (autoflow.json "prod_deploy"), it runs
after approval and its result is the record; otherwise a person marks the version as deployed. Every step is appended
to <data>/versions/prod-requests.jsonl and written onto the tickets the version holds, so a ticket shows when it
reached production and who let it through. Nothing here approves on its own.

A configured command may write JSON to WEBUDDY_DEPLOY_RECEIPT. Copy the binding
from WEBUDDY_DEPLOY_CONTEXT, then add observed_commit and checks.health/version/
smoke, each with result pass/fail and a nonempty evidence description. The
platform supplies a fresh nonce, request, target, version, commit, start time
and configuration digest for each execution. Ordinary stdout is never a receipt.
String prod_deploy entries remain supported; object entries use cmd and target.
Only the configured deployment script can attest its checks: this contract does
not make arbitrary application output an independent production observation.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import subprocess
import threading
import time
from pathlib import Path

from .errors import ApiError
from .browser_verify import full_sha

STATES = {"requested": "待批准", "approved": "已批准，待部署", "deploying": "正在部署", "deployed": "已上生产",
          "rejected": "已驳回", "failed": "部署失败"}
DEPLOY_S = 1800
_LOCK = threading.Lock()
_ACTIVE = set()


def _file(data_dir) -> Path:
    return Path(data_dir) / "versions" / "prod-requests.jsonl"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _append(data_dir, rec: dict) -> None:
    f = _file(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def requests(data_dir, project: str = "") -> list:
    """Each request folded from its log lines, newest first."""
    groups = {}
    f = _file(data_dir)
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            groups.setdefault(e["id"], []).append(e)
    rs = []
    for rid, events in groups.items():
        originals = [e for e in events if e.get("step") == "request"]
        for e in originals:
            if project and e["project"] != project:
                continue
            r = {"id": rid, "project": e["project"], "version": e["version"], "commit": e.get("commit", ""),
                 "tickets": e.get("tickets", []), "by": e["by"], "ts": e["ts"], "note": e.get("note", ""),
                 "checked": e.get("checked", ""), "state": "requested", "steps": events,
                 "source": "legacy", "execution": "unknown", "verification": "unverified"}
            if len(originals) > 1:
                r.update(ambiguous=True, state="ambiguous", state_text="历史申请 ID 冲突，待核对")
            else:
                for event in events:
                    r["state"] = event.get("state", r["state"])
                    for field in ("source", "execution", "verification", "receipt", "verification_note", "target", "command_sha256", "approved_config_sha256"):
                        if field in event:
                            r[field] = event[field]
                r["state_text"] = STATES.get(r["state"], r["state"])
                if r["state"] == "deployed":
                    r["state_text"] = ("部署验证通过" if r["verification"] == "pass" else
                                       "部署验证失败" if r["verification"] == "fail" else
                                       "人工登记已部署（未自动验证）" if r["source"] == "manual" else
                                       "命令完成，部署未验证" if r["execution"] == "completed" else "历史部署记录（未验证）")
                elif (r["state"] == "deploying" and rid not in _ACTIVE) or (r["execution"] == "unknown" and r["source"] == "command"):
                    r["execution"] = "unknown"
                    r["state_text"] = "部署结果未知，需核对；不会自动重跑"
            rs.append(r)
    return sorted(reversed(rs), key=lambda r: r["ts"], reverse=True)


def get(data_dir, rid: str) -> dict:
    for r in requests(data_dir):
        if r["id"] == rid:
            if r.get("ambiguous"):
                raise ApiError(409, "历史申请 ID 冲突，保留原始记录，请先核对归属")
            return r
    raise ApiError(404, "没有这条上生产申请")


def deploy_config(data_dir, project: str) -> dict:
    try:
        c = json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("prod_deploy") or {}
    except (OSError, ValueError):
        return {}
    value = c.get(project) if isinstance(c, dict) else None
    if isinstance(value, str):
        return {"cmd": value, "target": project + ":production"}
    if value is None:
        return {}
    if not isinstance(value, dict) or not isinstance(value.get("cmd"), str) or not isinstance(value.get("target"), str) or not value["target"]:
        raise ApiError(400, "部署配置需要 cmd 和明确的 target")
    return value


def deploy_command(data_dir, project: str) -> str:
    return deploy_config(data_dir, project).get("cmd", "")


def _receipt(path, binding, root=None):
    if not path.exists():
        return "unverified", None, "部署脚本没有提交验证回执"
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or any(receipt.get(k) != v for k, v in binding.items()):
            return "unverified", receipt, "回执与本次申请、目标、版本或执行身份不一致"
        checks = receipt["checks"]
        if not isinstance(checks, dict) or any(not isinstance(checks.get(k), dict) or
                checks[k].get("result") not in ("pass", "fail") or not isinstance(checks[k].get("evidence"), str) or
                not checks[k]["evidence"].strip() for k in ("health", "version", "smoke")):
            return "unverified", receipt, "回执缺少健康、版本或业务冒烟检查依据"
        expected = full_sha(Path(root), binding["commit"]) if root is not None else binding["commit"]
        observed = full_sha(Path(root), receipt.get("observed_commit") or "") if root is not None else receipt.get("observed_commit")
        if not expected:
            return "unverified", receipt, "申请提交无法在项目仓库中唯一解析"
        if not observed or observed != expected or any(checks[k]["result"] != "pass" for k in ("health", "version", "smoke")):
            return "fail", receipt, "运行版本不符或部署检查失败"
        return "pass", receipt, "健康、运行版本和业务冒烟检查通过"
    except (OSError, UnicodeError, ValueError, KeyError):
        return "unverified", None, "无法读取完整部署验证回执"


def _mark(P, r: dict, kind: str, who: str, text: str) -> None:
    for x in r.get("tickets") or []:
        t = P.store.ticket(x)
        if t:
            P.store.event(t["id"], who, kind, text, {"prod_request": r["id"], "version": r["version"]})


def request(P, project: str, version: str, by: str, note: str = "", checked: str = "") -> dict:
    from . import release
    p = P.project(project)
    rel = next((x for x in release.releases(P.data_dir, p["key"], 500) if x.get("version") == version), None)
    if not rel:
        raise ApiError(404, "没有版本 %s" % version)
    if not (checked or "").strip():
        raise ApiError(400, "写一句在验证环境里看过什么，再申请上生产")
    commit = full_sha(Path(p["root"]), rel.get("commit", ""))
    if not commit:
        raise ApiError(409, "版本提交无法在项目仓库中唯一解析，请核对版本记录")
    with _LOCK:
        open_ = [r for r in requests(P.data_dir, p["key"]) if r["version"] == version and (r["state"] in ("requested", "approved", "deploying", "deployed", "ambiguous") or r["source"] == "command" and r["execution"] == "unknown")]
        if open_:
            raise ApiError(409, "版本 %s 已经有一条申请（%s）" % (version, open_[0]["state_text"]))
        rid = "PR-" + secrets.token_hex(16)
        tickets = [x.get("key") for x in rel.get("tickets") or [] if x.get("key")]
        rec = {"id": rid, "step": "request", "state": "requested", "project": p["key"], "version": version,
               "commit": commit, "tickets": tickets, "by": by, "ts": _now(), "note": note.strip()[:2000],
               "checked": checked.strip()[:2000]}
        _append(P.data_dir, rec)
    r = get(P.data_dir, rid)
    _mark(P, r, "prod_request", by, "申请把版本 %s 发布到生产。验证环境：%s" % (version, r["checked"]))
    return r


def decide(P, rid: str, approve: bool, by: str, note: str = "") -> dict:
    with _LOCK:
        r = get(P.data_dir, rid)
        if r["state"] != "requested":
            raise ApiError(409, "这条申请现在是「%s」，不能再批准或驳回" % r["state_text"])
        if not approve and not note.strip():
            raise ApiError(400, "驳回要写原因")
        config = deploy_config(P.data_dir, r["project"]) if approve else {}
        state = "approved" if approve else "rejected"
        _append(P.data_dir, {"id": rid, "project": r["project"], "step": "decide", "state": state, "by": by, "ts": _now(),
                             "note": note.strip()[:2000],
                             "approved_config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()})
    r = get(P.data_dir, rid)
    _mark(P, r, "prod_approve" if approve else "prod_reject", by,
          ("批准版本 %s 上生产" if approve else "驳回版本 %s 上生产") % r["version"] + ("：" + note.strip() if note.strip() else ""))
    if approve and config.get("cmd"):
        threading.Thread(target=_deploy, args=(P, rid, by), daemon=True).start()
    return r


def _deploy(P, rid: str, by: str) -> None:
    with _LOCK:
        r = get(P.data_dir, rid)
        if r["state"] != "approved":
            return
        p = P.project(r["project"])
        config = deploy_config(P.data_dir, p["key"])
        config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        if config_hash != r.get("approved_config_sha256"):
            _append(P.data_dir, {"id": rid, "project": p["key"], "step": "deploy_failed", "state": "failed",
                                 "by": by, "ts": _now(), "source": "command", "execution": "not_started",
                                 "verification": "unverified", "verification_note": "部署配置与批准时不同，请重新申请"})
            return
        commit = full_sha(Path(p["root"]), r["commit"])
        if not commit:
            _append(P.data_dir, {"id": rid, "project": p["key"], "step": "deploy_failed", "state": "failed",
                                 "by": by, "ts": _now(), "source": "command", "execution": "not_started",
                                 "verification": "unverified", "verification_note": "申请提交无法在项目仓库中唯一解析，未执行部署"})
            return
        cmd = config["cmd"].replace("{version}", r["version"]).replace("{commit}", commit)
        started = _now()
        binding = {"schema": "webuddy-deploy-receipt-v1", "request_id": rid, "nonce": secrets.token_hex(24),
                   "target": config["target"], "version": r["version"], "commit": commit, "started_at": started,
                   "command_sha256": config_hash}
        _ACTIVE.add(rid)
        _append(P.data_dir, {"id": rid, "project": p["key"], "step": "deploy", "state": "deploying", "by": by,
                             "ts": started, "source": "command", "execution": "running", "verification": "unverified",
                             "target": binding["target"], "command_sha256": binding["command_sha256"]})
    execution, verification, receipt, why, out = "unknown", "unverified", None, "", ""
    exit_code = None
    try:
        with tempfile.TemporaryDirectory(prefix="webuddy-deploy-") as folder:
            path = Path(folder) / "receipt.json"
            env = dict(os.environ, WEBUDDY_DEPLOY_RECEIPT=str(path), WEBUDDY_DEPLOY_CONTEXT=json.dumps(binding))
            x = subprocess.run(cmd, shell=True, cwd=p["root"], capture_output=True, text=True, timeout=DEPLOY_S, env=env)
            exit_code = x.returncode
            execution = "completed" if exit_code == 0 else "failed"
            out = (x.stdout or "") + (x.stderr or "")
            if execution == "completed":
                verification, receipt, why = _receipt(path, binding, p["root"])
            else:
                why = "部署命令失败"
    except subprocess.TimeoutExpired:
        out = why = "部署命令超时，外部部署结果需核对，不自动重跑"
    except OSError as exc:
        out = why = "部署进程未能正常完成：" + str(exc)
    finally:
        with _LOCK:
            state = "deployed" if execution == "completed" else "failed"
            _append(P.data_dir, {"id": rid, "project": p["key"], "step": "deployed" if state == "deployed" else "deploy_failed",
                                 "state": state, "by": "部署命令", "ts": _now(), "output": out,
                                 "source": "command", "execution": execution, "verification": verification,
                                 "receipt": receipt, "verification_note": why, "exit_code": exit_code})
            _ACTIVE.discard(rid)
    r = get(P.data_dir, rid)
    _mark(P, r, "prod_deployed" if verification == "pass" else "prod_deploy_result", "部署命令",
          "版本 %s：%s。%s" % (r["version"], r["state_text"], why))


def deployed(P, rid: str, by: str, note: str = "") -> dict:
    """A person who did the deployment by hand records it."""
    with _LOCK:
        r = get(P.data_dir, rid)
        if r["state"] not in ("approved", "failed"):
            raise ApiError(409, "只有已批准的申请才能登记部署（现在是「%s」）" % r["state_text"])
        _append(P.data_dir, {"id": rid, "project": r["project"], "step": "deployed", "state": "deployed", "by": by,
                             "ts": _now(), "note": note.strip()[:2000], "source": "manual",
                             "execution": "reported", "verification": "unverified"})
    r = get(P.data_dir, rid)
    _mark(P, r, "prod_deployed", by, "人工登记版本 %s 已部署（未自动验证）" % r["version"] + ("：" + note.strip() if note.strip() else ""))
    return r
