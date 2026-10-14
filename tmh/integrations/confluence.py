"""Confluence Server / DC / Cloud: search and read pages (requirements, design notes, 运维手册)."""
from __future__ import annotations

from .base import Doc, Integration, strip_html


class Confluence(Integration):
    TYPE = "confluence"
    TITLE = "Confluence"
    CAPABILITIES = ("docs",)
    OPTIONS = {
        "url": "如 https://wiki.example.com（Cloud 写到 /wiki）",
        "space": "默认空间 key，可空",
        "auth": "Server/DC：{type: bearer, token_env: CONFLUENCE_TOKEN}；Cloud：{type: basic, user: 邮箱, password_env: CONFLUENCE_TOKEN}",
    }

    def ping(self) -> str:
        d = self.http.get("/rest/api/space", {"limit": 1})
        return "可访问，示例空间：%s" % ((d.get("results") or [{}])[0].get("name", "（无）"))

    def _doc(self, d: dict, body: bool = False) -> Doc:
        links = d.get("_links") or {}
        base = links.get("base") or self.url
        return Doc(id=str(d.get("id", "")), title=d.get("title", ""), url=base + links.get("webui", ""),
                   space=(d.get("space") or {}).get("key", ""), excerpt=strip_html(d.get("excerpt", ""))[:300],
                   body=strip_html(((d.get("body") or {}).get("storage") or {}).get("value", "")) if body else "",
                   updated=((d.get("version") or {}).get("when", "")), source=self.name)

    def search_docs(self, query: str, limit: int = 10) -> list:
        cql = 'type=page AND text ~ "%s"' % query.replace('"', '\\"')
        if self.opt("space"):
            cql = 'space="%s" AND ' % self.opt("space") + cql
        d = self.http.get("/rest/api/content/search", {"cql": cql, "limit": limit, "expand": "space,version"}) or {}
        return [self._doc(x) for x in d.get("results", [])]

    def get_doc(self, did: str) -> Doc:
        return self._doc(self.http.get("/rest/api/content/%s" % did, {"expand": "body.storage,space,version"}), body=True)
