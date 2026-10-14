---
id: dom:leave
title: 请假管理
summary: 员工提交请假、审批人通过或驳回，超期未处理的单据由定时任务作废
status: 待确认
updated: 2026-10-07 17:17
commit: 0959bbace3
---
# 请假管理

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务流 6 条，业务对象 3 个。域的名称和划分可在 `.tmh/knowledge/domains.json` 中修改。

**业务流**

| 业务流 | 触发 | 一句话 |
|---|---|---|
| [审批通过：记录审批人与审批时间](../flows/post-leave-approve.md) | `POST /leave/approve` | 审批人将待审批请假单置为已批准，记录审批人/时间并写审批日志 |
| [提交请假申请](../flows/post-leave-submit.md) | `POST /leave/submit` | 员工提交请假申请，校验天数1到30后建单并记审批日志 |
| [驳回](../flows/post-leave-reject.md) | `POST /leave/reject` | 审批人驳回待审批请假单，记录审批人并写驳回日志。 |
| [作废超期请假单（定时任务）](../flows/reportjob-expire.md) | `@Scheduled cron = "0 30 1 * * ?"` | 每天01:30将提交超30天仍未处理的请假单置为EXPIRED |
| [每晚导出请假汇总](../flows/reportjob-export.md) | `@Scheduled cron = "0 0 2 * * ?"` | 每晚 2 点定时导出请假汇总到共享盘，但实际仅写入 "ok"，且依赖 Windows。 |
| 查询请假单列表 | `GET /leave/list` | （未分析） |

**业务对象**

| 表 | 一句话 |
|---|---|
| [OA_APPROVAL_LOG](../entities/OA_APPROVAL_LOG.md) | 请假与报销共用的审批/操作日志表，只追加；字段名与 INSERT 语句不一致 |
| [OA_DEPT](../entities/OA_DEPT.md) | 公司部门树表，目前仅用于请假列表显示部门名。 |
| [OA_LEAVE](../entities/OA_LEAVE.md) | 请假单主表：提交后待审批，可被批准、驳回，超30天未处理自动作废 |

**与其他域的数据关系**
- [费用报销与部门预算](expense.md)：提交报销单 用了本域的 OA_APPROVAL_LOG（C）；财务审核 用了本域的 OA_APPROVAL_LOG（C）
<!-- tmh:facts:end -->

## 职责边界
管理请假单的提交、审批（通过/驳回）、超期作废，以及每晚汇总导出任务。审批日志表 OA_APPROVAL_LOG 与部门表 OA_DEPT 也归在本域。

## 核心流程
1. [提交请假申请](../flows/post-leave-submit.md)：天数须 1~30（`src/main/java/com/acme/oa/service/LeaveService.java:27`）。
2. [审批通过](../flows/post-leave-approve.md)、[驳回](../flows/post-leave-reject.md)：仅 SUBMITTED 可处理（`src/main/resources/mapper/LeaveMapper.xml:22,25`）。
3. [作废超期请假单](../flows/reportjob-expire.md)：每天 01:30，提交超 30 天未处理置 EXPIRED。
4. [每晚导出请假汇总](../flows/reportjob-export.md)：每天 02:00，实际只写 "ok"。
另有只读入口 GET /leave/list。状态：SUBMITTED → APPROVED/REJECTED/EXPIRED。

## 核心业务对象
[OA_LEAVE](../entities/OA_LEAVE.md)、[OA_APPROVAL_LOG](../entities/OA_APPROVAL_LOG.md)、[OA_DEPT](../entities/OA_DEPT.md)。

## 与其他域的关系
报销域共用 OA_APPROVAL_LOG 写日志。定时任务类 ReportJob 被自动划入本域，但名字像报表，两个任务的归属为【推断】。

## 风险与坑
- 审批日志建表列 BILL_ID 与插入列 LEAVE_ID 不一致，按脚本建库会导致所有写日志流程报错（`sql/schema.sql:50`，`src/main/resources/mapper/ApprovalLogMapper.xml:4`）。
- START_DATE 从不写入（`src/main/resources/mapper/LeaveMapper.xml:18`）。
- 驳回不检查影响行数，非待审批单也会写驳回日志（`src/main/java/com/acme/oa/service/LeaveService.java:48-49`）。
- 导出任务依赖 Windows cmd 与 UNC 路径（`src/main/java/com/acme/oa/job/ReportJob.java:19-22`）；deptTree 使用 Oracle CONNECT BY 且无调用方。
- 【待确认】30 天上限是否分假种；超期作废是否为业务要求；审批人是否需权限校验。

