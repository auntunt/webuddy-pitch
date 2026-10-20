# 端到端：Claude Code 通过 MCP 调用 tmh 的运维工具

日期：2026-10-07。Claude Code 2.1.292，用样例项目 `examples/legacy-java-oa`。Jira 和 Jenkins 由本机模拟服务提供：工单 OA-7 和一次失败的构建 #12，构建日志里有一段 `ExpenseService.audit(ExpenseService.java:60)` 的堆栈。

## 步骤

```sh
tmh install --repo .            # 写入 .mcp.json 和 .codex/config.toml
tmh kb build
tmh int add jira --type jira --url http://127.0.0.1:18731 --token-env JIRA_TOKEN
tmh int add ci --type jenkins --url http://127.0.0.1:18731 --user li --password-env JENKINS_TOKEN --set job=oa
tmh int test                    # ✓ jira：已登录为 Li　✓ ci：已登录为 li
claude -p "工单 OA-7 要做。先用 tmh 的 MCP 工具看工单和相关业务流，再看最近一次失败的构建出在哪条业务流。只分析，不改代码。" --allowedTools mcp__tmh
```

`.codex/config.toml` 里自动生成了 `env_vars = ["JIRA_TOKEN", "JENKINS_TOKEN"]`。

## 智能体实际的调用

1. `mcp__tmh__ticket {"key":"OA-7"}`：拿到工单，以及知识库给出的相关知识页（财务审核、提交报销单……）
2. `mcp__tmh__build_failure {}`：把失败定位到 `ExpenseService.java:60 ExpenseService.audit → 财务审核（POST /expense/audit）`
3. `mcp__tmh__flows {"query":"post-expense-audit"}`：查看完整调用链

整个过程没有读源码文件。共 5 轮，耗时 13.5 秒，花费 $0.063。

## 智能体的结论（原文）

> OA-7 要求财务审核报销单时，驳回必须填写原因，原因写进审批日志，申请人能看到。它对应的业务流是 `POST /expense/audit`（财务审核）。入口是 `ExpenseController.audit`，经 `ExpenseService.audit`（ExpenseService.java:55-68）改 OA_EXPENSE 状态，驳回时释放 OA_BUDGET 冻结预算，并写 OA_APPROVAL_LOG。目前代码里没有校验驳回原因，相关知识页也都还是“未分析”，需要先补写。
>
> 最近一次失败的构建是 oa #12，出在 `ExpenseService.audit` 第 60 行，抛 `IllegalStateException: 预算不足`，所属业务流正是 `post-expense-audit`。也就是说，OA-7 要改的流程和现有构建失败是同一条流程。动手前要先弄清这个失败是 OA-7 之前就有的，还是预算释放逻辑本身的问题。

## 注意

- `.claude/settings.json` 里的权限（允许 `mcp__tmh`）只有在工作区被信任后才生效。第一次在目标项目里运行 `claude` 时，要接受信任提示。无头运行时可以加 `--allowedTools mcp__tmh`。第一次试跑时没有信任工作区，智能体如实报告调用被拒绝，也没有绕过去改用命令行。
- 这次用的是模拟的 Jira 和 Jenkins，还没有连过真实实例。
