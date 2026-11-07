# 销售退货保存与重复提交验证

验收标准固定在 `acceptance.json`。范围是单据保存、读取与防重复；单据保持未审核，不把它解释为财务过账、库存审核或客户签收。

真实路径：Chrome 登录种子账号 → 打开销售退货 → Vue 的表单/明细编辑接口填入数据 → 点击页面真实保存按钮 → 捕获实际 HTTP 请求和响应 → MySQL 查询 → API 重新读取 → 页面列表核对 → 立即及两秒后重复提交。没有模拟服务响应、数据库或 Redis。表单填充使用组件接口，不声称覆盖每个键盘和下拉框交互。

`verify.mjs` 生成 JSON 用例报告，包含业务输入、预期、实际结果；保留完整请求/响应、SQL结果和原始 PNG 截图。截图不调整像素或编码。立即重复提交可能命中 Redis 防重复；两秒之后必须命中数据库单号检查，且始终只有一张单据。

## 本次真实发现

- 原金额函数把单笔字符串按字符处理，`12.50` 转换错误。
- 上一轮字符串修复遗漏了页面的数组契约：单账户传空数组，多账户弹窗传金额数组，导致 `split is not a function`，保存前抛错。本轮同时支持这两种实际输入。新增三项数组测试先失败，再在修复后通过。
- 隔离环境首次 JVM 与数据库时区不一致，单据被写成次日，当前日期列表看不到。后续 JVM、JDBC、MySQL 都明确使用中国时区；这属于本次测试环境配置，不以改查询日期掩盖问题。

## 准备隔离环境

需要 Docker、Node、npm、Python 3、Git、Chrome。以下资源名称和端口专供本样例；不可指向业务数据库。所有容器端口只绑定回环地址。

在已运行 `apply.py` 的 ERP 检出目录执行：

```sh
docker network create webuddy-erp-proof
docker run -d --name webuddy-erp-mysql --network webuddy-erp-proof -p 127.0.0.1:18306:3306 -e MYSQL_ROOT_PASSWORD=webuddy-isolated-test -e MYSQL_DATABASE=jsh_erp mysql:8.0 --default-authentication-plugin=mysql_native_password --default-time-zone=+08:00
docker run -d --name webuddy-erp-redis --network webuddy-erp-proof -p 127.0.0.1:16379:6379 redis:7-alpine redis-server --requirepass webuddy-isolated-test
# 等 MySQL 就绪后导入项目自带的种子数据。
docker exec -i -e MYSQL_PWD=webuddy-isolated-test webuddy-erp-mysql mysql --default-character-set=utf8mb4 -uroot jsh_erp < jshERP-boot/docs/jsh_erp.sql
docker exec -e MYSQL_PWD=webuddy-isolated-test webuddy-erp-mysql mysql -uroot jsh_erp -e "UPDATE jsh_platform_config SET platform_value='0' WHERE platform_key='checkcode_flag'; UPDATE jsh_system_config SET multi_account_flag='1' WHERE tenant_id=63;"
cd jshERP-web
npm install --legacy-peer-deps --no-audit --no-fund
cd ..
python3 .webuddy-tests/business-proof/serve.py
```

最后一条前台运行，可放在独立终端。这里只为隔离的种子账号关闭图形验证码、启用多账户；生产设置不改变。验证码服务的单元回归继续保留。

Chrome 使用独立临时配置启动，调试端口 18982，不能连接用户日常浏览器。Mac 示例：

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --remote-debugging-port=18982 --user-data-dir=/tmp/webuddy-erp-test-chrome --no-first-run about:blank
```

为该测试环境配置 `../profile.business-local.json`，并使用 `acceptance.json` 中的五条方案标准。该配置要求逐项覆盖，包含构建、前端回归、真实业务测试及清理。**43 没有这套 Docker/Chrome 环境，不能直接把此配置覆盖它现有的本机回归配置。**

也可在准备好依赖后直接执行：

```sh
python3 .webuddy-tests/business-proof/prepare.py
node .webuddy-tests/business-proof/verify.mjs
python3 .webuddy-tests/business-proof/cleanup.py
```

准备阶段重新构建后端和前端，绑定 Git 基准/完整差异摘要、JAR、前端入口和实际容器身份。源码或运行版本变化后拒绝复用旧构建。平台会另外保存本次报告、日志和验收契约。清理阶段停止本次应用和构建容器，数据库、Redis、静态代理及 Chrome 由启动者在查看证据后关闭。

种子数据的账号为仓库自带的 `jsh / 123456`；这是隔离测试数据，不是任何线上账号。依赖审计的既有高危问题不因本样例通过而消失。


2026-11-06 增加 A5：不携带登录凭据分别提交新的单账户、多账户退款单，核对拒绝响应及数据库计数为 0。当前 ERP 的 `LogCostFilter` 使用 HTTP 500 和 `loginOut` 表示未登录，前端 `request.js` 也按此契约处理；测试核对这两个精确值，不把任意 500 视为通过。此检查不覆盖跨租户授权或财务过账。
