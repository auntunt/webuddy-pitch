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
