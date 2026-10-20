"""信创 compatibility scanner: a deterministic, explainable rule engine.

Rules live in tmh/rules/*.json (and optionally <repo>/.tmh/rules/*.json for
project-specific additions). Every finding carries file:line evidence so an agent
or a reviewer can open the exact spot instead of trusting a summary.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import config as cfgmod
from .fsutil import is_text_candidate, iter_files, match_any, read_text, rel

RULE_DIR = Path(__file__).parent / "rules"
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
MAX_HITS_PER_RULE_FILE = 20
COMMENT_LINE = re.compile(r"^\s*(//|/\*|\*|--|'|<!--)")
BINARY_SUFFIXES = {".dll", ".so", ".dylib", ".exe", ".ocx"}
CODE_SUFFIXES = (".java", ".cs", ".vb", ".js", ".ts")


def load_rules(root: Path | None = None) -> list[dict]:
    rules: list[dict] = []
    dirs = [RULE_DIR]
    if root is not None:
        dirs.append(cfgmod.tmh_dir(root) / "rules")
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            for r in json.loads(f.read_text(encoding="utf-8")):
                flags = re.I if "i" in r.get("flags", "") else 0
                r["_res"] = [re.compile(p, flags) for p in r.get("patterns", [])]
                r["_path_res"] = [re.compile(p, re.I) for p in r.get("path_patterns", [])]
                rules.append(r)
    return rules


def _condition_holds(cond: str, cfg: dict) -> bool:
    m = re.match(r"^\s*([\w.]+)\s+(not\s+in|in)\s+([\w,\-]+)\s*$", cond)
    if not m:
        raise ValueError("bad rule condition: " + cond)
    key, op, values = m.group(1), m.group(2), set(m.group(3).split(","))
    actual = cfgmod.lookup(cfg, key)
    if key.endswith(".os") and actual in {"kylin", "uos", "openeuler"}:
        actual_set = {actual, "linux"}
    else:
        actual_set = {actual}
    hit = bool(actual_set & values)
    return hit if op == "in" else not hit


def active_rules(rules: list[dict], cfg: dict) -> list[dict]:
    disabled = set(cfg.get("scan", {}).get("disabled_rules", []))
    out = []
    for r in rules:
        if r["id"] in disabled:
            continue
        if all(_condition_holds(c, cfg) for c in r.get("requires", [])):
            out.append(r)
    return out


def effective_severity(rule: dict, cfg: dict) -> str:
    for key, table in rule.get("severity_by", {}).items():
        v = cfgmod.lookup(cfg, key)
        if v in table:
            return table[v]
    return rule["severity"]


def scan_text(path: str, text: str, rules: list[dict], cfg: dict) -> list[dict]:
    findings: list[dict] = []
    lines = text.splitlines()
    is_code = path.endswith(CODE_SUFFIXES)
    for r in rules:
        if r["_path_res"] and any(p.search(path) for p in r["_path_res"]):
            findings.append(_finding(r, cfg, path, 0, "(文件本身即为相关产物)"))
        if not r["_res"] or not match_any(path, r.get("files", ["*"])):
            continue
        hits = 0
        for i, line in enumerate(lines, 1):
            if is_code and COMMENT_LINE.match(line):
                continue
            for rx in r["_res"]:
                if rx.search(line):
                    findings.append(_finding(r, cfg, path, i, line.strip()[:200]))
                    hits += 1
                    break
            if hits >= MAX_HITS_PER_RULE_FILE:
                break
    return findings


def _finding(r: dict, cfg: dict, path: str, line: int, snippet: str) -> dict:
    return {
        "rule": r["id"], "category": r["category"], "severity": effective_severity(r, cfg),
        "title": r["title"], "file": path, "line": line, "snippet": snippet,
        "advice": r.get("advice", ""), "kb": r.get("kb", ""), "effort": r.get("effort", "M"),
    }


def scan_repo(root: Path, cfg: dict | None = None, only_files: list[str] | None = None) -> dict:
    root = root.resolve()
    cfg = cfg or cfgmod.load(root)
    rules = active_rules(load_rules(root), cfg)
    excludes = cfg.get("scan", {}).get("exclude", [])
    findings: list[dict] = []
    scanned = 0
    skipped: list[str] = []
    if only_files is not None:
        paths = [root / f for f in only_files if (root / f).is_file()]
    else:
        paths = [p for p in iter_files(root, include_binary_names=True)
                 if is_text_candidate(p) or p.suffix.lower() in BINARY_SUFFIXES]
    for p in paths:
        rp = rel(root, p)
        if match_any(rp, excludes):
            continue
        # Binary artefacts (.dll/.so) can only be matched by path rules.
        text = read_text(p) if p.suffix.lower() not in BINARY_SUFFIXES else ""
        if text is None:
            skipped.append(rp)
            continue
        scanned += 1
        findings.extend(scan_text(rp, text, rules, cfg))
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["category"], f["rule"], f["file"], f["line"]))
    return {
        "root": str(root), "files_scanned": scanned, "files_skipped": skipped[:200],
        "rules_active": [r["id"] for r in rules], "findings": findings, "summary": summarise(findings),
    }


def summarise(findings: list[dict]) -> dict:
    by_rule: dict[str, dict] = {}
    files_by_rule: dict[str, set] = defaultdict(set)
    for f in findings:
        e = by_rule.setdefault(f["rule"], {"rule": f["rule"], "title": f["title"], "category": f["category"],
                                           "severity": f["severity"], "effort": f["effort"], "kb": f["kb"],
                                           "advice": f["advice"], "hits": 0})
        e["hits"] += 1
        files_by_rule[f["rule"]].add(f["file"])
    for k, e in by_rule.items():
        e["files"] = len(files_by_rule[k])
    return {
        "by_severity": dict(Counter(f["severity"] for f in findings)),
        "by_category": dict(Counter(f["category"] for f in findings)),
        "by_rule": sorted(by_rule.values(), key=lambda e: (SEVERITY_ORDER.get(e["severity"], 9), -e["hits"])),
    }
