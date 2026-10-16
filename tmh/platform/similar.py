"""Similar tickets (相似工单查重): before a new ticket is opened, and on every ticket, show the
earlier tickets that read the same, so a repeat question gets the old answer instead of a new person.

Plain tf-idf over each ticket's title (weighted double) and description, using the same word
splitting as the knowledge-base search (Chinese bigrams, camelCase and snake_case parts).
No model call: it has to run on every keystroke and on intranet machines.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from ..context import terms

DONE = ("done", "closed")
# Words every complaint uses; matched on them, two unrelated tickets read 20% alike ("还是", "今天", "赶紧").
FILLER = {"还是", "一直", "没有", "今天", "昨天", "现在", "时候", "我们", "你们", "他们", "已经", "但是", "发现", "问题", "赶紧", "一下", "看一",
          "麻烦", "尽快", "处理", "出现", "怎么", "不了", "不能", "之后", "以后", "各位", "位好", "还有", "就是", "应该", "好像", "影响"}


_FILL = re.compile("|".join(sorted(FILLER, key=len, reverse=True)))


def _clean(text: str) -> str:
    """Filler cut out of the text, not just out of the word list, so 还是一直 leaves no 是一 behind."""
    return _FILL.sub(" ", text or "")


def _terms(text: str) -> list[str]:
    return terms(_clean(text))


def _vec(title: str, body: str) -> Counter:
    c = Counter(_terms(title or ""))
    for k in list(c):
        c[k] *= 2
    c.update(_terms((body or "")[:3000]))
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
            shared = _phrases(_clean(title + " " + (body or "")[:3000]), qw.keys() & dw.keys(), lambda k: qw.get(k, 0) * dw.get(k, 0))
            out.append({"key": t["key"], "title": t["title"], "status": t["status"], "assignee": t.get("assignee", ""),
                        "updated": t.get("updated", ""), "score": round(s, 3), "shared": shared,
                        "external": (t.get("external") or {}).get("key", "")})
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


def _phrases(text: str, common: set, weight) -> list[str]:
    """What the two tickets share, as words a person reads: overlapping bigrams joined back into the run they came
    from in the new ticket's text (供应+应商 → 供应商), heaviest first."""
    runs, start = [], None
    for i in range(len(text) + 1):
        if i < len(text) - 1 and text[i:i + 2] in common:
            start = i if start is None else start
        elif start is not None:
            a, b = start, i + 1  # the run covers text[a:b]
            runs.append(text[a:b])
            start = None
    score = {}
    for r in runs:
        score[r] = max(score.get(r, 0), sum(weight(r[j:j + 2]) for j in range(len(r) - 1)))
    words = [k for k in common if not any("\u4e00" <= ch <= "\u9fff" for ch in k)]  # identifiers, English words
    for w in words:
        score[w] = weight(w)
    # a run inside a longer one says nothing new
    keep = [r for r in score if not any(r != o and r in o for o in score)]
    return sorted(keep, key=lambda r: -score[r])[:5]
