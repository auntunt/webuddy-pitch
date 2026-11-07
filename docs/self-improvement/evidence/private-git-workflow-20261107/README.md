# 自建私有Git → Jenkins → 网页/MCP → 隔离合并演练

2026-11-07实际完成。复用Mac Docker中的SSH Git服务与Jenkins，没有新建或迁移生产仓库，没有修改模型调用内核。公开JSHERP源码、合成账号、合成业务数据和演练规则；不是怀柔项目联调或真人验收。

## 本轮实际结果

| 步骤 | 实际结果 | 证据 |
|---|---|---|
| 独立工作目录、设计与功能分支 | 从既有ERP克隆新目录，演练主分支固定75a9311，功能分支942949a | [状态与完整SHA](state.json)、[真实差异](change.patch) |
| 自建Git远端 | SSH推送两条rehearsal/git-workflow-20261107分支；未修改原主分支 | operations中的prepare命令与输出 |
| 基线Jenkins #9 | 57项JUnit通过，新增空说明规则失败；真实接口返回200并新增单据，整体FAILURE | [构建回执](baseline-build.json)、[业务结果](baseline/report.json)、[原始失败输入输出](baseline/single-reason-empty.json) |
| 候选Jenkins #10 | 60项JUnit、14条真实HTTP/MySQL/Chromium业务检查全部通过，整体SUCCESS | [构建回执](candidate-build.json)、[逐条业务结果](candidate/report.json) |
| 固定代码与控制侧依据 | 两次构建业务脚本摘要一致，JAR/首页/进程/源码均绑定各自提交；Jenkins实际任务脚本与版本化Jenkinsfile一致 | 两版build.json、[控制侧检查](controller.json) |
| 失败分流与去重 | 无候选完成回执拒绝合并；重复构建触发拒绝；缺失提交和失败基线均不放行；合并后重复操作拒绝 | [查询检查](checks.json)、operations中的非零退出原件 |
| 隔离Git合并与推送 | 快进到受测942949a，推送后重新读取远端SHA一致 | [合并回执](merge.json) |
| 真实网页 | 合成账号登录、打开ERP-1、切换证据页、实际下载交付包；1440×900、768×1024、390×844截图 | [下载包](webuddy-browser/ERP-1-delivery.json)、[桌面原图](webuddy-browser/task-1440.png)、[平板原图](webuddy-browser/task-768.png)、[手机原图](webuddy-browser/task-390.png) |
| 真实MCP | 官方SDK启动实际生成的客户端配置，stdio→HTTP读取；方案、两条原始记录与网页一致；不暴露候选提交工具 | [MCP数据](mcp-delivery.json)、[检查结论](checks.json) |
| 人员决定与发布 | 需求未确认，未真人复核、未业务验收；没有正式主分支合并或生产发布 | merge.json和交付包中的显式状态 |

基线与候选都执行了相同的控制侧规则；没有按被测结果改正确答案。新候选复用了此前4172462的退款说明实现，并新增可追溯设计说明。本轮新增的是私有Git全流程演练、取证和重复操作检查，不冒充新的ERP业务功能。

首次MCP delivery_get返回错误，初始断言未保留具体错误内容；补充诊断后原样复验通过，随后通过实际生成配置再次成功。没有修改产品代码、权限或门禁；首次失败原件保留，具体瞬时原因未确定。

只读Jenkins账号读取config.xml得到403，符合既有权限。配置一致性检查改用已授权的隔离管理员读取；没有扩大只读账号权限。不是绕过配置授权。

## 可操作入口

- Webuddy演练任务：<http://127.0.0.1:18986/#/t/ERP-1>。
- Jenkins失败/成功原件：<http://127.0.0.1:18080/job/erp-verification/9/>、<http://127.0.0.1:18080/job/erp-verification/10/>。
- 自建Git：`ssh://git@127.0.0.1:12222/repos/erp.git`。本轮两条演练分支见state.json；SSH密钥与主机指纹沿用本机private目录，不进入Git。
- 本机MCP配置：`部署包/jenkins-erp-demo-20261106/private/git-workflow-mcp.json`。读取现有本机合成凭据，不将令牌写进配置。未覆盖用户Cursor设置，未宣称Cursor桌面本人操作已完成。

这些地址只在当前Mac本机访问。平台演练账号demo-owner的密码在原private/accounts.json；不复制到文档或聊天。当前ERP预览18981仍是此前#8的4172462，不把它描述成#10新产物部署。#10的真实业务运行发生在Jenkins隔离工作区，结束后清理进程。

## 原件与操作记录

完整本机材料：`运维智能体/部署包/jenkins-erp-demo-20261106/proof/git-workflow-20261107`，逐步命令在同级`git-workflow-20261107-steps`。本目录保留关键原件、逐步开始/结束、命令、退出码、完整stdout/stderr及摘要。[完整本机文件清单](original-manifest.json)可定位其余JUnit与日志，Jenkins也保留构建档案。所有截图原始PNG直接复制，未缩放像素或重新编码。

[设计、职责、复跑步骤与现场人员操作表](../../../../examples/project-testing/jsherp/jenkins-demo/私有仓库全流程演练.md)。工具记录actor=Codex、actor_type=agent，identity_verified=false，不假称真人操作或防篡改审计。

## 当前边界

- SSH Git仓库已可用，但没有Gitea/GitLab网页PR及受保护分支能力；演练Git脚本不是产品审批系统。
- 平台中的运行仍标为external_test，current_validity=not_checked、ready_to_merge=null；不能把导入外部绿灯自动变成当前候选验收通过。任务顶部仍沿用既有接管提示，不能据此认定需求已确认或平台已自动完成开发。
- 本轮Webuddy产品代码基线71cfd2c6，新增代码仅为演练脚本及文档。没有更改认证、审批或验证引擎，也未重新发布43或阿里云。
- Jenkins构建仍在Linux演示容器，Windows没有登记为本轮Jenkins执行节点。原生Windows个人MCP凭据限制不变。
- 正式人员确认、客户网络接入、客户CI、怀柔业务规则及提效对照均未完成；不能由这次演练替代。

## 固定演示版本

交付时远端出现并行产品提交，已保留并合入本轮记录，没有强推。演练服务固定在本机 `platform-source-924263c0` 源码副本（产品基线71cfd2c6加本轮演练脚本），[文件摘要](fixed-source.json)记录实际内容；客户端配置也指向该副本。重新启动后通过实际MCP配置复验网页/协议原始记录一致，未重复导入运行或创建任务。测试用独立Chrome已关闭，18986演示服务保留。后续产品提交不继承本轮验证结论。
