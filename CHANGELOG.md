# Changelog

本项目版本号以 `pyproject.toml` 与 `tmh/__init__.py` 为准，两者必须一致（`scripts/release-check.*` 会校验）。
格式按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 组织，分组含义：

- **Added**：新增能力/入口
- **Changed**：行为或接口变化（升级时需要留意）
- **Fixed**：修复
- **Experiment**：实验性/试点结果，不是产品承诺
- **Negative result**：负结果，记录下来避免重复投入

## [Unreleased]

### Fixed

- 安装包现在包含项目安装所需的模板、技能、知识库、子代理和命令文档；从源码、wheel 或内置工具启动时使用同一份资源清单。补齐离线包缺失的 `docs/agent-commands.md`，内置工具刷新自身时保留工具文件。
- 发布检查使用隔离 Python 进程验证实际安装路径，并执行项目安装、重复安装、离线包校验及离线安装。旧检查在源码目录导入 `tmh`，可能误把源码检查结果当成安装包验证。
- 修复 CI 全局环境中 `NO_PROXY` / `no_proxy` 重复键导致的工作流启动失败，并增加 Ubuntu/Windows、Python 3.12 的安装包功能检查；修正交接文档的账号创建命令，明确发布检查所需的开发依赖。
- 测试机传输测试为无关的工具版本探测提供固定替身，保留真实 Git、补丁传输和清理断言，避免开发机 Corepack 下载 pnpm 并写入测试目录造成误报。

## [0.4.0] - 2026-10-21

本轮主题：**上下文供给契约（Context Pack v2）+ 组织知识与习惯 v0 + 本地试点/RSI 基线 + 发布物整理**。
分支 `iteration/context-pack-v2`，基线 `3220e3d`，发布提交见 `git log`。本版本没有引入任何第三方运行时依赖
（`dependencies = []`），Python ≥ 3.8 可运行，生产目标为 Python 3.12。

### Added

- **Context Pack v2**（`tmh/context_pack.py`）：`tmh context` 新增 `--json` / `--pack` / `--source <目录>` /
  `--require-all` / `--label`。结构化上下文包带来源、版本、逐条溯源与预算；预算不足时输出
  `used / omissions / complete`，每条未展开项带 `full_text` 句柄，不再静默截断。
- **多来源检索**：同一上下文包可混合当前项目与参考项目（`--source`），同名符号使用独立命名空间，不合并；
  任一来源不可用时 `--require-all` 直接失败，否则在包内显式标注来源不可用。
- **平台接入 Context Pack**：平台侧任务上下文改走 v2（`de7ebd8`），运行记录可审计“这单喂了什么”。
- **Org knowledge v0 + 本地多项目试点**（`7c5dd8d`）：组织级知识检索 v0；G4 本地多项目试点跑通，结果见
  `audit/g4-g8-report.md`。
- **Habits v0**（`c249bbb`）：只读开发者习惯推导（G9），不写入项目数据，结果见 `audit/g9-report.md`。
- **RSI 本地评测**：本地模型 RSI 基线、上下文质量 golden harness 与调参旋钮（`86f4d78`、`test_rsi_local_eval.py`），
  报告见 `audit/rsi-local-report.md`、`audit/evidence-rsi-local-report.md`。
- **证据/RSI 本地演示**（`5d31215`）：本地证据 E2E 与 RSI 回放 demo，可离线复跑。
- **运维自动化工具**（独立目录 `D:\DSH_project\ops\`，不属于本仓库包）：零依赖 `ops.mjs` CLI + MCP server，
  覆盖 dns/http/tls/app login-check/deploy drift/evidence verify/ssh exec/server audit；SSH 只读白名单、
  危险命令默认 deny、凭据只从环境变量读取。
- **发布物**：`CHANGELOG.md`（本文件）、`docs/DEPLOY.md`、`scripts/release-check.ps1|.sh`、
  `audit/release-readiness.md`。

### Changed

- `tmh/context.py`：末尾截断逻辑从 `text[:budget]` 静默截断改为带“省略 N 字符 + 如何读全文”说明的预算内截断
  （旧路径行为保留，可通过 `--legacy` 触发）。
- `tmh context` 默认输出已切到 v2 文本；`--legacy` 保留旧版单项目线性文本，旧脚本可继续用。
- `pyproject.toml` / `tmh/__init__.py` 版本 `0.3.0 → 0.4.0`；`server` 响应头/`static?v=` 由 `__version__` 自动跟随。
- CI（G5）：`fast gate` 固化为 7 个纯单元模块；Ubuntu + Windows、Python 3.11/3.13 矩阵，Windows 全量套件
  继续 `continue-on-error`（已知平台限制见 `audit/ci-test-report.md`）。测试环境统一 `PYTHONUTF8=1` 与
  `NO_PROXY=127.0.0.1,localhost,::1`。

### Fixed

- Windows 无 `resource` 模块时 `project_knowledge` 快照构建不再失败（`peak_rss_bytes=null`）。
- 重复来源名冲突：参考项目与当前项目同名符号使用唯一命名空间，避免 id 合并导致溯源错误。
- 测试在 Windows/CI 下的可信度问题（编码、回环代理、平台分支），见 `audit/ci-test-report.md`。

### Experiment

- G4 本地多项目试点（`test_g4_local_pilot.py`）：本地多项目知识检索与上下文包合并可用，规模仍远小于真实客户仓库。
- G2 本地 RSI 基线：以本地模型跑上下文质量评测，用于后续对比，不是效果承诺。
- 证据包 + RSI 回放 demo：本地离线复跑通过，生产签名链未在本轮重新演练。

### Negative result

- G3：部分离线/大规模检索组合在当前实现下没有收益或不可行，结论与数据见 `audit/rsi-local-report.md`；
  不把它包装成“能力已就绪”。
- 服务器侧 G1/G2/G6/G7 未在本轮运行，不能据本地结果宣称线上表现。
- Context Pack 规模验证尚未使用真实客户仓库；按项目库设计 §9 阶段 D 的规模测试仍待做。

## [0.3.0] - 2026-10-19

上一发布版本（平台、证据包、预览健康、Harness² 验证策略等）。本文件自 0.4.0 起维护；更早历史见
`docs/self-improvement/STATUS.md` 与 git 历史。
