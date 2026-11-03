# Ralph port 执行进度

本文件是 AI 开工时读取的接续记忆：先读本文件和最近 10 条提交，需要更早的细节再查归档。新记录追加在文件末尾。

## 长期有效的约定与边界

以下内容从历次记录中整理，原文和上下文见归档与 AGENTS.md；如与原文冲突，以原文为准。

- 开工：先看 `git status`（应干净），读本文件与 `git log --oneline -10`；涉及生产时再读本机生产接入记忆（路径见 AGENTS.md）。
- Git：普通快进推送，不强推、不改 Git 配置；验证失败不发布。
- 仅文档/记录的提交：只提交推送，并只读核对线上运行文件与最新提交一致，不为记录重启服务。
- 人工边界：Agent 不代人登录、复核、验收、采用知识或关单；不放宽 guard、证据与提交的绑定、既有状态迁移，不削弱测试断言。
- 数据与机密：不提交 `data/`、密钥、证书、令牌、业务数据库与外部配置；凭据值不输出、不复制导出。
- 证据：结论区分实测、推断与未验证；失败与勘误原样保留，追加说明而不改写原件。大体量实验证据包放在仓库外的 `分析/RSI协调/...` 目录，这里只记 SHA 与入口。
- RSI 实验（2026-10-26 状态）：冻结的无工具/单响应实验组合已停止，原 b2a6 真实根永久停止、403 记录保留；这不扩大为“普通协作不能用工具”。重新开始需要新的明确授权和前瞻计划。详见 [2026-10-26 归档](progress-archive/2026-10-26-rsi.md)。
- 产品范围：Coding 独立于办公 WorkBuddy，不要求同步（见 [STATUS.md](STATUS.md)）。

## 归档

| 文件 | 内容 |
|---|---|
| [progress-archive/2026-10-26-rsi.md](progress-archive/2026-10-26-rsi.md) | 2026-10-26 RSI、官方 Codex/Claude 客户端实验与勘误 |
| [progress-archive/2026-10-25.md](progress-archive/2026-10-25.md) | 2026-10-25 登记输入、隔离执行、多人试点、Token 登记等 |
| [progress-archive/2026-10-22-24.md](progress-archive/2026-10-22-24.md) | 2026-10-22 至 10-24 知识评审、租户权限、组织工作台、RSI-1/2 |
| [progress-archive/2026-10-19-20-ralph.md](progress-archive/2026-10-19-20-ralph.md) | 历史 Ralph P1–P6、复审、SI-015 与 0.4.0 发布前记录 |

## 最近记录

## 2026-10-26：独立 Codex 项目配置与 API 分发

- 人类本轮要求保留 API 接入和分发，为只接受官方 Codex 的网关建立独立配置。继续当前 `iteration/context-pack-v2`，起点 `9ae7ded6af9e7768561f410264185fd4f8d82b2d`；读取项目约定、接入记忆及最近十条提交。未恢复旧失败实验、未改变人工采用或关单规则。
- 实现：增加官方 Codex alias/profile 与完整 stdin 输入、JSON 完成答复/用量读取；新增项目路由、allowlist、直接模型 API 开关；API/CLI/MCP 接单和普通项目配置保留。页面的工单、交付、知识分析和助手使用同一项目路由。缺失执行器或非法配置明确停止，旧全局偏好不会自动改变通道。详见 [使用说明](../codex-project-route.md)。
- 独立审查发现并关闭三项 P2：普通日志误判模型成功；不可用的项目执行器被页面自动替换；助手旧全局偏好绕过项目默认。完成判定改为退出成功、完成事件、非空模型答复同时存在。缺失配置保留可见；交付默认停止，本项目明确改选仍允许。原测试断言和时限未削弱。
- 真实连接：服务器原安装官方 Codex 0.162.1，通过新的 owner-only `webuddy-cloudwave.config.toml` 继承现有 provider，一次受监督启动成功，3.486708 秒，得到正确合成答复。原基础配置字节未变；无真实业务内容、生产工单或服务变更。客户端报告输入 13,142 / 输出 13，缓存输入已包含在输入内；实际底层模型身份、HTTP 次数及账单未知，不据此宣称 RSI 成功。不再重复调用。
- 模拟完整流程：真实本地 HTTP 建单和启动 → 专用 alias → 真实隔离 Git 工作树改码 → 实际项目检查 → 保留差异、验证及进程回执。执行器是合成本地进程；主工作区及 HEAD 保持，没有人类采纳决定。
- 独立复核：42 项定向测试全部通过（4.752 秒）；另外 5 个真实合成进程完成判定案例、实际助手渲染及交付事件绑定通过。浏览器打开实际选择函数的独立验证页，确认专用/普通/缺失配置三种选择状态，保存原始截图；不是生产页面验收。
- 原始回归失败保留：首轮使用了不存在的 `test_ui_delivery` 模块（已纠正为 `test_delivery_design`），两项原生命周期用例失败；不改原测试的定向重跑 11 项通过。第二轮 258 项，257 通过，原手工构建 0.6 秒时限用例在模型/构建进程登记前超时，访问空 attempts 报错；相同模块和最终 UI 共 22 项原断言/时限重跑通过（10.494 秒）。最终整套回归和精确发布结果继续追加，不把失败记录覆盖或归因于已证明的环境问题。
- 证据：仓库外 `分析/implementation/20261026-codex-route/` 保存完整日志、真实连接原件、独立审查报告与文件哈希。未改 acceptance、guard、process_control、supervised_process、filelock、状态迁移或租户权限；自动流转保持关闭。
- 当前边界：`learning_runs` 的独立知识实验仍只适配原 Claude 隔离执行器。本批完成普通任务路由，并未接通此实验的 Codex 等价隔离。真实跨任务收益、LYB/LLA 本人交接/采用/验收、长期试点及整体 80% 尚未证明；不会因连接和测试通过加分。
- 发布准备：本机公开指纹、0600、严格 known_hosts SSH 与 sudo 新鲜核验通过；现役仍为 `c08b6ae...`，无 queued/running，`agents.json` 与 `agent-routes.json` 不存在，自动流转关闭。本批将按既有自动发布授权进行精确提交、Linux 兼容与数据副本检查后再切换；切换结果另记。
- 最终本机定向整套：16 个相关模块 **259 tests / 259 通过 / 0 失败错误 / 0 跳过，176.590 秒，退出 0**（`integration-sealed.log`）。覆盖 API、租户隔离、工具接入、运行/直接调用/手工构建生命周期、知识会话、需求理解和 UI。原 ResourceWarning 保留，不宣称全部测试无资源警告；没有重复完整 2,510 项旧基线全量。

- 候选 `975d7660553475a2f1e86f2b79d2db7310fd68fc` 已普通推送，未激活。精确发布包 Linux 259 项通过（221.229 秒），数据副本 Store/Registry 两次初始化保留原 70 业务表和 11 控制表的模式及记录；Mac 精确包 259 项有 1 项原总预算测试失败（登记到 1 个进程，原断言要求 2），188.922 秒。完整日志/失败现场保留，未改断言、时限，不把 Mac 此轮称通过。
- 上线前外部独立复核发现 `ROUTE-RETRY-REVOKE-01`（P2）：开启忙时重试后，在等待间撤销原执行器，第二次进程仍启动。示例的 retry_busy=false 不触发，但公共配置允许开启，因此暂停旧候选激活。原真实合成反例 2 次启动（预期 1），原件保留。
- 最小修复：在 invoke 内所有 spawn 紧邻 _spawn 前重新 resolve，兼顾忙时重试与恢复失败后的全新调用。新增 3 项回归，撤权/坏 JSON/alias 删除后只保留第一次实际进程与完整回执；未变路由允许第二次成功，恢复失败后撤权也阻止 fallback。原重试、取消及上下文检查保持。
- 修复验证：主任务复制原反例逐字执行通过，独立复审再次执行同字节反例通过；profiles 13/13（独立4.000秒）。相关 profiles/route/learning_sessions/direct-invocation 四模块 **63/63，17.111秒**；`git diff --check` 通过。新提交与双端精确包验证另行绑定，旧候选证据不冒充新候选通过。

- 2026-10-26 15:41:36 CST：新候选 `bdcd5f9` 已上线，221 运行文件一致；精确 Mac/Linux 均 **262/262、0 skip**，耗时175.115/223.499秒。完整备份读回、立即/60秒延迟12项HTTP、后续10项旧共享token负控通过。70业务/11控制表原schema和行保持，其他项目/权限/自动流转保持；详情 [上线记录](../../audit/production-deployment-2026-10-26-codex-route.md)。
- 实际启用 `cloudwave-codex` 和 PPTAUTO 路由，原基础模型配置保留。只读后验脚本首版误写组编号1000，现场ubuntu实际为1000:1001；保留首版失败后按账号实值复核通过，未更改生产权限。未新增模型调用、用户会话或人工决定。独立学习实验Codex适配、真实跨任务收益和多人长期试点仍未完成，整体80%未认定。

## 2026-10-28：项目本人复核与普通 AI 执行（进行中，未发布）

- 状态：doing。当前隔离工作区 `tob-maintenance-harness-project-execution-review`，分支 `feat/project-execution-review`，基线为生产实际版本 `1245231d4eda1def019c289ad79159533b493b27`。开工已读 git status、本进度与最近 10 个提交；原 `iteration/context-pack-v2`/`ce94dff` 分支保持，未恢复已停止的 RSI。当前修改尚未提交、推送或部署，不能当成功能交付。
- 范围：项目个人独立复核/正式验收，以及普通项目 AI 执行所需隔离。未提升任何真实用户为平台 owner/租户管理员，未更改 LLA/LYB 已有项目授权，未代登录、代复核、代验收或关单。原 execution capability、宿主进程 audit gate、require_workspace、guard/acceptance/锁/状态迁移保持。
- 个人复核配套：`server.py`/`ui.py` 对受管非 owner 要求当前指定独立复核人；重分配不能抹掉实现运行的原作者，识别服务端保留的 `agent:member:<user>`，不猜测旧 `agent:<alias>`。证据来源缺失或属于另一工单时拒绝。已有证据按钮增加实际限制说明；该按钮原已存在，这一部分本身不代表新增完整团队能力。
- 正式团队复核：`project_git.py` 在指定项目/当前授权下只允许有限 Git 元数据命令，经 rootless 只读容器读取；`agents.py`、`candidates.py`、`release.py` 只在团队读取 scope 内使用这一通路，不开放任意宿主进程。`team.py`/`tenant_policy.py`/`ui_team.py` 仅对已配置项目的 review、candidate_assess、business_accept 提供相应入口；合并、验证、预览和旧 `/accept` 保持原执行限制。补齐团队逐项复核、人工决定、业务验收和列表对保留成员作者的自签拒绝。
- 容器底层：`project_container.py` 直接使用本账户 rootless Docker Unix API；固定镜像 ID、固定入口 WATCH、最小环境、无网络、只读根文件系统、drop ALL caps、no-new-privileges、内存/进程数/CPU 限额。容器不获得 daemon socket 或宿主环境。所有权连接 EOF 与内部 deadline 结束 PID 1；取消定向删除并确认容器不存在。此模块目前只接入可信固定 Git 命令，**尚未接入可用的 AI 开发 API**；不能把只读 Git 的整项目挂载当成可运行任意项目代码的安全证明。
- 服务器准备：原生官方 Codex 0.162.1 及其必需的 codex-code-mode-host 单独复制进 rootless 镜像，未复制宿主 HOME、凭据或 RSI 文件。基础 node 镜像固定 digest；最终镜像 ID `sha256:957c6a7ef050650cf0587effb7c9bc049a2f1cb570ff8033de968d4d968df4f0`。仅新增镜像和合成验证目录，未更改生产 app/config/服务/账号/业务库。
- 原始失败保留：HTTP 夹具先缺 CSRF、后缺 GET context token，仅修夹具后真实个人会话 6/6 通过；只读容器初次因不存在的 `.tmh` 嵌套挂载启动失败，改为仅遮蔽已有元数据目录、拒绝符号链接后真实读取通过；候选 ref 初稿误写为 refs/tmh，独立审查纠正为精确 `refs/webuddy/candidates/<64hex>`，已用实际候选 submit→view 核对。固定显式 Entrypoint 后再次验证 EOF 和超时，不依赖镜像原 ENTRYPOINT。
- 已拒绝的模型代理方案：共享 Unix socket/回环 relay 不能证明请求一定来自官方 Codex，项目脚本可伪造公开 marker/客户端头。因此整个未发布的 `project_model_bridge.py` 与其原型专用测试已撤出产品候选；原代码、测试和失败日志完整保留在外部证据目录 `rejected-shared-socket-bridge/`，不是删除基线断言来获得通过。该原型还出现过早拒绝请求导致 BrokenPipe 的时序问题，原 84 项失败日志保留。代理的并发/读超时与目录中凭据/Unix socket 问题也未因撤出而被认定解决。
- 两次必要的有界真实接入验证均失败且现场保留：首轮缺官方配套 helper，网关报“没有带上 Key”；补 helper 并试验把现有 raw actor header 映射为 bearer 后，网关报“Key 无效”。没有返回模型结果，没有修改合成代码，两次容器均确认回收。已撤回这个未经证实的凭据格式映射；不能据此断言原官方客户端账号凭据失效。不继续猜测 Key/客户端认证，不更换供应商，不重启 RSI。
- 当前定向：`python3 -m unittest -v tests.test_project_container tests.test_project_review_permissions tests.test_team_workspace tests.test_tenant_policy tests.test_external_candidates_independent`，**82/82，20.660 秒，0 skip/fail/error**。未改已有测试。主 UI 与团队 UI 的 `node --check` 均通过；`git diff --check` 通过。没有把合成技术证据用作真实业务验收，也未将原型已撤出的测试计作最终功能证明。
- Linux 实测：普通隔离、取消、超时、脱离会话的遗留子进程四场景通过并定向回收；修正固定入口后，父进程 SIGKILL 后所有权 EOF 使容器以 125 退出，观察耗时 0.072 秒，随后确认删除；2 秒 deadline 返回 124 且回收完整。真实临时 Git 查询在宿主 audit gate 已拒绝进程的条件下通过，仓库外假配置不可读、写命令与撤权读取被拒绝。实际团队 candidate submit→view 已通过，精确绑定真实候选 ref/commit，缺构建、预览、逐项验收仍明确阻断。
- 未完成与待确认：完整正式签收仍依赖真实构建与固定版本预览，目前受管租户的启动入口仍拒绝；不能把读取候选成功算签收全流程通过。AI 执行还需可信官方客户端与不可信项目工具之间可核验的身份/通道隔离，并处理项目内凭据/Unix socket、配额、撤权和清理。当前不向用户索要私钥/Key，不扩大执行权限，不发布半成品；协调任务继续决定最小可用实现。未跑全量；工作区有明确的未提交工作副本，未宣称完成或干净。
- 原始证据与状态：`/Users/auntlee/Desktop/workspace/运维智能体/分析/implementation/20261028-project-execution-review/`，包含每轮 stdout/stderr、公开合成验证脚本、失败原件与 `status.json`。不要用旧 75/84 项结果替代当前 82 项，也不要把早期不完整镜像/入口的结果当最终镜像证据。

- 2026-10-28 补充：无 Git 材料任务回归发现 `repo` 错放在 `_assign` 而 `item` 未定义；已移至 `item` 按当前项目/用户查询，移除分配中的无用检查。`tests.test_project_container tests.test_project_review_permissions` **14/14，1.724 秒，OK**；未削弱断言。未提交、未发布，普通 AI 执行仍未完成。

- 2026-10-28 执行底座草稿：新增 `project_snapshot.py`、`project_mcp.py`、`project_client.py` 及对应测试；固定提交导出受筛查的独立源码副本、项目工具重查授权、客户端与工具容器分离，并在 MCP 初始化时原位清空临时认证副本。适配普通 `data/`、`.env.example` 和业务 token 文件名；凭据路径和高置信凭据内容阻断，不静默删除文件。检测不能证明不存在所有秘密。首次 25 项有 1 项 macOS /var 临时路径符号链接导致夹具失败，保留日志并解析真实路径；修复后 26/26 通过。新增控制器的合成 Unix socket 接线测试通过，仅使用模拟容器；尚未接入 Runner、正式候选、构建或预览，也未做真实模型容器调用。无权限扩张、提交、推送或部署。

- 2026-10-28 真实客户端集成验证：服务器临时合成 Git 项目，按当前 `project_snapshot/project_client/project_mcp` 源码导出固定提交、启动官方 Codex 和隔离项目工具；原官方网关成功，Codex 两次调用项目工具，将减法改为加法并执行断言，获得完成事件和非空答复。客户端及两次项目容器均退出 0、回收确认，临时认证副本原位清空；耗时 8.728 秒。仅一次受控模型调用，未访问真实项目或以 LLA/LYB 登录；原始输出留服务器私有临时目录，本地仅保存摘要。尚未接入工单 Runner、固定候选、构建/预览或正式验收，不得据此宣布成员功能完成。

- 2026-10-28 安全限制与项目适配：路径筛查不再把普通 `data`、示例环境文件或业务 token 词视为秘密；高置信凭据内容和密钥/证书文件仍阻断，错误现在保留路径及原因。普通文件保持完整。根据只读元数据，RW 的 `realworld` 是未固定检出的子模块，本版明确阻断并报路径，不能宣称源码完整；JB 是否可完整筛查仍待实际验证。新增测试共 28/28，通过；`git diff --check` 通过。关键未解决：当前项目工具容器对临时工作区使用可写宿主绑定，定时扫描不是硬磁盘配额，恶意进程可能快速耗尽磁盘；在实现并验证硬配额前不得启用或发布。现有成功模型调用只使用合成项目，不构成磁盘隔离证明。

- 2026-10-28 硬配额进展：服务器 rootless Docker 实测支持固定大小 tmpfs 卷。新增 `project_volume.py`，用所有权连接固定卷，项目工具只挂载该卷、不挂可写宿主目录；原代码副本作为只读输入，执行结果另存并保留原副本。服务器合成 16 MiB 验证两次调用共享改动、实际 ENOSPC、空目录与原副本保留、工具/固定容器和卷均回收；首次探针因 Python 缓冲关闭时 ENOSPC 未清理填充文件，原失败保留，改探针用无缓冲写入后通过。
- 含真实官方网关的第二次合成验证：Codex 进入 512 MiB 卷调用三次项目工具并测试；一次 `python` 不存在退出 127，模型随后改用 python3 测试通过。客户端退出 0，三工具容器与临时卷回收。首个摘要按源码空格做全字串比较误报 false，保留原件；独立 AST 比较确认加法实现且实际断言通过。此验证不是本人项目的生产功能。
- JB 只读首轮在 `jeecgboot-vue3/.env` 阻断，耗时 6.419 秒，未导出源码离开服务器；改成对环境文件的敏感字段与高置信凭据内容筛查，不仅凭文件名拒绝，重新核对中。固定版本导出增加对工作区未提交源码的显式拒绝，平台 `.tmh` 保留且不作为用户代码覆盖；知识需通过任务上下文另行提供并验证。RW 子模块固定源码缺失将明确阻断。未部署或扩大成员权限。

- JB 真实固定版本只读复验通过：提交 `84f46c214260780c02d6af085a1b2e44af224405`，3,144 文件、79,804,645 字节，13.672 秒，隔离容器回收确认；源码只在服务器的临时目录处理，未送模型、未导出到本机，临时目录已清理。首轮 `.env` 阻断原记录保留，修改环境字段筛查后无需跳过文件即通过。筛查只能发现已定义的凭据模式，不证明不存在所有秘密。该结果不是 LLA/LYB 真实工单执行。

- 所有权异常实测：SIGKILL 工作区持有进程后，原版 anchor 退出 125，但停止的容器及卷元数据仍留存；失败现场记录后由探针定向清理。新增独立、无网络的固定清理容器，只挂载 rootless Docker socket，不挂项目或供应商配置；通过随机标签核对后仅回收属于该任务的 anchor 和卷，随后自身自动删除。复测父进程 -9 后 anchor、卷、清理容器均自动删除，无需探针补救；普通 ENOSPC/跨调用保留/回收场景重跑通过。清理容器持有 rootless Docker socket，应由独立审查确认信任边界和启动竞争，不能等同于无特权。生产权限尚未开放。

- 固定候选产物：新增 `project_artifact.py`，可信只读容器使用临时 Git 对象库生成带固定父提交的提交、完整二进制补丁和 bundle；来源仓库只读，摘要读回核对。Mac 真实临时 Git 测试通过；Linux 实际隔离容器合成复测通过，另一个临时仓库取回 bundle 后确认提交、父提交、文本与二进制逐字节正确，原 HEAD/工作区不变，容器回收确认。这只是产物，尚未登记现有正式候选，也没有构建、预览或人工验收。

- 合成整链：新增未发布的 `project_job.py`，按同一时限串联固定源码、客户端/临时卷和固定候选产物，保存完整原始工具输出与回执。服务器一次受控官方模型调用完成合成 Git 项目修改，五次工具调用退出码 127、1、0、0、0，模型修正后完成；另一个临时仓库取回 bundle，固定提交、父提交及 AST 实现正确，来源 HEAD/内容不变，客户端、全部工具容器、卷及产物容器回收确认，耗时 17.900 秒。该结果仍为 proposal，不是已登记候选、技术检查、预览或人工验收；无真实成员会话或业务数据。

- 个人运行器接线：仅在现有受管项目隔离配置和有效个人授权下进入新路径；请求入口仍关闭。登记前固定工单需求、引用及来源提交，权限撤销后即使重授旧运行也不能继续；无关项目或同等权限重授不误中断。数据库短事务确保同一工单并发只登记一个运行，个人运行标记与批次随机值绑定并在事务内写入；重启不自动恢复旧授权，个人执行不走旧宿主工作树重试。平台 .tmh 未挂入项目容器，实际任务提示包含所选知识，Git 来源通过独立只读容器核对。
- 真实合成 Runner 验证：服务器独立临时租户、个人 alice、合成仓库及真实官方模型；宿主 subprocess 网关按原策略拒绝，个人身份正确，`.tmh` 中的知识规则实际出现在提示词，知识来源版本与固定提交一致，原知识和源代码未改。结果 bundle 在另一个合成仓库取回，固定提交、父提交与 AST 均正确；客户端、项目工具、临时卷和产物容器已回收。工具退出码 127、0、128、0、0，失败后模型修正。初次汇总脚本误读 runs 根目录的 prompt 路径，在运行实际成功后报 FileNotFoundError；失败记录保留，从真实 `member-job/prompt.md` 独立读回验证，无重复模型调用。当前只形成 proposal，正式候选未登记，也未执行独立构建、预览、人工复核或业务验收。


## 2026-10-28：LYB / LLA 试用入口的轻量修复

- 本轮只处理真实试用路径：非管理员首次打开团队任务用 `*` 请求导致 403；成员接手后错误展示下载开工包和本机开发。没有扩大后端权限或恢复 RSI。
- 团队页先读取已授权项目，自动选中当前或第一个项目，再读取单项目任务；没有项目时明确说明。管理员仍可看所有项目。成员接手后指向站内 Codex 修改代码，保留运行中、失败和待审阅状态；有完整执行权限的外部开发流程保持。
- 处理工单关联知识、团队详情等待返回时切页造成的旧页面写入。针对测试覆盖项目切换、无授权项目、管理员兼容、成员操作引导、异步切页。初次直接 unittest 调用缺 tests 导入路径，补齐原测试惯用路径后通过；一次新 UI 测试读假 DOM 的 innerHTML，改读实际文字后通过，未改产品判断或移除断言。
- 发布复用现有纯代码助手，项目配置及镜像保持；最终提交和两端精确包结果以发布记录为准。实际业务复核和验收由成员本人完成。

- 已发布：`be790b6c13dc31007a1c6c68d64248608b39a70c` 已快进推送 GitHub `feat/jb-partial-diagnostic` 并切换上线。Mac / Linux 同一精确包各 88 项通过、零跳过；235 运行文件保持固定清单。兼容副本和上线后原 schema / 行保持，立即及 60 秒 HTTP 健康通过，原配置与执行镜像保持。回滚锚点 `/opt/webuddy/backups/pre-be790b6c13dc-activation-20261028`，只允许切换程序，不用旧 DB 覆盖新写入。发布回执 `分析/implementation/20261028-member-permissions-release/release-evidence-be790b6/activation.json`，SHA-256 `ac6758e8f699358f3b8a0a1b01859a232a6c2017f5b43de724d2c2240ce69e7a`。本轮未调用模型、未代人验收；浏览器原路径复验由指挥任务继续。


## 2026-10-28：公司官网自动构建与预览已上线

- 运行版本 `dc7cd596de3be3e64b05632d868ebd19408e627b`；仅 CWWEB 启用固定候选自动测试/构建及隔离静态预览，原人工复核、合并、业务验收保留。没有恢复 RSI。
- Mac / Linux 精确包各 126 项通过；真实 CWWEB 测试与预览构建、独立数据完整候选演练和浏览器导航/图片检查通过。上线立即/60秒健康、原数据和配置保持通过，LYB/LLA真实账号只读入口通过。
- 本批无模型调用、无代签生产验收；实际试用留给本人。详情见 [发布和试用说明](../../audit/production-deployment-2026-10-28-company-preview.md)。记录本身只提交推送，不重复重启。

## 2026-10-29：仓库整理与 CI 回绿（PR 待合并，未发布）

- 分支 `devin/1761712000-repo-tidy` → `feat/jb-partial-diagnostic`（PR #1）。从 `main` 复制汇报材料（两条历史不相连，未合并历史），恢复 7 个 GBK 乱码文件名；本文件按阶段原样拆入 `progress-archive/`，内容未删；README 重写为平台 + CLI。`evidence/` 被 verification 文档、`tmh/resources.py` 和 `test_python_flows` 引用，保持原位。
- 修复 `d243809` 引入的 `req=None` 个人复核提示崩溃（无身份时判不允许，未放宽校验）；`tomllib` 改为可选导入，CLI 仍支持 3.8+，项目 Codex 执行需 3.11+。
- 测试：两个过时用例按 `4e8b92c`、`dc7cd59` 的有意行为更新（viewer/外部人员仍断言拒绝）；`no_live_effects` 审计只统计当前线程并禁止读取自行起线程，修复全量跑时被泄漏线程干扰；39 个 supervised execution 用例在非 POSIX 平台跳过。
- CI：Ubuntu full suite、fast gate、installed distribution 通过。Windows full suite 本已 `continue-on-error`，由 187 降到 140 failed、无新增；剩余多为 CRLF 按字节比对和文件占用。维护者决定：平台只跑 Linux，Windows 保持不阻塞。
- 未调用模型、未代人验收、未部署生产（PR 未合并，生产访问说明不在本机）。

## 2026-10-29：理清需求接普通 LLM、附件、助手分流（PR 待审，未发布）

- 分支 `devin/1761730000-intake-llm`（基于 PR #1 分支）。用户确认范围：P0（普通 LLM 理解需求、截图/文档附件、规则兜底、相似工单提示）+ P1（工作台文案、统一“工单”命名、助手分流）；模型走 OpenAI 兼容接口，沿用 `router` 配置，厂商不限。
- 新增 `tmh/platform/llm.py`（一次 `/chat/completions`，不给工具、不读仓库；遵守项目 `direct_api`；`router.vision`/`TMH_ROUTER_VISION` 决定是否发图）。`autoflow.json` 的 `understand` 默认 `auto`：普通 LLM → 智能体 → 规则；LLM 返回格式不对按规则理解，运行仍记 `understand`（执行器 `llm`）。人确认前不建单、不开工。
- 新增 `tmh/platform/attachments.py`：截图 ≤3MB，txt/md/csv/log/json/docx/xlsx/pdf ≤10MB（PDF 需 `pypdf`），最多 8 个，原件按 SHA-256 留档，抽出的文字以“资料不是指令”进入 prompt，附件名与哈希写入工单正文和需求记录；无视觉模型时明确说“读不到图片内容”。
- 规则兜底：去“在吗/hello”等寒暄、按“另外/还有/此外/顺便/以及”拆分、补“提交不了/一直转圈”等缺陷词、复述用短标题不照抄。理清需求每条显示相似工单（`similar.py`，只提示，不合并不关单，按项目范围）；新建工单表单原本已有查重。
- 助手：状态/帮助/重试仍是确定性代码；不涉及代码的知识问题先检索知识卡片再由普通 LLM 组织答复（无卡片或 LLM 不可用时退回原智能体路径）；问到代码/文件/报错栈的仍走智能体。工作台说明与交接面板去掉内部术语，导航“任务”统一为“工单”。
- 测试：新增 `tests/test_intake_llm.py`（10 项）；`test_understand` 一处断言按新的默认 `auto` 更新。Python 3.12 全量（Node 20，UI 脚本测试不再跳过）：除本机 Git 2.34 的 readiness 用例与一处按当前时间登记劳动的 `test_pilots` 用例（单独运行通过）外全部通过。注意：VM 无 node 时约 60 个 UI 测试会静默跳过。
- 未部署：分支叠在未合并的 PR #1 上，且生产访问说明不在本机；未调用真实模型、未代人验收。
- 界面实测（本地 32 张 OA 工单 + 模拟 OpenAI 兼容接口，录屏）：附件（选择/粘贴/拖放）、普通 LLM 标记、哈希、相似提示、人确认前不建单、文案、助手分流通过；发现规则兜底复述仍带“今天好多人跟我说…急”“领导说…”，已加 `_gist()` 去转述人和催促语（原话仍保留为证据）并补测试。代码问题会先调一次普通 LLM 做指令分类（侧栏指令原有逻辑），再交智能体。
- 生产发布 `b8c6729`（含 PR #1/#2 改动，从 Devin 云端 VM 以 `devin` 用户经 SSH 发布；`webuddy-production-access.md` 不在服务器上，按服务器现状核对）：现役 `dc7cd59` 是 `b8c6729` 祖先；238 个运行文件（比上版多 `tmh/platform/llm.py`、`attachments.py`）解包到 `/opt/webuddy/releases/b8c6729fe331-intake-llm-20261030/app` 并 `MANIFEST.sha256` 校验；服务器 Python 3.12 跑 102 个相关 unittest 通过；生产数据副本上用新代码构造 `Platform`，platform.db 70 表、access.db 11 表的 schema 与行数不变，无迁移。持 `.release.lock` 完整备份到 `/opt/webuddy/backups/pre-b8c6729fe331-activation-20261030`（配置、旧 app、data，数据库用 sqlite `.backup`，回读 integrity ok），切 `app` 软链并重启；即时与 60 秒后 HTTP（本机/公网 login 200、API 401）正常，NRestarts=0，数据库 quick_check ok，日志无报错。生产未配置 `router`，需求理解不会调用普通 LLM，行为与之前一致；服务器无 `pypdf`，PDF 只存原件。回滚：软链切回 `releases/dc7cd596de3b-cwweb-preview-20261028/app` 并重启，不动数据库。

## 2026-10-30 生产启用普通 LLM（Kimi Code）与转发模型固定温度

- 用户选定复用服务器上 Hermes 的 Kimi Code key（`~/.hermes/.env` 的 `KIMICODE_*`）作为 Webuddy 普通 LLM；`zjz-ai.webtrn.cn` 中转的 key 实测 403「用户已被封禁」，不可用。
- Kimi 推理模型只接受 `temperature=1`，原代码固定发 0 会 400。新增 `router.temperature` / `TMH_ROUTER_TEMPERATURE`，由 `kbqa._post` 覆盖调用方温度；补 `test_router_temperature_replaces_the_callers`。本地相关 89 项通过。
- 生产发布 `3d3f855`（运行文件只变 `tmh/kbqa.py`、`docs/platform.md`）：`/opt/webuddy/releases/3d3f855cace5-router-temp-20261030/app`，备份 `/opt/webuddy/backups/pre-3d3f855cace5-activation-20261030`（含旧 env、旧程序、数据库 `.backup`，完整性 ok）。服务器 Python 3.12 上 intake/understand/agent_routes/kbqa 相关用例通过（`test_tmh` 中 9 个安装类用例因验证包不含 templates/skills 而报错，与本次无关）。
- `/etc/webuddy.env` 追加 `TMH_ROUTER_BASE_URL=https://api.kimi.com/coding/v1`、`TMH_ROUTER_MODEL=kimi-for-coding-highspeed`、`TMH_ROUTER_TEMPERATURE=1`、`TMH_ROUTER_VISION=1`、`TMH_ROUTER_KEY`（在服务器上从 Hermes 文件复制，未经聊天和 Git）。
- 生产 `autoflow.json` 原 `on: false` 使理清需求实际为 `rules`；改为 `understand: "llm"`（普通 LLM 可用则用，否则规则，不起 agent）。原文件备份在同一备份目录。
- 验证：重启后本机/公网登录 200、API 401、NRestarts=0；在生产数据副本上 JB 项目理清需求走 `LLM`（约 16 秒，未调用 agent，未建单）。CWWEB、WEIGHBILL、GROUPRISK、PPTAUTO 在 `agent-routes.json` 里 `direct_api: false`，仍只走规则；是否放开由用户决定。
- 回滚：`/etc/webuddy.env` 与 `autoflow.json` 换回备份，`/opt/webuddy/app` 指回 `releases/b8c6729fe331-intake-llm-20261030/app`，重启；数据库不动。
- 追加（同日）：用户选择「全部放开」，`agent-routes.json` 中 CWWEB、WEIGHBILL、GROUPRISK、PPTAUTO 的 `direct_api` 改为 `true`（原文件备份为同一备份目录下 `agent-routes.before-direct-api.json`；执行器路由 `cloudwave-codex` 不变）。生产数据副本上 5 个项目 `llm.conf` 均 ready、理清需求通道均为 `llm`；CWWEB 真实调用 Kimi 约 14 秒拆成两条，未调用 agent、未建单。服务 active，公网登录 200。

## 2026-10-30 普通 LLM 从 Kimi Code 切到 Cloudwave GPT 网关

- `https://ai.cloudwaveai.cn/v1` 即 `cloudwave-codex` 执行器所用的 `aiseat` 网关（模型 `gpt-6-luna`）。先测时网关整站 Caddy 502；恢复后用户给了专用服务账号 key，起初 `/chat/completions` 返回 403 `client_not_allowed`（账号只放行官方 Codex 客户端），用户在网关后台开通普通 API 后约 30 秒生效。未伪装客户端请求头。
- 实测：`/v1/models` 只有 `gpt-6-luna`；`/chat/completions` 接受 `temperature=0`，示例拆成缺陷 + 新功能约 2.6 秒；读图（data URL）正确；`/responses` 也可用。
- `/etc/webuddy.env` 改为 `TMH_ROUTER_BASE_URL=https://ai.cloudwaveai.cn/v1`、`TMH_ROUTER_MODEL=gpt-6-luna`、`TMH_ROUTER_VISION=1`、新 `TMH_ROUTER_KEY`，删除 `TMH_ROUTER_TEMPERATURE`（此模型接受 0）。key 经 SSH 标准输入写入，不进 Git。原 Kimi 版 env 备份为 `/opt/webuddy/backups/pre-3d3f855cace5-activation-20261030/webuddy.env.kimi-router-20261030110418`。程序未变（仍 `3d3f855`）。
- 验证：重启后 active、NRestarts=0，本机/公网登录 200、API 401；生产数据副本上 5 个项目 `llm.conf` ready、通道 `llm`，JB 示例约 13 秒、CWWEB 示例约 9 秒拆成两条，未调用 agent、未建单。
- 回滚：把上述备份 env 拷回 `/etc/webuddy.env` 并重启 `webuddy.service`。

### 2026-10-30 按步骤分配执行器：Opus 5.5 分析/方案/诊断，Luna 改代码

- 代码 `48b34a4`：`agent-routes.json` 的项目路由新增 `steps`（运行模式 → 执行器）。`Runner.start` 按步骤选执行器；`FixLoop` 的 `edit`/`diagnose` 和人工审查的诊断也按步骤选执行器，并用该执行器自己的默认模型。`steps` 里的执行器必须在 `allowed_agents` 中，未知模式或配错即拒绝；人明确选了别的允许执行器时以人为准；不同执行器之间不续接会话（`earlier_session` 本来就按执行器过滤）。新增 3 个用例；Python 3.12 下全量只剩与本次无关的 `test_readiness_checks_the_real_machine_worst_first`（本机 Git 旧）。
- 选型实测：Cloudwave 网关上 `gpt-6-sol`、`gpt-6-astra` 可用，`gpt-6.1-*` 返回 400（ChatGPT 账号的 Codex 不支持）。aixoras 中转（Claude 系列，最高 `claude-opus-5-5`）的 Anthropic 接口几秒返回，OpenAI 接口约 90 秒；Cloudflare 会拦 Python 默认 UA。用户选择真实项目也用 Opus 指挥。
- 发布前在生产数据副本上用新代码对 JB-32（网关关闭 knife4j 没生效）跑了一次真实方案：路由选中 `claude`/`claude-opus-5-5`，Opus 读代码、调 `tmh impact`、翻 git 历史找到根因，330 秒完成，输出含合法 `tmh-plan`（文件清单 + 分层验收标准）。副本随后删除。
- 生产发布 `48b34a4`：`/opt/webuddy/releases/48b34a40be56-step-agents-20261030/app`，MANIFEST 校验通过，服务器上路由用例 22 个通过。备份 `/opt/webuddy/backups/pre-48b34a40be56-activation-20261030`（env、unit、`agents.json`、`agent-routes.json`、旧程序、数据库 `.backup`，完整性 ok）。`/etc/webuddy.env` 追加 `ANTHROPIC_BASE_URL=https://aixoras.com`、`ANTHROPIC_AUTH_TOKEN`（经 SSH 标准输入写入）和 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`；`agents.json` 加 `claude`（服务器 Claude Code 2.1，模型 `claude-opus-5-5`，`run_timeout` 1800）；CWWEB、WEIGHBILL、GROUPRISK、PPTAUTO、JB 路由加 `claude` 到 `allowed_agents`，并设 `steps: analyze/plan/diagnose → claude`，改代码仍走 `cloudwave-codex`（Luna）。本机/公网 login 200、API 401，NRestarts=0。
- 回滚：把备份里的 `0-webuddy.env`、`2-agents.json`、`3-agent-routes.json` 拷回原处，`app` 软链指回 `releases/3d3f855cace5-router-temp-20261030/app` 并重启；只想停用 Opus 时，只恢复 `3-agent-routes.json` 即可，不用重启。数据库不动。

### 2026-10-30 生产真实工单走查（JB）与诊断规则修正

- 用 computer use 在生产浏览器以 li 走 JB：口语加截图理清需求，普通 LLM 拆出两件，人工确认后建 JB-42、JB-43；JB-42 分析 #256、方案 #257 由 `claude`/`claude-opus-5-5` 完成（118 秒、133 秒，方案含 `tmh-plan`）。修改 #258 因 Windows 测试机（frp `12022`）离线 1 秒失败；用户开机并启动 sshd 后重跑 #259（`cloudwave-codex`，453 秒，改 1 个 Vue 文件），未采纳、未验收。
- 测试机问题：npm 连不上 registry.npmjs.org，esbuild 安装失败使 `pnpm install` 失败。经用户同意，将测试机用户 `auntu` 的 npm 源设为 `https://registry.npmmirror.com/`（原 `.npmrc` 备份为 `.npmrc.bak-webuddy-20261030`），安装恢复（11 秒）。缓存的失败基线 `data/checks/JB-63017ead0739af1d.json` 移到 `/opt/webuddy/backups/jb-baseline-check-20261030/`。JeecgBoot 前端 `vue-tsc --noEmit` 在原代码上仍不可用：默认栈溢出；加大栈后报原代码自身的类型错误（`MyComment.vue` TS1003），所以 JB 前端改动的构建检查依旧会因基线失败而跳过。
- 修正：没跑构建且改动只有一个文件时，FixLoop 原来不做诊断，Opus 诊断从未执行。现在项目路由把诊断交给另一执行器时，不论改动大小都做一次只读诊断；新增 `test_fix_loop_has_the_routed_engine_diagnose_a_small_unbuilt_change`。
- 界面待改：分析/方案的提示仍写“已交给 Cloudwave · 官方 Codex”；分析摘要“根因”显示提示词里的“（3 句以内）”；修改顶层“完成”不代表验证通过；验证页只显示基线退出码；手动运行区无单独诊断入口；`cloudwave-codex` 修改的 `runs.model` 为空。

### 2026-10-30 界面如实反映运行结果

- 用户要求修复走查发现的界面问题。分析/方案的提示改用服务端实际选中的执行器（`Runner.start` 返回的 `agent`），不再显示下拉框里选的那个。分析摘要的“根因”跳过标题里的提示词括注（如“结论（3 句以内）”）。
- 修改运行在工单接口里带上 `diff_bytes`。没有改动时不再显示“智能体改好了代码，等你审阅”，改为“没有改任何代码”，并给出“查看执行结论 / 重新出方案”两个按钮。运行列表和详情里的“完成”会补充说明“没有改动 / 验证没通过 / 未验证”。
- 官方 Codex profile 没有显式指定模型时，`runs.model` 记录 profile（`<CODEX_HOME>/<profile>.config.toml`，退而读 `config.toml`）里实际生效的模型，方便事后核对用的是不是 Luna。重试时，如果记录的模型就是这个配置默认值，就不当作人工指定的模型，免得诊断等步骤被强行换模型。新增 `tests/test_run_truth.py`。
- 已有的修改运行（如 #259、#260、#263）不回填 `runs.model`；新数据只在新运行上生效。
- 生产走查发现运行详情接口返回的是 `verification`，不是 `verify`，所以详情页的“完成”没有带上验证说明。`runStatus` 现在两个字段都读。
- 生产走查发现，租户托管模式下 `/api/meta` 不返回 `data_dir`，评论草稿提交时 `expected_workspace` 为空，`api_comment` 因此对所有评论都返回 409。修复方法：meta 新增 `workspace`（数据目录路径的 sha256 摘要，不暴露路径），评论守卫同时接受真实路径或这个摘要；空值和其他工作区的摘要仍然拒绝。

### 2026-10-30 诊断收敛：阻断项与建议分离、增量复审、兜圈子就停

- 起因：JB-42 连续三次修改（#260、#264、#265），Opus 诊断每次都判 fail / partial，而且每次指出的都是新的静态疑点（#265 的依据是参考组件状态管理不同）。原诊断提示问的是开放的“是否真的解决了”，不要求说明违反哪条验收标准；各次修改的诊断互相看不到；也没有停止条件。用户要求：“我们能改，然后改的对就行……总会有无尽的修改的”，并要求按业内共识做。
- 依据：Google 代码审查规范（整体变好即批准，Nit/Optional 不阻断）、Devin Review 的严重性分级、增量复审（先核对上次意见）。
- `MODE_TEXT["diagnose"]`：判 fail 必须列 `blocking`（对应的验收标准 `ac`、具体失败场景 `scenario`、代码位置 `where`）；推测风险、写法与参考代码不同、风格和健壮性进 `advisory`，不影响结论；给了之前的诊断时先逐条判断是否已解决（`prior`），新阻断项要说明是本次引入还是之前漏看。构建或测试失败仍然是阻断项。
- `FixLoop`：模型判 fail 但 `blocking` 是空列表时记为 `unknown`（不替它判通过；旧格式没有 `blocking` 字段的 fail 照旧算 fail）。同一工单下一次修改的诊断会带上紧挨着的上一次修改的 `blocking/evidence/cause/guide`（上一次是 pass 就不带）。连续 `STALL_AFTER=3` 次修改诊断都是 fail（中间遇到非 fail 即重新计数）时，`verify.json` 写 `stalled`，摘要显示“在兜圈子”并建议先实测或由人定方向；工单接口带出 `stalled`，运行说明里同步提示。摘要新增“阻断项”和“建议（不影响结论）”两节。
- 测试：`tests/test_agent_routes.py` 新增 4 个用例（无阻断项的 fail → unknown；advisory 不影响 pass；上一次阻断项进入提示 + 连续三次 → stalled；上一次 pass 打断循环），`tests/test_recheck_summary.py` 补 `vfy` 的兜圈子提示断言。相关 9 个测试文件 162 个通过，唯一失败仍是与本次无关的 `test_readiness_checks_the_real_machine_worst_first`（本机 Git 旧）。
- Devin Review 跟进：`blocking` 只算 `ac` 和 `scenario` 都非空的项（`fixloop.blockers`），`[{}]` 之类按没有阻断项处理；被改成 unknown 的 fail 在 `verify.json` 写 `vague_fail`，`fix_gate` 据此留给人看，不会自动提交（原来的 unknown 照旧）；兜圈子只数诊断本身判 fail 的次数，不把构建失败但诊断通过的修改算进去。新增 3 个用例。

### 2026-10-30 按项目开关的 AI 验收与关单；JB 前端构建检查改用项目自己的 vite build

- 用户选择：“全部交给 AI，包括验收和关单（改 AGENTS.md 规则，按项目开关）”，并说明 Windows 不重要。`AGENTS.md` 增加例外：只有 `autoflow.json` 的 `ai_accept` 列出的项目，由平台自己的 `tmh/platform/ai_accept.py` 在确定性闸门全部满足时签收并关单；人工验收入口的 guard 不变，开发用 Agent 仍不得手工代人验收。
- `ai_accept.after_commit` 挂在 `Orchestra.committed`（自动流转 `_flow_commit` 提交成功之后）。签收条件全部满足才做：项目开了 `ai_accept`；没人接手；工单在 `verify`；不是固定候选单；`epic.refuse` 放行；证据包已生成、完整、快照对应的正是这次运行；`verify.json` 当前有效、构建测试 `pass`、诊断 `pass` 且无阻断项、没改方案外文件；证据包里每条验收标准都有诊断逐条给出的 `pass`（缺条目、`unverified`、`fail`、待确认的标准都不行）。签收在 `verification_guard` 里调用 `_record_accept`（签收人 `AI 验收`，`via` 为 `AI 验收`，`basis` 写运行号和每条标准的依据），事件带 `ai: true`，状态改为 `closed`，然后照常 `flow.accepted` 走合并发布。任何一项不满足只记一条“AI 没有验收：原因，留给人验收”。
- 诊断提示新增“逐条核对的验收标准”（客户确认的优先，否则取方案的），`tmh-diag` 新增 `ac: [{id, result: pass/fail/unverified, how}]`，`verify.json` 保留 `ac`，摘要新增“逐条验收”一节。
- `autoflow.json` 的 `on` 可以写项目列表（`Orchestra.switched_on`），只让列出的项目自动流转；`true/false` 含义不变。
- `testbox.build_commands`：前端检查优先用项目自己的 `type:check`，其次项目 `build` 脚本里的 `vite build`，最后才猜 `vue-tsc`/`tsc`。JeecgBoot 原代码 `vue-tsc` 必然失败，而在测试机上对原代码跑 `pnpm install --prefer-offline && pnpm exec vite build` 退出码 0、92 秒。
- 测试：新增 `tests/test_ai_accept.py`（开关按项目、证据不全的 8 种情况留给人、签收+关单+发布、关闭/接手/证据包对应别的运行/被改动时不签），`test_agent_routes` 新增逐条验收进提示和摘要，`test_testbox` 新增前端检查选择。相关 16 个测试文件全部通过（除本机 Git 旧导致的 `test_readiness_checks_the_real_machine_worst_first`）。

## 2026-10-31 JB 真实验证环境（pstack「Prove It Works」第一步）

- 用户选择：在 Windows 测试机上起 JB 前后端做预览，AI 在真实页面上按验收标准逐条操作并截图；只有能复现的问题才阻断。
- 测试机 WSL（Ubuntu-24.04，15G 内存）：apt 换 aliyun 镜像，装 mysql 8（lower_case_table_names=1，导入 JB 自带开发库 `jeecg-boot`）、redis、maven；后端 jar 由 systemd `jb-backend` 跑在 :8080（`/jeecg-boot`）。WSL 的 sshd 经 frp（生产 12122）接入，生产 ubuntu 用户的公钥已加到 WSL `auntu`。
- 前端：`~/pv/base` 为生产 JB 仓库 HEAD 的克隆，pnpm（npmmirror）依赖已装；vite 按 `VITE_PUBLIC_PATH/VITE_GLOB_API_URL/VITE_PROXY` 带预览前缀启动，6 秒可响应。
- 浏览器：WSL 里 Playwright 1.48.2 + chromium（npmmirror）。`tools/verify/jb/` 的 doctor 实测：页面渲染、经验证码真实登录成功（验证码从 redis 按 JB 自身算法反查，不改 JB 代码），截图可见该提交的「AI助手」改动。
- 默认组织（受信宿主运行时）的托管进程可以按项目列表开自动流转（`on` 必须是列表）；自动合并在托管进程里仍强制关闭，其他租户仍全关（提交 b475114）。
- 下一步：验证器模块把候选提交送到 WSL、按验收标准跑 Playwright、截图回传写证据链，再接入 AI 验收的闸门。

## 2026-10-31 真实应用验证器接入 AI 验收（pstack「Prove It Works」）

- 新模块 `tmh/platform/browser_verify.py`：项目在 `<data>/verify-hosts.json` 配了验证机时，把被测版本（已提交的候选 commit，或 run 工作树的 base + diff）经 SSH 送到验证机，在独立工作树里起前端（后端与数据库是验证机自己的隔离开发库），由诊断执行器按验收标准写 Playwright 脚本（每条标准一个 test、每步截图），真实浏览器跑完把 JSON 报告和截图传回。
- 判定：断言失败 = 复现（fail）；测试通过且有截图 = pass；超时、步骤执行不了、跳过、没截图、环境起不来 = unverified。只有全部 pass 才算证明。
- 结果写进证据链：每条标准最多 3 张截图（`signoff.attach`，按 sha256 落盘），外加一条 `verify` 事件记录 run、base、diff_sha256、spec_sha256 与逐条结论。
- AI 验收（`ai_accept.after_commit`）：配了验证机的项目，必须页面实测全部 pass 才签收；诊断里某条标准「没法确认」不再阻断，但诊断判某条 fail 仍阻断。签收依据带 `real: pass`。
- 生产上实测传输链路：WSL 里登录 JB，A1（顶部有「AI助手」）pass，故意写错的 A2 判 fail（断言失败），两张截图回传。原 `tools/verify/jb/` 的 helper 已并入模块。
- 本机 node 是 v12，UI 测试需 `PATH=~/.nvm/versions/node/v24.19.0/bin:$PATH`。

## 2026-10-31 JB 无人化链路：实测误报与代码位置识别

- JB-49：页面还在 JeecgBoot 加载动画上就断言，A1 被误判为复现问题。修复 `22f0d31`：helpers 包装 `page.goto` 等 networkidle 且 `.app-loading` 消失，globalSetup 预热冷 Vite，等不到算 `TMH_SETUP`（未证明）。用该候选直接复跑，A1/A2 通过（约 44 秒）。
- JB-50：生成的定位同时命中隐藏的注册表单，触发 strict mode。修复 `1ac747a`：strict mode 判为未证明；脚本自身错误交回诊断执行器修一次，断言不许删改，结论绑定新的 `spec_sha256` 并记 `repaired_from`。真实断言失败、环境错误不修，最多修一次。
- JB-51 / JB-52：Opus 写的代码位置用了反引号包路径（`57e1c54`）、Markdown 表格分列，平台按 refs=0 停在分析。`4e92ddf` 改为按行宽松识别（`tmh/platform/coderefs.py`）：路径后同一行的「第 N 行」、`:N`、`#LN`、`LN` 或表格相邻的数字格都算；用 JB-48..52 的真实分析结论核对过。
- JB-53：分析 refs=3，自动走到 WSL 实测。两条 test 都卡在生成脚本的前置定位 `button` 文案 `^登录$` 上（Ant Design 两字按钮渲染为「登 录」），平台按断言失败判 fail，因此没有触发修脚本，也没有签收。修复 `e12b765`：前置条件改用 `anchor()`，找不到判 `TMH_ANCHOR`（未证明、可修一次脚本），只有标准本身的断言失败才算复现；提示里写明两字按钮带空格。
- 现状：还没有一张生产单零人工走完 AI 验收和关单。JB-44..53 都没有人工采纳、验收或关单。
- JB-53 复核：生成的脚本还打开了 `TMH_BASE + '/sys/login'`（多了一个斜杠，路由也不对），并且在第一次 `shot` 之前就断言了登录按钮。修复 `b790198`：截图之前的断言失败判为未证明（可修一次脚本），因为看不到页面实际状态，不能算复现；提示里写明 `TMH_BASE` 以 `/` 结尾、登录页是 `user/login`，进入页面后先截图再断言。
- JB-54（b790198）：零人工跑到实测。A2 通过；A1 判 fail，但 A1 自己的截图上，复选框旁清楚显示「记住账号」。原因是脚本假设文案在 `<label>` 里，实际页面是 checkbox 加一段 text。修复 `d356ecd` / `c2bdbfe`：第一份脚本只当草稿。凡是没通过的标准（环境没起来的除外），都带上失败时的页面结构（Playwright 1.48 没有 ariaSnapshot，退回 accessibility 树，一行一个元素）交回复核一次：页面确实没做到就原样保留，脚本写错了才改，改后的脚本必须保留标准里引号中的检查内容（`keeps()`），否则不采用。生产上用 JB-53 候选做了冒烟，故意用错的 label 定位，页面结构里能看到 `checkbox` 和 `text "记住账号"`。
- JB-55（c2bdbfe）：自动提交后停在诊断。Opus 判了 pass，但 `tmh-diag` 的字符串里有没转义的双引号（`实现"记住账号"功能`），JSON 解析失败，平台按「没给结论」处理。修复：`fixloop.loads()` 先按严格 JSON 解析，失败后把字符串里不在 `, : } ]` 之前的裸引号转义再解析，结构本身坏了仍然返回 None。用 JB-55 的真实输出核对：verdict=pass，A1 静态 unverified，其余 pass。
- JB-56（f3df2ae）：第一张零人工走完 AI 验收并关单的生产单。链路：analyze #323 → plan #324 → Luna fix #325 → 测试机 `vite build` 81 秒 → Opus 诊断 pass → 自动提交 `tmh/JB-56-r325`（13f53ff9）→ spec #326。原始脚本先 `login()` 再打开登录页，结果落到登录后的 404，A1/A2 都是 TMH_ANCHOR。review #327 只删掉了 login，断言原样保留，重跑后 A1/A2 通过，各 2 张截图，`repaired_from` 记的是原 spec 的 hash。AI 验收（ai:true，basis 里 real=pass，KEPT 为 A3–A5）后关单。合并发布停在 waiting（项目目录是 detached HEAD），自动合并本来就关着。证据包页面关单后仍列出缺少「验证门全部通过」和「乙方复核人」，待查。
- 全自动 / 每步人工 / 回滚（用户：“先不卡，我们先做全自动，然后做好版本管理，就可以及时回滚和人工介入，当然也需要可以切换为原本的各个步骤都要人介入的情况”）：AI 验收不加 pack gates 和乙方复核。新增项目模式 `auto`（autoflow.json 的 `on`、`ai_accept`、`merge` 三个列表都含该项目）/`partial`/`manual`，设置页逐项目切换（`POST /api/projects/<key>/mode`，租户模式下仅 default+legacy 的 platform owner）。切到全自动时，项目目录停在游离提交上就就地建 `webuddy/<KEY>` 分支作交付主线（文件不动，写入 autoflow.json `main`），已有分支就用它，名字冲突则拒绝。`release.settings` 的 `merge` 支持项目列表；托管 worker 只为 `auto` 模式的项目合并。回滚：`POST /api/projects/<key>/releases/<version>/rollback` → 在主线上 `git revert`（merge 提交用 `-m 1`），作为新版本打 tag 记入 releases.jsonl（`kind: rollback`, `of`），历史不改写，不推送不部署；冲突时 `revert --abort`，主线不动；该版本的工单重开为 doing 并设 hold 转人工。版本列表显示「回滚」/「已回滚（新版本）」。测试 `test_full_auto_mode_gets_a_delivery_line_and_a_version_can_be_rolled_back`（游离提交→建主线→合并→回滚→代码回到合并前→重复回滚 409→切回人工 merge off）。

## 2026-11-01 执行器结构化汇报（借鉴 dsh-superagent 的 `human_action` 与结构化报告）

- 用户：「你一直操作即可」；按约定顺序先做第 1 项：平台只读执行器的固定结论块，不再从正文里猜。
- 分析步骤新增 ```tmh-report {"refs": [{"path", "line"}], "human_action": ""}```（`tmh/platform/reports.py`，提示词在 `MODE_TEXT["analyze"]` 末尾）。`FILE_LINE.findall` 先读报告里的 refs（路径经 `rel_path` 校验、行号须为正整数）；没有报告或 refs 为空的老回答仍走正文识别。
- `human_action` 非空：自动流转在分析后停下，动态写「分析需要人先回答：…」，不起草方案；人回答后「交给自动处理」照常从分析接着走。
- 格式修复：分析、方案（Runner，带工单且不是交付流程的单）和诊断（FixLoop）缺块或块不合法时，把原回答交回同一执行器补一次块，只补格式、不许改结论；补不出就保持原结论（诊断仍记「没给结论」）。修复过的诊断在 verify.json 里记 `format_repaired`。执行器配置 `report_repair: false` 可关掉分析/方案的修复。
- 发布：PR #8 合并为 `94c239d`，已发到生产（release `94c239d0e358-structured-reports-20261101`）。MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0。第一次激活失败：远端 shell 的 cwd 是刚删掉的临时目录，rsync 报 getcwd 错（code 3），生产未切换；删掉半成品 release 和备份目录后，在 `cd ~` 下重跑成功。

## 2026-11-01 AI 验收观察模式（借鉴 dsh-superagent 的 observe → auto）

- 第 2 项：新项目先让 AI 验收「只说不签」，攒够和人一致的记录再切全自动。
- autoflow.json 新增 `ai_accept_observe` 列表。列在里面、但不在 `ai_accept` 里的项目，`ai_accept.after_commit` 照跑全部闸门（含页面实测），只在工单上写「AI 影子验收：本会验收通过（依据）」或「本不会验收（原因）」，事件 data 里是 `shadow: {would_accept, why, basis}`。不签收、不关单、不触发合并，工单留在待验收。`ai_accept` 优先于 `ai_accept_observe`。
- 人之后验收或退回时（`Orchestra.accepted` → `ai_accept.compare`），对最近一次影子结论记一条「AI 影子验收和人一致/不一致」（`shadow_compare: {run, ai, person, agree, by}`），每次影子结论只对比一次；AI 自己的验收不参与对比。
- 项目模式新增 `observe`（`on` 含项目、`ai_accept_observe` 含项目、`ai_accept` 不含）。`POST /api/projects/<key>/mode {"mode": "observe"}` 切换，权限同原来。`GET .../mode` 多返回 `shadow: {shadow, compared, agree, disagree}`。设置页显示「AI 验收观察中」和「对比 N 单，一致 M 单（不一致：…）」，可以在全自动、观察、每步人工三者之间切换。
- 测试：`tests/test_ai_accept.py` 新增 ShadowAcceptTest、ShadowCompareTest、ShadowModeSwitchTest。相关套件 475 passed（不含本机环境导致的就绪检查用例）。
- 发布：PR #9 合并为 `1290293`，已发到生产（release `1290293642bf-ai-accept-observe-20261101`），服务器上 `tests.test_ai_accept` 19 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，journal 里没有新报错。JB 仍是 on+ai_accept，merge 未开（半自动），模式没动。

## 2026-11-01 授权快照（借鉴 dsh-superagent 的 Mandate）

- 第 3 项：每次自动开工、每次 AI 结论都记下当时凭什么能做。
- `ai_accept.mandate(conf, key, data_dir)` 返回 `{policy, mode, switches, set_by}`：
  - `switches` 只取对这个项目生效的开关（on、ai_accept、observe、merge、plan、fix、commit、该项目的 max_lines、refix），所以别的项目改了不影响这个指纹；
  - `policy` 是这些开关的 sha256 前 12 位；
  - `set_by` 是 modes_log 里这个项目最近一次切换（by、ts、mode）。
- 自动受理（`_intake` 的 intake 事件）的 data 里写 `mandate`。AI 验收的 basis 里写 `mandate`，随签收进证据包、受 hash 约束；影子结论的事件 data 里也写一份。签收说明末尾写「授权：全自动（策略 xxxx，li 于 … 切换）」。
- 策略在这单开始后改过：不中断，按现在的授权判断。basis 里记 `changed_from`（开工时的策略），说明里写「这单开始后授权改过（原策略 …），按现在的授权判断」。
- 测试：`MandateTest`、`MandateOnVerdictTest`。
- 发布：PR #10 合并为 `01746cd`，已发到生产（release `01746cdc6e44-mandate-20261101`），服务器上 `tests.test_ai_accept` 22 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，journal 里没有新报错。CI：Ubuntu 全过；Windows py3.11 全量这次 30 分钟超时，失败集合与基线 push run（同样超时）一致，没有新增。

## 2026-11-01 工单阶段判定表（借鉴 dsh-superagent 的确定性 Ticket 阶段）

- 第 4 项：工单「在等谁」只由一张表算出来。`tmh/platform/stage.py` 的 `TABLE` 从上往下逐行判断，第一条成立的就是当前阶段；每行写明 `who`（person 等团队 / client 等客户 / agent 自动流转或检查在做 / assignee 接手人在写 / none 已结束）、`step`（进度条上对应哪一步）、文案和动作。
- `decide(t, facts)` 是纯函数；`compute(P, tickets)` 批量取齐事实（最新运行、在跑运行、我来写的检查、补全恢复、重新验证、签收状态、已发版本、自动处理和智能体是否可用）后逐张判定。
- 三处改成读这张表：
  - 首页「等你处理」（`Platform.inbox`）：`who=person` 进「等你处理」，`who=client` 进「等客户」。原来不在收件箱里、但在需求页显示为「等你看」的阶段（已接管、运行已取消、CLI/MCP 等下一步、提交检查没通过、客户改了验收标准、补全没理解完、大需求暂停、没有可自动执行的下一步）现在也列出来，数字和列表一致。
  - 需求、客户页和工单页顶部的状态（`workbench.states`）：由阶段的 `who` 映射成 等你看 / 等客户确认 / 做着 / 已出版本 / 已完成，说明文字就是阶段文案。
  - 工单详情的进度条：API 多返回 `stage`，进度条在阶段所在的那一步标「等你 / 等客户 / AI 在做 / 人工在做」，悬停显示阶段文案。
- 行的先后沿用原来需求页和收件箱的判断顺序；两边原来顺序不一致的地方（例如已接管但最近一次运行失败）现在以收件箱为准：失败、待审阅、退回优先于已接管。自动执行本身（`Orchestra.next_step`、`waiting`）没改。
- 测试：`tests/test_stage.py`（每条先后冲突一例，加进度条渲染），`test_workbench_states`、`test_recheck_summary`、收件箱用例照旧通过。
- 补漏：Windows py3.13 CI 上，自动处理开着、调度器当下没给出下一步时，没动过的新单被判成「没有可自动执行的下一步」（idle）。改成没动过的 new/analyzing 单在自动处理开着时一律算排队（`queued`），`test_stage` 补了这一例。
- 发布：PR #12 合并为 `413a7fc`，已发到生产（release `413a7fcdbb4c-ticket-stage-20261101`）。改动的运行文件：server.py、stage.py（新增）、ui.py、ui_css.py、workbench.py。服务器上解出的包里 `test_stage`、`test_workbench_states`、`test_recheck_summary` 共 26 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0。CI：Ubuntu 全过（py3.13 第一次挂在 harness probe 的已知抖动用例上，重跑通过）；Windows py3.11 的失败集合与基线一致；py3.13 基线那次跑到一半就超时，test_platform 的大部分用例没跑到，所以没法逐条对比，只确认了其中收件箱那一例是本次改动引起的，已修。

### 工单详情「下一步」改由阶段表选卡；补「等合并发布」「改动已采用待转验证」

- 工单详情的 `nextAction(d,f)` 现在先看 `d.stage.key`，按阶段挑对应的卡片（按钮、文案沿用原来那些分支），不再自己从头判断一遍；接口里没有 `stage` 的老数据照旧走原来的顺序。等你的阶段卡片前面加上阶段表的说法（如「li 已接管，自动处理暂停」），AI 在做的阶段直接显示阶段表的说法。
- `stage.TABLE` 新增两行：`release_waiting`（已关单，但最近一次合并发布停在「等待」，排在已出版本之前，后来的 `release` 事件会清掉它）和 `accepted`（修改已采用到分支，单子还没转待验证）。收件箱把等合并发布的已关单也列进「等你处理」，但不计入未关单数。
- 测试：`tests/test_stage.py` 新增阶段表两行的先后冲突、收件箱/工单接口/需求页三处一致（含发版后清掉等待）、Node 渲染下一步卡片（等合并、已出版本、退回、等签收、AI 在做、已接管、已采用、无 stage 的老数据）。本地 `test_platform`、`test_workbench*`、`test_ui_*`、`test_*_ui`、`test_stage` 等 543 个通过（就绪检查照旧排除）。
- 发布：PR #14 合并为 `fde4e26`，已发到生产（release `fde4e2601db1-next-action-20261101`）。服务器上解出的包里 `test_stage`、`test_workbench_states`、`test_recheck_summary` 共 31 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，发布后 journal 无报错。

### 普通 LLM 调用遇到临时故障自动退避重试

- `kbqa._post`（需求理解、`llm.chat`、分诊 `choose` 都走它）遇到 408、429、500、502、503、504、529 或连接不上，按 2、5、10 秒退避重试三次，`Retry-After` 更长时按它等（最多 30 秒）；其他错误和读超时照旧立刻抛出。智能体进程本来就有 `BUSY_WAITS` 重试，这次只补了直接 API 这一路。
- 测试：`tests/test_intake_llm.py` 新增一例（忙→连不上→忙→成功；400 不重试；连续 5xx 四次后抛出；读超时不重试）。
- 发布：PR #15 合并为 `6c3dd8f`，已发到生产（release `6c3dd8fa0e7d-llm-retry-20261101`）。服务器上解出的包里 `test_intake_llm`、`test_stage` 共 31 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，发布后 journal 无报错。
- DeepSeek docs 零碎项核对：自动合并改动行数上限已有（autoflow `max_lines`，默认 400，可按项目设）；全局暂停已有（autoflow `on: false` 写在文件里，重启后仍生效）；智能体进程的繁忙重试已有（`BUSY_WAITS`），这次补的是直接 API 一路。

### 项目绑定 GitHub 仓库推送交付结果；项目群收关键事件通知

- 代码库管理（`tmh/platform/repo_sync.py`）：项目在 设置 → 项目 里绑定一个 GitHub 仓库（`autoflow.json` 的 `repos`）。平台为每个项目生成一把专用 ed25519 部署密钥（`<data>/keys/<KEY>-deploy`，0600，不进 Git 和数据库），远端名 `webuddy`，固定 GitHub 官方主机密钥、禁止交互。推送默认关，「测试连接」（`ls-remote`）通过后才能打开；测试失败会自动关掉推送。
- 推送的东西：候选分支 `tmh/<单号>-r<运行>`、交付主线 `webuddy/<项目>`、版本标签 `webuddy-<项目>-<版本>`、回滚生成的新版本。只做普通推送（具名 ref，不强推、不删分支）；被拒（例如远端有别人的提交）就在工单上记一条，不回退本机已合并、已出的版本，下次再推。
- 项目群通知（`tmh/platform/announce.py`）：项目可以绑定一个机器人待过、能主动发消息的飞书 / 钉钉 / 企业微信群（`autoflow.json` 的 `notify`），只能选本项目的会话。分析要人回答、AI 没验收留给人、验收通过并出版本、等合并、合并冲突、回滚、推送失败这几类事件发到群里，带工单链接。发送失败只记进动态，不挡自动流转。飞书沿用 `tmh/bots.py` 原有的签名校验、解密和主动发送。
- 接口：`GET /api/projects/<key>/channels`、`POST …/repo`、`POST …/notify`，写操作只给平台管理员，已登记到 `tenant_policy.API_ROUTES`（177 条）。
- 测试：`tests/test_repo_sync.py`（地址解析与拒绝、密钥生成与复用、测试连接前不能开推送、本地 bare 仓库模拟 GitHub 的分支/标签普通推送、非快进被拒、项目群隔离与失败不抛错）。CI 上没有 git 身份时打附注标签会失败，测试里显式给了身份；`test_full_auto_mode…` 只在版本确实打了标签时核对标签。
- 发布：PR #17 合并为 `af7a0b3`，已发到生产（release `af7a0b3c81bb-repo-sync-20261101`）。服务器上解出的包里 `test_repo_sync`、`test_tenant_policy`、`test_ai_accept` 共 58 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0。
- 还没接通：飞书企业自建应用的凭证没配（生产没有 `TMH_FEISHU_*`），没有群可绑；也还没有目标 GitHub 私有仓库，JB 没绑仓库，推送是关的。

### 代码仓库支持自己机器上的 SSH 裸仓库；JB 已绑定 Windows 测试机 WSL 私有仓库

- 用户选择把私有仓库放在 Windows 测试机的 WSL 里（不放 GitHub 组织）。`repo_sync` 新增 `kind: "ssh"`：地址 `ssh://用户@主机:端口/路径/仓库.git`，绑定时固定主机密钥（`hostkey`，按 `[host]:port` 记，可直接给出或绑定时读一次），每个项目单独的 `keys/<KEY>-known_hosts`，`StrictHostKeyChecking=yes`；这种仓库没有网页链接。GitHub 一路不变。
- 发布：PR #19 合并为 `f778586`，已发到生产（release `f778586bb09e-selfhost-repo-20261102`）。服务器上解出的包里 `test_repo_sync`、`test_tenant_policy` 共 38 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，journal 无报错。
- WSL 一侧：裸仓库 `/home/auntu/git/JeecgBoot.git`（`receive.denyNonFastForwards`、`receive.denyDeletes`）。生产的 JB 部署公钥写进 auntu 的 `authorized_keys`，带 `restrict,command="/home/auntu/git/webuddy-git-only.sh"`，只放行对这一个仓库的 `git-receive-pack` / `git-upload-pack`（实测要 shell、读别的目录都被拒）。改之前备份了 `authorized_keys`。主机密钥指纹 `SHA256:IV+/0HYcdROF3qjfK8WVVydnCxOb6BJvXAWCUekU0pg`，与 WSL 上 `/etc/ssh/ssh_host_ed25519_key.pub` 核对一致。
- 生产经本机 frp 端口访问：`ssh://auntu@127.0.0.1:12122/home/auntu/git/JeecgBoot.git`。测试连接通过后打开了推送；已有的 52 条候选分支 `tmh/JB-*` 首次整批推上去（约 100 MiB，44 秒），再用 `repo_sync.push` 推了一次 `tmh/JB-56-r325` 验证普通推送路径。JB 当前是半自动（没有 `webuddy/JB` 交付主线和版本标签），之后自动提交的候选分支会自动推上去。
- 已知局限：测试机关机、休眠或 frp 断开时推送失败，只在工单上记一条，本机结果不受影响，下次一起推；仓库在 WSL 里只有一份，生产的 JB checkout 本身持有同样的提交，可作为恢复来源。

### 飞书接入：租户入口的机器人回调、企业自建应用、真实消息进来；通知和回复改成带按钮的卡片

- 生产的多租户网关原来拒绝所有没有 `X-TMH` 的外部回调，飞书消息进不来。PR #21（`d4b9518`，release `d4b95185c989-bot-callbacks-20261102`）新增 `/t/<租户>/bot/<平台>/<项目>`：只有 active 租户可进，正文不超过 1 MiB，转给该租户的 worker。worker 凭据绑定租户、`bot:<平台>`、方法、路径、正文 hash、时间和公开标记 `X-Webuddy-Public: bot`。飞书自己的签名、Encrypt Key、Verification Token 照旧在 `bots.feishu` 里校验。其他公开入口仍然关着。
- 飞书应用：企业「云涌世纪」下新建了企业自建应用「Webuddy 交付助手」（`cli_aa6d45bff2f81bfe`）。原本打算复用「webuddy-云涌助手」，但它是长连接模式，可能还有别的程序在用，所以没动它。机器人能力已开；事件订阅用开发者服务器模式，回调地址 `https://webuddy.bbstack.date/t/default/bot/feishu/JB`，订阅 `im.message.receive_v1`；1.0.0 版已发布，可用人数在 6 人以内，免审批。四项凭证只写在 `/etc/webuddy.env`（改前有备份），JB 的 `.tmh/config.json` 里只记环境变量名。
- 真实消息验证：用户在和机器人的会话里 @ 了它，2026-11-02 12:09:46 生产收到，生成了 intake `9e2bc2d35916`，`convs.json` 登记了 `JB:feishu:oc_86d07bda59b6e0d90a6ffd2212f4f3fd`。JB 的项目通知绑到了这个会话（`autoflow.json` 改前备份在 `backups/autoflow.json.pre-feishu-bind-1793592637`），测试消息发送返回成功。这个应用没有 `im:message.group_msg` 权限，读不了群历史，所以发出去的消息有没有显示，要靠人在飞书里看。
- PR #22（`f6c488f`，release `f6c488f96177-feishu-cards-20261102`）：
  - `bots.feishu_card`：卡片带彩色标题，下面一个按钮，点了进 Webuddy。
  - `announce.say`：卡片标题写「JB · 事件」，有工单时按钮是「打开工单」，没有时是「打开 Webuddy」。`tell_team` 的各个调用点标了事件名和颜色。
  - 群里说「简报」，或者问平台本身（比如「多少项目在你管理下」），机器人不再去查知识库，直接回一张卡片：`chat.brief` 列出各项目等你处理、未关单、进行中、今天关单的数量。
  - 钉钉和企业微信没有卡片，标题和链接写成 markdown。
  - 生产 `/etc/webuddy.env` 新增 `TMH_PUBLIC_URL=https://webuddy.bbstack.date`，卡片按钮的链接从这里取。
- 发布：服务器上解出的包里 `test_repo_sync`、`test_tenant_gateway`、`test_tenant_runtime` 共 47 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，journal 无报错。发布后用生产代码往 JB 通知会话发了一张测试卡片，飞书接口返回成功。

### 飞书登录：企业飞书账号登录已绑定的 Webuddy 账号

- 用户确认飞书卡片和简报都能用之后指出：还没有基于飞书的登录。PR #24（合并为 `353b541`，release `353b541f2824-feishu-login-20261102`）在租户网关加了飞书 OAuth 登录，复用「Webuddy 交付助手」的 App ID/Secret；没配这两个环境变量时登录页和以前一样，`/login/feishu` 404。
- 流程：`/login/feishu` 跳 `accounts.feishu.cn/open-apis/authen/v1/authorize`（state + PKCE S256，签名 flow cookie 10 分钟）→ `/login/feishu/callback` 核对 state，服务端用 `authen/v2/oauth/token` 换令牌、`authen/v1/user_info` 取 `open_id`/`tenant_key`/姓名，飞书令牌不落库。已绑定且账号启用 → 发普通 `tmh_session`；未绑定 → 签名 `tmh_feishu_bind` cookie，回登录页提示用密码登录一次完成绑定；已经登录着 → 直接绑到当前账号。
- 边界：飞书不建账号、不授权，只能登进已用密码（或当前会话）证明过的账号；账号停用即失效；绑定记 `tenant_key`，登录时必须一致，可选 `TMH_FEISHU_TENANT_KEY` 只认指定企业（不符的在发绑定凭证前就拒）；已绑定的飞书身份不会被另一个账号改绑；绑定写 `access_audit` 的 `feishu_bind`。表 `feishu_identities(app_id, open_id, tenant_key, user, name, created)` 在 `tenancy.DDL`，启动时自动建。
- 飞书客户端里（UA 含 Lark/Feishu）登录页自动跳飞书授权，所以卡片按钮点开就是登录状态；`location.hash` 拼进 next，`#/t/JB-1` 这类链接登录后不丢。退出跳 `/login?out=1`，这一页不自动跳，避免退出后立刻被登回去。
- Devin Review 两轮：改绑、非本企业仍发绑定凭证、已登录时绑定提示被跳过、飞书内退出即重登 4 条已修；「HTTP 下 cookie 不带 Secure」不改（生产只走 HTTPS，`_scheme` 为 https 时带 Secure，与 `tmh_session` 同一规则）。
- 飞书开放平台：安全设置的重定向 URL 加了 `https://webuddy.bbstack.date/login/feishu/callback`。授权页只要「获取用户身份标识」一项权限。
- 发布：服务器上解出的包里 `test_tenant_gateway`、`test_login` 共 19 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，journal 无报错；生产 `/login` 有「用飞书登录」，`/login/feishu` 303 到飞书授权、`redirect_uri` 正确。
- 真实验证：在 Devin 的浏览器里（已登录 li、飞书已登录李逸斌）走了一遍，飞书授权后真实换到令牌和身份，走「已登录直接绑定」把 李逸斌 绑到了 `li`（`access_audit` 有 `feishu_bind`）。退出后点「用飞书登录」，在飞书授权页点「授权」后不输密码直接回到 li 的工作台（普通浏览器里飞书每次都显示授权页；飞书客户端内是否免确认还没验证）。还没在飞书手机/桌面客户端里点卡片验证自动登录。

## 2026-11-02 飞书登录改为本企业默认开户（PR #26，生产 dfb8688bf06a）

- 用户要求：权限系统接入飞书后默认绑定本企业飞书，权限不做复杂设计。配置了 `TMH_FEISHU_TENANT_KEY` 时，本企业的飞书成员第一次用飞书登录、且未绑定任何账号，就由 `feishu_login.provision()` 在同一事务里完成：建账号、加入 `default` 组织、写 `feishu_identities`、修订号 +1、记审计 `feishu_join`。
- 账号名依次试：飞书姓名去掉空白、`姓名-<open_id后4位>`、`fs-<open_id后10位>`，取第一个可用的。密码是随机哈希，不能用密码登录。
- 角色取 `TMH_FEISHU_ROLE`，默认 `member`，只允许 `member` 或 `viewer`，永远不会给 `admin`。项目权限仍由管理员在「成员与权限」里授予。
- 别的企业照旧在 `identity()` 里被拒。已绑定的身份不会被改绑。没配企业键时，仍按原来的方式先用密码绑定。
- 生产：`/etc/webuddy.env` 追加 `TMH_FEISHU_TENANT_KEY`，取值为已绑定的 李逸斌 身份的企业键（改前备份为 `webuddy.env.bak-pre-feishu-tenant-20261102`）。
- 发布：服务器上解出的包里 `test_tenant_gateway`、`test_login`、`test_tenant_policy` 共 47 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，journal 无报错；`/login/feishu` 303 到飞书授权。
- 在生产库副本上用发布包代码模拟（不写生产库）：本企业新身份自动开出 `测试成员`（default/member）；再登一次不重复开户；li 原有的绑定不变；别的企业被拒。还没有真实的第二位本企业成员登录过。
- CI：Ubuntu 全过；Windows full suite 在基线上同样失败（与本改动无关）。

## 2026-11-03 只有一个组织时界面不再出现租户（PR #28，生产 17cbbc305867）

- 用户飞书登录成功后指出：都用飞书了，界面上的「租户 / 平台管理员 / 默认组织」没有必要。只改前端显示，后端租户、成员关系、权限检查和接口都不动。
- `accessSingle(data)` = 租户数少于 2。成立时：
  - 顶栏 `#tenantScope` 不显示；
  - 「成员与权限」页隐藏「当前租户」「管理目标租户」，操作列表 `accessActionRows` 过滤掉 `tenant_*`，标题「当前租户成员」改为「成员」。
- 有两个及以上租户时界面照旧；之后要隔离第二家客户，仍可通过接口建租户，界面会自动恢复。
- 测试：`accessData` 夹具默认改成两个租户，原有走 `tenant_rename` 表单的用例按多租户场景跑，断言不变；新增 `test_single_tenant_hides_tenant_selector_and_tenant_actions`。
- 发布：服务器上解出的包里 `test_tenant_gateway`、`test_login`、`test_ui_access`、`test_tenancy` 共 83 个用例通过（UI 用例要把 `tests` 加进 PYTHONPATH）。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，发布后 journal 无报错。
- CI：Ubuntu 全过；Windows full suite 仍是同样的 141 个失败加 1 个错误，和 PR #26 时一致，没有 UI 用例失败。
- 定位（和用户对齐）：Webuddy 负责老项目的维护交付（需求 → AI 改代码 → 构建、独立诊断、浏览器实测 → 证据 → 验收关单 → 版本和回滚），不是通用的团队工作台。飞书负责身份和沟通入口。

## 2026-11-03 工单状态改成人话（第 1 步：只换显示文字）

- 用户认同「老系统的 AI 维护交付平台、以一次可验证交付为中心」的定位，但指出工单命名不够人类友好。样稿规则：标题在前、编号退后；状态写「谁 + 做什么」；内部术语换日常用词（验收标准→检查项、候选→预览版、合并主干→上线、证据包→测试记录、甲方→客户、智能体→AI）。
- 本次只改 `stage.TABLE` 及 `decide` 动态文字、收件箱分组 `G`、详情卡「重试上线」按钮和合并等待的事件/通知文字。阶段键、who/step、判定顺序和状态迁移都不变。
- 测试：`test_stage`、`test_workbench_states` 期望文字按新说法更新，断言结构不变；`test_stage`、`test_workbench_states`、`test_platform`、`test_workbench`、`test_ui_ticket_run_sync`、`test_repo_sync` 等通过。`test_platform::test_readiness_checks_the_real_machine_worst_first` 在改动前的基线上同样失败（本机环境，与本改动无关）。ruff 对改动文件的告警数与基线相同。
- 补充（PR #30）：CI 发现 `test_intake_recovery_api` 断言「已保存答复」，`recovering` 的文字改成「AI 正在按已保存答复补全检查项」。本机全量 2743 通过，只剩改动前就失败的 readiness 一项；CI Ubuntu 全过，Windows full suite 仍是基线上的 141 个失败加 1 个错误。
- 发布（生产 720bc43c1a90）：服务器上解出的包里 `test_stage`、`test_workbench_states`、`test_intake_recovery_api`、`test_repo_sync` 共 54 个用例通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0。

## 2026-11-03 主导航按「一次可验证交付」重排（第 2 步的第一部分）

- 顶部主导航从「工作台 / 项目 / 工单 / 团队协作 / 知识与记忆 + 管理：交付 / 客户 / 设置」改成「总览 / 需求 / 版本 / 项目知识 / AI 工作记录 / 成效 + 管理：项目 / 客户 / 设置 / 成员与权限」，对应样稿里的项目内标签。
- 只改 `NAV`、`navOf`、`navCurrent`、管理区和 `paintTabs` 的分组与文字；路由一个没删，旧链接（`#/team`、`#/atlas`、`#/kb`、`#/versions`、`#/overview`、`#/eff` 等）照常打开，并高亮到新归属（团队协作 → 需求，图谱/架构 → 项目知识，版本 → 版本，监控/提效 → 成效）。「项目工具」改名「更多」，团队协作移进「更多」。
- 成员与权限仍按 `can_manage` 显示；后台、权限检查、阶段判定和验收闸门都没动。
- 测试：`test_ui_navigation` 的路由表补上新分组（team 现在归到需求），断言结构不变；`tests/test_ui*.py` 与 `test_workbench` 共 308 个通过。
- 发布（生产 08cc9923dff4）：服务器上解出的包里 `test_ui_navigation`、`test_stage`、`test_workbench_states` 共 29 个通过。发布检查：MANIFEST_OK、两个库 integrity=ok、running_runs=0、本机和公网 /login 200、/api/projects 401、NRestarts=0，发布后日志没有报错。CI Ubuntu 全过，Windows full suite 仍是基线失败。

## 2026-11-03 新建项目：Git 地址或上传 zip 导入代码，导入后直接进入建知识库

- 用户要求收窄为：好用的界面提交项目代码（Git 之外还要能手动传 zip）→ LLM 分析、建知识库 → 提需求 → 看能否改对代码。原来「新建项目」只能填服务器上的绝对路径。
- 新增 `tmh/platform/project_import.py` 与 4 个接口：`POST /api/projects/import`（source=git|zip）、`POST /api/projects/import/<job>/chunk`（base64 分片，单片 ≤3 MB，避开网关 5 MB 上限）、`POST /api/projects/import/<job>/finish`、`GET /api/projects/import/<job>`。目录由平台决定：`<data>/repositories/<KEY>`，请求字段不会变成路径或命令。
- Git：只收 https:// 与 ssh 地址，禁 file/ext 协议、不拉子模块、不弹密码；地址里的令牌只用于拉取，保存和 origin 都去掉。zip：拒绝越界路径，丢弃 .git、符号链接和 __MACOSX，限 1 GB / 解压 4 GB / 30 万个文件，失败不留目录；解压后新建 Git 基线提交。导入在后台线程跑，状态写在 `<data>/project-imports/<job>/state.json`。
- 租户策略：4 个接口进清单（181 条），写操作按工作区配置处理，需平台管理员且目标在批准目录内；查询状态只给管理员。Agent 身份不能发起导入。
- 界面：「新建项目」改成 Git 仓库 / 上传 zip 两种方式，自动从地址或文件名猜代号；显示上传百分比和后台步骤；完成后给出「开始分析代码、建知识库」，进入项目的知识库建设引导（已有的图谱 + 智能体写业务说明流程）。原来的「登记服务器目录」保留为对话框里的次要入口。
- 测试：新增 `test_project_import`（zip 导入成 Git 项目且不带上传的 .git/链接、越界失败不留痕、分片顺序和发起人校验、Git 地址校验和去令牌）、`test_tenant_policy` 补拒绝用例、`test_ui_library` 补 zip 分片上传到进入知识库的界面用例。本机起服务实测：zip 导入 DEMO、Git 导入 octocat/Hello-World 都完成并登记。

## 2026-11-03 导入的项目自带 tmh 项目工具；记录需求默认选当前项目

- 生产走查 PETS（spring-petclinic，Git 导入，128 个文件）时，知识页 run 330 写出了内容，但智能体找不到 `tmh`，没通过 `tmh kb done`，survey 正确记为未完成。原因：JB 的 `.tmh/tool/tmh.py` 是早先手动 `tmh install` 的，Git/zip 导入的项目没有。
- 修复：`tmh/install.py` 抽出 `vendor_tool(repo)`（install 第 1 步原样复用；从仓库内的 vendored 工具重装时不删自身）。`project_import._guard` 在登记前调用它，并把 `/.tmh/` 写进导入仓库的 `.git/info/exclude`，代码基线保持干净；zip 里自带的 `.tmh/tool/` 一律丢弃，工具只用平台自己的。
- 记录需求弹窗：非跨项目视图里默认选顶栏当前项目（`S.proj`），不再沿用跨项目视图残留的筛选（走查时顶栏是 PETS，弹窗默认 JB）。
- 验证：`tests/test_project_import.py`、`test_distribution.py`、`test_tmh.py`、`test_integrations.py` 72 passed；`tests/test_ui*.py` 305 passed；ruff 通过。

## 2026-11-03 测试机上项目克隆的 HEAD 跟着工作副本走（PETS 构建读不到 git 信息）

- 现象：PETS-1 重查时测试机上基线构建 197 秒后失败，`git-commit-id-maven-plugin:9.2.0:revision` 报 `Could not get HEAD Ref`，`dotGitDirectory` 指向 `C:\tmh-runner\repos\PETS\.git`。
- 原因：没有公开 https 源的项目，测试机上的克隆是 `git init` + 拉 bundle 的 `refs/tmh-send/*`，主仓库 HEAD 一直是未出生的 `refs/heads/master`；工作副本 `work/PETS` 是它的 worktree，JGit 经 commondir 读主仓库 HEAD，于是失败。JB 同样是未出生 HEAD，只是没用这个插件。
- 修复：`TestBox.prepare` 切换工作副本时同时 `git -C repos/<项目> update-ref --no-deref HEAD <基线>`，克隆自己的 HEAD 与工作副本一致。测试机上已先手工把 PETS 的克隆 HEAD 指到基线，未改动代码 `mvn -B -q compile -DskipTests` 61 秒通过（退出码 0）。
- 验证：`tests/test_testbox.py` 新断言（无修复时失败）；testbox/fixloop/recheck 相关 222 个测试中只有两个与本改动无关的已有失败（`test_recheck_summary` old_proof 未改动时同样失败；`test_team_workspace` 本机 Node 太旧不支持 `?.`）。
- 发布：生产 `8a04344decb3`（PR #36）。服务器上用发布包跑 `tests.test_testbox`、`tests.test_project_import` 14 个通过；manifest、两个库完整性、running_runs=0、本机/公网 HTTP、NRestarts=0 均正常。生产上 PETS-1（run 339）重新验证：原代码 `mvn -B -q compile -DskipTests` 16.7 秒通过，带改动 15.3 秒通过，结果「重新验证：通过」。PETS 旧的失败基线缓存移到 `/opt/webuddy/backups/pets-checks-githead-20261103/`，没有删除。

## 2026-11-03 测试机连不上时，不再记成「构建没通过」；只通过 Webuddy 复验测试机修复

- 用户要求：只验证 Webuddy，不直接改项目和测试环境。于是把手工改过的 PETS 克隆 HEAD 改回未出生的 `refs/heads/master`，旧的基线缓存移到 `/opt/webuddy/backups/pets-checks-revert-manual-20261103/`，然后只在 Webuddy 界面上点「重新验证本次改动」（PETS-1，run 339，重新验证记录 #3）。
- 结果：生产 `8a04344` 自己把克隆 HEAD 指到了基线 `500158f`，原代码 `mvn -B -q compile -DskipTests` 16.1 秒通过，证明 PR #36 的修复确实生效，不依赖手工。带改动那一步在传代码时 `scp: Connection closed`（setup，退出码 -2），平台却显示「重新验证：构建没通过」，`verify.check=fail`。
- 测试机连不上的原因：生产机上的 frps 把 12022 端口开放到公网，104.105.159.113 从 20:42 起向它发起约 1.5 万次连接（每分钟 160 次左右），Windows 的 sshd 被挤爆，正常连接也被断开。已在生产机加 iptables：12022 只允许本机（lo 和 43.153.76.85）访问，其余丢弃；之后该来源 0 次连接，测试机恢复可达。规则没有持久化，重启后会失效。
- 修复：新增 `fixloop.handover_failure`。代码根本没送到测试机（setup 失败）时，修改轮和重新验证都按「测试机没准备好（…）」处理，记 `check=skip`，不算构建失败；修改轮不会拿连接错误当编译错误回炉。`fix_gate` 遇到这种 skip 一律留给人或等重新验证，不会无构建自动提交；AI 验收本来就要求 `check=pass`，规则不变。

## 2026-11-03 发布：测试机没准备好不再记成构建没通过（`ed3d4f6`）

- [PR #38](https://github.com/auntunt/webuddy-pitch/pull/38) 合并后发布到生产：`/opt/webuddy/releases/ed3d4f6c1891-testbox-setup-not-build-20261103/app`，备份 `/opt/webuddy/backups/pre-ed3d4f6c1891-activation-20261103`。发布前服务器上用发布包跑 `tests.test_testbox tests.test_project_import tests.test_recheck_publication tests.test_run_handoff` 36 项通过；running_runs=0；两库 `integrity_check` ok；本机/公网 `/login` 200；NRestarts=0；日志无报错。
- CI：Ubuntu 两项全量通过。Windows 两项全量失败，但合并前的主线 `3cc9365`、PR #36、PR #37 的 Windows 全量同样失败（主线 py3.11 164 failed，本 PR 141 failed，集中在 learning 与 Windows SQLite 文件占用）；本 PR 失败里的 3 个 `test_platform` 用例本机单跑通过。
- 只经 Webuddy 界面验证（未改 PETS 代码、仓库 HEAD 或测试机项目状态）：PETS-1 运行 #339 点「重新验证本次改动」，重新验证记录 #4，22:49:33–22:50:15，测试机 `mvn -B -q compile -DskipTests` 14.2 秒通过，结果「重新验证：通过」。历史记录 #3 保留为 `kind=setup`「把改动传到测试机」exit -2（scp Connection closed），不再算构建失败。
- 生产主机同日重启：`webuddy-guard.service` 开机加回 12022 白名单与 104.105.159.113 封禁；factory 控制台按用户决定不恢复。

## 2026-11-03：业务状态图页与项目知识页统一样式

- 用户看过 pstack/poteto 思路的样稿后要求：状态图顺应 Webuddy 自己的风格而不是另起主题，其他知识页一同调整，然后审查。
- 新增「项目知识 → 业务状态图」（`#/states`，`ui_states.py`）：每个业务域一张状态图，用 Pele（MIT，`tmh/platform/vendor/pele.global.js`，只在这一页通过 `/ui/pele.js` 按需加载）渲染；右侧是规则（`文件:行号`）、走到问题的编号路径（蓝色虚线，打破规则的状态红框）、依据。颜色全部取 `ui_theme.py` 的令牌。
- 数据：智能体用新运行模式 `chart`（画业务状态图）写 `.tmh/knowledge/statecharts/<域>.json`；`statecharts.py` 只读回、校验格式（必须 stateDiagram、路径状态必须在图里、路径必须指向规则），路径会把对应规则标成未守住；图里写的提交之后、规则引用的文件有改动时标「代码改了，这张图要重看」。智能体不能把图标成已确认，一律「待确认」。
- 业务与代码图谱从深色主题改为浅色产品令牌；统计口径改为「被业务流读写的表」「业务流已写说明」，避免和架构依据的「数据库表 9 张」看起来对不上。项目知识首页、知识页、架构依据本来就用产品令牌，本轮审查未改。
- 本地验证：`tests/test_statecharts.py` 5 项；本地演示数据导入 spring-petclinic，手写一份示例状态图（仅本地演示数据，不进仓库、不进生产项目）截图核对 `#/memory #/kb #/atlas #/states #/map #/library`，哈希切页无前端报错。`test_platform::test_readiness_checks_the_real_machine_worst_first` 在未改动的基线上同样失败（本机 git 检查为 warn），与本批无关。
- 未验证：真实智能体在 `chart` 模式下画图的质量（本 VM 没有 Claude/Codex 可执行文件）；生产上需由人点「让 AI 画状态图」后才会有图。

## 2026-11-03 发布：业务状态图（`b88ef1d`）与租户入口补漏

- [PR #40](https://github.com/auntunt/webuddy-pitch/pull/40) 合并后发布：`/opt/webuddy/releases/b88ef1d4f4ff-statecharts-20261103/app`，备份 `/opt/webuddy/backups/pre-b88ef1d4f4ff-activation-20261103`。服务器上用发布包跑 `test_statecharts test_platform test_memory_workspace` 92 项、`test_ui_memory` 16 项通过（首轮 `test_ui_memory` 因 tests 目录不在 PYTHONPATH 导入失败，补路径后通过）；running_runs=0；两库 integrity ok；本机/公网 `/login` 200；NRestarts=0；日志无报错。
- 勘误：上线后在生产租户入口 `/t/default/` 打开业务状态图，`/api/projects/PETS/statecharts` 和 `/ui/pele.js` 均 403。原因：租户策略 `tenant_policy.API_ROUTES` 是冻结清单，新路由没登记；`/ui/pele.js` 是脚本标签请求，带不上 `X-Webuddy-Context`。本地验证漏跑了 `tests/test_tenant_policy.py`（其清单测试会直接失败）。
- 修复：渲染器改为项目读接口 `GET /api/projects/<key>/statecharts/renderer`（返回 `{js}`，页面用带上下文头的 `get()` 取回后注入），删掉 `/ui/pele.js`；两个路由登记进 `API_ROUTES`，清单数 181→183。业务与代码图谱新样式在生产已核对正常。

## 2026-11-03：生产 PETS 首次由 AI 画业务状态图

- 运行 #348（PETS 无执行器路由，按默认走 `claude`，即 aixoras 上的 Claude Code）23 秒失败：上游 403「预扣费额度失败，剩余 $0.09」。用户说明应该都用 Codex。生产 `agent-routes.json` 为 PETS 加路由 `agent: cloudwave-codex`（原文件备份 `/opt/webuddy/backups/agent-routes.json.pre-pets-codex-20261103`）。JB 仍是 `analyze/plan/diagnose → claude`，其余步骤 Codex，未改，待用户决定。
- 运行 #349（cloudwave-codex）39 秒完成，基于 `500158f` 写出 `owner/vet/system` 三张图，平台校验 0 问题；owner 8 条规则、vet 2 条、system 0 条；没有问题路径（AI 说明找不到能具体指出的规则突破）。只写了 `.tmh/knowledge/statecharts/`。
- 显示修正：大图原来被缩成看不清，小图被放得过大；改为缩放限制在 0.85–1.3，放不下就滚动。没有规则的图不再显示 ✓。

## 2026-11-03：生产执行器全部改为 Codex

- 用户决定「都换成codex」。生产 `agent-routes.json`：去掉各项目 `steps`（原 CWWEB/GROUPRISK/JB/PPTAUTO/WEIGHBILL 的 analyze/plan/diagnose → claude），各项目 `agent` 统一为 `cloudwave-codex`，并加 `default: {agent: cloudwave-codex}`，没有登记路由的项目（OFBIZ、RW、以后新导入的）也走 Codex。`direct_api` 未改。备份 `/opt/webuddy/backups/agent-routes.json.pre-all-codex-20261103`。路由每次运行时读取，无需重启；修改时 running/queued 运行为 0。
- 核对（`agent_routes.resolve` + `step_agent`，8 个项目 × analyze/plan/fix/edit/diagnose/kb/chart/ask）：全部为 `cloudwave-codex`。
- 影响：`fixloop` 在诊断与修改同一执行器时，不跑构建的小改动不再做只读诊断复查（原来因诊断交给另一个执行器而保留），直接留给人；跑构建的改动照常诊断。AI 验收本来就要求构建通过，不受影响。

## 2026-11-03：只改页面模板的改动也能在浏览器里实测

- 问题：PETS-2/PETS-3 只改了模板和文案，平台不跑构建，也没有页面实测；`browser_verify` 只由 AI 验收调用，且驱动脚本写死 JeecgBoot 前端（vite + 验证码登录）。
- 改动：`verify-hosts.json` 的项目可以写 `repo`（实测机上的检出目录，相对家目录，默认 `pv/base`）和 `start`（启动命令，拿到 `$PORT`、`$PFX`）；写了 `start` 就运行它，不走 vite，等待启动最长 900 秒。没有 `yml` 时 `login()` 只打开首页。项目第一次用到的实测机目录会自动 `git init`，再由 bundle 带上完整历史。
- 新接口 `POST/GET /api/runs/<rid>/page-check`（已登记租户策略，路由数 185）。运行详情页的「试用本次改动」里多了「在页面上实测」按钮，结果按检查项逐条显示，截图附在工单证据里，署名「页面实测」。它只记录证据，不验收也不关单。检查项优先取签收快照，没有时取方案里的。
- 实测机（WSL）：新建 `~/.m2/settings.xml`，镜像指向阿里云（Maven Central 在那里连不通）。
- 生产首次从界面实测 PETS-2（运行 #343），结果是「没有找到要在页面上实测的检查项」：PETS-2 的方案输出里没有 `tmh-plan` 块，签收快照也是空的，而客户检查项（7 条）只存在 `signoff.client_ac` 里。现在检查项依次取签收快照、客户检查项、方案，和 `signoff`、`fixloop.criteria` 的取法一致。
- 再次实测 PETS-2 时报 `ValueError`：写实测脚本的 `_ask` 在路由里找不到 diagnose 步骤（执行器统一改成 Codex 后已经删掉），于是退回到 autoflow 的 `codex`，而这个执行器不在路由的允许列表里。JB 的 AI 验收实测也会因此失败。现在没有 diagnose 步骤时，改用 `agent_routes.resolve` 给出的项目执行器；实测没跑完时，原因直接写出异常信息。
- 第三次实测 PETS-2：Codex 写好了脚本（运行 #350），bundle 也送到了实测机，但 Spring Boot 启动失败。git-commit-id 插件报错 `Could not get HEAD Ref ... /home/auntu/pv/PETS/base/.git`，因为平台新建的检出只拉了 bundle，HEAD 还是空的（和 Windows 测试机上那次是同一类问题）。驱动现在会在 HEAD 为空时把它指到被测的基线。另外，等待启动期间应用进程退出了，就立刻结束并报「app exited before it was ready」，不用再白等 900 秒。
- 第四次实测 PETS-2：Spring Boot 起来了，Playwright 也跑了，但三条检查项都报 `TypeError: Cannot read properties of undefined (reading 'replace')`。原因是 AI 写的脚本调用了 `shot(page, '步骤名')`，少传了 testInfo。`shot()` 现在兼容这种写法，自动用 `test.info()` 补上。
- 第五次实测（PETS-2 运行 343、PETS-3 运行 347，都从界面发起）：两个应用都起来了，也都截到了图。
  - PETS-2：A1（详情页不再显示 Add New Pet）、A2（详情页其余内容保留）都通过。A3 没能证明：脚本把列表页的标题写成了 Find Owners，实际是 Owners。
  - PETS-3：判了 fail，但这是**误判**。截图上「Pet Count」列和每行的数量都在，失败的是脚本里的 `getByRole('columnheader', { name: 'Pet Count' })`。实测机的 Playwright 1.48.2 和升级后的 1.56.1 都把没写 scope 的 `<th>` 识别成 `cell`；本机 1.64 识别成 `columnheader`。
  - 两次修复脚本的步骤都没交回脚本。PETS-3 那次，修复的 AI 拿仓库里还没改的代码去对照，断定「确实没做到」。原因是 `repair_prompt` 没带改动，仓库目录里也还没有这份改动。
- 本次修复：
  - `repair_prompt` 带上候选改动（只在验证基线加改动、还没提交时带），说明仓库目录里还没有这份改动，并要求不管改没改都交回完整脚本。
  - 定位器没找到、但失败时的页面内容里有它要找的文字：记为「没能证明」，并交给修复脚本那一步，不再判 fail。页面里真没有这段文字的，仍然判 fail。
  - SPEC_RULES 加了一条：表格里的文字用 `getByText` 找，不依赖 `columnheader` 角色。
  - 实测机 `~/pv/verifier` 的 `@playwright/test` 从 1.48.2 升到 1.56.1。浏览器 chromium-1194 原本就缓存在机器上，没有重新下载。升级后失败时能拿到带角色的 `ariaSnapshot`，之前只能拿到摊平的页面大纲。旧的 package.json 和 lock 备份为 `*.bak-1.48.2`。
- [PR #49](https://github.com/auntunt/webuddy-pitch/pull/49) 发布到生产（`e30e870`）之后，从界面重跑了 PETS-2、PETS-3：
  - PETS-3（运行 347）：A1 **通过**，3 张截图。脚本改用了 `table.getByText('Pet Count', { exact: true })`，并逐行核对「Pet Count」列的数字等于 Pets 列里的宠物个数。
  - PETS-2（运行 343）：「没有写出实测脚本」，12 秒就结束了（运行 357）。Codex 在只读沙箱里跑 `tmh flows get-owners-ownerid`，这个命令要往 `.tmh/flows.json` 写缓存，写失败就报错退出了，Codex 随后放弃，没写脚本。
- 本次修复：
  - `cli._load_flows`：`flows.json` 只是缓存，写不进去就跳过，只读检出里照样能返回结果。
  - `verify`：AI 回复里没有脚本时，再问一次，并提示它按工单和改动来写；第二次仍然没有，才记「没有写出实测脚本」。
- [PR #50](https://github.com/auntunt/webuddy-pitch/pull/50) 发布到生产（`6f72a29`）后，从界面重跑了 PETS-2（运行 343）：A1、A2、A3 三条都**通过**，分别有 1 / 4 / 2 张截图。加上 PETS-3（运行 347）A1 也已通过，两张只改页面模板的单现在都由 Webuddy 自己在真实应用里逐条实测通过。两张单仍停在等人确认，没有替人验收或关单。
  - 发布时的问题：服务器上用发布包跑测试那一步，`test_python_flows` 有 5 个报错，原因是 verification 包里没有 `docs/self-improvement/evidence/runtime-2026-10-18/bootv2` 这批测试样例。命令写的是 `... | tail -2 && activate`，管道的退出码只看 tail，所以测试报错也照样激活了。其余 82 个测试全部通过，本次改动的测试就在其中。以后这一步要加 `set -o pipefail`。
- 产品对外名称改为「网梯运维系统」（用户 11/4 要求，用于给客户录屏的演示）。
  - 界面里写死的默认名称、工具连接页、侧边栏助手的提示词，都改成了这个名字。
  - 组织入口（tenant_gateway）原来固定显示 webuddy，现在跟单机版一样读环境变量 `TMH_BRAND`。
  - 生产 `/etc/webuddy.env` 里的 `TMH_BRAND` 改为「网梯运维系统」。
  - Git 提交作者、域名和内部代号不变。
  - 本机 node 是 v12，`tests/test_ui_access.py` 在本机跑不了，和这次改动无关。
- 新增「上生产申请」（演示脚本第 ⑤ 段：验证环境验收 → 申请上生产 → 人工确认）。
  - 原来「上线」只到合进主干、打版本号；发到客户生产这一步没有记录，也没有人工确认节点。
  - 版本页每个版本多一行「生产」状态：申请（必须写在验证环境里看过什么）→ 批准 / 驳回（驳回要写原因）→ 部署。
  - 部署：项目在 autoflow.json 的 `prod_deploy` 里配了命令，批准后自动执行并记下输出；没配，就由人点「登记已部署」。
  - 每一步都必须是个人账号操作（`_human_action`），追加记录到 `<data>/versions/prod-requests.jsonl`，并写进版本所含每张工单的时间线，事件为 `prod_request`、`prod_approve`、`prod_reject`、`prod_deployed`、`prod_failed`。
  - 租户入口：批准和驳回需要 manager 权限。
  - 新增路由已登记到 `tenant_policy`（共 187 条）。
- 新增「执行中插话」（演示脚本第 ③ 段）。原来只能等运行结束后，在讨论里补一句再重跑。
  - 运行详情页：运行进行中时，日志下方有输入框。调用 `POST /api/runs/<rid>/say`（必须是个人操作；受管实验的运行不行；已结束的运行返回 409），写入的地方：
    - `<data>/runs/<rid>/notes.md`；
    - 运行日志里的「— X 插话：…」；
    - 工单时间线（事件 `steer`）。
  - 执行器拿到环境变量 `TMH_NOTES`。analyze / plan / fix / understand / chart / kb 这几类运行的首轮提示词带 `agents.steer_hint`：开始时和每一步之前 `cat "$TMH_NOTES"`，按最新的话调整，并在最终回复里写明怎么处理的。重试轮和续接会话不再追加这段。
  - `tests/test_platform.py::test_readiness_checks_the_real_machine_worst_first` 在改动前的基线上同样失败，属于本机环境问题，跟这次无关。
- 新增「客户 → 项目 → 系统」三级归档（演示脚本第 ① 段）。原来只有客户和项目两级，项目又只是一份代码库，同一份标品私有化部署给不同客户，没地方区分是哪一套。
  - workbench 增加 `systems` 表（`project + name` 唯一）和 `system_links` 表（`kind = intake | ticket`）。
  - 工单 `links.system` 存所属系统；`store.update_ticket` 像保留 client 一样保留 system，除非显式传 `drop_system`。
  - `sync` / `_inherit`：从需求对话建出来的单、大需求下的子单，自动跟着归到同一个系统。
  - 新增接口：
    - `GET /api/projects/<key>/systems`、`POST /api/projects/<key>/systems`：列出 / 登记系统；
    - `POST /api/tickets/<key>/system {system}`：给工单设置或取消系统。系统不属于工单所在项目时返回 409。
  - `/api/workbench/intake` 接受 `system`；也接受 `system_name`，没有同名系统就新建。
  - 界面：
    - 「记录需求」窗口多一个「系统」下拉；
    - 工单顶部显示「客户 / 项目 / 系统」，系统可以直接改；
    - 客户页多一块「项目与系统」，能登记新系统；
    - 需求列表和客户页的需求行带上系统名。
  - 租户策略增加 3 条路由，共 191 条。测试：`tests/test_systems.py`。
- 运维工单增加排查（演示脚本第 ⑥ 段）：`tmh/platform/ops_diag.py`，提供 `GET` / `POST /api/tickets/<key>/ops`，类型为「运维」的工单详情页多一张「运维排查」卡。
  - 相似经验：用 `similar.py` 在本项目的经验卡（已采用 / 候选 / 观察期）里找。相似工单会带上它们当时记下的排查结论。
  - 只读查数据：数据源只能由服务器管理员在 `<data>/datasources.json` 里配置，界面上不能改，支持 sqlite 和 postgres。
    - 只允许一条 SELECT / WITH 语句，含写入或改结构关键字的一律拒绝；
    - sqlite 用 `mode=ro` 打开并设 `query_only`，postgres 在只读事务里执行；查询限时 10 秒，最多返回 200 行；
    - 每次查询，包括出错的，都写进工单时间线（`ops_query`）。
  - 记结论：原因分数据、配置、使用、环境、需要改代码几类，写入 `ops_conclusion`。记结论不会改工单状态，也不会替人关单。
  - 原因不是「需要改代码」并勾选沉淀时，生成 `kind=ops` 的经验候选，`fix` 里写明不改代码。候选要人工在知识页采用后才生效。
  - 租户策略增加 2 条路由，共 193 条。测试：`tests/test_ops_diag.py`。
