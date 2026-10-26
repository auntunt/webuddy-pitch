# 权威输入到固定合成探针：内部验证切片

本模块只供可信宿主显式调用，没有 HTTP、CLI、MCP 或平台启动接线。它不运行官方 Codex、模型或知识采用，不是可供业务使用的新执行入口。`Probe(P, authenticated_actor)` 的主体来自宿主已认证上下文；请求只有 root/request、项目、工单、两份经验修订 ID 与 baseline/candidate arm。工具 content 凭据、无执行能力的 manager 和跨项目来源不能用它获得执行权。内部 tree 模式只用于受监督清理夹具，不能从请求指定。

`Ledger.for_store` 借用实际 Store 连接与 RLock，只在自己的 cursor 上使用 sqlite3.Row，不改连接 row_factory、PRAGMA 或所有权；close 不关闭 Store。已有事务一律拒绝。原三张 Codex 台账表不改，新适配器仅显式初始化一张 codex_learning_dispatch。它不是新的预算或任务状态机，不修改旧 rsi_prepare 表。

T1 在 Registry→Store→同连接 BEGIN IMMEDIATE→实际命名 lesson 锁内捕获。输入包含完整工单、原始 UTF-8 修订、授权的来源证据及参考文件、选择池、included/omitted、实际内存干预、公开路由与版本。二进制参考内容按原字节的 base64 保留；超过8MiB拒绝，不截断。root 合同的 baseline/candidate 摘要必须对应已存修订 content 的原始 UTF-8 字节，不可改用 fix 或另一种 JSON 摘要。基线修订是冻结比较资料；runtime_baseline 另记现行可用知识，不把未采用的旧修订当成已采用规则。候选只在内存视图变为 active，原知识台账和人工决定不变。

宿主构建标识从本地应用仓库 HEAD 和实现文件摘要取得，和项目提交分列；不能从 root 自报值推断宿主身份。这是可信宿主下的本地构建绑定，不是外部生产者认证或对任意文件篡改的远程证明。

生命周期/私有 reserve 检查在普通业务写入前执行。预留、Store._create_run_in_tx（含知识输入）和完整 input BLOB 同事务提交。混合事务遇到任何异常，包括 Stopped，都整笔回滚；之后仅以独立 stop-only 事务锁存 root/已有 attempt 生命周期及停止事件。停止提交失败返回真实数据库错误，不假称已停。原独立 Ledger API 的成功 Stopped 提交及 TX01 失败回滚语义保留。

同槽进程内互斥加现有 filelock 覆盖最新 claim/原件读取→Runner._control→T2。Store/Registry 锁先释放，再取得 Runner 锁；任何原 claim、owner/lifecycle/attempt（含不完整 setup）都禁止重新 control 或领取 owner。T2 重读权限、来源、协议、路由、取消和原窗口，intent 与一次性 claim 原子提交。失败保留原文件和异常，只释放本控制器实际取得的 lease。认领后丢失首个 lease 时，受限 Runner 禁止 run_command 重新 claim。新控制器或新 request 不能返还原累计槽或绕过在途状态。

只使用 IndependentRunner→Runner.run_command→现有 supervised_process。固定 Python 代码从 stdin 读取完整输入，返回字节数及摘要；没有伪 Codex JSONL。目标只在入口/Registry/Store/lesson/DB 锁全部释放后启动。观察将控制器、监督器与目标 PID 分列，合成目标启动数与真实 Codex 启动未知分列。

总预算取原绝对结束点与控制器入口单调预算的较小值；预检、锁等待、Git 和登记消耗均扣除。监督器收到实际剩余量；没有额外5秒 watchdog。锁等待和只读 Git 查询尚无可中断证明，因此不承诺调用硬性按时返回。清理宽限不延长成功窗口。正常结束先写运行终态并封存，_sealed_run 核对唯一 attempt、owner、输出和完整清理，再把现场 observation 与结算同事务写入。

两个文件/数据库窗口仍不可原子化：终态行已写但 finished 文件封存失败，以及文件封存后 observation/settle 提交失败。两者都保留原件与异常，维持 intent/unknown 或待核对，不补成成功、不重 owner、不重派、不开放下一槽。取消前检查可阻止目标启动；最后检查到实际 Popen 之间没有原子零启动保证。on_spawn 后撤权或失去 lease 的测试只证明监督停止与清理。原件和直接数据库改写不能当作授权输入。

所有结果保持 producer_authenticated/execution_admitted/adoptable=false、production_prompt_equivalent=false；真实 Codex 启动/身份、HTTP、任务验收和实付为 unknown/None。合成探针收到资料，不证明模型遵循知识或组织收益。新 A 的候选待定 schema、私有未见 B/C、官方认证与运行闭包、本人采用及新 D 均未接入；旧永久停止 root 不复活。原预算/API门不恢复。

本切片定向：`python3 -m unittest -v tests.test_codex_dispatch_probe`。临时真实 Registry/Store/SQLite、第二连接读锁、触发器、跨控制器/进程入口锁、固定本地目标与真实三代进程；不读取生产数据/凭据，不调用模型或网络。测试的2秒就绪屏障、Future 等待限额是夹具断言，不是产品 watchdog。Windows 监督器、任意逃离进程组的后代、直接 fork 宿主复用以及强杀监督器的运行闭包未在本切片证明。
