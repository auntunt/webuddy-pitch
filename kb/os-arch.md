# 操作系统、CPU 架构、JDK 与字符集

> 核对日期：2026-10。标注【核对】处请以厂商文档为准。

## 目标环境速览

| 维度 | 常见选择 | 备注 |
|---|---|---|
| 操作系统 | 银河麒麟（Kylin）V10、统信 UOS 服务器版、openEuler 及其商业发行版 | 都是 Linux；包管理多为 yum/dnf（麒麟服务器、openEuler）或 apt（UOS 桌面） |
| CPU | 鲲鹏（ARM64）、飞腾（ARM64）、海光（x86_64）、兆芯（x86_64）、龙芯（LoongArch64） | 海光/兆芯是 x86 指令集，大多数 x86 本地库可直接用；ARM64 与 LoongArch 需要对应本地库 |
| JDK | 毕昇 JDK（华为，ARM 优化）、腾讯 Kona、阿里 Dragonwell、龙芯 JDK（LoongArch 必需）、OpenJDK 发行版 | 8/11/17/21 为主 |

## 操作系统差异

- **路径**：盘符、反斜杠、UNC 共享路径全部改为配置项；Linux 文件名大小写敏感（`Upload.JPG` ≠ `upload.jpg`），这是迁移后最常见的“文件找不到”。
- **脚本**：`.bat`/`.cmd`/PowerShell 改为 shell；Windows 服务改为 systemd 单元；计划任务改为 systemd timer 或 cron。
- **外部命令**：代码里 `Runtime.exec` / `Process.Start` 调用的命令要逐个列出，确认 Linux 等价物与权限。
- **换行与 BOM**：脚本必须是 LF；配置文件的 UTF-8 BOM 可能导致解析失败。
- **字体**：报表、PDF、验证码、图片水印依赖中文字体。Windows 自带商业字体不能随意拷到服务器，应使用系统自带或已授权字体，并在模板里改字体名后对比输出。
- **时区与区域**：容器/服务器默认时区可能是 UTC，检查 `TZ`、JVM `-Duser.timezone`、数据库会话时区。

## CPU 架构

1. **找出所有本地代码**：`tmh assess` 的 `ARCH-*` 命中（JNI、JNA、`DllImport`、`.so`/`.dll` 文件、已知带本地库的依赖）。
2. **逐个确认来源**：有源码 → 交叉编译 aarch64 / loongarch64；第三方 → 找厂商信创版本或替代库；无法替代 → 列为阻塞项上报。
3. **常见替换**：sigar → oshi；netty-tcnative 动态版 → `netty-tcnative-boringssl-static`（确认含目标架构）或 JDK SSL；老版本 sqlite-jdbc → 新版本（已含 aarch64）；Windows 专用 DLL → 必须换方案。
4. **容器镜像**：基础镜像换成目标架构可用的镜像（麒麟/统信/openEuler 官方镜像或多架构镜像），CI 增加对应架构构建；不能在 x86 机器上“看起来构建成功”就算完成，至少在目标架构上跑一次测试。
5. **性能与并发**：ARM 内存模型较弱，存在数据竞争的老代码在 ARM 上更容易暴露问题；压测要在目标架构上做。

## JDK

- 内部 API：`sun.misc.BASE64Encoder` → `java.util.Base64`；`sun.misc.Unsafe`、`com.sun.image.codec.jpeg` 等需替换。
- 版本：1.6/1.7 先升到 8；需要 Spring Boot 3 时升到 17+，同时 `javax.*` → `jakarta.*`（推荐 OpenRewrite 等确定性重写工具批量完成，再由智能体处理剩余编译错误）。
- 龙芯平台必须使用龙芯提供的 JDK（或已支持 LoongArch 的 OpenJDK 发行版）【核对版本】。
- JVM 参数：去掉 Windows 专用参数；ARM 上可评估毕昇 JDK 的特性参数【核对】。

## 字符集

- Windows 中文环境默认 GBK，Linux 默认 UTF-8。所有依赖默认字符集的地方（`new String(bytes)`、`getBytes()`、`FileReader`、`Encoding.Default`）都要**显式指定**。
- 不要一律改 UTF-8：对接的老文件、银行/税务报文、老系统接口如果确实是 GBK，就显式写 GBK。改之前先确认数据实际编码。
- .NET Core/5+ 默认不含 GBK，需要 `Encoding.RegisterProvider(CodePagesEncodingProvider.Instance)`。
- 数据库从 GBK 迁到 UTF-8：一个汉字从 2 字节变 3 字节，字节长度语义的 VARCHAR 可能溢出；达梦可选“按字符计长”（初始化参数）。
