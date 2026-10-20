# Harness² 验证层接入与同版本本地验收

日期：2026-10-19。主仓库 `/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness`，分支 `codex/self-evolution-resume`。实现提交 `1ac19f116ac982a134635659e24edf9bc6cb0115`；重验测试的封存等待修复 `a32e8a64750b1f13d9e9bb0ec638db2e2a17329c`。仅本地提交，无合并、推送或生产发布。

用户本轮要求融合 Google Research Harness² 可用部分，并在进行中明确回复 BOOTV2 搜索与状态筛选的“确认本地验收”。此次产品改动和用户业务确认分别记录，未把技术探测冒充真人确认。

## 官方依据和落实范围

已读取 [官方仓库固定版本](https://github.com/google-research/harness2/tree/1cfe254e8d25b15f37048c3730134686abe60335) 的 README、实验说明、核心策略/账本/经验库/上下文/选择模块及 Codex substrate。提交日期 2026-10-14，核查日期 2026-10-19，Apache-2.0；来源文件哈希见 `upstream-source-manifest.json`。没有运行上游默认关闭 sandbox 的执行器，也未复制其实现代码。研究来源和适用边界见 [接入设计](../harness2-integration.md)。

实际落地的是验证层：维护者配方版本、同输入流程的基线/候选业务探测、固定源码、独立数据库、完整日志与回收证明、历史策略进入任务包。没有实现完整 Propose–Probe–Compose，也没有更改模型权重、模型默认提示词或权限。比较的是两份应用代码在同一验收配方下的行为，不是两种 harness 的因果效果；一个任务不能推导通用修对率。

## 真实 CLI → 探测 → MCP → 验收

- 需求：`BOOTV2-3`；候选：1；原真实 Codex 登记运行：7。
- 基线：`8be50de6b4b4200dc6d792c2a7f0b871f9288da4`。
- 候选：`8b6cb6da908fc7bdcb585789a1b8f2ce78569ffd`，复用前轮真实 Codex 产物，本轮没有新增模型调用或修改该应用提交。
- 配方：`bootv2-items-search-v1`；版本：`9ee97372cb36ef415954944d60950eb2aa039eeab2bb5ef84f186ab1cb98e372`。
- 实际探测：1；CLI 请求：`bootv2-harness-probe-20261019-001`。

| 行为标准 | 固定基线 | 固定候选 |
|---|---|---|
| A1 中文、Unicode casefold、%、下划线、引号按字面搜索 | fail | pass |
| A2 全部/未完成/已完成、关键词交集、空结果和清除 | fail | pass |
| A3 固定前缀、刷新、编辑取消/重试/保存的筛选上下文 | fail | pass |
| A4 200字含CRLF、原编号与状态、503完整恢复、CSRF、重启持久化 | pass | pass |

双方工作进程退出码均为0，但基线业务检查失败。因此结果由业务观察决定，不由进程退出码决定。基线进程1.079秒、候选0.569秒；这些是过程耗时，不包括所有准备、协议和人工操作开销。两组都显示 `cleanup.complete=true`，另用 OS 的只读信号0确认进程组均已不存在。

CLI 发起后立即返回编号。官方 MCP `ClientSession` 从 `/tmp` 启动真实 stdio 客户端，经运行中的8791 HTTP接口读取配方、报告、历史策略及任务包。执行配置实际发现27个工具，未提供人工决定工具；默认16个、只读13个由回归测试核对。新增工具是 `harness_recipes`、`harness_probe_start/get/cancel`、`harness_library`。完整协议输入输出见 `check-live-mcp.py`、`mcp-*.json` 和 stderr。

新增探测使旧逐项技术观察失效。协调验收会话读取上述观察、独立代码复核及实际浏览器后，通过 MCP 重新记录对应四项技术结果。实现者和技术观察使用不同审计标签；这些标签不是独立身份认证。

用户明确确认先记录在原证据上，再在**应用提交和全部验收条件均未改变**的前提下，把同一真实确认关联到附加探测后的证据；说明保留“协调者转录”、原请求和权限边界。不是新造用户答复，也不要求用户重复批准同一内容。最终 CLI `state=accepted`、`technical_acceptance=true`、`human_accepted=true`；证据哈希 `c21ef614385ae438aa3fb73c066960422fa848003414ca34d01a7a281c881c86`。

## 原数据与可打开应用

日常8791服务按原进程身份检查后以 SIGINT 停止并重新启动，继续使用8793作为预览入口。原BOOTV2固定预览进程与代码版本保持；浏览器 reload 后读取到三个原事项以及搜索/状态控件。截图工具返回的原始1280×805 JPEG和完整DOM见 `browser-preview.jpg` / `browser-preview.txt`，未重编码或压缩；仅纠正了最初误写的PNG扩展名，改名前后SHA256一致，记录见 `browser-image-metadata.json`。实际预览入口：[固定候选](http://127.0.0.1:8791/pv/BOOTV2-3/__commit/8b6cb6da908fc7bdcb585789a1b8f2ce78569ffd/)。本轮只检查打开与原数据呈现；前轮完整的组合筛选、编辑和窄屏浏览器证据仍见 `verification-external-candidate-2026-10-19.md`。

两份探测各创建自己的三条夹具记录和数据库，不读取或修改真实三条事项。`preservation-report.json` 核对：三个原事项逐字段相等；原3项目、5工单、51事件、7运行以及所有其他既有表的数据行完整保留。新增探测、请求回执、技术观察和用户决定作为新行保存。应用主干仍为 `547e4447b6921bcbfaa555b26a4391d1fc33d3ab`。8792、生产和暂停的其他自动任务未操作。

## 独立复核与失败修复

独立代理 `/root/candidate_chain_review` 只读产品源码，在临时项目添加9项回归；最终9/9通过，12.434秒，7个复核文件运行前后SHA256一致。它发现并验证修正：

1. `git archive` 的 export-ignore/export-subst 会改变受测源码。改为读实际 Git tree/blob，保留可执行位，不支持的链接/特殊文件明确失败。
2. Python 优化模式会删除 `assert`，导致错误搜索假通过。改用始终执行的显式业务判断；故障候选在 `PYTHONOPTIMIZE=1` 下仍失败。
3. 应用输出经 `readline` 转存时，超时会丢未换行的尾字节。改为直接写二进制日志，NUL、0xff和无换行尾巴完整保存。
4. 需求/验证在最后过程结束后变化仍可能发布通过。开始时绑定原始独立验证digest，执行间、发布前和读取时复核；历史观察与当前有效性分开。
5. 已确认停止与结果发布竞争。通过跨进程完成锁和最终取消检查串行化，成功确认的停止不再发布通过。

还覆盖两个 Store 的重复启动、验证内容替换、旧source缺字段兼容。真实原始红灯、修正后的绿灯和限定结论见 `independent-review-final.md` 与各日志。早期不完整夹具、格式错误和一次错误测试类名保留为调试失败，不计产品缺陷。

全量还暴露了两个旧测试等待条件问题，均通过额外强制延迟固定复现，保留原验收断言：

- 首轮758项在第二次退回时返回409，测试错误读取成功字段。此时自动采纳已写verify，但仍持有来源锁。测试现在等待对应Runner回调结束，再执行这条“完成后退回”路径；API保护未改。
- 第二轮758项在多命令重验SQL行done、生命周期尚未封存时读到unknown。测试现在等待owner释放，再重新读取验证；仍要求pass和两条真实命令。没有把unknown算作通过，也不靠反复重试到绿灯。

复现脚本和红绿日志分别为 `reproduce-legacy-callback-race.py`、`reproduce-legacy-recheck-publication.py` 及相关日志。第二个场景还保留完整HTTP状态和base64原始过程文件。

## 最终验证与完整归档

最终在 `a32e8a64750b1f13d9e9bb0ec638db2e2a17329c`，使用 Python 3.14.6 / MCP SDK 1.30.0 执行 `python -m unittest discover -s tests -v`：**758项全部通过，0跳过，306.496秒，退出码0**。183个源码、测试及构建文件执行前后SHA256相同；完整输出见 `full-platform-third.log`，结构化核对见 `final-verification.json` 和 `source-{before,after}-third-full.json`。独立代理另确认两处旧测试修正仍保留原业务断言，见 `independent-wait-review.txt`。

全量仍记录84行 `ResourceWarning`（其中5条未关闭socket警告，包含测试HTTP错误响应资源）；原文完整保留，未隐藏或计作业务验收通过。这是测试资源收尾的后续事项，不改变本轮真实探测两个受管进程组已消失的独立OS核对。首两轮全量失败与确定性红绿复现均保留，不能仅看最终绿灯忽略它们。

证据归档目录：[完整原始证据](evidence/harness2-2026-10-19/)。真实实验位于 `real-probe-1/`，其33项封存产物已逐一校验复制后的SHA256；结果文件和所有权回执也保留。原始数据目录 `data/harness2-integration-20261019/`、`data/product-workbench/harness-probes/1/` 保持。配方和完整测试夹具随实现提交，最终归档清单记录每个文件的原始字节长度与SHA256。操作者私有凭据未归档。

能力只适用于可信本地 BOOTV2 starter 配方；目录和进程分离不是OS沙箱，主动逃逸/机器掉电边界仍未扩展。没有做通用网站验收、候选生产数据迁移或完整自动策略合成。下一步应围绕真实失败扩展独立正反例和配方，并建设与提议者分离的保留任务集，而不是重复这一已通过案例计数。
