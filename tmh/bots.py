"""Ask the knowledge base from a group chat: 钉钉, 飞书, 企业微信, or a plain HTTP API.

Someone in the business group writes “资金计划能不能按部门导出？”, the robot runs
the same pre-check as `tmh kb triage` and answers in the chat: the verdict, how
sure, which knowledge pages it rests on. Anything that needs a person is written
to open-questions.md (“已转人工 #n”); the named answerers can reply in the chat
with “答复 #n …”, which is recorded word for word like `tmh kb answer`.

Configuration lives in .tmh/config.json under "bots". Secrets are environment
variable names only, never values:

    "bots": {
      "dingtalk": {"secret_env": "TMH_DINGTALK_SECRET"},
      "feishu":   {"app_id_env": "TMH_FEISHU_APP_ID", "app_secret_env": "TMH_FEISHU_APP_SECRET",
                   "verification_token_env": "TMH_FEISHU_TOKEN", "encrypt_key_env": "TMH_FEISHU_ENCRYPT_KEY",
                   "base_url": "https://open.feishu.cn"},
      "wecom":    {"corp_id_env": "TMH_WECOM_CORP_ID", "token_env": "TMH_WECOM_TOKEN",
                   "aes_key_env": "TMH_WECOM_AES_KEY", "secret_env": "TMH_WECOM_SECRET", "agent_id": "1000002",
                   "base_url": "https://qyapi.weixin.qq.com"},
      "api":      {"key_env": "TMH_BOT_API_KEY"},
      "answerers": ["张三", "zhangsan"],
      "record": true
    }

Callback addresses on the platform (`tmh serve`): /bot/dingtalk/<项目代号>,
/bot/feishu/<项目代号>, /bot/wecom/<项目代号>, /bot/api/<项目代号>. They do not
use the platform's access token; each request must carry a valid signature of
its own platform instead (or the API key for /bot/api).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import struct
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

from . import aes, kbqa
from .config import load as load_cfg

KINDS = ("dingtalk", "feishu", "wecom", "api")
CHANNEL = {"dingtalk": "钉钉", "feishu": "飞书", "wecom": "企业微信", "api": "开放接口"}
ASYNC = True  # tests set False to run the reply inline


class BotError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def conf(root: Path) -> dict:
    return load_cfg(root).get("bots") or {}


def _env(c: dict, key: str, what: str, required: bool = True) -> str:
    name = c.get(key) or ""
    v = os.environ.get(name, "") if name else ""
    if required and not v:
        raise BotError(503, "机器人未配置：%s（环境变量 %s）" % (what, name or "未指定"))
    return v


def status(root: Path) -> dict:
    """Which robots are configured and whether their environment variables are set (never the values)."""
    c = conf(root)
    need = {"dingtalk": ["secret_env"], "feishu": ["app_id_env", "app_secret_env"],
            "wecom": ["corp_id_env", "token_env", "aes_key_env", "secret_env"], "api": ["key_env"]}
    out = {}
    for k in KINDS:
        if k in c:
            b = c[k] or {}
            miss = [b.get(e) or e for e in need[k] if not (b.get(e) and os.environ.get(b[e]))]
            out[k] = {"configured": True, "ready": not miss, "missing_env": miss}
    return {"bots": out, "answerers": c.get("answerers") or [], "record": c.get("record", True)}


# ---- the conversation ---------------------------------------------------------------------
HELP = ("直接发需求或问题原文，我按项目知识库预判能不能做、依据哪些页面；需要人判断的会转给业务方并记下问题编号。\n"
        "答复人可以发“答复 #编号 答复原文”记录答复，发“改判 预判编号 理由”标记预判不对。")
_MENTION = re.compile(r"@_user_\d+|^\s*@\S+\s+")


def clean(text: str) -> str:
    t = _MENTION.sub(" ", text or "")
    return " ".join(t.split())


def handle(root: Path, text: str, channel: str, sender: str, use_model: bool = True) -> dict:
    """One chat message in, one reply out. Returns {"reply": markdown, "kind": ..., ...}."""
    c = conf(root)
    t = clean(text)
    who = (sender or "").strip()
    can_answer = bool(who) and who in [str(x) for x in c.get("answerers") or []]
    if not t or t in ("帮助", "help", "?", "？"):
        return {"kind": "help", "reply": HELP}
    m = re.match(r"^答复\s*#?(\d+)\s*[:：]?\s*(.+)$", t, re.S)
    if m:
        if not can_answer:
            return {"kind": "denied", "reply": "只有配置里的答复人可以在群里记录答复，请联系运维同事。"}
        try:
            r = kbqa.answer(root, int(m.group(1)), m.group(2).strip(), who)
        except (KeyError, ValueError) as e:
            return {"kind": "error", "reply": e.args[0]}
        return {"kind": "answer", "reply": "已记录问题 #%d 的答复%s。" % (r["n"], "，写入知识页 " + "、".join(r["pages"]) + " 等待修订" if r["pages"] else "")}
    m = re.match(r"^改判\s+([0-9a-f]{8})\s*[:：]?\s*(.*)$", t, re.S)
    if m:
        if not can_answer:
            return {"kind": "denied", "reply": "只有配置里的答复人可以改判。"}
        try:
            kbqa.overrule(root, m.group(1), who, m.group(2).strip() or "群里改判")
        except (KeyError, ValueError) as e:
            return {"kind": "error", "reply": e.args[0]}
        return {"kind": "overrule", "reply": "已记录改判 %s。" % m.group(1)}
    res = kbqa.triage(root, t, use_model=use_model, channel=channel, sender=who)
    rec = {"questions": [], "queued": []}
    if c.get("record", True) and (res["questions"] or res["to_write"]):
        rec = kbqa.record(root, res, "%s:%s" % (channel, who or "群成员"))
    return {"kind": "triage", "reply": reply_text(res, rec), "triage": res, "recorded": rec}


def reply_text(res: dict, rec: dict) -> str:
    L = ["**%s**（把握：%s）" % (res["verdict"], res["confidence"])]
    if res["verdict"] != "需要人判断" and res["answer"]:
        L.append(res["answer"])
    basis = res["basis"] or (res["chain"]["flows"] + res["chain"]["domains"])[:3]
    if basis:
        L.append("依据：" + "、".join("%s（%s）" % (p, res["status"].get(p, "无页")) for p in basis))
    if res["verdict"] == "需要人判断":
        why = [r for r in res["reasons"] if not r.startswith("转发模型")][:2]
        if why:
            L.append("原因：" + "；".join(why))
        nums = rec.get("questions") or []
        olds = [q["n"] for q in res["open_questions"]][:3]
        if nums:
            who = "、".join(dict.fromkeys(q.get("who") or "业务方" for q in res["questions"]))
            L.append("已转人工：问题 %s，转给%s。答复后会写回知识库。" % ("、".join("#%d" % n for n in nums), who))
        elif olds:
            L.append("相关问题还在等业务方答复：%s。" % "、".join("#%d" % n for n in olds))
        else:
            L.append("请运维同事确认后答复。")
    L.append("预判编号 %s" % res["id"])
    return "\n\n".join(L)


# ---- outbound HTTP ------------------------------------------------------------------------
def _http(url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 15) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    h = {"Content-Type": "application/json; charset=utf-8"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


_seen: "OrderedDict[str, float]" = OrderedDict()
_seen_lock = threading.Lock()


def _dup(key: str) -> bool:
    """Platforms retry a callback they think failed; answer each message once."""
    if not key:
        return False
    with _seen_lock:
        if key in _seen:
            return True
        _seen[key] = time.time()
        while len(_seen) > 2000:
            _seen.popitem(last=False)
    return False


def _later(fn, *a):
    if ASYNC:
        threading.Thread(target=_safe, args=(fn,) + a, daemon=True).start()
    else:
        fn(*a)


def _safe(fn, *a):
    try:
        fn(*a)
    except Exception as e:  # nothing to send the error to; leave a trace in the activity log
        try:
            kbqa.activity.log(a[0], "finding", "群机器人答复失败：%s" % type(e).__name__, detail=str(e)[:500])
        except Exception:
            pass


def _log_in(root: Path, channel: str, sender: str, text: str):
    kbqa.activity.log(root, "question", "%s 群里 %s 提问" % (channel, sender or "群成员"), detail=text[:500])


# ---- 钉钉 DingTalk: outgoing robot (企业内部机器人), HTTP callback ---------------------------
def dingtalk_sign(secret: str, ts: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), ("%s\n%s" % (ts, secret)).encode(), hashlib.sha256).digest()).decode()


def dingtalk(root: Path, headers: dict, raw: bytes) -> tuple[int, dict]:
    c = conf(root).get("dingtalk")
    if c is None:
        raise BotError(404, "这个项目没有配置钉钉机器人")
    secret = _env(c, "secret_env", "钉钉机器人 AppSecret")
    ts, sign = headers.get("timestamp") or "", headers.get("sign") or ""
    try:
        fresh = abs(time.time() * 1000 - int(ts)) < 3600 * 1000
    except ValueError:
        fresh = False
    if not fresh or not hmac.compare_digest(sign, dingtalk_sign(secret, ts)):
        raise BotError(401, "签名不对")
    d = json.loads(raw.decode("utf-8") or "{}")
    if _dup(d.get("msgId", "")):
        return 200, {}
    text = ((d.get("text") or {}).get("content") or "").strip()
    sender = d.get("senderNick") or d.get("senderStaffId") or ""
    _log_in(root, "钉钉", sender, text)
    hook = d.get("sessionWebhook") or ""
    host = urllib.parse.urlparse(hook).hostname or ""
    if hook and host.endswith(".dingtalk.com") and urllib.parse.urlparse(hook).scheme == "https":
        def go():
            r = handle(root, text, "dingtalk", sender)
            _http(hook, {"msgtype": "markdown", "markdown": {"title": "知识库预判", "text": r["reply"]}})
        _later(go)
        return 200, {}
    r = handle(root, text, "dingtalk", sender)  # no session webhook: answer in the response body
    return 200, {"msgtype": "markdown", "markdown": {"title": "知识库预判", "text": r["reply"]}}


# ---- 飞书 Feishu / Lark: event subscription, im.message.receive_v1 ---------------------------
def feishu_decrypt(key: str, enc: str) -> dict:
    k = hashlib.sha256(key.encode()).digest()
    b = base64.b64decode(enc)
    return json.loads(aes.unpad(aes.cbc_decrypt(k, b[:16], b[16:])).decode("utf-8"))


def feishu_encrypt(key: str, obj: dict, iv: bytes | None = None) -> str:  # used by tests and local trials
    k = hashlib.sha256(key.encode()).digest()
    iv = iv or os.urandom(16)
    return base64.b64encode(iv + aes.cbc_encrypt(k, iv, aes.pad(json.dumps(obj).encode("utf-8")))).decode()


_tokens: dict = {}


def _feishu_token(c: dict) -> str:
    base = (c.get("base_url") or "https://open.feishu.cn").rstrip("/")
    app = _env(c, "app_id_env", "飞书 App ID")
    t = _tokens.get(("feishu", app))
    if t and t[1] > time.time() + 60:
        return t[0]
    d = _http(base + "/open-apis/auth/v3/tenant_access_token/internal", {"app_id": app, "app_secret": _env(c, "app_secret_env", "飞书 App Secret")})
    if d.get("code"):
        raise BotError(502, "飞书取 token 失败：%s" % d.get("msg"))
    _tokens[("feishu", app)] = (d["tenant_access_token"], time.time() + int(d.get("expire") or 3600))
    return d["tenant_access_token"]


def feishu(root: Path, headers: dict, raw: bytes) -> tuple[int, dict]:
    c = conf(root).get("feishu")
    if c is None:
        raise BotError(404, "这个项目没有配置飞书机器人")
    key = _env(c, "encrypt_key_env", "飞书 Encrypt Key", required=False)
    vtoken = _env(c, "verification_token_env", "飞书 Verification Token", required=False)
    if not key and not vtoken:
        raise BotError(503, "飞书机器人至少要配置 Encrypt Key 或 Verification Token 之一，用来校验回调")
    d = json.loads(raw.decode("utf-8") or "{}")
    sig = headers.get("X-Lark-Signature") or ""
    if key and sig:
        want = hashlib.sha256(((headers.get("X-Lark-Request-Timestamp") or "") + (headers.get("X-Lark-Request-Nonce") or "") + key).encode() + raw).hexdigest()
        if not hmac.compare_digest(sig, want):
            raise BotError(401, "签名不对")
    if "encrypt" in d:
        if not key:
            raise BotError(400, "回调是加密的，但没有配置 Encrypt Key")
        try:
            d = feishu_decrypt(key, d["encrypt"])
        except (ValueError, KeyError):
            raise BotError(401, "解密失败")
    elif key:
        raise BotError(401, "配置了 Encrypt Key，回调却没有加密")
    # with an Encrypt Key, a payload that decrypts is authentic; otherwise the Verification Token must match
    tok = d.get("token") or (d.get("header") or {}).get("token") or ""
    if vtoken and not hmac.compare_digest(tok, vtoken):
        raise BotError(401, "Verification Token 不对")
    if d.get("type") == "url_verification":
        return 200, {"challenge": d.get("challenge", "")}
    h, ev = d.get("header") or {}, d.get("event") or {}
    if h.get("event_type") != "im.message.receive_v1" or _dup(h.get("event_id", "")):
        return 200, {}
    msg = ev.get("message") or {}
    if msg.get("message_type") != "text":
        return 200, {}
    try:
        text = json.loads(msg.get("content") or "{}").get("text", "")
    except ValueError:
        text = ""
    sid = (ev.get("sender") or {}).get("sender_id") or {}
    sender = sid.get("user_id") or sid.get("open_id") or ""
    _log_in(root, "飞书", sender, text)

    def go():
        r = handle(root, text, "feishu", sender)
        base = (c.get("base_url") or "https://open.feishu.cn").rstrip("/")
        card = {"config": {"wide_screen_mode": True}, "elements": [{"tag": "markdown", "content": r["reply"]}]}
        _http(base + "/open-apis/im/v1/messages/%s/reply" % urllib.parse.quote(msg.get("message_id", "")),
              {"msg_type": "interactive", "content": json.dumps(card, ensure_ascii=False)},
              {"Authorization": "Bearer " + _feishu_token(c)})
    _later(go)
    return 200, {}


# ---- 企业微信 WeCom: 自建应用 message callback (encrypted XML) -------------------------------
def wecom_signature(token: str, ts: str, nonce: str, enc: str) -> str:
    return hashlib.sha1("".join(sorted([token, ts, nonce, enc])).encode()).hexdigest()


def _wkey(aes_key: str) -> bytes:
    k = base64.b64decode(aes_key + "=")
    if len(k) != 32:
        raise BotError(503, "企业微信 EncodingAESKey 应为 43 位")
    return k


def wecom_decrypt(aes_key: str, corp_id: str, enc: str) -> str:
    k = _wkey(aes_key)
    p = aes.unpad(aes.cbc_decrypt(k, k[:16], base64.b64decode(enc)), 32)
    n = struct.unpack(">I", p[16:20])[0]
    msg, rid = p[20:20 + n], p[20 + n:].decode("utf-8")
    if rid != corp_id:
        raise BotError(401, "企业 ID 不对")
    return msg.decode("utf-8")


def wecom_encrypt(aes_key: str, corp_id: str, msg: str) -> str:
    k = _wkey(aes_key)
    b = msg.encode("utf-8")
    p = os.urandom(16) + struct.pack(">I", len(b)) + b + corp_id.encode("utf-8")
    return base64.b64encode(aes.cbc_encrypt(k, k[:16], aes.pad(p, 32))).decode()


def _wecom_token(c: dict) -> str:
    base = (c.get("base_url") or "https://qyapi.weixin.qq.com").rstrip("/")
    corp = _env(c, "corp_id_env", "企业微信企业 ID")
    t = _tokens.get(("wecom", corp))
    if t and t[1] > time.time() + 60:
        return t[0]
    d = _http(base + "/cgi-bin/gettoken?" + urllib.parse.urlencode({"corpid": corp, "corpsecret": _env(c, "secret_env", "企业微信应用 Secret")}))
    if d.get("errcode"):
        raise BotError(502, "企业微信取 token 失败：%s" % d.get("errmsg"))
    _tokens[("wecom", corp)] = (d["access_token"], time.time() + int(d.get("expires_in") or 7200))
    return d["access_token"]


def wecom(root: Path, method: str, q: dict, raw: bytes) -> tuple[int, str]:
    c = conf(root).get("wecom")
    if c is None:
        raise BotError(404, "这个项目没有配置企业微信应用")
    token, key, corp = _env(c, "token_env", "企业微信回调 Token"), _env(c, "aes_key_env", "企业微信 EncodingAESKey"), _env(c, "corp_id_env", "企业微信企业 ID")
    ts, nonce, sig = q.get("timestamp", ""), q.get("nonce", ""), q.get("msg_signature", "")
    if method == "GET":  # URL verification when the callback is saved in the admin console
        echo = q.get("echostr", "")
        if not hmac.compare_digest(sig, wecom_signature(token, ts, nonce, echo)):
            raise BotError(401, "签名不对")
        return 200, wecom_decrypt(key, corp, echo)
    try:
        enc = ET.fromstring(raw.decode("utf-8")).findtext("Encrypt") or ""
    except ET.ParseError:
        raise BotError(400, "不是 XML")
    if not hmac.compare_digest(sig, wecom_signature(token, ts, nonce, enc)):
        raise BotError(401, "签名不对")
    x = ET.fromstring(wecom_decrypt(key, corp, enc))
    if x.findtext("MsgType") != "text" or _dup(x.findtext("MsgId") or ""):
        return 200, ""
    text, sender = x.findtext("Content") or "", x.findtext("FromUserName") or ""
    agent = x.findtext("AgentID") or str(c.get("agent_id") or "")
    _log_in(root, "企业微信", sender, text)

    def go():
        r = handle(root, text, "wecom", sender)
        base = (c.get("base_url") or "https://qyapi.weixin.qq.com").rstrip("/")
        d = _http(base + "/cgi-bin/message/send?access_token=" + urllib.parse.quote(_wecom_token(c)),
                  {"touser": sender, "msgtype": "markdown", "agentid": int(agent) if agent.isdigit() else agent, "markdown": {"content": r["reply"]}})
        if d.get("errcode"):
            raise BotError(502, "企业微信发消息失败：%s" % d.get("errmsg"))
    _later(go)
    return 200, ""


# ---- 开放接口: POST /bot/api/<key> {"text", "sender"} with Authorization: Bearer <key> ----------
def api(root: Path, headers: dict, raw: bytes) -> tuple[int, dict]:
    c = conf(root).get("api")
    if c is None:
        raise BotError(404, "这个项目没有开放问答接口")
    want = _env(c, "key_env", "开放接口密钥")
    got = (headers.get("Authorization") or "").replace("Bearer ", "", 1).strip()
    if not got or not hmac.compare_digest(got, want):
        raise BotError(401, "接口密钥不对")
    try:
        d = json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        raise BotError(400, "请求不是 JSON")
    text = str(d.get("text") or "").strip()
    if not text:
        raise BotError(400, "text 不能为空")
    sender = str(d.get("sender") or "")[:80]
    r = handle(root, text, str(d.get("channel") or "api")[:20], sender, use_model=d.get("model", True) is not False)
    out = {"reply": r["reply"], "kind": r["kind"]}
    if r.get("triage"):
        t = r["triage"]
        out.update({"id": t["id"], "verdict": t["verdict"], "confidence": t["confidence"], "basis": t["basis"],
                    "chain": t["chain"], "questions": r["recorded"]["questions"]})
    return 200, out
