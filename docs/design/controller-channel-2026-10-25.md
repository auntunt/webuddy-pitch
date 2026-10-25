# 非root控制器与受信配置边界：固定ID临时通道

本增量把可调度/优化控制角色移到UID/GID508103的独立进程。root仍是受信资产配置和执行broker，可以读取oracle；不是证明root不可读。候选508101、评估508102及固定文本动作沿用上一增量。当前仍为合成临时Linux实现，不是IDE执行、任意恶意代码沙箱、真实未见任务或组织收益证明，不安装常驻root生产服务。

## 受信通道

非root控制器只有两条固定FIFO：root所有者，request为0620/root:508103、response为0640/root:508103。controller仅有写请求、读响应权，不能改权限或替换端点。特权端在私有目录打开FIFO；控制器进入独立mount/PID/net/IPC namespace+chroot，仅绑定这两个FIFO，不绑定私有资产目录、Catalog、账本、配置、凭据或oracle。root目录/proc/环境/FD不通过继承传入控制器；补充组/capabilities清空、no_new_privs、系统库和proc只读。测试身份和组事先无账号/占用，以单独root-owned/tmp锁独占，不创建持久账号。

另在控制器root中放一个root0400的独立随机deny-canary，用来实际检查DAC拒绝；它不是oracle，不承载oracle内容或摘要。oracle和它的摘要均不进入控制器视图。受信root配置可读此文件和oracle是预期权限。

私有controller Catalog绑定公开plan/input、原根合同、私有执行计划、通道代码和固定控制动作。`Session.run`只接受登记的plan/input ID及取消信号；构造器的broker/目录属于受信部署配置，不能映射成任意外部路径参数。导入前仍须验证root-owned私有源树，导入后的摘要不能修复不可信Python导入。没有任意命令、UID、mount、env或预算RPC。

## 最小公开协议

每条请求精确四字段：action、plan_id、input_id、request_id。仅input/run/status/cancel，身份来自实际非root进程的固定文件访问权，不来自payload中的actor/UID。两ID必须匹配该次已准入固定任务；未知字段、私有详情、换ID及参数篡改只返回固定denied，不包含原异常、路径或值。

input返回完整已登记public capture；run只返回接受意图；status只投影state、冻结任务的verdict布尔、粗阶段和取消请求状态；cancel只发停止请求，不能代替停止/清理回执。oracle、私有计划、root合同、根pool、execution/binding等oracle派生摘要、原始错误和完整执行详情均不投影。控制器stdout中的自报成功不参与root结果判定。

帧为4字节长度与原始UTF-8 JSON。请求最多4096字节，公开响应最多8MiB，每次session最多128请求；超出拒绝，不静默截断。完整公开capture超过上限时，在controller/HTTP派发前拒绝，原始记录保持，不把部分内容当完整输入。保留原始完整history、原生产有效窗口及所有public字段。私有oracle只由root配置和独立评估器接触，控制器不能查询摘要来进行猜测；唯一允许的判定位只对应已冻结的同一任务/答案，不能通过换参数反复探测不同答案。

## 意图、预算与清理

复用原rsi_prepare_events追加根级controller_intent/finished，不新建表/预算。一次原provider request只允许一个controller绑定；同request_id正文重放返回原回复，不同正文冲突。不同controller请求号不会启动第二个root job。同plan/input再次调用返回原公共结果或unknown，不重启控制器、HTTP或候选；未完成意图不自动恢复。预算拒绝/预检可保留审计锚，不声称全数据库无变化。

root job异步调用原Launcher，保留原provider intent、原累计预算、根期限与候选/评估各3秒上限。控制器单独上限8秒且受同一根剩余期限约束，不刷新根预算，不用控制器watchdog掩盖候选的3秒timeout。控制器取消、失联、协议结束或源码变化会停止root job；执行未知仍由原账本保留最大预留/已知usage历史，不虚造第二笔费用。已确认完成的任务不会因随后controller出错而伪造未知提供商收费。

原SP回执继续绑定nonce/owner/output；只有controller与broker线程确认结束才释放测试身份锁，清理未确认保留意图/锁并拒绝自动重跑。没有root递归遍历/chown/删除角色树，不将历史PID当操作授权。控制通道完整公开收发和角色原件留在root私有现场，公共输出不包含私有异常正文。

## 未完成

真实Claude/Cursor工具及隐式会话、真实profile/可信价格、当前租户授权在生产入口的再核、通用敌对代码资源/系统调用隔离、生产专用身份及未知调查恢复仍未完成。固定文本exact-match与临时FIFO不能证明真实A→未见B/C→真人采用→D或多人长期提效。HTTP signed chunk-size限制在live准入前仍须限定支持框定；Windows原生监管/隔离/凭据ACL仍未完成。

## 本批验证范围

I1修后同一冻结488文件源：Mac相关45方法31通过/14显式root跳过；临时root-owned Linux通道14/14，再连续两轮28/28，均无失败/错误/跳过。三轮实际21控制器、12回环传输、12候选、3评估进程，共48原路径SP回执，逐份确认清理及原进程组消失。14不是14次内核执行，其中6纯方法、8root门控里1项只做准入拒绝。

独立诊断进程内分别放开响应FIFO写权、投影私有执行摘要、误信controller伪成功，三项原测试各产生1个预期断言失败且0error；未改源码/断言/时钟。相关成功与失败现场保留在仓库外分析目录，复制件与原路径回执明确区分。原3秒候选超时先于8秒控制器watchdog，失联取消和预算最大预留/无重发也覆盖。没有新全量、真实模型或生产接入验证，独立技术复审待。
