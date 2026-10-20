已仅修改以下两文件：

- [app.py](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/BOOTV2-1-r3/app.py)：移除临时文件依赖；保留 8192 字节保存上限，设置 64 KiB 的累计错误恢复读取上限。9055 字节请求可完整回显并重试原事项；更大请求拒绝读取，浏览器保留原输入。
- [tests/test_app.py](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/BOOTV2-1-r3/tests/test_app.py)：保留原测试，补充临时存储故障、读取边界、输入回显及重试验证。

编译、`git diff --check`、22 项内存 HTTP 传输＋SQLite 补充测试、16 个脚本逻辑场景通过。

已实际执行 `python3 -m unittest discover -s tests -v`，但全部测试在绑定本地端口时被沙箱阻止。320px 实际渲染也因浏览器启动失败未完成，**尚不能标记验收通过**。

未修改 `.tmh/`、依赖或部署配置；未提交、推送或部署。仅用于本地技术验收，不代表客户签收。