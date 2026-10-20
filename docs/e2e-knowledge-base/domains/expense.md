---
id: dom:expense
title: 费用报销与部门预算
summary: 员工提交报销、财务审核、出纳付款，并按部门月度预算冻结/释放/消耗额度
status: 待确认
updated: 2026-10-07 17:17
commit: 0959bbace3
---
# 费用报销与部门预算

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务流 4 条，业务对象 2 个。域的名称和划分可在 `.tmh/knowledge/domains.json` 中修改。

**业务流**

| 业务流 | 触发 | 一句话 |
|---|---|---|
| [财务审核](../flows/post-expense-audit.md) | `POST /expense/audit` | 财务对已提交报销单审核通过或驳回；驳回时释放部门预算冻结额，并记录审批日志。 |
| [提交报销单](../flows/post-expense-submit.md) | `POST /expense/submit` | 员工提交报销单，校验用户、5万限额与部门月预算，通过后建单并冻结预算 |
| [出纳付款](../flows/post-expense-pay.md) | `POST /expense/pay` | 出纳对审核通过的报销单付款：调财务系统、置已付并把部门预算从冻结转已用 |
| 我的报销单 | `GET /expense/mine` | （未分析） |

**业务对象**

| 表 | 一句话 |
|---|---|
| [OA_BUDGET](../entities/OA_BUDGET.md) | 按部门和月份记录预算总额、冻结额与已用额，支撑报销预算控制 |
| [OA_EXPENSE](../entities/OA_EXPENSE.md) | 员工报销申请单，记录金额、类别、审核与付款信息及状态流转 |

**与其他域的数据关系**
- [请假管理](leave.md)：本域 提交报销单 用了 OA_APPROVAL_LOG（C）；本域 财务审核 用了 OA_APPROVAL_LOG（C）
- [用户管理](user.md)：本域 提交报销单 用了 OA_USER（R）
<!-- tmh:facts:end -->

## 职责边界
管理报销单从提交、财务审核到出纳付款的全过程，并联动部门月度预算（OA_BUDGET）。不含用户维护和请假。

## 核心流程
1. [提交报销单](../flows/post-expense-submit.md)：校验用户、5 万上限、部门当月预算，建单并冻结预算（`src/main/java/com/acme/oa/service/ExpenseService.java:34-52`）。
2. [财务审核](../flows/post-expense-audit.md)：通过或驳回，驳回释放冻结额（`src/main/java/com/acme/oa/service/ExpenseService.java:55-68`）。
3. [出纳付款](../flows/post-expense-pay.md)：调外部财务系统，置已付，冻结转已用（`src/main/java/com/acme/oa/service/ExpenseService.java:71-80`）。
状态：SUBMITTED → AUDITED/REJECTED；AUDITED → PAID。

## 核心业务对象
- [OA_EXPENSE](../entities/OA_EXPENSE.md)：报销单。
- [OA_BUDGET](../entities/OA_BUDGET.md)：部门月度预算，剩余=TOTAL-FROZEN-USED。

## 与其他域的关系
- user：提交时读取 OA_USER 校验申请人状态。
- leave：共用 OA_APPROVAL_LOG 写审批日志，报销单号存在 LEAVE_ID 列里（`src/main/resources/mapper/ApprovalLogMapper.xml:4`）。

## 风险与坑
- 预算按系统当前月份匹配，跨月提交/付款会错位（`src/main/resources/mapper/BudgetMapper.xml:10,13`）。
- 重复驳回已拦截（驳回更新 0 行抛异常，不再重复释放预算，`src/main/java/com/acme/oa/service/ExpenseService.java:64-68`）；重复“通过”仍不校验，会多写审批日志【推断】。
- 外部支付在本地事务内且先于落库，失败无法回滚（`src/main/java/com/acme/oa/service/ExpenseService.java:77`）。
- 提交时先读余额后冻结，并发可能超额【推断】。
- 【待确认】跨月应扣哪个月预算；5 万上限是否分类别；财务 /api/pay 是否幂等（见 open-questions.md）。

