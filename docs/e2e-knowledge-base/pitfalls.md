# 坑与反直觉的地方

隐藏的定时任务、靠触发器维护的字段、配置中心覆盖、魔法常量等。
- 出纳付款：外部支付调用在本地事务内且先于落库，失败不可回滚外部付款（ExpenseService.java:77）。

- 审批日志表 OA_APPROVAL_LOG 的列 LEAVE_ID 同时被报销审核用来存报销单 id（ApprovalLogMapper.xml:4）。
- 报销重复驳回已修复：驳回更新 0 行即抛异常，不再重复释放预算（ExpenseService.java:64-68）。遗留：重复“通过”不检查影响行数，仍会写 EXPENSE_PASS 日志（ExpenseService.java:61-62）【推断】。
- 审批日志表 OA_APPROVAL_LOG 的列 LEAVE_ID 被报销流程复用来存报销单ID（ApprovalLogMapper.xml:4, ExpenseService.java:50）。
- 请假驳回不检查更新行数，非 SUBMITTED 单据也会写 REJECT 日志（LeaveService.java:48-49）。
- 停用用户不校验存在性，也不处理在途单据（UserService.java:23-25）。
- ReportJob.expire 名为报表任务实为请假单作废，且无审批日志（ReportJob.java:26-28）。
- ReportJob.export 名为导出请假汇总，实际只写 "ok"，并依赖 Windows cmd 与 UNC 路径（ReportJob.java:19-22）。
- OA_BUDGET 冻结/释放/消耗均按当前系统月份匹配，跨月会错位（BudgetMapper.xml:10,13）。
- OA_APPROVAL_LOG：schema.sql:50 列 BILL_ID，ApprovalLogMapper.xml:4 插入 LEAVE_ID，两处不一致；且请假/报销共用同表无单据类型列。
- LeaveMapper.deptTree 没有任何调用方，且使用 Oracle CONNECT BY（LeaveMapper.xml:32）。
- PasswordUtil.hash 用 MD5 并以 new String(bytes) 转换摘要，结果会损坏（PasswordUtil.java:7-10）。
