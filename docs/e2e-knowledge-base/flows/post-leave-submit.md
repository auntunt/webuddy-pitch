---
id: flow:post-leave-submit
title: 提交请假申请
summary: 员工提交请假申请，校验天数1到30后建单并记审批日志
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 提交请假申请

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[请假管理](../domains/leave.md)　入口类型：接口　触发：`POST /leave/submit`

**调用链与数据（工具抽取）**

```text
POST /leave/submit  「提交请假申请」  [接口]
入口：LeaveController.submit  (src/main/java/com/acme/oa/controller/LeaveController.java:26)
调用链：
  - [入口] LeaveController.submit (src/main/java/com/acme/oa/controller/LeaveController.java:25)
    - [逻辑] LeaveService.submit (src/main/java/com/acme/oa/service/LeaveService.java:25)
      - [数据] LeaveMapper.nextId (src/main/resources/mapper/LeaveMapper.xml:15)
      - [数据] LeaveMapper.insert (src/main/resources/mapper/LeaveMapper.xml:18)
        - 新增 OA_LEAVE
      - [数据] ApprovalLogMapper.insert (src/main/resources/mapper/ApprovalLogMapper.xml:4)
        - 新增 OA_APPROVAL_LOG
状态变化：
  - OA_LEAVE.STATUS: (新建) → SUBMITTED  (src/main/resources/mapper/LeaveMapper.xml:18)
业务规则（代码中的校验）：
  - 若 days <= 0 || days > 30：请假天数必须在 1 到 30 天之间  (src/main/java/com/acme/oa/service/LeaveService.java:28)
事务：LeaveService.submit
```
**涉及的业务对象**：[OA_APPROVAL_LOG](../entities/OA_APPROVAL_LOG.md)（新增）、[OA_LEAVE](../entities/OA_LEAVE.md)（新增）
<!-- tmh:facts:end -->

## 业务目的
员工发起请假申请，系统登记请假单并留下提交日志，供后续审批。

## 触发与角色
申请人调用 `POST /leave/submit`，参数 applicant、deptId、days、reason（src/main/java/com/acme/oa/controller/LeaveController.java:25-28）。

## 主要步骤
1. 校验天数（src/main/java/com/acme/oa/service/LeaveService.java:27）。
2. 取序列号并插入请假单，状态 SUBMITTED（src/main/java/com/acme/oa/service/LeaveService.java:30；src/main/resources/mapper/LeaveMapper.xml:18）。
3. 写审批日志，动作 SUBMIT，COMMENTS 存请假原因（src/main/java/com/acme/oa/service/LeaveService.java:32）。
4. 返回请假单 ID。

## 业务规则
- 天数须在 1～30 的整数（src/main/java/com/acme/oa/service/LeaveService.java:27）。
- 未校验申请人是否存在/在职、部门是否匹配、假期余额；表中无起止日期【推断】。

## 状态变化
OA_LEAVE.STATUS：新建 → SUBMITTED（src/main/resources/mapper/LeaveMapper.xml:18）。

## 异常与边界
- 有 @Transactional，异常整体回滚（src/main/java/com/acme/oa/service/LeaveService.java:25）。
- 无幂等控制，重复提交产生多张单【推断】。
- 天数为 int，不支持半天。
- SQL 使用序列、SYSDATE、DUAL（Oracle 方言，src/main/resources/mapper/LeaveMapper.xml:15）。

## 待确认问题
- 【待确认】上限 30 天是否含特殊假种（产假、年假）？是否需要假期余额校验？
- 【待确认】是否需要记录请假起止日期？

