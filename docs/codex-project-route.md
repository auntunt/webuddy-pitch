# Codex 专用项目配置

Webuddy 继续通过页面、API、CLI/MCP 接单和分发。项目可单独选择官方 Codex CLI；其他项目原有 Claude、自定义执行器和模型 API 保留。

```text
页面 / API / CLI / MCP
          ↓
   项目权限与工单记录
          ↓
    项目执行器路由
      ├─ 普通项目 → 原有执行器 / API
      └─ 专用项目 → 官方 Codex → 现有网关 → 模型
                                      ↓
                           输出、测试、候选改动与人工审核
```

## 1. 独立 Codex profile

在实际运行 Webuddy 的服务器账号下生成配置。以下示例复用该账号已经配置好的 `aiseat` provider 和认证，不读取、输出或复制密钥：

```sh
python3 -m tmh agent-config codex --model gpt-6-luna \
  --profile webuddy-cloudwave --inherit-provider aiseat
```

将输出保存为 `~/.codex/webuddy-cloudwave.config.toml`，权限设为 `0600`。原有 `config.toml` 保留。官方 Codex 0.162.1 的 `exec --profile` 会叠加这个文件；其他版本应先核对实际 `codex exec --help`。

此 profile 固定模型和 provider；认证仍由官方客户端从已有配置读取。缺少 provider 或认证时报告失败，不用其他供应商代替。`approval_policy="never"` 表示执行中不能等待交互审批；只读或工作区写入沙箱仍由 Webuddy 按任务类型设置。

## 2. 注册独立执行器

合并以下条目到 Webuddy 数据目录的 `agents.json`，保留已有条目。`bin` 使用服务器上实际安装的官方客户端路径：

```json
{
  "cloudwave-codex": {
    "title": "Cloudwave · 官方 Codex",
    "engine": "codex",
    "bin": "/home/ubuntu/.npm-global/bin/codex",
    "profile": "webuddy-cloudwave",
    "prompt_transport": "stdin",
    "args": ["--ephemeral", "--color", "never"],
    "resume": false,
    "retry_busy": false,
    "run_timeout": 600,
    "models": [["gpt-6-luna", "服务器现有模型"]],
    "defaults": {}
  }
}
```

提示词通过标准输入完整传递，避免操作系统命令行长度限制。执行器保存原始输出，读取官方 JSON 事件中的最终答复、会话和用量。只有成功退出、完成事件和非空答复同时存在，才算调用成功。客户端报告的 token 不是账单；一次 CLI 启动也不等于一次 HTTP 请求。

`resume:false` 每步使用本次完整任务输入，`retry_busy:false` 关闭 Webuddy 的忙时自动重试。它们不声称关闭官方客户端内部的所有 HTTP 重试。超时和取消继续由已有进程监督器执行。

## 3. 项目路由

在同一数据目录创建 `agent-routes.json`：

```json
{
  "schema": 1,
  "projects": {
    "PPTAUTO": {
      "agent": "cloudwave-codex",
      "allowed_agents": ["cloudwave-codex"],
      "direct_api": false
    }
  }
}
```

该项目默认选择专用执行器，也拒绝显式请求其他执行器。项目页面按这份配置显示选择项。未配置的项目保持原行为；可选的 `default` 对所有项目提供默认值，项目字段再覆盖它。

`direct_api:false` 禁止项目知识预判和界面指令解析旁路直接调用模型 API。知识检索仍可用；界面指令使用规则，模型知识预判须改用任务分析，或显式设置 `model:false` 使用规则分类。API 接单、读取、分发本身仍保留。

路由配置错误、执行器缺失或启动失败都会留下明确失败；不会换成另一个执行器继续。路由只选择执行方式，不授予新的执行权限。

页面不会用以前保存的其他项目偏好覆盖指定路由。缺失的执行器仍显示为“配置不可用”；交付阶段此时不能自动开始。若管理员允许多个执行器，用户仍可在当前项目明确改选其中一个可用执行器。

## 当前团队版边界

普通成员和个人工具连接仍可按权限建单、协作、查知识。当前受管租户的自动流转保持关闭；只有既有可信执行权限的所有者可显式启动宿主执行。不能仅靠此配置放开所有成员的宿主脚本权限。

改码仍进入独立 Git 工作树，主工作区保持原样；测试与候选版本回执保留。人工复核、知识采用、验收和关单仍需真实有权人员完成。本配置不是多人试点完成或跨任务收益证明。

独立知识实验执行器 `learning_runs` 目前仍只接受其原有 Claude 隔离配置，本次没有把它改成 Codex。项目任务、知识页和普通评测可使用这里的专用路由；这不表示独立的跨任务实验已完成 Codex 适配。原有失败实验和停止记录保持。
