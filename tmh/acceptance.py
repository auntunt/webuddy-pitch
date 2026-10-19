"""Acceptance state machine for change contracts (.tmh/tasks/T###-*.md).

Closing a task is a person's act: the implementer's own tests, a green build and a merged branch are each
evidence, never a verdict. So a task moves through explicit states, and each move checks what it needs:

  draft_contract → implementing            only when every acceptance criterion (AC) has a check and a layer
  implementing → verify_local              only after a passing `tmh verify` and a path check (path.py)
  verify_local → merged → deployed_awaiting_verify → auto_verified | needs_human
  auto_verified | needs_human → user_confirmed_fix → closed      a person only (confirm / close)
  any check state → implementing           a failed check sends the task back, with the reason

State, history and evidence pointers live in .tmh/acceptance/<task>.json; the contract's "验收状态" line mirrors
the current state for people reading the contract. Layers: L1 contract and flow review, L2 independent rerun,
L3 retest after deployment, L4 a person on the real system (docs/acceptance.md).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from statistics import median
from contextlib import contextmanager

from . import config as cfgmod
from .report import now

STATES = [
    ("draft_contract", "草拟契约"), ("implementing", "实现中"), ("verify_local", "本地验证通过"), ("merged", "已合并"),
    ("deployed_awaiting_verify", "已部署待回测"), ("auto_verified", "自动证据齐全"), ("needs_human", "待人工验收"),
    ("user_confirmed_fix", "用户已确认"), ("closed", "已关闭"),
]
LABEL = dict(STATES)
CHECKING = ("verify_local", "merged", "deployed_awaiting_verify", "auto_verified", "needs_human")
MOVES = {  # state -> states it may move to
    "draft_contract": ("implementing",),
    "implementing": ("verify_local",),
    "verify_local": ("merged", "needs_human", "implementing"),
    "merged": ("deployed_awaiting_verify", "needs_human", "implementing"),
    "deployed_awaiting_verify": ("auto_verified", "needs_human", "implementing"),
    "auto_verified": ("user_confirmed_fix", "needs_human", "implementing"),
    "needs_human": ("user_confirmed_fix", "implementing"),
    "user_confirmed_fix": ("closed", "implementing"),
    "closed": ("implementing",),  # reopened by a person
}
HUMAN_ONLY = {"user_confirmed_fix", "closed"}
LAYERS = ("L1", "L2", "L3", "L4")
AGENT_NAMES = {"", "agent", "ai", "bot", "claude", "codex", "tmh", "assistant", "智能体", "助手"}
AGENT_ENV = ("CLAUDECODE", "CODEX_SANDBOX", "TMH_RUN")  # set inside Claude Code, Codex sandboxes and platform runs
PLACEHOLDER = re.compile(r"^\s*(（.*）)?\s*$")


class Refused(Exception):
    """A move the rules do not allow; the message says what is missing."""


# ---------------------------------------------------------------- contract parsing
def acc_dir(root: Path) -> Path:
    return cfgmod.tmh_dir(root) / "acceptance"


def find_contract(root: Path, tid: str) -> Path:
    d = cfgmod.tmh_dir(root) / "tasks"
    tid = tid.upper().split("-")[0]
    hit = sorted(d.glob("%s-*.md" % tid)) + sorted(d.glob("%s.md" % tid)) if d.is_dir() else []
    if not hit:
        raise Refused("找不到任务契约 %s（.tmh/tasks/%s-*.md）" % (tid, tid))
    return hit[0]


def _section(text: str, num: int) -> str:
    m = re.search(r"^## %d\..*?$(.*?)(?=^## \d+\.|\Z)" % num, text, re.M | re.S)
    return m.group(1) if m else ""


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def ac_rows(text: str) -> list[dict]:
    """The rows of section 4: id, clause, layer, check and result, whatever order the columns are in."""
    rows, head = [], None
    for line in _section(text, 4).splitlines():
        if not line.strip().startswith("|"):
            continue
        c = _cells(line)
        if head is None:
            if any("验收条款" in x for x in c):
                head = c
            continue
        if set("".join(c)) <= set("-: "):
            continue
        get = lambda *names: next((c[i] for i, h in enumerate(head) if i < len(c) and any(n in h for n in names)), "")
        rows.append({"id": c[0], "clause": get("验收条款"), "layer": get("层级").upper()[:2], "check": get("检查方式"), "result": get("结果")})
    return rows


def ac_problems(text: str) -> list[str]:
    """Why this contract cannot enter implementation yet (empty when it can)."""
    rows = ac_rows(text)
    if not rows:
        return ["第 4 节没有验收标准（AC）表"]
    out = []
    if not any("层级" in l for l in _section(text, 4).splitlines() if "验收条款" in l):
        out.append("第 4 节的表没有“层级”列（旧契约：按 docs/acceptance.md 的迁移说明补一列 L1–L4）")
    for r in rows:
        if PLACEHOLDER.match(r["clause"]):
            out.append("%s 没有写验收条款" % r["id"])
        if PLACEHOLDER.match(r["check"]):
            out.append("%s 没有写检查方式" % r["id"])
        if out and "层级" in out[0]:
            continue
        if r["layer"] not in LAYERS:
            out.append("%s 的层级要写 L1/L2/L3/L4（现在是“%s”）" % (r["id"], r["layer"] or "空"))
    return out


def _ac_size(text: str) -> tuple[int, int]:
    rows = [r for r in ac_rows(text) if not PLACEHOLDER.match(r["clause"])]
    return len(rows), sum(len(r["clause"]) + len(r["check"]) for r in rows)


def size_warnings(text: str, peers=None) -> list[str]:
    """Advisory only. peers are other contract texts (excluding this contract).

    With >=5 nonempty peers, compare AC count and clause/check character count to
    their medians. Otherwise use absolute limits of 8 ACs and 1600 characters.
    Titles and explicit new-file/module estimates are independent warning signals.
    """
    count, chars = _ac_size(text)
    sizes = [size for p in (peers or []) if (size := _ac_size(p))[0]]
    out = []
    if len(sizes) >= 5:
        for value, typical, label in ((count, median(s[0] for s in sizes), "AC 条数"),
                                      (chars, median(s[1] for s in sizes), "AC 字符量")):
            if typical > 0 and value >= 2 * typical:
                out.append("%s %d 达到同批中位数 %g 的 2 倍，建议检查是否需要拆分" % (label, value, typical))
    else:
        if count > 8:
            out.append("AC 超过 8 条（%d 条），建议检查任务尺寸" % count)
        if chars > 1600:
            out.append("AC 字符量超过 1600（%d 字），建议检查任务尺寸" % chars)
    title = re.search(r"^#\s+(.+)$", text, re.M)
    if title and re.search(r"\S\s*[与和及]\s*\S", title.group(1)):
        out.append("标题有并列结构，建议确认是否包含多件独立任务")
    estimates = re.findall(r"(?:新建|新增)\s*(\d+)\s*(?:个)?\s*(?:模块|文件)", text)
    estimates += re.findall(r"\b(?:create|add)\s+(\d+)\s+(?:new\s+)?(?:modules?|files?)\b", text, re.I)
    for line in text.splitlines():
        if re.search(r"(?:预计)?(?:新建|新增)(?:模块|文件)\s*[：:]", line):
            estimates.append(str(len(set(re.findall(r"`([^`]+)`", line)))))
    if any(int(n) > 3 for n in estimates):
        out.append("预计新建模块或文件超过 3 个，建议检查边界及依赖")
    return out


def entries(text: str) -> list[str]:
    """Entry points the contract names (backticked, on the 入口 line of section 5)."""
    for line in _section(text, 5).splitlines():
        if re.match(r"\s*-\s*入口[：:]", line):
            return [x.strip() for x in re.findall(r"`([^`]+)`", line) if x.strip()]
    return []


def passed(result: str) -> bool:
    return result.strip().startswith(("通过", "✅", "pass", "PASS"))


# ---------------------------------------------------------------- state record
def _record_path(root: Path, tid: str) -> Path:
    return acc_dir(root) / ("%s.json" % tid)


def _tid(p: Path) -> str:
    return re.match(r"(T\d+)", p.name).group(1)


def load(root: Path, tid: str) -> dict:
    c = find_contract(root, tid)
    tid = _tid(c)
    p = _record_path(root, tid)
    rec = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    base = {"task": tid, "file": c.relative_to(root).as_posix(), "state": "draft_contract", "build_id": None, "ref": None,
            "evidence": [], "blockers": [], "confirmed_by": None, "confirmed_at": None, "history": []}
    base.update(rec)
    return base


def _save(root: Path, rec: dict) -> None:
    p = _record_path(root, rec["task"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    c = root / rec["file"]
    text = c.read_text(encoding="utf-8")
    line = "- 验收状态：%s（%s）" % (rec["state"], LABEL[rec["state"]])
    if re.search(r"^- 验收状态：.*$", text, re.M):
        text = re.sub(r"^- 验收状态：.*$", line, text, count=1, flags=re.M)
    elif re.search(r"^- 状态：.*$", text, re.M):
        text = re.sub(r"^(- 状态：.*)$", r"\1\n" + line, text, count=1, flags=re.M)
    c.write_text(text, encoding="utf-8")


def start(root: Path, tid: str) -> dict:
    """A new contract starts as draft_contract."""
    rec = load(root, tid)
    if not _record_path(root, rec["task"]).exists():
        rec["history"].append({"at": now(), "from": None, "to": "draft_contract", "who": "tmh", "note": "建契约"})
        _save(root, rec)
    return rec


def agent_session() -> str:
    return next((k for k in AGENT_ENV if os.environ.get(k)), "")


def _human(who: str, to: str) -> None:
    env = agent_session()
    if env:
        raise Refused("“%s”只能由人做：当前是智能体会话（%s），请把结论交给人，由人在自己的终端或平台“验收通过”里操作" % (LABEL[to], env))
    if (who or "").strip().lower() in AGENT_NAMES:
        raise Refused("“%s”要写明是谁确认的：--who <姓名>（不能是 agent / 智能体）" % LABEL[to])


# ---------------------------------------------------------------- moves
def advance(root: Path, tid: str, to: str, who: str = "", note: str = "", ref: str = "", build: str = "",
            path_result: dict | None = None) -> dict:
    """Move a task to state `to` if the rules allow it; raises Refused with the reason otherwise."""
    root = root.resolve()
    rec = load(root, tid)
    cur = rec["state"]
    if to not in LABEL:
        raise Refused("未知状态 %s，可选：%s" % (to, "、".join(LABEL)))
    if to not in MOVES.get(cur, ()):
        raise Refused("不能从“%s”直接到“%s”，可以去：%s" % (LABEL[cur], LABEL[to], "、".join(LABEL[x] for x in MOVES.get(cur, ())) or "无"))
    text = (root / rec["file"]).read_text(encoding="utf-8")
    ev = None
    if to in HUMAN_ONLY or cur == "closed":
        _human(who, to if to in HUMAN_ONLY else "closed")
    if to == "implementing" and cur != "draft_contract" and not note.strip():
        raise Refused("退回实现要写原因：--note \"哪条 AC 没过、证据在哪\"")
    if to == "implementing" and cur == "draft_contract":
        probs = ac_problems(text)
        if probs:
            raise Refused("没有完整的验收标准，不能进入实现：\n  - " + "\n  - ".join(probs))
    if to == "verify_local":
        rep = cfgmod.tmh_dir(root) / "reports" / "verify-latest.json"
        v = json.loads(rep.read_text(encoding="utf-8")) if rep.exists() else None
        if not v or not v.get("passed"):
            raise Refused("先运行 tmh verify --task %s 并通过（%s）" % (rec["task"], "还没有验证报告" if not v else "最近一次未通过"))
        if path_result is None:
            from .path import path_check
            path_result = path_check(root, rec["task"])
        if not path_result["ok"]:
            raise Refused("入口路径检查没通过：\n  - " + "\n  - ".join(path_result["problems"]))
        ev = {"type": "tmh_verify", "at": v.get("time"), "ok": True, "report": ".tmh/reports/verify-latest.json",
              "path_check": {"entries": path_result["entries"], "covered": len(path_result["covered"]), "manual": len(path_result["manual"])}}
        rec["blockers"] = [b for b in rec["blockers"] if not b.startswith("path_unverified")]
        rec["blockers"] += ["path_unverified: %s" % m for m in path_result["manual"]]
    if to == "merged":
        if not ref.strip():
            raise Refused("写明合并到哪里：--ref <提交号或合并请求>")
        rec["ref"] = ref.strip()
        ev = {"type": "merge", "at": now(), "ref": rec["ref"]}
    if to == "deployed_awaiting_verify":
        if not build.strip():
            raise Refused("写明部署的是哪个可测构建：--build <构建号或版本>")
        rec["build_id"] = build.strip()
        ev = {"type": "deploy", "at": now(), "build_id": rec["build_id"]}
    if to == "auto_verified":
        kinds = {e.get("type") for e in rec["evidence"]}
        lack = [lb for k, lb in (("tmh_verify", "本地验证和入口路径检查"), ("deploy", "部署的构建号")) if k not in kinds]
        if lack:
            raise Refused("证据包缺 %s，不能标“自动证据齐全”" % "、".join(lack))
        rows = ac_rows(text)
        left = [r["id"] for r in rows if not passed(r["result"])]
        l4 = [r["id"] for r in rows if r["layer"] == "L4"]
        why = (["AC %s 还没有“通过”的结果" % "、".join(left)] if left else []) + (["AC %s 是 L4，要人验收" % "、".join(l4)] if l4 else []) \
            + (["还有阻塞：%s" % "；".join(rec["blockers"])] if rec["blockers"] else [])
        if why:
            raise Refused("证据不齐，不能标“自动证据齐全”，请改去“待人工验收”（needs_human）：\n  - " + "\n  - ".join(why))
        ev = {"type": "ac_results", "at": now(), "ok": True, "build_id": rec["build_id"]}
    if to == "user_confirmed_fix":
        rec["confirmed_by"], rec["confirmed_at"] = who.strip(), now()
        ev = {"type": "user_confirmed", "at": rec["confirmed_at"], "by": rec["confirmed_by"], "note": note}
    if to == "implementing" and cur != "draft_contract":
        rec["confirmed_by"] = rec["confirmed_at"] = None
    if ev:
        rec["evidence"].append(ev)
    rec["history"].append({"at": now(), "from": cur, "to": to, "who": who or "agent", "note": note})
    rec["state"] = to
    _save(root, rec)
    _chain(root, rec, cur, to, who, note, text)
    return rec


def evidence_path(root: Path, tid: str) -> Path:
    return cfgmod.tmh_dir(root) / "evidence" / ("%s.jsonl" % tid)


def _chain(root: Path, rec: dict, cur: str, to: str, who: str, note: str, text: str) -> None:
    """The task's evidence package (tmh/evidence.py): a snapshot when it is handed over for acceptance, then the
    person's confirmation (carrying the hash of what they confirmed), the close, or the send-back."""
    import hashlib
    from . import evidence as ev
    path = evidence_path(root, rec["task"])
    recs = ev.read(path)
    if to in ("auto_verified", "needs_human"):
        data = {"state": to, "contract": rec["file"], "contract_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "ac": ac_rows(text), "entries": entries(text), "evidence": rec["evidence"], "blockers": rec["blockers"],
                "build_id": rec.get("build_id"), "ref": rec.get("ref")}
        kind = "pack"
    elif to == "user_confirmed_fix":
        data, kind = {"signer": who.strip(), "note": note, "package_hash": ev.head(recs), "via": "tmh accept confirm"}, "sign"
    elif to == "closed":
        data, kind = {"by": who.strip(), "note": note}, "close"
    elif to == "implementing" and cur != "draft_contract" and recs:
        data, kind = {"from": cur, "note": note}, "reject"
    else:
        return
    ev.append(path, kind, who or "agent", data)


PROPOSAL_KINDS = {"missing-requirement": "补充需求", "dependency": "澄清依赖"}
PROPOSAL_HEADER = "<!-- tmh-proposal "


@contextmanager
def _proposal_guard(root: Path):
    """Serialize proposal creation/confirmation across CLI processes; fail closed on a stale lock."""
    directory = acc_dir(root) / "proposals"
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".write-lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise Refused("草稿操作正在进行；若上次操作中断，请由人核实后清理 proposals/.write-lock 再试") from None
    try:
        yield directory
    finally:
        lock.rmdir()


def _proposal_record(path: Path) -> tuple[dict, str]:
    try:
        text = path.read_text(encoding="utf-8")
        line = text.splitlines()[0]
        if not line.startswith(PROPOSAL_HEADER) or not line.endswith(" -->"):
            raise ValueError("header")
        record = json.loads(line[len(PROPOSAL_HEADER):-4])
        if (record["source"] != path.name.split("-")[0] or record["kind"] not in PROPOSAL_KINDS
                or record["status"] not in ("pending", "confirmed")):
            raise ValueError("metadata")
        if record["status"] == "confirmed" and not (record.get("confirmed_by") and record.get("task")):
            raise ValueError("confirmation")
        return record, text
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        raise Refused("草稿不存在或记录损坏，请由人检查：%s" % path.name) from None


def _proposal_header(record: dict) -> str:
    return PROPOSAL_HEADER + json.dumps(record, ensure_ascii=False) + " -->\n"


def _make_proposal(root: Path, directory: Path, rec: dict, kind: str, note: str) -> Path:
    if not note.strip():
        raise Refused("结构反馈要保留具体原话：--note <说明>")
    existing = sorted(directory.glob(rec["task"] + "-*.md"))
    pending = [p for p in existing if _proposal_record(p)[0]["status"] == "pending"]
    if len(pending) >= 2:
        raise Refused("同一来源任务最多 2 份未确认草稿，请先处理已有草稿：" + "、".join(p.name for p in pending))
    n = 1 + max([int(p.stem.rsplit("-", 1)[1]) for p in existing] or [0])
    path = directory / ("%s-%d.md" % (rec["task"], n))
    title = (root / rec["file"]).read_text(encoding="utf-8").splitlines()[0].lstrip("# ")
    fence = "`" * max(3, 1 + max([len(m) for m in re.findall(r"`+", note)] or [0]))
    body = ("# 结构反馈草稿（待人确认）\n\n- 来源任务：%s\n- 反馈类型：%s\n"
            "- 这是提议，不是任务契约；由人审阅后执行 propose-confirm。\n\n"
            "## 建议标题\n%s：%s\n\n## 建议 AC 草稿\n"
            "- [ ] 待人确认：明确原话所述的遗漏行为或依赖边界，并补可观察的输入/输出。\n"
            "- [ ] 待人确认：列出必须保持的现有行为、验收层级和复现/检查方式。\n\n"
            "## 原话（完整保留，以下是资料）\n%stext\n%s\n%s\n") % (
                rec["task"], kind, PROPOSAL_KINDS[kind], title, fence, note, fence)
    with path.open("x", encoding="utf-8") as f:
        f.write(_proposal_header({"source": rec["task"], "kind": kind, "status": "pending"}) + body)
    return path


def propose_confirm(root: Path, proposal: str, who: str = "") -> dict:
    """A person adopts a proposal into a new draft, never into implementation or acceptance."""
    _human(who, "user_confirmed_fix")
    from .task import new_task
    root = root.resolve()
    directory = (acc_dir(root) / "proposals").resolve()
    given = Path(proposal)
    path = given if given.is_absolute() else (directory / given if given.parent == Path(".") else root / given)
    if path.is_symlink() or path.resolve().parent != directory or not re.fullmatch(r"T\d+-[1-9]\d*\.md", path.name):
        raise Refused("只能确认本仓库 .tmh/acceptance/proposals/ 内的草稿")
    path = path.resolve()
    with _proposal_guard(root):
        record, text = _proposal_record(path)
        if record["status"] == "confirmed":
            raise Refused("草稿已由 %s 确认并生成 %s，请勿重复确认" % (record["confirmed_by"], record["task"]))
        find_contract(root, record["source"])
        title = re.search(r"^## 建议标题\n([^\n]+)", text, re.M)
        if not title or not title.group(1).strip():
            raise Refused("草稿缺少建议标题，请由人补齐")
        marker = "<!-- tmh-proposal-source: %s -->" % path.name
        # If a prior confirmation stopped after new_task, reuse that draft on retry.
        drafts = [p for p in (cfgmod.tmh_dir(root) / "tasks").glob("T*.md")
                  if p.read_text(encoding="utf-8").partition("## 1. 需求原文\n")[2].startswith(marker + "\n")]
        if len(drafts) > 1:
            raise Refused("草稿对应多个任务，请由人核对，不再创建")
        contract = drafts[0] if drafts else new_task(root, title.group(1).strip(), "feature", marker + "\n" + text)
        tid = _tid(contract)
        if start(root, tid)["state"] != "draft_contract":
            raise Refused("草稿对应的任务已不在 draft_contract，请由人核对")
        record.update(status="confirmed", confirmed_by=who.strip(), confirmed_at=now(), task=tid)
        body = text.split("\n", 1)[1].replace("# 结构反馈草稿（待人确认）", "# 结构反馈草稿（已由人确认）", 1)
        updated = (_proposal_header(record) + body
                   + "\n## 人工确认记录\n- 确认人：%s\n- 生成任务：%s（初始 draft_contract）\n" % (who.strip(), tid))
        # Write a replacement first so interrupted writes never turn a pending draft into a broken header.
        staged = path.with_suffix(".tmp")
        try:
            staged.write_text(updated, encoding="utf-8")
            staged.replace(path)
        finally:
            staged.unlink(missing_ok=True)
        return {"task": tid, "file": contract.relative_to(root).as_posix(), "proposal": path.relative_to(root).as_posix(),
                "confirmed_by": who.strip(), "state": load(root, tid)["state"]}


def correct(root: Path, tid: str, kind: str, note: str, who: str = "") -> dict:
    """Record a correction (a mis-triage, a change that grew too big, a wrong direction). When one kind recurs,
    the fix is a reviewed change to the acceptance skill, not a note in some session's memory."""
    rec = load(root, tid)
    p = acc_dir(root) / "corrections.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"at": now(), "task": rec["task"], "kind": kind, "note": note, "who": who or "agent"}
    if kind in PROPOSAL_KINDS:
        with _proposal_guard(root) as directory:
            proposal = _make_proposal(root, directory, rec, kind, note)
            row["proposal"] = proposal.relative_to(root).as_posix()
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n = sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and json.loads(l).get("kind") == kind)
    th = int(cfgmod.load(root).get("correction_threshold", 3))
    return dict(row, count=n, threshold=th, due=n >= th)


def records(root: Path) -> list[dict]:
    d = cfgmod.tmh_dir(root) / "tasks"
    out = []
    for c in sorted(d.glob("T*.md")) if d.is_dir() else []:
        try:
            out.append(load(root, _tid(c)))
        except (Refused, AttributeError, ValueError):
            continue
    return out


def by_build(root: Path, build: str) -> list[dict]:
    return [r for r in records(root) if r.get("build_id") == build]
