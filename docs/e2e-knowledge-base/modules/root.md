---
id: mod:.
title: OA 办公系统主模块
summary: 单体传统 OA 应用（Spring Boot + MyBatis + Oracle，WebLogic war），含请假、报销、用户。
status: 待确认
updated: 2026-10-07 17:17
commit: 0959bbace3
---
# OA 办公系统主模块

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 目录：`（仓库根）`　构建文件：`pom.xml`　源文件 25 个（测试 1）　类 14 个（入口层 3 / 业务层 6 / 数据层 5）

**最长的方法**（改动风险高）

| 方法 | 行数 | 位置 |
|---|---|---|
| `ExpenseService.submit` | 19 | `src/main/java/com/acme/oa/service/ExpenseService.java:34` |
| `ExpenseService.audit` | 17 | `src/main/java/com/acme/oa/service/ExpenseService.java:55` |
| `ExpenseService.pay` | 10 | `src/main/java/com/acme/oa/service/ExpenseService.java:74` |
| `LeaveService.submit` | 10 | `src/main/java/com/acme/oa/service/LeaveService.java:25` |
| `LeaveService.approve` | 8 | `src/main/java/com/acme/oa/service/LeaveService.java:37` |
| `ReportJob.export` | 7 | `src/main/java/com/acme/oa/job/ReportJob.java:17` |
| `UserService.add` | 6 | `src/main/java/com/acme/oa/service/UserService.java:15` |
| `LeaveService.reject` | 5 | `src/main/java/com/acme/oa/service/LeaveService.java:46` |

**被调用最多的方法**（改了影响面大）

| 方法 | 调用方数 | 位置 |
|---|---|---|
| `ApprovalLogMapper.insert` | 5 | `src/main/java/com/acme/oa/mapper/ApprovalLogMapper.java:8` |
| `ExpenseMapper.selectById` | 2 | `src/main/java/com/acme/oa/mapper/ExpenseMapper.java:12` |
| `UserMapper.selectById` | 2 | `src/main/java/com/acme/oa/mapper/UserMapper.java:9` |

**改动最频繁的文件**（git 历史）：`src/main/java/com/acme/oa/service/ExpenseService.java`(2 次)、`pom.xml`(1 次)、`sql/proc_leave.sql`(1 次)、`sql/schema.sql`(1 次)、`src/main/java/com/acme/oa/controller/ExpenseController.java`(1 次)、`src/main/java/com/acme/oa/controller/LeaveController.java`(1 次)、`src/main/java/com/acme/oa/controller/UserController.java`(1 次)、`src/main/java/com/acme/oa/job/ReportJob.java`(1 次)
<!-- tmh:facts:end -->

## 职责
整个应用是单模块的传统 OA（Spring Boot 2.3 + MyBatis + Oracle，打 war 包，部署 WebLogic），包含请假、报销、用户三块业务（pom.xml:4-16；src/main/webapp/WEB-INF/weblogic.xml:4）。

## 结构与依赖
- 分层：controller（3）→ service（3 个业务类）→ mapper（5 个，对应 src/main/resources/mapper/*.xml）；另有定时任务 ReportJob、工具类 PasswordUtil。
- 依赖：Oracle JDBC ojdbc8、PageHelper（helperDialect=oracle）、sigar 本地库（pom.xml:19-22；src/main/resources/application.yml:6-7）。代码中未见 sigar 的使用【推断】。
- 数据库：10.1.1.20 的 Oracle ORCL，库账号 oa，未配密码（src/main/resources/application.yml:4-5）【待确认】密码来源。
- 数据库对象：sql/schema.sql 建表，sql/proc_leave.sql 有存储过程 P_LEAVE_STAT（按月统计请假），应用代码中无调用方【推断】。
- 前端：src/main/webapp/print.jsp 使用 ActiveX、LODOP 控件和 IE 条件注释（src/main/webapp/print.jsp:3-5），仅 IE 可用。

## 代码健康
- 最长方法为 ExpenseService.submit（19 行）、audit（14 行）、pay（10 行），改动风险集中在报销（src/main/java/com/acme/oa/service/ExpenseService.java:34、55、71）。
- ApprovalLogMapper.insert 被 5 处调用，改它影响请假与报销所有审批日志（src/main/java/com/acme/oa/mapper/ApprovalLogMapper.java:8）；其 LEAVE_ID 列同时存报销单 id。
- 平台绑定：Oracle 专有 SQL（SYSDATE、CONNECT BY、ROWNUM、(+)）、Windows 路径与 cmd（src/main/java/com/acme/oa/job/ReportJob.java:19-22、src/main/resources/application.yml:9）、WebLogic 描述符、ActiveX。
- 安全：PasswordUtil 用无盐 MD5，且用 new String(bytes) 转换摘要，会损坏字节，结果无法可靠比对（src/main/java/com/acme/oa/util/PasswordUtil.java:7-10）。代码里未见调用方【推断】。
- 缺少权限校验：接口都靠请求参数传操作人（如 src/main/java/com/acme/oa/controller/ExpenseController.java:33）。
- 测试只有 LeaveServiceTest 一个文件，报销与用户无测试。

## 维护建议
- 改报销流程先看 flow:post-expense-audit 的重复审核问题，再动代码。
- 数据库、中间件、操作系统迁移时，先抽出 Oracle 方言和 Windows 依赖清单（见上）。
- 修改 ApprovalLogMapper 前先确认 5 处调用方。
- 数据库密码、上传目录等配置应外置【推断】。

