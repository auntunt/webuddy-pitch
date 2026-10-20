# 提交请假申请

状态：待确认

## 业务目的
员工提交请假申请，生成一张待审批的请假单并留下提交记录。

## 触发与角色
- 触发：POST /leave/submit（参数：申请人、部门、天数、事由）
- 操作人 / 角色：申请人。【推断】代码中没有任何登录/权限判断，申请人是请求参数传入的，可被随意填写。

## 主要步骤
1. 校验请假天数在 1~30 天。
2. 取序列 SEQ_OA_LEAVE 得到单号。
3. 写入 OA_LEAVE，状态 SUBMITTED。
4. 写入 OA_APPROVAL_LOG，动作 SUBMIT，备注为事由。（两步在同一事务内）

## 业务规则
- 天数必须在 1~30 天（LeaveService.java:28）。
- 注释写“超过 3 天需要部门经理审批”，但代码只校验了范围，没有按天数分流审批人。【待确认】是遗漏还是在别处实现？

## 状态变化
- OA_LEAVE.STATUS：(新建) → SUBMITTED

## 异常与边界
- 天数越界抛 IllegalArgumentException。
- 未校验部门是否存在、起止日期（插入语句没有 START_DATE，而列表查询会读取 START_DATE）。【推断】起止日期可能由别处维护或根本没填。

## 证据
- 入口：`LeaveController.submit`（src/main/java/com/acme/oa/controller/LeaveController.java:26）
- 业务逻辑：`LeaveService.submit`（LeaveService.java:25）
- SQL：LeaveMapper.xml:18，ApprovalLogMapper.xml:4

## 待确认问题
- 【待确认】3 天以上需部门经理审批的规则是否需要实现？谁来审批？
- 【待确认】申请人身份是否应取登录用户？
- 【待确认】请假起止日期从哪里录入？
