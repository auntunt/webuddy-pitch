# 日常 Coding 实用性评估证据

入口为 `index.html`；完整文字评估位于上两级 `usability-assessment-2026-10-19.md`。页面离线可用，无外部字体、脚本或数据上报。

`cases.json` 是历史任务候选和验收条件，不是自动执行配方或已确认的新需求。`scope.json` 保留完整发现清单、GitHub 元数据及来源摘要；不包含凭据、业务源文件或工作数据库。Coding 独立于办公 WorkBuddy。

两份 `.log` 为原始完整输出；`*-result.json` 保存真实执行命令、源码哈希、Git 状态及回收回执。`run-sample.executed.py.txt` 是在 `data/practical-assessment-20261019/run-sample.py` 执行的脚本原字节快照，其相对根路径基于原位置；不是安装入口。`metrics-observation.json` 来自本地只读备份，仅记录必要聚合和候选历史。原备份留在忽略目录，不进入此交付包。

`manifest.json` 对归档产物逐字节核对；生成与浏览器检查记录另行保留。未修改业务代码，没有生产连接或办公室集成操作。

## 页面验证

浏览器已实际检查关键词、证据筛选、空结果、版本展开、390像素宽度无横向溢出，以及JSON与完整Markdown下载后字节相等。最终7项检查通过，控制台未返回错误/警告。截图保留工具返回的原始JPEG，没有缩放或重编码。打印预览及直接file URL打开未验证。

第一次自动化用精确label选择select时未匹配，改用已观察到的控件ID后功能通过。第一次把Markdown链接当作网页预览，实际浏览器下载文件；原失败记录保留在browser-verification.json。入口随后明确标为下载，并用下载原字节核对，最终结果见browser-final-verification.json。这些是报告页面检查，不是业务应用验收。

临时8797静态服务已停止；日常8791/8793服务没有在本轮重启。
