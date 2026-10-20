# 待确认问题

| 问题 | 涉及页面 | 要问谁 | 答复 |
|---|---|---|---|
| 财务系统 /api/pay 是否幂等、失败如何对账 | flow:post-expense-pay | 财务/业务方 | |
| 跨月付款扣哪个月预算（现按付款当月） | flow:post-expense-pay | 财务 | |
| 出纳 cashier 是否需鉴权 | flow:post-expense-pay | 业务方 | |
| 重复驳回已拦截；重复“通过”是否也应报错（目前静默写日志）？ | flow:post-expense-audit | 财务/业务 | |
| 报销通过后预算冻结额何时转为实际支出？ | flow:post-expense-audit | 财务 | |
| 驳回释放预算应按提交月还是当前月？ | flow:post-expense-audit | 财务 | |
| OA_APPROVAL_LOG.LEAVE_ID 存报销单 id 是否有意，如何区分单据类型？ | flow:post-expense-audit | 开发/业务 | |
| 提交报销时冻结预算后，驳回/撤销是否释放？5万上限是否因类别/人员而异？ | flow:post-expense-submit | 财务 | |
| 请假驳回对不存在/非待审批单据是否应报错？目前会写无效日志 | flow:post-leave-reject | 业务 | |
| 请假上限30天是否区分假种、是否需余额校验、起止日期是否需要记录 | flow:post-leave-submit | HR | |
| 新增用户的操作权限与是否需要审计日志 | flow:post-user-add | 业务 | |
| 用户停用（离职）后其在途请假/报销单及审批权限如何处理？ | flow:post-user-disable | 业务 | |
| 超期30天作废请假单是否为业务要求？作废后是否通知/可重提 | flow:reportjob-expire | HR | |
| 每晚请假汇总导出的内容口径与文件消费方？当前仅写入 "ok" | flow:reportjob-export | 业务 | |
| 请假审批人是否需权限/上下级校验、能否自批 | flow:post-leave-approve | 业务方 | |
| 预算行由谁何时录入？跨月报销的冻结/释放/付款应按提交月还是当前月？ | tbl:OA_BUDGET | 财务 | |
| OA_APPROVAL_LOG 建表列 BILL_ID 与 INSERT 列 LEAVE_ID 不一致，实际库是哪个 | tbl:OA_APPROVAL_LOG | 开发/DBA | |
| OA_DEPT 数据由谁维护？deptTree 查询是否已废弃？ | tbl:OA_DEPT | 业务/开发 | |
| 报销类别 CATEGORY 是否固定为差旅/招待/办公并需校验 | tbl:OA_EXPENSE | 财务 | |
| 已停用用户是否仍可作为审批人/审核人/申请人？目前仅报销提交校验状态 | tbl:OA_USER | 业务 | |
| 请假单 START_DATE 从不写入，是否应在提交时录入 | tbl:OA_LEAVE | 业务方 | |
| application.yml 未配数据库密码，实际来源？sigar、PasswordUtil、P_LEAVE_STAT 是否仍在使用？ | mod:. | 开发 | |
