"""上生产申请：版本在验证环境验收后，由人申请发布到生产，另一个人工确认节点批准或驳回，部署后登记。

A version (release.py) is only on the project's main line. Going to the client's production is a separate, human
step: someone who checked the version in the verification environment asks for it, a person approves or rejects,
and the deployment is recorded once done. If the project has a deploy command (autoflow.json "prod_deploy"), it runs
after approval and its result is the record; otherwise a person marks the version as deployed. Every step is appended
to <data>/versions/prod-requests.jsonl and written onto the tickets the version holds, so a ticket shows when it
reached production and who let it through. Nothing here approves on its own.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

from .errors import ApiError

STATES = {"requested": "待批准", "approved": "已批准，待部署", "deploying": "正在部署", "deployed": "已上生产",
          "rejected": "已驳回", "failed": "部署失败"}
DEPLOY_S = 1800
_LOCK = threading.Lock()


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
    out: dict = {}
    f = _file(data_dir)
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if project and e.get("project") != project:
                continue
            if e.get("step") == "request":
                out[e["id"]] = {"id": e["id"], "project": e["project"], "version": e["version"], "commit": e.get("commit", ""),
                                "tickets": e.get("tickets", []), "by": e["by"], "ts": e["ts"], "note": e.get("note", ""),
                                "checked": e.get("checked", ""), "state": "requested", "steps": [e]}
            elif e.get("id") in out:
                r = out[e["id"]]
                r["steps"].append(e)
                r["state"] = e.get("state", r["state"])
    rs = sorted(out.values(), key=lambda r: r["ts"], reverse=True)
    for r in rs:
        r["state_text"] = STATES.get(r["state"], r["state"])
    return rs


def get(data_dir, rid: str) -> dict:
    for r in requests(data_dir):
        if r["id"] == rid:
            return r
    raise ApiError(404, "没有这条上生产申请")


def deploy_command(data_dir, project: str) -> str:
    try:
        c = json.loads((Path(data_dir) / "autoflow.json").read_text(encoding="utf-8")).get("prod_deploy") or {}
    except (OSError, ValueError):
        return ""
    return str(c.get(project) or "") if isinstance(c, dict) else ""


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
    with _LOCK:
        open_ = [r for r in requests(P.data_dir, p["key"]) if r["version"] == version and r["state"] in ("requested", "approved", "deploying", "deployed")]
        if open_:
            raise ApiError(409, "版本 %s 已经有一条申请（%s）" % (version, open_[0]["state_text"]))
        rid = "PR%s-%s" % (time.strftime("%Y%m%d%H%M%S"), p["key"])
        tickets = [x.get("key") for x in rel.get("tickets") or [] if x.get("key")]
        rec = {"id": rid, "step": "request", "state": "requested", "project": p["key"], "version": version,
               "commit": rel.get("commit", ""), "tickets": tickets, "by": by, "ts": _now(), "note": note.strip()[:2000],
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
        state = "approved" if approve else "rejected"
        _append(P.data_dir, {"id": rid, "project": r["project"], "step": "decide", "state": state, "by": by, "ts": _now(),
                             "note": note.strip()[:2000]})
    r = get(P.data_dir, rid)
    _mark(P, r, "prod_approve" if approve else "prod_reject", by,
          ("批准版本 %s 上生产" if approve else "驳回版本 %s 上生产") % r["version"] + ("：" + note.strip() if note.strip() else ""))
    if approve and deploy_command(P.data_dir, r["project"]):
        threading.Thread(target=_deploy, args=(P, rid, by), daemon=True).start()
    return r


def _deploy(P, rid: str, by: str) -> None:
    r = get(P.data_dir, rid)
    p = P.project(r["project"])
    cmd = deploy_command(P.data_dir, p["key"]).replace("{version}", r["version"]).replace("{commit}", r["commit"])
    _append(P.data_dir, {"id": rid, "project": p["key"], "step": "deploy", "state": "deploying", "by": by, "ts": _now(), "cmd": cmd})
    try:
        x = subprocess.run(cmd, shell=True, cwd=p["root"], capture_output=True, text=True, timeout=DEPLOY_S)
        ok, out = x.returncode == 0, ((x.stdout or "") + (x.stderr or ""))[-4000:]
    except subprocess.TimeoutExpired:
        ok, out = False, "部署超过 %d 秒没结束" % DEPLOY_S
    _append(P.data_dir, {"id": rid, "project": p["key"], "step": "deployed" if ok else "deploy_failed",
                         "state": "deployed" if ok else "failed", "by": "部署命令", "ts": _now(), "output": out})
    _mark(P, get(P.data_dir, rid), "prod_deployed" if ok else "prod_failed", "部署命令",
          ("版本 %s 已部署到生产" if ok else "版本 %s 部署失败") % r["version"])


def deployed(P, rid: str, by: str, note: str = "") -> dict:
    """A person who did the deployment by hand records it."""
    with _LOCK:
        r = get(P.data_dir, rid)
        if r["state"] not in ("approved", "failed"):
            raise ApiError(409, "只有已批准的申请才能登记部署（现在是「%s」）" % r["state_text"])
        _append(P.data_dir, {"id": rid, "project": r["project"], "step": "deployed", "state": "deployed", "by": by,
                             "ts": _now(), "note": note.strip()[:2000]})
    r = get(P.data_dir, rid)
    _mark(P, r, "prod_deployed", by, "版本 %s 已部署到生产" % r["version"] + ("：" + note.strip() if note.strip() else ""))
    return r
