---
id: tbl:OA_DEPT
title: 部门
summary: 公司部门树表，目前仅用于请假列表显示部门名。
status: 待确认
updated: 2026-10-07 17:16
commit: 0959bbace3
---
# 部门

<!-- tmh:facts:start 本段由 tmh kb build 自动生成，请勿手改 -->
> 归属业务域：[请假管理](../domains/leave.md)　类型：TABLE

**表结构**（`sql/schema.sql:2`）

```sql
CREATE TABLE OA_DEPT (
  ID NUMBER(19) PRIMARY KEY,
  DEPT_NAME VARCHAR2(100) NOT NULL,
  PARENT_ID NUMBER(19)
);
```

**哪些业务流在用**

| 业务流 | 操作 | 业务域 |
|---|---|---|
| 查询请假单列表 | 查询 | leave |

**直接访问它的代码**：`LeaveMapper.selectPage`(R)
<!-- tmh:facts:end -->

## 业务含义
公司部门，树形结构（PARENT_ID 指向上级部门）（sql/schema.sql:2）。

## 关键字段
- ID：部门主键，被 OA_LEAVE.DEPT_ID 等引用（src/main/resources/mapper/LeaveMapper.xml:10）。
- DEPT_NAME：部门名称，必填。
- PARENT_ID：上级部门，根部门为 NULL（src/main/resources/mapper/LeaveMapper.xml:32）。

## 生命周期
代码中没有任何新增/修改/删除 OA_DEPT 的语句，数据应由外部或手工维护【推断】【待确认】。

## 谁在读写
- 只读：LeaveMapper.selectPage 通过外连接取部门名，部门缺失时仍保留请假单（src/main/resources/mapper/LeaveMapper.xml:9-10）。
- LeaveMapper.deptTree 用 CONNECT BY 查询部门树（src/main/resources/mapper/LeaveMapper.xml:32），但全仓库没有调用方，疑似死代码。

## 注意事项
- deptTree 使用 Oracle 专有 CONNECT BY/LEVEL，selectPage 使用 `(+)` 外连接语法，数据库迁移需改写。
- 部门表挂在请假域下，但预算（OA_BUDGET）、报销也按 DEPT_ID 使用部门，归属偏窄【推断】。
- 无外键约束可见，DEPT_ID 合法性靠应用层，目前未校验【推断】。

