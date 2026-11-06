# Jenkins 与 ERP 本轮证据

- contracts.log：26项当前适配器/私有CI协议回归；模拟HTTP边界，不冒充现场CI。
- integration.log：独立源码副本58项适配器、权限、只读交付依据、人工合并门禁回归。副本来自精确89a5202归档，叠加本轮5个运行/测试文件；没有修改原工作区未提交内容。
- jenkins-ci-aborted.json / jenkins-ci-failure.json：真实自建Jenkins经Webuddy产品查询得到的阻断结果。
- jenkins-reader-permissions.json：真实只读账号POST build/config均403。
- baseline-empty-reason.json：旧ERP接受空退款说明，实际新增1单；新演示规则尚未实现时的业务反例。

实际ERP源代码在独立演示仓库，基线75a9311d5bd485e7fe0701c042520831aa1fa44c，定制候选4172462acc9fce18f023aa88c0d229b9212ebe8d。完整运行日志、截图及构建档案保留在本机 `../部署包/jenkins-erp-demo-20261106/proof/` 与自建Jenkins，不是客户环境。

旧构建1取消、2缺前端锁文件失败、3/4路由等待失败、5/6宽屏表头定位失败保留。后续复验记录另行追加，不改写这些结果。定制版短程真实DB/API/浏览器诊断已通过，正式Jenkins前后对照仍在执行。
