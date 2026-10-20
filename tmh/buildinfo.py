"""Project build analysis: what the system is made of, how it is built and run, and where it is fragile.

Everything here is read from files (build descriptors, imports, deployment
descriptors, config keys) and from the knowledge graph, so each item carries the
file it came from. Secret values are never read into the result: for config files
only key names, JDBC URL host/database parts and counts are kept.
The narrative ("what this means for maintenance") is the agent's job, written to
the 系统总览 page; this module only supplies the facts it builds on.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from .fsutil import _read_text, iter_files, read_text, rel

# import prefix → component; also used when there is no pom (decompiled or copied sources)
IMPORT_MARKERS = [
    ("Spring Boot", r"org\.springframework\.boot\."),
    ("Spring MVC", r"org\.springframework\.web\.bind\.annotation\."),
    ("Spring Data JPA", r"org\.springframework\.data\.(jpa|repository)\."),
    ("JPA / Hibernate", r"(javax|jakarta)\.persistence\.|org\.hibernate\."),
    ("JdbcTemplate", r"org\.springframework\.jdbc\.core\."),
    ("MyBatis", r"org\.apache\.ibatis\.|org\.mybatis\."),
    ("MyBatis-Plus", r"com\.baomidou\.mybatisplus\."),
    ("Redis", r"redis\.clients\.|org\.springframework\.data\.redis\.|org\.redisson\."),
    ("Elasticsearch", r"org\.elasticsearch\.|co\.elastic\."),
    ("FastDFS", r"org\.csource\.|com\.github\.tobato\.fastdfs"),
    ("Kafka", r"org\.apache\.kafka\."),
    ("RabbitMQ", r"com\.rabbitmq\.|org\.springframework\.amqp\."),
    ("RocketMQ", r"org\.apache\.rocketmq\."),
    ("ActiveMQ / JMS", r"org\.apache\.activemq\.|javax\.jms\."),
    ("Quartz", r"org\.quartz\."),
    ("Spring Scheduling", r"org\.springframework\.scheduling\."),
    ("Shiro", r"org\.apache\.shiro\."),
    ("Spring Security", r"org\.springframework\.security\."),
    ("Dubbo", r"(org|com)\.apache\.dubbo\.|com\.alibaba\.dubbo\."),
    ("Spring Cloud", r"org\.springframework\.cloud\."),
    ("Activiti / Flowable", r"org\.(activiti|flowable|camunda)\."),
    ("Apache POI", r"org\.apache\.poi\."),
    ("iText / PDF", r"com\.itextpdf\.|com\.lowagie\.|org\.apache\.pdfbox\."),
    ("HttpClient", r"org\.apache\.http\.|okhttp3\.|org\.apache\.commons\.httpclient\."),
    ("Fastjson", r"com\.alibaba\.fastjson\."),
    ("Jackson", r"com\.fasterxml\.jackson\."),
    ("WebService (CXF/Axis)", r"org\.apache\.(cxf|axis)\.|javax\.jws\."),
    ("WebSocket", r"javax\.websocket\.|org\.springframework\.web\.socket\."),
    ("Servlet", r"javax\.servlet\.|jakarta\.servlet\."),
]
IMPORT_RX = re.compile(r"^import\s+(?:static\s+)?([\w.]+)", re.M)
DECOMPILED_RX = re.compile(r"Decompiled with (CFR|Procyon|Fernflower|JD-)|Could not load the following classes|WARNING - Removed try catching itself", re.I)
DEPLOY_NAMES = re.compile(r"^(Dockerfile.*|docker-compose.*\.ya?ml|compose\.ya?ml|Jenkinsfile|\.gitlab-ci\.yml|.*\.(sh|bat|cmd|command)|nginx.*\.conf|.*\.conf|server\.xml|context\.xml|catalina\.properties|web\.xml)$", re.I)
CONFIG_NAMES = re.compile(r"^(application|bootstrap|config|jdbc|db|database|redis|system)[\w.-]*\.(properties|ya?ml)$", re.I)
SECRET_KEY = re.compile(r"(password|passwd|pwd|secret|token|access[-_.]?key|private[-_.]?key)", re.I)
JDBC_RX = re.compile(r"jdbc:(\w+):(?://)?([^/;?\s'\"]+)?[/:;]?(?:databaseName=)?([\w-]*)", re.I)


def _compose_services(text: str) -> list[dict]:
    """Minimal docker-compose reader: service names, images, ports. Indentation based, no YAML library."""
    out, cur, in_services, base, key = [], None, False, None, ""
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        ind = len(line) - len(line.lstrip())
        s = line.strip()
        if ind == 0:
            in_services = s.startswith("services:")
            continue
        if not in_services:
            continue
        if base is None:
            base = ind
        if ind == base and s.endswith(":"):
            cur = {"name": s[:-1].strip("'\""), "image": "", "build": False, "ports": []}
            out.append(cur)
            key = ""
            continue
        if cur is None:
            continue
        m = re.match(r"(\w[\w-]*):\s*(.*)$", s)
        if m and ind > base:
            key, val = m.group(1), m.group(2).strip().strip("'\"")
            if key == "image":
                cur["image"] = val
            elif key == "build":
                cur["build"] = True
            elif key == "ports" and val.startswith("["):
                cur["ports"] += [p.strip(" '\"") for p in val.strip("[]").split(",") if p.strip()]
        elif s.startswith("- ") and key == "ports":
            cur["ports"].append(s[2:].strip("'\""))
    return out


def _config_facts(text: str, suffix: str) -> dict:
    keys, secrets, jdbc = [], 0, []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"([\w.\-\[\]]+)\s*[:=]\s*(.*)$", s)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        keys.append(k)
        if SECRET_KEY.search(k) and v and not v.startswith("${"):
            secrets += 1
        jm = JDBC_RX.search(v)
        if jm:
            jdbc.append({"db": jm.group(1).lower(), "host": (jm.group(2) or "").split("@")[-1], "name": jm.group(3) or ""})
    interesting = [k for k in keys if re.search(r"datasource|redis|server\.(port|servlet|context)|context-path|mq|kafka|rabbit|elasticsearch|fdfs|fastdfs|mail|oss|minio|ftp", k, re.I)]
    return {"keys": len(keys), "interesting": interesting[:30], "plain_secrets": secrets, "jdbc": jdbc}


def analyze(root: Path, disc: dict | None = None, g=None, flows: list[dict] | None = None) -> dict:
    from . import discover as discmod
    root = root.resolve()
    disc = disc or discmod.discover(root)
    comp_files: dict[str, Counter] = defaultdict(Counter)
    decompiled, uesc, java_files, java_lines = [], 0, 0, 0
    deploy, configs, artifacts = [], [], []
    pkg_roots = Counter()
    for p in iter_files(root, include_binary_names=True):
        rp = rel(root, p)
        name = p.name
        suf = p.suffix.lower()
        if suf in (".war", ".jar", ".ear") and "/lib/" not in "/" + rp and "WEB-INF" not in rp:
            try:
                artifacts.append({"file": rp, "mb": round(p.stat().st_size / 1048576, 1)})
            except OSError:
                pass
            continue
        if suf == ".java":
            text = _read_text(p) or ""  # raw: \\uXXXX still escaped, so they can be counted
            java_files += 1
            java_lines += text.count("\n") + 1
            head = text[:4000]
            if DECOMPILED_RX.search(head) or DECOMPILED_RX.search(text[-2000:]):
                decompiled.append(rp)
            if "\\u" in text and re.search(r"\\u[4-9][0-9a-f]{3}", text):
                uesc += 1
            pm = re.search(r"^package\s+([\w.]+)", head, re.M)
            if pm:
                pkg_roots[".".join(pm.group(1).split(".")[:2])] += 1
            imps = IMPORT_RX.findall(head)
            for comp, rx in IMPORT_MARKERS:
                if any(re.match(rx, i) for i in imps):
                    comp_files[comp][rp] += 1
            continue
        if DEPLOY_NAMES.match(name) and suf not in (".java",):
            if suf in (".sh", ".bat", ".cmd", ".command") and rp.count("/") > 3:
                continue
            text = read_text(p) or ""
            item = {"file": rp, "kind": _deploy_kind(name, text)}
            if "compose" in name.lower() and suf in (".yml", ".yaml"):
                item["services"] = _compose_services(text)
            elif name.lower().startswith("dockerfile"):
                fm = re.search(r"^FROM\s+(\S+)", text, re.M | re.I)
                item["from"] = fm.group(1) if fm else ""
            elif suf == ".conf" and "server" in text and ("proxy_pass" in text or "listen" in text):
                item["kind"] = "Nginx"
                item["proxy"] = re.findall(r"proxy_pass\s+([^;]+);", text)[:8]
                item["listen"] = re.findall(r"listen\s+([^;]+);", text)[:4]
            elif item["kind"] == "其他配置":
                continue
            deploy.append(item)
            continue
        if CONFIG_NAMES.match(name):
            text = read_text(p) or ""
            c = _config_facts(text, suf)
            c["file"] = rp
            configs.append(c)
    # build output is skipped by iter_files; look for the deliverable explicitly
    for pat in ("dist/*", "target/*", "build/libs/*", "out/*", "*/target/*", "*/dist/*"):
        for p in sorted(root.glob(pat)):
            if p.suffix.lower() in (".war", ".jar", ".ear") and p.is_file() and not any(a["file"] == rel(root, p) for a in artifacts):
                artifacts.append({"file": rel(root, p), "mb": round(p.stat().st_size / 1048576, 1)})
    j = disc.get("java", {})
    components = []
    for comp, rx in IMPORT_MARKERS:
        files = comp_files.get(comp)
        if files:
            components.append({"name": comp, "files": len(files), "example": sorted(files)[0]})
    have = {c["name"] for c in components}
    same = {"Hibernate/JPA": "JPA / Hibernate", "Activiti/Flowable": "Activiti / Flowable", "POI": "Apache POI"}
    for fw in j.get("frameworks", []):  # declared in pom/gradle but not seen in imports (or not import-based, e.g. JSP)
        if fw in have or same.get(fw) in have or (fw == "Spring" and any(n.startswith("Spring") for n in have)) or fw.startswith("MyBatis XML"):
            continue
        components.append({"name": fw, "files": 0, "example": "构建文件声明"})
    components.sort(key=lambda c: -c["files"])

    res = {
        "languages": disc.get("languages", {}), "loc": disc.get("loc", {}), "total_files": disc.get("total_files", 0),
        "java": {"files": java_files, "lines": java_lines, "build": j.get("build", ""), "version": j.get("java_version", ""),
                 "spring_boot": j.get("spring_boot", ""), "modules": [{"path": m.get("path"), "artifact": m.get("artifact", ""), "packaging": m.get("packaging", "")}
                                                                      for m in j.get("modules", [])][:40],
                 "web_xml": j.get("web_xml", []), "packages": [k for k, _ in pkg_roots.most_common(5)]},
        "dotnet": {"projects": len(disc.get("dotnet", {}).get("projects", [])), "frameworks": disc.get("dotnet", {}).get("frameworks", [])},
        "components": components, "deploy": deploy[:40], "configs": configs[:30], "artifacts": artifacts[:20],
        "decompiled": {"files": len(decompiled), "share": round(len(decompiled) / java_files, 3) if java_files else 0, "examples": decompiled[:5]},
        "unicode_escaped_files": uesc,
    }
    if g is not None:
        res.update(_graph_facts(g))
    if flows is not None:
        res.update(_flow_facts(flows))
    res["risks"] = _risks(res)
    return res


def _deploy_kind(name: str, text: str) -> str:
    n = name.lower()
    if n.startswith("dockerfile"):
        return "Dockerfile"
    if "compose" in n:
        return "Docker Compose"
    if n in ("jenkinsfile", ".gitlab-ci.yml"):
        return "CI 流水线"
    if n in ("server.xml", "context.xml", "catalina.properties"):
        return "Tomcat"
    if n == "web.xml":
        return "web.xml"
    if n.endswith((".sh", ".bat", ".cmd", ".command")):
        return "脚本"
    return "其他配置"


def _graph_facts(g) -> dict:
    layers = Counter()
    for n in g.nodes("cls"):
        layers[n["data"].get("layer") or "other"] += 1
    fns = g.nodes("fn")
    big = sorted((n for n in fns if n["data"].get("lines", 0) >= 150), key=lambda n: -n["data"]["lines"])
    hubs = sorted((n for n in fns if n["data"].get("fan_in", 0) >= 15 and n["data"].get("layer") in ("service", "dao", "manager", "other", "component")),
                  key=lambda n: -n["data"]["fan_in"])
    eps = Counter(n["data"].get("entry_kind", "") for n in g.nodes("ep"))
    tests = sum(1 for n in g.nodes("file") if n["data"].get("test"))
    return {"layers": dict(layers.most_common()), "entries": dict(eps.most_common()), "test_files": tests,
            "big_methods": {"count": len(big), "top": [{"name": n["label"], "lines": n["data"]["lines"], "at": "%s:%d" % (n["file"], n["line"])} for n in big[:12]]},
            "hubs": [{"name": n["label"], "fan_in": n["data"]["fan_in"], "at": "%s:%d" % (n["file"], n["line"])} for n in hubs[:12]],
            "tables": len(g.nodes("tbl")), "state_machines": len(g.nodes("sm"))}


def _flow_facts(flows: list[dict]) -> dict:
    dyn, dispatch, unres, effects = Counter(), [], 0, Counter()
    reach = 0
    for f in flows:
        if f["crud"]:
            reach += 1
        for t in f["crud"]:
            if t.startswith("〈动态"):
                dyn[t] += 1
        for n in f["nodes"]:
            if n.get("dispatch"):
                dispatch.append(n["label"])
        unres += len(f["unresolved"])
        for s in f["side_effects"]:
            effects[s["kind"]] += 1
    disp = Counter(dispatch)
    return {"flow_reach": {"flows": len(flows), "with_tables": reach},
            "dynamic_tables": [{"expr": k, "flows": v} for k, v in dyn.most_common(10)],
            "dispatch_points": [{"label": k, "flows": v} for k, v in disp.most_common(10)],
            "unresolved_calls": unres, "side_effects": dict(effects.most_common())}


def _risks(r: dict) -> list[dict]:
    """Maintenance risks that follow directly from the facts; each says why it matters."""
    out = []
    d = r["decompiled"]
    if d["files"]:
        out.append({"level": "高" if d["share"] > 0.3 else "中", "title": "源码来自反编译（%d 个文件，占 %.0f%%）" % (d["files"], d["share"] * 100),
                    "why": "注释、局部变量名和部分泛型信息已丢失，个别方法可能反编译失败；改动前要和线上包核对行为。", "at": d["examples"][:3]})
    if r.get("test_files", 1) == 0:
        out.append({"level": "高", "title": "没有自动化测试", "why": "改动只能靠人工回归；先给要改的业务流补特征测试再动手。", "at": []})
    for x in r.get("dynamic_tables", [])[:1]:
        n = sum(y["flows"] for y in r["dynamic_tables"])
        out.append({"level": "中", "title": "表名在运行时决定（%d 条业务流）" % n,
                    "why": "例如 %s。静态分析只能看到“写了某张表”，具体是哪张要看表单/配置数据，影响分析需结合数据库配置。" % x["expr"], "at": []})
    if r.get("dispatch_points"):
        out.append({"level": "中", "title": "按配置分派的扩展点 %d 处" % len(r["dispatch_points"]),
                    "why": "如 %s。实际执行哪个实现由配置或数据决定，改接口时所有实现都要回归。" % r["dispatch_points"][0]["label"], "at": []})
    secrets = [c for c in r["configs"] if c["plain_secrets"]]
    if secrets:
        out.append({"level": "中", "title": "配置文件中有明文密码类配置（%d 个文件）" % len(secrets),
                    "why": "迁移或交付时需要改成环境变量或加密配置；这里只统计了键名，没有读取值。", "at": [c["file"] for c in secrets[:3]]})
    bm = r.get("big_methods", {})
    if bm.get("count", 0) >= 10:
        out.append({"level": "低", "title": "超长方法 %d 个（≥150 行）" % bm["count"],
                    "why": "最长的是 %s（%d 行）。这类方法通常集中了多条业务规则，是改动最容易出错的地方。" % (bm["top"][0]["name"], bm["top"][0]["lines"]), "at": [bm["top"][0]["at"]]})
    if r.get("unicode_escaped_files"):
        out.append({"level": "低", "title": "%d 个文件里中文写成 \\uXXXX" % r["unicode_escaped_files"],
                    "why": "按中文搜索源码会搜不到；tmh 已在分析时还原，手工 grep 时要注意。", "at": []})
    return out
