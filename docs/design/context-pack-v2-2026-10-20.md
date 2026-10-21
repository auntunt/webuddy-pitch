# Context Pack v2：有来源、预算精确、可机器消费的上下文包

日期：2026-10-20。基线：`auntunt/webuddy-pitch` main（本地基线提交 `3220e3d`）。
上位设计：[可复用项目资产与版本化知识库](./project-knowledge-library-2026-10-20.md)（下称"项目库设计"）。
本轮实现：`tmh/context_pack.py` + CLI `tmh context --json|--pack|--source` + `tests/test_context_pack.py`。

## 1. 为什么要做

项目库设计 §6.6 对上下文有硬性要求：

> 完整原文与上下文摘要分离。上下文可分页或选取片段，但必须返回来源、覆盖范围、遗漏提示和读全文入口；
> 预算不足不能默默截掉用户需求、AC 或原始证据。原文不截断、不降质。

而 CLI 与智能体此前都走 `tmh/context.py::build_context`：

1. **只支持单项目**：`search(root, ...)` 只看一份 `graph.db` + 一份注册表；
2. **没有来源与版本**：输出只有标题和路径，agent 无法说明"这条来自哪个项目、哪个提交、哪版知识"；
3. **静默截断**：`text[:budget]` 直接切字符串，切点可能落在句子中间，且不告诉调用方少了什么——
   这正是设计里点名禁止的行为；
4. **不可机器消费**：只有文本，平台/评测/RSI 无法结构化地知道"这次到底喂了什么"。

平台层 `tmh/platform/project_library.py::context()` 已经实现了版本化、带来源的多项目检索，
但它与 CLI/agent 的日常入口是两套实现；本模块把"有来源、预算精确、可机器读"的契约下沉到
确定性工具层，并保持与旧入口兼容。

## 2. 契约（v2）

`assemble(sources, query, budget=8000, json_mode=False, require_all=False, log=True)`：

| 字段 | 含义 | 不变式 |
| --- | --- | --- |
| `schema` | 结构版本（当前 2） | 破坏性变更必须 +1 |
| `sources[]` | 每个来源：label/root/current/available/revision/knowledge_revision/error | 不可用来源必须显式出现，不能消失 |
| `items[]` | 每条：id/section/kind/title/domain/score/status/path/line/end_line/excerpt/full_text/source/source_version/knowledge_revision | id 以来源为前缀，两个项目的同名符号不会被合并 |
| `sections` | pages/flows/tables/code 的 count 与 bytes | 与 items 实际渲染一致 |
| `omissions[]` | 未展开项：id/section/title/reason/full_text | 只要有截断就非空；每条都能读全文 |
| `omissions_capped` | 文本视图省略显示的行数 | 只影响展示，不影响 JSON 的完整清单 |
| `complete` | 是否无遗漏且全部来源可用 | `true` 才表示"这次没落下" |
| `used`/`budget` | 实际字符数 / 上限 | `used <= budget`（除预算小到连页头都放不下） |
| `notice` | 固定声明 | 来源事实 ≠ 当前项目行为验证 ≠ 人工验收 |

预算分配：`usable = budget × 0.92`（预留页头/来源/遗漏提示/用法说明），
按 `pages 42% / flows 20% / tables 14% / code 16%` 分配到各节，再有余量按分数 spill-over。
**任何条目整条放入或整条不放入，绝不切开。**

## 3. 多来源语义

- 当前项目 `current=true` 排在前；参考来源紧随其后。
- 每条 id = `来源id:原始id`，同名类/表/页面跨项目不合并（项目库设计 §3、§6）。
- 每条带 `source_version`（Git HEAD）与 `knowledge_revision`（graph.db + 注册表 + 术语表的 sha256 前 12 位）。
- `--require-all`：任一来源不可用即报错；默认降级为 `available=false` + `complete=false`，
  绝不"空结果假装没有影响"（项目库设计 §9 反例）。

## 4. RSI 接口

每次组装写一条 `activity.jsonl`：

```json
{"ts": "...", "kind": "context", "text": "<query>", "budget": 8000, "used": 7302,
 "sources": [{"label": "oa", "revision": "...", "available": true}],
 "items": 12, "omitted": 3, "complete": false}
```

它让后续可以回答：哪些需求总是预算不足、哪些知识页从未被任何任务取用、
加预算是否真的提升了任务成功率——这是"多用户开发习惯 → RSI"的最小数据接缝。

## 5. 兼容与迁移

- `build_context()` 签名不变，仅把静默截断改成**带省略说明的截断**（说明计入预算），
  现有 913 个测试的调用方式不受影响。
- `tmh context` 默认仍走旧文本渲染；`--json / --pack / --source` 走 v2。
  下一轮（待平台回归确认）可把默认切到 v2，并让 `platform/agents.py` 的任务上下文也走 `assemble`。
- `project_knowledge.py` 的 `import resource` 加了 Windows 降级（无该模块时 `peak_rss_bytes=null`，
  构建不失败），便于在本机复跑快照流程。

## 6. 验收

`tests/test_context_pack.py`（12 项，全部通过）：

- 每条带来源/版本/知识修订/full-text 句柄；页面 → `tmh kb read`，代码 → `path:line-end`；
- 600 字符预算：`used<=600`、`complete=false`、遗漏清单非空且每条可读全文、文本含"未展开"；
- 大预算：`complete=true`、无遗漏；
- 多来源：id 不冲突、current 在前、两个来源都出现；
- 不可用来源显式出现；`require_all` 失败关闭；
- 输出确定性（两次组装逐字节一致）；
- 每次组装写 activity 记录；
- 旧 `build_context` 小预算下不再静默截断。

回归：`tests/test_tmh.py -k "context or knowledge or report_has"` 17 项通过。

## 7. 下一步（对应项目库设计阶段）

1. ✅ 平台任务上下文（`platform/agents.py`）已改走 `assemble`，运行记录里保存 `context` 回执
   （`runs/<id>/context.json` + run 输出行）；旧 `build_context` 作为异常/`TMH_CONTEXT_PACK=0` 回退。
2. ✅ v2 默认化：`tmh context` 默认输出 v2 文本，旧渲染降为 `--legacy`；`--json`/`--source` 始终走 v2。
3. 参考来源从"目录"升级为 `ReferenceBinding`（固定版本 + 模块范围 + 用途），与 `project_library` 的
   revision 对齐（G4 本地试点已验证模块级语义，平台表写入待服务器）。
4. 检索后端可替换：向量检索作为 `KnowledgeSearch` 的第二实现，不改变本契约。
5. 检索质量尺子已落地：`tmh/context_quality.py` + `tests/fixtures/context_golden.json`（26 条）+
   `tests/test_context_quality.py`；PPR 与参数网格实验均为负结果，默认 lexical 不变（见 `benchmarks/`）。
