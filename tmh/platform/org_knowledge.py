"""Organization knowledge v0: a read-only roll-up over the knowledge of every project.

Why this module exists
----------------------
`docs/design/project-knowledge-library-2026-10-20.md` §2/§8 asks for an
organization-level knowledge view on top of the per-project library. Two rules
shape this v0:

* **read-only aggregation, no copies.** Items point back at the project + page /
  lesson / file they came from; the full text is never copied here. Reading the
  whole project knowledge still happens in the project.
* **never merge two projects' same-named things.** De-duplication only joins
  items whose *normalized content* is identical; provenance keeps every project
  apart. Two projects with a page/table of the same name but different content
  stay two items (design §3/§9).

Sources read here (all read-only):
* `<project root>/.tmh/knowledge/**/*.md` — page frontmatter (id/title/status),
  `.pages.json` (status registry), `glossary.md` (terms), `decisions.md` /
  `pitfalls.md` (rules);
* `<data dir>/lessons.jsonl` — experience cards written from human verdicts
  (`tmh/platform/learn.py`), mapped to patterns (fix) and rules (anti-pattern).

The interface is deliberately narrow (`build`, `search`) so a future storage
backend (or a server-side materialized view) can replace it without touching UI,
CLI or MCP callers.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from pathlib import Path

SCHEMA = 1
TYPES = ("term", "pattern", "component", "rule")
TYPE_LABEL = {"term": "术语", "pattern": "模式", "component": "组件", "rule": "行业规则"}
SUMMARY_MAX = 200
_LESSON_FIELDS = {"symptom": "fix", "cause": "fix", "fix": "fix", "verify": "verify", "anti": "rule"}
_PUNCT = re.compile(r"[\s\u3000:：,，.。;；、!！?？'\"“”‘’()（）\[\]【】<>《》/\\|+*_`~-]+")
_FRONT = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
_H1 = re.compile(r"^#\s+(.+)$", re.M)
_TABLE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$", re.M)
_BULLET = re.compile(r"^[-*]\s+(.+)$", re.M)


def _norm(text: str) -> str:
    """Normalization used only for de-duplication (never for display)."""
    # Preserve punctuation/case: Java identifiers and rules can differ only by
    # those characters. Display summaries are never identity evidence.
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).split())


def _short(text: str, limit: int = SUMMARY_MAX) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONT.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def _body_summary(body: str) -> str:
    """A short human-readable line: first paragraph outside the generated facts block."""
    body = re.sub(r"<!-- tmh:facts:start.*?tmh:facts:end -->", "", body, flags=re.S)
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block or block.startswith("#") or block.startswith(">") or block.startswith("|") or block.startswith("```"):
            continue
        line = re.sub(r"^[-*]\s*", "", block.splitlines()[0])
        if line.strip():
            return _short(line)
    return ""


def _provenance(project: dict, kind: str, ref: str, item_id: str, revision: str = "", confirmed: bool = False) -> dict:
    return {"project": project.get("key") or project.get("name") or "", "project_id": project.get("id"),
            "kind": kind, "ref": ref, "id": item_id, "revision": revision,
            "confirmed": bool(confirmed), "root": project.get("root", "")}


def _kb_dir(project: dict) -> Path | None:
    root = Path(str(project.get("root") or ""))
    d = root / ".tmh" / "knowledge"
    return d if d.is_dir() and not d.is_symlink() and d.resolve().is_relative_to(root.resolve()) else None


def _pages(kb_dir: Path) -> list[dict]:
    from ..kb import confirmation_status
    out = []
    try:
        registry = json.loads((kb_dir / ".pages.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        registry = {}
    for p in sorted(kb_dir.rglob("*.md")):
        if p.is_symlink() or not p.resolve().is_relative_to(kb_dir.resolve()):
            continue
        rel = p.relative_to(kb_dir).as_posix()
        if rel in ("glossary.md", "decisions.md", "pitfalls.md", "open-questions.md") or rel.startswith("README"):
            continue
        try:
            text = p.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        meta, body = _frontmatter(text)
        record = registry.get(meta.get("id"), {}) if isinstance(registry, dict) else {}
        if record.get("orphan"):
            continue
        title = meta.get("title") or (m.group(1).strip() if (m := _H1.search(body)) else rel)
        out.append({"rel": rel, "id": meta.get("id") or rel, "title": title, "content": body,
                    "status": (confirmation_status(record, text) if isinstance(record.get("learning"), dict) and record["learning"].get("pending") else
                               "需更新" if record.get("stale") else confirmation_status(record, text) or meta.get("status") or ""), "commit": meta.get("commit") or "",
                    "summary": _body_summary(body) or title, "registered": bool(record)})
    return out


def _readable_page(project: dict, kb_dir: Path, page: dict) -> bool:
    """Only advertise new drafts when the existing KB reader can open them."""
    from ..kb import page_path
    from ..graph import graph_path
    root = Path(project["root"])
    try:
        return (page["registered"] and graph_path(root).is_file() and
                page_path(root, page["id"]).resolve() == (kb_dir / page["rel"]).resolve())
    except (KeyError, ValueError):
        return False


def _table_terms(kb_dir: Path) -> list[dict]:
    out = []
    f = kb_dir / "glossary.md"
    if not f.is_file() or f.is_symlink() or not f.resolve().is_relative_to(kb_dir.resolve()):
        return out
    try:
        text = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for m in _TABLE_ROW.finditer(text):
        term, code, note = (x.strip() for x in m.groups())
        if not term or term in ("业务词",) or set(term) <= {"-", " "}:
            continue
        content = (note + "；代码/表：" + code).strip("；") if code else note
        out.append({"title": term, "summary": _short(content), "content": content})
    return out


def _doc_rules(kb_dir: Path) -> list[dict]:
    out = []
    for name in ("decisions.md", "pitfalls.md"):
        f = kb_dir / name
        if not f.is_file() or f.is_symlink() or not f.resolve().is_relative_to(kb_dir.resolve()):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in _BULLET.finditer(text):
            line = m.group(1).strip()
            if len(line) < 6:
                continue
            out.append({"title": line.split("：")[0][:60], "summary": _short(line), "content": line,
                        "ref": name})
    return out


def _lesson_items(data_dir: Path) -> list[dict]:
    from . import learn
    out = []
    for card in learn.lessons(data_dir, limit=1000000):
        if card.get("status") != "active":
            continue
        symptom = _short(card.get("symptom") or card.get("title") or "")
        fix = _short(card.get("fix") or card.get("note") or "")
        anti = _short(card.get("anti") or "")
        project = card.get("project") or ""
        if fix:
            out.append({"type": "pattern", "title": symptom or fix[:60], "summary": fix,
                        "content": (card.get("symptom") or card.get("title") or "") + "\n" + (card.get("fix") or card.get("note") or ""),
                        "project": project, "ref": "lessons.jsonl#" + str(card.get("id") or ""),
                        "revision": "", "confirmed": card.get("status") in ("active", "retired"),
                        "lesson_id": card.get("id") or ""})
        if anti:
            out.append({"type": "rule", "title": symptom or anti[:60], "summary": anti,
                        "content": (card.get("symptom") or card.get("title") or "") + "\n" + (card.get("anti") or ""),
                        "project": project, "ref": "lessons.jsonl#" + str(card.get("id") or ""),
                        "revision": "", "confirmed": card.get("status") in ("active", "retired"),
                        "lesson_id": card.get("id") or ""})
    return out


def _collect(store, *, include_drafts: bool = False, project_key: str = "") -> tuple[list[dict], list[dict]]:
    """[(item, provenance)] and the project list actually read."""
    raw: list[dict] = []
    projects = []
    data_dir = Path(getattr(store, "path", "")).parent if getattr(store, "path", None) else None
    for project in store.projects():
        if project_key and project.get("key") != project_key:
            continue
        kb = _kb_dir(project)
        if not kb:
            continue
        projects.append(project)
        rev = ""  # page-level commit when the project records one
        from .project_library import profile
        browse_drafts = include_drafts and profile(store, project)["workflow"] == "development"
        for page in _pages(kb):
            status = page["status"]
            rel = page["rel"]
            if status == "已确认" or (browse_drafts and status in ("待确认", "需更新") and _readable_page(project, kb, page)):
                kind = "component" if rel.startswith("modules/") else ("pattern" if rel.startswith("flows/") else "rule")
                raw.append({
                    "type": kind, "title": page["title"], "summary": page["summary"],
                    "status": status,
                    "dedup_text": page["title"] + "\n" + page["content"],
                    "provenance": {**_provenance(project, "page", rel, page["id"], page["commit"] or rev, status == "已确认"), "status": status},
                })
        for term in _table_terms(kb):
            raw.append({"type": "term", "title": term["title"], "summary": term["summary"],
                        "dedup_text": term["title"] + "\n" + term["content"],
                        "provenance": _provenance(project, "glossary", "glossary.md", _norm(term["title"]), "", True)})
        for rule in _doc_rules(kb):
            raw.append({"type": "rule", "title": rule["title"], "summary": rule["summary"],
                        "dedup_text": rule["content"],
                        "provenance": _provenance(project, "doc", rule["ref"], _norm(rule["title"]), "", True)})
    if data_dir and data_dir.is_dir():
        for lesson in _lesson_items(data_dir):
            if project_key and lesson["project"] != project_key:
                continue
            prov = {"project": lesson["project"], "project_id": None, "kind": "lesson",
                    "ref": lesson["ref"], "id": lesson["lesson_id"], "revision": "",
                    "confirmed": lesson["confirmed"], "root": ""}
            raw.append({"type": lesson["type"], "title": lesson["title"], "summary": lesson["summary"],
                        "dedup_text": lesson["content"],
                        "provenance": prov})
    return raw, projects


def _merge(raw: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in raw:
        key = item["type"] + "|" + _norm(item["dedup_text"])
        status = item.get("status") or "已确认"
        # Matching text is not matching review evidence. Keep historical IDs
        # for confirmed items, and never lend their badge to a draft/stale page.
        if status != "已确认":
            key = json.dumps([key, status], ensure_ascii=False, separators=(",", ":"))
        if key in merged:
            merged[key]["provenance"].append(item["provenance"])
            merged[key]["reviewed"] = merged[key]["reviewed"] and item["provenance"]["confirmed"]
            if not merged[key]["summary"]:
                merged[key]["summary"] = item["summary"]
        else:
            merged[key] = {
                "id": item["type"] + "-" + hashlib.sha256(key.encode()).hexdigest()[:24],
                "type": item["type"], "type_label": TYPE_LABEL.get(item["type"], item["type"]),
                "title": item["title"], "summary": _short(item["summary"]),
                "dedup_key": hashlib.sha256(key.encode()).hexdigest(),
                "status": status,
                "reviewed": item["provenance"]["confirmed"],
                "provenance": [item["provenance"]],
            }
    return sorted(merged.values(), key=lambda i: (TYPES.index(i["type"]) if i["type"] in TYPES else 99, i["id"]))


def build(store, *, include_drafts: bool = False, project_key: str = "") -> dict:
    """Read-only roll-up; unconfirmed pages require explicit browsing opt-in."""
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    raw, projects = _collect(store, include_drafts=include_drafts, project_key=project_key)
    items = _merge(raw)
    by_type = {t: sum(1 for i in items if i["type"] == t) for t in TYPES}
    provenance_projects = sorted({p["project"] for i in items for p in i["provenance"] if p.get("project")})
    return {
        "schema": SCHEMA, "generated": started, "readonly": True,
        "items": items,
        "projects_read": [{"key": p.get("key"), "name": p.get("name"), "root": p.get("root")} for p in projects],
        "provenance_projects": provenance_projects,
        "stats": {"items": len(items), "raw_candidates": len(raw), "by_type": by_type,
                  "projects_contributing": len(provenance_projects),
                  "cross_project_items": sum(1 for i in items if len({p.get("project") for p in i["provenance"]}) > 1)},
        "notice": "只读聚合：每条的全文仍在来源项目里；同名但内容不同的条目不会被合并。",
    }


def _tokens(text: str) -> set[str]:
    s = unicodedata.normalize("NFKC", str(text or "")).lower()
    out = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2}", s))
    out |= {s[i:i + 2] for i in range(len(s) - 1) if "\u4e00" <= s[i] <= "\u9fff" and "\u4e00" <= s[i + 1] <= "\u9fff"}
    return out


def search(store, q: str, limit: int = 20, types: tuple | list | None = None, *, include_drafts: bool = False, project_key: str = "") -> list[dict]:
    """Search the roll-up. Returns structured items with full provenance; no full text."""
    built = build(store, include_drafts=include_drafts, project_key=project_key)
    wanted = _tokens(q)
    if not wanted:
        return []
    scored = []
    for item in built["items"]:
        if types and item["type"] not in types:
            continue
        hay = _tokens(item["title"] + " " + item["summary"])
        score = len(wanted & hay)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda x: (-x[0], x[1]["type"], x[1]["id"]))
    return [dict(item, score=score) for score, item in scored[:limit]]
