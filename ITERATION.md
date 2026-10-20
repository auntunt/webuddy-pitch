# 本轮迭代记录 · 2026-10-20

**基线**：`auntunt/webuddy-pitch` main（导入时提交 `3220e3d`，tarball 无历史，已本地 `git init`）。
**分支**：`iteration/context-pack-v2`。
**方向**：用户的路线 3（架构审计）→ 2（知识库/上下文引擎）→ 4（全量迭代），路线 1（域名/服务器自动化）并行。
本文件记录路线 2 的第一个可验收增量。

## 改了什么

| 文件 | 变更 | 目的 |
| --- | --- | --- |
| `tmh/context_pack.py` | 新增（~430 行） | Context Pack v2：结构化、带来源/版本、预算精确、多来源、JSON、遗漏报告、activity 记录 |
| `tmh/context.py` | 末尾截断逻辑 | 去掉 `text[:budget]` 静默截断；改为带"省略 N 字符 + 怎么读全文"说明的预算内截断 |
| `tmh/cli.py` | `cmd_context` + context 参数 | `tmh context --json` / `--pack` / `--source <dir>` / `--require-all` / `--label` |
| `tests/test_context_pack.py` | 新增 12 项测试 | 契约验收（溯源、预算、多来源、失败关闭、确定性、RSI 记录、旧路径无静默截断） |
| `docs/design/context-pack-v2-2026-10-20.md` | 新增设计文档 | 对照 `project-knowledge-library-2026-10-20.md` §6.6/§7/§9 的契约与下一步 |
| `tmh/project_knowledge.py` | `import resource` 降级 | Windows 没有 `resource` 模块时快照构建不再失败（`peak_rss_bytes=null`） |

## 为什么是这一刀

用户的四个核心问题里，"百万行代码重构的精准功能/代码信息提供"最底层是**上下文供给的契约**：

1. 只给文本、不给来源/版本 → 无法审查、无法复验、无法跨项目引用；
2. 预算不足静默截断 → 这正是项目库设计 §6.6 禁止的"默默截掉证据"；
3. 单项目 → 无法支撑"多项目知识反哺"；
4. 不可机器读 → 无法度量"喂了什么"，RSI 没有数据接缝。

平台层 `platform/project_library.py` 已有版本化多项目检索，但 CLI/agent 日常入口仍是旧的单项目
`build_context`；本轮把契约下沉到确定性工具层，先让**最大量使用的路径**具备可审查性。

## 怎么验证

```bash
cd webuddy-pitch
python -m pytest tests/test_context_pack.py -q          # 13 passed
python -m pytest tests/test_tmh.py -k "context or knowledge or report_has" -q   # 17 passed
python -m pytest tests/test_phase1.py tests/test_command.py -q                  # 9 + 6 passed

# 端到端（在已 kb build 的仓库上）：
python -m tmh context "报销单财务审核驳回后预算" --repo <repo> --json --budget 4000
python -m tmh context "..." --repo <repo> --pack --budget 1200     # 预算不足时列出未展开项
python -m tmh context "..." --repo <repo> --source <参考项目目录> --json   # 多来源，id 不合并
```

预算 1200 的真实输出（节选，完整对照见 `D:\DSH_project\iteration\context-pack-demo.md`）：
保留 8 个知识页，列出 1 条未展开 + "另有 24 条未列出（--json 查看完整清单）"，`used <= budget`，
每条未展开项都带 `full_text` 句柄。

**已知 Windows 限制（非本轮改动引起）**：`tests/test_platform.py` 在 Windows 上 setup 即报
`AttributeError: module 'os' has no attribute 'O_NOFOLLOW'`（58 errors），这是该测试面向 Linux 的设计；
本轮改动未触碰该文件。Linux/WSL 下应正常，待 WSL 侧复跑确认。

## 已确认的边界

- `tmh context` 默认仍走旧渲染；v2 需显式 `--json/--pack/--source`。默认切换与 `platform/agents.py`
  接入留到下一轮（避免一次改动同时动 CLI 默认与平台回归面）。
- 检索仍是词法 + 图谱一步扩展，不是向量；`assemble` 的接口不变，可替换后端。
- 本轮没有导入真实标品规模数据；规模验证仍需按项目库设计 §9 阶段 D 做。

## 下一轮建议（按 ROI）

1. `platform/agents.py` 任务上下文改走 `assemble`，把 `used/omissions/complete` 带入运行记录（可审计"这单喂了什么"）。
2. v2 默认化（旧渲染保留 `--legacy`），跑全量 913 测试。
3. 参考来源升级为 `ReferenceBinding`（固定版本 + 模块范围 + 用途），与 `project_library` 对齐。
4. 规模实测：用 `ofbiz-framework` 或真实标品，记录冷构建/增量/检索延迟/峰值内存（Windows 上已修 `resource` 问题）。
5. 把 activity.jsonl 的 `context` 记录接进 RSI 信号：预算不足率、知识页利用率、任务成功率 vs 上下文大小。
