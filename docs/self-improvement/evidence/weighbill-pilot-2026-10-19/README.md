# 磅单并发保护证据索引

当前业务候选 `ab9601e305bf9efdf908554174c56ca101194405`；基线 `60d6422ee898959557fc529a8e0335524b5ee2c0`。平台 `8e05c2af64128d06966160871c3b2126b765f8e6`。详见 [验证记录](../../verification-weighbill-pilot-2026-10-19.md)。A3真实浏览器后半段尚未完成，**不构成最终通过或业务签收**。

| 内容 | 文件 |
| --- | --- |
| 真实需求、验收和CLI任务包 | `task.md`、`criteria.json`、`ticket-package.json` |
| 外部Codex完整输入、原始输出、结束/回收及命令输出 | `implementation/` |
| 原始基线失败、HTTP/SQLite及盲重试复现 | `independent/` |
| 独立复核、初次竞态红灯、修后结果及夹具纠错 | `independent-candidate/REVIEW-FINAL.md` 及同目录全部原始材料 |
| 协调者及平台完整测试 | `full-pytest.log`、`coordinator-checks.json`、`platform-verification/2/`、`3/`、`4/` |
| 最终可恢复源码 | `candidate.bundle`、`candidate-source.tar`、`candidate.diff`、`candidate-history.txt` |
| 本地配置与历次候选 | `project-config.json`、`candidate-*.json`、`*.previous-*.json` |
| 浏览器实际步骤/失败及截图 | `browser-timeline.json`、`browser-conflict.jpg` |
| 真实预览数据前后及原图读取 | `preview-before-browser.json`、`preview-after-b-save.json`、`preview-after-a-conflict.json`、`preview-original-integrity.json`、`preview-originals/` |
| 完整合成预览数据与有效一致备份 | `preview-data/`、`preview-consistent-snapshot.db` |
| MCP当前观察与CLI状态 | `mcp-technical-observation.json`、`assessment-results.json`、`candidate-current.json` |
| 原项目及BOOTV2保持 | `preservation-report.json`、前后完整摘要、`bootv2-preservation.json` |

`candidate.bundle`需要业务基线提交作为前置条件，已在含基线的隔离clone中运行`git bundle verify`。`candidate-source.tar`是完整Git候选源码，不依赖原仓库的未提交文件；不是包含运行依赖的部署包。实际运行使用本机已有Python3.12虚拟环境，未验证新机器安装。原源码仓库、真实台账/原图没有迁移或复制到此预览；仅保存原文件的保持性摘要。

本目录脚本最初从`data/weighbill-pilot-20261019`运行，部分按该路径定位仓库。归档脚本用于审计，直接在本目录执行不保证路径正确。截图和图片保存原始字节；未缩放像素或重新编码。SQLite在线备份为一致读取；`preview-data/`另保留抓取时的原始db/WAL/SHM，优先使用在线备份恢复验收时点。

`archive-metadata.json`记录归档时点和版本，`manifest.json`记录每个归档文件的完整字节数和SHA256（manifest自身除外）。原失败日志没有被最后成功替换；空stderr文件表示当次无stderr，不是截断。所有材料只证明明确记录的范围，A3 unknown必须保留到实际浏览器闭环完成。
