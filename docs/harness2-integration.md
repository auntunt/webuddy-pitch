# Harness² 在 Webuddy 中的第一段落地

核查日期：2026-10-19。上游：[google-research/harness2](https://github.com/google-research/harness2)，固定提交 [`1cfe254e8d25b15f37048c3730134686abe60335`](https://github.com/google-research/harness2/tree/1cfe254e8d25b15f37048c3730134686abe60335)（2026-10-14），Apache-2.0。上游说明不是 Google 官方支持的产品。

本轮把它的“有界探测、版本化执行环境、持久证据和可复用经验”应用到外部 Agent 候选的业务验证层。没有安装上游执行器或复制其源码，也没有实现完整的 Propose–Probe–Compose 递归优化。当前实际比较的是**同一验收配方下的两个应用提交**，不能称为两个 harness 的因果 A/B 实验，更不能推导模型修对率。

## 取舍依据

上游 README 和 `harness2/core/{recursion,ledger,library,context,selection}.py` 描述：在预算内提议策略、实际探测、组合有效改动；在限定环境内持久保存经验；保持选择时的信息与事后评判分离；未知评判不是零分。可修改表面包括提示词、护栏、记忆、工具指导、子代理、技能、脚本和插件。

Webuddy 已有固定 Git 候选、独立构建测试、受管进程、预览和逐项技术验收。当前真实缺口是：候选自带的测试即使全绿，也可能遗漏用户的搜索与筛选要求。因此先增加一份候选代码以外、由维护者版本管理的真实业务探测，复用现有停止与进程回收，不增加一套不相容的执行系统。

上游默认 Codex 执行环境关闭 sandbox、网络开放，并提示公开评分规则存在泄漏风险；它建议 Linux/Python 3.12，当前包要求 Python >=3.12,<3.14。Webuddy 当前在 macOS/Python 3.14.6 验证。这里没有沿用上游的执行权限默认值、没有开启网络、没有自动改动全局客户端配置；上游 benchmark 结果也不是本项目的验收证据。

## 已实现的路径

1. 外部 Agent 提交固定候选，平台独立构建和应用测试先通过。
2. CLI/MCP 选择维护者内置的配方。配方版本绑定脚本、执行器、检查定义和预算的 SHA256。
3. 分别从基线与候选 Git 对象导出精确 blob 内容；不使用会受 `export-ignore` / `export-subst` 改写的 `git archive`。符号链接、子模块及特殊文件暂不支持，明确失败。
4. 两个版本各用新目录、新 SQLite 数据库及独立应用进程运行同一套真实 HTTP/SQLite 检查。原项目数据库不作为探测输入，也不写入。
5. 保存完整请求、响应、表单、应用原始二进制输出、数据库、源码清单、过程回收回执与失败原因。候选程序不会被导入探测进程。检查不使用可被 Python 优化模式跳过的 `assert`。
6. 只有真实业务检查全部通过且过程回收、来源及证据哈希有效，候选探测才通过。进程退出 0 仅表示探测协议完成；`done`、`passed`、比较结论和人工验收是不同字段。
7. 一旦启动探测，旧技术观察与签收哈希立即失效；失败、未知、正在运行或证据变化阻止技术验收。通过后仍需重新核对逐项技术观察。最终本地验收使用真实用户确认，MCP 不提供人工决定工具。
8. 项目的 `harness-library` 和 `ticket` 任务包提供带原版本、配方和证据链接的历史记录。后续 Agent 可以复用策略，但历史通过不能证明新候选通过，不会自动改变权限、执行政策或启动模型。

基线有业务失败而候选通过，是有效的应用版本对照。基线因基础设施原因未知时，比较保持 `unknown`；候选自身即使有完整通过证据，也不声称比基线改善。需求/配置/候选变化仍由候选主门禁阻止；历史探测结果作为历史保留。

## CLI 与 MCP

服务需加载本轮实现；先通过 `webuddy status` 确认连接。命令也可写为 `python3 -m tmh.workbench`。

```sh
webuddy harness-recipes
webuddy harness-probe 1 --recipe bootv2-items-search-v1 \
  --agent codex-probe --request-id bootv2-probe-001
webuddy harness-report '<返回的 probe_id>'
webuddy harness-library BOOTV2
webuddy acceptance 1
```

开始命令立即返回运行编号。需要停止时：

```sh
webuddy harness-stop '<probe_id>' --agent codex-probe --request-id bootv2-probe-stop-001
webuddy harness-report '<probe_id>'
```

MCP 对应 `webuddy_harness_recipes`、`webuddy_harness_probe_start`、`webuddy_harness_probe_get`、`webuddy_harness_probe_cancel`、`webuddy_harness_library`。启动/停止须显式开放执行权限；默认只提供新增的三个读取工具。请求去重、未知回执阻断和停止通道复用 [Agent 接入契约](workbench-agent.md)。命令、代码路径和任意用户上传脚本不能通过探测参数注入。

当前配方 `bootv2-items-search-v1` 只适用于 BOOTV2 Python starter 的 `app.py PORT PREFIX DB` 接口及 A1–A4 编号。编号一致并不证明语义一致，调用者必须核对实际需求和返回的检查说明。四项覆盖中文及 Unicode 字面搜索；组合状态、空结果与清除；固定前缀、刷新和编辑上下文；200 字含 CRLF、原编号与状态、503 后完整重试、CSRF 和重启持久保存。它是 HTTP/SQLite 探测，不替代浏览器布局、键盘或无障碍的完整检查。

## 时限与信任范围

基线和候选共用 90 秒执行预算；单次 Git 导出最多使用剩余预算中的 20 秒，单次 HTTP 最多 3 秒、应用就绪最多 10 秒。启动前的候选核对以及最终回收/证据写入有额外开销，90 秒不是硬实时的端到端承诺。取消通过持久文件传递，不能把停止请求视为已回收。所有权中断、回执缺失或输出不完整时禁止自动重启，不能只凭历史 PID 发信号或自行清空未知状态。

目录、数据和进程分离适用于可信本地工作区，**不是 OS 安全沙箱**。同一操作系统用户下的恶意应用可以越权访问其他文件；主动 `setsid` 逃逸、监管进程自身强杀和机器掉电仍受现有隔离限制。当前不运行不可信远程候选，不迁移实际客户数据，不合并或发布。

## 后续边界

尚未实现自动生成配方、跨任务选择/组合提示词、独立保留测试集、预算成本优化或完整的 Harness² 递归执行。下一步应先给真实缺陷增加独立正反例，再扩展新的业务配方；需要至少多个固定任务和防泄漏评估，才能讨论策略是否稳定改善交付。失败和负面结果必须与成功记录一起保留。

本轮实际结果、独立复核红绿记录、固定版本和完整原始证据见 [验收记录](self-improvement/verification-harness2-2026-10-19.md)。
