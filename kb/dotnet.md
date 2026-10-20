# .NET 项目信创改造（.NET Framework → .NET 8+ on 麒麟/统信）

> 核心事实：.NET Framework 只能跑在 Windows 上，信创操作系统是 Linux，所以 .NET Framework 项目的信创改造 = 先完成 .NET 现代化迁移，再做数据库/架构/国密适配。核对日期：2026-10。

## 迁移路线

1. **盘点**：`tmh assess` + `tmh map`。重点看：旧式 csproj 数量、`packages.config`、`HintPath` 二进制引用、WebForms 页面数、WCF 契约数、`System.Web` 使用面、Windows API 命中。
2. **定目标版本**：选当前 LTS（.NET 8 或 10）。确认目标 CPU：x64、arm64 官方支持；LoongArch64 需使用龙芯提供的 .NET SDK/运行时【核对】。
3. **按依赖图自底向上**：`tmh map` 的“.NET 项目引用”给出顺序。先迁没有依赖的类库：
   - 旧式 csproj → SDK 风格（`try-convert` 或手工；Microsoft 的迁移工具形态在变化，以当时官方推荐为准【核对】）。
   - 类库改为多目标 `net48;net8.0` 或 `netstandard2.0`，让新旧宿主可以并存，降低一次性切换风险。
   - `packages.config` → `PackageReference`，逐个确认包有 .NET 8 版本。
4. **宿主层最后迁**：Web、Windows 服务、WCF 服务。
5. **再做信创适配**：数据库提供程序、路径、字符集、本地库、国密。
6. **在目标环境验证**：在麒麟/统信 + 目标 CPU 上跑测试与冒烟，不能只在 Windows 上 `dotnet build` 通过就算完成。

## Web 层

| 源 | 目标 | 说明 |
|---|---|---|
| ASP.NET MVC 5 | ASP.NET Core MVC | 控制器基本可平移；过滤器、模型绑定、`HttpContext`、路由、Bundling、`Web.config` 配置需改 |
| Web API 2 | ASP.NET Core Web API | `ApiController` → `ControllerBase` + `[ApiController]`，`IHttpActionResult` → `IActionResult` |
| WebForms (.aspx) | Razor Pages / Blazor / 前后端分离 | **没有自动转换**，按页面重写；页面多时用 `Microsoft.AspNetCore.SystemWebAdapters` 做增量迁移（YARP 反代，新老并行）【核对】 |
| `HttpContext.Current` | 依赖注入 `IHttpContextAccessor` | 静态访问是迁移最大阻力之一，先在旧代码里收敛 |
| Session / Forms 认证 | ASP.NET Core 认证中间件 + 分布式缓存 | Windows 集成认证改 LDAP/OAuth/统一身份认证 |
| `Server.MapPath` | `IWebHostEnvironment.ContentRootPath/WebRootPath` | 注意 Linux 大小写敏感 |

## 服务通信

- WCF 服务端 → **CoreWCF**（保留 SOAP 契约，调用方无感，适合对外接口不能变的情况）或 gRPC / REST（需要调用方配合）。
- WCF 客户端 → `System.ServiceModel.Http` 等 NuGet 包可在 .NET 8 使用（只支持部分绑定）【核对】。
- ASMX → CoreWCF 或 REST；.NET Remoting → 无替代，必须改协议。
- MSMQ → 国产 MQ / RabbitMQ / RocketMQ 等。

## Windows 依赖

| 依赖 | 替代 |
|---|---|
| 注册表 `Microsoft.Win32.Registry` | 配置文件 / 环境变量 |
| `System.Drawing` (GDI+) | SkiaSharp、ImageSharp（注意许可证）；验证码、缩略图、二维码、条码是常见出现点 |
| WMI / 性能计数器 | `/proc`、`System.Diagnostics.Metrics`、OpenTelemetry |
| EventLog | `ILogger` + 日志平台 |
| Windows 服务 `ServiceBase` | Worker Service + `UseSystemd()` |
| COM / Office Interop | NPOI、OpenXML SDK、WPS 等提供的信创文档 SDK |
| 水晶报表 | FastReport、报表服务或前端报表 |
| `Encoding.Default` / GBK | 显式编码 + `CodePagesEncodingProvider` |
| 本地 DLL `DllImport` | 目标架构 `.so`，或纯托管实现 |

## 数据访问

- ADO.NET：先把 `SqlConnection/SqlCommand` 改为 `DbConnection/DbCommand` + 工厂，再接国产库提供程序（达梦 DmProvider、金仓 Kdbndp 等）。参数前缀（`@`/`:`）按目标库与模式调整。
- EF6：EF 6.4+ 能在 .NET 8 运行，但国产库多只提供 EF Core 提供程序，通常迁到 EF Core。EDMX 先改 Code First；注意 EF Core 与 EF6 的行为差异（延迟加载默认关闭、`GroupBy` 翻译、级联删除）。
- 厂商 EF Core 包版本必须与 EF Core 主版本一致【核对】。
- Dapper：基本不受影响，只需替换连接类型与 SQL 方言。

## 配置与宿主

- `Web.config/App.config` → `appsettings.json` + 环境变量 + `IOptions<T>`；过渡期可引用 `System.Configuration.ConfigurationManager` 包。
- IIS → Kestrel + Nginx（或信创 Web 服务器）反向代理；`<system.webServer>` 的模块/处理程序改中间件，URL 重写放 Nginx。
- `Global.asax` 生命周期 → `Program.cs` 中间件管道。
- 发布：`dotnet publish -r linux-arm64 --self-contained`（或框架依赖部署 + 目标机安装运行时）；systemd 单元托管。
