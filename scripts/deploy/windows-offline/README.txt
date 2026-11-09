Webuddy 标准 Windows 安装程序

如果使用 Webuddy-Setup-<版本>-x64.exe：
双击并按安装向导完成；使用桌面 Webuddy 图标启动，开始菜单“退出 Webuddy”停止。
默认按当前用户安装，无需手动构建或运行 PowerShell。选择局域网访问时由向导请求管理员权限。
Cursor CLI 选项复用本机安装，缺少时联网运行官方安装程序；首次认证使用开始菜单“登录 Cursor”。
升级时再次运行安装程序，配置和数据保留；卸载同样保留数据。正在执行任务时先在网页停止或等待完成。
包内不含个人账号或凭据。模型服务需要目标电脑上的有效登录和网络连接。

以下说明仅适用于单独下载的便携 ZIP：

Webuddy Windows x64 客户离线运行包

适用：Windows 10/11 x64。本包不支持 Windows ARM、Windows 7、WSL 或 Linux。

1. 将整个 ZIP 解压到本地可写目录（例如 D:\Webuddy）。不要在 ZIP 内直接启动。
2. 双击 start.cmd 启动。默认开启局域网访问：启动窗口会打印“本机地址”和“局域网地址”
   （都带访问令牌），用浏览器打开即可；其他电脑打开“局域网地址”。
3. 打开网页 设置 → 智能体：点击“扫描本机”自动发现 Codex / Claude Code / Cursor
   （命令路径、配置目录、模型与 API 地址），按结果点“采用”；需要密钥时在
   “连接配置”里填写并点“测试连接”。
4. 其他电脑连不上时，以管理员身份运行一次 configure-firewall.ps1（或在 Windows 防火墙
   提示时允许 Python）。只想本机访问：在 设置 → 访问方式 选“仅本机”，保存后重启 Webuddy。
5. 停止：在启动窗口按 Ctrl+C，等待“已停止”。不批量结束系统 Python/Node 进程。

安装和启动不会下载文件、安装全局软件、改注册表或全局 PATH。
Python 使用包内独立版本。Codex、Claude Code、Git、Node 优先复用 PATH 中已有安装，
缺少时使用包内官方版本。检测到已有工具损坏会明确报错，不悄悄替换。
check.cmd 打印文件清单核对结果、实际使用的工具和数据目录；不一致只提示，不阻止启动。

数据默认在 %LOCALAPPDATA%\Webuddy\data，访问方式等设置保存在
%LOCALAPPDATA%\Webuddy\config.json，解压新版本到其它目录后仍生效。
启动已有数据目录会沿用平台的持久调度、恢复与授权规则。首次试用请用新数据目录。
本包不会自动迁移服务器数据，也不会覆盖原 ~/.tmh、agents.json、Codex 或 Claude 配置。

Cursor Agent：本包支持调用本机 agent 命令（兼容 cursor-agent），不内置 Cursor CLI 安装包或账号。
check.cmd 会显示 Cursor 检测结果；未安装不影响其他执行器启动。
  webuddy.cmd tool cursor --version
  webuddy.cmd tool cursor login
仅安装 Cursor 编辑器不等于已安装 CLI；请在运行 Webuddy 的同一系统账号完成登录。
设置页中的 Cursor 支持分析与获准的修改任务。只读任务使用 Ask 模式；
Windows 下 Cursor 沙箱按客户批准关闭；仍须满足项目执行权限、需求确认、候选验证和人工验收门禁。
不自动批准工作区信任或 MCP 服务。真实 Cursor 模型与客户设备调用须按现场实际结果核对。

高级用法（可选）：包外 JSON 配置仍可用 ——
  webuddy.cmd --config "D:\Webuddy 配置\local.json" start
或设置 WEBUDDY_CONFIG 环境变量。字段：data_dir、host、port、environment、tools。
本地网页与项目命令支持 Windows；多租户 worker 依赖 Unix socket，需部署到受支持的服务端，
Windows 客户端可通过 MCP 连接该服务端。
升级：先停止旧包并备份外部数据/配置，再解压新包到新目录后双击 start.cmd；
保留旧包；回退仅切程序目录，数据库变更须按对应版本的兼容说明核对。
