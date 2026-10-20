---
id: tbl:OA_APPROVAL_LOG
title: OA_APPROVAL_LOG
summary: 请假与报销共用的审批/操作日志表，只追加；字段名与 INSERT 语句不一致
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# OA_APPROVAL_LOG

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 归属业务域：[请假管理](../domains/leave.md)　类型：TABLE

**表结构**（`sql/schema.sql:50`）

```sql
CREATE TABLE OA_APPROVAL_LOG (
  BILL_ID NUMBER(19),
  OPERATOR VARCHAR2(32),
  ACTION VARCHAR2(20),
  COMMENTS VARCHAR2(500),
  CREATED DATE
);
```

**哪些业务流在用**

| 业务流 | 操作 | 业务域 |
|---|---|---|
| [审批通过：记录审批人与审批时间](../flows/post-leave-approve.md) | 新增 | leave |
| [驳回](../flows/post-leave-reject.md) | 新增 | leave |
| [提交请假申请](../flows/post-leave-submit.md) | 新增 | leave |
| [财务审核](../flows/post-expense-audit.md) | 新增 | expense（跨域） |
| [提交报销单](../flows/post-expense-submit.md) | 新增 | expense（跨域） |

**直接访问它的代码**：`ApprovalLogMapper.insert`(C)
<!-- tmh:facts:end -->

## 业务含义
请假、报销两类单据共用的操作留痕表，每次提交、通过、驳回追加一行（src/main/resources/mapper/ApprovalLogMapper.xml:4）。

## 关键字段
- BILL_ID：单据 ID，建表为 BILL_ID（sql/schema.sql:50），但 INSERT 写的是 LEAVE_ID（src/main/resources/mapper/ApprovalLogMapper.xml:4）。
- OPERATOR：操作人，申请人/审批人/审核人。
- ACTION：SUBMIT、APPROVE、REJECT（src/main/java/com/acme/oa/service/LeaveService.java:32,43,49）；EXPENSE_SUBMIT、EXPENSE_PASS、EXPENSE_REJECT（src/main/java/com/acme/oa/service/ExpenseService.java:50,67）。
- COMMENTS：请假提交为事由、驳回为意见、批准为 null；报销提交时放的是 category（src/main/java/com/acme/oa/service/ExpenseService.java:50），语义不一致。
- CREATED：SYSDATE。

## 生命周期
只有新增，代码中无更新、删除或归档【推断，仅就已见代码】。

## 谁在读写
只写不读：请假提交/批准/驳回、报销提交/审核共 5 个业务流新增；报销为跨域使用。无任何代码读取该表。

## 注意事项
- 【待确认】INSERT 列 LEAVE_ID 与建表列 BILL_ID 不一致，按现有脚本执行会报“列不存在”；是否有其它建表脚本或库里实际为 LEAVE_ID？
- 表中无单据类型列，请假 ID 与报销 ID 可能重叠，只能靠 ACTION 前缀区分【推断】。
- 因为是事务内写入，日志失败会让主业务一起回滚。

