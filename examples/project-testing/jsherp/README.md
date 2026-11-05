# jshERP 测试接入

基准：导入项目 JSHERP 的 `8f5dc087`。`overlay/` 为新增测试源码，`apply.py` 将它们安装到指定工作树，并执行两个相关修正：启用原先被 Maven 配置跳过的测试编译；修复单笔金额转负数被当作字符数组处理的问题。安装不会创建业务数据、启动外部服务或代人验收。

```sh
python3 examples/project-testing/jsherp/apply.py /path/to/jsherp-checkout
```

测试使用项目已有的 Spring Boot Test、JUnit 和 Mockito；前端纯函数使用 Node 内置测试工具，直接加载实际 `util.js`，仅隔离未调用的下载/UI依赖。

| 范围 | 内容 | 验证边界 |
|---|---|---|
| 金额与查询 | 十进制精度、大额退款、无效金额、排序输入与唯一查询 | 直接执行业务工具函数 |
| 登录规则 | 密码、禁用账号、禁用/过期租户、数据库异常 | 实际服务，数据库依赖隔离 |
| 验证码 | 缺失、过期、错误、重放、消费和显式关闭 | 实际服务，Redis依赖隔离 |
| 接口访问 | 未登录读写、登录放行、路径穿越 | 实际 Filter，隔离会话存储 |
| 单据编号 | 锁顺序、冲突、异常释放、打断和所有权令牌 | 实际服务，数据库/Redis依赖隔离 |
| HTTP契约 | 编号序列化、业务失败、错误请求方法 | Spring MockMvc；不是网络端到端 |
| 前端业务 | 大整数与进位、审批规则、退款、查询与合并 | 实际纯函数；不是浏览器界面测试 |

## 运行

后端需要 Java 8，前端需要支持内置 JUnit reporter 的 Node（已用 Node 20 以上验证相关运行方式）。报告路径由项目测试配置指向，不以 Maven 的 BUILD SUCCESS 单独判通过。

```sh
mvn -B -f jshERP-boot/pom.xml -Dmaven.test.failure.ignore=false -DfailIfNoTests=true test
mkdir -p target
node --experimental-vm-modules --test --test-reporter=junit --test-reporter-destination=target/frontend.xml .webuddy-tests/frontend.test.cjs
```

Windows 使用 `.webuddy-tests/backend.ps1 -JavaHome <Java8目录>`。`profile.windows.json` 可作为平台“项目测试”的配置，执行位置为已登记的 SSH 测试机。它不自动安装 Java 8，也不掩盖测试机断连或缺工具。

此配置是通用回归基线，所以未将套件映射成某张工单的全部验收项。具体需求应新增真实用例、设置精确映射，并按需要打开 `require_all_criteria`。

新增 [销售退货业务验证](business-proof/README.md)：在独立本机 MySQL/Redis/应用/Chrome 环境验证单账户和多账户保存、读取、页面金额及重复单号拒绝；4 条方案标准逐项关联用例。使用 `profile.business-local.json`，不能直接覆盖 43 的普通回归配置。单据未审核，不代表财务过账或库存审核。

**仍须单独验证：**其他采购、库存、销售与财务流程；完整键盘/下拉框交互；数据库迁移、并发负载及依赖漏洞修复。

实测记录：Linux Java 8 后端40项、Node前端17项通过（新增3项数组输入回归）；Mac前端使用 `npm install --legacy-peer-deps --no-audit --no-fund` 后构建成功。依赖审计检出187项（严重36、高危59、中危81、低危11），安全检查尚未通过。此安装参数解决既有webpack4的peer依赖解析冲突，不代表这些旧依赖已修复。

43测试站现已在JSHERP启用本机执行配置（2026-11-05），Java8/Maven在`/opt/webuddy/tools`。Windows合成测试通过，但Java8安装受下载中断阻碍；`profile.windows.json`保留为环境就绪后的切换配置，不表示ERP已在Windows验收。43 ERP本地提交`65bcbd28`（数组修复及业务测试资产，后端40/前端17项在43通过），未推上游公共仓库。
