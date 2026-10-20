---
id: flow:post-user-disable
title: 停用用户（离职）
summary: 离职时将用户状态置为 DISABLED，不检查存在性和在途单据。
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 停用用户（离职）

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[用户管理](../domains/user.md)　入口类型：接口　触发：`POST /user/disable`

**调用链与数据（工具抽取）**

```text
POST /user/disable  「停用用户（离职）」  [接口]
入口：UserController.disable  (src/main/java/com/acme/oa/controller/UserController.java:24)
调用链：
  - [入口] UserController.disable (src/main/java/com/acme/oa/controller/UserController.java:23)
    - [逻辑] UserService.disable (src/main/java/com/acme/oa/service/UserService.java:23)
      - [数据] UserMapper.disable (src/main/resources/mapper/UserMapper.xml:10)
        - 修改 OA_USER
状态变化：
  - OA_USER.STATUS: * → DISABLED  (src/main/resources/mapper/UserMapper.xml:10)
```
**涉及的业务对象**：[OA_USER](../entities/OA_USER.md)（修改）
<!-- tmh:facts:end -->

## 业务目的
员工离职时停用其账号（接口名「停用用户（离职）」）。

## 触发与角色
管理员/HR（推断）调用 `POST /user/disable`，参数 id（src/main/java/com/acme/oa/controller/UserController.java:23-26）。无权限校验【推断】。

## 主要步骤
1. 将指定用户状态置为 DISABLED（src/main/java/com/acme/oa/service/UserService.java:24；src/main/resources/mapper/UserMapper.xml:10）。

## 业务规则
- 无条件更新：不检查用户是否存在、当前状态（src/main/resources/mapper/UserMapper.xml:10 无状态条件）。

## 状态变化
任意状态 → DISABLED。没有对应的“重新启用”流程【推断】。

## 异常与边界
- 用户不存在时更新 0 行，无报错（src/main/java/com/acme/oa/service/UserService.java:23-25）。
- 不处理该用户名下未完成的请假/报销单、待办或审批权限，停用后在途单据如何处理代码未体现【推断】【待确认】。
- 无事务、无操作日志。

## 待确认问题
- 离职停用后，在途的请假/报销单如何处理？
- 是否允许重新启用？

