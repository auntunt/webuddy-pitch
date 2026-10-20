# CLI / MCP 与 Agent 交接验证 · 2026-10-19

用户要求 Claude Code、Cursor、Codex 能接续 Webuddy 的需求和软件交付工作，减少网页点选，并支持 Agent 通信。本轮完成共享工作台数据的 CLI、stdio MCP 与持久消息交接；不是远程多租户 MCP，也没有把消息或模型完成状态当作人的验收。

实现提交：`c873fc6c9e2d6368ae49b68950c4ac290dba81b0`。接续基线 `ad0f625`，分支 `codex/self-evolution-resume`。仅本地提交；没有推送、合并或发布生产，没有改变全局客户端配置或其他暂停任务。

## 已实现的用户路径

1. `webuddy`、`python3 -m tmh workbench`、`python3 -m tmh.workbench` 使用同一 CLI，连接现有工作台。
2. 读取项目、完整需求、代码位置、验证命令、所有运行引用、完整输出、证据和固定版本预览。
3. 创建保留原文且暂停自动执行的需求；发送问题、交接和结果，按接收连接及事件游标接续读取。
4. 明确启用执行后，通过现有运行管理器分析、规划、实现、取消、重试、重新验证和启动已采纳候选预览。新增消息、客户标准或需求变更使旧方案失效。
5. 写入使用持久请求编号去重。响应未知时先读回执，不能换编号重复启动；停止和沟通通道仍可使用。
6. Claude Code / Cursor / Codex 配置生成器输出绝对启动路径，支持从其他项目目录启动。官方 MCP SDK 管理握手、工具发现、stdio 和取消。

MCP 默认10个工具，只读8个，显式 `--allow-execution` 后15个；与CLI/API共用严格参数契约。身份显示 `agent:<连接名>`。工单内容、源代码和日志是任务资料，不授予新权限。

## 真实工作台与编程客户端验收

使用日常 `127.0.0.1:8791`，数据目录 `data/product-workbench`。操作前保存数据库备份 `data/agent-native-main-before.db`。没有新增模型实现运行或替代人工签收。

| 操作 | 实际结果与证据 |
|---|---|
| CLI读取真实BOOTV2 | 获取完整 `BOOTV2-1`、运行 #6、候选 `8be50de6b4b4200dc6d792c2a7f0b871f9288da4`；仍缺人工复核/签收，未标成已验收。见 `bootv2-context.stdout.json`。 |
| CLI创建接入验证事项 | 创建 `BOOTV2-2`，同请求重放返回原工单；没有自动启动运行。见 `create-native-ticket*.json`。这是一项接入验证事项，不是新的客户业务完成记录。 |
| CLI发送交接 | 事件 #43，完整消息由 `agent:codex` 发往 `codex-native`；见 `cli-handoff.stdout.json`。 |
| 官方SDK真实连接 | `ClientSession` 从无关目录按生成配置启动，发现10个默认工具，读取真实工单/候选，写入回复 #44；同编号重放不产生新事件。见 `live-sdk-*.json`。 |
| 真Codex通过MCP读取 | 原始工具回执证实 `webuddy_messages_list`、`webuddy_ticket_get`、`webuddy_preview_get` 成功；不是根据模型退出码判断。见 `real-codex-fixed.stdout.jsonl`。 |
| 真Codex写消息 | `webuddy_message_send` 被客户端以 “MCP tool call requires approval, but approval policy is never” 拒绝，服务端未收到该写入。未关闭审批或更换通道重放该被拒请求。 |
| 服务重启后接续 | CLI读回事件 #44、原请求 `complete` 回执和新工单完整原文。见 `inbox-after-restart.json`、`receipt-after-restart.json`、`new-task-context-after-restart.json`。 |
| 浏览器核对 | 实际打开 `BOOTV2-2`，显示CLI/MCP等待明确下一步及两条通信；实际打开BOOTV2固定提交预览，三条事项仍在。原始PNG与可访问性文本见 `browser-handoff.*`、`browser-bootv2-preview.*`。 |
| 数据与进程核对 | 原3个项目、3张工单、41条事件、6次运行逐行不变，原三条业务数据相等；客户端结束后无本次MCP桥接残留。见 `main-after-verification.json`、`mcp-process-cleanup.json`。 |
| 安装入口与打包 | 专用Python 3.14环境安装后的 `webuddy status` 读到真实服务；最终wheel包含全部新模块及console入口，模块字节与当前源码相等。见 `installed-console-status.json`、`wheel-final-verification.json`。 |

Claude Code 和 Cursor 已验证生成配置的精确 command/args 能由官方协议客户端从其他目录启动，未在这两个产品的真实登录会话内逐项验证。真实Codex只读成功和写入审批失败分别记录，不能合并成“三款产品全部验收通过”。

## 回归与独立复核

最终使用 Python **3.14.6** 与官方 **MCP SDK 1.30.0**，执行 `data/agent-venv314/bin/python -m unittest discover -s tests -v`：**718项全部通过，0跳过，281.225秒，退出码0**。源码、测试和构建配置共173个文件执行前后SHA256完全一致，提交前再次核对一致。原始结果见 `full-python314-final.log` 和 `full-python314-final-source.json`。日志仍含资源清理警告，已保留；本次桥接进程清理结果单独核对，不用测试退出码代替。

覆盖包括28项Agent API测试、17项独立CLI/HTTP测试及13项官方SDK MCP测试。这些是边界与行为覆盖，不是业务修对率。后端覆盖真实HTTP认证、跨进程同请求去重、完整消息与游标、未知结果停止/沟通、旧方案失效及未完成进程回收不可绕过；MCP覆盖完整文本/结构化返回、权限集合、未知参数、丢响应、进程关闭与三种生成配置启动。

`agent_bridge_review` 独立发现并验证修复：持续滴流绕过空闲超时、非对象JSON导致异常、缺SDK/端点错误处理、未知回执、未知启动错误阻止安全取消、旧handwork扫描绕过创建不执行约束、沟通遗漏在方案版本绑定之外。根代理实际配置验收发现 `tmh/mcp.py` 遮蔽官方SDK；修正绝对入口的 `sys.path` 后补三种配置启动回归。完整记录见 `independent-review.md`。

原始失败全部保留：

- `workbench-client-review-red.log` 与对应绿灯，说明独立复核发现的问题及修复。
- `live-sdk.stderr.txt`、早期 `real-codex*.jsonl` / stderr：SDK名称遮蔽、一次配置覆盖格式错误及当时无法发现工具的实际失败；最终成功读取见带 `fixed` 的记录。
- `full-suite.log`：715项、12跳过、退出0，但执行期间源码改变，`source_unchanged=false`；不作为最终版本验收。
- `full-final.log`：Python 3.11.15全量718项，8错误、1失败，不能当作通过。8项为旧测试快照的sqlite3 `iterdump()` 与字典row_factory不兼容，可仅用stdlib复现；Python 3.14实现已处理此情形。取消用例在调用cancel前已超过0.5秒预算，先返回124使其前置断言失败，没有证据表明是取消优先级回归。
- `python311-independent-diagnosis.log`：同一3.11环境生命周期12项定向复跑通过，抽取两项数据库快照仍失败。这个复跑不抵销原全量红灯；本轮未改旧测试来隐藏失败。

## 交付与当前边界

接入说明：[docs/workbench-agent.md](../workbench-agent.md)。本机三份生成配置在 `data/agent-client-configs/`，使用已安装SDK的 `data/agent-venv/bin/python`。另有 `data/agent-venv314/bin/webuddy` 可直接调用。移动仓库或环境后应重新生成绝对路径。

所有原始测试日志、HTTP/SDK/真实Codex回执、原分辨率PNG及文件哈希均在 `evidence/agent-native-2026-10-19/`。没有裁剪正文、压缩截图或删除失败；`MANIFEST.json` 记录完整文件字节数与SHA256。

当前通信是持久收件箱拉取，不会自动唤醒另一编程助手；没有宣称A2A协议。连接名是自声明审计标签，沿用已有工作台共享令牌，适用于可信工作区，不是Agent间独立权限。仅提供stdio桥接，没有公共远程MCP端点。HTTP请求在连接后有总截止时间，系统DNS解析不保证受该截止时间限制，默认回环IP不需要DNS。

外部助手提交任意代码候选、无需网页的人工复核、远程受限凭据及通知订阅留在SI-012第二段。当前不直接包装旧handwork.take，避免旧路径的“人工”归因、提前采纳或未知审查继续流转。已有运行仍可通过CLI/MCP控制与查看证据；不会把模型退出、收到结果消息或打开预览当成客户验收。

下一轮优先打通外部实现 → 不可变候选登记 → 平台独立构建验证 → 固定版本预览 → 明确人工验收，继续复用现有需求、候选、进程监管及版本门禁。
