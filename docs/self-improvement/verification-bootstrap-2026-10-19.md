# 新建项目继承已验证的事项编辑修复

2026-10-19，接续 `a75113c`。本轮处理上一轮已经复现的缺口：BOOTV2 候选修好了 CRLF 长度边界，但从零创建项目仍生成旧实现。现在新项目的编辑路径与已验证的 BOOTV2 #6 保持一致。

实现与完整证据提交：`012c0ae47829da3faddbc35624ed515505bb8129`（`Carry verified newline handling into new project templates`），仅本地，未推送；此记录随后单独补记提交号。

## 实现与失败回归

只修改 `tmh/platform/project_bootstrap.py` 的应用及测试模板，以及已有创建集成测试中的应用测试数量断言。编辑标题按 `len(raw_title) - raw_title.count("\r\n")` 检查逻辑长度，数据库保存和错误回显继续使用完整原文；8 KiB 保存上限、64 KiB 错误恢复窗口、CSRF、原 id 和完成状态保持原有约束。创建、Git、预览配置及部署逻辑没有改动。

原 23 个应用测试方法逐字节保留，新增 3 个方法直接继承上一轮通过独立验收的 BOOTV2 实现。不是只检查模板中是否出现关键字：正式 `create()` 会生成项目、实际编译并运行全部 26 个 HTTP/SQLite 测试，再形成 Git 基线和创建回执。

完整证据位于 [bootstrap-2026-10-19](evidence/bootstrap-2026-10-19/)。旧模板原文保存为 `before-app.py` / `before-tests.py`。实现代理的旧 APP + 新测试红测有 3 项测试、16 个子场景失败；独立 12 项红测有 4 项失败，覆盖普通及预览前缀下的 CRLF 200 字保存与故障后重试。失败日志原样保留，没有清洗或截断。

## 实际验证结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 正式创建入口 | 构建和 26 项应用测试通过，生成 Git 工作区干净，回执和提交一致 | `create-receipt.json`、`create-verification.json`、`generated-app-tests-green.log` |
| 平台创建相关测试 | 9 项通过 | `bootstrap-tests-green.log` |
| 独立创建与业务验收 | 重新使用独立临时 Store/data_dir 调用正式 create；26 项应用测试通过，独立 HTTP/SQLite 验收 12/12 通过，无阻塞发现 | `independent-create-review.json`、`independent-review.md`、`independent-acceptance-green.log` |
| 平台最终完整回归 | **452 项，450 通过、0 失败、0 错误、2 跳过，196.368 秒，退出码 0** | `platform-full.log` |
| 源码差异 | 源码及说明的空白检查通过，旧测试原文保留；生成两份源码与已验证 BOOTV2 #6 逐字节一致 | `source.diff`、独立源码 SHA256 |

完整回归仍有两项可选依赖跳过；原日志中的 SQLite/socket ResourceWarning 未过滤。独立审查脚本的第一次运行在 macOS `/var` 与 `/private/var` 别名比较处失败，修正为规范路径比较后完整重跑；`*-first-attempt.*` 原始记录继续保留。这是审查脚本问题，不计作业务修复成果。

## 从页面创建并实际操作

使用隔离工作台 `data/bootstrap-verification-2026-10-19`，临时端口 8797/8798，身份“自动流转”。没有调用模型或替代人工复核。浏览器从交付工作台填写目标、选择创建新项目，点击“创建交付”，实际建立 **BOOTNEW** 和交付 `cffc4b261268`。页面显示创建检查成功；原始创建回执内有编译退出 0 和 26 项实际测试通过。

生成提交：`eecdee9054beb07e1517c735d1d14a1cb862d298`。通过页面“打开主干版本 → 启动预览”启动真实应用，没有使用预先准备的应用替代新建产物。

1. 新增对照事项 id=1 和编辑目标 id=2，将 id=2 标为完成。
2. 编辑 id=2，原生 textarea 输入 100 个“事” + LF + 99 个“项”（value.length=200），点击保存成功。SQLite 保留原始 CRLF（实际原文长度 201），id=2、done=1 和 id=1 均正确。
3. 再填 99 个“验” + LF + 100 个“证”。使用独立 SQLite EXCLUSIVE 只读事务临时阻塞数据库，实际保存返回不可用，页面完整保留 200 个逻辑字符和 `/items/2/edit` 表单目标。锁设置 45 秒自动释放上限，实际提前释放并退出。
4. 原错误页点击“重试保存”成功；刷新后仍保留。SQLite 精确核对 CRLF 原文、原 id、done=1、对照事项和总共两行。
5. 通过工作台“重新启动”重建预览；应用刷新后数据仍相同。最终数据库备份读回与 JSON 完全一致。

原始截图包括 `browser-created-project.jpg`、`browser-native-200-saved.jpg`、`browser-503-retained.jpg`、`browser-retry-saved.jpg` 和 `browser-final-after-restart.jpg`。图片保持原分辨率、原编码；最终页面与故障页已实际打开检查。应用源码、项目配置、数据库、工作台数据库和完整创建回执均保留；`BOOTNEW-source.bundle` 经 `git bundle verify` 验证。

## 接续状态与边界

本轮修复使后续新建 Web 项目直接继承已经验证的编辑能力。没有修改既有 BOOTV2 源码和数据，也没有自动迁移其他项目。日常 8791 工作台在无活动运行时重启到最终代码，原 BOOTV2 固定版本预览仍为 up、匹配运行 #6，三条原数据与上一轮导出相同。

临时预览通过页面停止，并实际检查其受管进程组已退出；临时 8797/8798 工作台也已停止，隔离项目和数据保留。8792 未操作。没有新模型运行、人工复核、客户签收或生产发布，因此此轮不能重复计入上一轮真模型交付成果。

下一轮优先解决 Python 业务入口与验收证据的可追溯关联，或客户答复后再理解超时的恢复路径；根据实际阻塞选择其一。不能以文件相交、人工豁免或测试数量将未知业务路径判为通过。
