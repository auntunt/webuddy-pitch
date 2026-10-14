"""Baseline capture and the independent verification gate.

Principle carried over from the maintenance-delivery workbench: the agent that
writes the change must not be able to make verification pass by weakening it.
So the gate (1) refuses edits/deletions of tests and config that existed at
baseline, (2) re-scans changed files for newly introduced 信创 incompatibilities,
and (3) runs the project's own build and test commands, recording the result.
New test files are allowed and encouraged.
"""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import time
from pathlib import Path

from . import config as cfgmod
from . import scanner
from .fsutil import SKIP_DIRS, git_changed_files, git_head, iter_files, match_any, rel, sha256_file
from .report import now

BLOCKING_SEVERITIES = {"high", "medium"}
HARNESS_PATHS = (".tmh/", ".claude/", ".agents/", ".codex/", "AGENTS.md", "CLAUDE.md", ".cursor/rules/tmh-")


def source_changes(paths: list[str]) -> list[str]:
    """Drop harness files and build output (target/, bin/, obj/ … even when not git-ignored)."""
    return [c for c in paths if not c.startswith(HARNESS_PATHS) and not (set(c.split("/")[:-1]) & SKIP_DIRS)]


def fingerprint(f: dict) -> str:
    """Line numbers move when code is edited; identify a finding by rule+file+text."""
    return hashlib.sha1(("%s|%s|%s" % (f["rule"], f["file"], f["snippet"])).encode("utf-8")).hexdigest()[:16]


def detect_commands(root: Path) -> dict:
    cmds = {"build": "", "test": ""}
    if (root / "mvnw").exists():
        cmds["test"] = "./mvnw -q -B test"
    elif (root / "pom.xml").exists():
        cmds["test"] = "mvn -q -B test"
    elif (root / "gradlew").exists():
        cmds["test"] = "./gradlew test"
    elif (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        cmds["test"] = "gradle test"
    else:
        slns = sorted(root.glob("*.sln"))
        if slns:
            cmds["build"] = "dotnet build %s" % shlex.quote(slns[0].name)
            cmds["test"] = "dotnet test %s" % shlex.quote(slns[0].name)
    return cmds


def protected_files(root: Path, cfg: dict) -> dict[str, str]:
    globs = cfg.get("protected", [])
    out = {}
    for p in iter_files(root, include_binary_names=True):
        rp = rel(root, p)
        if match_any(rp, globs):
            out[rp] = sha256_file(p)
    for extra in (".tmh/config.json",):
        if (root / extra).exists() and match_any(extra, globs):
            out[extra] = sha256_file(root / extra)
    return out


def baseline_path(root: Path) -> Path:
    return cfgmod.tmh_dir(root) / "baseline.json"


def load_baseline(root: Path) -> dict | None:
    p = baseline_path(root)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def take_baseline(root: Path, run_tests: bool = False) -> dict:
    root = root.resolve()
    cfg = cfgmod.load(root)
    scan = scanner.scan_repo(root, cfg)
    base = {
        "created": now(), "created_ts": time.time(), "head": git_head(root),
        "protected": protected_files(root, cfg),
        "findings": sorted({fingerprint(f) for f in scan["findings"]}),
        "finding_count": len(scan["findings"]),
        "tests": None,
    }
    if run_tests:
        base["tests"] = run_commands(root, cfg)
    p = baseline_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(base, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return base


def run_commands(root: Path, cfg: dict, timeout: int = 3600) -> list[dict]:
    cmds = dict(detect_commands(root))
    for k in ("build", "test"):
        if cfg.get("commands", {}).get(k):
            cmds[k] = cfg["commands"][k]
    seq = [(k, cmds[k]) for k in ("build", "test") if cmds.get(k)]
    seq += [("check", c) for c in cfg.get("commands", {}).get("extra_checks", [])]
    results = []
    for kind, cmd in seq:
        t0 = time.time()
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True, text=True, timeout=timeout, errors="replace")
            code, outp = r.returncode, (r.stdout + "\n" + r.stderr)
        except subprocess.TimeoutExpired:
            code, outp = -1, "超时 (%ds)" % timeout
        results.append({"kind": kind, "command": cmd, "exit_code": code, "seconds": round(time.time() - t0, 1),
                        "tail": "\n".join(outp.strip().splitlines()[-40:])})
    return results


def check_protected(root: Path, cfg: dict, base: dict) -> list[dict]:
    if cfg.get("allow_protected_edits"):
        return []
    problems = []
    for rp, h in base.get("protected", {}).items():
        p = root / rp
        if not p.exists():
            problems.append({"file": rp, "problem": "基线中的受保护文件被删除"})
        elif sha256_file(p) != h:
            problems.append({"file": rp, "problem": "基线中的受保护文件被修改"})
    return problems


def new_findings(root: Path, cfg: dict, base: dict | None, changed: list[str] | None) -> list[dict]:
    if changed is not None:
        scan = scanner.scan_repo(root, cfg, only_files=changed)
    else:
        scan = scanner.scan_repo(root, cfg)
    known = set(base.get("findings", [])) if base else set()
    return [f for f in scan["findings"] if f["severity"] in BLOCKING_SEVERITIES and fingerprint(f) not in known]


def verify(root: Path, run_tests: bool = True, timeout: int = 3600) -> dict:
    root = root.resolve()
    cfg = cfgmod.load(root)
    base = load_baseline(root)
    changed = git_changed_files(root, base.get("head") if base else None)
    if changed is not None:
        changed = source_changes(changed)
    result = {
        "time": now(), "head": git_head(root), "baseline_head": base.get("head") if base else None,
        "changed_files": changed, "protected_violations": check_protected(root, cfg, base) if base else [],
        "new_findings": new_findings(root, cfg, base, changed), "commands": [], "notes": [],
    }
    if changed:
        from .fsutil import git_changed_lines
        cl = git_changed_lines(root, base.get("head") if base else None)
        result["changed_lines"] = {f: cl[f] for f in changed if f in cl}
    if base is None:
        result["notes"].append("没有基线：受保护文件检查跳过，扫描回归按全量计算。先运行 tmh baseline。")
    if changed is None:
        result["notes"].append("不在 git 仓库中，无法得到改动文件列表。")
    if run_tests:
        result["commands"] = run_commands(root, cfg, timeout)
        if not result["commands"]:
            result["notes"].append("没有识别到构建/测试命令，请在 .tmh/config.json 的 commands 中配置。")
    failed_cmds = [c for c in result["commands"] if c["exit_code"] != 0]
    result["passed"] = not result["protected_violations"] and not result["new_findings"] and not failed_cmds
    result["tests_ran"] = bool(result["commands"])
    _write_report(root, result)
    return result


def _write_report(root: Path, r: dict) -> None:
    d = cfgmod.tmh_dir(root) / "reports"
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    (d / ("verify-%s.json" % stamp)).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "verify-latest.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    md = verify_md(r)
    (d / ("verify-%s.md" % stamp)).write_text(md, encoding="utf-8")


def verify_md(r: dict) -> str:
    out = ["# 验证结果：%s\n" % ("通过" if r["passed"] else "未通过"),
           "时间 %s · 当前提交 `%s` · 基线 `%s`\n" % (r["time"], (r["head"] or "-")[:12], (r["baseline_head"] or "-")[:12])]
    if r["changed_files"] is not None:
        out.append("改动文件 %d 个。\n" % len(r["changed_files"]))
    out.append("## 受保护文件\n")
    out.extend(["- ❌ `%s` %s" % (p["file"], p["problem"]) for p in r["protected_violations"]] or ["- ✅ 未改动基线测试与配置"])
    out.append("\n## 新引入的信创不兼容点\n")
    out.extend(["- ❌ `%s:%d` %s %s — `%s`" % (f["file"], f["line"], f["rule"], f["title"], f["snippet"][:100]) for f in r["new_findings"]] or ["- ✅ 无"])
    out.append("\n## 构建与测试\n")
    if not r["commands"]:
        out.append("- ⚠️ 未运行")
    for c in r["commands"]:
        out.append("- %s `%s` 退出码 %s，%.1fs" % ("✅" if c["exit_code"] == 0 else "❌", c["command"], c["exit_code"], c["seconds"]))
        if c["exit_code"] != 0:
            out.append("\n```\n%s\n```" % c["tail"])
    if r["notes"]:
        out.append("\n## 说明\n")
        out.extend("- " + n for n in r["notes"])
    return "\n".join(out) + "\n"
