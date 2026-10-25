# 固定文本Token Adapter与原响应派生

起点d8c632d；本增量仅scripts/tests/docs，不增加生产路由、个人连接执行权或Store自动迁移。复用原Ledger、私有Registry与SP。旧v2 Messages协议保留，旧fixture Broker新增明确v2限定，不因Adapter扩展间接接受新协议；新Token登记入口与B/C/D共同输入接线是后续独立增量。

## 显式协议与计量

新profile为`server-fixed-text-token-adapter-v2`，无price，billing_mode为`tokens-inclusive-v1`。只支持显式messages/responses和各自固定路径、参数版本、协议摘要，不自动探测、回退、重定向、代理、重试或执行模型工具。Adapter注册时从未创建的Token基合同冻结v5 provider原根；不能把已创建v4/v3或旧金额根升级、换名重领授权。

Messages请求保留完整system/messages，固定非流、无工具和关闭thinking；计量要求普通输入、缓存写入、缓存读取、输出四项均为有效非负整数，所有输入相加。Responses使用instructions/input、固定max_output_tokens，关闭存储、后台、流、工具和并行工具，禁止自动裁剪、不带恢复ID；输入/输出使用包含子项的父计数，总数须与父项相加相等。缓存读、可选缓存写和reasoning子项均不得超过各自父项，不重复相加。缺计量、布尔值、负值、矛盾数或未知维度拒绝结算，保留最大预留并封根。

上述口径依据2026-10-25只读获取的[OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses/create)及[Anthropic Messages API](https://platform.claude.com/docs/en/api/messages/create)。这两份官方文档说明协议含义，**不证明当前第三方代理遵守协议或实际Token上界**。

## Token上界的信任边界

新profile必须引用额外owner-only bounds原件。其摘要、模型、协议、完整输入/输出上界、有效期及mode须匹配；要求可信部署明确核实包含全部输入/输出、没有隐藏重试、usage覆盖全部Token。声明缺失、未核实或fixture证明借用为live时拒绝。原件与请求/profile一起封存，请求期间原件身份变化触发取消和原unknown占用。

**这些字段是可信部署准入声明，不会自行证明供应方保障。** 本工具不生成或批准实际供应方的上界；本次只创建明确标为fixture的合成声明。必须另外核实实际模型、代理内部调用/重试和完整usage，再由可信部署提供有证据的原件。手填cap、网页参数说明、模型自报或HTTP200均不足。未闭合时不发真实调用；本轮不再要求人民币价表，金额仍unknown。

同一权威根覆盖A、两臂、终测、judge/probe/retry和followup。原call/Token/期限与唯一intent保持；跨端或模型不另开100M根，当前只允许一个冻结模型/profile。用量未知、取消、超时不释放意图后的最大占用，历史重放不重新HTTP。5h固定窗口由原根控制，预定19:30不等于实际启动。

## 从原始响应到候选

`Adapter.bind_candidate(key, request)`不接受调用方策略文本。它核对原根/提案、原profile/上界、SP nonce/owner/完整清理、原始输出字节、HTTP框定/请求摘要/协议/源码及归一化用量；仅从唯一完整文本块取得策略，保留首尾空白、CRLF和完整Unicode。Responses允许另有reasoning元数据，但不提取它作为策略；工具输出、多条消息、多个文本块、未完成或空策略不能绑定。已花用量仍保留。

之后调用原Ledger原子绑定完整候选与预封集合，原合同/hash/预算不变。每次后续非提案调用重新核原响应与候选一致性；baseline/candidate分别校验system与冻结策略摘要。调用方直接写Ledger声明不能通过Adapter派生复核。原输出损坏时拒绝，不补造或借另一任务原件。

Adapter返回的`candidate_derivation_verified=true`只说明这次从原监管响应全文重新得到同一策略；Ledger本身仍只证明声明绑定，保持false。它不证明策略有效、模型权重身份、CLI/IDE等价、独立终测、人工采用或组织收益，rsi_qualified始终false。新D的本人采用与实际选中证据尚未接完，不能用这个标记替代。

## 验证与旧证据

新增真实回环两协议、完整正文/鉴权、候选派生/伪造拒绝、包含计量、累计预算、重复意图、原件篡改、上界变化取消及原生超时测试。原38个provider测试方法AST不变；只在其夹具增加路径/Bearer观察。监管及HTTP原期限、guard/验收/锁与人工决定不改。

原负控证据误标见`audit/negative-control-erratum-2026-10-25.md`。本批也保留了被另一道不可变门掩盖的初版负控、过严子用例ID解析器失败；最终汇总须核实际退出、tests/failures/errors和准确目标/子用例，不只看exit1。具体双端结果、原件核验、稳定性和有效负控记在进度中；旧199或旧全量只属于各自原始修订，不挪作最终新源通过。
