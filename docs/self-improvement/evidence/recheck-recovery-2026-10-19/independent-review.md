# 已完成运行重新验证：独立复核结果

基线：`64f2385cd3a8364362cef326827d52007861ea41`。独立复核者仅修改 `tests/test_recheck_crash_independent.py` 和本目录独立证据，没有修改产品实现。

## 结论

冻结版本的 **8 项独立回归全部通过，17.144 秒**，见 [independent-final-sealed.log](independent-final-sealed.log)。执行前后 9 个相关文件的 SHA-256 完全一致，详见 [independent-final-sealed-source-receipt.json](independent-final-sealed-source-receipt.json)。另独立执行 13 项重验 UI 和 3 项摘要回归，16 项通过，见 [independent-ui-summary-final.log](independent-ui-summary-final.log)。没有将其他代理运行的测试计入以上数字。

本轮范围内未发现剩余阻断问题。原实现运行与重新验证现在使用独立记录；旧通过结论不会在新验证开始、运行中断或回执缺失时继续支持采纳或签收。

## 实际路径与结果

夹具先在临时真实 Git 工作树中执行 build/test，正常封存原 run，再创建普通证据包。新的随机端口 HTTP 服务通过真实 POST 启动两条检查命令；build 完成后，test 及其子进程持续运行，测试向该服务父进程发送真实 SIGKILL。测试不调用模型、不使用已有服务和客户数据。

| 独立路径 | 已验证结果 |
|---|---|
| SIGKILL → 重启 → 明确收回执 → 再次验证 | 子孙进程由监管回收；原始 `00 ff` 字节保存；原 run 全行、原 lifecycle 和原输出保持不变；新验证使用新 operation ID 并实际运行命令通过 |
| 上游验证失效 | 运行中和中断后，普通旧包为 stale；当前 parse/baseline/build/test/match 门为 unknown；历史 snapshot 内原 build/test pass 原文保留 |
| 新验证完成 | 新通过结果不让旧包自动复活；显式重新打包后才恢复当前 build/test pass |
| 命令之间的间隙 | 实际 build 返回 0 后暂停，虽然没有活动命令，整轮 lease 仍被持有；第二 Platform 不会误恢复，第二次重验被拒；原操作随后继续并通过 |
| 活跃重验时采纳 | 第二调用者不能采纳并移除正在验证的工作树 |
| 缺少最终停止回执 | 原件改名保留，GET 不补写、不启动命令；新重验被拒。原件恢复并明确收回执后才允许继续，收回执本身不会变成验证通过 |
| 缺失或错配结果证据 | lifecycle、source 或 verification 缺失均使当前验证 unknown；同时修改两份一致 artifact 的 checked_commit 或 source_run 也无法继承已封存成功 |
| 实际检查失败 | test 真实退出 7，保留 current fail 和完整输出，原 run 仍为原始 done；不能采纳。失败结果重新打包后仍不能用说明文字绕过签收，test 门保持 fail，并不被冒称为旧未知结果 |
| 签收竞态 | 在实际当前依据检查后尝试启动重验，被同一 source guard 拒绝；签收完成后才可启动。后续验证使旧签名成为历史 previous_decision |

签收相关用例使用明确标注 `SYNTHETIC` 的临时签收人和本地 token，仅为竞态及门禁回归，不代表真实人工复核、客户授权或客户签收。

## 失败证据与修复依据

[independent-red-real.log](independent-red-real.log) 保存原始真实失败：进行中和重启后旧 verify 仍 pass、普通旧包仍 current、恢复覆盖原完成 run 的 status/result/exit_code。此次失败执行前后源码相同，有独立源码回执。

[independent-failed-sign-red.log](independent-failed-sign-red.log) 保存第二个真实失败：候选检查退出 7，重新打包后 test 门为 fail，但说明文字仍允许签收并关闭临时工单。最终冻结回归验证它已被 409 阻止，且失败门仍显示 fail。

`independent-red.log` 是测试夹具最初遗漏 X-TMH 头产生的 403；`independent-adopt-red.log` 是接口实现中途的字段合同不一致。二者完整保留，不计作冻结产品失败。`independent-final.log` 的 7 项虽通过，但执行期间 signoff.py 有并行修改；其回执如实记录 `source_unchanged=false`，最终证明以 `independent-final-sealed.*` 为准。

## 审查与证据保留

只读复核了 operations 独立表、整轮 source guard 与 owner lease、结束后回执验证、只读 GET、显式恢复 POST、版本和 source_run 绑定、原子产物发布、签收验证到落地的锁范围，以及 UI 当前结果和历史结果的区别。当前失败不得沿用旧绿色结果；最终停止回执只证明执行收尾，不证明业务通过。

原始观察在 [independent-final-sealed/](independent-final-sealed/)，包含完整 run、verify、lifecycle、operation 文件原始字节 Base64、HTTP 状态、证据包及进程状态。逐项读回结果和各记录 SHA-256 在 [independent-final-sealed-readback.json](independent-final-sealed-readback.json)。8 项中均未使用夹具补救 worker 信号；读回时全部本轮临时 worker 已退出。

UI 验证为代码审查、真实本地状态读取和 DOM 模拟，不代替父代理的浏览器验收。本报告未验证 SSH 测试机、生产部署、整机掉电、监管进程本身被强杀或故意逃离进程组的命令。未操作 8792 或生产。测试通过不能作为需求修对率、客户验收率或部署成功率。

## 冻结后补充字段

8 项冻结执行结束后，根代理在 `signoff.brief` 增加返回 `binding_blocked` 字段，供最终页面的签收按钮禁用使用；state 和 gate 规则未因此改变。独立回执准确记录的是此字段新增前的源码，不覆盖原日志，也不把后来的 UI 按钮改动计作已经通过本报告的测试。该字段和最后按钮改动交由根代理的最终全量测试及浏览器验收覆盖，结果以其后续最终回执为准。本复核只读确认字段透传，不重复运行完整 8 项。
