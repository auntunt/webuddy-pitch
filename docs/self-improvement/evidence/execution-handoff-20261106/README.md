# 执行方式交接验证

主实现：`d7354ab4b8a54c57cf471ffdfe3f4eb355c70f5f`；最终代码候选（补负责人变化失效）：`8ab6b1f0a96212ed5249964a7957da8d85c0c425`。基线：`5d80631`。

## 实际检查

- Mac Python 3.11，`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/tests:$PWD" python -m unittest ... -q`。模块见各日志的对应记录与进度文档。测试之间有重叠，不累计成业务场景总数。
- 官方 MCP SDK 使用 `/tmp/webuddy-developer-mcp-venv/bin/python` 执行 `tests.test_workbench_mcp tests.test_tool_read_mcp`；真实 stdio/HTTP 夹具与生成的 Cursor/Claude/Codex 配置启动。没有使用客户 Cursor 账号或模型。
- Mac 凭据用例初次失败是 `/var` 符号链接被既有保护拒绝；复验设置 `TMPDIR=/private/tmp`，不修改凭据保护。
- Windows 自有设备，Python 3.11，隔离副本中运行 `tests.test_workspace_preflight tests.test_development tests.test_developer_terminal`。真实 Git 仓库/worktree，合成任务和账号；不是原生 Windows 个人 MCP 凭据支持证明。
- 安装包从精确提交的 `git archive` 重新构建到独立目录，执行 `python -I -X utf8 scripts/installed-smoke.py <target>`，检查安装、刷新、完整资源和离线安装。
- 隔离 HTTP 服务、合成开发者账号，Chrome 三尺寸 1440×900 / 768×1024 / 390×844。`task-*` 为顶部，`confirmation-*` 为确认稿区域；原始 PNG 未压缩。`browser.json` 保存文本和实际页面宽度。
- `http-handoff.json`：真实 HTTP 选择系统执行、相同请求重放、改变回答使旧选择失效；随后刷新页面核对失效文字。没有调用模型、合并或验收真实任务。

## 当前限制

预检是开工快照，不能锁住外部编辑器。仓库/版本不匹配、未提交内容、知识版本未匹配均返回待处理；不会重置文件或替开发者决定。平台正式候选继续受完整提交、契约、独立验证及人工门禁约束。

客户 Cursor 桌面、怀柔业务规则/数据及客户两机链路未联调。原生 Windows 个人 MCP 凭据限制仍保留。测试机发布和精确提交 CI 结果以进度文件后续记录为准。

最终候选增量检查：43 文件清单 2,414 项一致，15 个数据库完整性/迁移副本检查通过；49 项交接与团队回归通过。Windows 对最终负责人变化修复另跑 12 项通过。系统执行演练用合成命令执行器实际经过原有 `run_start plan → fix`，生成 `VALUE = 1 → 2` 的真实 Git 差异；模型调用为零，不是模型能力或客户业务正确性证明。首次上传尚未完成导致摘要校验拒绝，重传完成后验证通过，旧服务未受影响。
