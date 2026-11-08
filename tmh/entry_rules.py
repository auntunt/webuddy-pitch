"""Entry coverage audit and model-detected entry rules.

The audit is deterministic: classes that look like framework entry points but
produced no flow. The rules step asks the configured router model for a
declarative pattern set; the reply is validated against a fixed schema and
stored in .tmh/entry-rules.json with provenance. Model output is data, never
executed code; applied entries stay labelled 模型识别入口（待核实）."""
import hashlib
import json
import re
from pathlib import Path

RULE_FILE = "entry-rules.json"
ENTRY_SUFFIXES = ("Action", "Controller", "Servlet", "Job", "Listener", "Endpoint")
ENTRY_BASES = frozenset({"ActionSupport", "HttpServlet", "Controller", "AbstractController", "ControllerBase",
                         "Job", "StatefulJob", "InterruptableJob", "QuartzJobBean", "MessageListener",
                         "Servlet", "GenericServlet"})
DEFAULT_METHODS = re.compile(r"^(execute|service|doGet|doPost|handleRequest|processRequest|onMessage|run|doWork|perform)\w*$")
MAX_RULES = 30
MAX_PATTERN = 200
MAX_CANDIDATES = 60
SCOPE = "model-detected-entry-candidate"
KIND = "模型识别入口（待核实）"

_OVER_BROAD = re.compile(r"^\.\*$|^\.\+$|^\(\?:\.\*\)\*$|^\w*\.\*$")


def uncovered_candidates(classes: dict, covered: set) -> list:
    """Likely entry classes not covered by any flow. `classes` is codeindex's name→[cls] map."""
    out = []
    for name, cs in classes.items():
        for c in cs:
            if c.get("kind") != "class" or name in covered or c["name"] in covered:
                continue
            why = ""
            if name.endswith(ENTRY_SUFFIXES):
                why = "命名形态像入口类"
            elif ENTRY_BASES & set(c.get("bases") or []):
                why = "继承了框架入口基类"
            if not why:
                continue
            out.append({"class": c["fqn"] or name, "name": name, "file": c["file"], "bases": list(c.get("bases") or []),
                        "methods": sorted(c.get("methods") or {}), "why": why,
                        "module": (c["file"].split("/", 1)[0] if "/" in c["file"] else "")})
    out.sort(key=lambda x: (x["module"], x["class"]))
    return out


def coverage(classes: dict, flows: list, map_named: set) -> dict:
    """`map_named`: classes referenced by framework config (web.xml/struts/spring); they count as entry candidates even without a name suffix."""
    covered = {f["handler"].rsplit(".", 1)[0] for f in flows}
    uncovered = uncovered_candidates(classes, covered | set())
    extra = []
    for name in sorted(map_named - covered):
        for c in classes.get(name, []):
            if name not in {u["name"] for u in uncovered}:
                extra.append({"class": c["fqn"] or name, "name": name, "file": c["file"], "bases": list(c.get("bases") or []),
                              "methods": sorted(c.get("methods") or {}), "why": "框架配置中登记过", "module": c["file"].split("/", 1)[0] if "/" in c["file"] else ""})
    uncovered += extra
    per_module = {}
    for u in uncovered:
        per_module[u["module"]] = per_module.get(u["module"], 0) + 1
    return {"total": len(uncovered), "per_module": per_module, "uncovered": uncovered}


def _valid_regex(pattern):
    if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_PATTERN:
        raise ValueError("规则中的正则太长或不是字符串")
    if _OVER_BROAD.match(pattern.strip()):
        raise ValueError("规则中的类匹配过于宽泛：%s" % pattern)
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError("规则中的正则不合法：%s" % exc)


def validate_document(doc) -> list:
    """Fixed declarative schema; anything else is rejected."""
    if not isinstance(doc, dict) or not isinstance(doc.get("framework"), str) or not isinstance(doc.get("rules"), list):
        raise ValueError("模型回复不是 {framework, rules[]} 结构")
    if len(doc["rules"]) > MAX_RULES:
        raise ValueError("规则超过 %d 条上限" % MAX_RULES)
    rules = []
    for r in doc["rules"]:
        if not isinstance(r, dict) or set(r) - {"class_pattern", "extends", "method_visibility", "method_pattern", "url_template", "reason"}:
            raise ValueError("规则含不支持的字段")
        out = {"class_pattern": _valid_regex(r.get("class_pattern")).pattern}
        if r.get("extends"):
            if not isinstance(r["extends"], str) or len(r["extends"]) > 200:
                raise ValueError("extends 字段不合法")
            out["extends"] = r["extends"].split(".")[-1]
        if r.get("method_visibility") not in (None, "public"):
            raise ValueError("method_visibility 只支持 public")
        if r.get("method_pattern"):
            out["method_pattern"] = _valid_regex(r["method_pattern"]).pattern
        if r.get("url_template"):
            if not isinstance(r["url_template"], str) or len(r["url_template"]) > 200:
                raise ValueError("url_template 字段不合法")
            out["url_template"] = r["url_template"]
        if not isinstance(r.get("reason"), str) or not r["reason"].strip():
            raise ValueError("规则缺少判定理由")
        out["reason"] = r["reason"][:300]
        rules.append(out)
    return rules


def load_rules(root: Path):
    path = Path(root) / ".tmh" / RULE_FILE
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        return None
    return doc


def apply_rules(root: Path, fb) -> list:
    """Stored rules → entry dicts matching build_flows' entry shape."""
    doc = load_rules(root)
    if not doc:
        return []
    try:
        rules = validate_document(doc)
    except ValueError:
        return []
    framework = doc.get("framework", "")
    entries = []
    for name, cs in fb.classes.items():
        for c in cs:
            if c.get("kind") != "class":
                continue
            fqn = c["fqn"] or name
            for rule in rules:
                if not re.search(rule["class_pattern"], fqn):
                    continue
                if rule.get("extends") and rule["extends"] not in (c.get("bases") or []):
                    continue
                pat = re.compile(rule["method_pattern"]) if rule.get("method_pattern") else DEFAULT_METHODS
                for m in sorted(c.get("methods") or {}):
                    if rule.get("method_visibility") == "public" and m.startswith("_"):
                        continue
                    if not pat.match(m):
                        continue
                    entries.append({"kind": "接口", "trigger": "模型识别 %s" % (rule.get("url_template") or m),
                                    "class": name, "method": m, "file": c["file"], "line": 0,
                                    "scope": SCOPE, "url": rule.get("url_template", ""),
                                    "limitations": ["模型识别入口（待核实）：%s" % rule["reason"]],
                                    "registration": ".tmh/%s（%s）" % (RULE_FILE, framework)})
                    break
                break
    return entries


def summarize(root: Path, m: dict, uncovered: list) -> str:
    """Bounded input for the model: build files, framework config excerpts, top candidates."""
    parts = []
    for e in m.get("endpoints", [])[:1]:
        pass  # endpoints are covered already; only evidence sources follow
    for name in ("pom.xml", "build.xml", "build.gradle", "web.xml", "struts.xml", "struts-config.xml", "applicationContext.xml"):
        p = next(Path(root).rglob(name), None)
        if p:
            parts.append("== %s ==\n%s" % (p.relative_to(root), p.read_text(encoding="utf-8", errors="replace")[:4000]))
    for u in uncovered[:MAX_CANDIDATES]:
        sig = "、".join(u["methods"][:12])
        parts.append("候选类 %s（继承：%s；方法：%s；文件：%s；理由：%s）" % (u["class"], ",".join(u["bases"]) or "-", sig or "-", u["file"], u["why"]))
    return "\n\n".join(parts)[:24000]


SYSTEM = ("你在为一个传统业务系统补充入口识别规则。只输出 JSON："
          '{"framework": "框架名", "rules": [{"class_pattern": "匹配类全名的正则", '
          '"extends": "可选基类名", "method_visibility": "public", '
          '"method_pattern": "可选方法名正则", "url_template": "可选URL形态", "reason": "判定理由"}]}。'
          "只给能由类名/基类/方法签名判定的规则，不要宽泛匹配，不要输出解释文字。")


def detect(root: Path, conf: dict, chat=None) -> dict:
    """conf: kbqa.router_conf-style {'ready','model',...}. Returns stored doc + counts."""
    if not conf.get("ready"):
        raise ValueError("没有可用的直连模型配置（router base_url/model/key）；先在 .tmh 配置或 TMH_ROUTER_* 环境变量里配好")
    from tmh import mapper, codeindex, flow as flowmod
    m = mapper.build_map(root)
    idx = codeindex.build_index(root)
    fb = flowmod.FlowBuilder(root, m, idx)
    fdata = flowmod.build_flows(root, builder=fb)
    before = fdata["entry_coverage"]["total"]
    text = summarize(root, m, fdata["entry_coverage"]["uncovered"])
    sha = hashlib.sha256(text.encode()).hexdigest()[:16]
    reply = (chat or _default_chat)(conf, SYSTEM, text)
    doc = json.loads(reply.strip().removeprefix("```json").removesuffix("```").strip())
    rules = validate_document(doc)
    stored = {"framework": doc["framework"][:80], "rules": rules, "model": conf.get("model", ""),
              "detected_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
              "input_sha256": sha}
    path = Path(root) / ".tmh" / RULE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stored, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fdata2 = flowmod.build_flows(root, m, idx)
    return {"stored": str(path), "framework": stored["framework"], "rules": len(rules),
            "coverage_before": before, "coverage_after": fdata2["entry_coverage"]["total"],
            "model": stored["model"]}


def _default_chat(conf, system, text):
    from tmh import kbqa
    data = kbqa._post(conf, {"model": conf["model"], "temperature": 0, "max_tokens": 4000,
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}]}, timeout=120)
    msg = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
    if not isinstance(msg, str) or not msg.strip():
        raise ValueError("模型没有返回内容")
    return msg
