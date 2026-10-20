# SI-001：客户答复后的再理解恢复

日期：2026-10-19。工作分支：`codex/self-evolution-resume`。本轮开始时的提交：`66c03493e0f6fd19a9e92a5decc4a05fe4d9d3a8`。实现与完整原始证据提交：`ba5dab7c225a15b3e3f79ea22c49a575736a1b4c`（`Recover saved customer answers after interpretation failures`）。仅本地、未推送；本段随后以文档提交补记。

**当前结论：已打通保存答复 → 理解超时 → 保留现场 → 重启服务 → 工程师重试 → 补全标准的本地恢复路径。** 独立复核发现的并发合同覆盖、运行操作者归因及关闭工单后误报成功已修复，并保留每次失败的回归日志。浏览器采用明确标注的合成客户和本地 reader；不是一次真实模型交付或客户签收。

## 原问题与这次改变

原路径存在一个实际死结：客户通过答复链接回答问题后，系统已保存答案并消费链接，问题也不再属于未回答问题；随后再理解超时或失败，验收标准中的 `【待确认】` 却仍然存在。工程师再次询问客户时没有可发送的问题，实施又被未确认标准阻塞，页面没有“使用已保存答复继续理解”的入口。

这次增加明确的恢复路径：工程师查看原问题、客户原答复、来源和失败运行，按保存的答复启动一次新的需求理解。原客户不必重复回答。成功仅表示原待确认标准被补全并实际落地，不能代表代码已实现、验收已通过或已经发布。

客户原话与恢复操作者是两个身份：`slots` 中的答案和 `from` 保留原客户来源；新理解运行的 `author`、恢复尝试的 `requested_by` 记录发起恢复的工程师。合同确认记录仍按原客户答复归因。旧失败运行、旧日志和历史尝试不被新运行覆盖。

## 实现约束与可观察行为

| 范围 | 实际约束与表现 | 证据 |
| --- | --- | --- |
| 恢复入口 | `POST /api/tickets/<key>/intake-retry` 委托服务端恢复函数；规范化工单编号，使用请求操作者，忽略请求体伪造的客户答案。返回明确的恢复状态与失败原因。 | [HTTP 回归](../../tests/test_intake_recovery_api.py)、[API 日志](evidence/intake-recovery-2026-10-19/api-final.log) |
| 新运行与去重 | 恢复在锁内建立新 job；同一失败记录已有恢复运行时，重复点击或并发请求返回 409，不重复生成运行。迟到结果不能替换后来建立的 job。 | [独立回归](../../tests/test_intake_recovery_independent.py)、[独立复核](evidence/intake-recovery-2026-10-19/independent-review.md) |
| 原运行结束证明 | 需要与该次失败理解绑定的运行，以及可读取、已封存的 `lifecycle.json`。有 PID 的 attempt 必须有 `cleanup.complete=true`；损坏、缺失或未完成回执不能推定安全。明确记录为未启动执行器的 job 单独处理。 | [后端回归](../../tests/test_intake_recovery.py)、[独立回归](../../tests/test_intake_recovery_independent.py) |
| 配置与业务门槛 | 工单关闭、理解仍在运行、执行器禁用或不可用、配额限制、答案或合同绑定变化等情况阻止重试。自动流转继续尊重人工接管、依赖、推迟及全局关闭状态。 | [兼容回归日志](evidence/intake-recovery-2026-10-19/backend-compatibility.log)、[独立复核](evidence/intake-recovery-2026-10-19/independent-review.md) |
| 未知答案 | “不清楚”等未知答复不能填成已确认；即使合成 reader 声称补全也继续保留待确认。再次返回占位内容时保留失败说明与适用的重试入口。 | [独立回归](../../tests/test_intake_recovery_independent.py) |
| 已确认合同保护 | 仅允许补全本次具体答案关联的原待确认标准。已确认条目的编号、文本、检查方式、层级、keep 标记以及无关内容不接受 reader 重写。 | [独立回归](../../tests/test_intake_recovery_independent.py)、[27 项合跑](evidence/intake-recovery-2026-10-19/backend-contract-green-attempt.log) |
| 并发合同修改 | 恢复开始时保存答案与完整合同绑定；结果完成前、实际写入锁内再次核对。另一人修改 `check`/`layer` 时保留新合同，旧恢复包维持阻塞，不重新绑定后重放。超时回退同样检查。 | [初次缺陷](evidence/intake-recovery-2026-10-19/independent-first.log)、[超时冲突复测](evidence/intake-recovery-2026-10-19/independent-timeout-conflict.log) |
| 只读状态查询 | `recovery_state` 直接读取保存的会话、运行及证据，不隐式 sweep。工单详情、需求列表、客户工作台的 GET 投影统一使用恢复状态；真实 HTTP 测试比较完整数据库导出与文件字节，查询前后不变，包括过期但尚保留的 job。 | [HTTP 回归](../../tests/test_intake_recovery_api.py)、[API 日志](evidence/intake-recovery-2026-10-19/api-final.log) |
| 页面状态 | 失败显示“客户答复已保存，再理解未完成，等工程师处理”；运行中显示按已保存答复补全标准；关闭工单仍按已关闭展示。工单、客户、需求视图共享 `workbench.states`。 | [HTTP 回归](../../tests/test_intake_recovery_api.py)、[UI 回归](../../tests/test_intake_recovery_ui.py) |
| 页面操作 | 展示原答复、来源、失败与尝试记录；提供重试和理解运行入口。操作防重复，异步刷新限定当前工单；保留评论和编辑草稿，成功后更新验收标准。最终浏览器截图见下表。 | [UI 定向日志](evidence/intake-recovery-2026-10-19/ui-green-final-layout.log)、下方浏览器记录 |

只读结论有明确范围：它覆盖新增的恢复状态和上述业务页 GET 投影。原 `intake.load(...)` 仍包含过期理解回退及保存逻辑，`/api/intake/<sid>` 和客户答复页面的旧路径会使用它；本轮不能宣称整个应用所有 GET 都无副作用。针对旧 `load` 的竞态，已补锁内重验 job 编号、开始时间和过期条件，避免旧读取终止后来建立的新 job。

旧数据没有完整恢复包时，只能从确实保存的具体答案、仍待确认的条目、对应的失败或取消再理解运行及安全结束回执重建。早期第一次理解的成功运行不能充当后一次失败运行的结束证明；缺乏唯一客户来源或可靠绑定时保留阻塞，交工程师核对。

## 浏览器路径：已读回的超时证据

主代理在隔离本地服务 `http://127.0.0.1:8797` 执行浏览器操作。数据目录为 `data/intake-recovery-verification-2026-10-19`，工单 `INTREC-1`，会话 `86762c2a002d`，标题含 `SYNTHETIC`。夹具使用本地 Python reader，未调用模型、未操作真实客户项目。

| 步骤 | 已证实结果 | 原始材料 |
| --- | --- | --- |
| 初始合同 | 初始会话、工单与合同在答复前已导出，供比较。 | [会话](evidence/intake-recovery-2026-10-19/fixture-initial-session.json)、[工单](evidence/intake-recovery-2026-10-19/fixture-initial-ticket.json)、[合同](evidence/intake-recovery-2026-10-19/fixture-initial-contract.json) |
| 客户真实提交 | 浏览器提交“完整保留输入；恢复后重试保存到原事项。原编号、完成状态和其他事项不变。”，来源为“合成验收客户（客户）”。原问题为“保存遇到故障时，希望保留什么，恢复后怎么操作？”。 | [答复后导出](evidence/intake-recovery-2026-10-19/browser-after-answer.json) |
| 实际超时 | 理解运行 #2，job `a84526ea`，总预算 10 秒；生命周期耗时 10.01 秒，退出码 124，停止原因为 timeout。执行器真实派生子进程并持有输出。 | [超时会话](evidence/intake-recovery-2026-10-19/browser-session-after-timeout.json)、[进程与回执](evidence/intake-recovery-2026-10-19/browser-timeout-process-groups.json) |
| 进程回收 | 组号 74129、子进程 74134；回执记 `term_sent=true`、`kill_sent=false`、`remaining_group=false`、`output_complete=true`、`reaped=true`、`complete=true`。另一次实际组查询确认 74129 已不存在。不能把这次 TERM 正常结束写成 KILL 生效。 | [进程与回执](evidence/intake-recovery-2026-10-19/browser-timeout-process-groups.json) |
| 答复与阻塞保留 | 会话保持 confirmed，原答案 q1 和来源保留；问题列表已空，A1 仍 open，A2/A3 保留已确认，`open_ac=1`。恢复状态 failed、`can_retry=true`；没有假装合同已经补全。 | [超时会话](evidence/intake-recovery-2026-10-19/browser-session-after-timeout.json)、[答复后导出](evidence/intake-recovery-2026-10-19/browser-after-answer.json) |
| 工程师看到可恢复状态 | 第一轮截图中可读到保留的原答复、失败说明、重试理解及查看运行按钮。此截图先于后续布局调整，不能作为最终布局验收图。 | [初始保留状态截图](evidence/intake-recovery-2026-10-19/browser-timeout-retained-first.jpg) |
| 客户不被要求重复答复 | 客户页面明确告知答复完整记录、再理解未完成、工程师可按保存答复重试，无需重复回答。 | [客户失败状态截图](evidence/intake-recovery-2026-10-19/browser-client-failed.jpg) |

本文整理者已读回上述 JSON，并实际打开两张截图核对可读内容；没有代替主代理重复点击浏览器，也没有重编码或缩放原始截图文件。

主代理实际完成重试并重新加载最终源码复验。重试期间未发送评论保持原样；服务重启后保存答复和失败记录仍可恢复。恢复成功后能分别打开旧失败 #2 和新成功 #3，完整正文自动更新；客户端 GET 刷新提示已记录并等待工程师安排。完成后的最终页面重载属于主动刷新，不代表未发送评论具备跨刷新持久化能力。

| 最终封存项 | 结果 |
| --- | --- |
| 新旧运行 | #2 仍为 failed，耗时 10.01 秒；#3 为 done，耗时 3.088 秒。三个运行的生命周期均 finished、cleanup.complete；实际进程组均不存在。[完整运行](evidence/intake-recovery-2026-10-19/browser-all-runs.json)、[结束检查](evidence/intake-recovery-2026-10-19/browser-final-verification.json) |
| 答复和合同 | 原问题、原答案、合成客户来源保留；A1 补全，A2/A3 的所有字段与初始合同完全相同。[最终合同](evidence/intake-recovery-2026-10-19/browser-final-contract.json)、[会话](evidence/intake-recovery-2026-10-19/browser-final-session.json) |
| 浏览器运行中与完成 | [重试中](evidence/intake-recovery-2026-10-19/browser-retry-running.jpg)、[最终完整页面](evidence/intake-recovery-2026-10-19/browser-retry-resolved-final.jpg)、[客户结果](evidence/intake-recovery-2026-10-19/browser-client-resolved-final.jpg)、[旧失败运行](evidence/intake-recovery-2026-10-19/browser-original-timeout-run.jpg)、[新成功运行](evidence/intake-recovery-2026-10-19/browser-new-successful-run.jpg)。主代理实际打开、读回截图；保留原始图片字节，无压缩或重新编码。 |
| 关闭工单竞态 | 合同绑定恢复在最终写入锁内遇到已关闭/不存在工单，返回未落地并保留阻塞，不记 resolved。[首次红灯](evidence/intake-recovery-2026-10-19/independent-closed-race-red.log)、[修复绿灯](evidence/intake-recovery-2026-10-19/backend-closed-race-green.log)、[独立最终19项](evidence/intake-recovery-2026-10-19/independent-final-closed-fix.log)、[后端最终63项](evidence/intake-recovery-2026-10-19/backend-final.log)；各组有重叠，不相加。 |
| 最终完整回归 | 490 项：488 通过、2 项可选依赖跳过；173.668 秒，退出码 0。命令：`NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost python3 -m unittest discover -s tests -v`。[最终日志](evidence/intake-recovery-2026-10-19/platform-full-local-bypass.log)。仍有既有 `ResourceWarning`，不能称无警告。 |
| 日常工作台与收尾 | 8791 已重启加载最终源码，8793 的 BOOTV2 #6 固定提交预览仍可打开，三条原数据逐字段相等。8797 隔离服务已停止，无活跃理解运行；8792 和生产未操作。[检查记录](evidence/intake-recovery-2026-10-19/final-checks.json)、[数据读回](evidence/intake-recovery-2026-10-19/normal-after-data.json)。 |

封存包含原始输出、提示词、每次 attempt、完整 SQLite 备份和会话文件：[夹具归档](evidence/intake-recovery-2026-10-19/fixture-archive/)。源码变更与摘要随实现提交保存。不要把数据库中没有的 `finished` 字段当运行终态；时间与结束状态以每次 `lifecycle.json` 的 `ended_at` / `finished` 为准。

本机代理影响了最初两次完整套件中的 HTTP 测试。`Host: evil.example` / `Host: bot.example.com` 请求原本被送往 `127.0.0.1:7897`，代理返回空 502，本地测试服务未收到请求；不是恢复代码的判断失败。仅为子进程设置 loopback 的 `NO_PROXY/no_proxy` 后，两条原测试原样通过。保留 [传输诊断](evidence/intake-recovery-2026-10-19/api-proxy-transport-diagnostic.log)、[原环境失败](evidence/intake-recovery-2026-10-19/api-proxy-original-environment.log)、[绕过后通过](evidence/intake-recovery-2026-10-19/api-proxy-local-bypass.log)。未改全局代理或原测试以隐藏失败。

## 定向测试与首次失败记录

以下各组存在重叠，不能相加为独立用例数，更不能换算为模型修对率。运行测试的进程与返回内容均为合成夹具；真实 HTTP、数据库文件及受管子进程的使用仅证明软件路径行为。

| 日志 | 实际结果 | 范围与时间边界 |
| --- | --- | --- |
| [backend-red.log](evidence/intake-recovery-2026-10-19/backend-red.log) | 9 项，13 个 error，0.183 秒 | 初始接口尚未实现；包含子测试错误，不是 13 个独立客户失败。 |
| [backend-first-green-attempt.log](evidence/intake-recovery-2026-10-19/backend-first-green-attempt.log) | 9 项，1 failure、1 error，0.259 秒 | 夹具错误读取 `ApiError.status`，实际属性为 `code`；重复请求本身已正确返回 409。 |
| [backend-green.log](evidence/intake-recovery-2026-10-19/backend-green.log) | 9 项通过，0.258 秒 | 后端会话与恢复状态定向验证；进程调用使用进程内合成替身。 |
| [api-first.log](evidence/intake-recovery-2026-10-19/api-first.log) | 6 项，3 failures，9.302 秒 | 一个关闭夹具误把 key 当 numeric id；另外两个看到 running，发生于后端同步开发期间，没有保存足以确认精确根因的失败会话。不能据此归因于 `_plan`。 |
| [api-current.log](evidence/intake-recovery-2026-10-19/api-current.log) | 6 项通过，3.863 秒 | 修正夹具、读取当时源码复跑；另存 [实际 wait=true 诊断](evidence/intake-recovery-2026-10-19/api-running-diagnostic.log)。 |
| [api-final.log](evidence/intake-recovery-2026-10-19/api-final.log) | 8 项通过，5.158 秒 | 真实临时 HTTP、SQLite、会话与受管 Python reader；包含 GET 无写入、重复请求、关闭、配置、鉴别请求头、损坏回收证明。这里的失败 reader 退出码为 7，不能冒称它是超时测试。 |
| [independent-first.log](evidence/intake-recovery-2026-10-19/independent-first.log) | 9 项，2 failures，0.924 秒 | 确认两个产品缺陷：并发修改 `check`/`layer` 被覆盖；运行 author 错记最初受理人。后续已分别补合同检查和恢复操作者归因。 |
| [backend-contract-green-attempt.log](evidence/intake-recovery-2026-10-19/backend-contract-green-attempt.log) | 27 项通过，6.575 秒 | 当时的 9 项后端、10 项独立、8 项 API 合跑；不包含后来新增的关闭竞态。 |
| [independent-final.log](evidence/intake-recovery-2026-10-19/independent-final.log) | 18 项通过，2.120 秒 | 11 项独立恢复、6 项既有人工接管、1 项旧超时落地；文件名中的 final 不代表之后未再发现缺陷。 |
| [backend-compatibility.log](evidence/intake-recovery-2026-10-19/backend-compatibility.log) | 43 项通过，17.883 秒 | 恢复及旧需求理解、直接 invoke、接管等兼容路径。日志末有未关闭 socket 的 `ResourceWarning`，不能称无警告。 |
| [independent-closed-race-red.log](evidence/intake-recovery-2026-10-19/independent-closed-race-red.log) | 1 项失败，0.132 秒 | 后续发现理解中关闭工单，跳过落地仍错误标为 resolved；修复绿灯与独立最终记录见上表。 |
| [ui-red.log](evidence/intake-recovery-2026-10-19/ui-red.log) | 12 项，4 failures，0.665 秒 | 新增恢复页面行为首次红灯，既有同步行为同时检查。 |
| [ui-first-green-attempt.log](evidence/intake-recovery-2026-10-19/ui-first-green-attempt.log) | 12 项，1 failure，0.549 秒 | JS 夹具预期一次 POST、实际未发生；作为中间失败保留，不以最终通过抹去。 |
| [ui-green-final-layout.log](evidence/intake-recovery-2026-10-19/ui-green-final-layout.log) | 15 项通过，0.709 秒 | 7 项恢复 UI 与 8 项既有运行同步行为；之后页面仍有历史展示调整，最终完整套件及浏览器已覆盖该调整。 |
| [integration-first.log](evidence/intake-recovery-2026-10-19/integration-first.log) | 52 项通过，9.628 秒 | 较早集成结果，早于后续独立合同修复，不是最终完整回归。 |

本轮相关回归文件：[后端恢复](../../tests/test_intake_recovery.py)、[HTTP 与状态投影](../../tests/test_intake_recovery_api.py)、[独立合同与竞态](../../tests/test_intake_recovery_independent.py)、[恢复 UI](../../tests/test_intake_recovery_ui.py)、[工单运行同步](../../tests/test_ui_ticket_run_sync.py)。独立复核者的结论及受检源码哈希见 [独立记录](evidence/intake-recovery-2026-10-19/independent-review.md) 与 [最终源码快照信息](evidence/intake-recovery-2026-10-19/independent-sources-final.json)；它们也有各自的验证时点，不能覆盖后来变更。

## 适用边界

- 本轮证明的是客户答复已经保存后，失败再理解可以安全、可追溯地继续；使用的客户、问题和 reader 均明确标记为合成。没有测量真实模型理解质量，也没有真实客户签收。
- 补全验收标准不等于业务实现。本轮未因此生成实现证据、部署凭据或签收决定；仍需后续代码、独立验证、预览与验收。
- “不清楚”、已确认合同发生变化、工单关闭、执行器不可用或缺少运行结束证明时继续阻塞，不能计为恢复成功。
- 子进程清理依赖已有运行时边界：POSIX 受管进程组内的清理不等于任意逃逸进程回收；`setsid` 逃逸、服务被强杀或重启后的 reaper、远程 TestBox 等没有在本轮新增保障。参见 [运行时验证记录](verification-runtime-2026-10-18.md)。
- 本轮未访问生产主机，未部署，也未恢复此前暂停的自动任务。用于 API 回归的服务绑定临时 loopback 端口并在测试清理；浏览器专用 8797 验证服务已停止，完整数据保留。


源码与原始证据摘要：[tested-sources.json](evidence/intake-recovery-2026-10-19/tested-sources.json)、[完整源码快照](evidence/intake-recovery-2026-10-19/source-snapshot/)、[SHA256SUMS](evidence/intake-recovery-2026-10-19/SHA256SUMS)。初次全量 489 项及最终源码未绕代理的 490 项各有相同两处环境失败，均原样保留；绕过后最终源码 490 项无失败。
