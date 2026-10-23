"""Bounded HTTP adapter shared by the human CLI and stdio MCP process."""
from __future__ import annotations

import json
import http.client
import os
import re
import socket
import threading
import time

from .agent_contract import SPECS, validate
from . import workbench_credentials as credentials


class ClientError(Exception):
    def __init__(self, message, code="client_error", status=0, uncertain=False, request_id=None):
        super().__init__(message)
        self.message, self.code, self.status, self.uncertain = message, code, status, uncertain
        self.request_id = request_id

    def as_dict(self):
        result = dict(error=self.message, code=self.code, status=self.status, uncertain=self.uncertain)
        if self.request_id is not None:
            result["request_id"] = self.request_id
        return result


class Client:
    def __init__(self, endpoint=None, agent="cli", token=None, timeout=15, allow_execution=False, operator=False, operator_token="", credential_file=None, tool_token=None):
        selected = endpoint or os.environ.get("WEBUDDY_URL")
        self.credential_file = credential_file if credential_file is not None else os.environ.get("WEBUDDY_CREDENTIAL_FILE")
        try:
            if self.credential_file:
                if tool_token is not None:
                    raise credentials.CredentialError("不能同时指定凭据文件与内存凭据", "credential_conflict")
                saved = credentials.load(self.credential_file)
                if selected and credentials.endpoint(selected)[0] != saved["endpoint"]:
                    raise credentials.CredentialError("工作台地址与凭据绑定地址不同；不得将凭据转发到其他地址", "credential_endpoint_mismatch")
                selected, tool_token = saved["endpoint"], saved["token"]
            self.endpoint, u = credentials.endpoint(selected or "http://127.0.0.1:8791")
            if tool_token is not None:
                credentials.document(dict(schema=1, endpoint=self.endpoint, token=tool_token))
        except credentials.CredentialError as exc:
            raise ClientError(str(exc), exc.code) from exc
        self.tenant = u.path.split("/")[-1] if u.path else None
        self.tool_token = tool_token
        if self.tenant and not self.tool_token:
            raise ClientError("租户连接需要个人工具凭据。请在网页登录个人工具连接，运行 connect --stdin --save-to <私有文件>，再使用 --credential-file。", "tool_credential_required")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", agent):
            raise ClientError("连接名必须为 1–32 个英文字母、数字、下划线或连字符", "invalid_agent")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ClientError("HTTP 超时必须大于 0 且不超过 60 秒", "invalid_timeout")
        self.agent, self.timeout, self.allow_execution = agent, timeout, allow_execution
        self.operator = operator
        self.operator_token = operator_token
        self.token = token if token is not None else os.environ.get("WEBUDDY_TOKEN", "")
        self.address = u

    def safe_value(self, value):
        """Prevent a misconfigured upstream from echoing a delegated secret."""
        if isinstance(value, str):
            for secret in (self.tool_token, self.token, self.operator_token):
                if secret:
                    value = value.replace(secret, "[redacted]")
            return value
        if isinstance(value, list):
            return [self.safe_value(item) for item in value]
        if isinstance(value, dict):
            return {self.safe_value(key): self.safe_value(item) for key, item in value.items()}
        return value

    def connection_status(self):
        """Validate the live identity before saving credentials or listing MCP tools."""
        value = self.call("status")
        info, allowed = value.get("tool_connection"), value.get("allowed_operations")
        if (not isinstance(info, dict) or info.get("tenant") != self.tenant
                or info.get("scope") not in ("read", "content")
                or not info.get("user") or not info.get("id")
                or info.get("execution") is not False
                or info.get("status") != "active"
                or not isinstance(info.get("project_ids"), list)
                or not info.get("expires_at")
                or not isinstance(allowed, list)
                or any(not isinstance(op, str) for op in allowed)):
            raise ClientError("服务未返回有效的个人工具身份与权限；未保存凭据，请核对租户工具接入版本。", "invalid_tool_status")
        if info["scope"] == "read" and any(SPECS.get(op, {}).get("write") for op in allowed):
            raise ClientError("服务返回的权限与只读凭据不一致", "invalid_tool_status")
        return value

    def permits(self, operation):
        spec = SPECS[operation]
        return (not self.tenant or (not spec.get("execution") and not spec.get("operator")
                and (not spec["write"] or operation in ("ticket_create", "message_send"))))

    def call(self, operation, args=None):
        try:
            args = validate(operation, {} if args is None else args)
        except ValueError as e:
            raise ClientError(str(e), "invalid_arguments") from e
        spec = SPECS[operation]
        if not self.permits(operation):
            raise ClientError("个人租户工具连接仅支持授权项目读取、创建任务和工作消息；不允许执行、评审、采用或人工决定。", "tool_operation_forbidden")
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
        if self.tool_token:
            headers["Authorization"] = "Bearer " + self.tool_token
        elif self.token:
            headers["X-TMH-Token"] = self.token
        if self.allow_execution and not self.tenant:
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
            conn.request("POST", self.address.path + "/api/agent/" + operation, body=json.dumps(args, ensure_ascii=False).encode("utf-8"), headers=headers)
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
            payload = self.safe_value(payload)
            if 200 <= response.status < 300:
                # The server gives a workbench-relative authenticated entry;
                # never send users directly to the cookie-protected preview port.
                for item in [payload, *(payload.get("items", []) if isinstance(payload.get("items"), list) else [])]:
                    if isinstance(item, dict) and isinstance(item.get("preview_entry_path"), str) and item["preview_entry_path"].startswith("/pv/"):
                        item["preview_url"] = self.endpoint + item["preview_entry_path"]
                return payload
            message = payload.get("error") or "工作台返回 HTTP %s" % response.status
            if response.status == 401:
                message = ("个人工具凭据无效、已撤销或已过期。请在网页登录个人工具连接核对权限，再用 connect 导入新凭据。" if self.tenant else
                           "工作台需要认证。通过 WEBUDDY_TOKEN 环境变量提供管理员已配置的 TMH_TOKEN；不要把令牌写入参数或聊天。")
            raise ClientError(message, payload.get("code") or ("needs_reconcile" if "needs_reconcile" in str(message) else "http_error"), response.status,
                              bool(payload.get("uncertain")) or "needs_reconcile" in str(message) or (spec["write"] and response.status >= 500), args.get("request_id") if spec["write"] else None)
        except (OSError, http.client.HTTPException, ValueError, UnicodeError) as e:
            # A lost response is not evidence that a POST failed. Never auto retry.
            message = "连接或响应失败（%s）。" % type(e).__name__
            if spec["write"]:
                message += "结果未知；用 request_get 查询原 request_id，勿换编号重复操作。"
            else:
                message += "请检查工作台地址和服务状态。"
            raise ClientError(message, "connection_error", uncertain=spec["write"], request_id=args.get("request_id") if spec["write"] else None) from e
        finally:
            if timer is not None:
                timer.cancel()
            conn.close()
