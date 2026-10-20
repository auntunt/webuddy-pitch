"""Technology-stack discovery for Java (Maven/Gradle), .NET (sln/csproj) and Go repositories."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from .fsutil import iter_files, read_text, rel

LANG_BY_SUFFIX = {
    ".java": "Java", ".kt": "Kotlin", ".groovy": "Groovy", ".scala": "Scala", ".cs": "C#", ".vb": "VB.NET",
    ".go": "Go", ".fs": "F#", ".xml": "XML", ".sql": "SQL", ".jsp": "JSP", ".aspx": "ASPX", ".ascx": "ASPX",
    ".cshtml": "Razor", ".js": "JavaScript", ".ts": "TypeScript", ".vue": "Vue", ".html": "HTML",
    ".properties": "Config", ".yml": "Config", ".yaml": "Config", ".config": "Config", ".json": "Config",
}

FRAMEWORK_MARKERS = [
    ("Spring Boot", r"org\.springframework\.boot"),
    ("Spring MVC", r"org\.springframework:spring-webmvc|spring-webmvc"),
    ("Spring", r"org\.springframework"),
    ("Struts 1", r"struts:struts|org\.apache\.struts:struts-core"),
    ("Struts 2", r"org\.apache\.struts:struts2"),
    ("MyBatis", r"mybatis"),
    ("MyBatis-Plus", r"mybatis-plus"),
    ("Hibernate/JPA", r"hibernate|javax\.persistence|jakarta\.persistence"),
    ("Dubbo", r"dubbo"),
    ("Spring Cloud", r"spring-cloud"),
    ("Shiro", r"shiro"),
    ("Quartz", r"quartz"),
    ("EJB", r"javax\.ejb|jakarta\.ejb"),
    ("Activiti/Flowable", r"activiti|flowable|camunda"),
    ("JasperReports", r"jasperreports"),
    ("POI", r"org\.apache\.poi"),
]
DOTNET_MARKERS = [
    ("ASP.NET MVC 5", r"Microsoft\.AspNet\.Mvc|System\.Web\.Mvc"),
    ("ASP.NET Web API 2", r"Microsoft\.AspNet\.WebApi|System\.Web\.Http"),
    ("ASP.NET Core", r"Microsoft\.NET\.Sdk\.Web|Microsoft\.AspNetCore"),
    ("Entity Framework 6", r"\bEntityFramework\b"),
    ("EF Core", r"Microsoft\.EntityFrameworkCore"),
    ("WCF", r"System\.ServiceModel"),
    ("Dapper", r"\bDapper\b"),
    ("NHibernate", r"NHibernate"),
    ("Newtonsoft.Json", r"Newtonsoft\.Json"),
    ("log4net", r"log4net"),
    ("Quartz.NET", r"\bQuartz\b"),
    ("Hangfire", r"Hangfire"),
    ("Crystal Reports", r"CrystalDecisions"),
]


def _strip_ns(tree: ET.Element) -> ET.Element:
    for el in tree.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return tree


def parse_pom(text: str) -> dict:
    try:
        root = _strip_ns(ET.fromstring(text))
    except ET.ParseError as e:
        return {"error": "pom 解析失败: %s" % e}

    def t(el, path, default=""):
        x = el.find(path)
        return (x.text or "").strip() if x is not None and x.text else default

    props = {}
    pe = root.find("properties")
    if pe is not None:
        for c in pe:
            props[c.tag] = (c.text or "").strip()
    deps = []
    for d in root.findall("dependencies/dependency"):
        deps.append({"group": t(d, "groupId"), "artifact": t(d, "artifactId"), "version": t(d, "version"), "scope": t(d, "scope")})
    managed = [t(d, "groupId") + ":" + t(d, "artifactId") for d in root.findall("dependencyManagement/dependencies/dependency")]
    parent = root.find("parent")
    return {
        "group": t(root, "groupId") or (t(parent, "groupId") if parent is not None else ""),
        "artifact": t(root, "artifactId"),
        "version": t(root, "version") or (t(parent, "version") if parent is not None else ""),
        "packaging": t(root, "packaging", "jar"),
        "parent": (t(parent, "groupId") + ":" + t(parent, "artifactId") + ":" + t(parent, "version")) if parent is not None else "",
        "modules": [m.text.strip() for m in root.findall("modules/module") if m.text],
        "properties": props,
        "dependencies": deps,
        "managed": managed,
        "plugins": [t(p, "artifactId") for p in root.findall("build/plugins/plugin")],
    }


def parse_csproj(text: str) -> dict:
    sdk_style = bool(re.search(r"<Project\s+Sdk=", text))
    tf = re.findall(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", text)
    tfv = re.findall(r"<TargetFrameworkVersion>([^<]+)</TargetFrameworkVersion>", text)
    pkgs = re.findall(r"<PackageReference\s+Include=\"([^\"]+)\"(?:\s+Version=\"([^\"]+)\")?", text)
    refs = re.findall(r"<Reference\s+Include=\"([^\",]+)", text)
    prefs = re.findall(r"<ProjectReference\s+Include=\"([^\"]+)\"", text)
    hint = re.findall(r"<HintPath>([^<]+)</HintPath>", text)
    out_type = re.findall(r"<OutputType>([^<]+)</OutputType>", text)
    guids = re.findall(r"<ProjectTypeGuids>([^<]+)</ProjectTypeGuids>", text)
    sdk = re.findall(r"<Project\s+Sdk=\"([^\"]+)\"", text)
    return {
        "sdk_style": sdk_style, "sdk": sdk[0] if sdk else "",
        "target_frameworks": [x.strip() for t in tf for x in t.split(";") if x.strip()] or tfv,
        "packages": [{"name": n, "version": v} for n, v in pkgs],
        "references": refs, "project_references": [p.replace("\\", "/") for p in prefs],
        "hint_paths": [h.replace("\\", "/") for h in hint],
        "output_type": out_type[0] if out_type else "",
        "is_web": "349c5851-65df-11da-9384-00065b846f21" in (guids[0].lower() if guids else "") or "Sdk.Web" in (sdk[0] if sdk else ""),
    }


def parse_packages_config(text: str) -> list[dict]:
    return [{"name": n, "version": v} for n, v in re.findall(r"<package\s+id=\"([^\"]+)\"\s+version=\"([^\"]+)\"", text)]


def discover(root: Path) -> dict:
    root = root.resolve()
    langs: Counter = Counter()
    loc: Counter = Counter()
    poms, gradles, slns, projs, pkgcfgs = [], [], [], [], []
    web_xml, aspx_count, jsp_count, mapper_xml = [], 0, 0, 0
    total_files = 0
    for p in iter_files(root):
        total_files += 1
        rp = rel(root, p)
        lang = LANG_BY_SUFFIX.get(p.suffix.lower())
        name = p.name
        if lang:
            langs[lang] += 1
        if p.suffix.lower() in (".go", ".java", ".cs", ".vb", ".kt", ".jsp", ".aspx", ".xml", ".sql", ".js", ".ts", ".vue", ".cshtml"):
            text = read_text(p)
            if text is not None:
                loc[lang or p.suffix] += text.count("\n") + 1
                if p.suffix.lower() == ".xml" and "<mapper" in text and "namespace=" in text:
                    mapper_xml += 1
        if name == "pom.xml":
            poms.append(rp)
        elif name in ("build.gradle", "build.gradle.kts"):
            gradles.append(rp)
        elif p.suffix.lower() == ".sln":
            slns.append(rp)
        elif p.suffix.lower() in (".csproj", ".vbproj", ".fsproj"):
            projs.append(rp)
        elif name == "packages.config":
            pkgcfgs.append(rp)
        elif name == "web.xml":
            web_xml.append(rp)
        if p.suffix.lower() == ".aspx":
            aspx_count += 1
        if p.suffix.lower() == ".jsp":
            jsp_count += 1

    java_modules = []
    dep_blob = []
    for rp in poms:
        info = parse_pom(read_text(root / rp) or "")
        info["path"] = rp
        java_modules.append(info)
        for d in info.get("dependencies", []):
            dep_blob.append("%s:%s" % (d["group"], d["artifact"]))
        dep_blob.append(info.get("parent", ""))
    for rp in gradles:
        text = read_text(root / rp) or ""
        deps = re.findall(r"(?:implementation|compile|api|runtimeOnly|compileOnly|testImplementation)\s*\(?\s*['\"]([^'\"]+)['\"]", text)
        java_modules.append({"path": rp, "gradle": True, "dependencies": [{"coord": d} for d in deps]})
        dep_blob.extend(deps)

    dotnet_projects = []
    pkg_blob = []
    for rp in projs:
        text = read_text(root / rp) or ""
        info = parse_csproj(text)
        info["path"] = rp
        pc = (root / rp).parent / "packages.config"
        if pc.exists():
            info["packages"] += parse_packages_config(read_text(pc) or "")
        dotnet_projects.append(info)
        pkg_blob.append(text)
        pkg_blob.extend(x["name"] for x in info["packages"])

    blob = "\n".join(dep_blob)
    frameworks = [n for n, rx in FRAMEWORK_MARKERS if re.search(rx, blob, re.I)]
    if jsp_count:
        frameworks.append("JSP (%d)" % jsp_count)
    if mapper_xml:
        frameworks.append("MyBatis XML 映射 (%d)" % mapper_xml)
    nblob = "\n".join(pkg_blob)
    dn_frameworks = [n for n, rx in DOTNET_MARKERS if re.search(rx, nblob)]
    if aspx_count:
        dn_frameworks.append("WebForms (%d 个 .aspx)" % aspx_count)

    java_ver = ""
    for m in java_modules:
        props = m.get("properties", {})
        java_ver = java_ver or props.get("java.version") or props.get("maven.compiler.source") or props.get("maven.compiler.release", "")
    spring_boot = ""
    for m in java_modules:
        if "spring-boot" in m.get("parent", ""):
            spring_boot = m["parent"].rsplit(":", 1)[-1]

    stacks = []
    if poms or gradles or langs.get("Java"):
        stacks.append("java")
    if projs or slns or langs.get("C#") or langs.get("VB.NET"):
        stacks.append("dotnet")
    if langs.get("Go"):
        stacks.append("go")

    return {
        "root": str(root), "stacks": stacks, "total_files": total_files,
        "languages": dict(langs.most_common()), "loc": dict(loc.most_common()),
        "java": {"build": "maven" if poms else ("gradle" if gradles else ""), "modules": java_modules,
                 "frameworks": frameworks, "java_version": java_ver, "spring_boot": spring_boot,
                 "web_xml": web_xml, "module_graph": maven_module_graph(java_modules)},
        "dotnet": {"solutions": slns, "projects": dotnet_projects, "frameworks": dn_frameworks,
                   "project_graph": dotnet_project_graph(dotnet_projects)},
    }


def maven_module_graph(mods: list[dict]) -> dict:
    internal = {m.get("artifact"): m.get("path") for m in mods if m.get("artifact")}
    graph = {}
    for m in mods:
        if not m.get("artifact"):
            continue
        graph[m["artifact"]] = sorted({d["artifact"] for d in m.get("dependencies", []) if d.get("artifact") in internal and d["artifact"] != m["artifact"]})
    return graph


def dotnet_project_graph(projs: list[dict]) -> dict:
    graph = {}
    for p in projs:
        base = p["path"].rsplit("/", 1)[0] if "/" in p["path"] else ""
        deps = []
        for r in p.get("project_references", []):
            parts = (base + "/" + r).split("/") if base else r.split("/")
            norm: list[str] = []
            for x in parts:
                if x == "..":
                    if norm:
                        norm.pop()
                elif x and x != ".":
                    norm.append(x)
            deps.append("/".join(norm))
        graph[p["path"]] = deps
    return graph
