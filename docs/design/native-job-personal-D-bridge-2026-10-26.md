# 原生评测job、本人报告引用与同根新任务D

本批是软件协议实现和合成验证，不代表真实模型试验、本人采用或组织收益已经发生。原PPT多人窗口已经结束，不顺延、不回填；之后的工程试验必须单独登记真实新起止和有限调用计划。2be8960两个快照P2、5eb957e有限执行协议已有各自限定独立接受，不能扩大为本批接受。

## 发布来源

私有 `native_job_bridge.Jobs.publish` 只接受前瞻finite-v7根、当前确切lesson修订、与其完整fix逐字匹配的原候选，以及已经实际执行的预登记双臂断言报告。它核对所有原provider intent/监督回执/完整输出、共同capture/计划/配置/代码/模型、原根及完整frontier。它不调用普通evaluate来补造native来源，不调用人的决定，也不新增模型调用。

原生job使用独立 `native_evaluate` 类型，写入既有learning_jobs，status为实际机器断言结论。普通启动入口仍只接受旧review/evaluate；任意未知job类型在采用门拒绝。没有新增或改变既有状态迁移。原生job的公开配置和结果只含原根、确切报告/修订摘要、数量和“固定原生文本策略”范围；完整输入、预期答案、原始输出、原件路径和监督身份保留在data目录下owner-only的native-learning/NJ…/evidence.json，不进入公开job或源码。

发布在原Registry→Store/SQLite→lesson保护内重新核验，并在lesson锁持有时实际commit。job、原根发布锚在同一SQLite事务；文件先独占写入并fsync。数据库失败时原件文件保留为孤立证据，原job/锚回滚；重试只能复用逐字相同的孤立文件，不覆写或重跑评估。已存在job的来源损坏不能由publish补修。

## 本人采用

既有个人登录、项目授权、HUMAN_ONLY、CAS和投影outbox保持。native job在原 `_job` 门中进入独立只读验证：原根create/注册/报告锚、原前缀attempt逐字指纹、全部固定原件、监督nonce/owner/输出及实际双臂文本/请求/模型、当前capture/知识、当前确切修订必须一致。旧普通job继续走原评测门，不能借一段native reason获得原生资格。

本人明确提交采用时，UI把其输入的完整原因与所选job的原根/确切报告摘要组成 `native-bc-decision-reference-v1`；不是自动提交或代签。服务端再次核验这份确切引用，裸文字、错误报告、过期原件或未知job类型不能登记人的intent。采用后的原生link还要求当前最新applied个人决定实际引用那个native job、确切修订仍被采用；普通job即使通过且引用相同报告文字，仍不能成为native provenance。

## 原根里的新D

D必须是此前原生意图/已消费留出集合中没有的实际新任务。实际生产capture必须通过原selector/renderer，明确包含已被本人采用的确切修订和完整正文。其计划固定原根、候选、个人决定、job、输入和followup family。独立D断言在私有registry预先冻结并追加原根登记，在任何D请求前核摘要；不进入发给模型的输入。

D请求沿同一个有限calls/window/停止计数，在完整输出被确认前不认为成功。普通报告read仍要求原完整frontier，不能普遍忽略晚到请求。原生job链只允许那个已登记D的唯一自身attempt扩展前缀；其他late attempt、未知结果、撤回、修订或输入/断言变化全部拒绝。D的原provider响应通过固定工具外断言子进程验证，最多3秒且不超过原根余时；先登记唯一评估intent，缺回执/未知时不自动重跑。失败断言是失败，不把HTTP成功、模型自评或job的历史passed当作D成功。

finite入场新增同事务reserve/intent：Registry外层授权→Store/SQLite写事务→lesson锁→当前性检查和reserve/intent→实际commit→释放lesson。原公开reserve/intent包装继续复用相同内部逻辑，禁止嵌套事务的规则不放宽。真实第二进程分别验证commit时文件锁仍被持有，以及SQLite写入者在竞争入场等待时能够取得lesson锁，避免反向锁序死锁。

原生已提交意图、已消费留出和D预登记保留跨根的稳定任务身份及原输入摘要。新根不能重置这些暴露；相同任务重捕获不同历史/原始SHA也不能冒充新的终测任务。旧合同、失败和暴露集合不回写；原根幂等读取仍可进行。

## 能证明的范围

原生job与D均只证明固定文本、冻结原输入、实际知识消费和可执行输出断言，不证明完整CLI工具会话、强OS oracle隔离或真人多人组织收益。fixture标记保持，rsi_qualified和production_equivalent保持false；不得据此认定80分或自动采用/关单。真实本人未采用时D等待本人，不以合成个人决定替代。
