---
id: flow:post-expense-audit
title: 财务审核
summary: 财务对已提交报销单审核通过或驳回；驳回时释放部门预算冻结额，并记录审批日志。
status: 待确认
updated: 2026-10-07 17:20
commit: cbf8f6f3b5
---
# 财务审核

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[费用报销与部门预算](../domains/expense.md)　入口类型：接口　触发：`POST /expense/audit`

**调用链与数据（工具抽取）**

```text
POST /expense/audit  「财务审核」  [接口]
入口：ExpenseController.audit  (src/main/java/com/acme/oa/controller/ExpenseController.java:33)
调用链：
  - [入口] ExpenseController.audit (src/main/java/com/acme/oa/controller/ExpenseController.java:32)
    - [逻辑] ExpenseService.audit (src/main/java/com/acme/oa/service/ExpenseService.java:55)
      - [数据] ExpenseMapper.selectById (src/main/resources/mapper/ExpenseMapper.xml:7)
        - 查询 OA_EXPENSE
      - [数据] ExpenseMapper.auditPass (src/main/resources/mapper/ExpenseMapper.xml:17)
        - 修改 OA_EXPENSE
      - [数据] ExpenseMapper.auditReject (src/main/resources/mapper/ExpenseMapper.xml:20)
        - 修改 OA_EXPENSE
      - [数据] BudgetMapper.release (src/main/resources/mapper/BudgetMapper.xml:10)
        - 修改 OA_BUDGET
      - [数据] ApprovalLogMapper.insert (src/main/resources/mapper/ApprovalLogMapper.xml:4)
        - 新增 OA_APPROVAL_LOG
状态变化：
  - OA_EXPENSE.STATUS: SUBMITTED → AUDITED  (src/main/resources/mapper/ExpenseMapper.xml:17)
  - OA_EXPENSE.STATUS: SUBMITTED → REJECTED  (src/main/resources/mapper/ExpenseMapper.xml:20)
业务规则（代码中的校验）：
  - 若 e == null：报销单不存在  (src/main/java/com/acme/oa/service/ExpenseService.java:59)
  - 若 n == 0：报销单不是待审核状态，不能重复驳回  (src/main/java/com/acme/oa/service/ExpenseService.java:66)
事务：ExpenseService.audit
```
**涉及的业务对象**：[OA_APPROVAL_LOG](../entities/OA_APPROVAL_LOG.md)（新增）、[OA_BUDGET](../entities/OA_BUDGET.md)（修改）、[OA_EXPENSE](../entities/OA_EXPENSE.md)（查询修改）
<!-- tmh:facts:end -->

## 业务目的
财务对已提交的报销单做通过/驳回决定；驳回时把提交时冻结的部门预算释放回去，并留下审批痕迹（src/main/java/com/acme/oa/service/ExpenseService.java:55-68）。

## 触发与角色
财务人员调用 `POST /expense/audit`，参数 id、auditor、pass、可选 comment（src/main/java/com/acme/oa/controller/ExpenseController.java:32-35）。代码里没有校验调用者是否真有财务角色，auditor 由请求参数传入【推断】。

## 主要步骤
1. 按 id 查报销单，不存在则报“报销单不存在”（src/main/java/com/acme/oa/service/ExpenseService.java:57-60）。
2. pass=true：置 AUDITED，记录审核人和审核时间（src/main/resources/mapper/ExpenseMapper.xml:17）。
3. pass=false：置 REJECTED，记录审核人，并检查更新行数；为 0（单据不是 SUBMITTED）则抛“不能重复驳回”，事务回滚（src/main/resources/mapper/ExpenseMapper.xml:20；src/main/java/com/acme/oa/service/ExpenseService.java:64-67）。自本次修复提交起。
4. 驳回成功（更新 1 行）后，才按单据部门和金额减少当月预算的冻结额（src/main/java/com/acme/oa/service/ExpenseService.java:68；src/main/resources/mapper/BudgetMapper.xml:10）。
5. 写审批日志，动作为 EXPENSE_PASS 或 EXPENSE_REJECT（src/main/java/com/acme/oa/service/ExpenseService.java:70；src/main/resources/mapper/ApprovalLogMapper.xml:4）。
整个方法在同一事务内（src/main/java/com/acme/oa/service/ExpenseService.java:55）。

## 业务规则
- 只有 SUBMITTED 状态的单据才会被更新（SQL 的 WHERE 条件，src/main/resources/mapper/ExpenseMapper.xml:17、20）。
- 释放预算按“当前系统月份”匹配 OA_BUDGET.MONTH（TO_CHAR(SYSDATE,'yyyymm')，src/main/resources/mapper/BudgetMapper.xml:10），不是单据提交月。
- 通过时不动预算：冻结额保持不变，是否在别处转为实际支出代码里看不到【待确认】。

## 状态变化
SUBMITTED → AUDITED（通过）；SUBMITTED → REJECTED（驳回）。驳回时驳回意见只进审批日志，不进单据。

## 异常与边界
- 单据不存在抛 IllegalArgumentException，事务回滚。
- 重复驳回已修复（自本次修复提交起）：驳回时 UPDATE 影响 0 行就抛 IllegalStateException，预算不再重复释放，也不写日志（src/main/java/com/acme/oa/service/ExpenseService.java:64-68）。
- 并发两个财务同时驳回同一单：状态更新带 `STATUS='SUBMITTED'` 条件，只有一个能更新 1 行，另一个抛异常回滚，预算只释放一次【推断】。
- 通过分支仍不检查影响行数（src/main/java/com/acme/oa/service/ExpenseService.java:61-62）：对非 SUBMITTED 单据（含已驳回的）调用通过，单据不变，但仍会写一条 EXPENSE_PASS 日志，产生与实际状态不符的审批痕迹【推断】。
- 释放预算跨月（提交在上月、驳回在本月）会扣错月份，或本月无预算行时更新 0 行而无报错【推断】。
- 通过分支 SQL 写审核时间 AUDITED_AT，驳回分支没有（src/main/resources/mapper/ExpenseMapper.xml:17、20）。
- 日志插入的列名是 LEAVE_ID，这里存的却是报销单 id（src/main/resources/mapper/ApprovalLogMapper.xml:4），与请假单日志共用一表，id 可能混淆。

## 待确认问题
- 重复驳回已拦截；重复“通过”是否也应报错而不是静默写日志？
- 通过后冻结额何时转为实际支出？
- 驳回释放预算是否应按提交月而非当前月？
- 审批日志表用 LEAVE_ID 存报销单 id 是否有意设计，如何区分单据类型？

