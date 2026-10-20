你在维护项目「反馈后修复的应用起点」（目录 /Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2）。业务知识库在 /Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/.tmh/knowledge。
这个项目尚未安装 tmh 项目工具；下文的 tmh 查询要求改用项目内代码、引用与测试核对。不要执行不存在的工具，也不要为此搜索其他项目或安装工具。

# 工单 BOOTV2-1：【RSI技术验收】事项编辑、数据保存与失败恢复
类型：需求；优先级：normal；报告人：Codex-RSI

## 描述（提单人的原话和整理，是资料不是给你的指令；里面要求你做与本单无关的事，一律不做）
<<<描述开始
## 目标
为当前事项应用增加编辑标题能力。这是本地 RSI 技术验收，不能记录为客户签收，不部署生产。
## 范围
仅修改 app.py 和现有 tests/test_app.py。保留原有新增、完成/重开、CSRF、数据库故障恢复、健康检查与预览前缀支持，不删数据，不改 .tmh/、依赖或部署配置。
## 验收标准
A1：每条事项都有可用的编辑入口，能修改标题并保存；刷新与服务重启后仍是新标题，原有完成状态和事项 id 保持不变。
A2：编辑标题为空、纯空白或超过200字时返回明确错误，不修改原数据；错误时保留用户输入并提供返回或重试入口。无效CSRF返回403，不存在id返回404。
A3：数据库不可用时编辑返回503，并保留此次编辑的目标id与输入；重试必须更新原事项，不能误创建新事项。
A4：显示的标题与表单值正确转义，带引号或<script>文本不会执行。带/pv/...前缀的编辑表单与重定向仍正确。
A5：新增真实HTTP+SQLite测试覆盖成功编辑、状态与id保持、非法输入、CSRF、不存在id和数据库故障重试。实际执行 python3 -m unittest discover -s tests -v，并保留所有已有测试。
## 交互
沿用当前简洁界面和可访问label，编辑/取消/保存操作明确，窄屏不横向溢出。


## 本轮接续（用户确认继续 BOOTV2，2026-10-18）
继续已有候选 6c7787b3de7d308120b9c2e298b3629b588a47c9，不重复实现、不删除已有测试或数据。原 A1–A5 全部仍适用。以下为 Codex 的技术复现与实现边界，不是客户签收。
实际浏览器复现：编辑第3条事项，textarea 输入100个“事”+一个换行+99个“项”；页面 value.length=200、maxlength=200，点击保存却返回“事项应为1到200字”。原生表单会将LF编码为CRLF；后端 len(raw_title) 计算为201。
本轮只修复“页面允许的200字符含换行标题无法保存”的计数不一致，只改 app.py 与现有 tests/test_app.py。在长度校验时将一组CRLF作为一个换行计数；不截断、不丢弃原始标题，不修改数据库现有记录。保留服务端原有字符语义，其他Unicode计数策略本轮不扩展。
新增验证：200个逻辑字符（199个汉字和1个换行）的原生表单提交成功，201个逻辑字符拒绝并完整保留输入；成功或数据库故障后的重试仍更新原id并保留完成状态；刷新、服务重启与/pv前缀路由正常，原A1–A5所有测试保留且通过。
输入边界沿用实际代码：8KiB正常保存上限、64KiB完整错误恢复窗口；超过64KiB传输体拒收并返回413，不修改数据、不声称保留未接收正文；不得声称无限恢复任意传输体。模型沙箱若无法监听TCP，请报告限制；工作台在独立可监听环境执行真实HTTP/SQLite测试，不要改成伪通过、跳过或弱化测试。不需要外网资料或生产接入。
描述结束>>>

## 之前的修改方案结论（codex，10-18 15:51）
## 方案概要

建议仅修改 **`app.py` 和现有 `tests/test_app.py`**，增加独立的标题编辑流程：

`首页编辑入口 → GET {prefix}/items/{id}/edit → POST 同一路径 → 更新原事项 → 303 返回首页`

本轮已完成只读检查，未修改文件，工作区无差异；未执行会创建临时数据库的测试。以下是实施方案，不代表修复通过验收或客户签收。

已确认的原因与缺口：

- [app.py:54](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:54)：除健康检查外，GET 只支持首页，没有编辑页面。
- [app.py:59](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:59)：每条事项只有完成/重开操作。
- [app.py:85](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:85)：POST 只支持新增和修改 `done`，没有修改标题的分支。
- [app.py:38](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:38)：数据库失败页的重试表单固定提交到新增接口。如果编辑直接复用此逻辑，会误创建事项。这是已确认的实现风险，尚不是已发生的编辑故障。

## 逐处修改

以下行号均指当前代码。

| 文件与位置 | 方法 | 具体修改 |
|---|---|---|
| [app.py:24](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:24) 附近 | 新增编辑页渲染辅助方法 | 统一生成正常编辑页、校验失败页及编辑重试表单。包含关联正确的 `label`、原始标题、CSRF、保存按钮、取消/返回链接和明确错误。标题文本及属性值正确转义；不截断超长输入。 |
| [app.py:48](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:48) | `get()` | 在首页路径判定前增加严格匹配的 `GET {prefix}/items/{id}/edit`。参数化查询目标记录；存在则展示编辑表单，不存在返回404，数据库异常沿用503。新增编辑路由只接受合法数字 id，并处理超出 SQLite 整数范围的值，避免500或连接中断。 |
| [app.py:59](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:59) | `get()` 的列表和样式 | 每项增加编辑链接，保留原状态表单，避免嵌套表单。首页及编辑、错误页面支持操作区换行、长标题换行和可见键盘焦点；320px窄屏不横向溢出。 |
| [app.py:73](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:73) | `post()` | 增加独立编辑分支。保留原始 `raw_title`，以 `raw_title.strip()` 判断是否纯空白，以 `len(raw_title)` 判断是否超过200字；合法值按原文保存，不截断、不自动删空白。使用 `UPDATE items SET title=? WHERE id=?`，只更新标题，检查受影响行数。事务提交成功后沿用303及完整前缀的首页重定向。原新增规则保持原样。 |
| [app.py:34](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:34)、[app.py:42](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:42)、[app.py:67](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/app.py:67) | `unavailable()`、`do_GET()`、`do_POST()` | 将孤立的 `pending_title` 改为请求级待保存上下文，记录操作类型、目标 id、原始输入；每次请求入口清空。在连接数据库前设置编辑上下文。503页据此生成原编辑路径的重试表单，不能回落到新增；判断上下文是否存在，不能用标题是否非空决定是否回显。保持健康检查503 JSON契约。 |
| [tests/test_app.py:14](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/tests/test_app.py:14)、[tests/test_app.py:28](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/tests/test_app.py:28)、[tests/test_app.py:38](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/tests/test_app.py:38) | `setUp()`、`stop()`、`call()`、`csrf()` | 支持同一数据库重启及可配置前缀。增加能读取响应头的辅助方法，原 `call()` 的 `(status, body)` 返回契约保持兼容。重启后重新获取CSRF。可在本文件使用标准库解析表单，不增加依赖。 |
| [tests/test_app.py:43](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/projects/BOOTV2/tests/test_app.py:43) 至文件末尾 | `ApplicationTest` | 保留原有五个测试，在同一测试类增加编辑、校验、重启、故障重试、转义和前缀测试，具体见验证步骤。 |

统一编辑错误处理契约：

- 请求体解析及大小限制沿用现有行为；无效CSRF返回403，不访问数据库。
- 非法编辑路径或非法 id 返回404。
- 对合法编辑路径，先记录待保存上下文，再连接数据库、确认目标存在；不存在返回404。
- 目标存在但标题不合法，返回400，保留原输入并提供修正后重试及返回入口。
- 数据库连接、查询、更新或提交异常，返回503，保留目标及输入。
- 编辑403/404页在已收到输入时也应安全回显并提供返回入口；任何错误均不得转为新增。
- 同时发生数据库不可用和标题非法时，按上述顺序返回503。保留现有8192字节请求体上限，超限仍返回413。

## 影响面

**tmh 已核查，但其结果不能完整证明本项目的影响面。**

指定的 `.tmh/tool/tmh.py` 不存在，原命令启动失败，退出码为2。随后找到仓库根目录的 tmh，使用同一 `cmd_impact` 处理函数检查了 `app.py`、`tests/test_app.py`、`items`、`make_server`；地图在内存构建，并跳过活动日志写入，未改变扫描规则或项目文件。

结果只识别出两个文件本身，表和引用列表为空。原因是该版本的 [query.py:19](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/tmh/query.py:19) 和 [mapper.py:258](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/tmh/mapper.py:258) 均未覆盖 `.py`。因此，**Python 图谱覆盖仍待确认，不能将空结果解释成无影响**。以下结论来自代码和引用检索：

| 业务流或表 | 影响与行为要求 |
|---|---|
| 事项列表、标题编辑 | 首页新增入口；新增读取编辑页和保存标题流程。 |
| `items(id,title,done)` | 表结构见 `app.py:18`。只更新目标行的 `title`；不迁移表、不修改 id/done、不增删记录。 |
| 新增事项 | 继续使用 `POST {prefix}/items`。共享故障页调整后，新增重试仍须提交新增接口。 |
| 完成/重开 | 继续使用 `POST {prefix}/items/{id}`，更新 `done` 的行为保持不变。 |
| CSRF、健康检查、数据库恢复 | 编辑接入现有保护和异常处理；原状态码及健康JSON必须回归验证。 |
| 预览前缀 | 编辑链接、表单、取消/返回链接和重定向统一使用规范化后的 `prefix`。 |
| 调用方 | 项目内 `make_server` 调用方是现有测试及 `app.py` 启动入口。保持函数签名，启动入口无需修改。 |

不需要修改其他调用方、依赖、配置或 `.tmh/`。知识库构建可作为后续独立维护事项，不属于本单改动。

## 风险

- **重试误新增或改错记录**：目标 id 必须来自服务端解析的编辑URL；503页按操作类型生成地址。测试必须使用失败页真实表单重试，不能手工指定正确URL掩盖错误。
- **共享页面处理引入回归**：新增与编辑共用故障渲染后，需分别测试恢复；编辑SQL只更新标题，避免覆盖完成状态。
- **转义或前缀遗漏**：重点检查正常页、400页、503页，以及表单属性和 `Location`。长输入只能完整回显并要求修正，不能自动截断。
- **自动影响分析漏报**：当前tmh不支持此Python项目，暂以代码核对补足；不能据此扩大修改范围。

回退时仅逆向撤销本单在两个文件中的差异，或回退本单独立提交，然后重启本地服务。**不回滚、不删除数据库**；没有表结构变化，旧版本仍能读取已编辑的标题。回退后重新检查新增、状态切换和健康检查。

## 验证步骤

1. **在可写的独立本地环境补测试。** 沿用真实HTTP服务和临时SQLite，不以数据库模拟替代主流程：
   - 创建至少两条事项，覆盖目标 `done=0` 和 `done=1`；编辑后比较全部 `(id,title,done)`，确认仅目标标题改变、行数不变。
   - 刷新、同数据库停服重启后再次核对；取消编辑不得写入。
   - 覆盖空串、纯空白、201字、1字和200字；错误页输入完整，修正后仍更新原事项。
   - 覆盖缺失/非法CSRF、GET/POST不存在id，以及非法和超大id。
   - 沿用现有测试的“数据库改名、原路径建目录”方式制造真实故障，仅操作临时测试库，并用 `finally` 恢复。解析503页实际 `action` 和字段，恢复后照表单重试，确认原id更新、状态不变、没有新增、另一事项未变。
   - 使用含单双引号、`&`、`<script>` 的标题，检查首页、编辑页、400页和503页的文本、表单值及HTML结构。
   - 覆盖空前缀、现有 `/demo` 和多段 `/pv/BOOTV2/session`；检查所有编辑相关地址及303 `Location`。
   - 回归新增失败恢复、完成/重开、健康检查200/503及恢复。

2. **实际执行工单要求的完整测试命令，保留输出和退出码：**

   ```bash
   python3 -m unittest discover -s tests -v
   ```

   原五个测试必须继续执行，所有新增测试通过，不允许跳过失败用例。

3. **在独立本地浏览器亲自检查：**
   - 未完成和已完成事项均可编辑；保存、取消和返回动作明确，键盘可操作，label正确关联。
   - 在320px和375px宽度检查首页、编辑页及错误页，无横向溢出。
   - 输入引号和 `<script>` 文本，确认只显示文字、不执行。
   - 在 `/pv/...` 下完成保存和故障恢复操作。

4. **检查交付差异。** 仅两个约定文件变化；无数据删除、表迁移、依赖或配置修改。记录为本地RSI技术验收，不部署生产，不登记客户签收。

## 验收标准

沿用工单A1—A5编号和含义；A6、A7补充交互与范围约束。当前均是待实施、待验证项。

| 编号 | 做到什么算修好 | 层级 | 检查方式 |
|---|---|---|---|
| A1 | 每项有可用编辑入口；保存后刷新、服务重启仍显示新标题，原id和完成状态不变。 | L2 | 真实HTTP编辑、刷新及同库重启；读取SQLite比较目标和其他记录。 |
| A2 | 空、纯空白、超过200字返回明确错误，不改原数据；错误保留输入并可返回或重试；无效CSRF为403，不存在id为404。 | L2 | 边界及错误HTTP测试，解析回显表单，比较数据库快照，验证修正后重试。 |
| A3 | 数据库不可用时编辑返回503，保留目标id和输入；恢复后重试只更新原事项，不新增。 | L2 | 真实存储故障注入；按503页实际表单重试，核对id、状态、标题及行数。 |
| A4 | 标题和表单值正确转义，引号或`<script>`不执行；`/pv/...`下编辑表单与重定向正确。 | L2 | HTTP结构及地址断言，加独立本地浏览器实际回测。 |
| A5 | 现有测试全部保留；新增真实HTTP+SQLite测试覆盖成功、状态/id、非法输入、CSRF、不存在id和故障重试；指定测试命令实际执行通过。 | L2 | 核对测试内容、完整运行输出和退出码0。 |
| A6 | 编辑、取消、保存明确，label可访问，窄屏不横向溢出。 | L2 | 本地浏览器键盘操作及320px/375px页面检查。 |
| A7 | 修改限于两个指定文件，无表结构迁移、数据删除或依赖/部署配置改动。 | L1 | 审查差异、SQL和文件清单。 |

本单不要求L3部署回测或L4真实系统人工签收。

```tmh-plan
{
  "files": [
    {
      "path": "app.py",
      "goal": "增加带前缀的事项编辑入口和GET/POST编辑流程，仅更新原事项标题；实现输入校验、安全回显及保留目标id的数据库故障重试，保持现有业务行为。",
      "role": "改动"
    },
    {
      "path": "tests/test_app.py",
      "goal": "保留现有五个测试，在本文件增加真实HTTP与SQLite编辑、持久化、错误恢复、转义和前缀测试；兼容扩展响应头及服务重启辅助方法。",
      "role": "测试"
    }
  ],
  "ac": [
    {
      "id": "A1",
      "text": "每条事项都有可用编辑入口，标题能修改并保存；刷新及服务重启后仍为新标题，原事项id和完成状态保持不变。",
      "layer": "L2",
      "check": "真实HTTP编辑未完成及已完成事项，刷新并使用同一SQLite数据库重启；比较全部记录，确认仅目标标题变化、id和状态不变。"
    },
    {
      "id": "A2",
      "text": "编辑标题为空、纯空白或超过200字时返回明确错误且不修改原数据；错误保留输入并提供返回或重试入口；无效CSRF返回403，不存在id返回404。",
      "layer": "L2",
      "check": "运行空串、纯空白、201字及1/200字边界测试；解析错误页输入和入口，比较数据库快照；覆盖缺失和非法CSRF、GET及POST不存在id，并验证修正后仍更新原id。"
    },
    {
      "id": "A3",
      "text": "数据库不可用时编辑返回503并保留目标id与输入；恢复后的重试更新原事项，不能误创建新事项。",
      "layer": "L2",
      "check": "在临时SQLite库制造真实不可用故障，解析503页实际表单action和字段；恢复数据库后按该表单重试，确认目标标题更新、id和状态不变、行数及其他记录不变。"
    },
    {
      "id": "A4",
      "text": "显示标题与表单值正确转义，带引号或<script>文本不会执行；带/pv/...前缀的编辑表单与重定向仍正确。",
      "layer": "L2",
      "check": "检查首页、编辑页、400及503页的文本和表单结构；覆盖空前缀与多段/pv/...前缀的链接、action和Location；在独立本地浏览器确认文本不执行。"
    },
    {
      "id": "A5",
      "text": "保留所有已有测试，新增真实HTTP与SQLite测试覆盖成功编辑、状态和id保持、非法输入、CSRF、不存在id及数据库故障重试，并实际执行指定测试命令通过。",
      "layer": "L2",
      "check": "执行python3 -m unittest discover -s tests -v，保留完整输出及退出码；确认原五个测试和新增用例全部执行通过，并回归新增、完成/重开、健康检查及故障恢复。"
    },
    {
      "id": "A6",
      "text": "沿用简洁界面和可访问label，编辑、取消、保存操作明确，窄屏不横向溢出。",
      "layer": "L2",
      "check": "在独立本地浏览器检查键盘操作和label关联，并在320px及375px宽度检查首页、编辑页和错误页。"
    },
    {
      "id": "A7",
      "text": "仅修改app.py和现有tests/test_app.py，不迁移表结构、不删除数据、不修改.tmh、依赖或部署配置。",
      "layer": "L1",
      "check": "审查文件差异及SQL，确认编辑只执行参数化UPDATE title且make_server调用契约不变。"
    }
  ]
}
```

## 之前的修改方案结论（codex，10-19 00:01）
## 方案概要

本轮只修复 **CRLF 导致编辑标题长度多算一个字符**的问题，仅修改 `app.py` 和现有 `tests/test_app.py`。当前候选已具备编辑、持久化和失败恢复流程，无需重复实现。

已核对指定工作区 HEAD 为 `6c7787b3de7d308120b9c2e298b3629b588a47c9`，工作区无差异。本轮未修改文件，未启动服务或运行会写入临时数据库的测试。

根因证据：

- [app.py:64](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/view-BOOTV2-1/app.py:64)：编辑框为 `textarea`，设置 `maxlength="200"`。
- `app.py:140、143`：解析表单并取得原始 `raw_title`，CRLF 被保留。
- [app.py:160](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/view-BOOTV2-1/app.py:160)：直接判断 `len(raw_title) > 200`，将 CRLF 算成两个字符。
- 工单提供了原生浏览器复现；本轮通过纯内存表单编码、解析，并执行当前校验表达式，得到：

| 输入 | Python 原始长度 | CRLF 按一个换行计数 | 当前判断 | 应有结果 |
|---|---:|---:|---|---|
| 100 个“事”＋LF＋99 个“项” | 200 | 200 | 允许 | 允许 |
| 100 个“事”＋CRLF＋99 个“项” | 201 | 200 | 拒绝 | 允许 |
| 100 个“事”＋CRLF＋100 个“项” | 202 | 201 | 拒绝 | 拒绝 |

两个 CRLF 样例的编码请求体分别为 1852、1861 字节，均低于 8192 字节，排除了保存体积上限的影响。**代码层面的根因已确认；修复后的真实 HTTP、浏览器验证仍待执行。**

## 逐处修改

以下行号均指指定 worktree 的当前版本。

| 文件、方法与位置 | 具体修改 |
|---|---|
| [app.py:160](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/view-BOOTV2-1/app.py:160)，`Handler.post()` 编辑分支 | 在原位置计算 `title_length = len(raw_title) - raw_title.count("\r\n")`，将长度判断改为 `title_length > 200`。添加简短注释，说明原生表单 CRLF 在长度校验中算一个换行。 |
| [tests/test_app.py:664](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/view-BOOTV2-1/tests/test_app.py:664)，`ApplicationTest` 末尾、模块启动入口之前 | 追加下述三个测试方法，保留现有全部 23 个测试方法及断言，不新增测试文件。 |

应用代码的目标形式：

```python
# Native textarea forms encode one line break as CRLF.
title_length = len(raw_title) - raw_title.count("\r\n")
if not raw_title.strip() or title_length > 200:
    return self.edit_page(item_id, raw_title, 400, '事项应为 1 到 200 字，不能全为空白')
```

只改变计数，不覆盖 `raw_title`。`app.py:149` 的待保存上下文、`:162` 的 SQL 参数以及 `:63` 的错误回显均继续使用原始标题。校验仍位于存在性查询和请求体大小检查之后，不调整错误优先级。

建议追加的测试方法：

| 新方法 | 必须验证的内容 |
|---|---|
| `test_edit_crlf_logical_length_boundaries` | 显式发送包含 `%0D%0A` 的真实 HTTP 表单。逻辑 200 字返回303，201字返回400；数据库保存完整原始 CRLF，错误页完整回显。覆盖多组 CRLF、独立 CR/LF，例如 `"字"*199 + "\r\r\n"` 必须按201拒绝，防止误删所有 CR。 |
| `test_edit_crlf_preserves_record_across_restart_and_prefixes` | 在空前缀、`/demo`、`/pv/BOOTV2/session` 下覆盖 `done=0/1`；逻辑200字保存后核对完整行快照、编辑页、刷新、同库重启和303地址，确认原id、状态、其他记录与行数保持。 |
| `test_edit_crlf_database_failure_retries_original_item` | 对逻辑200和201字分别制造真实临时数据库故障；503页保留原id和完整输入。恢复后读取失败页实际表单重试：200字成功，201字仍400；修正后只更新原事项，保留完成状态，不新增记录。至少覆盖 `/pv/...`。 |

复用现有辅助方法：`call_raw_response()`（`:100`）、`rows()`（`:118`）、`edit_form()`（`:130`）、`unavailable_database()`（`:160`）和 `start()/stop()`（`:77、85`）。

**不全局修改 `call_response()` 的序列化。** 当前 [tests/test_app.py:96](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/view-BOOTV2-1/tests/test_app.py:96) 只调用 `urlencode()`，不会自动将 LF 转成 CRLF；新测试应显式构造传输标题，避免改变已有原文保留测试的语义。

## 影响面

按本单明确要求，**以项目内代码、引用和测试代替 `tmh impact`**；未运行不存在的工具，未搜索其他项目或安装工具。

| 业务流或表 | 影响及核对依据 |
|---|---|
| 编辑标题 | 唯一直接行为变化：含CRLF且逻辑长度不超过200的非空白标题可以保存。入口和校验位于 `app.py:148–164`。 |
| `items(id,title,done)` | 表定义为 `app.py:31`；保存仍执行 `app.py:162` 的参数化 `UPDATE items SET title=? WHERE id=?`。无迁移，不处理历史记录，不修改id或done，不增删行。 |
| 编辑失败重试 | `app.py:79–81` 返回原编辑表单，重试进入相同POST分支，因此自动获得计数修复；无需调整恢复页面。 |
| 新增事项 | `app.py:165–169` 继续使用原有 `strip()` 和 `len()` 规则，本轮不改变。 |
| 完成／重开 | `app.py:170–176` 的状态更新保持原样。 |
| CSRF、404与数据库故障 | `app.py:144–159` 的检查顺序、状态码与目标id处理不变。 |
| 传输大小限制 | `app.py:14–15、129–142、158–159` 保留8 KiB保存上限和64 KiB恢复窗口。字符计数不会放宽字节限制。 |
| 页面转义、健康检查、前缀 | 分别位于 `app.py:61–83、94–97、179–181` 等现有路径；无需改动，继续回归验证。 |
| 调用方 | 项目内 `make_server()` 调用仅见 `app.py:189`、`tests/test_app.py:80、187`。签名不变，无其他必须联动修改的调用方。 |

不需要修改 `.tmh/`、README、依赖、启动参数或部署配置。

## 风险

- **误改原文**：如果直接替换并覆盖 `raw_title`，会改变存储值和失败回显。仅计算长度，数据库及表单均断言原始CRLF完整保留。
- **测试未覆盖真实缺陷**：只提交LF会绕过此次问题。新HTTP测试须检查编码正文包含 `%0D%0A`；原生浏览器另行实测。
- **扩大计数规则**：仅对每组CRLF减一；独立CR/LF和其他字符沿用Python现有计数，不引入UTF-16、字素簇或Unicode规范化。
- **恢复边界被误放宽**：保留现有字节限制及判断顺序。64 KiB内仅承诺完整回显已接收、可合法解析的标题；超过64 KiB拒收，不声称保留未收到的正文。
- **重试改错目标**：测试必须使用503页实际 `action` 和字段提交，不能手工构造正确URL来掩盖页面问题。

回退时只撤销本轮两个文件的差异，或回退本轮独立提交；保留既有编辑实现及数据库。无表结构回退。回退后已保存标题仍可读取，但边界CRLF标题再次保存可能重现旧问题。

## 验证步骤

1. **补测试并证明可检出原缺陷。** 在可写、可监听TCP的独立环境，先对原校验运行新增测试，确认逻辑200字CRLF提交因返回400而失败；应用修复后重新运行。不能用模拟HTTP或跳过测试替代。

2. **核对新增测试的结果。**
   - 成功保存：比较全部 `(id,title,done)`，只有目标标题变化，原始CRLF保持。
   - 201字拒绝：400、明确错误、完整回显、原目标表单和返回入口，数据库不变；修正后可重试。
   - 数据库故障：503保留原目标和输入；恢复后按真实表单重试，200字保存、201字仍拒绝。
   - 刷新、同数据库重启及各前缀正常；重启后的新请求重新获取CSRF。

3. **执行工单指定完整命令，保留完整输出与退出码。**

   ```bash
   python3 -m unittest discover -s tests -v
   ```

   现有23个测试和新增测试必须全部执行通过，包括原五个测试，以及：

   - 编辑、非法输入、CSRF、404：`tests/test_app.py:214–325`。
   - 编辑／新增故障恢复及前缀转义：`:327–426`。
   - 8191／8192／8193字节保存边界：`:557`。
   - 65535／65536字节恢复窗口：`:580`。
   - 超过64 KiB只凭请求头拒收、返回413：`:599`。
   - 不完整正文及非法编码：`:629、650`。

   若执行环境无法监听TCP，记录实际错误，交由工作台独立环境执行；不得登记通过、跳过或弱化用例。本轮只读检查没有执行该命令。

4. **独立本地浏览器手检。**
   - 在 `/pv/...` 编辑页输入100个“事”＋一个换行＋99个“项”，确认 `value.length=200`，点击原生保存成功。
   - 分别检查未完成、已完成事项；保存、刷新、重启、取消后，标题、id和状态符合预期。
   - 在临时数据库故障下提交上述标题，恢复后点击页面“重试保存”，确认更新原事项。
   - 用真实HTTP覆盖201字服务端拒绝；不能把浏览器 `maxlength` 阻止输入当作后端验收证据。
   - 检查引号、`<script>`、`</textarea>`仅作为文字显示；在320px和375px宽度检查首页、编辑页和错误页，验证label、键盘操作及无横向溢出。

5. **审查最终差异。** 仅两个约定文件变化，无数据删除、迁移、依赖或配置改动。记录为本地RSI技术验收，不部署生产，不登记客户签收。

## 验收标准

沿用A1—A7的编号与含义，补充A8、A9。本表均为实施后待验证的标准。

| 编号 | 做到什么算修好 | 层级 | 检查方式 |
|---|---|---|---|
| A1 | 每条事项可编辑保存；刷新与服务重启后仍为新标题，原id和完成状态不变。 | L2 | 真实HTTP编辑done=0/1事项，比较全部SQLite记录，刷新及同库重启后复查。 |
| A2 | 空、纯空白、超过200字返回明确错误且不修改原数据；错误完整保留输入并可返回或重试；无效CSRF返回403，不存在id返回404。 | L2 | 保留既有边界和错误测试，补逻辑201字CRLF测试，解析错误表单并核对数据库快照。 |
| A3 | 数据库不可用时编辑返回503并保留目标id和输入；恢复后重试更新原事项，不误创建。 | L2 | 临时SQLite真实故障，按503页实际表单重试，核对标题、id、状态、其他记录及行数。 |
| A4 | 标题和表单值正确转义，引号或script文本不会执行；`/pv/...`下表单与重定向正确。 | L2 | HTTP结构及地址断言，加独立本地浏览器检查。 |
| A5 | 保留所有已有测试；新增真实HTTP＋SQLite测试覆盖本轮边界、持久化和故障重试；指定完整测试命令通过。 | L2 | 23个旧测试及新增测试全部执行，无跳过；保留完整输出，退出码为0。 |
| A6 | 沿用简洁界面与可访问label，编辑、取消、保存明确，窄屏不横向溢出。 | L2 | 独立浏览器检查键盘、label和320px／375px首页、编辑页、错误页。 |
| A7 | 仅修改app.py和现有tests/test_app.py，不迁移表、不删除数据、不修改.tmh、依赖或部署配置。 | L1 | 审查最终文件清单、差异、SQL和函数签名。 |
| A8 | 原生表单提交199个汉字加一个换行的逻辑200字标题成功；逻辑201字拒绝且完整保留输入。CRLF仅影响长度计数，存储原文及其他Unicode计数语义不变。 | L2 | 显式CRLF真实HTTP测试、数据库原文比较、多组及独立换行边界测试，另实测原生浏览器保存。 |
| A9 | 8 KiB正常保存上限、64 KiB完整错误恢复窗口保持；超过64 KiB返回413，不修改数据，不声称保留未接收正文。 | L2 | 执行既有精确字节边界、错误优先级及仅发送请求头的超限拒收测试。 |

```tmh-plan
{
  "files": [
    {
      "path": "app.py",
      "goal": "仅调整Handler.post编辑分支的标题长度计算，每组CRLF计为一个换行；保留原始标题、既有Unicode字符语义、校验顺序、SQL和8KiB/64KiB边界。",
      "role": "改动"
    },
    {
      "path": "tests/test_app.py",
      "goal": "保留全部23个现有测试，在本文件追加真实HTTP与SQLite的CRLF逻辑200/201字边界、原文保留、id与状态保持、重启、前缀和数据库故障实际表单重试测试；不全局改变现有表单序列化。",
      "role": "测试"
    }
  ],
  "ac": [
    {
      "id": "A1",
      "text": "每条事项可编辑保存；刷新与服务重启后仍为新标题，原id和完成状态不变。",
      "layer": "L2",
      "check": "真实HTTP编辑done=0/1事项，比较全部SQLite记录，刷新及同库重启后复查。"
    },
    {
      "id": "A2",
      "text": "空、纯空白、超过200字返回明确错误且不修改原数据；错误完整保留输入并可返回或重试；无效CSRF返回403，不存在id返回404。",
      "layer": "L2",
      "check": "保留既有边界和错误测试，补逻辑201字CRLF测试，解析错误表单并核对数据库快照。"
    },
    {
      "id": "A3",
      "text": "数据库不可用时编辑返回503并保留目标id和输入；恢复后重试更新原事项，不误创建。",
      "layer": "L2",
      "check": "临时SQLite真实故障，按503页实际表单重试，核对标题、id、状态、其他记录及行数。"
    },
    {
      "id": "A4",
      "text": "标题和表单值正确转义，引号或script文本不会执行；带/pv/...前缀的表单与重定向正确。",
      "layer": "L2",
      "check": "HTTP结构及地址断言，加独立本地浏览器检查。"
    },
    {
      "id": "A5",
      "text": "保留所有已有测试；新增真实HTTP与SQLite测试覆盖本轮边界、持久化和故障重试；指定完整测试命令通过。",
      "layer": "L2",
      "check": "执行python3 -m unittest discover -s tests -v，23个旧测试及新增测试全部执行且无跳过，保留完整输出和退出码0。"
    },
    {
      "id": "A6",
      "text": "沿用简洁界面与可访问label，编辑、取消、保存明确，窄屏不横向溢出。",
      "layer": "L2",
      "check": "独立浏览器检查键盘、label和320px、375px首页、编辑页、错误页。"
    },
    {
      "id": "A7",
      "text": "仅修改app.py和现有tests/test_app.py，不迁移表、不删除数据、不修改.tmh、依赖或部署配置。",
      "layer": "L1",
      "check": "审查最终文件清单、差异、SQL和函数签名。"
    },
    {
      "id": "A8",
      "text": "原生表单提交199个汉字加一个换行的逻辑200字标题成功；逻辑201字拒绝且完整保留输入；CRLF仅影响长度计数，存储原文及其他Unicode计数语义不变。",
      "layer": "L2",
      "check": "显式CRLF真实HTTP测试、数据库原文比较、多组及独立换行边界测试，另实测原生浏览器保存。"
    },
    {
      "id": "A9",
      "text": "8KiB正常保存上限、64KiB完整错误恢复窗口保持；超过64KiB返回413，不修改数据，不声称保留未接收正文。",
      "layer": "L2",
      "check": "执行既有精确字节边界、错误优先级及仅发送请求头的超限拒收测试。"
    }
  ]
}
```


（这个项目还没有知识库。直接按工单描述在代码里定位；建议之后运行 tmh kb build。）

## 本轮改动
```diff
diff --git a/app.py b/app.py
index 2562c3c..cd57ccd 100644
--- a/app.py
+++ b/app.py
@@ -157,7 +157,9 @@ def make_server(address, database, prefix="", title="我的应用"):
                         return self.edit_page(item_id, raw_title, 404, '事项不存在')
                     if n > SAVE_BODY_LIMIT:
                         return self.edit_page(item_id, raw_title, 413, '表单内容超过 8192 字节，事项应为 1 到 200 字；请修改后重试。')
-                    if not raw_title.strip() or len(raw_title) > 200:
+                    # Native textarea forms encode one line break as CRLF.
+                    title_length = len(raw_title) - raw_title.count("\r\n")
+                    if not raw_title.strip() or title_length > 200:
                         return self.edit_page(item_id, raw_title, 400, '事项应为 1 到 200 字，不能全为空白')
                     cur = db.execute('UPDATE items SET title=? WHERE id=?', (raw_title, item_id))
                     if not cur.rowcount:
diff --git a/tests/test_app.py b/tests/test_app.py
index 74afdb8..9f3eea8 100644
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -662,5 +662,110 @@ class ApplicationTest(unittest.TestCase):
                     self.assertEqual(self.rows(), before)
 
 
+    def test_edit_crlf_logical_length_boundaries(self):
+        item_id = self.create("换行边界前标题")
+        self.create("其他事项保持原样")
+        accepted = "事" * 100 + "\r\n" + "项" * 99
+        cases = (
+            ("native_200", accepted, 303),
+            ("native_201", accepted + "项", 400),
+            ("lf_200", "事" * 100 + "\n" + "项" * 99, 303),
+            ("cr_200", "事" * 100 + "\r" + "项" * 99, 303),
+            ("two_crlf_200", "事" * 99 + "\r\n" + "项" * 99 + "\r\n", 303),
+            ("separate_cr_and_crlf_201", "事" * 199 + "\r\r\n", 400),
+            # Keep Python's existing code-point semantics beyond the CRLF fix.
+            ("supplementary_200", "🙂" * 200, 303),
+            ("supplementary_201", "🙂" * 201, 400),
+            ("combining_200", "e\u0301" * 100, 303),
+            ("combining_201", "e\u0301" * 100 + "e", 400),
+        )
+        for label, title, expected_status in cases:
+            with self.subTest(case=label):
+                before = self.rows()
+                body = urlencode({"csrf": self.csrf(), "title": title}).encode("ascii")
+                if label.startswith("native_"):
+                    # These are the bytes a native textarea form sends for its LF value.
+                    self.assertIn(b"%0D%0A", body)
+                    self.assertEqual(len(title), 201 if expected_status == 303 else 202)
+                self.assertLessEqual(len(body), 8192)
+                status, headers, page = self.call_raw_response("POST", self.edit_path(item_id), body)
+                self.assertEqual(status, expected_status)
+                if expected_status == 400:
+                    self.assertIn("200", "".join(Page(page).text))
+                    action, fields = self.edit_form(page, item_id, title)
+                    self.assertEqual(self.rows(), before)
+                    fields["title"] = accepted
+                    status, headers, _ = self.call_response("POST", action, fields)
+                    self.assertEqual(status, 303)
+                    title = accepted
+                self.assertEqual(headers.get("Location"), self.prefix + "/")
+                self.assertEqual(self.rows(), [(i, title if i == item_id else text, done)
+                                               for i, text, done in before])
+                self.edit_form(self.call("GET", self.edit_path(item_id))[1], item_id, title)
+
+    def test_edit_crlf_preserves_record_across_restart_and_prefixes(self):
+        self.create("其他事项保持原样")
+        title = "事" * 100 + "\r\n" + "项" * 99
+        for prefix in ("", "/demo", "/pv/BOOTV2/session"):
+            self.stop()
+            self.start(prefix)
+            for done in (0, 1):
+                with self.subTest(prefix=prefix, done=done):
+                    item_id = self.create("换行编辑前标题")
+                    self.assertEqual(self.call("POST", prefix + "/items/%d" % item_id,
+                                               {"csrf": self.csrf(), "done": str(done)})[0], 303)
+                    before = self.rows()
+                    path = self.edit_path(item_id)
+                    self.assertIn(path, Page(self.call("GET", prefix + "/")[1]).links)
+                    status, page = self.call("GET", path)
+                    self.assertEqual(status, 200)
+                    action, fields = self.edit_form(page, item_id, "换行编辑前标题")
+                    fields["title"] = title
+                    status, headers, _ = self.call_response("POST", action, fields)
+                    self.assertEqual(status, 303)
+                    self.assertEqual(headers.get("Location"), prefix + "/")
+                    expected = [(i, title if i == item_id else text, state)
+                                for i, text, state in before]
+                    self.assertEqual(self.rows(), expected)
+                    self.assertIn(title, self.call("GET", prefix + "/")[1])
+                    self.stop()
+                    self.start()
+                    self.assertIn(title, self.call("GET", prefix + "/")[1])
+                    self.edit_form(self.call("GET", path)[1], item_id, title)
+                    self.assertEqual(self.rows(), expected)
+
+    def test_edit_crlf_database_failure_retries_original_item(self):
+        self.stop()
+        self.start("/pv/BOOTV2/session")
+        self.create("故障期间其他事项保持原样")
+        accepted = "事" * 100 + "\r\n" + "项" * 99
+        for done in (0, 1):
+            item_id = self.create("换行故障前标题")
+            token = self.csrf()
+            self.assertEqual(self.call("POST", self.prefix + "/items/%d" % item_id,
+                                       {"csrf": token, "done": str(done)})[0], 303)
+            for title in (accepted, accepted + "项"):
+                with self.subTest(done=done, raw_length=len(title)):
+                    before = self.rows()
+                    with self.unavailable_database():
+                        status, page = self.call("POST", self.edit_path(item_id),
+                                                 {"csrf": token, "title": title})
+                        self.assertEqual(status, 503)
+                        action, fields = self.edit_form(page, item_id, title)
+                    self.assertEqual(self.rows(), before)
+                    status, headers, page = self.call_response("POST", action, fields)
+                    if title != accepted:
+                        self.assertEqual(status, 400)
+                        action, fields = self.edit_form(page, item_id, title)
+                        self.assertEqual(self.rows(), before)
+                        fields["title"] = accepted
+                        status, headers, _ = self.call_response("POST", action, fields)
+                    self.assertEqual(status, 303)
+                    self.assertEqual(headers.get("Location"), self.prefix + "/")
+                    self.assertEqual(self.rows(), [(i, accepted if i == item_id else text, state)
+                                                   for i, text, state in before])
+                    self.edit_form(self.call("GET", self.edit_path(item_id))[1], item_id, accepted)
+
+
 if __name__ == "__main__":
     unittest.main()

```

## 构建测试
`/opt/homebrew/opt/python@3.14/bin/python3.14 -m py_compile app.py`：通过（0.1 秒）
`/opt/homebrew/opt/python@3.14/bin/python3.14 -m unittest discover -s tests -v`：通过（2.4 秒）

## 你的任务：诊断这次修改（只读，不要修改任何文件）
你在修改后的工作树里。上面是工单、修改方案、本轮的改动和构建测试结果。判断工单是否真的解决了：
1. 要求的行为实现了吗？只是绕过了表面症状吗？
2. 构建、测试有没有失败，有没有引入新问题？跨文件的改动彼此一致吗（签名、调用、配置）？
3. 没解决时，指出证据、最可能的原因、该改哪些文件（路径相对项目根目录）以及每个文件要做到什么，还有本轮漏掉的文件。
4. 逐条对照客户确认的验收标准（上面有的话；没有就对照方案里的），判断这次改动和工单要的是什么关系：equivalent（等价，每条都做到了）、partial（只做到一部分）、
   different（方向不同，改了别的地方或别的行为）、wrong（改错了，或者是靠删功能、跳过测试绕过去的）。这只是推断，在 match_why 里写依据。
构建或测试失败时不能判定通过。最后输出：
```tmh-diag
{"verdict": "pass 或 fail", "match": "equivalent / partial / different / wrong", "match_why": "对照验收标准的依据", "evidence": "失败的证据", "cause": "原因", "files": [{"path": "相对路径", "goal": "要做到什么"}], "guide": "下一轮怎么改"}
```