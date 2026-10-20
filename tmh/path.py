"""Path check: is the change actually on the path its contract's entry points take?

The failure it catches: a second implementation written next to the real one (a new service method, a new
class) that tests pass against, while the entry the user actually calls never reaches it. So:

  1. the contract's entries (section 5, 入口, backticked: Class.method, URL, flow id) must resolve to traced
     business flows;
  2. every changed hunk of product code must fall on a method or SQL statement of those flows, or in a method
     that a method on those flows calls by name;
  3. a hunk in a method no entry reaches is a break (a parallel implementation, or work outside the contract);
     a hunk the graph cannot see (front-end, configuration, reflection-dispatched code) is listed for a person (L4)
     instead of being counted either way.

Test files never count as reaching an entry: a change that only adds tests or docs fails.
"""
from __future__ import annotations

import re
from pathlib import Path

CODE_EXT = (".java", ".cs", ".vb", ".go", ".kt", ".scala")
SQL_XML = re.compile(r"<(select|insert|update|delete)\b[^>]*\bid\s*=\s*[\"']([^\"']+)", re.I)
TEST_PATH = re.compile(r"(^|/)(src/test|tests?|__tests__|spec)/|(Tests?|Spec|IT)\.(java|cs|kt)$|(_test\.go|\.spec\.[jt]sx?|\.test\.[jt]sx?)$")
DOC_EXT = (".md", ".txt", ".adoc", ".rst", ".png", ".jpg", ".svg")


def _overlap(spans, a, b) -> bool:
    return any(x <= b and y >= a for x, y in spans)


def _xml_statements(path: Path) -> list[tuple[str, int, int]]:
    """(statement id, first line, last line) of the MyBatis statements in a mapper file."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out, cur = [], None
    for i, l in enumerate(lines, 1):
        m = SQL_XML.search(l)
        if m and cur is None:
            cur = (m.group(2), i)
        if cur and re.search(r"</(select|insert|update|delete)\s*>", l, re.I):
            out.append((cur[0], cur[1], i))
            cur = None
    return out


def resolve_entries(flows: list[dict], names: list[str]) -> tuple[list[dict], list[str]]:
    hit, missing = [], []
    for n in names:
        key = n.strip()
        bare = key[5:] if key.startswith("flow:") else key
        fs = [f for f in flows if bare in (f["id"], f["handler"]) or f["handler"].endswith("." + bare)
              or (bare.startswith("/") and bare in f["trigger"].split()) or bare == f["trigger"]]
        if fs:
            hit += [f for f in fs if f not in hit]
        else:
            missing.append(key)
    return hit, missing


def path_check(root: Path, tid: str = "", entry_names: list[str] | None = None) -> dict:
    from . import acceptance, codeindex, flow as flowmod
    from .fsutil import git_changed_files, git_changed_lines
    from .verify import load_baseline, source_changes
    root = root.resolve()
    if entry_names is None:
        text = acceptance.find_contract(root, tid).read_text(encoding="utf-8")
        entry_names = acceptance.entries(text)
    res = {"ok": False, "entries": entry_names, "flows": [], "covered": [], "breaks": [], "manual": [], "problems": []}
    if not entry_names:
        res["problems"].append("契约第 5 节“入口”没有用反引号写出入口（如 `LeaveController.list` 或 `GET /leave/list`）")
        return res
    data = flowmod.build_flows(root)
    flows = data["flows"]
    mine, missing = resolve_entries(flows, entry_names)
    res["flows"] = [f["id"] for f in mine]
    for m in missing:
        res["problems"].append("入口 %s 在业务流里找不到（反射/配置分派的入口图谱看不到，请在契约里改写成可追踪的入口，或把这条 AC 标 L4）" % m)
    base = load_baseline(root)
    head = base.get("head") if base else None
    files = git_changed_files(root, head)
    if files is None:
        res["problems"].append("不在 git 仓库里，拿不到改动")
        return res
    files = source_changes(files)
    lines = git_changed_lines(root, head)

    # what the entries reach: methods (Class.method) and statements, with their spans per file
    on_path, spans = set(), {}
    for f in mine:
        for n in f["nodes"]:
            if n.get("file"):
                on_path.add(n.get("label") or "")
                spans.setdefault(n["file"], []).append((n["line"], n.get("end") or n["line"]))
    other = {}  # methods other flows reach: a hunk there is work outside the contract, not a dead branch
    for f in flows:
        if f in mine:
            continue
        for n in f["nodes"]:
            if n.get("file"):
                other.setdefault(n.get("label") or "", f["id"])
    idx = codeindex.build_index(root)
    methods = {}  # file -> [(Class.method, first, last, body)]
    for cname, cs in idx["classes"].items():
        for c in cs:
            for mname, ms in c["methods"].items():
                for mm in ms:
                    methods.setdefault(mm.get("file") or c["file"], []).append(
                        ("%s.%s" % (c["name"], mname), mm["line"], mm.get("end_line") or mm["line"], mm.get("body", "")))
    path_bodies = "\n".join(b for ms in methods.values() for (lab, _, _, b) in ms if lab in on_path)

    product = [f for f in files if not TEST_PATH.search(f) and not f.endswith(DOC_EXT)]
    for f in product:
        hunks = lines.get(f) or [(1, 10 ** 9)]
        if not (root / f).exists():
            res["manual"].append("%s 被删除：确认没有入口还依赖它" % f)
            continue
        if f.endswith(CODE_EXT):
            ms = methods.get(f, [])
            for a, b in hunks:
                inside = [m for m in ms if m[1] <= b and m[2] >= a]
                if not inside:
                    if any(m[0] in on_path for m in ms):
                        res["covered"].append("%s:%d 入口路径上的类里的声明改动" % (f, a))
                    else:
                        res["manual"].append("%s:%d 不在任何方法里（字段/常量/新类型），图谱看不到它被谁用" % (f, a))
                    continue
                for lab, s, e, _ in inside:
                    short = lab.split(".")[-1]
                    if lab in on_path:
                        res["covered"].append("%s:%d %s" % (f, a, lab))
                    elif re.search(r"\b%s\s*\(" % re.escape(short), path_bodies):
                        res["covered"].append("%s:%d %s（被入口路径上的方法按名调用；公共方法请用 tmh impact 看扇出）" % (f, a, lab))
                    elif lab in other:
                        res["breaks"].append("%s:%d %s 属于契约外的业务流 %s（改到别的业务了，或契约入口没写全）" % (f, a, lab, other[lab]))
                    else:
                        res["breaks"].append("%s:%d %s 没有任何入口调用到它（平行实现：写了但没接上）" % (f, a, lab))
        elif f.endswith(".xml") and _xml_statements(root / f):
            stm = _xml_statements(root / f)
            for a, b in hunks:
                inside = [s for s in stm if s[1] <= b and s[2] >= a]
                if not inside:
                    res["manual"].append("%s:%d 映射文件里语句之外的改动" % (f, a))
                for sid, s, e in inside:
                    if _overlap(spans.get(f, []), s, e):
                        res["covered"].append("%s:%d SQL %s" % (f, a, sid))
                    else:
                        res["breaks"].append("%s:%d SQL %s 不在契约入口的路径上" % (f, a, sid))
        else:
            res["manual"].append("%s 是图谱不追踪的文件（前端/配置/脚本），要人按 AC 在页面或环境里确认（L4）" % f)
    res["problems"] += res["breaks"]
    if not res["covered"] and not res["problems"]:
        res["problems"].append("没有一处产品代码改动落在契约入口的路径上（只改了测试/文档，或改动都没接上入口）")
    res["ok"] = not res["problems"]
    return res


def path_text(r: dict) -> str:
    out = ["# 入口路径检查：%s" % ("通过" if r["ok"] else "未通过"),
           "入口：%s → 业务流：%s" % ("、".join(r["entries"]) or "无", "、".join(r["flows"]) or "无")]
    if r["covered"]:
        out.append("\n接上入口的改动：")
        out += ["  ✅ " + x for x in r["covered"]]
    if r["problems"]:
        out.append("\n断点：")
        out += ["  ❌ " + x for x in r["problems"]]
    if r["manual"]:
        out.append("\n图谱看不到、要人确认（L4）：")
        out += ["  ⚠️ " + x for x in r["manual"]]
    return "\n".join(out)
