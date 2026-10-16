"""Evidence packages: an append-only, hash-chained record of what was checked and who signed.

A ticket's acceptance used to be a status change that left nothing behind. An evidence package is the thing
left behind: one JSON line per record (the snapshot taken when the change is handed over for acceptance, a
screenshot added, an internal review, a sign-off link issued, the signature or the rejection). Each record
carries the hash of the one before it, so editing or deleting any line breaks every hash after it, and
`check` says where. The package belongs to the client; `html` renders it as a single page they can keep.

Used by the platform (tmh/platform/signoff.py, one package per ticket) and the CLI (`tmh accept evidence`,
one package per task contract).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

GENESIS = "0" * 64


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(rec: dict) -> str:
    return hashlib.sha256(canon({k: v for k, v in rec.items() if k != "hash"}).encode("utf-8")).hexdigest()


def read(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"kind": "unreadable", "raw": line[:200]})
    return out


def check(recs: list[dict]) -> tuple[bool, str]:
    """(intact, problem): every record's hash matches its content and links to the one before it."""
    prev = GENESIS
    for i, r in enumerate(recs, 1):
        if r.get("kind") == "unreadable":
            return False, "第 %d 条记录不是合法 JSON（被改过）" % i
        if r.get("seq") != i or r.get("prev") != prev:
            return False, "第 %d 条记录的顺序或前一条哈希对不上（有记录被删除、插入或调换）" % i
        if digest(r) != r.get("hash"):
            return False, "第 %d 条记录（%s）的内容和哈希对不上（被改过）" % (i, r.get("kind"))
        prev = r["hash"]
    return True, ""


def head(recs: list[dict]) -> str:
    return recs[-1]["hash"] if recs else GENESIS


def append(path: Path, kind: str, by: str, data: dict) -> dict:
    """Add one record. Refuses to extend a chain that no longer checks out: a broken package stays visibly broken."""
    path = Path(path)
    recs = read(path)
    ok, why = check(recs)
    if not ok:
        raise ValueError("证据包已被改动，不能再追加：%s" % why)
    rec = {"seq": len(recs) + 1, "ts": now(), "kind": kind, "by": by or "", "data": data, "prev": head(recs)}
    rec["hash"] = digest(rec)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def latest(recs: list[dict], kind: str) -> dict | None:
    for r in reversed(recs):
        if r.get("kind") == kind:
            return r
    return None


def since(recs: list[dict], seq: int) -> list[dict]:
    return [r for r in recs if r.get("seq", 0) > seq]


# ---------------------------------------------------------------- page

CSS = ("*{box-sizing:border-box}body{font:15px/1.7 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;color:#1d2433;background:#fff;"
       "max-width:860px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 4px;text-wrap:balance}"
       "h2{font-size:16px;margin:28px 0 8px;padding-top:12px;border-top:1px solid #e3e7ef}.sub{color:#5b6475;font-size:13px}"
       "table{border-collapse:collapse;width:100%;margin:8px 0;font-variant-numeric:tabular-nums}"
       "th,td{border:1px solid #dfe3eb;padding:6px 10px;text-align:left;vertical-align:top}th{background:#f4f6fa;font-weight:600}"
       ".wrap{overflow-x:auto}.ok{color:#1a7f37}.bad{color:#c62828}.warn{color:#9a6700}.tag{display:inline-block;padding:0 8px;border-radius:10px;"
       "font-size:12px;background:#eef1f6}.seal{border:2px solid #1a7f37;border-radius:8px;padding:12px 16px;margin:12px 0}"
       ".seal.bad{border-color:#c62828}img{max-width:100%;border:1px solid #dfe3eb;border-radius:4px;margin:4px 0}"
       "code{background:#f1f3f7;padding:0 4px;border-radius:3px;word-break:break-all}ul{padding-left:20px}"
       "@media print{body{padding:0}h2{break-after:avoid}table{break-inside:avoid}}")


def page(title: str, body: str, extra_css: str = "") -> str:
    import html as H
    return ("<!doctype html><html lang=zh><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<meta name=robots content=noindex><title>%s</title><style>%s%s</style><body>%s</body></html>" % (H.escape(title), CSS, extra_css, body))


# ---------------------------------------------------------------- export for third parties
# The package leaves webuddy as an in-toto Statement v1 (https://in-toto.io/Statement/v1): the subject is the
# chain's head hash (and the commit the change landed in, when known), the predicate carries every record, so
# anyone can recompute the chain without webuddy. Unsigned for now: it proves the records were not changed after
# export by matching the head hash someone kept (the sign-off page shows it), not who exported them.
STATEMENT = "https://in-toto.io/Statement/v1"
PREDICATE = "https://webuddy.ai/evidence/v1"


def statement(name: str, recs: list[dict], summary: dict, commit: str = "") -> dict:
    subject = [{"name": name, "digest": {"sha256": head(recs)}}]
    if commit and len(commit) == 40:
        subject.append({"name": name + " 的代码提交", "digest": {"gitCommit": commit}})
    return {"_type": STATEMENT, "subject": subject, "predicateType": PREDICATE,
            "predicate": {"exported": now(), "summary": summary, "records": recs}}


def verify_statement(st: dict, expect_head: str = "") -> tuple[bool, list[str]]:
    """What a client's auditor runs on an exported package: is it ours, is the chain intact, does its head match
    the subject (and, given, the head they wrote down when they signed)."""
    notes = []
    if st.get("_type") != STATEMENT or st.get("predicateType") != PREDICATE:
        return False, ["不是 webuddy 导出的证据包（类型不对）"]
    recs = (st.get("predicate") or {}).get("records") or []
    ok, why = check(recs)
    if not ok:
        return False, [why]
    notes.append("哈希链完整：%d 条记录，逐条重算一致" % len(recs))
    sha = next((x["digest"].get("sha256") for x in st.get("subject") or [] if "sha256" in (x.get("digest") or {})), "")
    if sha != head(recs):
        return False, notes + ["声明里的摘要 %s 和记录算出来的 %s 对不上" % (sha[:12], head(recs)[:12])]
    notes.append("声明摘要和记录一致：%s" % sha)
    if expect_head:
        if not sha.startswith(expect_head.lower()):
            return False, notes + ["和你手里记下的哈希 %s 对不上：签收之后记录变过" % expect_head]
        notes.append("和你记下的哈希一致")
    return True, notes
