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
| CI | GitHub/GitLab/Jenkins 实际来源、必需检查名、完整 SHA 查询权限：待提供；支持 GitHub Actions、登记连接的 GitLab/Gitea；Jenkins 接口及自建验证见下文，客户联调待完成 |
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

Gitea 将 provider 改为 `gitea`，仓库只能为 `owner/repo`，required-check 对应 commit status context。部署方需限制能写入这些状态的 CI 身份；不把开发 Agent 自报状态作为可信 CI。GitLab 使用完整 SHA 下最新流水线的成功状态及具备相同 SHA/流水线绑定的必需 job；旧失败流水线保留在 CI，成功重跑可重新验证。GitLab 下游子流水线、GitHub Enterprise 当前不自动适配，使用前需按真实环境补齐。不会回退到另一仓库的绿色记录。

查询有时间、体积和分页上限，超限或异常受阻。失败、取消、跳过、缺失、未完成均不通过。MCP `webuddy_candidate_ci(candidate_id)` 和网页既有 CI API 查询当前精确提交；合并时服务端再次查询。本轮 GitLab/Gitea 是协议夹具验证，尚未连接客户真实 CI；需要提供实际产品版本、地址、仓库、必需检查、服务账号和可达网络进行联调。

协议依据：[GitLab pipelines](https://docs.gitlab.com/api/pipelines/)、[GitLab jobs](https://docs.gitlab.com/api/jobs/)、[Gitea combined status](https://docs.gitea.com/api/1.25/operations/repo-get-combined-status-by-ref/)。

### Jenkins 自建连接

新增 `provider=jenkins`，沿用同一候选 CI 查询与合并门禁。下列配置在当前开发代码中实现；实际构建验证记录见 JSHERP Jenkins 演练目录，不能把自建环境结果视为客户 Jenkins 已接通。

```json
{
  "company-jenkins": {
    "provider": "jenkins",
    "url": "https://jenkins.example.internal",
    "user_env": "WEBUDDY_JENKINS_USER",
    "token_env": "WEBUDDY_JENKINS_TOKEN",
    "projects": {"ERP": ["company/erp"]},
    "repositories": {
      "company/erp": {
        "remote_urls": ["ssh://git@git.example.internal/company/erp.git"],
        "jobs": {"erp-verification": ["ERP", "verification"]}
      }
    }
  }
}
```

项目 CI 配置填写同一个 connection、repository 和 required_checks。jobs 的数组是 Jenkins 文件夹与任务路径段，不是任意 URL。注册的 remote_urls 必须与 Git 插件实际 checkout 的仓库 URL 一致；别名应由运维显式登记。账号只需 Overall/Read 和相关 Job/Read；不授予 Build、Configure 或管理员权限。使用 API token，HTTPS 必须校验证书；私有 CA 安装到平台信任环境，不关闭校验。

读取 Git 插件 BuildData 的 remoteUrls 与完整 lastBuiltRevision.SHA1，再读取构建结果；不信任任务参数里的 GIT_COMMIT。每个必需任务选择最近100次中当前仓库/提交的最新构建。完成且 SUCCESS 才通过；UNSTABLE、FAILURE、ABORTED、NOT_BUILT、执行中、无记录、未知SCM或查询异常均受阻。较新构建没有可核对的 checkout 记录时，不借旧成功放行。

适用前提：Jenkins 使用 Git 插件 checkout，构建任务及必需检查由可信维护者管理。仅用 shell git clone、无 BuildData、下游聚合、特殊多仓库 checkout 需实际核对，不能自动声称兼容。配置连接只查询，不触发构建；候选需先同步到登记远端，由现有 Jenkins 流程构建。本地合并仍 `pushed=false`、`deployed=false`。

接口依据：[Jenkins Remote API](https://www.jenkins.io/doc/book/using/remote-access-api/)、[Git 插件](https://plugins.jenkins.io/git/)。

## 长期改造计划共用管理

个人连接可按 `read/content/execute/develop` 的交集使用改造计划读取、内容修订及执行管理能力，并非笼统只读。`--allow-writes`、`--allow-execution`、当前项目权限和受管隔离要求继续生效。实际工具、输入示例、冲突/幂等、重连与分页规则见 [长期改造管理](workbench-agent.md#长期改造管理本轮实现候选验收进展见进度记录)。

网页与MCP都指向同一 `#/projects/<project>/reforms/<plan_id>`；换客户端后按计划、请求和运行编号找回。业务验收、独立技术复核、合并及发布不包含在普通计划管理工具中。三个桌面宿主联调与浏览器工作区验收状态见实施证据，官方SDK协议通过不替代宿主实测。

## Cursor 项目接入

Cursor 与 Codex、Claude Code 共用 Webuddy 的工单、知识来源、候选、测试和人工验收规则。新版本默认初始化三个宿主；已有项目可补装：

```sh
python3 -m tmh install --repo /path/to/project --engines cursor
```

Windows 使用安装包的 `runtime\python\python.exe` 代替 `python3`。安装生成 `.cursor/skills/` 与 `.cursor/mcp.json`，共用项目 `AGENTS.md`；保留其他 MCP 服务和原有指令。Java 迁移、信创适配技能及参考材料一并安装。MCP 使用安装时的 Python 和项目绝对路径，无需 `sh`；移动项目或 Python 后重新执行安装刷新路径，并在 Cursor 重新加载 MCP。

- 本地 `tmh` MCP：读取当前项目的知识、代码来源、业务流及影响范围。
- 平台 `webuddy` MCP：沿用个人工具连接；执行 `webuddy config cursor`，把输出中的 `webuddy` 服务合入 Cursor 的 `mcpServers`。不要覆盖已有 `tmh` 或其他服务。令牌不写进项目配置，原生 Windows 个人凭据的既有限制仍适用。
- 处理真实任务前先调用平台工作目录预检，核对项目、仓库、版本和未提交改动；候选同步及验收沿用既有流程。宿主审批拒绝时停止对应操作，查询回执，不改审批策略。

这是 Cursor 本地开发和 MCP 接入，不等于平台已获得无人值守调用 Cursor 的能力。本次不安装模拟的 Codex/Claude 钩子，也不把提示词当作只读隔离。自动执行适配还需验证 Cursor CLI 的工具限制、取消回收、运行回执和用量；完成前不作为平台只读 Review 执行器。

验证边界：安装/刷新、中文空格路径、其他 MCP 配置保留、本地实际 stdio 和平台正式 SDK 读取已验证；实际 Cursor CLI 非交互调用遇到登录提示，宿主完整读写链路仍待验证。配置生成与协议测试不代表实际 Cursor 已完成业务任务。


## Webuddy 调用 Cursor Agent

这是平台执行器，区别于 Cursor 通过 MCP 读取 Webuddy。管理员在“设置 → 智能体”可配置内置 `cursor`，也可“添加执行器 → Cursor Agent”，设置模型和任务超时。平台原有项目执行器选择会展示它；受个人 Codex 隔离策略约束的连接仍只提供 Codex，不自动扩权。

先在**运行 Webuddy 的机器、运行 Webuddy 的系统账号**中安装并登录 Cursor Agent CLI。仅在另一台电脑安装 Cursor 编辑器，不能让服务器获得执行能力。按 [Cursor 官方安装说明](https://cursor.com/docs/cli/installation)安装，执行 `cursor-agent --help`，确认支持 `--print`、`--output-format stream-json`、`--sandbox enabled` 和 `--mode ask`，再执行 `cursor-agent login`。账号登录由本人完成，不把登录态、API Key 或个人路径提交仓库。

若官方安装只提供 `agent`，或 Webuddy 的服务 PATH 找不到命令，由主机维护者在外部数据目录的 `agents.json` 配置准确的绝对路径；此配置不进入客户程序包。例如以下占位路径须替换为本机实际位置，其他现有配置保留：

```json
{
  "cursor": {
    "bin": "/absolute/path/to/agent",
    "models": [],
    "defaults": {},
    "run_timeout": 1800
  }
}
```

Windows 使用对应可执行文件的绝对路径；本轮没有完成原生 Windows Cursor CLI 或 WSL 的真实模型联调，不把本机协议替身验证当作平台支持证明。命令与工作区必须能被 Webuddy 所在系统直接访问。

执行采用已有 Runner 的隔离工作树、运行日志、预算、超时和停止回执。只读任务使用 Ask 模式并要求启用 Cursor 沙箱。当前明确拒绝 fix/edit/kb/chart 写入任务：[官方无交互说明](https://cursor.com/docs/cli/headless)要求写入使用 `--force`，本接入不以此替代人工审批。因此当前支持分析、方案、问答和诊断，不宣称已接通 Cursor 自动改码。不添加 `--force`、`--yolo`、`--trust` 或 `--approve-mcps`，不修改用户的 Cursor 审批策略。需要登录、信任或工具授权时，应先由本人按 Cursor 规则处理；平台不自动批准。旧 CLI 不支持所需参数时会失败，不降级到无保护执行。

仅退出码为零且收到完整成功结果才记为执行成功。模型结果、会话编号、原始输出和停止过程随运行保存；成功执行仍不等于测试通过或业务验收。默认关闭 Cursor 会话自动续接与繁忙自动重试，恢复通过平台既有检查和新运行进行。已有 MCP、候选、人工验收和发布权限边界保持不变。
