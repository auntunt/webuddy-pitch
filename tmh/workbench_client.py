"""Bounded HTTP adapter shared by the human CLI and stdio MCP process."""
from __future__ import annotations

import json
import http.client
import os
import re
import socket
import threading
import time
import urllib.parse

from .agent_contract import SPECS, validate


class ClientError(Exception):
    def __init__(self, message, code="client_error", status=0, uncertain=False):
        super().__init__(message)
        self.message, self.code, self.status, self.uncertain = message, code, status, uncertain

    def as_dict(self):
        return dict(error=self.message, code=self.code, status=self.status, uncertain=self.uncertain)


class Client:
    def __init__(self, endpoint=None, agent="cli", token=None, timeout=15, allow_execution=False, operator=False, operator_token=""):
        self.endpoint = (endpoint or os.environ.get("WEBUDDY_URL") or "http://127.0.0.1:8791").rstrip("/")
        try:
            u = urllib.parse.urlsplit(self.endpoint)
            u.port
        except ValueError as e:
            raise ClientError("工作台地址或端口格式不正确", "invalid_endpoint") from e
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
            raise ClientError("工作台地址必须是 http(s)://host:port，不得带路径、凭据或查询参数", "invalid_endpoint")
        if u.scheme == "http" and u.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ClientError("远程连接必须使用 HTTPS；本地可使用 127.0.0.1/localhost", "insecure_endpoint")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", agent):
            raise ClientError("连接名必须为 1–32 个英文字母、数字、下划线或连字符", "invalid_agent")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ClientError("HTTP 超时必须大于 0 且不超过 60 秒", "invalid_timeout")
        self.agent, self.timeout, self.allow_execution = agent, timeout, allow_execution
        self.operator = operator
        self.operator_token = operator_token
        self.token = token if token is not None else os.environ.get("WEBUDDY_TOKEN", "")
        self.address = u

    def call(self, operation, args=None):
        try:
            args = validate(operation, {} if args is None else args)
        except ValueError as e:
            raise ClientError(str(e), "invalid_arguments") from e
        spec = SPECS[operation]
        if spec.get("operator") and not self.operator:
            raise ClientError("需要操作者在终端明确确认；Agent/MCP不能代签", "operator_required")
        if spec.get("operator") and not self.operator_token:
            raise ClientError("缺少独立操作者凭据，工作区Agent令牌不能代替", "operator_credential_required")
        if spec["execution"] and not self.allow_execution:
            raise ClientError("此连接未启用执行。MCP 启动时添加 --allow-execution；CLI 使用明确的 start/retry/recheck/preview --start 命令。", "execution_disabled")
        headers = {"Content-Type": "application/json", "X-TMH": "1", "X-Webuddy-Agent": self.agent}
        if spec.get("operator"):
            headers.pop("X-Webuddy-Agent")
            headers["X-Webuddy-Operator"] = "1"
            headers["X-Webuddy-Operator-Token"] = self.operator_token
        if self.token:
            headers["X-TMH-Token"] = self.token
        if self.allow_execution:
            headers["X-Webuddy-Execution"] = "1"
        # Direct connection: never forward credentials via redirects or environment
        # proxies. A deadline closes the socket even if a peer continuously drips
        # headers/body (socket's inactivity timeout alone does not cover that).
        cls = http.client.HTTPSConnection if self.address.scheme == "https" else http.client.HTTPConnection
        conn = cls(self.address.hostname, self.address.port, timeout=self.timeout)
        deadline = time.monotonic() + self.timeout
        timer = None
        expired = threading.Event()
        try:
            conn.connect()
            sock = conn.sock

            def expire():
                expired.set()
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("deadline")
            sock.settimeout(remaining)
            timer = threading.Timer(remaining, expire)
            timer.daemon = True
            timer.start()
            conn.request("POST", "/api/agent/" + operation, body=json.dumps(args, ensure_ascii=False).encode("utf-8"), headers=headers)
            response = conn.getresponse()
            raw = response.read()
            if expired.is_set() or time.monotonic() > deadline:
                raise TimeoutError("deadline")
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError):
                if 200 <= response.status < 300:
                    raise
                payload = {}
            if not isinstance(payload, dict):
                if 200 <= response.status < 300:
                    raise ValueError("response must be an object")
                payload = {}
            if 200 <= response.status < 300:
                # The server gives a workbench-relative authenticated entry;
                # never send users directly to the cookie-protected preview port.
                for item in [payload, *(payload.get("items", []) if isinstance(payload.get("items"), list) else [])]:
                    if isinstance(item, dict) and isinstance(item.get("preview_entry_path"), str) and item["preview_entry_path"].startswith("/pv/"):
                        item["preview_url"] = self.endpoint + item["preview_entry_path"]
                return payload
            message = payload.get("error") or "工作台返回 HTTP %s" % response.status
            if response.status == 401:
                message = "工作台需要认证。通过 WEBUDDY_TOKEN 环境变量提供管理员已配置的 TMH_TOKEN；不要把令牌写入参数或聊天。"
            raise ClientError(message, payload.get("code") or ("needs_reconcile" if "needs_reconcile" in str(message) else "http_error"), response.status,
                              bool(payload.get("uncertain")) or "needs_reconcile" in str(message) or (spec["write"] and response.status >= 500))
        except (OSError, http.client.HTTPException, ValueError, UnicodeError) as e:
            # A lost response is not evidence that a POST failed. Never auto retry.
            message = "连接或响应失败（%s）。" % type(e).__name__
            if spec["write"]:
                message += "结果未知；用 request_get 查询原 request_id，勿换编号重复操作。"
            else:
                message += "请检查工作台地址和服务状态。"
            raise ClientError(message, "connection_error", uncertain=spec["write"]) from e
        finally:
            if timer is not None:
                timer.cancel()
            conn.close()
