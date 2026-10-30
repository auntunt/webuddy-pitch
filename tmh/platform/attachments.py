"""What comes with a requirement besides the words: screenshots and documents, kept as they were.

Each file is stored once by its SHA-256. Screenshots go next to the evidence package's files (signoff.edir), so the
ticket's evidence page serves them; documents stay under <data>/intake/files. Text is pulled out of documents here,
without a model and without third-party packages (PDF only when `pypdf` is installed): what a model or the rules read
is exactly what is recorded with the conversation. Nothing here interprets the content.
"""
from __future__ import annotations

import base64
import hashlib
import re
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from .errors import ApiError

IMAGE = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
DOCS = {"txt", "md", "csv", "log", "json", "docx", "xlsx", "pdf"}
MAX_FILES = 8
MAX_IMAGE = 3 * 1024 * 1024
MAX_DOC = 10 * 1024 * 1024
MAX_TEXT = 20000
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _docx(raw: bytes) -> str:
    with zipfile.ZipFile(BytesIO(raw)) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    lines = []
    for para in root.iter(_W + "p"):
        t = "".join(x.text or "" for x in para.iter(_W + "t"))
        if t.strip():
            lines.append(t)
    return "\n".join(lines)


def _xlsx(raw: bytes) -> str:
    with zipfile.ZipFile(BytesIO(raw)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).iter(_S + "si"):
                shared.append("".join(x.text or "" for x in si.iter(_S + "t")))
        sheets = sorted(n for n in z.namelist() if re.match(r"^xl/worksheets/sheet\d+\.xml$", n))
        lines = []
        for n in sheets:
            lines.append("# " + n.rsplit("/", 1)[1][:-4])
            for row in ElementTree.fromstring(z.read(n)).iter(_S + "row"):
                cells = []
                for c in row.iter(_S + "c"):
                    v = c.find(_S + "v")
                    val = v.text if v is not None and v.text else "".join(x.text or "" for x in c.iter(_S + "t"))
                    if c.get("t") == "s" and val.isdigit() and int(val) < len(shared):
                        val = shared[int(val)]
                    cells.append(val)
                if any(x.strip() for x in cells):
                    lines.append("\t".join(cells))
    return "\n".join(lines)


def _pdf(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("服务器没有安装 pypdf，PDF 只保存原件、没有抽取文字")
    return "\n".join((pg.extract_text() or "") for pg in PdfReader(BytesIO(raw)).pages)


def extract(ext: str, raw: bytes) -> str:
    if ext == "docx":
        return _docx(raw)
    if ext == "xlsx":
        return _xlsx(raw)
    if ext == "pdf":
        return _pdf(raw)
    return _decode(raw)


def image_dir(data_dir: Path) -> Path:
    from .signoff import edir
    return edir(data_dir) / "files"


def doc_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "intake" / "files"


def save(data_dir: Path, files: list) -> list:
    """[{name, data: data URL or base64, type?}] → [{name, sha256, file, kind, type, bytes, text, note}]."""
    if not files:
        return []
    if not isinstance(files, list) or len(files) > MAX_FILES:
        raise ApiError(400, f"附件最多 {MAX_FILES} 个")
    out = []
    for f in files:
        if not isinstance(f, dict):
            raise ApiError(400, "附件格式不对")
        name = re.sub(r"[\\/\x00-\x1f]", "_", str(f.get("name") or "附件"))[:120]
        data, mime = str(f.get("data") or ""), str(f.get("type") or "")
        m = re.match(r"^data:([\w.+/-]*)(?:;[^,]*)?;base64,(.*)$", data, re.DOTALL)
        if m:
            mime, data = m.group(1) or mime, m.group(2)
        try:
            raw = base64.b64decode(data, validate=False)
        except (ValueError, TypeError):
            raise ApiError(400, f"附件「{name}」不是有效的 base64")
        if not raw:
            raise ApiError(400, f"附件「{name}」是空的")
        sha = hashlib.sha256(raw).hexdigest()
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if mime in IMAGE:
            if len(raw) > MAX_IMAGE:
                raise ApiError(413, f"截图「{name}」不能超过 3MB")
            file = f"{sha}.{IMAGE[mime]}"
            target, kind, text, note = image_dir(data_dir) / file, "image", "", ""
        elif ext in DOCS:
            if len(raw) > MAX_DOC:
                raise ApiError(413, f"文档「{name}」不能超过 10MB")
            file = f"{sha}.{ext}"
            target, kind, note = doc_dir(data_dir) / file, "doc", ""
            try:
                text = extract(ext, raw)
            except Exception as e:  # noqa: BLE001 - the original is still kept; say why there is no text
                text, note = "", str(e) if isinstance(e, ValueError) and str(e) else f"没能读出文字（{type(e).__name__}）"
            if len(text) > MAX_TEXT:
                text, note = text[:MAX_TEXT], f"文字太长，只取了前 {MAX_TEXT} 字"
        else:
            raise ApiError(400, "附件「{}」的类型不支持：截图收 PNG/JPEG/WebP，文档收 {}".format(name, "、".join(sorted(DOCS))))
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(raw)
        out.append({"name": name, "sha256": sha, "file": file, "kind": kind, "type": mime, "bytes": len(raw), "text": text, "note": note})
    return out


def data_url(data_dir: Path, a: dict) -> str:
    raw = (image_dir(data_dir) / a["file"]).read_bytes()
    return "data:{};base64,{}".format(a["type"], base64.b64encode(raw).decode("ascii"))


def public(a: dict) -> dict:
    """What a ticket and its evidence record carry: the file and where its words went, not the whole text."""
    return dict({k: a[k] for k in ("name", "sha256", "file", "kind", "bytes", "note") if k in a}, chars=len(a.get("text") or ""))
