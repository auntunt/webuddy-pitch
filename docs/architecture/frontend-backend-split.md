# 前后端拆分与前端工程化方案

## 1. 现状（2026-11-09，提交 eb80a830）

| 层 | 现状 | 问题 |
|---|---|---|
| 界面 | `tmh/platform/ui*.py` 共 24 个文件、约 97 万字符的 HTML/CSS/JS 写在 Python 字符串里，`ui.page()` 拼成一个页面；全局函数 + 423 处内联 `onclick`；约 40 个 hash 路由（`#/t`、`#/kb`、`#/projects`…） | 没有模块边界和类型，改一处容易影响别处；无法做组件级测试；31 个测试文件靠字符串断言界面 |
| 接口 | `tmh/platform/server.py` 4574 行：`Platform` 门面（89–960 行）、214 个 `@route` 处理函数（960–3873 行）、HTTP 处理器与鉴权（3873–4574 行）全在一个文件 | 路由、鉴权、业务调用混在一起；接口没有显式契约，只有 Agent 接口有 `agent_contract.SPECS` |
| 执行底座 | `tmh/platform/*.py` 各业务模块（candidates、fixloop、agents、project_verify、knowledge…）+ `Platform` 门面 | 本身已按领域分文件，问题主要在门面和路由层 |

约束：内网/离线可用、不依赖 CDN；Windows 离线包运行时不能要求 Node；Python 标准库 HTTP 服务继续使用（不换 Flask）；现有 URL、Cookie、令牌、租户鉴权和 Agent 接口保持兼容。

## 2. 目标边界

```
web/                      前端工程（Vue 3 + TypeScript + Vite）
  src/api/                类型化接口客户端：唯一允许发请求的地方
  src/pages/<领域>/        页面组件，按路由拆分
  src/components/         共享组件（表格、状态标签、对话框、证据块…）
  src/styles/             DESIGN.md 的颜色/间距变量
tmh/platform/web_dist/    构建产物（带内容哈希，随包发布，运行时不需要 Node）
tmh/platform/http/        HTTP 层：请求解析、鉴权、静态资源、错误映射
tmh/platform/api/         接口层：按领域拆分的路由模块，只做参数校验和调用服务
tmh/platform/app.py       Platform 门面（从 server.py 移出）
tmh/platform/<领域>.py     执行底座，保持现状
```

规则：
- 前端只通过 `src/api/` 调用 `/api/*`，不拼接业务逻辑；状态、权限、可执行动作以服务端返回为准（与现在的“按钮权限与后端一致”要求相同）。
- 接口层不写业务逻辑，只做参数校验、身份获取、调用 `Platform`/领域模块、把 `ApiError` 映射为 HTTP 状态。
- 执行底座不感知 HTTP。

## 3. 技术选型

- **Vue 3 + TypeScript + Vite + vue-router**。不引入组件库，按 DESIGN.md 自建少量共享组件，保持现有视觉。暂不引入全局状态库，用组合式函数管理状态，确有跨页共享再加。
- **构建产物入库**：`web_dist/` 随代码提交，服务器、Windows 离线包和 pip 安装都不需要 Node。CI 重新构建并比对产物，不一致即失败，防止源码与产物脱节。
- **依赖**：版本固定（锁文件入库），只选发布超过 7 天的版本；离线包内容审计把 `web_dist/` 纳入扫描。
- **测试**：Vitest 做组件和接口客户端测试；Playwright 做真实浏览器流程（桌面 1440×900 与手机 390×844），逐步替代字符串断言界面的测试。

## 4. 迁移方式：新旧并存、按页替换

1. 新前端挂在 `/next/`，与旧页面共用同一套登录、Cookie、令牌和租户鉴权；旧页面 `/` 保持不变。
2. 按页面迁移，每迁一页：功能对齐 → Playwright 用例覆盖 → 旧页面该路由跳转到新页面 → 删除对应 `ui_*.py` 代码和其字符串断言测试。
3. 所有页面迁完后 `/` 指向新前端，删除 `ui.py` 拼页面逻辑。

迁移顺序（先产品方向最重要、交互最集中的页面）：

| 批次 | 页面 | 理由 |
|---|---|---|
| 1 | 应用外壳（顶栏、项目切换、导航、登录态）+ “验证现有改动”与候选详情 | 本轮交付主线；页面新、旧代码少 |
| 2 | 工单列表/详情（`#/t`、`#/tickets`）、运行（`#/runs`） | 使用最频繁 |
| 3 | 知识库、业务地图、图谱（`#/kb`、`#/maps`、`#/atlas`） | 最复杂，需要组件化地图 |
| 4 | 交付、版本、团队、设置及其余页面 | 收尾 |

## 5. 后端拆分步骤

1. `Platform` 类移到 `tmh/platform/app.py`；`server.py` 重新导出，现有导入不受影响。
2. 路由按领域拆到 `tmh/platform/api/`（meta/workspace、projects、tickets、runs、candidates/deliveries、knowledge/kb、maps/atlas、team/access、settings/agents、sessions/assist、testbox 等），共用同一个 `route` 注册表；路由顺序与匹配结果保持不变，用测试比对拆分前后的路由表。
3. HTTP 处理器、鉴权、预览代理移到 `tmh/platform/http/`。
4. 新增静态资源服务：`/next/` 返回新前端入口，`/next/assets/*` 带哈希长缓存，只读、不经过业务写入。
5. 每个迁移到新前端的接口补一份响应类型（TypeScript），后续可从服务端生成。

## 6. 验证要求

- 每一步全量测试通过；拆分前后路由表（方法、路径模式、处理函数名）一致。
- 新前端：`npm run build` 产物与入库产物一致；Vitest、Playwright 通过；记录实际验证的尺寸。
- Windows 离线包 CI 继续通过（包内含 `web_dist/`，断网启动可打开 `/next/`）。
- 43 测试环境部署后实际打开 `/next/` 完成“验证现有改动”流程。

## 7. 本轮范围

方案 + 第一步：后端拆分第 1–4 步（行为不变），新前端工程骨架 + 应用外壳 + “验证现有改动”与候选详情页挂在 `/next/`。旧页面不删除。
