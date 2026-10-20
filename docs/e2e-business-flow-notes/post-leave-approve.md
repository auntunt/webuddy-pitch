# 审批通过：记录审批人与审批时间

状态：待确认

## 业务目的
审批人同意请假申请，记录审批人和审批时间并留痕。

## 触发与角色
- 触发：POST /leave/approve（参数：单号、审批人）
- 操作人 / 角色：审批人。【推断】代码未校验该人是否有审批权限，也未校验是否本部门经理或是否本人审批自己的单据。

## 主要步骤
1. 仅当单据状态为 SUBMITTED 时，更新为 APPROVED，写入审批人和审批时间。
2. 若没有更新到行，报错“单据不是待审批状态”。
3. 写入 OA_APPROVAL_LOG，动作 APPROVE。（同一事务）

## 业务规则
- 只有待审批（SUBMITTED）的单据可通过，靠 UPDATE 条件判断，可防重复审批（LeaveMapper.xml:22）。

## 状态变化
- OA_LEAVE.STATUS：SUBMITTED → APPROVED（同时写 APPROVER、APPROVED_AT）

## 异常与边界
- 单号不存在与状态不对都报同一个错误。
- 已被定时任务作废（EXPIRED）的单据不能再审批通过。

## 证据
- 入口：`LeaveController.approve`（LeaveController.java:31）
- 逻辑：`LeaveService.approve`（LeaveService.java:37）
- SQL：LeaveMapper.xml:22

## 待确认问题
- 【待确认】谁有权审批？是否需要分级审批、禁止自批？
- 【待确认】通过后是否需要通知申请人或同步考勤？代码中没有看到。
