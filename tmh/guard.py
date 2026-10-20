"""Agent hooks. Claude Code calls these through .claude/settings.json and Codex
through .codex/hooks.json; the same checks also run from a git pre-commit hook
for human edits.

Hook protocol (Claude Code; Codex follows the same shape): JSON on stdin;
exit 0 = allow, exit 2 = block and the stderr text is shown to the model so it
can correct course.
"""
from __future__ import annotations

import io
import json
import os
import re
import shlex
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from . import config as cfgmod
from . import scanner
from .fsutil import git, git_changed_files, match_any, read_text
from .verify import BLOCKING_SEVERITIES, fingerprint, load_baseline, source_changes

ALWAYS_PROTECTED = [".tmh/baseline.json", ".tmh/config.json", ".tmh/tool/**", ".claude/settings.json", ".codex/hooks.json", ".codex/config.toml"]
DANGEROUS_BASH = [
    (r"\bgit\s+push\b.*(--force|-f\b)", "强制推送会覆盖远端历史"),
    (r"\bgit\s+reset\s+--hard\b", "会丢弃未提交改动"),
    (r"\bgit\s+clean\s+-[a-z]*f", "会删除未跟踪文件"),
    (r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME|\*)(\s|$)", "危险的递归删除"),
    (r"\b(mvn|gradle|\./mvnw|\./gradlew)\b.*\b(deploy|publish)\b", "发布制品属于人工操作"),
    (r"\bdotnet\s+nuget\s+push\b", "发布制品属于人工操作"),
    (r"(?i)\b(drop\s+(table|database|schema|user)|truncate\s+table)\b", "破坏性数据库语句"),
    (r"(?i)\b(disql|sqlplus|ksql|gsql|obclient|isql)\b", "直接连库执行 SQL 需由人确认（可让人工在终端执行）"),
    (r"\baccept\s+(confirm|close)\b|\baccept\s+advance\b.*--to[= ]\s*(user_confirmed_fix|closed)\b", "用户确认与关单只能由人操作（验收状态机）"),
    (r"\baccept\s+propose-confirm\b", "结构反馈草稿只能由人确认（不允许智能体创建已确认任务）"),
]


def _repo_root(payload: dict) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    cwd = Path(env or payload.get("cwd") or os.getcwd())
    top = git(cwd, "rev-parse", "--show-toplevel")
    return Path(top) if top else cwd


def _relpath(root: Path, file_path: str) -> str:
    p = Path(file_path)
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return ""


def _read_payload() -> dict:
    try:
        return json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return {}


def _edited_paths(payload: dict) -> list[str]:
    ti = payload.get("tool_input", {}) or {}
    out = [ti.get(k) for k in ("file_path", "notebook_path", "path") if ti.get(k)]
    return out


def pre_edit(payload: dict | None = None) -> int:
    payload = payload if payload is not None else _read_payload()
    root = _repo_root(payload)
    cfg = cfgmod.load(root)
    base = load_baseline(root) or {}
    for fp in _edited_paths(payload):
        rp = _relpath(root, fp)
        if not rp:
            continue
        if match_any(rp, ALWAYS_PROTECTED):
            sys.stderr.write("[tmh] %s 是 harness 的验证配置，智能体不能修改。如需调整请让维护人员手工修改。\n" % rp)
            return 2
        if cfg.get("allow_protected_edits"):
            continue
        # Only files that existed at baseline are locked: new tests are welcome.
        if rp in base.get("protected", {}) and (root / rp).exists():
            sys.stderr.write(
                "[tmh] %s 是基线中已存在的测试/受保护文件，不能修改或删除（防止通过改测试让结果变绿）。\n"
                "可以新增测试文件；若确实要改旧测试（例如断言依赖 Oracle 方言），请在任务契约里写明原因并请维护人员确认后手工调整。\n" % rp)
            return 2
    return 0


def post_edit(payload: dict | None = None) -> int:
    payload = payload if payload is not None else _read_payload()
    root = _repo_root(payload)
    cfg = cfgmod.load(root)
    base = load_baseline(root) or {}
    known = set(base.get("findings", []))
    rules = scanner.active_rules(scanner.load_rules(root), cfg)
    msgs = []
    for fp in _edited_paths(payload):
        rp = _relpath(root, fp)
        if not rp or rp.startswith(".tmh/"):
            continue
        _mark_stale(root, rp)
        text = read_text(root / rp)
        if text is None:
            continue
        for f in scanner.scan_text(rp, text, rules, cfg):
            if f["severity"] in BLOCKING_SEVERITIES and fingerprint(f) not in known:
                msgs.append("- %s:%d %s %s\n  建议：%s" % (f["file"], f["line"], f["rule"], f["title"], f["advice"][:160]))
    if msgs:
        sys.stderr.write("[tmh] 本次修改引入了与改造目标不兼容的写法（若是有意为之，请在任务契约里说明）：\n" + "\n".join(msgs[:10]) + "\n")
        return 2
    return 0


def _mark_stale(root: Path, rp: str) -> None:
    d = cfgmod.tmh_dir(root)
    if not d.is_dir():
        return
    with open(d / "stale-files.txt", "a", encoding="utf-8") as f:
        f.write(rp + "\n")


def _human_accept_command(command: str) -> bool:
    """Supplement raw patterns with shell-word and actual CLI option parsing.

    This recognizes literal tmh invocations, not arbitrary shell evaluation;
    acceptance._human remains the independent runtime identity check.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>\n")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return False  # Invalid shell quoting; the original raw checks still apply.
    segments, segment = [], []
    for word in words:
        if word and set(word) <= set(";&|()<>\n"):
            segments.append(segment)
            segment = []
        else:
            segment.append(word)
    segments.append(segment)
    # shlex removes quotes: a quoted ";" may be a CLI option's value.
    # Also parse the unsplit words so that value cannot hide a human action.
    segments.append(words)
    from .acceptance import HUMAN_ONLY
    from .cli import build_parser
    parser = None
    for segment in segments:
        for i, word in enumerate(segment):
            if word != "accept" or i == 0 or Path(segment[i - 1]).name not in ("tmh", "tmh.py"):
                continue
            parser = parser or build_parser()
            # Parse only, never dispatch. CLI parsing covers option order,
            # --key=value and argparse's supported option abbreviations.
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                try:
                    args, _ = parser.parse_known_args(segment[i:])
                except SystemExit:
                    continue
            if args.action in ("confirm", "close", "propose-confirm") or (
                    args.action == "advance" and args.to in HUMAN_ONLY):
                return True
    return False


def pre_bash(payload: dict | None = None) -> int:
    payload = payload if payload is not None else _read_payload()
    cmd = (payload.get("tool_input") or {}).get("command", "")
    root = _repo_root(payload)
    cfg = cfgmod.load(root)
    # Shell edits bypass the Edit/Write hook, so check writes to locked files here too.
    if re.search(r"(>|\bsed\s+-i|\btee\b|\bmv\b|\brm\b|\bcp\b|\btruncate\b|open\(|write_text|\.write\()", cmd):
        base = load_baseline(root) or {}
        locked = list(ALWAYS_PROTECTED[:2]) + ([] if cfg.get("allow_protected_edits") else list(base.get("protected", {})))
        hit = [p for p in locked if p in cmd or p.rsplit("/", 1)[-1] in cmd.split()]
        if hit:
            sys.stderr.write("[tmh] 该命令可能会改动受保护文件 %s。基线测试与验证配置不能由智能体修改；新增测试请另建文件。\n" % ", ".join(hit[:3]))
            return 2
    for rx, why in DANGEROUS_BASH:
        if why.startswith("直接连库") and cfg.get("allow_db_cli"):
            continue
        if re.search(rx, cmd):
            sys.stderr.write("[tmh] 已拦截命令：%s（%s）。如确需执行，请告诉用户由人工在终端操作。\n" % (cmd[:200], why))
            return 2
    if _human_accept_command(cmd):
        sys.stderr.write("[tmh] 已拦截人工验收/草稿确认命令；只能由人在正常终端操作。\n")
        return 2
    return 0


def stop(payload: dict | None = None) -> int:
    """Before the agent ends its turn: if code changed since the last verify, ask it to verify."""
    payload = payload if payload is not None else _read_payload()
    if payload.get("stop_hook_active"):
        return 0
    root = _repo_root(payload)
    base = load_baseline(root)
    if base is None:
        return 0
    changed = source_changes(git_changed_files(root, base.get("head")) or [])
    if not changed:
        return 0
    kb_reminder = _kb_reminder(root)
    latest = cfgmod.tmh_dir(root) / "reports" / "verify-latest.json"
    newest_change = max(((root / c).stat().st_mtime for c in changed if (root / c).exists()), default=0)
    # Changes that predate the baseline are not this session's work.
    if newest_change <= base.get("created_ts", 0):
        return 0
    if latest.exists() and latest.stat().st_mtime >= newest_change:
        if kb_reminder:
            print(json.dumps({"decision": "block", "reason": kb_reminder}, ensure_ascii=False))
        return 0
    print(json.dumps({"decision": "block", "reason": "代码有改动但还没有运行独立验证。请运行 `python3 .tmh/tool/tmh.py verify`，把结果（通过/失败及原因）写进任务契约的“验证记录”，再结束。"}, ensure_ascii=False))
    return 0


def _kb_reminder(root: Path) -> str:
    """Code was edited after the knowledge base was last rebuilt: ask for an incremental update."""
    x = cfgmod.tmh_dir(root)
    stale = x / "stale-files.txt"
    if not (x / "cache" / "graph.db").exists() or not stale.exists():
        return ""
    files = sorted(set(stale.read_text(encoding="utf-8").split()))
    if not files:
        return ""
    return ("项目知识库在这些文件改动后还没更新：%s。请按 knowledge-upkeep 技能运行 `python3 .tmh/tool/tmh.py kb build`，"
            "修订它报告的过期页面（tmh kb next → 改 → tmh kb done），再结束。" % "、".join(files[:6]))


def pre_commit() -> int:
    """git pre-commit: same protection for Codex sessions and humans."""
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel") or ".")
    cfg = cfgmod.load(root)
    base = load_baseline(root) or {}
    staged = (git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMRD") or "").splitlines()
    bad = [s for s in staged if s in base.get("protected", {}) and not cfg.get("allow_protected_edits")]
    if bad:
        sys.stderr.write("[tmh] 提交包含对基线测试/受保护文件的修改：\n%s\n若经过人工确认，可用 git commit --no-verify 提交，并在任务契约中记录原因。\n" % "\n".join("  " + b for b in bad))
        return 1
    return 0


# ---- engine-neutral entry points (Codex hooks, and tool logging for both engines)
def _tool_input(payload: dict) -> dict:
    ti = payload.get("tool_input") or payload.get("input") or payload.get("arguments") or {}
    if isinstance(ti, str):
        try:
            ti = json.loads(ti)
        except ValueError:
            ti = {"command": ti}
    return ti if isinstance(ti, dict) else {}


def _command(ti: dict) -> str:
    c = ti.get("command") or ti.get("cmd") or ""
    return " ".join(c) if isinstance(c, list) else str(c)


def _patch_paths(text: str) -> list[str]:
    return re.findall(r"^\*\*\* (?:Update|Add|Delete) File:\s*(.+?)\s*$|^\*\*\* Move to:\s*(.+?)\s*$", text or "", re.M)


def _files_of(payload: dict) -> list[str]:
    ti = _tool_input(payload)
    files = [ti.get(k) for k in ("file_path", "notebook_path", "path") if isinstance(ti.get(k), str)]
    for src in (ti.get("patch"), ti.get("input"), _command(ti)):
        if isinstance(src, str) and "*** " in src:
            files += [a or b for a, b in _patch_paths(src)]
    return files


def _is_edit(payload: dict) -> bool:
    name = str(payload.get("tool_name") or payload.get("tool") or "")
    return bool(re.search(r"Edit|Write|apply_patch|patch", name, re.I)) or "*** Begin Patch" in _command(_tool_input(payload))


def agent_pre(payload: dict | None = None) -> int:
    payload = payload if payload is not None else _read_payload()
    if _is_edit(payload):
        for f in _files_of(payload):
            rc = pre_edit({"tool_input": {"file_path": f}, "cwd": payload.get("cwd")})
            if rc:
                return rc
        return 0
    if _command(_tool_input(payload)):
        return pre_bash({"tool_input": {"command": _command(_tool_input(payload))}, "cwd": payload.get("cwd")})
    return 0


def agent_post(payload: dict | None = None) -> int:
    """Log what the agent did (shown in the report's 分析过程) and check edited files."""
    payload = payload if payload is not None else _read_payload()
    root = _repo_root(payload)
    name = str(payload.get("tool_name") or payload.get("tool") or "tool")
    ti = _tool_input(payload)
    files = [f for f in (_relpath(root, f) for f in _files_of(payload)) if f]
    if _is_edit(payload):
        text = "修改 " + "、".join(files[:4]) if files else "修改文件"
    elif re.search(r"Read|view", name, re.I):
        text = "读取 " + ("、".join(files) or "文件")
    elif re.search(r"Grep|Glob|search", name, re.I):
        text = "搜索 %s" % (ti.get("pattern") or ti.get("query") or "")
    elif _command(ti):
        text = "执行 %s" % _command(ti)[:120]
    else:
        text = name
    from . import activity
    activity.log(root, "tool", text, tool=name)
    if _is_edit(payload) and files:
        return max(post_edit({"tool_input": {"file_path": f}, "cwd": payload.get("cwd")}) for f in files)
    return 0
