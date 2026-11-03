"""Ops tickets (运维): find earlier tickets and experience that read alike, look at the client's business data
read-only, write down what was found, and close it out without touching the code when the cause is data, config or use.

The data source is configured by whoever runs the server, never through the UI:
<data>/datasources.json  {"BID": {"kind": "sqlite", "path": "/srv/bid/bid.db"} | {"kind": "postgres", "dsn": "..."}}
Queries are one SELECT/WITH statement; sqlite opens the file read-only with query_only on, postgres runs in a
read-only transaction with a statement timeout. At most ROWS rows come back. Every query goes on the ticket timeline.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

from .errors import ApiError

ROWS = 200
SECONDS = 10
CAUSES = {"data": "数据问题", "config": "配置问题", "usage": "使用问题", "env": "环境问题", "code": "需要改代码"}
_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_WRITE = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum|grant|revoke|copy|call|merge|lock|reindex)\b", re.IGNORECASE)


def source(data_dir, project: str) -> dict:
    f = Path(data_dir) / "datasources.json"
    try:
        c = json.loads(f.read_text(encoding="utf-8")).get(project.upper()) or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return c if c.get("kind") in ("sqlite", "postgres") else {}


def clean_sql(sql: str) -> str:
    s = _COMMENT.sub(" ", str(sql or "")).strip().rstrip(";").strip()
    if not s:
        raise ApiError(400, "写一条 SELECT 查询")
    if ";" in s:
        raise ApiError(400, "一次只能查一条语句")
    if not re.match(r"(?is)^(select|with)\b", s) or _WRITE.search(s):
        raise ApiError(400, "只能只读查询：以 SELECT 或 WITH 开头，不能有改数据或改结构的语句")
    return s[:4000]


def _sqlite(c: dict, sql: str):
    db = sqlite3.connect("file:%s?mode=ro" % Path(c["path"]).resolve(), uri=True, timeout=2)
    try:
        db.execute("PRAGMA query_only=ON")
        end = time.monotonic() + SECONDS
        db.set_progress_handler(lambda: 1 if time.monotonic() > end else 0, 10000)
        cur = db.execute(sql)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(ROWS + 1)
        return cols, [list(r) for r in rows]
    finally:
        db.close()


def _postgres(c: dict, sql: str):
    env = dict(os.environ, PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=%d" % (SECONDS * 1000))
    q = "BEGIN READ ONLY;\nCOPY (SELECT * FROM (%s) q LIMIT %d) TO STDOUT WITH CSV HEADER;\nROLLBACK;" % (sql, ROWS + 1)
    p = subprocess.run(["psql", c["dsn"], "-X", "-q", "-v", "ON_ERROR_STOP=1"], input=q, capture_output=True, text=True,
                       timeout=SECONDS + 5, env=env, check=False)
    if p.returncode:
        raise ValueError((p.stderr or "psql 失败").strip()[-400:])
    rows = list(csv.reader(io.StringIO(p.stdout)))
    return (rows[0] if rows else []), rows[1:]


def query(P, t: dict, sql: str, by: str) -> dict:
    project = t["key"].rsplit("-", 1)[0]
    c = source(P.data_dir, project)
    if not c:
        raise ApiError(409, "项目 %s 还没有配置只读数据源（由服务器管理员在 datasources.json 里配置）" % project)
    s = clean_sql(sql)
    started = time.monotonic()
    try:
        cols, rows = (_sqlite if c["kind"] == "sqlite" else _postgres)(c, s)
    except (sqlite3.Error, ValueError, OSError, subprocess.SubprocessError) as e:
        P.store.event(t["id"], by, "ops_query", "查询出错：%s" % str(e)[:300], {"sql": s, "error": str(e)[:300]})
        raise ApiError(400, "查询出错：%s" % str(e)[:300]) from e
    more = len(rows) > ROWS
    rows = [[v if isinstance(v, (int, float)) or v is None else str(v)[:300] for v in r] for r in rows[:ROWS]]
    ms = int((time.monotonic() - started) * 1000)
    P.store.event(t["id"], by, "ops_query", "只读查询 %d 行%s" % (len(rows), "（只显示前 %d 行）" % ROWS if more else ""),
                  {"sql": s, "columns": cols, "rows": rows[:20], "count": len(rows), "more": more, "ms": ms})
    return {"columns": cols, "rows": rows, "count": len(rows), "more": more, "ms": ms}


def _lesson_text(x: dict) -> str:
    return "\n".join(str(x.get(k) or "") for k in ("symptom", "fix", "verify", "note"))


def look(P, t: dict) -> dict:
    """Earlier tickets and experience cards that read like this one, the queries run so far and the conclusion."""
    from . import learn
    from .similar import similar
    project = t["key"].rsplit("-", 1)[0]
    p = P.project(project)
    pool = [x for x in P.store.tickets(project_id=p["id"], limit=5000) if x["id"] != t["id"]]
    tickets = similar(pool, t["title"], t.get("body") or "", exclude=t["id"], limit=5, floor=0.12)
    by_key = {x["key"]: x for x in pool}
    for r in tickets:
        r["type"] = by_key.get(r["key"], {}).get("type", "")
        ends = [e for e in P.store.events(by_key[r["key"]]["id"]) if e["kind"] == "ops_conclusion"] if r["key"] in by_key else []
        if ends:
            r["conclusion"] = ends[-1]["body"]
    cards = [x for x in learn.lessons(P.data_dir, project) if x.get("status") in ("active", "candidate", "probation")]
    fake = [{"id": i, "key": c["id"], "title": c.get("title") or c.get("symptom", "")[:60], "body": _lesson_text(c), "status": c.get("status", "")}
            for i, c in enumerate(cards)]
    hits = similar(fake, t["title"], t.get("body") or "", limit=5, floor=0.12)
    by_id = {c["id"]: c for c in cards}
    lessons = [{"id": h["key"], "title": h["title"], "status": h["status"], "score": h["score"],
                "symptom": by_id[h["key"]].get("symptom", "")[:300], "fix": (by_id[h["key"]].get("fix") or "")[:600],
                "kind": by_id[h["key"]].get("kind", "")} for h in hits]
    ev = P.store.events(t["id"])
    c = source(P.data_dir, project)
    return {"datasource": {"kind": c["kind"]} if c else None, "tickets": tickets, "lessons": lessons,
            "queries": [dict(e["data"] or {}, ts=e["ts"], by=e["author"], text=e["body"]) for e in ev if e["kind"] == "ops_query"][-20:],
            "conclusion": next((dict(e["data"] or {}, ts=e["ts"], by=e["author"], text=e["body"]) for e in reversed(ev) if e["kind"] == "ops_conclusion"), None),
            "causes": CAUSES}


def conclude(P, t: dict, cause: str, text: str, fix: str, by: str, distill: bool) -> dict:
    """Write down what it was. Not code: it closes out without a code change, and may become an experience candidate
    that a person adopts on the knowledge page before it is ever used."""
    from . import learn
    if cause not in CAUSES:
        raise ApiError(400, "原因选一个：" + "、".join(CAUSES.values()))
    text, fix = str(text or "").strip()[:2000], str(fix or "").strip()[:2000]
    if not text:
        raise ApiError(400, "写明查到了什么")
    q = [e for e in P.store.events(t["id"]) if e["kind"] == "ops_query" and not (e["data"] or {}).get("error")]
    data = {"cause": cause, "fix": fix, "queries": len(q), "code_change": cause == "code"}
    out = {"cause": cause, "label": CAUSES[cause], "lesson": None}
    if distill and cause != "code":
        project = t["key"].rsplit("-", 1)[0]
        last = (q[-1]["data"] or {}).get("sql", "") if q else ""
        card = learn.add_lesson(P.data_dir, {
            "source_key": "ops:%s" % t["key"], "project": project, "ticket": t["key"], "title": t["title"], "kind": "ops",
            "status": "candidate", "by": by, "flows": (t.get("links") or {}).get("flows") or [],
            "symptom": ("%s。%s" % (t["title"], (t.get("body") or "")[:300])).strip("。"),
            "fix": "原因：%s。%s\n处理：%s\n不改代码。" % (CAUSES[cause], text, fix or "（未写）"),
            "verify": ("排查用的只读查询：\n" + last) if last else "", "note": text})
        out["lesson"] = card["id"]
        data["lesson"] = card["id"]
    P.store.event(t["id"], by, "ops_conclusion", "%s：%s" % (CAUSES[cause], text), data)
    return out
