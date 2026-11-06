# 开发人员主导的终端协作

选工单 → Agent 分析和追问 → 负责人确认需求、设计与测试方案 → 开发 → 固定候选 → 测试、AI Review、CI → Leader 复核 → 负责人确认合并。

AI 负责整理和执行，Leader 负责独立复核。Leader 可以在团队工作台或个人终端查看、逐项记录、批准和退回。负责人不能批准自己的候选。批准只对当前证据有效，返修、需求或证据变化后必须重新检查。

## 接入与选择任务

在网页“我的工具连接”创建“协作开发”连接，选择授权项目。已有只读、协作、执行连接不会自动升级。下载客户端并把生成的 MCP 配置放进 Codex、Claude Code 等支持 MCP 的终端。

可直接对 Agent 说：

> 列出 ERP 待办，让我选择本轮任务。逐个读取完整需求和相关代码，提出设计与测试方案；用终端提问功能分批向我提问，提供选项并允许自由回答。未知事项不要替我猜。保留客户已确认的验收要求，完成问答后展示确认稿，等我本人确认再开发。

MCP 顺序是 `tickets_list`、`ticket_get`、`development_start`、`development_propose`、`development_answer`、`development_get`。每个任务单独保存修订和原始回答，可以中断后恢复。问题由当前 Agent 分析产生；提问界面由 Codex/Claude Code 宿主提供，并非服务端直接弹出终端界面。

## 负责人确认

以下命令由本人在交互终端运行。使用个人账号登录；密码不回显，密码与会话不保存到 MCP 配置。不要让 Agent 代输确认。

```sh
webuddy develop ERP-1 --action status
webuddy develop ERP-1 --action ask
webuddy develop ERP-1 --action confirm
```

`ask` 可直接回答未决问题；也可以在 Agent 对话中回答，由 MCP 记录。`confirm` 显示完整确认稿，要求输入任务和摘要。修改来源、问题或回答后，旧确认失效。开发确认不等于客户业务验收。

## 开发、测试与 CI

Agent 使用自己的已授权开发能力修改代码，再通过 `candidate_submit` 登记固定提交，通过 `candidate_verify` 发起平台验证。提交必须已存在于登记项目仓库中；需要远端同步时由开发工具按项目既有 Git 权限同步候选分支。

平台原有执行隔离要求继续生效。协作开发连接不授予宿主机或项目执行权限；缺少隔离配置时会拒绝执行，不能用更换工具名称绕过。

本仓库已有 GitHub Actions CI。业务项目需由管理员配置实际仓库和必须通过的检查名称，例如：

```sh
webuddy ci-config ERP --repository your-org/erp --required-check backend-tests --required-check frontend-tests
```

名称必须与实际 Actions 检查名称一致。候选分支需先推送到配置仓库以触发该提交的 CI。MCP 的 `candidate_ci` 可读取检查结果。服务端在合并时重新查询完整提交；缺失、失败、跳过、取消和未完成都不算通过。私有仓库使用服务端已有 GitHub 访问凭据，凭据不进入报告。

## Leader 复核与负责人合并

在团队工作台为任务分配负责人和另一位复核人（Leader）。Leader 查看完整差异、AI Review、测试结果、固定版本预览与逐项证据，再决定：

```sh
webuddy develop ERP-1 --action assess --candidate-id 12
webuddy develop ERP-1 --action review --candidate-id 12
# 发现问题时：
webuddy develop ERP-1 --action reject --candidate-id 12
```

`assess` 记录每项实际结果及依据，允许 `unknown`；未验证不能改成通过。`review` 批准当前证据包；`reject` 记录退回原因。AI 的技术结论不能替代 Leader 的个人批准。

Leader 批准并且必需 CI 通过后，负责人再次核对并输入确认短语：

```sh
webuddy develop ERP-1 --action merge --candidate-id 12
```

合并只对当前任务、固定候选和证据生效。主干移动、证据变化、责任人变化或 Leader 退回都会阻止旧确认继续使用。未选择终端协作的旧任务保持原有合并规则。

**合并结果是平台登记仓库的本地主干快进。**回执明确返回 `pushed=false`、`deployed=false`。推送远端、项目 CD 和客户业务验收分别执行；本功能不自动发布业务项目。Webuddy 平台自身仍按项目约定验证后发布 43 测试站，阿里云生产需用户另行指定。

请求超时后先读取任务、候选和原请求回执，不能直接换编号重复写入。终端会在写入前显示请求编号；没有确认结果时保留这个编号用于核对。
