---
id: flow:reportjob-expire
title: 作废超期请假单（定时任务）
summary: 每天01:30将提交超30天仍未处理的请假单置为EXPIRED
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 作废超期请假单（定时任务）

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[请假管理](../domains/leave.md)　入口类型：定时任务　触发：`@Scheduled cron = "0 30 1 * * ?"`

**调用链与数据（工具抽取）**

```text
@Scheduled cron = "0 30 1 * * ?"  「每天凌晨作废超期单据」  [定时任务]
入口：ReportJob.expire  (src/main/java/com/acme/oa/job/ReportJob.java:27)
调用链：
  - [入口] ReportJob.expire (src/main/java/com/acme/oa/job/ReportJob.java:26)
    - [逻辑] LeaveService.expireStale (src/main/java/com/acme/oa/service/LeaveService.java:53)
      - [数据] LeaveMapper.expireStale (src/main/resources/mapper/LeaveMapper.xml:28)
        - 修改 OA_LEAVE
状态变化：
  - OA_LEAVE.STATUS: SUBMITTED → EXPIRED  (src/main/resources/mapper/LeaveMapper.xml:28)
```
**涉及的业务对象**：[OA_LEAVE](../entities/OA_LEAVE.md)（修改）
<!-- tmh:facts:end -->

## 业务目的
清理长期无人审批的请假单，避免待办堆积。

## 触发与角色
系统定时任务，cron `0 30 1 * * ?`，每天 01:30 触发，无人工角色（src/main/java/com/acme/oa/job/ReportJob.java:26-28）。类名为 ReportJob 但做的是请假作废【推断】。

## 主要步骤
1. 定时器调用 LeaveService.expireStale（src/main/java/com/acme/oa/job/ReportJob.java:28）。
2. 执行批量 UPDATE（src/main/java/com/acme/oa/service/LeaveService.java:53-54；src/main/resources/mapper/LeaveMapper.xml:28）。

## 业务规则
- 仅处理 STATUS=SUBMITTED 且 CREATED 早于当前时间 30 天的单据（src/main/resources/mapper/LeaveMapper.xml:28）。
- 这里的“30 天”与请假天数上限 30 无关，为单据停留时长；两者数值巧合相同【推断】。

## 状态变化
OA_LEAVE.STATUS：SUBMITTED → EXPIRED（src/main/resources/mapper/LeaveMapper.xml:28）。

## 异常与边界
- 不写审批日志，不通知申请人（src/main/java/com/acme/oa/service/LeaveService.java:53-55）。
- 返回的影响行数被丢弃，未记录日志（src/main/java/com/acme/oa/job/ReportJob.java:28）。
- 多实例部署时每个实例都会触发，UPDATE 幂等所以无害，但无分布式锁【推断】。
- 使用 SYSDATE（Oracle 方言）。

## 待确认问题
- 【待确认】超期阈值 30 天是否是业务要求？作废后是否允许申请人重新提交或通知？

