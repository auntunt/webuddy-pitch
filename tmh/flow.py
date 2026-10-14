"""Business-flow extraction: entry point → business logic → data access → tables.

A "flow" starts at something the outside world triggers (a URL, a SOAP operation,
a scheduled job, a message listener) and follows resolved method calls through
the repository. Along the way it collects what a maintainer needs to see before
touching the code:

* the call chain, layered as 入口 / 业务逻辑 / 数据访问 / 表;
* every data operation (C/R/U/D) with its table and SQL statement;
* state changes such as `SET STATUS = 'APPROVED' ... WHERE STATUS = 'SUBMITTED'`,
  which are aggregated into per-table state machines;
* business rules visible in code (guard conditions that throw with a message);
* transactions and external side effects (HTTP, MQ, files, processes).

Everything is a syntactic fact with file:line. Business meaning — names, intent,
exceptions the code does not show — belongs in .tmh/knowledge/flows/<id>.md, which
the report shows side by side with these facts.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path

from . import golang
from . import mapper as mapmod
from .codeindex import build_index

MAX_DEPTH = 8
MAX_FANOUT = 3  # an interface call with more implementations than this is shown as a dispatch point, not expanded
FLOW_TEXT_MAX_LINES = 300
CALL = re.compile(r"(?<![\w.])(?:this\s*\.\s*)?(?:(\w+)\s*\.\s*)?(\w+)\s*\(")
CHAIN_CALL = re.compile(r"\b(\w+)\s*\.\s*(\w+)\s*\.\s*(\w+)\s*\(")
LOCAL_DECL = re.compile(r"\b([A-Z]\w*)(?:<[^;=()]*>)?\s+(\w+)\s*(?:=|;|:)")
VAR_NEW = re.compile(r"\bvar\s+(\w+)\s*=\s*new\s+(\w+)")
STATE_COL = r"(\w*(?:STATUS|STATE|_FLAG|FLAG)\w*)"
SPRING_REPO = re.compile(r"\b\w*(?:Repository|JpaSpecificationExecutor)\s*<\s*([A-Z]\w*)")
DERIVED_OPS = [(r"save", "S"), (r"(delete|remove)", "D"), (r"(insert|persist|add|create)", "C"), (r"(update|modify|set)", "U")]
# Packages whose classes are plumbing, not business steps (kept out of flow chains unless they hold SQL).
INFRA_PKG = r"\.(util|utils|tool|tools|common\.util|helper|helpers|redis|cache|jedis)\."
CODE_STATE = re.compile(r"\b(\w+)\s*\.\s*set(\w*(?:Status|State|status|state))\s*\(|\b(\w+)\s*\.\s*(\w*(?:Status|State|status|state))\s*=(?!=)\s*")
EF_OPS = {"Add": "C", "AddRange": "C", "Remove": "D", "RemoveRange": "D", "Attach": "U", "Update": "U"}
SIDE_EFFECTS = [
    (r"\b(restTemplate|webClient|httpClient|HttpClient|WebClient|RestTemplate|OkHttpClient|HttpWebRequest|WebRequest)\b|\bFeign", "调用外部 HTTP 接口"),
    (r"\b(kafkaTemplate|rabbitTemplate|jmsTemplate|amqpTemplate|rocketMQTemplate)\s*\.\s*\w+|MessageQueue\s*\.|\.Publish\s*\(", "发送消息"),
    (r"\bnew\s+(FileWriter|FileOutputStream|StreamWriter|FileStream)\b|File\.(Write|Append|Copy|Move)\w*\s*\(|Files\.(write|copy|move)\s*\(", "写文件"),
    (r"Runtime\.getRuntime\(\)\.exec|ProcessBuilder|Process\.Start", "启动外部进程"),
    (r"\b(JavaMailSender|mailSender|SmtpClient)\b", "发送邮件"),
    (r"\b(redisTemplate|stringRedisTemplate|jedis|IDatabase|cache|CacheManager|JedisManager|RedisUtil\w*)\s*\.\s*\w+", "读写缓存"),
    # Go
    (r"\bhttp\.(Get|Post|PostForm|Head|NewRequest\w*)\s*\(|\b\w*[cC]lient\.Do\s*\(", "调用外部 HTTP 接口"),
    (r"\bos\.(WriteFile|Create|OpenFile|Rename|Remove\w*)\s*\(", "写文件"),
    (r"\bexec\.Command\w*\s*\(", "启动外部进程"),
    (r"\bsmtp\.SendMail\s*\(", "发送邮件"),
    (r"\b(RDB|rdb|redisClient|RedisClient|Rdb)\s*\.\s*\w+\s*\(", "读写缓存"),
]


def _norm(t: str) -> str:
    return mapmod._norm_table(t)


def analyze_sql(sql: str) -> dict:
    s = " ".join(sql.split())
    head = re.match(r"\s*(?:\{\s*)?(\w+)", s)
    op_word = head.group(1).upper() if head else ""
    op = {"SELECT": "R", "WITH": "R", "INSERT": "C", "UPDATE": "U", "DELETE": "D", "MERGE": "U", "CALL": "P", "EXEC": "P", "EXECUTE": "P"}.get(op_word, "R")
    tables = sorted(mapmod._tables_in(s))
    writes = []
    wm = re.search(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|DELETE|MERGE\s+INTO)\s+([A-Za-z_][\w$#.\"\[\]]*)", s, re.I)
    if wm and op in "CUD":
        writes.append(_norm(wm.group(1)))
    procs = [_norm(p) for p in re.findall(r"\b(?:CALL|EXEC(?:UTE)?)\s+([\w.]+)", s, re.I)]
    states = []
    if op == "U" and writes:
        sm = re.search(r"\bSET\b(.*?)(?:\bWHERE\b|$)(.*)", s, re.I | re.S)
        if sm:
            pairs = re.findall(STATE_COL + r"\s*=\s*(?:'([^']*)'|(DYN_\w+))", sm.group(1), re.I)
            for col, val in [(c, dyn_label(v.strip()) if v else dyn_label(d)) for c, v, d in pairs]:
                frm = []
                for c2, v2 in re.findall(STATE_COL + r"\s*=\s*'([^']*)'", sm.group(2), re.I):
                    if c2.upper() == col.upper():
                        frm.append(v2)
                for c2, vs in re.findall(STATE_COL + r"\s+IN\s*\(([^)]*)\)", sm.group(2), re.I):
                    if c2.upper() == col.upper():
                        frm += re.findall(r"'([^']*)'", vs)
                states.append({"table": writes[0], "column": col.upper(), "from": frm or ["*"], "to": val})
    if op == "C" and writes:
        im = re.search(r"\(([^()]*)\)\s*VALUES\s*\((.*)\)", s, re.I | re.S)
        if im:
            cols = [c.strip().upper() for c in im.group(1).split(",")]
            vals = _split_top(im.group(2))
            for c, v in zip(cols, vals):
                vm = re.match(r"^'([^']*)'$", v.strip())
                if vm and re.match(STATE_COL + "$", c, re.I):
                    states.append({"table": writes[0], "column": c, "from": ["(新建)"], "to": vm.group(1)})
    if DYN in s.upper():
        tables = sorted({dyn_label(t) for t in tables})
        writes = [dyn_label(t) for t in writes]
        for st in states:
            st["table"] = dyn_label(st["table"])
    return {"op": op, "tables": tables, "writes": writes, "procs": procs, "states": states}


def _split_top(s: str) -> list[str]:
    out, cur, depth = [], "", 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


_LIT = r"@?\"(?:[^\"\\]|\\.|\"\")*\""
_EXPR = r"[A-Za-z_][\w.]*(?:\([^()\"]*(?:\([^()\"]*\)[^()\"]*)*\))?(?:\.\w+(?:\([^()\"]*\))?)*"
_CONCAT = re.compile(r"(%s(?:\s*\+\s*(?:%s|%s))*)" % (_LIT, _LIT, _EXPR))
DYN = "DYN_"


_DYN_NAMES: dict = {}


def _dyn_name(expr: str) -> str:
    e = expr
    while "(" in e:
        e2 = re.sub(r"\([^()]*\)", "()", e).replace("()", "")
        if e2 == e:
            break
        e = e2
    tok = DYN + str(len(_DYN_NAMES) if e.upper() not in _DYN_NAMES else _DYN_NAMES[e.upper()][0])
    _DYN_NAMES.setdefault(e.upper(), (tok[len(DYN):], e))
    _DYN_NAMES[tok.upper()] = (tok[len(DYN):], e)
    return tok


def dyn_label(t: str) -> str:
    """Table/value placeholder produced from a concatenated expression → readable label."""
    if t.upper().startswith(DYN) and t.upper() in _DYN_NAMES:
        return "〈动态:%s〉" % _DYN_NAMES[t.upper()][1]
    return t


def _sql_literals(body: str) -> list[tuple[str, int]]:
    """SQL-looking string literals in a method body, with line offset.

    Adjacent literals are joined; a variable concatenated in between
    (`"update " + tablename + " set status=" + st`) becomes a DYN_ placeholder, so a
    table chosen at runtime shows up as 〈动态:tablename〉 instead of being lost."""
    out = []
    for m in _CONCAT.finditer(body):
        parts = re.findall(r"(%s)|(%s)" % (_LIT, _EXPR), m.group(1))
        lit = ""
        for lp, ep in parts:
            if lp:
                lit += "".join(re.findall(r"\"((?:[^\"\\]|\\.|\"\")*)\"", lp))
            elif ep:
                lit += " %s " % _dyn_name(ep)
        if re.match(r"\s*(?:\{\s*)?(SELECT|INSERT|UPDATE|DELETE|MERGE|WITH|CALL|EXEC)\b", lit, re.I):
            out.append((lit, body.count("\n", 0, m.start())))
    return out


class FlowBuilder:
    def __init__(self, root: Path, project_map: dict | None = None, index: dict | None = None):
        self.root = root.resolve()
        self.map = project_map or mapmod.build_map(self.root)
        self.idx = index or build_index(self.root)
        self.classes = self.idx["classes"]
        self.mybatis = {}
        for d in self.map["data_access"]:
            if d["kind"] == "MyBatis":
                self.mybatis[d["namespace"]] = d
                self.mybatis.setdefault(d["namespace"].split(".")[-1], d)
        self.mybatis_sql = self._mybatis_sql()
        self.dbsets = {}
        for cs in self.classes.values():
            for c in cs:
                if "DbContext" in c["bases"]:
                    for fname, f in c["fields"].items():
                        gm = re.match(r"I?DbSet\s*<\s*(\w+)\s*>", f["raw"])
                        if gm:
                            self.dbsets[(c["name"], fname)] = self._entity_table(gm.group(1)) or fname.upper()
        self.entity_tables = {e["class"].split(".")[-1]: e["table"] for e in self.map["entities"]}
        # JPQL names an entity by its @Entity(name) or class name; map both to the table.
        self.jpql_tables = {}
        for e in self.map["entities"]:
            self.jpql_tables[e["class"].split(".")[-1].upper()] = e["table"]
            if e.get("jpql"):
                self.jpql_tables[e["jpql"].upper()] = e["table"]
        self.repos = self._spring_data_repos()

    def _spring_data_repos(self) -> dict:
        """Spring Data repository interfaces → entity class (from `extends XxxRepository<Entity, Id>`)."""
        direct, parents = {}, {}
        for cs in self.classes.values():
            for c in cs:
                if c["kind"] != "interface":
                    continue
                head = c.get("head", "")
                rm = SPRING_REPO.search(head)
                if rm:
                    direct[c["name"]] = rm.group(1)
                else:
                    parents[c["name"]] = c["bases"]
        out = dict(direct)
        changed = True
        while changed:
            changed = False
            for n, bases in parents.items():
                if n not in out:
                    for b in bases:
                        if b in out:
                            out[n] = out[b]
                            changed = True
                            break
        return out

    def _entity_table(self, cls: str) -> str:
        for e in self.map["entities"]:
            if e["class"].split(".")[-1] == cls:
                return e["table"]
        return ""

    def _mybatis_sql(self) -> dict:
        from .fsutil import read_text
        out = {}
        for d in self.map["data_access"]:
            if d["kind"] != "MyBatis":
                continue
            text = read_text(self.root / d["file"]) or ""
            for mm in mapmod.MYBATIS_STMT.finditer(text):
                start = text.find(">", mm.end()) + 1
                end = re.search(r"</%s>" % mm.group(1), text[start:], re.I)
                body = text[start: start + end.start()] if end else ""
                body = re.sub(r"<!\[CDATA\[|\]\]>", "", body)
                body = re.sub(r"<[^>]+>", " ", body).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
                line = text.count("\n", 0, mm.start()) + 1
                out[(d["namespace"], mm.group(2))] = {"sql": " ".join(body.split()), "file": d["file"], "line": line, "kind": mm.group(1).lower()}
        return out

    # ---- resolution -------------------------------------------------
    def _class(self, name: str):
        cs = self.classes.get(name)
        return cs[0] if cs else None

    def _concrete(self, name: str) -> list[str]:
        c = self._class(name)
        if c and c["kind"] == "interface":
            impls = [i for i in self.idx["impls"].get(name, []) if self._class(i) and self._class(i)["kind"] != "interface"]
            if impls:
                return impls
        return [name]

    def _methods(self, cls_name: str, meth: str) -> list[dict]:
        seen = set()
        todo = [cls_name]
        while todo:
            cn = todo.pop(0)
            if cn in seen:
                continue
            seen.add(cn)
            c = self._class(cn)
            if not c:
                continue
            if meth in c["methods"]:
                return c["methods"][meth]
            todo += c["bases"]
        return []

    def _layer(self, cls: dict) -> str:
        if cls.get("lang") == "go":
            return cls.get("layer") or "service"
        n, a = cls["name"], cls.get("annos", "")
        if self._is_mapper(n) or "DbContext" in cls["bases"] or re.search(r"(Mapper|Dao|DAO|Repository|Repo|Rep|DbHelper|SqlHelper|DataAccess)$", n) or "@Repository" in a:
            return "dao"
        if re.search(r"@(Rest)?Controller", a) or re.search(r"(Controller|Action|Servlet|Endpoint|Resource|Facade|Api)$", n) or "Controller" in cls["bases"]:
            return "entry"
        return "service"

    def _is_mapper(self, type_name: str) -> bool:
        c = self._class(type_name)
        fq = c["fqn"] if c else type_name
        return fq in self.mybatis or type_name in self.mybatis

    # ---- tracing ----------------------------------------------------
    def trace(self, cls_name: str, meth_name: str, max_depth: int = MAX_DEPTH) -> dict:
        self._max_depth = max_depth
        flow = {"nodes": [], "edges": [], "data_ops": [], "states": [], "rules": [], "transactions": [], "side_effects": [], "unresolved": []}
        self._seen: set = set()
        root_id = self._visit(cls_name, meth_name, flow, 0, None)
        flow["root"] = root_id
        return flow

    def _add_node(self, flow, node) -> str:
        for n in flow["nodes"]:
            if n["key"] == node["key"]:
                return n["id"]
        node["id"] = "n%d" % len(flow["nodes"])
        flow["nodes"].append(node)
        return node["id"]

    def _noise(self, owner: dict, m: dict) -> bool:
        """Steps that say nothing about the business: accessors, entity/POJO methods, generic utilities."""
        if "body" not in m:
            return False
        body = m["masked"]
        if _sql_literals(m["body"]):
            return False
        if "@Entity" in owner.get("annos", "") or re.search(INFRA_PKG, "." + owner.get("fqn", "") + ".") or owner.get("infra"):
            return True
        return "(" not in body and body.count("\n") <= 4

    def _visit(self, cls_name, meth_name, flow, depth, parent):
        ms = self._methods(cls_name, meth_name)
        cls = self._class(cls_name)
        if not ms or not cls:
            return None
        m = next((x for x in ms if "body" in x), ms[0])
        owner = self._class(m["class"]) or cls
        if depth and self._noise(owner, m):
            return None
        key = "%s.%s" % (owner["name"], m["name"])
        nid = self._add_node(flow, {"key": key, "layer": self._layer(owner) if depth else "entry", "label": key, "file": m["file"], "line": m["line"],
                                    "end": m.get("end_line", m["line"]), "comment": m.get("comment", "")})
        if parent:
            flow["edges"].append({"from": parent, "to": nid})
        if key in self._seen or depth > self._max_depth or "body" not in m:
            return nid
        self._seen.add(key)
        if ("@Transactional" in m.get("annos", "") or "@Transactional" in owner.get("annos", "") or "TransactionScope" in m["body"]
                or owner.get("lang") == "go" and re.search(r"\.\s*(Transaction|Begin)\s*\(", m["masked"])):
            flow["transactions"].append({"method": key, "file": m["file"], "line": m["line"]})
        self._rules(m, key, flow)
        self._effects(m, key, flow)
        self._sql_in_body(m, key, nid, flow)
        types = {}
        for f, info in owner["fields"].items():
            types[f] = info["type"]
        types.update(m["params"])
        go = owner.get("lang") == "go"
        if not go:
            for t, v in LOCAL_DECL.findall(m["masked"]):
                types.setdefault(v, t)
            for v, t in VAR_NEW.findall(m["masked"]):
                types[v] = t
        self._code_states(m, key, flow, types)
        if go:
            self._go_data(m, key, nid, flow, types)
        # EF: ctx.Set.Op(
        for recv, prop, op in CHAIN_CALL.findall(m["masked"]):
            t = types.get(recv)
            if t and (t, prop) in self.dbsets:
                table = self.dbsets[(t, prop)]
                tid = self._add_node(flow, {"key": "T:" + table, "layer": "table", "label": table, "file": "", "line": 0})
                flow["edges"].append({"from": nid, "to": tid, "op": EF_OPS.get(op, "R")})
                flow["data_ops"].append({"op": EF_OPS.get(op, "R"), "table": table, "via": "%s.%s.%s" % (t, prop, op), "file": m["file"], "line": m["body_line"], "sql": ""})
        seen_calls = OrderedDict()
        for mm in CALL.finditer(m["masked"]):
            recv, name = mm.group(1), mm.group(2)
            if name in ("if", "for", "while", "switch", "catch", "return", "new", "synchronized", "using", "lock", "foreach", "nameof", "typeof"):
                continue
            pre = m["masked"][max(0, mm.start() - 4):mm.start()]
            if pre.endswith("new ") or pre.endswith("new"):
                continue
            line = m["body_line"] + m["masked"].count("\n", 0, mm.start())
            if recv in (None, "this", "base", "super"):
                target_types = [owner["name"]] + ([owner["name"].rsplit(".", 1)[0]] if go and owner["kind"] != "package" else [])
            else:
                t = types.get(recv) or (recv if self._class(recv) else None)
                if not t:
                    continue
                target_types = [t]
            for t in target_types:
                if t in self.repos and not self._has_body(t, name):
                    seen_calls.setdefault(("repo", t, name), line)
                    continue
                if self._is_mapper(t):
                    seen_calls.setdefault(("mapper", t, name), line)
                    continue
                impls = [ct for ct in self._concrete(t) if self._methods(ct, name)]
                if len(impls) > MAX_FANOUT and self._max_depth > 0:  # per-method graph edges keep every possible callee
                    seen_calls.setdefault(("dispatch", t, name), (line, tuple(impls)))
                    continue
                for ct in impls:
                    seen_calls.setdefault(("code", ct, name), line)
        for (kind, t, name), line in seen_calls.items():
            if kind == "dispatch":
                line, impls = line
                dk = "%s.%s" % (t, name)
                did = self._add_node(flow, {"key": dk + "*", "layer": "service", "dispatch": True, "label": "%s → %d 个实现，运行时按配置/类型分派" % (dk, len(impls)),
                                            "file": m["file"], "line": line, "comment": ""})
                flow["edges"].append({"from": nid, "to": did})
                flow["unresolved"].append({"call": dk, "file": m["file"], "line": line,
                                           "why": "接口有 %d 个实现，静态分析不确定走哪个：%s" % (len(impls), "、".join(impls[:12]) + ("等" if len(impls) > 12 else ""))})
                continue
            if kind == "mapper":
                self._mapper_call(t, name, nid, flow, line, m["file"])
            elif kind == "repo":
                self._repo_call(t, name, nid, flow, line, m)
            elif "%s.%s" % (t, name) != key:
                self._visit(t, name, flow, depth + 1, nid)
        return nid

    def _mapper_call(self, type_name, stmt, parent, flow, line, file):
        c = self._class(type_name)
        ns = c["fqn"] if c and c["fqn"] in self.mybatis else self.mybatis[type_name]["namespace"]
        info = self.mybatis_sql.get((ns, stmt))
        key = "%s.%s" % (type_name, stmt)
        nid = self._add_node(flow, {"key": key, "layer": "dao", "label": key, "file": info["file"] if info else file, "line": info["line"] if info else line, "comment": ""})
        flow["edges"].append({"from": parent, "to": nid})
        if info:
            self._record_sql(info["sql"], key, nid, flow, info["file"], info["line"])
        else:
            flow["unresolved"].append({"call": key, "file": file, "line": line, "why": "MyBatis 语句未找到（可能是注解 SQL 或动态 SQL）"})

    def _has_body(self, cls_name: str, meth: str) -> bool:
        return any("body" in x for x in self._methods(cls_name, meth))

    def _repo_call(self, repo, meth, parent, flow, line, caller):
        """A call on a Spring Data repository: @Query text when declared, else the method-name convention."""
        entity = self.repos[repo]
        table = self.entity_tables.get(entity) or entity.upper()
        decl = next(iter(self._methods(repo, meth)), None)
        key = "%s.%s" % (repo, meth)
        nid = self._add_node(flow, {"key": key, "layer": "dao", "label": key, "file": decl["file"] if decl else caller["file"],
                                    "line": decl["line"] if decl else line, "comment": decl.get("comment", "") if decl else ""})
        flow["edges"].append({"from": parent, "to": nid})
        qargs = _anno_args(decl.get("annos", ""), "Query") if decl else None
        if qargs:
            vm = re.search(r"(?:^|\bvalue\s*=\s*|^\s*)((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)", qargs.strip())
            sql = "".join(re.findall(r"\"((?:[^\"\\]|\\.)*)\"", vm.group(1) if vm else qargs))
            native = re.search(r"nativeQuery\s*=\s*true", qargs)
            self._record_sql(sql, key, nid, flow, decl["file"], decl["line"], None if native else self.jpql_tables)
            return
        op = _derived_op(meth)
        if op == "S":  # save(x): new entity → insert, otherwise update
            op = "C" if self._is_new_arg(caller, line) else "U"
        tid = self._add_node(flow, {"key": "T:" + table, "layer": "table", "label": table, "file": "", "line": 0})
        flow["edges"].append({"from": nid, "to": tid, "op": op})
        flow["data_ops"].append({"op": op, "table": table, "via": key, "file": caller["file"], "line": line,
                                 "sql": "(Spring Data %s.%s，按方法名推断)" % (entity, meth)})

    @staticmethod
    def _is_new_arg(m, line) -> bool:
        """repo.save(x) on the given line where x was created with `new` in the same method."""
        rel = line - m["body_line"]
        src = m["masked"].split("\n")
        if not 0 <= rel < len(src):
            return False
        am = re.search(r"\.\s*save\w*\s*\(\s*(new\b|\w+)", src[rel])
        if not am:
            return False
        if am.group(1) == "new":
            return True
        return bool(re.search(r"\b%s\s*=\s*new\s+\w" % re.escape(am.group(1)), m["masked"]))

    def _sql_in_body(self, m, key, nid, flow):
        for lit, off in _sql_literals(m["body"]):
            self._record_sql(lit, key, nid, flow, m["file"], m["body_line"] + off)
        if m["file"].endswith(".go"):
            for bm in re.finditer(r"`([^`]*)`", m["body"]):
                if golang.SQL_TEXT.match(bm.group(1)):
                    self._record_sql(bm.group(1), key, nid, flow, m["file"], m["body_line"] + m["body"].count("\n", 0, bm.start()))
        for am in re.finditer(r"@(Select|Insert|Update|Delete)\s*\(\s*\"((?:[^\"\\]|\\.)*)\"", m.get("annos", "")):
            self._record_sql(am.group(2), key, nid, flow, m["file"], m["line"])

    def _record_sql(self, sql, via, nid, flow, file, line, entity_names=None):
        a = analyze_sql(sql)
        if entity_names:  # JPQL/HQL: entity names → tables
            ren = lambda t: entity_names.get(t.upper(), t)
            a["tables"] = sorted({ren(t) for t in a["tables"]})
            a["writes"] = [ren(t) for t in a["writes"]]
            for st in a["states"]:
                st["table"] = ren(st["table"])
        for t in a["tables"]:
            op = a["op"] if t in a["writes"] or a["op"] == "R" else "R"
            tid = self._add_node(flow, {"key": "T:" + t, "layer": "table", "label": t, "file": "", "line": 0})
            flow["edges"].append({"from": nid, "to": tid, "op": op})
            flow["data_ops"].append({"op": op, "table": t, "via": via, "file": file, "line": line, "sql": " ".join(sql.split())[:300]})
        for p in a["procs"]:
            tid = self._add_node(flow, {"key": "P:" + p, "layer": "table", "label": p + "()", "file": "", "line": 0})
            flow["edges"].append({"from": nid, "to": tid, "op": "P"})
            flow["data_ops"].append({"op": "P", "table": p, "via": via, "file": file, "line": line, "sql": " ".join(sql.split())[:300]})
        for st in a["states"]:
            st.update({"via": via, "file": file, "line": line})
            flow["states"].append(st)

    def _etable(self, t: str) -> str:
        """Table of a type name: an entity, or (Go) a struct GORM would map by its default naming."""
        if not t:
            return ""
        if t in self.entity_tables:
            return self.entity_tables[t]
        short = t.split(".")[-1]
        c = self._class(t)
        if c and c.get("lang") == "go":
            return self.entity_tables.get(short) or (golang.default_table(short) if c["kind"] == "struct" and c["fields"] else "")
        return ""

    def _go_table(self, expr: str, types: dict) -> str:
        e = expr.strip().lstrip("&*").strip()
        lm = re.match(r"^(?:\[\]\*?)?([A-Za-z_][\w.]*)\s*\{", e)
        if lm:
            t = lm.group(1)
            if t not in self.classes and "." not in t:
                t = next((k for k in self.classes if k.endswith("." + t)), t)
            return self._etable(t)
        if re.match(r"^\w+$", e):
            return self._etable(types.get(e, ""))
        return ""

    def _go_data(self, m, key, nid, flow, types):
        """GORM chains: `DB.Model(&User{}).Where(...).Update("status", x)`, `tx.Create(&token)`, `DB.Table("abilities").Find(&xs)`."""
        body, masked = m["body"], m["masked"]
        for a, b in golang.statements(masked):
            s = masked[a:b]
            if not golang.GORM_STMT.search(s):
                continue
            raw = body[a:b]
            tm = re.search(r"\.\s*Table\s*\(\s*\"(\w+)", raw)
            mm = re.search(r"\.\s*Model\s*\(", s)
            model = ""
            if mm:
                e = _close_paren(s, mm.end() - 1)
                model = self._go_table(s[mm.end():e], types) if e > 0 else ""
            for om in re.finditer(r"\.\s*(%s)\s*\(" % "|".join(golang.GORM_OPS), s):
                k = om.end() - 1
                e = _close_paren(s, k)
                args = golang._split(raw[k + 1:e]) if e > 0 else []
                table = tm.group(1).upper() if tm else model
                if not table and args and om.group(1) not in ("Update", "UpdateColumn", "Count", "Pluck"):
                    table = self._go_table(golang._split(s[k + 1:e])[0], types)
                if not table:
                    continue
                op = golang.GORM_OPS[om.group(1)]
                if op == "S":
                    op = "C" if args and re.match(r"^\s*&?[\w.]+\s*\{", args[0]) else "U"
                line = m["body_line"] + masked.count("\n", 0, a + om.start())
                tid = self._add_node(flow, {"key": "T:" + table, "layer": "table", "label": table, "file": "", "line": 0})
                flow["edges"].append({"from": nid, "to": tid, "op": op})
                flow["data_ops"].append({"op": op, "table": table, "via": key, "file": m["file"], "line": line, "sql": " ".join(raw.split())[:300]})
                if om.group(1) in ("Update", "UpdateColumn") and len(args) >= 2:
                    cm = re.match(r'^\s*"' + STATE_COL + r'"\s*$', args[0], re.I)
                    if cm:
                        flow["states"].append({"table": table, "column": cm.group(1).upper(), "from": ["*"], "to": self._const_value(args[1], m),
                                               "via": key, "file": m["file"], "line": line})
                if om.group(1) in ("Updates", "UpdateColumns") and args:
                    for col, val in re.findall(r'"' + STATE_COL + r'"\s*:\s*([^,}]+)', args[0], re.I):
                        flow["states"].append({"table": table, "column": col.upper(), "from": ["*"], "to": self._const_value(val, m),
                                               "via": key, "file": m["file"], "line": line})

    def _go_rules(self, m, key, flow):
        """`if cond { ...ApiError(c, "msg") / errors.New("msg")...; return }`: the guard and the message people see."""
        body, masked = m["body"], m["masked"]
        for im in re.finditer(r"\bif\s+(.+?)\{", masked):
            ob = im.end() - 1
            cb = _close_paren(masked.replace("{", "(").replace("}", ")"), ob)
            if cb < 0:
                continue
            blk_m, blk = masked[ob:cb], body[ob:cb]
            if "return" not in blk_m or "if " in blk_m:
                continue
            em = re.search(r"\b(errors\.New|fmt\.Errorf|\w*(?:[Ee]rr|[Ff]ail|[Aa]bort|[Dd]eny|[Rr]eject)\w*|JSON)\s*\(", blk_m)
            if not em:
                continue
            tail = blk[em.end():]
            lit = re.search(r"\"message\"\s*:\s*\"((?:[^\"\\]|\\.)+)\"", tail) or next(
                (x for x in re.finditer(r"\"((?:[^\"\\]|\\.)+)\"", tail) if not (x.group(1).isidentifier() and x.group(1).islower())), None)
            if not lit:
                continue
            cond = " ".join(body[im.start() + 3: ob].split())
            line = m["body_line"] + masked.count("\n", 0, im.start())
            flow["rules"].append({"method": key, "condition": cond[:120], "exception": em.group(1), "message": lit.group(1)[:120], "file": m["file"], "line": line})

    def _rules(self, m, key, flow):
        if m["file"].endswith(".go"):
            return self._go_rules(m, key, flow)
        body, masked = m["body"], m["masked"]
        for tm in re.finditer(r"\bthrow\s+new\s+(\w+)\s*\(", masked):
            seg = body[tm.end(): tm.end() + 200]
            msg = re.match(r"\s*@?\"((?:[^\"\\]|\\.)*)\"", seg)
            line_start = masked.rfind("\n", 0, tm.start()) + 1
            a = max(0, line_start - 300)
            prev = masked[a: tm.start()]
            cond = ""
            cm = list(re.finditer(r"\bif\s*\(", prev))
            if cm:
                k0 = a + cm[-1].end()
                depth, out = 1, ""
                for k in range(k0, tm.start()):
                    ch = masked[k]
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    out += body[k]
                cond = " ".join(out.split())
            line = m["body_line"] + masked.count("\n", 0, tm.start())
            flow["rules"].append({"method": key, "condition": cond[:120], "exception": tm.group(1), "message": msg.group(1) if msg else "", "file": m["file"], "line": line})

    def _code_states(self, m, key, flow, types):
        """`bill.setStatus(Const.X)` / `x.status = ...`: the state change is attributed to the receiver's
        entity table when its type is known, and constants are resolved to their literal values."""
        body, masked = m["body"], m["masked"]
        for sm in CODE_STATE.finditer(masked):
            recv, col = sm.group(1) or sm.group(3), sm.group(2) or sm.group(4)
            if sm.group(2):
                end = _close_paren(masked, sm.end() - 1)
                arg = body[sm.end(): end].strip() if end > 0 else ""
            else:
                semi = masked.find(";", sm.end())
                arg = body[sm.end(): semi].strip() if semi > 0 else ""
            if not arg or len(arg) > 80:
                continue
            t = types.get(recv) or (recv if self._class(recv) else "")
            table = self._etable(t) or (t if t else "(代码)")
            line = m["body_line"] + masked.count("\n", 0, sm.start())
            flow["states"].append({"table": table, "column": col.upper(), "from": ["*"], "to": self._const_value(arg, m),
                                   "via": key, "file": m["file"], "line": line})

    def _const_value(self, expr: str, m: dict | None = None) -> str:
        """`"2"` → 2；`Const.Flow_status_end` → Flow_status_end=2 (static constant resolved from source); else the expression."""
        e = re.sub(r"\.(toString|intValue|longValue|shortValue|byteValue)\(\)$", "", expr.strip())
        e = re.sub(r"^(?:Integer|Long|String|Short)\.valueOf\((.*)\)$|^new\s+(?:Integer|Long|Short)\((.*)\)$", lambda x: x.group(1) or x.group(2), e).strip()
        lm = re.fullmatch(r"\"([^\"]*)\"|'(.)'|(-?\d+)[LlDdFf]?", e)
        if lm:
            return next(g for g in lm.groups() if g is not None)
        cm = re.fullmatch(r"(?:(\w+)\.)?([A-Za-z_]\w*)", e)
        if not cm:
            return e
        cls, name = cm.group(1), cm.group(2)
        if cls:
            val = self._constants(cls).get(name)
        else:  # same class, or `import static ...Const.*`
            val = None
            if m:
                cands = [m["class"]] + ([m["class"].rsplit(".", 1)[0]] if m["file"].endswith(".go") else self._static_imports(m["file"]))
                val = next((self._constants(c)[name] for c in cands if name in self._constants(c)), None)
        return "%s=%s" % (name, val) if val is not None else name

    def _static_imports(self, file: str) -> list:
        cache = self.__dict__.setdefault("_simport_cache", {})
        if file not in cache:
            from .fsutil import read_text
            text = read_text(self.root / file) or ""
            cache[file] = [x.split(".")[-1] for x in re.findall(r"^\s*import\s+static\s+([\w.]+)\.(?:\*|\w+)\s*;", text, re.M)]
        return cache[file]

    def _constants(self, cls_name: str) -> dict:
        cache = self.__dict__.setdefault("_const_cache", {})
        if cls_name in cache:
            return cache[cls_name]
        out = {}
        c = self._class(cls_name)
        if c and c.get("lang") == "go":
            from .fsutil import read_text
            d = self.root / c["godir"] if c["godir"] else self.root
            for p in sorted(d.glob("*.go")):
                text = read_text(p) or ""
                blocks = re.findall(r"^const\s*\((.*?)^\)", text, re.M | re.S) + re.findall(r"^const\s+(\w+.*)$", text, re.M)
                for blk in blocks:
                    for km in re.finditer(r"^\s*(\w+)\s*(?:[\w.]+\s*)?=\s*(\"[^\"]*\"|-?\d+)\s*(?://.*)?$", blk, re.M):
                        out.setdefault(km.group(1), km.group(2).strip('"'))
        elif c:
            from .fsutil import read_text
            text = read_text(self.root / c["file"]) or ""
            for km in re.finditer(r"\bstatic\s+(?:final\s+)?[\w.<>]+\s+(\w+)\s*=\s*(\"[^\"]*\"|'.'|-?\d+[LlDdFf]?|true|false)\s*;", text):
                out[km.group(1)] = km.group(2).strip("\"'").rstrip("LlDdFf") if km.group(2)[0] not in "tf" else km.group(2)
        cache[cls_name] = out
        return out

    def _effects(self, m, key, flow):
        for rx, label in SIDE_EFFECTS:
            for em in re.finditer(rx, m["body"]):
                line = m["body_line"] + m["body"].count("\n", 0, em.start())
                flow["side_effects"].append({"kind": label, "method": key, "file": m["file"], "line": line, "code": em.group(0)[:60]})
                break


def _close_paren(text: str, open_idx: int) -> int:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _anno_args(annos: str, name: str) -> str | None:
    """Text inside the parentheses of @name(...), honouring string literals."""
    am = re.search(r"@%s\s*\(" % name, annos)
    if not am:
        return None
    depth, i, instr = 1, am.end(), False
    while i < len(annos):
        ch = annos[i]
        if instr:
            if ch == "\\":
                i += 1
            elif ch == '"':
                instr = False
        elif ch == '"':
            instr = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return annos[am.end():i]
        i += 1
    return annos[am.end():]


def _derived_op(meth: str) -> str:
    """Spring Data method-name convention: save* → S (insert or update), delete*/remove* → D, else read."""
    for rx, op in DERIVED_OPS:
        if re.match(rx, meth, re.I):
            return op
    return "R"


def _slug(s: str) -> str:
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"[^\w一-鿿]+", "-", s).strip("-").lower()
    return s[:80] or "flow"


def _split_handler(h: str) -> tuple[str, str]:
    h = h.split("(")[0]
    parts = h.split(".")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return parts[0], ""


def build_flows(root: Path, project_map: dict | None = None, index: dict | None = None, builder=None) -> dict:
    fb = builder or FlowBuilder(root, project_map, index)
    m = fb.map
    gofiles = fb.idx.get("go_files") or {}

    def go_cls(file, cls):  # an import alias or the file's own package name → the package owner
        return (gofiles.get(file) or {}).get("aliases", {}).get(cls, cls)
    entries = []
    for e in m["endpoints"]:
        cls, meth = _split_handler(e["handler"])
        if e["file"].endswith(".go"):
            cls = go_cls(e["file"], cls)
        trig = "%s %s" % (e["method"], e["path"]) if e["stack"] != "wcf/asmx" else "SOAP %s" % e["path"]
        entries.append({"kind": "接口", "trigger": trig, "class": cls, "method": meth, "file": e["file"], "line": e["line"]})
    for j in m["jobs"]:
        if j["class"] and j["file"].endswith(".go"):
            cls, meth = _split_handler(j["class"])
            entries.append({"kind": "定时任务", "trigger": "%s %s" % (j["kind"], j.get("schedule") or j["class"]), "class": go_cls(j["file"], cls), "method": meth,
                            "file": j["file"], "line": j["line"]})
        elif j["class"]:
            cls, meth = _split_handler(j["class"]) if j["kind"] == "@Scheduled" else (j["class"].split(".")[-1], "execute" if j["kind"] in ("Quartz", "Quartz.NET") else "Execute")
            entries.append({"kind": "定时任务", "trigger": "%s %s" % (j["kind"], j.get("schedule", "")), "class": cls, "method": meth, "file": j["file"], "line": j["line"]})
    seen_jobs = {e["class"] for e in entries if e["kind"] == "定时任务"}
    for j in _inherited_jobs(fb):
        if j["class"] not in seen_jobs:
            entries.append(j)
    for l in m["listeners"]:
        cls, meth = _split_handler(l["class"]) if l["kind"] != "JMS MessageListener" else (l["class"].split(".")[-1], "onMessage")
        entries.append({"kind": "消息监听", "trigger": "%s %s" % (l["kind"], l.get("target", "")), "class": cls, "method": meth, "file": l["file"], "line": l["line"]})
    flows = []
    used = set()
    for e in entries:
        if not e["method"]:
            continue
        t = fb.trace(e["class"], e["method"])
        if not t["nodes"]:
            continue
        fid = _slug(e["trigger"] if e["kind"] == "接口" else "%s-%s" % (e["class"], e["method"]))
        base, k = fid, 2
        while fid in used:
            fid = "%s-%d" % (base, k)
            k += 1
        used.add(fid)
        root_node = t["nodes"][0]
        name = root_node.get("comment") or ("" if e["file"].endswith(".go") else next((n.get("comment") for n in t["nodes"][1:] if n.get("comment")), ""))
        crud = {}
        for op in t["data_ops"]:
            crud.setdefault(op["table"], set()).add(op["op"])
        flows.append({"id": fid, "kind": e["kind"], "trigger": e["trigger"], "handler": "%s.%s" % (e["class"], e["method"]),
                      "name": name, "name_source": "代码注释" if name else "", "file": e["file"], "line": e["line"],
                      "crud": {k: "".join(sorted(v, key="CRUDP".index)) for k, v in sorted(crud.items())}, **t})
    return {"flows": flows, "state_machines": state_machines(flows), "matrix": crud_matrix(flows)}


QUARTZ_BASES = {"Job", "StatefulJob", "InterruptableJob", "QuartzJobBean"}


def _inherited_jobs(fb) -> list[dict]:
    """Quartz jobs that extend a project base class (BaseJob implements Job → XxxJob extends BaseJob).

    Such jobs are usually registered at runtime from a database table, so no XML or annotation names
    them. The entry is the method the subclass fills in: its own execute(), or the abstract template
    method of the base it overrides (e.g. doTask)."""
    out = []
    for cs in fb.classes.values():
        c = cs[0]
        if c.get("kind") != "class" or c.get("lang", "java") != "java":
            continue
        if any(x.get("abstract") for ms in c["methods"].values() for x in ms):
            continue  # the abstract template itself
        chain, cur, hit = [], c, False
        for _ in range(6):
            if any(b.split(".")[-1] in QUARTZ_BASES for b in cur["bases"]):
                hit = True
                break
            nxt = next((fb._class(b) for b in cur["bases"] if fb._class(b) and fb._class(b).get("kind") == "class"), None)
            if nxt is None or nxt in chain or nxt is c:
                break
            chain.append(nxt)
            cur = nxt
        if not hit or not chain:
            continue  # direct implementations are found by the mapper already
        meth = next((n for n in ("execute", "executeInternal") if n in c["methods"]), None)
        if not meth:
            templ = {n for a in chain for n, ms in a["methods"].items() if any(x.get("abstract") for x in ms)}
            meth = next((n for n in c["methods"] if n in templ), None)
        if not meth:
            continue
        mm = c["methods"][meth][0]
        out.append({"kind": "定时任务", "trigger": "Quartz %s（继承 %s，运行时注册）" % (c["name"], chain[-1]["name"]), "class": c["name"], "method": meth,
                    "file": c["file"], "line": mm.get("line", c["line"])})
    return out


def state_machines(flows: list[dict]) -> list[dict]:
    sm: dict = {}
    for f in flows:
        for s in f["states"]:
            k = (s["table"], s["column"])
            d = sm.setdefault(k, {"table": s["table"], "column": s["column"], "transitions": []})
            for fr in s["from"]:
                tr = {"from": fr, "to": s["to"], "flow": f["id"], "flow_name": f["name"] or f["trigger"], "file": s["file"], "line": s["line"]}
                if tr not in d["transitions"]:
                    d["transitions"].append(tr)
    out = []
    for d in sm.values():
        states = []
        for tr in d["transitions"]:
            for s in (tr["from"], tr["to"]):
                if s not in states and s != "*":
                    states.append(s)
        d["states"] = states
        out.append(d)
    return out


def crud_matrix(flows: list[dict]) -> dict:
    tables = sorted({t for f in flows for t in f["crud"]})
    return {"tables": tables, "rows": [{"flow": f["id"], "label": f["name"] or f["trigger"], "cells": {t: f["crud"].get(t, "") for t in tables}} for f in flows if f["crud"]]}


def flow_text(f: dict, max_lines: int = 0) -> str:
    """Plain-text rendering of one flow for terminals and agents."""
    out = ["%s  %s%s" % (f["trigger"], f["name"] and "「%s」" % f["name"] or "", "  [%s]" % f["kind"]),
           "入口：%s  (%s:%d)" % (f["handler"], f["file"], f["line"]), "调用链："]
    children: dict = {}
    for e in f["edges"]:
        children.setdefault(e["from"], []).append(e)
    nodes = {n["id"]: n for n in f["nodes"]}

    expanded: set = set()
    budget = [max_lines or FLOW_TEXT_MAX_LINES]

    def walk(nid, depth, seen):
        if budget[0] <= 0:
            return
        n = nodes[nid]
        loc = " (%s:%d)" % (n["file"], n["line"]) if n["file"] else ""
        again = nid in expanded and children.get(nid)
        out.append("  " * (depth + 1) + "- [%s] %s%s%s" % ({"entry": "入口", "service": "逻辑", "dao": "数据", "table": "表"}[n["layer"]], n["label"], loc,
                                                         "（展开见上）" if again else ""))
        budget[0] -= 1
        if nid in seen or again:
            return
        expanded.add(nid)
        seen = seen | {nid}
        for e in children.get(nid, []):
            if nodes[e["to"]]["layer"] == "table":
                out.append("  " * (depth + 2) + "- %s %s" % ({"C": "新增", "R": "查询", "U": "修改", "D": "删除", "P": "调用过程"}[e.get("op", "R")], nodes[e["to"]]["label"]))
                budget[0] -= 1
            else:
                walk(e["to"], depth + 1, seen)

    if f.get("root"):
        walk(f["root"], 0, set())
        if budget[0] <= 0:
            out.append("  …调用链较长，已截断；完整内容见报告或 tmh flows --json")
    if f["states"]:
        out.append("状态变化：")
        for s in f["states"]:
            out.append("  - %s.%s: %s → %s  (%s:%d)" % (s["table"], s["column"], "/".join(s["from"]), s["to"], s["file"], s["line"]))
    if f["rules"]:
        out.append("业务规则（代码中的校验）：")
        for r in f["rules"]:
            out.append("  - %s%s  (%s:%d)" % ("若 %s：" % r["condition"] if r["condition"] else "", r["message"] or r["exception"], r["file"], r["line"]))
    if f["transactions"]:
        out.append("事务：" + "、".join(t["method"] for t in f["transactions"]))
    if f["side_effects"]:
        out.append("外部副作用：")
        for s in f["side_effects"]:
            out.append("  - %s：%s  (%s:%d)" % (s["kind"], s["code"], s["file"], s["line"]))
    if f["unresolved"]:
        out.append("未能解析：")
        for u in f["unresolved"]:
            out.append("  - %s：%s" % (u["call"], u["why"]))
    return "\n".join(out)
