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

Plans are kept in <data>/reforms/<项目代号>.json.
"""
from __future__ import annotations

import json
import re
import threading
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
_LOCK = threading.Lock()


def _file(data_dir: Path, key: str) -> Path:
    return Path(data_dir) / "reforms" / ("%s.json" % key)


def plans(data_dir: Path, key: str) -> list:
    f = _file(data_dir, key)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return []


def _save(data_dir: Path, key: str, ps: list) -> None:
    f = _file(data_dir, key)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(ps, ensure_ascii=False, indent=1), encoding="utf-8")


def plan(data_dir: Path, key: str, pid: str) -> dict:
    for x in plans(data_dir, key):
        if x["id"] == pid:
            return x
    raise KeyError(pid)


# ---------------------------------------------------------------- splitting

def split(atlas: dict, domains: list) -> list:
    """One piece per chosen domain, least entangled first: [{domain, title, flows, tables, shared, risk, order}]."""
    doms = {d["id"]: d for d in atlas.get("domains") or []}
    pick = [d for d in domains if d in doms] or [d for d in doms if d != "dom:_"]
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

def create(data_dir: Path, key: str, atlas: dict, b: dict, by: str) -> dict:
    kind = b.get("kind") if b.get("kind") in KINDS else "restructure"
    title = (b.get("title") or "").strip()
    goal = (b.get("goal") or "").strip()
    if not title:
        raise ValueError("改造计划需要一个名称")
    if not goal:
        raise ValueError("写清楚要改成什么样：目标、范围和不能变的东西")
    if not atlas.get("built"):
        raise ValueError("项目还没有知识库，没法按业务域拆分。先在知识库页建设一次")
    items = split(atlas, list(b.get("domains") or []))
    if not items:
        raise ValueError("没有选中任何业务域")
    target = (b.get("target") or "").strip().strip("/")
    if kind == "rewrite" and not target:
        raise ValueError("跨语言重写要写明新代码放在哪个目录，例如 java")
    if target and (target.startswith(".") or ".." in target.split("/") or ":" in target):
        raise ValueError("目标目录要写项目里的相对路径，例如 java")
    lead = b.get("lead") or {}
    if (lead.get("title") or "").strip() or (lead.get("body") or "").strip():
        items.insert(0, {"order": 0, "lead": True, "domain": "", "title": (lead.get("title") or "先导部分").strip()[:100],
                         "body": (lead.get("body") or "").strip()[:4000], "flows": 0, "tables": 0, "flow_ids": [], "files": [],
                         "shared": [], "unresolved": 0, "score": 0, "risk": "低"})
    with _LOCK:
        ps = plans(data_dir, key)
        n = max([int(x["id"][1:]) for x in ps if re.match(r"^r\d+$", x["id"])] + [0]) + 1
        p = {"id": "r%d" % n, "kind": kind, "title": title[:100], "goal": goal[:4000], "keep": (b.get("keep") or "").strip()[:2000],
             "target": target, "wave": max(1, min(20, int(b.get("wave") or 3))), "auto": b.get("auto", True) is not False, "by": by, "created": now(),
             "items": items, "log": []}
        ps.append(p)
        _save(data_dir, key, ps)
    return p


def remove(data_dir: Path, key: str, pid: str) -> None:
    with _LOCK:
        _save(data_dir, key, [x for x in plans(data_dir, key) if x["id"] != pid])


def _log(p: dict, text: str) -> None:
    p.setdefault("log", []).append({"at": now(), "text": text})
    p["log"] = p["log"][-50:]


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


def release(P, proj: dict, pid: str, n: int | None, by: str) -> list:
    """Open change tickets for the next `n` pieces (the plan's wave size by default); returns the new ticket keys."""
    key = proj["key"]
    with _LOCK:
        ps = plans(P.data_dir, key)
        p = next((x for x in ps if x["id"] == pid), None)
        if not p:
            raise KeyError(pid)
        ld = _lead(p)
        if ld and not ld.get("ticket"):
            todo = [ld]  # the groundwork goes alone
        elif ld and not p.get("lead_passed"):
            raise ValueError("先导部分「%s」还没验收通过，其余部分要等它" % ld["title"])
        else:
            todo = [it for it in p["items"] if not it.get("ticket")][: (n or p["wave"])]
        domains = len([x for x in p["items"] if not x.get("lead")])
        made = []
        for it in todo:
            links = {"flows": it["flow_ids"], "reform": {"plan": pid, "order": it["order"]}}
            if p.get("base") and not it.get("lead"):
                links["base"] = p["base"]  # the coding line starts this change from the lead's commit
            t = P.store.create_ticket(proj["id"], "%s：%s（%s%s）" % (KINDS[p["kind"]][0], p["title"], "先导：" if it.get("lead") else "", it["title"]), by,
                                      body=ticket_body(p, it, domains, earlier(P, p, it["order"])), type="change", priority="normal",
                                      labels=[KINDS[p["kind"]][0]], links=links)
            it["ticket"] = t["key"]
            it["released"] = now()
            made.append(t)
        if made:
            p.pop("paused", None)
            keys = "、".join(t["key"] for t in made)
            _log(p, "上一批全部验收通过，自动放出 " + keys if by == P.flow.BY else "%s 放出 %s" % (by, keys))
        _save(P.data_dir, key, ps)
    for t in made:
        P.store.event(t["id"], by, "comment", "由改造计划「%s」放出，第 %d 部分" % (p["title"], t["links"]["reform"]["order"]))
        P.flow.submit(proj, t)
    return [t["key"] for t in made]


def outcome(P, proj: dict, t: dict, passed: bool, note: str, gave_up: str = "") -> list:
    """A piece was accepted or rejected: advance the plan, or pause it (`gave_up` says why nothing will redo it
    automatically). Returns the keys of tickets it opened."""
    ref = (t.get("links") or {}).get("reform") or {}
    if not ref.get("plan"):
        return []
    with _LOCK:
        ps = plans(P.data_dir, proj["key"])
        p = next((x for x in ps if x["id"] == ref["plan"]), None)
        if not p:
            return []
        it = next((x for x in p["items"] if x.get("ticket") == t["key"]), {})
        name = "第 %d 部分「%s」" % (ref.get("order") or 0, it.get("title", ""))
        if not passed:
            if gave_up:
                p["paused"] = "%s验收没通过，%s。退回原因：%s" % (name, gave_up, note[:200])
                _log(p, "暂停自动推进：" + p["paused"])
            else:
                _log(p, "%s验收没通过，正在自动重改" % name)
            _save(P.data_dir, proj["key"], ps)
            return []
        _log(p, "%s验收通过" % name)
        if it.get("lead"):
            p["lead_passed"] = True
            p["base"] = _tip(P, proj, t)
            _log(p, "后面各部分从先导的提交 %s 开始" % p["base"][:10] if p["base"] else "先导不是自动提交的，后面各部分从项目当前代码开始")
        _save(P.data_dir, proj["key"], ps)
        if not p.get("auto") or p.get("paused") or all(x.get("ticket") for x in p["items"]):
            return []
        for x in p["items"]:
            if x.get("ticket"):
                xt = P.store.ticket(x["ticket"])
                if xt and xt["status"] != "closed":
                    return []  # the wave is not done yet
    return release(P, proj, p["id"], None, P.flow.BY)


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
    with _LOCK:
        ps = plans(data_dir, key)
        p = next((x for x in ps if x["id"] == pid), None)
        if not p:
            raise KeyError(pid)
        if auto is not None:
            p["auto"] = bool(auto)
            _log(p, "自动推进已" + ("打开" if auto else "关闭"))
        if resume and p.pop("paused", None):
            _log(p, "人工恢复自动推进")
        _save(data_dir, key, ps)
    return p


def view(P, proj: dict, p: dict) -> dict:
    """A plan with the live state of each piece's ticket."""
    st, rej = {}, {}
    for it in p["items"]:
        if it.get("ticket"):
            t = P.store.ticket(it["ticket"])
            st[it["ticket"]] = t["status"] if t else "gone"
            rej[it["ticket"]] = sum(1 for e in P.store.events(t["id"]) if e["kind"] == "reject") if t else 0
    items = [dict(it, status=st.get(it.get("ticket"), ""), rejects=rej.get(it.get("ticket"), 0)) for it in p["items"]]
    c = {"total": len(items), "lead": bool(_lead(p)), "released": sum(1 for i in items if i.get("ticket")), "closed": sum(1 for i in items if i["status"] == "closed"),
         "verify": sum(1 for i in items if i["status"] == "verify"), "rejected": sum(1 for i in items if i["rejects"]),
         "first_pass": sum(1 for i in items if i["status"] == "closed" and not i["rejects"])}
    return dict(p, items=items, counts=c, kind_label=KINDS[p["kind"]][0])


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
