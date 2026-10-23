# 协作闭环 UI 实际浏览器验证

验证日期：2026-10-23。最终产品源已冻结为 `39cde13`；本目录仅补充浏览器证据，不修改运行源文件。

## 验证范围与边界

使用独立回环端口 51391 的真实 gateway、独立租户 worker、SQLite 临时数据和正常密码登录。两个合成租户分别具有同名 APP / REF 项目，使用合成 contributor 与 viewer 账号；没有访问生产、调用模型、启动构建、创建公开分享、替用户业务验收或关单，也没有导入用户录音或私聊内容。夹具脚本、原始图片、临时数据与复现日志保留在仓库外 `部署包/coordination-20261023/ui-check/`。

这些是实际界面与交互证据，不是全量测试结果或生产上线凭据。未知写入结果、存储异常与并发场景由实际产品 JavaScript 的定向测试及独立复现脚本验证；不把截图当作其证明。

## 实际完成的流程

1. contributor 正常登录，进入合成租户甲。从全部项目进入会议入口时要求先选择真实项目；选择 APP 后创建完整的五行合成会议记录。
2. 明确 TODO 被提取为规则草稿。界面未推断负责人、期限与完成条件；人工补齐负责人、交付物、完成条件后保存，刷新保留未提交字段；明确发布创建 APP-2，仍为新建任务，没有自动确认或关单。
3. 从任务工作台打开交接详情，保存工作简报第 1 版：结论、待决定、下一步、协作人、未知期限。完整需求和来源仍保留。工作台会议来源链接从全部项目准确进入 `#/meetings/1/APP` 并选中 APP。
4. 未配置执行环境的 contributor 通过纯内容入口创建文档交付，保存完整手工材料 v1；未调用模型或执行程序。添加内容要求，绑定 v1 并填写实际阅读依据，状态变为已核对材料。
5. 保存材料 v2 后，覆盖项对 v1 的核对立即显示“来源已变化”，保留原核对人和依据；直接核对旧绑定的按钮不可用。旧阶段的运行和人工复核提交同样依现有执行权限禁用，手工材料仍可保存。
6. 390px 视口检查 document.clientWidth 与 scrollWidth 均为 390。负责人、期限、交付物、完成条件和来源状态均保留，没有横向溢出或移动端省略字段。
7. 在租户甲填写未提交行动草稿，切到租户乙的同名 APP 后无甲的数据和草稿；切回甲完整恢复。合成撤权使旧页面自动清空并显示重新进入提示，恢复授权后整页重新读取，原撤权上下文的草稿未残留。
8. 使用 viewer 正常登录，会议原文、任务负责人和已发布行动可读，新增行动及表单均禁用。交付材料可读，保存新版本、增改覆盖要求、核对与撤回均禁用，模板按钮不提供可写操作。验证结果通过页面实际 disabled 状态确认。
9. 通过键盘 Enter 完成组织选择，正常读取对应租户。一次浏览器控制通道 click 超时后先读当前页确认没有导航，再用已聚焦链接 Enter；未产生重复业务写入。

## 发现与修复记录

- 初次会议列表真实请求暴露 query adapter 把 parse_qs 列表直接传入分页参数的问题；根代理修复并添加真实 HTTP 红绿回归。随后正常读取、创建和发布。
- 独立审查复现了未知 POST 后首次 GET 失败无法按原请求重试、成功回执后存储清理失败可能再次创建、存储异常缺少可见错误、textarea 规范化破坏未编辑 CRLF 等问题。均修复并增加有意义行为回归。现有旧阶段草稿可显式恢复，并必须重新核对来源后绑定；不会静默绑定新版本。
- 独立审查的 4 项原红灯与 6 个额外恢复场景全部通过；日志保留于仓库外 `部署包/coverage-content-20261023/ui-review-green.json`。源码冻结前新 UI 30 项、既有 handoffs 21 项、access 38 项、delivery_design 8 项，合计 97 项通过；`git diff --check` 通过。未削弱基线断言。

## 图片说明

所有 16 张图片均为浏览器返回的原始编码字节，直接复制并逐一核对 SHA-256；未缩放像素、压缩、裁剪或重新编码。共 1,817,222 字节。长页面保留完整高度，查看器可能按显示尺寸缩放，不改变交付文件。

推荐审阅：

- `09-final-meeting-desktop-full.jpg`：最终桌面会议页，完整标题、来源、任务负责人和行动字段。
- `10-final-brief-desktop.jpg`：最终桌面工作简报，清楚展示结论、待决定、下一步与责任约定。
- `10-final-brief-desktop-full.jpg`：同一工作台的完整页面，保留需求与交接详情。
- `11-final-coverage-desktop-full.jpg`、`12-final-coverage-390-full.jpg`：最终材料 v2 与 v1 核对失效、执行权限边界。
- `13-final-meeting-readonly-390-full.jpg`：最终只读会议与完整行动信息。
- `14-final-coverage-readonly-390-full.jpg`、`15-final-coverage-readonly-390.jpg`：最终只读交付，全部写操作禁用。
- `01` 至 `08` 为过程中保留的原始场景。`02` 标题处于滚动位置、`03` 简报不在视口内、`06` 是执行按钮呈现修复前的旧源图片，不应用于认定最终按钮状态；保留它们用于验证经过，最终状态以上述 final 图片为准。`08` 记录撤权清屏。

实现代理已实际打开最终会议、简报、390px 会议/覆盖图片核对；根代理亦亲自打开最终 09、10、12 原图。

## 资源清理

验收页签已关闭，视口已恢复默认。合成服务收到 Ctrl-C 正常退出（exit 0），执行 finally 关闭 worker 和数据库；随后检查端口 51391 无监听、进程列表无该临时目录或服务脚本所属进程。夹具及原始日志保留，无后台持续运行任务。

## 原始图片校验

| 图片 | 字节数 | SHA-256 |
|---|---:|---|
| [01-meetings-empty.jpg](01-meetings-empty.jpg) | 58153 | `d0139b5e5eabacc558b6334810ffced9a28a370b22883f4e0b4700231b34575c` |
| [02-meeting-published.jpg](02-meeting-published.jpg) | 72790 | `7e3fc2bf32a71f502366cf4e50aa671d16ca3b14ae7f8628e96f5ad244982b73` |
| [03-brief-workspace.jpg](03-brief-workspace.jpg) | 51069 | `e5fbf7f88783b3d702b987a145bef1542e56fdc48d74115aa4a51ed522e75be6` |
| [04-coverage-checked.jpg](04-coverage-checked.jpg) | 59396 | `53783f60502ad83ccd756423d9bdd4949cae0e09dc01191bec62bb3f18a855c8` |
| [05-coverage-stale.jpg](05-coverage-stale.jpg) | 82737 | `eb8278b79ee4d9d3f04de37a67c477ae043e6e60a32555034aaf9f3f331665be` |
| [06-coverage-390-full.jpg](06-coverage-390-full.jpg) | 208106 | `5adc2bbd028d08c7fb89658a063fe8b7047811f1d8e12e91081a5e5487fbc979` |
| [07-meeting-390-full.jpg](07-meeting-390-full.jpg) | 86498 | `6b95c1c6e933b15cff7b3f7da7362fb5fd9b41dca2c66d99c2271fa5ddd96035` |
| [08-revoked-390.jpg](08-revoked-390.jpg) | 8206 | `7f8b50e69c1a31fa646d3e5c5d29c2112b19e3efeab53c6b7a3ccfec7def9a58` |
| [09-final-meeting-desktop-full.jpg](09-final-meeting-desktop-full.jpg) | 108068 | `5d54fe8487f3cced31553bdf5147847e83f7bdf47812bb8245f5faf44e7d33c5` |
| [10-final-brief-desktop-full.jpg](10-final-brief-desktop-full.jpg) | 213243 | `99cec1ddea4bbc0cf51d6b71f28a2157e8376245984d0c17b53ef6df4de54208` |
| [10-final-brief-desktop.jpg](10-final-brief-desktop.jpg) | 84422 | `d941811689faeb3564f9a77a91e9552f70ada073a49d6350095dba2e3fe01e72` |
| [11-final-coverage-desktop-full.jpg](11-final-coverage-desktop-full.jpg) | 266456 | `333e1d40f38b04a9d813135a468a7dda9af1705fad140dbc7e8f8c0192ba9cd1` |
| [12-final-coverage-390-full.jpg](12-final-coverage-390-full.jpg) | 200295 | `534d34fb817d1f7fea7fa9f59014102cd580b137bb12dfe40485ad54d72d8ec8` |
| [13-final-meeting-readonly-390-full.jpg](13-final-meeting-readonly-390-full.jpg) | 81363 | `44437a8ca9753ae4fe51e4a86f18698c18a9ff85703f7e2528f70fd793e7f8bd` |
| [14-final-coverage-readonly-390-full.jpg](14-final-coverage-readonly-390-full.jpg) | 196785 | `f8a68f47ec7d19e211fef97620db28f7923999f73e7541459da961ef60580951` |
| [15-final-coverage-readonly-390.jpg](15-final-coverage-readonly-390.jpg) | 39635 | `599da93c161cc0f62bbe9926dabeeae5a499b2b2f0e53bff7244fa1506c478dc` |
