# 固定登记 ID 的 Linux 隔离交付：最小增量

本增量实际运行两个分离身份的固定程序：候选把已登记公开输入和原 provider 原生文本结果交付为完整 blocks；独立 evaluator 才能读取私有 oracle，对完整 blocks 做 exact-match。它不是任意代码沙箱、IDE 执行适配器或真实业务评测。`production_equivalent=false`、`rsi_qualified=false` 保持；真实 profile、A/B/C/D 与真人决定仍 pending。

## 输入和权限

`Launcher` 只能由受信服务器代码在显式 Linux root 临时夹具中构造，`dispatch` 仅接受登记 plan/input ID 和取消信号。没有 root RPC、shell/命令参数、外部 UID、挂载源或环境入口，也没有生产启动钩子。构造器中的目录和 broker 对象属于受信控制面的部署配置，不得直接映射成 HTTP 参数。导入代码本身必须由受信部署流程先验证并放在 root-owned 私有源树；文件摘要不能让从攻击者源树导入 Python 变安全。

两套私有 Catalog 分别登记执行合同与 oracle；合同固定原公开 plan/input 摘要、原 root 合同、执行 bundle、oracle 摘要、固定动作及 3000ms 上限。缺失/未知字段/任意命令/变化来源在新 HTTP 或 namespace 派发前拒绝。当前只允许 `deliver` 和用于真实取消/超时验证的固定 `hang` 动作，不执行模型提供的命令或代码。

候选只得到原 capture 全文与完整 native response，不得到 oracle、它的摘要、任意完整执行详情或提供商凭据。公开输入保留完整原始 history、原生产有效窗口和所有来源；候选的输出只选择已有原生 response 的完整 content blocks，不截断文本或媒体。本增量仅支持原适配器的文本协议，不把媒体转换成缩略信息。

## 实际执行边界

controller 使用 root，候选/评估各使用固定且不同的临时数值 UID/GID 508101/508102，不创建持久账号，不使用共享 nobody。运行前用 root-owned /tmp 锁独占这对测试身份，拒绝已有账号或活动进程占用。这仍是临时测试身份约束，不是已经部署的生产身份服务。

两个角色各自进入 mount/PID/network namespace 和独立 chroot。只挂载只读系统运行库与只读 proc；没有宿主 home、业务目录或控制面挂载。候选的 root 中根本不放 oracle。评估角色的 oracle 文件仅属于其数值身份；仅把固定候选完整输出投影给评估角色，不挂载候选可写目录。外层控制/证据目录保持0700；在严格umask=077下显式设置新建沙箱内部固定目录0755，oracle文件仍为评估身份0400。清空环境、补充组、capabilities，设置 no_new_privs；不继承目录/凭据 FD，stdin 为 DEVNULL。固定程序会实际检查这些内核观察，不把自报检查当通用恶意代码不可逃逸证明。

调用使用原已审 `supervised_process` / `process_control`，每阶段上限取原根绝对期限与3秒的较小值。候选与评估各有原始 output.bin、nonce/owner 绑定监管回执；取消/异常不会继续启动 evaluator。任何程序错误只产生固定错误标识，不把 oracle 内容拼入异常或公共返回。评估只返回布尔结论和候选原始输出摘要。错误答案是 `verdict=false`，不会因为程序正常退出而变成通过。

root 不递归遍历、chown、删除或“回收归属”候选/评估树；保留原所有者与整个现场。namespace 挂载随进程消亡清理，不安装常驻 privileged 服务。仍需针对实际编程工具、资源限制、系统调用/文件系统扩大、多个生产身份和长期运行另行实现并审查。

## 原根账本与未知语义

只在原 `rsi_prepare_events` 追加根级 isolation_intent/isolation_finished，不新建预算或费用表。一次原 provider request 只能绑定一次执行来源，完整已知 provider 回执是进入执行的前提。相同登记 ID 重放返回原结果；待决返回 pending，不启动第二个 namespace 或 HTTP。新进程代际不能借此恢复新派发。

执行待决时，原 root 阻止其他派发，原 attempt 按最大预留计入总额；不把已知 provider 历史用量删掉。正常完成并拿到完整独立回执，才将待决预留恢复为原已知用量。执行未知使原 attempt 变为 unknown，原用量/settled 事件保留、最大预留持续、root 阻塞。沿原“settled 后 unknown”规则拒绝晚到结算释放。它是保守预算占用，不是声称发生了第二笔提供商收费。

提交执行意图后即使 controller 崩溃、目录创建失败或最终结果写入失败，根级待决仍阻止新派发并保留最大值；不依据时间过去或进程消失自动重试。最终事件写入与未知状态变更同一 SQLite 事务回滚。失联/损坏材料的人工调查流程及生产恢复仍未实现。

## 不计入完成的内容

真实模型/价格及 usage 取证、真实 Claude/Cursor 工具与隐式会话等价、任意候选代码执行、生产专用身份、真正未见任务的独立评估、真人采用及 D 后续验证、多人成本和收益证据、Windows 原生隔离/监管/凭据 ACL均未由本增量完成。HTTP signed chunk-size 已知限制仍在真实 profile 准入前阻止启用，不用合成成功给组织收益评分。
