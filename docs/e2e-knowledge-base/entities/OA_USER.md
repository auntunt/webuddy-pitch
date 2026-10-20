---
id: tbl:OA_USER
title: 用户
summary: 系统用户（员工）表，工号为主键，状态 ACTIVE/DISABLED。
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 用户

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 归属业务域：[用户管理](../domains/user.md)　类型：TABLE

**表结构**（`sql/schema.sql:8`）

```sql
CREATE TABLE OA_USER (
  ID VARCHAR2(32) PRIMARY KEY,   -- 工号
  NAME VARCHAR2(50) NOT NULL,
  DEPT_ID NUMBER(19),
  STATUS VARCHAR2(10)            -- ACTIVE / DISABLED
);
```

**哪些业务流在用**

| 业务流 | 操作 | 业务域 |
|---|---|---|
| [新增用户](../flows/post-user-add.md) | 新增查询 | user |
| [停用用户（离职）](../flows/post-user-disable.md) | 修改 | user |
| [提交报销单](../flows/post-expense-submit.md) | 查询 | expense（跨域） |

**状态流转（STATUS）**：(新建) → ACTIVE（新增用户）；* → DISABLED（停用用户（离职））

**直接访问它的代码**：`UserMapper.disable`(U)、`UserMapper.insert`(C)、`UserMapper.selectById`(R)
<!-- tmh:facts:end -->

## 业务含义
系统用户（员工），主键为工号（sql/schema.sql:8）。

## 关键字段
- ID：工号，字符串主键。
- NAME：姓名，必填。
- DEPT_ID：所属部门，对应 OA_DEPT，建表未设外键，可为空。
- STATUS：ACTIVE / DISABLED（sql/schema.sql 注释）。

## 生命周期
新增即 ACTIVE（src/main/resources/mapper/UserMapper.xml:7）；停用为 DISABLED（src/main/resources/mapper/UserMapper.xml:10）。没有重新启用、修改资料、删除的代码【推断】。

## 谁在读写
- 新增用户：先查后插（src/main/java/com/acme/oa/service/UserService.java:16-19）。
- 停用用户：无条件更新（src/main/java/com/acme/oa/service/UserService.java:24）。
- 提交报销单：校验用户存在且非 DISABLED（src/main/java/com/acme/oa/service/ExpenseService.java:37）。

## 注意事项
- STATUS 只在报销提交时被检查；请假、报销审核、付款是否检查用户状态，在已有页面中未见，停用用户仍可能被用作审批人/审核人【推断】【待确认】。
- 报销提交没有校验单据 deptId 是否等于用户 DEPT_ID【推断】，用户 DEPT_ID 实际用途有限。
- 停用不处理在途单据。

