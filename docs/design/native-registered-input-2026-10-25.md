# 原生 Token 登记与共同知识输入

本增量是私有软件接线，不新增生产 HTTP/MCP 路由、执行身份、模型配置或调用授权。旧 `Broker` 仍只接受原 v2 fixture 根；新 `TokenBroker` 显式要求 v5 Token 根和对应原生固定文本 profile，不由个人 read/content 连接获得执行权。

## 原输入与当前有效性

复用原 `capture`、`agents.build_prompt`、lesson selector/renderer 与 `lesson_context.current`。一次 capture 保存完整输入、原始 history 和生产实际最后六条窗口、知识块原文及来源。两臂使用同一原始 catalog 输入；只有 system/policy 摘要允许不同。原工厂/selector/renderer/capture 代码摘要变化不能重标旧输入；不重新按臂检索、挑选或拼写知识。

有租户上下文时，当前 manager 身份、账号 epoch、项目与原执行门均由 `tenant_policy` 核验。当前原型要求与原根共用一个权威 Store 路径。fixture 无上下文只在明确回环 fixture registry 中使用，不是 live 权限。项目、工单、引用绑定和已冻结经验的正文/授权变化会拒绝新派发，已有请求取消后仍按原最大预留处理未知结果。

锁顺序沿用 Registry → Store → lesson ledger。原生 Adapter 的内部 `dispatch_guard` 只包住当前性复核、reserve、intent；在 HTTP 子进程之前释放。这样撤回不能插在知识检查与 intent 之间，权限和知识变化也不会被整段网络持锁阻塞。已有原 SP 清理、期限、进程组及未知重放规则保持。

## input × arm 与原根

原 `registered_plan` 锚不变；追加根事件登记实际输入摘要/工单身份和 input×baseline/candidate 唯一槽。登记和原计划锚同一事务，故障回滚不留下半个槽。不同连接竞争同一槽只有一个请求可以提交；同一计划重放复用原意图，不二次 HTTP。重复或损坏的槽历史拒绝。

双臂必须来自原根预封的 input SHA/来源族，且策略由原 proposal 响应派生后核验。训练标签不能把预封输入变成 propose/judge/probe/retry 输入。generic terminal 拒绝，必须明确 baseline/candidate。没有新额度、新根或新状态迁移，仍累计原调用次数、Token 和绝对期限。计划登记可能先于预算拒绝保存，不将“零预留/HTTP”误说成“整个 DB 未变化”。

## D：已实现的只读门与尚未实现的关系

当前只允许合成 fixture 检查普通采用后的新任务使用；live D 明确拒绝。只读核验原 `learning_decisions` applied/adopt、确切 revision/content/source、原 evaluate job/result 摘要、当前采用指针；原 selector 必须真的选中并渲染这份经验，system 也必须是该原响应派生策略。D 必须来自原 followup 族及独立工单，不复用已登记任务。原根全部预封双臂须有完整且 settled 的原 transport 回执，取消/缺失结果不能冒充完成。撤回后拒绝重放。

这些检查不把“文本响应完整”升级为“业务正确”，也不把旧 evaluate 报告的 passed 升级为本原生 B/C 的合格报告。`bc_report_relation_verified=false`、`qualified_bc_report_verified=false`、`production_equivalent=false`、`rsi_qualified=false` 保持。**确切原生 B/C 语义评估报告 → 原本人决定 → 同预算根 D 的桥仍未实现，live D 不得启用。** 不向 `learning_jobs` 伪造合格结果，不代本人采用，不以合成账号机制证明真人参与。

## 验证与实际通道边界

新增反例覆盖授权 epoch 派发前零预留/零 HTTP、请求中取消及 unknown 最大持有；原知识撤回/工单变化；独立 OS 写锁探测；两 Store 连接争同臂、事务失败回滚、重放、实际选择、D 策略变更和重复历史。负控在外置进程内替换方法，要求真实 unittest 目标断言失败和真实退出码，编译/导入失败不算成功负控。最终命令、同源清单、原件和实际退出见进度文件与仓库外证据。

现有 CPA/Magpie 通道只读调查发现限额参数翻译、内部换号/刷新重发和缺失 usage 归零问题；本项目不会修改该外部网关，也不自签真实上界或试拨模型。原生 HTTPS 准备需现成固定路由/模型和真实全输入输出硬界、全部内部尝试计量事实；复用原全链 100M 根和原 19:30–00:30 窗口，预定时间不回填实际开始。实际费用未知仍未知。Windows 锁/凭据 ACL 实机、真实 Cursor/完整 CLI 会话与工具计量未证明。
