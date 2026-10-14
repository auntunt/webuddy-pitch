"""Go sources: the same facts as for Java and C#, read the way Go code is written.

Go has no classes, so the index models two kinds of owner per package directory:

* the package itself (`model`, `controller`, or `relay/common` when two directories share a package name),
  owning its plain functions, so `model.GetUserById(...)` resolves like a static call;
* each struct or interface (`model.User`), owning the methods declared on it, wherever in the package
  they are written; embedded structs count as bases, and a struct implements every interface whose
  method names it has.

Import aliases, parameter and local types (`u := &model.User{}`, `var xs []model.Token`, `t, err :=
model.GetToken(...)` through the callee's result type) are resolved after every file is parsed, so the
per-file parse stays cacheable. The map reads gin routes (Group prefixes joined, the last argument is the
handler), GORM models (gorm tags, `TableName()`, otherwise GORM's snake_case plural), `Table("x")` and raw
SQL, and background work started from main (`go pkg.Func(...)`) or cron (`AddFunc`).
"""
from __future__ import annotations

import re
from pathlib import Path

from .fsutil import read_text

FUNC = re.compile(r"^func\s*(?:\(\s*(\w+)?\s*\*?\s*(\w+)(?:\[[^\]]*\])?\s*\)\s*)?(\w+)\s*(?:\[[^\]]*\])?\s*\(", re.M)
TYPE = re.compile(r"^(?:type\s+|[ \t]+)(\w+)(?:\[[^\]\n]*\])?\s+(struct|interface)\s*\{", re.M)
IMPORT_ONE = re.compile(r"^import\s+(?:([\w.]+)\s+)?\"([^\"]+)\"", re.M)
IMPORT_BLOCK = re.compile(r"^import\s*\((.*?)^\)", re.M | re.S)
BUILTIN = {"string", "int", "int8", "int16", "int32", "int64", "uint", "uint8", "uint16", "uint32", "uint64", "float32", "float64",
           "bool", "byte", "rune", "error", "any", "interface", "struct", "uintptr", "complex64", "complex128"}
KEYWORDS = {"if", "for", "switch", "select", "return", "func", "go", "defer", "range", "case", "default", "else", "var", "const",
            "type", "map", "chan", "make", "new", "len", "cap", "append", "copy", "delete", "panic", "recover", "print", "println"}
ENTRY_DIRS = {"controller", "controllers", "handler", "handlers", "api", "apis", "router", "routers", "routes", "web", "rest", "endpoint", "endpoints"}
DAO_DIRS = {"model", "models", "dao", "daos", "repository", "repositories", "repo", "store", "storage", "db", "database", "entity", "entities", "mapper"}
INFRA_DIRS = {"common", "logger", "log", "constant", "constants", "utils", "util", "i18n", "types", "pkg", "lib", "helper", "helpers", "consts"}
GORM_OPS = {"Create": "C", "CreateInBatches": "C", "FirstOrCreate": "C", "Save": "S", "Update": "U", "Updates": "U", "UpdateColumn": "U",
            "UpdateColumns": "U", "Delete": "D", "Find": "R", "First": "R", "Take": "R", "Last": "R", "Count": "R", "Pluck": "R", "Scan": "R",
            "FindInBatches": "R"}
GORM_STMT = re.compile(r"\b(\w*DB|db|Db|tx|Tx|trx|txn)\s*\.\s*(Model|Table|Where|Create|Save|Find|First|Delete|Update\w*|Select|Joins|Preload|Order|"
                       r"Limit|Offset|Unscoped|Omit|Clauses|Session|WithContext|Scopes|Group|Distinct|Count|Pluck|Take|Last|FirstOrCreate|"
                       r"CreateInBatches|Scan|Not|Or|Set|Attrs|Assign)\s*\(")
ROUTE = re.compile(r"\b(\w+)\s*\.\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|Any|Handle|HandleFunc)\s*\(")
GROUP = re.compile(r"\b(\w+)\s*:?=\s*(\w+)\s*\.\s*Group\s*\(\s*\"([^\"]*)\"")


# ---------------------------------------------------------------- parsing (per file, cacheable)

def _close(text: str, i: int, o: str = "(", c: str = ")") -> int:
    depth = 0
    for k in range(i, len(text)):
        if text[k] == o:
            depth += 1
        elif text[k] == c:
            depth -= 1
            if depth == 0:
                return k
    return -1


def _split(s: str) -> list:
    out, cur, depth = [], "", 0
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur)
    return out


def params(sig: str) -> dict:
    """`c *gin.Context, a, b string, opts ...Option` → {c: *gin.Context, a: string, b: string, opts: Option}."""
    out, pending = {}, []
    for p in _split(sig):
        toks = p.strip().split(None, 1)
        if len(toks) == 1:
            pending.append(toks[0])  # `a, b string`: the type comes with the last name
            continue
        if len(toks) == 2:
            for n in pending + [toks[0]]:
                if re.match(r"^\w+$", n):
                    out[n] = toks[1].strip().lstrip(".")
            pending = []
    return out


def _results(seg: str) -> str:
    """First result type of a signature tail: `(*User, error)` → *User; `[]Token` → []Token."""
    s = seg.strip()
    if s.startswith("("):
        parts = _split(s[1:_close(s, 0)] if _close(s, 0) > 0 else s[1:])
        first = parts[0].strip() if parts else ""
        toks = first.split(None, 1)
        return toks[1] if len(toks) == 2 and re.match(r"^\w+$", toks[0]) and not toks[1].startswith(("(", ".")) else first
    return s


def _body_start(masked: str, j: int) -> int:
    """Index of the `{` opening a function body, skipping `interface{}`/`struct{...}` in the result types."""
    n = len(masked)
    while j < n:
        if masked.startswith(("interface{", "struct{", "interface {", "struct {"), j):
            k = masked.find("{", j)
            j = _close(masked, k, "{", "}") + 1
            if j <= 0:
                return -1
            continue
        ch = masked[j]
        if ch == "{":
            return j
        if ch == "\n" and not masked[:j].rstrip().endswith((",", "(")):
            nxt = masked[j + 1: j + 2]
            if nxt and not nxt.isspace():
                return -1  # a declaration without a body
        j += 1
    return -1


def _locals(masked: str) -> dict:
    out = {}
    for v, t in re.findall(r"\b(\w+)\s*:?=\s*&?((?:\[\]\*?)?[A-Za-z_][\w.]*)\s*\{", masked):
        out.setdefault(v, ("type", t))
    for v, t in re.findall(r"\bvar\s+(\w+)\s+((?:\[\]|\*)*[A-Za-z_][\w.]*)", masked):
        out.setdefault(v, ("type", t))
    for v, t in re.findall(r"\b(\w+)\s*:?=\s*new\(\s*([\w.]+)\s*\)", masked):
        out.setdefault(v, ("type", t))
    for v, f in re.findall(r"\b(\w+)(?:\s*,\s*\w+)*\s*:=\s*([A-Za-z_]\w*(?:\.\w+)?)\s*\(", masked):
        if v != "_" and f.split(".")[-1] not in KEYWORDS:
            out.setdefault(v, ("call", f))
    return {k: v for k, v in out.items() if k not in KEYWORDS and k != "_"}


def imports(text: str) -> list:
    out = []
    for blk in IMPORT_BLOCK.findall(text):
        for line in blk.splitlines():
            im = re.match(r"\s*([\w.]+\s+)?\"([^\"]+)\"", line)
            if im:
                out.append([(im.group(1) or "").strip(), im.group(2)])
    for a, p in IMPORT_ONE.findall(text):
        out.append([a, p])
    return out


def type_decls(masked: str, spans: list) -> list:
    """Top-level `type X struct {` and the members of `type ( ... )` groups, outside function bodies → [(match, open, close)]."""
    out = []
    for tm in TYPE.finditer(masked):
        if any(a < tm.start() < b for a, b in spans) or any(a < tm.start() < b for _, a, b in out):
            continue
        if not tm.group(0).startswith("type"):
            grp = masked.rfind("\ntype (", 0, tm.start())
            if grp < 0 or masked.find("\n)", grp, tm.start()) >= 0:
                continue
        ob = masked.find("{", tm.end() - 1)
        cb = _close(masked, ob, "{", "}")
        if cb > 0:
            out.append((tm, ob, cb))
    return out


def func_spans(masked: str) -> list:
    out = []
    for fm in FUNC.finditer(masked):
        po = masked.find("(", fm.end() - 1)
        pcl = _close(masked, po)
        bs = _body_start(masked, pcl + 1) if pcl > 0 else -1
        be = _close(masked, bs, "{", "}") if bs > 0 else -1
        if be > 0:
            out.append((bs, be))
    return out


def parse(rp: str, text: str) -> list:
    from .codeindex import mask, _comment_above
    masked = mask(text)
    cmasked = mask(text, strings=False)
    lines = text.splitlines()
    pm = re.search(r"^\s*package\s+(\w+)", masked, re.M)
    pkg = pm.group(1) if pm else "main"
    d = rp.rsplit("/", 1)[0] if "/" in rp else ""
    base = {"lang": "go", "gopkg": pkg, "godir": d, "file": rp, "head": "", "annos": ""}
    pc = dict(base, name="", kind="package", line=1, fields={}, methods={}, bases=[], comment="", goimports=imports(cmasked))
    types: dict = {}
    spans = []
    for fm in FUNC.finditer(masked):
        po = masked.find("(", fm.end() - 1)
        pcl = _close(masked, po)
        if pcl < 0:
            continue
        bs = _body_start(masked, pcl + 1)
        line = masked.count("\n", 0, fm.start()) + 1
        rv, rt, name = fm.group(1), fm.group(2), fm.group(3)
        ps = params(masked[po + 1:pcl])
        if rv and rt:
            ps.setdefault(rv, rt)
        doc = _comment_above(lines, line)
        doc = re.sub(r"^%s\b[\s:：-]*" % re.escape(name), "", doc).strip()  # Go doc comments open with the name
        meth = {"name": name, "class": rt or "", "file": rp, "line": line, "params": ps, "annos": "", "comment": doc,
                "ret": _results(masked[pcl + 1: bs if bs > 0 else masked.find("\n", pcl)])}
        if bs > 0:
            be = _close(masked, bs, "{", "}")
            if be < 0:
                continue
            spans.append((bs, be))
            meth.update(body=text[bs + 1:be], masked=masked[bs + 1:be], body_line=text.count("\n", 0, bs + 1) + 1,
                        end_line=text.count("\n", 0, be) + 1, locals=_locals(masked[bs + 1:be]))
        else:
            meth["abstract"] = True
        if rt:
            types.setdefault(rt, dict(base, name=rt, kind="type", line=line, fields={}, methods={}, bases=[], comment=""))["methods"].setdefault(name, []).append(meth)
        else:
            pc["methods"].setdefault(name, []).append(meth)
    for tm, ob, cb in type_decls(masked, spans):
        name, kind = tm.group(1), tm.group(2)
        line = masked.count("\n", 0, tm.start()) + 1
        c = types.setdefault(name, dict(base, name=name, kind=kind, line=line, fields={}, methods={}, bases=[], comment=""))
        c.update(kind=kind, line=line, comment=_comment_above(lines, line))
        body_m, body_t = masked[ob + 1:cb], text[ob + 1:cb]
        depth = 0
        for lm, lt in zip(body_m.split("\n"), body_t.split("\n")):
            s = lm.strip()
            if depth == 0 and s:
                if kind == "interface":
                    mm = re.match(r"(\w+)\s*\(", s)
                    if mm:
                        c["methods"].setdefault(mm.group(1), []).append({"name": mm.group(1), "class": name, "file": rp, "line": line, "params": {},
                                                                         "annos": "", "comment": "", "abstract": True})
                    elif re.match(r"^\*?[\w.]+$", s):
                        c["bases"].append(s.lstrip("*"))
                else:
                    tag = re.search(r"`([^`]*)`", lt)
                    fm = re.match(r"^([\w, ]+?)\s+([*\[\]]*(?:map\[[^\]]*\])?[\w.]+(?:\[[^\]]*\])?)", s)
                    em = re.match(r"^\*?([\w.]+)$", s)
                    if em:
                        c["bases"].append(em.group(1))
                        c["fields"][em.group(1).split(".")[-1]] = {"type": em.group(1), "raw": em.group(1), "tag": tag.group(1) if tag else ""}
                    elif fm:
                        for f in fm.group(1).split(","):
                            if f.strip():
                                c["fields"][f.strip()] = {"type": fm.group(2), "raw": fm.group(2), "tag": tag.group(1) if tag else ""}
            depth += lm.count("{") + lm.count("(") - lm.count("}") - lm.count(")")
    return [pc] + list(types.values())


# ---------------------------------------------------------------- linking (whole repository)

def go_modules(root: Path) -> dict:
    """go.mod module path → directory (relative to root)."""
    from .fsutil import iter_files, rel
    out = {}
    for p in iter_files(root):
        if p.name == "go.mod":
            mm = re.search(r"^module\s+(\S+)", read_text(p) or "", re.M)
            if mm:
                d = rel(root, p.parent)
                out[mm.group(1)] = "" if d in (".", "") else d
    return out


def snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s).lower()


UNCOUNTABLE = ("data", "info", "information", "metadata", "equipment", "news", "series", "species", "media", "feedback", "staff")
SQL_TEXT = re.compile(r"^\s*(select\b.+\bfrom\b|insert\s+into\b|update\s+[\w.`\"]+\s+set\b|delete\s+from\b|with\b.+\bselect\b)", re.I | re.S)
CATALOG = re.compile(r"^(PG_\w+|TABLES|COLUMNS|SCHEMATA|STATISTICS|SQLITE_MASTER|INFORMATION_SCHEMA)$")


def plural(w: str) -> str:
    if w.endswith(UNCOUNTABLE):
        return w
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    if re.search(r"(s|x|z|ch|sh)$", w):
        return w + "es"
    return w + "s"


def default_table(struct: str) -> str:
    """GORM's default naming: UserGroup → user_groups."""
    return plural(snake(struct)).upper()


def bare(t: str) -> str:
    """`*[]model.User` → model.User; `map[string]*X` → X; `...Option` → Option."""
    t = (t or "").strip()
    t = re.sub(r"^map\[[^\]]*\]", "", t)
    t = re.sub(r"^(\.\.\.|\*|\[\d*\]|chan\s+)+", "", t)
    t = re.sub(r"\[.*\]$", "", t)
    return t.strip("*")


def link(classes: dict, root: Path) -> dict:
    """Merge per-file Go fragments into package and type owners, resolve names. Returns per-file alias maps."""
    frags = [c for cs in classes.values() for c in cs if c.get("lang") == "go"]
    if not frags:
        return {}
    for k in [k for k, cs in classes.items() if any(c.get("lang") == "go" for c in cs)]:
        classes[k] = [c for c in classes[k] if c.get("lang") != "go"]
        if not classes[k]:
            del classes[k]
    mods = go_modules(root)
    pkg_of = {}
    for c in frags:
        if c["kind"] == "package":
            pkg_of.setdefault(c["godir"], c["gopkg"])
    seen = {}
    for d, p in pkg_of.items():
        seen.setdefault(p, []).append(d)
    gname = {d: (p if len(seen[p]) == 1 else (d or p)) for d, p in pkg_of.items()}

    def dir_of(path: str) -> str | None:
        for mp, md in sorted(mods.items(), key=lambda x: -len(x[0])):
            if path == mp or path.startswith(mp + "/"):
                sub = path[len(mp):].strip("/")
                return "/".join(x for x in (md, sub) if x)
        return None

    owners: dict = {}
    files: dict = {}
    for c in frags:
        d = c["godir"]
        if c["kind"] == "package":
            key = gname.get(d, c["gopkg"])
            al = {}
            for a, p in c.get("goimports") or []:
                dd = dir_of(p)
                if dd is not None and dd in gname and a not in ("_", "."):
                    al[a or pkg_of[dd]] = gname[dd]
            al[c["gopkg"]] = key
            files[c["file"]] = {"dir": d, "pkg": key, "aliases": al}
        else:
            key = "%s.%s" % (gname.get(d, c["gopkg"]), c["name"])
        o = owners.get(key)
        if o is None:
            o = owners[key] = dict(c, name=key, fields=dict(c["fields"]), methods={}, bases=list(c["bases"]),
                                   fqn=(d.replace("/", ".") + "." if d else "") + (c["name"] or c["gopkg"]), short=c["name"] or c["gopkg"])
            o.pop("goimports", None)
        elif c["kind"] != "type" and o["kind"] in ("type", "package") and c["kind"] != "package":
            o.update(kind=c["kind"], file=c["file"], line=c["line"], comment=c["comment"])
            o["fields"].update(c["fields"])
            o["bases"] += c["bases"]
        for mn, ms in c["methods"].items():
            for m in ms:
                m["class"] = key
            o["methods"].setdefault(mn, []).extend(ms)
    for f, info in files.items():
        info["types"] = {k for k in owners}

    def resolve(t: str, f: str) -> str:
        b = bare(t)
        if not b or b in BUILTIN:
            return b
        info = files.get(f) or {}
        if "." in b:
            a, n = b.split(".", 1)
            pk = (info.get("aliases") or {}).get(a)
            return "%s.%s" % (pk, n) if pk and "%s.%s" % (pk, n) in owners else n
        own = "%s.%s" % (info.get("pkg", ""), b)
        return own if own in owners else b

    for o in owners.values():
        o["bases"] = [resolve(b, o["file"]) for b in o["bases"]]
        for fn, fi in o["fields"].items():
            fi["type"] = resolve(fi["raw"], o["file"])
        for ms in o["methods"].values():
            for m in ms:
                m["params"] = {k: resolve(v, m["file"]) for k, v in m["params"].items()}
                m["rtype"] = resolve(m.get("ret", ""), m["file"])
    for o in owners.values():
        for ms in o["methods"].values():
            for m in ms:
                info = files.get(m["file"]) or {}
                ps = m["params"]
                for v, (kind, raw) in (m.pop("locals", None) or {}).items():
                    if v in ps:
                        continue
                    if kind == "type":
                        ps[v] = resolve(raw, m["file"])
                        continue
                    if "." in raw:
                        a, fn = raw.split(".", 1)
                        cls = (info.get("aliases") or {}).get(a)
                    else:
                        cls, fn = info.get("pkg"), raw
                    callee = (owners.get(cls) or {}).get("methods", {}).get(fn) if cls else None
                    if callee and callee[0].get("rtype") and callee[0]["rtype"] not in BUILTIN:
                        ps[v] = callee[0]["rtype"]
                for a, pk in (info.get("aliases") or {}).items():
                    ps.setdefault(a, pk)
    for o in owners.values():
        top = o["godir"].split("/")[0] if o["godir"] else o["gopkg"]
        leaf = o["godir"].rsplit("/", 1)[-1] if o["godir"] else o["gopkg"]
        dirs = set(o["godir"].split("/")) if o["godir"] else {o["gopkg"]}
        o["layer"] = "entry" if dirs & ENTRY_DIRS or o["gopkg"] in ENTRY_DIRS else "dao" if dirs & DAO_DIRS or o["gopkg"] in DAO_DIRS else "service"
        o["infra"] = top in INFRA_DIRS and o["layer"] == "service"
        o["bkey"] = snake(o["short"]).split("_")[0] if o["kind"] != "package" else leaf.lower()
        classes.setdefault(o["name"], []).insert(0, o)
    return files


def implements(classes: dict, impls: dict) -> None:
    """Structural typing: a Go struct implements an interface whose method names it all has."""
    ifaces = [c for cs in classes.values() for c in cs if c.get("lang") == "go" and c["kind"] == "interface" and c["methods"]]
    structs = [c for cs in classes.values() for c in cs if c.get("lang") == "go" and c["kind"] in ("struct", "type")]
    for i in ifaces:
        need = set(i["methods"])
        for s in structs:
            if need <= set(s["methods"]):
                impls.setdefault(i["name"], [])
                if s["name"] not in impls[i["name"]]:
                    impls[i["name"]].append(s["name"])


# ---------------------------------------------------------------- project map (per file, cacheable)

def map_go(rp: str, text: str, m: dict) -> None:
    from .codeindex import mask
    from . import mapper as mapmod
    masked = mask(text)
    cm = mask(text, strings=False)
    pm = re.search(r"^\s*package\s+(\w+)", masked, re.M)
    pkg = pm.group(1) if pm else "main"
    tablename = {}
    for tm in re.finditer(r"^func\s*\(\s*(?:\w+\s+)?\*?(\w+)\s*\)\s*TableName\s*\(\s*\)\s*string\s*\{\s*return\s+\"(\w+)\"", cm, re.M):
        tablename[tm.group(1)] = tm.group(2)
    structs = set()
    for tm, ob, cb in type_decls(masked, func_spans(masked)):
        name, kind = tm.group(1), tm.group(2)
        line = masked.count("\n", 0, tm.start()) + 1
        m["symbols"][name].append({"file": rp, "line": line, "kind": kind, "fqn": "%s.%s" % (pkg, name)})
        if kind != "struct":
            continue
        body = text[ob + 1:cb]
        if name in tablename or "gorm:\"" in body or re.search(r"^\s*\*?gorm\.Model\b", body, re.M):
            structs.add(name)
            table = (tablename.get(name) or "").upper() or default_table(name)
            m["entities"].append({"class": name, "table": table, "file": rp, "line": line, "go": True})
            m["tables"][table].add(rp)
    for name, t in tablename.items():
        if name not in structs:  # TableName() written apart from its struct
            m["entities"].append({"class": name, "table": t.upper(), "file": rp, "line": 0, "go": True, "override": True})
    for t in re.findall(r"\.\s*Table\s*\(\s*\"(\w+)\"", cm):
        m["tables"][t.upper()].add(rp)
    lits = re.findall(r"`([^`]*)`", cm) + re.findall(r"\"((?:[^\"\\]|\\.)*)\"", cm)
    for t in mapmod._tables_in("\n".join(x for x in lits if SQL_TEXT.match(x))):
        if not CATALOG.match(t):
            m["tables"][t].add(rp)
    # gin / net/http routes: Group prefixes per variable, the last plain argument is the handler
    prefix: dict = {}
    for fm in FUNC.finditer(cm):
        po = cm.find("(", fm.end() - 1)
        pcl = _close(cm, po)
        bs = _body_start(masked, pcl + 1) if pcl > 0 else -1
        be = _close(masked, bs, "{", "}") if bs > 0 else -1
        if be < 0:
            continue
        body = cm[bs:be]
        local = dict(prefix)
        for line_no, ln in enumerate(body.split("\n")):
            gm = GROUP.search(ln)
            if gm:
                local[gm.group(1)] = mapmod._join_path(local.get(gm.group(2), ""), gm.group(3)) if gm.group(3) else local.get(gm.group(2), "")
            rm = ROUTE.search(ln)
            if not rm:
                continue
            k = ln.find("(", rm.end() - 1)
            e = _close(ln, k)
            args = _split(ln[k + 1:e] if e > 0 else ln[k + 1:])
            if not args:
                continue
            verb = rm.group(2).upper()
            a0 = args[0].strip()
            if verb == "HANDLE" and len(args) >= 3 and a0.startswith('"'):
                verb, args = a0.strip('"').upper(), args[1:]
                a0 = args[0].strip()
            if not a0.startswith('"') or len(args) < 2:
                continue
            if verb in ("ANY", "HANDLEFUNC"):
                verb = "ANY"
            handler = args[-1].strip()
            if not re.match(r"^[A-Za-z_][\w.]*$", handler):
                continue
            if "." not in handler:
                handler = "%s.%s" % (pkg, handler)
            path = mapmod._join_path(local.get(rm.group(1), ""), a0.strip('"'))
            m["endpoints"].append({"method": verb, "path": path, "handler": handler, "file": rp,
                                   "line": cm.count("\n", 0, bs) + line_no + 1, "stack": "gin" if rm.group(2) != "HandleFunc" else "net/http"})
    # background work
    for jm in re.finditer(r"\.\s*AddFunc\s*\(\s*\"([^\"]+)\"\s*,\s*([A-Za-z_][\w.]*)\s*\)", cm):
        h = jm.group(2) if "." in jm.group(2) else "%s.%s" % (pkg, jm.group(2))
        m["jobs"].append({"kind": "cron", "class": h, "file": rp, "line": cm.count("\n", 0, jm.start()) + 1, "schedule": jm.group(1)})
    if pkg == "main" or re.search(r"^func\s+init\s*\(", cm, re.M):
        for jm in re.finditer(r"^\s*go\s+([A-Za-z_]\w*\.[A-Za-z_]\w*)\s*\(", cm, re.M):
            m["jobs"].append({"kind": "后台协程", "class": jm.group(1), "file": rp, "line": cm.count("\n", 0, jm.start()) + 1, "schedule": ""})


# ---------------------------------------------------------------- flow helpers

def statements(masked: str) -> list:
    """Logical statements of a body: chained calls split over lines (`DB.Model(&X{}).\\n Where(...)`) joined. → [(start, end)]"""
    out, start, k = [], 0, 0
    lines = masked.split("\n")
    pos = 0
    for i, ln in enumerate(lines):
        end = pos + len(ln)
        s = ln.rstrip()
        nxt = lines[i + 1].lstrip() if i + 1 < len(lines) else ""
        if not (s.endswith((".", "(", ",", "&&", "||", "+")) or nxt.startswith(".")):
            out.append((start, end))
            start = end + 1
        pos = end + 1
        k += 1
    if start < len(masked):
        out.append((start, len(masked)))
    return out
