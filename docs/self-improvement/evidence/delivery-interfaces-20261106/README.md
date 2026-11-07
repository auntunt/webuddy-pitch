# 交付依据与私有 CI 接口验证

全部业务内容为隔离合成任务，不是怀柔业务验收。

- `final-tests.log`：Mac Python 3.11，114 项定向回归通过；只读副作用、项目隔离、确认失效、合并门禁、GitHub 与私有 CI 协议夹具。
- `final-mcp.log`：官方 MCP SDK 20 项通过，包含新增 delivery_get 的只读 stdio 往返；Cursor/Claude/Codex 配置启动，不等于客户桌面联调。
- `team-tests.log`：候选界面及团队逻辑 41 项通过，与前一批部分重叠，不相加统计。
- `tests.log` 保留初次接口清单数量断言失败；补入新路由的授权拒绝检查并更新清单，最终通过。
- `browser.json`、`task-*.png`：实际 Chrome 与隔离 HTTP 服务，1440×900、768×1024、390×844。点击下载，确认稿存在但无测试仍显示未验证。
- `ci-browser.log`、`ci-*.png`：实际候选页面 1440×900、390×844，CI 未配置明确显示，不出现合并按钮。
- `EXT-1-delivery.json`、`candidate-packet.json`：从真实 HTTP 导出的合成任务。后者含临时 Git 项目的真实本机构建/单测记录；业务为 VALUE 常量演练，不是退款正确性证明。

GitLab/Gitea 使用协议夹具，无客户服务账号和真实 CI 环境；Jenkins 尚未适配。下载包是保存记录，当前有效性保留未知，不可作为批准凭证。浏览器首次启动进程未持久化导致连接拒绝，调整测试进程生命周期后检查成功；没有修改产品来隐藏失败。
