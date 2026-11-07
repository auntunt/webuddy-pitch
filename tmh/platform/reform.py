"""Old-system reform: restructuring, dependency upgrades, framework migration, compatibility work.

A reform is too big for one ticket, but each piece of it is an ordinary change: so a reform plan splits the goal
by business domain (from the knowledge base), orders the pieces from the least entangled to the most (a domain
that shares fewer tables with the others goes first and serves as the pilot), and releases them as change
tickets in waves. Each ticket then goes through the usual automatic flow: analysis, plan, per-file edits, build
and tests, diagnosis, a commit on its own branch, human acceptance. The plan page tracks every piece.

The plan runs the same loop as a single fix, one level up: a fix is redone when acceptance rejects it, and a
plan moves on when acceptance passes its pieces. With automatic advance on, the next wave is released once
every released piece has passed; a piece that is still rejected after the automatic redos pauses the plan
until a person resumes it. What acceptance said about earlier pieces goes into the tickets of later ones.

A plan can start with a lead piece (第 0 部分): the groundwork every domain builds on, such as the new project's
skeleton in a cross-language rewrite. While it is open only the lead is released; once it passes, the commit it
ended on becomes the plan's base and every later piece's change starts from there, so parallel domains do not each
lay their own groundwork. The project's own branch is never touched.

For upgrades and migrations the plan also lists the project's declared dependencies (Maven, npm, NuGet, pip),
so the goal can name what moves from which version to which.

Plans are stored with tickets in platform.db; legacy JSON is imported once and retained.
"""
from __future__ import annotations

import json
import re
import uuid
import hashlib
from contextlib import contextmanager, nullcontext
import xml.etree.ElementTree as ET
from pathlib import Path

from .store import now

KINDS = {
    "restructure": ("结构重构", "只调整代码结构，业务行为不变：拆分过大的类和方法、去掉重复代码、理清分层。"),
    "upgrade": ("依赖升级", "升级框架、类库或运行环境的版本，修掉随之而来的不兼容。"),
    "migrate": ("框架迁移", "把一块功能从旧框架或旧写法换到新的上，对外行为不变。"),
    "adapt": ("兼容适配", "适配新的数据库、中间件、操作系统或浏览器，例如国产化替换。"),
    "rewrite": ("跨语言重写", "用另一种语言或技术栈重新实现原系统。原代码只读，作为对照；新代码写在目标目录里，对外接口和数据保持一致。"),
}
DDL = (
    "CREATE TABLE IF NOT EXISTS reform_operations(actor TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,plan_uid TEXT NOT NULL,result TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(actor,request_id))",
    "CREATE TABLE IF NOT EXISTS reform_catalog(project_key TEXT PRIMARY KEY,payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS reform_dispatch(plan_uid TEXT NOT NULL,item_order INTEGER NOT NULL,batch INTEGER NOT NULL,ticket_id INTEGER NOT NULL UNIQUE,state TEXT NOT NULL,actor TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(plan_uid,item_order))",
)


@contextmanager
def _transaction(data_dir, store=None):
    from ..fsutil import open_db
    db = store.db if store else open_db(Path(data_dir)/'platform.db', timeout=30)
    lock = store.lock if store else nullcontext()
    try:
        with lock:
            db.execute('BEGIN IMMEDIATE')
            try:
                for statement in DDL:
                    db.execute(statement)
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
    finally:
        if not store:
            db.close()


def _load(data_dir, key, db):
    row = db.execute('SELECT payload FROM reform_catalog WHERE project_key=?', (key,)).fetchone()
    if row:
        return json.loads(row['payload'] if isinstance(row, dict) else row[0])
    f = _file(data_dir, key)
    ps = json.loads(f.read_text(encoding='utf-8')) if f.exists() else []
    if not isinstance(ps,list):
        raise ValueError('改造计划存储损坏，请核对原始JSON')
    for p in ps:
        p.setdefault('uid', uuid.uuid4().hex)
        p.setdefault('revision',1)
        p['legacy_history_complete'] = False
    _save(data_dir,key,ps,db)
    return ps


def _file(data_dir: Path, key: str) -> Path:
    return Path(data_dir) / "reforms" / ("%s.json" % key)


def plans(data_dir: Path, key: str, include_archived=False) -> list:
    with _transaction(data_dir) as db:
        ps = _load(data_dir,key,db)
    return ps if include_archived else [p for p in ps if not p.get('archived')]


def _save(data_dir: Path, key: str, ps: list, db=None) -> None:
    if db is None:
        with _transaction(data_dir) as connection:
            _save(data_dir,key,ps,connection)
        return
    db.execute('INSERT INTO reform_catalog VALUES(?,?) ON CONFLICT(project_key) DO UPDATE SET payload=excluded.payload',
               (key,json.dumps(ps,ensure_ascii=False)))


def plan(data_dir: Path, key: str, pid: str) -> dict:
    for x in plans(data_dir, key, include_archived=True):
        if x["id"] == pid:
            return x
    raise KeyError(pid)


# ---------------------------------------------------------------- splitting

def split(atlas: dict, domains: list, scope_mode: str | None = None) -> list:
    """One piece per chosen domain, least entangled first: [{domain, title, flows, tables, shared, risk, order}]."""
    doms = {d["id"]: d for d in atlas.get("domains") or []}
    if scope_mode not in (None,'all','selected'):
        raise ValueError('范围模式只能是all或selected')
    if scope_mode == 'selected' and any(d not in doms for d in domains):
        raise ValueError('所选业务域已变化，请刷新预览')
    selected = [d for d in domains if d in doms]
    pick = ([d for d in doms if d != 'dom:_'] if scope_mode == 'all' else selected
            if scope_mode == 'selected' else selected or [d for d in doms if d != 'dom:_'])
    shared = {d: {} for d in pick}
    for l in atlas.get("links") or []:
        for a, b in ((l["a"], l["b"]), (l["b"], l["a"])):
            if a in shared:
                shared[a][doms.get(b, {}).get("title", b)] = l["n"]
    flows = {}
    for f in atlas.get("flows") or []:
        flows.setdefault(f["domain"], []).append(f)
    items = []
    for d in pick:
        dd = doms[d]
        fs = flows.get(d, [])
        n_shared = sum(shared[d].values())
        unresolved = sum(f.get("unresolved") or 0 for f in fs)
        score = n_shared * 2 + len(fs) + unresolved * 3
        items.append({"domain": d, "title": dd["title"], "flows": len(fs), "tables": dd.get("tables", 0),
                      "flow_ids": [f["id"] for f in sorted(fs, key=lambda f: -(f.get("steps") or 0))][:8],
                      "files": sorted({f["file"] for f in fs if f.get("file")})[:40],
                      "shared": sorted(shared[d].items(), key=lambda x: -x[1])[:6], "unresolved": unresolved, "score": score})
    items.sort(key=lambda x: (x["score"], x["title"]))
    level = "低"
    for n, it in enumerate(items, 1):  # by thirds of the order; a tie keeps the level of the one before it
        it["order"] = n
        if n == 1 or it["score"] != items[n - 2]["score"]:
            level = "低" if (n - 1) * 3 < len(items) else "中" if (n - 1) * 3 < 2 * len(items) else "高"
        it["risk"] = level
    return items


def preview(atlas, body):
    revision = hashlib.sha256(json.dumps(atlas,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return {'items':split(atlas,list(body.get('domains') or []),body.get('scope_mode')) if atlas.get('built') else [],
            'knowledge_revision':revision}


# ---------------------------------------------------------------- dependencies

def dependencies(root: Path, limit: int = 300) -> list:
    """Declared dependencies: [{system, file, name, version}]."""
    root = Path(root)
    out = []
    skip = {".git", ".tmh", "node_modules", "target", "bin", "obj", "dist", "build"}

    def walk(pattern):
        for f in root.rglob(pattern):
            if not any(p in skip for p in f.relative_to(root).parts[:-1]):
                yield f
    for f in walk("pom.xml"):
        try:
            tree = ET.parse(f)
        except (ET.ParseError, OSError):
            continue
        ns = {"m": tree.getroot().tag.split("}")[0].strip("{")} if tree.getroot().tag.startswith("{") else {}
        q = (lambda t: "m:" + t) if ns else (lambda t: t)
        props = {}
        pe = tree.getroot().find(q("properties"), ns)
        if pe is not None:
            for c in pe:
                props[c.tag.split("}")[-1]] = (c.text or "").strip()
        parent = tree.getroot().find(q("parent"), ns)
        rel = f.relative_to(root).as_posix()
        if parent is not None:
            out.append({"system": "Maven", "file": rel, "name": "%s:%s（父）" % (parent.findtext(q("groupId"), "", ns), parent.findtext(q("artifactId"), "", ns)),
                        "version": parent.findtext(q("version"), "", ns)})
        for d in tree.getroot().iter("{%s}dependency" % ns["m"] if ns else "dependency"):
            v = d.findtext(q("version"), "", ns).strip()
            m = re.fullmatch(r"\$\{(.+)\}", v)
            out.append({"system": "Maven", "file": rel, "name": "%s:%s" % (d.findtext(q("groupId"), "", ns), d.findtext(q("artifactId"), "", ns)),
                        "version": props.get(m.group(1), v) if m else v})
        for k in ("java.version", "maven.compiler.source", "spring-boot.version", "spring.version"):
            if k in props:
                out.append({"system": "Maven", "file": rel, "name": k, "version": props[k]})
    for f in walk("package.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for sec in ("dependencies", "devDependencies"):
            for n, v in (j.get(sec) or {}).items():
                out.append({"system": "npm", "file": f.relative_to(root).as_posix(), "name": n, "version": str(v)})
    for f in list(walk("*.csproj")) + list(walk("packages.config")):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for n, v in re.findall(r'<(?:PackageReference|package)\s+(?:Include|id)="([^"]+)"\s+[Vv]ersion="([^"]+)"', txt):
            out.append({"system": "NuGet", "file": f.relative_to(root).as_posix(), "name": n, "version": v})
        for v in re.findall(r"<TargetFramework(?:Version)?>([^<]+)<", txt):
            out.append({"system": ".NET", "file": f.relative_to(root).as_posix(), "name": "目标框架", "version": v})
    for f in walk("requirements*.txt"):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*([=<>!~]=?\s*[^\s;#]+)?", line)
            if m and not line.strip().startswith("#"):
                out.append({"system": "pip", "file": f.relative_to(root).as_posix(), "name": m.group(1), "version": (m.group(2) or "").strip()})
    seen, uniq = set(), []
    for d in out:
        k = (d["system"], d["name"], d["version"])
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq[:limit]


# ---------------------------------------------------------------- plans and tickets

def create(data_dir: Path, key: str, atlas: dict, b: dict, by: str, *, _db=None, _persist=True) -> dict:
    kind = b.get("kind") if b.get("kind") in KINDS else "restructure"
    title = (b.get("title") or "").strip()
    goal = b.get("goal") or ""
    if not title:
        raise ValueError("改造计划需要一个名称")
    if not goal.strip():
        raise ValueError("写清楚要改成什么样：目标、范围和不能变的东西")
    if not atlas.get("built"):
        raise ValueError("项目还没有知识库，没法按业务域拆分。先在知识库页建设一次")
    knowledge_revision = preview(atlas,b)['knowledge_revision']
    if b.get('knowledge_revision') and b['knowledge_revision'] != knowledge_revision:
        raise ValueError('项目知识已变化，请重新预览；原稿未修改')
    items = split(atlas, list(b.get("domains") or []), b.get('scope_mode'))
    if not items:
        raise ValueError("没有选中任何业务域")
    target = (b.get("target") or "").strip().strip("/")
    if kind == "rewrite" and not target:
        raise ValueError("跨语言重写要写明新代码放在哪个目录，例如 java")
    if target and (target.startswith(".") or ".." in target.split("/") or ":" in target):
        raise ValueError("目标目录要写项目里的相对路径，例如 java")
    lead = b.get("lead") or {}
    if (lead.get("title") or "").strip() or (lead.get("body") or "").strip():
        items.insert(0, {"order": 0, "lead": True, "domain": "", "title": (lead.get("title") or "先导部分").strip(),
                         "body": lead.get("body") or "", "flows": 0, "tables": 0, "flow_ids": [], "files": [],
                         "shared": [], "unresolved": 0, "score": 0, "risk": "低"})
    with (nullcontext(_db) if _db is not None else _transaction(data_dir)) as db:
        ps = _load(data_dir, key, db)
        fingerprint = hashlib.sha256(json.dumps({'operation':'reform_create','arguments':b},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if b.get('request_id') and _persist:
            previous = db.execute('SELECT fingerprint,result FROM reform_operations WHERE actor=? AND request_id=?',(by,b['request_id'])).fetchone()
            if previous:
                fp,result = (previous['fingerprint'],previous['result']) if isinstance(previous,dict) else previous
                if fp != fingerprint:
                    raise ValueError('请求编号已用于不同内容')
                return json.loads(result)
        uid = uuid.uuid4().hex
        p = {"id": "r"+uid, "uid":uid, "revision":1, "knowledge_revision":knowledge_revision,
             "scope_mode":b.get('scope_mode') or ('selected' if b.get('domains') else 'all'),
             "domains":list(b.get('domains') or []), "kind": kind, "title": title, "goal": goal, "keep": b.get("keep") or "",
             "target": target, "wave": max(1, min(20, int(b.get("wave") or 3))), "auto": b.get("auto", True) is not False, "by": by, "created": now(),
             "items": items, "log": []}
        for field in ('source_version','target_environment','criteria','dependencies'):
            if field in b:
                p[field] = b[field]
        if b.get('source_version'):
            p['base'] = b['source_version']
        if _persist:
            ps.append(p)
            _save(data_dir, key, ps, db)
            if b.get('request_id'):
                db.execute('INSERT INTO reform_operations VALUES(?,?,?,?,?,?)',
                    (by,b['request_id'],fingerprint,p['uid'],json.dumps(p,ensure_ascii=False),now()))
    return p


def remove(data_dir: Path, key: str, pid: str, *, _db=None) -> None:
    with (nullcontext(_db) if _db is not None else _transaction(data_dir)) as db:
        ps = _load(data_dir,key,db)
        p = next((x for x in ps if x['id']==pid),None)
        if not p:
            raise KeyError(pid)
        pending = db.execute("SELECT ticket_id FROM reform_dispatch WHERE plan_uid=? AND state IN ('pending','claimed')",(p['uid'],)).fetchone()
        if pending:
            raise ValueError('计划仍有待调度或结果待核对工作，不能归档')
        for it in p['items']:
            if it.get('ticket'):
                project_key,num = it['ticket'].rsplit('-',1)
                row = db.execute("SELECT t.status FROM tickets t JOIN projects p ON p.id=t.project_id WHERE p.key=? AND t.num=?",(project_key,int(num))).fetchone()
                active = db.execute("SELECT r.id FROM runs r JOIN tickets t ON t.id=r.ticket_id JOIN projects p ON p.id=t.project_id WHERE p.key=? AND t.num=? AND r.status IN ('queued','running')",(project_key,int(num))).fetchone()
                if active or not row or (row['status'] if isinstance(row,dict) else row[0]) != 'closed':
                    raise ValueError('计划仍有未完成工作，请先暂停并核对或取消；归档不会停止运行')
        if p.get('archived'):
            return
        p['archived'] = now()
        p['auto'] = False
        p['revision'] += 1
        _log(p,'计划已归档，历史与工单关系保留')
        _save(data_dir,key,ps,db)


def _log(p: dict, text: str) -> None:
    p.setdefault("log", []).append({"at": now(), "text": text})
    p["updated"] = now()


def earlier(P, p: dict, before: int) -> list:
    """What acceptance said about the pieces already done: rejection reasons and acceptance notes, newest last."""
    out = []
    for it in p["items"]:
        if it["order"] >= before or not it.get("ticket"):
            continue
        t = P.store.ticket(it["ticket"])
        if not t:
            continue
        for e in P.store.events(t["id"]):
            if e["kind"] in ("reject", "accept") and "：" in (e.get("body") or ""):
                out.append("「%s」%s" % (it["title"], e["body"][:300]))
    return out[-10:]


def _lead(p: dict) -> dict | None:
    return next((x for x in p["items"] if x.get("lead")), None)


def ticket_body(p: dict, it: dict, total: int, notes: list | None = None) -> str:
    kname, kdesc = KINDS[p["kind"]]
    tgt = p.get("target") or ""
    if it.get("lead"):
        lines = ["%s「%s」的第 0 部分（先导）：%s。其余 %d 个业务域会在这部分验收通过后，从它的代码开始改。" % (kname, p["title"], it["title"], total), "",
                 "## 改造目标", p["goal"], "", "## 这一类改造的要求", kdesc]
        if p.get("keep"):
            lines += ["", "## 不能变的东西", p["keep"]]
        lines += ["", "## 这一部分要做的", it.get("body") or "后面各业务域都要用到的公共部分：工程结构、依赖、配置和公共代码。",
                  "", "只做公共部分，不要实现具体业务域的功能，那些留给后面各部分的工单。"]
        if tgt:
            lines += ["新代码写在目标目录 %s/ 里；原代码只读，不要改。" % tgt]
        lines += ["", "## 验收条件", "- 构建通过", "- 后面各业务域可以直接在这个基础上添加代码"]
        return "\n".join(lines)
    lines = ["%s「%s」的第 %d/%d 部分：业务域「%s」。" % (kname, p["title"], it["order"], total, it["title"]), "",
             "## 改造目标", p["goal"], "", "## 这一类改造的要求", kdesc]
    if p.get("keep"):
        lines += ["", "## 不能变的东西", p["keep"]]
    ld = _lead(p)
    if ld:
        lines += ["", "## 起点", "先导部分「%s」已经验收通过%s。在它的基础上继续，不要重建或改动公共部分，缺什么公共的东西在工单里说明。"
                  % (ld["title"], "，这一部分的修改从它的提交 %s 开始" % p["base"][:10] if p.get("base") else "")]
    if tgt:
        lines += ["", "## 范围", "原业务域「%s」的代码只读，作为对照（%d 条业务流，%d 张表）；在目标目录 %s/ 里写出它对应的实现。别的业务域留给各自的工单。"
                  % (it["title"], it["flows"], it["tables"], tgt)]
    else:
        lines += ["", "## 范围", "只改业务域「%s」里的代码（%d 条业务流，%d 张表）。别的业务域留给各自的工单。" % (it["title"], it["flows"], it["tables"])]
    if it.get("files"):
        lines += ["涉及的入口文件："] + ["- %s" % f for f in it["files"][:15]]
    if it.get("shared"):
        lines += ["", "## 和其他业务域共用的表（读写方式不能变）"] + ["- 与「%s」共用 %d 张" % (d, n) for d, n in it["shared"]]
    if it.get("unresolved"):
        lines += ["", "注意：这个业务域有 %d 处调用链断开（动态表名、反射或按配置分派），改之前先确认实际走向。" % it["unresolved"]]
    if notes:
        lines += ["", "## 前面几部分验收时说的（照着避开同样的问题）"] + ["- " + n for n in notes]
    if p["kind"] == "rewrite":
        lines += ["", "## 验收条件", "- 构建通过", "- 接口规范测试通过：这个业务域的接口路径、参数和返回格式与原系统一致"]
    else:
        lines += ["", "## 验收条件", "- 构建和测试通过", "- 涉及的业务流行为与改造前一致" if p["kind"] != "upgrade" else "- 升级后涉及的业务流行为与升级前一致"]
    return "\n".join(lines)


def _blocked(P, p):
    if p.get('archived'):
        return '计划已归档'
    if p.get('paused'):
        return p['paused']
    if p.get('cancelled'):
        return '计划已取消后续调度'
    uncertain = P.store.one("SELECT ticket_id FROM reform_dispatch WHERE plan_uid=? AND state='claimed'",(p['uid'],))
    if uncertain:
        return '批次领取结果待核对；请核对工单与运行回执，不能重复启动'
    for it in p['items']:
        if it.get('ticket'):
            ticket = P.store.ticket(it['ticket'])
            if not ticket or ticket['status'] != 'closed':
                return '等待本批工单 %s 完成；请查看当前状态与验收依据' % it['ticket']
    return ''


def _release_in_tx(P, proj, p, n, by, db):
    why = _blocked(P,p)
    if why:
        raise ValueError(why)
    ld = _lead(p)
    if ld and not ld.get('ticket'):
        todo = [ld]
    elif ld and not p.get('lead_passed'):
        raise ValueError('先导部分还没验收通过，请核对验收回执')
    else:
        todo = [it for it in p['items'] if not it.get('ticket')][:n or p['wave']]
    if not todo:
        return []
    if p.get('source_version'):
        from .agents import git
        source = p['source_version']
        root = Path(proj['root'])
        actual = git(root,'rev-parse','--verify','--end-of-options',source+'^{commit}',check=False).strip()
        if actual != source:
            raise ValueError('固定源版本不可访问，请核对项目登记仓库；不会改用HEAD')
        git(root,'update-ref','refs/webuddy/reforms/'+p['uid']+'/source',source)
    if by != P.flow.BY:
        p['execution_owner'] = by
        if getattr(P,'tenant_context',None) is not None:
            from . import tenant_policy
            who = tenant_policy.identity(P,by)
            p['execution_connection'] = (who.get('tool_connection') or {}).get('id')
    batch = p.get('batch',0)+1
    domains = sum(not x.get('lead') for x in p['items'])
    made = []
    for it in todo:
        links = {'flows':it['flow_ids'],'reform':{'plan':p['id'],'uid':p['uid'],
            'order':it['order'],'batch':batch,'project':proj['key']}}
        if p.get('base') and not it.get('lead'):
            links['base'] = p['base']
        t = P.store._create_ticket_in_tx(proj['id'], '%s：%s（%s%s）' %
            (KINDS[p['kind']][0],p['title'],'先导：' if it.get('lead') else '',it['title']),by,
            body=ticket_body(p,it,domains,earlier(P,p,it['order'])),type='change',priority='normal',
            labels=[KINDS[p['kind']][0]],links=links)
        db.execute('INSERT INTO reform_dispatch VALUES(?,?,?,?,?,?,?)',
            (p['uid'],it['order'],batch,t['id'],'pending',by,now()))
        it.update(ticket=t['key'],released=now(),batch=batch)
        made.append(t)
    p['batch'] = batch
    p['revision'] += 1
    _log(p,'%s 放出第 %d 批：%s' % (by,batch,'、'.join(t['key'] for t in made)))
    return made


def _dispatch(P, proj, pid, made):
    for t in made:
        with _transaction(P.data_dir,P.store) as db:
            ps = _load(P.data_dir,proj['key'],db)
            p = next(x for x in ps if x['id']==pid)
            if getattr(P,'tenant_context',None) is not None:
                from . import tenant_policy
                from .errors import ApiError
                owner = p.get('execution_owner')
                try:
                    if not owner:
                        raise ApiError(403,'旧计划缺少执行负责人，请从受权入口重新核对')
                    who = tenant_policy.identity(P,owner)
                    if p.get('execution_connection'):
                        from .tool_access import validate_connection
                        ctx = P.tenant_context
                        connection = validate_connection(ctx.registry,ctx.tenant_id,p['execution_connection'],owner)
                        if connection['scope'] not in ('execute','develop') or proj['id'] not in connection['project_ids']:
                            raise ApiError(403,'原工具连接不再授权本项目执行')
                    tenant_policy._check(P,who,proj,'contributor')
                    tenant_policy.require_execution(P,owner)
                except ApiError as exc:
                    p['paused'] = '执行授权需要重新核对：'+str(exc)
                    p['revision'] += 1
                    _log(p,p['paused'])
                    _save(P.data_dir,proj['key'],ps,db)
                    continue
            if p.get('paused') or p.get('archived') or p.get('cancelled'):
                continue
            claimed = db.execute("UPDATE reform_dispatch SET state='claimed',updated=? WHERE ticket_id=? AND state='pending'",
                                 (now(),t['id'])).rowcount
        if not claimed:
            continue
        # A crash after claiming leaves a visible reconciliation requirement;
        # replay never resubmits an action whose external result is unknown.
        for fn in P.store.on_create:
            fn(t,t['reporter'])
        P.flow.submit(proj,t)
        with _transaction(P.data_dir,P.store) as db:
            db.execute("UPDATE reform_dispatch SET state='submitted',updated=? WHERE ticket_id=? AND state='claimed'",(now(),t['id']))


def release(P, proj: dict, pid: str, n: int | None, by: str) -> list:
    with _transaction(P.data_dir,P.store) as db:
        ps = _load(P.data_dir,proj['key'],db)
        p = next((x for x in ps if x['id']==pid),None)
        if not p:
            raise KeyError(pid)
        made = _release_in_tx(P,proj,p,n,by,db)
        _save(P.data_dir,proj['key'],ps,db)
    _dispatch(P,proj,pid,made)
    return [t['key'] for t in made]


def outcome(P, proj: dict, t: dict, passed: bool, note: str, gave_up: str = "") -> list:
    ref = (t.get('links') or {}).get('reform') or {}
    if not ref.get('plan') or t['project_id'] != proj['id']:
        return []
    made = []
    with _transaction(P.data_dir,P.store) as db:
        ps = _load(P.data_dir,proj['key'],db)
        p = next((x for x in ps if x['id']==ref['plan']),None)
        if not p or p.get('archived') or (ref.get('uid') and ref['uid'] != p['uid']):
            return []
        it = next((x for x in p['items'] if x.get('ticket')==t['key'] and x['order']==ref.get('order')),None)
        if not it or (it.get('batch') is not None and it['batch'] != ref.get('batch')):
            return []
        current = P.store.ticket(t['id'])
        if not current or current['project_id'] != proj['id'] or current['links'].get('reform') != ref:
            return []
        verdict = {'passed':passed,'note':note,'gave_up':gave_up}
        if it.get('outcome') == verdict:
            return []
        if passed and current['status'] != 'closed':
            return []
        it['outcome'] = verdict
        p['revision'] += 1
        name = '第 %d 部分「%s」' % (it['order'],it['title'])
        if not passed:
            if gave_up:
                p['paused'] = '%s验收没通过，%s。退回原因：%s' % (name,gave_up,note)
                _log(p,'暂停自动推进：'+p['paused'])
            else:
                _log(p,name+'验收没通过，正在自动重改')
        else:
            _log(p,name+'验收通过')
            if it.get('lead'):
                p['lead_passed'] = True
                p['base'] = _tip(P,proj,t)
            if p.get('auto') and not _blocked(P,p):
                made = _release_in_tx(P,proj,p,None,P.flow.BY,db)
        _save(P.data_dir,proj['key'],ps,db)
    _dispatch(P,proj,p['id'],made)
    return [t['key'] for t in made]


def _tip(P, proj: dict, t: dict) -> str:
    """The commit a piece ended on: the tip of the branch its automatic change was committed to (later human
    commits on that branch included), else that commit; "" when nothing was committed automatically."""
    from . import learn
    ad, _ = learn._adopted(P.store, t["id"])
    if not ad:
        return ""
    root = Path(proj["root"])
    return learn._resolve(root, ad.get("branch") or "") or learn._resolve(root, ad.get("commit") or "")


def configure(data_dir: Path, key: str, pid: str, auto: bool | None = None, resume: bool = False) -> dict:
    with _transaction(data_dir) as db:
        ps = _load(data_dir,key,db)
        p = next((x for x in ps if x['id']==pid),None)
        if not p:
            raise KeyError(pid)
        if p.get('archived'):
            raise ValueError('计划已归档')
        if auto is not None:
            p['auto'] = bool(auto)
            _log(p,'自动推进已'+('打开' if auto else '关闭'))
        if resume and p.pop('paused',None):
            _log(p,'人工恢复自动推进')
        p['revision'] += 1
        _save(data_dir,key,ps,db)
    return p


def resume(P, proj, pid, by):
    with _transaction(P.data_dir,P.store) as db:
        ps = _load(P.data_dir,proj['key'],db)
        p = next((x for x in ps if x['id']==pid),None)
        if not p:
            raise KeyError(pid)
        if p.get('archived'):
            raise ValueError('计划已归档')
        p.pop('paused',None)
        why = _blocked(P,p)
        pending = P.store.q("SELECT t.id FROM tickets t JOIN reform_dispatch d ON d.ticket_id=t.id WHERE d.plan_uid=? AND d.state='pending'",(p['uid'],))
        uncertain = P.store.one("SELECT ticket_id FROM reform_dispatch WHERE plan_uid=? AND state='claimed'",(p['uid'],))
        made = [] if uncertain else [P.store.ticket(row['id']) for row in pending]
        if made:
            why = ''
        if not made and not why:
            made = _release_in_tx(P,proj,p,None,by,db)
        p['revision'] += 1
        _log(p,'恢复计划；'+(why or '已核对当前批次'))
        _save(P.data_dir,proj['key'],ps,db)
    _dispatch(P,proj,pid,made)
    return dict(view(P,proj,p),opened=[t['key'] for t in made],blocked=why,
                next_action='查看本批工单' if why else '查看下一批')


def view(P, proj: dict, p: dict) -> dict:
    """A plan with the live state of each piece's ticket."""
    st, rej = {}, {}
    for it in p["items"]:
        if it.get("ticket"):
            t = P.store.ticket(it["ticket"])
            st[it["ticket"]] = t["status"] if t else "gone"
            rej[it["ticket"]] = sum(1 for e in P.store.events(t["id"]) if e["kind"] == "reject") if t else 0
    dispatch = {}
    if P.store.one("SELECT name FROM sqlite_master WHERE name='reform_dispatch'"):
        dispatch = {r['item_order']:r['state'] for r in P.store.q('SELECT item_order,state FROM reform_dispatch WHERE plan_uid=?',(p['uid'],))}
    items = [dict(it, status=st.get(it.get("ticket"), ""), rejects=rej.get(it.get("ticket"), 0),
                  dispatch_state=dispatch.get(it['order'],'legacy' if it.get('ticket') else 'not_released'),
                  evidence_validity='not_checked') for it in p["items"]]
    c = {"total": len(items), "lead": bool(_lead(p)), "released": sum(1 for i in items if i.get("ticket")), "closed": sum(1 for i in items if i["status"] == "closed"),
         "verify": sum(1 for i in items if i["status"] == "verify"), "rejected": sum(1 for i in items if i["rejects"]),
         "first_pass": sum(1 for i in items if i["status"] == "closed" and not i["rejects"])}
    return dict(p, items=items, counts=c, blocked=_blocked(P,p), kind_label=KINDS[p["kind"]][0])


def listener(P):
    """How a reform plan hears the coding line's verdicts: a passed wave releases the next, a give-up pauses it."""
    def heard(proj: dict, t: dict, v: dict) -> dict | None:
        opened = outcome(P, proj, t, v["passed"], v["note"], v["gave_up"])
        if opened:
            P.store.event(t["id"], P.flow.BY, "flow", "这一批全部验收通过，改造计划自动放出下一批：%s" % "、".join(opened))
            return {"opened": opened}
        return None
    heard.app = "改造计划"
    return heard
