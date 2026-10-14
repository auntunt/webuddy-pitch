## 维护 harness（tmh）

本仓库是一个需要长期维护的 toB 业务系统，由 tmh harness 辅助维护：先弄清业务流，再改代码，改完独立验证。
工具：`python3 .tmh/tool/tmh.py <命令>`（下文简写 `tmh`）。

### 知识优先：先查知识库，再读代码
本项目有一份持续维护的**项目知识库** `.tmh/knowledge/`（知识图谱 + Wiki）：总览 `index.md` → 业务域 `domains/` → 业务流 `flows/` / 业务对象 `entities/` / 代码模块 `modules/`，以及术语表 `glossary.md`、决定、坑、待确认问题。每页上半部分是工具从代码抽取的事实（带 文件:行号），下半部分是经整理的业务理解。**不要通读仓库**，那样既不准又浪费 token。

1. `tmh status`、`tmh kb status`：看基线、进行中的任务契约、知识库覆盖与过期情况。知识库不存在或覆盖很少时，先用 `legacy-onboard` 技能建立。
2. **任务开始先运行 `tmh context "<需求或问题原文>"`**：取出相关的知识页、业务流、表和代码位置。再用 `tmh kb chain "<需求>"` 读这条业务链路（业务域 → 业务流 → 表）的**知识页原文**，或 `tmh kb read <id>` 读指定页面，然后才打开具体文件。
   知识库是项目知识的唯一来源：按原文读、按原文引用（页面 id），**不要另做摘要、技能或第二份笔记**，每多一次转述就多丢一次信息。
3. 需要更多时：`tmh kb show <类|方法|表|URL>` 看图谱关系（调用方、被调用方、读写哪些表、属于哪条业务流）；`tmh flows <id>` 看完整调用链；`tmh impact <目标>` 看影响面；`tmh where <关键词>` 兜底搜索。
4. 页面标“过期”说明代码已变，以代码为准；标“待确认”说明还没经人确认，结论要核实。
5. **业务方的需求或问题先做预判**：`tmh kb triage "<原文>"` 给出能不能做、把握多大、依据哪些页面。涉及资金、审批、口径，依据还没经人确认，或相关页面有未答复的问题时，结论一律是“需要人判断”：把答复草稿交给人，不要直接回复业务方。知识库没写、代码也说不清的业务规则用 `tmh kb ask "<问题>" --pages <id> --to <要问谁>` 记下来，**不要猜**；业务方的答复由人用 `tmh kb answer` 或平台写回，智能体再据此修订页面，最后由人确认。
6. 弄清楚了知识库没写的东西，顺手补上（`tmh kb next --page <id>` → 写 → `tmh kb done <id>`）；改完代码用 `knowledge-upkeep` 修订过期页面。知识库越用越准，后续任务越省。

### 按工作类型使用技能
| 工作 | 技能 |
|---|---|
| 第一次接手、整体分析项目、建立/补全知识库 | `legacy-onboard` |
| 梳理/讲解业务流，出可视化报告 | `business-flow` |
| 老项目上实现新需求、改缺陷 | `legacy-feature` |
| 改完代码后增量更新知识库（修订过期页面） | `knowledge-upkeep` |
| 信创评估、出改造方案 | `xinchuang-assess` |
| 执行信创改造工作项（数据库/中间件/操作系统/架构/国密） | `xinchuang-migrate` |
| .NET Framework 迁移到 .NET 8+ | `dotnet-modernize` |
| 按工单开工、构建失败、Sonar 问题、查团队文档、发群通知 | `ops-tools` |

### 运维工具（工单、构建、质量、文档、通知）
团队的 Jira/禅道/GitLab/Jenkins/SonarQube/Confluence/群机器人通过 tmh 接入（`tmh int list` 查看），智能体也可以用 MCP 服务 `tmh` 直接调用。
有工单号先 `tmh ticket <号>`，构建失败先 `tmh build failure`，它们会把外部信息对应到知识库里的业务流。凭据只在环境变量里，不要索要或写进文件；评论、流转、触发构建、发通知默认只演练，执行前先征得用户同意。

### 硬性规则
- **先契约后代码**：新需求和改造任务先用 `tmh task new` 写清“要改变 / 必须保持 / 验收方式 / 受影响的业务流”，契约里的问题没有答案前不动代码。
- **不改基线测试与验证配置**：钩子会拦截。新增测试可以；旧测试确需修改时写进契约，由人工确认后手工改。
- **完成前必须 `tmh verify`**，并用 `tmh flows --changed` 核对实际触及的业务流，结果写回任务契约“验证记录”。没有运行过的检查不能写成“通过”。
- **把分析过程留下来**：关键发现、取舍、疑问用 `tmh note finding|decision|question "<一句话>"` 记录，团队会在报告里看到。
- **区分事实与推断**：结论标明是读代码得到的事实、【推断】，还是需要业务方回答的【待确认】。业务说明只有人看过才能标“已确认”。
- **需要人决定的事要停下来问**：改变对外接口或报表口径、改变状态流转、删除数据、数据库与中间件选型、无法替代的第三方组件。
- 不执行发布、推送、连生产库、删除数据的操作。
- 改造工作项要更新台账：`tmh items --set <ID> --status doing|done|blocked --note "<做了什么/为什么>"`。

### Codex 说明
- `.codex/hooks.json` 配置了与 Claude Code 相同的检查：改文件前保护基线测试，改完检查新引入的问题，拦截危险命令，有改动未验证时结束前提醒；每次工具调用都会记入分析过程。被钩子拦下时按提示调整，不要绕过。
- `.codex/agents/` 里有知识库撰写（kb-writer，可并行）、只读勘察、影响分析、SQL 改写、独立复核子代理，大范围阅读和批量撰写交给它们，主会话只保留结论。

### 常用命令
```
tmh context "需求原文"               # 任务开始先查：相关知识页、业务流、表、代码位置
tmh kb build | status | next | done <id> | show <名称>   # 知识库：构建/增量更新、覆盖情况、领取任务、校验入库、查图谱
tmh kb chain "需求" | read <id>…      # 读业务链路 / 指定页面的原文
tmh kb triage "需求" [--record] | questions | ask "问题" --pages <id> --to <人>   # 需求预判、待答问题（答复由人 tmh kb answer <号> "原话" --who <姓名>）
tmh kb metrics      # 少找人统计；人认为预判不对时由人 tmh kb overrule <预判编号> --who <姓名> --reason "…"
tmh status | flows [关键词] [--changed] | report | note finding|decision|question "…"
tmh where 关键词 | impact 目标 | task new "标题" --kind feature | baseline | verify
tmh assess | items [-v]            # 有信创等改造目标时
tmh ticket 工单号 [--task] | build failure [job] | quality | doc search 词 | trace 工单号   # 运维工具
tmh int list | types -v | add | test   # 运维工具接入
```
