# Webuddy CLI 与 MCP：让编程助手接入工作台

Claude Code、Cursor、Codex 可以通过 CLI 或 MCP 读取 Webuddy 里的需求、知识与证据，并在个人授权范围内创建暂停执行的任务、留下工作消息。它们与网页使用同一份工单数据。工具标签不能代替个人身份，也不能用换标签的方式自审。

当前 MCP 使用官方 Python SDK 的 **stdio** 传输：编程助手启动一个轻量桥接进程，由它连接已经运行的 Webuddy HTTP 服务。桥接进程本身不启动模型或应用。此版本没有公开的远程 MCP `/mcp` 端点。

## 云端租户：个人工具连接

租户成员在自己的网页登录 `/t/<租户>/tools` 页面创建连接，指定获准项目、期限和 `read`（只读）或 `content`（读取并创建任务/发送消息）范围。凭据归属于实际个人；每次请求重新检查账号、成员身份、项目授权、期限和撤销状态。凭据不能跨租户，也不能让成员获得原本没有的项目权限。

个人工具连接**不开放执行、候选登记或评审、知识采用、业务签收、合并和关单**；传入 `--allow-execution` 会被拒绝。它不复用管理员浏览器会话、密码或旧共享 Token。旧回环服务的完整执行命令仍保留兼容，但不属于云端成员连接能力。

创建连接后令牌仅显示一次。可在交互终端粘贴令牌（不回显），或通过标准输入导入完整 `{schema:1, endpoint, token}` JSON。不要将令牌放入命令参数、聊天、仓库或 MCP 配置：

```sh
mkdir -m 700 -p "$HOME/.config/webuddy"
# 交互粘贴令牌；endpoint 必须是网页登录中的确切租户地址。
python3 -m tmh.workbench connect \
  --endpoint https://webuddy.bbstack.date/t/default \
  --save-to "$HOME/.config/webuddy/team.json"

# 或完整 JSON 从安全保存的下载文件读取，正文不进入命令参数。
python3 -m tmh.workbench connect --stdin \
  --save-to "$HOME/.config/webuddy/team.json" < /安全位置/工具连接.json
```

两种导入方式二选一。`connect` 先读取实时身份和权限，验证成功后原子创建新 `0600` 文件；已有路径不会覆盖。输出只有个人/租户/范围/期限和文件路径，不含令牌。下载的原 JSON 仍包含秘密，应由本人妥善保管或清理。父目录必须存在、属于当前账号且不可被其他账号写入；路径不接受符号链接，文件不接受硬链接或非普通文件。Windows 原生 ACL 尚未实现，当前明确拒绝导入/加载，不能把 Windows 的 `chmod` 当作凭据隔离证明。

保存后使用文件路径或 `WEBUDDY_CREDENTIAL_FILE`，不需要 `WEBUDDY_TOKEN`：

```sh
export WEBUDDY_CREDENTIAL_FILE="$HOME/.config/webuddy/team.json"
python3 -m tmh.workbench status
python3 -m tmh.workbench projects
python3 -m tmh.workbench ticket PROJECT-1
python3 -m tmh.workbench knowledge-search PROJECT '接口约束'
python3 -m tmh.workbench send PROJECT-1 --body-file 工作记录.md \
  --request-id team-progress-001 --agent claude
```

`status.tool_connection` 返回真实个人、租户、当前项目范围、期限和 `execution:false`，顶层 `allowed_operations` 是当前可用操作。只读凭据不能发送消息。`--agent` 只表示显示/消息标签：同一个人使用 Claude/Cursor 时回执仍归属该个人，不能通过改标签更换请求主体或获得独立审阅身份。同一意图沿用原 `request_id`；断线结果未知时，先用 `request <原编号>` 查询，不自动重发或换号重复创建。撤权、过期或账号失效后旧凭据及旧回执重放均不得绕过授权；必要时由本人在网页处理。

个人工具读取任务时，`repository.head_status=not_checked` 表示没有执行宿主 Git 来核验当前 HEAD。预览读取同样只返回保存的历史记录（`verification_status=not_checked`、`preview.recorded`、`historical_binding`），不提供可访问 URL、不声称当前提交存在或进程健康。历史采纳记录不能替代现行提交核验和业务验收。固定知识版本的原文仍按清单 SHA 校验，来源共享撤销后不能继续读取。

个人工具的 `candidate_get` / `candidates_list` 返回 `state=not_checked`，`current`、`verification_passed`、`preview_ready`、`technical_acceptance`、`ready_for_human`、`human_accepted` 为 JSON `null`。这里的 `null` 表示**未执行当前性判定**，不能转换成 `false`、`stale`、失败或通过；CLI/MCP 保留该 JSON 语义。`preview_url` / `preview_entry_path` 为空，当前证据 hash 不签发。候选、所属工单/项目/运行、全部已有评审与决定、验证原文和已存预览在标明 `historical` 的 `history` 中；其中 `history.ticket_preview` 明确是所属工单最新保存的预览，`binding_status=not_checked`，可能属于同工单的后续候选，不是所请求候选的预览证明；历史 URL 只保留原文，不是可导航的有效预览。探测来源及其结果声明、采纳运行和预览中的显式关联必须属于当前工单/项目，矛盾记录拒绝返回；复检文件内声明的操作和源运行也必须匹配登记记录，未声明时仅是未核对历史。共享预览状态文件损坏返回不可核验错误，不当作空记录，也不披露其他项目原文。原文保留完整 UTF-8/CRLF；损坏的非 UTF-8 字节以 `record_status=invalid_utf8`、`encoding=base64`、`raw_base64`、字节数和 SHA256 无损返回，不当作可解析证据；工单证据原文无法读取、解码，或 JSONL 含坏行/非对象记录时 `requirement_hash=null`、`requirement_status=not_checked`，不为缺失合同签发摘要。普通网页、独立验证和人工验收仍使用原来的实时核验链路。

复检的主运行文件与操作归档都逐层核对 `previous_verifications` 中已声明的归属，兼容旧平铺记录及 `{diff, verification}` 快照。旧轮次可以使用不同操作编号，但不能属于另一运行或项目；矛盾记录返回409，原文件不改写。未声明身份或登记已经缺失的旧记录仍保留原文，不补造绑定。`binding_status=stored_match` 只描述当前层的登记归属，不证明历史内容正确、全部旧轮次已核验或当前测试通过。探测来源比较保留JSON类型，布尔值或浮点数不能冒充整数编号。

个人工具的 `ticket_get` / `run_get` 也不触发运行恢复、锁或进程健康检查；`run_get.history.run` 保留完整输出与提示词，顶层 `output` 仍按 `since` 字符游标返回。`library_get` 保留数据库登记的 `queued` / `building` 等 `status`，另以 `runtime_status=not_checked` 表示没有核验或恢复构建。这些历史状态不证明工作进程仍运行。`request_get` 的 `pending` / `uncertain` 继续表示结果未知且 `needs_reconcile=true`；不能因为本次只读不恢复而改判失败，或换新编号重复操作。既有 schema 初始化/兼容迁移保留；迁移完成后的读取不会重写业务状态。

用安装了 MCP SDK 的 Python 生成配置：

```sh
python3 -m tmh.workbench config claude --credential-file "$HOME/.config/webuddy/team.json"
python3 -m tmh.workbench config cursor --credential-file "$HOME/.config/webuddy/team.json"
python3 -m tmh.workbench config codex --credential-file "$HOME/.config/webuddy/team.json"
```

生成配置只包含解释器、桥接脚本和凭据文件路径，不内嵌令牌。MCP 启动先检查实时身份，按返回的可用操作与本地限制的交集公开工具；连接失败时不回退到旧共享 Token 或扩大权限。启动后的每个请求仍由网关重新授权，撤权不能靠保持 MCP 进程绕过。`--read-only` 可以进一步收窄内容凭据。配置生成、官方 SDK 协议验收和实际 Claude/Cursor 产品中的模型调用是不同验证层次；具体实机结果以本轮进度记录为准，未运行的客户端不算通过。

## 旧独立服务兼容模式

以下 root URL、共享 Token 与执行命令供旧的独立受信任服务保留，不适用于上述 `/t/<租户>` 个人连接。租户模式不会因为这些例子、工具标签或本地执行开关放宽服务器禁令。

## 安装与连接

以下命令在本仓库根目录执行。工作台需运行本仓库当前版本；已有服务时不要重复启动同一数据目录和端口。CLI 默认连接 `http://127.0.0.1:8791`。

CLI 使用项目现有的 Python 环境，无需 MCP SDK：

```sh
python3 -m tmh workbench status
python3 -m tmh workbench --agent codex ticket BOOTV2-1
```

安装包后也可以用 `webuddy`：

```sh
python3 -m pip install -e .
webuddy status
```

MCP 需要 **Python 3.10 或以上**，以及可选依赖 `mcp>=1.30,<2`。可使用现有的合适虚拟环境，或新建专用环境：

```sh
python3.11 -m venv data/agent-venv
data/agent-venv/bin/python -m pip install -e '.[mcp]'
data/agent-venv/bin/python -m tmh.workbench status
```

`python3 -m tmh workbench`、`python3 -m tmh.workbench` 与安装后的 `webuddy` 进入同一个 CLI。`--agent`、`--endpoint`、`--credential-file`、`--timeout` 可以放在子命令前或后，例如：

```sh
webuddy --agent codex --endpoint http://127.0.0.1:8791 ticket BOOTV2-1
webuddy ticket BOOTV2-1 --agent codex --endpoint http://127.0.0.1:8791
```

连接地址也可通过 `WEBUDDY_URL` 设置。连接名应保持稳定，例如 `codex`、`cursor`、`claude`；它参与消息路由与请求回执查找。

## 接入 Claude Code、Cursor、Codex

用实际安装 MCP SDK 的 Python 生成配置。下面三条命令已经通过本地配置生成器验证；它们只输出配置，**不会覆盖任何现有配置文件**：

```sh
data/agent-venv/bin/python -m tmh.workbench config claude
data/agent-venv/bin/python -m tmh.workbench config cursor
data/agent-venv/bin/python -m tmh.workbench config codex
```

生成器会填入当前 Python 和 `tmh/workbench_entry.py` 的绝对路径，因此助手从其他项目目录启动时也能找到桥接程序。更换机器、移动仓库或更换虚拟环境后，应重新生成。不要把这台机器的绝对路径当成团队通用配置。

| 客户端 | 生成内容与接入位置 |
|---|---|
| Claude Code | 输出包含 `mcpServers.webuddy` 的 JSON；把该条目合入目标项目 `.mcp.json` 的 `mcpServers`，保留其他条目。客户端可能要求确认项目 MCP 配置。见 [Claude Code 官方说明](https://code.claude.com/docs/en/mcp)。 |
| Cursor | 输出包含 `mcpServers.webuddy` 的 JSON；合入项目 `.cursor/mcp.json` 或用户 `~/.cursor/mcp.json` 的 `mcpServers`，保留其他条目。见 [Cursor 官方说明](https://cursor.com/docs/mcp)。 |
| Codex | 输出 `[mcp_servers.webuddy]` TOML；合入当前 Codex 使用的配置，保留原设置。仅旧独立服务模式生成 `env_vars = ["WEBUDDY_TOKEN"]`；个人连接只引用凭据文件路径。 |

默认 MCP 可以读取资料、创建暂停执行的需求和发送消息，**不提供运行、取消、重验或启动预览工具**。可以选择两种明确的权限配置：

```sh
# 仅提供读取工具
data/agent-venv/bin/python -m tmh.workbench config codex --read-only

# 允许工作台执行模型、停止运行、重验与启动候选预览
data/agent-venv/bin/python -m tmh.workbench config codex --allow-execution
```

将 `codex` 换成 `claude` 或 `cursor` 可生成对应配置。如果同时传入两种标志，只读优先。直接启动桥接程序的等价命令是：

```sh
data/agent-venv/bin/python -m tmh.workbench mcp --agent codex --read-only
```

这条命令等待 MCP 客户端通过标准输入通信，终端没有普通提示属于正常现象。标准输出只用于 MCP 协议。协议握手、工具发现和调用已通过官方 `ClientSession` 对真实 CLI 子进程的测试；这不等于已经分别在 Claude Code、Cursor、Codex 三个产品中完成实机认证。

## 一条实际使用路径

先读取连接信息和现有需求：

```sh
webuddy status --agent codex
webuddy projects --agent codex
webuddy tickets --project BOOTV2 --agent codex
webuddy ticket BOOTV2-1 --agent codex
```

`ticket` 返回完整需求、仓库位置与验证命令、运行引用、预览和证据状态。需要运行的完整输出时，再按运行编号调用 `run`。

新增需求会保留原文并暂停自动流程，**创建本身不消耗模型额度，也不会自动改代码**。正文可以来自 UTF-8 文件；`--body-file -` 表示完整读取标准输入，包括换行和空白：

```sh
webuddy create BOOTV2 '事项管理：增加关键词筛选' \
  --agent codex --request-id bootv2-search-request-001 --body-file - <<'REQUEST'
在事项列表增加关键词筛选，支持清除筛选。
验收：新增、编辑、完成状态和重启后的持久保存均保持正常；空结果时给出明确提示。
REQUEST
```

保存返回的 `ticket.key`。既有工单若仍由自动流程管理，需要先在现有工单页认领，避免两个执行者同时改动或自动采纳。关联交付阶段的工单继续从交付阶段页执行，当前 Agent 入口不能跳过阶段条件。

需要工作台执行器继续时，用返回值替换下例中的占位符，并从 `status` 返回的执行器中选择 `--engine`：

```sh
TASK='<create 返回的 ticket.key>'
webuddy start "$TASK" analyze --engine codex --agent codex --request-id search-analyze-001
webuddy run '<start 返回的 run.id>' --agent codex --wait 30
webuddy start "$TASK" plan --engine codex --agent codex --request-id search-plan-001
```

方案成功后再启动 `fix`。服务端要求方案由本 Agent API 为**当前完整需求**产生，运行成功并包含可检查的验收标准；需求变化、旧方案或没有绑定的方案都会被拒绝。当前采用保守的上下文绑定：新增沟通评论、退回原因或客户验收标准也可能使原方案失效，此时先读最新任务包并重新运行 `plan`。`done` 和模型退出码为零仍不等于验收通过。

```sh
webuddy start "$TASK" fix --engine codex --agent codex --request-id search-fix-001
webuddy run '<实现运行编号>' --agent codex --wait 30
webuddy recheck '<实现运行编号>' --agent codex --request-id search-recheck-001
webuddy preview "$TASK" --agent codex
```

实现产物仍需现有流程审阅和采纳。`preview --start` 只允许启动与已采纳运行绑定的本地候选，并校验版本；它不代表部署成功或业务验收完成：

```sh
webuddy preview "$TASK" --run-id '<已采纳运行编号>' --start \
  --agent codex --request-id search-preview-001
```

## 外部 Agent 从代码到验收

外部助手可以在项目自己的 Git 工作树实现需求，然后登记完整候选提交。候选必须已经存在于登记项目的本地 Git 对象库；接口不接受任意仓库地址、路径或 shell 命令。不同机器上的提交需先按团队现有 Git 方式取回本地。登记不修改主干，不启动模型，也不代表采纳。

1. `ticket TASK` 读取完整需求、`requirement_hash`、项目路径和配置，明确基线及验收条件。
2. 在隔离工作树实现并提交。基线必须是候选祖先，且与工单明确固定的 `base` / `code_at` 一致。
3. `submit` 登记固定候选；`verify` 由平台在独立工作树运行真实构建与测试，受现有总预算、取消和进程回收约束。
4. 验证通过后 `candidate-preview` 启动固定提交；`candidate` 返回经工作台授权的可打开入口。
5. 独立复核会话逐项观察实际结果，用 `assess` 提交全部标准的证据。实现者不能用同一身份自签；标签本身仍是自声明，不能当身份认证。
6. `acceptance` 读取是否具备最终签收条件。操作者可以在终端完成最后一次确认，无需回网页找按钮。

用实际返回值替换以下占位符；所有写操作都需稳定的请求编号：

```sh
webuddy submit BOOTV2-3 --agent codex-external \
  --base '<完整基线SHA>' --commit '<完整候选SHA>' \
  --requirement-hash '<ticket返回的哈希>' --criteria-file criteria.json \
  --summary '实现说明和测试限制' --request-id external-submit-001
webuddy verify '<候选ID>' --agent codex-external --request-id external-verify-001
webuddy candidate '<候选ID>'
webuddy candidate-preview '<候选ID>' --agent codex-external --request-id external-preview-001
webuddy assess '<候选ID>' --agent independent-reviewer \
  --verification-hash '<当前验证哈希>' --preview-hash '<当前预览哈希>' \
  --results-file results.json --body-file review.md --request-id external-review-001
webuddy acceptance '<候选ID>'
```

`criteria.json` 是完整数组，例如 `[{"id":"A1","text":"中文关键词能筛出对应事项","check":"用真实HTTP和浏览器核对事项编号"}]`。`results.json` 必须逐项对应全部编号，每项包含 `id`、`status`（`pass` / `fail` / `unknown`）、`evidence`（实际观察和证据引用）。缺项、重复项、自签和过期哈希都会拒绝。没有真实测试命令、测试失败或预览未就绪时不能进入签收。

`candidate` / `acceptance` 返回 `verification_passed`、`preview_ready`、`technical_acceptance`、`ready_for_human`、`human_accepted` 和 `missing`。重新验证、预览重启、需求沟通/配置变化或更新候选都会使相关旧结论失效；历史原样保留。每次预览使用独立日志文件。`cancel-verification` 仅停止当前验证，不删除代码；停止后读取候选的验证回执。

最终确认仅在操作者的交互终端提供，MCP 永远不公开此工具：

```sh
webuddy approve '<候选ID>' --evidence-hash '<当前完整证据哈希>' \
  --operator-key-file data/product-workbench/operator-approval.key \
  --body '已核对该版本和逐项证据，同意本地验收' --request-id operator-accept-001
```

终端展示完整证据后要求输入 `accept <完整证据哈希>`；`reject` 使用同样方式记录退回。它们**不合并、不发布、不关闭工单**。服务启动时在数据目录创建独立 `0600` 操作者凭据，普通 Agent 令牌不能代替，MCP 客户端也不会发送它。远程操作者可自行通过专用 `WEBUDDY_OPERATOR_TOKEN` 环境变量注入；不要把值写入聊天、代码、Agent 配置或日志。此机制隔离共享工作区凭据，不能隔离运行在同一操作系统用户下、拥有全文件访问权的程序，也不证明持有者是真人。

本轮真实 BOOTV2-3：外部 Codex 生成搜索和状态筛选代码；其沙箱无法监听测试端口或写共享 Git 元数据，失败完整保留。协调者运行真实测试后本地提交，平台再独立验证，另一个审查会话复核。最终技术验收及人工状态以 `webuddy acceptance 1` 的当前返回为准。

## 候选外部的业务探测

新增 [Harness² 探测接入](harness2-integration.md)：`harness-recipes` 查看适用范围，`harness-probe <候选ID> --recipe bootv2-items-search-v1 --request-id <唯一编号>` 在独立数据上对照固定基线与候选，`harness-report <探测ID>` 读取完整行为证据。启动后旧技术观察失效，失败或未知阻止签收；通过后重新 `assess`，再读取 `acceptance`。这不替代真实用户确认，也不因进程退出 0 而通过。`harness-library BOOTV2` 的历史记录同时进入 `ticket` 任务包，供后续 Agent 核对复用。

## Agent 间沟通与交接

消息进入工单时间线，记录发送连接、接收连接、消息类型、可选回复事件和请求编号。`--kind` 支持 `note`、`question`、`handoff`、`result`；省略 `--to` 时广播给 `*`。

```sh
webuddy send BOOTV2-1 --agent codex --to cursor --kind handoff \
  --request-id bootv2-review-handoff-001 --body-file - <<'MESSAGE'
请先读取当前工单和候选运行，复核编辑保存、刷新和失败重试。
请回复实际操作、数据变化、候选提交与证据位置；尚未验证的项目请明确标注。
MESSAGE

webuddy inbox --agent cursor --ticket BOOTV2-1 --after 0 --limit 20
```

接收者保存返回的 `next_after`，下次从该游标接续。**即使 `has_more=false`，也保存最后一页的 `next_after`**；空页保持原游标。CLI 默认读取当前连接及广播消息，MCP 调用 `webuddy_messages_list` 时可显式传入 `to_agent`。读取不会标记已读，游标由接收者自行保存。

这是一份可持续读取的工单消息记录：不会推送到外部运行中的 Claude Code、Cursor 或 Codex，也不会自动唤醒对方、执行消息正文或实现 A2A 协议。交接内容是任务资料，不是新的授权；收到 `result` 不代表独立复核或人工验收完成。

## 请求回执、超时与恢复

所有写操作必须传入 `request_id`，CLI 参数为 `--request-id`。编号在同一连接名下持久保存：相同编号与内容返回原结果；相同编号配不同操作或内容返回冲突。一次真正的新意图使用新编号，同一意图重试必须保持原编号和参数。

```sh
webuddy request bootv2-review-handoff-001 --agent codex
webuddy run '<运行编号>' --agent codex --since 0
webuddy cancel '<运行编号>' --agent codex --request-id stop-run-001
```

单次 HTTP 超时默认 15 秒，`--timeout` 最大 60 秒；`run --wait` 的总等待范围为 0–60 秒。等待结束或 MCP 请求被取消，都不会自动取消工作台已接受的运行。需要停止时显式调用 `cancel`，再读取运行的停止和进程回收回执。运行输出的 `since`、`output_len` 使用字符游标，按返回的 `output_len` 接续读取。

断线或响应格式异常时，写操作可能已保存。CLI 和 MCP **不会自动重试写操作**。先以原连接名查询原 `request_id`，核对工单、运行和回执：

| 回执状态 | 下一步 |
|---|---|
| `complete` | 读取保存的 `result`；不要再启动同一工作。 |
| `failed` | 读取确定失败的原因；纠正问题后，只有明确形成新操作时才使用新编号。 |
| `pending` / `uncertain` | `needs_reconcile=true`；结果未确认，先核对并处理原操作。不能换编号绕过，启动同一对象上的重复工作。 |

结果未确认时仍可读取、发送沟通消息和请求停止，避免恢复通道被锁死。当前没有对外开放“清除未知状态”工具；不能仅凭断线、时间过去或进程消失宣称原操作未执行。`retry` 还会检查原运行的失败状态、上下文和进程回收记录，回收不完整时拒绝重试。

## 工具目录

CLI、HTTP Agent API 与 MCP 共享 [`tmh/agent_contract.py`](../tmh/agent_contract.py) 的严格 JSON Schema：拒绝未知字段、错误类型和越界参数，不静默转换或截断正文。MCP 返回完整 JSON 文本和 `structuredContent`，失败同时设置 `isError=true`。

| MCP 工具 | CLI | 权限与用途 |
|---|---|---|
| `webuddy_status` | `status` | 读取连接、可用执行器与能力边界 |
| `webuddy_projects_list` | `projects` | 按 `after` / `limit` 读取项目 |
| `webuddy_tickets_list` | `tickets` | 按项目、状态、关键词分页读取工单 |
| `webuddy_ticket_get` | `ticket` | 读取完整任务、仓库、运行引用、预览与证据 |
| `webuddy_ticket_create` | `create` | 写入需求；需要 `request_id`，暂停自动执行 |
| `webuddy_message_send` | `send` | 写入持久消息；需要 `request_id` |
| `webuddy_messages_list` | `inbox` | 按事件游标读取 Agent 消息 |
| `webuddy_request_get` | `request` | 读取当前连接名下的持久回执 |
| `webuddy_run_get` | `run` | 读取运行、完整输出、验证和停止回执 |
| `webuddy_run_start` | `start` | 执行：启动 `analyze` / `plan` / `fix`，返回运行引用 |
| `webuddy_run_cancel` | `cancel` | 执行：停止运行并回收进程 |
| `webuddy_run_retry` | `retry` | 执行：通过状态与回收检查后重试 |
| `webuddy_run_recheck` | `recheck` | 执行：重新构建、验证已有改动 |
| `webuddy_preview_get` | `preview` | 读取指定候选预览与版本 |
| `webuddy_preview_start` | `preview --start` | 执行：启动已采纳候选的本地预览 |
| `webuddy_candidates_list` / `webuddy_candidate_get` | `candidates` / `candidate` / `acceptance` | 读取外部候选和完整验收状态 |
| `webuddy_candidate_submit` | `submit` | 执行权限：登记项目仓库中的固定提交 |
| `webuddy_candidate_verify` | `verify` | 执行：独立工作树构建与测试 |
| `webuddy_candidate_cancel` | `cancel-verification` | 执行：停止本次验证并保留回执 |
| `webuddy_candidate_preview` | `candidate-preview` | 执行：启动已通过验证的候选预览 |
| `webuddy_candidate_assess` | `assess` | 逐项技术观察，不是人工决定 |
| `webuddy_harness_recipes` | `harness-recipes` | 读取维护者版本化的业务探测配方 |
| `webuddy_harness_probe_start` | `harness-probe` | 执行：独立数据对照基线和候选；旧技术观察失效 |
| `webuddy_harness_probe_get` | `harness-report` | 读取真实行为结果、完整证据和回收状态 |
| `webuddy_harness_probe_cancel` | `harness-stop` | 执行：请求停止，保留部分结果 |
| `webuddy_harness_library` | `harness-library` | 读取项目有证据支持的历史验证策略 |
| `webuddy_library_get` / `webuddy_library_search` / `webuddy_library_read` | `library` / `knowledge-search` / `knowledge-read` | 读取获准项目和固定来源知识；当前授权仍逐次检查 |
| `webuddy_library_build` / `webuddy_library_cancel` / `webuddy_library_resume` | `knowledge-build` / `knowledge-cancel` / `knowledge-resume` | 仅旧独立服务执行权限：构建、取消或继续知识修订 |
| `webuddy_library_reference` / `webuddy_library_unlink` | `knowledge-reference` / `knowledge-unlink` | 仅旧独立服务内容权限：调整已授权知识引用，不授予来源共享权限；个人租户工具连接不开放 |

工具数量随版本化目录变化，具体以 `tools/list` 为准；租户个人连接还取实时 `allowed_operations` 的交集，且最多允许创建任务/发送消息两种内容写入。人工决定不在任何 MCP 配置中。执行类写操作仅供旧独立受信任服务，也都要求 `request_id`。工具隐藏之外，桥接调用和 HTTP 入口仍检查参数与权限，不能靠猜工具名越过当前连接的权限配置。

## 身份与连接边界

`--agent` 是调用者自己声明的审计和路由标签，**不是身份认证，也不是每个 Agent 独立的访问控制**。同一工作台凭据下的可信调用者可以声明其他连接名；不要把这些标签用于不可信租户隔离。消息和运行使用 `agent:<连接名>`，不会记成人的审阅或批准。

旧独立服务沿用已有 `TMH_TOKEN` 认证配置；客户端从环境变量 `WEBUDDY_TOKEN` 读取对应令牌，通过请求头发送。这个旧令牌属于工作台的可信访问凭据，不是只授权某一个 Agent 或某个工单的受限令牌。个人租户连接使用 `Authorization: Bearer`，绝不附带旧 Token、浏览器 Cookie 或浏览器上下文令牌。不要把任何令牌放进命令参数、聊天、仓库或生成配置里。

本地默认使用回环地址；非回环地址只接受 HTTPS。HTTP 客户端拒绝重定向，防止把凭据和写请求转送到另一个地址；所有连接均不使用环境 HTTP 代理。端点只允许 root URL 或固定 `/t/<租户>` 前缀，不接受其他路径、查询参数或嵌入凭据；显式地址与凭据文件绑定地址冲突时拒绝连接。MCP 桥接有 4 个并发 HTTP 工作线程的上限，运行中的 HTTP 调用受连接超时约束，取消不会启动额外重试。

建立连接后的整个 HTTP 请求有截止时间，持续滴流也会关闭 socket；系统 DNS 解析不保证受此截止时间约束。默认回环 IP 不需要 DNS。客户端不使用环境代理。

编程助手自身的工具审批仍然有效。本轮真实 Codex 已成功调用 `ticket_get`、`preview_get`、`messages_list`；非交互 `approval_policy=never` 下，`message_send` 被客户端要求审批而拒绝，服务端没有收到该写入。正常交互会话需按客户端提示允许所需工具；这里没有改写用户配置或关闭审批。Claude、Cursor 已验证生成配置能用官方协议客户端从其他目录启动，但尚未在这两个产品的真实登录会话中逐项验收。

## 可重复的协议验收

测试使用官方 MCP `ClientSession` 启动真实 CLI 子进程，再经 HTTP 客户端连接隔离夹具。夹具返回的运行、候选和证据只用于协议测试，不能作为 BOOTV2 的业务验收或真实模型结果。

```sh
data/agent-venv/bin/python -m unittest tests.test_workbench_mcp -v
```

以下 10 项是可在该稳定夹具上重复检查的只读评估条件。它们供接入客户端时逐项核对；不声称已由三个客户端的模型分别完成。涉及负例的调用必须在发送任何 HTTP 请求之前拒绝。

| 评估问题 | 预期条件 |
|---|---|
| 旧独立服务默认连接公开哪些工具？ | 当前 `tools/list` 返回 21 个工具；没有任何执行类工具。租户模式另外受实时允许列表限制。 |
| 旧独立服务只读连接公开哪些工具？ | 当前 16 个读取工具，没有 `ticket_create` 或 `message_send`。 |
| 同时传入只读和执行标志时采用哪种配置？ | 旧独立模式仍只有 16 个读取工具；租户模式直接拒绝 `--allow-execution`。 |
| 如何区分夹具与真实工作台？ | 夹具 `webuddy_status` 的 `scope` 为 `fixture`，不能据此声称真实服务已验收。 |
| 工单的完整原文是否保留？ | 夹具 `webuddy_ticket_get` 返回的正文与测试的 `long_text` 逐字符一致，包括中文、空格、换行和制表符。 |
| 工单夹具是否代表已通过验收？ | 证据的 `verdict` 是 `not_accepted`，`commit` 是 `fixture-only`。 |
| 只支持文本结果的客户端会丢失字段吗？ | JSON 文本解析后与 `structuredContent` 完全一致。 |
| 能把布尔值当成运行编号吗？ | `webuddy_run_get` 的 `run_id=true` 返回 `invalid_arguments`；HTTP 请求数不增加。 |
| 能给读取工具加入任意 URL 字段吗？ | `webuddy_status` 的未知字段被拒绝，返回 `invalid_arguments`。 |
| 工具名能否扩展成未提供的发布能力？ | 调用 `webuddy_release` 返回 `tool_not_enabled`；HTTP 请求数不增加。 |

实现依据是 [MCP 2025-11-25 传输规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) 与安装版本的官方 Python SDK。此仓库固定在 SDK 1.x 的兼容范围，主分支上的 SDK 2.x 示例不可直接当作本实现接口。客户端接入位置参考上面的 Claude Code 和 Cursor 官方文档；核查日期为 2026-10-19。
