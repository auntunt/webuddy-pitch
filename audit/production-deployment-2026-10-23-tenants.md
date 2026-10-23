# 租户与权限管理发布记录

状态：**2026-10-23 17:23:55 CST 上线，延迟健康检查通过**。运行提交 `56018de6c3bc5dd499e696d3543633f4c4557c4d`，分支 `iteration/context-pack-v2`，GitHub 已普通快进推送。

实现提交 `273dc97`；独立测试夹具修复 `5aef9d5`、`56018de`。后两个提交没有改变产品代码。

## 已交付

固定 `/t/<不可变租户ID>/`、独立租户数据库和工作进程、个人账号、平台所有者、组织管理员/成员/只读成员，以及项目 manager/contributor/viewer 授权。成员与项目授权、修订号、请求幂等和审计同事务。列表先按项目权限过滤，再计数/分页；未登记 API 默认拒绝。

网关和 worker 均验证可信请求身份；实际 worker 持有跨进程授权锁至业务处理完成，再释放锁发送响应。撤权与已经接纳的操作有确定顺序；网关死亡不能提前释放仍在提交的 worker 的屏障。进程启动及就绪等待在锁外。密码重置、停用、授权变更使旧会话或页面上下文失效，旧内容清屏。

顶部切换组织，「成员与权限」维护账号/成员/项目角色。无业务成员身份的平台所有者只能管理，不能读取租户业务。草稿按实例、账号、租户隔离；真实账号只读显示，知识确认、答复及改判拒绝 Agent 标识和冒用 `by`。

使用说明：[组织、成员与项目权限](../docs/tenant-access.md)。设计：[最终合同](../docs/design/tenant-access-2026-10-23.md)。界面：[实际浏览器检查及原始图](../docs/design/tenant-access-2026-10-23/browser-verification.md)。

## 验证

最终提交两端均执行 `python3 -m unittest discover -s tests`，使用回环限定、合成数据及完整失败捕获；测试期间不修改受测文件。

| 环境 | 总数 | 通过 | 跳过 | 失败/错误 | 时间 | 冻结文件 |
|---|---:|---:|---:|---:|---:|---:|
| 本机 Python 3.14 | 1523 | 1507 | 16 | 0 | 454.621s | 380 个保持 |
| 服务器 Python 3.12.3 | 1523 | 1509 | 14 | 0 | 658.502s | 406 个保持 |

两端各缺可选 MCP SDK 14 项，本机另缺 cryptography 2 项。未通过跳过新增失败或改变断言获得成功。本机完整日志 SHA256 `0cbec5cf7af4487e8c00b296353c29eace8a5f56e45999b1c8e9f2b9d11a1eef`；服务器完整日志 SHA256 `4a001112c6fd0a28d92b2f714bbe763c0e32f4bd725a9779a98eb1c665911810`。

- 精确版本合成个人密码登录 HTTP **26/26**，覆盖真实账号、隔离、角色及管理操作；临时进程和数据已清理。
- UI 新增 **38 项**回归。Chrome 实际验证同编号跨租户草稿、真实创建任务且零运行、只读控制、撤权清屏、控制面专用访问、知识答复实名记录，以及 390px 管理页无横向溢出。7 张原始 JPEG 共 387298 字节，主代理亲自打开，全部与源图逐字节相同，没有压缩、转码或降采样。
- 网关强杀的空闲/实际数据库写锁屏障两项，10 轮 **20/20**；真实 HTTP→Runner→supervisor→父/子/孙进程，强杀 worker 或网关，两项 10 轮 **20/20**。校验真实 PPID、存活屏障、完整输出、owner_lost/125、所属 PID/PGID 清理及无关进程存活；不声称覆盖主动 setsid 逃逸、监督进程 SIGKILL 或整机故障。
- `acceptance.py`、`guard.py`、`filelock.py`、`process_control.py`、`supervised_process.py` 与起点逐字节相同；MOVES 不变。三个既有测试文件共 77 个原方法的断言保持，改动只补齐真实会话或 UI 启动依赖。

## 首轮失败与修复

`273dc97` 本机 1522 项有 8 failures；服务器同版本有相同 8 failures 加 1 error。完整失败日志、警告和捕获产物均保留，没有直接重跑后忽略。

8 项 UI 失败发生在原断言前：独立 JavaScript 夹具缺少真实 `ACCESS_BOOT_JS` 的 `appPath` 依赖。`5aef9d5` 装载真实页面启动片段及 location，并新增证据按钮前缀回归；两个原模块 18 个方法完整 AST 相同，未 mock 权限或改变断言。

Linux 新 policy 夹具重复插入 `Store.add_project` 已登记的来源，UNIQUE(project_id,root) 正确拒绝。Mac `/var` 与 `/private/var` 别名掩盖该错误。`56018de` 读取既有来源并断言项目和 root，保留四个权限断言，不使用 OR IGNORE。原始与规范化路径用例通过，随后从最终提交重新跑双端全量。

原 Linux 失败仅保留完整堆栈，诊断器未捕获当时局部变量里的临时数据库；不宣称保留原 DB。另以原测试与相同产品字节、规范路径准确独立重现，cleanup 前保存整个合成根、DB、65 个 schema 对象、31 表全部 15 行和 SQL dump；12 份证据验证通过，标记为独立重现而非原 Linux 现场。

## 迁移与发布

精确 Git blob 包包含 197 个运行文件、406 个验证文件，字节、长度和模式核对通过。完整 1775 成员生产私有副本迁移两次幂等；45 张原业务表全部结构/原行、users.json/session.key 字节保持，仅增独立控制面。副本真实 default worker 初始化成功、退出 0，PID 回收，socket 和本次凭据清理；没有伪造生产用户会话。

生产停止旧服务后完整备份到 `/opt/webuddy/backups/pre-56018de6c3bc-20261023T092352Z`：原程序、data、配置及三个项目 `.tmh`；1775 个 data 成员和项目 277/37/20 个成员全部读回一致。唯一现有个人账号 `li` 被显式指定为平台所有者及 default 管理员；旧业务数据原位，旧会话失效，用户需要重新登录。

`/opt/webuddy/app` 切换至 `/opt/webuddy/releases/56018de6c3bc-tenant-access-20261023/app`，`webuddy.service` 于 17:23:55 CST 启动。10 项回环登录/匿名和旧 token 拒绝检查通过。17:25:58 CST（122.264s 后）18 项公网及回环检查通过；网关/default worker 的 PID、启动时间、cwd、私有 socket 与 cgroup 一致。17:26:00 active/running、自动重启 0、启动以来 error 日志 0。

原 45 张表、身份文件、非数据库文件、项目文件均保持，SQLite integrity_check=ok。环境、服务单元、Caddy 与同机另一应用保持。主代理重新校验 11 份完整报告/日志的 SHA 和长度，并于 17:29:29 CST 从 Mac 独立验证正常 TLS 登录页 200、三项匿名 API 401。

17:30:57 CST 最终只读核验再次确认 197 个运行文件 SHA/长度/模式保持、active/running、重启 0、错误日志 0，网关 PID 与 worker PID/start_ticks 保持。网关自身 start_ticks 此次首次记录，未宣称以前已记录该字段。未修改生产或旧证据；完整新回执 `final-handoff-runtime.json`，SHA256 `c6faf1919ccd9fa28ba7cef6559e286a9641666175abfcff72c71f91c10c6443`。

**控制面启用后不能切回忽略 ACL 的旧程序**，否则旧账号或凭据可能重新获得访问。失败路径停止服务并保留全部当前数据，后续部署兼容控制面的修复版本；不恢复旧数据库覆盖新业务写入。本次没有触发回退或数据恢复。

原始证据保存在仓库外 `部署包/tenant-access-20261023/`。入库的是[证据哈希清单](../docs/design/tenant-access-2026-10-23/server-readback-manifest.json)、[脱敏发布摘要](../docs/design/tenant-access-2026-10-23/production-verification.json)、[本机验证](../docs/design/tenant-access-2026-10-23/local-verification.json)和[不变量检查](../docs/design/tenant-access-2026-10-23/invariants.json)；不提交数据库、凭据或业务正文。收尾仅文档，不重复重启。

## CI 与支持边界

[GitHub CI 39930617746](https://github.com/auntunt/webuddy-pitch/actions/runs/39930617746) 在 17:29:06 CST：8 项成功（Linux 3.11/3.13 全量、两平台四项快速检查、两平台安装）；Windows 3.11/3.13 全量仍运行。保存[完整快照](../docs/design/tenant-access-2026-10-23/github-ci-snapshot.json)，不宣称整个 CI 已完成。新网关依赖 POSIX/Unix socket，Windows 未支持，历史全量问题也未在本轮解决。

新组织没有 OS 执行沙箱，模型、脚本、构建和预览执行保持关闭，无开放开关。默认组织的宿主执行只开放给有成员与项目权限的可信平台所有者；普通成员的 Git 证据核对及依赖该核对的评审暂受限。全部受管组织的公开分享、签收、捕获回调和预览禁用；自动流转、自动合并、启动恢复也不启用。

SSO/MFA、邀请、配额和跨租户知识发布协议尚未实现。未使用真实生产个人会话操作业务，未验证真实 Claude 执行器或模型质量。测试和浏览器证据均为合成账号，不等于生产业务验收，也不替代人工确认、验收、采用或关单。

人工审阅建议：`tenancy.py` 的事务/版本/会话失效，`tenant_gateway.py` 与 `tenant_runtime.py` 的二次授权及进程锁，`tenant_policy.py` 的路由/资源/执行边界，`server.py` 的 `api_kb_confirm` / `api_kb_answer` / `api_kb_overrule` 严格个人身份；尤其注意受限执行和公开能力的产品取舍。
