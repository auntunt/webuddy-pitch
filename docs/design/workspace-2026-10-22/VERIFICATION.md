# Webuddy 工作区发布与验收记录

日期：2026-10-22。**已于 2026-10-22 02:08:51 CST 上线，02:11:08 CST 延迟检查通过。** 本文不包含客户原文、业务数据库、账号密码或密钥。

## 1. 版本与发布状态

| 对象 | 已知事实 | 当前结论 |
| --- | --- | --- |
| 主功能提交 | `67981d06e0f4d42f8eb4cbdb294c6aab6b45245a`，已推送 GitHub | 工作区、团队流程、记忆与交接的主功能已入库 |
| 最终代码候选 | `369ec16f58861c779eadec887ea22b5ea7d1e1ba`，追加任务状态标记的 CSS 隔离修补 | 已同步 GitHub `iteration/context-pack-v2`，服务器全量、迁移演练、切换及延迟检查通过 |
| 较早服务器目录 | `67981d0` 只执行了 stage | 没有执行该候选的 validate 或 activate；不得称其通过服务器测试或已上线 |
| 预期生产旧版本 | `affe0a29c4eff9cbbde8a11f1dc1a1935b7bf5b8` | 切换前已实测核对，旧版本保留以供代码回退 |

主功能提交和最后的 CSS 修补分开记录。较早工作树的测试结果可以支持对应改动，但不能替代 `369ec16` 最终包在服务器 Python 3.12 上的完整验证。本文新增记录也不改变已打包程序的提交身份。

## 2. 已完成的本机验证

以下结果来自本轮主任务的测试与实屏回读记录；本文整理时没有重新执行测试，也没有向生产提交业务请求。集成说明见 [README 第 10 节](README.md#10-集成实现与实屏回读2026-10-22)。

| 验证 | 已记录结果 | 适用范围 |
| --- | --- | --- |
| 首轮全量 unittest | 1,069 项完成，其中 16 项可选依赖跳过 | 本机该轮工作树；不是“1,069 项全部通过”，不覆盖后续全部修补 |
| 后续集中回归 | 108 项通过 | 对应集成后的集中复测；与全量结果存在重叠，不能相加作为独立用例数 |
| 团队安全修补回归 | 52 项定向测试通过 | 对应最终团队责任、复核和旧入口约束修补；不等于最终候选全量通过 |
| 部署脚本自检 | 语法、旧提交临时打包读回、原表行 hash、追加 schema 与回滚故障注入通过 | 打包/部署工具的本机验证，未运行生产切换 |
| 独立合成 HTTP smoke | 19 项通过，合成服务正常退出，临时数据清理 | 本机 Python 3.14 的临时工作树副本；不能替代服务器 Python 3.12 结果 |

本机完整日志已复制到仓库外 `部署包/workspace-20261022/candidate-final/`，SHA 清单为 `local-test-evidence.json`。集中回归命令为 `PYTHONPATH=tests NO_PROXY=127.0.0.1,localhost TMH_UNDERSTAND=rules python3 -m unittest tests.test_workspace tests.test_memory_workspace tests.test_ui_memory tests.test_team_workspace tests.test_external_candidates_independent tests.test_login tests.test_ui_library -q`。可选依赖跳过保留为未验证范围，不通过删去跳过项改善结果表述。

### 实际浏览器操作

验证使用本机隔离的虚构项目和测试账号。截图来自实际界面，不是生成设计板；不代表客户业务验收。

| 路径 | 实际操作与观察结果 | 可回看产物 |
| --- | --- | --- |
| 登录 → 工作台 → 项目 | 使用真实登录流程进入；本人任务依据登录身份显示；项目及主要入口可达 | [桌面工作台](screenshots/workspace-desktop-final.png) |
| 团队责任分配 | 修改负责人和独立复核人；保存后读回；关闭详情后列表同步显示新分配 | [分配后的列表](screenshots/team-assignment-refreshed.png) |
| 经验共享 → 跨项目引入 | 在虚构 OA 项目整理共享副本；CORE 项目引入后读回“已引入本项目，仍按相关度选择” | [经验引入结果](screenshots/memory-import-final.png) |
| 项目交接 | 生成并确认指定版本；按章节阅读，来源清单折叠展开；下载完整 Markdown 后与持久化正文逐字符比较 | [桌面交接](screenshots/handoff-desktop-final.png) |
| 导出完整性 | 下载正文为 **38,466 字符、52,130 字节**，与持久化正文一致 | 数量与比对结果已记录；导出原文不随公开发布记录提交 |
| 窄屏布局 | 390×844 视口无横向溢出；固定底部导航实测位于 **y=780**，长页滚动不再带走导航 | [手机工作台](screenshots/workspace-mobile-fixed.png)、[手机交接](screenshots/handoff-mobile-final.png) |

桌面检查视口为 1680×825。页面 console error 查询为空。独立视觉复评为 **8/10**，在评审截图范围内没有阻断项；该评分只表达视觉与阅读评审，不代表功能覆盖率、可访问性认证或业务成功率。交互结果另由上述操作回读与测试支持。

图片保留原始文件与原始字节，没有压缩、重采样或用缩略图替换。设计方向与生成设计板仍在 [设计说明](README.md)，不能作为实际功能通过的证据。

### 重点回归约束

- 本人队列使用真实登录身份，显示名或 Agent 标识不能冒充人工责任人；团队分配检查并发修订，拒绝自己复核自己提交的候选。
- 固定候选的技术检查、人工复核、本地主干合并和业务验收分别记录。需求、候选证据、预览或责任分配改变时，相关批准需要重新核对。旧接口不能绕过已分配团队责任或固定候选验收约束。
- 同类问题建议限同一项目，保留完整原工单；人工确认/排除绑定可见 fingerprint。来源变化不能沿用过期确认。
- 外项目经验进入任务必须经过共享及当前项目引入；实际使用保留来源记录。项目交接保留历史版本，来源变化显示 stale 理由，旧版不会用新版来源重建。
- 长交接按结构化章节阅读，来源页面按需展开，完整 Markdown 导出保持不变；较晚返回的旧请求不能覆盖已经切走的页面或当前版本。

相关回归定义可查看 [团队测试](../../../tests/test_team_workspace.py)、[工作台测试](../../../tests/test_workspace.py)、[记忆后端测试](../../../tests/test_memory_workspace.py)和[记忆界面测试](../../../tests/test_ui_memory.py)。测试定义是覆盖范围说明，不独立证明某次运行通过。

## 3. 交接入口与 API

| 用户入口 | 路由 | 用途 |
| --- | --- | --- |
| 工作台 / 项目 | `#/workspace`、`#/projects` | 从当前任务、责任和项目范围进入工作 |
| 团队 | `#/team`，视图 `mine / team / review / unassigned` | 分配责任、查看交付证据及执行明确的人工作业 |
| 知识与记忆 | `#/memory` | 检索来源、管理候选/确认/停用状态、组织共享与项目引入 |
| 项目交接 | `#/handoff/<project-key>` | 当前及历史交接版本、来源有效性、确认与全文导出 |

旧任务、知识、重构与交付入口继续保留；新的一级导航没有删除这些流程。

| API | 参数或动作 | 使用边界 |
| --- | --- | --- |
| `GET /api/workspace` | `project`、`view`、`q`、分页参数 | 读取真实任务派生的工作队列；不触发执行 |
| `GET /api/team` | `project`、`view`、`ticket`、`offset`、`limit`；`request_id` 读取本人回执 | 读取责任、候选、技术检查、人工决定及未决请求 |
| `POST /api/team` | `assign`、`claim`、`comment`、`run_recheck`；`candidate_submit / verify / cancel / preview / assess / merge`、`review`、`business_accept` | 必须是有效个人账号；具体动作受负责人、复核人、固定证据和请求回执约束 |
| `GET /api/memory` | `project`、`q`、`section=overview / knowledge / lessons / clusters / brief` | 组织目录用于查阅，不自动授权把所有项目内容注入任务 |
| `GET /api/memory/brief` | `project`、可选 `revision` | 返回完整 `markdown`、结构化 `sections`、来源、版本与 stale 状态 |
| `POST /api/memory` | `lesson_create / edit / confirm / retire / restore / share / unshare / take / untake`；`cluster_scan / confirm / exclude`；`brief_generate / confirm` | 明确项目和操作者；确认绑定当前来源。启用个人登录的部署中，共享 token 不能替代人工确认 |
| `GET /api/org/knowledge`（既有入口增强） | `q`、`type`、`limit` | 只读组织目录与带来源检索；不运行模型或构建任务 |

接口实现在 [server.py](../../../tmh/platform/server.py)、[team.py](../../../tmh/platform/team.py)、[memory.py](../../../tmh/platform/memory.py)与[workspace.py](../../../tmh/platform/workspace.py)。本表是交接索引，调用方仍需按接口字段及错误回执处理冲突与待决状态。

## 4. 明确的能力边界

- 当前是共享工作区，任务责任与独立复核不是企业多租户或项目级访问隔离。组织目录可查阅不等于可以跨项目自动使用全部内容。
- 记忆复用保留适用范围并按相关度选择。共享采用人工整理的副本；过长共享字段明确报错，不静默截断原经验。没有自动“所有经验永远有效”的保证。
- 同类问题是保守且可解释的建议，不自动合并工单、不删除原文、不关单，也不把相似度当作问题原因相同的证明。
- 项目讲解/交接由已有结构化事实和完整来源整理。没有资料的未知系统不会被补写为已理解；历史版本、未确认内容和过期理由继续可见。
- 团队候选合并写入项目的本地主干，不等于推送 GitHub、部署客户环境或客户签收。平台“已出版本”也不构成生产部署回执。
- 本轮没有验证广联达真实业务数据、完整 Java/.NET 重构迁移、标品归并成效或组织提效指标。合成项目功能验证不替代这些业务验证。
- 可选依赖跳过、Windows 实机兼容性、未覆盖视口/辅助技术，以及生产真实账号的完整业务旅程，不因本轮本机结果而自动通过。

## 5. 服务器最终验收与上线证据

正式程序提交为 `369ec16f58861c779eadec887ea22b5ea7d1e1ba`，后续提交仅补充文档与截图，不改变这一运行身份。入口：[Webuddy](https://webuddy.bbstack.date)。

| 检查 | 实际结果 |
| --- | --- |
| 包身份 | 181 个运行文件、365 个验证源码文件与最终提交逐字节/权限一致；tar 成员在本机与服务器读回 |
| Python 3.12.3 全量 | **1085 passed / 14 skipped / 342 subtests passed**，470.70 秒，零失败；14 项为未安装可选 MCP SDK |
| 隔离合成服务 | **19 项 HTTP 检查通过**，进程退出 0，临时数据已清理；覆盖工作区、团队读取、记忆创建/确认、分组确认、交接生成/确认及共享 token 拒绝写入 |
| 迁移 | 原 26 表全部原列/原行 hash 保持；追加 7 张空表，第二次初始化 schema 幂等 |
| 备份 | `/opt/webuddy/backups/pre-369ec16f5886-20261021T180849Z`，0700；完整 app/data/config，1767 个数据成员逐项读回一致 |
| 原子切换 | `/opt/webuddy/app` → `/opt/webuddy/releases/369ec16f5886-workspace-20261022/app`；02:08:51 CST 启动，PID 971250、实际 cwd 正确 |
| 数据保全 | 原 3 项目、49 工单、254 运行、739 事件及其余原表记录不变；原非 DB 文件字节/权限不变，无新增数据文件 |
| 配置/其他服务 | 外部环境、systemd 单元、Caddy 配置 SHA 保持；Caddy、factory-web 状态/PID保持 |
| 本地读取 | 激活时 8 项检查通过，含匿名 API 401、新 workspace/team/memory 接口及现有身份/自动流转设置 |
| 延迟检查 | 启动约137秒后，回环+公网16项读取检查通过，PID保持、自动重启0、完整性ok、原数据继续不变 |
| 错误日志 | 发布启动以来 systemd error 级日志行数为0 |
| 实际公网 UI | Chrome 实际打开登录页并检查原始截图；未用生产账号提交真实工单或执行模型任务 |
| 回退 | 本次未触发回退。旧程序和完整备份保留；若回退，应只切程序，不用旧数据覆盖新的用户写入 |

新增空表：`code_candidates`、`candidate_assessments`、`candidate_decisions`、`candidate_team_decisions`、`candidate_merges`、`ticket_team`、`team_requests`。

运行包 SHA-256：`29e77503d7762f0b4d7ab6d519b5908be6117d80ce0405fa687509e224b5d296`。
验证包 SHA-256：`34feeaf1697a5dc0029a2e21a6181d9b3344b6ad130d242cc23a0f99801c5c71`。
全量日志 SHA-256：`a09b26aee973e3ae318133c54285a0397f633c20f7bcf875fc324cd040232d5a`。

服务器证据位于上述 release 的 `verification/`、`migration-rehearsal/`、`deployment.json`、`postcheck.json`。9 份完整证据已下载到本机仓库外 `部署包/workspace-20261022/candidate-final/server-evidence/`，全部 SHA 读回一致；索引为 `readback-manifest.json`。备份内业务资料、密钥及完整浏览器周边内容没有进入 GitHub。原验证 SSH 连接未正常收尾，后人工中断本机连接；通过独立连接重新读取的最终验证报告中 full/smoke exit code 均为0，部署由另一个正常退出的连接完成。

GitHub [CI 运行 39648135699](https://github.com/auntunt/webuddy-pitch/actions/runs/39648135699)：两组 Linux 全量、四组两平台快速检查、两平台安装检查通过。Windows 3.11 全量未通过；与 `30686e6` 对照，失败名称集合完全相同，未发现新增失败用例，但日志提前结束，新增团队套件未跑到，不能宣称 Windows 全量兼容。Windows 3.13 结果另以该运行页面为准，不作为本次 Linux 生产验收依据。

**上线结论：这版工作区、协作、知识与交接能力已经进入 Webuddy 生产服务，GitHub 保存代码和完整设计资料。**
