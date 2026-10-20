# 验收闭环：验收状态机、分层验收、入口路径检查

AI 让改代码变快以后，团队卡在“写得快，却不敢合、不敢上线，关单也拿不出证据”。tmh 要补的就是这一层：

> **tmh 给传统 toB 老系统补上验收这一层：业务流证据、部署后分层验收、用户确认才关单。**

本文是这一层的契约。规则写在代码和钩子里，不靠提示词：`tmh/acceptance.py`（状态机）、`tmh/path.py`（入口路径检查）、
`tmh/guard.py`（拦住智能体替人确认或关单）、平台 `POST /api/tickets/<key>/accept`（平台上唯一的关单路径）。

## 1. 验收状态机

每个任务契约（`.tmh/tasks/T###-*.md`）都有一个验收状态。状态、历史和证据指针记在 `.tmh/acceptance/T###.json`，
契约头部的“验收状态”一行跟着同步，方便人读。

| 状态 | 含义 | 谁能推进到这里 | 进入条件（工具会检查） |
|---|---|---|---|
| `draft_contract` 草拟契约 | 契约在写 | `tmh task new` 自动 | — |
| `implementing` 实现中 | 可以动代码了 | 实现方 | 第 4 节每条 AC 都有**条款、层级（L1–L4）、检查方式**；从检查状态退回时必须写原因 |
| `verify_local` 本地验证通过 | 本地证据齐了 | 实现方或独立验收 | 最近一次 `tmh verify` 通过，且**入口路径检查**通过（见第 3 节）；图谱看不到的改动记成阻塞 `path_unverified` |
| `merged` 已合并 | 代码进了目标分支 | 任何人（或集成钩子，见第 6 节） | 写明 `--ref` 提交号或合并请求 |
| `deployed_awaiting_verify` 已部署待回测 | 部署到了可测环境 | 任何人（或集成钩子） | 写明 `--build` 构建号或版本 |
| `auto_verified` 自动证据齐全 | L1–L3 都有“通过”结果 | 独立验收 | 第 4 节每条 AC 的结果都是“通过”，没有 L4 条款，没有阻塞；否则只能去 `needs_human` |
| `needs_human` 待人工验收 | 证据不够，或有 L4 条款 | 任何人 | — |
| `user_confirmed_fix` 用户已确认 | 业务方或提报人确认修好了 | **只能是人** | `--who <姓名>`；在智能体会话里（`CLAUDECODE`、`CODEX_SANDBOX`、平台运行的 `TMH_RUN`）直接拒绝 |
| `closed` 已关闭 | 结束 | **只能是人** | **只能从 `user_confirmed_fix` 进入** |

合法的迁移（其他一律拒绝，并提示能去哪）：

```text
draft_contract → implementing → verify_local → merged → deployed_awaiting_verify → auto_verified → user_confirmed_fix → closed
                                    │             │               │                     │   ↑                   │
                                    └─────────────┴───────────────┴──→ needs_human ─────┴───┘                   │
verify_local / merged / deployed_awaiting_verify / auto_verified / needs_human / user_confirmed_fix → implementing（退回，写原因）
closed → implementing（人重新打开）
```

硬规则（不可削弱）：

1. **关单只认用户确认。** 实现方自测通过、CI 绿、已合并都只是证据，`closed` 只能从 `user_confirmed_fix` 进入，而这两步只能由人在自己的终端（`tmh accept confirm|close --who 姓名`）或平台“验收通过”上做。智能体执行这两条命令会被 Bash 钩子拦下，绕过钩子直接调也会因为环境变量被拒。
2. **没有验收标准不进实现。** `draft_contract → implementing` 检查第 4 节，缺条款、缺检查方式、缺层级都拒绝。
3. **“通过”要有证据。** 进 `verify_local` 要读到通过的 `verify-latest.json`；进 `auto_verified` 要每条 AC 的结果栏写着“通过”。

## 2. 分层验收（L1–L4）

每条 AC 标一个层级。默认规则：读 diff、契约、图谱就能证明的标 L1；能在独立环境用测试证明的标 L2；
必须在部署后的可测构建上再跑的标 L3；要真实库、真机、业务判断的标 L4。拿不准时往高标。

| 层 | 做什么 | tmh 抓手 | 本轮状态 |
|---|---|---|---|
| L1 契约与业务流核对 | diff 是否只做了契约里的事；AC 能不能检查；改动接上入口没有；扇出 | `tmh accept check`、`tmh accept path-check`、`tmh flows --changed`、`tmh impact`、技能 `acceptance-route` | **已做** |
| L2 独立环境复验 | 不改产品代码、不改基线测试，重跑特征测试和 `tmh verify` | `tmh verify --task`、钩子锁基线、子代理 `independent-verifier`、技能 `acceptance-l2` | **已做** |
| L3 部署后回测 | 等部署事件，在同一可测构建上回测同一批 AC | 状态 `merged`/`deployed_awaiting_verify`，字段 `ref`/`build_id` | **预留**：状态和字段已有，事件自动推进未做（第 6 节） |
| L4 真人/业务方确认 | 列清步骤、数据前提、找谁确认 | 契约第 4、6 节；状态 `needs_human` | **清单约定**：写在契约第 4 节，L4 条款存在时不能进 `auto_verified` |

## 3. 入口路径检查（`tmh accept path-check` / `tmh verify --task`）

要拦的是一种常见的假绿：在真实实现旁边另写一套（新方法、新类），测试对着新的那套跑通了，用户真正调用的入口却根本没走到它。

做法：

1. 读契约第 5 节“入口”一行里反引号写的入口（`LeaveController.list`、`GET /leave/list` 或业务流 id），在业务流里找到对应的调用链；找不到就失败。
2. 取相对基线的改动行（`git diff -U0`），逐块判断：
   - 落在入口调用链上的方法、或链上的 MyBatis 语句里 → 接上了；
   - 落在链上方法按名调用、但图谱没展开的方法里（常见于工具方法）→ 算接上，提示用 `tmh impact` 看扇出；
   - 落在别的业务流的方法里 → 断点：改到了契约外的业务，或者契约入口没写全；
   - 落在任何入口都到不了的方法里 → 断点：**平行实现，写了但没接上**；
   - 测试和文档不算接上：只改了测试或文档就失败。
3. 图谱看不到的改动不算通过也不算失败，单独列给人确认（L4），并记成阻塞 `path_unverified`，挡住 `auto_verified`：
   前端（.vue/.ts/.js）、配置（yml、properties、非映射 XML）、方法外的声明（字段、常量、新类型）、删掉的文件。

做不到的地方（如实标出，不假装）：

- 反射、配置表、规则引擎分派的入口，图谱追不到。这时把入口写成能追到的那一层，或把相关 AC 标 L4。
- 前端没有调用链图谱。JeecgBoot 这类前端为主的工单，路径检查只能把前端改动列给人看。
- 按方法名匹配：同名重载、接口多实现时可能偏宽。偏宽的结果是“接上”，所以它不能替代 L2 测试。

T001 例子：入口 `LeaveController.list`，改 `LeaveService.list` 和 `LeaveMapper.xml` 的 `selectPage` 都在链上，通过；
如果新增 `LeaveService.listByStatus` 但控制器没调用它，检查报“平行实现”；控制器改成调用它之后，同一个方法就算接上了。

## 4. 角色拆分

| 角色 | 允许 | 禁止 |
|---|---|---|
| 实现（`legacy-feature` 等技能、平台的 fix 运行） | 改产品代码、补特征测试、填契约结果栏、推进到 `implementing`/`verify_local` | 确认、关单；把“自测通过”写成“用户确认” |
| 独立验收（技能 `acceptance-l2`、子代理 `independent-verifier`） | 跑 L1/L2、写证据、推进到 `verify_local`/`needs_human`/`auto_verified`、退回实现、记纠错 | 改产品代码和测试；合并；确认、关单 |
| 人（开发负责人、业务方、提报人） | `user_confirmed_fix`、关单、L4 签字、策略变更 | — |

## 5. 平台工单与状态机的对应

平台看板仍用原来六个状态，不另起一套名字，对应关系如下：

| 平台状态 | 契约验收状态 |
|---|---|
| 新建 / 分析中 / 待确认 | `draft_contract` |
| 处理中 | `implementing` |
| 待验证 | `verify_local`、`merged`、`deployed_awaiting_verify`、`auto_verified`、`needs_human` |
| 已关闭 | `user_confirmed_fix` + `closed`（“验收通过”一步完成，记录验收人） |

平台上的同样两条硬规则：

- **关单只能走“验收通过”**：改状态接口拒绝直接改成“已关闭”，工单页状态下拉里也不再出现“已关闭”。
- **方案没有验收标准，不进入自动改代码**：方案（plan）要输出“验收标准”一节，机器读的 `tmh-plan` 里带 `ac` 列表；自动流程读不到 AC 就停在方案，等人补。人手动点“改代码”不受影响，那是人做的决定。

## 6. L3 预留：合并和部署事件

本轮没有做事件自动推进，但字段和状态已经备好，集成钩子以后只需调用：

```sh
tmh accept advance T001 --to merged --ref <提交号或合并请求>              # GitLab/GitHub 合并事件
tmh accept advance T001 --to deployed_awaiting_verify --build <构建号>    # Jenkins 部署成功事件
```

部署后超时没有回测结果，或环境不可达，转 `needs_human`。这些事件目前由人或脚本手工调用。

## 7. 按可测构建组织验收（约定）

验收不按工单关闭日或合并日散着催，按“一次可测构建”成组：

- 部署时用 `--build` 把任务记到构建上；`tmh accept status --build jenkins-42` 列出这个构建里所有任务及其状态和阻塞。
- 每个构建一页 `.tmh/acceptance/builds/<构建号>.md`，由人或通知脚本按这个格式写：

```markdown
# 构建 jenkins-42（2026-10-15 部署到测试环境）
| 任务 | AC | 层级 | 回测结果 | 证据 |
|---|---|---|---|---|
| T001 | A1–A5 | L1/L2 | 通过 | .tmh/reports/verify-…md |
| T001 | A6 真实库筛选 | L4 | 待业务方 | — |
汇总：可标“自动证据齐全” 0 个；需要人确认 1 个（T001：张三）
```

- 群通知用一句话：“构建 #42 可验收：T001、T014；其中 2 条需要业务确认”。自动发通知属于 L3，本轮不做。

## 8. 纠错回流

误分诊、方向不对、改太多，都用 `tmh accept correct T001 --kind wrong-direction|too-big|misroute --note "…"` 记进
`.tmh/acceptance/corrections.jsonl`。同一类累计到阈值（默认 3，`.tmh/config.json` 的 `correction_threshold`）时命令会提示：
**提一个评审 PR 修改 `skills/acceptance-l2` 的反模式检查项**。不要只改会话记忆，也不要自己合并改行为的变更。

## 9. 旧契约迁移

旧契约照常能读，只在推进状态时要求补齐：

1. 头部加一行 `- 验收状态：draft_contract（草拟契约）`（不加也行，第一次推进时会自动写入）。
2. 第 4 节表格在“验收条款”后插一列“层级”，每条填 L1–L4。
3. 第 5 节“入口”一行把入口写进反引号。
4. 已经做完的任务按实际情况补状态：`tmh accept advance T001 --to implementing`，跑 `tmh verify --task T001` 后到 `verify_local`，再按需要推进到 `needs_human` 等人确认。

T001 改前（`docs/e2e-T001-contract.md`）：

```markdown
- 状态：待人工验收

| # | 验收条款 | 检查方式（自动化测试 / 命令 / 人工） | 结果 |
|---|---|---|---|
| A1 | 不传 status 时 `service.list(page)` 仍调用 mapper 的分页区间 … | LeaveListFilterTest（旧代码先跑通） | 通过（mvn test，LeaveListFilterTest） |
| A6 | 真实库上筛选结果正确 | 需达梦/Oracle 环境，本仓库无库 → 人工验收 | 未验证（无数据库环境，需人工） |

- 入口：`LeaveController.list` — src/main/java/com/acme/oa/controller/LeaveController.java:20（GET /leave/list，新增可选参数）
```

T001 改后：

```markdown
- 状态：待人工验收
- 验收状态：needs_human（待人工验收）

| # | 验收条款 | 层级 | 检查方式（自动化测试 / 命令 / 人工） | 结果 |
|---|---|---|---|---|
| A1 | 不传 status 时 `service.list(page)` 仍调用 mapper 的分页区间 … | L2 | LeaveListFilterTest（旧代码先跑通） | 通过（mvn test，LeaveListFilterTest） |
| A5 | 新增 SQL 片段无 Oracle 专有写法（达梦兼容） | L1 | tmh verify 的兼容检查 | 通过（新增代码无新兼容点） |
| A6 | 真实库上筛选结果正确 | L4 | 业务方在达梦测试库按 PENDING/APPROVED 各查一次，对照库内条数 | 未验证（无数据库环境，需人工） |

- 入口：`LeaveController.list` — src/main/java/com/acme/oa/controller/LeaveController.java:20（GET /leave/list，新增可选参数）
```

```text
$ tmh verify --task T001                  # 入口路径：LeaveController.list → get-leave-list，改动都在链上
$ tmh accept advance T001 --to verify_local
$ tmh accept advance T001 --to needs_human --note "A6 需要真实库"
$ tmh accept confirm T001 --who 张三 --note "测试库查过"   # 人在自己的终端
$ tmh accept close T001 --who 张三
```

## 10. 与强制工作法的对照

| 工作法条款 | 落在哪里 |
|---|---|
| 1. 反馈 → Issue → PR → 部署 → 用户确认 | 状态机主线 `draft_contract → … → user_confirmed_fix → closed`；平台工单同样走到“验收通过” |
| 2. 只有用户确认能关单 | `closed` 只能从 `user_confirmed_fix` 进；这两步要 `--who` 姓名，智能体会话直接拒绝，Bash 钩子拦命令；平台改状态接口拒绝直接关单 |
| 3. 无 AC 不进实现队列 | `draft_contract → implementing` 检查 AC 条款/层级/检查方式；平台自动流程读不到方案里的 AC 就不进入改代码 |
| 4. 纠正回写 Issue，PR 对照 AC | 退回实现必须写原因（记入历史）；`acceptance-l2` 要求结论逐条对照第 4 节 AC |
| 5. 纠错回流走评审 PR | `tmh accept correct` 记录，达阈值提示提评审 PR 改 `skills/acceptance-l2`，不改会话记忆 |
| 6. 自动化可标记，关闭与策略变更要人批 | 智能体可推进到 `needs_human`/`auto_verified`，确认和关单只能人做 |
| 7. CI 通过 ≠ 评审 ≠ 合并 ≠ 部署 ≠ 复测 ≠ 用户确认 | 分成 `verify_local`、`merged`、`deployed_awaiting_verify`、`auto_verified`、`user_confirmed_fix` 五个不同状态，各有证据 |

## 11. 暂不做（deferred）

| 项 | 为什么往后放 |
|---|---|
| L3 事件自动推进（合并/部署 webhook → 状态） | 先把状态和字段用起来，接哪家 CI 由项目定 |
| 构建验收清单自动生成、群通知 | 依赖 L3 事件 |
| 日志/工单自动生成排查 Issue、长周期巡检 | 偏运行时值班，不是维护 harness 的第一卖点 |
| E2E 自愈与语义裁决 | 容易做成假绿，要先有稳的 L1–L3 |
| 通用的等待/唤醒智能体运行时 | 不把 tmh 做成另一个智能体操作系统 |
| 前端调用链图谱 | 路径检查目前把前端改动列给人确认 |

## 命令速查

```sh
tmh task new "标题" --kind bugfix                      # 新契约，验收状态 draft_contract
tmh accept check T001                                   # AC 是否完整（条款/层级/检查方式）、入口
tmh accept advance T001 --to implementing               # 开工
tmh accept path-check T001 [--entry X]                  # 改动是否接上契约入口
tmh verify --task T001                                  # 独立验证 + 入口路径检查
tmh accept advance T001 --to verify_local|merged|deployed_awaiting_verify|auto_verified|needs_human [--ref|--build|--note]
tmh accept reject T001 --note "原因"                     # 退回实现
tmh accept confirm T001 --who 姓名 / close T001 --who 姓名   # 只能由人
tmh accept status [T001] [--build 构建号]
tmh accept correct T001 --kind too-big --note "…"
```
