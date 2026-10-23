# 组织工作台与任务交接发布记录

实现提交：`911e42d9a34d0df13115e8f9405fbdcf0297d4b5`。分支：`iteration/context-pack-v2`。状态：**2026-10-23 12:06:23 CST 已上线，延迟健康检查通过**。

## 修改与边界

真实任务工作台新增待接手、交接阶段、下一责任人和实际等待时间；同页读取完整需求、固定来源和历史。发送、接收、退回、阻塞、恢复、撤回需个人登录，使用 revision 与稳定请求编号，交接/事件/重试回执同事务提交。

收到材料不改变 assignee、独立复核人、既有工单状态、技术/业务验收；guard、acceptance、filelock 与所有已有测试文件等同改动前。仍是共享工作区责任视图，没有新增项目 ACL。失效候选须先处理来源，不把交接当成验收凭证。

使用说明：[任务交接](../docs/task-handoffs.md)。浏览器原始证据：[验证记录](../docs/design/organization-workspace-2026-10-23/implementation-evidence/browser-verification.md)。

## 已完成验证

- 最终定向：65 tests / 7.327s / OK。
- 本机 Python 3.14：1393 tests / 414.665s / OK，1377 通过、16 可选依赖跳过、无失败/错误；283 个受测文件 SHA 不变。
- 本机完整日志 SHA-256：`e09049462b1375fdafd636bdf4918dd88c75124846e29fb247d17afc22ae4389`。
- 服务器 Python 3.12.3：1393 tests / 569.803s / OK，1379 通过、14 可选 MCP SDK 跳过、无失败/错误；390 个受测文件不变。完整日志 SHA-256：`aea930cd143a95cdccf50b05e1b56d8afba68777561d40e42f7d8105af7dad5b`。36/36 合成 HTTP 检查通过，临时进程和数据已清理。
- Chrome 合成个人账号完成研发→测试→交付退回，以及撤回、阻塞/恢复、草稿保留；390px 无横向溢出，控制台 warning/error 空。合成库三次交接、八个事件，两任务仍 new、负责人 alice，未做候选决策。
- 浏览器发现成功后空表单绑定旧 revision，已修并新增回归；最终 UI 21 项通过。首轮 1390 项全量虽然通过，但运行期间有 UI 修复，不作为最终凭证。
- 10 张完整原始 JPEG（包含失败现场与最终版本）共 1352779 字节；未转码或缩小像素。最终六张 643189 字节。主代理亲自打开桌面及手机截图复核；临时服务和页签已关闭。
- 精确 Git blob 包：191 个运行文件、390 个验证文件，SHA/长度/权限逐项读回；临时合成服务 36 项 HTTP 通过，测试数据清理。
- 发布工具自检覆盖 SQLite BLOB/原记录摘要、完整 tar 读回，以及切换后失败、停止超时、回滚停止失败三条路径。回滚仅切换程序，不恢复旧业务数据。
- 服务器副本迁移：原 41 张表全部原列、原行及结构保持；仅新增四张空表；两次初始化幂等、integrity_check=ok。未初始化真实生产 Platform。

## 发布过程

GitHub 已普通快进 `033e3dd..911e42d`。切换前版本为 `a8e22b7`；接入记忆、公钥指纹、0600 与严格主机密钥校验已核对。首次传输超出 300 秒，按精确允许清单续传完成；没有放宽产品测试预算。一次提前执行尚未完成 stage 的 rehearsal 返回文件不存在，未运行迁移或修改生产。最终 stage 成功后才顺序执行副本迁移与全量。

服务器全量完成后原 SSH 连接未收尾；独立连接确认验证报告 full/smoke 两项退出码均为 0、受测文件未变及进程结束后，仅终止本机旧验证 SSH 客户端（退出 255）。保留这一传输问题，不把它伪装为产品测试退出 0。

12:06:23 CST，`/opt/webuddy/app` 切换到 `/opt/webuddy/releases/911e42d9a34d-handoff-workspace-20261023/app`，`webuddy.service` 启动。191 个运行文件的 SHA、长度和权限全部一致，启动后 16 项回环读取通过。原 41 张表的原列、原行与结构保持，仅新增预期四张空表；非数据库文件、三个项目原文件和外部配置未变。

完整回退备份：`/opt/webuddy/backups/pre-911e42d9a34d-20261023T040621Z`，含旧程序、data、配置及三个项目 `.tmh`，1775 个 data 成员和 277/37/20 个项目成员读回一致。旧程序仍保留。没有恢复旧数据；后续回退只切程序，不能覆盖新业务写入。

12:08:40 CST（启动约 137 秒后），**32/32 公网 HTTPS 与回环读取检查通过**，SQLite integrity_check=ok；原表、非 DB 文件、项目文件与外部配置继续保持。12:09:49 CST 再次核验 active/running、自动重启 0、启动以来 error 级日志 0，191 个运行文件保持。Caddy 未重启，同机另一应用未修改。Mac 侧独立 TLS 登录页 200、两项匿名 API 401，共三项通过。

完整外部证据目录：`/Users/auntlee/Desktop/workspace/运维智能体/部署包/handoff-workspace-20261023/`。服务器 11 份报告与完整日志全部下载，SHA-256、长度及本机读回一致；[证据清单](../docs/design/organization-workspace-2026-10-23/implementation-evidence/server-readback-manifest.json)和[脱敏发布摘要](../docs/design/organization-workspace-2026-10-23/implementation-evidence/production-verification.json)已入库。业务备份、凭据和实际业务正文不进入仓库。发布记录按文档单独提交，不再次重启程序。

12:19:13 CST 文档收尾前只读复核：191 个运行文件 SHA、长度和权限保持；服务 active/running、PID 不变、自动重启 0。本轮最终仅添加文档与证据，不改变已全量验证的产品/测试，不因文档再次重启。

## GitHub CI 与 Windows 边界

[实现提交的 CI 39897236343](https://github.com/auntunt/webuddy-pitch/actions/runs/39897236343) 在 12:18:41 CST 的快照：两组 Linux 全量、两平台安装与四组快速检查共 8 项成功；Windows 3.11 全量失败，3.13 仍在运行。

Windows 3.11 完整原始日志为 **188 failed / 558 passed / 71 skipped / 5 errors / 273 subtests passed（944.57s）**，约 56% 时在 `threading.py:327` 收到 KeyboardInterrupt，未执行完全部用例。新增四个交接测试模块没有失败/错误条目，但安静日志不能逐项证明通过，UI 与工作台模块也未证实执行，因此不宣称 61 个新增用例在 Windows 全过。

父提交 `033e3dd` 的同平台原始日志也已保存：当前 184 个唯一失败/错误 test ID 中 164 个曾在父提交出现；另 20 个（19 个 test_platform、1 个 test_preview_health_flow）缺少相同范围对照，不能统称基线或断言为新回归。[完整逐项明细](../docs/design/organization-workspace-2026-10-23/implementation-evidence/github-ci-windows-py311-failure-summary.json)和[父提交比较](../docs/design/organization-workspace-2026-10-23/implementation-evidence/github-ci-windows-py311-parent-comparison.json)保留；两份原始日志位于外部 `candidate-911e42d/github-ci/`，没有改超时、过滤失败或修改原测试。Linux 生产验收通过不能证明 Windows 全量兼容。

## 尚未覆盖

没有调用真实模型、代人验收、采用知识或处理真实交接。浏览器全路径是本地合成账号验证，生产验证是精确文件与 HTTP 读取，不冒充生产登录后的业务操作验收。既有 Claude 启动检查、Windows 实机与可选 MCP 的限制仍保留；不能将本轮协作流程验收解释为模型质量或组织效率收益已证明。
