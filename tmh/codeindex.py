"""Lightweight structural index of Java, C# and Go sources: classes, fields, methods, calls.

This is not a compiler front end. It masks comments and string literals, follows
brace depth to find class members, and records enough type information (fields,
constructor/method parameters, simple locals) to resolve `receiver.method(...)`
calls to classes in the same repository. That is what business-flow tracing
needs, and it stays fast and dependency-free on very large legacy repositories.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import golang
from .fsutil import iter_files, read_text, rel

CONTROL = {"if", "for", "while", "switch", "catch", "synchronized", "using", "lock", "foreach", "return",
           "new", "else", "try", "finally", "do", "throw", "when", "base", "this", "super", "get", "set",
           "fixed", "checked", "unchecked", "nameof", "typeof", "sizeof", "default", "await", "yield"}
CLASS_HEAD = re.compile(r"\b(class|interface|enum|record|struct)\s+(\w+)(?:\s*<[^>{]*>)?([^{]*)$", re.S)
METHOD_HEAD = re.compile(r"(\w+)\s*(?:<[^>()]*>)?\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*(?:throws\s+[\w.,\s]+|:\s*(?:base|this)\s*\([^)]*\)|where\s+[^{]+)?\s*$", re.S)
FIELD_DECL = re.compile(r"(?:^|\s)([A-Za-z_][\w.]*)(?:\s*<[^;=()]*>)?(?:\[\])?\s+(\w+)\s*(?:=[^;]*)?$", re.S)
ANNOTATION = re.compile(r"@\w+(?:\.\w+)*(?:\s*\([^()]*(?:\([^()]*\)[^()]*)*\))?")
# Notes that CFR/Procyon/Vineflower/JD put above members of decompiled code: never a business description.
DECOMPILER_NOTE = re.compile(r"^(WARNING\b|Exception decompiling|Decompiled\b|Decompilation\b|Enabled (aggressive|force)|Could not load|Loose catch|Converted monitor|"
                             r"Unable to fully|This method has failed|Lifted jumps|Inlined |Renamed from|Duplicate member|Illegal identifiers|Jad\b|JD-Core|"
                             r"Source code recreated|Compiled from|Class Version|Java compiler version|Qualified Name|JD-GUI|\s*\w+(\.\w+){2,}\s*$)")
CS_ATTR = re.compile(r"\[[^\[\]]*\]")
MODIFIERS = {"public", "private", "protected", "internal", "static", "final", "readonly", "volatile", "transient",
             "abstract", "virtual", "override", "sealed", "async", "partial", "synchronized", "native", "default",
             "extern", "unsafe", "new", "const"}


def mask(text: str, strings: bool = True) -> str:
    """Blank out comments and (unless strings=False) string/char literals, keeping offsets and newlines."""
    out = list(text)
    i, n = 0, len(text)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        nx = text[i + 1] if i + 1 < n else ""
        if c == "/" and nx == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif c == "/" and nx == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
        elif c == '"' and text.startswith('"""', i):
            j = text.find('"""', i + 3)
            j = n if j < 0 else j + 3
            if strings:
                blank(i + 1, j - 1)
            i = j
        elif c == '"':
            verbatim = i > 0 and text[i - 1] == "@"
            j = i + 1
            while j < n:
                if verbatim and text[j] == '"' and j + 1 < n and text[j + 1] == '"':
                    j += 2
                    continue
                if not verbatim and text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"' or (not verbatim and text[j] == "\n"):
                    break
                j += 1
            if strings:
                blank(i + 1, j)
            i = j + 1
        elif c == "`":  # Go raw string
            j = text.find("`", i + 1)
            j = n if j < 0 else j
            if strings:
                blank(i + 1, j)
            i = j + 1
        elif c == "'":
            j = i + 1
            while j < n and j - i < 8 and text[j] != "'":
                j += 2 if text[j] == "\\" else 1
            if j < n and text[j] == "'":
                if strings:
                    blank(i + 1, j)
                i = j + 1
            else:
                i += 1
        else:
            i += 1
    return "".join(out)


def _strip_generics(t: str) -> str:
    t = re.sub(r"<.*>", "", t).replace("[]", "").strip()
    return t.split(".")[-1]


def _params(sig: str) -> dict:
    out = {}
    sig = ANNOTATION.sub(" ", CS_ATTR.sub(" ", sig))
    depth, cur, parts = 0, "", []
    for ch in sig:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    for p in parts:
        toks = [t for t in re.split(r"\s+", p.split("=")[0].strip()) if t and t not in ("final", "ref", "out", "in", "params", "this")]
        if len(toks) >= 2:
            out[toks[-1]] = _strip_generics(" ".join(toks[:-1]))
    return out


def _clean_head(head: str) -> tuple[str, str]:
    """Return (annotations_text, head_without_annotations)."""
    annos = " ".join(ANNOTATION.findall(head) + CS_ATTR.findall(head))
    h = CS_ATTR.sub(" ", ANNOTATION.sub(" ", head))
    return annos, " ".join(h.split())


def _comment_above(lines: list[str], line_no: int) -> str:
    """First sentence of the comment block right above a declaration (skipping annotations)."""
    i = line_no - 2
    while i >= 0 and (lines[i].strip().startswith(("@", "[")) or not lines[i].strip()):
        i -= 1
    buf = []
    while i >= 0:
        s = lines[i].strip()
        if s.startswith(("//", "/*", "*", "///")) or s.endswith("*/"):
            s = re.sub(r"^(///?|/\*\*?|\*/?)\s*|\s*\*/$", "", s)
            s = re.sub(r"</?summary>", "", s).strip()
            if s and not s.startswith("@"):
                buf.insert(0, s)
            i -= 1
            continue
        break
    buf = [b for b in buf if not DECOMPILER_NOTE.match(b)]
    text = " ".join(buf).strip()
    text = re.split(r"(?<=[。.!?！？])\s", text)[0] if text else ""
    return text[:80]


def parse_source(rp: str, text: str, lang: str) -> list[dict]:
    masked = mask(text)
    cmasked = mask(text, strings=False)  # comments gone, literals kept: annotation values such as @Query("...")
    lines = text.splitlines()
    classes: list[dict] = []
    stack: list[tuple[str, object]] = []  # ("class", cls) | ("method", m) | ("block", None)
    pkg = ""
    pm = re.search(r"^\s*(?:package|namespace)\s+([\w.]+)", masked, re.M)
    if pm:
        pkg = pm.group(1)
    seg_start = 0
    i, n = 0, len(masked)
    paren = 0
    while i < n:
        c = masked[i]
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        if c not in "{};" or paren:
            i += 1
            continue
        head = masked[seg_start:i]
        raw_annos = _clean_head(cmasked[seg_start:i])[0] if "@" in head or "[" in head else ""
        top = stack[-1] if stack else None
        in_class_body = top is not None and top[0] == "class"
        in_method = any(k == "method" for k, _ in stack)
        if c == "{":
            kind = ("block", None)
            if not in_method:
                annos, h = _clean_head(head)
                annos = raw_annos or annos
                cm = CLASS_HEAD.search(h)
                if cm and (top is None or in_class_body or top[0] == "block"):
                    line = masked.count("\n", 0, seg_start + len(head) - len(head.lstrip())) + 1
                    bases = [b for b in re.split(r"[\s,:]+|extends|implements", cm.group(3)) if b and b not in ("extends", "implements", "where")]
                    cls = {"name": cm.group(2), "kind": cm.group(1), "fqn": (pkg + "." if pkg else "") + cm.group(2), "file": rp, "line": line,
                           "bases": [_strip_generics(b) for b in bases], "head": " ".join(cm.group(3).split())[:400], "annos": annos, "fields": {}, "methods": {}, "lang": lang,
                           "comment": _comment_above(lines, line)}
                    classes.append(cls)
                    kind = ("class", cls)
                elif in_class_body:
                    mm = METHOD_HEAD.search(h)
                    if mm and mm.group(1) not in CONTROL and not re.search(r"=\s*[^=]*$", h.split("(")[0]):
                        cls = top[1]
                        line = masked.count("\n", 0, i) + 1
                        decl_line = masked.count("\n", 0, seg_start + len(head) - len(head.lstrip())) + 1
                        meth = {"name": mm.group(1), "class": cls["name"], "file": rp, "line": decl_line, "body_start": i + 1,
                                "body_end": None, "params": _params(mm.group(2)), "annos": annos,
                                "comment": _comment_above(lines, _first_code_line(lines, decl_line))}
                        cls["methods"].setdefault(meth["name"], []).append(meth)
                        kind = ("method", meth)
                    else:
                        toks = [t for t in h.split() if t not in MODIFIERS]
                        if len(toks) >= 2 and re.match(r"^\w+$", toks[-1]) and toks[-1] not in CONTROL:  # C# property `public DbSet<X> Xs {`
                            raw = " ".join(toks[:-1])
                            top[1]["fields"][toks[-1]] = {"type": _strip_generics(raw), "raw": raw}
            stack.append(kind)
        elif c == "}":
            if stack:
                k, obj = stack.pop()
                if k == "method":
                    obj["body_end"] = i
        elif c == ";" and in_class_body:
            _, h = _clean_head(head)
            h = re.sub(r"=.*$", "", h, flags=re.S).strip()
            toks = h.split()
            toks = [t for t in toks if t not in MODIFIERS]
            if len(toks) >= 2 and "(" not in h and re.match(r"^\w+$", toks[-1]):
                raw = " ".join(toks[:-1])
                top[1]["fields"][toks[-1]] = {"type": _strip_generics(raw), "raw": raw}
            elif "(" in h:  # interface / abstract method declaration
                mm = METHOD_HEAD.search(h)
                if mm and mm.group(1) not in CONTROL:
                    line = masked.count("\n", 0, seg_start + len(head) - len(head.lstrip())) + 1
                    top[1]["methods"].setdefault(mm.group(1), []).append({"name": mm.group(1), "class": top[1]["name"], "file": rp, "line": line,
                                                                         "body_start": None, "body_end": None, "params": _params(mm.group(2)), "annos": raw_annos,
                                                                         "comment": _comment_above(lines, line), "abstract": True})
        seg_start = i + 1
        i += 1
    for cls in classes:
        for ms in cls["methods"].values():
            for m in ms:
                if m.get("body_start") is not None and m.get("body_end") is not None:
                    m["body"] = text[m["body_start"]:m["body_end"]]
                    m["masked"] = masked[m["body_start"]:m["body_end"]]
                    m["body_line"] = text.count("\n", 0, m["body_start"]) + 1
                    m["end_line"] = text.count("\n", 0, m["body_end"]) + 1
                m.pop("body_start", None)
                m.pop("body_end", None)
    return classes


def _first_code_line(lines: list[str], decl_line: int) -> int:
    """Declaration heads can start at an annotation; return the line of the first annotation/decl."""
    return decl_line


def build_index(root: Path, cache=None) -> dict:
    root = root.resolve()
    classes: dict[str, list[dict]] = {}
    for p in iter_files(root):
        suf = p.suffix.lower()
        if suf not in (".java", ".cs", ".go") or p.name.endswith("_test.go"):
            continue
        rp = rel(root, p)
        lang = {".java": "java", ".cs": "cs", ".go": "go"}[suf]
        fn = golang.parse if lang == "go" else lambda r, t: parse_source(r, t, lang)
        if cache is not None:
            parsed = cache.get("index", rp, p, lambda text: fn(rp, text) if text is not None else [])
        else:
            text = read_text(p)
            parsed = fn(rp, text) if text is not None else []
        for c in parsed or []:
            classes.setdefault(c["name"], []).append(c)
    go_files = golang.link(classes, root)
    impls: dict[str, list[str]] = {}
    for name, cs in classes.items():
        for c in cs:
            for b in c["bases"]:
                impls.setdefault(b, []).append(name)
    golang.implements(classes, impls)
    return {"classes": classes, "impls": impls, "go_files": go_files}
