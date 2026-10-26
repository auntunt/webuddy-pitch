"""Generate engine configuration for third-party / domestic model APIs.

Never writes a key to disk: configuration references an environment variable
that the operator sets in their own shell or secret store.
"""
from __future__ import annotations

import json
import re


def inherited_codex_profile(profile: str, provider: str, model: str) -> str:
    """A separate CLI profile that reuses credentials in the existing user config.

    No credential discovery, provider-table copying, or direct HTTP adapter is
    involved. The installed official client merges this file with its base config.
    """
    for label, value in (("profile", profile), ("provider", provider)):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
            raise ValueError(label + " 只能包含字母、数字、下划线和短横线")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:\-\[\]/]{0,79}", model):
        raise ValueError("模型名不合法")
    return ("# 保存为 $CODEX_HOME/%s.config.toml（通常为 ~/.codex/）。\n"
            "# 使用官方 Codex CLI：codex exec --profile %s。\n"
            "# 复用现有 config.toml 中的 provider 和认证；不复制密钥。\n"
            "# 若 provider 不存在，先由管理员配置；不会切换到其他服务。\n"
            "model = %s\nmodel_provider = %s\napproval_policy = \"never\"\n"
            % (profile, profile, json.dumps(model), json.dumps(provider)))

# Anthropic-compatible endpoints usable by Claude Code (checked 2026-10 from vendor
# docs; confirm against the provider's current docs before production use).
CLAUDE_PRESETS = {
    "deepseek": {"base_url": "https://api.deepseek.com/anthropic", "key_env": "DEEPSEEK_API_KEY"},
    "kimi": {"base_url": "https://api.moonshot.cn/anthropic", "key_env": "MOONSHOT_API_KEY"},
    "kimi-code": {"base_url": "https://api.kimi.com/coding/", "key_env": "KIMI_API_KEY"},
    "glm": {"base_url": "https://open.bigmodel.cn/api/anthropic", "key_env": "ZHIPU_API_KEY"},
    "glm-intl": {"base_url": "https://api.z.ai/api/anthropic", "key_env": "ZAI_API_KEY"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/apps/anthropic", "key_env": "DASHSCOPE_API_KEY"},
    "custom": {"base_url": "https://your-gateway.example.com", "key_env": "LLM_GATEWAY_KEY"},
}
# Codex speaks only the Responses API (wire_api = "chat" was removed). As of 2026-10
# DeepSeek, Kimi and Z.ai publish Responses-compatible endpoints with Codex guides;
# `verified` = False means we found no vendor Codex guide for that endpoint.
CODEX_PRESETS = {
    "deepseek": {"base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY", "verified": True,
                 "doc": "https://api-docs.deepseek.com/quick_start/agent_integrations/codex"},
    "kimi": {"base_url": "https://api.moonshot.cn/v1", "key_env": "MOONSHOT_API_KEY", "verified": True,
             "doc": "https://platform.kimi.com/docs/api/responses"},
    "kimi-code": {"base_url": "https://api.kimi.com/coding/v1", "key_env": "KIMI_API_KEY", "verified": True,
                  "doc": "https://www.kimi.com/code/docs/en/third-party-tools/codex.html"},
    "glm-intl": {"base_url": "https://api.z.ai/api/v1", "key_env": "ZAI_API_KEY", "verified": True,
                 "doc": "https://docs.z.ai/devpack/tool/codex.md"},
    "glm": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "key_env": "ZHIPU_API_KEY", "verified": False,
            "doc": "未找到智谱国内站的 Codex 说明；不通时改用 glm-intl 或 litellm"},
    "qwen": {"base_url": "https://<WorkspaceId>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1", "key_env": "DASHSCOPE_API_KEY", "verified": False,
             "doc": "https://help.aliyun.com/zh/model-studio/compatibility-with-openai-responses-api"},
    "litellm": {"base_url": "http://127.0.0.1:4000/v1", "key_env": "LITELLM_KEY", "verified": False,
                "doc": "本机 LiteLLM 网关，把只支持 Chat Completions 的模型转成 Responses API"},
    "custom": {"base_url": "https://your-gateway.example.com/v1", "key_env": "LLM_GATEWAY_KEY", "verified": False, "doc": ""},
}


def claude_config(provider: str, model: str, fast_model: str = "") -> str:
    p = CLAUDE_PRESETS.get(provider)
    if not p:
        raise SystemExit("未知 provider，可选：" + ", ".join(CLAUDE_PRESETS))
    fast = fast_model or model
    return """# Claude Code 接第三方模型（{provider}）
# 1) 在你自己的 shell 或密钥管理里设置密钥（不要写进仓库、聊天或配置文件）：
#    export {key_env}=...
# 2) 启动前导出以下变量（可放进 ~/.bashrc 或启动脚本）：
export ANTHROPIC_BASE_URL="{base}"
export ANTHROPIC_AUTH_TOKEN="${key_env}"
export ANTHROPIC_MODEL="{model}"
export ANTHROPIC_DEFAULT_SONNET_MODEL="{model}"
export ANTHROPIC_DEFAULT_OPUS_MODEL="{model}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="{fast}"
export CLAUDE_CODE_SUBAGENT_MODEL="{model}"
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
export API_TIMEOUT_MS=600000
# 3) 在项目根目录运行 claude。技能、子代理、钩子会从 .claude/ 自动加载。
#
# 说明：端点为 2026-10 核对的 Anthropic 兼容地址，模型名以厂商当前文档为准。
# 第三方模型对工具调用、长上下文和子代理的支持程度不同，先用下面的冒烟提示测一次。
""".format(provider=provider, key_env=p["key_env"], base=p["base_url"], model=model, fast=fast)


def codex_config(provider: str, model: str, fast_model: str = "") -> str:
    p = CODEX_PRESETS.get(provider)
    if not p:
        raise SystemExit("未知 provider，可选：" + ", ".join(CODEX_PRESETS))
    note = "厂商文档：%s" % p["doc"] if p["verified"] else "【未实测】%s" % p["doc"]
    fast = ""
    if fast_model:
        fast = "\n# 子代理（只读勘察、影响分析）用便宜的模型，主会话用强模型：\n[agents]\ndefault_subagent_model = \"%s\"\n" % fast_model
    return """# Codex CLI 接第三方模型（{provider}）——合并到 ~/.codex/config.toml，或另存为 ~/.codex/{provider}.config.toml 后用 codex --profile {provider}
# Codex 只支持 Responses API（wire_api = "responses"）。{note}
model = "{model}"
model_provider = "{provider}"

[model_providers.{provider}]
name = "{provider}"
base_url = "{base}"
env_key = "{key_env}"
wire_api = "responses"
{fast}
# 密钥只放环境变量：export {key_env}=...（不要写进仓库或配置文件）
# 在项目根目录运行 codex；它会读取 AGENTS.md、.agents/skills/、.codex/agents/ 和 .codex/hooks.json。
# 模型名以厂商当前文档为准。
""".format(provider=provider, key_env=p["key_env"], base=p["base_url"], model=model, note=note, fast=fast)


SMOKE_PROMPT = """请只做以下检查并用中文简短汇报，不要修改任何文件：
1. 运行 `python3 .tmh/tool/tmh.py status` 并复述输出的前 5 行
2. 读取 .tmh/PROJECT_MAP.md 的标题行
3. 列出你能看到的技能（skills）名称
如果任何一步无法调用工具，请直接说明是哪一步。"""
