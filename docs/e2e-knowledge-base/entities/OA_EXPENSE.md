---
id: tbl:OA_EXPENSE
title: 报销单
summary: 员工报销申请单，记录金额、类别、审核与付款信息及状态流转
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 报销单

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 归属业务域：[费用报销与部门预算](../domains/expense.md)　类型：TABLE

**表结构**（`sql/schema.sql:28`）

```sql
CREATE TABLE OA_EXPENSE (
  ID NUMBER(19) PRIMARY KEY,
  USER_ID VARCHAR2(32),
  DEPT_ID NUMBER(19),
  AMOUNT NUMBER(12,2),
  CATEGORY VARCHAR2(20),         -- 差旅/招待/办公
  STATUS VARCHAR2(16),           -- SUBMITTED / AUDITED / REJECTED / PAID
  AUDITOR VARCHAR2(32),
  AUDITED_AT DATE,
  CASHIER VARCHAR2(32),
  PAID_AT DATE,
  CREATED DATE
);
```

**哪些业务流在用**

| 业务流 | 操作 | 业务域 |
|---|---|---|
| 我的报销单 | 查询 | expense |
| [财务审核](../flows/post-expense-audit.md) | 查询修改 | expense |
| [出纳付款](../flows/post-expense-pay.md) | 查询修改 | expense |
| [提交报销单](../flows/post-expense-submit.md) | 新增 | expense |

**状态流转（STATUS）**：(新建) → SUBMITTED（提交报销单）；SUBMITTED → AUDITED（财务审核）；SUBMITTED → REJECTED（财务审核）；AUDITED → PAID（出纳付款）

**直接访问它的代码**：`ExpenseMapper.auditPass`(U)、`ExpenseMapper.auditReject`(U)、`ExpenseMapper.insert`(C)、`ExpenseMapper.markPaid`(U)、`ExpenseMapper.selectById`(R)、`ExpenseMapper.selectByUser`(R)
<!-- tmh:facts:end -->

## 业务含义
一张报销申请，从员工提交、财务审核到出纳付款的全过程载体（sql/schema.sql:28）。

## 关键字段
- ID：主键，来自序列 SEQ_OA_EXPENSE（src/main/resources/mapper/ExpenseMapper.xml:10）。
- USER_ID、DEPT_ID、AMOUNT、CATEGORY（注释：差旅/招待/办公，无约束；sql/schema.sql:28）。
- STATUS：SUBMITTED / AUDITED / REJECTED / PAID。
- AUDITOR、AUDITED_AT：审核人与时间；CASHIER、PAID_AT：出纳与付款时间。
- CREATED：创建时间。无驳回意见字段，意见仅进审批日志。

## 生命周期
提交即 SUBMITTED（src/main/resources/mapper/ExpenseMapper.xml:13）→ 审核 AUDITED 或 REJECTED（src/main/resources/mapper/ExpenseMapper.xml:17、20）→ AUDITED 后付款 PAID（src/main/resources/mapper/ExpenseMapper.xml:23）。REJECTED、PAID 为终态，未见撤回、删除【推断】。

## 谁在读写
- 提交报销单：新增。
- 财务审核：查询并更新（auditPass/auditReject）。
- 出纳付款：查询并更新（markPaid）。
- 我的报销单：按用户查询。

## 注意事项
- CATEGORY 在提交时未校验取值（src/main/java/com/acme/oa/service/ExpenseService.java:48）【推断】。
- 状态更新 SQL 带前置状态条件，可防并发重复审核/付款（src/main/resources/mapper/ExpenseMapper.xml:17、20、23）。
- 表中没有 REJECT 意见、没有记录释放预算所属月份，跨月时见 [OA_BUDGET](OA_BUDGET.md)。
- 【待确认】CATEGORY 合法取值是否固定为差旅/招待/办公？

