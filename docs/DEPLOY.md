# 部署手册（Webuddy / tmh 运维平台）

面向**专用机器直接部署**：Linux 服务器上从分支拉代码、装 Python 依赖（零第三方运行时依赖）、起服务、
Caddy 反代、systemd 托管，并给出备份/升级/回滚/冒烟/安全清单。

- 目标运行环境：**Tencent Cloud Linux**（Ubuntu 22.04 / 24.04 或同代 CentOS/OpenCloudOS 均可），Python **3.12.3**。
- 本仓库运行时**没有第三方依赖**（`pyproject.toml` 的 `dependencies = []`）；`pyproject.toml` 声明
  `requires-python >= 3.8`，但生产/CI 目标是 3.11–3.12，3.8 仅保证语法兼容。
- 唯一可选依赖是 **MCP**：`pip install ".[mcp]"`（需要 `mcp>=1.30`，仅使用平台/工作台的 stdio MCP 时才需要）。
- 平台数据默认在 `~/.tmh/platform`（`tmh serve --data` 可改），项目数据在各项目目录的 `.tmh/` 下。

> 约定：本文命令以 `deploy` 用户、`/opt/webuddy` 目录、域名 `webuddy.example.com` 为例；按实际替换。
> 所有写入敏感信息（令牌/密码）的文件权限设为 `600`，且**不要提交进 git**。

## 1. 部署前置

| 项 | 要求 | 检查命令 |
|---|---|---|
| 操作系统 | Linux x86_64（生产目标）；Windows 仅开发/测试 | `uname -a` |
| Python | 3.10+（建议 3.12.3）；`venv`、`ensurepip` 可用 | `python3 --version` |
| git | **≥ 2.38**（平台的分支/工作树操作依赖新版 git） | `git --version` |
| SSH 客户端 | `openssh-client`（智能体在独立工作树里改代码、离线包校验用） | `ssh -V` |
| 端口 | 平台默认 `127.0.0.1:8790`；预览端口默认自动分配（`--preview-port` 可固定 8791–8799） | `ss -ltnp` |
| 磁盘 | 数据目录至少预留 10 GB（SQLite + 工作树 + 日志） | `df -h` |
| 内存 | 建议 ≥ 4 GB（智能体运行时另算） | `free -m` |
| 反代 | Caddy 2.x（示例），或 nginx | `caddy version` |
| 智能体（可选） | Claude Code / Codex 命令在部署用户 PATH 上并已登录；否则平台“分析/改代码”按钮不可用 | `claude --version`、`codex --version` |

不要用 root 直接跑 `tmh serve`：建一个专用用户（示例 `deploy`），把数据/仓库目录归它所有。

```sh
sudo useradd -m -s /bin/bash deploy
sudo mkdir -p /opt/webuddy && sudo chown deploy:deploy /opt/webuddy
```

## 2. 安装

### 2.1 拉分支 + venv + `pip install .`

```sh
sudo -u deploy -i            # 之后都用 deploy 用户
git clone -b iteration/context-pack-v2 https://github.com/auntunt/webuddy-pitch.git /opt/webuddy/app
cd /opt/webuddy/app
git log -1 --oneline         # 记录发布提交，回滚要用

python3 -m venv /opt/webuddy/venv
. /opt/webuddy/venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .                 # 运行时零依赖；只装 tmh 包本身
# 需要平台/工作台 MCP 时再装：python -m pip install '.[mcp]'
```

安装后验证 CLI 入口：

```sh
tmh --version            # 必须输出 0.4.0
webuddy --help | head     # workbench CLI 存在
python -c "import tmh; print(tmh.__version__)"
```

### 2.2 源码直跑（不安装，适合排障/离线）

```sh
cd /opt/webuddy/app
python3 tmh.py --version     # 仓库根有 tmh.py 入口
python3 -m tmh --version
```

> `pip install .` 会把包装进 venv 的 site-packages；**源码直跑走仓库目录**。两种方式不要混用同一个数据目录
> 排查不同代码版本时，建议用 `--data` 指向不同目录。

## 3. 初始化平台数据与账号

```sh
cd /opt/webuddy/app
export TMH_BRAND="Webuddy"              # 界面产品名，可改
export TMH_PUBLIC_URL="https://webuddy.example.com"   # 对外地址；上线体检用，见 §7

# 1) 建平台数据目录（首次运行会自动初始化 SQLite）
mkdir -p /opt/webuddy/data
# 2) 建登录账号（管理员）：密码至少 8 位；--password-stdin 便于脚本
printf '%s\n' 'YOUR_STRONG_PASSWORD' | tmh user add admin --data /opt/webuddy/data --password-stdin
tmh user list --data /opt/webuddy/data
```

- 平台默认 **只监听本机** `127.0.0.1:8790`；对外由 Caddy 反代（§5）。
- 如需平台直接监听 `0.0.0.0`，必须先设置随机令牌：`TMH_TOKEN=$(python3 -c 'import secrets;print(secrets.token_hex(16))')`，
  否则服务会拒绝向外网开放。**推荐一律只用 Caddy 反代 + 本机监听**，不直接暴露 8790。
- 有账号后网页登录走 `/login`（表单字段 `username/password/next`，成功后下发 `tmh_session` cookie）。
- 项目登记：`tmh serve` 启动时若当前目录有 `.tmh/` 会自动登记；其他项目在网页“添加项目”填目录。
  也可显式：`tmh serve --data /opt/webuddy/data --project /srv/legacy-project --key TOG`。
- 自动处理（智能体自动跑）默认关闭，需要时在网页“设置”里开，避免一上线就消耗额度。

启动（先手动跑通，再交给 systemd）：

```sh
tmh serve --host 127.0.0.1 --port 8790 --data /opt/webuddy/data --brand "$TMH_BRAND"
# 另开终端验证
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8790/login   # 期待 200
```

## 4. systemd

`/etc/systemd/system/webuddy.service`：

```ini
[Unit]
Description=Webuddy (tmh serve)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=deploy
Group=deploy
WorkingDirectory=/opt/webuddy/app
Environment=PATH=/opt/webuddy/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUTF8=1
Environment=PYTHONIOENCODING=utf-8
Environment=NO_PROXY=127.0.0.1,localhost,::1
Environment=no_proxy=127.0.0.1,localhost,::1
Environment=TMH_BRAND=Webuddy
Environment=TMH_PUBLIC_URL=https://webuddy.example.com
EnvironmentFile=-/etc/webuddy.env
ExecStart=/opt/webuddy/venv/bin/tmh serve --host 127.0.0.1 --port 8790 --data /opt/webuddy/data
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
# 数据和仓库都在 /opt/webuddy 下，限制可写范围（可选加固）
ReadWritePaths=/opt/webuddy
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

`/etc/webuddy.env`（**权限 600，不要进 git**）：

```sh
# 只放机密；非机密的 TMH_BRAND 等已写在 unit 里
# TMH_TOKEN=            # 只有在 --host 0.0.0.0 时才需要
# 通知集成（按需）：TMH_WECOM_* / TMH_DINGTALK_SECRET / TMH_FEISHU_*
```

启用：

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now webuddy
systemctl status webuddy --no-pager
journalctl -u webuddy -n 100 --no-pager      # 启动失败先看这里
```

> 智能体（claude/codex）由平台以部署用户身份调用；确保 `deploy` 已登录过智能体 CLI，且 systemd 的
> `Environment=PATH` 里能找到它们（或把可执行文件软链到 `/usr/local/bin`）。

## 5. Caddy 反向代理（含 HTTPS）

`/etc/caddy/Caddyfile`：

```caddyfile
webuddy.example.com {
    encode zstd gzip

    # 上传/证据/截图可能较大；按需调大
    request_body {
        max_size 64MB
    }

    # 智能体运行、知识库构建是长请求，超时要放宽
    reverse_proxy 127.0.0.1:8790 {
        transport http {
            read_timeout 10m
            write_timeout 10m
            dial_timeout 10s
        }
        header_up X-Forwarded-Proto {scheme}
        header_up X-Real-IP {remote_host}
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }

    log {
        output file /var/log/caddy/webuddy-access.log {
            roll_size 50MiB
            roll_keep 5
        }
    }
}
```

```sh
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
curl -sI https://webuddy.example.com/login | head -20   # 期待 200 + 证书有效
```

- 证书：Caddy 自动申请/续期 Let's Encrypt（80/443 需可达）；内网无公网时用自签或内部 CA。
- 单独给预览版本开域名时，加一段 `pv.example.com` 反代到 `--preview-port`，并给服务设置
  `Environment=TMH_PREVIEW_BASE=https://pv.example.com`。
- 若前面还有一层云负载均衡/网关：把真实 IP 头透传，避免登录审计里全是 127.0.0.1。

## 6. 数据与备份

| 数据 | 位置 | 说明 |
|---|---|---|
| 平台库（工单/运行/项目） | `~/.tmh/platform/` 或 `--data` 指定目录（默认 `/opt/webuddy/data`） | 核心数据 `platform.db`（SQLite）；`agents.json`、`autoflow.json` 等 |
| 项目知识库/映射 | 各项目目录 `.tmh/` | `kb/`、`knowledge/`、`config.json`、`report/` |
| 证据签名密钥 | `--data` 目录下的 `signing_ed25519`（+ `.pub`） | **必须备份**；丢了旧证据包无法再签新记录 |
| 平台运行工作树 | `--data` 下 worktree/预览相关目录 | 可重建，但备份更省事 |
| 部署配置 | `/etc/webuddy.env`、`/etc/caddy/Caddyfile`、systemd unit | 不进 git，单独备份 |

备份建议（每天一次，停写或用 SQLite 在线备份）：

```sh
sudo -u deploy bash -c '
  set -euo pipefail
  dest=/opt/webuddy/backups/$(date +%F)
  mkdir -p "$dest"
  sqlite3 /opt/webuddy/data/platform.db ".backup '"'"'$dest/platform.db'"'"'"
  cp -a /opt/webuddy/data/agents.json "$dest"/ 2>/dev/null || true
  cp -a /opt/webuddy/data/signing_ed25519* "$dest"/ 2>/dev/null || true
  tar -czf "$dest/projects-tmh.tgz" -C /srv legacy-project/.tmh 2>/dev/null || true
'
```

没有 `sqlite3` 命令时可用 `python3 -c "import sqlite3;c=sqlite3.connect(...);c.backup(...)"`，或在维护窗口
`systemctl stop webuddy` 后直接 `cp`。备份包建议加密（含工单正文与客户信息），并异地保留至少 7 天。

## 7. 健康检查与 ops 冒烟

平台自身：

```sh
curl -s -o /dev/null -w 'login=%{http_code}\n' http://127.0.0.1:8790/login     # 200
curl -s http://127.0.0.1:8790/ | head -c 300                                   # 未登录应为登录页，不是 500
journalctl -u webuddy -n 20 --no-pager
```

发布检查脚本（本仓库自带）：

```sh
cd /opt/webuddy/app
bash scripts/release-check.sh            # 快速门禁；Linux 生产门禁
# 可选：pip install . 冒烟（在干净 venv 里验证打包）
INSTALL_SMOKE=1 bash scripts/release-check.sh
```

运维 `ops` 工具（独立于本项目仓库，见 `D:\DSH_project\ops\`；若已部署到服务器同目录则）：

```sh
node ops/ops.mjs dns  webuddy.example.com
node ops/ops.mjs tls  webuddy.example.com
node ops/ops.mjs http https://webuddy.example.com/login
TMH_USER=admin TMH_PASS=*** node ops/ops.mjs app login-check
node ops/ops.mjs evidence verify <工单号>       # 校验 /e/<key>.intoto.json 的哈希链与签名
TMH_USER=admin TMH_PASS=*** node ops/ops.mjs evidence verify <工单号> --anchor <签收页哈希>
```

平台“上线体检”页（设置里可打开）会检查智能体命令、最近运行、项目目录、签名密钥、磁盘；`bad` 项必须在
首个工单之前处理。

## 8. 升级与回滚

**升级前必做：备份（§6）+ 记录当前提交。**

```sh
cd /opt/webuddy/app
git log -1 --oneline | tee /opt/webuddy/backups/last-good.txt
# 1) 备份（同 §6）
# 2) 拉分支
git fetch origin
git status --porcelain            # 必须为空；有本地改动先停手
git checkout iteration/context-pack-v2
git pull --ff-only origin iteration/context-pack-v2
git log -1 --oneline
# 3) 重装到 venv
. /opt/webuddy/venv/bin/activate
python -m pip install --upgrade .
python -c "import tmh; print(tmh.__version__)"     # 必须等于 CHANGELOG 里的版本
# 4) 重启并冒烟
sudo systemctl restart webuddy
sleep 3 && systemctl is-active webuddy
curl -s -o /dev/null -w 'login=%{http_code}\n' http://127.0.0.1:8790/login
bash scripts/release-check.sh
```

**回滚**：代码回退到备份记录里的提交，重装并重启；数据不需要回滚时不要动 `--data`：

```sh
cd /opt/webuddy/app
git checkout <last-good-commit>
. /opt/webuddy/venv/bin/activate
python -m pip install --upgrade .
sudo systemctl restart webuddy
```

只有在升级确实改坏数据时才恢复备份：`systemctl stop webuddy` → 用备份覆盖 `platform.db`（及密钥）
→ `systemctl start webuddy`。恢复前把当前库另存一份，避免二次损失。

## 9. 安全清单（上线前逐项确认）

- [ ] 部署用户是专用 `deploy`，不是 root；`/opt/webuddy` 属主正确。
- [ ] `tmh serve` 只监听 `127.0.0.1`；对外只经 Caddy（443/80）。若确需 `0.0.0.0`，已设置 `TMH_TOKEN` 且高强度。
- [ ] 平台至少一个账号，密码 ≥ 8 位且非弱口令；离职/换人时 `tmh user del` 或改密。
- [ ] `/etc/webuddy.env`、`/etc/caddy/Caddyfile`、备份目录权限 600/700，不含明文密码提交到 git。
- [ ] 智能体 CLI 使用专用账号登录；不需要时关闭“自动处理”；确认额度告警方式。
- [ ] 项目目录只读挂载/只读账号运行（除平台工作树外不要让服务有写客户仓库的权限）。
- [ ] 防火墙只开 22/80/443 与必要运维口；云安全组同策略。
- [ ] 日志/备份含客户数据：加密备份、限制访问、定期清理；不要贴进工单正文。
- [ ] 证据签名密钥已备份；签收页哈希由客户记录。
- [ ] 升级流程与回滚人已明确；发布提交记录在案。

## 10. 常见问题

**Q1：Windows 上测试跑不全 / `os.O_NOFOLLOW` 报错？**
`tests/test_platform.py` 等少数用例按 Linux 设计（`os.O_NOFOLLOW`、符号链接、进程组），Windows 上会报
`AttributeError`/skip，属已知平台限制，不是本轮改动引入。生产门禁以 Linux 为准；本地开发用 WSL2 跑全量最接近。
`audit/ci-test-report.md` 记录了 Windows 失败分类。

**Q2：`git` 版本太老导致平台分支工作树/候选操作失败？**
平台大量使用 `git worktree`、`git merge-tree`、`show-ref` 等新行为。要求 **git ≥ 2.38**；
`git --version` 检查，Ubuntu 22.04 自带 2.34 偏老，建议官方 PPA 或源码安装。

**Q3：本机测试服务连不上 / 平台内部请求打到了代理？**
测试与预览服务都在回环地址。必须让 `127.0.0.1/localhost/::1` 绕过代理：
`NO_PROXY=127.0.0.1,localhost,::1`、`no_proxy` 同值（Windows 用 `$env:NO_PROXY`）。
另外统一 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，否则中文/emoji 固件在 Windows 代码页下会失败。

**Q4：`tmh` 命令找不到？**
`pip install .` 后入口在 venv 的 `bin/`；确认 `PATH` 或直接用 `/opt/webuddy/venv/bin/tmh`。
也可以用 `python3 tmh.py`（仓库根）或 `python3 -m tmh`。

**Q5：端口 8790 被占用？**
换 `--port 8795` 并同步改 Caddy 反代；或检查是否有残留进程 `ss -ltnp | grep 8790`。

**Q6：网页能开但点“分析/改代码”没反应？**
先看平台“上线体检”：智能体命令是否在 PATH、最近运行是否连续失败、额度/登录是否过期；再看
`journalctl -u webuddy` 与项目目录权限。

**Q7：证书没自动续上？**
Caddy 需要 80/443 可达；检查 `journalctl -u caddy`、DNS 是否指向本机；内网环境改用内部 CA 或
`tls internal`，并把相应根证书发给用户。
