---
id: flow:post-expense-pay
title: 出纳付款
summary: 出纳对审核通过的报销单付款：调财务系统、置已付并把部门预算从冻结转已用
status: 待确认
updated: 2026-10-07 17:15
commit: 0959bbace3
---
# 出纳付款

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[费用报销与部门预算](../domains/expense.md)　入口类型：接口　触发：`POST /expense/pay`

**调用链与数据（工具抽取）**

```text
POST /expense/pay  「出纳付款」  [接口]
入口：ExpenseController.pay  (src/main/java/com/acme/oa/controller/ExpenseController.java:39)
调用链：
  - [入口] ExpenseController.pay (src/main/java/com/acme/oa/controller/ExpenseController.java:38)
    - [逻辑] ExpenseService.pay (src/main/java/com/acme/oa/service/ExpenseService.java:74)
      - [数据] ExpenseMapper.selectById (src/main/resources/mapper/ExpenseMapper.xml:7)
        - 查询 OA_EXPENSE
      - [数据] ExpenseMapper.markPaid (src/main/resources/mapper/ExpenseMapper.xml:23)
        - 修改 OA_EXPENSE
      - [数据] BudgetMapper.consume (src/main/resources/mapper/BudgetMapper.xml:13)
        - 修改 OA_BUDGET
状态变化：
  - OA_EXPENSE.STATUS: AUDITED → PAID  (src/main/resources/mapper/ExpenseMapper.xml:23)
业务规则（代码中的校验）：
  - 若 e == null || !"AUDITED".equals(e.get("STATUS"))：只有审核通过的报销单才能付款  (src/main/java/com/acme/oa/service/ExpenseService.java:78)
事务：ExpenseService.pay
外部副作用：
  - 调用外部 HTTP 接口：restTemplate  (src/main/java/com/acme/oa/service/ExpenseService.java:80)
```
**涉及的业务对象**：[OA_BUDGET](../entities/OA_BUDGET.md)（修改）、[OA_EXPENSE](../entities/OA_EXPENSE.md)（查询修改）
<!-- tmh:facts:end -->

## 业务目的
让出纳对已审核通过的报销单完成付款，并把部门当月预算从“冻结”转为“已用”。

## 触发与角色
出纳调用 `POST /expense/pay`，参数 id、cashier（src/main/java/com/acme/oa/controller/ExpenseController.java:38-40）。代码未校验调用者身份，cashier 由请求传入【推断】。

## 主要步骤
1. 按 id 查报销单（src/main/java/com/acme/oa/service/ExpenseService.java:73，src/main/resources/mapper/ExpenseMapper.xml:7）。
2. 校验单据存在且状态为 AUDITED（src/main/java/com/acme/oa/service/ExpenseService.java:74-76）。
3. 同步 POST 调用财务系统 `http://fin.internal/api/pay`，把整单作为请求体（src/main/java/com/acme/oa/service/ExpenseService.java:77）。
4. 标记已付：写 STATUS=PAID、CASHIER、PAID_AT（src/main/resources/mapper/ExpenseMapper.xml:23）。
5. 扣预算：对该部门当月 FROZEN 减、USED 加报销金额（src/main/java/com/acme/oa/service/ExpenseService.java:79，src/main/resources/mapper/BudgetMapper.xml:13）。

## 业务规则
- 只有 AUDITED 的单据可付款（src/main/java/com/acme/oa/service/ExpenseService.java:74-75）。
- markPaid 的 SQL 带 `AND STATUS='AUDITED'`，有乐观并发保护（src/main/resources/mapper/ExpenseMapper.xml:23）。
- 预算按“当前系统月份” TO_CHAR(SYSDATE,'yyyymm') 匹配，而非报销发生月（src/main/resources/mapper/BudgetMapper.xml:13）。
- 预算 SQL 使用 Oracle 的 SYSDATE/TO_CHAR（信创迁移需改写）。

## 状态变化
OA_EXPENSE.STATUS：AUDITED → PAID（src/main/resources/mapper/ExpenseMapper.xml:23）。OA_BUDGET：FROZEN 减少、USED 增加。

## 异常与边界
- 状态不符抛 IllegalStateException（src/main/java/com/acme/oa/service/ExpenseService.java:75）。
- 外部支付调用在 DB 更新之前且在 @Transactional 内（src/main/java/com/acme/oa/service/ExpenseService.java:71,77）：外部已付款但后续 DB 失败时，只回滚本地，外部付款不会撤销，重试可能重复付款【推断】。
- markPaid 返回值未检查（src/main/java/com/acme/oa/service/ExpenseService.java:78）：并发下更新 0 行也会继续扣预算【推断】。
- consume 返回值未检查、未校验 FROZEN 足够，当月无预算记录时静默不扣（src/main/resources/mapper/BudgetMapper.xml:13）【推断】。
- 外部调用无超时/幂等键可见，持有数据库事务期间等待网络【推断】。

## 待确认问题
- 【待确认】财务系统 /api/pay 是否幂等？失败后如何对账？
- 【待确认】跨月付款时，应扣报销所属月还是付款当月的预算？
- 【待确认】付款人 cashier 是否需要鉴权/角色限制？

