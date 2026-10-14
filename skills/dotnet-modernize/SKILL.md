---
name: dotnet-modernize
description: 把 .NET Framework 项目（MVC/Web API/WebForms/WCF/Windows 服务/EF6）迁移到 .NET 8+ 以便运行在麒麟/统信等 Linux 信创环境。用户提到 .NET 迁移、.NET Core、去 Windows 化、.NET 信创时使用。
---

# .NET Framework → .NET 8+

先读 `.tmh/kb/dotnet.md`。.NET 信创的前提是项目能在 Linux 上运行，所以这一步通常是整个改造的第 1 波。

## 步骤

1. **盘点**：`tmh assess` 与 `tmh map`，记下：项目依赖顺序（地图的“.NET 项目引用”）、旧式 csproj、`packages.config`、`HintPath` 二进制、WebForms 页面数、WCF 契约、`NET-WIN-*` 命中。
2. **定计划并写契约**（`tmh task new "迁移 <项目> 到 net8.0" --kind upgrade`）：
   - 迁移顺序：无依赖类库 → 业务类库 → 宿主（Web/服务）
   - 每个第三方包/二进制的 .NET 8 可用性（查不到的列为待确认）
   - WebForms、WCF 服务端、COM 组件的处理方式（重写/CoreWCF/替换）——**这类决定需要用户确认**
3. **逐个项目迁移**（每个项目一次提交，保持可回退）：
   - 转 SDK 风格 csproj；`packages.config` → `PackageReference`
   - 类库优先多目标（`net48;net8.0`），让旧宿主继续工作
   - 替换 Windows 依赖：注册表→配置、`System.Drawing`→SkiaSharp/ImageSharp、EventLog→ILogger、ServiceBase→Worker Service
   - 数据访问：`SqlConnection` → `DbConnection` 抽象，为后续换国产库提供程序做准备
   - `dotnet build` 通过后跑测试；有 Linux 环境时在 Linux 上跑
4. **宿主迁移**：MVC/Web API → ASP.NET Core（控制器、过滤器、认证、配置、静态文件）；`Web.config` → `appsettings.json`；IIS 配置 → Kestrel + Nginx。
5. **验证**：`tmh verify`（在 `.tmh/config.json` 的 `commands` 中配置 `dotnet build`/`dotnet test`，必要时加上在 Linux 容器里的冒烟命令）。
6. **记账与知识**：更新工作项；在 `.tmh/knowledge/decisions.md` 记录迁移决定。

## 注意
- 行为差异要有测试覆盖：JSON 序列化（Newtonsoft → System.Text.Json 的默认值不同，可以先保留 Newtonsoft）、日期时区、字符串比较/排序的区域设置、EF Core 查询翻译。
- 不要一次迁所有项目；每一步都应可编译、可测试。
