"""GitLab (self-managed or gitlab.com, API v4): issues, merge requests, pipelines and job logs."""
from __future__ import annotations

import urllib.parse

from .base import Build, Change, Integration, IntegrationError, Issue, norm_status


class GitLab(Integration):
    TYPE = "gitlab"
    TITLE = "GitLab（含私有部署）"
    CAPABILITIES = ("issues", "changes", "builds")
    OPTIONS = {
        "url": "如 https://gitlab.example.com",
        "project": "项目路径或数字 id，如 oa/oa-web",
        "auth": "{type: header, name: PRIVATE-TOKEN, token_env: GITLAB_TOKEN}（个人/项目访问令牌，read_api 权限即可读）",
    }

    def __init__(self, name, conf, dry_run=True):
        conf = dict(conf)
        conf.setdefault("auth", {"type": "header", "name": "PRIVATE-TOKEN", "token_env": "GITLAB_TOKEN"})
        super().__init__(name, conf, dry_run)

    @property
    def p(self) -> str:
        proj = str(self.opt("project", ""))
        if not proj:
            raise IntegrationError("integrations.%s 缺少 project（项目路径，如 oa/oa-web）" % self.name)
        return "/api/v4/projects/" + urllib.parse.quote(proj, safe="")

    def ping(self) -> str:
        me = self.http.get("/api/v4/user")
        return "已登录为 %s" % (me.get("name") or me.get("username"))

    # issues -----------------------------------------------------------------
    def _issue(self, d: dict) -> Issue:
        return Issue(key="#%s" % d.get("iid"), title=d.get("title", ""), status=d.get("state", ""),
                     type="issue", assignee=(d.get("assignee") or {}).get("name", ""), reporter=(d.get("author") or {}).get("name", ""),
                     description=d.get("description") or "", url=d.get("web_url", ""), created=d.get("created_at", ""),
                     updated=d.get("updated_at", ""), resolved=d.get("closed_at") or "", labels=d.get("labels") or [], source=self.name)

    def get_issue(self, key: str, comments: int = 5) -> Issue:
        iid = key.lstrip("#")
        i = self._issue(self.http.get("%s/issues/%s" % (self.p, iid)))
        if comments:
            notes = self.http.get("%s/issues/%s/notes" % (self.p, iid), {"sort": "desc", "per_page": comments}) or []
            i.comments = [{"author": (n.get("author") or {}).get("name", ""), "created": n.get("created_at", ""), "body": n.get("body", "")}
                          for n in reversed(notes) if not n.get("system")]
        return i

    def search_issues(self, query: str, limit: int = 20) -> list:
        d = self.http.get(self.p + "/issues", {"search": query, "per_page": limit, "order_by": "updated_at"}) or []
        return [self._issue(x) for x in d]

    def add_comment(self, key: str, body: str) -> dict:
        r = self.http.post("%s/issues/%s/notes" % (self.p, key.lstrip("#")), {"body": body})
        return {"ok": True, "id": r.get("id", ""), **({"dry_run": True} if r.get("dry_run") else {})}

    # merge requests ---------------------------------------------------------
    def _mr(self, d: dict) -> Change:
        return Change(id="!%s" % d.get("iid"), title=d.get("title", ""), state=d.get("state", ""), author=(d.get("author") or {}).get("name", ""),
                      source_branch=d.get("source_branch", ""), target_branch=d.get("target_branch", ""), url=d.get("web_url", ""),
                      updated=d.get("updated_at", ""), description=d.get("description") or "", source=self.name)

    def list_changes(self, state: str = "open", limit: int = 20) -> list:
        st = {"open": "opened", "opened": "opened", "merged": "merged", "closed": "closed", "all": "all"}.get(state, state)
        return [self._mr(x) for x in self.http.get(self.p + "/merge_requests", {"state": st, "per_page": limit}) or []]

    def get_change(self, cid: str) -> Change:
        return self._mr(self.http.get("%s/merge_requests/%s" % (self.p, cid.lstrip("!"))))

    def change_files(self, cid: str) -> list:
        d = self.http.get("%s/merge_requests/%s/changes" % (self.p, cid.lstrip("!"))) or {}
        return [c.get("new_path") or c.get("old_path") for c in d.get("changes", [])]

    # pipelines --------------------------------------------------------------
    def _pipe(self, d: dict) -> Build:
        return Build(job=str(self.opt("project")), number=str(d.get("id", "")), status=norm_status(d.get("status", "")),
                     started=d.get("started_at") or d.get("created_at") or "", duration_s=float(d.get("duration") or 0),
                     url=d.get("web_url", ""), commit=d.get("sha", ""), branch=d.get("ref", ""), cause=d.get("source", ""), source=self.name)

    def list_builds(self, job: str = "", limit: int = 10) -> list:
        return [self._pipe(x) for x in self.http.get(self.p + "/pipelines", {"per_page": limit, "ref": job or None}) or []]

    def _pipeline_id(self, job: str, number: str) -> str:
        n = str(number or "last").lower()
        if n.isdigit():
            return n
        params = {"per_page": 1, "ref": job or None}
        if n in ("lastfailed", "failed"):
            params["status"] = "failed"
        d = self.http.get(self.p + "/pipelines", params) or []
        if not d:
            raise IntegrationError("没有找到符合条件的流水线")
        return str(d[0]["id"])

    def get_build(self, job: str = "", number: str = "last") -> Build:
        return self._pipe(self.http.get("%s/pipelines/%s" % (self.p, self._pipeline_id(job, number))))

    def build_log(self, job: str = "", number: str = "last", tail: int = 200) -> str:
        pid = self._pipeline_id(job, number)
        jobs = self.http.get("%s/pipelines/%s/jobs" % (self.p, pid), {"per_page": 100}) or []
        bad = [j for j in jobs if j.get("status") == "failed"] or jobs[-1:]
        out = []
        for j in bad[:3]:
            text = self.http.get_text("%s/jobs/%s/trace" % (self.p, j["id"]))
            lines = text.splitlines()
            out.append("==== job %s (%s) ====\n%s" % (j.get("name"), j.get("status"), "\n".join(lines[-tail:] if tail else lines)))
        return "\n".join(out)

    def trigger_build(self, job: str = "", params: dict | None = None) -> dict:
        body = {"ref": job or self.opt("ref", "master"), "variables": [{"key": k, "value": v} for k, v in (params or {}).items()]}
        r = self.http.post(self.p + "/pipeline", body)
        return {"ok": True, "id": r.get("id", ""), **({"dry_run": True} if r.get("dry_run") else {})}
