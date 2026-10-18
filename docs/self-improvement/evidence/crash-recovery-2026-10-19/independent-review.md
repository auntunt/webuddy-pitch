# 服务强杀恢复：独立复核

2026-10-19，基线 `0428c1ca771f0d53f54310806fd782e99675ab78`。复核者仅修改独立测试及本目录证据；未修改本轮产品实现。

## 结论与实际验证

普通受管运行路径的 8 项独立回归通过，最终日志为 [independent-final-sealed.log](independent-final-sealed.log)，耗时 3.158 秒。执行前后关键源码 SHA-256 相同，详见 [independent-final-source-receipt.json](independent-final-source-receipt.json)。本结论仅对应这些源码，不能替代后续版本验证。

测试启动真实临时 HTTP 服务父进程、实际 Runner、临时 Store、真实 Git 项目及独立工作树；命令为本地测试程序，不调用模型。主路径对持有者发送真实 SIGKILL，受管命令及派生子进程忽略 SIGTERM。父进程返回 `-9` 后，独立监管完成回收，重启 Runner 根据回执恢复。测试同时确认：

- 子进程和孙进程在夹具清理前均已退出，主路径没有使用夹具补救信号。
- `output.bin` 完整保留 `owned-crash-output\x00\xff\n`，文本显示替换无效 UTF-8 不影响原始字节证据。
- 原工作树中 `VALUE = 1` 及后续完整注释保留；新运行 #2 从恢复快照建立不同工作树，并实际读取同样的完整内容；原项目 HEAD 未改变。
- 数据库已写 `done` 但生命周期尚未封口时发生强杀，重启不会跳过该记录，也不会把未封口运行视为业务成功。
- 第二个 Runner 无法修改仍持有 flock 的活跃运行；历史 PID/PGID 本身不触发信号。
- 把另一个真实运行的完整 planned/final/raw 回执复制过来，即便 nonce、目录和输出摘要彼此一致，仍因 owner 不同保持 blocked。
- 有效持有者已丢失且生命周期原文件损坏时，原始无效字节保留于 `restart-recovery/original-lifecycle.json`，可见状态改为 failed/blocked；重复恢复不能用可读错误摘要替代原始证明而自行放行。
- 尚未启动任何 attempt 的已丢失持有者可以结束；一旦存在未登记 attempt 目录，必须保持 blocked。

原始观察位于 [independent-final-sealed/](independent-final-sealed/)，包含完整行记录、生命周期、过程文件原始字节的 Base64 和进程状态。最终逐项读回及 SHA-256 位于 [independent-readback.json](independent-readback.json)。读回时全部本轮临时 worker 命令均已不存在。

## 真实失败及修复确认

[independent-red.log](independent-red.log) 保留基线红灯：第二实例会错误终止活跃状态；父服务强杀后子孙进程仍存活，原始输出与结束证明不足。红灯现场中使用的夹具补救清理有单独记录，未计作产品回收成功。

[independent-proof-expanded.log](independent-proof-expanded.log) 保留后续真实失败：有效失主但生命周期损坏的记录仍长期显示 running。最终用例验证修复及重复核对的保守行为。

中途 `independent-first-green.log` 的 helper 回执读取异常已修复；`independent-green-two.log` 的续跑失败来自独立夹具最初误用项目根目录，后改为真实受管工作树。此夹具错误不计作产品缺陷。所有原始日志均保留。

## 关键代码审查

当前实现符合普通运行恢复合同：恢复只读取独立监管回执，不根据历史 PID 发送信号；owner 绑定 token、run_id 和规范化 data_dir； planned/final 的 schema、nonce、目录、owner 与原始输出长度/摘要相互校验。缺失或矛盾的清理证明不允许续跑。

运行持有 flock，子进程不继承持有者的锁与保活写端；父服务丢失后，由实际拥有目标 Popen 的独立监管响应 EOF 并回收。恢复先写数据库状态、最后原子封存 lifecycle；中间再次崩溃不会先出现可续跑的最终封口。父 Runner 只读核对独立监管保存的 output.bin，避免覆盖过程中损坏原始输出。

UI 另执行 29 项相关回归通过，日志为 [independent-ui-review.log](independent-ui-review.log)：blocked 不继续假装运行/轮询；pending 仅 GET 轮询；人工重新核对回执使用显式 POST，防重复请求及离开页面后的旧回调；完整回执经过转义；续跑需要后端允许和完整停止证明。该部分为代码审查及 DOM 模拟，不冒充浏览器实际验收。

## 明确保留的边界

- 已完成普通运行之后的 `fixloop.recheck`，即 `run_command(active=False)` 多命令业务回执恢复，未纳入本轮完成范围。监管仍保存原始输出并回收，但旧业务检查结果如何失效及重新封存需要后续独立路径验证；不能据本轮结果宣称所有重验流程都可恢复。
- 无原始所有权证明的旧记录继续保守阻止恢复；不会猜测 PID 后强杀。
- 故意脱离进程组的命令、监管进程本身遭 SIGKILL 或整机故障，不在本次“父服务 SIGKILL”完整回收证明范围。
- 未操作正常 8791 用户数据、8792、生产服务或真实模型；未部署。上述绿色结果不是需求修对率、客户签收或部署成功证明。

普通受管运行范围内未发现需要阻止本轮合入的剩余问题。
