---
id: index
title: 传统 OA 办公系统
summary: 单体 OA：请假审批、费用报销（含部门预算）、用户管理，Spring Boot + Oracle + WebLogic
status: 待确认
updated: 2026-10-07 17:18
commit: 0959bbace3
---
# 传统 OA 办公系统

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 规模：模块 1，源文件 25，类 14，方法 53；入口 接口 10、定时任务 2；表 8；业务流 12；业务域 3。

**技术栈（自动识别）**：代码行 Java 409、XML 133、SQL 64、JSP 7；框架 Spring Boot、Spring、MyBatis、JSP (1)、MyBatis XML 映射 (5)；JDK 1.8，Spring Boot 2.3.12.RELEASE

**业务域**

| 业务域 | 业务流 | 一句话 |
|---|---|---|
| [请假管理](domains/leave.md) | 6 | 员工提交请假、审批人通过或驳回，超期未处理的单据由定时任务作废 |
| [费用报销与部门预算](domains/expense.md) | 4 | 员工提交报销、财务审核、出纳付款，并按部门月度预算冻结/释放/消耗额度 |
| [用户管理](domains/user.md) | 2 | 按工号新增员工用户、离职时停用，为其他域提供申请人身份 |

**代码模块**：[legacy-java-oa](modules/root.md)

**外部副作用**：写文件（1 处）、启动外部进程（1 处）、调用外部 HTTP 接口（1 处）

另见：[术语表](glossary.md) · [决定](decisions.md) · [坑](pitfalls.md) · [待确认问题](open-questions.md)
<!-- tmh:facts:end -->

## 系统是什么
一套面向企业内部的 toB OA 办公系统，覆盖请假审批、费用报销与部门月度预算控制、用户管理，另有两个夜间定时任务（`src/main/java/com/acme/oa/job/ReportJob.java`）。

## 用户与角色
代码里没有统一的角色/鉴权，接口靠请求参数传操作人。从流程看有：申请员工、请假审批人、财务（审核报销）、出纳（付款）、管理员（增/停用用户）（`src/main/java/com/acme/oa/controller/ExpenseController.java:33`）【推断】。是否需要权限控制见【待确认】。

## 业务域地图
- [费用报销与部门预算](domains/expense.md)：提交→财务审核→出纳付款，联动预算冻结/释放/消耗。
- [请假管理](domains/leave.md)：提交→审批通过/驳回，超期自动作废，夜间导出。
- [用户管理](domains/user.md)：新增、离职停用。
关系：报销与请假共用审批日志表 OA_APPROVAL_LOG；报销提交依赖用户表。

## 技术架构
Spring Boot 2.3 + MyBatis，controller → service → mapper 三层；Oracle 数据库（`src/main/resources/application.yml:4-5`），war 打包部署 WebLogic（`src/main/webapp/WEB-INF/weblogic.xml:4`）；外部依赖财务系统 `/api/pay`、共享盘文件；打印页依赖 IE ActiveX（`src/main/webapp/print.jsp:3-5`）。详见 [模块页](modules/root.md)。

## 维护须知
1. 最大风险：审批日志表列名建表（BILL_ID）与插入（LEAVE_ID）不一致（`sql/schema.sql:50`，`src/main/resources/mapper/ApprovalLogMapper.xml:4`）；预算按系统当前月份匹配；重复驳回重复释放预算；外部支付在事务内（见 [坑](pitfalls.md)）。
2. 平台绑定：Oracle 专有 SQL、Windows 路径与 cmd、WebLogic、ActiveX，信创改造需优先清点。
3. 测试仅 LeaveServiceTest，改动报销前先补特征测试。
4. 业务问题见 [待确认问题](open-questions.md)，术语见 [术语表](glossary.md)；所有页面尚无人确认。
5. 业务域按代码自动划分，ReportJob 的两个定时任务被归入请假域，归属待业务方确认。

