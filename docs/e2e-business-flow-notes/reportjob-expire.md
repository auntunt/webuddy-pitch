# 每天凌晨作废超期单据

状态：待确认

## 业务目的
长期无人审批的请假单自动作废，避免待办堆积。

## 触发与角色
- 触发：每天 01:30 定时（cron "0 30 1 * * ?"）
- 操作人 / 角色：系统，无人工参与。

## 主要步骤
1. 将创建时间早于 30 天前、仍为 SUBMITTED 的单据改为 EXPIRED。

## 业务规则
- 超过 30 天未审批即作废（LeaveService.java:52 注释；LeaveMapper.xml:28 的 CREATED < SYSDATE - 30）。

## 状态变化
- OA_LEAVE.STATUS：SUBMITTED → EXPIRED

## 异常与边界
- 作废不写 OA_APPROVAL_LOG，也不通知申请人，审计上看不到谁/何时作废。【推断】
- expireStale 没有 @Transactional；单条 UPDATE，影响小。
- 多实例部署时每个实例都会触发，无分布式锁；由于 UPDATE 幂等，结果一致。【推断】
- “30 天”以数据库当前时间为准，是创建日起算，不是请假开始日。

## 证据
- 入口：`ReportJob.expire`（ReportJob.java:27）
- 逻辑：`LeaveService.expireStale`（LeaveService.java:53）
- SQL：LeaveMapper.xml:28

## 待确认问题
- 【待确认】作废是否需要留审批日志或通知申请人？
- 【待确认】超期应按创建日还是请假开始日计算？
