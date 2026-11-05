# 客户POC、Windows兼容与Review效果记录

2026-11-06 用户授权三项全部实施，验证后自动推送GitHub并更新43；阿里云不变。

验收目标：
- ERP退款需求：先固定金额规则，验证合法单/多账户、分摊不一致/非法金额无写入、正常回读和防重复；保留构建版本、HTTP、SQL和页面证据，不代人签收。
- Windows：按失败根因修复，实际Windows执行；安全契约不靠删除断言、continue-on-error或无依据skip放行。
- Review：按具体代码/审查记录有效问题、误报、人工发现和实际耗时，可汇总；没有人类样本或对照不得声称节省时间。

已查：当前HEAD a8534e1、43运行c730623，空间已清至约21GB。Windows失败主因包含CRLF、POSIX监管/持久化边界和测试资源释放。Windows SSH 43:12022本次超时，GitHub Windows runner可作为实际验证环境。旧原始日志/tmp/webuddy-proof-ci-windows.log可复用诊断。
