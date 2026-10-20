#!/usr/bin/env python3
"""把一个平台数据目录里的项目并进另一个，成为同一个平台里的多个项目。

用法：merge_data.py <并入到的数据目录> <被并入的数据目录>
被并入那边的编号（项目、工单、记录、运行……）整体往后挪，接在目标已有编号之后；
引用这些编号的地方（外键、记录里的 "run"、经验里的 "run"、runs/<编号> 目录）一起改。
按项目键分开存的文件（evals/<键>.json、checks/<键>-*.json、reforms/<键>.json）原样拷过去。
autoflow.json 留目标的，改动行数上限改成按项目分开记（各用原来那边的值）。
目标里已有同一个项目键时不合并，直接报错退出。只用标准库，不读写其他地方。
"""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

TABLES = ["projects", "tickets", "events", "runs", "points", "chats", "matters", "sessions"]
REFS = {"project_id": "projects", "ticket_id": "tickets", "run_id": "runs", "matter_id": "matters", "session_id": "sessions"}
SKIP = {"platform.db", "platform.db-journal", "platform.db-wal", "platform.db-shm", "worktrees", ".DS_Store",
        "runs", "autoflow.json", "lessons.jsonl", "testbox-check.json", "surveys.json"}


def cols(c, t):
    return [(r[1], r[2], r[4]) for r in c.execute("PRAGMA table_info(%s)" % t)]


def shift_run(text, off):
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return text
    if isinstance(d, dict) and isinstance(d.get("run"), int) and not isinstance(d.get("run"), bool):
        d["run"] += off
        return json.dumps(d, ensure_ascii=False)
    return text


def load(f, default):
    try:
        return json.loads(Path(f).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def merge(dst: Path, src: Path) -> dict:
    a = sqlite3.connect(str(dst / "platform.db"))
    b = sqlite3.connect("file:%s?mode=ro" % (src / "platform.db"), uri=True)
    keys_a = [r[0] for r in a.execute("SELECT key FROM projects")]
    keys_b = [r[0] for r in b.execute("SELECT key FROM projects")]
    clash = set(keys_a) & set(keys_b)
    if clash:
        sys.exit("目标里已经有项目 %s，不合并" % "、".join(sorted(clash)))
    off = {t: a.execute("SELECT COALESCE(MAX(id), 0) FROM %s" % t).fetchone()[0] for t in TABLES}
    added = {}
    for t in TABLES:
        have = {n for n, _, _ in cols(a, t)}
        for n, typ, dflt in cols(b, t):  # a column only the newer side has yet
            if n not in have:
                a.execute("ALTER TABLE %s ADD COLUMN %s %s%s" % (t, n, typ, " DEFAULT %s" % dflt if dflt is not None else ""))
        names = [n for n, _, _ in cols(b, t)]
        rows = []
        for r in b.execute("SELECT %s FROM %s" % (",".join(names), t)):
            r = dict(zip(names, r))
            r["id"] += off[t]
            for k, ref in REFS.items():
                if r.get(k) is not None:
                    r[k] += off[ref]
            if t in ("events", "chats"):
                r["data"] = shift_run(r.get("data"), off["runs"])
            rows.append([r[n] for n in names])
        a.executemany("INSERT INTO %s (%s) VALUES (%s)" % (t, ",".join(names), ",".join("?" * len(names))), rows)
        added[t] = len(rows)
    a.commit()
    a.close()
    b.close()

    rd = dst / "runs"
    rd.mkdir(exist_ok=True)
    for d in sorted((src / "runs").iterdir()) if (src / "runs").is_dir() else []:
        if d.is_dir() and d.name.isdigit():
            to = rd / str(int(d.name) + off["runs"])
            if to.exists():
                sys.exit("runs/%s 已存在，数据库和运行目录对不上，停下" % to.name)
            shutil.copytree(str(d), str(to))
    for f in sorted(src.iterdir()):  # files kept per project key (evals, checks, reforms …)
        if f.name in SKIP:
            continue
        for x in ([f] if f.is_file() else [y for y in f.rglob("*") if y.is_file() and "wt" not in y.relative_to(f).parts[:1]]):
            to = dst / x.relative_to(src)
            if to.exists():
                print("  跳过已存在的 %s" % to.relative_to(dst))
                continue
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(x), str(to))
    if (src / "lessons.jsonl").exists():
        with open(dst / "lessons.jsonl", "a", encoding="utf-8") as out:
            for line in (src / "lessons.jsonl").read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.write(shift_run(line, off["runs"]) + "\n")
    sa, sb = load(dst / "surveys.json", {}), load(src / "surveys.json", {})
    if isinstance(sa, dict) and isinstance(sb, dict) and sb:
        sa.update({k: v for k, v in sb.items() if k not in sa})
        (dst / "surveys.json").write_text(json.dumps(sa, ensure_ascii=False), encoding="utf-8")
    fa, fb = load(dst / "autoflow.json", {}), load(src / "autoflow.json", {})
    lim = {}
    for ks, conf in ((keys_a, fa), (keys_b, fb)):
        m = conf.get("max_lines", 400)
        for k in ks:
            lim[k] = m.get(k, m.get("*", 400)) if isinstance(m, dict) else m
    lim["*"] = 400
    fa["max_lines"] = lim
    fa["max_agents"] = max(int(fa.get("max_agents", 4) or 0), int(fb.get("max_agents", 4) or 0))
    for k, v in fb.items():
        fa.setdefault(k, v)
    (dst / "autoflow.json").write_text(json.dumps(fa, ensure_ascii=False), encoding="utf-8")
    return {"projects": keys_a + keys_b, "offsets": off, "added": added}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    r = merge(Path(sys.argv[1]), Path(sys.argv[2]))
    print("  合并后项目：%s" % "、".join(r["projects"]))
    print("  并入：" + "，".join("%s %d" % (t, n) for t, n in r["added"].items() if n))
