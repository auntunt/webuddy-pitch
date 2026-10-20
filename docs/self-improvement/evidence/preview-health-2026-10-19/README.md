# 预览健康与恢复：完整证据索引

日期：2026-10-19。对应上层 `verification-preview-health-2026-10-19.md`。本目录保留原始字节；截图是浏览器工具实际返回的 JPEG，没有再编码或缩小。机器可读文件清单与 SHA-256 见 `manifest.json`；复制及读回检查见 `archive-verification.json`、`readback-verification.json`。

## 最终版本与测试

- `implementation-commit.txt`、`implementation.patch`：产品及首批回归实现。
- `test-fix-commit.txt`、`test-fix.patch`：最后一处共享预算测试夹具修正；产品代码未在此提交中改变。
- `final-verification.json`、`full-platform-final.log`：最终全量退出码、实际数量、耗时与全部原始输出。以前各次全量保存在 `full-platform-first.log` 至 `full-platform-fourth.log`，不能当成最终通过证据。
- `source-before-final.json`、`source-after-final.json`：全部产品、测试及构建配置的执行前后摘要。第三、第四轮也分别保留摘要。
- `run-final-verification.py`、`archive-evidence.py`、`verify-archive.py`：本轮实际使用的冻结、执行、复制和读回脚本。

## 真实 HTTP / SQLite 故障演练

- `fixture/`：隔离 HP-1 的数据库、应用源码、完整运行记录、验证输出和预览状态；只排除私密凭据、临时 journal、字节码和 Git 管理目录。Git 完整历史另存于 `fixture-candidate.bundle`，验证回执见 `fixture-bundle-verification.txt`。
- `browser-recovery-stale-summary.*`：真实浏览器先发现的“预览区恢复但顶部仍陈旧”失败；没有删除或覆盖。
- `browser-final-behavior.json`、`browser-final-recovered*`、`browser-final-item*`：修复后实际 DOM、原始图像、草稿与事项保留。
- `cli-*`、`mcp-*`：健康、真实 503、恢复三个阶段的完整 CLI / 官方 MCP 协议结果；不等同于新一轮模型代码生成。
- `live-final-*`：故障前后 SQLite 和进程/预览状态的原始快照。
- `fixture-cleanup.json`：两次隔离服务及预览进程均已退出，8798/8799 已关闭；日常工作台保持运行。

## 日常 BOOTV2 保持

- `main-preservation-report.json`：全部平台数据行、三条原事项和既有验收证据保持。
- `main-platform-before.db`、`main-platform-after.db`、`main-bootv2-*.db`：完整 SQLite 快照。
- `main-acceptance-*.json`、`main-preview-*.json`：完整验收返回及预览状态。
- `browser-main-bootv2.txt`、`browser-main-bootv2.jpg`：从正常授权入口打开固定候选后的实际页面；未改原事项。

## 独立复核与失败机制

`independent-review.md`、`independent-ui-final-review.md`、`independent-flow-fixture-readonly-review.md` 记录 HTTP、UI 和版本绑定复核。对应原失败、正确修复、源码摘要和脚本全部保留。

三个旧时序夹具的原文件、确定性延迟反例、正例、预算重置反例及完整原始日志分别以 `process-*`、`handwork-*`、`recheck-budget-*` 命名。报告为 `independent-process-fixture-review.md`、`independent-handwork-budget-review.md`、`independent-recheck-budget-review.md`。准备延迟仅证明旧预算前提可能失效，不证明历史机器调度的唯一原因；产品总时限没有放宽，故意重置预算仍被回归阻止。

本轮健康检查是读取时的接口可用性核对，不证明所有业务正确，也不是持续后台监控。人工批准、生产发布和其他自动任务授权均未扩大。
