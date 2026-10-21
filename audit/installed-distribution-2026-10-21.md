# 安装包与发布门禁复核（2026-10-21）

起点：`iteration/context-pack-v2` 的 `016a5ede90288f1dac493ae4c9c91bd86c26cdc6`。
`v0.4.0` 仍指向 `a0af1994d50e0403a5714b287b441f8b3493cc2e`；本文记录标签之后的修复。

## 发现与修复

1. **安装后的项目安装命令失败。** 原 `pyproject.toml` 只打包 Python 模块和规则 JSON，未包含根目录下的 `kb`、模板、技能、代理与命令文档。实际把包安装到独立目录，再从源码目录之外执行 `tmh install`，复现 `FileNotFoundError: .../before-installed/kb`。
2. **原发布检查误通过。** 原检查在源码目录中执行 `import tmh`，Python 优先加载当前目录的源码，即使设置了 `PYTHONPATH`。基线 `release-check.sh` 报告 PASS 7 / FAIL 0 / SKIP 1，与上述真实命令失败同时成立。
3. **离线包与工具自刷新也存在缺口。** 离线清单未包含安装时必读的 `docs/agent-commands.md`；从项目内置工具重新安装到自身时，复制逻辑会先删除自身代码目录。
4. **GitHub CI 没有启动任何任务。** 基线 [Actions run 39548563473](https://github.com/auntunt/webuddy-pitch/actions/runs/39548563473) 在工作流解析阶段失败；actionlint 1.7.12 明确报告第 21 行 `no_proxy` 与第 20 行 `NO_PROXY` 重复，`env` 键不区分大小写。删除重复声明后配置检查通过；测试进程仍由 `tests/conftest.py` 设置两种大小写。

修复采用统一资源清单 `tmh/resources.py`，构建 wheel 时把原文件复制到包内 `_resources`。源码、wheel、内置工具与离线包使用同一资源来源；安装前先检查资源完整性。自刷新跳过相同源/目标目录。未增加第三方运行时依赖。

`scripts/installed-smoke.py` 在 `python -I` 隔离进程中确认实际导入位置，依次验证命令入口、项目安装、内置工具自刷新、完整资源的逐字节比较、离线包校验和解包安装。Bash、PowerShell 发布检查和 Ubuntu/Windows CI 共用该检查。用新检查测试旧安装包时，检查仍因缺少 `kb` 失败，证明能识别原问题。

## 本机验证

环境：macOS arm64，Python 3.12.7，Git 2.55.0；构建与测试依赖置于单独虚拟环境。

| 检查 | 实际结果 |
|---|---|
| 资源与安装回归用例 | 7 passed |
| wheel 安装后的隔离功能检查 | PASS；离线包 168 个文件校验通过 |
| sdist → wheel → 安装 → 隔离功能检查 | PASS |
| sdist 构建出的 wheel 与当前源码资源比对 | 41 个资源文件逐字节一致；wheel SHA-256 `4aaf1f63363876922ca9988059698d9abf5afb4a1316fd3ed7064b0cb282a1b7` |
| 干净运行时 venv 的真实控制台入口 | `tmh --version`、`webuddy --help`、`tmh install` 均通过，运行目录位于源码之外 |
| 发布检查 `INSTALL_SMOKE=1` | PASS 7 / FAIL 0 / SKIP 1；收集 1026 项，fast 60 passed，关键套件 45 passed；外部 `ops/tests` 未随仓库提供，按脚本跳过 |
| actionlint 1.7.12 | 修复前重复键报错；修复后退出码 0 |
| 测试机传输与分发回归 | 10 passed |

第一次全量回归为 **1009 passed / 1 failed / 16 skipped，326 subtests passed**。唯一失败是测试机传输用例调用了开发机的真实 `pnpm --version`，Corepack 自动下载 pnpm 到临时 home 的 `.cache/node/corepack`，导致“传输结束后 home 为空”的断言失败。

为版本探测提供固定工具替身后，仍保留真实 Git、SSH/SCP 本地替身、补丁传输、构建结果与清理断言，针对该组的回归 10 项通过。完整复跑结果为 **1010 passed / 0 failed / 16 skipped，326 subtests passed**（342.83 秒）。16 个跳过项均为当前验证环境未安装的可选 MCP SDK 或 cryptography 覆盖；未把这些用例计为通过。测试前后 249 个源码、测试与目录资源文件的摘要一致。

全量复跑日志 SHA-256：`4cfd9fb09db1edaceb09590f082396a40009bb0a71a27af23aaeb7cd355a2c68`。

## GitHub 上的跨平台复核

提交 `14c9de7` 后的 [Actions run 39560780630](https://github.com/auntunt/webuddy-pitch/actions/runs/39560780630) 已能启动任务，Linux 安装检查与四组快速测试通过。Windows 安装检查实际复现 `UnicodeEncodeError: 'charmap' codec can't encode characters`：`python -I` 会忽略工作流设置的 `PYTHONUTF8` / `PYTHONIOENCODING`。

后续修正仅为隔离检查及其子进程显式传入 `-X utf8`，同步调整分发回归用例与 Bash/PowerShell/CI 调用；未改动运行时代码。修正后本机针对分发/测试机的 10 项回归、发布检查（PASS 7 / FAIL 0 / SKIP 1）与 actionlint 均通过。上文全量本机结果来自该编码修正之前的安装发布修复。Windows 是否通过须查看修正后的 Actions 结果，不能由本机结果推断。

## 复跑方法

```sh
python3.12 -m venv /tmp/tmh-check
/tmp/tmh-check/bin/python -m pip install pytest setuptools wheel
PYTHON=/tmp/tmh-check/bin/python INSTALL_SMOKE=1 bash scripts/release-check.sh
/tmp/tmh-check/bin/python -m pytest tests -q -ra -p no:cacheprovider
```

独立安装包验证：

```sh
/tmp/tmh-check/bin/python -m pip install . --no-deps --no-build-isolation --target /tmp/tmh-installed
/tmp/tmh-check/bin/python -I -X utf8 scripts/installed-smoke.py /tmp/tmh-installed
```

使用新建的临时目录，避免混入旧包。原始日志、构建产物、修复前安装包和文件摘要保存在本次 Mac 工作区的 `部署包/context-pack-v2-20261021-verification/`，不包含平台数据库、账号或密钥。

## 验证范围

本次验证针对 GitHub 分支的代码和分发功能。服务器侧部署、真实工单 G1、40 例回放 G2、标品试点 G4、Claude 登录与性能 G6/G7 仍须按 `docs/NEXT-STEPS.md` 实测。Windows 执行结果以 GitHub Actions 为准；本机未把 Windows 或 PowerShell 检查标为通过。
