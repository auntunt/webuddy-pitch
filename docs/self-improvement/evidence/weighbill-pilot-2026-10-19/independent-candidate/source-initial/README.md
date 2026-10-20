# 称重单采集与台账子系统 `weighbill` 0.8.1

范围：**采集 + 台账**。手机拍照上传 → 视觉模型分割/识别 → 规则校验 → 入账，原图/单据图/签名图全部留存，台账变化可通知下游系统。

0.2.0 把 0.1 版的单文件 `app.py` 拆成一个标准子系统：核心逻辑只依赖**端口**，模型、存储、文件、身份、事件都是可替换的**适配器**。0.1 版的页面、接口、启动命令、数据库全部照旧可用。

## 快速启动

```bash
python -m venv .venv && .venv/bin/pip install -e ".[test]"
cp config.json.example config.json      # 填入 api_key
.venv/bin/weighbill serve               # 或:python app.py / uvicorn app:app --host 0.0.0.0 --port 8000
```

- 采集页（手机）：`http://<服务器IP>:8000/`
- 报表页（电脑）：`http://<服务器IP>:8000/report`
- 接口文档：`http://<服务器IP>:8000/docs`

```bash
weighbill version     # 版本(不碰库、不联网)
weighbill manifest    # 子系统清单(不碰库、不联网),宿主据此决定是否接入
weighbill health      # 各端口可用性;不可用时退出码 1
weighbill ingest a.jpg b.jpg --uploader 过磅员A
weighbill export --status needs_review > 待复核.csv
.venv/bin/python -m pytest              # 离线测试,不调用真实模型
```

## 0.8.1:原图保真与上传恢复

- 手机原文件原样进入待传箱并上传，服务端保存原始编码和全部字节。识别副本、裁剪图和预览图独立生成，不替换原文件。
- Excel 嵌入原图，只有显示尺寸变小；不再降采样或重新压缩。影像缺失、损坏或 Excel 不支持原始编码时明确拒绝生成，不悄悄缺图。
- 上传被拒绝时照片仍保留在手机待传箱，提供保存原图、重试。OCR 临时故障进入服务器重试队列。
- 暂存区使用跨进程文件锁；处理完成时校验登记仍在数据库中。上传批次标识绑定来源和照片内容，避免跨节点复用上传编号造成数据串用。
- 验收与环境接入边界见 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)。历史版本已压缩的文件无法凭空恢复，本版不覆盖历史图片。

## 0.8.0:迁移工具与跨服务器查重

- `weighbill migrate --source-config 旧.json --target-config 新.json [--dry-run]`:台账、图片(含预览)、修改记录、阈值原样搬,
  编号与版本保留、发号计数器抬高;可反复跑、断了接着跑;最后逐条逐字节核对,不一致退出码 1。来源暂存区有没处理完的照片时拒绝开始。
- 查重 + 登记包在跨服务器锁里(`RecordStore.named_lock`:OceanBase 行锁、SQLite flock),多台节点同一时刻登记同一张不会两条都悄悄进账。
- 实测:客户真实数据 102 条 / 206 张图迁到 OceanBase + RustFS 全部核对一致;整套用例在目标栈 200 通过。

## 0.7.0:OceanBase + 自建对象存储,七层防丢,图片预览

选型已定:数据库 OceanBase(MySQL 模式,`record_store: "oceanbase"`),图片 S3 协议对象存储(`blob_store: "s3"`,
RustFS / Ceph RGW / 信创对象存储;MinIO 社区版已停止维护,不用)。两者都对真实实例实测,整套用例在目标栈上 182 通过。
防丢:手机待传箱 + 离线外壳 → 服务器暂存区(先落盘再回「已收到」,失败自动重试)→ upload_id 保证不多登记 →
对象存储写入校验 → 数据库版本号与修改记录 → 每日核对 `weighbill verify --fix` → 备份。
预览:列表缩略图、详情中图、放大取原图,第一次被看时生成。详见 [deploy/PRIVATE-DEPLOY.md](deploy/PRIVATE-DEPLOY.md)。

## 0.6.0:为多台服务器的私有部署做准备

正式使用将私有部署在集团内网、多台服务器;预案见 **[deploy/PRIVATE-DEPLOY.md](deploy/PRIVATE-DEPLOY.md)**(目标形态、已就绪/待补、资源清单、故障处理、演练)。
本版去掉了只在单机成立的假设:记录带版本号,写入时核对(多台同时改同一张单不互相覆盖,`StaleRecord`);
磅差阈值存库(老的 thresholds.json 自动导入一次);网关模板 `deploy/nginx-weighbill.conf` 支持多节点、网关限流、日志令牌打码,已在真实 nginx 上实测。
`tests/test_multi_instance.py` 用两个独立实例共用一个库验证。

## 0.5.0:三路审计后的修补(数据正确性、安全、业务流程)

**数据正确性**:汇总/磅差/导出不再被 2000 条封顶截断;查重不再把不同日期、不同单号的单并掉,别人未审核的记录挡不住新单;
日期统一成 YYYY-MM-DD,没认出日期的按登记日期归档;磅差两边都多取两天再筛;修改串行化并留修改记录;Excel/CSV 防公式注入。
**口径**:吨位、车次、磅差只算现场已确认的(未审核+已审核),待现场确认、作废的不计入,看板注明并另报待确认;
有没配上的单时,磅差页同时给「只看配上的车」的逐车合计;日合计标红与单车同一规则(比例 + kg 下限)。
**新功能**:作废/恢复(不删、编号保留)、有疑问、修改记录;现场「最近上传」可找回没提交/没认出的单,能改单据类型、丢弃自己的草稿;
单据类型只记当天;编辑已审核的单据先确认;台账每分钟自动刷新。
**安全**:网关密钥 `gateway_secret`(配了以后只认 Caddy 加上的操作人头;匿名永远不是审核员;本机开发用 `local_user`);
像素炸弹在解码前拒绝(JPEG 先缩着解,手机 108MP 原图照收);上传限流 `upload_limit_per_hour`;拒绝跨站写请求;
现场链接按令牌摘要认自己的记录和图片;访问日志里的令牌打码;release.sh 任何一步失败都回滚并确认旧版起得来;备份包含阈值设置、写完才改名。

## 0.4.2:登记编号

每条记录一个系统编号 `前缀-登记日期-当天该类第几张`,如 `RK-20261014-0007`。登记时定下,之后改字段、改单据类型都不变,不复用,库里唯一;
识别失败的记录也有号。按**登记日期**编(磅单日期可能认错、被改)。前缀在配置 `ref_prefixes`,默认 厂商出厂 CC / 进场 JC / 出场 CK。
流水号由存储一条语句原子发放(`RecordStore.next_ref`,契约测试守着);老库启动时按登记先后补号一次(幂等)。
台账列表、详情、采集页、「已登记过」提示、Excel(原表列之后)都显示,可按编号搜索。

## 0.4.1:同一张磅单只登记一次

上传时在同类单据里找同一张(`domain.same_ticket`):磅单号相同;或号只差一个字(读错)且车号、净重、时间里读得出的都一样、至少两样对得上;
或没号时车号+净重+时间都一样;或号和车号都没读出时总重、皮重、净重三个数一样。命中就**不新建记录**,
返回已有那条并告诉上传的人(现场链接只给摘要:谁、什么时候、车号、净重、到哪一步)。候选 = 这次照片里已登记的 + 最近上传的同类单据 + 磅单日期前后一天。
相邻两张单的号本来就只差一个字(同一辆车连跑两趟),所以「差一个字」必须其余都对得上才算。

验收(`python bench/dedupe_eval.py data --config config.json`,cpu_ocr,客户 102 张真实磅单):第一次上传 102 张 → 新登记 102 条(没有把不同的单并掉);
每张再「重拍」(缩放、转 1.5°、压暗)上传一次:认出 101 张,漏 1 张(重拍那次号、车号、重量都没读出来,本身会被标成要人看)。
真实台账 102 张两两比对(1830 对)判成同一张:0。

## 0.4.0:无显卡识别(`vision_adapter: "cpu_ocr"`)

RapidOCR(PP-OCRv6 模型随 pip 包自带,onnxruntime 跑 CPU)出文字框 → `weighbill/ocr_fields.py` 按「标签格 | 数值格」配值、
按标题(`ocr_anchors`,默认含「称重单/过磅单/磅单」)把一张照片切成几张、纠针式打印的固定错字。数据不出服务器,不要 API key。
安装:`pip install '.[cpu-ocr]'`。可选 `serial_prefixes`:单号固定前缀(点阵 C/G、D/0 相混时按它纠正)。

两条与适配器无关的规则(大模型识别也受益):
- 进场单的车号不在当天/前一天的厂商车队里、而车队里恰好只有一辆差一个字,就改成那辆,并留提示让现场核对。
- 单据没印「日期」时,取出站(其次入站)时间里的日期。车号首字必须是省份简称。

验收(`python bench/cpu_ocr_eval.py data --config config.json`,走产品的完整上传流程,客户 102 张真实磅单):
车号+三项重量全对 91 张,24 张提示人看,**静默错(错了却 auto_ok)0 张**,每张约 2 秒(Apple M1)。
另用 9 张手机拍屏幕的留出照片:5 全对、4 提示、0 静默错。手写内容不读。

## 0.4.0:单据只分三种角色,名字全在配置里

代码里不写任何具体厂商、场地、客户。单据按角色分三种,内部键固定:

| 键 | 角色 | 默认显示名 |
|---|---|---|
| `supplier_out` | 厂商出厂单 | {厂商}出厂 |
| `site_in` | 进入我们场的单(与厂商出厂单配对算磅差) | {本场}进场 |
| `site_out` | 离开我们场的单(只采集,记客户) | {本场}出场 |

磅差 = 本场净重 − 厂商净重(正数 = 本场称得多),比例以厂商净重为基准。旧键 `byd_out / plant_in / product_out` 在接口参数、现场链接配置里照认,老数据库打开时原地改成新键。

| 名字配置项(config.json) | 说明 |
|---|---|
| `supplier_name` / `site_name` | 厂商名 / 我们场的名字,默认「厂商」「本场」 |
| `doc_labels` | 覆盖三类单据的显示名,如 `{"site_in": "原材料入库"}` |
| `doc_titles` / `summary_titles` / `summary_sheets` | Excel 每天一张表的标题 / 月度汇总表标题(`{m}` 填月份)/ 月度汇总表的工作表名 |
| `doc_notes` | Excel 表末的填表说明 |
| `out_sheet_suffix` | 出场单 Excel 按天分表、当天只有一个客户时的表名后缀,默认 `（{customer}）` |
| `customers` | 出场单客户的快捷选项 |

页面从 `/api/v1/schema`(现场链接从 `/api/v1/capture/<令牌>`)取这些名字。`tests/test_naming.py` 守着:客户的名字出现在产品代码里就失败。

## 0.3.0:按 2026-10-12 会议需求

**三类单据**:比亚迪出厂、加工厂入库、成品出库(客户记在「客户」里,如广富源、湛江钢铁)。码头不做。

**流程**:现场拍照 →「待现场确认」→ 监磅员核对(可改)后提交 →「未审核」,台账里实时可见 → 审核员对照纸质磅单**批量审核** →「已审核」。提交后只有审核员能改;改了已审核的单据要重新审核。

**现场链接**:监磅员不登录,直接打开 `/c/<令牌>` 拍。令牌在配置 `capture_links` 里,可以固定单据类型;链接只能看、提交自己传的单据,看不到台账。

**磅差对比**:同一车号,比亚迪出厂按时间顺序配加工厂入库(第 1 趟对第 1 趟),允许跨零点;磅差 = 比亚迪净重 − 加工厂净重。按天汇总 → 点开某天穿透到每车,两边磅单影像并排;没配上的两边单列。单车磅差率超 `diff_alert_pct`(默认 1%)标红;时间差只作参考,`transit_alert_minutes` 默认 0 不标红。成品出库只采集、不算磅差。

**统计看板**:台账页「总览」页签,数据来自 `/api/v1/stats?date_from=&date_to=`(数字大脑可直接拉)。三类单据吨位/车次/车辆、净重磅差、按天/按周趋势(点某天穿透到每车)、单车磅差分布、磅差×出站时刻散点(自动提示超阈值车是否集中在头一批)、磅差最大车次、车辆趟数、过磅时段、在途时长、货名/装点/客户构成、审核进度与识别质量。全部按磅单日期统计,图表手绘 SVG,不引外部库。

**Excel**:`/api/v1/export.xlsx?kind=byd_out|plant_in|product_out|reconciliation`。明细行嵌磅单影像(磅差明细两边各一张),汇总不放图,重量是数值。列顺序待现有线下台账到了再对齐。

| 新配置项 | 说明 |
|---|---|
| `reviewers` | 能批量审核、能改已提交单据的登录名;空 = 所有登录用户(试用期默认) |
| `capture_links` | `{"<随机令牌>": {"label": "比亚迪现场", "doc_type": "byd_out"}}`;属机密,清单里只显示「已设置」 |
| `diff_alert_pct` / `transit_alert_minutes` | 磅差率 / 时间差标红阈值 |

演示数据:`python bench/seed_demo.py <数据目录>`(3 天业务、含异常与未配对,不调用模型)。

### 0.3.1:对齐客户线下台账(2026-10-12 收到)

- **字段**:新增 装点、监磅员、供应商、备注;显示名改为 磅单号、车牌号、空重;单据类型改为 比亚迪出厂 / 原材料入库 / 产成品出库;列顺序与客户三张登记表一致(`/api/v1/schema`)。
- **只导出、不导入**:产品里没有导入入口。把客户线下台账装进本地做演示/验收用开发工具 `python tools/load_ledgers.py <数据目录> 登记表.xlsx ...`(不随包发布)。
- **磅差口径**:日合计 = 当天比亚迪全部车 − 当天加工厂全部车,总重/空重/净重三项都比,比例以比亚迪净重为基准(与《比亚迪&新岚过磅磅差对比表》一致);每车配对另列。加工厂名称配置项 `plant_name`(默认「新岚」)。
- **配对加了物理约束**:第 k 趟到达加工厂不可能晚于同一辆车第 k+1 趟出厂——少传一张单时标「没配上」,不会把后面的车次整体错位。车牌省份的繁体写法(粵/魯/蘇…)按简体配对,并在单据上提示改正。
- **Excel 导出版式照客户原表**:每天一张(表名、日期行、表头、逐车、合计、说明),月度汇总表;磅差导出照《磅差对比表》两行表头,另加每车明细(两边影像)与没配上的。
- **验收(客户 10-11、10-12 真实台账,共 102 张)**:导入后合计、10-11 磅差对比表 10 项数字与客户手工表完全一致;三张登记表导出与原表逐格 0 差异;102 张磅单图片与原表同一磅单号的图片字节一致。

## 页面

**采集页 `/`（手机）**：拍照或从相册选图 → 预览确认 → 分步显示「整理照片 / 上传进度 / 识别已等几秒」→ 每张单据一张结果卡，先说状态和下一步该做什么（不用管 / 等复核 / 重拍），再给净重读数、要复核的地方、字段与裁剪图。上传原始文件；只在服务端生成用于识别的缩小副本。识别服务未配置时一打开就提示并禁用拍照。底部列出本标签页已登记的单据。

**台账页 `/report`（电脑）**：默认打开「待复核」，页签带各状态计数，右侧显示当前列表的净重合计。点一行打开复核面板：左边照片（点击放大；分割失败时显示整张原图），右边表单；校验警告直接标在对应字段上，改重量时实时核对「总重 − 皮重 = 净重」。「保存，下一条」（Ctrl/⌘ + Enter）连续处理队列；重量对不上时保存前要求确认；有未保存修改时关闭或离开会先问。筛选条件记在地址栏里，刷新和转发链接不丢。

页面与样式都以 `Cache-Control: no-cache` 返回（ETag 未变时仍是 304），升级后不会有人停在旧页面上。不引用任何外部字体或 CDN。

## 结构

```
weighbill/
  domain.py  imaging.py  prompts.py   纯逻辑:字段、校验规则、图像处理、提示词
  ports.py                            五个端口的协议与契约说明
  adapters/                           端口的内置实现(固定清单,见下)
  service.py                          业务编排,只依赖端口
  bootstrap.py                        唯一装配点:HTTP、CLI、进程内调用都从这里拿服务
  http_api.py  cli.py                 入站适配器
  manifest.py                         机器可读的子系统清单
  testing/contracts.py                端口契约测试套件——新适配器必须通过
  static/                             采集页、报表页
app.py                                兼容入口(= create_app())
```

| 端口 | 职责 | 内置适配器 | 配置项 |
|---|---|---|---|
| `VisionModel` | 图片 → 单据框 / 字段 / 签名框 | `openai_compatible`（OpenRouter、内网 vLLM 等） | `vision_adapter` |
| `RecordStore` | 台账记录持久化 | `sqlite`、`oceanbase` | `record_store` |
| `BlobStore` | 原图、单据图、签名图留存 | `local`、`s3` | `blob_store` |
| `EventSink` | 台账变化通知下游 | `null`（默认）、`jsonl`、`webhook` | `event_sink` |
| `IdentityResolver` | 从网关注入的请求头认出操作人 | `header` | `identity_header` |

接入新系统（换 MySQL、换对象存储、换 OCR 引擎、推送到 ERP）的做法见 [docs/ADAPTERS.md](docs/ADAPTERS.md)。

## 流水线

上传 → 解码归一化（含 HEIC 伪装 jpg、EXIF 转正）→ 灰度对比度增强（仅送模型的副本）
→ 分割返回每张单据的框（外扩 2% 容错；兼容 0–1000 坐标与同框混用单位）→ 从原彩图裁剪
→ 逐张并行识别 → 校验：

- 总重 − 皮重 = 净重（容差 1kg）
- 车号：先去掉分隔点（`鲁A·5K862` 等各种点、句点、短横）；不含字母 I/O；普通牌 5–6 位、挂车牌 4 位 + 挂
- 序号：字符集 + 序号内嵌日期码与日期字段互验
- 时间格式、入站 ≤ 出站

→ 签名：识别附带框 → 墨迹吸附 → 墨迹占比校验，失败专项定位一次，再失败记「需人工框选」
→ 状态：全部通过 `auto_ok`，否则 `needs_review`；人工复核后 `reviewed`；处理失败 `failed`
→ 入账后发 `com.weighbill.record.created` 事件；复核后发 `com.weighbill.record.reviewed`

## 接口

**v1（子系统标准接口）**：统一错误体 `{"error":{"code","message"}}`，创建返回 201。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/v1/manifest | 子系统清单 |
| GET | /api/v1/health | 各端口可用性；`down` 时 503 |
| POST | /api/v1/records | multipart 字段 `photo` |
| GET | /api/v1/records | 参数 date_from/date_to/q/status/limit |
| GET | /api/v1/records/{id} | 单条 |
| PATCH | /api/v1/records/{id} | body `{"fields":{...}}`，重跑校验并标记 reviewed，记录复核人 |
| GET | /api/v1/records/export.csv | 同筛选参数，带 BOM |

**0.1 版接口**（页面依赖，路径/参数/响应/错误码不变）：`POST /api/upload`、`GET /api/records`、`GET|PATCH /api/records/{id}`、`GET /api/export.csv`、`GET /api/config`。

记录对象在 0.1 版 15 个字段之后追加了 `seg_model`、`reviewed_by`、`reviewed_at`。

## 配置

优先级与 0.1 版一致：**内置默认 < 环境变量 < `config.json`**。`config.json` 里出现未知键会**拒绝启动**（拼错的键被静默忽略 = 以为配上了其实没配），可用键见 `weighbill manifest` 的 `config_keys`。

| 环境变量 | 作用 |
|---|---|
| `LLM_BASE_URL` `LLM_API_KEY` `SEG_MODEL` `REC_MODEL` | 同 0.1 版 |
| `WEIGHBILL_CONFIG` | 配置文件路径（默认项目根 `config.json`） |
| `WEIGHBILL_DATA_DIR` | 数据目录（默认项目根 `data/`） |

私有化切换只改 `config.json`：

```json
{ "base_url": "http://<内网vLLM地址>/v1", "api_key": "任意",
  "seg_model": "Qwen3-VL-30B-A3B-Instruct", "rec_model": "Qwen3-VL-30B-A3B-Instruct" }
```

## 数据留存

```
data/
  ledger.db                 SQLite 台账(0.1 版的库直接可用,新增列自动补齐)
  events.jsonl              event_sink=jsonl 时的事件出箱
  images/YYYYMMDD/
    <批次>_orig.jpg  <批次>_r1.jpg  <批次>_r1_sig.png
```

对外只暴露 `data/images/`（URL `/files/images/...`）。备份 = 定时打包 `data/`。

## 门户接入

1. 移动门户以 H5 方式嵌入采集页 `/`（`accept="image/*" capture` 直接唤起相机）。
2. 用户身份由网关注入请求头 `X-Portal-User`（可用 `identity_header` 改名），直接传 UTF-8 中文即可，系统会正确还原。复核时的操作人记入 `reviewed_by`。
3. 系统自身不做登录，访问控制交给门户/网关层。

## 0.2.0 相对 0.1 的有意差异

每条都有测试先证实 0.1 版的旧行为，再断言新行为：

- **台账库不再能被下载**：0.1 版把整个 `data/` 挂在 `/files`，`GET /files/ledger.db` 返回整个库。现在只暴露 `images/`，图片 URL 不变。
- **中文操作人不再乱码**：`X-Portal-User: 张三` 在 0.1 版被存成 `å¼ ä¸‰`。
- **分割框全部无法裁剪时记一条 failed**：0.1 版返回 0 条记录，照片已落盘但台账无痕。
- **识别结果 / 签名框是数组时不再让整批 500**：0.1 版抛 `AttributeError`，同批已入账的单据与报错并存。
- **记录分割模型、复核人、复核时间**。
- **`config.json` 未知键拒绝启动**。
- **车号带分隔点不再报格式异常**：票据普遍印成 `鲁A·5K862`，0.1 版全部判为异常送进待复核；同时认挂车牌 `冀A·5837挂`。不合规的写法（位数不对、`挂` 前不是 4 位、含 I/O）仍然拦下。

重构本身的等价性由 `tests/test_equivalence.py` 保证：0.1 版 `app.py`（保存在 `tests/_legacy/`）与 0.2 喂同一份模型原始输出，逐项比对记录、落盘图片字节与模型调用序列。

## 已知边界

- 签名「人工框选」只标记状态，报表页尚无拖框工具。
- `webhook` 事件出口单次尝试不重试（at-most-once）；需要可靠投递用 `jsonl` 出箱或在网关侧重试。
- 健康检查不会真的调用模型（`vision.probed=false`），只报是否已配置。
- Qwen3-VL-8B 在部分多单据照片上把角点坐标 `[x1,y1,x2,y2]` 放在 `x,y,w,h` 键下返回，会被判为无效框、整张记 failed（不会静默丢失）。

多来源配置、业务边界与升级步骤见 [MULTI-ORIGIN.md](docs/MULTI-ORIGIN.md)。

### 台账协作编辑的版本条件

记录响应（含列表、详情和现场记录）增加 `version`。台账详情保存、详情/批量审核及现场字段提交均携带读取时的版本：

```json
{"fields":{"货名":"核对后的货名"},"expected_version":3}
```

`PATCH /api/v1/records/{id}`、兼容的 `PATCH /api/records/{id}` 和字段修改型 `POST .../records/{id}/submit` 支持 `expected_version`；`POST /api/v1/records/approve` 支持 `{"ids":["id"],"versions":{"id":3}}`。提供条件时必须为非负 JSON 整数；null、布尔、字符串、浮点及负数都不能作为版本。审核提供 versions 时，每个 ID 都必须有合法版本，缺失或不匹配逐条进入 skipped（包含 code），其他记录仍可成功。版本不匹配保存返回 409，且不会修改记录、写修改历史或发布业务事件；底层存储 CAS 继续防止多实例竞争。

**兼容边界：这些条件在已有 v1/legacy API 中是可选的。旧客户端省略条件仍可请求，但不保证端到端客户端防覆盖；并非所有客户端都已强制版本保护。** 其他作废、恢复、疑问标记等写操作不在本次条件写入范围内。

详情页遇到冲突或不完整/未知回执，会保留完整表单和原始草稿，读取并展示最新数据。用户可逐字段采用最新值或继续编辑当前表单，明确确认核对版本后再保存；不会自动合并、覆盖或读取最新版本盲重试。核对后的保存与审核分开操作。若最新数据读取失败，保存/审核保持阻断。草稿在当前页面内存中保留，关闭或刷新有提示，不保证浏览器崩溃后的持久恢复。批量审核失败不会显示成功；未知回执后清除选取，重新核对再审核。现场提交冲突或回执未知时保留表单并阻断重放，需由审核员核对最新记录。

### 完整前缀下的隔离预览

显式配置 `base_path`，例如 `/pv/WBILL-1/__commit/<完整40位SHA>`（实际配置替换为候选 SHA）。默认 `""` 保持根部署。前缀只允许安全路径段，不允许尾斜杠、查询、转义或路径穿越。代理应**原样转发完整前缀**；应用通过 FastAPI mount 处理它，不应另行剥离前缀或重复设置相同的 ASGI root_path。页面导航、资源/API、Service Worker、记录本地文件链接及 `/c/<token>` 现场页面均使用同一前缀。外部 S3 URL 保持原样；现场图片仍经来源校验路由提供。原图和导出编码/分辨率未变。

仅本机隔离预览的代理外部 Origin 与后端 Host 不一致时，可配置精确 `local_preview_origins`，例如 `["http://localhost:9090"]`。必须同时设置非空 base_path、保持 gateway_secret 为空，并将后端仅绑定回环地址；例外仅在客户端地址及后端 Host 都为回环地址时生效。生产不要启用。不会信任 X-Forwarded-Host，非白名单 Origin、null Origin、Sec-Fetch-Site: cross-site 仍拒绝写入。

定向验证（无需真实 OCR、外部数据库或对象存储，不读取 config.json）：

```sh
env -u WB_TEST_STACK -u PYTEST_ADDOPTS .venv/bin/python -m pytest -q tests/test_client_versions.py tests/test_concurrency.py tests/test_workflow.py tests/test_security.py tests/test_multi_instance.py tests/test_origins.py tests/test_original_integrity.py
```

新增 HTTP 测试使用临时 SQLite、ScriptedVision 和两个独立 TestClient，覆盖完整前缀实际路由、原图逐字节一致、旧页面保存/审核、显式核对后保存、ACK 丢失重试、非法版本及兼容请求。Node.js 测试执行实际页面控制器，覆盖草稿保留、核对门槛、失败回执及审核版本传递；不等同于真实浏览器端到端或部署验收。

隔离的 Webuddy 本地预览可用 `python tools/webuddy_preview.py --port <端口> --prefix <完整候选前缀> --data-dir <新专用目录>`。启动器只绑定 127.0.0.1，首次生成三条明确标识的合成台账及测试原图，后续保留修改；拒绝无预览标记的已有非空目录，不读取生产 config.json。真实 OCR 关闭，健康状态可为 degraded，不能据此宣称已接入现场识别。默认只允许 Webuddy 本机 8793 预览 Origin。
