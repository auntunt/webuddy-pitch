# 完成后重新验证：独立失败复现与合同

基线 `64f2385cd3a8364362cef326827d52007861ea41`。独立测试只写 `tests/test_recheck_crash_independent.py` 与本目录证据；未操作原项目数据、已有服务、8792、生产或模型。

## 已复现

[independent-red-real.log](independent-red-real.log)：1 个完整路径测试在 8 条业务结果断言上失败，测试前后产品源码摘要一致，见 [independent-red-real-source-receipt.json](independent-red-real-source-receipt.json)。详细原始数据位于 `independent-red-real/`，包括原始 run/verify/lifecycle、全部过程原始文件 Base64、普通证据包以及真实进程状态。

夹具首先在真实 Git 工作树运行原始 build/test，再正常封存原运行为 done，并为该实际验证生成普通证据包。不伪造模型 verdict、人工复核或客户签收。随后启动真实随机端口 HTTP Platform 服务，以 POST `/api/runs/<rid>/recheck` 请求重新验证；第一条命令通过，第二条本地检查命令及其子进程持续运行。对持有 HTTP 服务的 Popen 发送真实 SIGKILL，再用同一临时数据库构建新 Platform。

现象：

| 检查点 | 实际基线行为 | 合同 |
|---|---|---|
| 重验进行中 | `verified.check=pass`，live signoff snapshot 仍为 pass | 旧验证不再是当前通过结果 |
| 进行中的旧普通包 | `stale=false` | 旧包保持历史记录，但不再允许按当前依据签收 |
| 服务强杀并重启后 | 旧 verify 仍 pass，旧包仍非 stale | 重验中断必须可见，旧验证保持失效 |
| 原运行 | done 变 failed，原 result/exit_code 被覆盖 | 原完成运行结果保留，重验有独立生命周期和历史 |
| 实际进程与输出 | 监管正确回收子孙，raw 输出完整 | 继续保留此已满足行为 |

主路径没有使用夹具补救信号；所有本轮 worker 均已退出。首次 `independent-red.log` 是测试请求遗漏 X-TMH 头造成的 403，已修夹具且保留日志，不计作产品缺陷。

## 实现复核要点

- 持有整轮重验 lease，覆盖基线、候选及命令间隙，不能逐命令释放后允许第二实例启动重验。
- 开始第一条命令前持久化新 generation/进行中状态，并使依赖旧验证的交付复核及普通签收包失效；保留旧原始 verify/lifecycle/run。
- 重启只能核对该重验自己的 owner、原始输出和停止回执，不把它当成原 coding run 的失败。
- 证明完整回收后允许用户显式重新验证；启动重验、重启、GET 查询均不自动补跑命令或复活旧签收。
- 缺失、损坏、错 generation/owner 回执继续阻塞；恢复与重新验证必须明确分开。
- 最终绿色不能只由进程退出码或 verify 文件存在判断，必须覆盖真实检查结果、当前版本、命令历史和原工单结果保留。

后续独立测试依据根代理确定的最小接口契约补充，不主动扩大到新模型运行或远程测试机。
