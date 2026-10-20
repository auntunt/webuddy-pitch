"""Box-select a spot on a page and find the code behind it.

The client drags a box around what is wrong on a page of their own system and says one sentence. What is inside
the box comes to webuddy as data, not as a picture: the page address, the visible texts, element ids, names and
classes, source markers when the front end was built with them, and the API requests the page made. From that
the code is found in three layers, from exact to rough:

1. Source markers. Front ends built with code-inspector-plugin (or Vue's inspector) carry `file:line` on every
   element (`data-insp-path`, `data-v-inspector`). Exact to the line; only for modern front ends.
2. Knowledge-base matching, for JSP, FreeMarker, OFBiz widgets and other old templates. The texts in the box are
   looked up in the project's files, and through the label files (i18n: .properties, *UiLabels.xml, locale
   JSON) back to the label key and the templates that use the key: "Request" → CommonRequest →
   PersonTrainingForms.xml. Field names and ids count too. Candidates are ranked, each with the matches that put
   it there; rare texts weigh more than common ones.
3. API reverse lookup, for wrong data. The requests the page made are matched to entry points in the call graph,
   then to business flows and the tables they write.

Generic feedback tools (screenshots with a note) do not know where the code is; inspector plugins only work for
modern front ends. Layers 2 and 3 need the project's knowledge base, which is why this lives here.

The capture comes from a bookmarklet the client runs on their own page (a per-project token, made by a person on
the platform, lets it post; it can only add captures), or from the platform's own form. Captures are kept in
<data>/pins/<id>.json; a capture can start a requirement conversation (tmh/platform/intake.py).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from .errors import ApiError

MARKER_ATTRS = ("data-insp-path", "data-v-inspector", "data-inspector", "data-source", "data-loc")
TEMPLATE_EXT = (".vue", ".jsx", ".tsx", ".html", ".htm", ".jsp", ".ftl", ".vm", ".xml", ".cshtml", ".aspx", ".ascx", ".erb", ".php", ".js", ".ts")
LABEL_FILE = re.compile(r"(\.properties$|UiLabels\.xml$|(^|/)(locales?|i18n|lang)/[^/]+\.(json|ya?ml|js|ts)$|Resources?\.resx$)", re.I)
SKIP_DIR = re.compile(r"(^|/)(node_modules|dist|build|target|\.git|\.tmh|vendor|bower_components|coverage)/")
MAX_TEXTS = 30
MAX_FILES = 8


def pdir(data_dir: Path) -> Path:
    return Path(data_dir) / "pins"


# ---------------------------------------------------------------- what came in

def clean_capture(c: dict) -> dict:
    """Keep only what locating uses, bounded."""
    def strs(xs, n, size=120):
        out = []
        for x in xs or []:
            x = re.sub(r"\s+", " ", str(x or "")).strip()[:size]
            if x and x not in out:
                out.append(x)
        return out[:n]
    url = str(c.get("url") or "")[:500]
    els = []
    for e in (c.get("elements") or [])[:80]:
        if not isinstance(e, dict):
            continue
        els.append({k: str(e.get(k) or "")[:200] for k in ("tag", "id", "name", "cls", "text", "marker", "label")})
    return {"url": url, "title": str(c.get("title") or "")[:200], "texts": strs(c.get("texts"), MAX_TEXTS),
            "elements": els, "requests": strs(c.get("requests"), 40, 300), "box": c.get("box") if isinstance(c.get("box"), dict) else {},
            "note": str(c.get("note") or "").strip()[:1000], "screenshot": ""}


# ---------------------------------------------------------------- the repository

def _files(root: Path) -> list[str]:
    r = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True)
    files = r.stdout.splitlines() if r.returncode == 0 else [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
    return [f for f in files if not SKIP_DIR.search(f)]


def _grep(root: Path, needle: str, files: list[str]) -> dict:
    """file -> first line number containing the literal needle, over the given files."""
    if not needle or not files:
        return {}
    r = subprocess.run(["git", "-C", str(root), "grep", "-n", "-I", "-F", "--no-color", "-e", needle, "--"] + files[:4000],
                       capture_output=True, text=True, errors="replace")
    out = {}
    for line in r.stdout.splitlines():
        m = re.match(r"^(.*?):(\d+):", line)
        if m and m.group(1) not in out:
            out[m.group(1)] = int(m.group(2))
    return out


def _label_keys(root: Path, text: str, label_files: list[str]) -> dict:
    """label key -> (file, line) for label files whose value is exactly this text."""
    keys = {}
    hits = _grep(root, text, label_files)
    for f, _ in hits.items():
        try:
            lines = (root / f).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            if text not in line:
                continue
            k = None
            if f.endswith(".properties"):
                m = re.match(r"^\s*([\w.\-]+)\s*[=:]\s*(.*)$", line)
                if m and m.group(2).strip() == text:
                    k = m.group(1)
            elif f.endswith(".xml"):  # OFBiz: <property key="X"> … <value xml:lang="en">text</value>
                if re.search(r">\s*%s\s*<" % re.escape(text), line):
                    for j in range(i, max(-1, i - 40), -1):
                        m = re.search(r'<property key="([^"]+)"', lines[j])
                        if m:
                            k = m.group(1)
                            break
            else:
                m = re.search(r'["\']?([\w.\-]+)["\']?\s*:\s*["\']%s["\']' % re.escape(text), line)
                if m:
                    k = m.group(1)
            if k and k not in keys:
                keys[k] = (f, i + 1)
    return keys


def _marker(m: str):
    """'src/views/Leave.vue:12:5' or 'src/views/Leave.vue:12:5:div' -> (path, line)."""
    m = (m or "").strip()
    x = re.match(r"^(.+?\.[A-Za-z]{1,6}):(\d+)(?::\d+)?(?::\w+)?$", m)
    return (x.group(1).lstrip("./"), int(x.group(2))) if x else None


# ---------------------------------------------------------------- locating

def locate(root: Path, cap: dict, graph=None) -> dict:
    root = Path(root)
    files = _files(root)
    have = set(files)
    out = {"layer1": [], "layer2": [], "layer3": [], "basis": []}

    # 1. source markers
    seen = set()
    for e in cap["elements"]:
        mk = _marker(e.get("marker"))
        if not mk:
            continue
        path, line = mk
        path = next((f for f in files if f == path or f.endswith("/" + path)), path)
        if (path, line) in seen:
            continue
        seen.add((path, line))
        out["layer1"].append({"file": path, "line": line, "exists": path in have, "why": "页面元素带源码标记"})
    if out["layer1"]:
        out["basis"].append("第 1 层：框内元素带源码标记，精确到行")

    # 2. texts, label keys, field names in templates
    templates = [f for f in files if f.endswith(TEMPLATE_EXT) and not LABEL_FILE.search(f)]
    labels = [f for f in files if LABEL_FILE.search(f)]
    words = []
    for t in cap["texts"]:
        if 1 < len(t) <= 60:
            words.append(("text", t))
    for e in cap["elements"]:
        for k in ("id", "name"):
            v = e.get(k) or ""
            if re.fullmatch(r"[A-Za-z_][\w\-]{2,60}", v) and not re.search(r"\d{4,}|^(el|ant|ivu|van)-", v):
                words.append((k, v))
    score, why = {}, {}
    for kind, w in dict.fromkeys(words):
        direct = _grep(root, w, templates)
        via = {}
        if kind == "text":
            for key, (lf, ll) in _label_keys(root, w, labels).items():
                for f, ln in _grep(root, key, templates).items():
                    via.setdefault(f, (ln, key, lf, ll))
        found = set(direct) | set(via)
        if not found:
            continue
        weight = 1.0 / math.log2(1 + len(found))  # a text found in one file says more than one found in fifty
        for f in found:
            score[f] = score.get(f, 0) + weight * (1.5 if f in via else 1.0)
            if f in via:
                ln, key, lf, ll = via[f]
                why.setdefault(f, []).append({"line": ln, "match": "“%s”→ 标签 %s（%s:%d）" % (w, key, lf, ll)})
            else:
                why.setdefault(f, []).append({"line": direct[f], "match": "%s“%s”" % ({"text": "文字", "id": "id ", "name": "字段名 "}[kind], w)})
    path = urlparse(cap["url"]).path
    tail = [x for x in re.split(r"[/.]", path) if x and not x.isdigit() and x not in ("control", "index", "html", "jsp", "do", "action")][-2:]
    for f in list(score):  # the page address names the screen ("EditEmployeeTrainings" → …Training…)
        stem = f.rsplit("/", 1)[-1].lower()
        if any(len(x) > 3 and (x.lower() in stem or stem.split(".")[0] in x.lower()) for x in tail):
            score[f] += 0.5
            why[f].append({"line": 0, "match": "页面地址 %s" % path})
    ranked = sorted(score, key=lambda f: -score[f])[:MAX_FILES]
    out["layer2"] = [{"file": f, "score": round(score[f], 2), "line": min([x["line"] for x in why[f] if x["line"]] or [0]),
                      "matches": why[f][:6]} for f in ranked]
    if out["layer2"]:
        out["basis"].append("第 2 层：框内文字和字段名在模板和标签文件里匹配，%d 个候选，按匹配的稀有程度排序" % len(ranked))

    # 3. the API requests the page made → entry points → flows → tables
    if graph is not None and cap["requests"]:
        eps = [n for n in graph.nodes("ep")] if hasattr(graph, "nodes") else []
        for req in cap["requests"]:
            rp = urlparse(req).path.rstrip("/")
            if not rp:
                continue
            for ep in eps:
                trig = (ep.get("name") or "").split(" ")[-1].rstrip("/")
                if not trig or not trig.startswith("/"):
                    continue
                pat = "^" + re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(trig)) + "$"
                if re.search(pat, rp) or rp.endswith(trig):
                    flows = [e["src"] for e in graph.inn(ep["id"], "entry")]
                    tables = []
                    for fid in flows:
                        tables += [(graph.node(e["dst"]) or {}).get("name", e["dst"]) for e in graph.out(fid, "uses")]
                    out["layer3"].append({"request": req, "entry": ep.get("name"), "file": ep.get("file"), "line": ep.get("line"),
                                          "flows": [(graph.node(f) or {}).get("name", f) for f in flows], "flow_ids": flows,
                                          "tables": list(dict.fromkeys(tables))[:6]})
                    break
        if out["layer3"]:
            out["basis"].append("第 3 层：页面发出的接口请求对上了 %d 个后端入口" % len(out["layer3"]))
    if not any(out[k] for k in ("layer1", "layer2", "layer3")):
        out["basis"].append("框内的文字、字段名和接口在代码里都没找到：可能是动态拼出来的，转人工看")
    return out


# ---------------------------------------------------------------- captures

def save(P, p: dict, cap: dict, by: str, via: str) -> dict:
    cap = clean_capture(cap)
    if not (cap["texts"] or cap["elements"] or cap["requests"]):
        raise ApiError(400, "框里没有拿到文字、元素或接口")
    try:
        from ..graph import Graph
        g = Graph(P.root(p))
    except Exception:  # noqa: BLE001 - no knowledge base: layers 1 and 2 still work
        g = None
    res = locate(P.root(p), cap, g)
    pin = {"id": uuid.uuid4().hex[:12], "project": p["key"], "by": by, "via": via, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "capture": cap, "found": res}
    f = pdir(P.data_dir) / ("%s.json" % pin["id"])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(pin, ensure_ascii=False, indent=1), encoding="utf-8")
    return pin


def load(data_dir: Path, pid: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{12}", pid or ""):
        raise ApiError(404, "没有这条框选记录")
    f = pdir(data_dir) / ("%s.json" % pid)
    if not f.exists():
        raise ApiError(404, "没有这条框选记录")
    return json.loads(f.read_text(encoding="utf-8"))


def recent(data_dir: Path, key: str, limit: int = 20) -> list:
    d = pdir(data_dir)
    rows = []
    for f in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True) if d.is_dir() else []:
        try:
            x = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if x.get("project") == key:
            rows.append(x)
        if len(rows) >= limit:
            break
    return rows


def summary(pin: dict) -> str:
    """What the requirement conversation and the ticket carry about where it is."""
    c, r = pin["capture"], pin["found"]
    L = ["页面：%s%s" % (c["url"] or "（未知）", "（%s）" % c["title"] if c["title"] else ""),
         "框内文字：%s" % "、".join(c["texts"][:8])]
    if r["layer1"]:
        L.append("源码位置：" + "、".join("%s:%d" % (x["file"], x["line"]) for x in r["layer1"][:5]))
    if r["layer2"]:
        L.append("候选文件：" + "；".join("%s%s（%s）" % (x["file"], ":%d" % x["line"] if x["line"] else "", "，".join(m["match"] for m in x["matches"][:2]))
                                     for x in r["layer2"][:3]))
    if r["layer3"]:
        L.append("后端：" + "；".join("%s → %s" % (x["entry"], "、".join(x["flows"]) or "（未关联业务流）") for x in r["layer3"][:3]))
    return "\n".join(L)


# ---------------------------------------------------------------- the client's bookmarklet

def _tokens(data_dir: Path) -> Path:
    return Path(data_dir) / "pins" / "tokens.json"


def issue_token(data_dir: Path, key: str, by: str) -> str:
    """A per-project token that can only add captures. Stored hashed; issuing a new one replaces the old."""
    tok = secrets.token_urlsafe(18)
    f = _tokens(data_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    d = {h: v for h, v in d.items() if v["project"] != key}
    d[hashlib.sha256(tok.encode()).hexdigest()] = {"project": key, "by": by, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return tok


def token_project(data_dir: Path, tok: str) -> str:
    f = _tokens(data_dir)
    if not tok or not f.exists():
        return ""
    return (json.loads(f.read_text(encoding="utf-8")).get(hashlib.sha256(tok.encode()).hexdigest()) or {}).get("project", "")


def has_token(data_dir: Path, key: str) -> bool:
    f = _tokens(data_dir)
    return f.exists() and any(v["project"] == key for v in json.loads(f.read_text(encoding="utf-8")).values())


BOOKMARKLET = r"""(function(){if(window.__wbPin)return;window.__wbPin=1;var E='%(endpoint)s';
var o=document.createElement('div');o.style.cssText='position:fixed;inset:0;z-index:2147483647;cursor:crosshair;background:rgba(20,80,200,.06)';
var b=document.createElement('div');b.style.cssText='position:fixed;border:2px solid #1a56db;background:rgba(26,86,219,.12);pointer-events:none';o.appendChild(b);
var tip=document.createElement('div');tip.textContent='拖一个框圈住有问题的地方（Esc 取消）';tip.style.cssText='position:fixed;top:8px;left:50%%;transform:translateX(-50%%);background:#1a56db;color:#fff;padding:6px 12px;border-radius:6px;font:14px sans-serif';o.appendChild(tip);
document.body.appendChild(o);var x0,y0;function end(){o.remove();window.__wbPin=0;document.removeEventListener('keydown',k)}function k(e){if(e.key==='Escape')end()}document.addEventListener('keydown',k);
o.onmousedown=function(e){x0=e.clientX;y0=e.clientY;b.style.left=x0+'px';b.style.top=y0+'px';b.style.width=b.style.height='0'};
o.onmousemove=function(e){if(x0==null)return;b.style.left=Math.min(x0,e.clientX)+'px';b.style.top=Math.min(y0,e.clientY)+'px';b.style.width=Math.abs(e.clientX-x0)+'px';b.style.height=Math.abs(e.clientY-y0)+'px'};
o.onmouseup=function(e){var r={left:Math.min(x0,e.clientX),top:Math.min(y0,e.clientY),right:Math.max(x0,e.clientX),bottom:Math.max(y0,e.clientY)};o.style.display='none';
 var els=[],texts=[],all=document.body.getElementsByTagName('*');for(var i=0;i<all.length&&els.length<80;i++){var n=all[i],q=n.getBoundingClientRect();
  if(q.width&&q.height&&q.left>=r.left-2&&q.top>=r.top-2&&q.right<=r.right+2&&q.bottom<=r.bottom+2){var mk='';['data-insp-path','data-v-inspector','data-inspector','data-source','data-loc'].forEach(function(a){if(!mk&&n.getAttribute(a))mk=n.getAttribute(a)});
   var own='';for(var c=n.firstChild;c;c=c.nextSibling)if(c.nodeType===3)own+=c.nodeValue;own=own.replace(/\s+/g,' ').trim();if(!own&&n.placeholder)own=n.placeholder;if(!own&&n.title)own=n.title;
   if(own&&texts.indexOf(own)<0)texts.push(own);els.push({tag:n.tagName.toLowerCase(),id:n.id||'',name:n.getAttribute('name')||'',cls:(n.className&&n.className.baseVal===undefined?n.className:'')+'',text:own.slice(0,200),marker:mk})}}
 var reqs=(performance.getEntriesByType('resource')||[]).filter(function(x){return x.initiatorType==='xmlhttprequest'||x.initiatorType==='fetch'}).slice(-40).map(function(x){return x.name});
 var note=prompt('这里有什么问题？说一句就行（例如：这个金额不对 / 按钮要放到右边）')||'';end();
 fetch(E,{method:'POST',headers:{'Content-Type':'text/plain'},body:JSON.stringify({url:location.href,title:document.title,box:r,texts:texts,elements:els,requests:reqs,note:note})})
  .then(function(x){return x.json()}).then(function(d){alert(d.message||'已发送到 webuddy')}).catch(function(){alert('发送失败：webuddy 连不上')})}})();"""


def bookmarklet(base: str, tok: str) -> str:
    js = BOOKMARKLET % {"endpoint": base.rstrip("/") + "/capture/" + tok}
    return "javascript:" + re.sub(r"\s*\n\s*", "", js)
