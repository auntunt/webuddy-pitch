"""示例插件：把一个内部工单系统接进 tmh。

复制成 .tmh/integrations/myissues.py（文件名不能以 _ 开头），改好后：
    tmh int add mine --type myissues --url https://issues.example.com --auth bearer --token-env MYISSUES_TOKEN
    tmh int test mine
    tmh issue get REQ-1 --via mine

只需实现你的工具支持的方法；没实现的会提示“不支持”。
可用的统一模型：Issue、Build、Change、QualityIssue、Doc（见 tmh/integrations/base.py）。
self.http 已经处理好认证、超时、重试、代理、内网证书和写操作演练。
"""
from tmh.integrations import Integration, Issue


class MyIssues(Integration):
    TYPE = "myissues"
    TITLE = "内部工单系统（示例）"
    CAPABILITIES = ("issues",)
    OPTIONS = {"url": "系统地址", "auth": "{type: bearer, token_env: MYISSUES_TOKEN}"}

    def ping(self):
        me = self.http.get("/api/me")
        return "已登录为 %s" % me.get("name", "?")

    def get_issue(self, key, comments=5):
        d = self.http.get("/api/requirements/%s" % key)
        return Issue(key=key, title=d.get("title", ""), status=d.get("state", ""), type=d.get("category", "需求"),
                     description=d.get("content", ""), url="%s/req/%s" % (self.url, key), source=self.name)

    def search_issues(self, query, limit=20):
        rows = self.http.get("/api/requirements", {"q": query, "size": limit}).get("items", [])
        return [Issue(key=r["no"], title=r.get("title", ""), status=r.get("state", ""), source=self.name) for r in rows]

    def add_comment(self, key, body):
        r = self.http.post("/api/requirements/%s/comments" % key, {"content": body})  # 演练时不会真的发出
        return {"ok": True, **({"dry_run": True} if r.get("dry_run") else {})}
