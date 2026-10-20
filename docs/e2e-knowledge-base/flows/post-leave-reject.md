---
id: flow:post-leave-reject
title: 驳回
summary: 审批人驳回待审批请假单，记录审批人并写驳回日志。
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 驳回

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[请假管理](../domains/leave.md)　入口类型：接口　触发：`POST /leave/reject`

**调用链与数据（工具抽取）**

```text
POST /leave/reject  「驳回」  [接口]
入口：LeaveController.reject  (src/main/java/com/acme/oa/controller/LeaveController.java:37)
调用链：
  - [入口] LeaveController.reject (src/main/java/com/acme/oa/controller/LeaveController.java:36)
    - [逻辑] LeaveService.reject (src/main/java/com/acme/oa/service/LeaveService.java:46)
      - [数据] LeaveMapper.reject (src/main/resources/mapper/LeaveMapper.xml:25)
        - 修改 OA_LEAVE
      - [数据] ApprovalLogMapper.insert (src/main/resources/mapper/ApprovalLogMapper.xml:4)
        - 新增 OA_APPROVAL_LOG
状态变化：
  - OA_LEAVE.STATUS: SUBMITTED → REJECTED  (src/main/resources/mapper/LeaveMapper.xml:25)
事务：LeaveService.reject
```
**涉及的业务对象**：[OA_APPROVAL_LOG](../entities/OA_APPROVAL_LOG.md)（新增）、[OA_LEAVE](../entities/OA_LEAVE.md)（修改）
<!-- tmh:facts:end -->

## 业务目的
审批人驳回待审批的请假单，并留下驳回意见。

## 触发与角色
审批人调用 `POST /leave/reject`，参数 id、approver、comment（src/main/java/com/acme/oa/controller/LeaveController.java:36-39）。代码未校验 approver 是否有权审批该单【推断】。

## 主要步骤
1. 将请假单置为 REJECTED 并记录审批人（src/main/resources/mapper/LeaveMapper.xml:25）。
2. 写审批日志，动作 REJECT，含意见（src/main/java/com/acme/oa/service/LeaveService.java:49）。
同一事务（src/main/java/com/acme/oa/service/LeaveService.java:46）。

## 业务规则
- 仅 SUBMITTED 状态才会被更新（src/main/resources/mapper/LeaveMapper.xml:25 的 WHERE）。
- comment 为必填参数（src/main/java/com/acme/oa/controller/LeaveController.java:37）。

## 状态变化
SUBMITTED → REJECTED。

## 异常与边界
- Service 不检查单据是否存在、更新影响行数：id 不存在或状态不是 SUBMITTED 时更新 0 行，仍写入 REJECT 日志，造成日志与单据状态不符（src/main/java/com/acme/oa/service/LeaveService.java:48-49）。
- 驳回不涉及额度/余额回退，若请假有额度占用，代码未体现【推断】。

## 待确认问题
- 对非待审批单据驳回是否应报错而非静默写日志？
- 请假审批是否有额度或假期余额需要在驳回时回退？

