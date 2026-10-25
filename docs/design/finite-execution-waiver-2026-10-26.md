# 前瞻有限执行：解除Token总上限

本实现只提供新的私有服务端执行协议，不启动真实模型，不延长已结束的PPT多人试点，不代任何人采用知识或验收。不修改历史100M或20元合同，不把旧20元恢复为新许可门槛。

## 合同与执行边界

新提案合同 `trial-finite-proposal-v6` 和绑定配置后的 `trial-finite-provider-v7` 使用 `limits.max_total_tokens: null`。数字（包括极大整数）、缺字段或混入旧费用字段均拒绝。保留有限calls、starts_us、deadline_us；新计划须登记其真实新时间，不能回填旧窗口。授权摘要只能属于一个原根，既有原根不能换合同、更新预算或换代恢复执行。

本版budget.unit为observed_tokens，authorization_sha256绑定真实许可依据，prior_evidence_sha256保留之前证据的引用；不将该摘要或没有新调用解释为历史总用量为零。总账billed_tokens、实际费用和隐藏请求数未知，单独累计有完整可解释供应商报告的reported_tokens。response_usage_status为unknown时该部分和未完成请求仍未核清；reported_responses_only也不证明代理隐藏尝试、实费或整个组织的总用量。

## 独立配置与网络

新配置 `server-fixed-text-finite-adapter-v3` 只接固定Messages/Responses文本协议，经私有目录、完整合同/代码摘要、当前凭据身份、非root执行身份和HTTPS校验。显式新FiniteBroker复用已保护的真实capture、当前权限、知识选择器/渲染器、稳定预封任务身份、唯一input×arm、断线幂等及个人采用门。旧TokenBroker不能接新合同，新入口也不能接旧合同；旧profile仍必须有可信inclusive bound，绝不全局放宽旧协议。

不要求新profile提供100M硬上界或no_hidden_retries声明。资源限制与账单上界明确分离：max_request_bytes核对完整编码请求长度，超出则在reserve/HTTP前拒绝，不截断；output_cap_tokens只是固定请求的输出参数，不能用来证明供应商或代理的全部计费Token上界。旧attempt字段input_limit在此schema下保存字节资源阈值，绝不计作Token预留。单次监督超时取调用期限与原根剩余时间的较小值，原完整响应与监管回执保留。

## 响应、停止与复用

文本身份/模型/结束状态/唯一完整文本仍独立校验，工具输出、不完整或多义文本不能绑定候选。完整原始usage保留；缺失、额外不支持维度或不一致计数不会补零，归为unknown。仅缺用量不把一个已完成的文本请求变成未知执行结果，也不为已经解除的总上限拒绝后续有限计划。每个返回仍不代表真实RSI资格。

HTTP/监督/取消/模型不匹配等导致执行结果未知时，原根阻挡继续调用；相同编号查询原结果，不产生新的intent、网络重试或自动换根。预intent取消仍消耗一次原计划尝试数，取消后不能刷新调用额度。原候选、留出暴露、当前权限与知识撤回规则保持；只读报告必须仍通过本次2be8960的发布/本人引用快照检查。

## 验证与剩余依赖

新增合成回环验证覆盖无bound且无usage的Messages、部分usage的Responses、超过旧100M的报告用量、原合同原字节保持、有限次数和期限、请求字节拒绝、相同编号并发单次HTTP、真实监督取消/5秒超时及不重发；另以当前个人权限和原capture执行七次共同输入双臂及原断言worker，核对留出重捕获拒绝、报告回放和知识撤回失效。均不构成真实模型或多人收益证明。

原生learning job发布、确切报告与真人采用的绑定、同根D仍是下一依赖；普通job不得因本合同或一段reason文字被洗成native。没有新生产路由、个人工具执行权限扩张、自动采用或后台定时任务。
