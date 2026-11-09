"""Platform-enforced read-only check for steps that must not change files.

Windows sandboxes block shell commands for some engines, so read-only steps run with
the engine's full access there and this check enforces read-only instead. It compares
the work tree before and after the run; it reports changes and never reverts them,
since the person may have edits of their own.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def _git(workdir: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(workdir), *args], check=True, capture_output=True).stdout


def snapshot(workdir: Path) -> dict:
    """Status plus a content hash of every modified or untracked file in the work tree."""
    status = _git(workdir, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    hashes = {}
    for entry in status.split(b"\0"):
        if not entry:
            continue
        name = entry[3:].decode("utf-8", "replace")
        path = workdir / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
    return {"status": status, "hashes": hashes}


def changed(before: dict, after: dict) -> list[str]:
    names = set(before["hashes"]) | set(after["hashes"])
    diff = [n for n in sorted(names) if before["hashes"].get(n) != after["hashes"].get(n)]
    if before["status"] != after["status"] and not diff:
        diff = ["（工作区状态变化）"]
    return diff
