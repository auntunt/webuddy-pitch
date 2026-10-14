---
name: xinchuang-assess
description: 对 Java/.NET 老项目做信创改造评估（数据库、中间件、操作系统、CPU 架构、JDK/.NET、国密、浏览器），输出分波次改造方案、工作量与阻塞项。用户提到信创评估、国产化、迁移达梦/金仓/麒麟/鲲鹏等时使用。
---

# 信创改造评估

## 步骤

1. **确认改造目标**。读 `.tmh/config.json`；目标数据库、中间件、操作系统、CPU、是否国密不清楚时，向用户确认（给出常见选项），然后：
   `tmh init --target-db dm8|kingbase|opengauss|gaussdb|oceanbase --target-appserver tongweb|apusic|bes|inforsuite --target-os kylin|uos --target-arch arm64|loongarch64|x86_64 --target-crypto sm|none`
   用户暂不确定时保持 unknown，规则会按最严格方式运行，并在报告中注明。
2. **跑评估**：`tmh assess`，再 `tmh map`（若未生成）。
3. **复核扫描结果**（自动规则会有误报和漏报）：
   - 每条高风险规则抽查 2～3 处命中，打开文件确认；误报写进工作项备注并标记 `wontfix`。
   - 补查规则看不到的：动态拼接 SQL（`tmh where "+ \" where"`、`StringBuilder`）、配置中心、外部调用的第三方系统、二进制依赖（`lib/` 目录、`HintPath`）。
   - 存储过程、ActiveX 控件、WebForms、WCF 这类“大块头”单独估算。
4. **形成方案**，写入 `.tmh/knowledge/xinchuang-plan.md`：
   - 改造目标与兼容模式建议（引用 `.tmh/kb/db-dialects.md` 等知识库，并标注需要厂商确认的点）
   - 分波次计划：第 1 波平台与构建 → 第 2 波数据库 → 第 3 波中间件/OS/架构 → 第 4 波国密与前端；每波列工作项 ID、工作量、前置条件、验证方式
   - 阻塞项与需要客户/厂商提供的东西（驱动、嵌入式中间件包、信创版控件、测试环境）
   - 需要人决定的问题清单
5. **汇报**：先给结论（总体难度、最大的 3 个风险、建议的第一步），再给方案文件路径。不要把工作量估计说成承诺。
