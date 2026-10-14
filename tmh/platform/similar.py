"""Similar tickets (相似工单查重): before a new ticket is opened, and on every ticket, show the
earlier tickets that read the same, so a repeat question gets the old answer instead of a new person.

Plain tf-idf over each ticket's title (weighted double) and description, using the same word
splitting as the knowledge-base search (Chinese bigrams, camelCase and snake_case parts).
No model call: it has to run on every keystroke and on intranet machines.
"""
from __future__ import annotations

import math
from collections import Counter

from ..context import terms

DONE = ("done", "closed")


def _vec(title: str, body: str) -> Counter:
    c = Counter(terms(title or ""))
    for k in list(c):
        c[k] *= 2
    c.update(terms((body or "")[:3000]))
    return c


def similar(tickets: list[dict], title: str, body: str = "", exclude: int | None = None, limit: int = 5, floor: float = 0.18) -> list[dict]:
    docs = [(t, _vec(t.get("title", ""), t.get("body", ""))) for t in tickets if t.get("id") != exclude]
    q = _vec(title, body)
    if not docs or not q:
        return []
    df = Counter()
    for _, v in docs:
        df.update(v.keys())
    n = len(docs) + 1
    idf = lambda w: math.log((n + 1) / (df.get(w, 0) + 1)) + 1

    def w(v):
        return {k: (1 + math.log(c)) * idf(k) for k, c in v.items()}

    qw = w(q)
    qn = math.sqrt(sum(x * x for x in qw.values()))
    out = []
    for t, v in docs:
        dw = w(v)
        dot = sum(qw[k] * dw[k] for k in qw.keys() & dw.keys())
        if not dot:
            continue
        s = dot / (qn * math.sqrt(sum(x * x for x in dw.values())))
        if s >= floor:
            shared = sorted(qw.keys() & dw.keys(), key=lambda k: -qw[k] * dw[k])[:5]
            out.append({"key": t["key"], "title": t["title"], "status": t["status"], "assignee": t.get("assignee", ""),
                        "updated": t.get("updated", ""), "score": round(s, 3), "shared": shared,
                        "external": (t.get("external") or {}).get("key", "")})
    out.sort(key=lambda r: -r["score"])
    return out[:limit]
