---
id: flow:post-user-add
title: 新增用户
summary: 按工号新增用户，工号重复则拒绝，新用户默认启用。
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 新增用户

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务域：[用户管理](../domains/user.md)　入口类型：接口　触发：`POST /user/add`

**调用链与数据（工具抽取）**

```text
POST /user/add  「新增用户」  [接口]
入口：UserController.add  (src/main/java/com/acme/oa/controller/UserController.java:18)
调用链：
  - [入口] UserController.add (src/main/java/com/acme/oa/controller/UserController.java:17)
    - [逻辑] UserService.add (src/main/java/com/acme/oa/service/UserService.java:15)
      - [数据] UserMapper.selectById (src/main/resources/mapper/UserMapper.xml:4)
        - 查询 OA_USER
      - [数据] UserMapper.insert (src/main/resources/mapper/UserMapper.xml:7)
        - 新增 OA_USER
状态变化：
  - OA_USER.STATUS: (新建) → ACTIVE  (src/main/resources/mapper/UserMapper.xml:7)
业务规则（代码中的校验）：
  - 若 userMapper.selectById(id) != null：工号已存在  (src/main/java/com/acme/oa/service/UserService.java:17)
```
**涉及的业务对象**：[OA_USER](../entities/OA_USER.md)（新增查询）
<!-- tmh:facts:end -->

## 业务目的
在系统中新增一个用户（员工），工号即主键。

## 触发与角色
管理员（推断）调用 `POST /user/add`，参数 id（工号）、name、deptId（src/main/java/com/acme/oa/controller/UserController.java:17-20）。无权限校验【推断】。

## 主要步骤
1. 按工号查是否已存在（src/main/java/com/acme/oa/service/UserService.java:16；src/main/resources/mapper/UserMapper.xml:4）。
2. 不存在则插入，状态固定 ACTIVE（src/main/resources/mapper/UserMapper.xml:7）。

## 业务规则
- 工号唯一，重复抛“工号已存在”（src/main/java/com/acme/oa/service/UserService.java:17）。
- 新用户状态硬编码为 ACTIVE（src/main/resources/mapper/UserMapper.xml:7）。
- 不校验 deptId 是否存在、name 是否为空。

## 状态变化
（新建）→ ACTIVE。

## 异常与边界
- UserService.add 没有 @Transactional（src/main/java/com/acme/oa/service/UserService.java:15），先查后插在并发下可能同时通过检查，靠数据库主键约束兜底【推断】。
- 不写审批/操作日志。

## 待确认问题
- 谁有权新增用户？是否需要审计日志？
- 是否需要校验部门存在？

