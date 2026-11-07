# Windows 离线运行包

这是可解压启动的 Windows x86_64 服务端包。原来的 `tmh offline-pack` 仍是项目工具/模板资料包，两者用途不同。本轮不制作 Docker 交付镜像。

解压后先运行 `check.cmd`，再运行 `start.cmd`，访问 `http://127.0.0.1:8790/`。停止时在启动窗口按 Ctrl+C。默认数据保存在 `%LOCALAPPDATA%\Webuddy\data`，与程序分开。程序启动沿用现有数据恢复与权限规则。

包内有独立 Python、Webuddy、MCP/server 依赖，以及官方 Windows Codex、Claude Code、PortableGit、Node。Python 固定使用包内版本；其余工具先按本机 PATH 检测，仅缺失时使用包内版本。安装失败或损坏的本机工具会报错，可通过外部配置明确选用包内或其他可执行文件。不会全局安装、覆盖旧版本、改注册表或系统 PATH。

工具 `--version`、网页启动、实际模型访问、项目执行沙箱是不同验证。本包不含模型权重、账号、登录态或密钥。模型仍需现有官方账号或可达的内网服务。项目自己的数据库、JDK、npm 依赖等需按项目准备。

## 配置与工具

复制包内 `config.example.json` 到包外：

```json
{
  "data_dir": "D:\\Webuddy数据",
  "host": "127.0.0.1",
  "port": 8790,
  "environment": {
    "TMH_TOKEN_FILE": "D:\\Webuddy配置\\token.txt"
  },
  "tools": {}
}
```

```bat
webuddy.cmd --config "D:\Webuddy配置\local.json" check
webuddy.cmd --config "D:\Webuddy配置\local.json" start
webuddy.cmd tool codex login
webuddy.cmd tool claude
```

也可通过 `WEBUDDY_CONFIG` 指定文件。`environment` 继承并覆盖当前进程环境，值为字符串；支持既有模型环境和 `TMH_*` 设置。`tools` 可设置 `codex/claude/git/node` 的绝对可执行文件路径。服务不会把这些选择写回 `agents.json`，现有项目路由和独立执行器配置继续有效。详情见[外部配置说明](deployment-config.md)。真实配置与令牌不能加入 Git 或重分发包。

初次使用的本地模式沿用原平台规则。需要账号、多租户时先执行包内 `runtime\python\python.exe -m tmh access-init --help`，按现有初始化流程配置；MCP 使用包内 `runtime\python\python.exe -m tmh.workbench` 和现有连接配置，scope、执行开关、租户与项目权限不变。

每次 check/start 都先核对运行文件 SHA256；检查本身不创建业务数据、不读取秘密文件、不开始计划或模型任务。同一数据目录的包内启动器使用现有 Windows 命名互斥锁，重复启动会拒绝。它不取代既有运行监管与停止回执。

## 构建与来源

构建机需 Python 3.11+、pip 和 `7zz`。用户运行机器无需安装这些构建工具。固定第三方来源、版本、长度和 SHA256 在 `scripts/deploy/windows-offline/payloads.lock.json` 中；依赖 wheel 先按官方 PyPI 摘要核对，Codex/Claude 的 npm 包按 registry integrity 核对，Git/Node 按上游摘要核对。Python 来自官方 HTTPS 下载并固定哈希。工具原始配套文件和许可保留，不运行 npm postinstall。

```sh
python3 scripts/deploy/build-package.py --ref <固定提交> --out /tmp/webuddy-wheel
python3 scripts/deploy/build-windows-offline.py \
  --wheel-release /tmp/webuddy-wheel/<提交前12位> \
  --cache /tmp/webuddy-windows-downloads \
  --out /tmp/webuddy-windows-release
```

首次构建在线取回锁定文件，后续加 `--cache-only` 可完全离线重建。不会覆盖已有输出目录；缓存有损坏会报错，不静默覆盖。包内 wheel 按原始文件展开，不生成带构建机路径的 pip 启动器。若将来依赖 wheel 引入 `.data` 安装规则，构建会明确拒绝，需先补充相应安装处理与验证。

输出含 ZIP、整个 ZIP 的 SHA256/长度回执和使用说明；ZIP 内有 `release.json`、第三方来源锁和逐文件清单。用户应先核对可信渠道提供的 ZIP 哈希，再解压运行；内置清单用于检查损坏，不是代码签名。

## 验证、升级和回退

本机单元回归：`python3 -m unittest tests.test_windows_offline_bundle tests.test_deployment_config`。

实际 Windows 检查：使用包内 Python 执行 `scripts/deploy/test-windows-offline.py <解压后的Webuddy目录>`。它只建立独立合成数据，验证原始文件、中文/空格路径、工具复用与缺失回退、损坏拒绝、HTTP 鉴权、重复启动防重、受监管回收、重启读回和数据库完整性。`--expect-network-blocked` 要求测试管理员预先用 Windows 防火墙阻止测试程序出站，并在 finally 中清理临时规则；脚本不自行改防火墙，不调用模型或真实业务。

更新时停止旧服务，备份整个数据目录与包外配置，解压到新目录，显式指定同一数据目录。数据迁移仍由原平台负责；不能用本包覆盖线上数据库。回退只切换兼容程序，不能恢复旧库覆盖新写入。原 Windows 全量测试的已知限制仍保留，针对本包的启动检查不代表全量平台或客户项目验证通过。最新实际结果见进度记录和交付回执。
