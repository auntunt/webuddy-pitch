"""Small request helpers shared by the handler and the preview proxy."""
from __future__ import annotations



def _length(h) -> int:
    try:
        n = int(h.headers.get("Content-Length") or 0)
    except ValueError:
        return -1
    return n


def _cookie(header: str, name: str) -> str:
    for part in header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""
