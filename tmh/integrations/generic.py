"""Declarative adapter: connect a tool that has a JSON HTTP API without writing code.

Each capability section lists operations; each operation says where to call and
how to map the answer onto tmh's normalized fields. Example (TAPD-like tool):

    "tapd": {
      "type": "generic", "url": "https://api.tapd.cn",
      "auth": {"type": "basic", "user": "api_user", "password_env": "TAPD_PASSWORD"},
      "ping":   {"path": "/quickstart/testauth"},
      "issues": {
        "get":    {"path": "/bugs", "params": {"workspace_id": "123", "id": "{key}"}, "root": "data.0.Bug",
                   "map": {"key": "id", "title": "title", "status": "status", "description": "description",
                           "url": "https://www.tapd.cn/123/bugtrace/bugs/view?bug_id={id}"}},
        "search": {"path": "/bugs", "params": {"workspace_id": "123", "title": "{query}", "limit": "{limit}"},
                   "root": "data", "item": "Bug", "map": {"key": "id", "title": "title", "status": "status"}}
      }
    }

- `path` / `params` / `body` / map values may use {placeholders}: the call's
  inputs (key, query, limit, job, number, id, body, title, text), {base}, or any
  dotted field of the current item (e.g. {fields.status.name}).
- A map value without braces is a dotted path into the item.
- `root` is the dotted path to the record (get) or list (search) in the answer;
  `item` unwraps each list element (TAPD wraps rows as {"Bug": {...}}).
- `"text": true` returns the raw body (build logs).
"""
from __future__ import annotations

import re

from .base import Build, Change, Doc, Integration, IntegrationError, Issue, QualityIssue, norm_status

PH = re.compile(r"\{([A-Za-z0-9_.$-]+)\}")
SECTIONS = {"issues": ("get", "search", "comment"), "builds": ("list", "get", "log", "trigger"), "changes": ("list", "get"),
            "quality": ("issues",), "docs": ("search", "get"), "notify": ("send",)}


def dig(obj, path: str):
    if path in ("", "."):
        return obj
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def fill(tpl, vars_: dict, item=None):
    if isinstance(tpl, dict):
        return {k: fill(v, vars_, item) for k, v in tpl.items()}
    if isinstance(tpl, list):
        return [fill(v, vars_, item) for v in tpl]
    if not isinstance(tpl, str):
        return tpl
    m = PH.fullmatch(tpl)
    if m:  # keep the type of a lone placeholder ("{limit}" stays an int)
        v = vars_.get(m.group(1), dig(item, m.group(1)) if item is not None else None)
        return "" if v is None else v

    def sub(mm):
        k = mm.group(1)
        v = vars_.get(k, dig(item, k) if item is not None else None)
        return "" if v is None else str(v)
    return PH.sub(sub, tpl)


class Generic(Integration):
    TYPE = "generic"
    TITLE = "通用 HTTP/JSON（配置即接入，不用写代码）"
    OPTIONS = {"url": "API 根地址", "auth": "同其它适配器", "ping/issues/builds/changes/quality/docs/notify": "见 docs/integrations.md 的“通用适配器”"}

    def __init__(self, name, conf, dry_run=True):
        super().__init__(name, conf, dry_run)
        self.CAPABILITIES = tuple(s for s in SECTIONS if isinstance(conf.get(s), dict))

    def _op(self, section: str, op: str) -> dict:
        spec = (self.conf.get(section) or {}).get(op)
        if not spec:
            self.unsupported("%s.%s（配置里没有这一项）" % (section, op))
        return spec

    def call(self, section: str, op: str, **inputs):
        spec = self._op(section, op)
        v = dict(inputs, base=self.url)
        method = spec.get("method", "GET").upper()
        path = fill(spec["path"], v)
        params = fill(spec.get("params") or {}, v) or None
        body = fill(spec["body"], v) if "body" in spec else None
        r = self.http.request(method, path, params=params, json_body=body, headers=spec.get("headers"), read_only=spec.get("read_only", False))
        if r is None:
            return None
        if spec.get("text"):
            return r.text()
        data = r.json()
        return dig(data, spec.get("root", "")) if spec.get("root") else data

    def _map(self, section: str, op: str, item: dict, inputs: dict) -> dict:
        spec = self._op(section, op)
        out = {}
        v = dict(inputs, base=self.url)
        for field, src in (spec.get("map") or {}).items():
            out[field] = fill(src, v, item) if "{" in str(src) else dig(item, src)
        return out

    def _rows(self, section, op, **inputs) -> list:
        data = self.call(section, op, **inputs) or []
        if isinstance(data, dict):
            data = [data]
        item = self._op(section, op).get("item")
        return [self._map(section, op, (dig(x, item) if item else x) or {}, inputs) for x in data]

    def _one(self, section, op, **inputs) -> dict:
        data = self.call(section, op, **inputs)
        if isinstance(data, list):
            data = data[0] if data else None
        if not data:
            raise IntegrationError("%s 没有返回 %s" % (self.name, inputs))
        item = self._op(section, op).get("item")
        return self._map(section, op, (dig(data, item) if item else data) or {}, inputs)

    @staticmethod
    def _build(cls, d: dict, **fixed):
        known = cls.__dataclass_fields__
        kw = {k: ("" if v is None else v) for k, v in d.items() if k in known}
        kw.update(fixed)
        for k, f in known.items():
            if f.type in ("str", str):
                kw[k] = str(kw.get(k, "")) if not isinstance(kw.get(k, ""), (list, dict)) else kw[k]
        return cls(**kw)

    # -- capabilities --------------------------------------------------------
    def ping(self) -> str:
        if not self.conf.get("ping"):
            return "没有配置 ping，跳过连通性检查"
        spec = self.conf["ping"]
        self.http.request(spec.get("method", "GET"), fill(spec["path"], {"base": self.url}), params=spec.get("params"), read_only=True)
        return "可访问"

    def get_issue(self, key, comments=5):
        d = self._one("issues", "get", key=key)
        d.setdefault("key", key)
        return self._build(Issue, d, source=self.name)

    def search_issues(self, query, limit=20):
        return [self._build(Issue, d, source=self.name) for d in self._rows("issues", "search", query=query, limit=limit)][:limit]

    def add_comment(self, key, body):
        r = self.call("issues", "comment", key=key, body=body)
        return {"ok": True, **({"dry_run": True} if r is None else {})}

    def list_builds(self, job="", limit=10):
        rows = self._rows("builds", "list", job=job, limit=limit)
        return [self._build(Build, dict(d, status=norm_status(str(d.get("status", "")))), source=self.name, job=d.get("job") or job) for d in rows][:limit]

    def get_build(self, job="", number="last"):
        d = self._one("builds", "get", job=job, number=number)
        return self._build(Build, dict(d, status=norm_status(str(d.get("status", "")))), source=self.name, job=d.get("job") or job)

    def build_log(self, job="", number="last", tail=200):
        text = self.call("builds", "log", job=job, number=number) or ""
        text = text if isinstance(text, str) else str(text)
        return "\n".join(text.splitlines()[-tail:]) if tail else text

    def trigger_build(self, job="", params=None):
        r = self.call("builds", "trigger", job=job, **(params or {}))
        return {"ok": True, **({"dry_run": True} if r is None else {})}

    def list_changes(self, state="open", limit=20):
        return [self._build(Change, d, source=self.name) for d in self._rows("changes", "list", state=state, limit=limit)][:limit]

    def get_change(self, cid):
        return self._build(Change, self._one("changes", "get", id=cid), source=self.name)

    def quality_issues(self, path="", severity="", limit=100):
        rows = [self._build(QualityIssue, dict(d, line=int(d.get("line") or 0)), source=self.name)
                for d in self._rows("quality", "issues", path=path, severity=severity, limit=limit)]
        return [r for r in rows if not path or r.file.startswith(path)][:limit]

    def search_docs(self, query, limit=10):
        return [self._build(Doc, d, source=self.name) for d in self._rows("docs", "search", query=query, limit=limit)][:limit]

    def get_doc(self, did):
        return self._build(Doc, self._one("docs", "get", id=did), source=self.name)

    def send(self, title, text):
        r = self.call("notify", "send", title=title, text=text)
        return {"ok": True, **({"dry_run": True} if r is None else {})}
