"""Per-file parse cache so re-analysis of a large repository only re-parses changed files.

Each extractor (project map, code index) stores its per-file result keyed by the
file's size+mtime and content hash in `.tmh/cache/parse.db` (SQLite, stdlib).
On a 300k-line project the first run parses everything; later runs read unchanged
files' results straight from the cache. The cache is derived data: deleting it
only costs time.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import tmh_dir
from .fsutil import open_db

SCHEMA_VERSION = "7"


class ParseCache:
    def __init__(self, root: Path):
        self.root = root.resolve()
        d = tmh_dir(self.root) / "cache"
        d.mkdir(parents=True, exist_ok=True)
        self.db = open_db(d / "parse.db")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)")
        ver = self.db.execute("SELECT v FROM meta WHERE k='schema'").fetchone()
        if not ver or ver[0] != SCHEMA_VERSION:
            self.db.execute("DROP TABLE IF EXISTS entries")
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('schema', ?)", (SCHEMA_VERSION,))
        self.db.execute("CREATE TABLE IF NOT EXISTS entries(kind TEXT, path TEXT, stat TEXT, sha TEXT, payload TEXT, PRIMARY KEY(kind, path))")
        self.hits = 0
        self.miss_paths: set = set()
        self.seen: dict[str, set] = {}

    def get(self, kind: str, rp: str, p: Path, compute):
        """Return compute(text) for file p, cached. compute receives the decoded text (or None)."""
        from .fsutil import read_text
        self.seen.setdefault(kind, set()).add(rp)
        try:
            st = p.stat()
        except OSError:
            return None
        stat = "%d:%d" % (st.st_size, st.st_mtime_ns)
        row = self.db.execute("SELECT stat, sha, payload FROM entries WHERE kind=? AND path=?", (kind, rp)).fetchone()
        if row and row[0] == stat:
            self.hits += 1
            return json.loads(row[2])
        try:
            raw = p.read_bytes()
        except OSError:
            return None
        sha = hashlib.sha1(raw).hexdigest()
        if row and row[1] == sha:
            self.db.execute("UPDATE entries SET stat=? WHERE kind=? AND path=?", (stat, kind, rp))
            self.hits += 1
            return json.loads(row[2])
        self.miss_paths.add(rp)
        val = compute(read_text(p))
        self.db.execute("INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?)", (kind, rp, stat, sha, json.dumps(val, ensure_ascii=False)))
        return val

    @property
    def misses(self) -> int:
        return len(self.miss_paths)

    def close(self) -> None:
        for kind, paths in self.seen.items():  # forget deleted files
            known = [r[0] for r in self.db.execute("SELECT path FROM entries WHERE kind=?", (kind,))]
            gone = [(kind, k) for k in known if k not in paths]
            self.db.executemany("DELETE FROM entries WHERE kind=? AND path=?", gone)
        self.db.commit()
        self.db.close()
