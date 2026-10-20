已按方案修改，仅涉及两个文件：

- [app.py:160](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/BOOTV2-1-r6/app.py:160)：长度校验将每组 CRLF 算作一个换行；原始标题、保存逻辑及 8 KiB／64 KiB 限制保持不变。
- [tests/test_app.py:665](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/BOOTV2-1-r6/tests/test_app.py:665)：新增3个测试，覆盖200／201字边界、原文保留、id与状态、重启、前缀和故障重试；原23个测试完整保留。

语法检查、`git diff --check` 和独立静态复核通过。

已执行 `python3 -m unittest discover -s tests -v`，**退出码1**：26项均在监听TCP时被沙箱拒绝，报 `PermissionError: [Errno 1]`，尚未执行业务断言。[完整日志](/private/tmp/BOOTV2-1-r6-unittest.GU2GF4)

尚需工作台在可监听环境重跑测试，并完成原生浏览器与窄屏检查。未跳过或弱化测试，未提交、推送、部署生产或登记客户签收。