# Ralph port 执行进度

- 当前项：P4；状态：done
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
| P4 | done | 见 `P4:` 提交 | 已知死路及来源验证 |
| P5 | todo | — | 结构反馈草稿与人确认 |
| P6 | todo | — | 可替换文件锁与 Windows 阻塞盘点 |

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

## 待确认

- 暂无。P6 完成时在这里列出 Windows 剩余阻塞点。
