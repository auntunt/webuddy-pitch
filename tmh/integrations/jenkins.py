"""Jenkins: jobs (incl. folders / multibranch), builds, console log, trigger with CSRF crumb."""
from __future__ import annotations

import time
import urllib.parse

from .base import Build, Integration, IntegrationError, norm_status

ALIASES = {"last": "lastBuild", "lastfailed": "lastFailedBuild", "failed": "lastFailedBuild", "lastsuccessful": "lastSuccessfulBuild",
           "success": "lastSuccessfulBuild", "lastcompleted": "lastCompletedBuild"}


def job_path(job: str) -> str:
    """'folder/app/main' -> '/job/folder/job/app/job/main'. Already-prefixed paths pass through."""
    job = job.strip("/")
    if job.startswith("job/"):
        return "/" + job
    return "".join("/job/" + urllib.parse.quote(p, safe="") for p in job.split("/") if p)


class Jenkins(Integration):
    TYPE = "jenkins"
    TITLE = "Jenkins"
    CAPABILITIES = ("builds",)
    OPTIONS = {
        "url": "如 https://jenkins.example.com",
        "job": "默认 job（多级目录用 / 分隔，如 oa/oa-web/master）",
        "auth": "{type: basic, user: 你的账号, password_env: JENKINS_TOKEN}（用 API Token，不用登录密码）",
    }

    def _job(self, job: str) -> str:
        job = job or self.opt("job", "")
        if not job:
            raise IntegrationError("没有指定 job，也没有在配置里写默认 job")
        return job

    def ping(self) -> str:
        me = self.http.get("/me/api/json")
        return "已登录为 %s" % (me.get("fullName") or me.get("id") or "?")

    def _build(self, job: str, d: dict) -> Build:
        commit, branch, cause = "", "", ""
        for a in d.get("actions") or []:
            if not isinstance(a, dict):
                continue
            rev = a.get("lastBuiltRevision")
            if rev and not commit:
                commit = rev.get("SHA1", "")
                br = rev.get("branch") or []
                branch = br[0].get("name", "") if br else ""
            for c in a.get("causes") or []:
                cause = cause or c.get("shortDescription", "")
        status = "running" if d.get("building") else norm_status(d.get("result") or "")
        ts = d.get("timestamp") or 0
        return Build(job=job, number=str(d.get("number", "")), status=status,
                     started=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts / 1000)) if ts else "",
                     duration_s=round((d.get("duration") or 0) / 1000, 1), url=d.get("url", ""), commit=commit, branch=branch,
                     cause=cause, source=self.name)

    def _ref(self, number) -> str:
        n = str(number or "last")
        return ALIASES.get(n.lower().replace("_", "").replace("-", ""), n)

    def list_builds(self, job: str = "", limit: int = 10) -> list:
        job = self._job(job)
        tree = "builds[number,result,building,timestamp,duration,url,actions[causes[shortDescription],lastBuiltRevision[SHA1,branch[name]]]]{0,%d}" % limit
        d = self.http.get(job_path(job) + "/api/json", {"tree": tree})
        return [self._build(job, b) for b in (d or {}).get("builds", [])]

    def get_build(self, job: str = "", number: str = "last") -> Build:
        job = self._job(job)
        return self._build(job, self.http.get("%s/%s/api/json" % (job_path(job), self._ref(number))))

    def build_log(self, job: str = "", number: str = "last", tail: int = 200) -> str:
        job = self._job(job)
        text = self.http.get_text("%s/%s/consoleText" % (job_path(job), self._ref(number)))
        lines = text.splitlines()
        return "\n".join(lines[-tail:]) if tail else text

    def trigger_build(self, job: str = "", params: dict | None = None) -> dict:
        job = self._job(job)
        headers = {}
        try:
            c = self.http.get("/crumbIssuer/api/json")
            if c and c.get("crumbRequestField"):
                headers[c["crumbRequestField"]] = c["crumb"]
        except IntegrationError:
            pass  # CSRF protection off, or API token auth that does not need a crumb
        path = job_path(job) + ("/buildWithParameters" if params else "/build")
        r = self.http.request("POST", path, params=params or None, headers=headers)
        if r is None:
            return {"ok": True, "dry_run": True, "job": job}
        return {"ok": True, "job": job, "queue": r.headers.get("Location", "")}
