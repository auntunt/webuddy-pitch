# 术语表

| 业务词 | 代码 / 表 | 说明 |
|---|---|---|
| 出纳付款 | ExpenseService.pay / OA_EXPENSE.STATUS=PAID | 审核通过的报销单由出纳付款 |
| 预算冻结/已用 | OA_BUDGET.FROZEN / USED | 付款时冻结转已用 |
| 冻结额 | OA_BUDGET.FROZEN | 提交报销时占用的部门月度预算，驳回时释放 |
| 财务审核 | POST /expense/audit | 对报销单通过/驳回 |
| 冻结预算 | OA_BUDGET.FROZEN | 报销提交时占用部门当月预算，剩余=TOTAL-FROZEN-USED |
| 请假驳回 | POST /leave/reject / OA_LEAVE.STATUS=REJECTED | 审批人驳回请假单 |
| 工号 | OA_USER.ID | 用户主键，新增时必须唯一 |
| 超期请假单作废（EXPIRED） | LeaveMapper.expireStale / OA_LEAVE.STATUS=EXPIRED | 提交后30天未处理，每天01:30定时作废 |
| 每晚导出请假汇总 | ReportJob.export | 凌晨 2 点定时导出 CSV 到共享盘 |
| 部门 | OA_DEPT | 树形部门，PARENT_ID 为上级 |
