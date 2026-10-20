---
id: dom:user
title: 用户管理
summary: 按工号新增员工用户、离职时停用，为其他域提供申请人身份
status: 待确认
updated: 2026-10-07 17:17
commit: 0959bbace3
---
# 用户管理

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 业务流 2 条，业务对象 1 个。域的名称和划分可在 `.tmh/knowledge/domains.json` 中修改。

**业务流**

| 业务流 | 触发 | 一句话 |
|---|---|---|
| [新增用户](../flows/post-user-add.md) | `POST /user/add` | 按工号新增用户，工号重复则拒绝，新用户默认启用。 |
| [停用用户（离职）](../flows/post-user-disable.md) | `POST /user/disable` | 离职时将用户状态置为 DISABLED，不检查存在性和在途单据。 |

**业务对象**

| 表 | 一句话 |
|---|---|
| [OA_USER](../entities/OA_USER.md) | 系统用户（员工）表，工号为主键，状态 ACTIVE/DISABLED。 |

**与其他域的数据关系**
- [费用报销与部门预算](expense.md)：提交报销单 用了本域的 OA_USER（R）
<!-- tmh:facts:end -->

## 职责边界
维护系统用户（员工）的新增与停用。不含登录、权限、改资料。

## 核心流程
- [新增用户](../flows/post-user-add.md)：工号唯一，状态默认 ACTIVE（`src/main/java/com/acme/oa/service/UserService.java:17`）。
- [停用用户](../flows/post-user-disable.md)：无条件置 DISABLED，不查存在性和在途单据（`src/main/resources/mapper/UserMapper.xml:10`）。

## 核心业务对象
[OA_USER](../entities/OA_USER.md)，工号为主键，状态 ACTIVE/DISABLED。

## 与其他域的关系
报销提交时读取 OA_USER 校验状态；请假提交不校验申请人是否存在或在职。

## 风险与坑
- 停用后在途请假/报销单和审批权限无处理。
- PasswordUtil 使用 MD5 且把摘要字节直接转字符串，结果会损坏（`src/main/java/com/acme/oa/util/PasswordUtil.java:7-10`）【读代码所得】，需评估安全性与国密要求。
- 【待确认】停用后在途单据如何处理；新增用户的操作权限与审计。

