# 原生双臂语义报告与本人引用：第一段合同

本增量只实现提案前断言登记、原双臂原件核验、固定程序独立进程评估，以及既有本人决定对确切报告的只读引用核对。**没有完成 native learning-job 发布及同根 D 执行桥，LIVE D 仍由原 TokenBroker 拒绝。** 不新增生产路由/预算，不写 learning_jobs/learning_steps/learning_decisions，不启动模型，不代本人采用。

## 提案前原登记

`Reports.freeze(root, reference)` 只读原 owner-only Registry 的 `<reference>.json`。规格精确列出 schema、原root、完整contractSHA、原授权SHA、全部预封case及阈值；case绑定 Catalog input_id/raw SHA/来源族、固定 validator/expected/forbidden。完整集合与原根逐项一致，不允许少样本、重复输入或任意新输入；阈值必须明确，不提供现场默认值。沿现有程序断言能力至少三对、候选全部通过、无回退且有改善，允许显式加严，不允许0改善/布尔伪整数等放宽。

登记追加在原 rsi_prepare_events，所有 provider attempt 和候选派生之前一次冻结；相同原登记可重放，事后补登记、替换阈值/断言、换授权根均拒绝。全部原输入、profile、应用提交、模型与实现束摘要绑定。代码不会生成或批准真实试轮规格；测试文件中的断言和阈值都是合成资料，不能当作用户真实试轮已登记。

## 全部执行来源与评估

读取原根全部attempt，不只挑成功双臂；任一 reserved/intent/unknown/cancelled/失败或响应不完整均不产生通过报告。用原 Adapter.reconcile/SP 校验每个已完成响应、原profile/完整用量/原始body及清理。六个 input×arm须对应唯一的原 registered_plan、原 Catalog 输入/计划/策略；两臂共用原capture/current/selector/renderer。原集合在候选绑定时已消费，训练族不能借此重新暴露。

评估是本仓库固定 `native_bc_worker.py` 的独立受管进程，复用原 learning_eval.check 的 exact/contains_all/json_equal 语义；不接受模型评分、调用方passed或任意命令。标准输入为私有断言和原响应全文，标准输出只有断言结果。范围仅为预封输出断言，不能证明一般业务正确。进程使用原SP owner/nonce/完整输出/清理回执，最多3秒且受原root剩余绝对期限约束。它与控制器同UID，**不是独立帐号、oracle对任意本地代码不可读或完整内核隔离证明**；固定文本候选不执行代码，未向提供商发送expected/forbidden。

原根先登记唯一 evaluation_intent；中断或报告提交失败保留原件/未决，不自动再跑。原断言进程不调用模型，不增加Token额度或提供商调用。报告绑定所有attempt指纹、完整双臂来源、候选策略、原登记/模型/应用/profile及评估原件SHA。提交事务重核整个attempt集合，晚到预留不能被漏掉；后续新增attempt会使该报告当前性失效。报告不是D的最终读取协议，D追加attempt的精确豁免尚待后续软件，不能提前放行。

## 本人决定的精确引用

`Reports.decision_link(root, decision_id)` 只读原实际 applied/adopt/lesson 决定、确切修订/来源/当前采用指针和原 evaluate job。本人保存的原 reason 必须是完整JSON：`schema=native-bc-decision-reference-v1`、`root_pool`、`native_report_sha256`、`reason`。引用摘要必须等于核过全部原件的本报告；默认说明文字、仅候选SHA、仅普通job passed或另一个根的报告都不匹配。读取采用 Registry→Store→lesson 锁和SQLite一致快照；撤回/后来重采用使旧决定不可冒充当前决定。没有迁移或回填旧人的reason。

该函数返回 `reference_verified=true` 只表示确切引用成立；当前明确返回 `job_native_provenance_verified=false/live_d_eligible=false/rsi_qualified=false`。**普通 learning_job 的执行/计量没有自动变成本原生根来源。** 下一段需实现原生job在双臂前的不可变登记，以及由真实原根/SP/独立评估原件发布的确切修订报告，再核本人决定及D实际选中/渲染、D追加attempt和同根消耗。不能把此引用核对器当作该桥已完成。

## 范围与上线边界

本批只新增 scripts/tests/design/progress，旧579共同输入窄面独立审尚未被本批自验代替。原学习与人工决定门、guard/acceptance/锁/MOVES、原四表DDL和生产218运行文件不变。真实原生HTTPS上界、内部全部尝试计量/模型映射、本人资料未因合成评估而获得证明；不修改CPA/外部网关、不试拨模型/自签上界、不另起100M根、不顺延00:30原截止或倒填19:30实际开始。
