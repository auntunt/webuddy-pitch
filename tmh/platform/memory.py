"""Knowledge and long-term memory workspace.

Read models never start models, change tickets, or opt a project into foreign
memory. Derived groups and handover documents keep their inputs and revisions;
the existing learn module remains the sole lesson/adoption/execution ledger.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
import threading
import uuid
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

from . import filelock, learn, org_knowledge, project_library
from .errors import ApiError
from .store import now

SCHEMA = 1
_LOCK = threading.RLock()
_GENERIC = {"问题", "功能", "系统", "异常", "报错", "修复", "优化", "处理", "需求", "出现", "进行", "用户", "无法", "需要", "验证"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _project(P, key):
    p = P.store.project(key) if isinstance(key, (str, int)) and str(key).strip() else None
    if not p:
        raise ApiError(404, "请选择存在的项目")
    return p


def _path(P, p):
    return Path(P.data_dir) / "memory" / (str(p["id"]) + ".json")


def _load(P, p):
    path = _path(P, p)
    if not path.exists():
        return {"schema": SCHEMA, "project_id": p["id"], "clusters": [], "briefs": []}
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("schema") != SCHEMA or result.get("project_id") != p["id"]:
            raise ValueError("版本或项目不符")
        return result
    except (ValueError, OSError) as exc:
        raise ApiError(409, "记忆文件不可读，原文件保留：" + str(exc)) from exc


@contextmanager
def _write(P, p):
    """Serialize across processes; replace only a fully written new document."""
    path = _path(P, p)
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.with_suffix(".lock").open("a+b") as lock:
            filelock.try_lock(lock, blocking=True)
            try:
                state = _load(P, p)
                yield state
                temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
                try:
                    with temp.open("w", encoding="utf-8") as stream:
                        json.dump(state, stream, ensure_ascii=False, indent=2)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp, path)
                finally:
                    temp.unlink(missing_ok=True)
            finally:
                filelock.unlock(lock)


def _tickets(P, p):
    # Store's default is a display limit. Here the derived artifact must account
    # for every input and never silently drop older tickets.
    n = P.store.one("SELECT COUNT(*) n FROM tickets WHERE project_id=?", (p["id"],))["n"]
    return sorted(P.store.tickets(project_id=p["id"], limit=max(1, n)), key=lambda t: t["id"])


def _features(t):
    text = t["title"] + "\n" + learn.own_words(t.get("body") or "")
    links = t.get("links") or {}
    files = links.get("files") or []
    files = list(files) if isinstance(files, list) else []
    files += re.findall(r"(?:[\w.-]+/)+[\w.-]+\.(?:java|cs|py|js|ts|tsx|sql|xml)", text)
    errors = re.findall(r"\b[A-Za-z][\w.$]*(?:Exception|Error)\b|\b(?:ORA-\d+|SQLSTATE\s*[:=]?\s*[A-Z0-9]{5}|HTTP\s+[45]\d\d)\b", text)
    return {"flows": set(links.get("flows") or []), "files": set(files), "errors": set(errors),
            "words": learn._grams(text) - _GENERIC,
            "title": re.sub(r"\W", "", t["title"].lower()),
            "kind": "reform" if links.get("reform") else t.get("type", "bug")}


def _similar(a, b, fa=None, fb=None):
    fa, fb = fa or _features(a), fb or _features(b)
    if a["project_id"] != b["project_id"] or fa["kind"] != fb["kind"]:
        return None
    common = fa["words"] & fb["words"]
    similarity = len(common) / max(1, len(fa["words"] | fb["words"]))
    flows, files, errors = (fa[k] & fb[k] for k in ("flows", "files", "errors"))
    same_title = fa["title"] == fb["title"] and len(fa["title"]) >= 10 and len(common) >= 5
    if not ((flows or files or errors) and len(common) >= 3 and similarity >= .28 or same_title and similarity >= .65):
        return None
    reasons = []
    if flows:
        reasons.append("关联相同业务流：" + "、".join(sorted(flows)))
    if files:
        reasons.append("涉及相同文件：" + "、".join(sorted(files)))
    if errors:
        reasons.append("包含相同异常特征：" + "、".join(sorted(errors)))
    if same_title:
        reasons.append("具体问题标题相同")
    reasons.append("描述词重合 %.0f%%" % (similarity * 100))
    return {"score": round(similarity, 3), "reasons": reasons, "same_cause_confirmed": False}


def similar_tickets(P, ticket, limit=5):
    """Read-only recommendations for a ticket page, preserving original links."""
    t = P.store.ticket(ticket) if not isinstance(ticket, dict) else ticket
    if not t:
        raise ApiError(404, "工单不存在")
    p = _project(P, t["project_id"])
    excluded = {tuple(sorted((x, y))) for c in _load(P, p)["clusters"] for x, y in c.get("excluded_pairs", [])}
    out = []
    for other in _tickets(P, p):
        if other["id"] == t["id"] or tuple(sorted((t["key"], other["key"]))) in excluded:
            continue
        match = _similar(t, other)
        if match:
            out.append({"key": other["key"], "title": other["title"], "status": other["status"],
                        "project": p["key"], **match})
    return sorted(out, key=lambda x: (-x["score"], x["key"]))[:limit]


def _member(t):
    return {"key": t["key"], "ticket_id": t["id"], "project_id": t["project_id"], "title": t["title"],
            "status": t["status"], "body": t.get("body") or "", "links": t.get("links") or {},
            "fingerprint": _digest({k: t.get(k) for k in ("title", "body", "type", "links", "status")})}


def _cluster_suggestions(P, p, existing):
    tickets = _tickets(P, p)
    by_key = {t["key"]: t for t in tickets}
    features = {t["key"]: _features(t) for t in tickets}
    excluded = {tuple(sorted(pair)) for c in existing for pair in c.get("excluded_pairs", [])}
    # Blocking makes comparison proportional to shared anchors, not all pairs.
    blocks = defaultdict(list)
    for t in tickets:
        f = features[t["key"]]
        for kind in ("flows", "files", "errors"):
            for value in f[kind]:
                blocks[(f["kind"], kind, value)].append(t["key"])
        if len(f["title"]) >= 10:
            blocks[(f["kind"], "title", f["title"])].append(t["key"])
    pairs = {}
    for values in blocks.values():
        for i, a in enumerate(values):
            for b in values[i + 1:]:
                pair = tuple(sorted((a, b)))
                if pair in pairs or pair in excluded:
                    continue
                pairs[pair] = _similar(by_key[a], by_key[b], features[a], features[b])
    groups, assigned = [], set()
    # Preserve a persisted group's identity and excluded history; membership
    # expands only when the newcomer matches EVERY current member.
    for c in existing:
        keys = [m["key"] for m in c["members"] if m["key"] in by_key]
        groups.append((c, keys))
        assigned.update(keys)
    for t in tickets:
        key = t["key"]
        if key in assigned:
            continue
        for _, keys in groups:
            if keys and all(pairs.get(tuple(sorted((key, other)))) for other in keys):
                keys.append(key)
                assigned.add(key)
                break
        else:
            groups.append((None, [key]))
            assigned.add(key)
    out = []
    project_lessons = learn.lessons(P.data_dir, p["key"], 1000000)
    for old, keys in groups:
        if len(keys) < 2 and not old:
            continue
        matches = [{"tickets": [a, b], **pairs[tuple(sorted((a, b)))]}
                   for i, a in enumerate(keys) for b in keys[i + 1:] if pairs.get(tuple(sorted((a, b))))]
        members = [_member(by_key[key]) for key in keys]
        cid = old["id"] if old else "C-" + _digest([p["id"], keys[0]])[:20]
        if not old and cid in {c["id"] for c in existing}:
            cid = "C-" + _digest([p["id"], keys, "after-exclusion"])[:20]
        signature = _digest({"members": members, "matches": matches})
        changed = not old or signature != old.get("fingerprint")
        status = "candidate" if changed else old["status"]
        out.append({**(old or {}), "id": cid, "project": p["key"], "title": old["title"] if old else members[0]["title"],
                    "members": members, "matches": matches, "fingerprint": signature, "status": status,
                    "revision": (old.get("revision", 0) if old else 0) + int(changed), "pending_changes": changed,
                    "excluded_pairs": (old or {}).get("excluded_pairs", []),
                    "lessons": [{k: l.get(k) for k in ("id", "title", "ticket", "status", *learn.FIELDS, "stats", "provenance")}
                                for l in project_lessons if l.get("ticket") in keys],
                    "notice": "相似线索，不代表根因相同。原工单独立保留，仍需分别验证和验收。"})
    return out, len(tickets)


def clusters(P, project, q=""):
    p = _project(P, project)
    items, count = _cluster_suggestions(P, p, _load(P, p)["clusters"])
    if q:
        items = [c for c in items if q.casefold() in json.dumps(c, ensure_ascii=False).casefold()]
    return {"items": items, "tickets_scanned": count, "project": p["key"], "readonly": True,
            "method": "仅同项目、同类型；具体业务流/文件/异常锚点与描述共同匹配；每个新成员须与组内所有成员匹配。"}


def _record_cluster(c, actor, operation):
    result = copy.deepcopy(c)
    result["pending_changes"] = False
    result["updated"] = now()
    result["updated_by"] = actor
    history = result.setdefault("history", [])
    history.append({"revision": result["revision"], "action": operation, "by": actor, "at": now(),
                    "status": result["status"], "members": copy.deepcopy(result["members"]),
                    "matches": copy.deepcopy(result["matches"]), "fingerprint": result["fingerprint"],
                    "excluded_pairs": copy.deepcopy(result["excluded_pairs"])})
    return result


def _git(root, *args):
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=15)
        return result.stdout.decode("utf-8", "replace").strip() if result.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _safe_file(root, path):
    """Knowledge symlinks must not pull another project's content into a brief."""
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        return None
    return path.read_text(encoding="utf-8")


def _brief_inputs(P, p):
    from .. import kb
    from ..graph import graph_path
    root = Path(p["root"])
    sources, pages, warnings = [], [], []
    sources.append({"id": "project", "kind": "project", "label": "项目说明", "sha256": _digest({k: p.get(k) for k in ("key", "name", "description", "root")})})
    head = _git(root, "rev-parse", "--verify", "HEAD")
    # Include actual diff bytes: a second edit must invalidate a brief even if
    # git status lists exactly the same modified paths.
    dirty = _git(root, "diff", "--binary", "--no-ext-diff", "HEAD", "--", ".", ":(exclude).tmh")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    loose = {}
    for rel in untracked.split("\0"):
        if not rel or rel.startswith(".tmh/"):
            continue
        path = root / rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            loose[rel] = "symlink"
        elif path.is_file():
            loose[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    sources.append({"id": "code", "kind": "code", "label": "当前代码版本", "commit": head,
                    "sha256": _digest([head, dirty, loose]), "dirty": bool(dirty or loose)})
    if not head:
        warnings.append("项目没有可识别的 Git 提交；交接不能充当固定代码版本证明。")
    reg = kb.load_registry(root)
    kd = kb.kdir(root)
    if kd.exists() and not kd.is_symlink():
        for path in sorted(kd.rglob("*.md")):
            rel = path.relative_to(root).as_posix()
            try:
                content = _safe_file(root, path)
            except (UnicodeError, OSError) as exc:
                warnings.append("未读取知识页 %s：%s" % (rel, exc))
                continue
            if content is None:
                warnings.append("未读取越界或符号链接知识页：" + rel)
                continue
            parsed = kb.parse_page(content)
            meta = parsed.get("meta") or {}
            pid = meta.get("id") or rel
            record = reg.get(pid) or {}
            status = "需更新" if record.get("stale") else record.get("status") or meta.get("status") or "待确认"
            if status in ("需更新", "未分析", "待确认"):
                warnings.append("知识页 %s：%s" % (pid, status))
            source = {"id": "page:" + rel, "kind": "knowledge", "label": meta.get("title") or pid,
                      "path": rel, "page_id": pid, "status": status, "sha256": _digest([content, record])}
            sources.append(source)
            pages.append({**source, "content": content})
    graph = graph_path(root)
    if graph.exists() and not graph.is_symlink():
        sources.append({"id": "graph", "kind": "graph", "label": "代码事实图谱", "sha256": hashlib.sha256(graph.read_bytes()).hexdigest()})
    else:
        warnings.append("尚无代码事实图谱，入口、模块和业务流说明需要构建知识库。")
    tickets = _tickets(P, p)
    ticket_values = [{k: t.get(k) for k in ("key", "title", "body", "status", "assignee", "links")} for t in tickets]
    sources.append({"id": "tickets", "kind": "tickets", "label": "维护工单与交接事项", "sha256": _digest(ticket_values)})
    ls = learn.lessons(P.data_dir, p["key"], 1000000)
    lesson_values = [{k: l.get(k) for k in ("id", "title", "status", "ticket", "symptom", "cause", "fix", "verify", "anti", "provenance")} for l in ls]
    sources.append({"id": "lessons", "kind": "lessons", "label": "项目经验与确认状态", "sha256": _digest(lesson_values)})
    references = project_library.reference_state(P.store, p)
    sources.append({"id": "references", "kind": "references", "label": "固定知识引用", "sha256": _digest(references)})
    try:
        arch = P.kb.arch(p) if hasattr(P, "kb") else {"built": False}
    except (ApiError, ValueError, OSError) as exc:
        arch = {"built": False}
        warnings.append("项目结构暂不可用：" + str(exc))
    return {"sources": sources, "fingerprint": _digest(sources), "pages": pages, "tickets": ticket_values,
            "lessons": lesson_values, "references": references, "arch": arch, "warnings": warnings,
            "commit": head, "dirty": bool(dirty or loose)}


def _markdown(p, inputs):
    lines = ["# %s · 项目讲解与交接" % p["name"], "", "项目：%s" % p["key"], "",
             "根据当前代码事实、知识页、经验和工单自动整理；人工确认仅针对本版交接，不能代替测试或业务验收。", "",
             "## 项目是什么", "", p.get("description") or "尚未登记项目说明。", "",
             "## 代码与结构", "", "代码提交：`%s`" % (inputs["commit"] or "未识别"),
             "工作区：" + ("包含未提交变化（来源摘要已记录）" if inputs["dirty"] else "未发现未提交变化"), ""]
    arch = inputs["arch"]
    if arch.get("built"):
        lines += [arch.get("overview") or "系统总览尚待补充。", "",
                  "业务流 %s；表 %s；类 %s；未解析关系 %s。" % tuple(arch.get(k, 0) for k in ("flows", "tables", "classes", "unresolved")), ""]
        for d in arch.get("domains") or []:
            lines += ["- %s：%s（%s，业务流 %s）" % (d["title"], d.get("summary") or "待补充", d.get("status") or "仅事实", d.get("flows", 0))]
        lines += ["", "入口：" + "；".join("%s %s" % tuple(x) for x in arch.get("entries") or [])]
    lines += ["", "## 如何阅读与维护", "", "先读系统总览，再按本次任务的业务流进入对应模块与数据表；每页的状态及来源如下。", "",
              "运行、测试、部署命令仅以项目已有知识和交付记录为依据。本交接不会推测生产环境或自动执行命令。", ""]
    if not inputs["pages"]:
        lines += ["尚无知识页。可从项目知识库构建事实并补充运行和验收说明。", ""]
    for page in inputs["pages"]:
        lines += ["### %s（%s）" % (page["label"], page["status"]), "", "来源：`%s` · SHA-256 `%s`" % (page["path"], page["sha256"]), "", page["content"], ""]
    lines += ["## 当前待办与责任人", ""]
    opened = [t for t in inputs["tickets"] if t["status"] != "closed"]
    if not opened:
        lines.append("当前没有未关闭工单。")
    for t in opened:
        lines += ["### %s · %s" % (t["key"], t["title"]), "", "状态：%s；负责人：%s" % (t["status"], t.get("assignee") or "待分配"), "", t.get("body") or "未填写详情。", ""]
    lines += ["", "## 已沉淀的经验", ""]
    for l in inputs["lessons"]:
        lines += ["### %s · %s（%s）" % (l["id"], l.get("title") or "经验", l["status"]), "", "来源工单：%s" % (l.get("ticket") or "未关联")]
        lines += ["- %s：%s" % (learn.FIELD_LABEL[k], l[k]) for k in learn.FIELDS if l.get(k)]
        lines.append("")
    if not inputs["lessons"]:
        lines.append("尚无验收经验。")
    lines += ["", "## 固定参考来源", ""]
    for ref in inputs["references"]:
        lines += ["```json", json.dumps(ref, ensure_ascii=False, indent=2), "```", ""]
    if not inputs["references"]:
        lines.append("未绑定其他项目的固定知识版本。")
    lines += ["", "## 未确认和需更新事项", ""]
    lines += ["- " + warning for warning in inputs["warnings"]] or ["没有自动识别到缺口；这不代表业务知识完整。"]
    lines += ["", "## 完整来源清单", "", "```json", json.dumps(inputs["sources"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def _brief_sections(p, inputs):
    """A reading model whose boundaries never depend on headings in source text.

    The separately exported markdown stays complete. Each source page and each
    ticket is a distinct expandable item, including its original full text.
    """
    arch = inputs["arch"]
    overview = ["## 项目是什么", "", p.get("description") or "尚未登记项目说明。", "",
                "## 代码与结构", "", "代码提交：`%s`" % (inputs["commit"] or "未识别"), "",
                "工作区：" + ("包含未提交变化（来源摘要已记录）" if inputs["dirty"] else "未发现未提交变化"), ""]
    if arch.get("built"):
        overview += [arch.get("overview") or "系统总览尚待补充。", "",
                     "业务流 %s；表 %s；类 %s；未解析关系 %s。" % tuple(arch.get(k, 0) for k in ("flows", "tables", "classes", "unresolved")), ""]
        overview += ["- %s：%s（%s，业务流 %s）" % (d["title"], d.get("summary") or "待补充", d.get("status") or "仅事实", d.get("flows", 0)) for d in arch.get("domains") or []]
        overview += ["", "入口：" + "；".join("%s %s" % tuple(x) for x in arch.get("entries") or [])]
    overview += ["", "## 阅读路径", "", "先读项目总览，再选择本次工作涉及的业务知识；接着核对未完工单、责任人和经验，最后检查待确认项。", "",
                 "运行、测试、部署命令以项目已有知识和交付记录为依据。本交接不会推测生产环境或自动执行命令。"]
    tickets = [{"id": t["key"], "title": t["key"] + " · " + t["title"], "status": t["status"],
                "source": "工单 %s；负责人：%s" % (t["key"], t.get("assignee") or "待分配"),
                "body": t.get("body") or "未填写详情。"} for t in inputs["tickets"] if t["status"] != "closed"]
    lessons = [{"id": l["id"], "title": l.get("title") or l["id"], "status": l["status"],
                "source": "%s；来源工单 %s" % (l["id"], l.get("ticket") or "未关联"),
                "body": "\n\n".join("**%s**\n\n%s" % (learn.FIELD_LABEL[k], l[k]) for k in learn.FIELDS if l.get(k))} for l in inputs["lessons"]]
    return [
        {"id": "overview", "title": "项目与代码", "kind": "markdown", "body": "\n".join(overview)},
        {"id": "knowledge", "title": "业务知识", "kind": "entries", "intro": "按页阅读项目已有知识。页内保留原始标题与正文；状态表示来源的确认情况。", "empty": "尚无知识页，请在项目知识库构建事实并补充说明。",
         "items": [{"id": x["id"], "title": x["label"], "status": x["status"], "source": x["path"], "sha256": x["sha256"], "body": x["content"]} for x in inputs["pages"]]},
        {"id": "work", "title": "待办与责任人", "kind": "entries", "items": tickets, "empty": "当前没有未关闭工单。"},
        {"id": "lessons", "title": "经验与方案", "kind": "entries", "items": lessons, "empty": "尚无验收经验。"},
        {"id": "references", "title": "固定参考", "kind": "entries", "intro": "固定来源是参考材料，不能替代当前项目验收。", "empty": "未绑定其他项目的固定知识版本。",
         "items": [{"id": str(n), "title": x.get("source_project") or x.get("revision_id") or "参考来源", "body": json.dumps(x, ensure_ascii=False, indent=2), "format": "json"} for n, x in enumerate(inputs["references"])]},
        {"id": "gaps", "title": "需确认事项", "kind": "markdown", "body": "\n".join("- " + x for x in inputs["warnings"]) or "没有自动识别到缺口；这不代表业务知识完整。"},
        {"id": "sources", "title": "来源清单", "kind": "entries", "intro": "展开单项查看完整版本和内容摘要；完整清单也在 Markdown 导出中。", "items": [
            {"id": x["id"], "title": x["label"], "source": x.get("path") or x["kind"], "body": json.dumps(x, ensure_ascii=False, indent=2), "format": "json"} for x in inputs["sources"]]},
    ]


def _stale(old_sources, current):
    old, new = ({s["id"]: s for s in values} for values in (old_sources, current))
    out = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        if a != b:
            out.append({"source_id": key, "label": (b or a)["label"], "reason": "新增来源" if not a else "来源已移除" if not b else "来源内容或状态已变化"})
    return out


def read_brief(P, project, revision=""):
    p = _project(P, project)
    state = _load(P, p)
    current = _brief_inputs(P, p)
    briefs = state["briefs"]
    selected = next((b for b in briefs if str(b["revision"]) == str(revision)), None) if revision else (briefs[-1] if briefs else None)
    if revision and not selected:
        raise ApiError(404, "交接版本不存在")
    history = [{k: b.get(k) for k in ("revision", "created", "created_by", "confirmed", "fingerprint")} for b in reversed(briefs)]
    if not selected:
        return {"project": p, "exists": False, "revision": None, "markdown": _markdown(p, current),
                "sections": _brief_sections(p, current),
                "sources": current["sources"], "fingerprint": current["fingerprint"], "current_fingerprint": current["fingerprint"],
                "status": "preview", "stale": False, "stale_reasons": [], "history": [], "warnings": current["warnings"]}
    reasons = _stale(selected["sources"], current["sources"])
    return {**selected, "project": p, "exists": True, "history": history, "stale": bool(reasons), "stale_reasons": reasons,
            "sections": selected.get("sections") or [{"id": "archive", "title": "历史交接全文", "kind": "entries", "intro": "这版交接生成于章节阅读功能之前，原文完整保留。", "items": [{"id": "full", "title": "展开本版完整内容", "body": selected["markdown"]}]}],
            "status": "stale" if reasons else "confirmed" if selected.get("confirmed") else "draft",
            "current_fingerprint": current["fingerprint"]}


def _lesson_workspace(P, p=None, q=""):
    shared = learn.shared(P.data_dir, p["key"] if p else "")
    items = []
    if p:
        for l in learn.lessons(P.data_dir, p["key"], 1000000):
            items.append({**l, "scope": "project", "scope_label": "本项目记忆", "source_project": p["key"],
                          "auto_use": l["status"] == "active", "applicability": "本项目相近任务按相关度使用"})
    for l in shared:
        items.append({**l, "scope": "organization", "scope_label": "已共享经验", "auto_use": bool(p and l.get("taken") and l["status"] == "active"),
                      "applicability": "已引入本项目，仍按相关度选择" if p and l.get("taken") else "仅供查阅，项目引入后才会用于相近任务"})
    if q:
        terms = org_knowledge._tokens(q)
        items = [l for l in items if terms & org_knowledge._tokens(" ".join(str(l.get(k) or "") for k in ("title", *learn.FIELDS)))]
    return items


def dispatch_read(P, query, user):
    if not isinstance(query, dict):
        raise ApiError(400, "查询参数格式不正确")
    # The HTTP handler passes parse_qs values; direct callers use plain strings.
    query = {k: v[0] if isinstance(v, list) and len(v) == 1 else "" if v == [] else v for k, v in query.items()}
    section = query.get("section") or "overview"
    if section not in ("overview", "clusters", "knowledge", "lessons", "brief"):
        raise ApiError(400, "未知记忆分区")
    key, q = query.get("project") or "", query.get("q") or ""
    if not isinstance(key, str) or not isinstance(q, str):
        raise ApiError(400, "project 和 q 必须是文字")
    p = _project(P, key) if key else None
    if section == "brief":
        return read_brief(P, key, query.get("revision") or "")
    if section == "clusters":
        return clusters(P, key, q)
    items = _lesson_workspace(P, p, q)
    # Organization knowledge is a browsing catalog, not an authorization to
    # inject its full private project contents into other projects' tasks.
    browsing = {"include_drafts": bool(p), "project_key": p["key"] if p else ""}
    knowledge = org_knowledge.search(P.store, q, limit=200, **browsing) if q else org_knowledge.build(P.store, **browsing)["items"]
    result = {"section": section, "project": p, "query": q, "projects": [{"key": x["key"], "name": x["name"]} for x in P.store.projects()],
              "lessons": items, "knowledge": knowledge, "readonly": True,
              "scope_notice": "项目知识保留来源；组织目录用于查阅。跨项目自动使用仅限人工共享并由当前项目引入的经验或明确绑定的固定知识。",
              "summary": {"lessons": len(items), "active": sum(x.get("auto_use", False) for x in items),
                          "knowledge": len(knowledge), "shared": sum(x["scope"] == "organization" for x in items)}}
    if p and section == "overview":
        result["clusters"] = clusters(P, p["key"])
        brief = read_brief(P, p["key"])
        result["brief"] = {k: brief[k] for k in ("exists", "status", "revision", "stale", "stale_reasons", "warnings")}
    return result


def dispatch_action(P, body, user):
    if not isinstance(body, dict) or not isinstance(body.get("action"), str):
        raise ApiError(400, "请指定记忆操作")
    if not isinstance(user, str) or not user.strip():
        raise ApiError(401, "需要明确当前操作者")
    p = _project(P, body.get("project"))
    action = body["action"]
    if action == "lesson_create":
        fields, title = body.get("fields"), body.get("title")
        if not isinstance(title, str) or not title.strip() or not isinstance(fields, dict):
            raise ApiError(400, "请填写记忆标题和适用场景、做法")
        if any(k not in learn.FIELDS or not isinstance(v, str) for k, v in fields.items()):
            raise ApiError(400, "记忆字段格式不正确")
        if not fields.get("symptom", "").strip() or not fields.get("fix", "").strip():
            raise ApiError(400, "请写清适用场景和做法，避免没有适用范围的全局指令")
        return learn.add_lesson(P.data_dir, {"project": p["key"], "title": title, **fields, "kind": "manual",
                                "status": "candidate", "by": user, "note": "团队主动记录；确认后用于本项目相近任务", "files": [], "flows": []})
    if action.startswith("lesson_"):
        lid = body.get("lesson_id")
        if not isinstance(lid, str):
            raise ApiError(400, "请指定经验")
        try:
            if action in ("lesson_take", "lesson_untake"):
                return learn.take_shared(P.data_dir, lid, p["key"], action == "lesson_take", user)
            card = learn.lesson(P.data_dir, lid)
            if not card or card.get("project") != p["key"]:
                raise ApiError(404, "经验不属于当前项目")
            if action == "lesson_edit":
                fields = body.get("fields")
                if not isinstance(fields, dict) or any(k not in learn.FIELDS or not isinstance(v, str) for k, v in fields.items()):
                    raise ApiError(400, "记忆字段格式不正确")
                return learn.edit_lesson(P.data_dir, lid, fields, user)
            if action in ("lesson_share", "lesson_unshare"):
                fields = body.get("fields") or {}
                if not isinstance(body.get("title") or "", str) or not isinstance(fields, dict) or not all(k in learn.FIELDS and isinstance(v, str) for k, v in fields.items()):
                    raise ApiError(400, "共享字段必须是文字")
                # The legacy sharing function clips fields; reject oversize
                # here so this workspace never silently loses supplied text.
                if any(len(v.strip()) > 800 for v in fields.values()) or len(body.get("title") or "") > 120:
                    raise ApiError(400, "共享副本标题最多 120 字，每字段最多 800 字；请明确编辑副本，原经验保持完整")
                return learn.set_shared(P.data_dir, lid, action == "lesson_share", user, body.get("title") or "", fields,
                                        names=[p["key"], p["name"]])
            states = {"lesson_confirm": "active", "lesson_restore": "active", "lesson_retire": "retired"}
            if action in states:
                reason = body.get("reason") or ""
                if not isinstance(reason, str) or action == "lesson_retire" and not reason.strip():
                    raise ApiError(400, "请填写停用原因")
                return learn.set_status(P.data_dir, lid, states[action], user, reason or "在知识与记忆工作区确认")
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        raise ApiError(400, "未知经验操作")
    if action.startswith("cluster_"):
        with _write(P, p) as state:
            suggested, count = _cluster_suggestions(P, p, state["clusters"])
            if action == "cluster_scan":
                state["clusters"] = [_record_cluster(c, user, "scan") if c["pending_changes"] else c for c in suggested]
                return {"items": state["clusters"], "tickets_scanned": count, "project": p["key"]}
            c = next((x for x in suggested if x["id"] == body.get("cluster_id")), None)
            if not c:
                raise ApiError(404, "问题簇不存在")
            if body.get("expected_fingerprint") != c["fingerprint"]:
                raise ApiError(409, "工单或分组已变化，请更新后再确认")
            if action == "cluster_confirm":
                if len(c["members"]) < 2:
                    raise ApiError(409, "至少两张工单才能确认同类分组")
                c.update(status="confirmed", confirmed_by=user, confirmed_at=now())
            elif action == "cluster_exclude":
                key, reason = body.get("ticket_key"), body.get("reason") or ""
                if not isinstance(reason, str) or not reason.strip():
                    raise ApiError(400, "请填写移出原因")
                if key not in {m["key"] for m in c["members"]}:
                    raise ApiError(404, "工单不在此分组")
                c["excluded_pairs"] += [[key, m["key"]] for m in c["members"] if m["key"] != key]
                c["members"] = [m for m in c["members"] if m["key"] != key]
                c["matches"] = [m for m in c["matches"] if key not in m["tickets"]]
                c["fingerprint"] = _digest({"members": c["members"], "matches": c["matches"]})
                c["status"] = "candidate"
                c.setdefault("exclusions", []).append({"ticket_key": key, "reason": reason, "by": user, "at": now()})
            else:
                raise ApiError(400, "未知分组操作")
            c["revision"] += 1
            updated = _record_cluster(c, user, action)
            state["clusters"] = [x for x in state["clusters"] if x["id"] != c["id"]] + [updated]
            return updated
    if action == "brief_generate":
        with _write(P, p) as state:
            inputs = _brief_inputs(P, p)
            last = state["briefs"][-1] if state["briefs"] else None
            if last and last.get("sections") and last["fingerprint"] == inputs["fingerprint"]:
                return {**last, "unchanged": True}
            brief = {"revision": len(state["briefs"]) + 1, "created": now(), "created_by": user,
                     "fingerprint": inputs["fingerprint"], "sources": inputs["sources"], "warnings": inputs["warnings"],
                     "markdown": _markdown(p, inputs), "sections": _brief_sections(p, inputs), "confirmed": None}
            state["briefs"].append(brief)
            return brief
    if action == "brief_confirm":
        with _write(P, p) as state:
            selected = next((b for b in state["briefs"] if str(b["revision"]) == str(body.get("revision"))), None)
            if not selected:
                raise ApiError(404, "交接版本不存在")
            current = _brief_inputs(P, p)
            if selected["fingerprint"] != current["fingerprint"] or body.get("expected_fingerprint") != selected["fingerprint"]:
                raise ApiError(409, "交接来源已变化，请刷新生成新版后确认")
            if not selected.get("confirmed"):
                selected["confirmed"] = {"by": user, "at": now(), "fingerprint": selected["fingerprint"]}
            return selected
    raise ApiError(400, "未知记忆操作")
