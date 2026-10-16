"""Ticket evidence packages and the client's sign-off page.

When a ticket is handed over for acceptance (status → 待验证) the platform packs what backs the change: the
acceptance criteria the plan named and how each is checked, the plan's file list (the change contract), the
changed files and their size, whether the change stayed inside the plan and on the ticket's business flows,
the build and test result, and the verification gates (tmh/platform/gates.py: PASS / FAIL / UNKNOWN each, from
"there is a real change" to "it matches the acceptance criteria"). People then add to it: screenshots per criterion, an internal review. The client's
business owner signs or rejects on a page that shows business flows, criteria and results, never code. Every
record goes into the ticket's hash-chained package (tmh/evidence.py); the signature carries the hash of the
package it signed.

Files under <data>/evidence/: <KEY>.jsonl (the package), links.json (sign-off links by token hash; the token
itself is only ever in the link), files/<sha256>.<ext> (screenshots, named by content).
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import secrets
import subprocess
import time
from pathlib import Path

from .. import evidence as ev
from . import gates as G
from .errors import ApiError

AGENTS = ("自动流转", "system", "告警", "agent", "智能体")
CODE_EXT = (".java", ".cs", ".vb", ".go", ".kt", ".scala", ".py", ".xml", ".sql", ".js", ".ts", ".vue", ".jsx", ".tsx", ".jsp", ".html")
TEST_PATH = re.compile(r"(^|/)(src/test|tests?|__tests__|spec)/|(Tests?|Spec|IT)\.(java|cs|kt)$|(_test\.go|\.spec\.[jt]sx?|\.test\.[jt]sx?)$")
IMAGE = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_IMAGE = 3 * 1024 * 1024
LINK_DAYS = 7
REQUIRED = [("ac", "验收标准（AC）"), ("change", "代码改动"), ("gates", "验证门全部通过（没有没过或未知的）"), ("review", "乙方复核人")]
# packages sealed before the gates existed are judged by what they had then
LEGACY = [("ac", "验收标准（AC）"), ("change", "代码改动"), ("check", "构建或测试结果"), ("scope", "改动没超出方案"),
          ("path", "改动落在本单的业务流上"), ("review", "乙方复核人")]


def edir(data_dir: Path) -> Path:
    return Path(data_dir) / "evidence"


def epath(data_dir: Path, key: str) -> Path:
    return edir(data_dir) / ("%s.jsonl" % key.upper())


def records(data_dir: Path, key: str) -> list[dict]:
    return ev.read(epath(data_dir, key))


def _add(path: Path, kind: str, by: str, data: dict) -> dict:
    try:
        return ev.append(path, kind, by, data)
    except ValueError as e:
        raise ApiError(409, str(e))


def human(name: str) -> bool:
    return bool(name) and name not in AGENTS


# ---------------------------------------------------------------- packing

def _flows(P, p: dict, t: dict) -> list[dict]:
    """The ticket's business flows by name and domain, with the files their steps run through."""
    from ..graph import Graph, graph_path
    ids = list(dict.fromkeys(((t.get("links") or {}).get("flows") or [])))
    root = P.root(p)
    if not ids or not graph_path(root).exists():
        return [{"id": f, "name": f.replace("flow:", ""), "domain": "", "trigger": "", "files": []} for f in ids]
    g = Graph(root)
    doms = {(d["data"].get("key") or d["name"]): (d["label"] or d["name"]) for d in g.nodes("dom")}
    out = []
    for fid in ids:
        n = g.node(fid)
        if not n:
            out.append({"id": fid, "name": fid.replace("flow:", ""), "domain": "", "trigger": "", "files": []})
            continue
        files = {n["file"]} if n.get("file") else set()
        for e in g.out(n["id"], "step")[:200]:
            m = g.node(e["dst"])
            if m and m.get("file"):
                files.add(m["file"])
        out.append({"id": fid, "name": n["name"], "domain": doms.get(n.get("domain") or "", ""),
                    "trigger": (n.get("data") or {}).get("trigger", ""), "files": sorted(files)})
    return out


def _diff_stat(diff: str) -> dict:
    files, add, rem = [], 0, 0
    for line in (diff or "").splitlines():
        m = re.match(r"^diff --git a/(\S+) b/", line)
        if m:
            files.append(m.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            add += 1
        elif line.startswith("-") and not line.startswith("---"):
            rem += 1
    return {"files": files, "added": add, "removed": rem}


def _path_by_file(files: list[str], flows: list[dict]) -> dict:
    """File-level path check: product code changed on the ticket's flows, off them, or where the graph cannot see."""
    on = {f for fl in flows for f in fl["files"]}
    res = {"covered": [], "off": [], "manual": [], "basis": "按文件：改动的代码文件是否在本单关联业务流经过的文件里"}
    for f in files:
        if TEST_PATH.search(f) or f.endswith((".md", ".txt", ".png", ".jpg")):
            continue
        if f in on:
            res["covered"].append(f)
        elif f.endswith(CODE_EXT[:6]) or f.endswith(".xml") and "mapper" in f.lower():
            res["off"].append(f)
        else:
            res["manual"].append(f)
    res["ok"] = bool(res["covered"]) and not res["off"]
    if not flows:
        res["ok"], res["why"] = False, "工单没有关联业务流，判断不了改动是否落在入口路径上"
    elif not res["covered"] and not res["off"]:
        res["why"] = "没有一处产品代码改动落在关联业务流上"
    elif res["off"]:
        res["why"] = "有代码改动不在关联业务流上：%s" % "、".join(res["off"][:5])
    return res


def _reader(p: dict, fix: dict):
    """Reads a changed file as the change left it: from the adopted commit, else from the run's worktree."""
    dec = fix.get("decision") or ""
    if dec.startswith("accepted:") and "@" in dec:
        sha, root = dec.rsplit("@", 1)[-1], Path(p["root"])

        def read(path):
            r = subprocess.run(["git", "-C", str(root), "show", "%s:%s" % (sha, path)], capture_output=True)
            return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None
        return read
    wt = Path(fix.get("workdir") or "")
    if fix.get("workdir") and wt.is_dir():
        return lambda path: (wt / path).read_text(encoding="utf-8", errors="replace") if (wt / path).is_file() else None
    return None


def snapshot(P, t: dict) -> dict:
    """What backs the ticket's latest change right now (read from runs, verify.json and the knowledge graph)."""
    from .fixloop import plan_ac, plan_files, verified
    p = P.store.project(t["project_id"])
    runs = [P.store.run(r["id"]) for r in P.store.runs(ticket_id=t["id"]) if r["mode"] in ("plan", "fix")]  # newest first, full rows
    plan = next((r for r in runs if r["mode"] == "plan" and r["status"] == "done"), None)
    fix = next((r for r in runs if r["mode"] == "fix" and (r.get("decision") or "").startswith("accepted")), None) \
        or next((r for r in runs if r["mode"] == "fix" and r["status"] == "done" and r.get("diff")), None)
    ac = plan_ac(plan["result"] or "") if plan else []
    contract = plan_files(plan["result"] or "") if plan else {}
    flows = _flows(P, p, t)
    stat = _diff_stat(fix["diff"]) if fix else {"files": [], "added": 0, "removed": 0}
    v = verified(P.data_dir, fix["id"]) if fix else {}
    adopt = next((e for e in reversed(P.store.events(t["id"])) if e["kind"] == "adopt"), None)
    path = _path_by_file(stat["files"], flows)
    gates = G.evaluate(fix["diff"] or "", v, path, bool(contract), _reader(p, fix)) if fix else []
    return {
        "ticket": {"key": t["key"], "title": t["title"], "type": t["type"], "reporter": t["reporter"], "created": t["created"],
                   "body": (t.get("body") or "")[:2000]},
        "project": {"key": p["key"], "name": p["name"]},
        "flows": [{k: f[k] for k in ("id", "name", "domain", "trigger")} for f in flows],
        "ac": ac, "plan_run": plan and plan["id"],
        "contract": [{"path": k, "goal": g} for k, g in contract.items()],
        "change": fix and {"run": fix["id"], "agent": fix["agent"], "decision": fix.get("decision") or "", **stat},
        "check": {"result": v.get("check") or ("none" if not fix else "unknown"), "skip": v.get("skip", ""), "verdict": v.get("verdict", ""),
                  "rounds": v.get("rounds"), "commands": [{"cmd": c.get("cmd") or c.get("name") or "", "exit_code": c.get("exit_code")}
                                                          for c in (v.get("commands") or [])][:12]},
        "scope": {"beyond_plan": list(v.get("beyond_plan") or [])},
        "path": path,
        "gates": gates,
        "adopted": adopt and {"by": adopt["author"], "at": adopt["ts"], "branch": (adopt.get("data") or {}).get("branch", ""),
                              "commit": (adopt.get("data") or {}).get("commit", "")},
    }


def pack(P, t: dict, by: str, why: str = "转待验证") -> dict | None:
    """Add a snapshot when the change behind it is new (a re-fix after a rejection packs again)."""
    snap = snapshot(P, t)
    recs = records(P.data_dir, t["key"])
    last = ev.latest(recs, "pack")
    if last and ev.canon(last["data"].get("snapshot")) == ev.canon(snap):
        return None
    rec = _add(epath(P.data_dir, t["key"]), "pack", by, {"why": why, "snapshot": snap})
    P.store.event(t["id"], by, "evidence", "生成证据包（第 %d 条记录，哈希 %s）" % (rec["seq"], rec["hash"][:12]), {"seq": rec["seq"], "hash": rec["hash"]})
    return rec


def on_status(P, t: dict, old: str, new: str, by: str) -> None:
    if new == "verify":
        try:
            pack(P, t, by or "平台")
        except Exception as e:  # noqa: BLE001 - packing must never block the status change
            P.store.event(t["id"], "平台", "evidence", "证据包没生成：%s" % e)


# ---------------------------------------------------------------- state

def state(data_dir: Path, key: str) -> dict:
    """The package as it stands: the latest snapshot, what was added since, what is missing, who signed."""
    recs = records(data_dir, key)
    ok, why = ev.check(recs)
    last = ev.latest(recs, "pack")
    out = {"records": len(recs), "intact": ok, "problem": why, "hash": ev.head(recs), "packed": bool(last)}
    if not last:
        out.update({"missing": [lb for _, lb in REQUIRED], "complete": False, "status": "none", "snapshot": None})
        return _upstream(recs, out)
    snap = last["data"]["snapshot"]
    after = ev.since(recs, last["seq"])
    shots = [dict(r["data"], by=r["by"], ts=r["ts"]) for r in recs if r["kind"] == "attach"]
    reviews = [dict(r["data"], by=r["by"], ts=r["ts"]) for r in after if r["kind"] == "review"]
    reviewer = (snap.get("adopted") or {}).get("by") if human((snap.get("adopted") or {}).get("by", "")) else ""
    review = reviews[-1] if reviews else ({"by": reviewer, "ts": snap["adopted"]["at"], "note": "审阅采纳了改动"} if reviewer else None)
    waive = {}
    for r in reviews:  # a later review overrides an earlier one gate by gate
        waive.update({g: {"by": r["by"], "reason": why} for g, why in (r.get("waive") or {}).items()})
        for flag, g in (("scope_ok", "scope"), ("path_ok", "path")):
            if r.get(flag):
                waive[g] = {"by": r["by"], "reason": r.get("note", "")}
    gates = G.waived(snap["gates"], waive) if snap.get("gates") is not None else None
    have = {"ac": bool(snap["ac"]), "change": bool(snap.get("change") and snap["change"]["files"]),
            "check": snap["check"]["result"] == "pass",
            "scope": not snap["scope"]["beyond_plan"] or "scope" in waive,
            "path": snap["path"]["ok"] or "path" in waive, "review": bool(review),
            "gates": gates is not None and G.overall(gates) == G.PASS}
    need = REQUIRED if gates is not None else LEGACY
    signs = [r for r in after if r["kind"] in ("sign", "reject")]
    links = [r for r in after if r["kind"] == "link"]
    out.update({"snapshot": snap, "pack_seq": last["seq"], "pack_hash": last["hash"], "packed_at": last["ts"], "attachments": shots,
                "review": review, "have": have, "missing": [lb for k, lb in need if not have[k]],
                "gates": gates, "gate_state": G.overall(gates) if gates is not None else "",
                "links": [dict(r["data"], by=r["by"], ts=r["ts"]) for r in links],
                "decision": dict(signs[-1]["data"], kind=signs[-1]["kind"], ts=signs[-1]["ts"], hash=signs[-1]["hash"]) if signs else None})
    out["complete"] = not out["missing"]
    out["status"] = signs[-1]["kind"] + "ed" if signs else ("ready" if out["complete"] else "incomplete")
    return _upstream(recs, out)


def _upstream(recs: list, out: dict) -> dict:
    up = ev.latest(recs, "upstream_outcome")
    if up:  # a maintainer's merge upstream is the third-party verdict
        out["status"] = "upstream_" + up["data"]["state"]
        out["decision"] = {"kind": "sign" if up["data"]["state"] == "merged" else "reject", "signer": up["data"].get("by") or "上游",
                           "role": "上游维护者", "ts": up["ts"], "note": "", "via": "上游合并" if up["data"]["state"] == "merged" else "上游关闭",
                           "hash": up["hash"], "ac": {}}
    return out


STATUS_LABEL = {"none": "未生成", "incomplete": "证据不齐", "ready": "证据齐全，待签收", "signed": "甲方已签收", "rejected": "甲方已退回",
                "upstream_merged": "上游已合并", "upstream_closed": "上游已关闭"}


# ---------------------------------------------------------------- people add to it

def attach(P, t: dict, by: str, ac: str, note: str, image: str) -> dict:
    """A screenshot or a note backing one criterion (or the whole ticket when ac is empty)."""
    data = {"ac": (ac or "").strip()[:20], "note": (note or "").strip()[:1000]}
    if image:
        m = re.match(r"^data:(image/[a-z]+);base64,(.+)$", image, re.S)
        if not m or m.group(1) not in IMAGE:
            raise ApiError(400, "截图只收 PNG、JPEG、WebP（data URL）")
        raw = base64.b64decode(m.group(2), validate=False)
        if len(raw) > MAX_IMAGE:
            raise ApiError(413, "截图不能超过 3MB")
        sha = hashlib.sha256(raw).hexdigest()
        name = "%s.%s" % (sha, IMAGE[m.group(1)])
        f = edir(P.data_dir) / "files" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        if not f.exists():
            f.write_bytes(raw)
        data.update({"file": name, "sha256": sha, "bytes": len(raw)})
    if not data["note"] and not data.get("file"):
        raise ApiError(400, "截图和说明至少要有一个")
    rec = _add(epath(P.data_dir, t["key"]), "attach", by, data)
    P.store.event(t["id"], by, "evidence", "补充证据%s%s" % ("（%s）" % data["ac"] if data["ac"] else "", "：截图" if data.get("file") else ""),
                  {"seq": rec["seq"]})
    return rec


def review(P, t: dict, by: str, note: str, scope_ok: bool = False, path_ok: bool = False, waive: dict | None = None) -> dict:
    """The provider's internal review. Letting a gate through that did not pass (a change outside the plan, off the
    flows, a test changed on purpose, no build environment) takes a written reason per gate; a failed build or
    failed tests cannot be let through."""
    if not human(by):
        raise ApiError(403, "复核只能由人做")
    note = (note or "").strip()
    if (scope_ok or path_ok) and len(note) < 4:
        raise ApiError(400, "认可超出方案或不在业务流上的改动，要写明理由")
    s = state(P.data_dir, t["key"])
    if not s["packed"]:
        raise ApiError(409, "还没有证据包：工单转到“待验证”时自动生成")
    w = {}
    for g, why in (waive or {}).items():
        why = str(why or "").strip()
        if g not in G.NAMES:
            raise ApiError(400, "没有这道验证门：%s" % g)
        if len(why) < 4:
            raise ApiError(400, "放行“%s”要写明理由" % G.NAMES[g])
        cur = next((x for x in s.get("gates") or [] if x["id"] == g), None)
        if g in G.NOT_WAIVABLE and cur and cur["state"] == G.FAIL:
            raise ApiError(409, "%s没过，只能改代码，不能写理由放行" % G.NAMES[g])
        w[g] = why[:500]
    rec = _add(epath(P.data_dir, t["key"]), "review", by, {"note": note[:1000], "scope_ok": bool(scope_ok), "path_ok": bool(path_ok), "waive": w})
    P.store.event(t["id"], by, "evidence", "复核了证据包" + ("：" + note[:80] if note else ""), {"seq": rec["seq"]})
    return rec


# ---------------------------------------------------------------- sign-off links

def _links_file(data_dir: Path) -> Path:
    return edir(data_dir) / "links.json"


def _links(data_dir: Path) -> dict:
    f = _links_file(data_dir)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        return {}


def _save_links(data_dir: Path, d: dict) -> None:
    f = _links_file(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def _th(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue(P, t: dict, by: str, signer: str, role: str = "", days: int = LINK_DAYS, note: str = "") -> dict:
    """A one-time link for the client's named signer. Issuing one for a package that is not complete takes a reason."""
    signer, role, note = (signer or "").strip()[:40], (role or "").strip()[:40], (note or "").strip()[:500]
    if not signer:
        raise ApiError(400, "写明签收人（甲方业务确认人的姓名）")
    if t["status"] != "verify":
        raise ApiError(409, "工单在“待验证”时才能发签收链接（现在是 %s）" % t["status"])
    s = state(P.data_dir, t["key"])
    if not s["intact"]:
        raise ApiError(409, "证据包被改动过：%s" % s["problem"])
    if not s["packed"]:
        raise ApiError(409, "还没有证据包")
    if s["missing"] and len(note) < 4:
        raise ApiError(409, "证据还缺：%s。补齐后再发，或写明为什么现在就请甲方签" % "、".join(s["missing"]))
    token = secrets.token_urlsafe(24)
    days = max(1, min(30, int(days or LINK_DAYS)))
    exp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + days * 86400))
    links = _links(P.data_dir)
    for h, x in links.items():  # one live link per ticket: a new one replaces the old
        if x["key"] == t["key"] and not x.get("used"):
            x["used"] = "replaced"
    links[_th(token)] = {"key": t["key"], "signer": signer, "role": role, "expires": exp, "by": by, "used": ""}
    _save_links(P.data_dir, links)
    rec = _add(epath(P.data_dir, t["key"]), "link", by, {"signer": signer, "role": role, "expires": exp, "token_sha": _th(token)[:16],
                                                              "missing": s["missing"], "note": note})
    P.store.event(t["id"], by, "evidence", "发出签收链接给 %s%s，%d 天内有效%s" % (signer, "（%s）" % role if role else "", days,
                                                                     "；证据缺 %s，理由：%s" % ("、".join(s["missing"]), note) if s["missing"] else ""),
                  {"seq": rec["seq"]})
    return {"token": token, "path": "/sign/" + token, "signer": signer, "expires": exp}


def link_of(data_dir: Path, token: str) -> dict:
    if not re.match(r"^[A-Za-z0-9_\-]{20,64}$", token or ""):
        raise ApiError(404, "签收链接不对")
    x = _links(data_dir).get(_th(token))
    if not x:
        raise ApiError(404, "签收链接不对或已作废")
    return x


def decide(P, token: str, action: str, name: str, verdicts: dict, note: str, client: str = "") -> dict:
    """The signer's decision: sign when every criterion passed, otherwise reject with a reason. Closes or reopens
    the ticket through the same path as the 验收 button (POST /api/tickets/<key>/accept)."""
    x = link_of(P.data_dir, token)
    if x.get("used"):
        raise ApiError(410, "这个签收链接已经用过或被新链接替换了")
    if x["expires"] < ev.now():
        raise ApiError(410, "签收链接已过期，请联系乙方重新发送")
    t = P.store.ticket(x["key"])
    if not t or t["status"] != "verify":
        raise ApiError(409, "这张工单现在不在待验收状态，不需要签收")
    name, note = (name or "").strip(), (note or "").strip()[:2000]
    if name != x["signer"]:
        raise ApiError(400, "请输入签收人姓名“%s”确认身份" % x["signer"])
    s = state(P.data_dir, t["key"])
    if not s["intact"]:
        raise ApiError(409, "证据包被改动过，不能签：%s" % s["problem"])
    acs = [a["id"] for a in (s["snapshot"] or {}).get("ac") or []]
    res = {a: verdicts.get(a, "") for a in acs}
    if action == "sign":
        left = [a for a, v in res.items() if v != "pass"]
        if left:
            raise ApiError(400, "每条验收标准都确认“通过”才能签收；%s 没确认通过（不通过请点“退回”并写原因）" % "、".join(left))
    elif action == "reject":
        if len(note) < 2:
            raise ApiError(400, "退回必须写明原因")
    else:
        raise ApiError(400, "action 只能是 sign 或 reject")
    who = "%s（甲方%s）" % (name, x["role"] or "确认人")
    data = {"signer": name, "role": x["role"], "ac": res, "note": note, "pack_hash": s["pack_hash"], "package_hash": s["hash"],
            "via": "签收链接", "client": client[:60]}
    rec = _add(epath(P.data_dir, t["key"]), action, who, data)
    links = _links(P.data_dir)
    links[_th(token)]["used"] = rec["ts"]
    _save_links(P.data_dir, links)
    passed = action == "sign"
    body = "甲方签收：%s" % name if passed else "甲方退回：%s" % note
    P.store.event(t["id"], who, "accept" if passed else "reject", body + ("；" + note if passed and note else ""),
                  {"result": "pass" if passed else "fail", "evidence": rec["hash"], "via": "签收链接"})
    P.store.update_ticket(t["id"], who, status="closed" if passed else "doing")
    P.flow.accepted(P.store.project(t["project_id"]), P.store.ticket(t["id"]), passed, note, who)
    return {"ok": True, "action": action, "hash": rec["hash"], "ts": rec["ts"]}


# ---------------------------------------------------------------- pages

E = html.escape
CHECK_LABEL = {"pass": "通过", "fail": "没通过", "skip": "没跑", "none": "没有改动", "unknown": "没有结果"}
LAYER = {"L1": "自动测试", "L2": "智能体按步骤验证", "L3": "部署后自动检查", "L4": "人工确认"}


def _ac_table(s: dict, form: bool, img: str = "") -> str:
    snap = s["snapshot"]
    shots = {}
    for a in s.get("attachments") or []:
        shots.setdefault(a.get("ac") or "", []).append(a)
    rows = []
    auto = snap["check"]["result"] == "pass"
    for a in snap["ac"]:
        res = "自动化检查通过" if a.get("layer") == "L1" and auto else "待确认"
        sh = "".join(("<div>%s</div>" % E(x["note"]) if x.get("note") else "") +
                     ("<img src='%s' alt='%s 截图'>" % (E(img + x["file"]), E(a["id"])) if x.get("file") else "") for x in shots.get(a["id"], []))
        pick = ("<label><input type=radio name='ac_%s' value=pass required> 通过</label> <label><input type=radio name='ac_%s' value=fail> 不通过</label>"
                % (E(a["id"]), E(a["id"]))) if form else ""
        dec = s.get("decision") and (s["decision"].get("ac") or {}).get(a["id"])
        if dec and not form:
            res += "；签收人：%s" % ("通过" if dec == "pass" else "不通过")
        rows.append("<tr><td>%s</td><td>%s</td><td>%s<div class=sub>%s</div></td><td>%s%s</td>%s</tr>" % (
            E(a["id"]), E(a["text"]), E(LAYER.get(a.get("layer"), a.get("layer") or "")), E(a["check"]), E(res), sh,
            "<td>%s</td>" % pick if form else ""))
    if not rows:
        return "<p class=bad>方案里没有验收标准，这单不能签收。</p>"
    return ("<div class=wrap><table><thead><tr><th>#</th><th>验收标准</th><th>怎么验</th><th>结果与证据</th>%s</tr></thead><tbody>%s</tbody></table></div>"
            % ("<th>您的确认</th>" if form else "", "".join(rows)))


def _flows_html(snap: dict) -> str:
    if not snap["flows"]:
        return "<p class=warn>这单没有关联业务流。</p>"
    return "<ul>%s</ul>" % "".join("<li><b>%s</b>%s</li>" % (E(f["name"]), "　<span class=sub>%s</span>" % E(f["domain"]) if f["domain"] else "")
                                   for f in snap["flows"])


def _seal(s: dict) -> str:
    if not s["intact"]:
        return "<div class='seal bad'><b class=bad>证据包被改动过</b><div>%s</div></div>" % E(s["problem"])
    return ("<div class=seal><b class=ok>证据包完整，未被改动</b><div class=sub>%d 条记录 · 当前哈希 <code>%s</code></div></div>"
            % (s["records"], E(s["hash"])))


def sign_page(P, token: str, msg: str = "", done: dict | None = None) -> str:
    """What the client's signer sees: business flows, criteria and results, the seal; no code, no file names."""
    x = link_of(P.data_dir, token)
    t = P.store.ticket(x["key"])
    s = state(P.data_dir, x["key"])
    snap = s["snapshot"]
    title = "%s 验收签收" % x["key"]
    if not snap:
        return ev.page(title, "<h1>%s</h1><p>这单还没有证据包。</p>" % E(title))
    head = ("<h1>%s</h1><div class=sub>%s · %s · 签收人 %s%s</div>"
            % (E(snap["ticket"]["title"]), E(snap["project"]["name"]), E(x["key"]), E(x["signer"]), "（%s）" % E(x["role"]) if x["role"] else ""))
    body = [head]
    if done:
        body.append("<div class=seal><b class=ok>%s</b><div class=sub>%s · 记录哈希 <code>%s</code></div></div>" % (
            "已签收，谢谢" if done["action"] == "sign" else "已退回，乙方会按您写的原因处理", E(done["ts"]), E(done["hash"])))
    if msg:
        body.append("<p class=bad>%s</p>" % E(msg))
    if snap["ticket"]["body"]:
        body.append("<h2>问题描述</h2><p>%s</p>" % E(snap["ticket"]["body"][:600]).replace("\n", "<br>"))
    body += ["<h2>这次改的是哪项业务</h2>", _flows_html(snap)]
    chk = snap["check"]["result"]
    facts = ["自动化构建和测试：%s" % CHECK_LABEL.get(chk, chk)]
    if s.get("gates") is not None:  # counts only: the reasons name files, and the client's page shows no code
        n = {st: len([g for g in s["gates"] if g["state"] == st]) for st in (G.PASS, G.FAIL, G.UNKNOWN)}
        facts.append("验证门：%d 道，通过 %d 道%s%s" % (len(s["gates"]), n[G.PASS], "，没过 %d 道" % n[G.FAIL] if n[G.FAIL] else "",
                                                 "，结果未知 %d 道" % n[G.UNKNOWN] if n[G.UNKNOWN] else ""))
    rv = s.get("review")
    facts.append("乙方复核：%s" % ("%s，%s" % (rv["by"], rv["ts"][:16]) if rv else "还没有"))
    if s["missing"]:
        facts.append("<span class=warn>证据还缺：%s</span>" % E("、".join(s["missing"])))
    body += ["<h2>验收标准逐条</h2>", _ac_table(s, form=not done and t["status"] == "verify" and not x.get("used"), img="/sign/%s/f/" % token),
             "<h2>乙方准备情况</h2><ul>%s</ul>" % "".join("<li>%s</li>" % f if f.startswith("<span") else "<li>%s</li>" % E(f) for f in facts),
             _seal(s)]
    if not done and t["status"] == "verify" and not x.get("used"):
        body[-4] = "<form method=post>" + body[-4]
        body.append("<h2>签收</h2><p class=sub>每条都确认“通过”才能签收；有一条不通过请点“退回”，并写清楚哪里不对。签收会连同上面的证据包哈希一起留存。</p>"
                    "<p><label>请输入您的姓名确认身份：<input name=name required autocomplete=name style='font:inherit;padding:4px 8px'></label></p>"
                    "<p><textarea name=note rows=3 style='width:100%%;font:inherit;padding:6px' placeholder='备注（退回时必填：哪条不对、现象是什么）'></textarea></p>"
                    "<p style='display:flex;gap:12px;flex-wrap:wrap'><button name=action value=sign style='font:inherit;padding:8px 20px;background:#1a7f37;color:#fff;border:0;border-radius:6px'>签收</button>"
                    "<button name=action value=reject formnovalidate style='font:inherit;padding:8px 20px;background:#fff;color:#c62828;border:1px solid #c62828;border-radius:6px'>退回</button></p></form>")
    elif not done:
        d = s.get("decision")
        body.append("<p class=sub>%s</p>" % (E("这单已由 %s 于 %s %s。" % (d["signer"], d["ts"][:16], "签收" if d["kind"] == "sign" else "退回"))
                                            if d else "这个链接已经不能再签。"))
    return ev.page(title, "".join(body))


def package_page(P, key: str) -> str:
    """The whole package for the provider and the client's auditors: everything, records in order."""
    t = P.store.ticket(key)
    if not t:
        raise ApiError(404, "没有这张工单")
    s = state(P.data_dir, t["key"])
    recs = records(P.data_dir, t["key"])
    snap = s["snapshot"]
    title = "%s 证据包" % t["key"]
    body = ["<h1>%s · %s</h1><div class=sub>%s · 状态：%s · 生成于 %s</div>" % (E(t["key"]), E(t["title"]), E(t.get("pkey") or ""),
                                                                            E(STATUS_LABEL[s["status"]]), E(ev.now())), _seal(s)]
    if not snap:
        body.append("<p>还没有证据包：工单转到“待验证”时自动生成。</p>")
        return ev.page(title, "".join(body))
    body.append("<h2>缺项</h2>" + ("<p class=ok>无，证据齐全。</p>" if not s["missing"] else "<ul>%s</ul>" % "".join("<li class=bad>%s</li>" % E(m) for m in s["missing"])))
    body += ["<h2>业务流</h2>", _flows_html(snap), "<h2>验收标准</h2>", _ac_table(s, form=False, img="/e/%s/f/" % t["key"])]
    if snap["contract"]:
        body.append("<h2>变更契约（方案列的文件）</h2><ul>%s</ul>" % "".join("<li><code>%s</code> %s</li>" % (E(c["path"]), E(c["goal"])) for c in snap["contract"]))
    ch = snap.get("change")
    if ch:
        body.append("<h2>代码改动</h2><p>%d 个文件，+%d / −%d 行%s</p><ul>%s</ul>" % (
            len(ch["files"]), ch["added"], ch["removed"],
            "；分支 %s 提交 %s，%s 于 %s 采纳" % (E(snap["adopted"]["branch"]), E(snap["adopted"]["commit"]), E(snap["adopted"]["by"]), E(snap["adopted"]["at"]))
            if snap.get("adopted") else "", "".join("<li><code>%s</code></li>" % E(f) for f in ch["files"][:40])))
    if s.get("gates") is not None:
        word = {G.PASS: "<span class=ok>通过</span>", G.FAIL: "<span class=bad>没过</span>", G.UNKNOWN: "<span class=warn>未知</span>"}
        body.append("<h2>验证门（按成本从低到高）</h2><div class=wrap><table><thead><tr><th>门</th><th>结论</th><th>依据</th></tr></thead><tbody>%s</tbody></table></div>"
                    % "".join("<tr><td>%s</td><td>%s</td><td>%s%s%s</td></tr>" % (
                        E(g["name"]), word[g["state"]], E(g["why"]),
                        "<ul>%s</ul>" % "".join("<li>%s</li>" % E(str(x)) for x in sum([v for v in (g.get("detail") or {}).values() if isinstance(v, list)], []))
                        if g.get("detail") else "",
                        "<div class=warn>%s 放行（原来是%s）：%s</div>" % (E(g["waived"]["by"]), "没过" if g["waived"]["was"] == G.FAIL else "未知", E(g["waived"]["reason"]))
                        if g.get("waived") else "") for g in s["gates"]))
    c = snap["check"]
    body.append("<h2>构建与测试</h2><p>%s%s</p>%s" % (E(CHECK_LABEL.get(c["result"], c["result"])), "（%s）" % E(c["skip"]) if c.get("skip") else "",
                                                 "<ul>%s</ul>" % "".join("<li><code>%s</code> → %s</li>" % (E(str(x["cmd"])), E(str(x["exit_code"]))) for x in c["commands"])
                                                 if c["commands"] else ""))
    bp = snap["scope"]["beyond_plan"]
    body.append("<h2>范围</h2><p>%s</p>" % ("改动都在方案列的文件里。" if not bp else "超出方案：" + "、".join("<code>%s</code>" % E(f) for f in bp)))
    pc = snap["path"]
    body.append("<h2>入口路径</h2><p>%s</p><p class=sub>%s</p>" % (
        "<span class=ok>通过</span>" if pc["ok"] else "<span class=bad>未通过</span>：" + E(pc.get("why", "")), E(pc["basis"])))
    body.append("<h2>记录（追加式，每条带前一条的哈希）</h2><div class=wrap><table><thead><tr><th>#</th><th>时间</th><th>类型</th><th>谁</th><th>摘要</th><th>哈希</th></tr></thead><tbody>%s</tbody></table></div>"
                % "".join("<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>" % (
                    r.get("seq", 0), E(r.get("ts", "")), E(KIND.get(r.get("kind"), r.get("kind", ""))), E(r.get("by", "")), E(_summary(r)), E((r.get("hash") or "")[:16]))
                    for r in recs))
    return ev.page(title, "".join(body))


KIND = {"intake": "需求确认", "pack": "打包", "attach": "补充证据", "review": "乙方复核", "link": "发签收链接", "sign": "甲方签收", "reject": "甲方退回",
        "upstream_draft": "上游 PR 草稿", "upstream_approve": "批准提交", "upstream_submit": "提交上游", "upstream_state": "上游状态",
        "upstream_review": "上游评审", "upstream_ci": "上游 CI", "upstream_outcome": "上游结局", "upstream_reason": "补记原因"}


def _summary(r: dict) -> str:
    d = r.get("data") or {}
    k = r.get("kind")
    if k == "pack":
        s = d.get("snapshot") or {}
        return "%s；%d 条 AC，%d 个文件" % (d.get("why", ""), len(s.get("ac") or []), len((s.get("change") or {}).get("files") or []))
    if k == "intake":
        return "%s 确认了 %d 条验收标准%s" % (d.get("confirmed_by", ""), len(d.get("ac") or []), "（%d 条待确认）" % len(d["open"]) if d.get("open") else "")
    if k == "attach":
        return "%s%s%s" % (d.get("ac") or "整单", "：" + d["note"][:60] if d.get("note") else "", "（截图）" if d.get("file") else "")
    if k == "review":
        w = d.get("waive") or {}
        return d.get("note", "")[:80] + ("；放行：%s" % "、".join(G.NAMES.get(g, g) for g in w) if w else "")
    if k == "link":
        return "签收人 %s，有效至 %s" % (d.get("signer"), d.get("expires"))
    if k == "upstream_draft":
        return "%s（%s → %s）" % (d.get("title", ""), d.get("head", ""), d.get("base", ""))
    if k in ("upstream_approve", "upstream_submit"):
        return d.get("url") or d.get("note") or "草稿哈希 %s" % (d.get("hash") or "")[:12]
    if k == "upstream_state":
        return "%s → %s，CI %s" % (d.get("from") or "—", d.get("to"), d.get("ci"))
    if k == "upstream_review":
        return "%s %s：%s" % (d.get("by"), d.get("state"), (d.get("body") or "")[:60])
    if k == "upstream_ci":
        return d.get("state", "")
    if k == "upstream_outcome":
        return "%s%s，评审 %s 轮" % ("已合并" if d.get("state") == "merged" else "已关闭", "（%s）" % d["by"] if d.get("by") else "", d.get("rounds"))
    if k == "upstream_reason":
        return d.get("reason", "")
    if k in ("sign", "reject"):
        return "%s；签的证据包哈希 %s" % (d.get("note") or ("全部通过" if k == "sign" else ""), (d.get("package_hash") or "")[:12])
    return ""


def file_bytes(data_dir: Path, name: str) -> tuple[bytes, str]:
    if not re.match(r"^[0-9a-f]{64}\.(png|jpg|webp)$", name or ""):
        raise ApiError(404, "没有这个文件")
    f = edir(data_dir) / "files" / name
    if not f.is_file():
        raise ApiError(404, "没有这个文件")
    return f.read_bytes(), {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[name.rsplit(".", 1)[1]]


def brief(data_dir: Path, key: str) -> dict:
    s = state(data_dir, key)
    d = s.get("decision")
    return {"status": s["status"], "label": STATUS_LABEL[s["status"]], "missing": s["missing"], "intact": s["intact"], "problem": s["problem"],
            "hash": s["hash"], "records": s["records"], "page": "/e/%s" % key.upper(),
            "attachments": len(s.get("attachments") or []), "review": s.get("review"),
            "link": (s.get("links") or [None])[-1], "decision": d and {k: d.get(k) for k in ("kind", "signer", "role", "ts", "note", "via")},
            "gates": s.get("gates"), "gate_state": s.get("gate_state", "")}


def record_accept(P, t: dict, by: str, passed: bool, note: str) -> str:
    """The 验收 button inside the platform writes into the package too, so every verdict is on the chain."""
    s = state(P.data_dir, t["key"])
    if not s["packed"] or not s["intact"]:
        return ""
    acs = [a["id"] for a in (s["snapshot"] or {}).get("ac") or []]
    rec = _add(epath(P.data_dir, t["key"]), "sign" if passed else "reject", by,
                    {"signer": by, "role": "", "ac": {a: "pass" if passed else "" for a in acs}, "note": note, "pack_hash": s["pack_hash"],
                     "package_hash": s["hash"], "via": "平台验收按钮", "client": ""})
    return rec["hash"]


def owns(data_dir: Path, key: str, name: str) -> None:
    """A file is served under a ticket only when that ticket's package refers to it."""
    if not any(r.get("kind") == "attach" and (r.get("data") or {}).get("file") == name for r in records(data_dir, key)):
        raise ApiError(404, "没有这个文件")


def message_page(msg: str) -> str:
    return ev.page("验收签收", "<h1>验收签收</h1><p>%s</p>" % E(msg))
