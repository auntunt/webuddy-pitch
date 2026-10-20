---
id: tbl:OA_LEAVE
title: OA_LEAVE
summary: 请假单主表：提交后待审批，可被批准、驳回，超30天未处理自动作废
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# OA_LEAVE

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 归属业务域：[请假管理](../domains/leave.md)　类型：TABLE

**表结构**（`sql/schema.sql:15`）

```sql
CREATE TABLE OA_LEAVE (
  ID NUMBER(19) PRIMARY KEY,
  APPLICANT VARCHAR2(32),
  DEPT_ID NUMBER(19),
  DAYS NUMBER(3),
  REASON VARCHAR2(500),
  START_DATE DATE,
  STATUS VARCHAR2(16),           -- SUBMITTED / APPROVED / REJECTED / EXPIRED
  APPROVER VARCHAR2(32),
  APPROVED_AT DATE,
  CREATED DATE
);
```

**哪些业务流在用**

| 业务流 | 操作 | 业务域 |
|---|---|---|
| 查询请假单列表 | 查询 | leave |
| [审批通过：记录审批人与审批时间](../flows/post-leave-approve.md) | 修改 | leave |
| [驳回](../flows/post-leave-reject.md) | 修改 | leave |
| [提交请假申请](../flows/post-leave-submit.md) | 新增 | leave |
| [作废超期请假单（定时任务）](../flows/reportjob-expire.md) | 修改 | leave |

**状态流转（STATUS）**：(新建) → SUBMITTED（提交请假申请）；SUBMITTED → APPROVED（审批通过：记录审批人与审批时间）；SUBMITTED → REJECTED（驳回）；SUBMITTED → EXPIRED（每天凌晨作废超期单据）

**直接访问它的代码**：`LeaveMapper.approve`(U)、`LeaveMapper.expireStale`(U)、`LeaveMapper.insert`(C)、`LeaveMapper.reject`(U)、`LeaveMapper.selectPage`(R)
<!-- tmh:facts:end -->

## 业务含义
员工的请假申请单，一行一单（sql/schema.sql:15）。

## 关键字段
- STATUS：SUBMITTED / APPROVED / REJECTED / EXPIRED（sql/schema.sql:22）。
- DAYS：请假天数，提交时限 1～30（src/main/java/com/acme/oa/service/LeaveService.java:27）。
- APPROVER、APPROVED_AT：审批人及时间；批准时两者都写，驳回只写 APPROVER，不写时间（src/main/resources/mapper/LeaveMapper.xml:22,25）。
- START_DATE：建表有、列表查询会读（src/main/resources/mapper/LeaveMapper.xml:8），但 INSERT 不写（src/main/resources/mapper/LeaveMapper.xml:18），因此恒为空，列表显示空值【推断】。
- CREATED：创建时间，也是 30 天作废的判定依据（src/main/resources/mapper/LeaveMapper.xml:28）。

## 生命周期
提交即 SUBMITTED（src/main/resources/mapper/LeaveMapper.xml:18）；之后 APPROVED、REJECTED 或 EXPIRED，三者都是终态，代码中无再流转【推断】。EXPIRED 由每天 01:30 定时任务置位，条件 CREATED < SYSDATE-30（src/main/resources/mapper/LeaveMapper.xml:28）。

## 谁在读写
新增：提交请假；修改：批准、驳回、超期作废；查询：请假列表（分页，关联 OA_DEPT）。

## 注意事项
- START_DATE 从不写入，【待确认】是否应在提交时录入请假开始日期。
- 驳回不记 APPROVED_AT，与批准口径不同（src/main/resources/mapper/LeaveMapper.xml:25）。
- 列表用 Oracle 的 ROWNUM、(+) 外连接、SYSDATE，信创迁移需改写（src/main/resources/mapper/LeaveMapper.xml:5-13）。

