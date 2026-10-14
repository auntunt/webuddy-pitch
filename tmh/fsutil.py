"""Repository traversal, tolerant text decoding and small git helpers (stdlib only)."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from pathlib import Path
from typing import Iterator

SKIP_DIRS = {
    ".git", ".svn", ".hg", ".idea", ".vs", ".vscode", ".tmh", ".claude", ".agents", ".codex",
    "node_modules", "bower_components", "mvn-repo", "target", "build", "out", "bin", "obj", "dist",
    ".gradle", ".mvn", "packages", "__pycache__", ".venv", "venv", "logs", "TestResults", "vendor",
}
TEXT_SUFFIXES = {
    ".java", ".kt", ".groovy", ".scala", ".xml", ".properties", ".yml", ".yaml", ".json", ".sql",
    ".jsp", ".jspf", ".tag", ".ftl", ".vm", ".html", ".htm", ".js", ".ts", ".vue", ".css",
    ".cs", ".vb", ".fs", ".cshtml", ".vbhtml", ".razor", ".aspx", ".ascx", ".asax", ".ashx", ".asmx",
    ".master", ".svc", ".config", ".csproj", ".vbproj", ".fsproj", ".sln", ".props", ".targets",
    ".gradle", ".kts", ".sh", ".bat", ".cmd", ".ps1", ".conf", ".ini", ".txt", ".md", ".jrxml",
    ".pkb", ".pks", ".prc", ".trg", ".xmi", ".asp", ".dockerfile", ".toml", ".edmx", ".go", ".mod",
}
TEXT_NAMES = {"Dockerfile", "Jenkinsfile", "Makefile", "packages.config", "pom.xml", "mvnw", "gradlew"}
MAX_FILE_BYTES = 2 * 1024 * 1024


def open_db(path, **kw):
    """sqlite3.connect with a journal mode that works on mounted/synced folders.

    The default DELETE journal fails ("disk I/O error") on mounts that forbid
    unlinking files (sandboxed VMs, some network/sync drives); TRUNCATE keeps the
    journal file and only empties it, which works everywhere.
    """
    import sqlite3
    db = sqlite3.connect(str(path), **kw)
    try:
        db.execute("PRAGMA journal_mode=TRUNCATE")
    except sqlite3.Error:
        pass
    return db


def remove_file(p: Path) -> None:
    """Delete a derived file; where deleting is not allowed, empty it instead (readers treat empty as absent)."""
    try:
        p.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        p.write_bytes(b"")


def replace_file(src: Path, dst: Path) -> None:
    """Atomic rename when the filesystem allows it, else copy the bytes over."""
    try:
        src.replace(dst)
    except OSError:
        dst.write_bytes(src.read_bytes())
        try:
            src.unlink()
        except OSError:
            pass


def iter_files(root: Path, include_binary_names: bool = False) -> Iterator[Path]:
    """Yield repository files, pruning build output and VCS directories."""
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if is_text_candidate(p) or include_binary_names:
                yield p


def is_text_candidate(p: Path) -> bool:
    return p.suffix.lower() in TEXT_SUFFIXES or p.name in TEXT_NAMES


_JAVA_UESC = None


def _java_unescape(text: str) -> str:
    """Decompiled Java often spells Chinese as \\u5355\\u636e. Java itself translates these before lexing,
    so decoding them (non-ASCII only, never quotes/newlines) keeps meaning and line numbers while making
    messages, comments and SQL readable and searchable by their Chinese business terms."""
    global _JAVA_UESC
    import re
    if _JAVA_UESC is None:
        _JAVA_UESC = re.compile(r"(?<!\\)((?:\\\\)*)\\u+([0-9a-fA-F]{4})")

    def sub(m):
        cp = int(m.group(2), 16)
        return m.group(1) + chr(cp) if cp >= 0x80 and not 0xD800 <= cp <= 0xDFFF else m.group(0)
    return _JAVA_UESC.sub(sub, text)


def read_text(p: Path) -> str | None:
    """Decode a source file. Legacy Chinese projects are often GBK, so fall back to it."""
    text = _read_text(p)
    if text and "\\u" in text and p.suffix == ".java":
        text = _java_unescape(text)
    return text


def _read_text(p: Path) -> str | None:
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            return None
        raw = p.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw[:4096] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return None
    for enc in ("utf-8-sig", "utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def rel(root: Path, p: Path) -> str:
    return p.resolve().relative_to(root.resolve()).as_posix()


def match_any(path: str, globs: list[str]) -> bool:
    """Glob match where "**/" may also match zero directories and bare names match basenames."""
    name = path.rsplit("/", 1)[-1]
    for g in globs:
        if fnmatch.fnmatch(path, g) or fnmatch.fnmatch("/" + path, g) or ("/" not in g and fnmatch.fnmatch(name, g)):
            return True
        if g.startswith("**/") and fnmatch.fnmatch(path, g[3:]):
            return True
    return False


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_head(root: Path) -> str | None:
    return git(root, "rev-parse", "HEAD")


def git_changed_files(root: Path, base: str | None) -> list[str] | None:
    """Files changed relative to base (committed + staged + unstaged + untracked)."""
    if git(root, "rev-parse", "--is-inside-work-tree") != "true":
        return None
    out: set[str] = set()
    if base:
        d = git(root, "diff", "--name-only", base)
        if d is None:
            return None
        out.update(x for x in d.splitlines() if x)
    else:
        out.update(x for x in (git(root, "diff", "--name-only", "HEAD") or "").splitlines() if x)
    out.update(x for x in (git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines() if x)
    return sorted(out)


def git_changed_lines(root: Path, base: str | None) -> dict[str, list[tuple[int, int]]]:
    """New-side line ranges changed relative to base, per file (untracked files: whole file)."""
    out: dict[str, list[tuple[int, int]]] = {}
    d = git(root, "diff", "-U0", "--no-color", base or "HEAD") or ""
    cur = None
    for line in d.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
            if cur:
                out.setdefault(cur, [])
        elif line.startswith("@@") and cur:
            m = __import__("re").match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                start, n = int(m.group(1)), int(m.group(2) or 1)
                out[cur].append((start, start + max(n, 1) - 1))
    for f in (git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines():
        if f:
            out[f] = [(1, 10 ** 9)]
    return out
