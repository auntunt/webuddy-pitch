# 本轮实际命令与边界

产品候选：91744d2f981a7235d5172484a83ef6594a3bc296（实现62df3d7d与远端交付记录合并；合并没有改产品文件）。本机环境：macOS-27.0.1-arm64-arm-64bit-Mach-O；回归解释器为 /private/tmp/webuddy-developer-mcp-venv/bin/python；Node v24.16.0.

最终主体（修改冻结后运行；原输出 bc-frozen-regression.log）：

```sh
WEBUDDY_MAP_EVIDENCE_DIR=/private/tmp/webuddy-map-20261107/scenario-delivery-frozen TMPDIR=/private/tmp /private/tmp/webuddy-developer-mcp-venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_code_maps.py tests/test_tool_read.py tests/test_tool_access.py tests/test_reform_tenant_mcp.py tests/test_workbench_mcp.py tests/test_ui_reform.py tests/test_reform_state.py tests/test_reform_integration.py tests/test_reform_durability.py tests/test_report_exports.py tests/test_learning_context.py
```

手机分区及示范夹具材料调整后的差异复验（bc-final-delta.log）：

```sh
WEBUDDY_MAP_EVIDENCE_DIR=/private/tmp/webuddy-map-20261107/scenario-delivery-final TMPDIR=/private/tmp /private/tmp/webuddy-developer-mcp-venv/bin/python -B -m pytest -q -p no:cacheprovider tests/test_code_maps.py tests/test_project_tests.py tests/test_ui_reform.py
```

浏览器是本次自建、独立CDP端口18990的headless Chrome，不控制用户个人Chrome。服务由atlas-server.py启动，只有隔离合成账号/任务。依次实际运行 b-browser-responsive.mjs、b-browser-states.mjs（失败）、b-browser-states-retry.mjs、b-browser-expand.mjs、report-browser.mjs 与 report-failure-browser.mjs。操作细节在脚本及README中；截图保留原始PNG。

43候选的实际定向复验：

```sh
cd /opt/webuddy/releases/maps-91744d2f/app
python3 -m unittest discover -s tests -p test_code_maps.py -v
```

此处9项通过。完整Linux套件由精确提交的GitHub CI另行运行，不把9项替代完整套件。源码副本迁移/manifest与配置检查使用现有release helpers，日志独立保留。

已安装客户端经正式MCP SDK stdio→HTTPS读取43。报告首次设置STOP_AFTER_FIRST=1，49,152字节落盘后客户端终止；第二次使用原请求/导出标识续传；逐段及整文件校验通过。临时进程域名映射仍检查TLS与凭据端点，未改全局DNS。真实业务附件不提交；技术回执见../test-network。

没有执行客户验收、采用知识或关单。实际Codex宿主此前写审批拒绝没有改变；SDK与已安装客户端结果不宣称原宿主通过。
