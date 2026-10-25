# PROPOSAL-EVIDENCE-01：原负控标注勘误

这是对b61771f验证叙述的追加更正，不覆盖或重写原脚本、日志、结果JSON和旧报告。

原作者将仓库外`proposal-root-negative/result.json`中`forget-proposal-cost`标为`detected_with_assertion=true`。其原日志实际只有`IndentationError: unexpected indent`，发生在编译内存注入时；**目标unittest没有执行，不能作为预算断言检出的证据**。原进程退出1是真的，把它解释成断言失败是错误的。

因此，进度及原领导者报告中的“三项都准确断言失败”应理解为被本勘误撤销的历史错误陈述；其中“忘记A费用”一项原结果是注入基础设施失败。不能用后来有效的新控制回填原作者这次失败。

原件摘要保持：

| 原件 | 字节数 | SHA256 |
|---|---:|---|
| proposal-root-negative/result.json | 629 | 2bd958eaf65072184ecdca5f951828477af8d56fce6a24ad2bb6443e38f6f404 |
| proposal-root-negative/forget-proposal-cost.py | 771 | e8749da55670cee4d462c98f6cedf1c71fe627ec2d1e753f5e375c6a7a1d13b9 |
| proposal-root-negative/forget-proposal-cost.log | 364 | e4d37aaf5982522fbd1a1dcb3f302ce67faa6cbe252fb3b7b4e5ddeaa0a1dcbb |

独立审查在固定b61771f上另外构造了有效注入：1 test、1 assertion failure、0 errors、实际退出1，预算累计断言为`0 != 16000000`。原报告和新控制保存在仓库外`分析/independent-review/20261025-b61771f-proposal-root-review/`，见`独立复核结论.md`、`review-decision.json`、`evidence-review.md`及`evidence-data/corrected-forget-proposal-cost*`。这是一份新的独立证据，不能冒充原负控通过。

独立结论是离线v3范围限定接受，无产品阻断；62项正常验证及同代际竞争属于其实际范围，不批准后续Token协议、Adapter移动WIP、真实模型或组织收益。

后续负控汇总必须同时验证：实际进程退出、结构化测试结果存在、tests数量、failures与errors、准确测试及子用例身份。语法/导入/夹具错误导致退出1时，明确作为基础设施失败处理；不能只根据exit1或输出中含FAIL猜测成功。旧原件保持不变，新验证另开目录。本次Token Adapter负控还发现，单靠注册拒绝可能被另一道合同不可变门掩盖，已加强直接上界解析断言，保留此前未能检出的控制，不把它改为成功。
