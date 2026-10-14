"""GitHub (github.com or Enterprise, REST v3): issues only, enough to import closed history for replay."""
from __future__ import annotations

import re

from .base import Integration, IntegrationError, Issue


# "Fixes #12", "closes: #12", or the issue's URL after the keyword: GitHub's own closing keywords
CLOSES = re.compile(r"(?i)\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\b\s*:?\s*(?:https?://\S+?/issues/|#)(\d+)")


def limited(e: Exception) -> bool:
    """GitHub answers 403 (not 429) once the hourly quota is spent: stop, don't count it as a bad issue."""
    m = str(e).lower()
    return "rate limit" in m or "http 429" in m


class GitHub(Integration):
    TYPE = "github"
    TITLE = "GitHub Issues（含 Enterprise）"
    CAPABILITIES = ("issues",)
    OPTIONS = {
        "url": "https://api.github.com；Enterprise 用 https://<主机>/api/v3",
        "repo": "仓库，如 QuantumNous/new-api",
        "auth": "公开仓库可不填（每小时 60 次）；批量导入建议 {type: bearer, token_env: GITHUB_TOKEN}",
    }

    def __init__(self, name, conf, dry_run=True):
        conf = dict(conf)
        conf.setdefault("url", "https://api.github.com")
        super().__init__(name, conf, dry_run)

    @property
    def r(self) -> str:
        repo = str(self.opt("repo", "")).strip("/")
        if repo.count("/") != 1:
            raise IntegrationError("integrations.%s 缺少 repo（写成 所有者/仓库名，如 QuantumNous/new-api）" % self.name)
        return "/repos/" + repo

    def ping(self) -> str:
        d = self.http.get(self.r)
        return "可读仓库 %s" % d.get("full_name", "")

    def _issue(self, d: dict) -> Issue:
        labels = [x.get("name", "") for x in d.get("labels") or [] if isinstance(x, dict)]
        return Issue(key="#%s" % d.get("number"), title=d.get("title", ""), status=d.get("state", ""),
                     type="缺陷" if any("bug" in x.lower() for x in labels) else "issue",
                     assignee=(d.get("assignee") or {}).get("login", ""), reporter=(d.get("user") or {}).get("login", ""),
                     description=d.get("body") or "", url=d.get("html_url", ""), created=d.get("created_at", ""),
                     updated=d.get("updated_at", ""), resolved=d.get("closed_at") or "", labels=labels, source=self.name)

    def get_issue(self, key: str, comments: int = 5) -> Issue:
        n = key.strip().lstrip("#")
        d = self.http.get("%s/issues/%s" % (self.r, n))
        if d.get("pull_request"):
            raise IntegrationError("#%s 是合并请求，不是 issue" % n)
        return self._full(d, comments)

    def _full(self, d: dict, comments: int = 5) -> Issue:
        n = d.get("number")
        i = self._issue(d)
        if comments and d.get("comments"):
            cs = self.http.get("%s/issues/%s/comments" % (self.r, n), {"per_page": 100}) or []
            i.comments = [{"author": (c.get("user") or {}).get("login", ""), "created": c.get("created_at", ""), "body": c.get("body", "")}
                          for c in cs[-comments:]]
        return i

    def issues_for_ref(self, key: str) -> list:
        """#N in a commit is often the pull request ("Merge pull request #N", "fix … (#N)"): a merged one stands
        for the issues its title or description closes. Issues and pull requests share one number space."""
        n = key.strip().lstrip("#")
        d = self.http.get("%s/issues/%s" % (self.r, n))
        if not d.get("pull_request"):
            return [(self._full(d), "")]
        if not (d.get("pull_request") or {}).get("merged_at"):
            return []
        out = []
        for m in dict.fromkeys(CLOSES.findall("%s\n%s" % (d.get("title", ""), d.get("body") or ""))):
            if m == n:
                continue
            try:
                out.append((self.get_issue(m), "#" + n))
            except IntegrationError as e:
                if limited(e):
                    raise
        return out

    def search_issues(self, query: str, limit: int = 20) -> list:
        q = query.strip()
        if q in ("", "open", "closed", "all"):
            d = self.http.get(self.r + "/issues", {"state": q or "open", "per_page": min(limit, 100), "sort": "updated"}) or []
            return [self._issue(x) for x in d if not x.get("pull_request")][:limit]
        d = self.http.get("/search/issues", {"q": "repo:%s is:issue %s" % (self.opt("repo"), q), "per_page": min(limit, 100)}) or {}
        return [self._issue(x) for x in d.get("items", [])][:limit]

    def add_comment(self, key: str, body: str) -> dict:
        r = self.http.post("%s/issues/%s/comments" % (self.r, key.lstrip("#")), {"body": body})
        return {"ok": True, "id": r.get("id", ""), **({"dry_run": True} if r.get("dry_run") else {})}
