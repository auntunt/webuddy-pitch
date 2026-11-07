# Windows 云端完整结果：e282afab

同一候选、每个 Python 版本全部 307 个执行单元均有回执与 JUnit；没有超时或漏跑。以下按 `(classname, name)` 去重，调用与 teardown 的重复错误合并；完整原始记录数量另保存在 JSON。

| 环境 | 去重用例 | 通过 | 失败或错误 | 跳过 |
|---|---:|---:|---:|---:|
| GitHub Windows Python 3.11 | 3084 | 2340 | 129 | 615 |
| GitHub Windows Python 3.13 | 3084 | 2341 | 128 | 615 |

## 跳过的是什么

以下为 Python 3.11 的原始 skip 原因及数量（3.13 总数相同）。这是当前实现/既有测试条件，不是这些能力已经通过；本轮没有新增 skip。MCP SDK 和 cryptography 均已安装。

| 数量 | 原始原因 |
|---:|---|
| 48 | tenant gateway requires POSIX Unix sockets |
| 44 | supervised execution requires POSIX |
| 39 | 人工经验决定尚未验证 Windows 原子替换和目录 fsync；该平台明确拒绝写入 |
| 38 | private directory FDs and supervised HTTP transport require POSIX |
| 34 | requires POSIX process groups |
| 27 | requires POSIX supervision and local Git |
| 25 | existing supervised-process proof requires POSIX |
| 25 | private registry and supervised native HTTP require POSIX |
| 21 | private originals and actual supervised processes require POSIX |
| 21 | tenant workers require POSIX Unix sockets |
| 20 | private registry/real supervised loopback require POSIX |
| 20 | supervised private-fd transport requires POSIX |
| 17 | process-group lifecycle tests require POSIX |
| 16 | native private registry and supervised worker require POSIX |
| 14 | requires POSIX ownership leases |
| 13 | original process supervision requires POSIX |
| 13 | owner-only credential files require POSIX permission checks |
| 13 | private registry and real supervision require POSIX |
| 12 | original metered supervisor requires POSIX |
| 12 | real project builds require POSIX supervision and local Git |
| 10 | boundary snapshots require POSIX supervision and local Git |
| 9 | explicit temporary root-owned Linux FIFO/UID fixture |
| 9 | real library lifecycle requires POSIX supervision and local Git |
| 9 | requires POSIX owned process groups |
| 8 | requires POSIX owned process failure |
| 8 | requires real POSIX service-owner failure |
| 7 | integration builds require POSIX supervision and local Git |
| 7 | managed POSIX process lifecycle |
| 7 | private catalog and supervised loopback require POSIX |
| 6 | Linux cleanup directory-descriptor contract requires POSIX |
| 6 | explicit root-owned temporary Linux kernel fixture only |
| 5 | original metered provider needs POSIX |
| 4 | personal credential files require POSIX checks |
| 4 | tenant workers require POSIX sockets |
| 4 | 人工经验决定在 Windows 明确拒绝写入 |
| 3 | FIFO framing requires POSIX |
| 3 | existing supervisor requires POSIX |
| 3 | explicit temporary root-owned Linux typed evaluator fixture |
| 3 | native private registry and real file locks require POSIX |
| 3 | private workers require Unix sockets |
| 2 | real independent flock process requires POSIX |
| 2 | real inherited-fd process competition requires POSIX |
| 2 | requires POSIX process trees |
| 1 | POSIX cancellation |
| 1 | POSIX process group lifecycle |
| 1 | POSIX shared reader semantics |
| 1 | actual native fixture requires POSIX |
| 1 | credential files require POSIX permission checks |
| 1 | fixture requires unprivileged POSIX symlink creation |
| 1 | personal tenant stdio requires POSIX and optional MCP SDK |
| 1 | real inherited socket barrier requires POSIX pass_fds |
| 1 | real killed-owner proof is POSIX-only |
| 1 | real local library build uses POSIX supervision |
| 1 | requires POSIX fork |
| 1 | requires the real POSIX supervisor |
| 1 | sandbox directory mode contract is POSIX only |
| 1 | two real interpreters use inherited socket barriers |
| 1 | 人工经验决定与独立进程监管需要 POSIX |
| 1 | 合成 --help 可执行夹具使用 POSIX shebang；不声称 Windows 执行器已验证 |
| 1 | 独立进程监管需要 POSIX |
| 1 | 验证持有文件描述符期间替换锁路径 |
| 1 | 验证重入锁持有旧文件描述符时的身份 |

## 失败如何理解

- 真实可移植性缺口：44 条失败记录直接报 `os.getuid` 不存在；另有个人凭据原生保护不支持、签名私钥 ACL 拒绝、Windows 路径与隔离挂载不兼容。不能归为“全部是测试问题”。
- 测试夹具可移植性：`test_testbox` 使用无扩展名的 POSIX shebang 替代 ssh/scp，Windows 没有执行替代程序，实际调用系统 SSH；构造测试主机名解析失败。其他具体夹具错误见原件，不推定都是同一原因。
- 其余失败包含候选构建/验证未通过、门禁因此正确拒绝、端口访问、预览及文件访问错误。仅按观察记录，未逐项确认根因的项不宣称已修复。
- 两个版本错误数量不同，属于本次各环境实际结果；不取较低值替代另一个环境。

完整失败标识、原始错误摘要、报告文件名与所有执行退出码见 [cloud-summary.json](cloud-summary.json)。全部日志与 JUnit 见 GitHub Actions 42341045304 的 16 个 artifacts；本机持久副本位于 `运维智能体/部署包/windows-full-20261107/cloud-e282`，文件摘要见 [清单](cloud-artifacts-manifest.json)。
