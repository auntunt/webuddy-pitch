---
id: flow:reportjob-export
title: 每晚导出请假汇总
summary: 每晚 2 点定时导出请假汇总到共享盘，但实际仅写入 "ok"，且依赖 Windows。
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 每晚导出请假汇总

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[请假管理](../domains/leave.md)　入口类型：定时任务　触发：`@Scheduled cron = "0 0 2 * * ?"`

**调用链与数据（工具抽取）**

```text
@Scheduled cron = "0 0 2 * * ?"  「每晚导出请假汇总」  [定时任务]
入口：ReportJob.export  (src/main/java/com/acme/oa/job/ReportJob.java:18)
调用链：
  - [入口] ReportJob.export (src/main/java/com/acme/oa/job/ReportJob.java:17)
外部副作用：
  - 写文件：new FileWriter  (src/main/java/com/acme/oa/job/ReportJob.java:19)
  - 启动外部进程：Runtime.getRuntime().exec  (src/main/java/com/acme/oa/job/ReportJob.java:22)
```
<!-- tmh:facts:end -->

## 业务目的
每晚导出请假汇总到共享文件服务器，供业务查看（名称「每晚导出请假汇总」）。【推断】

## 触发与角色
定时任务，每天 02:00 触发（src/main/java/com/acme/oa/job/ReportJob.java:17）。无人工角色。

## 主要步骤
1. 在 C:\reports\leave.csv 写文件（src/main/java/com/acme/oa/job/ReportJob.java:19-21）。
2. 调用 Windows 命令把文件复制到 \\fileserver\share（src/main/java/com/acme/oa/job/ReportJob.java:22）。

## 业务规则
- 注释/名称说“导出请假汇总”，但代码只写入固定字符串 "ok"，没有查询任何请假数据（src/main/java/com/acme/oa/job/ReportJob.java:20）。功能实际未实现。
- 路径、共享地址均硬编码（src/main/java/com/acme/oa/job/ReportJob.java:19、22）。

## 状态变化
无。不读写数据库表。

## 异常与边界
- 强依赖 Windows（cmd /c、C:\ 盘符、UNC 路径），在 Linux/容器下会失败（src/main/java/com/acme/oa/job/ReportJob.java:22）。
- Runtime.exec 未等待进程结束、不检查返回码，复制失败无感知。
- 多实例部署时每个实例都会执行，没有分布式锁【推断】。
- 每日覆盖同一文件名，无历史留存。

## 待确认问题
- 汇总应包含哪些字段、哪个时间范围？谁消费 \\fileserver\share 上的文件？
- 当前只写 "ok" 是否为占位代码？

