"""Phase-1 modules: 少找人 metrics, chat robots (钉钉/飞书/企微/开放接口), similar tickets, offline pack, pure-Python AES."""
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from tmh import aes, bots, kb, kbqa, offline  # noqa: E402
from tmh import config as cfgmod  # noqa: E402
from tmh.cli import main  # noqa: E402
from tmh.platform.similar import similar  # noqa: E402

JAVA = HERE.parent / "examples" / "legacy-java-oa"


class AesTest(unittest.TestCase):
    def test_fips197_and_cbc_against_reference(self):
        k = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        self.assertEqual(aes.AES(k).encrypt_block(bytes.fromhex("00112233445566778899aabbccddeeff")).hex(), "69c4e0d86a7b0430d8cdb78070b4c55a")
        k256 = bytes(range(32))
        self.assertEqual(aes.AES(k256).encrypt_block(bytes.fromhex("00112233445566778899aabbccddeeff")).hex(), "8ea2b7ca516745bfeafc49904b496089")
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except ImportError:
            return
        for kl in (16, 24, 32):
            key, iv, d = os.urandom(kl), os.urandom(16), os.urandom(160)
            e = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
            ref = e.update(d) + e.finalize()
            self.assertEqual(aes.cbc_encrypt(key, iv, d), ref)
            self.assertEqual(aes.cbc_decrypt(key, iv, ref), d)
        self.assertEqual(aes.unpad(aes.pad(b"abc", 32), 32), b"abc")
        with self.assertRaises(ValueError):
            aes.unpad(b"\x00" * 16)


class Phase1Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = Path(tempfile.mkdtemp(prefix="tmh-p1src-")) / "r"
        shutil.copytree(JAVA, cls.src)
        kb.build(cls.src)

    def setUp(self):
        self.repo = Path(tempfile.mkdtemp(prefix="tmh-p1-")) / "r"
        shutil.copytree(self.src, self.repo)
        bots.ASYNC = False
        bots._seen.clear()
        bots._tokens.clear()

    def tearDown(self):
        bots.ASYNC = True

    def set_bots(self, b):
        c = cfgmod.load(self.repo)
        c["bots"] = b
        cfgmod.save(self.repo, c)


class FewerPeopleMetricsTest(Phase1Base):
    def test_triage_log_overrule_and_metrics(self):
        r = kbqa.triage(self.repo, "报销单财务审核驳回", use_model=False, channel="dingtalk", sender="小李")
        self.assertEqual(len(r["id"]), 8)
        row = kbqa.triages(self.repo)[0]
        self.assertEqual((row["id"], row["channel"], row["sender"]), (r["id"], "dingtalk", "小李"))
        # an automatic answer (as the router would give) that a person later overrules
        kbqa._append(self.repo, "triage.jsonl", {"id": "a1b2c3d4", "at": time.strftime("%Y-%m-%d %H:%M"), "ts": int(time.time()),
                                                 "request": "请假列表加筛选", "verdict": "可以做", "confidence": "中", "channel": "web"})
        kbqa._append(self.repo, "triage.jsonl", {"id": "b1b2c3d4", "at": time.strftime("%Y-%m-%d %H:%M"), "ts": int(time.time()),
                                                 "request": "请假单打印", "verdict": "可以做", "confidence": "高", "channel": "api"})
        with self.assertRaises(ValueError):
            kbqa.overrule(self.repo, "a1b2c3d4", "agent", "x")
        with self.assertRaises(KeyError):
            kbqa.overrule(self.repo, "ffffffff", "王工", "x")
        kbqa.overrule(self.repo, "a1b2c3d4", "王工", "筛选要改存储过程，不是加字段")
        n = kbqa.ask(self.repo, "驳回后预算是否全额释放？", ["dom:expense"], "财务")
        ev = kb.tmh_dir(self.repo) / "cache" / "questions.jsonl"
        rows = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines()]
        rows[0]["ts"] -= 7200  # asked two hours ago
        ev.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n", encoding="utf-8")
        kbqa.answer(self.repo, n, "全额释放", "王会计")
        m = kbqa.metrics(self.repo)
        self.assertEqual((m["triage"], m["auto"], m["overruled"], m["handoff"]), (3, 2, 1, 1))
        self.assertAlmostEqual(m["adopted_rate"], round(1 / 3, 3))
        self.assertEqual((m["answered"], m["answer_wait_hours"]), (1, 2.0))
        self.assertEqual(m["channels"], {"dingtalk": 1, "web": 1, "api": 1})
        self.assertEqual(sum(w["triage"] for w in m["weeks"]), 3)
        self.assertEqual(kbqa.metrics(self.repo, month="1999-01")["triage"], 0)
        self.assertIn("采纳率 33%", kbqa.metrics_text(m))
        self.assertEqual(kbqa.triages(self.repo)[1]["overruled"]["by"], "王工")
        self.assertEqual(main(["kb", "metrics", "--repo", str(self.repo)]), 0)
        self.assertEqual(main(["kb", "overrule", "b1b2c3d4", "--who", "李工", "--reason", "打印模板另有规则", "--repo", str(self.repo)]), 0)
        self.assertEqual(kbqa.metrics(self.repo)["overruled"], 2)
        self.assertEqual(main(["kb", "overrule", "b1b2c3d4", "--repo", str(self.repo)]), 1)  # needs a person


class BotTest(Phase1Base):
    def test_conversation_core(self):
        self.set_bots({"api": {"key_env": "X"}, "answerers": ["王会计"]})
        self.assertEqual(bots.handle(self.repo, "@运维助手 帮助", "dingtalk", "a")["kind"], "help")
        r = bots.handle(self.repo, "@运维助手 火星基地排班怎么做", "dingtalk", "小李", use_model=False)
        self.assertEqual(r["kind"], "triage")
        self.assertIn("需要人判断", r["reply"])
        self.assertIn("已转人工：问题 #", r["reply"])
        n = r["recorded"]["questions"][0]
        self.assertIn("dingtalk:小李", kbqa.questions(self.repo)[n - 1]["answer"])
        self.assertEqual(bots.handle(self.repo, "答复 #%d 没有这个业务" % n, "dingtalk", "小李")["kind"], "denied")
        ok = bots.handle(self.repo, "答复 #%d：没有这个业务" % n, "dingtalk", "王会计")
        self.assertEqual(ok["kind"], "answer")
        self.assertFalse(kbqa.questions(self.repo)[n - 1]["open"])
        tid = r["triage"]["id"]
        self.assertEqual(bots.handle(self.repo, "改判 %s 这个要找人" % tid, "dingtalk", "王会计")["kind"], "overrule")
        self.assertEqual(bots.clean("@_user_1 资金计划 能不能导出"), "资金计划 能不能导出")

    def test_dingtalk_signed_callback(self):
        self.set_bots({"dingtalk": {"secret_env": "T_DING"}})
        sent = []
        with mock.patch.dict(os.environ, {"T_DING": "s3cret"}), mock.patch.object(bots, "_http", side_effect=lambda u, b=None, h=None, timeout=15: sent.append((u, b)) or {}):
            ts = str(int(time.time() * 1000))
            body = json.dumps({"msgId": "m1", "text": {"content": " 报销单财务审核驳回"}, "senderNick": "小李",
                               "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=x"}).encode()
            with self.assertRaises(bots.BotError) as cm:
                bots.dingtalk(self.repo, {"timestamp": ts, "sign": "bad"}, body)
            self.assertEqual(cm.exception.code, 401)
            code, out = bots.dingtalk(self.repo, {"timestamp": ts, "sign": bots.dingtalk_sign("s3cret", ts)}, body)
            self.assertEqual((code, out), (200, {}))
            self.assertEqual(sent[0][0], "https://oapi.dingtalk.com/robot/sendBySession?session=x")
            self.assertIn("预判编号", sent[0][1]["markdown"]["text"])
            bots.dingtalk(self.repo, {"timestamp": ts, "sign": bots.dingtalk_sign("s3cret", ts)}, body)
            self.assertEqual(len(sent), 1)  # retried callback answered once
            evil = json.dumps({"msgId": "m2", "text": {"content": "报销"}, "sessionWebhook": "https://evil.example/x"}).encode()
            code, out = bots.dingtalk(self.repo, {"timestamp": ts, "sign": bots.dingtalk_sign("s3cret", ts)}, evil)
            self.assertEqual(out["msgtype"], "markdown")  # never posts to a host outside DingTalk
            self.assertEqual(len(sent), 1)
            old = str(int(time.time() * 1000) - 2 * 3600 * 1000)
            with self.assertRaises(bots.BotError):
                bots.dingtalk(self.repo, {"timestamp": old, "sign": bots.dingtalk_sign("s3cret", old)}, body)

    def test_feishu_encrypted_events(self):
        self.set_bots({"feishu": {"app_id_env": "F_ID", "app_secret_env": "F_SEC", "encrypt_key_env": "F_KEY", "verification_token_env": "F_TOK"}})
        env = {"F_ID": "cli_x", "F_SEC": "sec", "F_KEY": "enc-key", "F_TOK": "vtok"}
        calls = []

        def fake(url, body=None, headers=None, timeout=15):
            calls.append((url, body, headers))
            return {"code": 0, "tenant_access_token": "t-1", "expire": 7200} if "tenant_access_token" in url else {"code": 0}
        with mock.patch.dict(os.environ, env), mock.patch.object(bots, "_http", side_effect=fake):
            raw = json.dumps({"encrypt": bots.feishu_encrypt("enc-key", {"type": "url_verification", "challenge": "c-1", "token": "vtok"})}).encode()
            self.assertEqual(bots.feishu(self.repo, {}, raw), (200, {"challenge": "c-1"}))
            ev = {"schema": "2.0", "header": {"event_id": "e1", "event_type": "im.message.receive_v1", "token": "vtok"},
                  "event": {"sender": {"sender_id": {"open_id": "ou_1"}},
                            "message": {"message_id": "om_1", "message_type": "text", "content": json.dumps({"text": "@_user_1 报销单财务审核驳回"})}}}
            raw = json.dumps({"encrypt": bots.feishu_encrypt("enc-key", ev)}).encode()
            ts, nonce = "1700000000", "n1"
            sig = hashlib.sha256((ts + nonce + "enc-key").encode() + raw).hexdigest()
            with self.assertRaises(bots.BotError):
                bots.feishu(self.repo, {"X-Lark-Signature": "0" * 64, "X-Lark-Request-Timestamp": ts, "X-Lark-Request-Nonce": nonce}, raw)
            self.assertEqual(bots.feishu(self.repo, {"X-Lark-Signature": sig, "X-Lark-Request-Timestamp": ts, "X-Lark-Request-Nonce": nonce}, raw), (200, {}))
            reply = calls[-1]
            self.assertTrue(reply[0].endswith("/open-apis/im/v1/messages/om_1/reply"))
            self.assertEqual(reply[2]["Authorization"], "Bearer t-1")
            self.assertIn("预判编号", json.loads(reply[1]["content"])["elements"][0]["content"])
            with self.assertRaises(bots.BotError):  # plaintext callback while an Encrypt Key is configured
                bots.feishu(self.repo, {}, json.dumps(ev).encode())
            bad = json.dumps({"encrypt": bots.feishu_encrypt("other-key", ev)}).encode()
            with self.assertRaises(bots.BotError):
                bots.feishu(self.repo, {}, bad)
        self.assertEqual(kbqa.triages(self.repo)[0]["channel"], "feishu")

    def test_wecom_encrypted_callback(self):
        key = base64.b64encode(os.urandom(32)).decode().rstrip("=")
        self.set_bots({"wecom": {"corp_id_env": "W_CORP", "token_env": "W_TOK", "aes_key_env": "W_AES", "secret_env": "W_SEC", "agent_id": "1000002"}})
        env = {"W_CORP": "ww123", "W_TOK": "tok", "W_AES": key, "W_SEC": "sec"}
        calls = []

        def fake(url, body=None, headers=None, timeout=15):
            calls.append((url, body))
            return {"errcode": 0, "access_token": "at-1", "expires_in": 7200}
        with mock.patch.dict(os.environ, env), mock.patch.object(bots, "_http", side_effect=fake):
            echo = bots.wecom_encrypt(key, "ww123", "hello-echo")
            q = {"timestamp": "1", "nonce": "n", "echostr": echo, "msg_signature": bots.wecom_signature("tok", "1", "n", echo)}
            self.assertEqual(bots.wecom(self.repo, "GET", q, b""), (200, "hello-echo"))
            with self.assertRaises(bots.BotError):
                bots.wecom(self.repo, "GET", dict(q, msg_signature="x"), b"")
            msg = ("<xml><ToUserName>ww123</ToUserName><FromUserName>lisi</FromUserName><MsgType>text</MsgType>"
                   "<Content>报销单财务审核驳回</Content><MsgId>9</MsgId><AgentID>1000002</AgentID></xml>")
            enc = bots.wecom_encrypt(key, "ww123", msg)
            raw = ("<xml><ToUserName>ww123</ToUserName><Encrypt>%s</Encrypt></xml>" % enc).encode()
            q = {"timestamp": "2", "nonce": "m", "msg_signature": bots.wecom_signature("tok", "2", "m", enc)}
            self.assertEqual(bots.wecom(self.repo, "POST", q, raw), (200, ""))
            send = calls[-1]
            self.assertIn("/cgi-bin/message/send?access_token=at-1", send[0])
            self.assertEqual((send[1]["touser"], send[1]["agentid"], send[1]["msgtype"]), ("lisi", 1000002, "markdown"))
            wrong = bots.wecom_encrypt(key, "ww999", msg)
            with self.assertRaises(bots.BotError):
                bots.wecom(self.repo, "POST", {"timestamp": "2", "nonce": "m", "msg_signature": bots.wecom_signature("tok", "2", "m", wrong)},
                           ("<xml><Encrypt>%s</Encrypt></xml>" % wrong).encode())

    def test_open_api_and_status(self):
        self.set_bots({"api": {"key_env": "B_KEY"}, "dingtalk": {"secret_env": "NOPE"}})
        with mock.patch.dict(os.environ, {"B_KEY": "k-1"}):
            with self.assertRaises(bots.BotError):
                bots.api(self.repo, {"Authorization": "Bearer wrong"}, b'{"text":"x"}')
            code, out = bots.api(self.repo, {"Authorization": "Bearer k-1"}, json.dumps({"text": "报销单财务审核驳回", "sender": "OA", "model": False}).encode())
            self.assertEqual((code, out["kind"], out["verdict"]), (200, "triage", "需要人判断"))
            st = bots.status(self.repo)
            self.assertTrue(st["bots"]["api"]["ready"])
            self.assertEqual(st["bots"]["dingtalk"]["missing_env"], ["NOPE"])
            self.assertNotIn("k-1", json.dumps(st))


class SimilarTicketTest(unittest.TestCase):
    def test_ranks_by_shared_words(self):
        ts = [{"id": 1, "key": "OA-1", "title": "请假单列表按部门筛选不出数据", "body": "选择部门后列表为空", "status": "done"},
              {"id": 2, "key": "OA-2", "title": "报销单打印模板错位", "body": "打印时金额栏错位", "status": "open"},
              {"id": 3, "key": "OA-3", "title": "请假审批流程卡住", "body": "部门经理审批后不流转", "status": "open"}]
        r = similar(ts, "请假列表部门筛选为空")
        self.assertEqual(r[0]["key"], "OA-1")
        self.assertIn("筛选", r[0]["shared"])
        self.assertNotIn("OA-2", [x["key"] for x in r])
        self.assertNotIn("OA-1", [x["key"] for x in similar(ts, "请假单列表按部门筛选不出数据", exclude=1)])
        self.assertEqual(similar(ts, ""), [])


class OfflinePackTest(unittest.TestCase):
    def test_build_verify_and_tamper(self):
        d = Path(tempfile.mkdtemp(prefix="tmh-off-"))
        out = d / "pack.zip"
        r = offline.build(out)
        self.assertGreater(r["files"], 40)
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            self.assertIn("tmh/cli.py", names)
            self.assertIn("README-offline.md", names)
            self.assertIn("skills/knowledge-upkeep/SKILL.md", names)
            self.assertFalse(any("__pycache__" in n for n in names))
            self.assertIn("TMH_ROUTER_BASE_URL", z.read("README-offline.md").decode("utf-8"))
        self.assertTrue(offline.verify(out)["ok"])
        bad = d / "bad.zip"
        with zipfile.ZipFile(out) as a, zipfile.ZipFile(bad, "w") as b:
            for n in a.namelist():
                b.writestr(n, a.read(n) + (b"#x" if n == "tmh/kbqa.py" else b""))
        v = offline.verify(bad)
        self.assertEqual((v["ok"], v["bad"]), (False, ["tmh/kbqa.py"]))
        self.assertEqual(main(["offline-pack", "--verify", str(bad)]), 1)


if __name__ == "__main__":
    unittest.main()
