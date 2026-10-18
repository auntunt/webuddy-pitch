# 新项目模板独立复核

日期：2026-10-19。复核者：独立子代理 `design_reference_review`。

结论：冻结的模板修改及正式创建入口生成的应用没有发现阻塞问题。修复前，独立验收重现 4 个失败；修复后，正式创建的临时项目通过构建、全部 26 项应用测试，以及独立 12 项真实 HTTP / SQLite 验收。旧 23 个测试方法没有删改，新增 3 个方法与此前已通过的 BOOTV2 实现一致。

## 隔离范围与证据

验证调用实际 `tmh.platform.project_bootstrap.create`，使用一次性 `TemporaryDirectory`、独立 `Store` 和项目代号 `INDCREATE`。不是把模板字符串单独导出后直接宣布创建成功。创建回执对应真实 Git 提交；回执中的临时项目路径只作为历史来源，验证结束后目录已清理。

没有使用既有平台数据库、项目数据、已运行的应用、真实模型或生产。独立应用测试只使用其拥有的临时 SQLite 和随机回环端口。没有访问主代理正在验收的 8797/8798，也没有访问 8791/8792。

| 验证 | 结果 | 完整证据 |
| --- | --- | --- |
| 旧模板真实业务红测 | 12 项，4 失败、0 错误：无前缀与预览前缀下，CRLF 200 字保存及数据库恢复后重试均被错误拒绝 | `independent-acceptance-red.log` |
| 正式创建回执 | 构建退出 0；真实应用测试 26 项通过；回执与磁盘存档一致；提交与生成仓库 HEAD 一致 | `independent-create-receipt.json`、`independent-create-build.log`、`independent-create-test.log` |
| 生成应用独立验收 | 12/12 通过，源文件在执行期间不变 | `independent-acceptance-green.log` |
| 源码、测试保留及项目完整性 | 旧 23 方法逐字节不变、增加 3 方法；生成项目 Git 仍干净；没有创建项目本身的 `app.db` | `independent-create-review.json`、`independent-create-review.log` |
| 可重复验证入口与生成源快照 | 正式创建及独立验证脚本、生成的完整两份源文件 | `independent_create_review.py`、`independent-generated-app.py`、`independent-generated-tests.py` |

首次审查脚本在 macOS 的 `/var` 与 `/private/var` 路径别名比较上产生了一个审查脚本断言失败，发生在创建及应用测试已经通过之后。改为比较规范绝对路径后重新完整执行。首轮回执和原始日志完整保留在 `*-first-attempt.*`；这不是产品失败，也没有删除或覆盖首轮证据。

应用测试原始日志包含 Python 3.14 的 SQLite `ResourceWarning: unclosed database`，已完整保留。最终测试退出 0，26 项均为 `ok`；本轮计数修复没有改变既有数据库连接生命周期。

## 最终源码复核

生成文件与已独立验收的 BOOTV2 第 6 次运行逐字节一致：

- `app.py` SHA256：`a5bc89078052bc070b96e46255408721e88ce92750c91eef01fa973d7739a009`。
- `tests/test_app.py` SHA256：`6c3c1764893238ba21814da34cee7f99acc3bc90807c65a1a42075d83027b208`。

产品实现只改变编辑标题的长度计算：每个 CRLF 对按一次换行计数。数据库更新与错误回显仍使用原始 `raw_title`，没有添加裁剪、首尾去空白或存储归一化。8 KiB 保存上限、64 KiB 恢复窗口、CSRF 判断、原事项 id、完成状态和其他数据处理均未改变。

`project_bootstrap.py` 的 `APP` / `TESTS` 常量以外的代码经语法树对照保持不变；人工复核 diff 也没有发现创建、Git、配置或部署逻辑改动。平台集成测试仅将创建回执的预期应用测试数从 23 改为 26，其余断言保留。

旧模板的 23 个测试方法与生成测试逐方法比较，原文全部相同。生成测试全文件的 SHA256 又与先前已通过的 BOOTV2 测试相同，因此以下 3 个新增方法确为先前通过版本，没有将失败断言改宽或删去：

- `test_edit_crlf_logical_length_boundaries`
- `test_edit_crlf_preserves_record_across_restart_and_prefixes`
- `test_edit_crlf_database_failure_retries_original_item`

独立 12 项验证覆盖 CRLF 200/201 字、完整原文、原 id/done 与其他事项、刷新及服务重启、真实数据库不可用后的恢复重试、预览前缀、空白输入、CSRF、未知 id、转义、取消、完成/重开及非法 UTF-8。独立验证不依赖生成应用自己声明通过。

## 结论边界

本复核没有进行浏览器操作；主代理的真实 UI 创建与浏览器验收应单独记录。上述通过说明这一条新项目模板编辑路径已在正式创建产物上验证，不代表任意业务已经实现、不代表客户验收，也不代表生产部署。
