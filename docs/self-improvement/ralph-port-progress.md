# Ralph port 执行进度

## 2026-10-23：正式组织工作台与任务交接（第一批）

- 当前项：O1/O2 正式实现；状态：doing。用户要求“完成更具体的修改”，本轮接入真实任务工作台、交接/接收/退回、下一责任人、阻塞/恢复及研发→测试→交付路径；不只交付样稿。
- 开始：`iteration/context-pack-v2` / `033e3dd`，工作区干净；已读根 AGENTS、进度和最近十条提交。沿用验证后自动提交、GitHub 推送和生产部署授权；不重建分支，不改 Git 配置，保留历史 stash。
- 实施划分：后端新增独立 handoffs 模块及事务/迁移/并发测试；前端接现有工作台并加入交接详情；主代理负责真实 API、队列投影、集成验证与发布；独立审查身份、快照、锁序和回滚。使用计划执行、既有界面改造与交付前验证流程。
- 约束：交接不改变工单 assignee/status、独立复核人、MOVES、验收/采用/关单状态；“收到材料”只记接收事实。所有写入需要真实个人会话；共享令牌、显示名和 Agent 标识不能代人接收。仍为共享工作区，不宣称新增项目 ACL。
- 数据合同：交接绑定需求、项目来源与固定候选证据；revision 乐观并发、稳定 request_id 重放；交接/审计事件/回执同事务；不在写事务中调用会隐式 commit 的 schema/Store.x 或进行 Git/HTTP/模型调用。来源失效拒绝接收，保留完整历史；发送人/当前负责人可有理由撤回避免永久卡住。
- 展示：五种交接目标阶段与“未登记阶段”；未建立交接的历史等待为未知，不从 updated 倒推。原四类队列计数保留兼容，待接手单独计数；完整详情沿用真实团队候选状态与证据，阶段/角色不是权限。
- 验证计划：后端定向、HTTP 身份与全路径、503+队列分页、UI JS/交互/窄屏、独立代码审查；冻结提交后全量；部署精确清单、数据库副本迁移、备份/回滚路径、上线与延迟健康检查。真实 Claude 启动、Windows 与可选 MCP 的既有边界单列，不冒充本轮已解决。
- 实现已落地：新增 `handoffs.py`、`ui_handoffs.py`、四个测试文件和使用说明；扩展 Store 初始化、HTTP 路由、workspace 投影及 UI。仅新增四张交接表，保留旧工单/复核/验收模型。
- 审查修复：旧 events.ts 保持既有本地格式，专表 UTC；只读参考项目不发起新交接；来源 token 单独变化可保稿重绑；切任务期间提交结果正确解锁；成功提交后详情刷新失败不重复提交；页面下一责任人与实际候选状态一致；附加读异常仍返回持久成功回执；停用账号明确提示。
- 定向：后端 26 + 工作台新增 8 = 34 tests / 1.959s / OK；既有团队/知识/组织知识 55 tests / 17.804s / OK；HTTP 真回环六项 / 3.621s / OK；旧 workspace 四项通过。一次组合命令用 `tests.test_ui_handoffs` 导致同目录 helper 导入失败，前 44 项通过；按既有 UI 测试的 `PYTHONPATH=tests:.` 单独重跑，不改断言。UI 最终 18 项行为测试通过。
- 全量 doing：冻结 283 个实现/测试等文件 SHA，`NO_PROXY='*' no_proxy='*' TMH_UNDERSTAND=rules PYTHONPATH='<local-validation>:.' python3 -m unittest discover -s tests`，预期 1390 项。完整日志、跳过清单与失败现场保存在仓库外 `部署包/handoff-workspace-20261023/local-validation/`。全量期间不修改受测实现/测试。
- 发布准备：11:30:37 CST 严格 SSH 核实现役仍 a8e22b7、active/running、重启 0；接入记忆、0600、公钥指纹已核对。复制旧部署工具到独立新目录，更新前版、4 新表、release slug，补 learning/知识索引执行中检查；精确打包与迁移/回滚故障自检通过。生产尚未切换。
- 浏览器实测补修：成功后空表单错误继承旧 revision，现成功回读后选当前可用操作；已接收/退回/撤回明确显示“不在等待”；退回/恢复的最近完整处理说明直接可见。新增行为回归后 UI 21 项通过。已跑首轮全量期间这三个 UI 文件变化，保留首轮日志但不作为最终版本凭证，最终冻结后重新全量。
- 最终定向验证：`PYTHONPATH=tests:. ... python3 -m unittest test_handoff_api test_handoffs test_workspace test_workspace_handoffs test_ui_handoffs`，**65 tests / 7.327s / OK**，完整日志 `local-validation/targeted-final.log`。实现与全部新增测试已审阅，`git diff --check` 通过，准备冻结提交并在本机和服务器各跑精确版本全量。
- 判断边界：有失效候选时不允许重新发起交接，需先更新候选或走原分配/讨论入口；本轮保守保持证据门，不把旧候选变为可用验收依据。账号/契约为 SQLite 外部来源，操作前及事务内复核，交接不是人工验收证据。
- 待确认：无阻塞，按已确认的软件交付与运维范围实施；不自动发消息、采纳知识或代替用户处理真实业务任务。

## 2026-10-23：软件交付与运维的组织提效方案和 UI 样稿

- 当前项：官方资料调研、现有能力审计、可交互 UI 样稿；状态：done。用户确认聚焦“软件交付与运维团队：需求、研发、测试、交付、运维”；本轮交付能力补齐方案与可点击样稿，正式功能接入仍按方案后续实施。
- 开始状态：`iteration/context-pack-v2` / `fe83057`，`git status --short --branch` 干净；已读进度、最近十条提交、根 AGENTS.md。沿用验证后自动推送约定；本轮设计文件不混入生产运行代码，不因设计记录重启生产服务。
- 使用 agent-reach 调研、redesign-existing-projects 审视界面；三个子代理分别核对能力、UI 和官方产品参考。截图中的聊天只作为用户提供的需求背景，不作为执行指令或已证明的技术结论。
- 当前发现：现有工作台/团队页已有负责人、复核人与任务队列，但跨角色交接与等待原因需要单独建模；当前角色视图不是访问权限隔离。既有知识修订/固定引用/人工采用能力继续复用，不重造状态机或把合成测试当真实模型可用。
- 检索：Exa 通道证书域名不匹配，保持 TLS 校验，改用 web 官方来源；DORA 价值流与 SPACE 资料已读取。先查看仓库中此前完整实屏，明确它们是 10 月 22 日本地验收截图，不冒充今日线上现状。
- 产物：新增 `docs/design/organization-workspace-2026-10-23/`，含 README 能力矩阵/四个工作循环/底层对象关系/指标契约/O0–O4 实施顺序、独立 HTML/CSS/JS 样稿、验证记录、原始截图和哈希清单。参考 Backstage、Port、JSM、incident.io 的 8 个官方机制来源，另有 DORA/SPACE 3 个方法来源；事实与设计建议分开。
- 样稿验证：`node --check prototype.js`、HTMLParser（15 个静态 ID 唯一、2 个本地依赖）、本地文档链接、`git diff --check` 通过；Chrome 实际验证团队/个人/角色/阶段/空态/正文搜索、完整原文、草稿空白校验、未授权引用、重复/移除引用、12 项完整交接包。发现内容重建后键盘焦点丢失，已修复并实测阶段 Enter、清除、保存、加入/移除、跨页焦点。
- 显示验证：桌面 1680 × 825、手机 390 × 844；工作台/资产/交接无页面横向溢出，手机责任人与未知等待保留，控制台 warning/error 为空。原始 JPEG 按返回字节保存并实际打开检查，未二次压缩或重编码。直接 file 协议被浏览器安全策略拒绝，未绕过；已通过本机 HTTP 预览完成验收，未声称 file 协议可用。
- 发布核对：先读接入记忆、检查 0600/登记公钥指纹，再严格 known_hosts 只读 SSH；2026-10-23 01:44:10 CST 线上仍为 `a8e22b7`，188 个运行文件 SHA/长度/权限全部一致，active/running、重启 0。本轮不修改运行代码、不重跑产品全量、不因设计记录重启生产；沿用授权提交并普通快进推送 GitHub 当前分支。记录见本目录 `VERIFICATION.md` 与 `runtime-verification.json`。
- 命令边界：`agent-reach check-update` 返回 127（命令不存在），未安装软件；首次浏览器项目 label 定位失败后按实际 ID 完成检查。没有读取实际 data、私钥正文或生产外部配置，没有人工采用/确认/关单。当前进度记录与设计产物同一提交，不包含真实账号或客户数据。
- 待确认：范围已获答复，无阻塞；组织效率改善先定义指标与试点，不预设收益百分比。真实 Claude 启动、Windows 与 MCP 的已知验证边界仍保留。

## 2026-10-22：知识分类与评审闭环发布

- 当前项：推送 GitHub 与发布 Webuddy；状态：done（部署版本 `a8e22b7`）。用户本轮明确授权“推到服务器和github。每次修改完都是自动推送”，覆盖历史仅本地、不 push/部署限制；已在根目录 `AGENTS.md` 保存后续完成并验证后自动发布的约定。下列中间状态按发生顺序保留，最终结果见本节末。
- 开始状态：`iteration/context-pack-v2` / `924da09`，工作区干净，历史 stash 保留；GitHub 远端实查仍为 `3ecf977`，不改分支或 Git 配置、不强推。
- 发布采用已完成本机全量的知识闭环实现；另做服务器 Python 3.12 全量、合成 HTTP 和真实数据库副本迁移，全部通过才切换。保留原始日志、精确文件清单、配置与业务数据备份；业务人工确认边界不变。
- 已提交并推送 `59aea33`；GitHub 普通快进 `3ecf977..59aea33`，包含 8 个未推送的知识闭环提交与发布约定。服务器初查仍为 `3ecf977`、Python 3.12.3、active/running、无活跃运行，完整性 ok；私钥仅验证 0600 和公钥指纹，通过严格 known_hosts 登录及 sudo 核验，未输出或复制凭据。
- 精确版本包：188 个运行文件、383 个验证文件，Git 原始 blob 字节与权限逐项校验。本机重核 265 个完整测试清单文件与 `05022ce` 全量受测内容完全相同，完整日志 SHA-256 一致；临时服务 28 项 HTTP 检查通过并清理。部署脚本本机验证覆盖归档读回、BLOB 摘要、迁移保留记录以及切换后失败/stop 超时/回滚失败三个故障分支。
- 传输：初次 SCP 速度较慢，主动停止该文件传输进程，改用可续传的 rsync 无损传输压缩；不改变任何文件编码或像素，服务器接收后 188/383 个文件及两个 tar 的长度、SHA-256 和权限全部通过。首次未传完的包未 stage 或激活；候选准备阶段已核对不存在的评审回执应返回 404，修正的仅为新增部署 smoke 脚本期望值，没有改产品或基线断言。最终包与辅助脚本保留在本机 `部署包/learning-loops-20261022/candidate-59aea33-r2/`。
- 数据库副本迁移已完成：33 张原表的全部原列、原行哈希与结构不变；只新增预期 8 张空表；连续初始化两次幂等，integrity_check=ok，未初始化实际生产 Platform。服务器全量以清洁 HOME、无模型凭据和回环网络限定运行，原始日志/跳过原因/失败现场独立保存；正式切换仍等待其结果。
- 发布验证发现并修复两处测试问题，未上线失败版本：GitHub CI `39768074700` 的 Python 3.11 为 2 failed / 1313 passed / 16 skipped，3.13 为 1 failed / 1314 passed / 16 skipped（各 491 subtests passed）。新增 `test_learning_runs` 直接对自定义字典行工厂调用 `iterdump()`，Python 3.11/3.12 将键名当表名，报 `no such table: name`；服务器 3.12 已独立复现并保留完整现场。改用仓库已有 `dump_store` 一致性副本，仍完整比较所有表、行和结构，不改活连接行工厂。
- 第二处为旧 `test_org_knowledge_api` 的 Platform 夹具未还原进程全局 `bots.INTAKE`；pytest 定义顺序下，后续企微回调会访问已关闭数据库。新增真实 HTTP 夹具顺序测试在修复前稳定 2 个 subTest 失败，随后用 addCleanup/addClassCleanup 还原原回调所有者并关闭 HTTP/SQLite 资源；原 8 个 HTTP 测试方法断言 AST 全部保持。没有修改产品代码、超时或业务校验。
- 本机定向 `NO_PROXY='*' no_proxy='*' TMH_UNDERSTAND=rules python3 -m unittest tests.test_org_knowledge_api tests.test_phase1 tests.test_learning_runs tests.test_sqlite_snapshot`：**51 tests / 10.614s / OK**。完整 `fixture-isolation-red.log`、`fixture-fixes-green.log`、`fixture-review.json` 与两份 CI 完整日志均保留在上述部署工作区；本次修复独立提交后重新验证，不复用失败套件为上线凭证。
- 修复提交 `a8e22b7` 已普通快进推送。服务器 3.12 定向 pytest **51 passed / 15 subtests passed / 18.18s**；两份受测测试文件的 SHA 与提交一致。首轮服务器全量最终 **1331 tests / 539.432s / FAILED（errors=1, skipped=14）**，唯一错误为上述快照兼容性，383 个受测文件未变；失败完整日志 SHA-256 `c0d4fb4c895b103657a71f2abd582fcd7c882d65e17a2ad89e7ea9be213dda3d`，9 份初轮/修复证据下载并校验。另捕获到 `test_app.Test.test_value` 的 999 合成失败属于候选质量门的预期负例，不冒充外层套件失败或忽略真正的快照错误。
- 新候选 `a8e22b7` 的 188 个运行文件与初轮逐字节/权限一致；383 个验证文件再次核验，迁移副本第二次演练通过，全量已重新启动，新增隔离测试后预期 1332 项。GitHub CI `39769936344` 的两组 Linux 全量、两平台安装与四组快速检查已通过；Windows 两组全量仍在执行，未声明 Windows 兼容。
- 额外只读执行器检查：沿用实际服务 PATH 和原生 Claude 配置，在临时 HOME 下执行既有 5 秒 `--help` 能力核验，出现 TimeoutExpired；未运行模型、未更改参数/权限/生产配置。原生程序确为服务器 ELF 文件，无自定义命令或额外 args。保留检查结果，真实独立评审可用性与效果仍不当作发布测试已证明。
- 最终服务器全量：精确提交 `a8e22b750cfc161189c7aa354bd1f5c1a2a1199c` 执行 `python3 -m unittest discover -s tests`，**1332 tests / 543.623s / OK（skipped=14）**，即 **1318 通过、0 失败/错误**。14 项均缺少可选 MCP SDK；383 个受测文件保持一致。全量日志 SHA-256 `bdeb2d6b751c636ae5ce5e0f3eb988d167b7834c2b4aa82dc8edf4e57dd34d89`。新候选隔离 HTTP **28/28**，两次数据库副本迁移幂等。
- 正式发布：**2026-10-22 19:33:38 CST**，`webuddy.service` 启动新版；188 个运行文件与提交逐字节/权限一致。完整旧程序、data、外部配置与三项目 `.tmh` 已备份，1775 个 data 成员和 277/37/20 个项目成员读回一致；原 33 张表原列/原行不变，仅新增 8 张空表，非 DB 文件、知识文件及人工状态保持。备份 `/opt/webuddy/backups/pre-a8e22b750cfc-20261022T113336Z`；未回滚或恢复旧数据。
- 延迟检查：19:35:46 CST（启动约 128 秒后），**24/24** 公网 HTTPS 与服务器回环读取通过，active、自动重启 0、启动以来 error 级日志 0；SQLite 完整性 ok、旧数据与外部配置保持，Caddy 未重启，同机另一应用未动。19:43:19 CST Mac 侧 TLS 直连登录页 200、两项匿名 API 401，三项通过。生产浏览器新建/读取操作超时，只有页签 URL/标题可见，未取得本轮上线后的页面渲染证据；此前临时平台实屏验证仍为本地证据，不冒充生产实屏。
- 最终 GitHub CI [39769936344](https://github.com/auntunt/webuddy-pitch/actions/runs/39769936344)：8 个任务成功；Linux 3.11/3.13 各 **1316 passed / 16 skipped / 493 subtests passed**。两组 Windows 全量各 **168 failed / 495 passed / 71 skipped / 5 errors / 273 subtests passed**；工作流原有 Windows 非阻断配置未改。完整日志与逐条明细 `github-ci-39769936344/windows-failures.json` 保留，包含新 learning 模块的正文变化/登记标识错误，不能统称为已证明的基线失败，也不能宣称 Windows 兼容。
- 执行器边界复核：全量结束后的空闲状态，仍在原 **5 秒** `--help` 核验时 TimeoutExpired，结果见 `capability-check-idle.json`；未放宽超时、未绕过无工具隔离、未调用真实模型。**独立模型评审尚未验证可用**，不以合成执行器测试替代真实模型效果或启动能力。
- 证据与交付：[完整发布记录](../../audit/production-deployment-2026-10-22-learning.md)。本机 `部署包/learning-loops-20261022/candidate-a8e22b7/server-evidence/` 的 13 份报告/完整日志按长度和 SHA-256 读回一致；首轮失败证据另存且未覆盖。最终只提交并推送发布文档，运行文件与已上线版本一致，不为文档重复重启服务。
- 待确认/后续边界：无发布许可阻塞；Claude 原生执行器启动核验、Windows 新旧失败、可选 MCP 协议和真实模型质量/费用仍未通过，不自动采用业务知识、不代人确认。后续修改继续按根目录 `AGENTS.md` 自动验证、推送和部署。

## 2026-10-22：知识分类与评审闭环实施

- 当前项：最终全量验收与交付；状态：done。用户已授权按设计自动实施；实际分支 `iteration/context-pack-v2`，起点 `949d732`。开工工作区干净，无需 stash。
- K1 done（`c453245`）：三类只读目录、不可变修订、来源绑定、历史兼容。K2 done（`edc032a`）：独立评审及有界修订。K3 done（`a50f524`）：冻结成对评测、人工采用、授权与会话依赖。K4 done（`4cc8632`）：策略允许清单、统一界面及使用说明。最终全量 **1331 tests，1315 通过、16 可选依赖跳过、0 失败/错误**；无 skipped 实施项。
- 本轮使用 executing-plans 和 verification-before-completion；按技能将独立运行引擎、界面和日志并发部分交给子代理，共享目录中限定文件所有权，最后统一审查。
- 已核对：最近十条提交、设计、进度、Store/Runner/knowledge/learn/library/人工身份入口。`Store.x` 会自动提交，新事务不能使用它；旧经验日志仍为权威，新采用用持久化待办与幂等投影。
- 判断：首版参考工作流项目可浏览固定修订，模型评审启动暂沿用 development 限制，不暗中改变项目角色；自定义命令和额外 Agent 参数不能证明只读，评审拒绝它们。成本未知时保留未知；合成测试不等于真实模型效果。
- 约束：仅临时数据/仓库测试；不访问网络、不碰实际 data/ 或密钥、不启动日常端口、不 push、不部署。人工确认、guard、提交证据和已有状态迁移保持原边界。
- 待确认：无阻塞；真实模型质量、自动采用、定时任务和组织推广均不在本轮启用范围。
- K1 修改：新增 `tmh/platform/learning.py`、`tests/test_learning.py`；`Store` 启动时进行独立可回滚迁移。完整正文/证据清单和 SHA-256、工作区、HEAD、引用授权都固定；非 Git/未提交内容明确为工作副本清单，未伪称提交内容。Agent 修订不得变更事实登记头或生成块；历史确认不伪造机器通过。
- K1 验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_learning.py'` 9 tests OK；`test_org_knowledge.py` 10 tests OK；`test_memory_workspace.py` 24 tests OK。覆盖浏览文件字节/时间不变、完整长文、内容/源码/引用/工作区失效、跨项目拒绝、修订幂等、迁移/登记故障回滚。已人工审查新增模块、Store 差异和测试，`git diff --check` 通过。
- K2 期间发现并另行修复：独立 supervisor 自身超时退出后，外层 watchdog 发送取消写入已关闭的控制管道，抛 `BrokenPipeError`，把已有真实 timeout 回执误记成调度错误。失败现场保留 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-learning-timeout-failure-qxs7tkdz/scene`。新增屏障测试先等待真实监督进程退出再发取消，修复前稳定红灯；仅处理终端控制管道 EPIPE，仍必须读取完整、匹配的监督回执，缺回执/清理未知仍失败。
- 超时修复验证：`test_supervised_process.py` 15 tests OK；新确定性屏障用例连续 20/20 通过（20.621s）；`test_learning_runs.py` 27 tests OK（6.994s）。未放宽既有 .6 秒 timeout 或取消断言，完整输出字节与清理状态保持校验。重复脚本首轮类名拼错未运行，修正后实际执行完 20 轮。


- K2 done：新增 learning_runs.py、learning_facts.py 与对应测试；Store 增量迁移、Survey 显式选择独立评审，kb/org_knowledge 读取精确正文确认。独立无工具运行、逐条结论和冻结引用、最多 2 次默认修订/6 次调用/600 秒、幂等和内核锁所有权、完整步骤回执、取消/超时/恢复均已接通。事实原子发布先登记准备回执，失败显式重试或人工放弃；数据库与文件不假称单一原子事务。
- K2 验证：test_learning_runs.py 最终 31/31；test_learning_facts.py 28/28；旧 KB/组织知识及界面相关回归合计 64/64（含新 UI 22 项）。运行引擎真实超时/取消/崩溃恢复/所有权 fence 四例各重复 5 次共 20/20。收尾新增加三个确定性截止/租约测试，修复前 3/3 红灯，修复后通过；再补完整 _work 租约过期链路，从“running 且无 owner”修为 needs_resume，恢复不新增调用、不重置 deadline/calls。
- K2 已审阅：无模型调用持有数据库事务；发布和投影固定 Store→KB/ledger 锁序；历史成功回执只补审计，不因新正文/新来源而重新发布旧版本；来源过期保留人工指针以便撤销，实际使用另行校验。已确认/撤销均只面向确切修订，历史确认未补造机器通过。当前本机原生 Claude 帮助检查失败，测试用合成执行器与真实受管子进程证明机制，未执行真实模型评审。
- K3 doing：评测样本、断言、基线、模型和输入已冻结；正在完成实际任务上下文/旧会话与评测输入一致性审查。发现并修复 token 采集竞态、同一 outbox 同时重放、生成样本升级为留出、改断言复用样本、策略改名绕过样本历史及撤销经验回退 legacy。相关 6 个并发/屏障用例各重复 20 次，共 120/120。
- K3/K4 集成核对：平台任务与策略评测共用上下文过滤和预算渲染；工单上下文预览接入同一边界；知识登记的读取与分类移入 KB 锁，防止撤销后被误当成旧式未管理页面。完整上下文省略记录留在运行回执，不截断原知识正文。已采用事实生成下一草稿时只复制经核实的人工状态头，必须重新评审和采用。
- 当前定向验证：`NO_PROXY='*' no_proxy='*' PYTHONPATH='<离线辅助目录>:tests:.' python3 -m unittest test_learning test_learning_api test_learning_context test_learning_decisions test_learning_eval test_learning_facts test_learning_ledger test_learning_runs`，**166 tests / 17.439s / OK**。新上下文测试最初夹具缺少必需 summary 字段导致 7 个准备阶段错误，仅补齐合成夹具后通过；未改生产校验或既有断言。
- 集成回归：新界面、知识 Agent API、项目库事务及原记忆界面合计 **64 tests，63 通过、1 个可选依赖跳过**。首次命令误写不存在的 `test_ui_memory_workspace`，其导入错误现场保留；改为实际模块 `test_ui_memory` 后单独执行 **15/15 / 1.757s / OK**，没有重复全部用例掩盖错误。
- 定向原始日志及后续全量现场目录：`/private/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-learning-final-g7ug78bx`，保留完整输出、失败捕获与回环限定 sitecustomize；不联网安装依赖。
- 已实际打开本地临时平台页面并检查：项目选择、三类筛选、事实全文/来源详情、机器状态与人工状态分列；无通过批次时采用按钮禁用；策略仅显示 4000–12000 上下文预算；浏览器无 warning/error。仅使用合成账号与临时端口 56208，未启动真实模型或采纳任何业务知识，检查后已关闭页签及临时服务。
- 当前提交：K1 `c453245`；独立超时修复 `5d3d1a1`；K2 `edc032a`。最终会话依赖检查及全量回归完成前不声明 K3/K4 完成。
- 最终回执审查：过滤失效页面后，评测回执的分区统计仍保留过滤前计数；新增断言先复现 `1 != 0`，随后按实际保留项重算计数/字符数。`test_learning_context` + `test_learning_eval` **22/22 / 1.415s / OK**，原文与完整省略清单均保留。
- 会话检查初版：新增独立祖先回执，逐次检查已注入事实/经验/共享副本/策略；继承会话与复制的旧结论均保留依赖，修复追加上下文、服务繁忙重试和会话丢失回退也重新核对。新会话模块 19 项及既有续会话/繁忙重试/分文件修复 3 项合计 **22/22 / 7.154s / OK**。随后总审发现固定提交只读检查与主工作区策略的区别会造成误拒，新增真实 delivery_source + active 策略测试已准确复现，正在修复其实际上下文 root 绑定。
- K3 done：`learn.py` 统一可重入进程锁与带完成标记的日志投影；`learning.py` 保存完整经验修订及样本历史；新增 `learning_decisions.py`、`learning_eval.py`；`agents.py` / `fixloop.py` 接入实际使用和会话依赖；`server.py` 提供严格个人决定与 Agent 草稿/运行的独立入口。对应新增/扩充 learning、ledger、decisions、eval、context、sessions、API 和 delivery source 测试。为使每个提交具备完整依赖，策略运行及 API 基础随 K3 提交，K4 提交页面与操作说明。
- 固定工作区修复：策略回执保存实际 `context_root`；固定 checkout 只能由同一运行的来源记录、提交、工作目录、候选/方案归属共同证明，不能凭任意路径获准。原工作区已采用策略不继承到临时只读 checkout，后者按默认 6000 预算执行；采用撤销后旧冻结输入仍被拒。最终 `test_learning_sessions` 19 + `test_delivery_source_runner` 10，**29/29 / 6.105s / OK**；新增真实进程正例、三个冒用目录反例、准备后真实撤销决定反例。完整日志 `delivery-policy-sessions-green.log`；首轮红灯工具原文转存 `delivery-policy-red-from-tool.log`，文件明确区分转存与重跑。
- K3 审阅：逐段核对后端、会话、API 及对应测试 diff，`git diff --check` 通过。基线已有 delivery source 7 个方法和 supervisor 14 个方法的全部断言 AST 未变；新修复另加测试。`tmh/acceptance.py` 与 `tmh/guard.py` 全文件等同 `949d732`，人确认、保护清单、状态迁移与提交证据约束均未放宽。
- K4 doing：界面 `ui_learning.py` / `ui.py` / `ui_memory.py`、22 个新界面用例，以及设计状态和 `docs/knowledge-learning.md` 使用说明已完成；待最终全量验证后封存结果。
- K4 done：已读回完整操作说明与设计，核对页面入口、三类流程、执行器限制、机器/人工分离、策略范围、撤销恢复与未验证事项。22 个新界面测试和实际浏览器检查均已通过，内容/错误转义、异步切换与草稿保留已覆盖；界面检查后没有再改 UI 代码。K3 提交 `a50f524`；K4 与本记录一并提交。下一步冻结源文件清单，再运行一次全量，发现问题单独提交修复。

### 本轮全量验收与收尾

- 首轮受测提交：`4cc8632`；执行 `NO_PROXY='*' no_proxy='*' PYTHONPATH='<离线辅助目录>:.' python3 -m unittest discover -s tests`。**1331 tests / 401.584s / FAILED（errors=2, skipped=16）**，即 1313 通过、2 错误、16 跳过；完整日志 `full-unittest.log` 保留。265 个受测源文件与冻结清单逐个 SHA-256 一致，运行期间未编辑实现或测试。
- 两个错误均为本轮新增会话检查后需要更新的旧测试夹具，不能记为基线已知失败：① `test_project_bootstrap` 仍 patch 已移走的 `fixloop.build_prompt`，未进入断言即报 AttributeError；② `test_run_handoff` 的模拟父会话只有 mode/ended，没有真实运行 id，新祖先回执读取时报 KeyError，现场数据库记录为 failed/id。失败现场分别为辅助目录内 `failure-b1882075bb2947419122d1a522ed0ac5`、`failure-42c90e91b15e4fe9927fa63d6606d8a6`，已保留完整 traceback 和后者临时数据库。
- 修复范围仅这两个测试文件：替换新的上下文构造接点，并增加它未被调用的断言，确认交付仍使用原冻结材料；创建真实合成父运行，再检查完整需求、resume 和祖先回执。保留全部原断言和时间预算，未为测试放宽生产会话校验。
- 定向命令：`NO_PROXY='*' no_proxy='*' PYTHONPATH='<离线辅助目录>:tests:.' python3 -m unittest test_project_bootstrap test_run_handoff test_learning_sessions`，**42/42 / 12.395s / OK**；完整 `handoff-fixtures-green.log`。已审阅两个 diff，准备单独提交并重新冻结清单后跑全量。
- 首轮跳过原因逐条保存 `first-full-skips.json`：MCP SDK 缺失 14 项（知识 Agent 发现 1 + workbench 13），cryptography 缺失 2 项；未联网安装依赖。已有 HTTPError/SQLite/socket ResourceWarning 和 fork DeprecationWarning 原样保留，未过滤日志。
- 夹具修复已独立提交 `05022ce`，K4 为 `4cc8632`。第二轮全量正在运行，命令与首轮相同，日志改为 `full-unittest-final.log`，265 个源文件冻结于 `final-tested-source-manifest.json`。临时现场捕获器额外覆盖 subTest 错误，原捕获器另存 `sitecustomize-first-full.py`；测试结果统计和断言不变。第二轮开始前工作区干净。
- 最终全量：相同离线命令在 `05022ce` 上执行完毕，**1331 tests / 402.846s / OK（skipped=16）**，即 1315 通过、0 失败/错误，退出码 0。16 条跳过与首轮逐条一致，详见 `final-full-skips.json`；对应测试文件等同设计基线，跳过没有由本轮改动引入。未新增失败现场，首轮错误和全部警告原文仍保留。
- 完整性核对：265 个实现/测试/模板/技能文件与第二轮启动前 SHA-256 清单全部一致。`acceptance.py`、`guard.py`、`filelock.py` 全文件等同 `949d732`；四个有改动的原测试文件共 44 个原方法，其原有断言 AST 全部保留，另增加 2 条断言和 4 个测试方法。结果保存 `verification-result.json`、`baseline-assertions-final.json`，未变更机器配置、真实 data/、凭据或日常服务。
- 日志校验：首轮 `full-unittest.log` 36903 字节 / SHA-256 `f09450be21f1bf0675e8a210fbde3ef304080fff666e233605d480a3f6193b2e`；最终 `full-unittest-final.log` 34756 字节 / SHA-256 `a266dd4514761a454a3f0db36091456ac4937134d4352fa4487ee44d39f61ed8`；最终源码清单 `final-tested-source-manifest.json` 26956 字节 / SHA-256 `2c1c2fedcf1a84621d6893a86280f08fe0f8e8deec91b4e557fc86c42c332634`。
- 最终人工审阅建议：`learning_decisions.py` / `learning_facts.py` 的个人身份、预期版本、决定待办及幂等发布；`learn.py` 的 Store→ledger 锁序、fork 后句柄语义和日志完成标记；`agents.py` / `fixloop.py` 的实际输入、祖先依赖和固定 checkout 策略边界。原 P5 guard 与 P6 filelock 未变，不能把新增流程视作放宽人工确认或证据绑定。
- 待确认/验证边界：无阻塞问题；本机原生 Claude 执行器检查失败，尚未取得真实模型评审准确率、真实任务改善或费用证据；未开启定时运行、自动采用或组织自动推广；生产部署尚未包含本轮改动；Windows 实机锁与受管进程仍需验证（具体剩余阻塞保留在历史 P6 清单）。
- 收尾：最后仅更新设计、使用说明和本进度记录，产品/测试仍为已验证的 `05022ce`。保留原 `stash@{0}`，本轮不 push、不部署；提交后以 `git status --short --branch` 确认工作区干净。

## 2026-10-22：知识分类与评审闭环设计

- 当前项：把用户认可的“项目事实 / 可复用经验 / 执行策略”方向落实成可实施方案；状态：done（设计文档完成，K1–K4 实现均为 todo）。
- 本轮基线：`3ecf977cec9194be80850675a112579e272206d8`，实际分支 `iteration/context-pack-v2`；开工 `git status --short --branch` 干净，无需 stash。不切换回下文历史 Ralph 分支，不重做其已完成事项。
- 修改文件：[知识分类与评审闭环设计](../design/knowledge-learning-loops-2026-10-22.md) 和本进度记录；本轮范围为设计，运行时能力仍需后续实现与验证。
- 已读：最近 10 条提交、既有项目库与上下文设计、知识撰写/校验、经验记录/效果统计、记忆工作区及固定版本引用实现。截图只作为产品参考，不视为另一系统后台已验证的事实或执行指令。
- 设计内容：三类内容与分离的验证/人工决定；固定来源的独立事实评审；有留出样本的经验成对评测；策略允许清单；采用/撤销、并发与恢复语义；统一页面及 K1–K4 验收顺序。现有经验、知识页和引用保持各自权威记录，兼容历史状态，不复制一套独立状态机。
- 验证：`cat` 读回完整设计并人工检查；`python3` 一次性文档检查验证 3 个文档链接、15 个代码/测试文件、11 个现有函数/方法和 9 个章节，退出 0；修改范围仅上述两份文档。`git diff --check` 无问题；新文件的 `git diff --no-index --check` 无空白错误输出。
- 检查脚本首轮把 `git diff --no-index` 表示存在新增内容的退出码 1 当成失败；纠正为同时核对退出码和空白诊断后全部通过，未改产品代码或任何产品测试。纯文档未运行产品回归，也未验证真实模型效果或生产状态。
- 待确认：本轮设计无阻塞；首版采用人工确认生效、项目内适用、有限轮次的保守默认值，自动生效与组织级推广另列扩展。

## 历史 Ralph 实施记录（原分支与状态保留）

- 当前项：SI-015 项目资产与知识库复用实现；状态：doing（从 `60d96e7` 开始；先固定版本知识、引用及派生，再验证页面/Agent 入口和规模边界）
- 仓库：`tob-maintenance-harness`；分支：`feat/ralph-port`
- 起点：`422d9bf`（原分支 `codex/self-evolution-resume`）。
- 只读规格：`/Users/auntlee/Downloads/ralph-learn-pack/codex-prompts.md`，不复制进仓库。
- 恢复顺序：先读本文件和 `git log --oneline -10`，从第一个非 done 项继续；已经 skipped 的项保留原因，不重复执行。
- 初始工作区有 6 个修改文件、1 个未跟踪测试；已执行 `git stash push -u -m 'ralph-port-preflight-2026-10-19'`，保存为 `stash@{0}: On codex/self-evolution-resume: ralph-port-preflight-2026-10-19`。交接时保留 stash，不自动恢复。
- 初次在父目录执行 `git status --short --branch` 报非 Git 仓库；定位子目录后重新执行成功，再 stash、新建分支；未改 Git 配置。
- 不变量：离线；不碰 data/、密钥、证书；不启动日常 8791/8793 服务；不 push；不削弱人确认、证据绑定、钩子、保护清单、状态迁移或基线断言。
- 执行：逐项仅跑指定测试；每项最多 3 轮失败修复，仍失败则撤销该项未提交实现并记 skipped；最终才跑全量。

| 项目 | 状态 | 提交 | 说明 |
|---|---|---|---|
| P1 | done | `407d196` | AGENTS 区块预算与命令路由 |
| P2 | done | `eac0e2f` | 非阻塞任务尺寸提示 |
| P3 | done | `d761bb6` | 经验卡固定开销 lint |
| P4 | done | `ff532c8` | 已知死路及来源验证 |
| P5 | done | `c594ee5` | 结构反馈草稿与人确认 |
| P6 | done | `a06c09e` | 可替换文件锁与 Windows 阻塞盘点 |

## P1

- 状态：done。
- 阅读范围：`tmh/install.py`、两个模板、`tests/test_tmh.py`。
- 计划改动：`templates/AGENTS.block.md`、`docs/agent-commands.md`、`tests/test_tmh.py`；如安装后命令指引需要随工具分发，在 `tmh/install.py` 补对应复制。
- 命令/结果：`git status --short --branch` 确认旧改动；stash 成功；`git switch -c feat/ralph-port` 成功；工作区干净。
- 差异/假设：规格“单会话只做一项”由本次用户连续完成六项的指令覆盖；不请求暂停确认。
- 待确认：无。
- 实际改动：`templates/AGENTS.block.md` 从 7832 降至 2975 字节（≤3584）；新增 `docs/agent-commands.md`，`tmh/install.py` 随安装复制到 `.tmh/docs/`；`tests/test_tmh.py` 增加预算、硬规则与分发一致性验证。全部硬规则保留，证据绑定提交和禁止绕过钩子明示。
- 验证：`python3 -m unittest discover -s tests -p 'test_tmh.py'`，46 tests，OK（5.080s）。临时 Git 仓库运行 `install(root, ['claude', 'codex'])` 后实际读回 AGENTS.md 全文，确认 CLAUDE 引用和命令文档字节相同。`git diff --check` 通过，逐段审阅实现 diff 和新文档。
- 修复轮数：0；一次 patch 格式校验失败，未写入任何文件，改为单次更新后成功。

## P2

- 状态：done。
- 范围：`tmh/acceptance.py`、`tmh/cli.py`、`tmh/platform/epic.py`、`tests/test_acceptance.py`、`tests/test_platform.py`；规格提到 `intake.py` 时只按需定位入口。
- 计划：尺寸提示与 AC 放行逻辑分离，CLI 检查/进入实现和父单日志都提示；不自动拆分或改契约。
- 命令/结果：已完成 acceptance 全文件、platform 的 big_requirement 筛选及临时仓库 check 输出核对，见下方记录。
- 待确认：无。

### P2 验证记录

- `python3 -m unittest discover -s tests -p 'test_acceptance.py'`：14 tests，OK（2.423s）。临时仓库 CLI check 显示 9 条 AC 与并列标题提示，退出码仍为 0。
- platform 首轮 3 tests 报错：访问回环测试服务得到 HTTP 502，项目列表为空；推断为继承的代理把 localhost 请求转发。改用仅当前测试进程 `NO_PROXY='*' no_proxy='*'` 重跑，禁止回环请求走代理；未改测试或产品逻辑。
- 重跑 `NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_platform.py' -k big_requirement`：3 tests，OK（1.383s）；仅有既有测试资源关闭警告。后续测试沿用 NO_PROXY，未改机器设置。
- 实际改动：上述 5 个文件。`size_warnings` 与 `ac_problems`/`advance` 放行条件隔离；CLI check/成功进入 implementing 打印提示；epic 在建子单之前用 `_edit`/`_log` 记录，保留正常创建流程。
- 假设/阈值：peers 传其他契约原文、排除自身与无有效 AC 的样本；≥5 份时按条数或“条款+检查方式”字符量达到中位数 2 倍提示；少于 5 份用 >8 条 / >1600 字。后者相当于 8 条较长的约 200 字条款。标题并列、新建数 >3 独立提示；文件数量只匹配明确数字或反引号列表，避免猜测。epic 同一批其他 item 作为 peers。
- 审阅：已逐段检查 git diff；`git diff --check` 通过；基线断言、状态机、人确认和证据逻辑未改。失败处理：环境修复 1 轮，无实现修复。

## P3

- 状态：done。
- 范围：`tmh/platform/learn.py`、`tests/test_lessons.py`。
- 计划：只过滤含全局固定动作的经验卡提示注入，返回命中原句；保留人的原文与现有状态，不改变存储格式。
- 命令/结果：`test_lessons.py` 已通过，见下方记录。
- 待确认：无。
- 实际改动：`overhead_flags` 匹配 fix/verify/anti 的每次/每轮必须、开工前先、改完一律，以及 always + 动作、before/after every/each task/run/session/change/iteration/commit；排除有场景条件的建议和非指令的事实句。匹配原句仅在 add/edit 返回值携带 flags，不写入 lessons.jsonl 新字段。
- `relevant` 对本项目与已采纳共享卡均过滤；按既有 `_note_once` 模式每工单每轮人裁决前记录一次 overhead 日志。状态、信任和失败计数规则不变。
- 代码差异：原 edit 和日志折叠均截断到 800 字，edit 还 strip；为满足“人的原文逐字保留”移除这些处理，字段/存储格式不变。长文本测试覆盖末尾命中句及空白/换行完整保存。
- 验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_lessons.py'`：16 tests，OK（0.040s）；已审阅 git diff，`git diff --check` 通过；实现修复 0 轮。
- 边界：规则有意偏保守，未显式表达全局动作的说法可能漏报；未改页面/CLI 展示层（返回值已提供 flags）。

## P4

- 状态：done。
- 范围：只读 `docs/self-improvement/` 的 verification 记录及规格允许的 STATUS，修改 `skills/legacy-feature/SKILL.md`、`skills/acceptance-l2/SKILL.md`、`tests/test_tmh.py`，新增 `docs/dead-ends.md`。
- 计划：只纳入验证记录能直接支持的结论；保留环境限定；表格不含客户标识、地址、报价或凭据。
- 命令/结果：test_tmh 和 3 条来源抽查已完成，见下方记录。
- 待确认：无。
- 实际改动：新增 15 行文档、9 条死路；两个技能正文各增加按场景指向，description 未改；新增来源文件存在和行数预算测试。
- 来源抽查：① external-candidate 的“保留的失败与修复”第 1 条直接记录沙箱 TCP/Git 拒绝；② runtime 的问题表第 1 条记录父退出 0 仍有子孙与管道阻塞，配原始红灯日志；③ harness2 的基线/候选表及后文明确双方进程退出 0 但基线业务失败。另逐条核对 preview-health 的直接 2xx/无重定向约束、裸预览 401、Git archive 和优化模式 assert，来源均支持表述。
- 差异/假设：规格举例提到 Node/原生 Codex，表使用证据直接证明的“POSIX 包装父进程”表述，不推断特定包装器；沙箱限制仅针对记录中的 workspace-write 环境。
- 审阅：读回完整表并核对 5 列，无客户名、地址、报价、凭据；逐段审阅 diff，`git diff --check` 通过。未访问链接或证据目录之外的运行数据。
- 验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_tmh.py'`：47 tests，OK（6.079s）；修复 0 轮。

## P5

- 状态：done。
- 范围：`tmh/acceptance.py`、`tmh/cli.py`、`tmh/guard.py`、`tests/test_acceptance.py`；只读规格列出的 `tmh/task.py` 与指定钩子测试。
- 计划：missing-requirement/dependency 产生非任务草稿；同源最多两份未确认；人确认入口复用 `_human`，guard 增加拦截；不改 MOVES/HUMAN_ONLY、不接平台。
- 命令/结果：test_acceptance、指定 guard 钩子及临时仓库模拟上报→人工确认已完成，见下方记录。
- 待确认：平台接入留作建议，不在本次实现。
- 首轮：19 个 acceptance 测试、10 个 GuardAndVerifyTest/AgentHookTest 均通过。补并发及确认回执失败恢复两例后 21 个测试通过（3.003s）。
- 手工流程发现绝对草稿路径 `/var/...` 与 root.resolve() 的 `/private/var/...` 别名不一致，确认后返回相对路径报 ValueError；修复第 1 轮：先检查限定目录和符号链接，再规范化 path；新增用绝对路径确认的覆盖，重新跑指定测试和手工流程。
- 最终验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_acceptance.py'`：21 tests，OK（3.611s）；此前新增两例的中间版 21 tests 也通过（3.003s）。`... -p 'test_tmh.py' -k GuardAndVerifyTest -k AgentHookTest`：10 tests，OK（1.530s），包括 dangerous_bash 及 Codex hook。
- 临时 Git 仓库 CLI 手工流程复跑成功：上报→读回完整 Markdown→用测试夹具模拟人工入口→读回确认人/新任务号；新任务 T002 为 draft_contract、confirmed_by=None，源任务未迁移。不是实际任务或真人验收操作。
- 实际改动：4 个授权文件。草稿示例 `.tmh/acceptance/proposals/T001-1.md`，首行 JSON 注释标记来源/类型/状态，正文含建议标题、待补 AC 与完整原话（围栏长度避开原话反引号）；确认后原文保留并追加人名和任务号。
- 收敛：同来源两类合计最多 2 份 pending；跨进程 mkdir 写锁防并发穿透，异常释放；损坏草稿保守拒绝；重复确认拒绝；回执写失败重试复用已建 draft。进程被强杀可能留下 `.write-lock`，需人核实后清理（不把该锁用作崩溃恢复所有权证明）。
- 审阅：已逐段看实现/测试 diff，`git diff --check` 通过；guard 仅追加 propose-confirm 模式；MOVES/HUMAN_ONLY/AGENT_ENV、ALWAYS_PROTECTED、原确认/关闭拦截及证据链未改。共 1 轮实现修复。
- 平台建议：以后在父单展示结构反馈待审列表，人在正常身份验证入口选择采纳，生成 draft 后再走原有规格/AC 确认；不直接调用 `_follow_up` 自动放单。

## P6

- 状态：done。
- 范围：`tmh/platform/crash_recovery.py`、`recheck_operations.py`、`candidates.py`、`harness_probes.py`、`tmh/kb.py`，新增 `tmh/platform/filelock.py` 和 `tests/test_filelock.py`；只读指定相关测试及 Windows 剩余阻塞所需静态定位。
- 计划：POSIX flock / Windows msvcrt 第 0 字节锁统一接口，句柄/进程退出释放；保留 kb 的无原生后端 O_EXCL 回退；回执格式和恢复门槛不改。
- 命令/结果：filelock、新旧恢复/候选/探测指定测试与 KB 队列用例均已通过，见下方记录。
- 待确认：Windows 余项已列于后文，不扩展进程监管实现。
- 实际改动：新增 filelock + 12 个测试，4 个平台模块全部改用统一接口，KB 仅替换原生分支并保留 O_EXCL 回退。锁后端延迟加载，不存在 fcntl 时走 msvcrt；非阻塞竞争统一 BlockingIOError；Windows 在持有第 0 字节范围锁后初始化空文件，避免竞争写入；保留位置、非竞争错误和既有业务提示。
- 锁语义：当前所有调用点均排他；OS 句柄关闭/进程退出释放。Windows blocking=True 以非阻塞调用循环等待，避免 CRT 内建重试上限。所有权判断不使用 O_EXCL、历史 PID 或残留文件存在性。回执/数据库结构未改，process_control/supervised_process 未改。
- 验证：所有命令仅带进程级 `NO_PROXY='*' no_proxy='*'`，使用 `python3 -m unittest discover -s tests -p <文件>`：test_filelock.py **12/12**（0.148s）；test_crash_recovery_api.py **6/6**（0.612s）；test_crash_recovery_independent.py **8/8**（2.875s）；test_recheck_operations.py **14/14**（3.901s）；test_external_candidates.py **11/11**（8.724s）；test_harness_probes.py **7/7**（13.909s）；test_harness_probes_independent.py **9/9**（10.721s）；`test_tmh.py -k test_queue_is_bottom_up_and_parallel_safe` **1/1**（0.141s）。修复 0 轮。
- 实测边界：macOS/POSIX 真锁、真子进程 kill 后释放；Windows 使用 mock fcntl=None/msvcrt 验证 4 模块实际导入与锁调用、竞争/阻塞/错误/初始化。没有 Windows 实机，不把 mock 当实机结果。
- 审阅：逐段查看全部 git diff（含新文件），`git diff --check` 通过。AST 对比起点 `422d9bf`：MOVES/HUMAN_ONLY/AGENT_ENV/ALWAYS_PROTECTED 完全相同，DANGEROUS_BASH 仅追加一条；4 个有改动的既有测试文件中所有原 test_* 方法 AST 均未变。

## Windows 剩余阻塞（只盘点，不改）

1. 已知范围外：process_control.run_process / supervised_process.run_supervised 仍显式拒绝非 POSIX，受管组、管道传递等仍需另行移植。
2. `tmh/platform/preview.py` 的 `_kill` 使用 os.killpg/SIGKILL，启动依赖 shell=True/start_new_session；默认 Django 命令为 POSIX 环境变量前缀语法。预览进程身份与退出判断也需要 Windows 专门验证。
3. `tmh/platform/fixloop.py:_local` 写死 `/bin/sh -c`；命令拼装使用 shlex.quote/POSIX cd 语法。Windows 本地构建需要平台适配。
4. `tmh/install.py` 的 Codex hook/MCP 使用 sh、`$(...)`、`/dev/null` 与 python3；pre-commit 为 `/bin/sh`。`project_bootstrap.py` 用 shlex.quote 生成测试/预览命令；原生 cmd/PowerShell 不能直接视作兼容。
5. `candidates.py` Git 的 `core.hooksPath=/dev/null`，以及硬链接、POSIX 可执行位/0600/0444 权限语义，需要在 Windows/Git for Windows/目标文件系统实测；这些属于条件兼容风险，不断言 NTFS 不支持硬链接。
6. 本次默认排他锁满足所有现有调用点；`exclusive=False` 使用 CRT read-lock 模式，Windows 可能比 POSIX LOCK_SH 更严格，不能保证多个读者并行。若后续需要真共享锁，应单独设计 Windows 原生共享后端；当前无该生产调用点。

## P1–P6 首次全量回归（历史记录）

- 状态：done；测试实现提交 `a06c09e`；运行 `python3 -m unittest discover -s tests`。仅测试进程设置 NO_PROXY，并通过临时 PYTHONPATH 的 sitecustomize 禁止非回环 socket/DNS；不改机器配置、产品代码或测试断言。
- 完整原始日志：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-port-validation-i4mv6w0e/full-unittest.log`；离线辅助文件也仅在该临时目录。执行前 `git status --short --branch` 干净。
- 全量结果：806 tests，369.499s，FAILED（failures=1, skipped=15），即 790 通过、15 跳过、1 失败。唯一失败为 `test_direct_invocation_lifecycle.DirectInvocationLifecycleTest.test_intake_timeout_or_cancel_cannot_apply_a_late_successful_answer` 的 cancelled 子场景，预期 cancelled，实际 failed/124（总超时）。已有 socket/SQLite/HTTPError 资源关闭警告保留在原始日志。
- 跳过原因：用 unittest loader 只读取跳过标记，未重跑用例；`test_sign.py` 两例缺 cryptography，`test_workbench_mcp.py` 十三例缺可选 MCP SDK。未联网安装依赖。
- 当前分支单例复跑：同一离线环境执行 `python3 -m unittest discover -s tests -p 'test_direct_invocation_lifecycle.py' -k test_intake_timeout_or_cancel_cannot_apply_a_late_successful_answer -v`，1 test，OK（0.750s）。
- 基线复现：只从 `422d9bf` 导出 `tmh/`、`templates/`、`skills/`、该单个测试至临时 `baseline-422d9bf/`，没有导出 data/ 或任何密钥/证书。132 个文件的 `git hash-object` 逐个等于起点 blob，排除 archive 替换差异；基线没有本分支代码。相同环境重复原单例（最多 30 次，首次失败立即停止），第 13 次（1.705s）在同一 cancelled 子场景、同一断言、同一 failed/124 信息失败。没有修改测试夹具、断言或 0.5 秒预算，没有人为注入延时。
- 原始复现日志：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-port-validation-i4mv6w0e/baseline-reproduction.log`。入口命令为 `python3 -`，循环用 `unittest.defaultTestLoader.discover('tests', pattern='test_direct_invocation_lifecycle.py')` 只筛选上述 testMethodName，每轮以 `unittest.TextTestRunner(verbosity=2)` 执行，失败 `sys.exit(1)`。基线进程退出码 1。
- 非本分支引入的证据：该测试、`intake.py`、`agents.py`、`process_control.py`、`supervised_process.py` 的当前字节全部与起点一致；基线原样复现同一失败。测试的 0.5 秒总预算可能先于模拟 cancel 耗尽，成功返回码断言因此先失败；该时序敏感问题留待单独处理，未放宽断言或修改范围外监管逻辑。按完成标准保留并披露这一基线失败，不用反复全量重跑掩盖它。
- 原始日志校验：full-unittest.log 为 23269 字节，SHA256 `73578db1fdec8a9ef114b3b33d17420379a975af5e7bba1df34e9eafc127e19c`；baseline-reproduction.log 为 6151 字节，SHA256 `6a200d4b09675d76f125665057493138149875f8da9918576f78f305f298cb8f`。
- 收尾只更新本进度文件，产品/测试实现仍为 `a06c09e`；原 stash 保留。人工审阅重点：P5 的 guard 新规则、propose_confirm 人身份/幂等恢复边界，P6 的 filelock 字节锁/关闭释放/阻塞重试及 KB 回退边界。

## 待确认

- P5 平台接入：建议新增人工待审入口，不直接从结构反馈调用 `_follow_up` 自动派发；本次不接平台。
- P5 异常中断若留下 proposals/.write-lock，需要人先核实无活跃操作再清理；不自动猜测所有权。
- P5 升级前若确认回执写入失败，已有任务使用旧版未引用的草稿快照，升级后重试会保守拒绝；需人工核对草稿和任务内容，不自动迁移或推定已确认。
- P6：上列 Windows 剩余阻塞；需 Windows 实机验证默认排他锁自动释放，尤其不同文件系统与进程退出路径。共享读锁的并行性不在已证明范围。
- intake 基线时序失败已在下节修复并通过全量；没有新增待确认事项，生产监管实现保持原样。
- 构建树 2 秒就绪竞态已在末节自然复现、保留完整现场并修复，通过稳定性与全量回归；本次没有新增待确认事项，原时间限制和断言均保留。更早那次无现场的具体启动阶段仍不作推断。

## 后续：intake 取消测试基线时序修复

- 状态：done；起点 `db4e957`，继续在 `feat/ralph-port`；开工 `git status --short --branch` 干净，原 stash 保留。独立提交标题：`test: 消除 intake 取消用例的墙钟竞态`（本记录与修复一起提交）。
- 用户授权：修复基线时序失败，不能削弱断言或简单放宽超时；先验证稳定性，再跑全量，更新本文件并单独提交；不 push，全程自动推进。
- 定位结论：原 fixture 给真实进程与最终结果处理共用 0.5 秒预算，只有 invoke 已返回 0 才注入 cancel；若系统调度/监管收尾先耗尽预算，cancel 根本没有执行。生产超时行为符合规则，缺陷在测试未确定“成功退出→取消/超时→最终采纳”的事件先后；用测试时钟固定该顺序。
- 阅读范围：`tests/test_direct_invocation_lifecycle.py`、`tmh/platform/agents.py`、`intake.py` 及底层监管/生命周期测试。
- 待确认：无。
- 修复范围：只改 `tests/test_direct_invocation_lifecycle.py` 与本文件；生产 Runner/intake/监管器没有修改。测试局部替换 `agents.time` 的单调时钟，其他墙钟及全局 time 模块保持真实；原 0.5 秒逻辑预算和传递给监管器的预算均保留并断言。真实监管器/子进程照常执行，测试适配层仅给它独立的 5 秒墙钟 watchdog，避免进程启动决定调用者测试的事件先后。
- 原 sleep 改为把逻辑时钟精确推进到 deadline，未延长被验证的逻辑超时；新增 deadline 前 1ms 成功、取消先发生后 deadline 到达、真实监管启动延迟 0.6 秒三个场景。原断言全部保留，另增加原进程 exited/0、预算值与 cleanup.complete 的断言。
- 红灯：先只加“慢监管启动”用例，在旧夹具下运行对应 `-k test_intake_cancel_after_slow_supervisor_startup_keeps_successful_process_evidence`，1 test，0.862s，按预期失败（failed != cancelled，124 != 0）。随后应用可控时钟夹具。
- 首次绿灯：`python3 -m unittest discover -s tests -p 'test_direct_invocation_lifecycle.py' -v`，15 tests，6.893s，OK；日志位于 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/intake-lifecycle-validation-vx3ag9qb/direct-green.log`。全部后续验证继承进程级 NO_PROXY 与该临时目录的离线 sitecustomize。
- 稳定性计划：原失败用例连续 100 次，完整 direct invocation 模块连续 10 轮；任何失败立即停下修复。再核对真实墙钟监管相关测试和完整回归；不修改已有真实超时用例。
- 稳定性结果：上述 100 次原用例 + 10 轮完整模块（150 tests），合计 **250 次测试执行全部通过**，119.306s，无跳过；每轮还验证两个 patch 已正确恢复，未泄漏给后续测试。命令为 `python3 <临时目录>/stability.py`，脚本与完整 `stability.log` 保留在同一临时目录。
- 回归敏感性：临时脚本 `regression_guards.py` 分别在内存禁用 Runner.stop_reason / Runner.cancel，原用例分别按预期产生 2 / 1 个断言失败，均直接拒绝“迟到智能体答案被采纳”；脚本确认失败类型后退出 0。没有改磁盘上的生产代码。这些是有意注入错误的负向实验，完整记录在 `regression-guards.log`。
- 审阅：逐段查看测试 diff；AST 对比 `db4e957` 确认原 **42 条断言全部原样保留**；`git diff --check` 通过，生产 tmh/ 内容未变。以下真实墙钟验证、全量均已完成。
- 真实墙钟验证：分别运行 `python3 -m unittest discover -s tests -p <文件> -v`：`test_process_control.py` 14 tests / 6.808s，`test_supervised_process.py` 14 / 4.535s，`test_run_lifecycle.py` 13 / 23.677s，合计 **41/41 通过**。没有应用本次测试夹具的 clock/supervisor patch；包含监管启动计入超时、真实进程树超时/取消和总预算跨调用等既有断言。日志 `real-deadlines.log`。
- 后续全量：**809 tests，374.241s，OK（skipped=15）**，即 794 通过、15 因可选依赖缺失跳过、0 失败/错误，退出码 0。运行 `python3 -m unittest discover -s tests`，仅继承进程级 NO_PROXY 和临时离线 sitecustomize。受测基线 `db4e957`，唯一测试改动文件 SHA256 `f1354cf3b708bffe8e838a0c8994fb6679b68ef6561fdcc7f3d7f7b65448d7c1`；测试结束后再次核对相同 hash。原始输出保存到同临时目录 `full-unittest.log`，既有资源关闭警告原样保留。
- 日志校验：`stability.log` 13563 字节 / SHA256 `aa31f211063c92fcb07eb37b93c88d4821772a3c149bf72d52ae746043e7bf22`；`full-unittest.log` 22075 字节 / SHA256 `b6510cbf468941461eafefd46f0fa92e7a9093156e5796b7822b0cd6d679dc34`。临时脚本、其他验证日志均保留，无压缩/截断。
- 收尾：只提交上述测试文件和本记录；无生产代码修改、无新的失败待处理，不 push，保留原 stash。

## 最终审查

- 状态：done；起点 `11078c5`，`feat/ralph-port` 开工干净。用户授权发现问题直接修复、验证、单独提交，不 push；原离线与不触碰真实数据/凭据的限制继续适用。
- 审查重点：P5 人工确认及 guard 可接受的命令形式、草稿与恢复边界；P6 所有权释放/Windows 字节锁/错误处理；11078c5 的测试时钟与 5 秒 watchdog 是否丢失真实超时覆盖。
- 已读进度与最近 10 条提交，完成代码审查、本地复现、修复与最终全量；待确认/已知限制见前文清单及各节。

### P5 审查修复

- 状态：done；提交 `1a11236`；修改 `tmh/acceptance.py`、`tmh/guard.py`、`tests/test_acceptance.py` 和本记录。以下确认行为全部是临时仓库内的合成测试，没有替人确认真实任务。
- 复现：5 个新增用例在修复前出现 11 个断言失败、1 个错误。① 当前 Codex 无沙箱环境仅有 `CODEX_THREAD_ID`，旧 `_human` 未识别；② guard 漏过前置选项、引号、转义和 `--to` 缩写等有效 CLI 命令；③ 引用原话的 `## 4.` 可被解析成新任务 AC；④ 确认回执失败后修改草稿，重试仍复用过期任务；⑤ proposals 目录符号链接可先写出仓库，最后才报路径异常。
- 修复：AGENT_ENV 只追加 `CODEX_THREAD_ID`；保留全部原始 DANGEROUS_BASH，新增 shell 分词和真实 CLI 参数解析的补充拦截；采纳原文逐行加 blockquote 前缀（测试反向去前缀逐字相等），不再参与契约章节解析；重试必须匹配原文快照；读写前拒绝草稿存储路径及文件符号链接。既有 MOVES/HUMAN_ONLY、保护清单、证据绑定不变。
- 验证：`python3 -m unittest discover -s tests -p 'test_acceptance.py' -v` **26/26**（5.872s）；`... -p 'test_tmh.py' -k GuardAndVerifyTest -k AgentHookTest -v` **10/10**（1.675s）。完整日志在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-final-review-b2e6yow4/` 的 `p5-red.log`、`p5-green.log`、`p5-hooks.log`。所有验证使用进程级 NO_PROXY 和临时离线 sitecustomize。
- 已亲自逐段审阅 diff，`git diff --check` 通过；原有测试方法和断言未改。guard 解析明确限于可见的字面命令，不宣称是任意 shell 求值的安全沙箱，运行时 `_human` 独立拦截仍保留。
- 待确认：旧版本回执中断留下的任务使用未引用的快照，升级后重试将保守拒绝，需人核对后处理；不自动改写旧任务或推定已确认。

### P6 审查修复

- 状态：done；提交 `21e68cd`；已复现 KB 原生锁获取把 ENOSPC 错误重试 1200 次并报“被占用”，以及 KeyboardInterrupt 时句柄未关闭。只收紧 `tmh/kb.py` 的异常分类/清理，保留内核所有权锁和无后端的 O_EXCL 旧回退；新增 3 个 `tests/test_filelock.py` 用例。锁后端和生产所有权回执没有改动。
- 红灯：`test_filelock.py -k kb_` 4 tests，2 failed；ENOSPC 被隐藏为 TimeoutError，打断后 fstat 仍成功。绿灯：`python3 -m unittest discover -s tests -p 'test_filelock.py' -v` **15/15**（0.396s），涵盖真实 POSIX 互斥/阻塞/关句柄/进程杀死释放、Windows mock 初始化及异常路径；`... -p 'test_tmh.py' -k test_queue_is_bottom_up_and_parallel_safe -v` **1/1**（0.210s），并行 KB 队列仍正确。日志 `p6-red.log`、`p6-green.log`、`p6-kb-queue.log`。
- 已逐段审阅两文件 diff，`git diff --check` 通过；只对规范化的 BlockingIOError 重试，其他异常立即抛出并关 fd。竞争的 1200 次/0.05 秒策略未放宽，底层字节锁/O_EXCL 回退未改。待确认仍为前文 Windows 实机验证/进程监管等剩余阻塞，没有把 mock 结果当实机证明。

### 11078c5 超时覆盖审查

- 状态：done；可控时钟与 5 秒 watchdog 只用于调用者事件顺序，不能单独证明真实 0.5 秒超时。补独立的 `tests/test_intake_wall_clock.py`：Runner/监管器使用真实 time，透传原 timeout，仅故意延迟真实 Popen 0.6 秒；必须 failed/124、规则回退、reader 未启动且清理完整。稳定性、回归敏感性及最终全量已通过；与本记录独立提交。
- 新用例最初按 `no_spawn` 字段检查时报 KeyError；核对真实 process_control 回执后改为断言 `cleanup.trigger == timeout_before_spawn`、完整校验的监管回执 `pid is None` 及 reader marker 不存在，验证意图未变。独立测试 **1/1**（0.865s）通过。原文件只补说明，原方法和 0.5 秒逻辑预算/5 秒测试 watchdog 均未改。
- 稳定性：临时 `stability.py` 交替执行完整 direct invocation 模块（15 tests）和独立墙钟模块（1 test），共 10 轮 **160/160**，88.079s；每个模块执行完检查 agents.time 与监管函数均恢复，未污染后续真实时钟用例。完整 `stability.log` 保留。
- 负向实验：临时 `watchdog_sensitivity.py` 在内存将真实监管执行预算替换为 5 秒；新用例按预期失败，原始监管回执为 `exited/0` 而非 `timeout/124`。脚本核对这一失败后退出 0，说明 Runner 最后标记 124 不能掩盖越过真实截止时间的 reader 执行；没有修改磁盘生产代码。完整 `watchdog-sensitivity.log` 保留。
- 审阅：已读回整个新增测试；AST 对比 `11078c5`，acceptance/filelock/direct invocation 的所有原方法均未改；对比起点 `422d9bf`，MOVES/HUMAN_ONLY/ALWAYS_PROTECTED 相同，AGENT_ENV/DANGEROUS_BASH 仅追加。`git diff --check` 通过。
- 全量：运行 `python3 -m unittest discover -s tests`，仅设置进程级 NO_PROXY 与临时离线 sitecustomize。首轮及最终结果完整保留于末节。

### P5 回执临时文件追加审查

- 状态：done；提交 `3a16a62`。首轮全量运行期间只在临时夹具中继续核对写入边界，未修改受测实现。复现预先创建 `T001-1.tmp` 符号链接时，旧 staging.write_text 会先覆写仓库外合成文件，再把链接移至草稿路径；`p5-staging-reproduction.log` 保留失败断言。
- 执行顺序：首轮全量结束后改为同目录独占创建唯一临时文件，关闭后再原子 replace，保留失败清理/重试语义；新增不触碰旧临时链接目标的测试，再跑最终全量。待确认：无。
- 完成：首轮全量结束后才改实现；`NamedTemporaryFile(delete=False)` 独占创建、关闭后 replace、finally 清理，不读写旧 `.tmp` 链接。新增回归检查仓库外合成文件字节不变、旧链接未动、确认后草稿为普通文件、无新临时文件遗留。验收测试 **27/27**（4.746s），含原回执失败恢复测试；`p5-staging-green.log` 保留。亲自审阅 diff，`git diff --check` 通过。状态：done。

### 最终审查全量与构建树失败对照

- 首轮全量：**818 tests，408.143s，FAILED（failures=1, skipped=15）**；唯一失败 `test_run_lifecycle.RunLifecycleTest.test_build_tree_uses_run_budget_and_cannot_launch_model_after_timeout`，在 2 秒 `wait_ready` 内三个合成进程树标记均未出现，尚未进入后续 3 秒总预算/5.5 秒收尾断言。intake、P5、P6 新用例没有失败。日志 `full-unittest.log`，受测 8 个实现/测试文件运行前后 SHA256 完全一致（`validated-files.json`）。
- 对照方法：该测试及 `agents.py`/`process_control.py`/`supervised_process.py` 与 `422d9bf` 没有差异。不能仅凭字节相同或复跑转绿判定根因；临时 `build_tree_diagnostics.py` 连续跑原单例，失败时在清理前保存合成 run/lifecycle/监管回执，未改其断言或时间限制。另导出起点 tmh/templates/skills 与该测试，逐个核对 Git blob，用于独立对照；没有导出真实 data/ 或凭据。
- 对照结果：当前分支原单例 **20/20**（72.072s），起点原样副本 **20/20**（69.255s），均未复现。起点目录 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-review-baseline-422d9bf-15ak0872` 的 132 文件逐个等于起点 blob；日志 `build-tree-current.log`、`build-tree-baseline.log`。本轮不宣称已证明该偶发失败的根因或修复它；原 2/3/5.5 秒限制和全部断言保留。
- 最终全量：在 P5 staging 修复提交 `3a16a62` 和本节测试改动上运行 `python3 -m unittest discover -s tests`，**819 tests，400.354s，OK（skipped=15）**，即 **804 通过、15 跳过、0 失败/错误，退出码 0**。8 个受测实现/测试文件的运行前后 SHA256 一致（`validated-files-final.json`），最终再次检查全部原测试方法 AST 未变、`git diff --check` 通过。原生监管代码没有修改。
- 跳过原因只读核对（没有再执行测试）：1 项 cryptography not installed；1 项 needs both（cryptography 与 ssh-keygen，当前缺前者）；13 项 optional MCP SDK not installed。没有联网补依赖。既有资源关闭警告保留在日志中。
- 最终全量的临时 sitecustomize 阻止非回环网络；仅父 unittest 进程的 addFailure 附加只读诊断，在 run_lifecycle 失败时于清理前记录合成运行回执，不改用例/结果/断言，也不向子解释器增加 unittest 导入。最终没有失败，诊断快照未触发。
- 日志校验：`full-unittest.log` 24630 字节 / SHA256 `784f142238cfeed97351ef88097fd6844962e3e091b69d926dc6b770b256568c`；`full-final.log` 23014 字节 / SHA256 `e45a2ecb2403510eb6ffe71ca163a190d2c921af26f55ea767152f9d7df838e3`；`stability.log` 2959 字节 / SHA256 `cf340b7e96057c77d4f2417d85122daf8d15da65ba83d7ac1813455a45302f82`。其余复现/负向/对照日志及脚本同目录原样保留。
- 交接重点：`guard.py:_human_accept_command` 及 acceptance 的 agent 标记、引用/快照/路径/临时文件边界；`kb.py:_Lock` 的重试分类与失败释放，以及 `filelock.py` Windows 字节锁/共享读锁限制；`test_intake_wall_clock.py` 的真实 0.5 秒约束和未启动证据。P1–P6 均保持 done，原 stash 保留，不 push。

## 后续：构建树 2 秒就绪失败

- 状态：done；起点 `baaf980`；已读本文件和最近 10 条提交；开工 `git status --short --branch` 干净，继续使用 `feat/ralph-port`，原 stash 保留。修复和本记录一起独立提交，标题 `test: 消除构建树夹具的串行解释器启动竞态`。
- 用户授权：保留失败现场确认根因，不削弱断言或简单放宽超时；稳定性验证后再跑全量，更新本文件、单独提交、不 push，全程自动推进。
- 计划：临时诊断脚本记录原用例各阶段真实耗时与工作线程栈，失败时保留整个合成临时仓库、进程回执和数据库，同时正常清理本测试所属进程。先定位，再针对根因修复，验证红绿灯与稳定性，最后全量。
- 阅读范围：`tests/test_run_lifecycle.py`、`tmh/platform/agents.py`、`fixloop.py`、`supervised_process.py` 与相关本地监管实现；沿用进程级离线保护和 NO_PROXY。未接触真实 data/ 或凭据。
- 待确认：无；原 2 秒就绪、3 秒总预算和 5.5 秒收尾限制保留。上一轮失败没有完整现场，不能用已通过的复跑代替根因证据。
- 自然复现：临时 `diagnose.py` 只包装阶段计时/观察回执和线程栈，测试、夹具、时间限制未改，也未注入延时或外加负载。完整生命周期模块 5 轮 **65/65**（122.470s）后，原构建树单例连续诊断在第 **18 次**失败（前 17 次通过）。日志、完整逐轮 trace 与诊断脚本保存在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-build-tree-zypem_4_/`。
- 失败现场：原合成仓库、数据库和全部回执保留在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-lifecycle-7_36wxhl/`，清理前快照 `failure-083.json`、完整时间线 `trace-083.json`。未删改现场；仍执行所属进程清理，之后只查询 PID 注册表中的 39874/39875/39878，`ps` 返回 1、输出为空，无这些进程遗留（`failure-cleanup-check.txt`）。
- 根因证据：以原 `wait_ready` 开始为零点，工作树准备结束约 0.540s，本地构建进入监管约 0.735s，监管器 ready/running 约 1.620/1.687s；tree/child/leaf 标记观察于约 2.031/2.271/2.325s。约 2.042s 就绪检查失败时只看到 tree 标记，run 仍为 running，`stopped_reason` 为空，工作线程正常在监管轮询中，3 秒总预算尚余约 0.96 秒。逐代 `Popen(sys.executable, ...)` 重复 Python 初始化/导入，把真实启动抖动串行叠加进 2 秒夹具握手。失败后的 cleanup 杀父进程导致最终 `orphaned/125`，不能把这个收尾结果倒因为生产超时。原先那次“全无标记”现场未保留，本次证明的是同一就绪竞态的自然复现，不臆测旧现场的具体阶段或 OS 调度原因。
- 修复：仅修改 `tests/test_run_lifecycle.py` 夹具，使用无线程的独立 POSIX 进程内 `os.fork()` 创建真实父/子/孙，每代仍独立登记 PID、设置忽略 TERM、写就绪标记和输出并持有日志管道；去掉不必要的 json/pathlib/subprocess 导入。生产代码、控制时钟、超时和监管器均未改；原 **13 个测试及全部原有辅助方法 AST 完全未变**。
- 新回归：仅对子代重新启动 Python 注入真实 1.05 秒延时（两代合计至少 2.1 秒），复用原构建树测试的全部断言和原时间限制；就绪时用 `ps` 验证三个不同活 PID、真实 parent→child→leaf 关系和同一进程组，结束后校验真实运行至少 3 秒、只有一个构建 attempt、timeout/124、TERM/KILL/完整清理和三代原始输出。没有伪造时钟、扩大 watchdog 或只重标失败状态。
- 初次验证：完整模块 **14/14**（27.546s，`lifecycle-green.log`）；最初慢启动红灯在旧夹具下就绪失败（2.529s，`slow-start-red.log`）。随后把延时限定为子解释器启动，以准确回归重复初始化；最终版本见下方红绿对照与稳定性记录。
- 最终回归红绿对照：临时 Python 脚本只在进程内将 `FIXTURE` 替换为 `git show baaf980:tests/test_run_lifecycle.py` 中原字符串，最终新增用例于 2 秒就绪处按预期失败（3.058s）；恢复修复后字符串，同一用例通过（3.449s）。`descendant-red-green.log` 完整保存，脚本检查失败类型后退出 0；磁盘生产代码从未改动。
- 稳定性阶段一：原失败用例连续 **100/100**，356.078s；命令 `NO_PROXY='*' no_proxy='*' PYTHONPATH=<诊断目录>:. python3 <诊断目录>/diagnose.py stability 100`。仍使用真实监管器、真实时钟与原始时间限制；随后顺序执行完整模块 10 轮，失败立即停止并保留合成现场，全部通过后才运行全量。
- 审阅：亲自逐段查看测试 diff；AST 检查原 30 个函数（含 13 个原测试方法）全部相同；`git diff --check` 通过，`git diff --name-only -- tmh` 为空。失败现场 `owned-fixture.py` 与 `baaf980` 原 FIXTURE 逐字相同，SHA256 `ef831e1336ab4cb4136427098f01ce8384e54138b816759cb332f6477627c1e0`。当前受测文件 SHA256 已保存至 `validated-files.json`，后续验证结束再次核对。
- 稳定性完成：原用例 100 次 + 完整模块 10 轮 × 14 次，合计 **240/240**，621.312s、0 跳过/失败/错误，进程退出码 0。其中模块阶段 **140/140**，265.234s；原用例总共 110 次就绪时间中位数 0.226s、最大 1.134s（原限制 2s）。完整 `stability.log` 和逐次 trace 均保留；受测测试文件哈希与阶段开始一致。随后才执行以下全量。
- 全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<诊断目录>:. python3 -m unittest discover -s tests`，**820 tests，307.188s，OK（skipped=15）**，即 **805 通过、15 跳过、0 失败/错误，退出码 0**。仍为 2 项缺 cryptography、13 项缺可选 MCP SDK；没有联网安装依赖。既有资源关闭警告原样保留，未改断言或屏蔽警告。离线 sitecustomize 仅在 unittest 主进程安装失败现场保留回调，本次未触发；子解释器只有离线保护，没有增加诊断导入。
- 最终核对：测试文件 SHA256 `f6625c87113382f20fcdbf74862575ca035346aa676cd3040207edea035178ea` 与稳定性开始、全量前后完全一致；原函数 AST 仍全部相同，生产 tmh/ 无 diff，`git diff --check` 通过。读回保留现场的监管回执，身份/nonce/原始输出哈希校验通过，三代完整日志均存在，失败后的进程清理为 complete；未把这个 cleanup 导致的 orphaned 回执冒充自然 timeout。
- 日志校验：`failure-083.json` 7488 字节 / SHA256 `6aa9f6dd27656f945b1253ca13398e231030c92ac046d943971ed034e257b876`；`trace-083.json` 152026 字节 / SHA256 `a6f0adf6233bed8039617f628edfcfc83a36a3ca336e5f7a91ac6b0d3f92c6c5`；`stability.log` 55954 字节 / SHA256 `917960e399a0a24278cc0bb4022fc28da24770e94d81c8fb2e6d45e4892b1bb1`；`full-unittest.log` 23049 字节 / SHA256 `c2e97c334265b3b64e640f05d3febbda6cadc92f57fc14d1fed7afdc8e9797fb`。其余日志哈希在同目录 `evidence-manifest.json`，没有压缩或截断文件。
- 收尾：只提交测试夹具/新回归和本进度文件；原 stash 保留，不 push。建议审阅本次真实三代 fork、每代 PID/信号/管道语义，以及新增回归的父子关系和真实 deadline 断言；P5 guard/人工确认、P6 锁语义与 Windows 待确认清单保持上一轮结论。

## 后续：复审 552eab9

- 状态：done；开工 `git status --short --branch` 干净，已读本文件和 `git log --oneline -10`；继续在 `feat/ralph-port`，原 stash 保留。独立提交标题：`test: 修复 fork 夹具就绪标记的发布竞态`。
- 范围：`tests/test_run_lifecycle.py`、监管器/进程控制与相关测试；仅本地合成进程、真实时钟，原 2 秒就绪、3 秒总预算和 5.5 秒清理边界不变。
- 计划：核查真实父子关系、信号与管道继承；用故障注入检查覆盖敏感性；先复现 `.ready` 创建与 PID 写入之间的发布窗口，再做最小修复、稳定性验证和全量。
- 已知边界：前轮慢启动注入针对再次启动子解释器；fork 后不会执行这段初始化延时，它验证消除串行初始化，不证明任意子进程调度延时都能满足就绪约束。实际超时与收尾仍由真实时钟检验。
- 待确认：无。人工确认/guard/锁的既有结论及 Windows 待确认清单保持不变；不 push。
- 发现并复现：`ready()` 原先先创建最终文件，再写 PID；新三代关系断言会读到空串。将真实孙进程暂停在 `open` 之后、`write` 之前，三代 PID 均存活，`.leaf.ready` 已存在且内容为空，回归准确失败（0.244s）。完整现场 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-lifecycle-re_vrdn6/` 和写入前快照保留在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-fork-audit-mtcvk_k2/`。
- 修复：夹具先写同目录、带 PID 的临时文件，关闭后 `os.replace` 原子发布就绪标记；新增真实孙进程发布屏障回归，释放后复用原三代取消测试的全部断言。红灯后同用例通过（0.652s）；原有时间限制和生产代码未改。慢解释器回归补注释明确其覆盖边界，不改行为。
- 故障注入：只在临时文件/测试进程内替换夹具或监管 worker，共 7 组：缺少孙进程、恢复默认 TERM、只杀 leader、忽略 invoke 取消、忽略构建取消、忽略真实 deadline、将真实 deadline 减半。全部由预期断言拒绝，非偶发错误；各轮正常清理后注册的活进程均为空，脚本/完整失败日志/现场在同目录，汇总 `mutation-summary.json`。生产文件没有写入故障代码。
- 审查结论：未发现真实三代进程、取消、超时和清理覆盖退化；发现的就绪标记发布窗口已修复。fork 发生在独立、无线程的夹具进程；每代独立登记 PID、忽略 TERM、持有原输出管道；三代真实 parent/PPID/PGID 断言保留。底层测试仍验证 TERM 忽略跨 exec、父退出而孙代持管道、输出 EOF 后清理、外部进程组不受影响、服务退出后的监管清理，以及监管启动时间计入 deadline。
- 定向验证：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 -m unittest -v test_run_lifecycle test_process_control test_supervised_process test_run_early_stop`，**47/47 通过**，34.532s、0 跳过，退出码 0；完整日志 `targeted.log`。原红灯场景注册的三个 PID 再次用精确 PID 查询，均已不存在。
- 差异验证：相对 `552eab9`，既有 **32 个函数（含 14 个测试）AST 全部不变**；FIXTURE 除 `ready` 函数外 AST 全部不变，生产 `tmh/` 无 diff，`git diff --check` 通过。受测文件 SHA256 `3151a3ab5ef58c16a13d71d2b90a2e22d3caf9edeb27b128f763cd67c1cb0f76` 写入 `validated-files.json`，稳定性和全量结束再次核对。
- 稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 <审查目录>/stability.py`，**150/150 通过**，205.006s、0 跳过/失败/错误，退出码 0。包括新发布屏障 50 次，以及原构建超时、新三代关系/真实 deadline、构建取消、invoke 取消、父退出清理各 20 次。保留完整 `stability.log`、逐次耗时与汇总；130 次就绪等待中位数 0.111s、最大 0.281s（发布屏障用例的该采样从释放后开始；其屏障等待另有 2 秒真实上限）。前后受测文件哈希一致，随后才跑全量。
- 全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 -m unittest discover -s tests`，**821 tests，299.133s，OK（skipped=15）**，即 **806 通过、15 跳过、0 失败/错误，退出码 0**。跳过原因仍为 2 项缺 cryptography、13 项缺可选 MCP SDK（逐项清单 `optional-skips.json`）；没有联网安装。资源关闭警告原样保留。父进程失败诊断未触发，子解释器仅继承离线保护。
- 最终核对：受测文件哈希在定向、稳定性、全量前后相同；审阅完整测试及本文件 diff，`git diff --check` 通过，生产目录无 diff。只提交这两个文件，原 stash 保留，不 push；提交号绑定至审查目录的 `validated-files.json`，完整文件哈希见 `evidence-manifest.json`。
- 日志校验：`publication-before-write.json` 376 字节 / SHA256 `9a0cee84a0f7a1a98ab607e0caffdcac4b71624ce5ead4a7aa2eae3a30cfefc0`；`mutation-summary.json` 2037 字节 / SHA256 `0c5503ea0a0bcbeafa756878d9aa5d636cf0bbed5501d311d47f9cfadb736648`；`stability.log` 29595 字节 / SHA256 `987b46e1cf997f6d62a194473c9f9a302ddfae3e1ab817cc999eb10b53c044cb`；`full-unittest.log` 23022 字节 / SHA256 `5a6dd94a8d8fc336da1ace364c6f832bddd501e85f4ff0459992decef8f1943a`。
- 人工审阅建议：`ready()` 的同目录原子发布；新发布屏障用例在真实孙进程写 PID 前检查标记不可见，释放后执行原取消断言；慢解释器回归注释的覆盖边界。无新增待确认，P5 guard/人工确认、P6 锁语义和 Windows 剩余阻塞点保留原清单。

## 后续：复审 7bce98f

- 状态：done；开工 `git status --short --branch` 干净，已读本文件与最近 10 条提交，继续在 `feat/ralph-port`，不 push，原 stash 保留。独立提交标题：`test: 加强发布屏障并修复迟启动清理竞态`。
- 范围：夹具原子发布、屏障握手与断言失败时的所属进程清理；只用合成临时仓库和进程、真实时钟，不放宽断言或超时。
- 计划：检查关闭/替换顺序及发布前后屏障；在临时脚本中注入关闭前发布、缺失/失败握手和迟启动，检查是否误通过或遗留进程；有实际问题再做最小修复并验证。
- 待确认：无新增；原 P5/P6 和 Windows 待确认清单保留。
- 审查发现一：原子发布实现本身顺序正确，但新增屏障只停在写入前，无法稳定检验关闭顺序。在临时夹具里把 `os.replace` 移入 `with`、放在关闭前，同一屏障用例 **5/5 错误通过**（3.061s），日志 `early-publish-before.log`。改为在真实孙进程写 PID 后、关闭前暂停，要求此时最终标记仍不存在；原夹具的原子发布实现不变。
- 审查发现二：原有 `cleanup_owned` 在 PID 快照后才启动的进程不会被清理，新屏障断言失败也会走这条路径。用 Event 将启动延后至空 PID 快照之后，真实屏障在原 2 秒处失败，原清理返回后仍有 **3 个活 PID 和 1 个活工作线程**。诊断脚本随后取消/回收它们，确认全无遗留；这是复用的旧辅助函数缺陷，不是 rename 引起。现场 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-lifecycle-zsf4jhdy/` 原样保留。
- 修复：测试清理先取消本测试库中尚未结束的运行，再取 PID 快照并保留原精确 PID 清理、2 秒线程 join；并发结束仅在状态已变为终态时忽略 cancel 的 ValueError。新增迟启动回归，不替换真实监管器或时钟：旧辅助函数准确失败（2.144s），修复后和屏障正常路径一起通过。
- 证据目录：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-publication-audit-0oj1565f/`。保留 `probe-before.py`、关闭前发布的错误夹具、原清理后与诊断救援后的 PID/线程快照 `late-launch-cleanup.json`、`cleanup-red.log` 及失败现场；后续日志另命名，不覆盖红灯证据。
- 红绿核对：两条正向回归 **2/2**（0.780s）；错误的“关闭前发布”夹具由此前 5/5 误通过变为 **5/5 准确失败**（0.928s，全部命中关闭前标记可见断言）。同一迟启动/屏障超时诊断在修复后不再启动任何夹具进程，清理返回时 PID 为空、工作线程已结束，后置诊断救援无需再杀进程（`late-launch-cleanup-after.json`）。
- 异常路径：释放标记写入失败、缺失暂停标记、孙进程在屏障处退出、rename 失败，四种情况都保留原错误/失败，清理后所属 PID 和工作线程均为空；现场/完整日志与 `negative-paths-summary.json` 保留。取消本身出错时仍在 `finally` 执行原精确 PID 回收和 join，合成 OSError 原样上抛，实测三个活进程全部回收、线程结束（`cancel-error.json`）。
- 初步定向：4 个相关模块 **48/48 通过**（34.562s）；随后补上上述取消异常的 finally 保证，针对最终字节重新跑同一组和稳定性。原 `FIXTURE` 字节完全未变；原 14 个其他测试方法 AST 不变，只加强清理辅助函数、屏障用例并新增迟启动回归。
- 最终定向：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 -m unittest -v test_run_lifecycle test_process_control test_supervised_process test_run_early_stop`，**48/48 通过**，34.480s、0 跳过，退出码 0，日志 `targeted-final.log`。最终受测文件 SHA256 `bb203df83d78697333344bb8713319a7defc968c84f1485e3f50fb2fb0d7ddd3` 保存至 `validated-files.json`。
- 清理复核：13 个保留的负向合成现场，逐个按注册表的精确 PID 查询，均已不存在；没有按进程名或端口查杀。`final-negative-cleanup.json` 保留核对结果。原超时/取消断言在清理前判定（或记录失败条件后明确 fail），新增清理不能把这些失败改为通过。
- 屏障语义：`.paused`/`.release` 仅用存在性握手，不读取其内容，不依赖它们的 PID 文本完整性；每个用例使用全新的私有临时目录。屏障位于真实文件关闭前，释放后才允许 close 与原子替换；最终 `.ready` 继续读取 PID 并校验活进程，原 2 秒就绪/取消和其他运行预算不变。
- 稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 <审查目录>/stability.py`，**148/148 通过**（两条重点回归各 50 次 + 完整模块 3 轮 × 16 项），115.961s、0 跳过/失败/错误，退出码 0。77 次就绪等待最大 0.838s；屏障用例的这个采样从释放后开始，暂停握手另有原 2 秒上限。真实时钟与超时不变，文件哈希前后一致；完整日志/逐次记录保留。随后才执行全量。
- 全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 -m unittest discover -s tests`，**822 tests，355.484s，OK（skipped=15）**，即 **807 通过、15 跳过、0 失败/错误，退出码 0**。逐项核对仍是缺 cryptography 的 2 项和缺可选 MCP SDK 的 13 项（`optional-skips.json`），未联网安装；原资源关闭警告保留。此前 5 份故意制造的失败快照保留，全量没有新增失败快照。
- 最终审查：原子发布实现无需改动；修复了屏障漏检和复用清理函数的迟启动漏洞。取消异常仍上抛，原精确 PID 清理和 2 秒 join 在 finally 中执行；没有扩大进程筛选范围，也没有放宽任一原时间限制。原 14 项其他测试 AST、整个 FIXTURE 字节及生产 `tmh/` 均无改动；最终代码哈希在定向、稳定性、全量前后相同，`git diff --check` 通过。只提交测试与本进度文件，提交号绑定到 `validated-files.json`。
- 日志校验：`early-publish-before.log` 1031 字节 / SHA256 `4e7e47ed0e1013982443f55e513c66fa76d3f2351a3bcecc9c94d4bd159f4338`；`early-publish-after.log` 11903 字节 / SHA256 `4360229eca2e626b3420b7d68d46ad6bd3e8d2fbdda7c2052da397ffe94fdf5a`；`late-launch-cleanup.json` 424 字节 / SHA256 `6024632cc93340ef4a325f28c524699112648e8402f21a0ebedf966c962a7df3`；`stability.log` 28555 字节 / SHA256 `b9cf73907def93a1e73b7da171617fb8669176aa16318c7729a95a142585bb52`；`full-unittest.log` 22988 字节 / SHA256 `c59c8b328de94bd64297cecaccfd5c273033980873c2a1d697f1303eef0621b6`。其余原始文件哈希在同目录 `evidence-manifest.json`。
- 人工重点：屏障从 write 前移到 close 前，是否准确捕获关闭前发布；`cleanup_owned` 先取消再取 PID 快照、并在取消出错时仍清理的顺序；迟启动回归的 Event 释放与 finally。无新增待确认，P5/P6 与 Windows 剩余阻塞点沿用原清单。

## 后续：项目资产与知识库复用设计

- 状态：done；起点 `663b98e`，`feat/ralph-port` 开工干净。P1–P6 和既有后续修复保持 done；本条是新需求设计，不将设计完成计作功能实现完成。
- 需求：标品及一个或多个参考项目可先作为知识来源，客户项目从已有标品派生；参考项目以后也能作为待修改老项目。底层需支持数十万行代码、灵活组合与知识复用。
- 已读：项目 Store/API/UI、Knowledge、graph/kb/context/parsecache、survey、Agent 上下文入口、现有相关测试与知识库/待办说明；只读本地源码和文档，不接触真实 data/ 或凭据，不启动服务。
- 发现：目前 project 主要绑定一个 root；解析按文件缓存、知识页锚点和队列可复用，但没有固定版本的跨项目引用/派生关系。图谱仍整体重建，检索缓存一次只保留一个项目；既有能力不能直接证明复杂标品规模下可用。
- 实际产物：`docs/design/project-knowledge-library-2026-10-20.md`、`docs/self-improvement/BACKLOG.md` 与本进度文件。设计包含统一实体、版本/来源/权限边界、现有落点、分段交付和行为验收；SI-015 实现仍为待办。
- 假设：角色可组合；引用默认固定版本、只提供资料；同项目继续维护与从标品派生客户项目均支持；已有人工确认和代码证据边界不变。不假定用户已指定某个真实参考仓库或授权导入。
- 验证：`cat docs/design/project-knowledge-library-2026-10-20.md` 完整读回 163 行 / 17326 UTF-8 字节；临时 Python 检查 5 条相对文档链接有效，9 个实现落点的文件/函数或类实际存在；检查代码围栏闭合与“设计/未实现”声明。`git diff --check` 通过；逐段审阅新文档与两份记录 diff。本轮仅文档，未运行或重报产品测试。
- 交接：单独文档提交 `docs: 设计标品与参考项目的版本化知识复用`，不 push。继续实施时先读 SI-015 与设计，按 A→B→C→D 验证；不重复 P1–P6，也不将当前文档视为真实项目接入或迁移授权。
- 待确认：没有阻塞设计的问题；真实仓库、分享范围与性能目标在后续接入时明确，保留为实施输入，不凭空编造。

## SI-015 实施

- 状态：done（首版交付；精细依赖分析和真实标品试点仍待续）；用户已明确“然后开始实现吧”。起点 `60d96e7`，`feat/ralph-port` 开工干净；原 stash 保持。不 push，不访问网络/真实 data/凭据，不启动日常服务，不改 Git 配置。
- 范围：兼容旧项目的来源/角色/工作区、不可变知识修订、多个固定引用及全文读取、从标品派生和同项目开始维护、任务输入绑定、网页及 CLI/MCP、失败恢复和规模验证。
- 执行：主线程实现知识构建/存储/引用/派生；按 executing-plans 技能的分工要求，由子代理独立处理页面与 Agent 接口，各自限定文件，统一审查与验收。其引用的附属技能本机未安装，使用现有 Git 分支及验证流程完成同类工作，不影响用户已授权范围。
- 合理假设：首版固定版本来自本地 Git；非 Git 项目沿用旧功能，版本化共享明确报告不支持，不伪造提交。权限范围是现有可信本地平台，跨项目共享须明确授予；不宣称组织级账号隔离。真实大型标品尚未指定，先用临时多仓库和数十万行合成项目验证，实际标品列为剩余验证项。
- 计划验证：来源不改写、同名隔离/固定引用/全文保留、更新与撤权失效、取消/失败恢复、派生字节与知识确认边界、UI/CLI/API；相关定向回归后全量。所有测试使用临时目录或临时仓库。
- 待确认：无阻塞实现的问题；真实试点仓库保留为后续接入输入。
- 初步实现：新增 `tmh/project_knowledge.py` 静态 worker 和 `tmh/platform/project_library.py`；来源原文与分析产物分目录，发布固定提交/分析器/配置/文件/索引摘要。Store 增量迁移来源与角色；知识引用、派生/维护、API/CLI/MCP/页面接入；任务与方案记录引用输入摘要。
- 第一轮定向：`python3 -m unittest -v tests.test_project_library tests.test_library_lifecycle tests.test_knowledge_agent_api tests.test_ui_library tests.test_ui_dialog`：55 tests，9.473s，OK（54 通过、1 缺 MCP SDK 跳过）。真实临时仓库/监督子进程覆盖固定版本、双来源、授权范围、全文、派生、迁移、失败/取消恢复；UI 为执行 JS 回归，尚不能替代浏览器验证。
- 自审修复：拿锁后重读 ready 状态；初次启动不抹掉 queued 取消；worker 核对真实分析器；禁用 Git replace/外部协议/继承索引配置；原文与生成知识命名空间分离；检索校验索引摘要并关闭连接。两项竞态测试注入旧行为均在预期断言失败，恢复新版通过。
- 后续加固进行中：旧执行入口拒绝 reference 工作流；共享/派生须真实登录会话或独立操作者凭据；归档来源任务/验收/验证报告，保留原始导入提交，客户知识重新确认；交付方案检查准确绑定的 run，不能由新无关方案替代。完整定向/浏览器/规模/全量尚待最终字节验证。
- 本轮验证资料目录：`/private/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-library-validation-_aov13wg/`；后续完整日志保存在此目录，离线保护仅允许测试回环连接，不修改机器设置。
- 实现范围：`tmh/project_knowledge.py`、`platform/project_library.py` 实现静态版本构建、分阶段恢复、范围授权、检索原文、独立派生与维护；Store/server/knowledge 接入兼容迁移与旧路径限制；agents/agent_api/fixloop/preview 绑定引用与执行边界；agent_contract/workbench 接 CLI/MCP；ui_library/ui 接网页。新增 6 个行为测试模块，既有测试只适配只读工具数及最小 mock fixture，原断言含义保持。
- 授权与输入：普通 API token 加人的显示名不能授予共享或创建工作区，7 类管理操作需真实签名会话或独立操作者凭据；Agent 仅能引用已有授权。任务包明确返回固定引用及摘要，与 requirement_hash 使用同一份引用输入；无引用时旧需求摘要逐字兼容。固定交付方案检查其实际 run，不能由新无关方案替代；提示词检索捕获 A→B→A 切换并拒绝启动。
- 工作流：SQLite 短事务原子核验工作流并登记 Runner；项目内核锁串行化工作流切换与预览、复检登记。后台迟到预览必须重新读工作流，仍有活动预览/运行/复检时拒绝切换。只读来源的旧 project/ticket/run/session 写入入口被拒绝，不会先写聊天再报错。
- 文件与确认：源 Git 对象原样导出到 source，分析产物在 analysis，生成页使用独立 `@knowledge/` 命名空间。派生先写精确导入提交，再另写初始化提交；来源任务/验收/报告完整归档，来源确认保留为历史并改为当前项目待确认。有排除文件的快照拒绝完整派生，未静默复制不完整工程。
- 实际排查记录：最初一组回归误写不存在的 `test_candidates` 模块（145 tests，1 导入错误、13 skips），改用真实模块；另一组 46 tests 发现既有方案选择单测的最小 Mock 缺 `project_id`，补夹具并单独模拟新增引用门槛，仍保留原方案选择全部断言并断言检查 run 10，真实边界另有集成测试。新增首次锁 I/O 错误用例时一次插入位置错误导致 NameError，恢复原取消断言位置后通过；这三次均属测试命令/夹具问题，原日志保留，没有改超时或弱化断言。
- 最终加固：首次 try_lock 的 I/O 错误关闭句柄、保留原异常且不登记/启动构建；`lease-mutation.log` 中运行期换回旧代码准确命中句柄未关闭断言，修复后同用例通过。就绪后恢复、queued 取消、分析器变更、破坏索引/监管回执、同分分页、固定方案失效及引用切换均有反例；内核锁和进程监管沿用 P6/P5 边界。
- 定向命令统一为 `NO_PROXY='*' no_proxy='*' PYTHONPATH=<资料目录>:tests:. python3 -m unittest -v <模块>`：`related-final.log` 9 组既有/新功能 **132/132**，151.319s；`feature-final.log` 新知识/生命周期/边界/集成/Agent/UI/dialog **73 tests，72 通过、1 MCP SDK 缺失跳过**，24.819s；最后锁和布局调整 `final-adjustments.log` **38/38**，4.312s；最终任务包与 UI 时序、既有 Agent API/client `packet-and-ui-final.log` **88/88**，20.969s。
- 稳定性：`python3 <资料目录>/stability.py`，queued 取消、发布后恢复、迟到预览、提示词引用 A→B→A 四条各 20 次，**80/80**，36.441s、0 跳过/失败/错误。保持真实 Git、监督子进程、内核锁与时钟，屏障只控制特定顺序；20 秒测试看门狗不改变产品 1800 秒构建预算。最后锁失败关闭修复不改变这些成功路径，随后完整生命周期模块再次通过。
- 浏览器：用合成帐号和临时回环服务实际登记 STD/REF/CLIENT → 两来源固定构建 → 分范围绑定两份引用 → 同名审批检索 → 完整原文 → 派生客户 → 原项目开始维护 → 客户改模块后与固定标品比较 → 移除引用。DOM、原始截图与全文保存在资料目录；脚本标签按文本呈现，控制台没有 error，全文逐字等于原文件。回执表实际渲染发现长路径挤窄中文列，修正列宽和横向滚动后再次截图亲自查看，未删减内容。
- 浏览器读回：三个原仓库 HEAD/状态保持，三个独立工作区干净，所有导入 blob 等于来源清单；归档报告原字节保留、当前知识待确认，原项目 id 仍为 1、两个旧引用保持、两份监管回执完整，0 模型运行/工单。最后从 CLIENT 移除 STD 后只剩 REF，旧对照消失，搜索只剩 1 条 REF 文档；`browser-verification.json`、`browser-final-state.json` 分别保留两阶段结果。临时服务与浏览器页均已关闭，日常 8791/8793 未启动。
- 网页时序：新增参考卡的比较入口；引用变化清除已有对照，迟到比较成功或错误均不能覆盖新范围；连续比较不同来源以最新请求为准。对应新增回调用例在原行为下先失败后通过；UI 不缓存独立操作者凭据，来源撤权会清除旧搜索/全文/对照，不只改提示文字。
- 规模：`scale.py` 冷/热/单文件变更三次真实构建，**286,780 行 Java、260 源文件、13 个目录组**，耗时 **9.576 / 6.355 / 6.113 秒**；解析文件 **260 / 0 / 1**，缓存条目 **0 / 520 / 518**（每文件两类解析）；峰值 **110018560 / 113344512 / 114147328 字节**；查询耗时 **0.092539 / 0.063672 / 0.061732 秒**。原文与源仓库未改变，分析器摘要与最终代码核对一致（`scale-analyzer-verified.json`）。
- 规模边界：原始脚本输出的 `modules:13` 只是目录组，`one_module_changed` 实际只改一个文件；解析器只识别 **1 个模块、0 业务域/流**。检索词包含宽泛 approval，26,522 命中是词法统计，不代表业务相关性质量。`scale-results.json` 原样保留，不能将合成速度当真实复杂标品的完整理解或多模块精度证明。
- 文档：新增 `docs/project-library.md`（82 行、8533 字节）说明网页/API/CLI/MCP、失败恢复、授权、无损归档和支持边界；设计与 BACKLOG 改为首版已实现，明确 C 的精细依赖/业务冲突与 D 的真实标品试点未完成。逐字读回，链接与代码围栏检查通过；非 Git/外部文档适配器保留后续扩展。
- 首次全量前：已记录 217 个源码/测试/模板/技能文件的 SHA256（`validated-files-before-full.json`），随后运行 `NO_PROXY='*' no_proxy='*' PYTHONPATH=<资料目录>:. python3 -m unittest discover -s tests`。仅父 unittest 进程安装既有生命周期失败现场保留回调；不改变断言、结果或子进程启动时序。首次失败和最终复跑结果、哈希复核见下方。
- 待确认/后续输入：无阻塞首版交付的问题。真实标品路径、允许共享范围与目标性能需实际试点时明确；精细业务依赖传播与升级冲突分析、非 Git/外部文档适配为后续能力。Windows 仍有上文六项阻塞，尤其 POSIX 进程监管、预览/本地 shell、hook 命令、权限/文件系统及原生锁实机验证；本轮静态 worker 复用 POSIX 监管，没有宣称 Windows 可运行。
- 审阅重点：`server.py:api_library_action` 的真实操作者认证与共享范围；`project_library.py:derive/_initialize_workspace` 的原始提交、完整归档和当前项目确认；`agents.py:reviewed_delivery_plan` 与任务包实际引用输入；`project_library.py:_lease/project_guard/resume` 的锁所有权、拿锁后重读和错误释放。`invariants.json` 核对 acceptance/guard/filelock/process_control/supervised_process 五文件与起点逐字一致；MOVES/HUMAN_ONLY/AGENT_ENV/ALWAYS_PROTECTED/DANGEROUS_BASH 的 AST 相同。P5 guard 与 P6 锁的既有人工审阅建议继续有效。

- 首次全量：895 tests，415.697s，FAILED（1 failure、16 skips），退出 1。唯一失败 `test_runtime_review.RuntimeRecoveryReviewTest.test_independent_runners_commit_and_dispatch_only_one_retry` 是本轮引入：Runner 在提示词准备至启动期间独占项目锁，阻止第二个 Runner 到达既有数据库重试去重屏障，两个均未获胜。完整 `full-unittest.log` 保留，SHA256 `8551eda86042e3acc5d4dcac11b54257b51453235db6f234e309dd466e980048`；不归因为环境或基线，也没有修改原测试屏障、断言和时限。
- 并发修复：移除 Runner 准备阶段的整段项目锁；`Store.create_run` 与工作流切换/工作区发布用 `BEGIN IMMEDIATE` 把当前工作流核验和登记置于同一短事务，唯一重试索引仍裁决两个独立 Runner。拒绝路径自动回滚，预览/复检的项目内核锁保持。运行还在事务内核对生成提示词时的工作区，阻止查阅→维护切换后用旧目录提示词启动。
- 新回归：独立连接在提示词完成后切换只读，必须不登记、不认领、不启动；真实 SQLite 写锁探针分别检查运行先登记、工作流先切换时的核验至发布原子性，以及失败后锁已释放；真实固定版本维护后旧工作区提示词拒绝启动。只有最后调度模型的 Thread 被拦截，Git、SQLite、工作流、提示词与派生仍执行真实路径。定向与稳定性结果见下方。
- 并发定向：`python3 -m unittest -v test_runtime_review test_library_boundaries test_library_integration test_run_lifecycle`，**42/42**，43.290s，退出 0（相同离线环境）。原失败的独立 Runner 重试测试逐字未改，现已通过；新三项边界回归均通过。
- 并发反例：只在诊断进程内分别移除运行事务、切换事务、登记时工作流检查、登记时工作区校验，四组均在预期断言准确失败，恢复后均通过（`registration-mutations-final.log`、JSON）。最初诊断函数复制了 globals 导致切换事务的暂停探针未接上，未把这次错误算作有效红灯；旧脚本及日志保留，改为使用原模块 globals 后重新验证。生产源码从未写入故障代码。
- 并发稳定性：上述原重试用例和三项新边界各 20 轮，**80/80**，32.052s，0 失败/错误/跳过，退出 0。真实独立连接、Git 派生、时钟及原重试屏障/时限保留；受测 5 个文件前后 SHA256 一致。最终全量前另存全部 217 文件摘要到 `validated-files-before-full-final.json`，首次失败日志和首轮摘要不覆盖。
- 最终全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<资料目录>:. python3 -m unittest discover -s tests`，**898 tests，305.777s，OK（skipped=16）**，即 **882 通过、16 跳过、0 失败/错误，退出 0**。逐项核对 14 项缺可选 MCP SDK（含 1 项新增协议用例）、2 项缺 cryptography；没有联网安装。资源关闭警告原样保留，未屏蔽。仅加载测试列出的完整跳过清单为 `optional-skips-final.json`。
- 最终字节与不变量：全量前后 217 个源码/测试/模板/技能文件 SHA256 一致（`validated-files-after-full-final.json`）；acceptance/guard/filelock/process_control/supervised_process 五个文件与 `60d96e7` 逐字一致。对比起点 1,196 个原测试/辅助函数 AST，仅两处已说明的 fixture/工具数适配；原独立 Runner 重试测试完整不变，原真实超时/取消/进程清理测试不变。`invariants-final.json` 保留结果。
- 验证日志摘要：`full-final.log` 22972 字节 / SHA256 `ce437d50b9b26a8928235b2246e6126102e60986e5227069418fc4a7b5e2b1ee`；`registration-targeted.log` 7962 字节 / `7aa55eb98ed2804c62774164d1cf2d89ba0816d94ba383a78f3488074da595e8`；`registration-stability.log` 17723 字节 / `f4707f8722a7b82c4a6163503325a4a70671dbed190ecb6c56374a5c8aae3c53`；`registration-mutations-final.log` 6092 字节 / `11844e6f15d598f13d2491bbd636eedba722abf923f887b451892d15101f83f3`。首次全量失败、反例、浏览器原图/DOM、原文、规模脚本与原始测量全部保留，无压缩或截断。
- 收尾：亲自审阅新增实现及全部集成 diff、最后四文件并发修复、基线两处夹具适配和文档；浏览器最终原图再次打开确认可读，文档链接/围栏与 `git diff --check` 通过。使用说明 [project-library.md](../project-library.md) 已读回；设计与 BACKLOG 明确首版及未完成范围。提交标题 `feat: 支持标品与参考项目的固定版本知识复用`，在 `feat/ralph-port` 独立提交，不 push，原 stash 保留。
- 新增人工审阅重点：`Store.create_run`、`project_library.configure/derive` 的短事务、回滚和工作区绑定；共享操作的真实操作者认证；来源确认的完整归档及客户重新确认。P5 guard / 人工确认和 P6 原生锁实现未改，原人工审阅建议及 Windows 六项剩余阻塞清单保持。

## 后续：复审 2c1cd53

- 状态：done；开工 `git status --short --branch` 干净，已读本文件和 `git log --oneline -10`，继续 `feat/ralph-port`，原 stash 保留。独立提交标题：`fix: 修复知识共享及运行登记的并发隔离`。
- 用户授权：重点审查跨项目共享授权、固定版本引用、派生人工确认隔离及运行登记事务并发；有问题直接修复、验证、独立提交，不 push，不等待回复。
- 范围：知识库服务与静态 worker、HTTP/Agent 入口、工作区初始化、任务绑定及 Store/Runner 事务，沿调用链核对既有确认与知识证据规则；不改状态迁移、保护规则、原断言或超时。仅临时仓库、回环与合成进程；不访问网络、真实 data/ 或凭据，不启动日常服务。
- 计划：先构造反例保留原失败，再修实现并验证回归敏感性、并发稳定性，最后全量与哈希/工作区核对。证据目录 `/private/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-library-review-3p9rpt4m/`，使用仅允许回环的进程级离线保护。
- 待确认：无；跨项目共享沿用可信本地平台的项目边界，不将本轮扩展为多租户身份系统。
- 已复现四类问题：运行先提交、引用输入后提交，导致独立连接可见无绑定运行，输入写入失败留下占用重试名额的 queued 记录，登记前最后一次引用变化也未被原子检查；共享范围读改写可覆盖另一连接刚完成的撤权；同项目开始维护更换 root 后，原方案在引用相同时仍被判断可用；发布前检查取消后，另一连接已确认的取消可能被 ready 写入覆盖。
- 原版本反例：生产代码保持 `2c1cd53` 时，新增六条反例 **6/6 准确失败**（2.424s，退出码 1，`review-red.log`）；再次运行 **6/6 失败**（2.400s，`review-red-scenes.log`），在清理前保存六个完整合成仓库、数据库及逐表快照、构建监管回执，目录 `red-scenes/`。未削弱原断言、时间限制或真实监管器。
- 修复：`Store.create_run` 在原 BEGIN IMMEDIATE 内复查引用并写入不可改写的输入/工作区，Runner 不再另行提交绑定；授权合并、引用校验/写入、发布取消检查使用数据库写事务，跨连接串行化。`run_current` 加入实际项目工作区身份，历史未知 root 不补记；已更换工作区的历史方案失效，结果原样保留。
- 修复自审：新增字段迁移初稿缺少跨连接重读；两个真实连接同时读到旧 schema 后，稳定出现重复加列错误（`migration-red.log`，1 test/1 failure/0.086s）。改成 BEGIN IMMEDIATE 后重读再迁移；9 条新增回归 **9/9 通过**（5.836s，`review-green.log`），包含并发升级、历史输入原样兼容及不可覆写绑定。该迁移问题只存在于本轮未提交初稿，未归因于 `2c1cd53`。
- 首轮定向：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 -m unittest -v test_library_review test_library_boundaries test_library_integration test_runtime_review`，**32/32 通过**（19.805s，`targeted-first.log`）；随后新增迁移/凭据边界用例，最终字节仍须重新定向、稳定性和全量验证。
- 第二轮定向与稳定性：8 个模块 **79 tests / 78 通过 / 1 可选 MCP SDK 缺失跳过**（38.231s，`targeted-final.log`）；新增 9 条边界回归加原独立 Runner 重试共 20 轮 **200/200 通过**（77.711s，`stability.log/json`），218 个文件哈希不变。操作者凭据/签名会话分别携带 Agent 标识的 7 类管理请求均 403，真人请求按范围授权正常。
- 调用链续查：`learn._run_case` 绕过 Runner.start，旧提示词可能被登记为新引用；评测、需求理解、人工提交三条直接 create_run 路径未传准备时工作区。新增四条反例 **4/4 准确失败**（1.728s，`direct-callers-red.log`），再次 **4/4 失败**（1.901s），完整合成现场保存在 `direct-callers-red-scenes/`。三个调用文件此前与 `2c1cd53` 相同。
- 补齐调用路径：评测在准备提示词前捕获引用，并将同一份输入传给提示词与登记事务；评测/需求理解/人工提交都传 `expected_root`，工作区变化时在登记前拒绝。未改其时钟、watchdog、取消/清理或人工验收逻辑。因有新的实际发现，重新跑最终定向和稳定性后再开始第一次全量；前轮日志保留，不覆盖。
- 最终定向：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 -m unittest -v test_library_review test_project_library test_library_lifecycle test_library_boundaries test_library_integration test_runtime_review test_knowledge_agent_api test_project_bootstrap test_direct_invocation_lifecycle test_handwork_lifecycle test_intake_wall_clock test_intake_recovery`，**115 tests / 114 通过 / 1 可选 MCP SDK 缺失跳过 / 0 失败错误**（43.545s、退出码 0，`targeted-after-callers.log`）。包含 14 条新增测试及既有直接调用、真实时钟、取消、人工提交生命周期。
- 不变量：原 82 个测试文件逐字未改；acceptance/guard/filelock/process_control/supervised_process 与 `2c1cd53` 逐字一致，HUMAN_ONLY/AGENT_ENV/MOVES/保护路径及钩子不变。来源决策归档、完整派生、读取授权与固定版本校验函数 AST 不变；其原行为测试通过。218 个受测文件哈希已记录至 `validated-files-final.json`，定向前后相同；检查结果在 `invariants.json`。
- 最终稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 <审查目录>/stability-after-callers.py`，13 条新增运行/并发边界测试加原独立 Runner 重试，共 20 轮轮换顺序，**280/280 通过**（118.602s、0 跳过/失败/错误、退出码 0）。逐轮耗时和哈希核验见 `stability-after-callers.json/log`；218 个文件全程未变。之后才启动本轮第一次全量 `python3 -m unittest discover -s tests`。
- 失败现场回收核对：两组保留场景中 9 个真实监管构建的 supervisor/worker PID 均已不存在，`negative-scenes-cleanup.json` 保留精确 PID 查询及原清理回执；未按名称/端口查杀。其余一个输入写入失败场景没有启动进程。
- 人工重点审阅：`project_library.act/reference/_run` 中授权读改写、引用登记、发布取消检查的事务边界；`Store.create_run` 及四个调用入口的输入快照/工作区核验与整体回滚；`schema/run_current/bind_run` 的历史未知工作区、不可改写证据与并发迁移语义。派生确认归档原实现不变，P5 guard/人工确认和 P6 原生锁保持原审阅重点及 Windows 六项剩余阻塞清单；无新增待确认。
- 全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 -m unittest discover -s tests`，**912 tests，371.850s，OK（skipped=16）**，即 **896 通过、16 跳过、0 失败/错误，退出码 0**。14 项缺可选 MCP SDK、2 项缺 cryptography，逐项身份/原因保存在 `optional-skips.json`；未联网安装。资源关闭警告原样保留，失败现场捕获没有触发。仅测试父进程安装诊断记录，子进程只继承离线保护。
- 收尾核验：全量前后 218 个源码/测试/模板/技能文件 SHA256 相同（`validated-files-final.json` 与 `validated-files-after-full.json`）；完整审阅六个生产文件、新增测试、使用说明与进度记录 diff，`git diff --check` 通过。修改为 `platform/{agents,handwork,intake,learn,project_library,store}.py`、新增 `tests/test_library_review.py`、`docs/project-library.md` 及本文件。不改原状态迁移/验收/保护规则，不访问真实 data/凭据，不 push，不修改 Git 配置；原 stash 保留。
- 日志校验：`review-red.log` 7334 字节 / SHA256 `fa53a66d570398739bd8ee41e7d97e581e4ef897b63435aa07bb467399758ad8`；`direct-callers-red.log` 8583 字节 / `387999624fe42a656997e338cb23bdf753a558de3fc53790e70bdb745b3a7877`；`targeted-after-callers.log` 22164 字节 / `9d1c52fd2a9ca553fdd2c59bf54c257287c5379303fa8b8d7a91d406cb123afb`；`stability-after-callers.log` 52525 字节 / `b75373eea393b6acab82cd29c3f7fa79aa6907388deb2129f7ad74dfb776004e`；`full-unittest.log` 23275 字节 / `12c28a102f178656573582324a93e289a37467db47e59293b9a852c94daddb05`。提交号与完整原始证据目录绑定记录在 `validation.json`/`evidence-manifest.json`。

## 后续：复审 2bb56f4

- 状态：done；开工 `git status --short --branch` 干净，已读本文件与 `git log --oneline -10`，继续 `feat/ralph-port`，原 stash 保留，不 push。
- 范围：新事务回滚/并发、历史工作区证据和数据库迁移兼容，沿运行登记及候选验收调用链检查死锁、误拒绝和错绑。原状态迁移、人工确认/guard/锁规则、基线测试断言及超时保持。
- 计划：真实临时数据库、仓库和独立连接构造反例；保留失败现场后做最小修复；定向与稳定性验证后跑一次全量，核验字节及工作区并独立提交。
- 证据目录：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-transaction-review-knzki576/`；沿用仅允许回环的进程级离线保护，旧轮证据不覆盖。不访问真实 data/凭据，不联网，不启动日常服务，不改 Git 配置。
- 开工检查记录：发现候选提交另有直接 INSERT runs 的路径，先将其与新增工作区绑定的交互列为待验证疑点；下方反例随后证实缺陷。
- 待确认：无；历史缺失工作区身份不得从当前 root 猜测补写，继续保持来源证据的保守边界。
- 反例：原 `2bb56f4` 生产代码下新增 6 条回归 **6/6 准确失败**（2.441s，退出 1，`review-red.log`），完整临时仓库和逐表数据库快照在 `red-scenes/`。包括外部候选漏绑/更换工作区后误拒绝、候选准备后工作区变化仍登记、分次读取授权拼出从未同时有效的状态、历史缺失绑定可被补写、无绑定兼容分支未核对运行所属项目。候选漏绑及分次授权读取是沿调用链发现的既有缺口；新工作区候选被历史证据规则拒绝是本次提交的兼容回归，不把所有发现都归因为该提交新引入。
- 修复：候选在原写事务内复查工作区、需求和授权并写入固定输入，去重含工作区身份；候选读取也检查来源证据。历史缺失绑定只能保留，不能用当前身份补写。当前证据核验用持有 Store 锁的读取 SAVEPOINT，整体读取运行归属/工作区/引用/授权；支持调用方已有写事务，不提前提交。
- 首轮绿灯排查：6 条中 5 通过，真实候选复检 1 失败（3.540s，`review-green-first.log`），因新夹具在基线 VALUE=1 时断言 VALUE=2，产品正确判为基线失败。改为基线严格断言 1、候选提交同时把实现和断言改为 2；未改已有测试或放宽断言。随后 12 条 **12/12**（7.306s，`review-green-second.log`）。
- 回滚/迁移覆盖：真实 SQLite 读锁使运行提交失败，运行/绑定/重试名额全部回滚；授权合并后引用写入被触发器拒绝，授权和引用一起回滚；旧五列库在 ALTER 被拒绝和 COMMIT 遇 BUSY 两阶段失败后，原数据/模式保持、写锁释放，随后可重新升级。历史空 root 不回填；读取 SAVEPOINT 的正常/拒绝/异常路径均不提交外层事务。
- 续查：候选拿到复检来源锁后会第二次读取状态，但预览分支忽略第二次 current=false。真实候选构建通过后、两次读取之间由独立连接撤权，旧执行函数仍调用预览启动；反例 **1/1 准确失败**（2.703s，`preview-red.log`），现场 `preview-red-scene/` 保留。补查锁内当前状态，最终启动调用仅在测试中拦截，不启动实际预览服务。
- 定向：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<本轮证据目录>:tests:. python3 -m unittest -v test_library_transactions test_library_review test_project_library test_library_lifecycle test_library_boundaries test_library_integration test_runtime_review test_external_candidates test_external_candidates_independent test_recheck_operations test_recheck_publication test_agent_api`，**140/140 通过**（68.272s，0 跳过/失败/错误，退出 0，`targeted.log`）。既有候选真实验证、独立人工签收、迁移和运行去重均包含在内。
- 敏感性：仅在诊断进程中换入旧候选读取、删除工作区去重字段、候选输入前提前提交、恢复分次读取、读取核验提前提交外层事务，**5/5** 均准确命中预期断言，0 非预期错误（`mutations.log` / `mutation-results.json`）。完整负向现场在 `mutation-scenes/`，生产文件未写入故障代码；不能将这些故意的红灯算作正常测试失败。
- 不变量：原 83 个测试文件逐字未改，acceptance/guard/filelock/process_control/supervised_process 与 `2bb56f4` 逐字一致；219 个受测源码/测试/模板/技能文件 SHA256 已保存至 `validated-files.json`。未改状态迁移、人工确认、钩子、锁所有权或原断言/超时。
- 稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<本轮证据目录>:tests:. python3 <本轮证据目录>/stability.py`，13 条新增回归加原有双连接迁移、双 Runner 重试，20 轮轮换顺序，**300/300 通过**（199.982s，0 跳过/失败/错误，退出 0）。逐轮结果及耗时在 `stability-results.json` / `stability.log`；219 个文件每轮哈希一致。随后才启动本轮首次全量。
- 负向现场清理：归档中 14 个真实监管任务的所有登记 PID 均已不存在，清理回执为 complete、原始输出长度/SHA256 和身份字段均匹配（`negative-scenes-cleanup.json`）。归档保留原 folder 身份，不能当作复制目录上的可恢复回执；直接用生产 read_receipt 读复制路径会正确拒绝 wrong folder，未改元数据绕过该校验。原场景构建结束时已由夹具在原位置验证真实回执。
- 最终自审补充：本轮未提交的“去重加入工作区”初稿忽略了旧版指纹。独立临时脚本在工作区未变化时重提旧候选，实际生成 id 2 并使 id 1 变为历史；反例 **1/1 准确失败**（0.418s，`legacy-replay-red.log/json`，完整现场 `legacy-replay-red-scene/`）。这是本轮初稿的新兼容问题，未归因于 `2bb56f4`。当时首次全量尚未结束；待其按未改动字节完成后，补齐安全的旧指纹重放并重新验证，未将首轮全量作为最终证明。
- 首轮全量：**925 tests，351.927s，OK（skipped=16）**，退出 0，219 个受测文件前后未变（`full-unittest.log`、`validated-files-after-first-full.json`）；由于随后补上旧指纹兼容，这一轮不是最终代码的全量证明，原日志和跳过清单保留。
- 兼容补齐：新候选仍按工作区指纹去重；找不到时只对证据仍有效的旧指纹返回原候选，不改原记录、不补写工作区。已有回归加强为“原工作区重提返回同一候选、维护后即使恢复旧 Git 引用也须新登记”；保持全部原断言，之后重新定向、敏感性、稳定性和全量。
- 最终定向：补齐旧指纹重放后，同一 12 模块命令 **140/140 通过**（50.665s，0 跳过/失败/错误，退出 0，`targeted-final.log`）；旧候选原工作区重放不新增记录、不补写输入，换工作区后生成新候选。5 组故障注入再次 **5/5 命中预期断言**（`mutations-final.log`、`mutation-final-results.json`），完整现场另存 `mutation-final-scenes/`，没有覆盖之前日志。
- 最终稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<本轮证据目录>:tests:. python3 <本轮证据目录>/stability-final.py`，20 轮轮换顺序，**300/300 通过**（168.644s，0 跳过/失败/错误，退出 0）。包含加强后的旧指纹重放/更换工作区用例；219 个文件每轮及结束哈希一致（`stability-final.log` / `stability-final-results.json`）。再核对所有负向归档共 18 个监管任务，登记 PID 均不存在，原始身份/输出一致、清理 complete（`negative-scenes-cleanup-final.json`）。随后运行最终全量。
- 最终全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<本轮证据目录>:. python3 -m unittest discover -s tests`，**925 tests，363.250s，OK（skipped=16）**，即 **909 通过、16 跳过、0 失败/错误，退出 0**。逐项核对为 14 项缺可选 MCP SDK、2 项缺 cryptography（`optional-skips-final.json`）；没有联网安装。资源关闭警告原样保留，失败现场捕获未触发，子解释器仅继承离线保护。最终 219 个文件前后 SHA256 一致（`validated-files-before-final-full.json` / `validated-files-after-final-full.json`）。
- 跳过原因核对：汇总脚本首次只按原因文本分类，遇到 `test_sign` 的 `needs both` 而断言失败；读回原测试装饰器并检查环境，确认 ssh-keygen 存在、cryptography 缺失，因此两项签名跳过均由后者造成（`skip-environment.json`）。保留原始跳过身份与原因，不将这个汇总脚本问题当成测试失败或修改跳过条件。
- 最终审查：生产只改 `tmh/platform/candidates.py` 与 `project_library.py`，新增 `tests/test_library_transactions.py`，更新使用说明及本文件。原 83 个测试文件逐字未改；Store 及五个保护/监管文件未改；schema/configure/derive/reference/act/_run/_write_run_inputs 的 AST 与 `2bb56f4` 相同（`invariants-final.json`）。读回完整新测试及最终 diff，文档链接/围栏和 `git diff --check` 通过。
- 收尾：在 `feat/ralph-port` 独立提交，标题 `fix: 修复候选证据绑定与事务读取隔离`；提交号写入本轮外部证据 `validation.json` 并核对提交字节，不 push。原 `ralph-port-preflight-2026-10-19` stash 保留；不访问真实 data/凭据，不更改 Git 配置，不启动日常服务。
- 人工重点审阅：候选登记内工作区/需求/授权复查与输入同事务写入；旧指纹只在证据有效时重放；`run_current` 的读取 SAVEPOINT 及其在外层写事务中的释放语义；缺失历史绑定不得补写、换工作区后即使 Git 引用相同也须重新登记。无新增待确认；P5 人工确认/guard、P6 锁的原审阅重点及 Windows 六项剩余阻塞清单保持，不宣称已完成 Windows 实机验证。
- 日志校验：`review-red.log` 7598 字节 / SHA256 `5f3400ec562d582a6514dc4662306558ab6bf8a72f4e9eb6f19133fd5cb864e2`；`legacy-replay-red.log` 965 字节 / SHA256 `7e73e5081f1a8dcf799df7ebda4b4e63ee4be70995132d4cb196d644402a0f7e`；`targeted-final.log` 25664 字节 / SHA256 `4ff193e6aa5f61c73edf9010f98c862aaad6d8d481a2650960b6eb8a2f103a1f`；`mutations-final.log` 6635 字节 / SHA256 `82ed869d847562fcf0a889ca2c3c1ee8f48f97caa423e0afd207bfebd7a6b5b7`；`stability-final.log` 57438 字节 / SHA256 `77a34d3565026c5c8b82bb0c70d512147ea511acbbefd93fc2ae3fdfdc42595f`；`full-final.log` 23185 字节 / SHA256 `a604236817de8f6df8bb077aa6b14ace3c09a450934b41606e511a834c3842d2`。全部原始失败场景、脚本、首轮/最终日志保留，完整文件清单见 `evidence-manifest.json`，没有压缩或截断原文件。

## 后续：发布 9ba7a3a，候选更新为 0788a52（2026-10-20）

- 状态：doing（SSH 已恢复，正在隔离验证及备份）；用户明确要求“上线吧”，授权本次生产发布及必要接入检查。继续 `feat/ralph-port`，初始源码为 `9ba7a3a41605602dbae07ad1d82d89a73d86bb2e`，最终发布候选为下方 `0788a52`；不开新分支，不 push，不更新本地日常 8791/8793，不读取或打包本地真实 data/。生产数据仅在服务器上做一致性备份、迁移和保全核验。
- 已读本文件、`git log --oneline -10`、生产接入记忆及部署脚本。开工工作区干净，原 stash 保留。
- 目标核对：本仓库脚本使用 `webuddy.bbstack.date` / `webuddy.service` / `/opt/webuddy/app`，现存旧记忆中的 `factory-web.service` 属于另一仓库，不能混用。直连目标域名的 TLS 校验通过、IP 为 `43.153.76.85`、首页 303 跳转 `/login`；不把可达性视为当前版本已上线。
- 待接入：本机 `/Users/auntlee/.codex/memories/webuddy-production-access.md` 明确记录临时部署授权于 2026-09-30 18:23:35 CST 到期，本项目的历史部署脚本也沿用该凭据名称。已异步询问有效 SSH 配置或本机凭据路径；不索取私钥内容，不使用过期/撤销凭据，不借用其他用途账号绕过。此项是缺少有效接入信息，用户无需重复授权上线。
- 发布准备目录：`/Users/auntlee/Desktop/workspace/运维智能体/部署包/ralph-9ba7a3a-20261020/`。固定 Git blob 导出 164 个运行时文件，生成未压缩 `webuddy-9ba7a3a.tar`（3,112,960 字节，SHA256 `e2d125acc9d3aa407dfb930a077e0f72c404e2a739d04dcd534fe94ee8e815b2`）；含完整运行依赖的模板、技能、知识库及 `install()` 所需 `docs/agent-commands.md`，无生产数据、私钥、证书或环境文件。
- `python3 prepare.py` 成功；实际打开 tar、解包并逐项读回，287 个运行时及测试支持文件的字节和模式与提交一致，清单在 `package-verification.json`。发布/回滚步骤及接入阻塞写入外部 `上线记录.md`，具体服务器布局和备份锚点仍待登录后实测。
- 正在从实际发布包解包的代码运行完整回归：`NO_PROXY='*' no_proxy='*' PYTHONPATH='../diagnostics:.' python3 -m unittest discover -s tests`。完整输出保存 `full-unittest.log`；仅合成数据、临时仓库与回环连接，原断言、时钟及测试文件不改。
- 首轮导出回归：**925 tests / 907 通过 / 2 失败 / 16 可选依赖跳过，336.439s，退出 1**，原包、导出树及完整日志原样保留。失败之一为 `examples/legacy-dotnet-erp/Erp.Core/Data/ErpContext.cs` 在本地存在但被大小写不敏感的 `data/` 忽略规则排除、从未纳入提交，干净导出缺少 `Customer` 实体；另一项是发布清单遗漏 `docs/dead-ends.md` 引用的四份验证文档。这是对发布物的实际验证发现，不能用原工作树通过结果覆盖。
- 修复：只为上述合成 `.cs` 文件增加窄范围忽略例外并将原字节纳入提交，其他 Data 文件及真实 data/ 继续忽略；导出清单加入四份既有验证文档。未改产品代码、原测试、断言或超时。修正后独立导出副本运行 `test_tmh.DotnetTest test_tmh.InstallTest`，**5/5 通过，0.404s，退出 0**（`export-fix-targeted.log`）。失败原因和补齐文件哈希在 `export-failure-analysis.json`。
- 包启动验证：从实际解包目录在系统分配的回环端口启动真实 `serve()`，合成账号/令牌、空数据库；登录页 200、匿名项目 API 401、带令牌项目/API 元信息/主页面 200，共五项检查通过。共享令牌未获得人工身份；服务退出码 0、临时数据清理，日志在 `smoke-server.log` / `smoke-result.json`。未启动日常端口或连接模型。
- 接入续期：用户已明确回复“这个锁已经手动延期了，你也可以更新一下我们的信息”，已更新本机接入记忆，注明确切新到期时间未提供。两处已有本机凭据均为 0600、指纹与登记公钥一致；未输出私钥。
- 实测 SSH：严格主机检查通过并显式提交登记的部署公钥，但 `ubuntu@43.153.76.85:22` 返回 `Permission denied (publickey)`、退出 255；详细诊断已保存 `ssh-check.stderr`。尚未执行远端命令，不能断言拒绝仍因过期；已异步请用户核对服务端授权或提供当前接入信息，不重复询问上线许可。
- 发布候选更新为 `0788a52e1b517b33fbe9b593be200d1c060a1cc4`（`fix: 纳入被忽略的 .NET 回归示例`）。`tmh/templates/skills/agents/kb/tests` 相对 `9ba7a3a` 逐字未改。新发布目录 `../部署包/ralph-0788a52-20261020/`，168 个运行时文件、292 个运行时及验证文件，实际读回字节/模式一致；包为 3,174,400 字节，SHA256 `758c2d075cbfdcd50a4c96649bf373284f4f14d0a8305d26064b6c53e0a1f20c`。
- 新包五项实际 HTTP 启动检查再次通过，退出码 0、合成数据清理。正在该包实际解包代码的 `test-source/` 再运行完整 `python3 -m unittest discover -s tests`，保留旧包及首轮失败日志，不用旧结果替代本轮结论。
- 最终包全量：**925 tests，352.660s，OK（skipped=16）**，即 **909 通过、16 跳过、0 失败/错误，退出 0**；14 项缺可选 MCP SDK、2 项缺 cryptography。`full-unittest.log` SHA256 `574661a9239c5db43e9a7b08121390c8f27ec51985d878fde74a163970fc1c63`，完整跳过身份/原因见 `diagnostics/optional-skips.json`；292 个文件执行前后字节/模式一致，结果绑定 `0788a52` 与发布包的 `validation.json`。失败捕获未触发，原资源关闭警告完整保留。
- 本轮实际结果：发布准备与验证完成；生产 SSH 仍拒绝已登记公钥，尚未上传、执行远端命令、备份/迁移生产数据库或重启服务，因此**未上线**。待服务器恢复对应公钥权限或提供新的有效接入信息；已有上线授权继续有效，不再重复询问部署许可。恢复后先按新发布目录的 `上线记录.md` 核对远端实际布局与数据，再进行切换与线上验收。
- 收尾仅追加本进度记录并单独提交，不改变受测发布源码。续期及本机实测拒绝均已写入 owner-only 接入记忆（0600）。原 stash、首轮失败包、全量日志、SSH 诊断和最终包均保留，不 push。
- 恢复推进：用户再次回复“已经更新了授权”；严格主机校验、显式已登记公钥登录成功，免密 sudo 可用。先读本文件与最近 10 条提交，工作区干净、HEAD `654c73b`，不重做已完成的本地发布包全量验证。接入记忆已更新；新到期时间未知，不假定永久授权。
- 服务器只读预检：`webuddy.service` active/running，`/opt/webuddy/app` 为普通目录、无 `.git`，端口 8790，外部配置 `/etc/webuddy.env`；Python 3.12.3、Git 2.43.0。应用 6.1M、数据 57M、磁盘空闲约 34GB。SQLite quick_check=ok；3 个项目、49 张工单、254 次运行（done 243 / failed 11），无 queued/running；自动流转 `on=false`，无调查状态、无服务子进程。`factory-web.service` inactive，Caddy active，均不属于本次变更。证据续存 `../部署包/ralph-0788a52-20261020/production-resume/`，此前拒绝记录保持。
- 隔离发布目录：`/opt/webuddy/releases/0788a52-20261020`。通过 SSH 上传原始发布包及只含固定提交源码/测试和离线诊断的验证包；首次未压缩传输较慢，停止本任务上传后用 SSH 无损传输压缩重传，服务器逐包 SHA256 和 168 个运行文件 / 292 个验证文件的字节、模式全部一致。未压缩 tar 原文件不变，旧服务仍运行。
- 迁移演练：SQLite backup API 在服务器创建 0700 隔离目录下的一致性副本，执行真实 Store、复检及候选 schema，然后再次执行。`integrity_check=ok`；原 9 张表全部原列与原行哈希一致，第二次执行后所有表一致；13 张新表仅项目档案和来源各 3 行，其他均空，未补写历史输入或人工决定。副本及明细留在服务器 `migration-rehearsal/`，本地仅保存计数、模式和哈希；没有将真实业务数据下载进仓库。
- Linux 验证：正在服务器隔离的 `verification/test-source/` 执行完整 `python3 -m unittest discover -s tests`；独立合成数据，Python 子进程只允许回环连接，原测试、断言、超时均保持。验证及真实服务启动检查均通过后才切换；服务器生产目录尚未迁移或停服。
- Linux 首轮完整结果：**925 tests / 902 通过 / 9 errors / 14 跳过，415.194s，远端退出 1**。9 项均在三个测试模块调用 `Store.db.iterdump()` 时抛出 `no such table: name`，尚未运行到对应的数据库不变断言。Python 3.12 的标准库导出器沿用 Store 的字典 row_factory，把 `name/type/sql` 键误当作行值；本机 Python 3.14 已在导出器游标上设 `row_factory=None`，故原本通过。完整失败日志 `production-resume/linux-full-first.log`，SHA256 `defbbc3f2142c8f25aa1b129c8388d52aa3f454ca0caa573afba24c83bf3f8ac`，原 292 个验证文件前后未变。
- 此轮远端测试已退出并写入结果文件，但原 SSH 响应连接停滞；通过新的严格校验连接读回结果、确认测试进程不存在后，仅关闭该本机旧 SSH 客户端。后续连接增加会话级保活参数，不改 SSH/Git 配置；没有把传输失败混作测试成功。
- 兼容修复：新增 `tests/sqlite_snapshot.py`，持有 Store 锁把整个已提交数据库备份到独立内存连接，再用默认行格式完整导出；不修改活连接的 row_factory，不删表/字段/记录。遇到未提交事务立即报错，不隐式提交或忽略变化。三个原测试模块仅替换快照取法，原相等性/证据/人工确认断言、超时及产品代码保持。新增两个测试验证文本/二进制/NULL、触发器/视图/索引/序列完整保留、数据或结构变化能被发现，以及未提交写入不会被隐藏。
- 定向命令：`python3 -m unittest -v tests.test_sqlite_snapshot tests.test_intake_recovery_api tests.test_preview_health_independent tests.test_python_pathmap_api`；同样的离线保护下，本机 Python 3.14 **25/25，11.581s，退出 0**，服务器 Python 3.12 **25/25，17.760s，退出 0**。服务器使用独立 `verification-fix/`，原失败树和日志完整保留；定向日志及修复五文件 SHA256 在 `production-resume/`。准备单独提交 `test: 兼容 Python 3.12 的数据库快照断言`，随后从该提交重新导出并在两端执行完整回归；当前仍未切换生产服务。
- 启动行为复核：旧版和新版人工分支扫描的 heartbeat 完全相同，settings 只增加提醒天数，原启动默认值不变；三个既有项目当前没有 `wb/*` 引用，没有未验收的手工认领记录，调查配置为空。首个检查错误地要求整个 settings AST 完全相同，失败后保留原记录，再按实际差异做精确核对；没有改产品行为或放宽基线测试。
