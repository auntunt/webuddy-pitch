# Jenkins 与 ERP 本轮证据

- contracts.log：26项当前适配器/私有CI协议回归；模拟HTTP边界，不冒充现场CI。
- integration.log：独立源码副本58项适配器、权限、只读交付依据、人工合并门禁回归。副本来自精确89a5202归档，叠加本轮5个运行/测试文件；没有修改原工作区未提交内容。
- jenkins-ci-aborted.json / jenkins-ci-failure.json：真实自建Jenkins经Webuddy产品查询得到的阻断结果。
- jenkins-reader-permissions.json：真实只读账号POST build/config均403。
- baseline-empty-reason.json：旧ERP接受空退款说明，实际新增1单；新演示规则尚未实现时的业务反例。

实际ERP源代码在独立演示仓库，基线75a9311d5bd485e7fe0701c042520831aa1fa44c，定制候选4172462acc9fce18f023aa88c0d229b9212ebe8d。完整运行日志、截图及构建档案保留在本机 `../部署包/jenkins-erp-demo-20261106/proof/` 与自建Jenkins，不是客户环境。

旧构建1取消、2缺前端锁文件失败、3/4路由等待失败、5/6宽屏表头定位失败保留。后续复验记录另行追加，不改写这些结果。定制版短程真实DB/API/浏览器诊断已通过，正式Jenkins前后对照仍在执行。

## 正式前后对照与交付

- Jenkins #7在75a9311：57项JUnit通过，新业务空说明检查失败（接口200且写1单）。#8在4172462：60项JUnit和14条真实HTTP/MySQL/浏览器检查通过。两次使用相同控制侧脚本摘要，源码/JAR/首页与运行进程身份有记录；构建结束HEAD及受跟踪文件不变。build-7/build-8保存报告与原始截图。
- jenkins-ci-pass.json：Webuddy适配器实际查询#8，核对注册仓库、完整提交和成功状态。与前面的失败/取消记录分开。
- preview/：真实ERP1440×900、768×1024、390×844截图；额外断言空白说明出现字段错误、有效说明清除错误。未保存补充UI表单。原ERP手机导航抽屉遮挡仍在，不宣称移动端适配。
- webuddy/：真实浏览器登录隔离服务，下载ERP-1交付依据并在三尺寸截图。mcp-delivery.json来自官方SDK的实际stdio→HTTP读取，方案与两条完整外部记录和网页相同。记录标识external_test，当前有效性未知，任务待澄清，无人工决定；不是自动开发全链路完成。
- 运行Webuddy代码638c256，GitHub Actions42214979985：10个必需检查成功；Windows3.11/3.13完整套件均失败，不能用workflow总success代替。失败仍涉及POSIX命令夹具、固定Git查询/预览、原子知识登记、探针等路径，未扩大跳过或放宽门禁。
- Mac独立源码副本58项、43精确发布目录58项相关回归通过。43最初使用不存在的venv路径导致命令未执行，改用实际系统Python后完成；首次失败原件保留。安装包由精确CI验证。
- 当前ERP只保存/回读/校验与防重复；客户CI、怀柔业务和客户两机联调未完成，模型/平台提效未测量。
