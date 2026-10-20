---
id: tbl:OA_BUDGET
title: 部门月度预算
summary: 按部门和月份记录预算总额、冻结额与已用额，支撑报销预算控制
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 部门月度预算

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 归属业务域：[费用报销与部门预算](../domains/expense.md)　类型：TABLE

**表结构**（`sql/schema.sql:42`）

```sql
CREATE TABLE OA_BUDGET (
  DEPT_ID NUMBER(19),
  MONTH CHAR(6),
  TOTAL NUMBER(14,2),
  FROZEN NUMBER(14,2) DEFAULT 0,
  USED NUMBER(14,2) DEFAULT 0
);
```

**哪些业务流在用**

| 业务流 | 操作 | 业务域 |
|---|---|---|
| [财务审核](../flows/post-expense-audit.md) | 修改 | expense |
| [出纳付款](../flows/post-expense-pay.md) | 修改 | expense |
| [提交报销单](../flows/post-expense-submit.md) | 查询修改 | expense |

**直接访问它的代码**：`BudgetMapper.consume`(U)、`BudgetMapper.freeze`(U)、`BudgetMapper.release`(U)、`BudgetMapper.remaining`(R)
<!-- tmh:facts:end -->

## 业务含义
每个部门每月一条预算记录，报销提交时占用（冻结），付款时转为已用，驳回时释放（sql/schema.sql:42；src/main/resources/mapper/BudgetMapper.xml:4-13）。

## 关键字段
- DEPT_ID + MONTH(CHAR(6)，yyyymm)：定位预算行；建表未声明主键/唯一约束（sql/schema.sql:42）【推断】。
- TOTAL：当月预算总额。
- FROZEN：在途报销占用额度，默认 0。
- USED：已付款额度，默认 0。
- 剩余额 = TOTAL - FROZEN - USED（src/main/resources/mapper/BudgetMapper.xml:4）。

## 生命周期
- 预算行的创建（月初录入）不在本代码中，来源未知【待确认】。
- 提交报销：FROZEN 增加（src/main/resources/mapper/BudgetMapper.xml:7）。
- 驳回：FROZEN 释放；付款：FROZEN 转 USED（src/main/resources/mapper/BudgetMapper.xml:10、13）。

## 谁在读写
- 提交报销单：读 remaining、写 freeze。
- 财务审核：驳回时 release。
- 出纳付款：consume。
- 全部以“当前系统月份”匹配，而非报销发生月（src/main/resources/mapper/BudgetMapper.xml:10、13）。

## 注意事项
- 跨月风险：月末提交、次月付款/驳回时，冻结与释放落在不同月份的行，上月 FROZEN 不释放、本月可能为负或更新 0 行【推断】。
- freeze 的 UPDATE 无余额条件，并发可超额（src/main/resources/mapper/BudgetMapper.xml:7）【推断】。
- 使用 SYSDATE/TO_CHAR（Oracle 方言）。
- 【待确认】预算行由谁、何时录入？跨月报销应按哪个月扣？

