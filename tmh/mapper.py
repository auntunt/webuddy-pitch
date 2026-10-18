"""Project map: deterministic facts about where things live in a legacy codebase.

The map answers the questions a new maintainer asks first — which URLs exist and
which class serves them, which jobs and listeners run in the background, which
tables are touched and from where — so an agent can navigate a large repository
by index instead of reading it all into context. Everything here is extracted
syntactically and is labelled as a fact with file:line; business meaning is left
to the knowledge notes the agent writes under .tmh/knowledge/.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .fsutil import iter_files, read_text, rel

JAVA_CLASS = re.compile(r"^\s*(?:public\s+|protected\s+|private\s+)?(?:abstract\s+|final\s+|static\s+)*(class|interface|enum|@interface|record)\s+(\w+)")
CS_CLASS = re.compile(r"^\s*(?:\[[^\]]*\]\s*)*(?:public\s+|internal\s+|protected\s+|private\s+)?(?:abstract\s+|sealed\s+|static\s+|partial\s+)*(class|interface|enum|struct|record)\s+(\w+)(?:<[^>]*>)?\s*(?:\([^)]*\))?\s*(?::\s*([^{]+))?")
SPRING_MAP = re.compile(r"@(Request|Get|Post|Put|Delete|Patch)Mapping\s*(\((.*)\))?")
ANNO_PATH = re.compile(r"(?:value\s*=\s*|path\s*=\s*)?\{?\s*\"([^\"]*)\"")
JAVA_METHOD = re.compile(r"^\s*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?[\w<>\[\],.? ]+\s+(\w+)\s*\(")
CS_METHOD = re.compile(r"^\s*public\s+(?:async\s+|virtual\s+|override\s+|static\s+)*([\w<>\[\],.? ]+)\s+(\w+)\s*\(")
TABLE_REF = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|MERGE\s+INTO|DELETE\s+FROM)\s+([A-Za-z_][\w$#]*(?:\.[A-Za-z_][\w$#]*)?)", re.I)
SQL_KEYWORDS = {"select", "where", "set", "values", "dual", "the", "a", "an", "table", "lateral", "unnest", "each", "if", "exists"}
MYBATIS_STMT = re.compile(r"<(select|insert|update|delete)\b[^>]*\bid\s*=\s*\"(\w+)\"", re.I)


def _norm_table(t: str) -> str:
    t = t.strip("`\"[]").split(".")[-1]
    return t.upper()


def _tables_in(sql: str) -> set[str]:
    out = set()
    for m in TABLE_REF.finditer(sql):
        t = m.group(1)
        if t.lower() in SQL_KEYWORDS or t.startswith(("#", "$")) or len(t) < 2:
            continue
        out.add(_norm_table(t))
    # Old-style comma joins: FROM A a, B b WHERE ...
    for m in re.finditer(r"\bFROM\s+([A-Za-z_][\w$#.]*(?:\s+(?:AS\s+)?\w+)?(?:\s*,\s*[A-Za-z_][\w$#.]*(?:\s+(?:AS\s+)?\w+)?)+)", sql, re.I):
        for part in m.group(1).split(",")[1:]:
            t = part.split()[0]
            if t.lower() not in SQL_KEYWORDS and len(t) >= 2:
                out.add(_norm_table(t))
    return out


def _join_path(a: str, b: str) -> str:
    p = ("/" + a.strip("/") + "/" + b.strip("/")).replace("//", "/")
    return p if p != "/" or not (a or b) else "/"


def map_java(rp: str, text: str, m: dict) -> None:
    lines = text.splitlines()
    pending: list[str] = []
    class_path = ""
    current_class = ""
    is_controller = False
    pkg = ""
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith("package "):
            pkg = s[8:].rstrip(";").strip()
        if s.startswith("@"):
            pending.append(s)
            # Annotation alone on the line: keep collecting.
            if not JAVA_CLASS.match(line):
                continue
        cm = JAVA_CLASS.match(line)
        if cm and not current_class:
            current_class = cm.group(2)
            fq = (pkg + "." if pkg else "") + current_class
            m["symbols"][current_class].append({"file": rp, "line": i, "kind": cm.group(1), "fqn": fq})
            annos = " ".join(pending)
            is_controller = "@RestController" in annos or "@Controller" in annos
            for a in pending:
                sm = SPRING_MAP.search(a)
                if sm and sm.group(1) == "Request" and sm.group(3):
                    pm = ANNO_PATH.search(sm.group(3))
                    class_path = pm.group(1) if pm else ""
            if "@Service" in annos:
                m["services"].append({"class": fq, "file": rp, "line": i})
            if "@Entity" in annos:
                tm = re.search(r"@Table\s*\(\s*name\s*=\s*\"(\w+)\"", annos)
                en = re.search(r"@Entity\s*\(\s*(?:name\s*=\s*)?\"(\w+)\"", annos)
                table = (tm.group(1) if tm else en.group(1) if en else current_class).upper()
                m["entities"].append({"class": fq, "table": table, "file": rp, "line": i, "jpql": en.group(1) if en else current_class})
                m["tables"][table].add(rp)
            if re.search(r"\b(implements\s+[\w, ]*\bJob\b|extends\s+QuartzJobBean)", line):
                m["jobs"].append({"kind": "Quartz", "class": fq, "file": rp, "line": i, "schedule": ""})
            if re.search(r"implements\s+[\w, ]*\bMessageListener\b", line):
                m["listeners"].append({"kind": "JMS MessageListener", "class": fq, "file": rp, "line": i, "target": ""})
            if re.search(r"extends\s+(HttpServlet|Action|DispatchAction|ActionSupport)\b", line):
                m["entrypoints"].append({"kind": "Servlet/Action 类", "class": fq, "file": rp, "line": i})
            pending = []
            continue
        if pending:
            annos = " ".join(pending)
            mm = JAVA_METHOD.match(line)
            if mm:
                method = mm.group(1)
                if is_controller:
                    for a in pending:
                        sm = SPRING_MAP.search(a)
                        if not sm:
                            continue
                        verb = sm.group(1).upper()
                        args = sm.group(3) or ""
                        pm = ANNO_PATH.search(args)
                        sub = pm.group(1) if pm else ""
                        if verb == "REQUEST":
                            vm = re.search(r"RequestMethod\.(\w+)", args)
                            verb = vm.group(1) if vm else "ANY"
                        m["endpoints"].append({"method": verb, "path": _join_path(class_path, sub), "handler": "%s.%s" % (current_class, method), "file": rp, "line": i, "stack": "spring"})
                sch = re.search(r"@Scheduled\s*\((.*)\)", annos)
                if sch:
                    m["jobs"].append({"kind": "@Scheduled", "class": "%s.%s" % (current_class, method), "file": rp, "line": i, "schedule": sch.group(1)[:80]})
                lis = re.search(r"@(Kafka|Rabbit|Jms|RocketMQMessage)Listener\s*\((.*)\)", annos)
                if lis:
                    m["listeners"].append({"kind": lis.group(1), "class": "%s.%s" % (current_class, method), "file": rp, "line": i, "target": lis.group(2)[:80]})
                ws = re.search(r"@WebServlet\s*\((.*)\)", annos)
                if ws:
                    m["endpoints"].append({"method": "ANY", "path": ws.group(1)[:80], "handler": current_class, "file": rp, "line": i, "stack": "servlet"})
                pending = []
            elif not s.startswith("@") and s and not s.startswith("//"):
                pending = []
    for t in _tables_in(_sql_strings(text)):
        m["tables"][t].add(rp)


def _sql_strings(text: str) -> str:
    """Concatenate string literals that look like SQL (ADO.NET / JDBC code)."""
    lits = re.findall(r"\"((?:[^\"\\]|\\.)*)\"", text)
    return "\n".join(l for l in lits if re.search(r"\b(select|insert|update|delete)\b", l, re.I))


def map_mybatis(rp: str, text: str, m: dict) -> None:
    ns = re.search(r"<mapper[^>]*namespace\s*=\s*\"([^\"]+)\"", text)
    if not ns:
        return
    stmts = []
    for mm in MYBATIS_STMT.finditer(text):
        line = text.count("\n", 0, mm.start()) + 1
        end = re.search(r"</%s>" % mm.group(1), text[mm.end():], re.I)
        body = text[mm.end(): mm.end() + end.start()] if end else ""
        tables = sorted(_tables_in(body))
        stmts.append({"id": mm.group(2), "kind": mm.group(1).lower(), "line": line, "tables": tables})
        for t in tables:
            m["tables"][t].add(rp)
    m["data_access"].append({"kind": "MyBatis", "namespace": ns.group(1), "file": rp, "statements": stmts})


def map_xml_config(rp: str, text: str, m: dict) -> None:
    name = rp.rsplit("/", 1)[-1]
    if name == "web.xml":
        servlets = dict(re.findall(r"<servlet>\s*<servlet-name>([^<]+)</servlet-name>\s*<servlet-class>([^<]+)</servlet-class>", text, re.S))
        for sname, url in re.findall(r"<servlet-mapping>\s*<servlet-name>([^<]+)</servlet-name>\s*<url-pattern>([^<]+)</url-pattern>", text, re.S):
            m["endpoints"].append({"method": "ANY", "path": url.strip(), "handler": servlets.get(sname, sname).strip(), "file": rp, "line": 0, "stack": "web.xml"})
        for fl in re.findall(r"<filter-class>([^<]+)</filter-class>", text):
            m["entrypoints"].append({"kind": "Filter", "class": fl.strip(), "file": rp, "line": 0})
    if name.startswith("struts") and name.endswith(".xml"):
        for attrs in re.findall(r"<action\s+([^>]+)>", text):
            nm = re.search(r"(?:name|path)\s*=\s*\"([^\"]+)\"", attrs)
            cl = re.search(r"(?:class|type)\s*=\s*\"([^\"]+)\"", attrs)
            if nm:
                m["endpoints"].append({"method": "ANY", "path": nm.group(1), "handler": cl.group(1) if cl else "", "file": rp, "line": 0, "stack": "struts"})
    for cron in re.findall(r"cronExpression\"?\s*(?:value\s*=\s*)?[>\"]\s*([^<\"]+)", text):
        m["jobs"].append({"kind": "XML cron", "class": "", "file": rp, "line": 0, "schedule": cron.strip()})


def map_csharp(rp: str, text: str, m: dict) -> None:
    lines = text.splitlines()
    ns = ""
    current = ""
    is_ctrl = False
    route_prefix = ""
    pending: list[str] = []
    for i, line in enumerate(lines, 1):
        s = line.strip()
        nm = re.match(r"namespace\s+([\w.]+)", s)
        if nm:
            ns = nm.group(1)
        if s.startswith("[") and not CS_CLASS.match(line):
            pending.append(s)
            continue
        cm = CS_CLASS.match(line)
        if cm:
            kind, name, bases = cm.group(1), cm.group(2), (cm.group(3) or "")
            fq = (ns + "." if ns else "") + name
            m["symbols"][name].append({"file": rp, "line": i, "kind": kind, "fqn": fq})
            annos = " ".join(pending)
            if not current or kind == "class":
                current = name
                is_ctrl = bool(re.search(r"\b(Controller|ApiController|ControllerBase)\b", bases)) or name.endswith("Controller") and ("Controller" in bases or not bases.strip())  # base class may sit on the next line
                rp_m = re.search(r"\[(?:RoutePrefix|Route)\(\s*\"([^\"]*)\"", annos)
                route_prefix = rp_m.group(1).replace("[controller]", name[:-10] if name.endswith("Controller") else name) if rp_m else ""
            if re.search(r"\bServiceBase\b", bases):
                m["jobs"].append({"kind": "Windows Service", "class": fq, "file": rp, "line": i, "schedule": ""})
            if re.search(r"\b(BackgroundService|IHostedService)\b", bases):
                m["jobs"].append({"kind": "HostedService", "class": fq, "file": rp, "line": i, "schedule": ""})
            if re.search(r"\bIJob\b", bases):
                m["jobs"].append({"kind": "Quartz.NET", "class": fq, "file": rp, "line": i, "schedule": ""})
            if re.search(r"\bDbContext\b", bases):
                m["data_access"].append({"kind": "EF DbContext", "namespace": fq, "file": rp, "statements": []})
            if "[ServiceContract" in annos:
                m["entrypoints"].append({"kind": "WCF 契约", "class": fq, "file": rp, "line": i})
            tm = re.search(r"\[(?:[\w.]*\.)?(?:Sugar)?Table(?:Attribute)?\(\s*\"(\w+)\"", annos)  # EF [Table] / SqlSugar [SugarTable]
            if tm:
                m["entities"].append({"class": fq, "table": tm.group(1).upper(), "file": rp, "line": i})
                m["tables"][tm.group(1).upper()].add(rp)
            pending = []
            continue
        mm = CS_METHOD.match(line)
        if not mm and current and ("[OperationContract" in " ".join(pending) or "[WebMethod" in " ".join(pending)):
            im = re.match(r"^\s*(?:public\s+)?([\w<>\[\],.? ]+)\s+(\w+)\s*\(", line)
            mm = im
        if mm and current:
            annos = " ".join(pending)
            ret, meth = mm.group(1), mm.group(2)
            if is_ctrl and (re.search(r"ActionResult|IHttpActionResult|IActionResult|JsonResult|HttpResponseMessage|ViewResult", ret)
                            or re.search(r"\[Http(Get|Post|Put|Delete|Patch)\b", annos)):  # ASP.NET Core actions returning their own types
                verb = re.search(r"\[Http(Get|Post|Put|Delete|Patch)", annos)
                route = re.search(r"\[(?:Route|Http\w+)\(\s*\"([^\"]*)\"", annos)
                ctrl = current[:-10] if current.endswith("Controller") else current
                path = route.group(1) if route else (route_prefix if verb and route_prefix else route_prefix + "/" + meth if route_prefix else "/%s/%s" % (ctrl, meth))  # [HttpGet] with no template: the controller's route
                if route and route_prefix and not path.startswith("~"):
                    path = route_prefix + "/" + path
                m["endpoints"].append({"method": verb.group(1).upper() if verb else "ANY", "path": "/" + path.lstrip("~/"), "handler": "%s.%s" % (current, meth), "file": rp, "line": i, "stack": "aspnet"})
            if "[OperationContract" in annos or "[WebMethod" in annos:
                m["endpoints"].append({"method": "SOAP", "path": meth, "handler": "%s.%s" % (current, meth), "file": rp, "line": i, "stack": "wcf/asmx"})
            pending = []
        elif s and not s.startswith("["):
            pending = []
        dm = re.search(r"DbSet<(\w+)>\s+(\w+)", line)
        if dm:
            m["tables"][dm.group(2).upper()].add(rp)
    for t in _tables_in(_sql_strings(text)):
        m["tables"][t].add(rp)


def map_webforms(rp: str, text: str, m: dict) -> None:
    head = re.search(r"<%@\s*(Page|Control|WebService|ServiceHost)([^%]*)%>", text)
    if head:
        inh = re.search(r"(?:Inherits|Class|Service)=\"([^\"]+)\"", head.group(2))
        m["endpoints"].append({"method": "ANY", "path": "/" + rp, "handler": inh.group(1) if inh else "", "file": rp, "line": 1, "stack": "webforms"})


def map_sql_file(rp: str, text: str, m: dict) -> None:
    for t in _tables_in(text):
        m["tables"][t].add(rp)
    for mm in re.finditer(r"CREATE\s+(?:OR\s+REPLACE\s+)?(PROCEDURE|FUNCTION|PACKAGE(?:\s+BODY)?|TRIGGER|VIEW|TABLE)\s+([\w.\"]+)", text, re.I):
        line = text.count("\n", 0, mm.start()) + 1
        m["db_objects"].append({"kind": mm.group(1).upper(), "name": _norm_table(mm.group(2)), "file": rp, "line": line})


MAP_SUFFIXES = (".go", ".java", ".xml", ".cs", ".vb", ".aspx", ".ascx", ".asmx", ".svc", ".sql", ".properties", ".yml", ".yaml", ".config", ".json", ".py")
LIST_KEYS = ("endpoints", "entrypoints", "jobs", "listeners", "services", "entities", "data_access", "db_objects", "configs", "diagnostics")


def map_file(rp: str, name: str, suf: str, text: str | None) -> dict:
    """Facts contributed by one file (independent of every other file, so it can be cached)."""
    m: dict = {k: [] for k in LIST_KEYS}
    m["tables"] = defaultdict(set)
    m["symbols"] = defaultdict(list)
    if suf == ".py":
        from .python_index import parse
        part = parse(rp, text)
        m["diagnostics"].extend(part["diagnostics"])
        m["endpoints"].extend(part["endpoints"])
        for cls in part["classes"]:
            for name, methods in cls["methods"].items():
                for method in methods:
                    m["symbols"][name].append({"file": rp, "line": method["line"], "class": cls["name"],
                                                "kind": "function", "fqn": cls["name"] + "." + name})
                    for sql in method["python_sql"]:
                        for table in _tables_in(sql["sql"]):
                            m["tables"][table].add(rp)
                        ddl = re.match(r"\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)", sql["sql"], re.I)
                        if ddl:
                            table = _norm_table(ddl.group(1))
                            m["tables"][table].add(rp)
                            m["db_objects"].append({"kind": "TABLE", "name": table, "file": rp, "line": sql["line"]})
    if text is not None:
        if suf == ".java":
            map_java(rp, text, m)
        elif suf == ".go":
            from .golang import map_go
            if not rp.endswith("_test.go"):
                map_go(rp, text, m)
        elif suf == ".xml":
            if "<mapper" in text:
                map_mybatis(rp, text, m)
            map_xml_config(rp, text, m)
        elif suf in (".cs",):
            map_csharp(rp, text, m)
        elif suf in (".aspx", ".ascx", ".asmx", ".svc"):
            map_webforms(rp, text, m)
        elif suf == ".sql":
            map_sql_file(rp, text, m)
        name = name.lower()
        if (name.startswith(("application", "bootstrap", "appsettings", "web.config", "app.config", "jdbc", "db", "datasource"))
                and suf in (".properties", ".yml", ".yaml", ".config", ".json", ".xml")):
            m["configs"].append(rp)
    m["tables"] = {k: sorted(v) for k, v in m["tables"].items()}
    m["symbols"] = dict(m["symbols"])
    return m


def build_map(root: Path, cache=None) -> dict:
    root = root.resolve()
    m: dict = {k: [] for k in LIST_KEYS}
    tables: dict = defaultdict(set)
    symbols: dict = defaultdict(list)
    for p in iter_files(root):
        suf = p.suffix.lower()
        if suf not in MAP_SUFFIXES:
            continue
        rp = rel(root, p)
        if cache is not None:
            part = cache.get("map", rp, p, lambda text: map_file(rp, p.name, suf, text))
        else:
            part = map_file(rp, p.name, suf, read_text(p))
        if not part:
            continue
        for k in LIST_KEYS:
            m[k].extend(part.get(k, []))
        for t, files in part["tables"].items():
            tables[t].update(files)
        for k, v in part["symbols"].items():
            symbols[k].extend(v)
    over = {e["class"]: e["table"] for e in m["entities"] if e.get("override")}
    if over:  # Go: TableName() declared in another file than its struct
        for e in m["entities"]:
            if e["class"] in over and not e.get("override"):
                e["table"] = over[e["class"]]
        m["entities"] = [e for e in m["entities"] if not e.get("override")]
    m["tables"] = {k: sorted(v) for k, v in sorted(tables.items())}
    m["symbols"] = {k: v for k, v in sorted(symbols.items())}
    return m
