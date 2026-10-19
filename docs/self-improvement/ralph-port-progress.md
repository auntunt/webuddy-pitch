# Ralph port 执行进度

- 当前项：P1；状态：done
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
| P1 | done | 见 `P1:` 提交 | AGENTS 区块预算与命令路由 |
| P2 | todo | — | 非阻塞任务尺寸提示 |
| P3 | todo | — | 经验卡固定开销 lint |
| P4 | todo | — | 已知死路及来源验证 |
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

## 待确认

- 暂无。P6 完成时在这里列出 Windows 剩余阻塞点。
