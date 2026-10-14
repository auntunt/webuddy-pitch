# 端到端运行记录：用 Claude Code + tmh 在老项目上实现一个新需求

日期：2026-10-07 · Claude Code 2.1.292（非交互模式 `claude -p`）· 样例项目 `examples/legacy-java-oa`

## 准备

```sh
python3 tmh.py install --repo <副本> --git-hook
tmh init --target-db dm8 --target-arch arm64 --target-crypto sm
tmh assess && tmh map && git commit -am "install tmh" && tmh baseline --with-tests   # mvn test 通过
```

## 给智能体的需求（原文）

> 新需求：请假列表接口 /leave/list 需要支持按审批状态（STATUS 字段，如 APPROVED、PENDING）筛选，不传时保持原行为。请按本仓库的 legacy-feature 技能流程完成……数据库改造目标是达梦。不要问我问题，遇到需要决定的事按合理默认处理并在契约里记录。

## 过程（10 轮，约 80 秒）

1. 智能体自己加载了 `legacy-feature` 技能，运行 `tmh status`、`tmh task new` 建契约
2. 读入口、服务、Mapper XML、基线测试，填写契约：要改变 / 必须保持 / 6 条验收条款 / 影响范围（附文件:行号）/ 风险（区分 [事实] [推断] [待确认]）
3. **先写特征测试** `LeaveListFilterTest`，在未改动的代码上跑通“保持不变”的两条
4. 最小改动实现：Controller 加可选参数，Service 新增重载并保留旧方法，Mapper XML 用 `<if>` 加参数绑定条件（标准 SQL，达梦可运行）。**没有顺手改**已有的 Oracle 写法，并说明那属于数据库改造工作项
5. `mvn test` 通过；`tmh verify`；把结果逐条写回契约；`tmh map` 刷新地图
6. 汇报中明确列出未验证项（真实库上的筛选结果）和需要人确认的问题

产物：[契约](e2e-T001-contract.md) · [代码 diff](e2e-T001.diff) · [新增测试](e2e-T001-LeaveListFilterTest.java)

## 这次运行暴露并已修复的问题

| 问题 | 修复 |
|---|---|
| `verify` 把未被 git 忽略的 `target/classes/application.yml`（构建副本）当成新改动，报了 4 条“新引入的不兼容点”，导致误判未通过 | 改动文件列表排除构建输出目录（target/bin/obj/build 等），加测试 |
| 智能体用 shell 脚本（python heredoc）改文件，绕过了 Edit/Write 钩子的即时检查 | `pre-bash` 钩子增加对受保护文件的写入检测；CLAUDE.md 要求用编辑工具改源码；`verify` 作为最后一道检查仍然有效 |
| 内置工具运行时在 `.tmh/tool/` 下生成 `__pycache__` | 启动脚本禁用字节码缓存，`.tmh/.gitignore` 忽略 |
| Stop 钩子把安装 harness 时新增的 AGENTS.md/CLAUDE.md 当成代码改动 | 排除 harness 文件，并忽略基线之前就存在的改动 |

修复后在同一副本上重新运行 `tmh verify`：受保护文件 ✅、新引入不兼容点 ✅ 无、`mvn -q -B test` ✅。
