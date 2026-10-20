# 运维工具接入

tmh 把团队在用的运维工具接进来，并把它们和项目知识库对上：

- 工单（Jira / 禅道 / GitLab Issues）→ 相关的业务流、表、代码位置 → 带工单链接的任务契约
- 构建失败（Jenkins / GitLab CI）→ 日志里的堆栈和编译错误 → 项目代码的 文件:行号 → 方法 → 业务流
- 代码质量（SonarQube）→ 按业务流分组，先处理核心业务流上的问题
- 合并请求（GitLab）→ 改动文件 → 涉及的业务流
- 工单号 → git 历史里的提交 → 改过的文件 → 业务流（`tmh trace`）
- 文档（Confluence）、群通知（钉钉 / 飞书 / 企业微信 / 任意 webhook）

智能体有两种用法：命令行 `tmh ...`，或者 MCP 服务 `tmh mcp`（`tmh install` 已经替 Codex 和 Claude Code 配好）。

## 1. 接入一个工具

```sh
tmh int types -v                       # 支持的类型和各自的配置项
tmh int add jira --type jira --url https://jira.example.com --token-env JIRA_TOKEN --set project=OA
export JIRA_TOKEN=...                  # 在启动 Codex / Claude Code 的终端里设置
tmh int test jira                      # 连通性检查（只读）
tmh int list                           # 已接入的工具、能力、环境变量是否已设置
```

配置写在 `.tmh/config.json` 的 `integrations` 下，可以提交到仓库，因为里面**只有环境变量名，没有凭据**。
如果把 `token`、`password`、`secret`、`webhook` 这类字段直接写成值，tmh 会拒绝加载并提示改成 `*_env`。

```json
"integrations": {
  "tools": {
    "jira":   {"type": "jira", "url": "https://jira.example.com", "project": "OA",
               "auth": {"type": "bearer", "token_env": "JIRA_TOKEN"}},
    "ci":     {"type": "jenkins", "url": "https://jenkins.example.com", "job": "oa/oa-web/master",
               "auth": {"type": "basic", "user": "li", "password_env": "JENKINS_TOKEN"}},
    "gitlab": {"type": "gitlab", "url": "https://gitlab.example.com", "project": "oa/oa-web",
               "auth": {"type": "header", "name": "PRIVATE-TOKEN", "token_env": "GITLAB_TOKEN"}},
    "sonar":  {"type": "sonarqube", "url": "https://sonar.example.com", "project": "oa",
               "auth": {"type": "bearer", "token_env": "SONAR_TOKEN"}},
    "group":  {"type": "dingtalk", "webhook_env": "DINGTALK_WEBHOOK", "secret_env": "DINGTALK_SECRET"}
  },
  "defaults": {"builds": "ci"},
  "agent_writes": false
}
```

所有工具都支持的通用配置项：

| 配置项 | 说明 |
|---|---|
| `auth` | `none` / `basic`（`user` 或 `user_env` + `password_env`）/ `bearer`（`token_env`）/ `header`（`name` + `token_env`）/ `query`（`param` + `token_env`） |
| `timeout` / `retries` | 默认 20 秒、重试 2 次（429 和 5xx、网络错误时按 0.5/1/2 秒退避） |
| `proxy` | 默认走系统代理环境变量；可写代理地址，或 `"none"` 直连。本机地址始终直连 |
| `cafile` | 内网自签 CA 证书的路径。`"verify": false` 可以关掉证书校验，但不建议 |
| `headers` | 额外的非敏感请求头 |
| `readonly` | `true` 时即使加 `--confirm` 也拒绝写操作 |
| `disabled` | `true` 时自动选择时跳过它 |

同一种能力接了多个工具时（比如 Jira 和禅道都有），用 `defaults` 指定默认的，或者在命令后加 `--via 名字`。

## 2. 内置适配器

| 类型 | 能力 | 认证建议 | 说明 |
|---|---|---|---|
| `jira` | 工单 | Server/DC 用个人访问令牌（bearer）；Cloud 用邮箱 + API token（basic） | REST API v2；搜索时可以直接写 JQL；支持评论、流转 |
| `zentao` | 工单 | `{type: zentao, account: 账号, password_env: …}` | 禅道 RESTful API v1（开源版 18+ / 企业版 / 旗舰版）；编号写成 `bug-12`、`story-3`、`task-7` |
| `github` | 工单 | 公开仓库可不填（每小时 60 次）；批量导入用 bearer，`token_env: GITHUB_TOKEN` | REST v3，github.com 默认、Enterprise 填 `https://<主机>/api/v3`；`--set repo=所有者/仓库`；编号写成 `#12`，提交里写的合并请求号会换成它关掉的 issue |
| `gitlab` | 工单、合并请求、构建 | `PRIVATE-TOKEN` 头（默认读 `GITLAB_TOKEN`） | API v4，私有部署和 gitlab.com 都可以；构建对应流水线，日志取失败的 job |
| `jenkins` | 构建 | 账号 + API Token（basic） | 支持多级目录 job（`a/b/c`）、`last`/`lastFailed` 别名、带 CSRF crumb 触发 |
| `sonarqube` | 代码质量 | bearer；老版本用 token 当用户名的 basic | 未解决问题（分页）、质量门禁 |
| `confluence` | 文档 | Server/DC 用 bearer；Cloud 用 basic | CQL 搜索、读正文（去掉 HTML） |
| `dingtalk` / `feishu` / `wecom` | 通知 | webhook 地址放环境变量（`webhook_env`），加签密钥也放环境变量（`secret_env`） | 钉钉、飞书支持加签 |
| `webhook` | 通知 | `webhook_env` | 任意 JSON webhook，`template` 定义消息体 |
| `generic` | 按配置 | 同上 | 见第 4 节，不写代码就能接一个新工具 |

## 3. 日常命令

```sh
tmh ticket OA-123                 # 工单详情 + 知识库里相关的业务流/表/代码
tmh ticket OA-123 --task          # 生成任务契约 .tmh/tasks/T###-OA-123-*.md，带工单链接和相关知识
tmh issue search "报销 驳回"       # Jira 也可以直接写 JQL
tmh build status [job]            # 最近构建
tmh build failure [job]           # 最近一次失败：错误行 → 项目代码位置 → 方法 → 业务流
tmh build log [job] --number 12 --tail 400
tmh quality --severity MAJOR      # Sonar 问题按业务流分组；--gate 看门禁
tmh change get '!42'              # 合并请求改动文件涉及的业务流
tmh doc search "报销流程"
tmh trace OA-123                  # 哪些提交提到这个工单、改了哪些文件、涉及哪些业务流
```

构建失败定位能识别 Java 堆栈（`at a.b.C.m(C.java:60)`）、.NET 堆栈（`in X.cs:line 42`）、javac/Maven（`/x/Foo.java:[12,5]`）、MSBuild（`Foo.cs(12,5): error CS…`）。JDK 和框架里的帧会被过滤掉，只留下本项目的代码。需要先有知识库（`tmh kb build`）。

## 4. 写操作的安全措施

评论、流转、触发构建、发通知这四类操作会改动外部系统。

- **默认只演练**：打印将要发出的请求（webhook 里的 `access_token`、`sign` 等参数会被打码），不会真的发送。确认无误后加 `--confirm`。
- 真正执行的写操作会记入分析过程（`activity.jsonl`），报告里能看到。
- 某个接入配置 `readonly: true` 后，任何写操作都会被拒绝。
- **智能体通过 MCP 调用时**，只有仓库配置 `integrations.agent_writes: true`、并且调用时传 `confirm: true`，才会真正执行。否则只能演练，需要人在终端里执行。
- 技能 `ops-tools` 要求智能体执行写操作前先征得用户同意，不触发发布类 job，不把工单流转到终态。

## 5. 扩展：接一个新工具

### 方式一：写配置（`generic`）

适合有 JSON HTTP 接口的工具，比如 TAPD、Teambition、内部工单系统、内部发布平台。

```json
"tapd": {
  "type": "generic", "url": "https://api.tapd.cn",
  "auth": {"type": "basic", "user": "api_user", "password_env": "TAPD_PASSWORD"},
  "ping": {"path": "/quickstart/testauth"},
  "issues": {
    "get":    {"path": "/bugs", "params": {"workspace_id": "123", "id": "{key}"}, "root": "data.0.Bug",
               "map": {"key": "id", "title": "title", "status": "status", "description": "description",
                       "url": "https://www.tapd.cn/123/bugtrace/bugs/view?bug_id={id}"}},
    "search": {"path": "/bugs", "params": {"workspace_id": "123", "title": "{query}", "limit": "{limit}"},
               "root": "data", "item": "Bug", "map": {"key": "id", "title": "title", "status": "status"}},
    "comment": {"method": "POST", "path": "/comments", "body": {"workspace_id": "123", "entry_type": "bug", "entry_id": "{key}", "description": "{body}"}}
  }
}
```

- 各能力下可以配置的操作：`issues`: get / search / comment；`builds`: list / get / log / trigger；`changes`: list / get；`quality`: issues；`docs`: search / get；`notify`: send。
- `path`、`params`、`body` 和 `map` 的值里可以用 `{占位符}`，取值来源有三种：调用参数（key、query、limit、job、number、id、body、title、text）、`{base}`，以及当前记录里任意一个点分字段（如 `{fields.status.name}`）。
- `map` 的值不带花括号时，表示记录里的点分路径。`root` 是返回 JSON 里记录（或列表）所在的位置；如果列表里每一行都包了一层，用 `item` 解开。日志类接口返回纯文本时，写 `"text": true`。
- 映射后的字段名和统一模型一致（见下文）。没映射到的字段留空。

> 上面 TAPD 的接口路径只是示意，接入前请按 TAPD 当前的开放平台文档核对。

### 方式二：写插件

需要特殊认证、分页或多次调用才能拼出结果时，写一个 Python 插件：放到 `<仓库>/.tmh/integrations/<名字>.py`，文件名不要以 `_` 开头。`tmh install` 会放一个示例 `_example.py`。

```python
from tmh.integrations import Integration, Issue

class MyIssues(Integration):
    TYPE = "myissues"
    TITLE = "内部工单系统"
    CAPABILITIES = ("issues",)

    def ping(self):
        return "已登录为 %s" % self.http.get("/api/me")["name"]

    def get_issue(self, key, comments=5):
        d = self.http.get("/api/requirements/%s" % key)
        return Issue(key=key, title=d["title"], status=d["state"], description=d["content"], source=self.name)
```

`self.http` 已经处理好认证、超时、重试、代理、内网证书和写操作演练，插件只需要关心接口和字段映射。插件可以覆盖同名的内置类型。插件加载失败时只打印一条警告，不会影响其它命令。

### 统一模型

| 模型 | 字段 |
|---|---|
| Issue | key, title, status, type, priority, assignee, reporter, description, url, created, updated, labels, links, comments |
| Build | job, number, status（success/failed/running/unstable/aborted）, started, duration_s, url, commit, branch, cause |
| Change | id, title, state, author, source_branch, target_branch, url, updated, description |
| QualityIssue | rule, severity, type, file, line, message, url |
| Doc | id, title, url, space, excerpt, body, updated |

## 6. MCP 服务

`tmh install` 会写好两份配置：

- Claude Code：仓库根目录的 `.mcp.json`（服务名 `tmh`），并在 `.claude/settings.json` 里启用它，允许调用 `mcp__tmh`。
- Codex：`.codex/config.toml` 里的 `[mcp_servers.tmh]`。Codex 默认只把少数环境变量传给 MCP 服务，所以 tmh 会把配置里用到的凭据变量名写进 `env_vars`，`tmh int add/remove` 之后会自动更新。只有项目被 Codex 标记为受信任时，才会读取项目级 `.codex/config.toml`；否则把这一段复制到 `~/.codex/config.toml`。

提供的工具：

- 始终提供：`context`、`flows`、`impact`、`trace`、`integrations`
- 接入了对应能力才出现：`ticket`、`ticket_task`、`issue_*`、`build_*`、`change_*`、`quality_*`、`doc_*`、`notify_send`

每个 MCP 工具都在进程内执行对应的 tmh 命令，所以命令行和 MCP 的行为完全一致。

## 7. 验证情况

- 已验证：`tests/test_integrations.py` 有 19 个用例，在 Python 3.8 和 3.13 下通过。测试用进程内的模拟 HTTP 服务器，覆盖每个内置适配器的请求格式和认证头、禅道 token 登录、钉钉加签、Jenkins crumb、重试和错误提示、凭据明文拒绝、演练与 `--confirm`、只读接入、插件加载、通用适配器映射、构建失败到业务流的定位、工单到任务契约、按工单追溯、MCP 握手和工具调用、安装后的 MCP 配置。
- 已验证：Claude Code 2.1 通过 MCP 实际调用了 `ticket`、`build_failure`、`flows`，从工单和失败构建定位到同一条业务流，全程没有读源码文件。见 [e2e-integrations.md](e2e-integrations.md)。
- 未验证：
  - 还没有连过真实的 Jira、Jenkins、GitLab、禅道、SonarQube、Confluence 和群机器人。接口格式是按各家公开文档写的，不同版本的字段可能有差异，第一次接入请先跑 `tmh int test`。
  - 禅道评论接口：禅道 v1 没有独立的评论接口，目前是通过编辑接口的 `comment` 字段写入，不同版本可能不支持。
  - Codex 的 `env_vars` 透传：按 Codex 文档写的，还没有在 Codex 里实际跑过。
