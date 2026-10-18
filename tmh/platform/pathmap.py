"""Candidate-bound Python method reachability, never a claim of business correctness.

Read Git objects into a disposable analysis directory. Do not execute/import the
project and do not use the checkout's graph to explain another version's diff.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath

from . import gates

SCHEMA = 1
SCOPE = "Python HTTP dispatcher 整方法的静态调用关联；不是某条 URL 的运行轨迹或业务验收。"
LIMITS = ["同一 HTTP 方法中的不同 URL/条件分支可能走不同路径；此处不证明具体请求经过修改行。",
          "动态调用、反射、运行时注册和外部依赖不能凭静态索引确认。",
          "代码关联、实际测试、人工复核与客户签收是独立证据。"]


def _hash(value):
    raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _git(root, *args):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    if p.returncode:
        raise ValueError(p.stderr.decode("utf-8", "replace").strip() or "无法读取 Git 对象")
    return p.stdout


def _object(root, prefix, kind):
    """An adoption hash is an object identity, never a potentially shadowing ref."""
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", prefix or ""):
        raise ValueError("没有有效的 Git 对象标识")
    matches = _git(root, "rev-parse", "--disambiguate=" + prefix.lower()).decode().splitlines()
    if len(matches) != 1 or _git(root, "cat-file", "-t", matches[0]).decode().strip() != kind:
        raise ValueError("Git 对象不存在、不唯一或类型不匹配；不能按同名分支猜测")
    return matches[0]


def _diff(diff):
    """Preserve every changed line; unsupported paths/hunks remain unknown."""
    files, cur, line, oldline = [], None, None, None
    for raw in diff.splitlines():
        if raw.startswith("diff --git "):
            m = re.fullmatch(r"diff --git a/(\S+) b/(\S+)", raw)
            cur = {"file": m[2] if m else raw, "lines": [], "added": [], "old_lines": [], "removed": [],
                   "blob": "", "old_blob": "", "malformed": not bool(m)}
            files.append(cur); line = oldline = None
        elif cur is None:
            continue
        elif raw.startswith("index "):
            m = re.match(r"index ([0-9a-f]+)\.\.([0-9a-f]+)", raw)
            if m:
                cur["old_blob"], cur["blob"] = m[1], m[2]
        elif raw.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            oldline, line = (int(m[1]), int(m[2])) if m else (None, None)
            if not m:
                cur["malformed"] = True
        elif raw.startswith("+") and not raw.startswith("+++"):
            if line is None:
                cur["malformed"] = True
            else:
                cur["lines"].append(line); cur["added"].append(raw[1:]); line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            if oldline is None:
                cur["malformed"] = True
            else:
                cur["old_lines"].append(oldline); cur["removed"].append(raw[1:]); oldline += 1
        elif line is not None and raw.startswith(" "):
            line += 1; oldline += 1
    return files


def for_change(project: dict, fix: dict, commit: str = "") -> dict:
    diff = fix.get("diff") or ""
    result = {"schema": SCHEMA, "source": {"commit": "", "diff_sha256": _hash(diff.encode()), "blobs": {}},
              "scope": SCOPE, "limitations": list(LIMITS), "diagnostics": [], "changes": [], "flows": [],
              "suggested": [], "selected": [], "status": "unknown", "can_record": False, "why": "尚无可核对的候选代码"}
    try:
        ref = commit or ((fix.get("decision") or "").rsplit("@", 1)[-1] if (fix.get("decision") or "").startswith("accepted:") else "")
        if not re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
            raise ValueError("没有已采纳的确定提交；不能使用当前工作目录替代候选版本")
        root = Path(project["root"])
        sha = _object(root, ref, "commit")
        result["source"]["commit"] = sha
        tree = {}
        for item in _git(root, "ls-tree", "-rz", sha).split(b"\0"):
            if not item:
                continue
            head, rawpath = item.split(b"\t", 1); mode, kind, blob = head.decode().split()
            path = rawpath.decode("utf-8", "strict")
            if kind == "blob" and path.endswith(".py"):
                tree[path] = (mode, blob)
        from ..codeindex import build_index
        from ..flow import build_flows
        with tempfile.TemporaryDirectory(prefix="tmh-python-map-") as td:
            target = Path(td); texts = {}
            for name, (mode, blob) in tree.items():
                path = PurePosixPath(name)
                if mode not in ("100644", "100755") or path.is_absolute() or ".." in path.parts:
                    result["diagnostics"].append({"file": name, "line": 0, "message": "非普通源文件，未解析", "status": "unknown"})
                    continue
                raw = _git(root, "cat-file", "blob", blob)
                dest = target / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
                result["source"]["blobs"][name] = {"git_blob": blob, "sha256": _hash(raw)}
                try:
                    import tokenize, io
                    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                    texts[name] = raw.decode(encoding).splitlines()
                except (SyntaxError, UnicodeError):
                    result["diagnostics"].append({"file": name, "line": 0, "message": "源文件编码无法解析", "status": "unknown"})
            idx = build_index(target)
            mapped = build_flows(target, index=idx)
            result["diagnostics"] += list(idx.get("diagnostics") or [])
            result["diagnostics"] += [d for d in mapped.get("diagnostics", []) if d not in result["diagnostics"]]
            spans = []
            for classes in idx["classes"].values():
                for cls in classes:
                    if cls.get("lang") not in ("python", "py"):
                        continue
                    for name, methods in cls["methods"].items():
                        for method in methods:
                            spans.append({"key": cls["name"] + "." + name, "file": method["file"],
                                          "line": method["line"], "end_line": method.get("end_line", method["line"])})
            for flow in mapped["flows"]:
                if not flow["file"].endswith(".py"):
                    continue
                result["flows"].append({**flow, "id": "flow:" + flow["id"]})
            for change in _diff(diff):
                name = change["file"]
                if gates.TEST_FILE.search(name) or name.endswith((".md", ".txt", ".png", ".jpg")):
                    continue
                row = {"file": name, "lines": change["lines"], "removed_lines": change["old_lines"],
                       "functions": [], "flow_ids": [], "status": "unknown", "why": ""}
                result["changes"].append(row)
                blob = result["source"]["blobs"].get(name, {}).get("git_blob", "")
                if not name.endswith(".py"):
                    row["why"] = "此检查只覆盖 Python；其他产品改动仍需独立路径证据"; continue
                if change["malformed"] or not change["blob"] or not blob.startswith(change["blob"]) or not texts.get(name):
                    row["why"] = "差异的文件版本与候选 Git 对象不匹配或无法解析"; continue
                if not change["lines"] and not change["old_lines"]:
                    row["why"] = "没有可核对的改动行"; continue
                if any(n > len(texts[name]) or n < 1 or texts[name][n - 1] != text for n, text in zip(change["lines"], change["added"])):
                    row["why"] = "差异内容/行号与候选源码不一致"; continue
                old_spans = []
                if change["old_lines"]:
                    try:
                        from ..python_index import parse as parse_python
                        old_blob = _object(root, change["old_blob"], "blob")
                        old_raw = _git(root, "cat-file", "blob", old_blob)
                        encoding, _ = tokenize.detect_encoding(io.BytesIO(old_raw).readline)
                        old_text = old_raw.decode(encoding); old_text_lines = old_text.splitlines()
                        if any(n > len(old_text_lines) or n < 1 or old_text_lines[n - 1] != text for n, text in zip(change["old_lines"], change["removed"])):
                            raise ValueError("删除行与原始 Git blob 不一致")
                        parsed = parse_python(name, old_text)
                        if parsed.get("diagnostics"):
                            raise ValueError("旧版源文件无法解析")
                        row["old_blob_sha256"] = _hash(old_raw)
                        row["old_blob"] = old_blob
                        for cls in parsed["classes"]:
                            for method_name, methods in cls["methods"].items():
                                for method in methods:
                                    old_spans.append({"key": cls["name"] + "." + method_name, "file": name,
                                                      "line": method["line"], "end_line": method.get("end_line", method["line"])})
                    except (OSError, ValueError, SyntaxError, UnicodeError) as error:
                        row["why"] = "删除位置缺少可靠的旧版函数证据：" + str(error); continue
                missing = False; per_line_flows = []
                positions = [(n, spans, "new") for n in change["lines"]] + [(n, old_spans, "old") for n in change["old_lines"]]
                for n, candidates, side in positions:
                    owners = [s for s in candidates if s["file"] == name and s["line"] <= n <= s["end_line"]]
                    if not owners:
                        missing = True; continue
                    # The innermost function wins. A containing factory is not evidence
                    # that every nested/unreferenced function can be entered.
                    width = min(s["end_line"] - s["line"] for s in owners)
                    owners = [s for s in owners if s["end_line"] - s["line"] == width]
                    if len(owners) != 1:
                        missing = True; continue
                    key = owners[0]["key"]
                    if key not in row["functions"]:
                        row["functions"].append(key)
                    ids = [f["id"] for f in result["flows"] if any(node["key"] == key for node in f["nodes"])]
                    per_line_flows.append({"line": n, "side": side, "function": key, "flow_ids": ids})
                    if not ids:
                        missing = True
                    row["flow_ids"] = sorted(set(row["flow_ids"] + ids))
                row["locations"] = per_line_flows
                if not missing and per_line_flows:
                    row.update(status="mapped", why="改动所在函数可从列出的 HTTP 方法入口静态到达；尚未证明具体请求行为")
                else:
                    row["why"] = "部分改动没有可解析的入口调用关系；未将同文件或外层函数范围算作覆盖"
            found = [c for c in result["changes"] if c["status"] == "mapped"]
            result["status"] = "mapped" if found and len(found) == len(result["changes"]) and not result["diagnostics"] else "partial" if found else "unknown"
            result["suggested"] = sorted({fid for c in found for fid in c["flow_ids"]})
            result["can_record"] = bool(found)
            result["why"] = "已定位候选版本中的静态函数关联" if result["status"] == "mapped" else "存在未解析或未关联的改动，不能据此通过路径检查"
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        result["diagnostics"].append({"file": "", "line": 0, "status": "unknown", "message": str(error)})
        result["why"] = str(error)
    result["digest"] = _hash(result)
    return result


def for_ticket(P, ticket):
    from .delivery import signoff_binding
    p = P.store.project(ticket["project_id"])
    binding = signoff_binding(P.data_dir, ticket["key"])
    runs = [P.store.run(r["id"]) for r in P.store.runs(ticket_id=ticket["id"]) if r["mode"] == "fix"]
    fix = next((r for r in runs if r["id"] == binding.get("fix_run")), None) if binding is not None else next(
        (r for r in runs if (r.get("decision") or "").startswith("accepted")), None)
    result = for_change(p, fix or {}, (binding or {}).get("commit", ""))
    recorded = (ticket.get("links") or {}).get("code_path")
    selected = recorded.get("flows", []) if recorded else (ticket.get("links") or {}).get("flows", [])
    result["selected"] = [f for f in selected if f in {x["id"] for x in result["flows"]}]
    if recorded and (recorded.get("commit") != result["source"]["commit"] or recorded.get("digest") != result["digest"]):
        result["why"] = "候选版本或差异已变化，原代码关联已过期；请核对当前结果后重新记录"
        result["recorded_current"] = False
    else:
        result["recorded_current"] = bool(recorded)
    return result


def path_result(mapping, selected):
    selected = set(selected or [])
    changes = mapping["changes"]
    covered = [c["file"] for c in changes if c["status"] == "mapped" and c.get("locations") and
               all(selected.intersection(loc["flow_ids"]) for loc in c["locations"])]
    unknown = [c["file"] for c in changes if c["file"] not in covered]
    ok = bool(changes) and not unknown and mapping["status"] == "mapped"
    return {"ok": ok, "covered": covered, "off": [], "manual": unknown, "basis": "python-static-functions",
            "source": mapping["source"], "mapping_digest": mapping["digest"], "changes": changes,
            "diagnostics": mapping["diagnostics"], "limitations": mapping["limitations"],
            "why": "候选版本的改动函数可从已关联 HTTP 方法入口静态到达；不代表具体 URL 或业务测试通过" if ok else
                   "候选版本尚有未关联或未解析的代码路径；记录关联后仍需实际业务测试"}
