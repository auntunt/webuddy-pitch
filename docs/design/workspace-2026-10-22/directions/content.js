/* Shared fictional product data for the three visual studies. */
window.designData = {
  date: '10 月 22 日 · 周四',
  organization: '交付与维护团队',
  tasks: [
    { key:'OA-142',title:'审批通过后仍显示待审批',project:'桥川协同平台',type:'维护',state:'待复核',wait:'等待 42 分钟',person:'林悦',action:'复核修复',detail:'补丁与测试证据已齐，等待核对审批状态回写。',tone:'review' },
    { key:'OA-137',title:'补齐退回流程的验收样例',project:'桥川协同平台',type:'维护',state:'待补信息',wait:'等待 2 小时',person:'许宁',action:'补充样例',detail:'需要业务方确认“退回发起人”与“退回上一步”的区别。',tone:'wait' },
    { key:'TRADE-089',title:'确认 Java 迁移第一批边界',project:'星河交易平台',type:'重构',state:'待决策',wait:'今天 14:00 前',person:'陈禾',action:'确认范围',detail:'第一批包含用户与权限；跨系统单点登录仍待确认。',tone:'review' },
    { key:'PORTAL-063',title:'验证附件下载失败的修复',project:'城北政务门户',type:'维护',state:'等待外部',wait:'昨天 16:18',person:'周岚',action:'查看沟通',detail:'已发送复现说明，等待现场反馈目标浏览器版本。',tone:'wait' },
    { key:'OA-139',title:'检查导出报表的字段映射',project:'桥川协同平台',type:'维护',state:'执行中',wait:'已运行 8 分钟',person:'林悦',action:'查看过程',detail:'正在核对字段含义与现有导出用例。',tone:'run' },
    { key:'TRADE-086',title:'沉淀权限迁移的兼容规则',project:'星河交易平台',type:'知识',state:'待确认',wait:'今天 09:23',person:'陈禾',action:'确认规则',detail:'从上一个任务提取了 3 条规则，需要负责人确认适用范围。',tone:'review' }
  ],
  note: { title:'审批状态回写规则',project:'桥川协同平台',version:'v2.3',owner:'林悦',source:'审批接口规范 · 第 4 节',body:'审批通过后，业务单据状态应更新为“已通过”。流程状态与业务状态分开保存；接口重试不得重复触发后续通知。',boundary:'适用于桥川 v2.3 的请假与报销流程；客户自定义流程仍需单独核对。' }
};
