# 已知死路（有本地验证记录）

仅适用于来源记录中的环境与前提；环境限制不等于所有沙箱都如此。需要起服务、回收进程或判断验证/预览结果时查对应行。

| 场景 | 试过的做法 | 实际结果 | 改用什么 | 来源文件 |
|---|---|---|---|---|
| 已记录的 Codex workspace-write 环境运行 HTTP 测试 | 在该沙箱监听 TCP | 真实测试出现 PermissionError | 在已授权且允许监听的本地验证环境执行，保留沙箱失败记录 | [verification-external-candidate-2026-10-19.md](self-improvement/verification-external-candidate-2026-10-19.md) |
| 同一沙箱写共享 worktree Git 元数据 | 直接在共享元数据上提交 | 写入被拒绝 | 由有授权的正常工作区完成提交并重新独立验证，不绕过沙箱 | [verification-external-candidate-2026-10-19.md](self-improvement/verification-external-candidate-2026-10-19.md) |
| POSIX 包装进程退出与超时清理 | 只 kill 父进程，或父退出 0 就算成功 | 子孙仍活着，继承的 stdout 管道导致读取卡住 | 检查本次受管进程组、管道排空和回收回执；按组 TERM/KILL，不清理无关组 | [verification-runtime-2026-10-18.md](self-improvement/verification-runtime-2026-10-18.md) |
| 判断业务探测通过 | 仅看工作进程退出码 0 | 基线和候选都退出 0，基线业务检查仍失败 | 对照逐条业务观察和同版本证据 | [verification-harness2-2026-10-19.md](self-improvement/verification-harness2-2026-10-19.md) |
| 判断固定版本预览健康 | 低于 500 就通过、跟随重定向、失败后试根路径或只看 PID | 401/404/重定向及启动后 503 可能被误判可用 | 直接检查完整健康路径的完整 2xx 响应，限总时长、禁代理及重定向，读取状态也复查 | [verification-preview-health-2026-10-19.md](self-improvement/verification-preview-health-2026-10-19.md) |
| 打开需要授权的预览 | 返回裸预览端口直链 | 缺授权 Cookie 得到 401 | 使用工作台授权入口；不关闭访问控制或浏览器保护 | [verification-external-candidate-2026-10-19.md](self-improvement/verification-external-candidate-2026-10-19.md) |
| 固定提交的受测源码导出 | 用 git archive 作为源码原样快照 | export-ignore/export-subst 改变实际受测内容 | 读取 Git tree/blob 并保留可执行位；不支持的链接/特殊文件明确失败 | [verification-harness2-2026-10-19.md](self-improvement/verification-harness2-2026-10-19.md) |
| Python 优化模式下运行业务检查 | 用 assert 判定业务正确 | 优化删除断言，错误行为假通过 | 使用始终执行的显式判断，并验证优化模式下的失败反例 | [verification-harness2-2026-10-19.md](self-improvement/verification-harness2-2026-10-19.md) |
| 本地 HTTP 回归继承系统代理 | 未排除回环请求代理 | 出现 502，不能据此定位应用逻辑 | 仅对本次测试设置 NO_PROXY，保持回环请求直连，不改全局设置 | [verification-external-candidate-2026-10-19.md](self-improvement/verification-external-candidate-2026-10-19.md) |
