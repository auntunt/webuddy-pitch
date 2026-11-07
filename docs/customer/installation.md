# 安装、配置与升级

## Windows x64 启动

将完整 ZIP 解压到本地可写目录，例如 `D:\Webuddy`。不要在压缩软件内直接运行。先双击 `check.cmd`，检查通过后双击 `start.cmd`，访问 <http://127.0.0.1:8790/>。

Python 使用包内运行环境。Codex、Claude Code、Git 和 Node 优先复用 PATH 中的本机工具，缺少时使用包内版本。已安装工具损坏时会拒绝，不自动覆盖。启动器仅修改当前进程树的环境，不修改系统 PATH 或注册表。

在启动窗口按 Ctrl+C 停止，等待服务退出。不要批量结束系统 Python 或 Node 进程。重复启动同一数据目录会被拒绝。检查只证明文件与工具入口可用，不能证明模型登录或项目执行沙箱可用。

## 数据与配置

默认业务数据位于 `%LOCALAPPDATA%\Webuddy\data`，不在发行包内。把 `config.example.json` 复制到包外后按需设置：

```json
{
  "data_dir": "D:\\Webuddy数据",
  "host": "127.0.0.1",
  "port": 8790,
  "environment": {"TMH_TOKEN_FILE": "D:\\Webuddy配置\\token.txt"},
  "tools": {}
}
```

```bat
webuddy.cmd --config "D:\Webuddy配置\local.json" check
webuddy.cmd --config "D:\Webuddy配置\local.json" start
```

也可设置 `WEBUDDY_CONFIG` 后运行 start.cmd。`tools` 可指定 codex、claude、git、node 的绝对可执行文件路径。`environment` 中的值须为字符串，继承并覆盖启动终端的环境；不把这些值写回项目配置。

真实令牌、账号和模型配置由客户另行管理。`TMH_TOKEN` 与 `TMH_TOKEN_FILE` 只能设置一个。对局域网开放须按现有服务规则配置访问令牌或租户账号，并选择所需 host；不关闭权限检查。

## 模型与 MCP

```bat
webuddy.cmd tool codex login
webuddy.cmd tool claude
runtime\python\python.exe -m tmh.workbench --help
```

模型需要获准账号或内网服务。MCP 使用服务签发的个人工具凭据，保存在发行目录外，通过 credential-file 引用；不把凭据正文写进命令行。read/content/execute/develop 的实际权限仍受连接 scope、客户端执行开关、租户、项目及当前授权限制。MCP 不提供代人验收、人工批准或生产发布权限。

本地项目知识 MCP 可用包内 Python 执行 `-m tmh mcp --repo "项目绝对路径"`。项目生成的 Claude/Codex 配置及钩子需要可解析的 Python3 与相应 shell；本包不修改系统工具配置，可显式配置包内 Python/Git Bash。原生 Windows 多租户 worker 使用边界与平台现有实现一致，不将 POSIX worker 支持宣称为 Windows 已支持。

## 升级与回退

1. 停止旧服务，完整备份业务数据、外部配置及账号配置。
2. 将新包解压到新目录，先运行 check，显式指向原数据目录。
3. 按既有数据库兼容和迁移规则启动；检查原数据、项目及权限后再投入使用。
4. 需要回退时切换兼容程序；不能用旧数据库覆盖升级后的业务写入。

MANIFEST.json 给出逐文件 SHA256，check/start 在继续前检查。包外完整性回执提供整个 ZIP 的哈希，应从可信分发渠道核对。清单检测损坏，不代替代码签名。


## 首次构建与测试

默认使用安装 Webuddy 的机器执行项目检查，无需另配 SSH。进入“设置 → 构建与测试位置”检查平台进程可找到的工具；这只是工具清单，测试结论以项目运行回执为准。安装包不包含所有业务项目的依赖，仍须配置该项目的测试命令、数据和必要工具。

需要另一台机器时，在同一位置选择“另一台机器（SSH）”，填写地址或 SSH 配置别名，保存后检查连接。已有远程配置保留，连接失败不会切回本机。项目测试配置中的执行位置优先于默认设置。切换配置后应重新检查环境、重新运行受影响验证，旧回执保留为历史。

主导航“改造计划”可进入计划列表，项目页面也提供直接入口。Java 迁移与信创适配复用现有计划及运行证据；专业技能随项目初始化安装，已初始化的项目需按现有更新流程刷新技能。业务规则、源与目标映射、差异测试和回退条件应进入计划及证据，技能模板不代表测试通过或人工验收。
