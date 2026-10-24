# 服务器供应方适配器与执行合同

这是未接入生产入口的最小软件增量。它能通过固定子进程发送一次原生 Messages 请求，绑定原始输入、实际响应声明的模型、usage、完整响应和原预算。回环假供应方验证不代表真实模型可用、实际账单已核实、任务正确、知识已采用或组织收益成立。当前真实付费调用为 0，评分仍为 null。

## 调用与授权边界

只有服务器受信程序可以构造 `Registry` / `Adapter`。没有新增 HTTP、MCP、用户可选命令、系统服务或自动调度入口；Store 启动不导入这些模块或安装准备表。现有人工确认、知识采用、业务验收、guard、MOVES 均保持。

部署应显式指定一个专用、非 root 的 broker UID，注册目录和凭据归该 UID，目录 0700、普通单链接文件 0600/0400。默认信任 UID 0 是拒绝未配置调用的保守默认值；live profile 只允许实际非 root broker 本人的私有目录，不允许靠 fixture 开关以 root 调用 live。开发夹具可以显式指定当前 UID 并仅允许 `127.0.0.1` HTTP。此参数来自受信构造函数，不是请求参数。

注册目录只读取 `<opaque-profile-id>.json` 和其中登记的 `credentials/<opaque-generation>`。采用目录 FD、O_NOFOLLOW、所有者/模式/类型核验；替换注册目录使旧 FD 失效。凭据通过原监管器的匿名 stdin 文件传给固定子进程，不放 argv、环境变量、公共摘要或命名请求文件；不读取 Mac AI 配置、其它应用配置或搜索未知密钥。供应方原始响应仍可能包含敏感信息，完整证据只保留在 broker 私有目录，不作为公开日志。

`register(profile_id, base_contract)` 只接受 profile 已批准的整个 v1 合同 SHA256（包含租户、项目、根族、候选/基线、A/B/C/D、预算和期限），不能由调用者选择更大预算或另一个项目。生成的 v2 合同再固定 profile 原字节、协议摘要及账本/适配器/transport 源码摘要；既有 v1 离线合同兼容，但不能用于派发。

## Profile 必须提供的可信信息

JSON 字段使用精确白名单。具体结构见 `Registry.load`，测试中只有合成样例，没有生产凭据或可直接启用的 live 样板。

- `schema=server-messages-adapter-v1`、`approved=true`、`mode=live`；`contract_sha256`、`protocol_sha256` 为管理员批准的固定合同与试验协议。
- `endpoint` 必须是无用户信息、query 或 fragment 的 HTTPS `/v1/messages`；`credential_ref` 是服务器登记的凭据代际。端点/模型不能从任务正文覆盖。
- `model` 必须与合同 provider/requested_model/response_model 完全相同。实际响应 model 不同则 unknown；响应字符串相同也不是供应商权重身份的独立证明。
- `price` 使用合同格式，输入和缓存单价相同，均为覆盖普通输入、所有缓存 TTL 写入/读取的**保守每 token 人民币微元上界**；输出另有正整数上界。单价须向上取整，依据为可信 `reference_sha256`。`billing_mode=token-only-upper-bound` 只适用于没有请求费/工具费等其它收费的合同；无法核实则不得配置为已批准。
- `input_cap_tokens` 必须是供应方对该固定模型可计费的完整输入硬上限，以 `input_cap_reference_sha256` 指向可信证据；不能拿字符数估算，也不额外调用未计量的 token-count API。每次预留整个上限，所以较小根预算可能直接拒绝，这不是放宽预算的理由。
- `output_cap_tokens`、`call_timeout_ms`、`max_response_bytes` 固定输出、单次时限和响应资源门；`valid_until_us` 须覆盖原根期限。`parameters_version=messages-text-standard-v1` 固定原生文本 system/messages、max_tokens、stream=false、service_tier=standard_only。不支持任意参数、工具、CLI 回退或隐式重试。

缺配置、缺可信价格/输入上限、过期、模式/所有权错误、合同不符或源码变化都拒绝。配置批准只来自服务器可信所有者，软件不能替管理员核验价表真实性。当前没有实际可信 live profile，也没有发起真实付费调用。

## 预算与证据

生成、基线、候选、judge、probe、retry、terminal、followup 全部使用原 `Ledger` 根；B/C 消费仍经原一次性消费锚。SQLite 在提交 v2 intent 前必须使用持久 journal 和 FULL 或 EXTRA synchronous；不替调用者修改数据库配置。预留与唯一意图在原 Store 写事务中，网络等待期间不持有 Store 锁。phase 不是重开预算的理由。

预留额是全输入硬上限乘输入上界，加输出上限乘输出上界；同时受累计调用、token、费用、原绝对期限限制。实际请求完整规范化字节和 profile SHA 绑定原 reserve 事件；同一 request ID 换材料拒绝。唯一 intent 的赢家才能启动固定 Python `-I` 子进程。重放不再发送，已有 intent 但缺原文件不能补写后重发。

原 profile 和 request.bin 私有保存；子进程仅发送一次 HTTP，不跟随跳转、不用环境代理、不重试。它先输出状态/完整响应头/请求摘要/源码摘要，再逐块保存所有收到的原始响应字节；没有使用有替换字符的 output.txt 做 JSON 证据。Content-Length 不完整、分块流失败、超过预声明响应资源门，都保留已收到的完整字节并失败；尚未接收的网络字节不会被冒充完整输出。

结算核对原监管身份、原输出长度/摘要、固定请求与 transport、原生响应身份/实际 model 和严格 usage。普通、缓存写入、缓存读取相加为完整输入；输出总数已含 thinking_tokens，不重复相加。标准服务层和已知零工具字段可接受，未报价的服务层/速度/工具或未知 usage 维度拒绝。全部原始响应保留。金额标记为 conservative_frozen_rate_upper_bound，供应商实际账单仍未核实。

`response_complete` 只表示一个原生文本响应以 end_turn 完成；不等于代码正确或业务任务完成。max_tokens、tool_use、非文本内容等不被执行，也不算完整文本响应。适配器没有自动采用或验收行为。

intent 后的断线、HTTP 错误/跳转、格式错误、模型或 usage 不符、超时、取消、配置/凭据/源码变化均保留最大预留和 unknown 历史，禁止退款重发。撤销后恢复相同 profile 字节，其 inode/ctime/mtime 身份变化仍会终止原运行；检查是监管轮询和最终复核，不承诺瞬时阻止已经到达供应方的请求。停止本机子进程不证明供应方没有计费。

`reconcile` 只能读取原合同、原请求和原监管回执，重新核对后以原 intent 晚结算，完全不读凭据、不发送网络。缺证据就拒绝，不能人为补造。unknown 晚结算不重新开放原根。新进程代际仍不能接管旧派发；原 SQLite/全部原锚被同权限攻击者一起重写、断电造成的存储硬件违约不在本地自摘要的独立防篡改保证内。

## 固定身份与生产隔离合同

本增量的 transport 是固定可信网络代码，不能执行任务给出的 shell 命令或模型工具。live 仅能运行在非 root 的专用 broker UID，其命令固定为解释器、`-I`、固定 transport 路径；环境只含最小 PATH/LANG/禁写 bytecode，无任务环境继承。网络与整个进程树由原 supervisor 的真实时钟、取消和 TERM/KILL 清理约束。注册目录和证据是私有通道，不开放 root 任意命令接口。

生产接入仍必须在固定代码审查后单独完成，不能把本模块或此前 nobody 探针当生产隔离完成：

1. 部署提供专用 broker UID 与不可由任务改写的代码/登记配置；controller 和 registry 的写入权限只给明确的管理员通道。该 UID 不兼任人类验收身份。
2. B/C 密封 oracle 由独立 evaluator 身份持有，broker、训练执行器、候选/Claude/Cursor 不得读取；任务只收到明确的公开输入。后续执行不可信项目代码时必须使用独立一次性 UID、只读输入和独立 mount/PID/net namespace，不能直接复用本 transport 的 broker UID。
3. 固定的隔离启动器只能接受登记的计划/输入/回执 ID，不能接受任意 root command、挂载源、UID 或环境。它应复用已验证的 namespace/原 supervisor 原语，先真实核验 oracle 拒读、无宿主进程/环境泄漏、无额外网络/权限与取消清理，再开放生产路径。
4. 真实 profile、价格证据、完整生产有效输入等价、单个候选在 B/C 反馈前冻结、全链分母和真人多周期试点都必须另行达到冻结判据。当前没有该生产启动器、专用 UID 部署或真实试点，RSI 资格 false，不能计组织收益分。

接口依据：[原生 Messages API](https://platform.claude.com/docs/en/api/messages)、[缓存 usage 计数](https://platform.claude.com/docs/en/build-with-claude/prompt-caching#tracking-cache-performance)、官方 Python SDK 的 [Usage](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/usage.py)、[固定服务层参数](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/message_create_params.py)、[输出包含思考 token](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/output_tokens_details.py)。核对日期 2026-10-25；本次读取原文保存在仓库外证据目录，不复制成项目代码。


平台边界：此版本复用POSIX进程监管器及私有目录FD。新增HTTP/FD清理测试仅在POSIX执行，非POSIX明确skip，不将Windows声明为支持；Windows原生隔离/凭据ACL/监管执行仍是后续阻塞。Mac与Linux原有断言、真实网络期限和清理覆盖保持。
