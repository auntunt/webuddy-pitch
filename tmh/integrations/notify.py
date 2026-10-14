"""Group-chat robots: 钉钉 DingTalk, 飞书 Feishu/Lark, 企业微信 WeCom, or any JSON webhook.

The webhook URL contains its access token, so it lives in an environment
variable (`webhook_env`), and so does the optional signing secret (`secret_env`).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse

from .base import Integration, IntegrationError, env_value


class _Webhook(Integration):
    CAPABILITIES = ("notify",)
    OPTIONS = {"webhook_env": "存放机器人 webhook 地址的环境变量名", "secret_env": "加签密钥的环境变量名（开启了加签才需要）",
               "at": "要 @ 的手机号列表（钉钉）/ open_id（飞书），可空"}

    def hook(self) -> str:
        return env_value(self.conf.get("webhook_env", ""), "机器人 webhook 地址")

    def secret(self) -> str:
        return env_value(self.conf["secret_env"], "机器人加签密钥") if self.conf.get("secret_env") else ""

    def ping(self) -> str:
        self.hook()
        return "webhook 环境变量已设置（发送前不会真的请求）"

    def payload(self, title: str, text: str) -> dict:
        raise NotImplementedError

    def target(self) -> str:
        return self.hook()

    def send(self, title: str, text: str) -> dict:
        body = self.payload(title, text)
        r = self.http.request("POST", self.target(), json_body=body, auth=False)
        if r is None:
            return {"ok": True, "dry_run": True, "payload": body}
        d = r.json() or {}
        code = d.get("errcode", d.get("code", d.get("StatusCode", 0)))
        if code not in (0, None):
            raise IntegrationError("机器人返回错误：%s" % (d.get("errmsg") or d.get("msg") or d))
        return {"ok": True}


class DingTalk(_Webhook):
    TYPE = "dingtalk"
    TITLE = "钉钉群机器人"

    def target(self) -> str:
        url, sec = self.hook(), self.secret()
        if not sec:
            return url
        ts = str(int(time.time() * 1000))
        sign = base64.b64encode(hmac.new(sec.encode(), ("%s\n%s" % (ts, sec)).encode(), hashlib.sha256).digest()).decode()
        return url + ("&" if "?" in url else "?") + "timestamp=%s&sign=%s" % (ts, urllib.parse.quote_plus(sign))

    def payload(self, title, text):
        at = self.conf.get("at") or []
        md = "### %s\n\n%s" % (title, text) + ("\n\n" + " ".join("@" + m for m in at) if at else "")
        return {"msgtype": "markdown", "markdown": {"title": title, "text": md}, "at": {"atMobiles": at}}


class Feishu(_Webhook):
    TYPE = "feishu"
    TITLE = "飞书群机器人"

    def payload(self, title, text):
        body = {"msg_type": "post", "content": {"post": {"zh_cn": {"title": title, "content": [[{"tag": "text", "text": line}] for line in text.splitlines() or [""]]}}}}
        sec = self.secret()
        if sec:
            ts = str(int(time.time()))
            body["timestamp"] = ts
            body["sign"] = base64.b64encode(hmac.new(("%s\n%s" % (ts, sec)).encode(), b"", hashlib.sha256).digest()).decode()
        return body


class WeCom(_Webhook):
    TYPE = "wecom"
    TITLE = "企业微信群机器人"

    def payload(self, title, text):
        return {"msgtype": "markdown", "markdown": {"content": "**%s**\n%s" % (title, text)}}


class Webhook(_Webhook):
    TYPE = "webhook"
    TITLE = "通用 JSON webhook（如内部告警平台）"
    OPTIONS = dict(_Webhook.OPTIONS, template='消息体模板，{title}/{text} 会被替换，默认 {"title": "{title}", "text": "{text}"}')

    def payload(self, title, text):
        tpl = self.conf.get("template") or {"title": "{title}", "text": "{text}"}

        def fill(v):
            if isinstance(v, str):
                return v.replace("{title}", title).replace("{text}", text)
            if isinstance(v, dict):
                return {k: fill(x) for k, x in v.items()}
            if isinstance(v, list):
                return [fill(x) for x in v]
            return v
        return fill(tpl)
