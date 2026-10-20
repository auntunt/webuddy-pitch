# Python 路径映射独立复核

2026-10-19，审查者为独立子代理。范围限定为 Python/http.server 方法级静态关系、候选版本绑定和入口记录；没有操作生产、8792、真实模型、原 BOOTV2 数据或客户签收。

本次审查未发现尚未修复的范围内阻塞。最终亲自执行 `python3 -m unittest tests.test_python_pathmap_independent tests.test_python_pathmap_api -v`，18 项独立测试与 6 项真实 HTTP/API 测试全部通过，共 24 项。命令、完整日志和被审源码 SHA-256 分别保存在 `independent-final-no-main-graph.log`、`independent-source-receipt-final.json`。此前 23 项通过日志及当时的源码回执仍保留，不覆盖历史证据。这些测试验证静态证据和交互合同，不计为客户验收或模型修对率。

## 已复现并修复的缺陷

| 缺陷 | 修复后的检查 | 原始失败证据 |
| --- | --- | --- |
| 同文件可达函数的新增行，掩盖不可达函数中的纯删除 | 新旧两侧逐行绑定内层函数；旧行核对旧 Git blob，不能借文件中别处新增行覆盖 | `independent-expanded-red.log` |
| 已采纳的短提交号被同名分支解析成另一个提交 | Git 对象前缀需唯一且类型正确，再读取完整对象；同名 ref 不改变来源 | `independent-expanded-red.log` |
| 用户取消 POST 仅保留 GET 后，旧技术入口仍使路径检查通过 | 当前 `code_path.flows` 为技术关联的权威集合；保留既有人工确认，但不借它覆盖这次技术选择 | `independent-selection-red.log` |

此前的 `independent-red.log` 是模块尚未实现时的合同红灯（12 项导入失败），不计作 12 个产品缺陷。`independent-first-implementation.log` 是初版 12 项全绿记录；其后补充负例才发现上述真实缺陷。

## 独立核验边界

- 已注册的 BaseHTTPRequestHandler 的 HTTP dispatcher 可关联唯一静态函数；同文件未调用函数、外层工厂包含的未调用嵌套函数、动态 getattr、注册前方法替换、未知装饰器都不能借同名或父级范围通过。
- 未注册类不推定入口；产品文件解析失败可见并阻止完整路径通过；只有测试文件改动不算产品路径。
- 候选读取来自已采纳 Git 对象。脏工作目录内容、同名完整 SHA 分支、同名短 SHA 分支都不能改变候选；缺失或错误候选不能匹配原差异。
- 所有产品改动位置需被选中入口覆盖。部分改动、混合产品配置改动、未选择入口、只选择其他 dispatcher 保持 unknown。
- GET 没有写业务数据库或根目录图缓存。POST 锁内重算映射摘要，拒绝过期摘要、错误入口和关闭工单。不增加 `flows_ok`、人工复核或签收事件。
- 候选变化保留旧记录用于追溯，但旧 `code_path` 在签收快照中变为 unknown；入口和函数事实来自候选源码，不借主分支旧图冒充当前版本。
- 最后将签收快照的根目录 `_flows` 读取移到非 Python 分支；实际测试令旧图读取抛出损坏异常，候选 Python 快照仍正常生成并绑定正确完整提交。当前 Python 路径不再依赖主分支图的可用性。
- 特意使用错误业务返回值作正面的静态可达样例：静态路径仍可成立，业务正确性必须由独立执行断言判断。dispatcher 标签没有编造 `/items/edit` 等具体 URL。

## 固定 BOOTV2 候选的实际 HTTP 证据

独立脚本 `independent_bootv2_trace.py` 从 Git 对象读取固定 `app.py`，验证完整源码摘要后在独立模块命名空间中执行；仅使用本脚本拥有的随机回环端口和临时 SQLite。

- 候选：`8be50de6b4b4200dc6d792c2a7f0b871f9288da4`。
- 基线：`6c7787b3de7d308120b9c2e298b3629b588a47c9`。
- 源码 SHA-256：`a5bc89078052bc070b96e46255408721e88ce92750c91eef01fa973d7739a009`。
- 实际命令与输出：`independent-http-trace.log`；源码、完整差异、每次原始请求/响应及全部 Python trace 事件：`bootv2-trace/`。

原始结果读回确认两个前缀（根路径和 `/pv/BOOTV2-1/__commit/<完整提交>`）共 10 项路径观察、40 项业务断言通过。路径观察与业务断言分开存储，不能互相代替。具体覆盖 CRLF 逻辑长度 200 保存、201 拒绝并保留全部输入、记录 ID 与 done 保持、其他记录不变、真实数据库路径不可用返回 503、数据库恢复后原表单重试保存、服务重启后持久数据仍在。

真实 `/unrelated` POST 同样进入 `do_POST → post`，但没有执行修改行 161/162 且返回 404；200 保存、201 拒绝和恢复重试分别实际执行了这两行。这是对“方法级静态关系不等于具体 URL 行为”的直接反例。

临时服务已停止，临时数据库目录已删除。未进行浏览器交互；浏览器验收由主代理单独记录。没有将 HTTP trace、断言数量或静态入口数量宣称为部署成功、模型改对率或客户签收。

## 浏览器发现后的证据卡同步复核

主代理浏览器操作发现“代码关联已记录，但本页证据卡仍显示旧 unknown”。UI 代理修复后，独立只读复核 `ticketSummarySync`、`pkgSync`、`pkgSummary`、`pkgActions` 与 `pkgWire`，并亲自执行 `python3 -m unittest tests.test_python_pathmap_ui tests.test_ui_ticket_run_sync -v`，20 项通过，完整日志为 `independent-ui-package-sync-final.log`，源码回执为 `independent-ui-package-sync-receipt.json`。

完整 package 参与刷新指纹，同 status、同 records 下 gate 变化仍更新证据卡；POST 记录两入口得到 pass，再只选 GET 记录后显示 unknown，不能残留旧 pass。只替换 `#pkSummary` 与 `#pkActions` 的内容，`#pkForm`、文件 input、表单提交处理器保持原节点和引用。测试检查评论文本、焦点、选区、AC 选择、说明、复核意见、例外理由、复选状态和已选文件对象保留。新操作按钮使用最新证据状态重绑；已有草稿旁显示需要按最新验证门核对的提示。没有发现本次小改动的新增阻塞。

这组测试运行真实交付 JavaScript 函数与受控 DOM 模拟，不宣称代替真实浏览器文件选择验收。主代理负责独立浏览器复验。保留的 `independent-ui-package-sync.log` 中 12 项 path-map UI 已通过，随后因复核者首次误写不存在的旧测试模块名而有 1 项导入错误；更正为 `tests.test_ui_ticket_run_sync` 后得到上面的 20 项通过，不把命令拼写错误记为产品缺陷。

## 保留的限制

本轮只证明所支持 dispatcher 的方法级静态调用关系；不解释任意框架、条件分支可达性、跨模块动态改写或运行时注册。未知部分按限制/诊断展示，不泛化为具体请求覆盖。
