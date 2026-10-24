# 真实试验的预登记检查

先阅读 [实施合同 v2](../../docs/design/cross-task-rsi-pilot-2026-10-25-v2.md)。本目录是本地准备工具，尚未接入生产实验 API，不会启动模型、改数据库或操作真实试点。

```sh
python3 scripts/rsi/check_preregistration.py scripts/rsi/preregistration.v2.template.json
```

样板未填真实项目、参与者及证据，预期输出 `blocked`、退出1。只能在真实负责者给出信息后填写新文件，保留原样板；凭据、答案和受保护终测材料不放入此 JSON。文件内只有其声明的编号及证据摘要，工具不沿路径读取任何证据。

退出0表示 `declared_complete`：声明结构齐全；退出1表示 `blocked`：具体依赖缺失；退出2表示 `invalid`：格式、类型或确定重复/冲突。输出包含原始文件SHA，不打印原文或字段值。无法读取文件时SHA为null。

**三个结果都不授予执行或签字权限。** 工具无法确认人名、同意、源家族独立性、供应商计量、费用、隔离或摘要所指证据是否真实；`evidence_verified=false`、`execution_authorized=false`、`score=null`始终保持。声明正控使用虚构成员，只测试结构，不能计入真实多人试点。

检查包括：A/B/C/D声明家族分离、至少三条留出实例与两个家族、确定的重复编号/输入SHA、优化者与托管人分离、五环节责任归属、两个正时长且不重叠的周期、累计调用/token/微人民币/期限正整数、模型与审查证据引用。拒绝编号首尾空白；opaque ID按精确字符串比较，不据此声称语义独立或识别近重复。每一调用的实际计量及硬门仍由后续受控执行器实现，本工具不能代替预算账本。


v2声明对齐单一预冻结候选、B/C一次独立终测、效果数值门槛和真实试点日历/任务全集；v1样板仅保留历史兼容。两者均不执行、不核证、不计分。

`trial_preparation.py`是尚未接生产入口的事务组件，供隔离临时Store验证：统一根预算预留/意图/未知/结算，终测实例一次消费，进程代际和原始锚。它不会被Store自动初始化，无模型或任意进程派发功能。调用方提供的scope/model/usage/价表仍需未来可信服务端adapter验证；inspect始终明确execution_authorized、provider_evidence_verified和os_holdout_isolation_verified为false。不能用它开启付费试验或声称OS隔离已经具备。
