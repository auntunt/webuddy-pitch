# 开发习惯日志 v0（只读派生层：个人 / 团队视图）

> 状态：v0 最小集已实现（`tmh/platform/habits.py` + `tests/test_habits.py`），本文定义字段、隐私边界、保留策略与 RSI 接口。
> 定位：**观察层**，不是绩效系统。习惯画像是"这台机器/这个团队平时怎么干活"的描述，受样本量与日志完整性限制，不得用于个人评价。

## 1. 目标与非目标

**目标**
- 把已有的平台运行流水（tickets / runs / events / knowledge_revisions）派生成可审计的**开发习惯信号**：常用操作模式、业务域、返工原因、提示词模式、知识撰写、审查关注点。
- 提供两个视图：**个人视图**（本人可见自己的模式，默认脱敏）与**团队匿名视图**（按项目聚合，无人名、无逐人记录）。
- 样本不足时不出比例，沿用 `learn.impact` 的 `fair` 纪律（`MIN_N = 5`）。
- 只读：不改表、不写库、不新增埋点；现有数据能派生的才算。

**非目标**
- 不做个人绩效评分、不做排名、不做能力画像、不做"谁该被优化"。
- 不存/不返回提示词、评论、验收备注的原文；不再复制一份"习惯日志表"。
- 不在 v0 增加 HTTP API/UI（属后续服务器项，见 g9-report）。

## 2. 数据来源（全部只读 SELECT）

| 信号 | 来源表/列 | 说明 |
|---|---|---|
| 操作模式分布 | `runs.mode`（ask/analyze/plan/fix/verify/kb/understand） | 未知模式归入 `未知`，不丢数据 |
| 业务域 | `runs.project_id → projects.key` 计数 | 只看跑了多少，不看内容 |
| 工单类型 | `tickets.type` 计数（bug/feature/change/question/ops） | 个人视图按本人参与过的工单；团队视图按项目内全部工单 |
| 返工信号 | `events.kind IN ('accept','reject')`；`runs.status='failed'`；`runs.retry_of` | accept_fail=验收退回次数；failed_runs=失败运行；retry_runs=重试运行 |
| 返工原因分类 | `events(accept/reject).body/data.note` 关键词分类 | **只出类别计数**，原文不返回 |
| 提示词模式 | `runs.prompt` | 只出 sha256 前 12 位 + 长度 + 长度档 + 关键词类别 |
| 知识撰写 | `runs.mode IN ('kb',)`；`knowledge_revisions.author` | kb_runs + pages_written |
| 审查关注点 | 验收事件 note 的关键词类别 | 通过/退回都算"审查关注点" |
| 可用性探针 | 各表 COUNT | `habits.available(store)` |

## 3. 个人视图字段（`habits.personal(store, author, project_id=None, *, redact=True)`）

```text
view: "personal"
privacy: {redact, contains_raw_text: false, raw_text_policy}
sample: {runs, tickets, reviews, fingerprints}
fair: bool                      # runs >= MIN_SAMPLE(5) 才出模式比例
notes: [str]                    # 样本不足/无验收记录说明
modes: {mode: count}
modes_share: {mode: 0-1} | null # fair 为 false 时 null
ticket_types: {type: count}
ticket_types_share: {...} | null# 工单数 >= 5 才出
domains: {project_key: count}   # 常用业务域（按运行数）
rework: {accept_fail, failed_runs, retry_runs, reasons{类别:次数}, reasons_share|null}
prompt_fingerprints: {total, by_bucket{短/中/长}, by_category{...}, hashes[{hash,length,bucket,categories}], notes}
knowledge_writing: {kb_runs, pages_written}
review_focus: {notes_classified, categories{关注点类别: 次数}}
person: 姓名                    # 仅 redact=False 时出现；任何情况下都不含原文
```

**脱敏默认**：`redact=True`（默认）不返回 `person`。`redact=False` 也只增加姓名，**不增加任何原文**——原文（prompt / 评论 / 验收备注）在模块内部只用于计算长度、类别与哈希，不进入返回值。
**哈希口径**：`sha256(prompt.encode('utf-8')).hexdigest()[:12]`。同 prompt 同哈希、不同 prompt 不同哈希（可做去重/聚类线索），不可逆、不跨库关联。
**长度档**：短 <120 字，中 <600 字，长 ≥600 字。

## 4. 团队视图字段（`habits.team(store, project_id=None, *, min_sample=5)`）

```text
view: "team"
privacy: {redact: true, contains_raw_text: false, per_person: false, raw_text_policy}
sample: {tickets, runs, decisions, participants}   # participants 仅为人数，不出名单
fair: bool
notes: [str]
min_sample: 5
modes: {mode: count}
ticket_types: {type: count}
projects: {project_key: count}
knowledge_pages: int
rework: {accept_fail, reasons{类别: 次数}}
review_focus: {notes_classified, categories{...}}
modes_share: {...} | null            # fair=false 时 null
ticket_types_share: {...} | null     # fair=false 时 null
review_focus_share: {...} | null     # fair=false 时 null
rework_rate: 0-1 | null              # fair=false 时 null
```

**样本不足纪律（`fair`）**：`fair = tickets >= min_sample AND decisions >= min_sample`（默认 5）。
- `fair=false`：只出**计数**（计数是事实），所有 `*_share` 与 `rework_rate` 返回 `null`，`notes` 写明"工单样本 N 张，少于 5 张，团队比例不出"。
- `fair=true`：出比例，`notes` 仍注明"比例可作团队习惯参考，仍不是绩效结论"。
- 阈值与 `learn.MIN_N` 一致，避免同一平台两套样本纪律。

## 5. 隐私与保留策略

1. **默认脱敏**：`REDACT = True`；团队视图永远 `redact: true`、`per_person: false`、无人名。
2. **不存原文**：v0 不新增任何存储；派生结果在请求内计算，不落盘。哈希/类别/长度属于低敏信息。
3. **不返回原文**：返回值中只有计数、比例、类别、长度档、哈希；测试用"哨兵原文"断言输出中不出现原句（`tests/test_habits.py::PromptFingerprintTest`）。
4. **身份最小化**：团队视图只给 `participants`（人数）；个人视图仅本人调用时可 `redact=False`。
5. **保留策略**：v0 沿用平台现有数据的保留策略（`runs/events/tickets` 随平台库），不新增留存期；后续如需清理，应先在 `events`/`runs` 定义保留窗口并写迁移，不在派生层偷偷删数。
6. **用途限制**：文档与报告均明确"习惯画像不是绩效结论"；团队视图只用于流程改进（如默认模式坑位、经验卡优先级、验收关注点提示）。

## 6. 与 RSI 的接口（哪些信号可进入回放/提示词优化）

| 信号 | 可进入 RSI 的方式 | 约束 |
|---|---|---|
| `modes` / `modes_share` | 决定回放批次的默认模式配比（如 fix 占比过高说明定位环节缺提示） | 团队级，不下钻到个人 |
| `rework.reasons` | 返工原因高频类别 → 经验卡/规则优先级 | 只按类别聚合，不带原备注 |
| `review_focus.categories` | 验收草案提示：常被退回的关注点（性能/安全/测试证据）写进交付前自检 | 只做提示，不评分 |
| `prompt_fingerprints` | 相似提示词聚类（哈希/长度/类别）→ 提示词模板优化；**不能**据此还原原文 | 哈希仅用于去重，不跨项目关联 |
| `knowledge_writing` | 知识撰写低的项目 → 提示补知识页 | 页面计数，不看正文 |
| `ticket_types` / `projects` | 评测集与回放样本的业务域覆盖 | 团队级 |

## 7. 已知局限

1. **线上单账号**：生产环境只有一个账号，团队视图的 `participants` 与去人聚合在真实数据上无法验证（需多账号试点）。
2. **事件语义漂移**：历史上 `accept` 曾同时表示"采纳改动"，`Store` 已迁移 `accept→adopt`；旧库数据里可能仍有歧义，v0 只取 `accept/reject` 且不回溯修复。
3. **备注分类是关键词法**：类别是启发式，多类别可同时命中；无法覆盖新词；只用于聚合趋势，不用于单条判断。
4. **验收人 ≠ 开发者**：签收链接的 `author` 是甲方姓名，返工信号按"该工单的开发者"归属，避免把客户意见记到客户头上。
5. **样本量**：小团队/新项目 `fair=false` 是常态；`fair=true` 也只是"可以看比例"，不是统计显著性检验。
6. **runs.mode 口径**：`verify` 等模式历史数据可能以事件代替运行记录，模式分布会低估该类活动。

## 8. 变更记录

- v0（2026-10-21）：只读派生层 + 个人/团队视图 + 16 个测试；无 API/UI；无新表。
