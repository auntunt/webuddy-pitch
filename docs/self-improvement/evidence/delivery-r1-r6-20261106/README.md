# R1—R6 本轮验证

代码候选：`ca3e1224bfae562ef1ea3c039fe37228f57c65bf`。Mac Python 3.11；隔离临时 Git、合成账号/执行器和实际 Node 测试适配器。不是怀柔项目验收。

## 命令与日志

下列命令以仓库为当前目录，前缀 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/tests:$PWD" python3.11 -m unittest`。批次有重叠，不合并计算场景数。

| 参数 | 日志 | 结果 |
|---|---|---|
| `test_direct_invocation_lifecycle test_library_review test_development test_project_tests` | webuddy-r1-r2-recheck.txt | 62 项通过（此批未设置禁写字节码） |
| `test_tool_read test_development test_stage test_workspace test_team_workspace test_project_tests` | webuddy-scoped.txt | 116 项通过 |
| `test_tool_read test_project_tests test_project_ci test_development test_team_workspace.TeamWorkspaceTest.test_terminal_approved_queue_moves_to_owner_without_changing_legacy` | webuddy-final-targeted.txt | 67 项通过 |
| `test_project_tests.RecheckProjectTests.test_optional_environment_dependency_blocks_recheck_without_writer test_platform.PlatformApiTest.test_a_rebuilt_change_the_diagnosis_judged_unsolved_still_waits_for_a_person test_stage test_workspace test_team_workspace` | webuddy-r-final.txt | 64 项通过 |
| `discover -s tests -p 'test_ui*.py'` | webuddy-r-ui.txt | 328 项通过 |
| `test_ui_architecture` | webuddy-ui-final-delta.txt | 4 项通过 |

`webuddy-r1-before.txt` 保留首次失败，不是通过记录。其中评测身份错误与本机进程监督回执异常分别保留。无新增 skip/xfail；未更改 CI 容错。

## 安装

使用 `git archive ca3e122` 的完整源码，安装到新建的 `/tmp/webuddy-r6-install-20261106` venv。执行仓库 `scripts/installed-smoke.py`，显式指向该 venv site-packages，Python `-I -X utf8` 隔离。结果见 `webuddy-r6-full-smoke.txt`，覆盖来源、CLI、install、refresh、完整资源和 offline install。此前仅导出 tmh/pyproject 的不完整实验包缺少资源，不能用其 CLI 成功代替正式安装；最终采用完整归档，未为此改产品打包规则。

## 浏览器

实际 Chrome headless，隔离 HTTP 18983/18984，未操作真实业务任务。截图均原始 PNG。

- `terminal-1440.png`、`terminal-390.png`：真实保存的终端确认稿，无 plan/无 fix；显示确认人、修订、方案、测试计划与标准。实测栏仍未验证；切换页签保留草稿。
- `leader-1440.png`、`leader-390.png`：临时 Git 候选与合成测试证据，终端选择为隔离 fixture；Leader 已批准，重复批准按钮禁用、待复核列表为空，提示由负责人终端确认合并。
- 桌面 1440×900、手机 390×844，DOM 检查无整页横溢，截图已打开检查。
- 修改隔离任务来源并刷新：确认变为 stale，原 confirm 事件保留。测试脚本最初对同 URL 导航未强制刷新读到了旧页面；改为实际 Page.reload 后通过，不据此宣称产品刷新故障。

客户 Windows/两机、客户 CI、真实规则/数据及真人业务签收未执行。CI 和部署证据在进度记录追加。
