export type Feature = { name: string; route: string; detail: string; project?: boolean }
export const featureGroups: { name: string; items: Feature[] }[] = [
  { name: '需求与协作', items: [
    {name:'完整工作台',route:'/workspace',detail:'待办、责任人、交接和复核'},
    {name:'全部工单',route:'/tickets',detail:'需求详情、优先级、附件、完整处理流程'},
    {name:'团队与分工',route:'/team',detail:'任务分配、个人队列和人工复核'},
    {name:'会议与行动',route:'/meetings',detail:'会议记录、行动项和责任跟进'},
    {name:'客户与沟通',route:'/clients',detail:'客户信息、原始需求和沟通记录'},
    {name:'需求收集',route:'/reqs',detail:'收集、澄清和转入工单'},
  ]},
  { name: '开发与交付', items: [
    {name:'整体改造计划',route:'/reform',detail:'多需求依赖、分批执行、检查点和整体集成'},
    {name:'改造任务',route:'/rtickets',detail:'查看改造中的任务进展'},
    {name:'依赖关系',route:'/rdeps',detail:'查看改造任务之间的依赖'},
    {name:'验证与交付',route:'/deliveries',detail:'创建项目、实施、验证、交付记录'},
    {name:'版本与发布',route:'/versions',detail:'版本依据、发布和回退入口'},
    {name:'运行记录',route:'/runs',detail:'运行详情、产物、失败原因与原始日志'},
    {name:'项目与环境',route:'/projects',detail:'仓库、项目配置、环境和准备情况'},
  ]},
  { name: '知识与项目理解', items: [
    {name:'知识与记忆',route:'/memory',detail:'项目知识、经验确认和来源'},
    {name:'知识分类与评审',route:'/memory/learning',detail:'知识版本、评审和采用'},
    {name:'同类问题',route:'/memory/clusters',detail:'问题分组、共性与经验'},
    {name:'项目交接说明',route:'/handoff/{project}',detail:'有来源的项目现状与交接',project:true},
    {name:'业务问题与局部地图',route:'/maps/{project}',detail:'围绕具体问题定位业务与代码',project:true},
    {name:'业务与代码图谱',route:'/atlas',detail:'查看业务、接口、数据和代码关系',project:true},
    {name:'状态流转',route:'/states',detail:'查看业务状态及转换依据',project:true},
    {name:'参考项目与引用',route:'/library',detail:'知识共享、授权和固定引用',project:true},
    {name:'知识页管理',route:'/kb',detail:'构建、编辑、校验和确认知识页',project:true},
  ]},
  { name: '效果与管理', items: [
    {name:'流程与统计',route:'/lead',detail:'流程进展、阻塞与团队协作数据'},
    {name:'提效报告',route:'/eff',detail:'对照实际处理记录评估效果'},
    {name:'试点记录',route:'/pilots',detail:'试点目标、证据与结论'},
    {name:'监控总览',route:'/overview',detail:'运行状态、监控与告警'},
    {name:'外部系统',route:'/int',detail:'工单系统、机器人和外部接入',project:true},
    {name:'完整设置',route:'/settings',detail:'模型连接、测试机、自动流程与访问配置'},
    {name:'成员与权限',route:'/access',detail:'查看并管理已获授权的成员和项目权限'},
  ]},
]
export function featureRoute(feature:Feature, project:string) { return feature.route.replace('{project}',encodeURIComponent(project)) }
