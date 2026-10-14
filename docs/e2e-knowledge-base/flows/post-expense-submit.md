---
id: flow:post-expense-submit
title: 提交报销单
summary: 员工提交报销单，校验用户、5万限额与部门月预算，通过后建单并冻结预算
status: 待确认
updated: 2026-10-07 17:15
commit: 0959bbace3
---
# 提交报销单

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[费用报销与部门预算](../domains/expense.md)　入口类型：接口　触发：`POST /expense/submit`

**调用链与数据（工具抽取）**

```text
POST /expense/submit  「提交报销单」  [接口]
入口：ExpenseController.submit  (src/main/java/com/acme/oa/controller/ExpenseController.java:27)
调用链：
  - [入口] ExpenseController.submit (src/main/java/com/acme/oa/controller/ExpenseController.java:26)
    - [逻辑] ExpenseService.submit (src/main/java/com/acme/oa/service/ExpenseService.java:34)
      - [数据] UserMapper.selectById (src/main/resources/mapper/UserMapper.xml:4)
        - 查询 OA_USER
      - [数据] BudgetMapper.remaining (src/main/resources/mapper/BudgetMapper.xml:4)
        - 查询 OA_BUDGET
      - [数据] ExpenseMapper.nextId (src/main/resources/mapper/ExpenseMapper.xml:10)
      - [数据] ExpenseMapper.insert (src/main/resources/mapper/ExpenseMapper.xml:13)
        - 新增 OA_EXPENSE
      - [数据] BudgetMapper.freeze (src/main/resources/mapper/BudgetMapper.xml:7)
        - 修改 OA_BUDGET
      - [数据] ApprovalLogMapper.insert (src/main/resources/mapper/ApprovalLogMapper.xml:4)
        - 新增 OA_APPROVAL_LOG
状态变化：
  - OA_EXPENSE.STATUS: (新建) → SUBMITTED  (src/main/resources/mapper/ExpenseMapper.xml:13)
业务规则（代码中的校验）：
  - 若 user == null || "DISABLED".equals(user.get("STATUS"))：用户不存在或已停用  (src/main/java/com/acme/oa/service/ExpenseService.java:38)
  - 若 amount.compareTo(new BigDecimal("50000")) > 0：单笔报销不能超过 5 万元  (src/main/java/com/acme/oa/service/ExpenseService.java:41)
  - 若 left == null || left.compareTo(amount) < 0：部门预算不足  (src/main/java/com/acme/oa/service/ExpenseService.java:45)
事务：ExpenseService.submit
```
**涉及的业务对象**：[OA_APPROVAL_LOG](../entities/OA_APPROVAL_LOG.md)（新增）、[OA_BUDGET](../entities/OA_BUDGET.md)（查询修改）、[OA_EXPENSE](../entities/OA_EXPENSE.md)（新增）、[OA_USER](../entities/OA_USER.md)（查询）
<!-- tmh:facts:end -->

## 业务目的
员工提交报销单，系统在提交时校验申请人、单笔限额和部门当月预算，并冻结相应预算额度，留下提交日志。

## 触发与角色
员工（或前端代其）调用 `POST /expense/submit`，参数 userId、deptId、amount、category（src/main/java/com/acme/oa/controller/ExpenseController.java:26-28）。接口内没有登录身份与 userId 的一致性校验【推断】。

## 主要步骤
1. 查询申请人，用户不存在或停用则拒绝（src/main/java/com/acme/oa/service/ExpenseService.java:36-39）。
2. 单笔金额超过 5 万元则拒绝（src/main/java/com/acme/oa/service/ExpenseService.java:40-42）。
3. 查询部门当月剩余预算 = TOTAL - FROZEN - USED，不足则拒绝（src/main/java/com/acme/oa/service/ExpenseService.java:43-46；src/main/resources/mapper/BudgetMapper.xml:4）。
4. 取序列号并插入报销单，状态 SUBMITTED（src/main/java/com/acme/oa/service/ExpenseService.java:47-48；src/main/resources/mapper/ExpenseMapper.xml:13）。
5. 冻结部门当月预算 FROZEN += amount（src/main/java/com/acme/oa/service/ExpenseService.java:49；src/main/resources/mapper/BudgetMapper.xml:7）。
6. 写审批日志，动作 EXPENSE_SUBMIT（src/main/java/com/acme/oa/service/ExpenseService.java:50）。返回报销单 ID。

## 业务规则
- 用户须存在且非 DISABLED（src/main/java/com/acme/oa/service/ExpenseService.java:37）。
- 单笔上限 50000（含），硬编码（src/main/java/com/acme/oa/service/ExpenseService.java:40）。
- 预算按“部门+当月(yyyymm)”，剩余须不小于申请额；无预算记录视为不足（src/main/java/com/acme/oa/service/ExpenseService.java:44）。
- 未校验 amount 是否为正数、category 是否合法、deptId 是否为用户所属部门【推断】。

## 状态变化
OA_EXPENSE.STATUS：新建 → SUBMITTED（src/main/resources/mapper/ExpenseMapper.xml:13）。预算 FROZEN 增加；之后的审批、扣减（USED）不在本流程。

## 异常与边界
- 方法有 @Transactional，抛异常则全部回滚（src/main/java/com/acme/oa/service/ExpenseService.java:34）。
- 并发：先读剩余预算再更新，freeze 的 UPDATE 无“剩余>=金额”条件，也不检查影响行数，并发提交可能超额冻结（src/main/java/com/acme/oa/service/ExpenseService.java:43,49；src/main/resources/mapper/BudgetMapper.xml:7）【推断】。
- 无幂等控制，重复提交会生成多张单并重复冻结。
- 审批日志表字段名为 LEAVE_ID，此处存的是报销单 ID，且 COMMENTS 存的是 category（src/main/java/com/acme/oa/service/ExpenseService.java:50；src/main/resources/mapper/ApprovalLogMapper.xml:4）。
- SQL 使用 SYSDATE、TO_CHAR、序列、DUAL，为 Oracle 方言（信创迁移需关注）。
- 预算月份取数据库当前时间，跨月边界提交按提交时刻计。

## 待确认问题
- 【待确认】5 万元上限是否所有类别/人员一致，是否含 5 万整？
- 【待确认】提交时冻结预算，驳回/撤销时是否释放？本流程之外未见，需核实。
- 【待确认】审批日志复用 LEAVE_ID 存报销单 ID 是否为有意设计（与请假共用表）？

