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
import uuid
import os
from xml.etree.ElementTree import ParseError
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
    if os.name == "nt" and (root / "mvnw.cmd").exists():
        cmds["test"] = r".\mvnw.cmd -q -B test"
    elif os.name == "nt" and (root / "gradlew.bat").exists():
        cmds["test"] = r".\gradlew.bat test"
    elif os.name != "nt" and (root / "mvnw").exists():
        cmds["test"] = "./mvnw -q -B test"
    elif (root / "pom.xml").exists():
        cmds["test"] = "mvn -q -B test"
    elif os.name != "nt" and (root / "gradlew").exists():
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
        report_spec = cfg.get("commands", {}).get("test_report") if kind == "test" else None
        report_path = None
        if report_spec:
            report_path = (root / report_spec["path"]).resolve()
            if not (root / ".tmh" / "test-output").resolve().is_relative_to(root) or not report_path.is_relative_to((root / ".tmh" / "test-output").resolve()):
                raise ValueError("CLI 用例报告必须放在 .tmh/test-output 下")
            if report_spec["format"] not in ("json", "junit"):
                raise ValueError("CLI 用例报告格式必须为 json 或 junit")
            # Move stale output aside; never let a successful no-op reuse it.
            if report_path.exists():
                archive = cfgmod.tmh_dir(root) / "reports" / ("previous-" + uuid.uuid4().hex)
                archive.parent.mkdir(parents=True, exist_ok=True)
                report_path.replace(archive)
        t0 = time.time()
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(root), capture_output=True, text=True, timeout=timeout, errors="replace")
            code, outp = r.returncode, (r.stdout + "\n" + r.stderr)
        except subprocess.TimeoutExpired as exc:
            def decoded(value):
                return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
            code, outp = -1, decoded(exc.stdout) + "\n" + decoded(exc.stderr) + "\n超时 (%ds)" % timeout
        results.append({"kind": kind, "command": cmd, "exit_code": code, "seconds": round(time.time() - t0, 1),
                        "output": outp, "tail": "\n".join(outp.strip().splitlines()[-40:])})
        if report_path:
            from .platform.project_tests import cases
            try:
                raw = report_path.read_bytes()
                artifact = cfgmod.tmh_dir(root) / "reports" / ("cases-" + uuid.uuid4().hex + "." + ("xml" if report_spec["format"] == "junit" else "json"))
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(raw)
                results[-1].update(cases=cases(raw, report_spec["format"]), artifact=artifact.relative_to(root).as_posix(), artifact_sha256=sha256_file(artifact))
                if any(c["status"] != "pass" for c in results[-1]["cases"]):
                    results[-1]["evidence_error"] = "报告含失败或跳过用例"
            except (OSError, ValueError, ParseError) as exc:
                results[-1]["evidence_error"] = str(exc)
                results[-1]["verification_state"] = "blocked"
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


def evidence_identity(root: Path, task: str = "") -> dict:
    """Bind verification to source bytes, configuration and the effective contract."""
    from .acceptance import find_contract, ac_rows, _tid
    from .fsutil import git
    tracked = git(root, "ls-files", "-z")
    others = git(root, "ls-files", "--others", "--exclude-standard", "-z")
    paths = set((tracked or "").split("\0")) | set(source_changes((others or "").split("\0")))
    files = {}
    for name in sorted(paths):
        if not name or name.startswith(HARNESS_PATHS):
            continue
        path = root / name
        if path.is_symlink():
            files[name] = ["symlink", os.readlink(path)]
        elif path.is_file():
            files[name] = [sha256_file(path), bool(path.stat().st_mode & 0o111)]
        else:
            files[name] = None
    contract = None
    if task:
        path = find_contract(root, task)
        task = _tid(path)
        text = path.read_text(encoding="utf-8")
        # Status and observed results are presentation; requirements and checks are inputs.
        import re
        text = re.sub(r"^- 验收状态：.*$", "", text, flags=re.M)
        rows = ac_rows(text)
        section = re.search(r"^## 4\..*?$(.*?)(?=^## \d+\.|\Z)", text, re.M | re.S)
        if section:
            text = text[:section.start(1)] + json.dumps([{k:v for k,v in r.items() if k != "result"} for r in rows], ensure_ascii=False) + text[section.end(1):]
        contract = hashlib.sha256(text.encode()).hexdigest()
    payload = {"files": files, "config": cfgmod.load(root), "baseline": load_baseline(root), "contract": contract}
    return {"task": task, "head": git_head(root), "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}


def current_report(root: Path, task: str, report: dict) -> bool:
    import re
    if not re.fullmatch(r"[0-9a-f]{32}", report.get("id", "")) or report.get("report") != ".tmh/reports/verify-" + report["id"] + ".json":
        return False
    original = root / report["report"]
    try:
        if json.loads(original.read_text(encoding="utf-8")) != report:
            return False
    except (OSError, ValueError):
        return False
    for command in report.get("commands", []):
        if command.get("artifact"):
            artifact = (root / command["artifact"]).resolve()
            if not artifact.is_relative_to((cfgmod.tmh_dir(root) / "reports").resolve()) or not artifact.is_file() or sha256_file(artifact) != command.get("artifact_sha256"):
                return False
    return bool(report.get("passed") and report.get("tests_ran") and report.get("identity") == evidence_identity(root, task))


def verify(root: Path, run_tests: bool = True, timeout: int = 3600, task: str = "") -> dict:
    root = root.resolve()
    cfg = cfgmod.load(root)
    base = load_baseline(root)
    identity = evidence_identity(root, task)
    changed = git_changed_files(root, base.get("head") if base else None)
    if changed is not None:
        changed = source_changes(changed)
    result = {
        "id": uuid.uuid4().hex, "identity": identity, "task": identity["task"],
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
    if task:  # the change must be on the path of the contract's entries (path.py)
        from .acceptance import Refused
        from .path import path_check
        try:
            result["path_check"] = dict(path_check(root, task), task=task)
        except (Refused, OSError) as e:
            result["path_check"] = {"ok": False, "task": task, "entries": [], "flows": [], "covered": [], "manual": [], "problems": [str(e)]}
    failed_cmds = [c for c in result["commands"] if c["exit_code"] != 0 or c.get("evidence_error")]
    result["static_passed"] = not result["protected_violations"] and not result["new_findings"] \
        and (result.get("path_check") or {"ok": True})["ok"]
    result["tests_ran"] = any(c["kind"] == "test" for c in result["commands"])
    result["code_changed"] = identity != evidence_identity(root, task)
    result["passed"] = bool(base and identity["head"] and result["static_passed"] and not failed_cmds and result["tests_ran"] and not result["code_changed"])
    result["outcome"] = "blocked" if not base or not identity["head"] or not result["tests_ran"] or result["code_changed"] or any(c.get("verification_state") == "blocked" or c["exit_code"] in (-1, 126, 127) for c in result["commands"]) else "review_required" if result["passed"] else "repair_required"
    if result["code_changed"]:
        result["notes"].append("执行期间代码或验证契约变化，报告不能支持当前候选。")
    if not result["tests_ran"]:
        result["notes"].append("测试未执行；静态检查或构建成功不代表完整验证通过。")
    proofs = {}
    for criterion, ids in cfg.get("commands", {}).get("criteria", {}).items():
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) for i in ids):
            raise ValueError("验收项用例关联必须是非空用例 ID 数组")
        command = next((c for c in result["commands"] if c["kind"] == "test"), {})
        indexed = {c["id"]: c["status"] for c in command.get("cases", [])}
        proofs[criterion] = {"status": "pass" if result["passed"] and all(indexed.get(i) == "pass" for i in ids) else "unverified", "cases": ids, "artifact": command.get("artifact")}
    result["criterion_evidence"] = proofs
    _write_report(root, result)
    return result


def _write_report(root: Path, r: dict) -> None:
    d = cfgmod.tmh_dir(root) / "reports"
    d.mkdir(parents=True, exist_ok=True)
    stamp = r["id"]
    r["report"] = ".tmh/reports/verify-%s.json" % stamp
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
    out.extend(["- ❌ `%s` %s" % (p["file"], p["problem"]) for p in r["protected_violations"]] or (["- ✅ 未改动基线测试与配置"] if r["baseline_head"] else ["- 未建立基线，未执行此检查"]))
    out.append("\n## 新引入的信创不兼容点\n")
    out.extend(["- ❌ `%s:%d` %s %s — `%s`" % (f["file"], f["line"], f["rule"], f["title"], f["snippet"][:100]) for f in r["new_findings"]] or ["- ✅ 无"])
    out.append("\n## 构建与测试\n")
    if not r["commands"]:
        out.append("- ⚠️ 未运行")
    for c in r["commands"]:
        out.append("- %s `%s` 退出码 %s，%.1fs" % ("✅" if c["exit_code"] == 0 else "❌", c["command"], c["exit_code"], c["seconds"]))
        if c["exit_code"] != 0:
            out.append("\n```\n%s\n```" % c["tail"])
    if r.get("path_check"):
        from .path import path_text
        out.append("\n## 入口路径（任务 %s）\n" % r["path_check"]["task"])
        out.append(path_text(r["path_check"]).split("\n", 1)[-1])
    if r["notes"]:
        out.append("\n## 说明\n")
        out.extend("- " + n for n in r["notes"])
    return "\n".join(out) + "\n"
