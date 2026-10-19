# Ralph port 执行进度

- 当前项：feat/ralph-port 最终审查；状态：done（最终全量 819 tests，804 通过、15 跳过；既有工作均保留）
- 仓库：`tob-maintenance-harness`；分支：`feat/ralph-port`
- 起点：`422d9bf`（原分支 `codex/self-evolution-resume`）。
- 只读规格：`/Users/auntlee/Downloads/ralph-learn-pack/codex-prompts.md`，不复制进仓库。
- 恢复顺序：先读本文件和 `git log --oneline -10`，从第一个非 done 项继续；已经 skipped 的项保留原因，不重复执行。
- 初始工作区有 6 个修改文件、1 个未跟踪测试；已执行 `git stash push -u -m 'ralph-port-preflight-2026-10-19'`，保存为 `stash@{0}: On codex/self-evolution-resume: ralph-port-preflight-2026-10-19`。交接时保留 stash，不自动恢复。
- 初次在父目录执行 `git status --short --branch` 报非 Git 仓库；定位子目录后重新执行成功，再 stash、新建分支；未改 Git 配置。
- 不变量：离线；不碰 data/、密钥、证书；不启动日常 8791/8793 服务；不 push；不削弱人确认、证据绑定、钩子、保护清单、状态迁移或基线断言。
- 执行：逐项仅跑指定测试；每项最多 3 轮失败修复，仍失败则撤销该项未提交实现并记 skipped；最终才跑全量。

| 项目 | 状态 | 提交 | 说明 |
|---|---|---|---|
| P1 | done | `407d196` | AGENTS 区块预算与命令路由 |
| P2 | done | `eac0e2f` | 非阻塞任务尺寸提示 |
| P3 | done | `d761bb6` | 经验卡固定开销 lint |
| P4 | done | `ff532c8` | 已知死路及来源验证 |
| P5 | done | `c594ee5` | 结构反馈草稿与人确认 |
| P6 | done | `a06c09e` | 可替换文件锁与 Windows 阻塞盘点 |

## P1

- 状态：done。
- 阅读范围：`tmh/install.py`、两个模板、`tests/test_tmh.py`。
- 计划改动：`templates/AGENTS.block.md`、`docs/agent-commands.md`、`tests/test_tmh.py`；如安装后命令指引需要随工具分发，在 `tmh/install.py` 补对应复制。
- 命令/结果：`git status --short --branch` 确认旧改动；stash 成功；`git switch -c feat/ralph-port` 成功；工作区干净。
- 差异/假设：规格“单会话只做一项”由本次用户连续完成六项的指令覆盖；不请求暂停确认。
- 待确认：无。
- 实际改动：`templates/AGENTS.block.md` 从 7832 降至 2975 字节（≤3584）；新增 `docs/agent-commands.md`，`tmh/install.py` 随安装复制到 `.tmh/docs/`；`tests/test_tmh.py` 增加预算、硬规则与分发一致性验证。全部硬规则保留，证据绑定提交和禁止绕过钩子明示。
- 验证：`python3 -m unittest discover -s tests -p 'test_tmh.py'`，46 tests，OK（5.080s）。临时 Git 仓库运行 `install(root, ['claude', 'codex'])` 后实际读回 AGENTS.md 全文，确认 CLAUDE 引用和命令文档字节相同。`git diff --check` 通过，逐段审阅实现 diff 和新文档。
- 修复轮数：0；一次 patch 格式校验失败，未写入任何文件，改为单次更新后成功。

## P2

- 状态：done。
- 范围：`tmh/acceptance.py`、`tmh/cli.py`、`tmh/platform/epic.py`、`tests/test_acceptance.py`、`tests/test_platform.py`；规格提到 `intake.py` 时只按需定位入口。
- 计划：尺寸提示与 AC 放行逻辑分离，CLI 检查/进入实现和父单日志都提示；不自动拆分或改契约。
- 命令/结果：已完成 acceptance 全文件、platform 的 big_requirement 筛选及临时仓库 check 输出核对，见下方记录。
- 待确认：无。

### P2 验证记录

- `python3 -m unittest discover -s tests -p 'test_acceptance.py'`：14 tests，OK（2.423s）。临时仓库 CLI check 显示 9 条 AC 与并列标题提示，退出码仍为 0。
- platform 首轮 3 tests 报错：访问回环测试服务得到 HTTP 502，项目列表为空；推断为继承的代理把 localhost 请求转发。改用仅当前测试进程 `NO_PROXY='*' no_proxy='*'` 重跑，禁止回环请求走代理；未改测试或产品逻辑。
- 重跑 `NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_platform.py' -k big_requirement`：3 tests，OK（1.383s）；仅有既有测试资源关闭警告。后续测试沿用 NO_PROXY，未改机器设置。
- 实际改动：上述 5 个文件。`size_warnings` 与 `ac_problems`/`advance` 放行条件隔离；CLI check/成功进入 implementing 打印提示；epic 在建子单之前用 `_edit`/`_log` 记录，保留正常创建流程。
- 假设/阈值：peers 传其他契约原文、排除自身与无有效 AC 的样本；≥5 份时按条数或“条款+检查方式”字符量达到中位数 2 倍提示；少于 5 份用 >8 条 / >1600 字。后者相当于 8 条较长的约 200 字条款。标题并列、新建数 >3 独立提示；文件数量只匹配明确数字或反引号列表，避免猜测。epic 同一批其他 item 作为 peers。
- 审阅：已逐段检查 git diff；`git diff --check` 通过；基线断言、状态机、人确认和证据逻辑未改。失败处理：环境修复 1 轮，无实现修复。

## P3

- 状态：done。
- 范围：`tmh/platform/learn.py`、`tests/test_lessons.py`。
- 计划：只过滤含全局固定动作的经验卡提示注入，返回命中原句；保留人的原文与现有状态，不改变存储格式。
- 命令/结果：`test_lessons.py` 已通过，见下方记录。
- 待确认：无。
- 实际改动：`overhead_flags` 匹配 fix/verify/anti 的每次/每轮必须、开工前先、改完一律，以及 always + 动作、before/after every/each task/run/session/change/iteration/commit；排除有场景条件的建议和非指令的事实句。匹配原句仅在 add/edit 返回值携带 flags，不写入 lessons.jsonl 新字段。
- `relevant` 对本项目与已采纳共享卡均过滤；按既有 `_note_once` 模式每工单每轮人裁决前记录一次 overhead 日志。状态、信任和失败计数规则不变。
- 代码差异：原 edit 和日志折叠均截断到 800 字，edit 还 strip；为满足“人的原文逐字保留”移除这些处理，字段/存储格式不变。长文本测试覆盖末尾命中句及空白/换行完整保存。
- 验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_lessons.py'`：16 tests，OK（0.040s）；已审阅 git diff，`git diff --check` 通过；实现修复 0 轮。
- 边界：规则有意偏保守，未显式表达全局动作的说法可能漏报；未改页面/CLI 展示层（返回值已提供 flags）。

## P4

- 状态：done。
- 范围：只读 `docs/self-improvement/` 的 verification 记录及规格允许的 STATUS，修改 `skills/legacy-feature/SKILL.md`、`skills/acceptance-l2/SKILL.md`、`tests/test_tmh.py`，新增 `docs/dead-ends.md`。
- 计划：只纳入验证记录能直接支持的结论；保留环境限定；表格不含客户标识、地址、报价或凭据。
- 命令/结果：test_tmh 和 3 条来源抽查已完成，见下方记录。
- 待确认：无。
- 实际改动：新增 15 行文档、9 条死路；两个技能正文各增加按场景指向，description 未改；新增来源文件存在和行数预算测试。
- 来源抽查：① external-candidate 的“保留的失败与修复”第 1 条直接记录沙箱 TCP/Git 拒绝；② runtime 的问题表第 1 条记录父退出 0 仍有子孙与管道阻塞，配原始红灯日志；③ harness2 的基线/候选表及后文明确双方进程退出 0 但基线业务失败。另逐条核对 preview-health 的直接 2xx/无重定向约束、裸预览 401、Git archive 和优化模式 assert，来源均支持表述。
- 差异/假设：规格举例提到 Node/原生 Codex，表使用证据直接证明的“POSIX 包装父进程”表述，不推断特定包装器；沙箱限制仅针对记录中的 workspace-write 环境。
- 审阅：读回完整表并核对 5 列，无客户名、地址、报价、凭据；逐段审阅 diff，`git diff --check` 通过。未访问链接或证据目录之外的运行数据。
- 验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_tmh.py'`：47 tests，OK（6.079s）；修复 0 轮。

## P5

- 状态：done。
- 范围：`tmh/acceptance.py`、`tmh/cli.py`、`tmh/guard.py`、`tests/test_acceptance.py`；只读规格列出的 `tmh/task.py` 与指定钩子测试。
- 计划：missing-requirement/dependency 产生非任务草稿；同源最多两份未确认；人确认入口复用 `_human`，guard 增加拦截；不改 MOVES/HUMAN_ONLY、不接平台。
- 命令/结果：test_acceptance、指定 guard 钩子及临时仓库模拟上报→人工确认已完成，见下方记录。
- 待确认：平台接入留作建议，不在本次实现。
- 首轮：19 个 acceptance 测试、10 个 GuardAndVerifyTest/AgentHookTest 均通过。补并发及确认回执失败恢复两例后 21 个测试通过（3.003s）。
- 手工流程发现绝对草稿路径 `/var/...` 与 root.resolve() 的 `/private/var/...` 别名不一致，确认后返回相对路径报 ValueError；修复第 1 轮：先检查限定目录和符号链接，再规范化 path；新增用绝对路径确认的覆盖，重新跑指定测试和手工流程。
- 最终验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_acceptance.py'`：21 tests，OK（3.611s）；此前新增两例的中间版 21 tests 也通过（3.003s）。`... -p 'test_tmh.py' -k GuardAndVerifyTest -k AgentHookTest`：10 tests，OK（1.530s），包括 dangerous_bash 及 Codex hook。
- 临时 Git 仓库 CLI 手工流程复跑成功：上报→读回完整 Markdown→用测试夹具模拟人工入口→读回确认人/新任务号；新任务 T002 为 draft_contract、confirmed_by=None，源任务未迁移。不是实际任务或真人验收操作。
- 实际改动：4 个授权文件。草稿示例 `.tmh/acceptance/proposals/T001-1.md`，首行 JSON 注释标记来源/类型/状态，正文含建议标题、待补 AC 与完整原话（围栏长度避开原话反引号）；确认后原文保留并追加人名和任务号。
- 收敛：同来源两类合计最多 2 份 pending；跨进程 mkdir 写锁防并发穿透，异常释放；损坏草稿保守拒绝；重复确认拒绝；回执写失败重试复用已建 draft。进程被强杀可能留下 `.write-lock`，需人核实后清理（不把该锁用作崩溃恢复所有权证明）。
- 审阅：已逐段看实现/测试 diff，`git diff --check` 通过；guard 仅追加 propose-confirm 模式；MOVES/HUMAN_ONLY/AGENT_ENV、ALWAYS_PROTECTED、原确认/关闭拦截及证据链未改。共 1 轮实现修复。
- 平台建议：以后在父单展示结构反馈待审列表，人在正常身份验证入口选择采纳，生成 draft 后再走原有规格/AC 确认；不直接调用 `_follow_up` 自动放单。

## P6

- 状态：done。
- 范围：`tmh/platform/crash_recovery.py`、`recheck_operations.py`、`candidates.py`、`harness_probes.py`、`tmh/kb.py`，新增 `tmh/platform/filelock.py` 和 `tests/test_filelock.py`；只读指定相关测试及 Windows 剩余阻塞所需静态定位。
- 计划：POSIX flock / Windows msvcrt 第 0 字节锁统一接口，句柄/进程退出释放；保留 kb 的无原生后端 O_EXCL 回退；回执格式和恢复门槛不改。
- 命令/结果：filelock、新旧恢复/候选/探测指定测试与 KB 队列用例均已通过，见下方记录。
- 待确认：Windows 余项已列于后文，不扩展进程监管实现。
- 实际改动：新增 filelock + 12 个测试，4 个平台模块全部改用统一接口，KB 仅替换原生分支并保留 O_EXCL 回退。锁后端延迟加载，不存在 fcntl 时走 msvcrt；非阻塞竞争统一 BlockingIOError；Windows 在持有第 0 字节范围锁后初始化空文件，避免竞争写入；保留位置、非竞争错误和既有业务提示。
- 锁语义：当前所有调用点均排他；OS 句柄关闭/进程退出释放。Windows blocking=True 以非阻塞调用循环等待，避免 CRT 内建重试上限。所有权判断不使用 O_EXCL、历史 PID 或残留文件存在性。回执/数据库结构未改，process_control/supervised_process 未改。
- 验证：所有命令仅带进程级 `NO_PROXY='*' no_proxy='*'`，使用 `python3 -m unittest discover -s tests -p <文件>`：test_filelock.py **12/12**（0.148s）；test_crash_recovery_api.py **6/6**（0.612s）；test_crash_recovery_independent.py **8/8**（2.875s）；test_recheck_operations.py **14/14**（3.901s）；test_external_candidates.py **11/11**（8.724s）；test_harness_probes.py **7/7**（13.909s）；test_harness_probes_independent.py **9/9**（10.721s）；`test_tmh.py -k test_queue_is_bottom_up_and_parallel_safe` **1/1**（0.141s）。修复 0 轮。
- 实测边界：macOS/POSIX 真锁、真子进程 kill 后释放；Windows 使用 mock fcntl=None/msvcrt 验证 4 模块实际导入与锁调用、竞争/阻塞/错误/初始化。没有 Windows 实机，不把 mock 当实机结果。
- 审阅：逐段查看全部 git diff（含新文件），`git diff --check` 通过。AST 对比起点 `422d9bf`：MOVES/HUMAN_ONLY/AGENT_ENV/ALWAYS_PROTECTED 完全相同，DANGEROUS_BASH 仅追加一条；4 个有改动的既有测试文件中所有原 test_* 方法 AST 均未变。

## Windows 剩余阻塞（只盘点，不改）

1. 已知范围外：process_control.run_process / supervised_process.run_supervised 仍显式拒绝非 POSIX，受管组、管道传递等仍需另行移植。
2. `tmh/platform/preview.py` 的 `_kill` 使用 os.killpg/SIGKILL，启动依赖 shell=True/start_new_session；默认 Django 命令为 POSIX 环境变量前缀语法。预览进程身份与退出判断也需要 Windows 专门验证。
3. `tmh/platform/fixloop.py:_local` 写死 `/bin/sh -c`；命令拼装使用 shlex.quote/POSIX cd 语法。Windows 本地构建需要平台适配。
4. `tmh/install.py` 的 Codex hook/MCP 使用 sh、`$(...)`、`/dev/null` 与 python3；pre-commit 为 `/bin/sh`。`project_bootstrap.py` 用 shlex.quote 生成测试/预览命令；原生 cmd/PowerShell 不能直接视作兼容。
5. `candidates.py` Git 的 `core.hooksPath=/dev/null`，以及硬链接、POSIX 可执行位/0600/0444 权限语义，需要在 Windows/Git for Windows/目标文件系统实测；这些属于条件兼容风险，不断言 NTFS 不支持硬链接。
6. 本次默认排他锁满足所有现有调用点；`exclusive=False` 使用 CRT read-lock 模式，Windows 可能比 POSIX LOCK_SH 更严格，不能保证多个读者并行。若后续需要真共享锁，应单独设计 Windows 原生共享后端；当前无该生产调用点。

## P1–P6 首次全量回归（历史记录）

- 状态：done；测试实现提交 `a06c09e`；运行 `python3 -m unittest discover -s tests`。仅测试进程设置 NO_PROXY，并通过临时 PYTHONPATH 的 sitecustomize 禁止非回环 socket/DNS；不改机器配置、产品代码或测试断言。
- 完整原始日志：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-port-validation-i4mv6w0e/full-unittest.log`；离线辅助文件也仅在该临时目录。执行前 `git status --short --branch` 干净。
- 全量结果：806 tests，369.499s，FAILED（failures=1, skipped=15），即 790 通过、15 跳过、1 失败。唯一失败为 `test_direct_invocation_lifecycle.DirectInvocationLifecycleTest.test_intake_timeout_or_cancel_cannot_apply_a_late_successful_answer` 的 cancelled 子场景，预期 cancelled，实际 failed/124（总超时）。已有 socket/SQLite/HTTPError 资源关闭警告保留在原始日志。
- 跳过原因：用 unittest loader 只读取跳过标记，未重跑用例；`test_sign.py` 两例缺 cryptography，`test_workbench_mcp.py` 十三例缺可选 MCP SDK。未联网安装依赖。
- 当前分支单例复跑：同一离线环境执行 `python3 -m unittest discover -s tests -p 'test_direct_invocation_lifecycle.py' -k test_intake_timeout_or_cancel_cannot_apply_a_late_successful_answer -v`，1 test，OK（0.750s）。
- 基线复现：只从 `422d9bf` 导出 `tmh/`、`templates/`、`skills/`、该单个测试至临时 `baseline-422d9bf/`，没有导出 data/ 或任何密钥/证书。132 个文件的 `git hash-object` 逐个等于起点 blob，排除 archive 替换差异；基线没有本分支代码。相同环境重复原单例（最多 30 次，首次失败立即停止），第 13 次（1.705s）在同一 cancelled 子场景、同一断言、同一 failed/124 信息失败。没有修改测试夹具、断言或 0.5 秒预算，没有人为注入延时。
- 原始复现日志：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-port-validation-i4mv6w0e/baseline-reproduction.log`。入口命令为 `python3 -`，循环用 `unittest.defaultTestLoader.discover('tests', pattern='test_direct_invocation_lifecycle.py')` 只筛选上述 testMethodName，每轮以 `unittest.TextTestRunner(verbosity=2)` 执行，失败 `sys.exit(1)`。基线进程退出码 1。
- 非本分支引入的证据：该测试、`intake.py`、`agents.py`、`process_control.py`、`supervised_process.py` 的当前字节全部与起点一致；基线原样复现同一失败。测试的 0.5 秒总预算可能先于模拟 cancel 耗尽，成功返回码断言因此先失败；该时序敏感问题留待单独处理，未放宽断言或修改范围外监管逻辑。按完成标准保留并披露这一基线失败，不用反复全量重跑掩盖它。
- 原始日志校验：full-unittest.log 为 23269 字节，SHA256 `73578db1fdec8a9ef114b3b33d17420379a975af5e7bba1df34e9eafc127e19c`；baseline-reproduction.log 为 6151 字节，SHA256 `6a200d4b09675d76f125665057493138149875f8da9918576f78f305f298cb8f`。
- 收尾只更新本进度文件，产品/测试实现仍为 `a06c09e`；原 stash 保留。人工审阅重点：P5 的 guard 新规则、propose_confirm 人身份/幂等恢复边界，P6 的 filelock 字节锁/关闭释放/阻塞重试及 KB 回退边界。

## 待确认

- P5 平台接入：建议新增人工待审入口，不直接从结构反馈调用 `_follow_up` 自动派发；本次不接平台。
- P5 异常中断若留下 proposals/.write-lock，需要人先核实无活跃操作再清理；不自动猜测所有权。
- P5 升级前若确认回执写入失败，已有任务使用旧版未引用的草稿快照，升级后重试会保守拒绝；需人工核对草稿和任务内容，不自动迁移或推定已确认。
- P6：上列 Windows 剩余阻塞；需 Windows 实机验证默认排他锁自动释放，尤其不同文件系统与进程退出路径。共享读锁的并行性不在已证明范围。
- intake 基线时序失败已在下节修复并通过全量；没有新增待确认事项，生产监管实现保持原样。
- 最终审查首轮另见构建树用例的 2 秒就绪失败；当前分支/起点各 20 次对照及最终全量均通过，尚未复现根因，不能声称已修复。完整记录在末节；未放宽任何时间限制或断言。

## 后续：intake 取消测试基线时序修复

- 状态：done；起点 `db4e957`，继续在 `feat/ralph-port`；开工 `git status --short --branch` 干净，原 stash 保留。独立提交标题：`test: 消除 intake 取消用例的墙钟竞态`（本记录与修复一起提交）。
- 用户授权：修复基线时序失败，不能削弱断言或简单放宽超时；先验证稳定性，再跑全量，更新本文件并单独提交；不 push，全程自动推进。
- 定位结论：原 fixture 给真实进程与最终结果处理共用 0.5 秒预算，只有 invoke 已返回 0 才注入 cancel；若系统调度/监管收尾先耗尽预算，cancel 根本没有执行。生产超时行为符合规则，缺陷在测试未确定“成功退出→取消/超时→最终采纳”的事件先后；用测试时钟固定该顺序。
- 阅读范围：`tests/test_direct_invocation_lifecycle.py`、`tmh/platform/agents.py`、`intake.py` 及底层监管/生命周期测试。
- 待确认：无。
- 修复范围：只改 `tests/test_direct_invocation_lifecycle.py` 与本文件；生产 Runner/intake/监管器没有修改。测试局部替换 `agents.time` 的单调时钟，其他墙钟及全局 time 模块保持真实；原 0.5 秒逻辑预算和传递给监管器的预算均保留并断言。真实监管器/子进程照常执行，测试适配层仅给它独立的 5 秒墙钟 watchdog，避免进程启动决定调用者测试的事件先后。
- 原 sleep 改为把逻辑时钟精确推进到 deadline，未延长被验证的逻辑超时；新增 deadline 前 1ms 成功、取消先发生后 deadline 到达、真实监管启动延迟 0.6 秒三个场景。原断言全部保留，另增加原进程 exited/0、预算值与 cleanup.complete 的断言。
- 红灯：先只加“慢监管启动”用例，在旧夹具下运行对应 `-k test_intake_cancel_after_slow_supervisor_startup_keeps_successful_process_evidence`，1 test，0.862s，按预期失败（failed != cancelled，124 != 0）。随后应用可控时钟夹具。
- 首次绿灯：`python3 -m unittest discover -s tests -p 'test_direct_invocation_lifecycle.py' -v`，15 tests，6.893s，OK；日志位于 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/intake-lifecycle-validation-vx3ag9qb/direct-green.log`。全部后续验证继承进程级 NO_PROXY 与该临时目录的离线 sitecustomize。
- 稳定性计划：原失败用例连续 100 次，完整 direct invocation 模块连续 10 轮；任何失败立即停下修复。再核对真实墙钟监管相关测试和完整回归；不修改已有真实超时用例。
- 稳定性结果：上述 100 次原用例 + 10 轮完整模块（150 tests），合计 **250 次测试执行全部通过**，119.306s，无跳过；每轮还验证两个 patch 已正确恢复，未泄漏给后续测试。命令为 `python3 <临时目录>/stability.py`，脚本与完整 `stability.log` 保留在同一临时目录。
- 回归敏感性：临时脚本 `regression_guards.py` 分别在内存禁用 Runner.stop_reason / Runner.cancel，原用例分别按预期产生 2 / 1 个断言失败，均直接拒绝“迟到智能体答案被采纳”；脚本确认失败类型后退出 0。没有改磁盘上的生产代码。这些是有意注入错误的负向实验，完整记录在 `regression-guards.log`。
- 审阅：逐段查看测试 diff；AST 对比 `db4e957` 确认原 **42 条断言全部原样保留**；`git diff --check` 通过，生产 tmh/ 内容未变。以下真实墙钟验证、全量均已完成。
- 真实墙钟验证：分别运行 `python3 -m unittest discover -s tests -p <文件> -v`：`test_process_control.py` 14 tests / 6.808s，`test_supervised_process.py` 14 / 4.535s，`test_run_lifecycle.py` 13 / 23.677s，合计 **41/41 通过**。没有应用本次测试夹具的 clock/supervisor patch；包含监管启动计入超时、真实进程树超时/取消和总预算跨调用等既有断言。日志 `real-deadlines.log`。
- 后续全量：**809 tests，374.241s，OK（skipped=15）**，即 794 通过、15 因可选依赖缺失跳过、0 失败/错误，退出码 0。运行 `python3 -m unittest discover -s tests`，仅继承进程级 NO_PROXY 和临时离线 sitecustomize。受测基线 `db4e957`，唯一测试改动文件 SHA256 `f1354cf3b708bffe8e838a0c8994fb6679b68ef6561fdcc7f3d7f7b65448d7c1`；测试结束后再次核对相同 hash。原始输出保存到同临时目录 `full-unittest.log`，既有资源关闭警告原样保留。
- 日志校验：`stability.log` 13563 字节 / SHA256 `aa31f211063c92fcb07eb37b93c88d4821772a3c149bf72d52ae746043e7bf22`；`full-unittest.log` 22075 字节 / SHA256 `b6510cbf468941461eafefd46f0fa92e7a9093156e5796b7822b0cd6d679dc34`。临时脚本、其他验证日志均保留，无压缩/截断。
- 收尾：只提交上述测试文件和本记录；无生产代码修改、无新的失败待处理，不 push，保留原 stash。

## 最终审查

- 状态：done；起点 `11078c5`，`feat/ralph-port` 开工干净。用户授权发现问题直接修复、验证、单独提交，不 push；原离线与不触碰真实数据/凭据的限制继续适用。
- 审查重点：P5 人工确认及 guard 可接受的命令形式、草稿与恢复边界；P6 所有权释放/Windows 字节锁/错误处理；11078c5 的测试时钟与 5 秒 watchdog 是否丢失真实超时覆盖。
- 已读进度与最近 10 条提交，完成代码审查、本地复现、修复与最终全量；待确认/已知限制见前文清单及各节。

### P5 审查修复

- 状态：done；提交 `1a11236`；修改 `tmh/acceptance.py`、`tmh/guard.py`、`tests/test_acceptance.py` 和本记录。以下确认行为全部是临时仓库内的合成测试，没有替人确认真实任务。
- 复现：5 个新增用例在修复前出现 11 个断言失败、1 个错误。① 当前 Codex 无沙箱环境仅有 `CODEX_THREAD_ID`，旧 `_human` 未识别；② guard 漏过前置选项、引号、转义和 `--to` 缩写等有效 CLI 命令；③ 引用原话的 `## 4.` 可被解析成新任务 AC；④ 确认回执失败后修改草稿，重试仍复用过期任务；⑤ proposals 目录符号链接可先写出仓库，最后才报路径异常。
- 修复：AGENT_ENV 只追加 `CODEX_THREAD_ID`；保留全部原始 DANGEROUS_BASH，新增 shell 分词和真实 CLI 参数解析的补充拦截；采纳原文逐行加 blockquote 前缀（测试反向去前缀逐字相等），不再参与契约章节解析；重试必须匹配原文快照；读写前拒绝草稿存储路径及文件符号链接。既有 MOVES/HUMAN_ONLY、保护清单、证据绑定不变。
- 验证：`python3 -m unittest discover -s tests -p 'test_acceptance.py' -v` **26/26**（5.872s）；`... -p 'test_tmh.py' -k GuardAndVerifyTest -k AgentHookTest -v` **10/10**（1.675s）。完整日志在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-final-review-b2e6yow4/` 的 `p5-red.log`、`p5-green.log`、`p5-hooks.log`。所有验证使用进程级 NO_PROXY 和临时离线 sitecustomize。
- 已亲自逐段审阅 diff，`git diff --check` 通过；原有测试方法和断言未改。guard 解析明确限于可见的字面命令，不宣称是任意 shell 求值的安全沙箱，运行时 `_human` 独立拦截仍保留。
- 待确认：旧版本回执中断留下的任务使用未引用的快照，升级后重试将保守拒绝，需人核对后处理；不自动改写旧任务或推定已确认。

### P6 审查修复

- 状态：done；提交 `21e68cd`；已复现 KB 原生锁获取把 ENOSPC 错误重试 1200 次并报“被占用”，以及 KeyboardInterrupt 时句柄未关闭。只收紧 `tmh/kb.py` 的异常分类/清理，保留内核所有权锁和无后端的 O_EXCL 旧回退；新增 3 个 `tests/test_filelock.py` 用例。锁后端和生产所有权回执没有改动。
- 红灯：`test_filelock.py -k kb_` 4 tests，2 failed；ENOSPC 被隐藏为 TimeoutError，打断后 fstat 仍成功。绿灯：`python3 -m unittest discover -s tests -p 'test_filelock.py' -v` **15/15**（0.396s），涵盖真实 POSIX 互斥/阻塞/关句柄/进程杀死释放、Windows mock 初始化及异常路径；`... -p 'test_tmh.py' -k test_queue_is_bottom_up_and_parallel_safe -v` **1/1**（0.210s），并行 KB 队列仍正确。日志 `p6-red.log`、`p6-green.log`、`p6-kb-queue.log`。
- 已逐段审阅两文件 diff，`git diff --check` 通过；只对规范化的 BlockingIOError 重试，其他异常立即抛出并关 fd。竞争的 1200 次/0.05 秒策略未放宽，底层字节锁/O_EXCL 回退未改。待确认仍为前文 Windows 实机验证/进程监管等剩余阻塞，没有把 mock 结果当实机证明。

### 11078c5 超时覆盖审查

- 状态：done；可控时钟与 5 秒 watchdog 只用于调用者事件顺序，不能单独证明真实 0.5 秒超时。补独立的 `tests/test_intake_wall_clock.py`：Runner/监管器使用真实 time，透传原 timeout，仅故意延迟真实 Popen 0.6 秒；必须 failed/124、规则回退、reader 未启动且清理完整。稳定性、回归敏感性及最终全量已通过；与本记录独立提交。
- 新用例最初按 `no_spawn` 字段检查时报 KeyError；核对真实 process_control 回执后改为断言 `cleanup.trigger == timeout_before_spawn`、完整校验的监管回执 `pid is None` 及 reader marker 不存在，验证意图未变。独立测试 **1/1**（0.865s）通过。原文件只补说明，原方法和 0.5 秒逻辑预算/5 秒测试 watchdog 均未改。
- 稳定性：临时 `stability.py` 交替执行完整 direct invocation 模块（15 tests）和独立墙钟模块（1 test），共 10 轮 **160/160**，88.079s；每个模块执行完检查 agents.time 与监管函数均恢复，未污染后续真实时钟用例。完整 `stability.log` 保留。
- 负向实验：临时 `watchdog_sensitivity.py` 在内存将真实监管执行预算替换为 5 秒；新用例按预期失败，原始监管回执为 `exited/0` 而非 `timeout/124`。脚本核对这一失败后退出 0，说明 Runner 最后标记 124 不能掩盖越过真实截止时间的 reader 执行；没有修改磁盘生产代码。完整 `watchdog-sensitivity.log` 保留。
- 审阅：已读回整个新增测试；AST 对比 `11078c5`，acceptance/filelock/direct invocation 的所有原方法均未改；对比起点 `422d9bf`，MOVES/HUMAN_ONLY/ALWAYS_PROTECTED 相同，AGENT_ENV/DANGEROUS_BASH 仅追加。`git diff --check` 通过。
- 全量：运行 `python3 -m unittest discover -s tests`，仅设置进程级 NO_PROXY 与临时离线 sitecustomize。首轮及最终结果完整保留于末节。

### P5 回执临时文件追加审查

- 状态：done；提交 `3a16a62`。首轮全量运行期间只在临时夹具中继续核对写入边界，未修改受测实现。复现预先创建 `T001-1.tmp` 符号链接时，旧 staging.write_text 会先覆写仓库外合成文件，再把链接移至草稿路径；`p5-staging-reproduction.log` 保留失败断言。
- 执行顺序：首轮全量结束后改为同目录独占创建唯一临时文件，关闭后再原子 replace，保留失败清理/重试语义；新增不触碰旧临时链接目标的测试，再跑最终全量。待确认：无。
- 完成：首轮全量结束后才改实现；`NamedTemporaryFile(delete=False)` 独占创建、关闭后 replace、finally 清理，不读写旧 `.tmp` 链接。新增回归检查仓库外合成文件字节不变、旧链接未动、确认后草稿为普通文件、无新临时文件遗留。验收测试 **27/27**（4.746s），含原回执失败恢复测试；`p5-staging-green.log` 保留。亲自审阅 diff，`git diff --check` 通过。状态：done。

### 最终审查全量与构建树失败对照

- 首轮全量：**818 tests，408.143s，FAILED（failures=1, skipped=15）**；唯一失败 `test_run_lifecycle.RunLifecycleTest.test_build_tree_uses_run_budget_and_cannot_launch_model_after_timeout`，在 2 秒 `wait_ready` 内三个合成进程树标记均未出现，尚未进入后续 3 秒总预算/5.5 秒收尾断言。intake、P5、P6 新用例没有失败。日志 `full-unittest.log`，受测 8 个实现/测试文件运行前后 SHA256 完全一致（`validated-files.json`）。
- 对照方法：该测试及 `agents.py`/`process_control.py`/`supervised_process.py` 与 `422d9bf` 没有差异。不能仅凭字节相同或复跑转绿判定根因；临时 `build_tree_diagnostics.py` 连续跑原单例，失败时在清理前保存合成 run/lifecycle/监管回执，未改其断言或时间限制。另导出起点 tmh/templates/skills 与该测试，逐个核对 Git blob，用于独立对照；没有导出真实 data/ 或凭据。
- 对照结果：当前分支原单例 **20/20**（72.072s），起点原样副本 **20/20**（69.255s），均未复现。起点目录 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-review-baseline-422d9bf-15ak0872` 的 132 文件逐个等于起点 blob；日志 `build-tree-current.log`、`build-tree-baseline.log`。本轮不宣称已证明该偶发失败的根因或修复它；原 2/3/5.5 秒限制和全部断言保留。
- 最终全量：在 P5 staging 修复提交 `3a16a62` 和本节测试改动上运行 `python3 -m unittest discover -s tests`，**819 tests，400.354s，OK（skipped=15）**，即 **804 通过、15 跳过、0 失败/错误，退出码 0**。8 个受测实现/测试文件的运行前后 SHA256 一致（`validated-files-final.json`），最终再次检查全部原测试方法 AST 未变、`git diff --check` 通过。原生监管代码没有修改。
- 跳过原因只读核对（没有再执行测试）：1 项 cryptography not installed；1 项 needs both（cryptography 与 ssh-keygen，当前缺前者）；13 项 optional MCP SDK not installed。没有联网补依赖。既有资源关闭警告保留在日志中。
- 最终全量的临时 sitecustomize 阻止非回环网络；仅父 unittest 进程的 addFailure 附加只读诊断，在 run_lifecycle 失败时于清理前记录合成运行回执，不改用例/结果/断言，也不向子解释器增加 unittest 导入。最终没有失败，诊断快照未触发。
- 日志校验：`full-unittest.log` 24630 字节 / SHA256 `784f142238cfeed97351ef88097fd6844962e3e091b69d926dc6b770b256568c`；`full-final.log` 23014 字节 / SHA256 `e45a2ecb2403510eb6ffe71ca163a190d2c921af26f55ea767152f9d7df838e3`；`stability.log` 2959 字节 / SHA256 `cf340b7e96057c77d4f2417d85122daf8d15da65ba83d7ac1813455a45302f82`。其余复现/负向/对照日志及脚本同目录原样保留。
- 交接重点：`guard.py:_human_accept_command` 及 acceptance 的 agent 标记、引用/快照/路径/临时文件边界；`kb.py:_Lock` 的重试分类与失败释放，以及 `filelock.py` Windows 字节锁/共享读锁限制；`test_intake_wall_clock.py` 的真实 0.5 秒约束和未启动证据。P1–P6 均保持 done，原 stash 保留，不 push。
