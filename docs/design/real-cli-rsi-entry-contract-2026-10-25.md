# 真实 CLI 跨任务试验：现有入口、最小合同与拒绝边界

状态：blocked_before_live；核对基线 `ac4b227df20c7d43e65b4b31a7435dc2d069a394`。这是实现前的可审合同，不是新增执行权限、可运行计划或已冻结的真人试验协议。继承[实施合同 v2](cross-task-rsi-pilot-2026-10-25-v2.md)及现有评分分母，不改留出数、3秒候选限制、8秒临时控制器限制或任何人工决定。真实模型调用/付费0，真实试点not_run，production_equivalent=false、rsi_qualified=false、score=null。

## 具体入口与断点

| 路段 | 已有代码与行为 | 未闭合的真实接口 |
|---|---|---|
| 平台授权→外部工具 | `tenant_gateway.make_handler` 的个人工具路由在 Registry 授权锁内校验个人连接；`tool_access.allowed_operations` 仅read/content，后者只增加ticket_create/message_send；`workbench_client.Client.permits/call` 拒绝个人连接执行或人工操作 | 没有 RSI 执行领取授权；读任务、发消息均不是领到执行租约。不能给现有read/content增加执行权作为捷径 |
| 读完整任务→返回外部提交 | `agent_api._execute` 的ticket_get返回需求指纹、知识引用与现有操作；`candidates.submit` 核项目Git、完整提交/基线、需求、工作区和验收条件 | 外部Git产物登记不携带本次真实CLI逐调用用量、根预算、capture及独立终测绑定，不能成为RSI已执行证明；完整工单packet也不等于生产有效prompt |
| 当前知识→生产公开输入 | `registered_trial.capture` 调用原agents.build_prompt/selector/renderer，保存完整来源、history和原有效窗口；`effective/assert_pair` 在native Messages形式下只允许system策略不同 | capture的tenant/project是受信调用者传入，不是未来执行权；native Messages无真实CLI隐式会话/工具/工作目录。当前cap中的GAPS保持，不凭prompt/messages相同升级等价 |
| 学习登记→执行与结果 | `learning_experiments.VERSION`为fixed-a-synthetic-v1，`learning_experiment_runs.start_sealed/_slot_material` 运行原合成槽；`learning_runs.start/_Worker.step` 可运行独立Claude，`get`明确cost=unknown | 生产合成协议与临时rsi_prepare_*根账本没有已授权的真实协议桥。manual无工具Claude仍不是包含工具/全部成本的RSI闭环；不把synthetic表的标签换成live |
| 真实CLI运行 | `agents.command` 构造Claude/Codex参数；`Runner.invoke` 有resume失败换新会话及busy重试；`run_command` 保存每次cwd/命令/原prompt与原SP产物。`learning_runs._configuration` 冻结Claude无工具参数及bin大小/mtime并拒绝Codex | 原SP证明进程与原字节，不证明CLI内部调用数/实际模型权重/真实费用；bin大小/mtime不是完整可执行依赖身份。临时空cwd、fresh/no-tools也不能证明所有CLI隐式上下文相同。stdout费用或一个CLI PID不能替代每次调用的可信计量 |
| 原根预算→临时执行 | `registered_trial.Broker.dispatch` 只接fixture-provider-only，live在registered_plan锚及HTTP之前拒绝；`provider_adapter.Registry.load/Adapter` 对live要求专用非root owner；`controller_channel.Session` 为root临时配置器并使用该fixture链 | 不能把root夹具中的registry模式改成live；真实transport的专用身份、配置、限制与特权配置器之间还没有受审接线。ac4b227正独立复审，本批不改其代码 |
| 原始产物→独立终测→人工采用/D | `registered_isolation.Launcher` 与controller临时通道验证固定文本和私有exact-match；生产`learning_decisions`保留真实人工采用/撤回；原handoffs/角色工作台记录成员交接 | 当前固定文本原件不是实际IDE/CLI受监管产物；未见B/C托管、真实业务终测规则、确切报告→真人决定→新D使用及多人周期仍缺真实输入。不能由Agent补签、虚构参与者或复用已曝光终测 |

## 最小纵向合同（未实现、未授权开跑）

唯一目标是把一条平台已授权任务绑定到已有领取/运行/产物入口，再由既有可信终测接收结果；不新增通用执行平台、不开放任意命令/UID/mount/env，不介入Claude/Cursor内部编码循环。

1. **服务端任务授权。** 从当前登录身份、租户/项目成员权及当前工作区派生任务作用域；固定完整需求、来源/引用和授权代际。执行入口、worker启动前及产物提交时均重核。外部仅提交服务端已登记的任务/计划ID，不接受客户端自选root_pool、项目路径或授权声明。领任务、取消与业务验收是不同权限。任何未来执行凭据需单独窄合同，现有个人read/content凭据继续拒绝执行。
2. **完整共同输入。** 由真实服务端上下文一次capture。baseline/candidate使用同应用提交、同原始资料/history/附件/引用、同renderer/有效窗口、同执行器及运行环境，只有预冻结策略及其版本不同。完整公开输入交给CLI，不交oracle或其摘要。若任一侧超限，整对拒绝；原文和历史保存，不裁剪凑限额。必须另外封闭工具定义、系统提示、设置、hook/MCP、恢复会话、隐式指令、工作目录及可读文件集合；native Messages配对检查不能证明这些相同。
3. **同根计量与先决拒绝。** 原实验根覆盖提炼、基线、候选、终测、D、重试和工具额外费用，期限不刷新。实际执行器/模型版本、配置/可执行依赖、可信价格或供应方硬上界、全部可计费维度、CLI内部调用/重试及工具费有可信约束才允许首个可付费动作。自报usage、stdout估价、max_calls=CLI进程数、仅exit0均不足。任一未知，首次派发前拒绝；有意图后未知则保留原最大预留，不重发、不退款。
4. **原执行与原始产物绑定。** 复用原SP及原根唯一intent，固定任务ID、capture/策略/应用/执行器/模型/根合同与实际attempt、cwd、会话/配置身份、原始stdout/stderr/产物完整字节及摘要；原SP nonce/owner/清理回执留在原路径。不同来源即使文字同也不得重标旧回执。Git候选还须经过现有完整基线/commit/需求与工作区校验；外部提交成功不代表模型计量已验证。
5. **独立判定与人类决定。** 原可信终测入口只接绑定一致、清理确认的原产物；未见B/C至少两族三实例及一次消费不降低。模型文本或controller自报成功不能写最终结论；错误仅公共粗投影，oracle及私有摘要不回传。独立技术复审不代替真人知识采用/业务验收。真人采用确切报告后，真实新D确实选中策略才记D使用；撤回和后续任务使用必须可核。

## 允许变更面与后续验收

本批仅本合同和进度的事实修正；不改运行代码、API、表、凭据范围、controller候选或旧封存报告。下一软件候选应先选定现有`learning_*`登记/worker中的单一桥接点与明确真实执行模式，再提交固定SHA复审；不能先暴露临时底层Catalog或任意callback给客户端。具体实现文件须以选定模式及真实profile合同为准，当前不承诺一份可直接执行的命令模板。

下一候选最少验收：当前授权撤回/换工作区/换需求后零派发；非执行凭据拒绝；任一侧共同输入或隐式上下文不封闭则整对零派发；实际模型/价表/内部重试或工具费不可信则首付费前拒绝；并发同意图一次登记；失联/取消/超时后未知最大占用且零重发；原始完整产物及SP身份不能借另一任务回执；私有终测信息不投影；真人采用/D/撤回门不被技术测试替代。只针对具体桥接增量测试，不重复旧H1/L1/fa3矩阵。

## 当前确切依赖与停点

软件缺口仍存在：生产真实协议桥、执行领取窄授权、CLI全上下文冻结及逐调用计量、非root真实transport与特权配置之间的受审接线。真人资料不是这些代码已完成的借口；本合同明确列为未实现。

但当前还缺决定这条桥实际输入和可信边界的原两项信息：获授权模型profile的服务器位置、明确模型/协议与可信价格/上界；真实试点项目/托管人/参与职责/周期与试验协议。已有有限服务器检查未找到所查位置的可用profile，不能推断全机没有；不重复扫描密钥或再问同一问题。没有profile不能选定真实CLI的认证、强制计量路径与隐式上下文，不能用回环或假CLI代替。没有真人试验协议不能生成真实A/B/C/D、托管答案、采用或多人投入。

因此本批停在可审合同和现有入口差距清单：不伪造live/真实组织证据，不为填补等待时间新增一层合成隔离框架。待明确实际受控执行模式及现有信息请求返回后，按上述断点切最小接线；此前仍可依据ac4b227独立复审的确切反例做窄修。
