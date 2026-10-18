# Python 候选版本的代码入口与技术证据

日期：2026-10-19。分支：`codex/self-evolution-resume`。本轮起点：`2713ce5853a7d89aaa44d2464a5c0183010db629`。本轮只在本地工作台接续 BOOTV2，未调用新模型、合并应用主干或操作生产。

## 修复的实际阻塞

BOOTV2 已有真实 Codex 沟通、方案、代码、外部测试和固定版本预览，但 Python 代码没有进入原来的业务流索引，证据包的路径检查一直是 unknown。直接把整个 `app.py` 标为命中会掩盖未调用函数的改动，不能作为补齐证据的方法。

现在工单的“工程细节 → 候选代码入口”读取已采纳的完整 Git 对象，显示候选提交、源码与差异摘要、改动函数、新增/修改行、删除行、静态入口和无法解析的部分。用户可记录当前版本的技术关联。记录不增加人工业务确认、复核或客户签收；候选版本或差异变化后，旧关联保留但失效。

此能力限定于 Python 标准库 `http.server` 中实际静态注册的 `BaseHTTPRequestHandler` 分派方法，以及可确定的本地调用和 SQLite 操作。它证明整个 HTTP 方法处理函数的静态可达关系，不推断具体 URL 条件分支，也不宣称任意 Python 框架已经支持。入口中无法解析的调用完整展示；改动位置无法定位、未注册入口、解析失败、动态替换或未知装饰器保留 unknown。

## 实现与失效约束

- 新 Python AST 索引接入 mapper、codeindex、flow、graph 和导航查询；解析缓存版本更新。函数标识包含文件与完整词法路径，外层函数范围或同名函数不能替代实际内层函数。
- 路径检查逐一核对新旧两侧改动行。删除行读取旧 Git blob 并核对原文；新增行核对候选源码。其他未覆盖产品文件保持 unknown，不能被一个命中文件盖过去。
- Git 对象前缀必须唯一、类型正确。与短 SHA 或完整 SHA 同名的分支不改变读取对象；当前工作目录的未提交内容不充当候选版本。
- GET 仅生成候选映射，不修改项目图或业务数据库。POST 在锁内重新核对候选、差异摘要、入口选择和工单状态；错误入口、过期摘要与关闭工单拒绝写入。
- `code_path.flows` 是此次技术选择的依据，重新选 GET 后不能借旧 POST 继续通过。已有人工记录保留，技术选择不会制造 `flows_ok`。
- Python 签收快照直接使用候选代码关联，不读取主干旧图；损坏主干图不会阻止固定候选分析。路径门文案明确为静态关联，其余构建、测试、人工复核和签收仍独立判断。

## 独立复核与真实请求

独立代理发现并复现三处产品误判：同文件纯删除漏计、短 SHA 被同名分支遮盖、取消入口后旧技术选择仍生效。它们均已修复并保留失败日志与回归。解析器另补未知方法/类装饰器和动态方法替换的失败样例。模块尚未实现时的导入失败是测试合同红灯，不计为多个产品缺陷。

[独立报告](evidence/python-flow-2026-10-19/independent-review.md)及[最终源码回执](evidence/python-flow-2026-10-19/independent-source-receipt-final.json)包含独立执行的24项结果。Python/旧语言兼容合跑67项通过；测试组互有重叠，不能相加当作总体覆盖。

独立验证器从 Git 对象读取 BOOTV2 的真实候选 `8be50de6b4b4200dc6d792c2a7f0b871f9288da4`，使用临时数据库和随机回环端口实际发 HTTP 请求。两个路径前缀下，10项执行轨迹观察与40项业务断言全部通过：CRLF逻辑200字保存、201字拒绝完整回显、真实数据库故障503、恢复后原事项重试、编号和完成状态保持、对照行保持、重启后数据持久化。

`POST /unrelated` 同样进入 `do_POST → post`，但返回404，没有执行修改行161/162；保存、长度拒绝和恢复重试实际经过这些行。这是静态方法关联不能冒充具体 URL 验收的直接反例。完整请求、响应、trace、源码、原始差异保存在[独立 HTTP 记录](evidence/python-flow-2026-10-19/bootv2-trace/independent-http-trace.json)，脚本为 [independent_bootv2_trace.py](evidence/python-flow-2026-10-19/independent_bootv2_trace.py)。验证器已停止自己的服务并清理临时数据库，原应用数据未参与故障注入。

## 浏览器验收与收尾

已发现并修复的浏览器缺陷原始截图保留为 [browser-recorded-full.png](evidence/python-flow-2026-10-19/browser-recorded-full.png)：后台已记录关联、证据包为第5条且路径pass，页面仍显示第4条与unknown。此图片是修复前证据，不能当最终成功图。

最终日常工作台 `http://127.0.0.1:8791/#/t/BOOTV2-1` 已加载本轮代码，浏览器完成以下操作：

| 路径 | 读回结果与证据 |
| --- | --- |
| 记录 POST 入口 | 固定候选完整提交为 `8be50de6b4b4200dc6d792c2a7f0b871f9288da4`。新行160/161/162、旧删除行160均落在 `make_server.Handler.post`，保存为技术事件与追加证据包。完整映射：[mapping-final.json](evidence/python-flow-2026-10-19/mapping-final.json)。 |
| 改选 GET | 后台和页面立即显示第6条记录、路径unknown，原POST不再参与检查。[服务端读回](evidence/python-flow-2026-10-19/ticket-get-only.json)、[浏览器读回](evidence/python-flow-2026-10-19/browser-get-only-proof.json)、[原始截图](evidence/python-flow-2026-10-19/browser-get-only-full.png)。 |
| 恢复 POST | 后台和页面立即显示第7条记录、静态路径pass；证据包仍缺乙方复核人，工单仍待验证。没有人工复核、签收或 `flows_ok`。[最终工单](evidence/python-flow-2026-10-19/ticket-final.json)、[完整页面](evidence/python-flow-2026-10-19/browser-final-full.png)。 |
| 表单保持 | 两次记录期间，未发送评论、未提交附件说明和本地图片选择 `browser-preview-retained.png` 保留；没有提交评论或附件。[浏览器状态](evidence/python-flow-2026-10-19/browser-final-proof.json)。修复仅刷新证据摘要与动作区域，保留表单及文件input原节点。 |
| 页面刷新 | 主代理主动重载后，POST选择和第7条证据包仍在。[刷新读回](evidence/python-flow-2026-10-19/browser-reloaded-proof.json)。主动重载清除了本代理的未提交测试草稿；本轮不宣称草稿可跨整页刷新持久化。 |
| 原应用与数据 | 8793固定候选预览仍打开，三条事项的全部字段、主干HEAD/状态、原模型运行逐项相同。没有新模型调用、人工签收或附件写入。[业务核对](evidence/python-flow-2026-10-19/final-business-checks.json)、[预览截图](evidence/python-flow-2026-10-19/browser-preview-retained.png)。 |

主代理已实际打开最终[证据包截图](evidence/python-flow-2026-10-19/browser-final-evidence-panel.png)及[版本面板截图](evidence/python-flow-2026-10-19/browser-final-version-panel.png)，核对文字可读。所有截图保持工具返回的原始字节，没有压缩、缩像素或重编码。浏览器工具不提供文件内容读取；本轮通过原生文件选择、页面文件名保持和同DOM节点测试验证选择保留，不宣称测试附件已上传。

最终完整命令：`NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost python3 -m unittest discover -s tests -v`。**541项，539通过、2项可选依赖跳过，187.119秒，退出码0**，日志为 [platform-full-ui-sync-final.log](evidence/python-flow-2026-10-19/platform-full-ui-sync-final.log)。仍有既有socket/HTTP资源警告，不宣称无警告。只对子进程设置回环代理绕过，未修改系统代理。

此前539项全绿的 `platform-full-final.log` 早于浏览器同步补修，保留为中间证据。随后两个同步红灯见 `ui-package-sync-red.log`，补修后52项相关回归通过、独立20项通过，再完成上述最终541项。独立首次UI命令有模块名称导入错误，保留原日志 `independent-ui-package-sync.log`；正确模块复跑见 `independent-ui-package-sync-final.log`，不能把命令错误计为产品缺陷。

最终源码摘要见 [tested-sources-final.json](evidence/python-flow-2026-10-19/tested-sources-final.json)，原始证据清单见 [SHA256SUMS](evidence/python-flow-2026-10-19/SHA256SUMS)。此前源码回执和失败日志全部保留。完整前后平台/应用SQLite备份也在证据目录；只新增3次技术关联及3次追加证据记录，原模型运行、应用数据和已附业务证据未改变。

## 后续边界

下一轮优先处理服务被强杀后的可验证遗留进程回收，或预览健康检查与候选数据隔离，不重复本轮入口映射。当前静态索引不证明具体请求行为、业务正确性或模型修对率；任意框架、运行时注册、跨模块动态改写仍有边界。已有人工复核与客户签收继续等待真实人员操作。8792及生产未操作，其他暂停自动任务未恢复。
