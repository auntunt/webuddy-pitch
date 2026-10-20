# WBILL-1 恢复验收：独立只读复核

**结论：现有证据足够将候选 4 的 A3 从 `unknown` 更新为 `pass`，限于这次合成台账、真实双页面的技术验收。没有发现阻断该更新的问题。** 这不是用户签收，不代表生产部署，也不替代原先跳过的外部集成验证。

复核对象为完整业务提交 `ab9601e305bf9efdf908554174c56ca101194405`、WBILL-1 / candidate 4 / run 10 / verification operation 4。独立读取时，候选仍为 `current=true`，验证和预览有效，技术观察仍保留先前的 A3 unknown；`candidate_decisions` 为空，`human_decision=null`、`human_accepted=false`。

主代理据此更新技术观察后，另只读查看了保存的 `candidate-current.json` 和官方 MCP 回执：当前为 `technical_acceptance=true`、`ready_for_human=true`、`state=awaiting_human`、`human_accepted=false`；新整体证据哈希为 `6641fbcaaa745ab5496b022c61cd08d3f2e88c0248165bafe6e1e5731e002b8c`。这段是对主代理已保存回执的补充审阅，没有再次操作应用或提交决定；读取摘要与原文件哈希保存在 `post-observation-receipts-read.json`。

## 亲自执行的核对

没有操作浏览器或重放保存/审核。独立执行了只读 CLI `candidate 4`、对实际应用的 HTTP GET、以 `mode=ro` 加 `query_only` 读取实际隔离 SQLite、Git/进程/文件检查，以及对保存证据的完整比较。`review_evidence.py` 的 **65 个一致性断言全部通过**；这些断言是交叉核对项目数，不是新增业务覆盖率或修对率。

| 核对点 | 独立观察 |
| --- | --- |
| 核对保存 | `wbill-preview-1` 从 v1/未审核变为 v2/未审核。A 的货名和整段备注完整保留，B 的重量保持总重 10900、皮重 10000、净重 900。保存历史仅追加货名和备注的真实前后值 |
| 单独审核 | v2 变为 v3/已审核；字段值不变。只增加审核状态、版本和审核归因，历史追加一条“审核通过” |
| B 旧页审核 | `preview-after-approval.json` 与 `preview-after-stale-approval.json` 整份相等，包括记录、历史和业务事件计数。浏览器记录显示版本冲突及最新 v3，没有新的“已审核”成功状态 |
| 刷新持久化 | 主代理的刷新 DOM 记录显示已审核台账一条，保留同样的货名、备注与 900 kg。独立再次 GET 当前服务、直接读取当前 SQLite，均与最终快照完全一致 |
| 两条未操作记录 | `wbill-preview-2`、`wbill-preview-3` 与前轮浏览器操作开始前的完整记录逐字段相等，仍是 v0/未审核，历史为空 |
| 归档数据库 | `preview-final-snapshot.db` 完整性检查为 `ok`；全部 records/history 行与本次独立读取的运行中数据库一致 |
| 原图 | 三张合成原图的字节数和 SHA-256 与首次生成标记一致。已打开查看保存的已审核截图和原图截图，没有编辑或压缩图片 |

修改历史是严格追加的 1 → 2 → 3 条：先改重量，再改货名/备注，最后审核。被拒绝的旧页审核没有新增历史。独立脚本保存了全部 SQLite 行、HTTP 原始响应的完整 base64、响应头及 SHA-256，未用片段或摘要替代原始数据。

## 版本和证据没有失效

- 实际预览仍是 PID `54023`，启动时间仍为 `2026-10-19 16:53:03`，端口 `53621`。`lsof` 读取的真实进程 cwd 为固定预览工作树 `data/product-workbench/previews/WBILL-1`。
- 候选克隆和实际服务工作树的 HEAD 都是完整 `ab9601e305bf9efdf908554174c56ca101194405`，跟踪文件无修改；逐个读取实际服务工作树全部跟踪文件并与该提交的 Git blob 比较，全部相等。
- 实际 HTTP `/report` 完整字节等于该固定提交页面替换约定完整前缀后的字节。因此没有只凭 URL 中的 SHA 判断正在运行的页面版本。
- 当前验证哈希仍为 `22d374336720166d3aed1073b225050b880cc15de0ca0e7a9e6b2da605e3b3df`，预览哈希仍为 `f36415bec2d488d05b0b21e933b226a1baf439b4e6996fed270bef40b7a6c41b`；与本轮 `candidate-before.json` 一致。需求哈希及五项验收条件也未改变。
- 服务端健康中的存储可用，真实 OCR 明确 `configured=false` / `ingest=false`；应用 `degraded` 来自关闭真实 OCR 的合成预览边界，不是本轮台账保存失效。

因此可用上述当前验证及预览哈希记录新的 A3 技术观察。提交新观察会生成新的整体证据哈希；不应把旧整体证据哈希沿用为用户签收凭据。

## 人工签收与观察范围

我审阅的是主代理保存的真实浏览器 DOM 时间线、原始截图，再用当前 HTTP/SQLite 交叉核对结果；**我没有亲自重新操作浏览器，也没有重跑原全量测试或 Codex 实现。** 前轮独立 API/控制函数测试仅作既有背景，没有计入本轮新增运行。

恢复时页面已经显示“已核对版本 1”。本轮后续保存和单独审核有对应 DOM、版本及业务历史。浏览器控制为何恢复、由谁解除先前原生确认框，证据不能确定；不推断是用户确认，更不能由此推导项目签收。

本轮 A/B 指两个独立页面状态，不是两个真实人员身份。隔离预览使用共同的合成本地身份“本地验收员”，所以应用记录的 `approved_by` 只能证明应用内审核流程发生。它与 Webuddy 的人工验收是不同状态：独立读取确认平台没有操作者决定，`human_accepted=false`。A3 技术观察通过后仍应等待真实用户签收。

旧无版本 API 的兼容盲写边界、内存草稿不保证崩溃恢复、未接入真实 OCR、未配置 S3/OceanBase等此前限制保持。本结论不扩大这些能力范围。

## 证据索引

- `candidate-live.json` / `.stderr.log`：本轮独立 CLI 读取的完整候选。
- `review_evidence.py`、`review-evidence.log`、`checks.json`：65 项只读断言、完整输出及结果。
- `http-transcript.json`、`live-HTTP-snapshot.json`、`live-SQLite-rows.json`：独立读取的真实响应及全部业务行。
- `platform-candidate-readonly-rows.json`：候选、技术观察、人工决定的只读记录。
- `process-command.json`、`process-cwd.json`、`preview-state-read.json`、`serving-source-files.json`：真实进程、固定预览与逐文件 Git blob 核对。
- `browser-timeline-reviewed.json`、`inputs-manifest.json`：此次实际审阅的完整时间线副本及输入内容哈希。
- `check_archive.py`、`archive-checks.log`、`archive-checks.json`、`saved-database-rows.json`：归档数据库一致性、截图哈希和已记录 BOOTV2 验收状态未变的比较。

独立复核只在本目录写脚本、输出和报告；未修改业务源码、平台验收、原仓库、合成业务记录、运行配置或进程。
