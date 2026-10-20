"""Jira Server / Data Center / Cloud (REST API v2, which both still serve)."""
from __future__ import annotations

from .base import Integration, IntegrationError, Issue


class Jira(Integration):
    TYPE = "jira"
    TITLE = "Jira（Server/DC/Cloud）"
    CAPABILITIES = ("issues",)
    OPTIONS = {
        "url": "如 https://jira.example.com",
        "project": "默认项目 key（搜索时限定），可空",
        "auth": "Server/DC 推荐 {type: bearer, token_env: JIRA_TOKEN}（个人访问令牌）；Cloud 用 {type: basic, user: 邮箱, password_env: JIRA_TOKEN}",
        "jql": "搜索时追加的 JQL 条件，可空",
    }
    FIELDS = "summary,status,issuetype,priority,assignee,reporter,description,created,updated,resolutiondate,labels,issuelinks,comment"

    def ping(self) -> str:
        me = self.http.get("/rest/api/2/myself")
        return "已登录为 %s" % (me.get("displayName") or me.get("name") or me.get("emailAddress") or "?")

    def _issue(self, d: dict, comments: int = 5) -> Issue:
        f = d.get("fields") or {}
        name = lambda x: (x or {}).get("displayName") or (x or {}).get("name") or ""
        links = []
        for l in f.get("issuelinks") or []:
            other = l.get("outwardIssue") or l.get("inwardIssue") or {}
            rel = (l.get("type") or {}).get("outward" if "outwardIssue" in l else "inward", "")
            links.append({"key": other.get("key", ""), "relation": rel, "title": (other.get("fields") or {}).get("summary", "")})
        cs = ((f.get("comment") or {}).get("comments") or [])[-comments:] if comments else []
        desc = f.get("description") or ""
        if isinstance(desc, dict):  # API v3 ADF slipped through
            desc = _adf_text(desc)
        return Issue(
            key=d.get("key", ""), title=f.get("summary", ""), status=(f.get("status") or {}).get("name", ""),
            type=(f.get("issuetype") or {}).get("name", ""), priority=(f.get("priority") or {}).get("name", ""),
            assignee=name(f.get("assignee")), reporter=name(f.get("reporter")), description=desc,
            url="%s/browse/%s" % (self.url, d.get("key", "")), created=f.get("created", ""), updated=f.get("updated", ""),
            resolved=f.get("resolutiondate") or "", labels=f.get("labels") or [], links=links,
            comments=[{"author": name(c.get("author")), "created": c.get("created", ""), "body": c.get("body", "") if isinstance(c.get("body"), str) else _adf_text(c.get("body"))} for c in cs],
            source=self.name)

    def get_issue(self, key: str, comments: int = 5) -> Issue:
        return self._issue(self.http.get("/rest/api/2/issue/%s" % key, {"fields": self.FIELDS}), comments)

    def search_issues(self, query: str, limit: int = 20) -> list:
        q = query.strip()
        if any(op in q for op in ("=", "~", " in ", " order by ", " ORDER BY ")):
            jql = q  # already JQL
        else:
            parts = []
            if self.opt("project"):
                parts.append('project = "%s"' % self.opt("project"))
            if q:
                parts.append('text ~ "%s"' % q.replace('"', '\\"'))
            if self.opt("jql"):
                parts.append("(%s)" % self.opt("jql"))
            jql = " AND ".join(parts) + " ORDER BY updated DESC"
        d = self.http.get("/rest/api/2/search", {"jql": jql, "maxResults": limit, "fields": self.FIELDS})
        return [self._issue(i, 0) for i in (d or {}).get("issues", [])]

    def add_comment(self, key: str, body: str) -> dict:
        r = self.http.post("/rest/api/2/issue/%s/comment" % key, {"body": body})
        return {"ok": True, "id": (r or {}).get("id", ""), **({"dry_run": True} if r.get("dry_run") else {})}

    def transition(self, key: str, to: str) -> dict:
        ts = self.http.get("/rest/api/2/issue/%s/transitions" % key).get("transitions", [])
        hit = [t for t in ts if to.lower() in (t.get("name", "").lower(), (t.get("to") or {}).get("name", "").lower(), str(t.get("id")))]
        if not hit:
            raise IntegrationError("%s 当前不能流转到“%s”。可选：%s" % (key, to, "、".join("%s→%s" % (t.get("name"), (t.get("to") or {}).get("name", "")) for t in ts)))
        r = self.http.post("/rest/api/2/issue/%s/transitions" % key, {"transition": {"id": hit[0]["id"]}})
        return {"ok": True, "transition": hit[0].get("name"), **({"dry_run": True} if r.get("dry_run") else {})}


def _adf_text(node) -> str:
    if not isinstance(node, dict):
        return str(node or "")
    if node.get("type") == "text":
        return node.get("text", "")
    sep = "\n" if node.get("type") in ("paragraph", "heading", "listItem", "codeBlock") else ""
    return "".join(_adf_text(c) for c in node.get("content") or []) + sep
