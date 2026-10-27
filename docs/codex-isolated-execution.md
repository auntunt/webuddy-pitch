# Codex 独立执行的配置组件

`tmh.platform.codex_frozen_config` 为后续可信隔离载体提供完整配置来源绑定、生成后的 worker 配置、固定环境与官方执行命令。本组件没有启动进程、网络入口或能力开关；`learning_runs._capabilities` 的真实 Codex 拒绝仍保持。普通项目执行器不变。

本组件只支持当前独立 profile 的简单覆盖：model、model_provider、approval_policy=never 和可选 reasoning。profile 中的 provider 表、MCP、hooks 等复杂覆盖直接拒绝，不猜测官方合并语义。源 config.toml 与 profile 均要求本人所有、owner-only、单链接常规文件，经目录 FD 与 NOFOLLOW 完整读回；超过8MiB拒绝，不截断。源字节、尺寸及生成配置 SHA 均进入公开 binding；环境凭据仅留在宿主对象，发生变化拒绝继续，不能换凭据重试。

生成配置仅含明确选定的模型、固定本地 Responses 入口、公开占位认证与命名文件/网络权限。源配置原文、真实 endpoint/认证、父附加指令、工具/记忆/插件设置均不复制进 worker HOME。宿主 broker 的 `upstream(environment)` 返回值含真实凭据，仅能留在可信宿主，禁止序列化到运行日志、公开回执、stdin 或 worker 环境。其持久身份/秘密存储由实际载体负责，本对象不能代替跨重启的私有来源登记。

worker 命令使用官方 `codex exec`、完整 stdin、JSONL、ephemeral 和 ignore-rules。不走普通 `agents.command()` 中硬编码的 `--sandbox read-only`，避免覆盖生成配置的命名权限。worker 环境为固定白名单，认证变量是公开占位值；真实凭据必须由宿主的固定目标 broker 注入。仅有该配置并不能建立隔离或证明其命名权限实际生效。

后续接线仍须复用 `IndependentRunner` 和原单监督链、取消/owner/原绝对期限；验证整个官方父进程的受限视图、工具派发、固定网关转发与完整原件。手动 sandbox、合成回显或本组件测试均不构成模型准入。此组件不授予业务人工确认、知识采用或关单。

文件读取组件要求实际载体使用 POSIX 与 Python 3.11+ TOML 读取器；不影响普通执行器原有 Python 要求。当前未验证 Windows 载体。

`codex_gateway.forward` 是可信宿主的一次固定目标交换函数，没有监听端口、任务入口或重试循环。它只接受本地固定 Host 的 POST /v1/responses、公开占位认证、完整无歧义 JSON 与已冻结的请求模型；实际 HTTPS endpoint 和认证从冻结来源取出，官方非逐跳请求头与完整 body 保持。重定向及协议升级不进入 worker；原始响应头和全部实际收到的传输解码 payload 交由宿主 journal 私有保存，短回包不能结算为完整。HTTP 载荷完整仅代表传输事实，不代表模型成功或执行准入。journal 和连接关闭后再检查原截止点，避免慢封存/关闭后的迟到成功。

此函数必须位于原 Runner/SP 监督的可信控制器内；整体取消负责打断阻塞的 TLS/read。调用方仍须实现只有可信 namespace relay 可连接的鉴权通道、严格 HTTP 入站读取、worker TCP 监听与完整清理，再接实际 IndependentRunner。公开占位认证不是通道身份凭据。root 控制器可指定已登记的 source_owner_uid 读取服务账号配置，owner 仍精确检查并进入公开绑定；普通进程不能指定其他 owner。

当前仅有合成凭据单元测试及真实回环 HTTP 分块/短回包测试；测试替换 HTTPS 连接为回环 HTTP，不声称验证了真实 TLS、供应商、官方客户端、namespace 通道或模型工具派发。安装闭包还须包含既有 `scripts/rsi/provider_transport.py` 的严格 framing 校验器；当前旧发布打包方式未在本增量中验证或改变。真实执行能力门继续关闭。
