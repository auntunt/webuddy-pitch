# Codex 独立执行的配置组件

`tmh.platform.codex_frozen_config` 为后续可信隔离载体提供完整配置来源绑定、生成后的 worker 配置、固定环境与官方执行命令。本组件没有启动进程、网络入口或能力开关；`learning_runs._capabilities` 的真实 Codex 拒绝仍保持。普通项目执行器不变。

本组件只支持当前独立 profile 的简单覆盖：model、model_provider、approval_policy=never 和可选 reasoning。profile 中的 provider 表、MCP、hooks 等复杂覆盖直接拒绝，不猜测官方合并语义。源 config.toml 与 profile 均要求本人所有、owner-only、单链接常规文件，经目录 FD 与 NOFOLLOW 完整读回；超过8MiB拒绝，不截断。源字节、尺寸及生成配置 SHA 均进入公开 binding；环境凭据仅留在宿主对象，发生变化拒绝继续，不能换凭据重试。

生成配置仅含明确选定的模型、固定本地 Responses 入口、公开占位认证与命名文件/网络权限。源配置原文、真实 endpoint/认证、父附加指令、工具/记忆/插件设置均不复制进 worker HOME。宿主 broker 的 `upstream(environment)` 返回值含真实凭据，仅能留在可信宿主，禁止序列化到运行日志、公开回执、stdin 或 worker 环境。其持久身份/秘密存储由实际载体负责，本对象不能代替跨重启的私有来源登记。

worker 命令使用官方 `codex exec`、完整 stdin、JSONL、ephemeral 和 ignore-rules。不走普通 `agents.command()` 中硬编码的 `--sandbox read-only`，避免覆盖生成配置的命名权限。worker 环境为固定白名单，认证变量是公开占位值；真实凭据必须由宿主的固定目标 broker 注入。仅有该配置并不能建立隔离或证明其命名权限实际生效。

生成配置按官方 0.162.1 字段明确设置 `web_search="disabled"`，清空 MCP/插件表，关闭应用、插件、远程插件、图像生成、浏览器、计算机操作及相关工具发现/依赖安装功能；命令启用 `--strict-config`。本地网络禁止并不能关闭提供商侧工具；该版本默认网页搜索为 cached，所以不能依赖默认值。字段依据固定版本的 [配置类型](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/config/src/config_toml.rs)、[功能注册表](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/features/src/lib.rs)及[托管工具生成逻辑](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/src/tools/hosted_spec.rs)核对。新增定向只证明生成配置和命令，不证明实际请求工具列表；后续真实接线仍须保存实际请求面并复核，能力门继续关闭。

后续接线仍须复用 `IndependentRunner` 和原单监督链、取消/owner/原绝对期限；验证整个官方父进程的受限视图、工具派发、固定网关转发与完整原件。手动 sandbox、合成回显或本组件测试均不构成模型准入。此组件不授予业务人工确认、知识采用或关单。

`IndependentRunner(..., codex_carrier=...)` 现提供宿主私有依赖接点，未从任务选项/API开放。载体的 `prepare(context)` 只构造 `CarrierLaunch`：固定控制器命令、宿主环境和强制私有回执校验；不得在 prepare 中启动进程或联网。命令中只能包含非秘密参数。真实凭据如需环境传入，只能给原监管中的可信宿主控制器；控制器必须另建上述固定 worker 环境，不能把自己的环境继承给 worker。所有控制器、broker、relay 和 worker 都必须在同一个原 Runner/SP 之下。

接点保留原 owner/取消事件/单调截止点及完整 stdin，由 Runner 调用且只调用一次原 run_command，载体拿不到执行回调。每次准备另给一个随机 launch_nonce，供可信控制器及私有回执绑定本次启动；它不代替原 run/attempt、身份认证或预算。准备和末次校验均消耗原预算，失败不回退普通命令，不允许会话继承或繁忙重试。私有校验必须核对受信控制器的固定输入/身份/原期限/清理证明，不能只相信可被 worker 伪造的 stdout；校验不能替换原 ProcessResult。普通 Runner 仍转发同一原监管参数。本接点仅以实际本地合成进程验证；尚未安装真实载体、接入 _Worker 宿主装配、实现私有回执读取器或开放 Codex 独立能力门。

独立 Codex 即使尚未通过能力门，缺少载体时也必须直接拒绝，不能依赖外围能力门掩盖回退路径。verify 接收原 ProcessResult 的完整深副本，包含嵌套 cleanup；原对象保留给监管链和发布记录。配置/argv 合成测试显式安装合成载体，不以普通命令回退作为测试通路，不改变原输入、时限或人工决定断言。

文件读取组件要求实际载体使用 POSIX 与 Python 3.11+ TOML 读取器；不影响普通执行器原有 Python 要求。当前未验证 Windows 载体。

`codex_gateway.forward` 是可信宿主的一次固定目标交换函数，没有监听端口、任务入口或重试循环。它只接受本地固定 Host 的 POST /v1/responses、公开占位认证、完整无歧义 JSON 与已冻结的请求模型；实际 HTTPS endpoint 和认证从冻结来源取出，官方非逐跳请求头与完整 body 保持。重定向及协议升级不进入 worker；原始响应头和全部实际收到的传输解码 payload 交由宿主 journal 私有保存，短回包不能结算为完整。HTTP 载荷完整仅代表传输事实，不代表模型成功或执行准入。journal 和连接关闭后再检查原截止点，避免慢封存/关闭后的迟到成功。

此函数必须位于原 Runner/SP 监督的可信控制器内；整体取消负责打断阻塞的 TLS/read。调用方仍须实现只有可信 namespace relay 可连接的鉴权通道、严格 HTTP 入站读取、worker TCP 监听与完整清理，再接实际 IndependentRunner。公开占位认证不是通道身份凭据。root 控制器可指定已登记的 source_owner_uid 读取服务账号配置，owner 仍精确检查并进入公开绑定；普通进程不能指定其他 owner。

当前仅有合成凭据单元测试及真实回环 HTTP 分块/短回包测试；测试替换 HTTPS 连接为回环 HTTP，不声称验证了真实 TLS、供应商、官方客户端、namespace 通道或模型工具派发。真实执行能力门继续关闭。

严格 framing 校验器通过既有 resources 流程完整带入 sdist、wheel、离线包和项目内置工具，网关从固定资源路径加载原始代码，不依赖检出树或顶层 scripts 包；原始 provider_transport.py 不修改、不维护副本。本轮在临时目录实际构建 sdist，再从解包的 sdist 构建 wheel，以 no-index/no-deps 安装；隔离解释器分别从 wheel、离线解包树及内置工具导入并检查完整字节与 framing 行为。新运行资源缺失时 install() 在创建项目之前拒绝。

以上是临时安装物验证，未更新服务器程序或旧硬编码发布清单。未来从源码目录发布必须包含 resources.FILES 所列文件，其中包括 scripts/rsi/provider_transport.py；不能只复制 tmh/ 后声明完整依赖已部署。
