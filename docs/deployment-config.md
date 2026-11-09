# 安装包与外部配置

本轮整理服务端包、个人客户端包、离线包和外部配置，为后续 Docker 镜像做准备。镜像制作、容器替换和真实数据迁移不在本轮交付中。

## 包的用途

| 产物 | 包含内容 | 用途 |
|---|---|---|
| `tmh-harness` wheel | CLI、服务端、状态图 JS / 许可证、项目测试 CJS、技能与模板等必需资源 | 服务端或项目工具安装 |
| `tmh-harness[server]` | 上述包及 cryptography、pypdf | 明确安装证据签名和 PDF 提取依赖 |
| `tmh-harness[mcp]` | 上述包及官方 MCP SDK 1.x | 需要 stdio MCP 能力的环境 |
| 网站下载的 `webuddy-client` wheel | 现有个人客户端模块，不含服务端、业务数据或凭据 | Codex / Claude Code / Cursor 个人连接 |
| `tmh offline-pack` | 工具、模板、技能、知识库及完整资源清单 | 内网项目离线安装与刷新 |
| `scripts/deploy/pack.sh` | 历史 JeecgBoot / RealWorld 完整运行数据迁移包 | 私有迁移备份，不能作为镜像或公开程序包 |

服务端和下载的个人客户端使用独立虚拟环境。两者共享 `tmh` 模块名，在同一环境混装不同版本会覆盖公共模块；服务端包已有 CLI，不必再安装个人客户端包。

安装示例：

```sh
python -m venv /opt/webuddy/venv
/opt/webuddy/venv/bin/python -m pip install 'tmh-harness[server,mcp]'
```

实际发布安装经过验证的固定 wheel，而不是把上面的示例当作某个私有源已发布的证明。`server` 和 `mcp` 都是可选依赖组，不改变原基础 CLI 的依赖。Node、Java、模型 CLI、浏览器与项目执行工具仍由实际执行环境配置，安装服务端包不等于这些能力可用。

## 从固定提交构建干净安装包

```sh
python scripts/deploy/build-package.py --ref <完整提交号> --out /private/release-packages
```

脚本从指定 Git 提交导出程序和必需资源，在全新临时目录构建 wheel。未提交改动、本地旧 `build/`、缓存和运行数据不参与构建。输出独立的提交目录、wheel 及含提交号、SHA-256 和字节数的 `release.json`；已有目录拒绝覆盖。构建后逐字节检查状态图 JS、许可证与项目测试 CJS。

构建环境需具备 pip 和构建依赖；该命令构建程序包，不导出配置、账号或业务数据，也不制作 Docker 镜像。发布前继续在源码目录之外安装并运行 `scripts/installed-smoke.py`，不能只看 wheel 文件存在。

## 程序、配置与数据的边界

| 内容 | 当前来源 | 更新方式 |
|---|---|---|
| 程序与静态资源 | 安装包 / 版本目录 | 换经过验证的程序包 |
| 数据目录 | `--data`；未指定时 `TMH_DATA_DIR`，再默认 `~/.tmh/platform` | 管理员指定路径；保留完整持久目录 |
| 站点环境变量 | 服务管理器的 EnvironmentFile / env；后续容器的 env_file | 修改后重启服务，重新读取 |
| 模型执行器与路由 | 数据目录内 `agents.json`、`agent-routes.json` | 现有管理入口或私有文件 |
| 自动流转与测试机 | `autoflow.json` | 沿用现有字段和权限，不扩大 AI 验收或执行授权 |
| 项目测试 | `project-tests.json` | 保留现有校验、修订与证据失效规则 |
| 价格显示、诊断数据源、告警 | `pricing.json`、`datasources.json`、`alerts.json` | 沿用对应模块；手工改价格需重启实例 |
| 工单、计划、批次、运行、证据、账号、租户与会话 | 数据目录及其子目录 | 完整备份与持久化，不打入程序包 |
| Codex / Claude / SSH 等执行环境配置 | 现有 HOME、CODEX_HOME、CLI profile 与项目配置 | 保留私有文件和权限；不导出到 Git |

JSON 继续与持久数据目录共用一套配置来源。没有新增一个覆盖网页写入的平行只读配置目录。网页需要原子替换的 JSON 不宜作为单个只读文件挂载；后续容器化应挂载完整数据目录并准备正确权限。

项目数据库里保存的绝对根路径、模型 CLI 路径、测试命令和 SSH 路径不会被自动重写。迁移时必须逐项核对新环境是否可访问；不能把旧路径悄悄换成当前目录或 HEAD。

## 站点环境示例

将 `config/webuddy.env.example` 复制为私有的 `config/webuddy.env`，设置真实值并限制为600权限。应用不自动加载 `.env`；由 systemd 等服务管理器加载。Git 忽略真实 `config/*.env`，示例文件只包含占位值。

| 变量 | 作用与默认值 |
|---|---|
| `TMH_DATA_DIR` | `serve`、`user`、`access-init`、配置检查等命令共用的数据目录默认值 |
| `TMH_HOST` | 服务默认监听地址，原默认 `127.0.0.1` 保留 |
| `TMH_PORT` | 默认监听端口，原默认 `8790` 保留 |
| `TMH_BRAND` | 站点名称，默认 webuddy |
| `TMH_PUBLIC_URL` | 真实对外地址，用于分享和客户端绑定 |
| `TMH_TOKEN` 或 `TMH_TOKEN_FILE` | 单实例对外监听访问令牌；租户模式仍走既有账号、连接与授权 |
| `TMH_FEISHU_APP_ID` | 可选飞书应用 ID |
| `TMH_FEISHU_APP_SECRET` 或 `TMH_FEISHU_APP_SECRET_FILE` | 可选飞书应用密钥 |
| `TMH_FEISHU_TENANT_KEY` | 可选企业限制，沿用原规则 |

显式 CLI 参数优先于环境变量，环境变量优先于原默认值。服务原来已经带 `--data /opt/webuddy/data` 时，新增环境变量不会覆盖该参数。

`tmh serve` 启动前读取支持的 `_FILE` 密钥。每种密钥只能提供直接值或文件之一；同时设置、空文件或无法读取均拒绝启动，且不输出内容。只去掉文件末尾换行。服务内部继续使用原环境变量，未另存密钥、改变凭据绑定或授予执行权限。

## 只读配置检查

```sh
tmh deployment-check --data /path/to/platform-data
# 也可先由服务管理器设置 TMH_DATA_DIR，再调用同一命令。
```

检查上述七个 JSON 文件的语法和顶层对象类型。输出文件名和状态：`not_configured`、`valid_object`、`invalid_json`、`invalid_type`、`unreadable`；语法错误带行列号。原内容不输出、不修改，不创建缺失目录，不读取 `_FILE` 密钥，也不启动模型或进程。全部符合时退出0，错误时退出2。

`valid_object` 仅表示通过该基础检查，不表示业务配置、项目根路径、执行器、网络和权限均已验证。新命令不替代各业务模块的严格校验；原生服务不会因为新增这个手动检查而无声改变旧 JSON 的加载规则。

## 清理与后续容器化

本轮清理的是包边界与构建输入，不删除用户数据、旧证据、原图、现役虚拟环境和发布备份。服务端 wheel 补齐缺失的状态图 vendor JS 和许可证；安装回归在源码目录之外实际读取渲染器，防止“源码可用、安装后缺文件”。

`.dockerignore` 为后续构建准备程序及必需资源允许列表，排除 Git、运行数据、测试证据、截图、旧部署包、缓存和私有环境文件；排除不删除原文件。Docker 草稿和早期未验收试构建另存本地，不作为本轮镜像交付。

后续制作镜像时再验证实际构建上下文、非 root 权限、数据卷、停止回执、重启接续、已登录租户、真实 MCP 和依赖平台；不能仅凭 `/login` 返回200宣布整个站点可用。真实迁移必须避免两个实例同时写同一数据目录，回退只切兼容程序，不以旧数据库覆盖新写入。
