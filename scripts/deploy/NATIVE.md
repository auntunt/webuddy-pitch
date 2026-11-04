# 阿里云 Webuddy 原生部署

2026-11-05 起应用由 Liyibin 的用户级 `webuddy-native.service` 管理，linger 已启用。公网仍是 https://webuddy.bbstack.date。共享 Cloudflare Tunnel 容器继续服务其他站点，不应停止。

- 应用：`/opt/webuddy/app` → `releases/9c6900b`，精确版本由 RELEASE.json 和 MANIFEST.json 核对。
- Python：`/opt/webuddy/venv/bin/python3`（3.11.14）；tmh：`/opt/webuddy/bin/tmh`。
- 业务数据、仓库、Codex 配置：`/opt/webuddy/data`、`repos`、`codex`。服务 HOME 为 `/opt/webuddy/home`，`.codex` 链接到独立 Codex 配置目录。
- 外部环境：`/opt/webuddy/config/webuddy.env`，600，仅在服务器管理，不入库。
- 监听：`192.168.112.1:8791`（companions_tunnel 桥接网关），Cloudflare 只将 Webuddy ingress 指向此地址。其他 ingress 不变。
- 进程保持 UTC 存储；界面按 Asia/Shanghai 显示。不直接改变 TZ 混写历史无偏移时间。

## 后续发布

使用 `systemctl --user status/restart webuddy-native.service`，不再用 docker compose 更新应用。精确提交先打包到新 releases 目录，核对清单、原生兼容测试、数据库副本迁移和完整备份后，再切换 app 链接并重启。核验 HTTP、运行文件、数据库以及超过60秒的服务状态。记录更新不重启。

旧 webuddy 容器已停止，restart=no；原卷只保留用于回退，不再是现役数据。不要直接运行 `docker start webuddy` 或旧 Compose，以免启动旧数据的第二个实例。

## 回退到容器

1. 先停止原生服务，确认无残留任务进程。完整备份**当前** data/repos/codex 及配置；保留迁移前备份。
2. 在两端均停止时，将当前三个目录完整同步回原命名卷，含删除项、隐藏文件和链接，校验文件内容、数据库及会话密钥。卷属主恢复旧容器 UID1100；使用旧容器实际 GID。不要把旧快照覆盖到当前数据。
3. cloudwave-codex.bin 为可移植的 `codex`，原容器 PATH 可解析。核对环境、模型配置和全部项目根，再启动旧容器并验证原入口。
4. 只将 Cloudflare 的 webuddy.bbstack.date ingress 恢复到 `http://webuddy:8790`，保留其他项。确认公网健康后禁用原生服务自动启动，确保只有一个写入实例。

回退是程序切换与最新数据转移，不是恢复历史数据库。本说明不是已执行回退的证明。
