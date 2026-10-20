"""禅道 ZenTao (开源版 18+ / 企业版 / 旗舰版, RESTful API v1).

Keys look like `bug-123`, `story-45`, `task-7`; a bare number is a bug.
Auth: POST /api.php/v1/tokens with account + password, then a `Token` header.
"""
from __future__ import annotations

import re

from .base import Integration, IntegrationError, Issue, env_value, strip_html

KINDS = {"bug": "bugs", "story": "stories", "task": "tasks"}
TYPE_CN = {"bug": "缺陷", "story": "需求", "task": "任务"}


class ZenTao(Integration):
    TYPE = "zentao"
    TITLE = "禅道"
    CAPABILITIES = ("issues",)
    OPTIONS = {
        "url": "禅道地址，如 http://zentao.example.com（部署在子目录就带上，如 /zentao）",
        "product": "默认产品 id（搜索缺陷/需求用）",
        "account": "禅道账号（不是密码，可直接写）",
        "auth": "{type: zentao, account: 账号, password_env: ZENTAO_PASSWORD}",
    }

    def __init__(self, name, conf, dry_run=True):
        super().__init__(name, conf, dry_run)
        self._token = ""

    def _auth(self) -> dict:
        if not self._token:
            a = self.conf.get("auth") or {}
            account = a.get("account") or self.opt("account") or (env_value(a["account_env"], "禅道账号") if a.get("account_env") else "")
            pw = env_value(a.get("password_env", ""), "禅道密码")
            r = self.http.request("POST", "/api.php/v1/tokens", json_body={"account": account, "password": pw}, auth=False,
                                  ok=(200, 201), read_only=True)
            self._token = (r.json() or {}).get("token", "")
            if not self._token:
                raise IntegrationError("禅道登录没有返回 token，检查账号密码、禅道版本（需要 RESTful API v1）")
        return {"Token": self._token}

    def _get(self, path, params=None):
        return self.http.get(path, params, headers=self._auth(), auth=False)

    def ping(self) -> str:
        me = self._get("/api.php/v1/user")
        prof = me.get("profile", me)
        return "已登录为 %s" % (prof.get("realname") or prof.get("account") or "?")

    @staticmethod
    def split(key: str) -> tuple[str, str]:
        m = re.match(r"(?i)(bug|story|task)[-#_ ]?(\d+)$", key.strip())
        if m:
            return m.group(1).lower(), m.group(2)
        if key.strip().lstrip("#").isdigit():
            return "bug", key.strip().lstrip("#")
        raise IntegrationError("禅道编号写成 bug-123 / story-45 / task-7")

    def _issue(self, kind: str, d: dict) -> Issue:
        name = lambda x: (x.get("realname") or x.get("account") or "") if isinstance(x, dict) else (x or "")
        desc = d.get("steps") if kind == "bug" else (d.get("spec") or d.get("desc") or "")
        return Issue(key="%s-%s" % (kind, d.get("id")), title=d.get("title") or d.get("name") or "", status=d.get("status", ""),
                     type=TYPE_CN[kind], priority=str(d.get("pri", "")), assignee=name(d.get("assignedTo")), reporter=name(d.get("openedBy")),
                     description=strip_html(desc or ""), url="%s/index.php?m=%s&f=view&id=%s" % (self.url, kind, d.get("id")),
                     created=d.get("openedDate", ""), updated=d.get("lastEditedDate") or "",
                     resolved=_date(d.get("closedDate")) or _date(d.get("resolvedDate")) or _date(d.get("finishedDate")), source=self.name)

    def get_issue(self, key: str, comments: int = 5) -> Issue:
        kind, iid = self.split(key)
        d = self._get("/api.php/v1/%s/%s" % (KINDS[kind], iid))
        i = self._issue(kind, d)
        acts = [a for a in (d.get("actions") or []) if a.get("comment")][-comments:] if comments else []
        i.comments = [{"author": a.get("actor", ""), "created": a.get("date", ""), "body": strip_html(a.get("comment", ""))} for a in acts]
        return i

    def search_issues(self, query: str, limit: int = 20) -> list:
        product = self.opt("product")
        if not product:
            raise IntegrationError("禅道搜索需要在配置里写 product（产品 id）")
        out = []
        for kind in ("bug", "story"):
            d = self._get("/api.php/v1/products/%s/%s" % (product, KINDS[kind]), {"limit": 100}) or {}
            for x in d.get(KINDS[kind], []):
                if not query or query.lower() in (x.get("title") or "").lower():
                    out.append(self._issue(kind, x))
        return out[:limit]

    def add_comment(self, key: str, body: str) -> dict:
        kind, iid = self.split(key)
        headers = self._auth()
        # 禅道 v1 没有独立的评论接口：缺陷用“编辑”接口追加备注 comment 字段
        r = self.http.request("PUT", "/api.php/v1/%s/%s" % (KINDS[kind], iid), json_body={"comment": body}, headers=headers, auth=False)
        return {"ok": True, **({"dry_run": True} if r is None else {})}


def _date(v) -> str:
    """禅道 writes 0000-00-00 for 'never'."""
    v = (v or "").strip() if isinstance(v, str) else ""
    return "" if not v or v.startswith("0000") else v
