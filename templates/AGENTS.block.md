## 维护 harness（tmh）

先理解业务流，再改代码，改完独立验证。`tmh` 指 `python3 .tmh/tool/tmh.py`。

### 按场景取知识
- 定位需求/缺陷：`tmh context "原文"` 找相关知识页和代码；理解业务链路：`tmh kb chain "需求"` / `tmh kb read <id>` 读原文；更多关系用 show、flows、impact、where。不要通读仓库。
- `.tmh/knowledge/` 是项目知识唯一来源，按原文读、引用页面 id，不另做摘要、技能或第二份笔记。过期页以代码为准，待确认页须核实；覆盖不足用 legacy-onboard，新增理解用 kb next/done 补入，代码变更用 knowledge-upkeep 修订。
- 业务需求预判：`tmh kb triage "原文"`。涉及资金/审批/口径、依据未经人确认或仍有未答问题，交人判断，不直接回复业务方。未知规则用 kb ask 记录，不猜；人通过 kb answer/平台写回答复后再修订，由人确认。
- 工单/构建失败用 tmh ticket / tmh build failure 对应业务流。凭据只放环境变量，不索要、不落文件；评论、流转、触发构建、通知默认演练，执行前征得用户同意。
- 需要查命令时读 `.tmh/docs/agent-commands.md`（源文件 `docs/agent-commands.md`）。

### 硬性规则
- 先契约后代码：tmh task new 写清要改变、必须保持、验收方式、受影响业务流；问题未答不动代码。
- **不改基线测试与验证配置**；可新增测试。旧测试确需改，写入契约，由人工确认后手工改。
- **没有验收标准（AC）不进实现**：契约第 4 节每条具备条款、L1–L4 层级、检查方式，由 tmh accept advance 检查。
- **完成前必须 tmh verify**（`--task <任务号>`，含入口路径检查），用 tmh flows --changed 核对触及业务流，写回契约验证记录；没跑过不得写通过。证据绑定具体提交，版本改变即失效。
- **关单只认用户确认**：自测/CI/合并不能关单；tmh accept confirm/close 只能由人执行，agent 最多推进待人工验收。实现与验收分离，改代码的会话不验收自身改动，交 acceptance-l2。
- 纠错走评审：用 tmh accept correct 记录方向/尺寸/分诊问题，达阈值提评审 PR 改技能，不只改会话记忆。
- 留下分析：tmh note finding/decision/question 记录关键发现、取舍、疑问；结论区分代码事实、【推断】、【待确认】，业务说明经人看过才标已确认。
- 对外接口/报表口径、状态流转、删除数据、数据库/中间件选型、不可替代第三方组件，需要人决定，停下询问。
- 不执行发布、推送、连生产库、删除数据。
- 改造项用 tmh items --set 更新 doing/done/blocked 与说明。
- Claude/Codex 钩子保护测试和验证配置、检查新增问题、拦危险命令、记录工具调用并提醒未验证改动。被拦按提示处理，禁止绕过；不得放宽保护清单和钩子。
