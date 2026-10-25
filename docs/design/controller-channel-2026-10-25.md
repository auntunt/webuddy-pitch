# 非root控制器与受信配置边界：固定ID临时通道

本增量把可调度/优化控制角色移到UID/GID508103的独立进程。root仍是受信资产配置和执行broker，可以读取oracle；不是证明root不可读。候选508101、评估508102及固定文本动作沿用上一增量。当前仍为合成临时Linux实现，不是IDE执行、任意恶意代码沙箱、真实未见任务或组织收益证明，不安装常驻root生产服务。

## 受信通道

非root控制器只有两条固定FIFO：root所有者，request为0620/root:508103、response为0640/root:508103。controller仅有写请求、读响应权，不能改权限或替换端点。特权端在私有目录打开FIFO；控制器进入独立mount/PID/net/IPC namespace+chroot，仅绑定这两个FIFO，不绑定私有资产目录、Catalog、账本、配置、凭据或oracle。root目录/proc/环境/FD不通过继承传入控制器；补充组/capabilities清空、no_new_privs、系统库和proc只读。测试身份和组事先无账号/占用，以单独root-owned/tmp锁独占，不创建持久账号。

另在控制器root中放一个root0400的独立随机deny-canary，用来实际检查DAC拒绝；它不是oracle，不承载oracle内容或摘要。oracle和它的摘要均不进入控制器视图。受信root配置可读此文件和oracle是预期权限。

私有controller Catalog绑定公开plan/input、原根合同、私有执行计划、通道代码和固定控制动作。`Session.run`只接受登记的plan/input ID及取消信号；构造器的broker/目录属于受信部署配置，不能映射成任意外部路径参数。导入前仍须验证root-owned私有源树，导入后的摘要不能修复不可信Python导入。没有任意命令、UID、mount、env或预算RPC。

## 最小公开协议

每条请求精确四字段：action、plan_id、input_id、request_id。仅input/run/status/cancel，身份来自实际非root进程的固定文件访问权，不来自payload中的actor/UID。两ID必须匹配该次已准入固定任务；未知字段、私有详情、换ID及参数篡改只返回固定denied，不包含原异常、路径或值。

input返回完整已登记public capture；run只返回接受意图；status只投影state、冻结任务的verdict布尔、粗阶段和取消请求状态；cancel只发停止请求，不能代替停止/清理回执。oracle、私有计划、root合同、根pool、execution/binding等oracle派生摘要、原始错误和完整执行详情均不投影。控制器stdout中的自报成功不参与root结果判定。

帧为4字节长度与原始UTF-8 JSON。请求最多4096字节，公开响应最多8MiB，每次session最多处理128请求，之后终止；第129条不读取，不单独返回denied。帧大小超限拒绝，不静默截断。完整公开capture超过上限时，在controller/HTTP派发前拒绝，原始记录保持，不把部分内容当完整输入。保留原始完整history、原生产有效窗口及所有public字段。私有oracle只由root配置和独立评估器接触，控制器不能查询摘要来进行猜测；唯一允许的判定位只对应已冻结的同一任务/答案，不能通过换参数反复探测不同答案。

## 意图、预算与清理

复用原rsi_prepare_events追加根级controller_intent/finished，不新建表/预算。一次原provider request只允许一个controller绑定；同request_id正文重放返回原回复，不同正文冲突。不同controller请求号不会启动第二个root job。同plan/input再次调用返回原公共结果或unknown，不重启控制器、HTTP或候选；未完成意图不自动恢复。预算拒绝/预检可保留审计锚，不声称全数据库无变化。

root job异步调用原Launcher，保留原provider intent、原累计预算、根期限与候选/评估各3秒上限。控制器单独上限8秒且受同一根剩余期限约束，不刷新根预算，不用控制器watchdog掩盖候选的3秒timeout。控制器取消、失联、协议结束或源码变化会停止root job；执行未知仍由原账本保留最大预留/已知usage历史，不虚造第二笔费用。已确认完成的任务不会因随后controller出错而伪造未知提供商收费。

原SP回执继续绑定nonce/owner/output；只有controller与broker线程确认结束才释放测试身份锁，清理未确认保留意图/锁并拒绝自动重跑。没有root递归遍历/chown/删除角色树，不将历史PID当操作授权。控制通道完整公开收发和角色原件留在root私有现场，公共输出不包含私有异常正文。

## 未完成

真实Claude/Cursor工具及隐式会话、真实profile/可信价格、当前租户授权在生产入口的再核、通用敌对代码资源/系统调用隔离、生产专用身份及未知调查恢复仍未完成。固定文本exact-match与临时FIFO不能证明真实A→未见B/C→真人采用→D或多人长期提效。HTTP signed chunk-size限制在live准入前仍须限定支持框定；Windows原生监管/隔离/凭据ACL仍未完成。

## 本批验证范围

I1修后同一冻结488文件源：Mac相关45方法31通过/14显式root跳过；临时root-owned Linux通道14/14，再连续两轮28/28，均无失败/错误/跳过。三轮实际21控制器、12回环传输、12候选、3评估进程，共48原路径SP回执，逐份确认清理及原进程组消失。14不是14次内核执行，其中6纯方法、8root门控里1项只做准入拒绝。

独立诊断进程内分别放开响应FIFO写权、投影私有执行摘要、误信controller伪成功，三项原测试各产生1个预期断言失败且0error；未改源码/断言/时钟。相关成功与失败现场保留在仓库外分析目录，复制件与原路径回执明确区分。原3秒候选超时先于8秒控制器watchdog，失联取消和预算最大预留/无重发也覆盖。没有新全量、真实模型或生产接入验证，独立技术复审待。

## C1：完成缓存须重新验证原隔离证据

ac4b227的独立审查确认：只核controller缓存与自身SP，不足以证明candidate/evaluator原件目前仍可验证。C1窄修把原隔离重放整理为共用只读入口：先核当前登记来源与原provider intent，再核isolation原锚/binding.json/execution-result、两角色原SP的owner/nonce/结果及完整output绑定。缓存evaluated/verdict必须与原独立执行结果一致；原件损坏/缺失或换绑定拒绝，不用历史缓存通过现时验证。

`Launcher.replay(plan_id,input_id,provider_intent=...)`只读，不调用dispatch、provider、角色或controller进程，不登记新意图、事件或预留。controller先退出原数据库事务再调用，避免嵌套事务；原isolation dispatch的既有完成分支也复用同一验证器。原根期限、预算、schema及未知最大占用不变，不修补旧记录。合法的provider尚无意图而controller已unknown，可重放unknown且不创建attempt；无原isolation锚不能支撑缓存成功。未知不升级为成功。

本验证针对一次读取时的证据完整性，不阻止受信root在验证后修改私有材料，不证明非root可写原件。新普通本地测试使用真实SP/SQLite/Catalog及完整缓存入口，特权源码/所有权预检被替代，不冒称namespace/UID证明；另有真实root隔离C1回归。最终冻结489源的Mac37方法22通过/15root跳过、Linux显式root37/37；最终普通回放两轮18/18。源码/调用cwd/前后清单、原红灯与修中误拒绝保留于仓库外controller-C1-20261025证据，独立修后复审仍待。

旧三项诊断负控是在一个进程各产生一条unittest失败，外层SSH实际exit0，不是三份独立exit1；旧Mac45 invocation缺cwd/源绑定，版本归属仅有包和交接的间接支持；初次precommit失败缺独立原命令traceback。这些限制不以本批新结果回填。真实CLI/profile/试点仍未运行，不给组织收益评分。

## C2：临时返回字段不参与持久快照比较

bf4fbd4独立复审限定关闭C1，但发现第二条completed分支将begin_isolation返回的`{anchor,result,new_execution:false}`与仅`{anchor,result}`的持久snapshot整dict比较，误拒绝完好证据。修正仅复制持久anchor/result作为比较基准；原件/结果/角色SP核验与末尾快照重读均保留，调用者item不被修改。pending/unknown不升级，预算和历史不变。

新增四条回归核真实begin completed item、完整第二分支的确定性时序、损坏/快照变化，以及pending/unknown。第二分支回归的cached provider/SP和lease有明确替身，不是特权竞争或新HTTP证明。冻结489源上，两正控在旧实现准确失败；修后Mac/Linux相关28方法各19通过/9root跳过，没有重跑旧root/H1/L1/fa3/I1矩阵。普通SP子环境新增PYTHONDONTWRITEBYTECODE，声明文件和整个导出source成员前后均核一致；旧独立491源的额外pyc原件保留，不能用本轮结果回填旧成员不变。
