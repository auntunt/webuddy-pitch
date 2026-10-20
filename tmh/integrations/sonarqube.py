"""SonarQube / SonarCloud: open issues on the project and the quality gate."""
from __future__ import annotations

from .base import Integration, IntegrationError, QualityIssue

SEVERITIES = ["BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"]


class SonarQube(Integration):
    TYPE = "sonarqube"
    TITLE = "SonarQube"
    CAPABILITIES = ("quality",)
    OPTIONS = {
        "url": "如 https://sonar.example.com",
        "project": "项目 key（sonar.projectKey）",
        "branch": "分支，可空",
        "auth": "{type: bearer, token_env: SONAR_TOKEN}；老版本用 {type: basic, user_env: SONAR_TOKEN}（token 当用户名、密码留空）",
    }

    @property
    def project(self) -> str:
        p = self.opt("project", "")
        if not p:
            raise IntegrationError("integrations.%s 缺少 project（sonar.projectKey）" % self.name)
        return p

    def ping(self) -> str:
        v = self.http.get("/api/authentication/validate")
        if not (v or {}).get("valid"):
            raise IntegrationError("SonarQube 认证无效，检查 token 环境变量")
        return "认证有效"

    def quality_issues(self, path: str = "", severity: str = "", limit: int = 100) -> list:
        params = {"componentKeys": self.project, "resolved": "false", "ps": min(500, limit), "s": "SEVERITY", "asc": "false",
                  "branch": self.opt("branch")}
        if severity:
            sev = severity.upper()
            params["severities"] = ",".join(SEVERITIES[:SEVERITIES.index(sev) + 1]) if sev in SEVERITIES else sev
        out = []
        page = 1
        while len(out) < limit:
            params["p"] = page
            d = self.http.get("/api/issues/search", params) or {}
            items = d.get("issues", [])
            for i in items:
                comp = i.get("component", "")
                f = comp.split(":", 1)[1] if ":" in comp else ""
                if path and not f.startswith(path.strip("/")):
                    continue
                out.append(QualityIssue(rule=i.get("rule", ""), severity=i.get("severity", ""), type=i.get("type", ""), file=f,
                                        line=int(i.get("line") or 0), message=i.get("message", ""),
                                        url="%s/project/issues?id=%s&open=%s" % (self.url, self.project, i.get("key", "")), source=self.name))
            total = (d.get("paging") or {}).get("total", d.get("total", 0))
            if not items or page * params["ps"] >= total:
                break
            page += 1
        return out[:limit]

    def quality_gate(self) -> dict:
        d = self.http.get("/api/qualitygates/project_status", {"projectKey": self.project, "branch": self.opt("branch")}) or {}
        ps = d.get("projectStatus", {})
        return {"status": ps.get("status", "NONE"),
                "failed": [{"metric": c.get("metricKey"), "actual": c.get("actualValue"), "threshold": c.get("errorThreshold")}
                           for c in ps.get("conditions", []) if c.get("status") == "ERROR"]}
