# 本轮执行入口

本机 macOS 27.0.1，16GB，Python 3.14.6。测试解释器 `/private/tmp/webuddy-developer-mcp-venv/bin/python`，冻结复跑设置 `TMPDIR=/private/tmp`、`-B -m pytest -q -p no:cacheprovider`。

- frozen-targeted.log：tests/test_tool_execute_gateway.py tests/test_reform_state.py tests/test_reform_durability.py tests/test_reform_process_crash.py tests/test_direct_invocation_lifecycle.py tests/test_project_tests.py tests/test_ui_reform.py tests/test_tenant_policy.py
- full-failures-recheck.log：tests/test_platform.py tests/test_project_import.py tests/test_tool_client.py tests/test_workbench_mcp.py tests/test_external_requirements.py
- readable-report-check.log：tests/test_scenario_materials.py tests/test_tool_read.py tests/test_reform_mcp.py
- full-mac.log：同一解释器，`-m pytest tests -q -p no:cacheprovider`；运行期间修改了代码，诊断结果不是冻结代码全量证明。
- 浏览器脚本连接本次自行启动的Chrome18990和隔离服务18989；固定测试夹具，完整来源见本目录脚本。不能用于真实任务确认。
- capacity.mjs：同一认证会话访问项目列表，所有原始耗时见capacity.json；未测真实执行负载。

脚本原路径在 `/private/tmp/webuddy-scenario-20261107`。重新运行时先启动新的隔离服务并使用其新计划ID；不要将合成凭据用于正式环境。

实际页面的编辑区默认折叠。scope-capture.mjs 展开外层编辑和场景依据区，再聚焦业务规则并滚动，scope-fields-1440/390.png 保存可读输入区；不将折叠区域的截图冒充已展示的内容。
