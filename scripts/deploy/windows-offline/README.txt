Webuddy Windows x64 离线运行包

适用：Windows 10/11 x64。本包不支持 Windows ARM、Windows 7、WSL 或 Linux。

1. 将整个 ZIP 解压到本地可写目录（例如 D:\Webuddy）。不要在 ZIP 内直接启动。
2. 双击 check.cmd，核对文件完整性、实际使用的工具和数据目录。
3. 双击 start.cmd，在浏览器打开 http://127.0.0.1:8790/ 。
4. 停止：在启动窗口按 Ctrl+C，等待“已停止”。不批量结束系统 Python/Node 进程。

安装和启动不会下载文件、安装全局软件、改注册表或全局 PATH。
Python 使用包内独立版本。Codex、Claude Code、Git、Node 优先复用 PATH 中已有安装，
缺少时使用包内官方版本。检测到已有工具损坏会明确报错，不悄悄替换。
check 只检查可执行文件和配置；不证明模型已登录或项目沙箱已经可用。
本包保留 Codex 的 sandbox/setup 等配套文件，不关闭已有平台权限或沙箱。

数据默认在 %LOCALAPPDATA%\Webuddy\data，关闭窗口或换包后保留。
启动已有数据目录会沿用平台的持久调度、恢复与授权规则。首次试用请用新数据目录。
升级前停止服务，完整备份数据与外部配置；回退程序不能用旧库覆盖新的业务写入。
本包不会自动迁移服务器数据，也不会覆盖原 ~/.tmh、agents.json、Codex 或 Claude 配置。

外部配置：复制 config.example.json 到包外，按需设置后运行：
  webuddy.cmd --config "D:\Webuddy 配置\local.json" check
  webuddy.cmd --config "D:\Webuddy 配置\local.json" start
也可以设置 WEBUDDY_CONFIG 环境变量再双击 start.cmd。
config 字段：data_dir、host、port、environment、tools。
相对 data_dir 相对于当前工作目录；建议使用绝对路径。
tools 中可以填写 codex、claude、git、node 的完整可执行文件路径。
environment 中填写所需环境变量（值为字符串），或从启动终端继承。
例如 TMH_TOKEN_FILE、CODEX_HOME、ANTHROPIC_BASE_URL、ANTHROPIC_API_KEY。
TMH_TOKEN 与 TMH_TOKEN_FILE 只能设置一个，文件中的值不会打印。
对局域网开放使用 host=0.0.0.0，并按现有平台要求配置访问令牌/租户权限。
不要将真实配置、账号或令牌发给他人、打入包或提交 Git。

本地官方客户端入口（仅改变当前进程的工具路径）：
  webuddy.cmd tool codex --version
  webuddy.cmd tool codex login
  webuddy.cmd tool claude --version
  webuddy.cmd tool claude
  webuddy.cmd tool git --version
在原有 Codex / Claude 账户与配置中完成登录或内网模型配置。
模型调用需要可达的服务和有效授权；“离线安装”不代表本地自带模型或免登录。
网页中的项目执行、人工验收及自动验收开关沿用原有规则，不因离线包扩大权限。
项目自己的 JDK、数据库、npm 依赖等仍按该项目准备，不包含所有业务项目依赖。

本地单实例网页默认沿用原平台行为。需要账号/多租户时先使用现有初始化入口：
  runtime\python\python.exe -m tmh access-init --help
MCP 依赖已在包内，连接到已部署服务仍用现有 webuddy 配置与权限：
  runtime\python\python.exe -m tmh.workbench --help

版本与来源见 release.json、payloads.lock.json。
MANIFEST.json 记录每个运行文件的 SHA256，check/start 每次检查后才继续。
它检测损坏，不代替可信分发：下载后请同时核对包外 bundle.json 的整个 ZIP 哈希。
licenses 与各工具目录保留上游许可；第三方工具受各自使用条款约束。
本包只交付 Windows 程序，不更新测试站或生产服务器。
