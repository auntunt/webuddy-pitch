"""Immutable learning inputs. Reads never create knowledge or authorize its use.

The page registry and lesson ledger remain the authorities for human status.
These tables contain snapshots and receipts, not a replacement state machine.
"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import ExitStack, contextmanager
from pathlib import Path

from . import learn, project_library as library
from .errors import ApiError
from .store import now
from .. import project_knowledge as pk

KINDS = ("fact", "lesson", "policy")
POLICY_SPECS = {"context_budget": {"min": 4000, "max": 12000, "default": 6000, "label": "上下文预算（字符）"}}
REF = re.compile(r"(?<![\w/])([\w./-]+\.[A-Za-z0-9]+):(\d+)")
LESSON_FIELDS = ("title", *learn.FIELDS, "applicability", "non_applicability")
LESSON_CONTENT_SCHEMA = "lesson-content-v2"


def lesson_content(card, schema=None):
    """Interpret immutable revisions with their recorded content protocol."""
    if schema in (None, ""):
        return {f: card.get(f, "") for f in LESSON_FIELDS}
    if schema != LESSON_CONTENT_SCHEMA:
        raise ApiError(409, "未知经验正文协议")
    value = {f: card[f] for f in LESSON_FIELDS if f in card}
    if any(v is not None and not isinstance(v, str) for v in value.values()):
        raise ApiError(409, "经验正文包含不可解释的字段类型")
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ApiError(409, "经验正文不可无损编码") from exc
    return value
DDL = (
    """CREATE TABLE IF NOT EXISTS learning_revisions (
    id TEXT PRIMARY KEY, project_id INTEGER NOT NULL, kind TEXT NOT NULL,
    origin_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
    source TEXT NOT NULL, fingerprint TEXT NOT NULL, parent_id TEXT NOT NULL,
    author TEXT NOT NULL, created TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS ix_learning_origin ON learning_revisions(project_id,kind,origin_id,created)",
    """CREATE TABLE IF NOT EXISTS learning_policies (
    project_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT NOT NULL,
    created TEXT NOT NULL, author TEXT NOT NULL, PRIMARY KEY(project_id,name))""",
    """CREATE TABLE IF NOT EXISTS learning_decisions (
    id TEXT PRIMARY KEY, project_id INTEGER NOT NULL, kind TEXT NOT NULL, origin_id TEXT NOT NULL,
    revision_id TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
    request_id TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
    created TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id,actor,request_id))""",
    """CREATE TABLE IF NOT EXISTS learning_policy_active (
    project_id INTEGER PRIMARY KEY, revision_id TEXT NOT NULL, decision_id TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS learning_eval_cases (
    project_id INTEGER NOT NULL, origin TEXT NOT NULL, input_hash TEXT NOT NULL,
    revision_id TEXT NOT NULL, job_id TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT 'holdout',
    case_digest TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(project_id,origin,input_hash))""",
)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256((value if isinstance(value, str) else encoded(value)).encode("utf-8")).hexdigest()


@contextmanager
def transaction(store):
    """Never call Store.x inside this scope: it commits the caller's transaction."""
    with store.lock:
        if store.db.in_transaction:
            raise RuntimeError("learning transaction cannot nest")
        try:
            store.db.execute("BEGIN IMMEDIATE")
            yield store.db
            store.db.commit()
        except BaseException:
            store.db.rollback()
            raise


def schema(store):
    # Individual DDL statements are transactional; executescript implicitly commits.
    with transaction(store) as db:
        for statement in DDL:
            db.execute(statement)
        columns = {c["name"] for c in db.execute("PRAGMA table_info(learning_eval_cases)").fetchall()}
        if columns and "purpose" not in columns:
            db.execute("ALTER TABLE learning_eval_cases ADD COLUMN purpose TEXT NOT NULL DEFAULT 'holdout'")
        if columns and "case_digest" not in columns:
            db.execute("ALTER TABLE learning_eval_cases ADD COLUMN case_digest TEXT NOT NULL DEFAULT ''")


def project(P, key):
    p = P.store.project(key.get("id") if isinstance(key, dict) else key)
    if not p:
        raise ApiError(404, "没有这个项目")
    return p


def binding(P, p):
    p = project(P, p)
    root = Path(p["root"]).resolve()
    if not root.is_dir():
        raise ApiError(409, "项目工作区不可读")
    try:
        commit = pk.git(root, "rev-parse", "--verify", "HEAD")
    except ValueError:
        # Non-Git sources are explicitly bound to captured file manifests below.
        if (root / ".git").exists():
            raise ApiError(409, "Git 来源不可读取，不能生成版本证据")
        commit = ""
    return {"project_id": p["id"], "root": str(root), "commit": commit,
            "workflow": library.profile(P.store, p)["workflow"],
            "references": library.bindings(P.store, p)}


def safe_read(root, rel):
    root = Path(root).resolve()
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ApiError(400, "证据路径必须在项目内：" + str(rel))
    if pk.excluded(path.as_posix()):
        raise ApiError(400, "证据路径不允许读取：" + str(rel))
    target = root / path
    if any((root / Path(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts) + 1)):
        raise ApiError(400, "证据不能经过符号链接：" + str(rel))
    if not target.resolve().is_relative_to(root):
        raise ApiError(400, "证据超出项目")
    try:
        return target.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ApiError(409, "证据不可读：" + str(rel)) from exc


def _facts(P, p):
    from .org_knowledge import _pages
    from ..kb import load_registry
    root = Path(p["root"])
    kb_dir = root / ".tmh" / "knowledge"
    if not kb_dir.is_dir():
        return []
    if kb_dir.is_symlink() or (root / ".tmh").is_symlink():
        raise ApiError(409, "知识库目录不能经过符号链接")
    if (kb_dir / ".pages.json").exists():
        safe_read(root, ".tmh/knowledge/.pages.json")
    reg = load_registry(root)
    out = []
    for page in _pages(kb_dir):
        rel = ".tmh/knowledge/" + page["rel"]
        content = safe_read(root, rel)
        r = reg.get(page["id"], {})
        out.append({"key": "fact:" + page["id"], "kind": "fact", "origin_id": page["id"],
                    "title": page["title"], "content": content, "fingerprint": digest(content),
                    "source": {"path": rel, "registry": r},
                    "human": {"status": page["status"], "by": r.get("confirmed_by", ""),
                              "at": r.get("confirmed_at", "")}})
    return out


def _lessons(P, p, content_schema=LESSON_CONTENT_SCHEMA):
    out = []
    for card in learn.lessons(P.data_dir, p["key"], limit=None):
        content = encoded(lesson_content(card, content_schema))
        source = {k: card.get(k) for k in ("ticket", "candidate_id", "source_key", "provenance", "files", "flows") if card.get(k) is not None}
        title = card.get("title", card["id"])
        if content_schema == LESSON_CONTENT_SCHEMA and title is None:
            title = card["id"]  # registry label only; immutable content retains explicit null
        out.append({"key": "lesson:" + card["id"], "kind": "lesson", "origin_id": card["id"],
                    "title": title, "content": content,
                    "fingerprint": digest({"content": content, "source": source}), "source": source,
                    "human": {"status": card["status"], "by": (card.get("history") or [{}])[-1].get("by", ""),
                              "at": (card.get("history") or [{}])[-1].get("ts", "")}})
    return out


def _policies(P, p):
    out = []
    for row in P.store.q("SELECT * FROM learning_policies WHERE project_id=? ORDER BY name", (p["id"],)):
        val = json.loads(row["content"])
        out.append({"key": "policy:" + row["name"], "kind": "policy", "origin_id": row["name"],
                    "title": val["title"], "content": row["content"], "fingerprint": digest(row["content"]),
                    "source": {}, "human": {"status": "draft", "by": "", "at": ""}})
    return out


def _origin(P, p, key, *, lesson_schema=LESSON_CONTENT_SCHEMA):
    kind, _, origin = key.partition(":")
    readers = {"fact": _facts, "lesson": _lessons, "policy": _policies}
    if kind not in readers or not origin:
        raise ApiError(400, "条目类型或标识无效")
    items = _lessons(P, p, lesson_schema) if kind == "lesson" else readers[kind](P, p)
    found = next((x for x in items if x["key"] == key), None)
    if not found:
        raise ApiError(404, "条目不存在或不属于当前项目")
    return found


def _decode(row):
    if not row:
        return None
    return dict(row, source=json.loads(row["source"]))


def revision(P, p, rid):
    p = project(P, p)
    row = P.store.one("SELECT * FROM learning_revisions WHERE project_id=? AND id=?", (p["id"], rid))
    if not row:
        raise ApiError(404, "修订不存在或不属于当前项目")
    return _decode(row)


def _save(db, p, item, source, actor, parent=""):
    fp = digest({"content": item["content"], "source": source})
    rid = "LR" + digest([p["id"], item["kind"], item["origin_id"], parent, fp])[:40]
    db.execute("INSERT OR IGNORE INTO learning_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
               (rid, p["id"], item["kind"], item["origin_id"], item["title"], item["content"],
                encoded(source), fp, parent, actor, now()))
    return rid


def capture(P, p, key, expected_fingerprint, actor):
    p = project(P, p)
    before = binding(P, p)
    item = _origin(P, p, key)
    if not expected_fingerprint or item["fingerprint"] != expected_fingerprint:
        raise ApiError(409, "正文已变化，请刷新后重新固定修订")
    paths = {m[0] for m in REF.findall(item["content"])}
    if item["kind"] == "lesson":
        paths.update(x for x in item["source"].get("files", []) if isinstance(x, str))
    evidence = [{"path": name, "content": safe_read(p["root"], name)} for name in sorted(paths)]
    for e in evidence:
        e["sha256"] = digest(e["content"])
    source = {**item["source"], "binding": before, "origin_fingerprint": item["fingerprint"],
              "evidence": evidence, "snapshot_kind": "working-copy-manifest"}
    if item["kind"] == "lesson":
        source["lesson_content_schema"] = LESSON_CONTENT_SCHEMA
    with transaction(P.store) as db:
        if binding(P, p) != before or _origin(P, p, key)["fingerprint"] != expected_fingerprint:
            raise ApiError(409, "固定修订时来源或授权发生变化")
        for e in evidence:
            if digest(safe_read(p["root"], e["path"])) != e["sha256"]:
                raise ApiError(409, "固定修订时证据文件变化")
        rid = _save(db, p, item, source, actor)
    return revision(P, p, rid)


def revision_current(P, p, r):
    try:
        p = project(P, p)
        source = r["source"]
        if p["id"] != r["project_id"] or binding(P, p) != source["binding"]:
            return False
        item = _origin(P, p, r["kind"] + ":" + r["origin_id"],
                       lesson_schema=source.get("lesson_content_schema"))
        if item["fingerprint"] != source["origin_fingerprint"]:
            return False
        return all(digest(safe_read(p["root"], e["path"])) == e["sha256"] for e in source["evidence"])
    except (ApiError, OSError, ValueError, KeyError):
        return False


def policy_content(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as exc:
            raise ApiError(400, "策略必须是结构化 JSON") from exc
    if not isinstance(value, dict) or set(value) - {"title", "parameters", "applicability"}:
        raise ApiError(400, "策略只允许标题、适用条件和允许清单中的参数")
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        raise ApiError(400, "策略需要标题")
    if not isinstance(value.get("applicability"), str) or not value["applicability"].strip():
        raise ApiError(400, "策略需要适用条件")
    params = value.get("parameters")
    if not isinstance(params, dict) or not params or set(params) - set(POLICY_SPECS):
        raise ApiError(400, "策略包含未允许的参数")
    for k, v in params.items():
        spec = POLICY_SPECS[k]
        if type(v) is not int or not spec["min"] <= v <= spec["max"]:
            raise ApiError(400, "策略参数超出允许范围：" + k)
    return encoded(value)


def propose(P, p, revision_id, content, actor):
    p = project(P, p)
    r = revision(P, p, revision_id)
    if not isinstance(content, str) or not content.strip():
        raise ApiError(400, "修订正文不能为空")
    if r["kind"] == "fact":
        from ..kb import FACTS_RX
        def protected(text):
            front = re.match(r"\A---\s*\n.*?\n---\s*\n", text, re.S)
            return (front.group() if front else "", FACTS_RX.findall(text))
        if protected(content) != protected(r["content"]):
            raise ApiError(400, "事实修订不能改变登记字段或程序生成的事实块")
    elif r["kind"] == "policy":
        content = policy_content(content)
    elif r["kind"] == "lesson":
        try:
            val = json.loads(content)
        except ValueError as exc:
            raise ApiError(400, "经验修订必须为字段 JSON") from exc
        if (not isinstance(val, dict) or set(val) - set(LESSON_FIELDS) or
                any(v is not None and not isinstance(v, str) for v in val.values())):
            raise ApiError(400, "经验修订只接受允许字段及完整字符串")
        # The revision is a complete immutable card, even when the editor sends
        # only changed fields. Projection must not silently inherit extra text
        # that the evaluator never saw and then immediately invalidate adoption.
        parent = json.loads(r["content"])
        schema = r["source"].get("lesson_content_schema")
        val = {**lesson_content(parent, schema), **val}
        if (any(not isinstance(v, str) for v in val.values()) if not schema else
                any(v is not None and not isinstance(v, str) for v in val.values())) or any(
                not isinstance(val.get(k), str) or not val[k].strip() for k in ("title", "symptom", "fix")):
            raise ApiError(400, "经验需要标题、现象、改法以及字符串字段")
        content = encoded(val)
        try:
            content.encode("utf-8")
        except UnicodeError as exc:
            raise ApiError(400, "经验修订包含不可无损编码的文字") from exc
    with transaction(P.store) as db, ExitStack() as guards:
        source = r["source"]
        valid = revision_current(P, p, r)
        if not valid:
            from .learning_decisions import adopted_current, source_current
            valid = adopted_current(P, p, r)
            if valid:
                # Only an exact, still-current human adoption may rebase its next
                # draft onto the published original. Keep DB -> file lock order.
                if r["kind"] == "fact":
                    from .. import kb
                    from . import learning_facts as F
                    root, _, _ = F._paths(p, r["origin_id"])
                    cache = root / ".tmh" / "cache"
                    cache.mkdir(exist_ok=True)
                    guards.enter_context(kb._Lock(cache / "kb.lock"))
                elif r["kind"] == "lesson":
                    guards.enter_context(learn.ledger_lock(P.data_dir))
                valid = adopted_current(P, p, r)
                if valid:
                    current = _origin(P, p, r["kind"] + ":" + r["origin_id"],
                                      lesson_schema=source.get("lesson_content_schema"))
                    if r["kind"] == "fact":
                        # The submitted header/facts already matched the parent.
                        # Publication changes only its human status in the file;
                        # copy that verified live header, never agent metadata.
                        if current["content"] != F._status(r["content"], kb.STATUS_OK):
                            raise ApiError(409, "已采用事实正文已变化，请重新固定修订")
                        old_head, _ = protected(r["content"])
                        live_head, _ = protected(current["content"])
                        content = live_head + content[len(old_head):]
                    source = dict(source, **current["source"], origin_fingerprint=current["fingerprint"])
                    valid = source_current(P, p, r)
        if not valid:
            raise ApiError(409, "来源已过期，请重新固定修订")
        title = json.loads(content)["title"] if r["kind"] in ("policy", "lesson") else r["title"]
        rid = _save(db, p, dict(r, content=content, title=title), source, actor, r["id"])
    return revision(P, p, rid)


def policy_create(P, p, name, title, parameters, applicability, actor):
    p = project(P, p)
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
        raise ApiError(400, "策略名称只能使用小写字母、数字、下划线和横线")
    content = policy_content({"title": title, "parameters": parameters, "applicability": applicability})
    with transaction(P.store) as db:
        old = db.execute("SELECT content FROM learning_policies WHERE project_id=? AND name=?", (p["id"], name)).fetchone()
        if old and old["content"] != content:
            raise ApiError(409, "同名策略已存在，请从旧版本创建修订")
        db.execute("INSERT OR IGNORE INTO learning_policies VALUES(?,?,?,?,?)", (p["id"], name, content, now(), actor))
    return capture(P, p, "policy:" + name, digest(content), actor)


def _jobs(P, p, rid=""):
    # Schema initialization belongs to startup; a GET must never migrate/recover.
    if not P.store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='learning_jobs'"):
        return []
    from .learning_runs import list_jobs
    return list_jobs(P, p, rid)


def catalog(P, p, kind="", q=""):
    p = project(P, p)
    if kind and kind not in KINDS:
        raise ApiError(400, "未知知识类型")
    items = []
    for k, reader in (("fact", _facts), ("lesson", _lessons), ("policy", _policies)):
        if not kind or k == kind:
            items.extend(reader(P, p))
    for item in items:
        rows = P.store.q("SELECT * FROM learning_revisions WHERE project_id=? AND kind=? AND origin_id=? ORDER BY rowid DESC",
                         (p["id"], item["kind"], item["origin_id"]))
        r = next((_decode(row) for row in rows if row["content"] == item["content"] and
                  json.loads(row["source"])["origin_fingerprint"] == item["fingerprint"]), None)
        from . import learning_decisions as D
        active = D._active(P, p, item)
        adopted = next((_decode(row) for row in rows if row["id"] == active), None)
        if adopted:
            r = adopted
        item["revision_id"] = r["id"] if r else ""
        item["stale"] = bool(r and not (revision_current(P, p, r) or (active == r["id"] and D.adopted_current(P, p, r))))
        item["active_revision_id"] = active
        jobs = _jobs(P, p, r["id"]) if r else []
        job = jobs[0] if jobs else {}
        item["machine"] = {"status": "stale" if item["stale"] else job.get("status", "unreviewed"), "job_id": job.get("id", "")}
        if item["kind"] == "policy":
            active = P.store.one("SELECT revision_id FROM learning_policy_active WHERE project_id=?", (p["id"],))
            item["human"]["status"] = "active" if active and any(x["id"] == active["revision_id"] for x in rows) else "draft"
    return {"project": {k: p[k] for k in ("id", "key", "name")},
            "items": [x for x in items if not q or q.casefold() in (x["title"] + "\n" + x["content"]).casefold()],
            "jobs": _jobs(P, p), "policy_specs": POLICY_SPECS, "readonly": True}


def detail(P, p, rid):
    p = project(P, p)
    r = revision(P, p, rid)
    history = [_decode(row) for row in P.store.q(
        "SELECT * FROM learning_revisions WHERE project_id=? AND kind=? AND origin_id=? ORDER BY rowid",
        (p["id"], r["kind"], r["origin_id"]))]
    decisions = P.store.q("SELECT * FROM learning_decisions WHERE project_id=? AND kind=? AND origin_id=? ORDER BY rowid",
                          (p["id"], r["kind"], r["origin_id"]))
    for d in decisions:
        d["payload"], d["result"] = json.loads(d["payload"]), json.loads(d["result"])
    active = None
    if r["kind"] == "policy":
        row = P.store.one("SELECT revision_id FROM learning_policy_active WHERE project_id=?", (p["id"],))
        active = row["revision_id"] if row else None
    elif r["kind"] == "fact":
        from . import learning_facts
        active = learning_facts.active_revision(P, p, r["origin_id"])
    elif r["kind"] == "lesson" and hasattr(learn, "active_revision"):
        active = learn.active_revision(P.data_dir, r["origin_id"])
    jobs = _jobs(P, p, rid)
    if jobs:
        from . import learning_runs
        jobs = [learning_runs.get(P, p, j["id"]) for j in jobs]
    from . import learning_decisions as D
    current = revision_current(P, p, r) or (active == r["id"] and D.adopted_current(P, p, r))
    try:
        token = D._token(P, p, r)
    except ApiError:
        token = None
    return {"revision": r, "current": current, "jobs": jobs, "expected_token": token,
            "history": history, "decisions": decisions, "expected_active": active, "active_revision_id": active}
