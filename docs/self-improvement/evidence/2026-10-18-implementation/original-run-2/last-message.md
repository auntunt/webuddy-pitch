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