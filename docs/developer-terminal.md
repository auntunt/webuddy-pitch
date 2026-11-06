# 开发人员主导的终端协作

选工单 → Agent 分析和追问 → 负责人确认需求、设计与测试方案 → 开发 → 固定候选 → 测试、AI Review、CI → Leader 复核 → 负责人确认合并。

AI 负责整理和执行，Leader 负责独立复核。Leader 可以在团队工作台或个人终端查看、逐项记录、批准和退回。负责人不能批准自己的候选。批准只对当前证据有效，返修、需求或证据变化后必须重新检查。

## 接入与选择任务

在网页“我的工具连接”创建“协作开发”连接，选择授权项目。已有只读、协作、执行连接不会自动升级。下载客户端并按页面命令重新安装（包含 `--force-reinstall`，避免同版本包被 pip 跳过），再把生成的 MCP 配置放进 Codex、Claude Code 等支持 MCP 的终端。已运行的 MCP 进程需重连后使用新工具。

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


## 客户接入核对与两机演练

以下待填内容不代表已接入甲方设备；真实人工确认由对应人员执行。

| 核对项 | 现场填写 / 当前缺口 |
|---|---|
| 平台主机 | 系统、CPU、内存、磁盘、数据目录、服务账号、固定代码 SHA：待提供 |
| 杭州开发终端 | 系统、Python、Codex/Claude Code、MCP 版本、个人账号：待提供 |
| 网络 | VPN/HTTPS 地址、访问白名单、Git 与模型出口、负责人：待提供 |
| 怀柔项目 | 正式仓库、登记仓库、基线分支、源码与数据副本授权：待提供 |
| CI | GitHub/GitLab/Jenkins 实际来源、必需检查名、完整 SHA 查询权限：待提供；支持 GitHub Actions、登记连接的 GitLab/Gitea；Jenkins 尚未适配 |
| 业务责任 | 需求确认人、开发负责人、独立 Leader、业务验收人、推送/发布负责人：待提供 |
| 模型 | 实际供应商/网关、模型与配置、发送范围、用量/账单依据：待提供；演示点数不是费用 |

选择实际工作方式后填写，不默认替客户选择系统：

| 位置 | A：开发者本地 Agent + MCP | B：平台已登记执行环境 |
|---|---|---|
| 代码修改 | 开发者电脑的授权仓库 | 已登记且有执行权限的隔离工作区 |
| 模型调用 | 开发者宿主已配置通道 | 平台执行器已配置通道 |
| 构建测试 | 本机结果可作资料；正式证据仍走候选验证门禁 | 登记测试环境执行并保存回执 |
| 候选与证据 | 推送候选分支后，将精确提交同步进平台登记仓库，再登记候选 | 固定提交登记候选，保存原始报告 |
| 正式远端与发布 | 负责人确认本地合并后，由项目指定 Git 维护者推送正式远端，项目既有 CI/CD 负责发布 | 相同；本地合并回执仍为 pushed=false、deployed=false |

现场逐项记录时间、操作者、任务、完整提交、请求编号和证据链接：连接 → 读取授权真实任务 → 本人确认当前修订 → 开发 → 同步准确提交 → 登记候选 → 验证 → 指定 Leader 复核 → 负责人确认合并 → Git 维护者推送 → 核对正式远端 SHA。Webuddy 自身 CI 不能代替怀柔项目 CI。

断线或超时：先查询原请求回执、候选和真实 Git 状态；结果未知时不换请求号重试登记或合并。条件恢复后复验，产生新证据；旧未执行记录保留。现场演练目前未完成，最小条件是可达设备、授权账号/仓库、实际测试配置及本人参与；先用隔离任务验证恢复，不能在真实任务上代人批准。

## 确认后选择系统执行或本地执行

新选择的协作任务，在确认稿通过后，由负责人本人记录执行方式：

```sh
# 二选一，只记录交接，不启动模型或修改代码
webuddy develop ERP-1 --action execution --mode system
webuddy develop ERP-1 --action execution --mode local
```

执行选择绑定当前确认修订和登记仓库的完整基线。需求变化后选择失效，不能继续开发或登记旧候选。运行中不可切换。请求编号可追溯，重复请求不重复执行。已有历史会话保持兼容；建议在下一轮确认后补记执行选择。

| 选择 | 下一步 | 代码与模型位置 |
|---|---|---|
| system | 显式调用原有 `run_start` 的 plan，再按当前方案门禁启动 fix；查询原运行回执 | 平台现有 Codex/Claude Code 执行器及其登记环境 |
| local | 先完成下面的目录核对，再由当前工具开发；同步准确提交后 `candidate_submit`、`candidate_verify` | 开发者实际工作目录；使用 Cursor/Codex/Claude Code 自己的模型配置 |

任务继续保持暂停自动流转，选择 system 不等于立即释放自动流转。项目已经开启原有自动流程且连接有执行权限时，可再明确运行 `webuddy hold ERP-1 --release --request-id <唯一编号>` 交回系统；读取回执和运行记录，未产生运行时按项目开关与缺口处理，不宣称已开工。回答问题、确认方案、选择执行方式均不启动模型。系统路径复用原有执行权限、隔离配置和计划门禁；不因接入 MCP 扩大权限。候选复核、负责人合并与发布继续分别执行。

### 在开发者电脑核对工作目录

```sh
webuddy preflight ERP-1 --directory /absolute/path/to/checkout
```

MCP 提供同一只读检查：`webuddy_workspace_preflight(ticket, directory)`。`directory` 必须来自开发工具当前实际工作区，不能使用平台返回的服务器路径，也不能猜目录名。CLI 返回非零或 MCP 返回 `ready=false` 时先处理差异。

检查读取真实 Git 根目录、worktree 的 Git 目录、分支、完整 HEAD、全部已跟踪与未跟踪变更，并与负责人选择时固定的起点及平台登记远端核对。SSH/HTTPS 形式的同一已支持仓库可匹配；无登记远端、未知地址格式或不同仓库均不能自动认定相同。检查不会拉取、切分支、重置、清理或提交文件，也不输出本地远端中的令牌。

知识修订与参考来源单独显示。没有对应当前 HEAD 的就绪知识修订时明确列出差异；由系统原有知识构建流程补齐，或先由负责人核对来源。知识就绪不等于业务规则正确。已开发后的 HEAD 通常不同于初始版本，不能靠重置代码让检查变绿；核对现有工作并按固定基线提交候选。

这是开工快照核对，不是对外部编辑器的强制沙箱，也不能证明开发者之后没有更换目录。候选提交仍由服务器核对完整提交、基线、确认契约和验收标准，测试、Review 和合并门禁继续生效。

客户端升级后重新安装下载包并重连 MCP，才能加载新预检工具。原生 Windows 的个人 MCP 凭据保护仍未支持；本次不绕过该限制，Git 预检可在隔离测试中单独验证。客户 Cursor 桌面实际连接与真实两机业务链路需现场验证，协议夹具通过不等于现场完成。


## 网页与 MCP 获取同一份交付依据

任务详情「验收依据」可下载完整 JSON。`GET /api/tickets/<key>/delivery`、MCP `webuddy_delivery_get(ticket)` 和 `webuddy delivery ERP-1` 使用同一只读数据组装逻辑，遵守当前租户和项目权限。旧 MCP 进程需在升级客户端后重连，才能发现新增工具。

内容包括原始需求、终端需求/设计/测试方案与确认修订、完整运行产出和差异、基线与候选验证报告、逐项证据原文、候选提交、技术评估、人工决定、合并历史及 CI 配置。没有生成的内容保持缺失；历史报告不自动变成当前通过。导出包 `current_validity=not_checked`、`ready_to_merge=null`，不是可执行批准凭证。当前验证与复核门禁仍在候选详情实时核对，MCP 不替人作决定。文件可能包含项目源码和业务资料，只在授权人员间保存和传递。

查看顺序：先看已确认的业务预期与测试方案，再看同一候选的实际检查、未执行/受阻/未覆盖项，最后由指定人员技术复核和业务验收。总测试数不替代逐条要求；需求确认、技术通过、业务验收和生产发布分别判断。

## 私有 Git 与 CI

平台已有本地 Git、隔离工作区、候选 ref、固定提交核对和本地主干合并。远端同步支持 GitHub 与自建 SSH Git；自建仓库使用 `ssh://git@host/path/repo.git`，按现有仓库配置登记部署公钥和固定主机指纹。平台不是 Git 托管服务。本地合并仍返回 `pushed=false`、`deployed=false`，正式推送和发布由指定维护者及项目原有流程承担。

CI 仓库来源独立配置。GitHub Actions 沿用 `--repository owner/repo --required-check NAME`。GitLab/Gitea 由运维在租户数据目录写入 `ci-connections.json`，文件只允许平台运维修改；凭据只通过服务环境变量注入，不能写入项目配置、Git 或报告。示例为占位值：

```json
{
  "intranet": {
    "provider": "gitlab",
    "url": "https://git.example.internal",
    "token_env": "WEBUDDY_INTERNAL_CI_TOKEN",
    "projects": {"ERP": ["team/subgroup/repo"]}
  }
}
```

只允许 HTTPS，保留系统证书校验；企业 CA 安装到服务的受信任证书环境，不关闭 TLS 校验。拒绝跳转。运维明确授权连接可访问的项目与仓库；项目管理员不能通过 API 指定任意地址或读取凭据。修改连接时暂停合并，使用现有 `.project-ci.lock` 独占锁并原子替换配置，完成后重新读取 CI。

项目管理员在本人终端执行并确认：

```sh
webuddy ci-config ERP --provider gitlab --connection intranet \
  --repository team/subgroup/repo --required-check business-tests --required-check regression
```

Gitea 将 provider 改为 `gitea`，仓库只能为 `owner/repo`，required-check 对应 commit status context。部署方需限制能写入这些状态的 CI 身份；不把开发 Agent 自报状态作为可信 CI。GitLab 使用完整 SHA 下最新流水线的成功状态及具备相同 SHA/流水线绑定的必需 job；旧失败流水线保留在 CI，成功重跑可重新验证。GitLab 下游子流水线、Jenkins、GitHub Enterprise 当前不自动适配，使用前需按真实环境补齐。不会回退到另一仓库的绿色记录。

查询有时间、体积和分页上限，超限或异常受阻。失败、取消、跳过、缺失、未完成均不通过。MCP `webuddy_candidate_ci(candidate_id)` 和网页既有 CI API 查询当前精确提交；合并时服务端再次查询。本轮 GitLab/Gitea 是协议夹具验证，尚未连接客户真实 CI；需要提供实际产品版本、地址、仓库、必需检查、服务账号和可达网络进行联调。

协议依据：[GitLab pipelines](https://docs.gitlab.com/api/pipelines/)、[GitLab jobs](https://docs.gitlab.com/api/jobs/)、[Gitea combined status](https://docs.gitea.com/api/1.25/operations/repo-get-combined-status-by-ref/)。
