# 磅单浏览器闭环接续证据

本轮接续同一 WBILL-1 候选4，业务提交 `ab9601e305bf9efdf908554174c56ca101194405`。浏览器完成核对保存、单独审核、旧页面审核拒绝、刷新持久化和完整原图打开；CLI/MCP 技术验收通过，等待用户对这个版本的业务确认。

- [本轮验证记录](../../verification-weighbill-acceptance-2026-10-19.md)：路径、结论与限制。
- [独立只读复核](independent/REVIEW.md)：实际 HTTP/SQLite、浏览器证据与运行版本交叉核对。
- `browser-timeline.json`：完整 DOM 操作记录；`browser-approved.jpg`、`browser-original.jpg`：工具返回的原始截图字节。
- `preview-before-resume.json`、`preview-after-reconciled-save.json`、`preview-after-approval.json`、`preview-after-stale-approval.json`：实际业务记录及历史；`preview-final-snapshot.db`：一致数据库备份。
- `candidate-before.json`、`mcp-before-acceptance.json`：本轮起点，保留 A3 unknown。
- `assessment-results.json`、`record-technical-acceptance.py`、`mcp-technical-acceptance.json`、`mcp-record.log`：逐项技术观察及完整 MCP 回执。
- `candidate-current.json`、`candidate-final-check.json`：两次 CLI 读取均为 `awaiting_human`、`technical_acceptance=true`、`human_accepted=false`。
- `preservation-*.json`：原仓库文件、原有平台数据行保持；`bootv2-before.json` / `bootv2-after.json`：已接受 BOOTV2 未变。
- `preview-runtime.log`、`preview-runtime-final.log`：两个时点的完整运行日志，未以摘要替代原文。
- `independent/`：独立脚本、完整 HTTP 原始响应、数据库行、过程输出及报告；一致性断言数量不代表业务覆盖率或提效比例。
- [前轮完整归档](../weighbill-pilot-2026-10-19/README.md)：固定候选源码、Git bundle、全量测试及原生弹窗故障。前轮材料未改写，本轮未重新执行全量。

`archive-metadata.json` 记录来源和版本；`manifest.json` 包含每个文件的字节数和 SHA-256（不含 manifest 自身）。整个原始目录逐文件原样复制，没有过滤、裁剪、截断、重编码或压缩。截图只在查看器里按显示区域呈现，文件保持原始字节。

本轮是本地隔离合成台账，真实 OCR 关闭。旧 API 省略条件仍兼容且不具客户端版本保护，草稿只保存在页面内存。弹窗恢复原因未知，不声称全程无人值守。合成记录内部“已审核”不等于用户对项目版本验收，未合并、推送或发布。

脚本保留执行时原貌：`preserve.py` 等依赖原先的 `data/weighbill-acceptance-20261019` 层级；回放时先复制回该位置或显式修改路径，并先检查本地状态。`record-technical-acceptance.py` 会记录观察，不能当只读检查重复执行。`archive.py --repo-root <仓库绝对路径>` 拒绝覆盖既有归档。
