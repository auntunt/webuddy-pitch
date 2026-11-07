# 老项目改造长期推进：实施与证据

基线：2026-11-07，产品分支 `devin/1793765109-bidding-demo-ui`，`e282afab238e658e495e5508e64c94b72101dfc2`。GitHub远端核对相同。原工作区存在未提交Windows记录；使用 `/tmp/webuddy-reform-20261107` 隔离工作树，不纳入这些改动。

## 当前实现清单

| 范围 | 当前已有 | 仍需补齐 |
|---|---|---|
| 网页/HTTP | `ui.py` 的 `#/reform`；`server.py` `/api/projects/<key>/reforms` 列表、预览、创建、放出、恢复、删除 | 独立深链接、明确范围、可靠恢复、分页与共用现行证据投影 |
| 计划持久化 | `reform.py` `data/reforms/<key>.json`；工单与运行在 `store.py` SQLite | 建单与映射原子化、稳定身份、归档、批次领取、事件、修订和幂等 |
| 执行/停止 | `agents.Runner`；`crash_recovery`、监督器、停止回执、UNIQUE retry_of | 系统执行固定授权基线与未验证恢复快照的合法关联 |
| 集成/验证 | `epic.py`、`delivery.py`、候选、项目测试和人工门禁 | 改造批次固定集成版本、依赖、检查点及整体验收关联 |
| MCP入口 | `agent_contract.py` → `workbench_mcp.py` → `workbench_client.py` → `agent_api.py` | 当前无改造管理工具；不能仅登记名称 |
| 权限 | `tool_access.py` scope、`tenant_policy.py`、`tenant_runtime.py`、资源归属、agent_api `_resource/_write` | 计划资源与新操作需完整登记，并保留身份/人工边界 |
| 文档/测试 | `docs/workbench-agent.md`、`developer-terminal.md`；`test_platform` 改造用例、`test_run_recovery` 与开发契约测试 | R/T逐项反例、真实SDK/stdio+HTTP/租户、实际浏览器和跨日记录 |

## 分阶段进展

### A1：R1 系统执行恢复（实施中）

两个隔离反例在基线失败：固定system基线不同导致retry拒绝；确认稿变化后retry_state错误允许。原失败见 `evidence/reform-20261107/r1-before.log`。

新增SQLite执行契约绑定及恢复快照来源登记；原授权基线与实际运行基线分开保存。续跑仍校验当前system选择、确认稿、项目/工单、停止回执、知识授权、原工作树及唯一后继；实际启动再次检查契约。恢复快照标为未验证，专用Git引用保留对象。旧记录无绑定时不猜测授权，返回核对交接的阻塞。

原需求、旧运行、工作树和历史证据不改写。新增表是增量迁移，不重新归属旧工单。回退只切程序，保留新表和新写入。此阶段不代表R2—R8、完整MCP或UI验收已完成。
