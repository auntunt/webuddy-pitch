# 43 Webuddy 开发测试环境

默认开发、修复和功能迭代发布到 https://webuddy.bbstack.date。阿里云 https://webuddy.cloudwaveai.cn 是生产，只有用户明确要求发布里程碑时才更新。

- 主机：ubuntu@43.153.76.85；系统级 `webuddy.service`，`systemctl` 管理，需要现有 sudo 权限。
- 接入前读取本机 `~/.codex/memories/webuddy-production-access.md`，核验密钥授权和主机身份。不要在仓库保存私钥或环境变量内容。
- 当前代码：`/opt/webuddy/app` → `/opt/webuddy/releases/0bdc135/app`。后续以实际链接、RELEASE.json、MANIFEST.json 和进程 cwd 为准。
- 数据：`/opt/webuddy/data`、`/opt/webuddy/repos`；外部配置 `/etc/webuddy.env`，Codex `/home/ubuntu/.codex`。保留43的独立数据与账号，不从阿里云复制覆盖。
- 运行环境：系统 Python 3.12.3；全局工具 `/home/ubuntu/.local/bin/tmh` 调用当前 app 的 tmh.py，版本0.4.0。现有Codex0.162.1的真实MCP测试机调用已经验证，无需为此次同步升级。
- HTTP：应用127.0.0.1:8790；Caddy处理HTTPS。DNS A→43.153.76.85，DNS only；同一站点保留webuddy-us.bbstack.date。
- Windows执行机通过43:12022转发，是独立的应用测试执行机；与此Webuddy测试站区分。

发布先核验精确提交清单、测试和数据库副本兼容性。复用root所有的 `/opt/webuddy/.release.lock`，确认无queued/running任务后停服务，完整备份data/repos/Codex及外部配置，保留旧程序，再原子切换app链接并启动。回退只切程序，不用旧数据库覆盖新写入。

上线后检查运行cwd/版本/清单、数据库完整性、内外登录及权限，并在60秒后核验状态。记录类提交不重复重启。2026-11-05系统提示service文件磁盘时间变化；本次只按现有已加载服务重启，未变更服务单元或对其他服务执行daemon-reload。
