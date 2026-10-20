# 中间件适配知识库

> 标注【核对】的内容请以厂商当前文档为准。核对日期：2026-10。

## 应用服务器

常见替换方向：WebLogic / WebSphere / JBoss / Tomcat → 东方通 TongWeb、金蝶 Apusic AAS、宝兰德 BES、中创 InforSuite AS 等。它们都实现 Jakarta EE / Java EE 规范，**标准 war 通常能部署，问题集中在专有描述符、类加载和资源配置**。

| 关注点 | 源（举例） | 迁移动作 |
|---|---|---|
| 专有描述符 | `weblogic.xml`、`ibm-web-bnd.xml`、`jboss-web.xml` | 改写为目标中间件的描述符（如 TongWeb 的 `tongweb-web.xml`【核对文件名】），context-root、会话超时、安全角色逐项映射 |
| 类加载顺序 | `prefer-web-inf-classes`、`parentLast` | 在目标中间件设置“应用类优先”，否则 jar 冲突（尤其是 xml-apis、日志、Jackson） |
| JNDI 数据源 | `java:comp/env/jdbc/xxx`、`<resource-ref>` | 在目标中间件控制台或配置文件中创建同名数据源；驱动 jar 放入中间件 lib 或应用内 |
| 专有 API | `weblogic.*`、`com.ibm.websphere.*` | 换成标准 API 或 Spring 能力 |
| 远程协议 | t3、IIOP | 改 HTTP/REST 或 MQ |
| 集群/会话 | 中间件自带会话复制 | 评估改为 Redis 会话或目标中间件的集群方案 |
| JSP 编译 | 中间件内置 Jasper 版本不同 | 回归所有 JSP，注意 `<%@ page pageEncoding %>` 与自定义标签 |

建议步骤：先在目标中间件部署原 war 不改代码，记录启动错误清单；再按清单逐项改，每改一项重新部署。

## Spring Boot 嵌入式容器

- 若甲方只要求“部署在信创操作系统”，内嵌 Tomcat 一般可以保留；若要求“信创中间件”，需替换。
- 方式一：排除 `spring-boot-starter-tomcat`，引入厂商的嵌入式 starter（TongWeb、BES 等均提供嵌入版【核对坐标与授权】）。
- 方式二：改为 war 打包，`extends SpringBootServletInitializer`，部署到信创中间件。
- 注意 Spring Boot 主版本与嵌入式 starter 版本对应；Spring Boot 3 需要 Jakarta EE 9+ 兼容的中间件版本。

## 消息与缓存

- IBM MQ / TIBCO / WebLogic JMS → 东方通 TongLINK/Q、RocketMQ、Kafka（开源）等。若业务通过 JMS API 使用，替换 ConnectionFactory 即可大部分复用；若直接用厂商 API，需要封装一层再替换。
- 消息语义检查：事务性、顺序、重复投递与幂等、死信、消息大小、字符集。
- 缓存：东方通 TongRDS 等宣称兼容 Redis 协议【核对命令覆盖度】。检查 Lua 脚本、Cluster/Sentinel 模式、`KEYS`/`SCAN` 用法、Redisson 高级特性。

## Web 服务器与网关

- Apache/Nginx 可用国产操作系统自带包；需要国密 HTTPS 时，常用支持 TLCP 的网关（铜锁 Tongsuo 编译的 Nginx、厂商国密网关）在入口处终结，应用内部保持 HTTP 或普通 TLS。
