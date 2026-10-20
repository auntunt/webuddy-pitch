---
id: flow:post-leave-approve
title: 审批通过：记录审批人与审批时间
summary: 审批人将待审批请假单置为已批准，记录审批人/时间并写审批日志
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 审批通过：记录审批人与审批时间

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[请假管理](../domains/leave.md)　入口类型：接口　触发：`POST /leave/approve`

**调用链与数据（工具抽取）**

```text
POST /leave/approve  「审批通过：记录审批人与审批时间」  [接口]
入口：LeaveController.approve  (src/main/java/com/acme/oa/controller/LeaveController.java:31)
调用链：
  - [入口] LeaveController.approve (src/main/java/com/acme/oa/controller/LeaveController.java:30)
    - [逻辑] LeaveService.approve (src/main/java/com/acme/oa/service/LeaveService.java:37)
      - [数据] LeaveMapper.approve (src/main/resources/mapper/LeaveMapper.xml:22)
        - 修改 OA_LEAVE
      - [数据] ApprovalLogMapper.insert (src/main/resources/mapper/ApprovalLogMapper.xml:4)
        - 新增 OA_APPROVAL_LOG
状态变化：
  - OA_LEAVE.STATUS: SUBMITTED → APPROVED  (src/main/resources/mapper/LeaveMapper.xml:22)
业务规则（代码中的校验）：
  - 若 n == 0：单据不是待审批状态  (src/main/java/com/acme/oa/service/LeaveService.java:41)
事务：LeaveService.approve
```
**涉及的业务对象**：[OA_APPROVAL_LOG](../entities/OA_APPROVAL_LOG.md)（新增）、[OA_LEAVE](../entities/OA_LEAVE.md)（修改）
<!-- tmh:facts:end -->

## 业务目的
审批人批准员工提交的请假单。

## 触发与角色
审批人调用 `POST /leave/approve`，参数 id、approver（src/main/java/com/acme/oa/controller/LeaveController.java:30-33）。代码未校验 approver 是否有审批权或是否为申请人本人【推断】。

## 主要步骤
1. 条件更新请假单为 APPROVED，写 APPROVER、APPROVED_AT（src/main/resources/mapper/LeaveMapper.xml:22）。
2. 影响行数为 0 则报错（src/main/java/com/acme/oa/service/LeaveService.java:40-41）。
3. 写审批日志，ACTION=APPROVE，意见为空（src/main/java/com/acme/oa/service/LeaveService.java:43，src/main/resources/mapper/ApprovalLogMapper.xml:4）。

## 业务规则
- 仅 SUBMITTED 状态可批准，靠 SQL 的 `AND STATUS='SUBMITTED'` 实现（src/main/resources/mapper/LeaveMapper.xml:22）。
- 两步在同一事务（src/main/java/com/acme/oa/service/LeaveService.java:37）。

## 状态变化
OA_LEAVE.STATUS：SUBMITTED → APPROVED（src/main/resources/mapper/LeaveMapper.xml:22）。

## 异常与边界
- 非待审批（含不存在、已批准、已驳回）统一抛 IllegalStateException“单据不是待审批状态”，无法区分原因（src/main/java/com/acme/oa/service/LeaveService.java:41）。
- 条件更新天然防止重复/并发审批。
- 审批意见恒为 null，不支持批准意见（src/main/java/com/acme/oa/service/LeaveService.java:43）。
- SYSDATE 为 Oracle 写法，信创迁移需改写。

## 待确认问题
- 【待确认】审批人是否需要权限/上下级校验，能否自批？

