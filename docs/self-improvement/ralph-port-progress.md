# Ralph port 执行进度

- 当前项：P6；状态：done（待最终全量回归）
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
| P6 | done | 见 `P6:` 实现提交 | 可替换文件锁与 Windows 阻塞盘点 |

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
- 命令/结果：待实现后跑 acceptance 全文件和 platform 的 big_requirement 筛选，并在临时仓库查看 check 输出。
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
- 命令/结果：待跑 `test_lessons.py`。
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
- 命令/结果：待运行 test_tmh 并抽查 3 条来源。
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
- 命令/结果：待跑 test_acceptance 和指定 guard 钩子，临时仓库模拟上报→人工确认。
- 待确认：平台接入留作建议，不在本次实现。
- 首轮：19 个 acceptance 测试、10 个 GuardAndVerifyTest/AgentHookTest 均通过。补并发及确认回执失败恢复两例后 21 个测试待读结果。
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
- 命令/结果：待跑 filelock、新旧恢复/候选/探测指定测试与 KB 队列用例。
- 待确认：最终记录 Windows 余项，不扩展进程监管实现。
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

## 最终全量回归

- 状态：todo；六项实现已分别完成，接着运行一次 `python3 -m unittest discover -s tests`，记录完整结果后最终提交进度。

## 待确认

- P5 平台接入：建议新增人工待审入口，不直接从结构反馈调用 `_follow_up` 自动派发；本次不接平台。
- P5 异常中断若留下 proposals/.write-lock，需要人先核实无活跃操作再清理；不自动猜测所有权。
- P6：上列 Windows 剩余阻塞；需 Windows 实机验证默认排他锁自动释放，尤其不同文件系统与进程退出路径。共享读锁的并行性不在已证明范围。
