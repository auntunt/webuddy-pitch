# tmh：传统 toB 软件项目维护 harness

装在 Codex / Claude Code 上的一套“老项目维护工作台”，可以接 DeepSeek、Kimi、GLM、Qwen 等国产模型。适用对象是国内 toB 软件公司长期维护的 Java / .NET 业务系统，比如 OA、ERP、CRM、财务和政务审批。

这类项目的维护难点几乎都一样：

- 写代码的人已经离开，文档早就过期了；
- 一个按钮背后到底发生了什么，没有人说得清；
- 改了这里，别处坏了。

tmh 的做法和资深工程师接手项目一样：**先对整个项目做一次统一分析，把理解沉淀成项目知识库**（知识图谱 + Wiki），之后每个任务先查知识库、只读相关代码，改完再增量更新知识库。这样结论有据可查，也不用每次都通读项目、重复花 token。改代码时先弄清业务流，改完由独立验证把关，整个分析过程都留有记录，可以直接拿给开发和业务方看。

## 能做什么

| 场景 | 产出 |
|---|---|
| **运维工单平台** | `tmh serve` 启动网页平台，和 Jira、禅道同级：工单列表与看板、业务全景、知识库，内置 Claude Code 和 Codex。工单直接连着知识库里的业务流和表，点一下让智能体分析定位、出方案或在独立工作树里改代码，改动经人审阅后采纳。详见 [docs/platform.md](docs/platform.md) |
| **接手项目，统一分析** | 项目知识库：工具从代码抽出知识图谱（入口、调用、SQL、表、状态机、模块依赖），自动划分业务域；智能体按任务队列自底向上写 业务流 → 业务对象 → 模块 → 业务域 → 系统总览，每页带证据、经人确认。详见 [docs/knowledge-base.md](docs/knowledge-base.md) |
| **日常维护** | `tmh context "<需求>"` 取出相关的知识页、业务流、表和代码位置，模型先看它再动手；代码改动后只有受影响的知识页被标为过期并排进修订队列 |
| **接手项目、讲解系统** | 业务流报告：每个入口 → 业务逻辑 → 数据访问 → 表的调用链、状态流转图、业务 × 表矩阵、代码里的校验规则。左边是工具抽取的事实（带文件:行号），右边是用业务语言写的说明（需要人确认） |
| **在老项目上实现新需求** | 变更契约（要改变什么、必须保持什么、验收方式、受影响的业务流）→ 特征测试 → 最小改动 → 独立验证，最后按改动行算出实际触及了哪些业务流 |
| **接团队的运维工具** | Jira、禅道、GitLab、Jenkins、SonarQube、Confluence、钉钉/飞书/企业微信，以及用配置或插件接的任何工具。工单 → 相关业务流和代码 → 任务契约；构建失败 → 出错代码 → 业务流；Sonar 问题按业务流分组。智能体通过 MCP 直接调用。详见 [docs/integrations.md](docs/integrations.md) |
| **改造升级**（信创、.NET Framework → .NET 8、JDK 升级） | 规则扫描、分波次方案、工作项台账；信创是其中的一个场景包 |

所有分析过程都会进入报告的“分析过程”页，包括智能体每一步读了什么、执行了什么、改了什么，它记下的发现、决定和疑问，以及变更契约和验证结果。

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
- **离线可用**：只依赖 Python 3.8+ 标准库。安装时工具会复制到目标仓库的 `.tmh/tool/`，内网和国产服务器上都能跑。

## 快速开始

```sh
# 安装到目标项目：插入 AGENTS.md/CLAUDE.md 区块，不覆盖原有内容；同时装好 Codex 和 Claude 的技能、子代理、钩子
python3 /path/to/tob-maintenance-harness/tmh.py install --repo /path/to/legacy-project --git-hook

cd /path/to/legacy-project
X="python3 .tmh/tool/tmh.py"
$X kb build && $X baseline --with-tests   # 知识图谱 + Wiki 骨架，记录基线
$X report --open                          # 生成并打开可视化报告
codex                                # 或 claude
```

进入智能体后可以直接说：

- “接手这个项目，做全项目分析，建立知识库”（`legacy-onboard`）
- “梳理这个系统的业务流，出一份报告”（`business-flow`）
- “请假列表要能按审批状态筛选”（`legacy-feature`）
- “做一次信创评估，目标达梦 + 麒麟 + 鲲鹏”（`xinchuang-assess`），这一项需要先运行 `tmh init --target-db dm8 ...`

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
| `baseline [--with-tests]` / `verify [--no-tests]` | 基线与独立验证闸门 |
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

## 已验证与未验证

已验证：

- 本仓库 `tests/` 中的 65 个用例在 Python 3.8 和 3.13 下全部通过，覆盖：
  - 知识库：图谱与业务域划分、按文件缓存、页面校验、代码改动只让受影响页面过期、自底向上的任务队列与并行领取、业务域手工调整的保留、按需检索、报告知识库页签
  - 业务流抽取（Spring + MyBatis、ASP.NET MVC + ADO.NET、Go：gin + GORM）
  - 状态机推导、改动行到业务流的映射
  - 报告渲染
  - Codex 风格的 `apply_patch` 和 shell 钩子拦截、工具调用记录
  - 安装幂等
  - 运维平台：工单生命周期、接口与访问保护、工单关联业务流、用替身智能体跑通“分析 → 在独立工作树修改 → 采纳提交到分支”，且不碰用户工作目录
  - 运维工具接入（用模拟 HTTP 服务器）：每个内置适配器、凭据只走环境变量、演练与确认、插件、通用适配器、构建失败定位、工单转契约、MCP 服务
- Claude Code 2.1 中做过两次端到端运行：
  - 加载技能、实现一个新需求的完整流程（`docs/e2e-run.md`）
  - 用 `business-flow` 技能梳理业务流并生成报告（`docs/e2e-business-flow.md`）
  - 通过 MCP 调用 tmh 的运维工具（模拟的 Jira 和 Jenkins）：从工单 OA-7 和一次失败构建定位到同一条业务流，5 轮，$0.06，见 `docs/e2e-integrations.md`
  - 全项目分析（3 个 kb-writer 子代理并行，21 页，约 3.5 分钟，$1.39），以及改一个方法后的增量维护（只修订受影响的 4 个页面，56 秒，$0.27），见 `docs/e2e-knowledge-base.md`，产出的知识库在 `docs/e2e-knowledge-base/`

未验证：

- **平台里真实调用 Claude Code / Codex**：命令行参数按两者文档拼装，测试用的是替身智能体，首次在本机使用请先在一张工单上试“分析定位”。
- **Codex 下的实际运行**：钩子按 Codex 文档的格式生成，但还没有在 Codex 里实际跑过。
- **真实运维工具**：还没有连过真实的 Jira、Jenkins、禅道等实例，接口是按各家文档写的，首次接入请先跑 `tmh int test`。
- **国产模型的效果**：各家模型在这套流程下的表现还没有测过。
- **大项目性能**：合成的 9.4 万行 Java 项目（1,500 个接口）首次构建约 11 秒，无改动重建约 8 秒；几十万行真实项目还没测。
- **真实大项目上的抽取质量**：几十万行的真实项目上，抽取覆盖率和误差还不清楚。静态分析看不到这些：
  - 反射和动态 SQL
  - 配置驱动的路由
  - 存储过程的内部逻辑
  - JSP/前端里的业务规则

  报告里“未能解析的调用”一栏会把看不到的部分列出来。

## 与原维护交付工作台（webuddy maintenance-harness）的关系

原工作台是带账户、审批、审计和发布控制的服务端产品，目前只能修改已有文件，只接了 Codex，单仓库上限约 5,000 个文件。tmh 是面向开发者的那一层，二者可以这样接起来：

- 原工作台调用 `tmh flows --json` / `tmh verify` 作为分析器和验证器；
- 交付记录中附上 `tmh report` 生成的报告，作为给客户的分析证据。

## 目录

```
tmh/            工具源码（graph.py 知识图谱，domains.py 业务域，kb.py Wiki 与任务队列，context.py 检索，
                flow.py 业务流抽取，codeindex.py 代码索引，parsecache.py 解析缓存，explorer.py 业务全景报告，buildinfo.py 项目构建分析，webreport.py 旧版报告，
                integrations/ 运维工具适配器与知识库关联，opscli.py 相关命令，mcp.py MCP 服务）
tmh/rules/      改造规则（信创等）
kb/             信创知识库
skills/         技能（安装到 .agents/skills 与 .claude/skills）
agents/         子代理（安装为 .claude/agents/*.md 与 .codex/agents/*.toml）
templates/      AGENTS.md / CLAUDE.md 区块
examples/       Java（Spring + MyBatis：请假、报销、用户三个业务域）与 .NET（MVC + WCF）样例
tests/          python3 -m unittest discover -s tests
docs/           端到端运行记录与样例报告
```
