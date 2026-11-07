# Windows 全量与 MCP 实测（2026-11-07）

本轮由 Agent 通过 SSH 和 GitHub Actions 执行；没有真人桌面点击、模型调用、客户验收或代人合并。本轮代码候选为 `e282afab238e658e495e5508e64c94b72101dfc2`，包含测试运行脚本、CI，以及两个实机复现的 Windows 进程修复；43 部署结果单独记录。

## 最终结论

Windows 全量范围已逐项尝试并保留回执，但未全部通过。原生 Windows 个人 MCP 的凭据保护仍不支持，不能交付为个人账号已接通。已修复两个实机进程问题并发布43测试站；阿里云未操作。

| 环境（同一 e282afab） | 通过 | 失败或错误 | 跳过 | 超时未完成 |
|---|---:|---:|---:|---:|
| 自有 Windows 测试机 Python3.11.9 | 2338 | 130 | 615 | 1 |
| GitHub Windows Python3.11 | 2340 | 129 | 615 | 0 |
| GitHub Windows Python3.13 | 2341 | 128 | 615 | 0 |

按测试标识去重，teardown 重复错误合并，每行总范围3084用例；不是3084种业务场景，也不跨环境相加。每个环境307个执行单元均有回执。云端全部有JUnit。实机两个模块首次300秒超时，另对其19个原用例独立补跑；18个产生JUnit，`test_a_client_can_check_it_with_plain_ssh_keygen` 仍300秒超时。该用例未通过且未完成，不以云端结果代替。原超时、补跑失败均保留。

最终实机 MCP：**15通过、1失败、4跳过**；Windows进程专项：**11通过、0跳过**。两个云端版本相同。协议测试实际使用官方MCP SDK、stdio与生成的客户端配置；没有代替真人使用Cursor/Claude/Codex桌面操作。

- [云端完整结果、跳过原因及失败分类](cloud-results.md)
- [实机完整汇总与未完成用例](own-summary.json) · [分片回执](own-run.json) · [补跑回执](own-supplement.json)
- [最终实机MCP原始日志](final-own-tests__test_workbench_mcp.log) · [JUnit](final-own-tests__test_workbench_mcp.xml)
- 全部原件持久保存于本机 `运维智能体/部署包/windows-full-20261107/own-e282` 与 `cloud-e282`，分别见[实机摘要清单](own-artifacts-manifest.json)、[云端摘要清单](cloud-artifacts-manifest.json)。实机完整归档442922字节，SHA256 `dd22ea324017c7f4796bd5f96ab22e23fcf77e0e76509246175aa33db4b4c702`，下载后与Windows摘要一致并实际解包读取。

## 已完成的自有 Windows MCP

设备 `laptop`，Python 3.11.9、Git 2.55、Node 24.18，12 线程、约 32 GB 内存。公网 SSH 端口连接超时；经 43 已有 SSH 转发连通，未修改网络配置或 TLS 验证。

固定源码提交 `21f4e73ef021fc12cb29ca0ee96e381a7ee8a27d`。MCP 专项包包含该提交的全部 tmh 代码、pyproject 和官方协议测试及 conftest；不冒充全仓包。SHA256 `95ecb54d51de203375fcd29d2492d81d1c3ad55a749abd26582138a29d91dea3`，Windows 校验后解包。独立 venv 安装 mcp 1.30.0、pytest 9.2.0、cryptography 50.0.2；使用隔离 HOME/USERPROFILE 与合成 HTTP 服务，不读取个人凭据。

命令：`python -m pytest tests/test_workbench_mcp.py -vv -rs --junitxml=mcp.xml`。

实际结果：**15 passed、1 failed、4 skipped，退出 1，23.36 秒**。

- 通过：真实 stdio 初始化和发现、Cursor/Claude/Codex 生成配置的子进程启动、完整文本、只读拒绝、参数校验、执行回执、冲突、写入响应丢失及异常响应、HTTP 工作线程上限和取消。
- 失败：个人 execute 连接在保存凭据时触发 `credential_platform_unsupported`。
- 跳过：个人连接撤权/实时权限、develop 权限、read 权限、个人配置无秘密启动；均为现有 POSIX 凭据条件。本轮未扩大 skip。
- 此结果不是 Cursor/Claude/Codex 桌面产品的真人登录联调；协议测试使用官方 MCP SDK 驱动生成配置。

原件：[JUnit](own-windows-mcp.xml)、[完整日志](own-windows-mcp.log)、[SSH 执行回执](own-windows-mcp-execution.log)。

## 云端与完整设备检查

- 第一轮 `9965b355`：[42337432312](https://github.com/auntunt/webuddy-pitch/actions/runs/42337432312)。MCP SDK 已安装；部分预览测试的控制台中断结束控制器，后续模块缺失，不能称跑完。
- 第二轮 `21f4e73`：[42337860567](https://github.com/auntunt/webuddy-pitch/actions/runs/42337860567)。新进程组仍不足以阻止全部控制台中断；原日志和失败保留。
- 第三轮 `a9ce6f20`：[42338796236](https://github.com/auntunt/webuddy-pitch/actions/runs/42338796236)。使用 DETACHED_PROCESS，各模块均有执行回执，但平台集成模块超时，不能称全部用例完成。
- 第四轮 `f8cb8ceb` / 42340162635 被新候选替代后明确取消，不能作为最终完整证据。
- 最终完整检查：[e282afab / 42341045304](https://github.com/auntunt/webuddy-pitch/actions/runs/42341045304)。平台集成模块按 pytest 原生用例拆分执行，保留原断言；其余模块仍逐模块执行。
- 自有测试机完整检查以同一 `e282afab` 为准，源码摘要和 Git 提交均核对后执行；最终结果见本页表格及实机汇总。

macOS 协议对照 **35 passed、67 subtests passed、0 skipped**，仅用于归因，不替代 Windows：[日志](webuddy-mcp-mac-control.log)、[JUnit](webuddy-mcp-mac-control.xml)。

## 当前边界

个人 Windows 凭据原生安全存储尚不支持；不得移除保护、使用 chmod 冒充 ACL，或拿旧共享令牌协议通过替代个人项目授权接入。Linux 平台与 Windows 浏览器访问、Windows 原生平台、Windows 个人 CLI/MCP 是不同结论。客户真实业务和人工操作均未在本轮代做。

## 两项实机修复

1. 预览存活检查：Windows 的 `os.kill(pid, 0)` 会终止目标。隔离反例修前只输出 before、进程退出 0，修后输出 before/alive True/after。改用只申请 SYNCHRONIZE 的 OpenProcess 和零等待查询，关闭句柄，不发信号。
2. venv 监督器：Windows 虚拟环境启动器额外产生一层进程，触发 owner_lost。仅 stdlib 监督器改为基础解释器直接启动；项目解释器、管道所有权、超时和清理机制保留。真实新 venv 反例修前失败，修后 Windows 执行模块 11 项通过。

修前、修后及执行命令保存在 [operations](operations/)。Mac 相关 46 通过、7 Windows 专用跳过；43 隔离候选同范围 46 通过、7 跳过。两者不是 Windows 完整套件的替代结果。

## 操作与交付留痕

全部技术操作由Agent执行；本轮没有真人业务确认、客户验收、真实客户数据或模型调用。

| 顺序 | 实际操作 | 证据与边界 |
|---|---|---|
| 1 | 公网SSH失败后，经43已有转发连接自有Windows | operations中的连接与准备日志；未修改网络配置 |
| 2 | GitHub直接TLS拉取失败，使用固定源码包和Git bundle | 完整SHA、精确HEAD、执行位/内容摘要核对；未关闭TLS |
| 3 | 建立独立venv、安装MCP/pytest/cryptography，运行协议专项 | 初始与最终MCP原件分开保存；合成账号与HTTP服务 |
| 4 | 实机复现并修复存活查询终止进程、venv监督器owner_lost | 修前/修后回执，Windows专项11项通过 |
| 5 | 云端16分片、实机8分片执行同一候选 | 每个模块/集成用例独立退出码，原始失败保留 |
| 6 | 实机两个超时模块按19个原用例补跑 | 补跑不改断言；仍有1个签名用例超时，停止重复尝试 |
| 7 | SSH中断后重新查询运行文件与进程，导出证据 | 实机主运行13:20:58—13:36:05，补跑13:36:13—13:41:14；断线不重启测试、不伪造退出回执 |
| 8 | 当前候选必需CI通过后，备份并发布43，核对即时与延迟健康 | 运行e282afab；未发布阿里云 |

脚本与完整操作日志见 [operations](operations/)。大规模测试原件放在持久证据包，Git内保留摘要、关键原件与可定位清单。

## CI及43发布

精确push CI42341011443的十项必需检查均成功，Linux3.11/3.13各3035通过49跳过、1943子用例通过。原标准工作流中的Windows完整两任务后来因后续提交触发而取消；不得把工作流状态说成全平台成功。独立Windows全量工作流42341045304已完整结束，结论failure，原件可下载。

43运行文件2606项、15数据库副本检查及46通过/7跳过的Linux定向检查完成。完整备份 `pre-e282afa-test-20261107T051731Z/state.tar.gz` 56074文件逐字节核对。13:19:17启动PID1812014，13:19:20即时和13:20:31延迟健康同PID、重启0，清单/数据库/内外登录200与匿名API401通过。程序回退入口 `releases/e961515/app`，不得恢复旧库覆盖新数据。

测试期间产品分支另有后续提交 `8d5600ed`，本报告的Windows结论仅绑定 `e282afab`，不能继承为后续代码完整验证通过。
