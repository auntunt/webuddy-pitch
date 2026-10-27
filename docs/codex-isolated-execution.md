# Codex 独立执行的配置组件

`tmh.platform.codex_frozen_config` 为后续可信隔离载体提供完整配置来源绑定、生成后的 worker 配置、固定环境与官方执行命令。本组件没有启动进程、网络入口或能力开关；`learning_runs._capabilities` 的真实 Codex 拒绝仍保持。普通项目执行器不变。

本组件只支持当前独立 profile 的简单覆盖：model、model_provider、approval_policy=never 和可选 reasoning。profile 中的 provider 表、MCP、hooks 等复杂覆盖直接拒绝，不猜测官方合并语义。源 config.toml 与 profile 均要求本人所有、owner-only、单链接常规文件，经目录 FD 与 NOFOLLOW 完整读回；超过8MiB拒绝，不截断。源字节、尺寸及生成配置 SHA 均进入公开 binding；环境凭据仅留在宿主对象，发生变化拒绝继续，不能换凭据重试。

生成配置仅含明确选定的模型、固定本地 Responses 入口、公开占位认证与命名文件/网络权限。源配置原文、真实 endpoint/认证、父附加指令、工具/记忆/插件设置均不复制进 worker HOME。宿主 broker 的 `upstream(environment)` 返回值含真实凭据，仅能留在可信宿主，禁止序列化到运行日志、公开回执、stdin 或 worker 环境。其持久身份/秘密存储由实际载体负责，本对象不能代替跨重启的私有来源登记。

worker 命令使用官方 `codex exec`、完整 stdin、JSONL、ephemeral 和 ignore-rules。不走普通 `agents.command()` 中硬编码的 `--sandbox read-only`，避免覆盖生成配置的命名权限。worker 环境为固定白名单，认证变量是公开占位值；真实凭据必须由宿主的固定目标 broker 注入。仅有该配置并不能建立隔离或证明其命名权限实际生效。

后续接线仍须复用 `IndependentRunner` 和原单监督链、取消/owner/原绝对期限；验证整个官方父进程的受限视图、工具派发、固定网关转发与完整原件。手动 sandbox、合成回显或本组件测试均不构成模型准入。此组件不授予业务人工确认、知识采用或关单。

文件读取组件要求实际载体使用 POSIX 与 Python 3.11+ TOML 读取器；不影响普通执行器原有 Python 要求。当前未验证 Windows 载体。
