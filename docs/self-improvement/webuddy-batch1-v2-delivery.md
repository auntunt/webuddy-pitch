# v2 第一批修复：代码与发布对照

任务依据：`Webuddy_分阶段修复执行文档_v2.docx` 第二部分。仅本批，不包含第二批、后续产品建设或 BID-1 应用导出修复。

- 产品分支：`devin/1793765109-bidding-demo-ui`（不是 main，也不是旧 iteration 分支）。
- 基线：`86eb56033297a7fe16e117e760d62628d0d74b8c`。
- 实现提交：[f6141189c329d634f657b695328a5887b858ac78](https://github.com/auntunt/webuddy-pitch/commit/f6141189c329d634f657b695328a5887b858ac78)。21 个文件，新增 1120 行、删除 154 行，包含测试及规范。
- 本记录补录于 2026-11-05（北京时间）。没有替用户签收、关单或执行客户业务。

## 逐项修改与证据

各项均已实现并通过下列自动化验证；真实浏览器交互验收未完成。以下测试为合成数据、隔离 HTTP 服务、Node 执行页面函数或受控子进程，不等同于生产业务验收。

| 文档条目 | 实际修改及用户可观察行为 | 主要文件 | 验证 |
|---|---|---|---|
| D1 授权项目范围 | 全部项目按当前会话授权范围聚合，不再用最近项目替代；未授权项目不进入计数；无项目、空项目及筛选零结果分别处理 | `server.py`、`tenant_policy.py`、`ui.py` | `test_scoped_boards`、`test_tenant_policy`、`test_tenant_gateway`；覆盖 A/B 范围、隐藏项目、伪造显示名、跨租户和撤权 |
| D2 能力与入口 | 管理员客户入口与成员权限一致；只读不打开写表单；可编辑但不可执行者仍按规则归档；加载失败有错误反馈，重试文案保持正确 | `ui_work.py`、`ui.py` | `test_ui_intake_permissions`、`test_ui_navigation`；覆盖只读、编辑、执行权限与延迟系统列表 |
| D3 状态读取恢复 | 网络错误退避重试，最大间隔 15 秒；显示断连及立即重试；权限失效停止；关闭停止轮询，旧响应不覆盖当前弹窗；取消失败仍保留状态 | `ui.py` | `test_intake_form_repair`；连续失败恢复、403、切换任务、取消失败和关闭后响应 |
| D4 附件身份 | 用稳定 ID 删除；A/B/C 连删 A/B 后只提交 C；读取中禁止提交，失败可移除；同名独立，删除后的读取回调不复活附件 | `ui.py` | `test_intake_form_repair`；精确请求内容、同名、迟到读取、粘贴及拖入 |
| D6 逐项证据 | 总体构建/套件通过不再证明保持项；逐项结果绑定证据包、工单、运行、提交、标准和环境；复测开始撤销旧结果；合法证据仍能支持既有自动验收 | `signoff.py`、`browser_verify.py`、`ai_accept.py` | `test_criterion_evidence`、`test_browser_verify`、`test_ai_accept`、两组 signoff binding 测试；覆盖过期、复验、环境变更和并发迟到结果 |
| D7 申请 ID | 随机唯一 ID；同秒不同版本独立；保留审批锁；历史冲突保留原始事件并标记歧义，禁止猜测归属后操作 | `prod_release.py` | `test_prod_release`、`test_prod_release_integrity`；覆盖独立申请、重复批准、驳回重申请、历史冲突 |
| D8 发布验证 | 命令完成、检查通过、检查失败、人工登记、历史记录和未知结果分别展示；回执绑定申请/目标/版本/执行/配置并要求健康、版本、冒烟依据；未知不自动重跑 | `prod_release.py`、`ui_work.py`、`ui.py` | 同上；受控真实子进程及回执错配/失败/缺失、配置变化、重启未知状态、页面状态测试 |
| U2a 输入交接 | 目标弹窗成功接管后才清空原输入；同会话误关可恢复文本或原任务；按用户、租户、项目隔离 | `ui_drafts.py`、`ui_work.py`、`ui.py` | `test_intake_form_repair`、`test_ui_intake_permissions`；打开失败保留、成功交接和跨范围隔离 |

文件路径除测试外均位于 `tmh/platform/`。用户提供的完整八节开发约定已追加到根目录 `AGENTS.md`，原内容保留；另补阿里云现役部署说明。

复用的既有能力：规则归档、执行器选择、进程内审批锁、登录边界、评论草稿。D6 证实并修复的是逐项证明不足，不声称任意任务原本能绕过全部门禁。没有建设跨进程发布调度；U2a 不覆盖刷新后恢复和附件持久草稿。

## 实际验证结果

- Mac：19 个相关模块，258 tests，20.486 秒，OK。最后补弹窗迟到响应校验后，47 个 UI 相关测试复验 OK（1.807 秒）。完整页面脚本解析与 `git diff --check` 通过。
- 阿里云：精确提交构建的 `webuddy:f614118`，Python 3.11，隔离容器无外网运行同 19 个模块，258 tests，53.478 秒，OK。
- 新镜像及上线容器：2260 个发布包文件 SHA-256 清单逐一一致，`RELEASE.json` 指向 f614118。
- 浏览器工具返回 host unavailable，没有页面截图，也没有完成登录后或移动端交互验收。这部分仍待真实浏览器验证。

测试模块：`test_criterion_evidence`、`test_signoff_delivery_binding`、`test_signoff_preview_binding`、`test_browser_verify`、`test_ai_accept`、`test_tenant_policy`、`test_tenant_gateway`、`test_scoped_boards`、`test_prod_release`、`test_prod_release_integrity`、`test_intake_form_repair`、`test_ui_intake_permissions`、`test_ui_dialog`、`test_ui_access`、`test_ui_navigation`、`test_ui_agent_routes`、`test_ui_library`、`test_intake_handoff`、`test_intake_llm`。命令使用 `PYTHONPATH=.:tests python3 -m unittest`。

## 阿里云发布与回退

- 站点：<https://webuddy.bbstack.date>；只切换 `zct-server` 的 Compose 服务 `webuddy`。
- 原镜像 `webuddy:d8f0c0f`，现役 `webuddy:f614118`。切换前 running_runs=0；停止服务后完整备份，再启动新镜像。
- 备份：`/home/Liyibin/webuddy/backups/pre-f614118-20261104T175810Z`，含 data/repos/codex 三个完整卷归档、原 Compose、外部环境配置及独立 SQLite 副本。敏感内容只留服务器。
- 12 个 SQLite 数据库 integrity_check 均为 ok；上线后 platform.db 与 control/access.db 再检查均为 ok。没有新增数据库迁移脚本。
- 本机回环 `/login` 200，未登录 `/api/projects` 401；Mac 公网 curl 同为 200/401，服务器公网 curl 登录 200。一次服务器 Python urllib 公网检查返回 403，记录为未通过，后续 curl 核对正常；不推断具体原因。
- 延迟复查：容器 running，restart=0，运行 RELEASE.json 仍为 f614118。
- 服务器验证日志：`~/webuddy/releases/f614118-tests.log`；构建日志：`~/webuddy/releases/f614118-build.log`；源码与清单：`~/webuddy/releases/f614118/`。
- 回退只把 Compose image 改回 `webuddy:d8f0c0f`（也保留 `webuddy:rollback-pre-f614118`），再 `docker compose up -d --no-build --no-deps webuddy`。保留现有卷，不用备份数据库覆盖上线后的新写入。不操作腾讯云已分叉服务。
