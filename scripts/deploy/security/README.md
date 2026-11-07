# Webuddy 容器中的 Codex 沙箱

阿里云 Docker 26.1.3 的默认 seccomp 策略阻止了 Codex 0.162.1 / bubblewrap 创建用户命名空间。宿主机 `unshare -Ur true` 成功，而原容器内失败。本策略支持嵌套沙箱，同时保留默认拒绝策略和既有非特权用户。

## 策略来源和差异

基础文件原样保留 Moby v26.1.3 [default.json](https://github.com/moby/moby/blob/v26.1.3/profiles/seccomp/default.json)，原文件 SHA256 见交付记录；上游许可证在 LICENSE.moby。

只追加以下规则：

- `clone`：必须包含 `CLONE_NEWUSER`。
- `unshare`：参数必须恰为 `CLONE_NEWUSER`。
- `mount`、`umount2`、`pivot_root`：允许沙箱建立自己的挂载树，内核仍检查调用方所在用户命名空间的 capability。

逐项移除上述五类调用，均会在对应沙箱初始化步骤失败。`setns` 不需要，未开放。没有添加 `CAP_SYS_ADMIN`、privileged、seccomp=unconfined，也没有修改宿主机内核开关或关闭 Codex 沙箱。

## 验证与部署

先在同版本临时镜像运行 `scripts/deploy/verify_codex_sandbox.py`：不用模型，不挂业务卷或凭据。它调用真实 `codex sandbox` 检查读、工作区写、只读拒写、越界拒写、符号链接越界拒绝、Git元数据保护、TCP/Unix socket拒绝、无有效capability及seccomp启用。

```sh
docker run --rm -i --network=none \
  --security-opt seccomp=/absolute/path/seccomp-codex-docker26.json \
  --entrypoint python3 webuddy:9c6900b - < scripts/deploy/verify_codex_sandbox.py
```

通过后，将精确提交的策略复制到宿主机版本化路径，在 Webuddy 服务的 Compose 中加入：

```yaml
security_opt:
  - seccomp=./security/seccomp-codex-<commit>.json
```

部署前检查无运行中任务，完整备份数据卷、外部配置与旧 Compose。重建容器后再次执行同一沙箱检查和 HTTP/数据库健康检查。只改变此服务的策略；回退恢复旧 Compose 并重建容器，不恢复旧数据库。后续升级 Docker、Codex 或 bubblewrap 时，重新执行实机验证，不假定策略永久兼容。

参考：[Docker seccomp](https://docs.docker.com/engine/security/seccomp/)、[OpenAI 沙箱说明](https://learn.chatgpt.com/docs/sandboxing)。
