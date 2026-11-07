# 最新代码、测试机制与 computer use 核对

日期：2026-11-07。基线：`c80251edd9c1a5224ef1ca313a9ddb4eb085b415`，产品分支 `devin/1793765109-bidding-demo-ui`。工作区开始干净，fetch 后本地与 GitHub 相同，fast-forward 返回 Already up to date。本轮仅修改说明与证据，不改变测试断言、业务规则或执行器能力。

## 已实际检查

- 阅读近期十条提交、现行交付规则及进度；核对 `browser_verify.py`、`project_tests.py`、`project_test_runner.cjs`、`testbox_mcp.py`、`project_client.py` 和 CI 配置与相关测试。
- 主闭环文档：[验证与 Review](../../../verification-review.md)。项目测试与测试机文档已交叉链接，未新建另一套状态机或批准机制。
- 本机测试环境：macOS，Python 3.14.6，`/private/tmp/webuddy-developer-mcp-venv/bin/python`。首次执行未安装 pytest，在测试收集前退出 1，保留 [原日志](pytest.log)。在该临时 venv 安装 pytest 后重跑，安装记录见 [dependencies.log](dependencies.log)。

实际重跑命令：

```sh
/private/tmp/webuddy-developer-mcp-venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_browser_verify.py tests/test_project_tests.py tests/test_testbox_mcp.py \
  tests/test_reform_mcp.py tests/test_reform_tenant_mcp.py tests/test_workbench_mcp.py \
  --junitxml=docs/self-improvement/evidence/testing-loop-20261107/results.xml
```

重跑退出码 0：**90 项通过，7 个子用例通过，0 失败、0 跳过，耗时 92.97 秒**。JUnit 的 tests=97 包含子用例，不宣称 97 种独立业务场景。原件：[pytest-retry.log](pytest-retry.log)、[results.xml](results.xml)。

这些检查包含结果分类、版本绑定、真实临时 Git／适配器执行，以及正式 SDK stdio/HTTP 协议；测试机 SSH、部分模型／调度使用测试替身，任务和账号是合成测试数据。`test_browser_verify.py` 使用构造报告与 PNG 占位字节验证判定规则，不能称为实际截图或页面验收。没有运行客户模型、真实客户任务或客户业务验收。

## 当前提交的远端 CI

现场查询 [push 运行](https://github.com/auntunt/webuddy-pitch/actions/runs/42358680840) 和 [另一条运行](https://github.com/auntunt/webuddy-pitch/actions/runs/42358684634)，两者 headSha 均为上述基线。查询原件：[ci-current.json](ci-current.json)、[ci-current-pr.json](ci-current-pr.json)。

两条运行均为 cancelled；各自 Linux 3.11／3.13 完整套件成功，正式 SDK MCP 两版成功，Windows 执行证据专项、快速检查与安装包检查成功；Windows 两版完整套件取消。没有把 cancelled 或 continue-on-error 当通过，也没有用旧版本全量数量替代本轮结果。

## computer use 现场操作记录

以下是本会话工具回执的人工可读记录，不是自动化产品报告。操作者为 Agent，无客户人工操作。

| 顺序 | 实际工具动作 | 回执与范围 |
|---|---|---|
| 1 | `cua.getState()` | 能列出本机应用；`browsers=[]`，错误原文 `Browsers: Error: The browser access host is unavailable` |
| 2 | `cua.getApp('com.apple.finder')` | 读到访达现有窗口与可访问性树，证明原生应用读取可用；没有点击、输入或修改文件 |

原始回执留在本次会话工具记录。访达包含个人文件名，不将整份桌面内容复制进 Git。没有产生截图，不虚构截图证据。网页导航、点击、输入、截图及原生应用写操作均未验证；Windows 桌面 GUI 未连接验证。需要恢复浏览器宿主连接后，用隔离任务补跑“打开→输入→操作→状态读回→原图截图”。先前 ERP 演练截图属于其旧版与指定演练，不能替代这一步。

产品 `browser_verify.py` 的 Playwright 宿主与本会话浏览器宿主分别配置；本会话连接失败不证明产品 Playwright 一律不可用。反过来，Playwright 通过也不证明通用桌面控制已接入。受限项目客户端显式禁用宿主 computer_use，本轮不修改安全边界。

## 测试站与交付边界

已读本机接入约定后，只读查询 43 测试站：运行目录 `/opt/webuddy/releases/reform-847f8605/app`，服务 active、PID 1877418、NRestarts 0。比对当前仓库 218 个受 Git 管理的 tmh 文件，缺失／摘要不一致为零，见 [runtime-check.json](runtime-check.json)。此检查只覆盖 tmh 文件，不声称本轮重做全部部署清单、数据库完整性或真实租户认证验证。

本轮无应用发布、无服务重启、无数据库写入、无阿里云生产操作。之前真实租户 MCP 503 修复与重连证据仍见进度中 c80251ed 的记录，不能当成本轮重新执行。

仍未完成：当前版本真实网页交互与截图、Windows 完整套件通过、Windows GUI、客户两机与真实业务链路。本轮文档完整不等于这些环境已验收。
