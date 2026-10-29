# Webuddy / tmh：AI-native 的老项目运维平台

面向国内 toB 软件公司长期维护的 Java / .NET 业务系统（OA、ERP、CRM、财务、政务审批等）。它由两部分组成：

- **tmh 工具链（CLI + MCP）**：装在 Codex / Claude Code 上的维护 harness。先对整个项目做一次确定性分析，沉淀成项目知识库（知识图谱 + Wiki），之后每个任务先查知识库、只读相关代码，改完由独立验证把关，增量更新知识库。可接 DeepSeek、Kimi、GLM、Qwen 等国产模型。
- **Webuddy 平台（`tmh serve`）**：和 Jira、禅道同级的运维工单平台。工单直接连着业务知识库，内置 Codex / Claude Code，支持多租户与团队、项目成员隔离开发、个人复核与正式验收、候选预览、证据包与甲方签收。

核心原则：能确定的事交给工具，需要判断的事才交给模型；事实与理解分开标注；AI 备齐证据，验收和关单只由人做。

> 当前状态、已知限制与下一轮优先级：[docs/NEXT-STEPS.md](docs/NEXT-STEPS.md) · 部署：[docs/DEPLOY.md](docs/DEPLOY.md) · 变更日志：[CHANGELOG.md](CHANGELOG.md) · 历次上线验证：[audit/](audit/)

## 能力一览

| 场景 | 说明 | 文档 |
|---|---|---|
| 运维工单平台 | 工单列表与看板、业务全景、知识库；在工单上让智能体分析定位、出方案或在独立工作树里改代码，人审阅后采纳 | [platform.md](docs/platform.md) |
| 多租户与团队 | 平台所有者、租户、成员与项目授权；共享令牌和显示名不能代替个人账号 | [tenant-access.md](docs/tenant-access.md)、[team-pilots.md](docs/team-pilots.md) |
| 项目执行与候选预览 | 每个项目独立的 Codex 路由与配置；成员在隔离工作区开发，候选自动测试/构建并提供隔离预览 | [codex-project-route.md](docs/codex-project-route.md)、[project-library.md](docs/project-library.md) |
| 编程助手接入 | Webuddy CLI / MCP：读取需求与证据、沟通交接、启动受控运行、查看候选预览 | [workbench-agent.md](docs/workbench-agent.md)、[task-handoffs.md](docs/task-handoffs.md) |
| 项目知识库 | 工具抽出知识图谱（入口、调用、SQL、表、状态机），智能体自底向上写业务流 → 业务域 → 系统总览，每页带证据、经人确认 | [knowledge-base.md](docs/knowledge-base.md) |
| 新需求与改动 | 变更契约 → 特征测试 → 最小改动 → 独立验证，按改动行算出触及的业务流 | [agent-commands.md](docs/agent-commands.md) |
| 验收闭环 | 没有验收标准不进实现；L1–L4 分层验收；入口路径检查拦住“没接上入口”的假绿；关单只认用户确认 | [acceptance.md](docs/acceptance.md) |
| 证据流 | 转待验证时自动打证据包（追加式哈希链），甲方用一次性链接逐条签收或退回，账本自动生成 | [evidence-flow.md](docs/evidence-flow.md) |
| 经验与学习 | 经验卡片人工决定、组织知识与开发习惯、学习实验 | [lesson-decisions.md](docs/lesson-decisions.md)、[knowledge-learning.md](docs/knowledge-learning.md) |
| 运维工具接入 | Jira、禅道、GitLab、Jenkins、SonarQube、Confluence、钉钉/飞书/企业微信，及配置或插件接入的任何工具 | [integrations.md](docs/integrations.md) |
| 改造升级 | 信创、.NET Framework → .NET 8、JDK 升级：规则扫描、分波次方案、工作项台账 | — |

## 快速开始

环境：CLI 只依赖 Python 3.8+ 标准库；平台里的项目 Codex 执行需要 Python 3.11+（读取 TOML 配置）。

**路径一：装进项目，在 Codex / Claude Code 里用**

```sh
# 插入 AGENTS.md/CLAUDE.md 区块（不覆盖原内容），装好技能、子代理、钩子和 MCP
python3 /path/to/webuddy-pitch/tmh.py install --repo /path/to/legacy-project --git-hook

cd /path/to/legacy-project
X="python3 .tmh/tool/tmh.py"
$X kb build && $X baseline --with-tests   # 知识图谱 + Wiki 骨架，记录基线
$X report --open                          # 生成并打开业务全景报告
codex                                     # 或 claude
```

进入智能体后可以直接说：“接手这个项目，做全项目分析，建立知识库”（`legacy-onboard`）、“梳理这个系统的业务流”（`business-flow`）、“请假列表要能按审批状态筛选”（`legacy-feature`）。

**路径二：启动平台**

```sh
cd /path/to/legacy-project                # 已运行过 tmh kb build
python3 .tmh/tool/tmh.py serve --key TOG --open           # 默认只在本机 127.0.0.1:8790
TMH_TOKEN=<随机串> python3 .tmh/tool/tmh.py serve --host 0.0.0.0   # 团队使用必须带令牌
python3 .tmh/tool/tmh.py user add <账号>                  # 有账号后网页改为账号密码登录
```

多租户、生产部署和升级见 [docs/tenant-access.md](docs/tenant-access.md) 与 [docs/DEPLOY.md](docs/DEPLOY.md)。也可以 `pip install .` 后使用 `tmh` 和 `webuddy` 两个命令。

## 项目知识库

```sh
tmh kb build            # 构建知识图谱 + Wiki 骨架；之后每次运行都是增量的，并报告哪些页面因代码变化而过期
tmh kb next             # 领取一个撰写任务：写作要求 + 有预算的上下文包（事实、相关源码、下层页面摘要）
tmh kb done <页面id>     # 校验（标题、摘要、各节内容、证据 文件:行号 真实存在）后入库
tmh kb status           # 覆盖情况：已确认 / 待确认 / 过期 / 未分析
tmh kb confirm <id> --by 张三   # 人工确认
tmh kb show <类|方法|表|URL>    # 查图谱：调用方、被调用方、读写哪些表、属于哪条业务流
tmh context "<需求原文>"        # 每个任务开始先运行：相关知识页、业务流、表、代码位置
```

- **知识图谱**（`.tmh/cache/graph.db`，SQLite）由工具确定性生成，不花 token。按文件缓存解析结果，第二次构建只重新解析改过的文件。
- **Wiki**（`.tmh/knowledge/`，随代码提交）：`index.md` 总览 → `domains/` 业务域 → `flows/` 业务流、`entities/` 业务对象、`modules/` 代码模块，外加术语表、决定、坑、待确认问题。每页上半部分是自动刷新的事实，下半部分是业务理解。
- **锚定**：每页记下它描述的代码的指纹。代码变了，只有受影响的页面过期，修订时上下文包里带着旧说明和变化点，只改需要改的部分。
- **全项目分析**：用 `legacy-onboard` 技能。智能体主会话写业务域和总览；业务流、业务对象交给多个 `kb-writer` 子代理并行写（子代理可以用便宜的模型）。上层页面只读下层页面的摘要，不再读代码。
- **日常维护**：AGENTS.md 要求“知识优先”：先 `tmh context`，再读代码。改完代码，Stop 钩子提醒用 `knowledge-upkeep` 增量更新知识库。

## 报告长什么样

`tmh report` 生成 `.tmh/report/` 文件夹（`index.html` 加按业务域拆分的 `data/`）。它不联网、不依赖任何库，可以在内网打开；发给别人时把整个文件夹打包。几千条业务流的系统也只在点开某个业务域时才加载那个域的数据。

报告把两层内容放在一起：静态分析抽出的**事实**（调用链、读写的表、状态流转、校验规则、代码位置），和智能体写在知识库里的**理解**（业务名称、目的、规则、推断）。理解里带 `文件:行号` 的句子显示为“代码核实”，写成【推断】的显示为“模型推断”，每页显示确认状态（已确认 / 待确认 / 过期 / 未分析）。

- **业务全景**：系统总览（智能体写）、业务域关系图（哪个域读写了哪个域的表）、每个业务域的规模和说明进度。
- **项目构建**：架构分层、技术组件（按 import 的文件数看依赖深浅）、部署与运行（compose 服务、Dockerfile、Tomcat、脚本、构建产物）、配置文件（只读键名，不读密码值）、维护风险（反编译代码、无测试、动态表名、配置分派、超长方法、高扇入方法）。
- **业务域**：业务流列表（可筛选）、业务对象与表、状态机图、业务说明。
- **业务流**：左边“业务理解”，右边“代码事实”：调用链图（链太长时用大纲，重复调用只展开一次）、数据与状态、规则与静态分析断点（接口多实现、动态表名等需要推断的地方）。
- 顶部搜索：业务名、URL、类名、表名。

`tmh report --classic` 生成旧版单文件报告 `classic.html`，带“分析过程”时间线，适合小项目。

`docs/demo-report.html` 是在样例项目上生成的旧版报告。

## 组成

```
┌──────────────── 智能体层（Codex / Claude Code） ────────────────┐
│ AGENTS.md（Codex 与 Claude 共用）/ CLAUDE.md：入口、规则、技能表        │
│ 8 个技能：legacy-onboard（全项目分析）business-flow  legacy-feature       │
│           knowledge-upkeep（知识库增量维护）ops-tools（运维工具协同）       │
│           xinchuang-assess  xinchuang-migrate  dotnet-modernize          │
│ 5 个子代理：知识库撰写（可并行）· 勘察 · 影响分析 · SQL 改写 · 独立复核      │
│   （Claude：.claude/agents/*.md；Codex：.codex/agents/*.toml）            │
│ 钩子：保护基线测试 · 检查新引入的问题 · 拦截危险命令 · 结束前要求验证 ·      │
│      记录每次工具调用（Claude：.claude/settings.json；Codex：.codex/hooks.json）│
│ MCP 服务 tmh：知识库检索 + 运维工具（.mcp.json；.codex/config.toml）          │
├──────────────── 知识层（都在仓库 .tmh/ 里，跨会话保留） ──────────────────┤
│ cache/graph.db             知识图谱（自动生成，按文件增量）                  │
│ knowledge/                 Wiki：总览/业务域/业务流/业务对象/模块/术语…     │
│                            每页 = 事实块 + 业务理解，锚定代码指纹，自动判过期 │
│ activity.jsonl             分析过程记录                                  │
│ tasks/                     变更契约    workitems.json  改造工作项台账      │
├──────────────── 确定性工具层（tmh 命令，纯 Python 标准库） ──────────────────┤
│ kb/context  知识库与按需检索   flows/report/note  业务流与报告               │
│ map/where/impact  定位与影响分析                                          │
│ task/baseline/verify  契约与验证闸门   assess/items  改造评估与台账            │
├──────────────── 运维工具接入层（tmh/integrations/） ──────────────────────┤
│ 统一模型：工单 · 构建 · 合并请求 · 质量问题 · 文档 · 通知                       │
│ 内置：Jira 禅道 GitLab Jenkins SonarQube Confluence 钉钉 飞书 企业微信 webhook │
│ 扩展：generic（写配置即可接入）· .tmh/integrations/*.py 插件                  │
│ 凭据只读环境变量 · 写操作默认演练 · 内网代理/CA · 重试                           │
└──────────────────────────────────────────────────────────────────────┘
```

- **能确定的事交给工具，需要判断的事才交给模型**：调用链、SQL、状态变化、影响范围都由工具确定性地抽取，附带文件和行号。这样模型能力弱一些也能用，结论人可以复查。
- **事实与理解分开**：工具抽取的是事实；业务说明由智能体起草，标【推断】【待确认】，人看过之后才能改成“已确认”。
- **不能靠改测试让结果变绿**：基线测试和验证配置由钩子锁住，`verify` 还会再查一遍。
- **离线可用**：CLI 只依赖 Python 3.8+ 标准库（平台里的项目 Codex 执行需要 3.11+）。安装时工具会复制到目标仓库的 `.tmh/tool/`，内网和国产服务器上都能跑。

## 接国产模型

```sh
$X agent-config codex  --provider deepseek --model <模型名> --fast-model <便宜的模型名>
$X agent-config claude --provider kimi --model <模型名>
```

命令会输出 `~/.codex/config.toml` 片段或需要设置的环境变量。密钥只放在环境变量里。

| provider | Codex（Responses API） | Claude Code（Anthropic 兼容） |
|---|---|---|
| deepseek | `https://api.deepseek.com`（厂商有 Codex 指南） | `https://api.deepseek.com/anthropic` |
| kimi / kimi-code | `https://api.moonshot.cn/v1` / `https://api.kimi.com/coding/v1`（有指南） | `https://api.moonshot.cn/anthropic` / `https://api.kimi.com/coding/` |
| glm-intl / glm | `https://api.z.ai/api/v1`（有指南）/ 国内站【未核实】 | `https://api.z.ai/api/anthropic` / `https://open.bigmodel.cn/api/anthropic` |
| qwen | 百炼 Responses 兼容地址（需要 WorkspaceId）【未核实】 | `https://dashscope.aliyuncs.com/apps/anthropic` |
| litellm | 本机网关，用于只支持 Chat Completions 的模型 | — |

端点于 2026-10 按厂商文档核对，模型名请以厂商当前文档为准。Codex 已经不支持 `wire_api = "chat"`。

## 接运维工具

```sh
$X int add jira --type jira --url https://jira.example.com --token-env JIRA_TOKEN --set project=OA
$X int add ci --type jenkins --url https://jenkins.example.com --user 账号 --password-env JENKINS_TOKEN --set job=oa/oa-web/master
export JIRA_TOKEN=... JENKINS_TOKEN=...   # 凭据只放环境变量，配置里只记变量名
$X int test

$X ticket OA-123 --task      # 工单 → 相关业务流/代码 → 带工单链接的任务契约
$X build failure             # 最近一次失败构建 → 出错的项目代码 → 业务流
```

评论、流转、触发构建、发通知默认只演练，加 `--confirm` 才执行。没有内置的工具，可以写一段 `generic` 配置接入，或者在 `.tmh/integrations/` 放一个插件。见 [docs/integrations.md](docs/integrations.md)。

## 命令

| 命令 | 作用 |
|---|---|
| `install [--engines codex,claude] [--git-hook]` | 安装到目标仓库 |
| `kb build\|status\|next\|done\|confirm\|show\|pack` | 项目知识库：构建/增量更新、覆盖情况、领取任务、校验入库、人工确认、查图谱 |
| `kb read\|chain\|triage\|questions\|ask\|answer` | 按原文读知识页和业务链路、需求预判、业务方问答回流 |
| `kb overrule 预判编号 --who --reason` / `kb metrics [--days]` | 改判一次预判；少找人统计（直接答比例、采纳率、每周转人工、答复等待） |
| `offline-pack [--out x.zip] [--verify x.zip]` | 打内网离线安装包（无第三方依赖，带 sha256 清单和接内网模型说明） |
| `context "需求或关键词"` | 按需检索相关的知识页、业务流、表和代码位置 |
| `flows [关键词] [--notes] [--changed] [--json]` | 业务流：清单、单条详情、生成说明模板、当前改动触及的业务流（按改动行判断） |
| `report [--open] [--classic]` | 生成业务全景报告（--classic 为旧版单文件） |
| `note finding\|decision\|question "…" [--detail] [--flow]` | 记录分析过程 |
| `map` / `where 关键词` / `impact 目标` | 项目地图、按业务词定位（支持中文）、反向影响分析 |
| `task new "标题" --kind feature\|bugfix\|...` | 变更契约 |
| `baseline [--with-tests]` / `verify [--no-tests] [--task T001]` | 基线与独立验证闸门（`--task` 同时检查改动是否接上契约入口） |
| `accept check\|path-check\|advance\|reject\|status [T001] [--to 状态] [--build 构建号]` | 验收状态机：检查 AC、入口路径检查、推进状态、按构建列出待验收任务 |
| `accept confirm\|close T001 --who 姓名` / `accept correct T001 --kind …` | 用户确认与关单（只能由人）；记一次纠错 |
| `init --target-xxx` / `assess` / `items` | 改造目标、评估、工作项台账（信创等） |
| `agent-config codex\|claude --provider ...` | 生成接国产模型的配置 |
| `status` | 总览 |
| `int list\|types\|add\|test\|remove` | 运维工具接入 |
| `ticket 工单号 [--task]` / `issue get\|search\|comment\|transition` | 工单：开工上下文、任务契约、查询、评论/流转（默认演练） |
| `build status\|log\|failure\|trigger [job]` | 构建：最近构建、日志、失败定位到业务流、触发（默认演练） |
| `change list\|get` / `quality [--gate]` / `doc search\|get` / `notify` | 合并请求、代码质量、文档、群通知 |
| `trace 工单号` | 按工单追溯提交、文件、业务流 |
| `mcp` | 以 MCP 服务方式运行（install 已配置好） |
| `serve [--port 8790] [--key TOG] [--open]` | 启动运维平台网页：工单、看板、业务全景、知识库，内置 Claude Code / Codex |

## 开发与测试

```sh
python -m pip install pytest
python -m pytest tests -q -p no:cacheprovider
```

CI（`.github/workflows/ci.yml`）在 Linux / macOS / Windows 上跑全量测试和安装包冒烟。测试数量随版本变化，不在这里写死；每次上线的实测结果记在 [audit/](audit/)。部分用例依赖可选的 MCP SDK、Git 2.38+ 等环境，缺失时跳过或给出提示。

## AI 记忆与接续文件

这个项目主要由 AI 编程助手迭代开发，下面这些文本是助手跨会话的记忆，移动、改名或删除前要先确认引用关系：

| 文件 | 作用 |
|---|---|
| [AGENTS.md](AGENTS.md) | 本仓库的开发、发布和安全约定，助手开工必读 |
| [docs/self-improvement/ralph-port-progress.md](docs/self-improvement/ralph-port-progress.md) | 接续记忆：长期有效的约定与边界 + 最近几轮记录，新记录追加在末尾 |
| [docs/self-improvement/progress-archive/](docs/self-improvement/progress-archive/) | 更早的进度记录，按阶段原样归档，需要时再查 |
| [STATUS.md](docs/self-improvement/STATUS.md)、[BACKLOG.md](docs/self-improvement/BACKLOG.md) | 自进化循环的接续基线、用户划定的边界和 SI 待办 |
| [docs/dead-ends.md](docs/dead-ends.md) 与 4 份 `verification-*.md` | 已知死路和替代做法；列在 `tmh/resources.py` 中，随工具安装到目标项目 |
| `docs/self-improvement/verification-*.md`、`evidence/` | 各轮验证记录和原始证据；`evidence/` 也被测试当作样例读取，不能直接移走 |

## 与原维护交付工作台（webuddy maintenance-harness）的关系

原工作台是带账户、审批、审计和发布控制的服务端产品，目前只能修改已有文件，只接了 Codex，单仓库上限约 5,000 个文件。tmh 是面向开发者的那一层，二者可以这样接起来：

- 原工作台调用 `tmh flows --json` / `tmh verify` 作为分析器和验证器；
- 交付记录中附上 `tmh report` 生成的报告，作为给客户的分析证据。

## 目录

```
tmh/            工具源码：知识图谱与 Wiki（graph.py、kb.py、context.py）、业务流抽取（flow.py）、
                报告（explorer.py）、运维工具适配器（integrations/）、MCP（mcp.py）、
                Webuddy CLI / MCP（workbench.py、workbench_mcp.py）
tmh/platform/   Webuddy 平台：服务端、页面、租户与团队、项目执行、候选、证据与签收
tmh/rules/      改造规则（信创等）
kb/             信创知识库
skills/ agents/ templates/   安装到目标项目的技能、子代理和 AGENTS.md / CLAUDE.md 区块
examples/       Java（Spring + MyBatis）与 .NET（MVC + WCF）样例
tests/          pytest 测试
scripts/ tools/ 部署、冒烟和实验脚本
docs/           功能说明、端到端记录；docs/self-improvement/ 为 AI 记忆与验证记录
audit/          历次生产发布与勘误记录
```

## 汇报材料

- `Webuddy-产品介绍（甲方版）.pptx`：给甲方和投资人的产品介绍；`src/build_deck_产品版.py` / `src/build_deck_模块版.py` 重新生成（python-pptx）
- `老项目运维提效-立项汇报.pptx`、`运维智能体-立项汇报（业务版）.pptx`、`老项目运维提效-工作拆解树（立项稿）.md`：立项材料
- `平台工作原理图.pptx`、`应用场景页-四个版本.pptx` 及对应预览图；`总体架构图-图片生成提示词*.md`
- `截图-新/`、`src/img/`：平台界面截图
- `PPT写作规则（去AI味）.md`：写作约定
- `重构实测/`：RealWorld 跨语言重写实测报告
