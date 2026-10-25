# 登记输入与执行接线：增量 1

本增量把真实生产提示词工厂接到“服务器登记计划 ID / 输入 ID → 原根预算 → 原 provider 回执”。它不是新的实验平台，不接生产路由，也不是隔离执行器。controller/候选/oracle evaluator 的实际 OS 身份隔离和回执串接仍待下一增量，当前明确返回 `isolated_execution=not_run`、`oracle_evaluation=not_run`、`rsi_qualified=false`。

## 已实现的实际通路

`capture` 调用一次原 `agents.build_prompt`，不重写提示词、selector、renderer、授权过滤或普通经验使用记录。保留完整工单/项目、完整输入 history、生产实际最后六条 history 窗口、原 prompt 全文、上下文/经验引用回执、选择池前后快照和 factory/lesson_input 源码摘要。调用有原生产工厂的普通读写/usage副作用，不是假 dry-run；必须由原有已授权服务器上下文调用。本轮只在合成临时 Store/项目验证，不读取或写入真实业务 data。

基线和候选由同一次 capture 生成，唯一允许差异为独立 system 策略及其摘要；prompt 正文、工具面、fresh session、来源摘要必须一致。长文本、null、原始 history、经验附件/前后来源均保留。D 后续任务应重新 capture 自己的真实来源，仍用同一根预算；这不代替真人采用或提供 D 的真实任务来源。

私有 `Catalog` 仅允许 `plan` / `input` 加 opaque ID，目录/文件校验所有者、私有模式、单链接与 O_NOFOLLOW。完整记录先写入临时目录并 fsync，再将非空目录原子发布；同一 ID 不覆盖。读取前后核目录与文件身份，运行期间仅核 inode/ctime/mtime 等身份，避免每次监管轮询重读大型完整输入。

`Broker.dispatch(plan_id,input_id)` 不接受命令、UID、mount、环境、端点、模型或预算参数。精确计划字段固定输入摘要、根合同、request ID、phase、策略和 broker 代码摘要，之后使用原 `Adapter.dispatch`。额外 `registered_plan` 原锚使用原 `rsi_prepare_events` 的根级事件，不新增表，不干扰 attempt 的原状态序列。相同 HTTP prompt 但不同来源/计划也不能把旧回执改标为新输入；已有 attempt 缺原登记锚时拒绝补写。

生成/judge/probe/retry/B/C/D 使用原 phase、原 pool、原绝对期限和唯一 intent。根预算不因计划/输入 ID 增加而刷新；B/C 仍需原一次性消费。没有第二套 token/费用账本，没有自动重试或模型工具执行。记录/代码运行中变化会取消原受监管请求，unknown 保留原最大预留与根阻塞。

本增量只接受原 registry 显式开启的合成回环 fixture profile。即使一个 profile 声称 live，也在预留或登记原锚前拒绝。没有开放实际付费、实际模型、生产人工确认、知识采用或关单通道。

## 完整输入与生产等价边界

这一步复用了真实 production factory 和 `lesson_input`，不是 `_assemble_lesson_answer` 的缩小问答模板。实际 native request 字节/参数/响应仍由原 provider 的 `request.bin`、原 profile 和完整监管回执保存，并由原 pool/request 与登记锚关联。

但原生 Messages 的 `tools=[]`、fresh session 与真实 Claude/Cursor 的内置工具、CLI 隐式会话、设置/参数默认值仍不同。工厂前后来源快照不是一次未来执行的重新授权，也不证明其他进程期间未改所有来源；捕获与后续派发必须继续经过未来的实际 runtime 身份和当前性闸门。本增量不保存密钥或任意 CLI 配置，不用不完整信息声称等价。`production_equivalent=false` 与差异清单不可由对比函数升级。

当前 HTTP 的 chunked 依赖标准库，独立扩展负控发现 signed chunk-size 仍会被接受，原红灯保留。这不是完整 RFC 解析器；在真实 profile 接入前必须限定可验证的框定策略，对不能验证的格式原件保留、unknown/最大预留，不使用合成验证给 M/C/P 加分。

## 下一实际执行增量（尚未实现）

固定 launcher 只能消费已登记 ID 和已绑定的原 provider intent/完整输入输出回执，不能接任意 root 命令/挂载源/UID/环境。它需要实际区分 controller、候选和独立 oracle evaluator 的身份及可见资产，沿已审原监管器/隔离原语串接唯一执行意图、取消/超时/未知和完整回收。原 canary 与共享 nobody 不构成生产实现。先在临时隔离合成环境审查具体代码和正负控；专用持久账号和生产入口另经固定实现审查。

真实 profile、可信价格、A/B/C/D、真人角色及观察周期仍 pending。它们没有被登记 ID 或合成工单代替，真实试验保持 `not_run`，评分仍为 null。
