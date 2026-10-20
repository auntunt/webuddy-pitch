# 标品、参考项目与固定知识版本

首版支持本地 Git 项目。标品和参考是可组合的角色；“仅供知识查阅”与“开发与维护”是独立的工作流。登记、构建知识和建立引用均不运行来源仓库的脚本，也不启动模型。

## 网页使用

1. 在项目选择器中点“添加项目”，登记本地仓库。标品与参考项目可先选“仅供知识查阅”。
2. 进入“工程 → 知识与引用”，选择提交、标签或分支，点“构建固定快照”。启动时解析成完整 Git 提交；未提交改动不进入快照。
3. 在客户项目添加一个或多个来源，明确选择已发布的知识版本、目录范围与用途。空范围表示整个快照；`modules/approval` 只包含该路径及其子路径。
4. 共享需要已有授权，或操作者明确授予所选范围。未登录帐号时，敏感操作需要独立操作者凭据；普通 API token 加一个人名不构成授权。
5. 检索结果保留来源项目、代码提交、知识修订、路径和适用性。片段最多 600 个字符并明确提示；“打开该版本完整原文”读取完整内容，二进制保留完整 Base64 和原文件下载入口。
6. 在标品的已发布版本上点“派生客户项目”，创建新的项目身份和独立工作区。查阅项目点“开始维护本项目”，保留原身份、来源和知识历史，建立独立可写工作区。

派生使用完整源快照生成原始导入提交，不复制 Git 历史或远程配置。随后独立的初始化提交把来源任务、验收和验证报告完整归档到 `.tmh/source-history/<源提交>/`，知识页改为需要当前项目重新确认；回执列出全部处理。源快照与导入提交保留原始字节，来源的人工确认不会成为当前项目的验收。

“比较当前代码”只比较当前已提交文件与所选固定版本的内容和模式。未提交改动、运行配置、动态调用及业务适用性仍需复核；比较不会修改绑定或自动升级引用。

## 版本、失败与更新

- 每次构建生成独立修订，绑定源提交、分析器摘要、分析配置、文件清单和索引摘要。源码原文与生成知识分别保存，生成页使用 `@knowledge/` 命名空间。
- 构建依次导出、分析、索引、发布；完成阶段持久保存检查点。恢复会校验原文和分析器，未完成的阶段重跑。已发布修订禁止恢复和覆盖。
- 取消、失败或服务中断不替换旧修订。恢复必须获得内核锁，并确认旧监管进程有完整回收证据；缺失或不完整回执不能用历史 PID 或“看起来没运行”代替。
- 同一来源多个构建隔离；查询自身知识选择该来源最后登记且成功的修订，旧构建迟到不会盖过较新的成功修订。跨项目引用始终指向用户选择的确切修订。
- 来源 HEAD 前进不会改变旧引用。可再构建新修订，显式添加新版本并移除旧版本；两个版本可以同时保留用于对照，不存在隐式升级。
- 新运行、交付方案、复检、采纳及外部候选的需求摘要均检查相关引用。版本、目录、用途或授权改变后，旧结果保留，但不能作为当前输入继续推进。检索在组装期间切换引用也会拒绝启动。
- 只查阅工作流拒绝旧写入和执行入口；后台延迟预览也在实际启动前复查。项目仍有 Agent 运行、预览或复检时，不能切换到只查阅。

## 本地 API

沿用平台已有认证。以下路径的 `<key>` 是项目代号。

| 方法与路径 | 作用 |
| --- | --- |
| `POST /api/projects` | 原登记参数加 `roles: ["product", "reference"]`、`workflow: "reference"` 或 `"development"` |
| `GET /api/projects/<key>/library` | 来源、角色、修订、覆盖范围、授权、引用与派生信息 |
| `GET /api/projects/<key>/knowledge/search?q=…&limit=20&offset=0` | 当前项目与显式绑定来源的分页检索 |
| `GET /api/projects/<key>/knowledge/file?revision_id=…&path=…` | 核对授权和摘要后返回完整原文 |
| `POST /api/projects/<key>/library` | 通过下表的 `action` 操作 |

| action | 参数与边界 |
| --- | --- |
| `configure` | `roles`, `workflow`；查阅转开发必须使用 `maintain` |
| `add_source` | `root`, `label`；为同一项目增加来源，固定历史继续保留 |
| `build` | `commit`（默认 HEAD），可选 `source_id`（默认当前项目目录） |
| `cancel` / `resume` | `revision_id`；先读状态，不能重写已发布版本 |
| `grant` / `revoke` | `project` 为使用方；grant 另需 `scopes`，显式替换授权范围 |
| `reference` | `revision_id`, `scopes`, `purpose`；可选 `grant: true` 明确授予并合并所选共享范围 |
| `remove_reference` | `binding_id`；只移除当前项目的绑定 |
| `compare` | `revision_id`；只比较获准范围 |
| `derive` | `revision_id`, `key`, `name`；完整范围且没有未导出文件才可派生 |
| `maintain` | 本项目的 `revision_id`；保留项目身份并建立工作区 |

`configure/add_source/grant/revoke/derive/maintain` 与 `reference + grant:true` 需要真实签名登录会话或独立操作者凭据。Agent 专用接口不提供这些管理权限；源文件、搜索结果或人名标签不能替代授权。这是可信本地平台的项目共享边界，不是组织级多租户帐号隔离。

## CLI 与 MCP

CLI 使用已配置的 `WEBUDDY_URL` 和平台凭据。下面的项目代号与修订号为示意；`REVISION_ID` 应替换为 library 返回的 32 位编号。

```sh
python3 -m tmh.workbench library STD
python3 -m tmh.workbench knowledge-build STD --commit HEAD --request-id std-build-001
python3 -m tmh.workbench knowledge-reference CLIENT REVISION_ID --scope docs --purpose '参考审批规则' --request-id client-ref-001
python3 -m tmh.workbench knowledge-search CLIENT 审批 --limit 20 --offset 0
python3 -m tmh.workbench knowledge-read CLIENT REVISION_ID docs/approval.md
python3 -m tmh.workbench knowledge-cancel STD REVISION_ID --request-id std-cancel-001
python3 -m tmh.workbench knowledge-resume STD REVISION_ID --request-id std-resume-001
python3 -m tmh.workbench knowledge-unlink CLIENT 1 --request-id client-unlink-001
```

每个新操作使用新请求编号，重试原操作复用原编号。CLI 的构建、取消和恢复命令明确携带执行标志。MCP 对应 `library_get/search/read/build/cancel/resume/reference/unlink`；默认不开放构建执行，需配置 `--allow-execution`，`--read-only` 只提供读取。MCP 运行还需要已有的可选 SDK。

## 支持范围与下一步

- 首版固定版本只支持本地 Git 根目录，不自动下载对象。非 Git 项目继续使用原功能，不能伪造长期可引用版本。
- 密钥、证书、常见凭据目录及 `.tmh/cache`、`.tmh/tool` 不进入快照；符号链接和子模块不跟随，清单逐项报告。存在未导出文件时拒绝完整派生，不生成缺文件的客户项目。文件名规则不构成通用秘密扫描器。
- 二进制、未支持编码和超过单文件解析上限的内容保留原始字节，明确列为未索引。查询过长会报错，原始需求与文件不截断。源码中的 `@knowledge` 根路径、仅大小写不同的文件路径会拒绝发布，避免存储歧义。
- 复用匹配分析器的文件解析缓存；跨快照先校验内容，不能只信 mtime。图谱仍整体重建，没有宣称完成模块依赖驱动的全量增量分析。
- 本轮 286,780 行合成 Java（260 文件、13 个目录组）测得冷构建约 9.6 秒、无变更重建约 6.4 秒、单文件变更约 6.1 秒，峰值内存约 109 MiB。解析器只识别为一个模块，未验证复杂动态调用、SQL 或业务流质量；目录组数量不能算作模块识别成绩。完整原始测量见进度文件。
- 尚需在用户指定的真实标品上检验语言/框架覆盖、业务理解、依赖失效传播、查询相关性和成本。客户知识的精细依赖覆盖、升级影响/冲突分析、非 Git 与外部文档适配器是后续工作。
- 静态 worker 复用现有 POSIX 进程监管。本轮未验证 Windows；原 P6 的 Windows 原生锁、进程树监管和相关工具链限制仍需单独完成。

实现与验证记录：[ralph-port 进度](self-improvement/ralph-port-progress.md)。原始设计：[项目资产与知识库设计](design/project-knowledge-library-2026-10-20.md)。
