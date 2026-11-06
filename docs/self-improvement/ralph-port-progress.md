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
- 在生产界面实测 ①③⑤⑥ 时发现三个界面问题，已修：
  - 运维排查里被拒绝的只读查询，错误提示原来是黑字，改成红字（`role=alert`）；
  - 工单上「自动处理中」的标签原来只看 `autoflow.on` 是否为真；`on` 是项目列表时，PETS 这类不在列表里的项目也被标成自动处理。现在按项目判断；
  - 需求对话里全是咨询的，原来仍显示「确认，建单」，点了返回 409。现在改为提示「已直接答复，不用建单」，按钮换成「结束对话」。
  - 运行页的「插话」输入框原来会在日志刷新时连同草稿一起被清掉，实际上没法打完一句话再发。现在刷新时保留草稿、焦点和光标位置，回车也能直接发送。
- 在工单页（`#/t/<KEY>`）打开「记录需求」时，项目默认取这张工单的项目。原来取的是顶栏的全局范围，在 PETS-6 上打开会默认选成 JB。运行页实时日志原来会把同一段输出显示两遍：两次轮询都带着同一个 `since` 并发发出，两次的结果都被追加到页面上。数据库里只存了一份，重新打开就只剩一条。现在按 `output_len` 算出这段输出从哪里开始，只追加 `since` 之后还没显示过的部分。
- 完整验收准备时发现：项目开成全自动后，新建的运维工单（`type=ops`）也会被自动线受理，进入分析、方案、修改和 AI 验收，和「运维单只排查、不改代码、不自动关单」冲突。现在 `Orchestra._intake()` 遇到运维单只记一条说明就返回，`next_step()` 对运维单也不再给出下一步，「交给自动处理」的等待队列因此不会收它。测试：`tests/test_ops_diag.py::test_auto_line_leaves_ops_tickets_alone`。
- 完整验收里 PETS-8 自动跑完方案和修改，构建也通过了，但 AI 往已有的 `VetControllerTests.java` 里加了一条断言（标题文字），被「改了已有测试或受保护文件」规则拦住，没有自动提交。规则本身没改；方案和修改的提示词改为：已有测试只在不改就会失败时才动，不为给新行为补断言去改已有测试。
- 完整验收续测：PETS-8 重新出方案（#372）后交回自动线，修改 #373 只动了 `vetList.html`，平台自动提交，但 AI 验收停在「没跑构建测试」：`testbox.build_commands` 只为 Java / 带类型检查的前端安排构建，Maven 模块里的页面模板一律跳过。用户选择改平台：
  - `build_commands`：`src/main/resources/`、`src/main/webapp/` 下的页面文件（模板、静态文件）也编译所在的 Maven 模块；
  - `ai_accept.after_commit`：改动全是页面文件（`testbox.page_only`）而项目没配页面实测时，留给人验收（编译只能证明能打包）；配了页面实测的，照旧要求每条验收标准在页面上实测通过才签收。
  - 测试：`tests/test_testbox.py::test_a_page_template_compiles_its_module_and_counts_as_page_only`、`tests/test_ai_accept.py::test_a_page_only_change_needs_page_checks_to_be_signed`。
- 完整验收再测（`a1ad736`）：模板子单 PETS-11 的修改 #377 已经真跑了 Maven 编译，但诊断 4 轮都判不通过，原因是「没有浏览器实测和截图」「没有部署记录」。页面实测要等改动提交后才跑，诊断却在提交前就要页面证据，顺序上永远满足不了。现在项目配了页面实测时，诊断提示里会多一段「之后还有页面实测」：读代码确认不了的页面效果写 unverified，不因缺页面实测、截图、部署记录判不通过；阻断项仍然只写代码层面的具体失败场景。AI 验收仍要求每条标准在页面上实测通过。测试：`tests/test_agent_routes.py::test_with_page_checks_the_diagnosis_is_told_they_come_after_the_commit`。
- 完整验收再测（`2a4ad3d`）：PETS-11、PETS-12 由 AI 签收了，但 PETS-12 的 A3–A6 这几条必须保持项只靠「测试机上构建通过」。PETS 只编译（`-DskipTests`），test 门是未知；签收文案却写的是「构建测试通过……在页面上逐条实测 6 条」，说多了。已改：
  - 项目没跑自动测试，或者这次只改了页面文件时，必须保持项也要在页面上实测，不再拿构建结果代替；跑过自动测试的仍由测试证明；
  - 签收文案照实写：「构建通过（这个项目没跑自动测试）」「页面逐条实测 N 条」「必须保持项由自动测试证明」，以及「证据包里还缺：…」；
  - 页面没证明的原因会把漏测的条目都列出来。
  已签收的 PETS-11/12 记录不动，报告里逐条写明每条是怎么证明的。测试：`tests/test_ai_accept.py::test_what_must_keep_working_is_proven_by_the_tests_or_else_on_the_page`。
- 完整验收再测（`61c0de4`）：通过「记录需求」建的运维单 PETS-13，AI 理解时追问了正确金额。追问已经在对话里答了，但 A1 仍记为待确认，于是：
  - 时间线写的是「有验收标准还待确认……答复回来就自动开始」。运维单本来就不会自动改代码，这句话会让人误会。
  - 头部报「客户答复已保存，AI 没理解完……缺少原失败运行绑定」。原因是旧记录兼容逻辑 `_recovery_recipe` 把「对话中答过、首次理解成功」当成了「再理解失败」。
  修复：
  - 带待确认标准的运维单写 `OPS_NOTE`，并注明「还有验收标准待和客户确认」；
  - 首次理解成功、也没有失败原因时，不再按旧记录构造恢复包。
  测试：`tests/test_intake_recovery.py::test_answers_given_while_talking_after_a_good_reading_are_not_a_stuck_recovery`、`tests/test_ops_diag.py::test_an_ops_ticket_with_open_criteria_does_not_promise_to_start_on_the_answer`。`test_stage`、`test_intake_recovery_ui` 里的 JS 用例因为本机 node 版本旧（不支持 `??`），改动前就失败。
- 完整验收续测（`f884d95`）：PETS 每步人工时，用「新建工单」直接建的运维单 PETS-14 没有任何运行，头部却显示「排队中」。原因有两个：
  - `stage.compute` 用全局 `bool(conf["on"])` 判断自动处理，只要别的项目（JB）开着，PETS 也算开；
  - 运维单本来就不进自动线，却也落到 `queued`。
  修复：
  - 自动处理改按项目判断（`Orchestra.switched_on`）；
  - 没有运行的运维单显示新阶段 `ops`「运维排查：查相似经验、只读查数据、记结论」，卡片指向下方的「运维排查」。
  测试：`tests/test_stage.py::test_an_ops_ticket_waits_for_ops_not_the_automatic_line`。`test_platform.py::test_readiness_checks_the_real_machine_worst_first` 在改动前就失败，与本次无关。
- 完整验收续测（`5265850`）：在运维单上执行只读查询后，查询结果很快就消失了。原因是每次查询都会写一条时间线事件，工单页随之重绘，`opsDiag` 被重建，输入框和结果都清空。修复：按工单把 SQL、结论草稿和最近一次结果保存在 `S.opsKeep`，重绘时恢复。测试：`tests/test_ops_diag.py::OpsDiagUiTest`。
- 完整验收续测（`5d5513f`）：在 PETS-16 的只读分析（#388）中插话「错误提示用中文：生日不能早于1990-01-01」。toast、日志和时间线 steer 都只出现一次，但 AI 的最终回复没有遵循这句话。查了原始输出：AI 一共跑了 5 条命令，每条之前都 `cat "$TMH_NOTES"`；插话在 04:00:34 写入，那时 AI 已经跑完最后一条命令、正在写最终回复，所以没有读到。当时平台不会提示，人会误以为 AI 收到了。修复：`Timing` 记下 AI 最后一次读 notes 时文件有多长；运行结束后，比这更晚写进来的插话会进日志，并在工单时间线上记一条 flow「插话没被读到……请写进工单讨论再让 AI 接着做」。同一次运行的重试共用 `notes.unread` 标记，同一句话只提示一次。测试：`tests/test_run_steer.py` 新增 2 条；相关的 129 条测试通过，跳过了已知的 readiness 基线失败。

- 2026-11-04 补：CI 全量里 `test_run_recovery_ui.py::test_stopping_toast_is_a_request_not_a_claim_of_cleanup` 自 PR #57（插话草稿保留，`paint()` 读 `document.activeElement`）起就在 node 测试壳里报 `document is not defined`，停止后的重绘被吞掉。测试壳补 `document={activeElement:null}`（与 `test_ui_ticket_run_sync.py` 一致），断言不变；本机 41 条相关 UI/插话测试通过。

2026-11-04 补：PR #66（插话在 AI 最后一次查看之后才到时，运行结束在日志和工单时间线说明「插话没被读到」，`notes.unread` 防重复，不自动重跑）合并后上线生产 `f5a2250`。新增的真跑执行器测试在非 POSIX 上跳过（同 `test_agent_profiles`）；Windows 全量套件在基线上本来就失败（大量 Windows 环境问题），ubuntu 全量两版通过。发布前服务器用发布包跑 15 组相关测试退出码 0；备份 `/opt/webuddy/backups/pre-f5a2250af61a-activation-20261104`，两库 integrity=ok，切换时 running_runs=0，login 200、未登录 /api/projects 401，NRestarts=0。插话未读提示尚未在生产界面上用真实运行复测。

2026-11-04 补：工具连接页直接给出连接步骤（PR #68，上线生产 `482e3eb`）。创建前常驻「怎么连接」和 `/t/<租户>/tools/client` 客户端下载（`tool_client.py` 现生成 wheel，只含 CLI + stdio MCP 桥，`mcp<2,>=1.30`，入口 `webuddy`；只认本人网页会话，工具令牌 403）；创建后按连接范围给出导入、`status`、Codex/Claude Code/Cursor 配置命令，命令不含令牌。发布前服务器用发布包跑 4 组相关测试 68 条通过；备份 `/opt/webuddy/backups/pre-482e3eb1bdaf-activation-20261104`，两库 integrity=ok，running_runs=0，login 200、未登录 401，NRestarts=0。生产实测：LYB 下载 wheel、干净 venv 安装、`connect --stdin`、`status`、`config codex --read-only`，再用 MCP SDK 按生成的配置连上，`list_tools` 13 个，`webuddy_projects_list` 只返回授权的 RW。验证建的 4 个 LYB 临时连接均已撤销；li 的「我的codex电脑」未动。

## 2026-11-04 下载的客户端记住服务器（PR #69，生产 5116edb）

- 问题：从工具连接页下载的客户端，不带参数直接运行时去连 `http://127.0.0.1:8791`，服务器部署时用户无从下手。
- 修复：`/t/<租户>/tools/client` 下载时把 `<对外地址>/t/<租户>` 写进 wheel 的 `tmh/workbench_site.json`。直接运行 `webuddy` 会显示服务器地址和下一步该做什么。`connect --stdin` 不带 `--save-to` 时，凭据默认存到 `~/.config/webuddy/credential.json`（目录按 0700 逐级创建，不受 umask 影响），之后 `status`、`config` 都不用再传 `--credential-file`。地址优先级：`--endpoint` > `WEBUDDY_URL` > 凭据里绑定的地址 > 下载时写进去的服务器。
- 服务器的 umask 是 002：第一版用 `mkdir(parents=True)` 建出来的 `~/.config` 是 775，被凭据路径检查拒绝。已改成逐级 0700 创建，并补了测试。服务器上 test_workbench_client 有 16 项在基线上就失败（环境原因），这次的失败清单和基线 482e3eb 完全一样。
- 发布：5116edb1f119，备份在 `/opt/webuddy/backups/pre-5116edb1f119-activation-20261104`。MANIFEST_OK，两个库 integrity=ok，running_runs=0，内外网 login 200、未登录访问 /api/projects 返回 401，active，NRestarts=0。
- 生产 E2E（LYB，干净的 HOME 和 venv）：下载 `webuddy_client-0.4.0-py3-none-any.whl`；直接运行 `webuddy` 显示 `https://webuddy.bbstack.date/t/default` 和下一步；没导入凭据时 `status` 指向 `/tools` 页，输出里没有 127.0.0.1。之后依次跑通 `connect --stdin`、`status`、`config codex --read-only`；MCP 列出 13 个工具，`webuddy_projects_list` 返回 RW。临时连接已撤销。
- 后续（同日）：用户反映创建连接后「没有弹出下载选项」。原因：凭据区在页面顶部，在页面下方点「创建」时看不到；而且每 15 秒核对身份、切换窗口时会清掉凭据区（这条安全设计保留）。修复：创建后由 `saveCredential()` 自动下载 `webuddy-credential.json`，并滚动到凭据区；步骤文案改成「已自动下载」。生产实测（LYB）：点创建后浏览器立即下载，文件里的 endpoint 是生产地址，测试连接已撤销。

## 2026-11-04 界面人机优化第一批（PR #70，生产 9cd16f3）

- 背景：用户要求「先做好界面优化，让人一目了然哪里该怎么填」，并在演示流程里加入「前线需求人员」（在客户现场收原话，排在 FDE 之前）。
- 记录需求弹窗：三步说明（贴原话 → 归档客户/项目/系统 → 交给 AI 理清，确认后才建单）；可选「谁提的」，填写后以 `提出人：…` 前缀并入原文留痕，不新增后端字段。
- 运维单进度条改为 受理 → 运维排查 → 记下结论 → 沉淀经验 → 闭环（`opsStepper`），不再显示改代码步骤。
- 版本页：预览启动命令收进「预览环境设置（管理员填一次即可）」；版本记录上方写明上生产四步。工作台「编写工作简报」默认收起。
- 验证：本机 UI 相关 632 passed、协作相关 170 passed；服务器用发布包跑 15 个相关模块 230 项 OK，失败清单与 `0064bfd` 一致（都为空）。
- 发布：备份 `/opt/webuddy/backups/pre-9cd16f331039-activation-20261104`；MANIFEST_OK，两库 integrity=ok，running_runs=0，内外网 login 200、未登录 /api/projects 401，active，NRestarts=0。
- 招投标演示项目选型：wzhnbb/bidding 只有介绍页；luhongbin/bidding（MIT，litemall 改的招投标/报价）可用，待导入。

## 2026-11-04 首页改成闭环总览（生产 5dc4642）

- 用户要求：状态看板的闭环图应该是首页形式。现在 `#/`、`#/home` 打开「闭环总览」：左边闭环图，右边流转中/失败/已关闭、点节点列出的工单、「等你处理」；深色指标带和智能洞察移到下方。工作台改为总览下的第二个标签 `#/workspace`，`#/board` 仍兼容。
- 顺带修复：选「全部项目」时首页显示「没有这个项目」。原因是租户网关把路径里的 `*` 当项目键去查（`tenant_policy._project` 拒绝 `*`）。新增 `ALL_PROJECT_PATHS`（GET `/loop`、`/inbox`）：`*`/`all` 只对租户管理员放行（`P.loop(None)` 不按权限过滤），其他人 403；前端 `boardQ()` 对非管理员改用当前项目。`POST /catchup` 的 `*` 仍拒绝，首页在全部项目时不显示一键交给自动处理。测试：`test_tenant_policy.py::test_all_project_boards_are_admin_only`。
- 验证：本机 UI 307 passed，UI+租户 350 passed；服务器发布包 15 个模块 231 项 OK，失败清单为空。
- 发布：383dc03 → bf14588 → 5dc4642，备份 `/opt/webuddy/backups/pre-<commit>-activation-20261104`；MANIFEST_OK，两库 integrity=ok，running_runs=0，内外网 login 200、未登录 /api/projects 401，active，NRestarts=0。生产实测 li（全部项目，79 单）与 LYB（当前项目，57 单）首页闭环图都在第一屏。

## 2026-11-04 BID 澄清：普通 LLM 读过的需求按回答再读；无执行权限成员按规则归档

- 生产实测（BID 会话 34fd87676a5d）：普通 LLM 读需求后提出「汇总范围和计算方式」，回答后问题消失，但 A1 仍是 `【待确认：…】`，只在“怎么验”后附了「按补充」。原因：`intake.answer` 和客户链接回答只对 `understood.by == "智能体"` 再读，普通 LLM（`by == "LLM"`）读的不再读。改为 `READERS = ("智能体", "LLM")` 三处统一；测试 `test_llm_reading_is_read_again_with_the_answer`（旧代码失败）。
- 带选项的问题（除业务流）也给输入框，写了以输入为准；点「其他，请说明」类选项转到输入框，不把选项原文当回答。
- 无执行权限的成员（LLA、LYB）「记录需求」：按钮显示「记录并归档」，请求带 `model:false`，按规则保存原话、提出人、客户/系统；有执行权限的人在工作台「继续理清」里点「让 AI 理清」（新 `POST /api/intake/<id> {action:"understand"}`，仍走原执行权限 guard），同一段对话交给 AI。「直接填写工单」也保留提出人。测试 `test_rules_only_record_is_handed_to_ai_later`。
- 验证：本机 intake/租户/工作台/系统/UI 410 passed。
- 发布：700614b → 42f911e，备份 `/opt/webuddy/backups/pre-42f911e035d6-activation-20261104`；发布包相关 23 个模块失败清单为空、与上一版一致；MANIFEST_OK，两库 integrity=ok，running_runs=0，内外网 login 200、未登录 /api/projects 401，active，NRestarts=0。

## 2026-11-04 MCP 也能提需求、让 AI 理清、回答追问；运行结束后页面实测按运行分支找被测版本

- 生产实测：BID-3 用 content 连接 `ticket_create` 直接建单，没有经过需求理解，所以终端演示不到「AI 澄清 → 回答 → 补全验收标准」。新增四个工具操作，复用 `intake.start/understand/answer` 与原执行权限 guard：
  - `intake_get`（read）：读客户原话、事项、验收标准、待回答问题；
  - `intake_start`（content）：记录原话和提出人（channel=mcp），只按规则整理，不调用模型、不建工单；
  - `intake_understand`、`intake_answer`（execute，需 `X-Webuddy-Execution: 1`，且 `tenant_policy` 走 `require_execution`）：让 AI 理清、按回答重读。确认建单仍在网页上由人做。
  - 租户策略按需求对话所属项目核对权限（新资源类型 `intake`）；工具连接按项目可见范围过滤。测试 `test_intake_is_recorded_without_a_model_and_ai_reading_needs_execution`。
- 生产实测：BID-1 #408 运行结束后点「在页面上实测」得到「找不到被测版本」。原因：手动入口不传 commit，`verify` 只看运行工作树，工作树在运行结束后已删除。改为工作树不在时取运行自己的分支 `tmh/<工单>-r<运行>` 的提交（`run_branch_head`）；测试 `test_a_finished_run_is_found_on_its_own_branch`。
- 验证：本机 browser_verify/agent_api/MCP/租户策略/工具连接/AI 验收/intake 191 passed。
- 发布：0cce32f → acfe736，备份 `/opt/webuddy/backups/pre-acfe7360c48d-activation-20261104`；发布包相关 25 个模块失败清单与上一版一致（SAME_FAILS）；MANIFEST_OK，两库 integrity=ok，running_runs=0，内外网 login 200、未登录 /api/projects 401，active，NRestarts=0。

## 2026-11-04 页面实测前置定位只要有一处可见；断言限定到内容区

- 生产实测（acfe736，BID-1 #408，绑定 c86c785）：已能登录评标系统并截到投标信息页（5 条构造记录、万元汇总按钮），但 A1–A3 都因 `anchor(getByText('招标项目', {exact:true}))` 命中菜单、筛选、表头 5 处触发 strict mode，业务断言没执行。`anchor` 只证明前置条件在，改为任一匹配可见即可；实测脚本提示补一条：`expect` 断言限定在内容区或表格里。
- 「记录并归档」后给无执行权限成员的提示改为指向「总览 → 动态与待办」里的「继续理清」（工作台没有这个入口）。
- 生产只读查证：LLA 归档的会话 f4fcfe7bebe6 的客户、系统在 `client_links`/`system_links` 里，「让 AI 理清」的返回值不带这两个字段，不是丢失。
- 验证：本机 browser_verify/ai_accept 48 passed，UI/intake 313 passed。
- 发布：acfe736 → f7ae844，备份 `/opt/webuddy/backups/pre-f7ae844b729d-activation-20261104`；发布包 25 个模块失败清单与上一版一致（SAME_FAILS）；MANIFEST_OK，两库 integrity=ok，running_runs=0，内外网 login 200、未登录 /api/projects 401，active，NRestarts=0。

## 2026-11-04 界面名称改回 Webuddy（0615fe3 上线）

- 用户要求系统名改为 webuddy：界面标题、页头、工具连接页、侧边栏助手提示、下载客户端说明里的“网梯运维系统”统一改为 `Webuddy`；生产 `/etc/webuddy.env` 的 `TMH_BRAND=Webuddy`。
- 本机：UI/工具连接/工作台/命令相关测试 398 passed, 17 skipped。服务器用发布包跑既定验证集，失败清单与 f7ae844 相同（SAME_FAILS）。
- 发布 `0615fe365bb7-brand-webuddy-20261104`：MANIFEST_OK，platform.db / access.db integrity=ok，running_runs=0，本机与公网 /login 200、未认证 /api/projects 401，ActiveState=active，NRestarts=0。备份 `/opt/webuddy/backups/pre-0615fe365bb7-activation-20261104`。
- 同时统计了生产 Codex（cloudwave-codex / gpt-6-luna）的输出速度：按 timing.json 的 output_tokens / model_seconds，中位数 kb≈45、analyze≈69、ask≈80、fix≈86、plan≈93 token/s；单次输入 8–23 万 token（约 80% 命中缓存），kb 是最慢的一步。

## 2026-11-04 执行器不再默认落到 Claude：按钮旁可选执行器，额度不足时提示换一个重试（d8f0c0f 上线）

- 生产实测：JSHERP-1 分析 #456、#457 用的是 Claude Code · Opus 5.5，两次都因网关 403「预扣费额度失败」失败；项目默认路由其实是 `cloudwave-codex`。用 Codex 手动重跑 #458，约 1 分钟完成。
- 原因：页面还没加载到项目（新建的项目、全部项目）时，`projectAgents/preferredAgent` 拿不到 `agent_route`，就按执行器列表顺序选第一个可用的，也就是 Claude。
- 改动：
  - `/api/meta` 带上平台默认路由 `agent_route_default`（只有路由策略，没有密钥）；新增 `projectRoute()`，项目没加载时按默认路由选执行器、按 allowed_agents 过滤。
  - 下一步里出现「分析定位 / 出方案 / 修改代码」按钮时，旁边加上「执行器」下拉框（`#naAg`），点按钮就用这里选的执行器；切换会记在这个人、这个租户、这个项目上，并跟「手动指派」保持一致。
  - 最近一次分析/方案/修改失败，且原因是额度不足或认证失败（403、401、429、额度、余额、Failed to authenticate 等）时，下一步写明「上一次用的 X 额度不足或认证失败」，给出「换执行器重新…」按钮，下拉框默认选另一个可用的执行器。不会自动换执行器去跑。
- 验证：本机 UI 相关 404 passed（新增 `test_unloaded_project_follows_default_route_and_quota_failure_offers_another_agent`）；`test_platform` 里 `test_readiness_checks_the_real_machine_worst_first` 在基线上同样失败（本机环境）。服务器用发布包跑既定验证集 + `tests.test_ui_agent_routes`，失败清单与 0615fe3 相同（SAME_FAILS）。
- 发布 `d8f0c0f340ab-agent-pick-20261104`：MANIFEST_OK，platform.db / access.db integrity=ok，running_runs=0，本机与公网 /login 200、未认证 /api/projects 401，active，NRestarts=0。备份 `/opt/webuddy/backups/pre-d8f0c0f340ab-activation-20261104`。
- 生产页面核对：`S.meta.agent_route_default.agent=cloudwave-codex`；JSHERP-1、PETS-9 的「手动指派」默认都是 Cloudwave · 官方 Codex。额度失败提示用页面里的真实函数和一条模拟的 403 运行核对过（文字和默认选中的 Codex 都对），生产上暂时没有停在这种状态的工单可截图。

## 2026-11-05 第一批产品修复与阿里云发布

- 基线：devin/1793765109-bidding-demo-ui / 86eb560；用户授权按 v2 第一批实施并上线阿里云。旧 iteration/context-pack-v2 保留，不合入独立 Codex 实验线。
- 范围：D1/D2 范围与权限，D3 轮询，D4 附件，D6 逐项证据，D7 申请 ID，D8 发布状态与回执，U2a 同会话输入交接；追加用户提供的开发规范，原 AGENTS.md 保留。
- 实机预检：zct-server 严格主机校验登录成功，webuddy:d8f0c0f running/restart0，Python3.11.2，Compose 与独立数据卷已核对；不操作腾讯云站点。
- 当前进行中：实现与定向验证。第二批及产品扩展保留后续任务，未启动。
- 实现完成：授权范围先过滤后汇总；导航/录入遵循权限；轮询退避、取消反馈与迟到响应隔离；附件稳定 ID 与读取状态；同会话输入交接恢复；逐项证据绑定当前包/提交/环境且复测撤销旧结果；发布随机 ID 与历史冲突隔离；命令完成、人工登记和回执验证分别展示。
- 本机集成验证：19 个相关模块 258 tests OK；最后弹窗响应校验后复验 47 tests OK，完整页面脚本解析通过，git diff --check 通过。受控 Node/HTTP/子进程检查不代表真实浏览器验收；浏览器访问 host 不可用，尚未完成真实页面交互检查。
- 发布前阿里云：原镜像 webuddy:d8f0c0f，running_runs=0，platform.db quick_check=ok；准备精确提交镜像及服务器备份。
- 已发布：实现提交 f6141189c329d634f657b695328a5887b858ac78 已推送 GitHub 产品分支，阿里云镜像 webuddy:f614118 已启动；服务器 258 tests OK（53.478s），2260 文件清单匹配，12 库 integrity_check=ok，延迟检查 running/restart0。本机及公网 curl 登录200、未登录项目API401；一次服务器 urllib 公网403保留为核验差异。
- 完整卷与配置备份：/home/Liyibin/webuddy/backups/pre-f614118-20261104T175810Z。回退仅切程序，保留新数据。
- 逐项代码、测试、未验证范围及回退说明见 [v2 第一批交付对照](webuddy-batch1-v2-delivery.md)。真实浏览器交互仍未验收；后续批次与 BID-1 未纳入。

## 2026-11-05 智能体配置界面

- 用户反馈设置页只有命令说明，没有具体配置界面。本次补独立读取/保存 API 与设置页列表、详情和表单；管理员可查看，平台管理员且现役受信主机可保存。
- 支持显示名称、模型列表、各步骤默认模型、任务超时、Codex profile 和新增 Codex 执行器。凭据沿用服务器配置，接口不回传命令参数/环境变量/密钥；不通过保存启动模型任务，不改变项目路由和授权。
- 保存保留未编辑字段，原子替换 agents.json，并用文件摘要拒绝过期提交；错误保留表单输入。命令可用仅显示“命令已安装”，不冒充已登录或调用成功。
- 本机 82 项设置/API/权限/UI 回归通过，59 项路由和 Codex 兼容性通过；完整页面脚本解析和 diff 检查通过。浏览器访问 host 仍 unavailable，无真实浏览器验收截图。
- 已推送并上线：`3ec27cb8d2759dbdaf9119aa00c704eae66523fa`，阿里云 `webuddy:3ec27cb`。服务器 Python3.11 隔离容器 141 tests OK（51.487s），2264 发布文件 SHA 清单一致，现有3个智能体配置只读兼容检查通过。
- 发布前 running_runs=0；完整卷/外部配置备份 `/home/Liyibin/webuddy/backups/pre-3ec27cb-20261104T181450Z`；12库完整性检查通过，上线后两主库再次 ok；回环及公网登录200、未登录新配置API401，容器 running/restart0。原镜像 f614118 保留，回退只切镜像不覆盖数据。
- 使用入口：刷新“设置 → 智能体”，点“配置”或“查看”。新增 Codex 执行器不会自动改变路由允许列表；本轮不提供 API 密钥编辑或真实模型付费连通测试，也未修改生产上的模型配置。

## 2026-11-05 阿里云 Codex 实际接入修复与 li 登录排查

- 用户反馈 li 登录失败并要求直接配置 Codex。只读查证 li active=1、平台管理员、default 组织 admin，组织 active；账号和 session.key 与第一批发布前完整备份一致。本轮未修改密码、权限或伪造用户会话。
- 当前控制库 li 密码记录与旧 users.json 的记录不同（未输出哈希）；仅能判定记录有差异，尚未收到登录错误提示，不能据此断言根因。仍待区分密码错误、限流、会话或组织跳转。
- Codex 确认的迁移遗漏：cloudwave-codex.bin 仍为腾讯云 /home/ubuntu/.npm-global/bin/codex，现容器实际 /usr/local/bin/codex；引用的 webuddy-cloudwave.config.toml 不存在。此前配置兼容检查只证明能读配置，未证明该执行器可运行。
- 已在阿里云外部配置修正 bin，新增独立 profile 继承既有 aiseat provider、gpt-6-luna 与服务器凭据；未复制密钥、未修改默认路由及其他执行器。原配置备份 /opt/webuddy/data/maintenance-backups/codex-access-20261104T183307。
- 使用平台实际 command 构建器在临时空目录以 understand/read-only 模式调用官方 CLI，要求不用工具、只答 WEBUDDY_CODEX_OK：15.2 秒、exit0、completed=true、结果精确匹配、无认证/额度错误。未触发业务任务或验收。配置热读取，无需重启服务。

## 2026-11-05 修复阿里云 HTTPS 登录来源误判

- 用户截图明确 origin_denied：请求在密码验证前被拒绝。公网用合法 Origin + 超长空测试正文复现相同403（正文校验在来源校验后、认证前，不尝试任何账号密码）。此前密码记录差异不是此报错的原因，未重置账号。
- 根因：_scheme 仅信任回环代理；阿里云 Cloudflare Tunnel 经容器网络连接，外部 HTTPS 被认作 HTTP。修复使用服务端配置 TMH_PUBLIC_URL 确定对外协议及固定来源，同时保留 Host 一致和 Sec-Fetch-Site 跨站拒绝，HTTPS 会话附 Secure。
- 新增隔离真实 HTTP 回归：修前合法来源登录403，修后正确合成密码303且 cookie Secure；错误协议、外部来源、null、跨站及伪造Host仍403。本机网关+登录23 tests OK（9.427s），diff检查通过。
- 已上线 `7fbad9a15bde6b0586e1a72e3f51e325c8bb6ddf` / webuddy:7fbad9a；服务器23 tests OK（25.957s）、2264文件清单一致；12库完整性通过。备份 /home/Liyibin/webuddy/backups/pre-7fbad9a-20261104T183856Z，旧镜像3ec27cb保留。
- 公网同源超长正文探针：修前403 origin_denied，修后413 invalid_request（来源已通过，正文按大小拒绝，未进入密码校验）；跨站探针仍403 origin_denied。内外登录GET200、未认证配置API401，主库完整性ok，running/restart0。隔离合成账号成功登录303已测，未代用户登录li。

## 2026-11-05 架构与依据页面改版

- 用户指出系统结构图不好看且表达有误。源码确认旧 archSvg 将入口统一连至中部位置、所有业务域连总表、所有外部调用连首个业务域，连线并非实际依赖；本次移除该示意图，保留现有真实项目图谱入口。
- 改为业务域总览：顶部4项规模统计、完整可搜索的业务域网格、右侧入口类型/高频数据表/全部外部调用；保留全部业务域、原始名称、完整说明、状态和跳转。高频表明确显示所列数量/总数，数据表可进知识页；分析来源/更新时间/待核对事项收进可展开区域。
- 响应式单列、长名称换行、键盘焦点、搜索零结果及清除入口；项目切换后迟到请求不重绘。无新增后端/数据变更，无自动翻译或改写知识事实。
- 本机31项架构页面/导航/完整脚本检查通过，diff检查通过。浏览器访问host不可用，已请求连接；未完成桌面/窄屏实际渲染，不宣称视觉验收已完成。
- 已推送并上线 `8a14b35459978fa1803c9df3bd4332966ac83efc` / webuddy:8a14b35；服务器31项测试通过（1.520s）、2265文件清单一致。切换前running_runs=0，备份 /home/Liyibin/webuddy/backups/pre-8a14b35-20261104T184921Z，12库完整性ok，上线后主库再次ok，服务running/restart0，内外登录200/未认证API401。回退镜像7fbad9a保留，不覆盖新数据；实际视觉渲染检查仍待浏览器连接恢复。

## 2026-11-05 修正业务与代码概览的定位文案

- 用户认可该页是源码业务/代码概览，而非完整架构，授权调整描述。页面标题、导航、助手跳转和命令入口统一“业务与代码概览”；本页统计、搜索、空状态和详情说明使用“功能分组”。保留知识库中的实际名称与其他业务流程用语，不改数据或路由。
- 页面说明改为“从功能分组查找业务流、数据操作与代码依据”；展开依据明确分组并非已确认业务边界或应用/部署架构。旧搜索别名仍可找到此页。
- 本机31项页面/导航/脚本检查与6项命令测试通过，diff检查通过；本轮仅文案，无布局变化。
- 已上线 `2a27d847d70cb639e0302d5e1899d1dc630ae076` / webuddy:2a27d84。服务器37 tests OK（1.508s），2265文件清单一致；备份 /home/Liyibin/webuddy/backups/pre-2a27d84-20261104T185558Z，12库完整性ok，内外登录200/API401，running/restart0。回退保留8a14b35镜像与现有数据。

## 2026-11-05 GPT Pro 复核缺口纠错

- 用户授权“可以修，然后提交”。基线 0b541fc；完成10项：历史运行与当前候选检查隔离、人工决定按事件顺序投影；项目/输入版本隔离迟到草稿；新增/编辑配置分离且重名409；附件读取不能解除提交锁；完整Git提交身份及历史短SHA唯一解析；配置读取固定管理员权限；首页待办范围/容器/请求代际隔离；同一需求的受项目授权直达交接链接；保留独立验收项结果但不放宽整单AI验收；保存成功与刷新失败分别反馈。
- 保留原人工审批、证据包/环境绑定、原子配置写入及版本摘要检查。AI签收在环境变化后仍失效；历史运行与过期并发响应不影响当前候选。新输入在请求成功返回后保留且可继续提交。
- 验证：16个相关模块215 tests OK（20.936s）；补强部分通过/未知混合验收的完整basis后，证据模块13 tests OK。10个新增缺陷用例在修改前基线均失败；当前版本全部通过。实际执行了Node页面函数、临时Git与部署回执脚本、隔离HTTP网关测试；未作真实浏览器视觉验收或业务人工签收。
- 发布前观察：阿里云 webuddy:2a27d84 running/restart0，Python3.11.2；当前容器时区UTC。用户另要求本批提交后修复中国时区，作为下一次独立提交。

## 2026-11-05 北京时间显示修复

- 前批10项修复已提交并推送 d1b5b81。用户追加中国时区问题：生产容器的无时区时间按UTC存储，页面曾原样显示或按浏览器当地时间解析。
- 页面统一用 Asia/Shanghai 格式化：工单/运行/对话/签收/交接/发布/知识/配置连接到期等时间；相对时间使用服务端明确偏移，不依赖浏览器地区。服务端保持现有存储时区，通过meta提供偏移；不改写历史业务记录或哈希链、不调整凭据有效期。
- 首页“今天”、工单日图及月度效率筛选按中国日历归属。传回API的“上次查看”游标仍使用服务端时间格式；日期型业务约定原样保留，原始日志与下载证据保持原件。
- 验证：整合27个模块/指定测试358 tests OK（55.061s），涵盖前批缺口及本轮UI/API/日月边界；最后补封存时间和对话时分显示后29 tests OK。UTC/上海/洛杉矶三种浏览器环境显示同一北京时间；临时SQLite跨日统计正确且原时间字节未改。完整脚本解析、diff检查通过；测试夹具有既存ResourceWarning，退出0，无失败。
- 两次独立实现提交合并为一次生产切换，避免重复停服。用户追加截图中的 bwrap namespace 拒绝与tmh命令可用性，待本次上线后独立核对。
- 已推送并上线：运行提交 `9c6900b60602b1118edd20242992747f73155cd2` 包含前批 `d1b5b81`，阿里云镜像 webuddy:9c6900b。服务器初次356项运行通过，另外2项因发布测试包未带examples/legacy-java-oa在类初始化失败；从同一精确提交补齐examples后2项通过（1.842s），无产品代码变更。清单2305文件逐字节匹配。
- 发布前running_runs=0，完整数据/仓库/Codex卷与外部配置备份 `/home/Liyibin/webuddy/backups/pre-9c6900b-20261104T192935Z`；14个SQLite库完整性通过。保留旧镜像2a27d84和rollback-pre-9c6900b；回退只切程序，不覆盖新数据。
- 即时与超过60秒延迟核验：容器running/restart0，主业务库和控制库integrity=ok；回环及公网登录200，未登录配置API401；Mac公网登录200。生产没有代人创建需求、保存智能体配置或验收；浏览器视觉交互未实测。

## 2026-11-05 截图中的 tmh 与 bwrap 问题核查（只读）

- 用户要求本批完成后检查。查到GROUPRISK最近运行464（kb）、463（chart）、461（kb）包含bwrap错误；项目根和知识目录存在，但`.tmh/tool/tmh.py`缺失。容器PATH上也没有`tmh`入口；`python3 -m tmh --help`在平台目录正常，说明平台模块已部署，不能说整个tmh没有部署。
- 固定无业务命令探针：宿主机`unshare -Ur /bin/true`成功；同一现役容器内返回Operation not permitted。容器非privileged、无额外cap、Seccomp=2，用户namespace内核开关允许；Codex0.162.1直接沙箱调用出现与截图一致的bwrap namespace拒绝。已定位到容器执行限制，未冒充模型额度或认证失败。
- 之前固定文字Codex连通测试只验证模型回复，不验证命令派发。本次未调用模型、未重跑业务任务、未修改沙箱/容器权限、项目工具或原运行记录。后续修复需补齐项目工具并验证受限命令执行、只读和越界写入约束；不能以关闭沙箱当修复。

## 2026-11-05 恢复阿里云容器中的 Codex 沙箱

- 用户授权修复容器无法开启沙箱。现役Webuddy镜像9c6900b、Docker26.1.3、Codex0.162.1。依据官方文档与现役CLI帮助，在无业务卷/凭据、无外部网络的临时容器复现默认策略下namespace拒绝。
- 基于Moby v26.1.3完整默认seccomp策略（上游原文件SHA256 `9c1025c88ccaa517b648da571961838744ea2137f176bfe6a48b21294cae9c76`），仅追加clone带CLONE_NEWUSER、unshare参数仅CLONE_NEWUSER，以及mount/umount2/pivot_root。原规则与顶层默认拒绝配置逐项保持。逐项移除这5类均失败；setns无需开放并已移除。
- 临时容器真实Codex沙箱9项通过：读取、工作区写入、只读拒写、外部拒写、符号链接越界拒写、Git元数据拒写、TCP拒绝、Unix socket拒绝、CapEff=0/Seccomp=2。默认策略反例仍失败在namespace创建。无模型调用或业务任务重跑。
- 部署策略和离线验证脚本纳入scripts/deploy；应用代码与模型配置保持原版本。准备完整备份后更新Compose的此服务seccomp路径并重建容器；不使用privileged、CAP_SYS_ADMIN、unconfined或关闭Codex沙箱，不修改宿主机sysctl。
- 已提交并推送策略 `f93e716`；宿主机部署文件 `~/webuddy/security/seccomp-codex-f93e716.json` SHA256 `280cde4a2eea3f83ae37da2043a7bc2d01729dd09a5cd1f24cb49464b80a06c1` 与精确提交一致。Compose只增加此服务security_opt，应用镜像仍9c6900b（运行源码未变），用户weppt、privileged=false、capadd=null。
- 发布前running_runs=0；完整备份 `/home/Liyibin/webuddy/backups/pre-sandbox-f93e716-20261104T193729Z`，14库integrity全部ok。旧Compose、镜像、业务/Codex卷保留；回退恢复旧Compose，仅重建容器，不恢复数据库。
- 现役生产容器中的同一9项真实Codex沙箱检查全部通过；即时HTTP内外登录200/未登录配置API401，运行文件2305清单一致、两主库完整性ok，running/restart0。仅临时自有夹具读写，验证后已清理；未重跑GROUPRISK业务任务或调用模型。

## 2026-11-05 阿里云宿主机部署准备

- 用户要求停用应用容器、直接部署服务器。准备用户级 systemd 服务 webuddy-native，开启 linger，独立 HOME/CODEX_HOME；保留原数据路径与 UTC 存储，页面继续北京时间。
- 精确应用版本9c6900b，原生Python3.11.14/SQLite3.50.4；宿主机358项回归通过（90.179s），14个真实数据库副本完整性及Store初始化通过。Codex0.166.0在宿主机及NoNewPrivileges=yes的临时systemd单元均通过9项沙箱检查；未调用模型。
- 原生入口192.168.112.1:8791只绑定现有隧道桥接地址；临时HTTP探针已确认容器到宿主机200。准备先停止应用容器、备份并迁移全部卷、核验后启动原生服务，再切换Webuddy单条隧道路由。共享隧道容器保留。
- 回退须先停原生服务并备份当前数据，将最新data/repos/codex同步回原卷并恢复1100属主后再启动旧容器；不得直接启动停用容器读取旧快照或恢复旧数据库。切换完成情况随后补记。
- 原生切换已执行：切换前running_runs=0，停止容器后完整备份至 `/home/Liyibin/webuddy/backups/pre-native-20261104T195006Z`；全部data/repos/codex复制后diff逐文件一致，再转属主1001:1002。14库完整性通过，11个项目根全部存在，2305源码文件清单匹配。
- 仅将cloudwave-codex.bin改成PATH上的codex；密钥和账号/会话原样迁移。为GROUPRISK缺失的.tmh/tool补装同版本工具，项目内和全局tmh --version均0.4.0，未修改知识或重跑业务任务。
- 用户级webuddy-native已enable/start，旧webuddy容器停止且restart=no。Cloudflare配置v5→v6，只将Webuddy ingress改为http://192.168.112.1:8791，另两站和404兜底保持。即时内外登录200、未登录配置API401；同服务HOME/PATH/NoNewPrivileges环境的9项真实Codex沙箱检查再次通过。原生操作与保留新数据的回退说明见scripts/deploy/NATIVE.md。
- 原生HTTPS检查发现uv Python默认CA路径不匹配阿里云系统，已显式配置SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt并重启；未关闭TLS校验。服务器Python访问公网登录探针随后返回403，不能认定为应用来源拒绝；Mac curl同源超长正文返回413 invalid_request，证明通过来源校验且未进入密码验证。
- 补验：系统CA下原生Python访问HTTPS返回200；Mac公网跨站正文403 origin_denied，同源413 invalid_request。会话密钥与旧卷字节相同，现役14库再次完整性ok；内外登录200/API401。仅验证技术入口与沙箱，未代用户登录、执行真实模型任务或人工验收。

## 2026-11-05 主域名改为 webuddy.cloudwaveai.cn

- 用户要求脱离个人BBstack域名。将webuddy.cloudwaveai.cn原直连A记录8.141.121.22改为代理CNAME，指向现有阿里云Cloudflare Tunnel；配置v8只保留新Webuddy入口，另两站和404兜底不变。旧webuddy.bbstack.date的CNAME和ingress已删除，未改个人域名其他记录。
- 服务TMH_PUBLIC_URL改为https://webuddy.cloudwaveai.cn，原配置备份于/home/Liyibin/webuddy/backups/domain-20261105T093242/webuddy.env；重启前running_runs=0。现役仍原生9c6900b，无运行代码或业务数据改动。
- Mac与服务器新域名HTTPS登录200，未登录配置API401；同源超长正文413 invalid_request，旧域名Origin403 origin_denied。未输入用户密码。飞书启用，其回调地址由公共地址生成，新地址为https://webuddy.cloudwaveai.cn/login/feishu/callback；尚未核验飞书开发者后台的允许列表或真人OAuth登录。
- 同步AGENTS.md与原生部署说明，避免后续误发旧容器/旧域名。域名变化不迁移浏览器cookie，需要在新域名重新登录。
- 超过60秒延迟核验：09:34:06 CST原PID702348保持、active、NRestarts=0；新域名登录继续200。

## 2026-11-05 GLD 权限与 li 对齐

- 用户明确要求gld与li相同权限；实际账号为GLD。GLD原已是default/admin，缺平台所有者；本次仅补platform_owners，并在authorization_guard/事务内更新授权revision、按既有逻辑失效权限变化的工具连接、写local-maintenance审计。未模拟li会话、未改账号密码/epoch/有效状态。
- 控制库完整备份~/webuddy/backups/permission-GLD-20261105T094345/access.db，仅保存在服务器0600。修改后Registry.context的role/platform_owner/project_grants/capabilities/can_manage与li逐项相同，双方accounts记录原样保持，完整性ok。无需重启或运行代码发布。
- 免费证书说明核对Let's Encrypt官方FAQ及DNS-01文档：可免费签发并部署国内服务器；本次未申请证书或切换国内直连入口。

## 2026-11-05 关闭Webuddy代理，恢复国内直连

- 用户明确要求A记录指向8.141.121.22、DNS only。已将代理CNAME替换为A（记录5cf22fd16237a5ac6043f31e918fb1ea），移除Webuddy隧道ingress（配置v9），其他两站隧道保持。
- 沿用宿主机Nginx和Certbot，为webuddy.cloudwaveai.cn新增独立站点与Let's Encrypt证书，到期2027-02-03；HTTP跳转HTTPS，ACME webroot保留，反代现役192.168.112.1:8791。应用服务未重启、数据未改。证书私钥仅在服务器。
- 首次证书请求ACME读超时；确认主机可达后再次申请成功。首次管理命令因镜像默认非root无法chroot，随后限定root助手；不共享PID时systemctl不可用，切换host PID后操作成功。Nginx测试通过（其他既有站点有protocol options警告）；reload刚发出时一次直连仍收到旧默认证书，reload生效后TLS校验正常。
- 原certbot-renew.timer已enable但inactive，已启动；既有deploy hook负责nginx reload，下次运行显示14:48 CST。全局tmh及沙箱配置不变。
- 直连TLS登录200；当前Mac无代理强制直连三次0.035590/0.045683/0.041439秒；这组是当前探针，不代表所有国内网络。API401、同源正文413、跨站403，响应server=nginx且无Cloudflare头；未代用户登录。
- Certbot定向dry-run续期成功；公共DNS已返回8.141.121.22。原生应用和Nginx、续期timer正常。配置与操作说明入库，未为记录重启应用。
- 补记DNS过渡观察：公共1.1.1.1查询已是8.141.121.22，但Mac系统解析随后仍命中旧104.21.0.95，普通curl在15秒超时；指定真实IP并保留域名/SNI的直连检查通过。旧本地/运营商DNS缓存仍可能短时访问旧入口，不将其描述为所有用户已完成解析切换。

## 2026-11-05 MCP配置随服务器迁移同步

- 用户要求MCP配置同步。服务端wheel按当前公共地址生成，现役包workbench_site.json已读回为https://webuddy.cloudwaveai.cn/t/default，无需改产品代码或重启。文档旧端点同步，并补迁移说明。
- 本机~/.webuddy客户端从现役同版本wheel重新安装；~/.config/webuddy/credential.json仅更新endpoint，原token字节保持，私有备份保留。status实查原li连接active、execute、原8个项目范围；没有创建连接或扩大权限。
- 本机Codex原没有webuddy条目，已按客户端生成结果追加到~/.codex/config.toml，保留其他MCP与设置；解释器和桥接脚本指向安装目录、仅引用凭据文件，允许原连接既有execution，未发起业务操作。旧配置私有备份，TOML读回通过。
- Mac系统DNS仍返回旧Cloudflare IP；一次status及配置生成成功，标准MCP握手随后网络超时。dscacheutil非root刷新无效，sudo -n要求密码，未改系统DNS/hosts。临时验证进程仅将该域名解析至已验证阿里云IP、保留域名TLS校验：官方MCP SDK initialize成功，23工具列出，projects_list成功。此临时解析未写入正式MCP配置，不能把测试等同于当前Mac DNS问题已解决。
- 其他成员已下载的客户端/凭据不随本机修改自动更新；需在新工具连接页重新下载/导入。未替其他成员签发凭据，未触发真实模型任务。

## 2026-11-05 恢复阿里云到Windows测试机连接

- 用户确认服务器已加入白名单，授权配置连接。现测8.141.121.22→43.153.76.85:12022的TCP与Windows SSH banner成功；平台实际SSH失败为publickey，旧页面仍展示此前超时。
- 为Liyibin生成专用/home/Liyibin/.ssh/webuddy_testbox_ed25519，私钥0600只留阿里云。SSH配置按host43.153.76.85+user auntu匹配专用IdentityFile/IdentitiesOnly，不影响其他主机。OpenSSH使用实际Unix账号的.ssh而非服务HOME覆盖值。
- 经Mac既有授权密钥严格校验登录旧中转机，再经其既有本机转发进入Windows，仅追加新公钥到C:/ProgramData/ssh/administrators_authorized_keys，追加前完整备份；限制agent/port/X11转发和PTY，保留原有密钥与ACL。没有迁移或输出旧私钥，没有放宽防火墙。
- Windows可信会话读回ECDSA主机公钥指纹与阿里云known_hosts相同；阿里云严格主机校验登录返回Windows_NT。首次PowerShell检查因远端命令引用/本地UTF8解码失败，修正完整命令引用后成功。
- 用现役平台TestBox.check及服务环境完成实际体检：Windows，C:/tmh-runner；Git2.47.1、Java17.0.20.1、Maven3.9.9、Node20.18.0、pnpm9.15.0、Docker29.1.3全部检出，missing=[]。旧testbox-check.json备份后更新，时间按UTC存储；readiness._build实际返回ok。未运行项目构建、业务任务或模型，应用无重启、NRestarts=0。

## 2026-11-05 网页助手复用MCP操作与GitHub导入重试

- 网页助手改为对话→真实工具→回执→结果，复用MCP同一23项成员操作、参数契约、执行服务与权限检查；按当前用户过滤项目并逐次核权，不开放shell或人工验收/合并/发布。沿用现有模型路由、会话和持久化结构，无新增依赖/数据库schema。
- 每步持久化调用与请求编号，未知结果重试复用原回执；支持继续/停止，重复点击不重复建单。输入响应固定会话/项目，切换项目或继续输入不会被迟到结果清空。桌面520px、移动全宽，折叠完整操作参数/结果，历史会话保留。
- GitHub已在阿里云真实浅克隆产品分支（4.86秒）并fetch成功；针对GitHub导入时已观察到的短暂连接中断增加最多3次重试，只清理该次新导入临时目录。认证错误/其他主机不重试；未使用镜像、关闭TLS或改全局Git配置。
- 本机109项针对回归通过（19.262秒）；补充Node异步输入检查通过，覆盖重复提交、项目切换、新输入保留和迟到建会话响应。隔离Chrome实际渲染1440×1000和390×844、发送并完成一次工具对话，无水平溢出。
- 阿里云使用候选代码、服务器真实路由模型与临时Platform：status→projects_list→ticket_create→最终回答完成，确实创建且只创建一张测试工单，运行数0。临时数据已清理；没有访问真实业务会话或代人验收。待完成精确提交发布与上线核验后补记。
- 实现提交 `2875e0e1b3d8eb4702efbfe9407ac45cc11dc4d4` 已推送github产品分支，并于10:27:31 CST切换阿里云原生服务；app→releases/2875e0e。服务器109项回归（59.074秒）+1项Node输入隔离测试通过，候选受测479文件逐字节与发布包一致，发布清单2311文件匹配。
- 发布前14个数据库完整性及副本Store初始化通过，全部库无queued/running任务；停服完整备份data/repos/codex/config/home至`/home/Liyibin/webuddy/backups/pre-2875e0e-20261105T022657Z/state.tar`（1.3G），原env/服务单元/旧链接保留。旧9c6900b程序不删；回退只切程序，绝不恢复旧数据库覆盖新写入。
- 停服备份期间外网两次探针502；新服务启动后公网与内部登录200、匿名项目API401、同源超限正文413、跨站403。运行cwd与RELEASE精确匹配，2311清单与14库再次通过，PID776903/active/running/NRestarts0。未在生产用户会话中提交业务需求；真实模型写入验证使用隔离临时数据。
- 10:28:41 CST（启动超过60秒）延迟复核：原PID776903、active/running、NRestarts0保持，运行清单/14库完整性、内外登录200与匿名API401再次通过。此次记录更新不重启服务。

## 2026-11-05 Codex直接驱动SSH测试机闭环

- 用户要求Codex改完代码直接SSH到测试机安装/启动/测试，并明确开发测试默认完整授权。复用现有TestBox传输与配置，给普通Codex修改运行注入专属MCP testbox_info/testbox_run；SSH密钥留服务器，Codex工作区沙箱保持。未开放个人隔离路径或改人工业务验收。
- 工具绑定运行/工作目录，按数据目录摘要+运行号隔离远端目录。同步HEAD+二进制补丁，脚本使用现有Windows PowerShell；保存完整日志、退出码、基准版本与补丁摘要。默认授权仅作用这两项工具；不逐次弹窗。
- 修复环要求最后一次测试对应当前改动，缺失/失败/未完成/代码变更均不通过；分文件修改完成后由主Codex执行测试。原固定构建和独立诊断保留。重新验证也重跑该脚本，不再只凭编译覆盖原测试结果。
- 本机104项针对回归通过（19.433秒），覆盖真实Git补丁传输、脚本失败、缺回执、过期回执、取消、路径越界、MCP协议及重新验证失败。Windows实机普通脚本exit0、超时脚本exit124通过；远端看护在超时后终止该脚本进程树。
- 首次真实Codex调用被默认MCP审批策略拒绝，已按官方单工具approval_mode=approve配置并复验，未关闭沙箱或改全局审批。第二次真实平台Runner._spawn中，Codex读取测试机→修改临时app.js→编写check.ps1→SSH同步→npm install→启动Node→HTTP断言status=ok→finally清理→返回exit0，脚本回执耗时60.538秒。证据只在服务器`/tmp/webuddy-testbox-live-7r9kkeaz`，测试数据独立，无真实业务工单写入。
- 阿里云104项针对回归通过（44.637秒），最终发布包443个运行/测试文件与受测目录逐字节一致；Windows远端看护脚本重用提取前后的字符串完全一致。首次Get-NetTCPConnection清理核验60秒超时，改用netstat后确认测试端口18973未监听，再仅删除本次合成运行的远端repo/work目录，真实项目目录未动。
- 实现提交`0741715368739e88d161839b901daf353e177733`已推送github产品分支并部署原生app→releases/0741715，2316文件清单匹配；14个生产库完整性及副本初始化通过，切换前无queued/running任务。完整停服备份`/home/Liyibin/webuddy/backups/pre-0741715-20261105T024906Z`保留data/repos/codex/config/home、旧链接与服务配置；回退只切程序、不恢复旧数据库。
- 启动后公网登录200、匿名项目API401、同源超限请求413、跨站403；运行清单及14库完整性通过。新任务使用新工具；未重跑历史失败业务任务或代人验收，测试机实测使用隔离合成应用。
- 10:50:39 CST延迟核验（10:49:15启动后84秒）：原PID803799、active/running、NRestarts0，cwd=0741715；2316文件清单、14库完整性、内外登录200/匿名API401保持。后续交付记录提交不重启服务。

## 2026-11-05 明确生产/测试分离并恢复BBstack测试入口

- 用户最新要求覆盖此前自动生产发布授权：日常修改/功能迭代默认在43测试站，里程碑后只有用户明确要求才更新阿里云生产。GitHub提交推送继续自动；AGENTS.md、原生部署说明及两份本机接入记忆已同步。生产数据与测试数据保留各自分叉，不能互相覆盖。
- Cloudflare新增webuddy.bbstack.date A→43.153.76.85，DNS only、TTL300，记录0b4a3855dc4af0fdd29ae1fb26fe0f9e。只在43 Caddy现有Webuddy站点增加此域名，原webuddy-us.bbstack.date及其他站点保留；配置验证通过后reload。备份/opt/webuddy/backups/domain-test-20261105T035751Z/Caddyfile。reload提示既有systemd单元磁盘变化，未为此改动其他服务或执行daemon-reload。
- 43现役webuddy.service active/PID731180，app仍/opt/webuddy/releases/d8f0c0f340ab-agent-pick-20261104/app，TMH_PUBLIC_URL原本就是https://webuddy.bbstack.date，不改env、不重启Webuddy、不迁移数据。本次只恢复域名，没有同步最新产品代码。
- 公共DNS1.1.1.1已解析43.153.76.85；Mac正常DNS和指定IP保留SNI的TLS登录均200，匿名API401，同源超限413、跨站403。阿里云生产DNS仍webuddy.cloudwaveai.cn→8.141.121.22、DNS only，本轮不改生产应用或配置。

## 2026-11-05 43测试站同步当前版本

- 用户要求43同步好；仅发布测试环境，不改阿里云生产。精确源码`d61738a7dbdcd0cc798d484e07e9f354f1ea9532`，包含此前网页助手、GitHub导入恢复、逐项纠错/北京时间、智能体配置和Codex SSH测试机闭环。
- 43 Python3.12.3上526项针对回归全部通过（138.951秒）；2316文件清单匹配；12个原有数据库完整性和副本Store初始化通过，所有项目根仍位于原data/repos目录。发布前无queued/running任务。
- 43原Codex0.162.1经真实Runner._spawn使用新MCP成功：修改临时app.js、SSH到Windows、npm install、启动Node、HTTP断言status=ok、exit0，测试回执33.923秒。无需升级CLI或修改模型/路由/密钥；测试端口18974无监听，合成远端目录已定向清理。证据`/tmp/webuddy-43-testbox-c983fipb`仅留43。
- 网页助手也用43原路由真实完成status→projects_list→ticket_create→结果，临时数据隔离并清理；没有使用真人会话写业务数据或代人验收。
- 复用原root0600发布锁，停服完整备份`/opt/webuddy/backups/pre-d61738a-test-20261105T043917Z`：data/repos、ubuntu的.codex、env与服务配置，旧程序保留。app现指向`/opt/webuddy/releases/d61738a/app`，12:39:49 CST启动，PID1052555；不复制阿里云数据库或账号。补齐此前缺少的/home/ubuntu/.local/bin/tmh入口，版本0.4.0且在实际服务PATH上。
- 即时内外登录200、匿名API401、同源超限413、跨站403；运行cwd/清单/12库完整性通过，active/running/NRestarts0。沿用已加载的systemd单元，未因既有磁盘mtime警告改动其他服务。阿里云只读核验仍0741715/PID803799/active/NRestarts0。
- 12:41:36 CST延迟复核（启动后107秒）：PID1052555保持、active/running/NRestarts0，2316清单及12库完整性再次通过，内外登录200/API401。操作说明补入scripts/deploy/TESTING.md；本次记录提交不重复重启应用。

## 2026-11-05 自动与手动验证、AI Review（实施完成，待43发布）

- 用户授权本轮全部实现后部署43试用，阿里云生产保持。增加完整分批只读审查，普通小改动也审查；外部手写代码共用覆盖结果，不再只读取前14000字符。记录执行器/模型、基准和完整diff摘要、每批范围、未知/二进制未覆盖项。
- 原复检API增加kind=tests/review/all，复用持久操作、锁、预算、进程回收和封存。单独Review只有在旧测试有效且代码/基准相同时保留测试；新代码或审查期间变化不继承旧通过。重跑Review本身不触发自动采纳。人工复核/验收权限与固定候选规则保持。
- 运行详情集中展示实际测试、AI判断和绑定当前运行的人工结果，提供三种复检按钮和人工复核入口；完成后的进程日志折叠。独立执行器与同执行器步骤明确区分，不把模型判断当实测。
- 本机229项针对回归通过（36.670秒）；后续界面与HTTP相关39项通过（4.957秒）。初次扩展回归的旧mock Git夹具/小改动免审预期失败，已调整公共Git调用点及本次明确改变的审查预期，后续routes+新审查48项通过。原ResourceWarning保留。
- 隔离HTTP实际执行review/all各200，错误kind返回400；GET正确返回版本覆盖与未签收状态。真实Chrome独立临时配置渲染1440和390宽度，无页面水平溢出、可见报错；本地合成执行器不冒充真实模型。浏览器工具宿主不可用，使用本机独立headless Chrome完成渲染。
- 43 SSH指纹/0600/严格known_hosts/sudo核验通过；原d61738a服务active、PID1052555、重启0。精确提交、Linux测试、真实Codex隔离审查和发布记录后续追加。

- 代码提交 `0bdc13579d7bb0c12c51d827d212681be97eb1c7` 已普通快进推送github。43精确发布清单2320文件，沿用既有部署范围；全量上传链路慢，停止后改用459361字节差量（SHA256 `87b2d21912f88df5398364b806c41bda80ca85a8ac264c2cb8e0984b21c17bd8`），未变文件逐摘要核对复用，不改变图片编码或业务数据。
- Linux精确代码230项针对测试通过（81.066秒）；12个数据库完整性和副本Store初始化通过。真实cloudwave-codex在独立临时项目执行“测试并Review”，测试pass、审查pass、1/1批完整，原运行decision保持空；完整进程回执及结果保留43 `/tmp/webuddy-review-live-22ypqv6n`，没有操作业务工单或真人签收。
- 2026-11-05 16:46:13 CST，43 app切换到`/opt/webuddy/releases/0bdc135/app`，webuddy.service PID1126083、active/running、NRestarts0。共用root0600发布锁；停服完整备份旧app、data/repos、Codex与外部配置到`/opt/webuddy/backups/pre-0bdc135-test-20261105T084510Z/state.tar`，44742文件逐字节校验通过，旧程序保留。沿用已加载服务单元，原mtime提醒未触发其他服务daemon-reload。
- 16:46:22 CST即时检查：2320文件、12数据库、进程cwd及版本一致；回环和公网登录200、匿名项目API401。阿里云生产未操作。最终延迟检查另记，本次文档补记不重启服务。
- 16:47:31 CST延迟复核（启动后78秒）：同PID1126083、active/running、重启0；2320文件、12库完整性、cwd、内外登录200和匿名API401再次通过。Mac独立公网检查同样200/401，跨站登录403，实际完整9000字节超限登录正文413。首个“声明100MB但只发1字节”的不完整正文探针15秒超时，不计为通过；改用完整正文后413通过。
- 最终补测本机73项通过（4.355秒），页面折叠日志后的1440/390宽度再次真实渲染核对，无水平溢出。使用与API说明见`docs/verification-review.md`；本记录和测试站版本说明作为文档提交，不重复重启。

## 2026-11-05 项目测试配置、用例证据及ERP接入（发布准备）

- 平台增加项目管理员配置、分阶段本机/SSH执行、JUnit/JSON原始报告、逐项关联、版本与证据失效检查；自动修改和手动复检共用执行器。未修改人工签收或业务关单规则。配置API及实际保存→复检→结果展开已验。
- 本机255项相关回归通过41.242秒，新增取消用例后20项项目测试通过5.255秒。POSIX后台服务跨阶段/取消与日志回收已实际验证，Windows早期合成报告流程通过，后续ERP环境尚未完成。
- jshERP隔离源码40项Java/14项Node通过；修复真实单笔退款转负数字符数组错误，保留源码CRLF。前端构建成功；依赖审计187项含59高危/36严重，未冒称安全通过。数据库、真实HTTP业务和浏览器E2E仍未验。
- 实现说明docs/project-testing.md；ERP测试与安装补丁examples/project-testing/jsherp；详细进度docs/self-improvement/project-testing-progress.md。只部署43，阿里云生产不动；上线结果随后补记。

## 2026-11-05 20:57 项目测试已发布43，ERP回归已接入

- 实现提交`062801866d62eed92f353e616f52ed01a3b54f5b`普通快进推送github；43 app→`/opt/webuddy/releases/0628018/app`，2336文件精确清单核对；Linux256项回归通过81.202秒，本机255项通过41.242秒，随后20项项目测试含新增取消检查通过5.255秒。
- 停服完整无损gzip备份`/opt/webuddy/backups/pre-0628018-test-20261105T125028Z/state.tar.gz`，46211文件逐字节校验；14库完整性和副本Store初始化通过。保留旧程序与备份，回退只切程序不恢复旧库。现役20:51:50 CST启动、PID1195456；20:53:22（92秒）、20:57:24检查同PID、active/running、重启0、2336清单、14库、内外200/401均通过。阿里云未操作。
- ERP实际平台执行器在43隔离工作树完成backend_build、backend40用例、frontend14用例，均通过；原始平台证据`/opt/webuddy/data/project-test-baselines/JSHERP-20261105`。确认注册根干净且无活动任务后，将精确补丁提交到43 JSHERP的master，提交`cfac6d956ca8cedbcdfa8329dbc8021fcd36113e`；未推上游jishenghua。平台外置project-tests.json启用JSHERP，executor=local。Java8/Maven保存在/opt/webuddy/tools；新运行/复检读取配置。
- Windows链路有间歇超时；SSH简单命令成功后仍出现下载/命令超时。最终新版本真实Windows合成测试通过，证据`/tmp/webuddy-project-remote-dc7xg9m9`，不等于ERP已在Windows通过。Java8官方TLS下载失败、SCP断连，临时回环SSH隧道下载也中断，未关闭证书验证。ERP维持已验证Linux配置。
- ERP真实MySQL/Redis、业务HTTP与浏览器E2E、并发/性能/迁移仍未覆盖；Mac前端构建成功，npm审计187项含36严重/59高危，不能称为安全通过。未代人验收/关单。
- 本机原始日志、原图、构建/审计JSON及实际解析的package-lock保留`../部署包/project-tests-0628018/`，源图字节未改。43仅删除本次已被正式版本替代的88MB临时候选源码，业务/旧备份保留，剩余约446MB，空间仍偏紧。


## 2026-11-05 项目测试证据纠错与真实ERP业务验证

- 修复依赖失败仍被用于验收证明的问题，报告有效性和依赖有效性分别保存；执行和失效检查统一绑定实际验收内容、来源及方案版本，覆盖方案变化和客户标准清空。
- 验证界面增加业务输入/预期/实际/关联用例表；原始报告经运行权限、路径与摘要核验后可打开和原样下载。普通成员只读；管理员可从最近报告选择用例关联。桌面1440与移动390真实Chrome检查无页面水平溢出，打开/下载、关联和只读行为通过；界面检查使用独立合成工单。
- 本机260项关联回归通过43.089秒。旧aa32aa0 CI的17项Linux失败已本机复现：16项测试夹具漏载实际北京时间函数，1项旧断言仍把整套成功等同逐项证明；加载实际函数并要求无逐项证据时人工确认全部标准，未放宽产品门槛。补充58项UI及14项需求测试通过。历史Windows进程/文件占用失败未在此宣称解决，全仓CI仍须观察新提交。
- 真实ERP销售退货链路发现上一轮金额修复遗漏数组输入，页面保存前出现split is not a function。保持字符串与实际数组契约，新增3项数组用例先失败、修复后17项前端用例通过。
- 本机隔离MySQL8/Redis7/Java8/Chrome环境，通过平台实际执行器完成构建40项后端、17项前端及4项业务用例，共61项。A1单账户12.50、A2双账户7.25+5.25、A3/A4重复单号拒绝均有精确用例关联，require_all_criteria=true；实际HTTP、数据库、API重读及页面金额一致，单据保持未审核。填表使用真实Vue组件接口、点击真实保存，不声称覆盖所有键盘/下拉框。
- 构建与运行绑定Git基准/完整差异、JAR、前端入口和容器身份；平台current_issue为空。原始截图/报告/日志及失败尝试完整保存在../部署包/project-test-business-20261105，SHA256读回校验；v4为最终成功证据。未代人签收、未执行财务过账；无伪造AI Review结论。
- 43保留现有本机回归配置，Docker业务配置单独交付，不直接启用到缺少Docker/Chrome的43。阿里云生产不操作。43旧pre-0bdc135备份已无损gzip，解压摘要与原tar一致，记录lossless-compression.json；原内容完整保留。待精确提交发布后追加运行版本与健康记录。

- 发布实现提交`c730623dda70b5ee228ccbe2479098696187a5df`已推送github；43精确2343文件重建，315项回归通过104.737秒。15库完整性及副本初始化通过，完整备份`/opt/webuddy/backups/pre-c730623-test-20261105T151931Z/state.tar.gz`逐字节校验46323文件。旧程序和完整备份保留，回退仅切程序。
- 43于23:21:02 CST启动，app→releases/c730623/app，PID1235942；23:21:05、23:49:56和23:51:41实查同PID、active/running、NRestarts0，运行清单/数据库/内外登录200与匿名API401通过。既有systemd单元mtime提示未扩展修改。阿里云未操作。
- 43 ERP独立工作树40项Java测试通过27.525秒；手工前端命令漏--experimental-vm-modules导致17项hook失败，按既有配置补齐参数后17项通过。注册根干净、无活动运行时应用精确补丁，本地master提交`65bcbd28fc8815bc4f082036fd827721285ff84b`；未推上游，原外置测试配置保持。报告保存`/opt/webuddy/data/project-test-baselines/JSHERP-20261105-array`。本次sudo生成的ERP文件所有者恢复ubuntu，注册根干净。
- GitHub Actions本提交运行42053087633：Linux3.11/3.13完整套件各2918 passed、39 skipped、1894 subtests passed；快速与安装包检查全部成功。Windows完整套件3.11为147 failed/991 passed/215 skipped/1 error，3.13为169 failed/1023 passed/215 skipped/1 error；166个可提取失败标识中142个出现在上一提交日志，其他未逐项完成根因确认，不宣称全部为历史问题或全平台CI全绿。工作流总状态success源于原Windows continue-on-error；未改工作流、未降低断言。这不阻断已完整通过的Linux部署，但Windows平台兼容性仍须单独修复。
- 43备份后可用空间约683MB；未删除业务数据或旧备份。最后记录更新只推送文档，不重启已验证服务。


## 2026-11-06 43测试服务器缓存清理

- 用户授权清理旧缓存腾出空间。清理前可用710033408字节，根盘99%；现役c730623、PID1235942、重启0。
- 通过rootless Docker原生builder prune清理闲置构建缓存（先24小时之前，再全部unused）；删除Snap下载缓存中仅单硬链接、超过60分钟的4个文件共492195840字节，以及/root/.cache/pip约158MiB。未清理镜像、容器、数据卷、业务数据、测试报告、日志、完整备份、回滚程序或已安装浏览器。
- 清理后可用3767590912字节（约3.77GB/3.51GiB），净增加3057557504字节（约3.06GB），使用率94%。Docker构建缓存0；13镜像/1运行容器/7数据卷保持，weppt容器ID与运行状态保持。构建缓存大小含共享层，不把工具报告的逻辑大小当实际释放量。
- 01:09:03 CST验证：2343运行文件清单及数据库完整性通过，Webuddy同PID、active/running、NRestarts0；内外登录200、匿名API401。未重启服务，未操作阿里云。原始清理/健康日志保留本机../部署包/cache-clean-20261106/。本次仅记录提交，无程序部署。


## 2026-11-06 we-ppt停用与历史备份收敛

- 用户明确we-ppt可以清理，并提出Webuddy备份无需保留过多。停止并删除rootless Docker容器weppt-dev-weppt-1；仅删除weppt-dev的6个标签和weppt-dev-deps专用镜像，其他镜像不动。实际可用空间从3766558720增至7279120384字节，释放约3.51GB。we-ppt作品/账号/配置卷、源码与原图保留，不宣称已删除作品或彻底卸载所有文件；未修改共享Caddy。
- 在原发布锁内核验最近3份完整备份：pre-0bdc135-test-20261105T084510Z、pre-0628018-test-20261105T125028Z、pre-c730623-test-20261105T151931Z。gzip完整性、data/repos/Codex/env成员及其中platform.db提取后integrity_check通过。
- 保留上述3份完整备份；只删除更早pre-<Git SHA>-发布备份中的app/data/projects/control和state.tar归档，共256个精确目标。旧config/清单、小型独立账号或域名备份保留。删除列表和完成状态留服务器root0600的/opt/webuddy/backups/retention-20261106.json。当前及旧版本releases均未清理。
- 备份目录约15GiB降至2.1GiB；此步净释放13738598400字节（约13.74GB）。最终可用21017382912字节（约21.02GB/19.57GiB），磁盘66%。后续无需为本次容量继续删业务数据。默认以最近3份已验证完整发布备份作为保留目标，新备份验证成功后再淘汰旧完整副本；本轮未新增定时清理任务。
- 01:20:12 CST现役仍c730623/PID1235942、active/running、重启0，运行清单与数据库检查、内外200/401通过。阿里云未操作。原始日志在本机../部署包/cache-clean-20261106/，本次仅推送记录，不重启Webuddy。


## 2026-11-06 广联达POC题库、Review记录与Windows执行兼容

- 用户要求参考会议转写准备更多复杂需求。新增 `examples/client-tickets/广联达POC场景与澄清问题.md`：6组场景、三级验证清单、21项澄清问题，标明甲方原话时间与推导场景。现役BID为domiegg/springboot-vue1810演示替身；真实政策、接口、源码与业务预期尚未提供，未擅自实现正式评标算法，不能称客户POC已验收。
- Review效果记录已落地：真人逐项记有效/误报/待核实、人工另行发现及实际分钟数；绑定具体Review，幂等保存、保留历史，效率页按人/运行/当前审查汇总。无真人样本，不估算节省时间，不改变签收/采纳/关单。72项相关回归通过，真实HTTP覆盖匿名/租户/项目/只读角色/智能体拒绝与会话身份；独立Chrome验证表单、防重复、关闭后的响应隔离和只读入口，原图已亲自打开。
- Windows新增Job Object子进程树监管、控制管道继承；修复原始输出换行、CRLF代码块和知识页、命令解释器与引号语义，以及退出采样顺序。共享删除读取方案在Windows压力测试仍失败，最终用命名内核互斥协调监管回执的读取与原子替换，读操作不创建磁盘锁文件；保留JSON、身份、原始字节与清理完整性校验。
- 最终实现 `e08b0a9e9490e936dc45e50ddfb3b29f9a02ca7c` 已普通快进推送github。Actions 42088218237：Windows3.11/3.13专项各141 passed、12 skipped、134 subtests passed；快速门禁和安装包成功。截至02:59完整Linux/Windows套件仍运行，不声称完整CI或全平台通过；Windows人工经验登记的原子持久化边界仍保留。Windows测试机SSH 43:12022两次超时，实际Windows证据来自GitHub runner。
- 43先完成371项相关回归、随后按新增差异分别143/58/45项复验（含平台专属跳过；这些数量有重叠，不相加作场景数）。最终2349文件精确清单、15数据库完整性与副本初始化通过；完整备份 `pre-e08b0a9-test-20261105T185618Z/state.tar.gz` 46245文件逐字节核对。未发布失败候选80d0061/fd44c91；两者仅留候选目录。
- 43现役app→releases/e08b0a9/app，webuddy.service于02:57:47 CST启动，PID1295605。02:57:50及02:59:09延迟82秒检查同PID、active/running、NRestarts0，清单/数据库/运行cwd及内外登录200、匿名API401通过。阿里云生产未操作。
- 新备份验证后保留pre-05402f5、pre-781b4e9、pre-e08b0a9三份完整归档；只删除先前三份pre-0bdc135/pre-0628018/pre-c730623的state.tar.gz，元数据与程序版本保留。root0600审计 `/opt/webuddy/backups/retention-20261106-feedback.json`，约20GB可用、67%已用。
- 原始Windows失败/通过日志、服务器验证、浏览器原图和合成脚本保留 `../部署包/poc-windows-review-20261106/`，SHA256读回验证。本次交付记录提交不重启服务；后续先查看上述精确实现CI结果，勿把此前取消或失败记录重做为当前缺陷。


## 2026-11-06 验证流程核对后的修复（发布准备）

- 修复旧式命令配置变化后Review-only仍复用旧测试通过：新记录绑定命令、项目profile、测试机配置、超时和实际验收契约；读取时重新核对，旧证据保留历史，复用需明确契约一致。隔离反例已转为实际临时Git/数据库/执行器回归；同时覆盖审查中配置变化。
- 项目profile补修改前独立工作树基线，失败结果与候选分别保存且继续验证候选。逐阶段/逐命令检查源码身份，版本变化停止后续普通阶段、保留清理；自动流程额外绑定每轮HEAD/差异/契约、完整命令和诊断。不是操作系统级源码只读，不能声称防止同权限进程在单阶段内改后还原。
- 阶段区分受阻、未执行、失败；自动修复遇到明确受阻停止，真正代码失败及其依赖未执行仍要求返修。验证页显示基线、当前范围和问题处理出口；范围由方案与审查声明并记录，不把声明当实际覆盖。保留人工签收、门槛、原始断言及修复轮次/时间预算。
- 本机关联172项曾全部通过；其后基线缓存加入环境配置摘要触发一处旧SimpleNamespace夹具缺少set字段，补齐夹具后11项通过。最终变化相关65项通过24.578秒、范围展示及复检27项通过11.223秒，数量有重叠不相加。原始失败和通过日志保留../部署包/verification-flow-20261106；未声称全仓CI/Windows或生产业务端到端已验。
- 新鲜SSH权限、指纹、严格known_hosts与sudo已核验；43仍e08b0a9、PID1295605、重启0、约19GiB可用。只发布43测试站，阿里云生产不操作。精确提交服务器验证、备份与延迟健康结果发布后另记。

- 046c61e精确服务器源码2349文件与15数据库副本检查通过，Linux173项通过65.201秒，尚未切换现役。交付复核补充版本变化逐项证据失效：测试期源码变化或执行机身份不符时，关联验收项保持unverified；本机40项通过18.751秒。最终提交将在此基础上执行针对复验再发布，046c61e不作为已上线版本。

- 358addf服务器精确清单/15数据库副本及40项针对回归通过10.797秒，仍未切换；范围字段补真实模型输入边界校验，非对象或非字符串数组记未声明，避免新增展示字段阻断验证。本机28项通过13.252秒；最终范围边界提交只需复验对应差异，不重复已验证全流程。

- 最终实现01bb05250945d550760c027f04a8471d874b16e6已普通快进推送github并发布43：2349文件精确重建、15数据库完整性和副本初始化通过；主体173项Linux回归通过，后续版本身份40项/范围解析28项分别通过10.797秒/16.188秒（重叠数量不相加）。
- 发布前完整备份pre-01bb052-test-20261106T031600Z/state.tar.gz，46245文件逐字节核对。43于11:17:26 CST启动，app→releases/01bb052/app，PID1419119；11:17:28即时及11:18:45延迟79秒检查同PID、active/running、重启0、源码清单/数据库/运行cwd及内外登录200/匿名API401通过；Mac独立公网200。旧systemd单元mtime提示保持，未改其他服务，启动最初一次连接未就绪后原就绪重试成功。
- 新备份验证后，复验保留的3份完整归档gzip及platform.db完整性，仅删除旧pre-05402f5的state.tar.gz（648515751字节），保留pre-781b4e9、pre-e08b0a9、pre-01bb052完整归档、旧程序与元数据。审计/opt/webuddy/backups/retention-20261106-verification.json，磁盘约19GiB可用。阿里云生产未操作；未代人业务验收/关单。
- GitHub本提交Push CI 42155325653于11:18查询时全量仍运行；快速门禁、Linux/Windows安装包、Windows3.13执行证据专项已成功，其他任务未作全绿声明。此记录只推文档，不重复重启。原始日志及SHA256在../部署包/verification-flow-20261106。


## 2026-11-06 终端协作开发、Leader复核与CI门槛（发布准备）

- 新增 develop 个人工具范围：选现有工单、持久分析稿/问题/回答、按修订继续。来源、问题、回答变化会撤销原确认；保留客户已确认验收要求。确认稿进入开发上下文、候选身份和项目测试契约，未确认不能启动所选任务的fix或登记候选。
- 人工终端独立个人登录：查看、问答、确认、逐项复核、批准、退回与合并。密码/会话只在进程内，MCP无人工确认/合并操作；后端继续检查真实会话、指定独立复核人和固定证据。所选终端任务由Leader批准后负责人再次确认合并，旧任务合并策略保持。
- 本仓库已有CI；增加项目管理员配置的GitHub Actions必需检查，查询精确完整SHA，失败/缺失/跳过/取消/未完成不通过，不跟随重定向传递凭据。合并重新核对并记录CI快照，配置锁阻止并发覆盖。本地主干快进明确pushed=false/deployed=false，项目远端推送/CD与业务验收仍独立。
- 本机114项相关回归通过20.353秒；团队与合并43项通过20.780秒；官方SDK19项stdio/租户协议检查通过15.795秒，真实HTTP个人登录读取通过。启动互斥与新scope另有针对复验；数量有重叠。临时Git合并使用合成测试/预览/CI边界夹具，不宣称客户业务验收。实现细节与使用入口见docs/developer-terminal.md。
- 146项首轮回归曾有两项断言失败：不存在工单返回404而非预期403、新增五条HTTP路由使数量200→205；已按实际契约修正并复验，权限与拒绝断言保持。发现并修复开发分派位置、approve/accept枚举、租户develop角色映射和旧来源回答复用问题。未全仓/Windows或生产端到端验收。
- 43新鲜SSH、sudo、登记指纹/0600和现役01bb052/PID1419119/重启0已核验，19GiB可用。待精确提交Linux验证、完整备份与发布；阿里云生产不操作。原始日志本机/tmp/webuddy-developer-*.log，交付归档随后补充。

- 7375b1b在43完成2358文件和15数据库副本检查，245项Linux回归通过125.497秒。尚未切换：发布助手残留旧路径被停服前预检拒绝，现役保持01bb052。已修正本机助手的模板替换；另补网页轻量客户端下载漏打包的developer_terminal.py，11项客户端/终端复验通过（Mac使用真实/private/tmp，保留凭据父目录禁符号链接要求）。最终补丁仅复验下载包差异，不重跑前述全组。

- 最终运行提交f566a90fb059fe564650cc435a6b6c6d81687279已普通快进推送github并发布43。下载客户端模块/安装说明补丁12项服务器复验通过0.465秒，主体245项回归保持；2358文件精确重建、15库完整性及副本开发表初始化通过。未发布7375b1b/91f1133，旧脚本路径错误在停服前拒绝，没有切换旧版本。
- 完整备份pre-f566a90-test-20261106T050043Z/state.tar.gz共46260文件逐字节核验；现役app→releases/f566a90/app，13:02:14 CST启动PID1448500。13:02:24即时、13:04:13延迟119秒均同PID/重启0，清单/数据库/运行cwd与内外200/401通过。启动最初一次连接未就绪后原重试成功；没有回灌数据库、代人验收或操作阿里云。
- 验证最近3份完整归档gzip及platform.db完整性后保留pre-e08b0a9、pre-01bb052、pre-f566a90；只删除旧pre-781b4e9的state.tar.gz（646401108字节），旧程序和元数据保留。审计/opt/webuddy/backups/retention-20261106-developer.json，磁盘19GiB可用、68%已用。
- 本机安装分发包smoke通过；网页轻量包另验脱离仓库独立运行。一次Mac临时目录/var符号链接触发既有凭据保护，使用真实/private/tmp复验通过，不修改保护规则。安装提示使用force-reinstall并要求重连MCP，避免同版本包被跳过。
- GitHub最终Push CI 42165690965/PR 42165696077交付查询仍运行；快速门槛和两个安装包任务已成功，未宣称全平台完整CI通过。完整日志（含失败与复验）及SHA256读回验证保留../部署包/developer-terminal-20261106。本记录只推文档，不再重启。

## 2026-11-06 CLI证据约束、返修停止和ERP故障检查（发布准备）

- 修复旧CLI静态检查/仅构建误记完整通过。验证绑定任务、完整HEAD、工作区内容、有效契约、配置和基线；执行前后比对，UUID原报告与用例原件保留，状态推进核对摘要。复用平台JSON/JUnit解析器，L2逐项关联用例；手写“通过”不再放行。CLI尚不产生L1/L3逐项权威记录，相关任务使用既有平台候选/复核/部署回执，未把登记ref/build当实际合并部署。
- needs_human改为待技术处理，增加blocked/awaiting_business，技术缺口不能直接签收；人工guard保留。平台同契约跨运行累计返修预算，单次运行连续三次同样失败或跨运行预算耗尽转technical_required；复验通过后解除停止标记。更新界面状态、验收文档和随客户端分发的操作说明。
- Mac Python3.11最终151项针对回归通过42.207秒；另安装4项通过，前序100/54/61项有重叠不累加。新增循环测试实际确认耗尽预算不调用writer、重复失败三次停止。最初Miniconda第三方tests包抢占导致11项导入错误，改用项目Python3.11复验；skills/.DS_Store导致安装测试误读，原文件移至/tmp保留，无产品代码绕过。
- ERP隔离环境重新构建：40项Java、17项Node及6项真实业务检查通过，含页面保存、HTTP/MySQL/API回读、防重复、未登录提交零新增。新增预期先误认401，源码确认LogCostFilter/request.js的既有500+loginOut契约后采用精确断言；另修复测试浏览器残留旧登录会话导致页面超时，每次清理专用回环源会话。保留失败与复跑日志。财务过账/库存审核未扩充，未宣称ERP全业务验证完成。
- 43发布前新鲜SSH/登记公钥0600/sudo核验通过，现役f566a90、PID1448500、重启0、19GiB可用；阿里云不操作。待精确提交Linux回归、完整备份及延迟健康检查。原始材料本机../部署包/reliability-implementation-20261106，发布后补记录。

- 运行提交d7e2ed1de22af3e863e6ec334f91b16d339b5e37已普通快进推送github并发布43。精确2359文件、15库完整性/副本检查通过；同提交Linux151项回归通过36.858秒。完整备份pre-d7e2ed1-test-20261106T053946Z/state.tar.gz校验46255文件字节一致后切换；启动初次curl尚未就绪，原重试随后成功。
- 43现役app→releases/d7e2ed1/app，13:41:08 CST启动PID1461441；13:41:18即时、13:42:29延迟81秒同PID/重启0，文件清单、15库、运行目录、内外登录200/匿名API401均通过。阿里云未操作，未代人签收。ERP本轮启动的应用/数据库/Redis、专用Chrome及本机代理均已停止，测试数据和原始证据保留。
- 最近三份完整归档gzip及platform.db核验后保留pre-01bb052/pre-f566a90/pre-d7e2ed1，只移除pre-e08b0a9的state.tar.gz（646402505字节）；旧程序和元数据保留，审计backups/retention-20261106-reliability.json，19GiB可用。
- GitHub Push CI42169577583、PR CI42169584684仍在运行；已观察快速门槛、Linux/Windows安装包和Windows3.11执行证据专项成功，未宣称完整CI或全平台通过。最终记录纠正独立安装检查为4项，并明确重复失败三次为单次运行停止、总预算跨运行累计；仅文档变更，不重启服务。

### 2026-11-06 工作台、任务详情与登录改版（发布准备）

- 基线 `c154ae9` / 运行 `d7e2ed1`，当前产品分支；四项日常导航、默认个人工作台、按需交接、任务阶段页签、业务证据主视图与范围、居中真实登录。运行/统计/客户/运维/重构/执行器/测试机/知识入口保留，额度进入账号菜单。工作台新增兼容只读投影，任务显示真实执行/验收/合并策略；不修改状态机或权限、验收门禁。
- 本机 UI 328、后端相关 86 通过；最后证据表与页面变更针对复验 48 通过。迟到详情响应不重建新任务草稿，提示词/交付请求有上下文保护；验收提交加锁，未知结果先查询。首次新 attention 计数回归发现详情投影变更影响计数，已改为分页投影前计算并复验。
- 隔离真实服务三重点页五尺寸检查（1440×900、768×1024、390×844、1920×1080、2560×1080），无整页溢出；19 项交互、3 项网络/迟到响应检查。改变实际测试契约复现失效；合成运行/关闭状态仅证明显示。没有对业务任务代人签收、关单、执行模型或发布。角色权限由回归覆盖，浏览器未逐个真实租户角色登录。
- 原始前后 PNG 与交互日志：`../部署包/ui-redesign-20261106/index.html`；说明 `docs/ui-redesign-20261106.md`。43 当前现场仍 `d7e2ed1`，健康、重启 0、19GiB 可用。下一步精确提交测试发布；未操作阿里云生产。

- 已发布 43：主实现 `7f43c44`，最终运行提交 `afddfca5d67875e05528f483c847ae3b6fad2179`（补正依据不足时顶部误示待验收）。均已普通快进推送。Linux 主实现 UI328+相关后端86通过；最终增量17项针对复验通过。2360份文件精确重建、15库完整性与迁移副本检查通过。
- 完整备份 `pre-afddfca-test-20261106T061907Z/state.tar.gz` 逐字节校验46256文件后切换。14:20:29 CST启动PID1474508，14:20:31即时及14:22:19延迟约110秒健康通过、同PID/重启0。回环及公网登录200、匿名API401，运行目录/文件清单/15库均一致。启动首次curl未就绪后按既有重试成功，原日志保留。
- 浏览器重新打开43实时登录页，1440×900、768×1024、390×844无整页溢出，真实飞书入口保持；未登录43业务账号。隔离当前提交三重点页五尺寸截图在 `afddfca/`，账号菜单及额度入口两项实际检查通过。前后对比 `../部署包/ui-redesign-20261106/index.html`；实际验收范围见 `docs/ui-redesign-20261106.md`。
- 三份保留归档全部gzip与platform.db核验后，仅移除最旧pre-01bb052的state.tar.gz（646401669字节）；保留pre-f566a90、pre-d7e2ed1、pre-afddfca、所有旧程序和元数据。审计 `backups/retention-20261106-ui-redesign.json`，可用19GiB。阿里云生产未操作，未代人验收/签收/关单。本次完整GitHub CI状态未作通过结论。


### 2026-11-06 R1—R6 交付修复（进行中）

基线为产品分支 `devin/1793765109-bidding-demo-ui` 的 `5147f70`，已核对 github 远端一致，工作区干净。范围：历史评测身份契约、依赖受阻分流、终端交接和确认稿展示、相关 CI、安装与客户试点准备。每项保留反例和实际验证；精确代码提交的目标平台必需 CI 通过后才部署 43。客户真实环境、人工决定及怀柔价值验证分别记录，不以演练代替。


本轮实现与本地检查：

| 条目 | 根因与修复 | 本轮依据 / 边界 |
|---|---|---|
| R1 | 历史输入被当持久工单；`build_prompt` 明确历史案例契约，评测不读现工单确认 | 生命周期/资料变更拒绝/开发确认等 62 项通过；合成执行器，不是业务正确率 |
| R2 | 可选上游受阻未计入必需依赖；项目测试保留递归 blocked_by 并将汇总标受阻 | 超时多级依赖、无关可选失败、真实测试失败、补齐重跑及不调用 writer 检查通过 |
| R3 | approved 一律计入 Leader 待办；布尔 handwork 被当姓名 | 终端批准转负责人，计数/分页/入口统一；历史流程保留；Leader 重复批准按钮禁用 |
| R4 | 详情只读平台 plan | 授权任务响应加入只读确认稿与修订事件；无 plan 仍显示，需求确认不充当实测/业务验收 |
| R5 | 新只读操作缺读取层项目校验；契约失效后 unknown 仍可自动采纳 | 增加范围与候选运行绑定，外部查询前拒绝；失效诊断阻止自动采纳；不修改 CI 容错或跳过规则 |
| R6 | 安装与升级指向旧分支 | 改固定交付 SHA、支持矩阵、重连与职责；追加客户核对和怀柔对照模板 |

实际执行 Mac/Python 3.11：`test_direct_invocation_lifecycle test_library_review test_development test_project_tests` 62 项；`test_tool_read test_development test_stage test_workspace test_team_workspace test_project_tests` 116 项；补充后定向 67 项、最终相关 64 项；UI discover 328 项，末次 UI 架构 4 项。各批有重叠，不能相加为不同场景数。命令均 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/tests:$PWD" python3.11 -m unittest ...`（早期 62 项未设禁写字节码）。首次进程回执异常及 KeyError 保留原日志；最小监督进程探针与随后重跑通过。一次只读检查遇 Python 首次导入写 pyc，被审计正确拒绝；禁写字节码后通过。误写不存在 UI 测试模块的命令未计通过，已改为实际架构测试。

真实 Chrome + 隔离 HTTP 服务：终端确认无 plan/无实测、确认人和修订、页签草稿保留；合成候选批准的 Leader 页面禁用重复批准，review 队列为空；1440×900、390×844 无整页横向溢出，原始截图已保存并实际打开检查。合成账号/证据仅用于界面与责任边界，不是真实客户验收。未执行真实怀柔/Windows/两机联调。

干净 venv 安装：第一次从现工作目录构建的安装文件出现空模块，CLI 导入失败；保留失败结论。随后将 210 个源码文件逐一核对字节长度复制到无 build 缓存的临时源码目录，强制安装成功，离开源码目录执行 tmh --version 输出 0.4.0、webuddy --help 成功。这是 macOS CLI 安装检查，不证明 Linux 客户主机或 Windows 凭据支持。交付用精确 Git 提交的隔离源码重新构建，包显示版本不充当代码版本。

证据：[本轮日志与截图](evidence/delivery-r1-r6-20261106/)。客户待提供：主机/终端系统、可达网络、怀柔仓库与 CI、规则与数据副本、模型通道/计量依据、需求/开发/Leader/验收/推送发布责任人。接入材料已补入 DEPLOY.md、developer-terminal.md、team-pilots.md。远端 CI 和 43 发布结果待本候选推送后追加；阿里云生产未操作。


精确候选 `ca3e122` 的 CI（Actions 42180012807 / 42180021287）：快速、安装包、Windows 执行与证据专项成功；Linux 完整套件发现两项旧测试仍期待检查契约变化后自动采纳，首次 3.11 结果 2990 passed、2 failed、45 skipped。产品现在正确阻止失效诊断放行。补齐两项测试：断言 unknown、历史保留和未采纳，再由合成测试中的明确人工 decide 操作采纳，保留已采纳提交复验与清理覆盖；本地两项通过，未放宽产品门禁。新提交推送后重新等待精确 CI；未部署失败候选。

用户随后明确可用现有 Windows 设备，SSH `webuddy-win` 本轮连通。实际系统 Windows NT 10.0.26200、Python 3.11.9、Git 2.55、Node 24.18；在 `C:\tmh-runner\work\webuddy-ca3e122-r1r6` 新隔离目录运行，包 SHA256 `e31197e72060ad0a5b8e2e1a45ac66b180761b311d62b3914e05007dea94b43a` 核对通过。183 项：141 通过、41 既有平台条件跳过、1 报错。唯一报错为 test_tool_client 的个人凭据保存触发 credential_platform_unsupported，说明原生 Windows 个人 MCP 接入仍未支持；未删除保护或新增 skip。此设备不是甲方怀柔环境，不算客户联调。完整 Windows 回执与日志另存本轮证据目录。

完整 `git archive ca3e122` 源码在 Mac 新 venv 安装后，`python -I -X utf8 scripts/installed-smoke.py <site-packages>` 通过来源、CLI、项目工具安装/刷新、全部资源和离线安装。仅导出 tmh/pyproject 的初次实验包不含 setup.py/安装资源，不能作为完整交付包，已改用完整提交归档。


### 2026-11-06 R1—R6 最终测试交付

- 运行代码提交 `d83c267ae5308fcd8de365688136e8d09a7c3cff`（核心实现 `ca3e122`，两者运行文件零差异）。[Actions 42181939561](https://github.com/auntunt/webuddy-pitch/actions/runs/42181939561)：Linux Python 3.11/3.13 完整套件各 **2992 passed、45 skipped**；快速、安装包、Windows执行/证据专项成功。部署前程序核对精确SHA及10个必需/专项任务 success。Windows3.13完整为 **30 failed、1143 passed、215 skipped**；截至本次记录Windows3.11完整仍在运行，不引用workflow容错总状态作全平台结论。失败涉及CLI验收夹具的POSIX引号、Windows文件锁/并发读、预览/固定代码查询以及未支持的原子知识登记；不是本轮Linux发布路径通过的替代证明，Windows整个平台支持尚未完成。
- 自有Windows设备额外实测 **183项：141通过、41既有跳过、1凭据门禁错误**。安装包在原生Windows新venv的安装、CLI、项目工具install/refresh、完整资源和offline install全部通过，原始输出与回执已归档；个人MCP原生凭据仍明确不支持，不能用chmod代替ACL。测试后无遗留Python/Node进程，远端原日志SHA与下载原件一致。不是甲方设备/怀柔业务联调。
- 43候选校验 **2380文件、15数据库完整性/副本初始化、120项相关回归**通过；先通过CI再部署。备份 `/opt/webuddy/backups/pre-d83c267-test-20261106T075519Z/state.tar.gz` **55848文件逐字节核对**。现役 `/opt/webuddy/app` → `/opt/webuddy/releases/d83c267/app`，`webuddy.service` 于15:56:57 CST启动，PID1502105；15:57:03即时及15:59:58延迟检查同PID、NRestarts0、active/running，运行cwd/清单/数据库与内外登录200、匿名API401通过。启动等待循环首次端口未就绪后正常恢复，原日志不删。
- 延迟检查后验证最近三份完整归档，保留pre-d7e2ed1/pre-afddfca/pre-d83c267；仅删除旧pre-f566a90的state.tar.gz（646516336字节），程序和恢复元数据保留；root审计 `/opt/webuddy/backups/retention-20261106-r1-r6.json`。磁盘约18GiB可用。恢复入口为备份中的old-app.txt及旧程序 `/opt/webuddy/releases/afddfca/app`；只切换程序，不用旧库覆盖新写入。阿里云生产未操作。
- [原始证据入口](evidence/delivery-r1-r6-20261106/README.md)：本轮回归、实际浏览器原图、Mac/Windows安装、Windows设备回执、精确CI门槛、服务器切换与延迟健康。此条记录提交晚于代码提交，运行文件一致性另行核对，不为文档重启服务。
- 结论分开：**代码修复与43测试交付完成；客户接入说明/核对表/试点模板已准备；客户真实联调未完成；真实项目价值尚未验证。** 接下来需甲方主机与终端系统/原生Windows个人MCP要求、实际仓库与CI、网络/模型通道、规则/数据副本和指定需求确认/开发/Leader/验收/推送发布人员。已有公开演练和自有设备测试不登记成怀柔成功样本。

### 2026-11-06 系统与本地开发交接（进行中）

- 基线 `5d80631`，已核对产品分支 github HEAD 一致、工作区干净。沿用 Codex/Claude Code 调用内核，不新增 Cursor 后端。
- 本轮目标：人工确认后明确选择系统/本地执行；回答、确认及选择不隐式开工。本地 CLI/MCP 只读检查实际目录、登记仓库、完整 HEAD、未提交内容和知识修订；差异显式保留。保持权限、独立复核与合并门禁。
- 新任务要求当前执行选择；历史未带新字段的会话保持原兼容行为。选择绑定当前确认摘要与固定代码起点，变更使旧候选契约失效。待定向回归、协议与安装检查后提交精确候选 CI。
- 定向本机首轮50项（18项因该解释器无可选MCP SDK跳过）；官方SDK独立复验20项通过，覆盖Cursor/Claude/Codex生成配置启动及新预检只读边界。相关集成107项初次1项Mac临时目录符号链接触发凭据保护；指定真实 `/private/tmp` 后31项复验通过，未修改凭据保护。最终受影响调用/权限/UI结构44项通过。
- 自有Windows设备Python3.11真实Git隔离目录28项通过（16.522秒），包括worktree、脏目录保留、远端/HEAD/知识版本不匹配和交接门禁；没有绕过原生Windows个人MCP凭据限制，未宣称客户Cursor桌面联调完成。
- 本机隔离HTTP服务、合成账号任务在Chrome检查1440×900、768×1024、390×844：确认稿、选择方式和固定起点可见，无整页溢出。证据 `docs/self-improvement/evidence/execution-handoff-20261106/` 保留原始截图与首次失败/复验日志。未对真实任务代人确认或执行模型。
- 最后复核将选择执行方式的基线查询纳入既有 `personal_scope`，不允许普通租户直接使用宿主Git。权限/交接32项、增加作用域断言后开发会话11项通过。模型调用实现未重写；仅在开工入口核对执行选择与固定起点。
- `d7354ab` 已推送；独立安装/刷新/离线安装通过，43隔离发布目录70项回归通过，Windows精确候选29项通过17.345秒。HTTP合成交接、重复请求、回答变化失效及页面显示通过。
- 复核补齐负责人变化时旧执行选择失效，59项定向回归通过；作为后续候选重新触发CI，不借用d7354ab的检查结果发布。此前快检、安装包和Windows执行证据专项成功，Linux完整当时仍运行。43尚未切换。
- `8ab6b1f` 精确CI `42191554868`：Linux3.11/3.13各8失败、2999通过、46跳过（Windows完整尚运行）；8项均在 `test_developer_merge` 的旧夹具确认后未选择执行方式而被新门禁拒绝。按新流程补负责人本地选择和固定起点断言，保留原合并/CI/身份断言，另补真实HTTP选择的伪造身份/非负责人拒绝与本人成功。21项复验通过；产品运行文件不变。失败日志保留，不部署失败候选，推送测试修订后等待精确CI。
- 测试修订提交 `3561a3b1143b9ad17191168c7471a2e03d1cc8ea`，与8ab6b1f的 `tmh/` 运行文件一致；精确CI `42193823161`。同提交43准备目录2421文件/15数据库副本通过，合并回归9项通过9.094秒；Windows隔离副本9项通过25.628秒。没有合并真实业务任务。待完整Linux门槛后切换43，阿里云不操作。
- 已完成43交付：运行 `3561a3b1143b9ad17191168c7471a2e03d1cc8ea`。精确CI42193823161的Linux3.11/3.13完整套件各3008通过、46跳过、1921子用例通过；快检、Linux/Windows安装包及Windows执行证据专项均成功。17:36记录时Windows完整套件仍运行，不宣称全平台通过。
- 2421文件清单、15数据库完整性与迁移副本核对通过。完整备份 `pre-3561a3b-test-20261106T093303Z/state.tar.gz` 55868文件逐字节一致。17:34:54 CST启动PID1528368；17:34:58即时、17:36:12延迟约74秒检查同PID、重启0，运行版本/目录、清单/数据库、内外登录200与匿名API401均通过。启动首次curl未就绪后既有重试成功；原始日志保留。
- 安装说明固定版本更新为3561a3b。实际运行代码与8ab6b1f一致；主实现d7354ab。客户Cursor桌面/怀柔项目两机链路未实测，Windows个人MCP凭据保护限制仍保留；自有Windows专项不替代客户接入或全平台兼容结论。阿里云生产未操作，真实业务任务未代人确认、复核、验收或合并。
- 三份保留备份均gzip及备份内platform.db完整性核验通过：pre-afddfca、pre-d83c267、pre-3561a3b。仅删除最旧pre-d7e2ed1的state.tar.gz（646443220字节），旧程序和元数据保留；审计 `/opt/webuddy/backups/retention-20261106-execution-handoff.json`。磁盘可用18GiB。后续仅补记录，不重启服务。


### 2026-11-06 网页与 MCP 交付依据、私有 CI 接入（进行中）

基线 811a49b，产品分支与远端一致，开始时工作区干净。复用内部 Git、候选、测试与人工门禁；增加同源只读交付依据入口，保留完整原始报告和当前有效性未知状态。私有 CI 按明确服务器连接配置接入，协议测试与客户现场联调分别记录。未提供客户 CI 地址和账号，真实联调尚未完成。

- 已实现同源 `delivery_get` / 网页下载 / CLI delivery：需求确认稿、测试方案、产出与差异、基线/候选报告、逐项证据、评估和人工历史；只读不运行 Git/进程/外部请求，当前有效性保持未知。候选页新增精确提交的必需 CI 查询，保留人工门禁。
- 私有 CI 新增运维登记的 HTTPS GitLab/Gitea 连接，按项目和仓库授权、环境变量凭据、完整 SHA 与必需检查核对；连接变化改变配置修订，查询异常、分页超限、缺失、失败/跳过/取消/未完成都受阻。GitLab 读取最新流水线，成功复跑不被旧失败永久阻塞。Jenkins、GitHub Enterprise及客户真实CI尚未接通，不宣称普遍兼容。
- Mac 114项定向回归、官方MCP SDK20项、团队/界面41项分别通过（部分重叠）。实际Chrome三尺寸下载和两尺寸候选CI查看通过；合成任务无测试/无CI不会显示可合并。初次路由清单计数失败保留，新增权限拒绝覆盖后复验。证据 [delivery-interfaces-20261106](evidence/delivery-interfaces-20261106/README.md)。待精确提交CI；43尚未发布本批。

- 初候选05f9b63已推送；Mac精确归档安装检查通过，自有Windows设备隔离源码25项CI/人工终端回归通过。复核发现Gitea畸形total_count或重复状态回执应明确拒绝，补校验和反例；17项CI复验通过，重新提交后等待新精确CI，不使用旧候选绿灯发布。

- 用户补充：客户CI尚未确定，授权先自建Jenkins，基于开源ERP进行定制并完整运行，准备终端追问、开发、测试与人工合并演示。采用已有JSHERP快照与回归资产，独立演示副本，不改原临时工作区的未提交修改。Jenkins需要真实自建协议与SCM绑定验证；此前“尚未适配”为当时状态，后续实现和实测另记。客户业务类型待答，正式规则不编造。

- 网页/MCP/GitLab/Gitea接口批次已发布43，运行代码89a5202390a092ae986cc8fba0d66f7cf32871c1，精确CI42207176912的10项必需检查全部success。Windows完整套件在该快照仍运行，未宣称全平台通过。最终候选2452文件清单、15数据库及40项差异回归通过，前批114项Linux回归亦通过。19:26:41 CST启动PID1555772，外部/回环200与匿名401即时通过；延迟检查回执另存证据目录。Jenkins新增适配仍在隔离环境开发，未混入本次发布包。

- 89a5202 延迟检查于19:29:46 CST完成，距启动约185秒，PID1555772不变、NRestarts0，运行目录/清单/数据库及内外200/401通过。备份 pre-89a5202-test-20261106T112505Z/state.tar.gz核对55909文件；代码回退入口releases/3561a3b/app，不能恢复旧库覆盖新写入。保留pre-d83c267/pre-3561a3b/pre-89a5202三份完整归档，仅移除pre-afddfca归档646450778字节，审计retention-20261106-delivery-interfaces.json。原始延迟与清理日志保留。

### 2026-11-06 自建 Jenkins + JSHERP 演练（进行中）

- Webuddy代码基线89a5202，远端产品HEAD一致。新增Jenkins只读适配，使用可信连接/项目/仓库/任务登记、Git插件完整SHA和结果；25项当前协议回归通过。真实Jenkins只读用户读取成功，POST build及config.xml均403。真实取消、失败构建查询均阻断；不是模拟返回或客户联调。
- 本机独立Docker网络启动SSH Git、Jenkins HTTPS、MySQL及Redis。原/tmp/webuddy-jsherp-local未提交改动保留。导入快照与原回归固定76dfc2c；首次构建因旧Maven源耗时取消；第二次后端成功，前端因无锁文件失败。新锁文件固定75a9311，第三次构建执行中。失败记录留独立部署包proof，不删除或写成通过。
- 新增退款说明演示规则、分轮问题、现场失败分支和既有试点模板链接；仅为演示假设，客户规则未确认。新增API/UI定制及真实浏览器断言待运行；尚未宣称完整ERP演示完成或发布Jenkins适配。

- Jenkins当前适配26项协议检查通过；从GitHub精确基线归档加本轮变更的独立副本58项权限/只读/合并集成通过。本机原目录读取pyc及部分源文件曾长时间阻塞，原运行中止/诊断保留，未删缓存或用户代码。
- ERP演示基线75a9311与候选4172462分开固定；新增退款说明5—200字符、仅非零销售退款、保存/修改共用后端校验与页面提示。真实诊断已得到旧版空说明保存成功且写1单、新版单/多账户拒绝非法说明且不写库，原保存/回读/防重复/未登录拒绝保持。首次浏览器脚本发现路由时序、宽屏表头分离与缺中文字库，修复测试宿主后重新执行，不冒充产品业务缺陷。正式Jenkins7/8前后对照运行中。

- 自建Jenkins正式前后对照完成：#7基线75a9311原57项JUnit通过，新规则空说明仍返回200且写1单，整体FAILURE；#8候选4172462的60项JUnit、14条真实MySQL/HTTP/浏览器业务检查通过，整体SUCCESS。同一控制侧脚本摘要，源代码/JAR/首页/进程身份绑定，结束源码不变。Webuddy适配器实际查询当前仓库/完整SHA得pass。
- ERP预览http://127.0.0.1:18981使用#8归档JAR与dist，下载后核对摘要；源代码另存erp-demo.bundle并verify通过。Webuddy隔离任务http://127.0.0.1:18985/#/t/ERP-1保存待澄清方案与真实Jenkins外部记录，明确external_test，未代人确认/审核/验收/合并。网页实际下载、官方MCP SDK真实stdio/HTTP读取一致，current_validity未知、ready_to_merge=null。此为合成操作令牌，不是客户个人连接联调。
- ERP字段校验和合法值恢复的实际浏览器补充检查通过，三尺寸原图保留；手机仍有原导航抽屉遮挡，不称移动适配完成。Webuddy任务三尺寸截图和真实下载保留。所有截图原编码原分辨率。提问材料20组及现场分支已准备；规则明确为演示假设，客户正式政策未编造。
- Webuddy实现638c256a851ecbcbbf3e2309bdf0d8fca57c2e3e已推送。精确CI42214979985十个必需检查成功；Windows完整3.11/3.13均失败，不称全平台通过。43准备2476文件清单与15数据库副本通过，58项精确回归通过。初次venv路径不存在，未执行测试；改用实际python3后通过，失败日志保留。
- 43于22:28:05 CST启动638c256，PID1598476；22:28:11即时和22:30:24延迟139秒同PID/重启0，运行清单、数据库、内外登录200/匿名API401通过。备份pre-638c256-test-20261106T142624Z/state.tar.gz，代码回退入口releases/89a5202/app；不以旧库覆盖新写入。阿里云未操作。容量保留结果后补。

- 638c256完整备份55940文件逐字节核对。22:31保留pre-3561a3b/pre-89a5202/pre-638c256三份已验证归档，只移除pre-d83c267归档734981754字节，旧程序与元数据不动；审计retention-20261106-jenkins.json。本轮仅43测试发布，未操作阿里云。
- 已生成本机Cursor/Claude只读演示MCP启动配置，官方SDK按该精确配置实际读取ERP-1成功；没有修改用户Cursor配置或声称桌面联调。配置与凭据留部署包private，不进入Git。记录提交晚于运行代码，tmh运行文件与638c256一致，不为材料重复重启。
- 结论：Jenkins接口、独立ERP定制与真实前后验证、网页/MCP历史依据读取和演示问题材料已交付；任务仍待人确认，Leader复核/负责人合并未代做。平台自动执行器从需求到合并的全链路、客户Jenkins/怀柔系统联调与实际提效均不在本轮已完成结论内。

### 2026-11-06 逐步操作留痕补齐

用户明确要求全部留痕，包含每一步手动操作。基线1ca49ac，工作区干净。本轮新增演示操作手册、14步真人现场记录表、历史实际方法与缺口说明，区分Agent/API/组件脚本与真人操作。未将早期缺少时间或逐键记录的历史倒填为完整；未替真人确认/复核/合并。

新增capture_step.py，逐次独立目录保存命令、操作者类型、实际UTC起止、退出码、完整stdout/stderr及SHA256；标签不是认证身份，exit0不等于验收。1项回归覆盖成功/失败/超时/启动失败及二进制字节完整性；本轮实际58项定向回归、真实官方SDK配置读取、5个基础容器状态查询都通过并逐步记录。产品tmh文件未变化；ERP原14项业务结果沿用此前记录，不说成这轮重跑。

13份仍在/tmp的历史脚本原件保存到部署包proof/operator-source，当前字节与摘要入索引；不保证代表每次早期执行版本。实际人工H01—H14均待真人执行。记录中另列截图上方“在写”与开发会话待澄清的展示映射待核对点，不隐去、不称本轮修复。证据入口evidence/jenkins-erp-20261106/operation-trace/。本轮只增加操作留痕资产与测试，不需重启43服务。

### 2026-11-07 项目知识共享协作优化（进行中）

基线7e2a57f，产品分支devin/1793765109-bidding-demo-ui与GitHub一致，开工工作区干净。复用项目知识、固定引用、共享经验和工单反馈，不改模型调用内核、不代人采用知识。目标：普通成员按授权项目检索且计数一致；固定来源更新可见但不自动升级；可带来源起草反馈；网页与原library_get接口共用结果。验收包含空权限、越权项目、撤权、私有经验、固定输入保持、真实HTTP和桌面/窄屏。

首轮126项定向回归通过。真实HTTP首验缺上下文令牌得到409，补夹具后因负断言误匹配Mac /private/tmp路径失败；改为匹配不可见业务内容后通过，失败原件保留。浏览器隔离服务合成普通成员已验证项目过滤、来源反馈草稿、新版提示；首次脚本误用nbody选择器，实际产品字段为nb，修正后通过。截图发现反馈弹窗在hash跳转时仍保留（保护草稿），补显式关闭后再检查引用页，不以遮挡截图冒充布局验收。后续验证和发布另记。

完成本轮功能：目录/搜索/项目选择与计数按账号权限前置过滤；固定引用只提示同来源已ready的新版本，撤权隐藏新版；网页可准备新版表单但保留旧引用与已有草稿；MCP library_get共用只读提示。反馈带来源及版本进入现有工单草稿，只读成员不显示起草。未新增模型执行、自动采用、跨项目通知或验收行为。

最终相关93项（92过、1可选SDK跳过）；前批126项与44项UI检查存在重叠，不相加。真实HTTP隔离1项通过；实际Chrome合成租户普通成员在1440×900和390×844验证授权目录、反馈草稿、固定引用提示和准备新版，未提交采用。原PNG及逐步命令回执见[evidence/knowledge-collaboration-20261107](evidence/knowledge-collaboration-20261107/README.md)。真实客户多人共享、人工试用、收益尚未验证。代码待精确CI及43测试交付，阿里云不操作。

代码候选cd01b4c1dd4670cddfe9b91ea3b5c66250e5cb81已普通推送。43隔离发布目录2565文件与精确清单一致，15数据库副本检查通过；当前Linux定向166项（165通过、1可选MCP SDK跳过），未切换服务。自有隔离Chrome和两个合成租户服务已关闭，未遗留登录会话或修改真实业务。待同提交必需CI完成后发布43。

cd01b4c精确CI42277266622的Linux3.11失败：3032通过、47跳过、2失败，均是test_lesson_decision_api仍期待普通成员读取/api/memory为403的旧契约。没有部署该候选。按本轮授权检索语义补齐真实HTTP断言：完整快照与正文、仅本项目列表、不泄露其他项目原文、只读账本不变；原旧确认409/越权403/错误项目404断言保留。产品运行代码未改，复验结果另记；失败完整日志已保留。
