# 当前状态与下一步：是否还需要继续开发？

> 日期：2026-10-21。版本 **0.4.0**。分支 `iteration/context-pack-v2`，tag `v0.4.0` 指向发布代码 `a0af199`。原始交接记录为 `74d8c08`，README 指针更新为 `016a5ed`；此后本分支含下述安装发布补丁，标签保持不变。
> 本文是交接说明：写给"复核 + 部署"的人（人类或另一个 AI）。**先读本文，再读 `docs/DEPLOY.md`。**

> **Mac 接续复核（2026-10-21）**：已拉取 `016a5ed` 并实际复现安装包缺少知识库资源、旧发布检查误导入源码的问题，同时修复 CI 工作流重复环境变量键导致的启动失败。补丁详情与验证记录见 [安装包复核](../audit/installed-distribution-2026-10-21.md)。

> **生产发布已完成（2026-10-21 16:28 CST）**：`affe0a2` 已上线。服务器全量 1013 passed / 14 skipped，326 subtests passed；公网与回环 28 项读取检查通过，原有数据和配置保持。见 [生产发布验证](../audit/production-deployment-2026-10-21.md)。此后的文档同步不改变该生产代码版本；真实工单交付等业务验收仍待执行。

## 1. 结论（一句话）

**基础发布验证已完成，继续真实业务验收，优先修复实测发现的问题。** 安装包复核已补齐发布缺口，Linux 服务器已完成升级、读取检查和数据保全核验；剩下的 roadmap 事项依赖真实任务与真实数据。下一轮功能开发应由实测结果决定。

## 2. 0.4.0 是什么（已交付）

本版本基于作者 2026-10-20 的 main 导出（基线提交 `3220e3d`，tarball 导入，**历史与上游 main 无关**），在其上完成：

| 类别 | 内容 |
|---|---|
| 上下文供给 | Context Pack v2 成为 `tmh context` 默认输出：带来源/commit/知识修订/逐条溯源/full_text 句柄；预算不足时输出 `omissions`+`complete`，不再静默截断；`--legacy` 保留旧文本 |
| 平台接入 | 平台任务上下文走 v2（运行目录 `runs/<id>/context.json` 回执）；渲染保留 `flow:`/`tbl:` canonical id；`kb_followup` 优先读回执（修复 v2 后分析不补知识页的回归） |
| 组织知识 v0 | `tmh/platform/org_knowledge.py` + `GET /api/org/knowledge` + `tmh platform org-knowledge`（只读聚合、provenance、同名不合并、不复制正文） |
| 开发者习惯 v0 | `tmh/platform/habits.py` + `GET /api/projects/<key>/habits` + `tmh platform habits`（只读、默认脱敏、团队视图 `MIN_SAMPLE=5`） |
| 多项目本地试点 | `tools/g4_local_pilot.py`（固定 revision/引用/派生/失效）；平台 HTTP/表写入未做 |
| RSI 本地基线 | `benchmarks/run_rsi_local.py`（本地 Ollama × 16 任务：cold 找全率 0 → 上下文包 0.3333）；线上 40 例回放未做 |
| 测试/发布 | Windows 平台单点修复、13 测试文件 UTF-8、Python 3.10 sqlite 兼容层、CI 矩阵、`CHANGELOG.md`、`docs/DEPLOY.md`、`scripts/release-check.*` |

## 3. 原始交接的验证数字（作者设备，补丁前）

以下保留原始验证记录。后续安装包复核证明仅 `pip install`、`--help`、源码目录内 `import tmh` 通过不足以验证安装功能；补丁后的结果以 [安装包复核](../audit/installed-distribution-2026-10-21.md) 为准。

- Windows：`release-check.ps1` → PASS 6 / FAIL 0 / SKIP 1（`-InstallSmoke` PASS 8/0/0）；collect-only **1022 tests / 0 error**；fast gate **58 passed / 2 skipped**；关键套件 43 passed。
- Linux（WSL，部署目标）：`test_platform.py` **58 passed / 1 failed**——唯一失败是 readiness 依赖 `git>=2.38`（WSL 是 2.34，CI runner 满足，属环境限制）；全量修复后折算 ≈**1005 passed / 1 failed / 0 error / 16 skipped**（node 在 PATH 时）。
- 打包：`pip install .` rc=0（`tmh-harness-0.4.0`），`tmh --help` / `webuddy --help` / `import tmh` 均正常。
- 回归：`test_analysis_writes_the_flow_pages_it_touched` 在 Linux 上由失败 → 通过（canonical id + context receipt 修复）。

## 4. 部署步骤（部署者照做）

下方为首次安装示例。本次生产发布沿用原服务和外部配置，通过独立版本目录与符号链接切换完成；现有生产机升级应先按 [生产发布验证](../audit/production-deployment-2026-10-21.md) 核对当前版本和回滚准备，不重复初始化账号或替换配置。

前置：Linux、Python **3.10+**（生产目标 3.12）、**git ≥ 2.38**、node 20+（仅 UI 测试需要）、零第三方运行时依赖。

```bash
git fetch origin iteration/context-pack-v2
git checkout iteration/context-pack-v2          # 或 git clone -b iteration/context-pack-v2

python3.12 -m venv /opt/webuddy/venv
/opt/webuddy/venv/bin/pip install .
/opt/webuddy/venv/bin/tmh --help                # 入口自检
/opt/webuddy/venv/bin/tmh user add <name> --data /opt/webuddy/data   # 交互输入密码；已有账号无需重复创建
/opt/webuddy/venv/bin/tmh serve --host 127.0.0.1 --port 8790 --data /opt/webuddy/data
```

Caddy 反代、systemd 托管、备份、升级回滚、安全清单：见 [`DEPLOY.md`](DEPLOY.md)（含 systemd unit、Caddy 配置、备份对象 `platform.db` + 签名密钥、回滚步骤）。

## 5. 部署后必须验证的事项（按顺序）

本次已完成全量回归、独立服务启动、登录页渲染、共享令牌只读访问与数据保全验证。以下清单保留业务验收要求；`/api/readiness` 全项、生产账号登录后的业务操作及 G1/G2/G4/G6/G7 不因发布成功而记为通过。

| # | 验证 | 通过标准 | 失败时看 |
|---|---|---|---|
| 1 | `scripts/release-check.sh` | PASS，无 FAIL | 脚本输出；先跑 `pytest --collect-only` 定位 import 错误 |
| 2 | `GET /api/readiness` | 无 `bad` 项（git/node/agent 视部署取舍） | `docs/DEPLOY.md` FAQ + readiness 明细 |
| 3 | 登录 + 打开工作台 | 登录 200，页面正常 | 账号/`TMH_TOKEN`/反代头 |
| 4 | **G1 证据闭环**：挑 1 张真实工单走 分析→改码→验证门→`/e/<KEY>.intoto.json` 非 404→签收→关单 | 证据包 `predicate.status != none`、`missing` 为空；离线 verify 通过 | 平台日志、`tmh evidence-verify`、验证门输出 |
| 5 | **G2 40 例回放**：`POST /api/projects/<key>/evals/run`（页面入口） | 产出找全率/准确率基线；经验卡 `used>0` | `learn.py`/`agents.py` 接线、`impact.fair` |
| 6 | **G4 标品试点**：登记标品+参考 → 固定修订 → 客户绑定 → 有来源检索（同名分列）→ 派生 → 局部失效 | `revisions/references` 非空；设计 §9 反例全过 | `project_library` API、知识快照构建 |
| 7 | G6/G7：Claude 登录、首调性能 | `agent:claude=ok`；首屏 API P95<1s | readiness、请求耗时 |

> 运维冒烟工具 `ops`（DNS/TLS/HTTP/login-check/evidence verify）在作者本机 `D:\DSH_project\ops`，**不在本仓库**；仓库内等价检查用 `scripts/release-check.*` + `curl`/`/api/readiness`。

## 6. 已知限制（如实声明，不要当"已完成"）

1. **此独立历史分支尚未合入 main**：本分支从 tarball 导入；合并前请先更新目标远程引用，再用 `git diff --stat github/main..HEAD` 复核真实改动。此项不代表 main 从未有过其他更新。
2. **Windows 全量仍未通过**：原始交接记录为约 47% 中断。后续 `affe0a2` 的两组 Windows 全量 CI 已结束且失败（非阻断）；两平台安装检查与快速测试通过。原记录提到的 `supervised execution requires POSIX` 是已知限制，不能据此把所有 Windows 失败都判为同一原因。
3. **服务器基础发布已验证，业务验收未完成**：G1/G2/G4/G6/G7 仍未在本次生产验收中执行；发布、只读 API、数据保全与真实任务交付分开记录。
4. **组织知识/习惯只有只读 API+CLI，没有 UI**；团队视图需要真实多账号数据。
5. **"百万行"未验证**：本地规模测试基于样例项目；接真实标品前不要对外做规模结论。
6. 未引入任何第三方运行时依赖；`[mcp]` 为可选扩展。

## 7. 如果之后还要继续开发（由数据触发，不是由 roadmap 触发）

| 优先级 | 开发项 | 触发条件 |
|---|---|---|
| P1 | G8/G9 只读 UI（组织知识页、习惯面板） | 部署方在界面上确有使用需求 |
| P1 | G4 平台侧接线（HTTP/表写入 + 真实标品试点后续） | 拿到真实标品仓库，且前 3 个验证步骤通过 |
| P2 | 检索结构解析升级（ast-grep/tree-sitter 方向）+ 50+ 任务 RSI 评测 | 真实标品上"找不到相关代码"成为主要失败模式 |
| P2 | 静态盲区报告、前端调用链 | 同上 |
| P3 | Windows 全量清零、`server.py` 拆分治理 | 纯工程债，不影响交付 |

## 8. 复核者的建议检查顺序

1. 本文 → 2. `README.md` 顶部指针 → 3. `docs/DEPLOY.md` → 4. `CHANGELOG.md` → 5. `git diff --stat origin/main..HEAD`（或按提交逐个看）→ 6. 跑 `scripts/release-check.sh` → 7. 抽查 `tmh/context_pack.py`、`tmh/platform/{org_knowledge,habits}.py`、`tests/test_*api.py`。

安全核对：仓库无凭据；`git grep -nE "password|secret|token" -- '*.py'` 只看环境变量读取，不落盘。
