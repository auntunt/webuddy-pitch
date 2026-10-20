已在独立工作树完成修改，仅涉及：

- [app.py](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/BOOTV2-1-r3/app.py)：新增标题编辑、校验和安全回显；保存只更新标题，503重试保留原事项id，避免误新增；支持预览前缀。
- [tests/test_app.py](/Users/auntlee/Desktop/workspace/运维智能体/tob-maintenance-harness/data/product-workbench/worktrees/BOOTV2-1-r3/tests/test_app.py)：保留原5项，新增8项，覆盖持久化、状态/id保持、错误处理、恢复重试、转义和前缀。

验证结果：

- 语法编译、`git diff --check` 通过。
- 已执行 `python3 -m unittest discover -s tests -v`，但沙箱禁止监听端口，13项均在启动服务时受阻。
- 使用真实SQLite和请求处理器的内存传输补充验证，13项通过；**不能替代真实HTTP测试通过**。
- 浏览器连接超时，窄屏与实际页面交互尚未验证。

未修改 `.tmh/`、依赖或部署配置，未提交、推送或部署。仍需在可监听端口的环境完成真实HTTP及浏览器验收。