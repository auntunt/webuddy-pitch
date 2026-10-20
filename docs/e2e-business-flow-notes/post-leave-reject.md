# 驳回

状态：待确认

## 业务目的
审批人不同意请假申请，将单据驳回并记录原因。

## 触发与角色
- 触发：POST /leave/reject（参数：单号、审批人、意见）
- 操作人 / 角色：审批人。【推断】同审批通过，未见权限校验。

## 主要步骤
1. 仅当状态为 SUBMITTED 时，更新为 REJECTED，写入审批人。
2. 写入 OA_APPROVAL_LOG，动作 REJECT，备注为驳回意见。（同一事务）

## 业务规则
- 状态条件在 SQL 中（LeaveMapper.xml:25）。

## 状态变化
- OA_LEAVE.STATUS：SUBMITTED → REJECTED

## 异常与边界
- 与“审批通过”不同：没有检查更新行数。对非待审批或不存在的单据驳回，不会报错，但仍会写一条 REJECT 审批日志，造成日志与单据状态不一致。【推断】这是缺陷或遗漏。
- 未写审批时间（approve 会写 APPROVED_AT，reject 不写）。
- 驳回后没有重新提交的流程，代码中 REJECTED 是终态。【待确认】

## 证据
- 入口：`LeaveController.reject`（LeaveController.java:37）
- 逻辑：`LeaveService.reject`（LeaveService.java:46）
- SQL：LeaveMapper.xml:25

## 待确认问题
- 【待确认】驳回后申请人能否修改重提？
- 【待确认】对非待审批单据驳回时是否应报错？
- 【待确认】驳回意见是否必填？
