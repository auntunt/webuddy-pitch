# SI-008：整次运行时限、进程回收与保留现场续跑

轮次日期：2026-10-18。实现基线 `6a10865f3c0fa2e32107f2ed16fb655600cbde3f`，分支 `codex/self-evolution-resume`。本文记录本轮运行时修复；最终验证和提交索引见下文及 STATUS.md。

## 已实现的用户路径

本轮打通“执行超时或取消 → 看见真实停止原因与回收证据 → 保留已有代码 → 创建新运行继续 → 查看新结果”的本地路径。运行页面区分停止请求、回收中、已回收和无法确认回收；失败或取消不能变成可采纳的成功结果。重新运行使用独立 Git 快照和新预算，原运行、原工作树及原始输出继续保留。

这些结果来自 **SYNTHETIC 技术夹具、真实本地子进程、真实 Git 工作树和浏览器操作**。确定性检查器代替模型，只用于复现进程与恢复行为。本轮测试数、退出码及浏览器中的“完成”不代表真实模型修对率、客户认可、生产部署或客户签收。BOOTV2 真实需求的续做另行记录，不混入本文的通过数或结论。

## 失败复现、修复与证据

| 已确认问题 | 本轮处理 | 可核查证据 |
| --- | --- | --- |
| 只 kill 包装父进程；子孙继承 stdout 后，逐行读取仍一直等待。包装父以 0 退出也可能留下活进程。 | 新增 `process_control.run_process`：独立 POSIX session/process group，非阻塞 stdin/stdout；超时或取消向受管组发 TERM，再按宽限期发 KILL；父退出但组或管道未结束不能判成功。 | 旧代码最小复现配置 1 秒预算，2.5 秒外层 watchdog 仍发现阻塞；[原始红灯日志](evidence/runtime-2026-10-18/lifecycle-before-wrapper-pipe.log)。进程测试包含三层子孙、忽略 TERM、无换行、堵塞 stdin、持续输出、EOF 后仍存活及父进程先退出。 |
| 每次 invoke/retry 都重新获得完整超时时间；FixLoop 曾用“任一调用成功”把后续超时掩盖成整体完成。 | Runner 以单调时钟保存整次 run 的预算；多次模型调用、繁忙退避和本地构建检查共享剩余时间。停止原因及失败调用覆盖早先成功，不启动后续模型，不自动采纳或扣成功点数。 | [13 项运行生命周期回归](evidence/runtime-2026-10-18/lifecycle-after-integration-rerun.log)，另有 [最新 13 项复跑](evidence/runtime-2026-10-18/lifecycle-latest.log)。包含“fix 已改代码，diagnose 超时”的真实进程路径，确认失败、工作树和 diff 保留、采纳被拒绝。 |
| 取消与结束写回之间存在竞态：已接受取消后仍可能写成 done；工作树准备期间取消后也可能继续启动。 | 同一 Runner 锁保护取消与终态提交；准备结束再检查停止状态。已经接受的取消保持 cancelled，终态已提交后才来的取消返回冲突。 | [独立复核 9 项回归](evidence/runtime-2026-10-18/independent-review-regressions.log)，使用线程屏障真实交错两条路径。 |
| 输出回调或落盘异常可能漏回收、留下“仍活跃”的进程登记，或只保留截断尾部。 | 回调异常先回收所属进程组，再携带过程结果抛出；`finally` 清理运行登记。原始字节与可读文本分别保存，一份保存失败仍尝试另一份，并记下落盘错误。每次尝试的提示、输出、时序独立保存。 | `test_process_control.py`、`test_runtime_review.py` 及 `test_run_lifecycle.py`；覆盖无损原始字节、跨块 UTF-8、160 行输出与无换行尾部、三次 busy 重试各自证据、二进制或文本单份保存失败。 |
| 恢复若直接沿用主干会丢失失败运行的改动；双击或恢复回执保存失败可能重复启动。 | 使用临时 Git index 生成未验证快照，包含受 Git 管理的修改、删除、重命名和未忽略的未跟踪文件；不改变原 index、分支或工作目录。新运行持久化 `retry_of`，数据库唯一约束阻止多个 Runner 创建重复后继；补充回执写失败仍能找到唯一已创建后继。 | [7 项真实 Git 恢复回归](evidence/runtime-2026-10-18/recovery-final.log)及独立复核回归。验证二进制、symlink、暂存与未暂存内容、旧日志与旧 DB 行不变；旧 lifecycle 只增加后继关联，既有时长不重新计算。 |
| 不完整清理记录、关闭工单、交付阶段或已有活跃任务可能绕过恢复条件。 | `retry_state` 与执行端共用约束；有 pid 的尝试必须明确 `cleanup.complete == true`，损坏回执和缺少回执的已启动旧运行不能推断安全。交付阶段引导回阶段页重新执行；不存在、未受管或不属于本项目的工作树不回退到主干。 | `test_run_recovery.py`、`test_run_recovery_ui.py`；实际测试并发点击仅产生一个新运行、另一任务存在时阻断、closed/delivery/损坏嵌套回执均阻断。 |
| intake 和 learn 直接 invoke，原来不经过 `_go`；异常时或“取消已写 ended 后再抛异常”时可能没有完成 lifecycle。 | 新增 `finish_invocation`，在正常返回和异常路径统一收尾。退出 0 后才发现预算到期或取消，不能再判 done；取消后异常也封存生命周期。已完成调用不会仅因时间后来流逝改判超时。 | [12 项直接调用回归](evidence/runtime-2026-10-18/direct-invocation-final.log)。同时覆盖真实 reader 输出回调失败、原始输出保留、`cleanup.complete` 和临时目录回收。最初两个异常路径缺口由源码独立复核指出，测试运行前已完成修复，因此不伪造对应旧版本红灯日志。 |
| 人工提交审查同样直接 invoke；构建/审查异常可能缺生命周期上下文，甚至把失败审查打印的 pass 当作可采用结论。 | handwork 在检查入口建立同一预算，原始基线与候选构建、模型审查共用它；失败调用不能用输出中的 pass 越过执行状态；最终收尾后只有正常完成才产生采用事件和转交验收。 | [人工路径 6 项回归](evidence/runtime-2026-10-18/handwork-lifecycle-regression.log)：5 项新增行为测试，加 1 项既有平台完整人工提交流程。包含构建超时、构建中取消、检查耗时挤占审查预算、非零退出却打印 pass、正常完成后采用。 |
| 首次 lifecycle 写盘等准备工作已耗尽预算时，`_go` 直接 return；finally 虽标记 finished，数据库却仍 queued。提前取消也可能没有退出码和后续通知。 | 早停分支调用统一 finalizer，先写 failed/124 或保留 cancelled/125，再追加停止说明、生成事件并调用一次需要接收失败的回调。finally 仅封存尚未 finished 的记录，回调耗时不改写既有结束时间。 | [4 项行为红灯](evidence/runtime-2026-10-18/early-stop-behavior-red.log)真实读到 queued 或空退出码；[4 项绿灯](evidence/runtime-2026-10-18/early-stop-green.log)验证终态、可恢复、零尝试、事件、回调一次及封存不变。与既有竞态/落盘测试的 [13 项回归](evidence/runtime-2026-10-18/early-stop-review-regressions.log)通过。 |

执行器保存 `runs/<id>/lifecycle.json`，包含预算、耗时、停止原因、是否结束及尝试清单；每个 `attempts/<序号>/` 保留 `process.json`、`output.bin`、`output.txt`，模型调用另保留提示和时序等资料。`cleanup` 区分信号发送、进程组是否仍存在、输出是否读完、父进程是否回收及总体是否完成。不能仅凭发出了信号或父进程退出声称整次回收成功。

## 浏览器实操与实际数据

隔离数据目录为 `data/runtime-verification`，页面明确标记 SYNTHETIC。浏览器最终实操对象是工单 `RUNTIME-2`；夹具脚本中的首个 `RUNTIME-1` 以及其运行 #1/#2 是前次操作记录，均原样保留，没有当作另一项真实业务成果。

| 对象 | 从实际导出读取的状态 |
| --- | --- |
| 原运行 #3 | `failed`，退出码 `124`，`stopped_reason=timeout`，预算 2 秒，记录耗时 **2.359 秒**；TERM/KILL 均有记录，`remaining_group=false`、`output_complete=true`、`reaped=true`、`complete=true`。 |
| 原运行现场 | `app.py` 为 `VALUE = 1`，未跟踪的 `retained-note.txt` 存在；旧工作树未删除。 |
| 页面重新运行所得 #4 | `done`，退出码 `0`，记录耗时 **0.21 秒**，`retry_of=3`；真实检查器先断言读到 `VALUE = 1` 与保留文件，再写 `VALUE = 2`。新旧运行均没有采纳决定。 |
| 页面状态 | 自动刷新为两次运行，新结果和“审阅改动”指向 #4；输入中的评论草稿仍保留。旧 #3 的停止证据仍能打开。 |

主任务已通过浏览器执行上述路径。文档整理时再次读取了导出的 `runs.json`、两份 `lifecycle.json`、`retained-worktrees.json`，并打开[最终浏览器截图](evidence/runtime-2026-10-18/runtime-recovery-final.jpg)核对显示内容；[超时恢复入口截图](evidence/runtime-2026-10-18/timeout-recovery-entry.jpg)也保留在证据目录。原始图片文件未在本次整理中改写或重编码。

完整技术夹具证据位于 [fixture/](evidence/runtime-2026-10-18/fixture/)，包含项目、工单、运行、事件 JSON，以及每次运行的原始输出、生命周期、恢复快照说明和补丁。夹具中保留的工作树内容导出与实际进程存活检查显示最后一个受管子进程已退出。页面仍写明没有运行构建测试、诊断无结论；这份夹具的“done”只证明受控恢复执行完成，未替用户采纳、验收或发布。

## 已完成的针对性验证

下表中的测试组有重叠，不能相加后声称独立覆盖量；跳过与警告也不计为通过。

| 验证记录 | 结果 |
| --- | --- |
| [runtime-core.log](evidence/runtime-2026-10-18/runtime-core.log) | 45 项通过，19.312 秒；覆盖进程控制、运行预算及相关执行器回归。 |
| [lifecycle-after-integration-rerun.log](evidence/runtime-2026-10-18/lifecycle-after-integration-rerun.log) | 13 项通过，8.859 秒。 |
| [lifecycle-ready-fixtures-final.log](evidence/runtime-2026-10-18/lifecycle-ready-fixtures-final.log) | 13 项通过，22.389 秒，退出码 0；增加真实就绪握手并移除 Python 冷启动对极短预算的干扰，确认目标场景已建立后等待原有整次预算自然到期。 |
| [recovery-final.log](evidence/runtime-2026-10-18/recovery-final.log) | 7 项通过，4.177 秒；真实 Git 和本地检查器，未 mock `start`。 |
| [recovery-finalization-wait.log](evidence/runtime-2026-10-18/recovery-finalization-wait.log) | 7 项通过，3.716 秒，退出码 0；修复夹具等待收尾落盘的竞态后再次执行，产品恢复门槛保持不变。 |
| [independent-review-regressions.log](evidence/runtime-2026-10-18/independent-review-regressions.log) | 9 项通过，2.444 秒；取消竞态、落盘错误、独立 Runner 的持久化幂等。 |
| [direct-invocation-final.log](evidence/runtime-2026-10-18/direct-invocation-final.log) | 12 项通过，3.713 秒；intake/learn 直接调用收尾。 |
| [handwork-lifecycle-regression.log](evidence/runtime-2026-10-18/handwork-lifecycle-regression.log) | 6 项通过，9.392 秒；含既有平台人工提交回归。 |
| [early-stop-green.log](evidence/runtime-2026-10-18/early-stop-green.log) | 4 项通过，0.342 秒；真实 Store 和回执文件，延迟首次落盘复现执行前耗尽预算，不运行模型或子进程。 |
| [early-stop-review-regressions.log](evidence/runtime-2026-10-18/early-stop-review-regressions.log) | 13 项通过，4.113 秒；上述 4 项与既有取消竞态、持久化恢复和落盘失败回归合跑，有重叠。 |
| `test_run_recovery_ui.py` | 15 项 API/JavaScript 行为回归：完整回执、转义与不截断、取消后持续轮询、双击与迟到响应、重试失败、交付限制。首轮完整回归中该组通过；该轮全套本身仍失败，不能据此称最终全量通过。 |

第二轮完整回归 [unittest-final.log](evidence/runtime-2026-10-18/unittest-final.log) 为 **446 项，3 失败、2 跳过，152.602 秒**。其中两处恢复夹具在最终回执落盘前检查恢复条件，另一处持续输出夹具在极短预算内没有首个输出。第三轮 [unittest-verified.log](evidence/runtime-2026-10-18/unittest-verified.log) 为 **446 项，1 失败、2 跳过，162.287 秒**；唯一失败是进程树夹具尚未证明已启动，就用 0.6 秒总预算检查三个启动标记。两轮失败原文均保留，处理见下节。

其后的 [unittest-complete.log](evidence/runtime-2026-10-18/unittest-complete.log) 已记录 **448 项，0 失败、0 错误、2 跳过，171.933 秒**；该版不包含随后发现的执行前早停缺口及新增 4 项回归，因此不代表最新源码已获全量确认。早停修复后的 [最终完整回归](evidence/runtime-2026-10-18/unittest-final-452.log) 已实际结束：**452 项，450 通过、0 失败、0 错误、2 跳过，171.109 秒，退出码 0**。跳过为可选依赖测试；原日志中的资源警告继续保留。最终前端脚本 `node --check` 退出码 0，源码与说明文档的 `git diff --cached --check` 通过。原始提示、终端输出及补丁内原有的行末空白原样保留，因此整目录含证据的空白检查会报告这些原始字节，不清洗日志以取得形式上的通过。

## 保留的失败记录与处理

- 旧代码 wrapper/管道卡住的真实失败保存在 `lifecycle-before-wrapper-pipe.log`。`lifecycle-integration-first.log` 的 32 项初次集成有 1 项失败：测试的普通 `Mock` 自动生成了 truthy `.always`，误当成“失败也通知”的回调；已显式设定回调属性，保持“成功回调不可被调用”的业务断言。
- `lifecycle-after-integration.log` 有一次 2.5 秒外层 watchdog 失败，随后该单项 1.239 秒通过，13 项复跑通过。旧失败未删除；失败断言已增加工作线程堆栈。该次旧日志没有堆栈，不能断言原因就是机器负载，也不把它与初始已确认的管道缺陷混为一谈。
- `recovery-first.log` 的两处子用例失败在额外提示断言：FixLoop 给实际模型提示插入当轮“不跑测试”说明，旧全文因此不是连续子串。新运行存储的 prompt 仍完整保存旧原文，模型提示仍含原始需求；改为分别验证这两项，未删去源码、日志或原始需求。
- `unittest-integration.log` 的首轮完整回归为 **420 项，2 失败、3 错误、2 跳过，153.501 秒**。三个错误来自旧测试夹具没有真实 Runner 接口，已补为实际 Runner；另外两项涉及人工审查结论及缺失执行器的错误提示，已修复。人工路径已单独复测通过，后续完整回归仍保留新的失败记录。现有 HTTPError/socket/SQLite `ResourceWarning` 保留在原日志中，没有过滤成“零警告”。
- `unittest-final.log` 的第二轮完整回归有三处失败。两处在 `test_run_recovery.old_run`：测试看到内存 `finished` 就继续，而 `_go` 尚可能持锁写入最终 `lifecycle.json`。恢复接口以落盘回执为准，仍阻断是正确行为。夹具现持同一锁等待终态、内存及落盘的 `finished`、本次进程登记已清除；超时和恢复失败附运行、完整生命周期及阻断原因。未放宽清理证明或恢复规则；[7 项修正后复测](evidence/runtime-2026-10-18/recovery-finalization-wait.log)通过。
- 第二轮另一失败为持续输出测试的 `output_bytes` 长度为 0。该日志只证明 0.2 秒内未得到首个输出，不能从中证明管道排空饿死了时限检查。夹具改用 `/bin/sh` 内置循环并给予 1 秒启动及输出时间，同时要求多次输出回调、累计字节完整、总体耗时小于 1.5 秒、超时原因及回收均正确；[进程控制复测](evidence/runtime-2026-10-18/process-control-final.log)保留结果。此调整未改产品预算语义。
- 第三轮唯一失败的输出只有停止说明，连 `fixture-start:tree` 都不存在；旧用例没有先证明 Python 父、子、孙三代均启动。极短预算先被启动准备消耗是可能原因，旧日志不足以定位具体耗时步骤，不能把它算作“已启动进程树回收失败”。夹具现于忽略 TERM 并写出启动日志后，为每级写独立 ready 文件；测试确认三代就绪且真实 PID 存活，再等待同一次运行自然超时。夹具预算为 3 秒，包含启动时间，**没有在就绪后重置时钟**；5.5 秒外层 watchdog 限制回收与落盘。非零退出、timeout、三条完整日志及零存活子孙断言保留，另明确断言 TERM、KILL 与 `cleanup.complete`。
- 同组一并修正了其他启动前提：长日志须先写完 160 行和无换行尾部，fix 后超时须已进入诊断，构建树与独立组保护场景须已建立三代树；取消也等待信号处理已设置。跨 invoke 与 429/重试证据使用真实原生 shell，仍断言首调用成功、第二调用超时、第三调用不启动，以及共享总预算和每次独立证据。产品执行器、时限和清理规则均未修改。[最终 13 项复测](evidence/runtime-2026-10-18/lifecycle-ready-fixtures-final.log)通过。
- 这次夹具调整的中间失败也保留：[lifecycle-ready-tree.log](evidence/runtime-2026-10-18/lifecycle-ready-tree.log) 的 13 项有 1 失败，因为最初以运行中 DB 输出作为就绪信号，而短日志由 Runner 批量缓冲到结束才刷新；改为上述独立 ready 文件。[lifecycle-ready-tree-final.log](evidence/runtime-2026-10-18/lifecycle-ready-tree-final.log) 的目标树已通过，但 0.3 秒 busy 夹具尚未写出 PID 文件，13 项中有 1 错误；改用原生 shell 发真实 429，并保留仅一次启动及总预算退避断言。之后中间版 [lifecycle-stable-fixtures.log](evidence/runtime-2026-10-18/lifecycle-stable-fixtures.log) 13 项通过（11.735 秒）；最终包含其余就绪前提的版本为上面的 22.389 秒记录，不能重复相加。
- 448 项整体验证后，独立复核发现执行前早停只封存回执而未写数据库终态。测试给 0.03 秒预算，将首次生命周期保存延迟 0.06 秒，实际重现 queued 与 finished 并存；预先取消的分支则缺少退出码。最早 [early-stop-red.log](evidence/runtime-2026-10-18/early-stop-red.log) 使用 finalizer 调用次数断言；随后换成数据库状态、回执及事件的业务断言，保留 [early-stop-behavior-red.log](evidence/runtime-2026-10-18/early-stop-behavior-red.log)：4 个测试、5 个失败（包含两个取消/超时子用例）。修复后 4 项通过。再次只读复核确认：早停与取消由同一 Runner 锁中的 finalizer 写终态，未启动 `_execute_run`；普通成功回调与计费不触发，always 回调拿到已封存回执且只调用一次；回调抛异常只记到输出，不能替换原停止原因；finally 不再重复封存，已结束的耗时与时间戳保持不变。此结论限于所读早停路径及对应回归，最新全量仍以主任务实际完成结果为准。

## 适用范围与未完成边界

1. 进程清理限定为 **POSIX** 上本次新建 session 的受管 process group；不会按模型名称或监听端口查杀，也不会清理其他任务的组。子进程故意调用 `setsid()` 逃逸后不在此权限范围内。若它继续持有输出管道，当前实现报告 `cleanup_failed`，不跨组追杀；已有真实测试验证这一点。逃逸进程同时关闭管道的情形也不能据此声明被发现或回收。
2. `on_output`、`on_spawn` 等回调同步执行，必须及时返回。预算不是任意 Python 回调、文件 I/O 或同步 Git 操作的硬抢占机制。达到预算后还有信号宽限、排空管道和证据落盘时间，因此浏览器示例的 2 秒预算对应 2.359 秒结束，不是 2 秒整强制消失。
3. 本轮预算与取消保证已覆盖本地模型命令、本地构建及上述直接调用路径。**远程 TestBox 分支的 SSH/远端子进程整组回收未覆盖**；其既有功能测试不等于远端取消或总预算已打通。
4. **server 被强杀或重启后的 orphan reaper 尚未实现。** 现有 `Runner.recover()` 会把遗留 queued/running 记录改为 failed，但不会据此证明旧进程已回收。缺少充分清理证据时恢复入口保持阻断。
5. 恢复快照保留 Git 可表示的当前改动；被 `.gitignore` 忽略的数据、外部数据库、进程内存及外部副作用不随该快照恢复。新快照明确标注未验证，不等于采纳、合并或签收。交付阶段仍必须从原阶段按当前版本与复核门槛重新执行。

复跑新增本地行为测试：

```sh
python3 -m unittest tests.test_process_control tests.test_run_lifecycle tests.test_run_recovery tests.test_runtime_review tests.test_run_recovery_ui tests.test_direct_invocation_lifecycle tests.test_handwork_lifecycle tests.test_run_early_stop -v
```

完整回归命令为 `NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost python3 -m unittest discover -s tests -v`。浏览器夹具创建脚本 [setup_browser_fixture.py](evidence/runtime-2026-10-18/setup_browser_fixture.py)会拒绝覆盖已存在的 `data/runtime-verification`；不要直接删掉既有夹具以复跑。本文不记录生产接入、真实模型调用或客户签收成果。

## 最终接续结果

真实 BOOTV2 的沟通、方案、修改、实际构建测试、独立验证和固定提交预览已完成，见 [业务验收记录](verification-bootv2-2026-10-19.md)。浏览器发现的旧采纳记录遮盖新运行已修复：最新未采纳 fix 优先审阅，已采纳分支仅从当前 fix 决定读取；两项新增 JS 行为回归先红后绿，33 项相关 UI 回归通过。实际 #6 采纳后浏览器已核对首屏指向 `8be50de` 和 `tmh/BOOTV2-1-r6`。

8791 在无活动运行时重启到最终源代码，固定版本预览再次确认 `matches_run=true`、状态 up；合成夹具服务 8797/8798 已停止，数据和全部证据保留。未操作 8792。原始图片保持全分辨率原编码，数据库备份已读回，源码 bundle 已校验。没有生产发布或客户签收。
