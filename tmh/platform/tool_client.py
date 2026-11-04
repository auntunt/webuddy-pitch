"""Downloadable personal-tool client: the CLI and stdio MCP bridge as one wheel.

Members install it on their own computer, import the credential issued by the
tools page and point Codex, Claude Code or Cursor at the generated config. The
wheel carries only the client modules, never server code or data.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

from .. import __version__

NAME = "webuddy_client"
FILENAME = f"{NAME}-{__version__}-py3-none-any.whl"
MODULES = ("__init__.py", "agent_contract.py", "workbench.py", "workbench_client.py",
           "workbench_credentials.py", "workbench_entry.py", "workbench_mcp.py")
SITE = "workbench_site.json"
_cache = {}


def _digest(data):
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def wheel(endpoint=None):
    """Return (filename, bytes); deterministic for the running release.

    endpoint (https://host/t/<tenant>) is written into the client so a bare
    `webuddy` knows which server it came from.
    """
    root = Path(__file__).resolve().parent.parent
    sources = [("tmh/" + name, (root / name).read_bytes()) for name in MODULES]
    if endpoint:
        sources.append(("tmh/" + SITE, json.dumps({"endpoint": endpoint}).encode()))
    key = hashlib.sha256(b"".join(data for _, data in sources)).hexdigest()
    if key not in _cache:
        info = f"{NAME}-{__version__}.dist-info/"
        files = sources + [
            (info + "METADATA", (f"Metadata-Version: 2.1\nName: webuddy-client\nVersion: {__version__}\n"
                                 "Summary: Webuddy 个人工具连接客户端（命令行与 MCP）\n"
                                 "Requires-Python: >=3.10\nRequires-Dist: mcp<2,>=1.30\n").encode()),
            (info + "WHEEL", b"Wheel-Version: 1.0\nGenerator: tmh\nRoot-Is-Purelib: true\nTag: py3-none-any\n"),
            (info + "entry_points.txt", b"[console_scripts]\nwebuddy = tmh.workbench:main\n"),
        ]
        record = "".join(f"{path},{_digest(data)},{len(data)}\n" for path, data in files)
        files.append((info + "RECORD", (record + info + "RECORD,,\n").encode()))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path, data in files:
                entry = zipfile.ZipInfo(path, date_time=(2020, 1, 1, 0, 0, 0))
                entry.external_attr = 0o644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
        _cache.clear()
        _cache[key] = buffer.getvalue()
    return FILENAME, _cache[key]
