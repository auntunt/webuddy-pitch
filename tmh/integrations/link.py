"""Tie ops-tool data to the project knowledge base.

- ticket  → the knowledge pack for its title/description, and a task contract that links back
- build   → stack frames and compiler errors in the log → code locations → business flows
- quality → Sonar findings grouped by the business flows whose code they sit in
- trace   → commits that mention a ticket key → files → business flows
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from ..fsutil import git
from ..graph import Graph, graph_path

JAVA_FRAME = re.compile(r"at\s+([\w$.]+)\.([\w$<>]+)\(([\w$-]+\.(?:java|kt|groovy)):(\d+)\)")
DOTNET_FRAME = re.compile(r"at\s+([\w.`<>+\[\],]+)\.([\w<>`]+)\(.*?\)\s+in\s+(.+?):line\s+(\d+)")
# javac/maven "[ERROR] /x/Foo.java:[12,5] msg", msbuild "Foo.cs(12,5): error CS0103", generic "path/File.ext:12"
COMPILE = re.compile(r"((?:[A-Za-z]:)?[\w./\\$-]+\.(?:java|cs|vb|xml|jsp|kt|groovy|sql|cshtml|aspx))(?::\[(\d+),\d+\]|\((\d+),\d+\)|:(\d+))")
ERROR_LINE = re.compile(r"(?i)(\[ERROR\]|BUILD FAILURE|FAILED|error CS\d+|error MSB\d+|Exception|Caused by:|Tests run:.*Failures: [1-9]|AssertionError|npm ERR!)")


def has_kb(root: Path) -> bool:
    return graph_path(root).exists()


class Locator:
    """Resolve log paths / class names to repository files and graph nodes."""

    def __init__(self, root: Path):
        self.root = root
        self.g = Graph(root)
        self.files = [r[0] for r in self.g.db.execute("SELECT DISTINCT file FROM nodes WHERE file != ''")]
        self.by_base = defaultdict(list)
        for f in self.files:
            self.by_base[f.rsplit("/", 1)[-1].lower()].append(f)
        self.cls_file = {r[0]: r[1] for r in self.g.db.execute("SELECT label, file FROM nodes WHERE kind='cls'")}

    def resolve(self, path: str = "", cls: str = "") -> str:
        if cls:
            outer = cls.split("$")[0]
            if outer in self.cls_file:
                return self.cls_file[outer]
        p = path.replace("\\", "/")
        base = p.rsplit("/", 1)[-1].lower()
        cands = self.by_base.get(base, [])
        if len(cands) == 1:
            return cands[0]
        best = [f for f in cands if p.endswith(f) or p.lower().endswith(f.lower())]
        if best:
            return max(best, key=len)
        # longest common suffix
        scored = sorted(cands, key=lambda f: -_suffix_len(f.lower(), p.lower()))
        return scored[0] if scored else ""

    def method_at(self, file: str, line: int) -> dict | None:
        rows = self.g.db.execute("SELECT * FROM nodes WHERE kind='fn' AND file=? AND line<=? AND end_line>=? ORDER BY (end_line-line) LIMIT 1",
                                 (file, line, line)).fetchall()
        return self.g._node(rows[0]) if rows else None

    def flows_for_fn(self, fid: str) -> list:
        return [e["src"] for e in self.g.inn(fid, "step")]

    def flows_for_file(self, file: str) -> list:
        out = []
        for r in self.g.db.execute("SELECT id FROM nodes WHERE kind='fn' AND file=?", (file,)):
            out += self.flows_for_fn(r[0])
        return list(dict.fromkeys(out))

    def flow_label(self, fid: str) -> str:
        n = self.g.node(fid)
        if not n:
            return fid
        return "%s（%s）%s" % (n["name"], n["data"].get("trigger", ""), " · 域：" + n["domain"] if n.get("domain") else "")


def _suffix_len(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


# ---------------------------------------------------------------- tickets

def ticket_brief(root: Path, issue, budget: int = 6000) -> str:
    i = issue
    out = ["# %s %s" % (i.key, i.title), ""]
    meta = [("类型", i.type), ("状态", i.status), ("优先级", i.priority), ("经办人", i.assignee), ("报告人", i.reporter), ("更新", i.updated)]
    out.append("、".join("%s：%s" % (k, v) for k, v in meta if v))
    if i.url:
        out.append("链接：" + i.url)
    if i.labels:
        out.append("标签：" + "、".join(i.labels))
    out.append("")
    if i.description:
        out += ["## 描述", i.description.strip()[:2000], ""]
    if i.links:
        out.append("## 关联工单")
        out += ["- %s %s %s" % (l.get("relation", ""), l.get("key", ""), l.get("title", "")) for l in i.links]
        out.append("")
    if i.comments:
        out.append("## 最近评论")
        out += ["- %s（%s）：%s" % (c.get("author", ""), (c.get("created") or "")[:16], (c.get("body") or "").strip().replace("\n", " ")[:300]) for c in i.comments]
        out.append("")
    if has_kb(root):
        from ..context import build_context
        q = "%s %s" % (i.title, (i.description or "")[:600])
        out.append(build_context(root, q, budget).replace("# 与“", "## 知识库：与“", 1))
    else:
        out.append("（还没有项目知识库，运行 tmh kb build 后这里会列出相关业务流、表和代码位置）")
    return "\n".join(out)


def ticket_task(root: Path, issue) -> Path:
    from ..task import new_task
    t = (issue.type or "").lower()
    kind = "bugfix" if any(w in t for w in ("bug", "缺陷", "故障", "defect", "incident")) else "feature"
    request = (issue.description or issue.title).strip()
    p = new_task(root, "%s %s" % (issue.key, issue.title), kind, request)
    text = p.read_text(encoding="utf-8")
    link = "- 工单：%s %s" % (issue.key, ("[%s](%s)" % (issue.url, issue.url)) if issue.url else "")
    text = text.replace("- 类型：", link + "\n- 类型：", 1)
    if has_kb(root):
        from ..context import build_context
        ctx = build_context(root, "%s %s" % (issue.title, (issue.description or "")[:600]), 5000)
        text = text.rstrip() + "\n\n## 附：知识库给出的相关内容（tmh context 自动生成，填第 5 节时参考）\n\n" + ctx.replace("\n#", "\n###").lstrip("# ") + "\n"
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------- builds

def parse_log(log: str) -> dict:
    frames, errors = [], []
    seen = set()
    for line in log.splitlines():
        m = JAVA_FRAME.search(line)
        if m:
            k = (m.group(3), m.group(4))
            if k not in seen:
                seen.add(k)
                frames.append({"cls": m.group(1), "method": m.group(2), "path": m.group(3), "line": int(m.group(4)), "raw": line.strip()})
            continue
        m = DOTNET_FRAME.search(line)
        if m:
            k = (m.group(3), m.group(4))
            if k not in seen:
                seen.add(k)
                frames.append({"cls": m.group(1), "method": m.group(2), "path": m.group(3), "line": int(m.group(4)), "raw": line.strip()})
            continue
        if ERROR_LINE.search(line):
            errors.append(line.strip()[:300])
            for m in COMPILE.finditer(line):
                ln = int(m.group(2) or m.group(3) or m.group(4))
                k = (m.group(1), str(ln))
                if k not in seen:
                    seen.add(k)
                    frames.append({"cls": "", "method": "", "path": m.group(1), "line": ln, "raw": line.strip()[:300]})
    return {"frames": frames, "errors": list(dict.fromkeys(errors))[:30]}


def locate_frames(root: Path, frames: list) -> list:
    if not has_kb(root):
        return []
    L = Locator(root)
    out = []
    for f in frames:
        file = L.resolve(f["path"], f["cls"])
        if not file:
            continue  # framework / JDK frame
        fn = L.method_at(file, f["line"])
        flows = L.flows_for_fn(fn["id"]) if fn else L.flows_for_file(file)
        out.append({"file": file, "line": f["line"], "method": fn["label"] if fn else "", "flows": flows,
                    "flow_labels": [L.flow_label(x) for x in flows], "raw": f["raw"]})
    return out


def failure_report(root: Path, build, log: str) -> dict:
    parsed = parse_log(log)
    located = locate_frames(root, parsed["frames"])
    flows = defaultdict(int)
    for x in located:
        for fl in x["flows"]:
            flows[fl] += 1
    labels = {}
    if located:
        L = Locator(root)
        labels = {f: L.flow_label(f) for f in flows}
    return {"build": build.to_dict() if build else None, "errors": parsed["errors"], "locations": located,
            "flows": [{"id": f, "label": labels.get(f, f), "hits": n} for f, n in sorted(flows.items(), key=lambda x: -x[1])],
            "kb": has_kb(root)}


def format_failure(r: dict) -> str:
    b = r["build"] or {}
    out = ["# 构建 %s #%s：%s" % (b.get("job", ""), b.get("number", ""), b.get("status", ""))]
    if b.get("url"):
        out.append(b["url"])
    if b.get("commit"):
        out.append("提交 %s %s" % (b["commit"][:10], b.get("branch", "")))
    out.append("")
    if r["errors"]:
        out.append("## 日志里的错误行")
        out += ["- " + e for e in r["errors"][:15]]
        out.append("")
    if r["locations"]:
        out.append("## 落在项目代码里的位置")
        for x in r["locations"][:20]:
            out.append("- %s:%d %s%s" % (x["file"], x["line"], x["method"], ("  → " + "；".join(x["flow_labels"][:3])) if x["flow_labels"] else ""))
        out.append("")
    if r["flows"]:
        out.append("## 受影响的业务流")
        out += ["- `%s` %s（%d 处）" % (f["id"], f["label"], f["hits"]) for f in r["flows"][:10]]
        out.append("")
        out.append("下一步：`tmh flows %s` 看调用链，`tmh context` 取相关知识页。" % r["flows"][0]["id"][5:])
    elif not r["kb"]:
        out.append("（还没有项目知识库，无法把错误位置对应到业务流；先运行 tmh kb build）")
    elif not r["locations"]:
        out.append("（日志里没有找到属于本项目代码的堆栈或编译错误位置）")
    return "\n".join(out)


# ---------------------------------------------------------------- quality

def quality_by_flow(root: Path, issues: list) -> dict:
    groups = defaultdict(list)
    if not has_kb(root):
        return {"(未建知识库)": [i.to_dict() for i in issues]}
    L = Locator(root)
    for i in issues:
        file = L.resolve(i.file) if i.file else ""
        flows = []
        if file and i.line:
            fn = L.method_at(file, i.line)
            flows = L.flows_for_fn(fn["id"]) if fn else []
        if not flows and file:
            flows = L.flows_for_file(file)
        d = i.to_dict()
        d["repo_file"] = file
        for f in flows or ["(不在任何业务流上)"]:
            groups[L.flow_label(f) if f.startswith("flow:") else f].append(d)
    return dict(sorted(groups.items(), key=lambda x: -len(x[1])))


# ---------------------------------------------------------------- trace

def trace(root: Path, key: str, limit: int = 50) -> dict:
    out = git(root, "log", "--all", "-i", "--grep", key, "--format=@@%H|%an|%ad|%s", "--date=short", "--name-only", "-n", str(limit)) or ""
    commits, cur = [], None
    for line in out.splitlines():
        if line.startswith("@@"):
            h, an, ad, s = (line[2:].split("|", 3) + ["", "", "", ""])[:4]
            cur = {"commit": h, "author": an, "date": ad, "subject": s, "files": []}
            commits.append(cur)
        elif line.strip() and cur is not None:
            cur["files"].append(line.strip())
    files = list(dict.fromkeys(f for c in commits for f in c["files"]))
    flows = {}
    if files and has_kb(root):
        L = Locator(root)
        for f in files:
            for fl in L.flows_for_file(f):
                flows[fl] = L.flow_label(fl)
    return {"key": key, "commits": commits, "files": files, "flows": [{"id": k, "label": v} for k, v in flows.items()], "kb": has_kb(root)}
