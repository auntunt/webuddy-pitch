# Webuddy CLI 与 MCP：让编程助手接入工作台

Claude Code、Cursor、Codex 可以通过 CLI 或 MCP 读取 Webuddy 里的需求、提交沟通和交接消息、调用工作台执行器，以及查看代码、运行日志、验证证据和预览。它们与网页使用同一份工单和运行数据。

当前 MCP 使用官方 Python SDK 的 **stdio** 传输：编程助手启动一个轻量桥接进程，由它连接已经运行的 Webuddy HTTP 服务。桥接进程本身不启动模型或应用；明确调用执行工具后，由工作台的持久运行管理器负责这些进程。此版本没有公开的远程 MCP `/mcp` 端点。

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

`python3 -m tmh workbench`、`python3 -m tmh.workbench` 与安装后的 `webuddy` 进入同一个 CLI。`--agent`、`--endpoint`、`--timeout` 可以放在子命令前或后，例如：

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
| Codex | 输出 `[mcp_servers.webuddy]` TOML；合入当前 Codex 使用的配置，保留原设置。生成结果包含 `env_vars = ["WEBUDDY_TOKEN"]`，只记录环境变量名。 |

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

默认 MCP 提供 13 个工具；只读配置提供 10 个；显式开放执行后提供 22 个。人工决定不在任何 MCP 配置中。执行类写操作也都要求 `request_id`。工具隐藏之外，桥接调用和 HTTP 入口仍检查参数与执行标志，不能靠猜工具名越过当前连接的权限配置。

## 身份与连接边界

`--agent` 是调用者自己声明的审计和路由标签，**不是身份认证，也不是每个 Agent 独立的访问控制**。同一工作台凭据下的可信调用者可以声明其他连接名；不要把这些标签用于不可信租户隔离。消息和运行使用 `agent:<连接名>`，不会记成人的审阅或批准。

服务端沿用已有 `TMH_TOKEN` 认证配置；客户端从环境变量 `WEBUDDY_TOKEN` 读取对应令牌，通过请求头发送。这个令牌属于工作台的可信访问凭据，不是只授权某一个 Agent 或某个工单的受限令牌。不要把令牌放进命令参数、聊天、仓库或生成配置里。应由启动助手的环境或现有秘密管理方式注入；图形客户端是否继承终端环境需要在该客户端中检查。Codex 配置仅列出要传递的环境变量名称。

本地默认使用回环地址；非回环地址只接受 HTTPS。HTTP 客户端拒绝重定向，防止把凭据和写请求转送到另一个地址；访问回环地址时绕过系统 HTTP 代理。服务不接受端点中的路径、查询参数或嵌入凭据。MCP 桥接有 4 个并发 HTTP 工作线程的上限，运行中的 HTTP 调用受连接超时约束，取消不会启动额外重试。

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
| 默认连接公开哪些工具？ | `tools/list` 返回 13 个工具；没有任何执行类工具。 |
| 只读连接公开哪些工具？ | 仅 10 个读取工具，没有 `ticket_create` 或 `message_send`。 |
| 同时传入只读和执行标志时采用哪种配置？ | 仍然只有 10 个读取工具。 |
| 如何区分夹具与真实工作台？ | 夹具 `webuddy_status` 的 `scope` 为 `fixture`，不能据此声称真实服务已验收。 |
| 工单的完整原文是否保留？ | 夹具 `webuddy_ticket_get` 返回的正文与测试的 `long_text` 逐字符一致，包括中文、空格、换行和制表符。 |
| 工单夹具是否代表已通过验收？ | 证据的 `verdict` 是 `not_accepted`，`commit` 是 `fixture-only`。 |
| 只支持文本结果的客户端会丢失字段吗？ | JSON 文本解析后与 `structuredContent` 完全一致。 |
| 能把布尔值当成运行编号吗？ | `webuddy_run_get` 的 `run_id=true` 返回 `invalid_arguments`；HTTP 请求数不增加。 |
| 能给读取工具加入任意 URL 字段吗？ | `webuddy_status` 的未知字段被拒绝，返回 `invalid_arguments`。 |
| 工具名能否扩展成未提供的发布能力？ | 调用 `webuddy_release` 返回 `tool_not_enabled`；HTTP 请求数不增加。 |

实现依据是 [MCP 2025-11-25 传输规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) 与安装版本的官方 Python SDK。此仓库固定在 SDK 1.x 的兼容范围，主分支上的 SDK 2.x 示例不可直接当作本实现接口。客户端接入位置参考上面的 Claude Code 和 Cursor 官方文档；核查日期为 2026-10-19。
