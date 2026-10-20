# 数据库适配知识库（Oracle / MySQL / SQL Server → 国产数据库）

> 本文件是给智能体和工程师的工作手册，不是厂商文档。版本差异很大，凡标注【核对】的内容，动手前请查目标库当前版本的官方文档或在测试实例上验证。核对日期：2026-10。

## 总体策略

1. **先定兼容模式，再决定改多少。** 国产库普遍提供“兼容某种商业库”的模式，选对模式能省掉大部分改写：
   - 达梦 DM8：实例参数 `COMPATIBLE_MODE`（0 不兼容，1 SQL92，2 Oracle，3 SQL Server，4 MySQL，其余见文档）【核对】。另有初始化时决定、事后不能改的 `CASE_SENSITIVE`（大小写敏感）、`CHARSET`、`LENGTH_IN_CHAR`（VARCHAR 长度按字符还是字节）。
   - 人大金仓 KingbaseES V8R6+/V9：初始化时选择数据库模式（Oracle / MySQL / SQL Server / PG）【核对】。
   - openGauss / GaussDB：建库时 `DBCOMPATIBILITY`（A=Oracle，B=MySQL，C=Teradata，PG）。
   - OceanBase：租户分 MySQL 模式与 Oracle 模式（Oracle 模式为企业版能力）【核对】。
2. **初始化参数一旦定了很难改**：大小写敏感、字符集、VARCHAR 长度语义、空串是否等于 NULL。动代码前把这几项写进 `.tmh/knowledge/decisions.md`。
3. **SQL 清单驱动**：用 `tmh map` 得到“表 → 代码”与 MyBatis 语句清单，用 `tmh assess` 得到方言命中点，逐条处理并在工作项里记录。
4. **能机械改的用确定性脚本，语义相关的才交给模型**（例如驱动类名、连接串、方言配置是机械替换；分页、递归、合并语句要理解上下文）。

## 驱动与连接串

| 目标库 | JDBC 驱动类 | 连接串示例 | .NET 提供程序 |
|---|---|---|---|
| 达梦 DM8 | `dm.jdbc.driver.DmDriver` | `jdbc:dm://host:5236`（指定模式用 `?schema=XXX`）【核对】 | DmProvider（`Dm.DmConnection`），EF Core 有达梦提供的包【核对版本】 |
| 金仓 KingbaseES | `com.kingbase8.Driver` | `jdbc:kingbase8://host:54321/db` | Kdbndp（`Kdbndp.KdbndpConnection`），EF Core 包由厂商提供【核对】 |
| openGauss | `org.opengauss.Driver` | `jdbc:opengauss://host:5432/db` | Npgsql 可连部分版本（协议兼容性需验证）；或厂商驱动 |
| GaussDB | 华为提供的 GaussDB JDBC 驱动【核对类名】 | 见华为云文档 | 华为提供的 .NET 驱动【核对】 |
| OceanBase | `com.oceanbase.jdbc.Driver` | `jdbc:oceanbase://host:2881/db` | MySQL 模式可用 MySqlConnector |

要点：
- 国产驱动 jar 多数不在 Maven 中央库，放到企业私服，固定 `groupId:artifactId:version`，不要用 `systemPath`。
- 连接池校验语句：达梦/金仓/openGauss 一般用 `select 1`（达梦 Oracle 模式下 `select 1 from dual` 也可用）。
- .NET 侧建议先把 `SqlConnection` 等具体类型收敛到 `DbConnection` / `DbProviderFactory`，再换提供程序，改动面最小。

## ORM 与分页插件

- Hibernate/JPA：达梦方言 `org.hibernate.dialect.DmDialect`（随驱动包提供，**方言 jar 版本必须与 Hibernate 主版本对应**）；金仓 `org.hibernate.dialect.Kingbase8Dialect`；openGauss 可从 PostgreSQL 方言起步。
- MyBatis：`databaseId` 多数据库分支时，为目标库补一份；没有分支时直接改 SQL。
- PageHelper：`helperDialect`。达梦在 Oracle 模式下可用 `oracle`，新版本 PageHelper 支持 `dm`【核对】；金仓按所选模式；openGauss 用 `postgresql`。
- MyBatis-Plus：`DbType.DM`、`DbType.KINGBASE_ES`、`DbType.OPENGAUSS` / `GAUSS` 等，分页拦截器要同步改。
- 主键策略：Oracle 序列 → 目标库序列或自增列；`@SequenceGenerator`、`useGeneratedKeys`、`selectKey` 都要检查。

## Oracle → 国产库

| Oracle 写法 | 达梦（Oracle 模式） | 金仓（Oracle 模式） | openGauss/GaussDB（A 兼容） | 通用改写 |
|---|---|---|---|---|
| `ROWNUM` 分页 | 支持 | 支持 | 部分支持，复杂嵌套需验证 | `LIMIT n OFFSET m` / `FETCH FIRST n ROWS ONLY` |
| `(+)` 外连接 | 支持 | 支持 | 有限支持【核对】 | 标准 `LEFT JOIN` |
| `CONNECT BY` | 支持 | 支持 | 部分版本支持【核对】 | `WITH RECURSIVE` |
| `MERGE INTO` | 支持 | 支持 | 支持 | — |
| `seq.NEXTVAL` | 支持 | 支持 | 支持 `nextval('seq')`，A 模式下点语法需验证 | — |
| `FROM DUAL` | 支持 | 支持 | 支持 | 去掉 |
| 空串 `''` 视为 NULL | 取决于参数 | Oracle 模式下一致【核对】 | A 模式下一致 | 显式处理，回归测试覆盖 |
| `DATE` 含时分秒 | 一致 | 一致 | A 模式下一致 | — |

**最容易出问题的不是语法报错，而是“能跑但结果不同”**：空串与 NULL、日期截断、排序时 NULL 的位置、字符串比较的尾部空格、数值精度、大小写。每类至少准备一条带样例数据的特征测试。

## MySQL → 国产库

- 反引号标识符 → 双引号或去掉（达梦/金仓 MySQL 模式下部分支持反引号【核对】）。
- `LIMIT a,b` → `LIMIT b OFFSET a`。
- `ON DUPLICATE KEY UPDATE` / `REPLACE INTO` / `INSERT IGNORE` → `MERGE` 或 `INSERT ... ON CONFLICT`（PG 系）。
- `IFNULL` → `COALESCE`；`GROUP_CONCAT` → `LISTAGG` / `STRING_AGG` / `WM_CONCAT`（达梦）。
- `DATE_FORMAT` / `STR_TO_DATE` → `TO_CHAR` / `TO_DATE`（格式符完全不同，逐条换）。
- `AUTO_INCREMENT` → `IDENTITY` / 序列 / `SERIAL`。
- MySQL 默认大小写不敏感的比较（取决于 collation）→ 国产库多数大小写敏感，查询条件可能需要 `UPPER()`。
- `TINYINT(1)` 当布尔、`0000-00-00` 零日期、隐式类型转换都要专门检查。

## SQL Server → 国产库

- `SELECT TOP n` → `LIMIT n`；`GETDATE()` → `SYSDATE` / `CURRENT_TIMESTAMP`；`ISNULL` → `COALESCE`/`NVL`。
- `[name]` 标识符 → 双引号；`dbo.` 架构名 → 目标库 schema。
- `WITH (NOLOCK)` → 删除（目标库多为 MVCC，读不阻塞写）。
- `IDENTITY(1,1)` / `SCOPE_IDENTITY()` / `@@IDENTITY` → 自增列 + `RETURNING` 或序列。
- `NEWID()` → `SYS_GUID()`（达梦/金仓 Oracle 模式）或 `gen_random_uuid()`（PG 系）。
- `DATEADD` / `DATEDIFF` → 日期加减与 `EXTRACT`，**单位与边界语义不同**，必须测试。
- T-SQL 存储过程、临时表 `#tmp`、表变量、`TRY...CATCH` 需要整体重写评估；达梦/金仓 SQL Server 模式能覆盖一部分【核对】。

## 函数对照

| 用途 | Oracle | MySQL | SQL Server | 达梦 | 金仓/PG 系 |
|---|---|---|---|---|---|
| 空值替换 | NVL | IFNULL | ISNULL | NVL / IFNULL / ISNULL | COALESCE（金仓 Oracle 模式有 NVL） |
| 当前时间 | SYSDATE | NOW() | GETDATE() | SYSDATE / NOW() | NOW() / CURRENT_TIMESTAMP |
| 字符串聚合 | LISTAGG | GROUP_CONCAT | STRING_AGG | LISTAGG / WM_CONCAT | STRING_AGG |
| 日期转字符串 | TO_CHAR | DATE_FORMAT | CONVERT/FORMAT | TO_CHAR | TO_CHAR |
| 子串 | SUBSTR | SUBSTRING | SUBSTRING | SUBSTR | SUBSTR/SUBSTRING |
| 条件 | DECODE | IF / CASE | IIF / CASE | DECODE | CASE（金仓 Oracle 模式有 DECODE） |

## 存储过程

1. 用 `tmh map` 的“数据库对象”与 `DB-ORA-003` 命中清单统计过程/包/触发器数量与行数，按调用方（`{call ...}`、`CommandType.StoredProcedure`）建立对应关系。
2. 分三类：可直接在兼容模式运行的；需要局部改写的（系统包 `DBMS_*`/`UTL_*`、`EXECUTE IMMEDIATE`、游标属性、异常名）；建议上移到应用层的（复杂业务、批处理）。
3. 每个过程先写输入/输出特征测试（固定样例数据 → 期望结果表），在源库跑通后再迁移。
4. 达梦 DMSQL、金仓 PL/SQL 对 Oracle 语法覆盖度较高，但 `DBMS_JOB`、`DBMS_LOB`、`UTL_FILE`、`UTL_HTTP` 等系统包要逐个核对【核对】。

## 大小写与保留字

- 达梦：默认大小写敏感；不带引号的标识符转大写。建表脚本若混用 `"userName"` 与 `USERNAME`，迁移后会报“对象不存在”。
- PG 系（金仓 PG 模式、openGauss）：不带引号的标识符转**小写**。
- 保留字：`LEVEL`、`COMMENT`、`USER`、`TYPE`、`DOMAIN`、`REFERENCE`、`OFFSET` 等常被用作列名，迁移后需要加引号或改名【以目标库保留字表为准】。

## 数据迁移工具（概览）

- 达梦：DTS 迁移工具；金仓：KDTS；openGauss：Chameleon / DataKit 等；OceanBase：OMS。【以厂商当前工具为准】
- 迁移后至少核对：行数、主键唯一性、数值合计、日期最大最小值、中文与特殊字符抽样、LOB 抽样、序列当前值。

## 排查清单

- [ ] 兼容模式、大小写、字符集、VARCHAR 长度语义已确定并记录
- [ ] 驱动、连接串、连接池校验语句、方言、分页插件已改
- [ ] 主键生成策略已核对（序列/自增/UUID）
- [ ] 所有 `${}` 动态 SQL 已确认（标识符白名单，值改 `#{}`）
- [ ] 方言命中点逐条处理或标注“兼容模式下保留”，并有测试覆盖
- [ ] 存储过程清单与处理方案确定
- [ ] 空串/NULL、日期、排序、精度的特征测试通过
- [ ] 数据迁移核对报告
