# 冻结后增量复核

2026-10-19。此次仅重新运行已有独立测试、只读复核产品增量并写本目录证据，未修改产品和测试源码。

最新 8 项独立回归全部通过，3.701 秒：[independent-final-again.log](independent-final-again.log)。执行前后源码摘要完全一致：[independent-final-again-source-receipt.json](independent-final-again-source-receipt.json)。此前原始日志未覆盖。

针对上次冻结后的三项变化，未发现新增阻断问题：

1. 原始生命周期备份先写独占临时文件并 fsync，再用 hard link 原子发布；既有原始备份不会被替换，发布失败不会留下半份正式备份。原文件损坏、再次恢复仍保守阻塞的实际用例继续通过。
2. `_save_lifecycle` 在完成路径的 finally 中释放 owner；最终封口写入失败不再永久占有锁，尚未封口的 `done` 行仍由恢复路径重新核对。独立真实强杀 done 窗口回归继续通过。另只读核对新增 API 测试的故障注入和结果断言，未将父代理报告的 API 测试计入此次 8 项。
3. supervisor 保留启动失败的 `error` 内容，未改变成功/清理门；预取消时发送 `C` 同时设置 `sent_start` 与 `sent_stop`，避免在 worker 已按取消结束后再发送启动 ACK 或重复取消。只读核对了不存在执行器和延迟第二次读取的取消回归；本轮没有重新运行整个 supervisor 测试组。

读回证据：[independent-final-again-readback.json](independent-final-again-readback.json)。实际父服务返回 `-9`；子孙进程在夹具清理前均退出，主路径补救信号为 0；原始 `00 ff` 字节完整，新运行成功读取原工作树修改。损坏原始回执仍逐字节保存，重复检查仍 blocked。全部本轮临时 worker 均已退出。

结论延续 [independent-review.md](independent-review.md)，普通受管运行范围无剩余阻断问题。完成后 `active=False` 的多命令重验业务回执恢复、整机故障和独立监管自身被强杀仍不属于本轮完成声明。
