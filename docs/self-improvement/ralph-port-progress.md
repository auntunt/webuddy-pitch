# Ralph port 执行进度

## 2026-10-26：现有官方Codex真实连接验证

- 当前项：done（本次唯一外层尝试已停止，取证包装层失败，官方客户端未启动，真实连通目标未达成）。起点9bd3d37，Git干净并读取进度、最近10提交与生产接入记忆。沿已有模型测试授权，验证Webuddy监督进程→真正已安装官方Codex→现有用户网关→模型；这不是重跑旧无工具/单响应协议，不受旧研究helper复审阻塞。
- 仅一次外层客户端启动、至多120秒、不fallback/切模型/重启或失败重试；新空scratch及新非业务合成prompt/唯一回读标记，不输入PPT、原A-B-C-D、holdout或oracle。现有账号和网关配置保持，密钥不复制导出；正常工具声明、初始化及辅助上下文如实记录，不冒充旧评测合同通过。旧b2a6永久停止及403原件保持，不新建真实业务根或代人采用验收。
- 预检已核：服务器@openai/codex 0.162.1、官方npm shim→codex.js，launcher SHA61b0194f…/package SHA41088ff1…与既有固定身份一致；native628e3548…/companion ec718306…/Node93956de2…及现役Webuddy agents/SP/PC逐项SHA、长度、模式现场匹配。原0600配置当前aiseat/Responses/gpt-6-luna、用户网关ai.cloudwaveai.cn，路由白名单元数据留存，未输出凭据；无模型/配置环境覆盖、MCP/hook，空scratch父链和全局无AGENTS。
- 前瞻计划在任何启动前固定于仓库外`分析/RSI协调/pilot-software-20261025/official-codex-connectivity-v1/`，plan SHA`8cdebf0539e0747b6fe86bf3a6794766cf33ab8a79966e0b6f494de8b56689a9`。完整argv由现役agents.command生成：原官方shim exec/read-only/skip-git/CWD/output-last-message，附json/ephemeral/color never及approval_policy never；模型沿原配置，不改账号/配置、不忽略guard或rules。新合成37×43题与唯一回读标记、prompt SHA、控制器源及120秒结束条件预先绑定；没有沿用旧问题或旧root预算/时钟。
- 实际失败：2026-10-26 13:48:28.938–13:48:29.065 CST，外层0.127秒，现有SP实际目标退出1、exited、reaped/output_complete/cleanup complete且无残留组。完整157字节原输出为strace的两条PTRACE_TRACEME Operation not permitted；强制strace是本次作者加入的诊断前置，不是官方客户端、Webuddy产品或网关本身要求。官方exec_io标记、stdout/stderr文件均未产生，trace无native执行，故外层尝试1、所见官方CLI实际启动0、真实回复0；不能说官方客户端已发请求被网关拒绝，也不能把本次失败转嫁给账号或模型。
- 严守单次边界：未去掉strace再跑、未提权ptrace、未改网关或伪造头、未重试/fallback。保留旧b2a6的403与永久停止；本批既没有复活旧根，也没有创建真实任务/采用/多人效果。原summary的outer_client_attempts=1仅指监督外层尝试；追加attempt-adjudication.json明确CLI实际未启动，0字节不表示客户端静默运行。model只证配置标签，真实响应model/usage/发票未知；没有将1CLI当1HTTP，DNS不是模型推理。
- 原件：服务器新私有/tmp目录内完整源码/plan/launch-once/进程追踪/监督回执/输出/summary共13文件21878字节已逐SHA/长度/mode取回，已知现有配置凭据值扫描无命中，未复制导出密钥。原始summary和157字节错误不改，独立判定追加保留。后验只读核对scratch仍空、配置完整SHA保持、指定目录关联进程0，未向保存PID发信号。纯材料核验不重跑CLI；不以组织机制210项通过覆盖这次失败。
- 固定包：manifest SHA`94704cac6c7c33ef7f52d5c5d4bf908aee9a9a136ff287a5069aa64d999d94ef`，33文件50730字节；未压缩tar SHA`7c2874c755fdd4ec4b5de16e22939dcabc1358748b367be434e12df5894fb370`，122880字节，逐34文件成员读回一致；新解包目录verify_package.py实际exit0，确认原字节和失败证据，不是33项运行测试或连接成功。未改产品代码，不重跑无关全量。
- 后续最小方向：若后续明确允许新的有界尝试，取消“必须strace”的诊断依赖，直接由既有SP监督exec_io→原官方shim，保留原配置、只读沙箱、完整输出和单次期限；这是下一计划，不回写或重试本次。当前阻断只属于本次取证包装，不成为普通工具协作/PPT或所有模型业务的永久准入门。产品源码、生产任务和服务未改；仅进度文档提交/普通推送及219运行文件只读核验，不重启。

## 2026-10-26：Claude研究网关HEAD窄修复与范围勘误

- 当前项：done（研究网关本地修复与材料收口完成，待独立复审；原客户端实验仍未通过）。起点81ca779，开工Git干净并读取进度及最近10提交。此前压缩后转入领导者审查，遗漏已承诺的HEAD小修复；本次补齐，不重复210项组织机制回归。领导者报告保留在仓库外分析目录。
- 范围：新目录`分析/RSI协调/pilot-software-20261025/offline-claude-m2-followup-v2/`复制原网关SHA9b4fd150…，保留旧673文件封存、原allowlist及1响应条件。只运行新本地合成HTTP回归；不启动Claude/Codex、旧fixture、真实模型或业务根，不改产品运行代码和生产服务。有限静态调查仅用匹配2.1.234的既有可读材料，不猜参数或新增额度。
- 修复：HEAD及已解析的未知HTTP方法统一进入完整record和原异常route中止，不再落入未记录/未停止的默认501。HEAD按协议不写响应体，分开记录表示内容与实际wire长度。abort和新grant使用同一RLock，停止先置位且后续POST不获新许可；已在停止前取得许可的并发响应不宣称被撤销。原两条allowlist及最多1份合成回复不变；不扩成通用框架，不宣称覆盖方法分派前的畸形HTTP。
- 红绿：完全相同的新测试源码，对原网关执行`PYTHONDONTWRITEBYTECODE=1 python3 test_gateway_http.py --source messages_gateway.baseline.py --artifacts red-http -v`，7测试方法/8个含子例断言失败/actual exit1。HEAD及BREW/PATCH/OPTIONS/CUSTOM-METHOD/lowercase均返回501且未停，随后合法POST获200/grant1；GET/显式abort后仍获许可亦准确失败。修复后同命令改`--source messages_gateway.py --artifacts green-http`，7/7、0skip/failure/error、exit0：HEAD400且零响应体/先停，后POST400/grant0，完整wire/body保留；两条允许路径、JSON/SSE正控、第二次请求及并发单许可均通过。没有弱化断言或放宽2秒socket/屏障时限。
- 稳定性：同一修复源20轮，每轮7项，140/140通过；各轮原始HTTP、日志、服务端状态和线程关闭记录完整保留。源SHA不变：网关`db22821c4e24afac19329358edb9ac5167a5411d294b1e4bfab280d1fbe70799`，原源`9b4fd150…`。只验证本地HTTP；未重新启动正/负客户端控、旧fixture或真实推理。
- 有限静态调查：复用2.1.234既有528份native可读片段及4份wrapper/README/types/原help，完整532份查找输入保留。K1g确有HEAD /api/hello及provider/proxy/socket/cert分支；这些不是保持原路由的受支持关闭契约。8处title邻近命中为功能公告UI/metadata/daemon名称；help的--name只承诺显示名，未承诺停止标题模型请求。未找到足以准入的标题/HEAD抑制控制，保持not_established_unknown；片段缺失不证明整个native绝无控制。没有猜flag、换model或增加响应/调用额度，不生成新运行计划。
- 追加勘误独立保存于scope-corrections.json：native+6 ELF身份不等于完整helper/runtime链；实际Git三次exec及同native rg、setpriv libcap-ng和Git libpcre2/libz未被七项清单完整覆盖，广泛/usr、/lib、/lib64挂载未穷尽固定。未来启动必须前瞻固定真实依赖及有限挂载范围，不继承Codex M1/M3。旧依赖数据未重采以改措辞。
- 原结果层级勘误：全部HTTP=HEAD1+POST2=3，合成回复grant1；客户端完整收到779字节title SSE和107字节主请求400体，但没有主任务成功输出。positive_transport_complete=false是组合成功谓词，不是完全没收包。标题POST缺自定义policy，主POST含policy及date/SDK上下文；两正文及retry0不证明串行或标题消费导致主请求。postcheck的进程/mount/lease为实查，no_product_data/candidate/provider部分字段为常量声明；fake usage/cost不是真实账单。已有collector错误累积/abort/summary处理予以承认，完整M5仍未通过。
- 封存核验：旧673文件/15917378字节全部SHA/长度/mode一致，旧summary及exact-evidence原字节不变。新包manifest SHA`931df152ce2f7e9cdc83bdf449a3674c51d51cf729d1cf0dcf34cae718e6454c`，5148文件/7083928字节；未压缩tar SHA`d6ce1fef9c3371f03b3286061a4848dd428d9cd606ebbddcca624b642a03a83c`、18350080字节，逐5149文件成员读回完全一致，新目录verify_package.py实际exit0。文件数量不是运行测试数量；默认核验不运行HTTP或客户端。
- 边界：停止的是原冻结无工具/单响应RSI实验组合，不扩大成Webuddy普通协作不能用工具或真实PPT工作不能开展。原b2a6真实根永久停止，403/client_not_allowed保留；无新根/延期/原料复用，个人采用、真实跨任务或多人净收益没有新增通过证据。仅进度文档提交/普通快进GitHub；按纯文档约定核219现役文件，不改产品运行代码或重启服务。没有新增待用户确认事项。

## 2026-10-26：Claude单配置M2启动条件与最多两控

- 当前项：done（有界批次已停止；正控incomplete，负控skipped，路线不准入）。起点1d75b5d…文档/c08b6ae4…产品，开工Git干净并读进度与最近10提交；现有授权允许条件化离线实施，无额外账号/价格/审批要求。产品没有改动；原b2a6永停，没有新真实root/真实推理、安装升级或账号配置更改。
- 启动依据已固定：同一服务器Claude包2.1.234、native SHA3473601e…；原--version124/5秒和help0保持。从相同ELF精确字节偏移取得可读SDK构造器、hQ extends MA、应用factory、URL builder及Messages方法：BASE_URL进入SDK，拼接/v1/messages或?beta=true；不是仅凭变量名。readelf固定/lib64/ld-linux-x86-64.so.2及6项NEEDED的静态闭包/摘要，声明只读/usr、/lib、/lib64、native文件、独立proc/dev挂载；不声称整个宿主依赖均已独立钉住。实际还观察到新空工作区内Git与同ELF的rg启动辅助进程，不能把它们当成额外控或模型Bash调用。
- 冻结后仅启动C-M2-P一次：单一argv包含真实空--tools与--setting-sources、bare/strict空MCP/settings{}/禁skills/不持久化；模型claude-sonnet-4-6、端口29871、完整policy/prompt/fakekey/两份JSON与SSE响应均在启动前固定。launch-source-manifest SHA `3ed04131e5955505e54d9cc03f852edfa9f57bff8564c27d73346f0efa13dc21`；actual exec使用-s65535，主--print实参无截断且真实空元素可核。settings{}仍是附加，完整空来源语义不因argv或退出值被宣布通过。
- 核心发现：正控实际发出2条完整POST，均到隔离回环/v1/messages?beta=true、tools=[]、retry-count0且正文不同。第一条是客户端自动生成会话标题的system/prompt，不含冻结的任务policy；第二条才是带自定义policy的主任务。只许可第一份合成响应，第二次尝试立即拒绝并取消；不能将标题推理重命名为免费控制流、删抓包或补第二份响应绕过上限。两调用的顺序/并发因果未凭收包顺序推断。
- 判定：空工具声明、init中MCP/skills/plugins为空在所见输入中成立，但**正控没有证明主任务完整收包/终态成功**。第一辅助请求还要求结构化title，冻结主任务文本回复不证明标题语义成功；不能把prepared/server-written当主任务received。严格完整输入与单次响应方案未满足，overall=incomplete_not_passed；C-M2-N未启动，内建Bash注入后是否拒绝执行/推进仍untested。没有随机未知工具或畸形事件的“假通过”。CLI的num_turns/cost/usage由本地fake响应计算，原文保留，不是实际供应商账单；原文“Request interrupted by user”在此是自动界限触发的取消，不是人类操作记录。
- 停止与清理：原12秒监督门未改，本次约1.71秒因第二尝试cancelled130、TERM回收、reaped/cleanup complete；root取证脚本exit0不计用例通过。39份最终原件/5235166字节已逐项SHA/长度/mode读回，前37份首次快照完整保持；batch-stop明确正控1/负控0，case mkdir与负控前置阻止重跑/继续。候选/evaluator UID活进程0、所属进程0、host挂载残留0、lease释放；未代人确认、采用或关单。
- 辅助采集失败保留：首静态采集阈值100命中108处、初alias假设hQ=MA不符，修为真实继承关系后得到同一native源码；两次本地exec分析误把helper argv/rg self-exec计作主--print，错误摘要及第二脚本保留，最后按实际主进程匹配。均无额外客户端/fixture重跑，不改原请求/输出。旧非阻断标签一并澄清：ToolsV2只显式列web_search、不禁止附加项；171是重复字段出现次数；上批collector0仅producer_reported，本批另留subprocess invocation回执。
- 可审包：仓库外`分析/RSI协调/pilot-software-20261025/offline-claude-m2-v1/`，入口result-summary.json、positive-exact-evidence.json及全部源/响应/trace/原件。evidence-manifest SHA `fbbd5bba6fcb9f6201e84d94cfe155cec4dc129fef604f183dd9014b042f3c95`，673登记文件/15917378字节；tar逐674成员原字节读回，并在新目录执行verify-package.py退出0。这是材料核验，不是673项运行测试。默认验证不联网；源码/计划与实际remote程序相等，原39文件逐项相符。
- 下一步仅交独立review：如再考虑该严格协议，先找版本匹配且受支持的关闭标题等辅助模型调用的依据；没有依据就保持该组合停止。本批不改配置、不换模型、不增加控/回复，不先补M4/M5/M6框架。旧M4 failed、M5/M6整项untested保持；本次普通终止不推广到所有活跃/脱组/持管道后代。仅进度提交/普通推送并只读核219现役源码，不做无关生产变更或重启；未测真人D/跨任务或多人收益，旧窗口不延期。

## 2026-10-26：M2受支持无工具能力有界判定与独立结论勘误

- 当前项：done（有界能力判断完成；当前Codex组合停止，路线不准入）。基线37c0c955…文档/c08b6ae4…产品，开工Git干净并读进度与最近10提交。按本批范围只复用既有固定官方help/schema与匹配安装的可读源码，未外部检索；没有新增CLI/fixture、模型请求或真实root，不轮换模型/开关、不执行替代路线、不修改产品。
- 独立复审：report SHA `2ccf9b54e4021b1ea7338c74128ec305bda813154ce5fa025a7a3a6f0465c79b`、decision `f2f086487c0101676732647c4cf167c7e6a6cb41212d393483894e30ac4e49e0`、manifest `a49f77e4ea12bb769a6e56a11d499a82d35d1dc48c0b8fa79fbf92007e814f53`实际核对。接受限定增量、不准入：M1/M3仅限定proved，M2/M4failed，M5/M6整项untested。此前37c0c95作者把M5/M6列“限定通过”偏宽，现追加更正，不覆盖旧报告/证据。
- 配置/解析依据：服务器@openai/codex package0.162.1 SHA41088ff1…、codex.js SHA61b0194f…与既有身份相同；本次SSH只读官方npm的JS/README/package及文件清单，不读取真实配置或凭据。JS79–112行只解析native路径、241–244行原样转发argv，没有工具策略解析；观察到的npm包不含可读native Rust配置解析实现或完整config-schema。实际native628e3548…与companionec718306…仍引用已固定受测身份，不将此次源码读取冒充新CLI执行。
- schema覆盖：从原固定run3 app-server schema-dump完整恢复317份JSON/3602403字节，逐份SHA绑定，结构索引171处tool/execution/feature相关属性。这是材料检查，不是317或171项运行测试。ConfigReadResponse `/definitions/Config/properties/tools`指向ToolsV2，仅含web_search；AppConfig/default_tools_enabled、omit_tools_from明确作用于connector工具；AppsRead.includeTools只是display-only元数据。ThreadStart.config任意字典、DynamicToolSpec声明以及TurnStart.toolOutput均没有提供关闭所有内建工具的契约；exec help也没有--tools。Config projection允许additionalProperties，故**不能由字段缺失证明所有native配置都不可能**，只结论“现有固定材料无法建立一个受支持候选”。
- M2决定：有依据候选0，新验证调用0，不再用已失败feature-disabled组合重复试验，也不猜未解析TOML字段、删抓包tools、换模型或缺companion制造通过。保留原禁用配对10工具反例；真实companion执行来自另一默认11工具配置，不能说禁用组已经实测执行。下一步若重议Codex，须先取得与该固定版本/构建匹配的官方native解析源或明确全局无工具契约，再审一个候选；本批不升级、不改客户端身份。
- 后续缺口仅登记，不抢先实现：M4的RAM许可不是durable reservation/unknown/recovery或connect/control/model总尝试硬止；M5短写循环已有修正，无须重做，但thread/write/fsync异常未进入完成门、流/SP/request未有可执行父子绑定、model/usage known/unknown尚非正式适配层；M6只已证Node/native取消/原12秒/结果竞态/原A拒发，活跃companion、脱组/持管道后代和所有槽/不同root未证。原strace -s0截断字符串，完整声明argv/env来自源码与argv-env.json，不能再称完整独立实参抓取。
- 下一可审路线：仅形成`claude-next-route-plan.json`，不执行。固定既有服务器Claude安装包2.1.234/native SHA3473601e…；原--version5秒124仍失败，help0有明确bare、tools空、strict空MCP、setting-sources空、禁skills和无session持久。方案列完整argv空字符串、fake ANTHROPIC_API_KEY、独立HOME/同OS隔离/无上游、最小正负控；base_url路由及版本依赖证据尚须在任何未来执行前核定。绝不删bare或把真实AUTH_TOKEN改当API_KEY，不宣称真实账号/模型可用。
- 固定产物：仓库外`分析/RSI协调/pilot-software-20261025/offline-native-m2-capability-20261026-v1/`：M2-capability-decision、candidate-source-analysis、review-boundary-corrections、Claude方案、全部317 schema/可读源/10份引用原件。manifest SHA `4bdab96b1163db2fb75230cf60a4fad425d67a631165046a7711cfd6ae9938b4`，342文件/8801010字节；独立tar逐343成员读回相同。`PYTHONDONTWRITEBYTECODE=1 python3 verify-fixed-inputs.py`通过，仅校验固定字节/JSON/零候选与零执行，不联网、不运行CLI。旧1525文件seal不修改，原失败根b2a6c8da…永停。
- 身份标签勘误：6a43fb22…/d939c9be…是bundle-manifest SHA；实际v1 tar SHA `cb2b1c9d35155f0b98b96aa9ece76fb2a1548db94407fa11ba42187fbf0775e5`，v2 tar `ea167f89c4813178fc63d077083b13855e0a64fcca0af555ade89289075ba8db`，均92160字节。本次再次核对，无字节差异，不把标签误用说成包被替换。
- 发布边界：仅进度文档提交/普通快进GitHub；按纯文档约定核219现役源码与服务，不重启，不跑无关产品全量或以检查数替代准入。新固定能力结论仍交独立review；不代人采用/验收/关单，不重提已取消cap/价格审批，不将跨任务收益、本人采用新D、多人持续交接或旧窗口延期写成已证。

## 2026-10-26：官方Codex实际离线记录网关与隔离验证

- 当前项：状态done（离线研究与固定证据收口；**所测路线不准入**）。没有产品运行源码变更。实际服务器官方Codex0.162.1；17个新场景加原23个观察共40个场景，不是40项单测。新增15例执行真正官方客户端，另2例是明确标识的合成Python负控；不把负控冒充原生执行。原b2a6c8da…根仍永久blocked/unknown，本轮不触碰其暴露输入、不新建真实root、不推理真实供应商、不改真实配置、不安装升级或伪造客户端头。
- 固定成果：仓库外`分析/RSI协调/pilot-software-20261025/offline-native-codex-v1/`，`offline-gate-summary.json`逐项M1–M6/S1–S8、`case-identities.json`完整case/请求/流身份、`source-lineage.json`原run1–5及新四次启动的精确源绑定。9份原始读回清单共1408文件/12614712字节，逐项SHA/长度/mode无差异；不覆盖原失败原件。固定v1执行包manifest SHA `6a43fb22206aa49e3bfd572c70e183531646b4debc0fbcfe26a19ebcab56b54f`，v2 `d939c9bea8cd9f54dce4acae11791c698ef93867350061c86284fade674f7257`；两个tar实际逐成员读回，默认runner --verify不联网。v2仅增加取消返回/真实超时两例及trusted broker取消触发；不改原固定Driver。
- M1限定通过：新包实际执行Node22.23.1→官方codex.js→native→code-mode host；launcher SHA61b0194f…、native628e3548…、companionec718306…、Node93956de2…，原字节只读挂载，完整argv/env/cwd/strace和UID508101记录。原supervisor/process_control、原Driver SHA1a07b89a…保持。旧run1–5直接运行native，run1–4漏companion，不能冒充完整安装证明；run5已补完整native+companion，Node启动链只由新包证明。
- M2准确失败：干净两臂即使关闭所测特性、skills文件和项目文档读取，完整请求`input[0].additional_tools`仍含namespace functions/custom exec；顶层没有tools并不等于禁工具。run5真实code-mode host执行JS，第二POST有custom_tool_call_output和实际marker；新包同样实际执行并发2POST，但第二次转发被拒。旧run2 shell命令在bwrap安装边界失败，不能说shell已经执行。没有用缺companion或disabled-host错误冒充禁工具成立；完整污染入口扫描与严格双臂语义等价未验收。
- M3限定通过：每例独立scratch HOME/config/work/fake key、mount/PID/net/ipc namespace，数值UID互斥租约；同边界公开canary可读，evaluator508102正控摘要相符，绝对路径/symlink受保护oracle拒读，真实host-only canary未挂载，父proc env/FD拒读，cap全0/no_new_privs。CLI不能覆写root保护回执。未挂生产data、真实HOME、原题/答案或秘密；不宣称穷尽内核攻击。
- M4部分通过、整体未准入：OS仅loopback，DNS/直连/代理/子进程拒绝。网关无上游实现，预定每槽至多1次合成模型forward、8连接准入、2控制请求准入；所有已观察拒绝及完整strace保留。负控12次连接观察/8准入、3GET/2准入、5POST/1forward。**准入上限不是尝试总数硬上限**，该缺口明确保留。原uncapped run3 HTTP503 18POST/断连6POST仍为反例，不倒填新上限；新503 7POST但只有1forward，后续全部拒绝。
- M5限定通过：trusted root独立stdout/stderr原始pipe、nonce/owner/hash/长度/mode/请求关联；stderr伪合法final而stdout无final时，CLI/helper退出0仍被Driver拒收，回执覆写失败。候选产物声明为整个原始stdout.bin，不抽取/拼接policy；40字节实际CRLF/中文/emoji和双消息保留，last-message仅派生对照。缺response.completed虽有agent_message仍阻断；usage省略时CLI填0，实际usage保持unknown；请求model绝不替代响应身份。完整fake响应计划/已写字节与CLI收到分列，40字节或response_complete只证明fixture进程完成，不代表禁工具、真实准入或质量。
- M6限定通过：活跃真实CLI请求后取消；独立真实12秒门触发call_timeout，原Driver与监管器回收全链。另一例真实CLI已完整输出、Broker在返回前设置取消，原结果保留且response_complete=true，但Driver complete=false/explicit_cancel；不会推进。原intent和实际HTTP出现后只杀自有controller，原supervisor owner_lost125、reaped/cleanup complete；无A-result时原目录重开零派发，有结果的其余场景也全部重开拒绝、HTTP计数不增。取消不证明真实远端工作/费用停止。
- S门汇总：S1/S2 fail；S3、S5–S8限定通过；S4 partial（错误/重试与单forward成立，尝试总量门仍缺）。M1/M3/M5/M6限定通过，M2 fail，M4 partial_not_qualified。完整M2失败已经足以判定所测版本/配置不满足路线，不能以其它通过数量冲抵。Claude假API_KEY替代路线、真实账号403解决、真实成本/Token、真人采用及组织ROI均未测或未证明。
- 命令/结果：固定runner --verify（9源文件）通过；v1三组指定case、v2两例均使用expected-bundle-sha固定后经SSH sudo运行无上游夹具，原始启动程序/输出/exit保留。四次root wrapper实际exit0仅表示取证脚本完成；各失败case保持incomplete_blocked。owner-loss原controller实际-9、supervisor125不改写为成功。readback.py四次完整读回，assemble-summary.py断言全部来源、负控、字节与停止事实通过；没有重跑无关全量或用此前152项组织功能测试代离线gate。
- 收尾：候选/evaluator UID活进程0、自有四根相关进程0、host mount相关残留0、UID lease可非阻塞重新取得并释放。证据`postcheck.stdout.json`；真实模型配置只核摘要不输出内容。产品源码/守卫/锁/人工确认未变；本次仅提交进度，普通快进GitHub，按纯文档约定核219现役运行文件与服务，不重启服务。独立review仍须审固定包，作者自验不充当独立准入。
- 精确剩余项：若将来重议路线，先取得版本匹配且递归tools为空、注入工具也不执行的官方配置/合同；补连接/控制/模型尝试总上限及到限停止；补完整输入入口污染与等价验证。当前不通过升级、更换模型、修改headers或复活旧根绕门；本轮已完成必要离线收口，不以缺真人或账单重新提问。

## 2026-10-26：官方客户端与本地Messages路线只读核查

- 当前项：失败根之后的只读接入可行性；状态done（核查/最小差异/离线验证方案已形成，不代表路线准入）。实际root b2a6c8da…仍永久unknown/blocked，不再请求、改profile、延期或新根刷新；本轮模型/连通性请求0，无安装升级/配置修改/凭据导出。
- 版本：Mac Codex --version 0.163.0、Claude 2.1.310；服务器Codex --version 0.162.1，Claude安装包2.1.234，其--version在原5秒门超时124并完整回收、无剩余组，随后--help0/约0.332秒。不重跑到通过、不把package版本当成功的CLI版本输出。两端完整help、包/launcher/native binary身份与原配置公开字段均留存。
- Codex：exec help支持stdin/ephemeral/ignore-user-config/ignore-rules/JSONL/output-schema；两版本help未列禁用全部tools开关，read-only明确只是模型命令的沙箱策略，不证明禁止读取oracle/隐式设置。底层特性、内部重试、完整有效请求/真实response model与usage未知；403声明只准官方客户端不等于已验证该CLI成功。不能据此启动新实验或伪装headers。
- Claude：两版本help支持原strict组合tools空/bare/strict空MCP/setting-sources空/禁skills/不持久session/独立system。bare help说明Anthropic认证仅API_KEY或显式apiKeyHelper；本机既有3425回环配置只有AUTH_TOKEN，不能推定严格bare链已认证，也不能删bare或擅自把token改当API key。当前模型标签commandcode-plan/deepseek/deepseek-v4.1-flash[1m]、可用性/账号准入仍未知；Mac回环不等于服务器回环，旧CRLF实测失败保留。
- 原生Messages：现有单请求adapter可支持Messages，但当前live profile严格HTTPS，原本机配置为HTTP回环；不得把真实调用标fixture或放宽已接受profile/guard。任何后续传输类及认证/OS隔离/隐式attempt计量须独立前瞻审定。
- 最小可审材料：仓库外native-route-feasibility-v1/feasibility-decision.json，逐路线列支持/不支持或未知、最小适配差异；离线方案包括完整有效请求/禁工具与隐式输入、独立oracle OS拒读、429/断流内部attempt计量、完整CRLF/Unicode输出及model/usage未知、总时限取消/进程树回收。方案未执行模型测试，不冒充隔离通过；未来不得复用旧暴露任务/答案或复活失败根。

## 2026-10-26：独立实际A隐私接受后的有限真实实验

- 当前项：原实际A/3BC的一次性登记与有限真实模型实验；状态done（一次有限执行及失败封存结束，实验未通过且不完整）。实际A隐私/Catalog/断言v2独立结论已直接读回接受，无新增软件阻断；运行c08、计划a87879…、驱动1a07b8…及50..53原输入保持。先fresh核身份/源/配置再激活，原8槽/1200秒A-BC/43200秒总根/120秒单次/null总cap不变，不做模型预调用。A完整原回复须符合原policy JSON约定，不合格停本根，不抽取/改写/重试。D仅实际本人采用后新建并同根执行。
- 历史范围纠正：06:27的业务66表是当次SQL计数；控制11表来自此前基线及06:13控制字节保持断言，06:27输出的控制不变字段为常量，不能称当时重新SQL核对11表。旧原记录保留；本次将单独fresh查询实际计数。

- 预检结果：07:10及07:13 fresh读取，219运行源码/15私有RSI文件、li当前authz_revision=7与execution/manager、default/PPTAUTO4/来源4、50..53原任务整行、原capture/Catalog及四请求SHA均一致；现有aiseat/Responses/gpt-6-luna及配置SHA不变，无预调用。SQL实查业务66/控制11。首轮助手错误把Store解码JSON列与raw SQLite行比较而失败，原脚本/错误保留；v2直接读取raw行，未替换任务/原件，完整预检通过。
- 一次实际登记：07:13:56.314864 CST激活，A/BC截至07:33:56.314864，总根截至19:13:56.314864；8槽/120秒单次/null总token保持。root `b2a6c8da32006e9ac45a3a5ff50bc5ae07e382ddf02480a6858dfe278aea5ed9`；actual profile `30abd639c5aa8e461ae5fcd9707252936cd1ea340df2d41763e483a80c0e64e1`；完整provider contract `97c0b3ad5df5e1362e0480120942ad9ae1ee55c816b45a3f5cc15d09fc844cd4`；原BC freeze登记SHA `b1f9c1c8a09a105f8f09ca86d5a6a60294c0cd88528be9600c95f0ffdcc9d74a`、replayed=false，均在A前完成。D材料/原断言私有封存，无D任务。
- 实际A结果：经原审定driver唯一一次请求，实际request2915字节/SHA b1fb2610…与独立审定完全一致。代理HTTP403 / client_not_allowed，明确账号仅允许官方Codex客户端；非超时，原transport进程约1.15965秒exit0、完整输出/回收、remaining_group=false。HTTP完成不等于模型成功，Adapter按原规则留unknown、账本1次attempt/root blocked；driver complete=false/blocked并追加cancel，无重试/新根/客户端伪装、profile切换或延期。
- 当前结果：有限执行与失败封存完成，工程实验**未通过且不完整**；A无完整模型回复，未进入policy JSON检查/候选绑定，BC0、D0、无job/revision/本人采用。actual_response_model、usage、实际费用和上游隐藏attempt未知；reported_tokens=0只是已报告累计，不能当真实消耗0。未形成BC收益、D或组织收益证明。
- 原件核验：服务端24份执行/登记/完整响应/监督回执/驱动原件42436字节全部SHA/长度/mode读回后再次重核；私密runtime凭据仅留服务器0600私有registry，不导出。建档前/登记前备份数据库均留服务器；原66表除sqlite_sequence外所有旧行以及所有旧schema对象保持，只新增4张原rsi_prepare表，当前业务70/控制11实查；4任务仍原行、项目run0/decision0，服务active/running、重启0。产品源码未改/未重启。
- 交接：仓库外native-real-engineering-plan/actual-finite-execution-v5/actual-experiment-result.json、registration.json与完整server-originals、readback-manifest.json；根unknown与失败原件保留，不恢复旧DB。下一阻塞是代理客户端准入限制；本根不继续，不能把旧预算/API问答或已通过隐私审计重新列为待办。不得因另接官方客户端而复用/刷新本根或宣称已完成真人试点。

## 2026-10-26：真实暂停任务与TASK捕获封存

- 当前项：原生创建A/3BC并封存真实TASK输入；状态doing（真实建档、捕获及作者核验已完成，等待独立实际A隐私审计；不提前激活）。起点f3a0623，开工干净，已读进度、最近十条提交和本机生产接入记忆。v5限定独立接受已直接读回：返回取消P2软件关闭、窗口实现关闭，原题意/分阶段冻结结论保留；不再把软件审查或c08发布列为依赖。
- 实际操作：2026-10-26 06:13 CST，通过未改动tenant_policy.authorize与agent_api.dispatch原生接口，用既有有权限技术主体创建4张paused工单；主体为既有技术身份，Agent署名`agent:member:li`，不是LYB/LLA个人会话。每条有独立稳定request_id、complete回执和完整原行；全部new+hold/handwork、execution_started=false，未给两位成员授新权，未创建个人会话、D、模型run或采用。
- 当前对象：default / PPTAUTO项目4 / 来源4 / development；原空非Git工作区保持，不初始化Git，不覆盖旧项目说明。原PPT完整文件SHA与完整单页文字/题目/schema先核对后建档。新任务是本次技术准备，不是旧五小时多人试点复活或真实参与证据。

| 实际任务 / DB ID | 固定输入 | 捕获内部完整性SHA | 原生Catalog整条记录SHA |
| --- | --- | --- | --- |
| PPTAUTO-1 / 50 | A-policy | `324a2e203304a29935016efd2ba729e4c363b34f4f2de304692af62389d7691b` | `7529813b46860370c49170e020796e26368bf6774e90b03605203081b4ddced3` |
| PPTAUTO-2 / 51 | B-case-record | `2e273163b7dd3eec87065e2cc87dca49eb48879ed6a7262fae92156673f50bd2` | `642060b9a958f5e6cd93b0315db1bef423bed8441808ddf32b397e807bac6be0` |
| PPTAUTO-3 / 52 | C-cumulative-metrics | `7afc4b73fc5714d1fb76674ba2612f93566a5e33dd09bf4fb7dc8a2ccab11b9c` | `65fd9c84c5330e7bfda56e8b2ab5bc0ad9430aa6a47699b82a13421c793cdafc` |
| PPTAUTO-4 / 53 | C-cross-project-boundary | `99713aae9b6fe091e86b087511f0635963896a4f6222821786f481605675e5c5` | `767548be32cf90e811baf42779afdcf08b97e13229f3877f8106f2a727a6ca46` |

- 原件：4份完整任务行、4份原生创建回执、4份实际TASK分支capture与4份effective包等22份194358字节，从原服务器私有目录完整读回SHA/长度/mode；没有复制生产备份数据库或旧账本前缀到Mac/Git。原生Catalog.admit/load另封存4份完整规范记录，owner UID1000/0600，输入目录封存不等于root登记；没有activation/profile/contract/root时钟或供应商请求。
- 副作用核对：服务端保留建档前SQLite备份；旧63表所有原行和旧schema对象保持，只新增4个ticket、4个created事件及4个Agent请求complete回执。原接口按需建3张既有schema表agent_requests、agent_run_sources、harness_probe_runs，当前业务66表；后两表为空，不是rsi_prepare_*。控制DB字节/成员权限/原lessons字节不变。原工厂按原逻辑追加4条PPTAUTO-1..4的nomatch检索审计，原日志前缀完整；这不是模型运行或真人劳动证据。
- A实际输入：真实task50/PPTAUTO-1，经实际已发布factory与精确c08私有broker原TASK分支捕获，包含真实learning_lessons selector/renderer块（当前无匹配知识）；history为空。exact原生Responses请求预览2915字节，作者15项检查通过：A完整原页保留，不含BC/D任务key/文本/答案、整份计划、旧窗口/上限，tools=[]/truncation=disabled。私有capture元数据仍保留原项目历史说明，native_effective只发送prompt，不把元数据送模型。原analyze模式的代码定位指令完整保留，system要求指定JSON；不删改共同提示，也不将文本提取等同PPT质量或组织收益。作者核验不能代替独立A隐私门。
- 摘要口径修正：捕获内部capture_sha256不含自身摘要字段；Catalog整条canonical记录SHA包含该字段；pretty文件SHA又是原件身份。首版未登记的assertion准备稿混用了内部SHA并混入额外case元数据，保留v1；v2改用原生Catalog实际admit/load摘要，native BC模板字段与provenance分开。原任务/捕获/题意、expected/forbidden/阈值完全未改，root依赖字段仍null，未运行Reports.freeze或模型。D原材料和独立断言完整封存，D任务/采用/job/input绑定仍为空。
- 当前可审包：仓库外`native-real-engineering-plan/actual-task-captures-v5/independent-A-privacy-review-packet-v2.json`、`actual-bindings-v2.json`、`private-actual-case-assertions-preparation-v2.json`、`input-catalog-admission.json`及原件清单。当前provider/profile草案来自现有0600配置，aiseat/Responses/gpt-6-luna，config SHA `e1fdd620e99d325356dfcf1041da55712843905d97750c3ed4fec79ff9d8b9d4`；密钥留原处，actual_response_model/actual_profile_sha256未知，正式profile未入册，无预探测或额外预算/API询问。
- 精确身份：运行代码c08b6ae4ffe140d1d6cb35b7671d4410890ca62b；计划SHA a87879c0da0e6e964d855ed82a7455baa2b1d41c9b9b00a29a179750e4f2cbf7；驱动SHA 1a07b89a37cd5aba661e9b9d9f51ed9ac7acca825df2630d6c23aaf7107acb8b，均保持。06:27 CST再核旧schema对象、4项暂停状态/无run/无decision/无rsi表，以及219运行源码、active/running/重启0通过；只记观测，不重启已接受发布。
- 当前剩余：独立实际TASK A有效payload隐私审计及真实绑定核对；通过后再一次性actual activation/profile/contract/root绑定、原BC断言freeze，然后仅经已审驱动调度A/BC，A后只用真实完整输出形成候选和成对计划。D仍需真实本人当前采用后新任务/selector捕获。当前模型调用0、工程root未登记、时钟未启动、D未创建、rsi_qualified=false；旧失败/unknown/v4原件、question预捕获与unadmitted模板均保留，后两者仍不可用于真实登记。

- 收尾复核：真实任务绑定manifest-v2的56份原件共783142字节逐份SHA/长度重核零差异，清单SHA `87eb8fae9ddd3ce22cf152449d20a8bfafd9674aab1bbc21fb275545ae95ead9`。交接JSON移除已关闭的软件/发布待办并保留旧字段历史，唯一当前门为独立实际TASK A有效请求隐私及原生Catalog/私有断言v2绑定审计；未启动模型或时钟。补充组织产品只读审查的8模块154项专项12.548秒/exit0，不替代已通过的精确发布门或真实团队效果证据。

## 2026-10-26：真实RSI接入准备与取消返回竞态

- 当前项：已授权真实工程实验的可执行准备；状态doing（接入只读核对与新驱动作者验证已完成，v5登记前独立复核仍待）。起点3a961df，开工工作区干净；c08已发布，独立补审接受限定历史发布证据，发布不再是待办。运行代码仍c08，未重启或修改生产产品。
- 独立v4结论：PLAN-D-TARGET-01、PLAN-FREEZE-SEQUENCE-01在规格层关闭；PLAN-HUMAN-WINDOW-01因新增P2 `PLAN-DRIVER-CANCEL-RETURN-01`未关闭。watchdog最后一次读到未取消后、Broker返回前发生取消，旧最终回执只复核时钟，会记complete=true；外部Event路径还可继续B0。原v4计划/驱动/独立反例和历史证据全部保留，不改成通过。
- 新v5驱动：在watchdog join之后、决定持久回执前重新检查cancel.json和外部取消；保留原结果，但写complete=false/explicit_cancel与blocked，不允许下一槽或重发。激活schema更新v2；原1200/43200/120秒、8调用、null总token、权限/guard/断言均不变。固定驱动SHA `1a07b89a37cd5aba661e9b9d9f51ed9ac7acca825df2630d6c23aaf7107acb8b`；只修改仓库外私有控制器，生产源码未改。
- 验证：新增真实线程屏障两条在v4准确2目标failure/0error，修后2/2。Mac/Linux各原16+新2+原独立8=26项通过；独立8断言原文未改，仅绑定新驱动。Mac两屏障各50次，共100/100，0失败错误；分别删除external/durable最终取消门的变体各准确1目标failure/0error。两端各一次真实FiniteBroker→监督进程→回环HTTP仍在缩短1.5秒窗口取消、原unknown保持、子组回收、重试不增加请求；原时限未放宽，不把此视为真实供应商或等满20分钟。新驱动仍需独立重新复核，作者验证不代替关闭P2。
- 新计划v5 SHA `a87879c0da0e6e964d855ed82a7455baa2b1d41c9b9b00a29a179750e4f2cbf7`。相对v4仅更新驱动/版本与修复说明；A/BC/D原完整材料、题意、schema、独立oracle、阈值、四阶段冻结、原时间/调用限制全部一致。尚未创建真实activation、root、profile或新任务，未延长/复活旧根或旧五小时多人窗。
- 真实接入只读核验：现有服务器0600配置仍aiseat/Responses/gpt-6-luna；凭据仍在原配置，没有输出/复制值，没有供应商HTTP（包括未发模型目录探针）。模型目前只证配置标签，actual_response_model与权重身份尚未知，不能伪造成功调用。只备妥未批准、未入册profile模板，actual_profile_sha256=null，deadline/contract/credential runtime reference留待实际一次激活绑定，不装成已冻结profile。
- 实际对象：default / PPTAUTO项目id4 / 主来源id4 / development；工作区为空且非Git，原样如实记录，不初始化Git、不覆盖历史项目说明。原34页PPT及SHA已核，不是缺少用户材料。本项目当前没有工单，真实A和3个BC任务ID为空，D任务必须本人采用后新建。旧项目说明保留已过期窗口及100M历史，不作为本轮授权；A有效提示中没有这些旧窗口/上限文字。
- 身份：通过原Registry/TenantContext/tenant_policy在真正只读SQLite连接上核对现有权限，跳过会初始化schema的构造器，不改账号/权限。既有平台所有者具备当前工程执行资格，LYB/LLA保留原contributor/manager且runtime_allowed=false；这些元数据不是本人登录、参与或采用，未授新权或代签。
- A原工厂预捕获：已从实际已发布agents.py和精确c08私有registered_trial.py执行project-question分支；生产DB/控制DB/原账本字节前后相同，捕获期间禁止socket。完整A单页及原题保留，实际有效包不含BC/D任务ID、整页材料、独立oracle或整个计划，tools=[]；原检查9项及补充请求检查12项通过。该捕获ticket_id=null、明确eligible_for_registration=false，不能代替后续真实任务分支的最终A捕获。首轮助手误从不含私有scripts的运行包导入而失败，原日志保留；改从已核15份私有脚本的验证包导入，实际factory仍来自生产app，不修改产品或sys权限。
- 当前原件：仓库外`native-real-engineering-plan/actual-engineering-preparation-v5.json`、`prepared-inputs-and-plan-v5.json`、`plan-v5-driver-readiness.json`、`driver-v5/`、`A-question-pre-capture-v2/`。实际factory SHA `2522cab2e15deb4acc236e0511ae3511956edfa58a1098172cd9fcf40f929e36`，私有broker SHA `1eeb8699e0688d587857615035d9be4542749689b74721bec78a5c3029778097`；question捕获SHA `ceb1647ae50b9f8c9b6c13b0354c24759d5a88cec0f335e7b97c4461ce31380c`，不是实际任务捕获。
- 剩余依赖：新v5/驱动独立关闭返回取消P2；获准进入登记准备后创建真实A/3BC任务、重新固定实际任务捕获并独立审计A精确有效请求；随后一次真实时钟、原profile/root/凭据运行引用及BC/D独立断言绑定，才可有限A/BC。D仍需真实本人采用与原selector/renderer新任务捕获。当前工程根未登记、模型调用0、本人采用false、rsi_qualified=false/production_equivalent=false；不重复索要预算、100M硬界、价格或原生API。

## 2026-10-26：c08 精确发布门与真实工程计划分阶段冻结

- 当前项：原生job/本人引用/同根D与UI修复收口；状态done（软件发布收口；真实工程计划v4/驱动已固定，登记前独立复核仍待）。起点c08b6ae，当前iteration/context-pack-v2开工干净，已读进度与最近十条提交。3cc独立接受限定于软件桥，c08独立接受限定于UI；独立6条Node脚本含9947矩阵行，不是9947个单测。两者均不证明真人采用或组织收益。
- 原失败保留：R1 Linux全量原1000秒门触发TimeoutExpired/SSH1，full_exit与smoke_exit未知，未完成2510项、不计通过。诊断根352.937秒主动精确组SIGINT退出-2、SSH0，只作时序分析；停止前快照737，最终751条stop包含中断清理，不是全量通过。原源、日志、失败traceback及诊断记录14份289983字节SHA/长度完整读回，R1与诊断各512声明源+2metadata=514成员未变。原30.412秒真实deadline反例保留。
- 环境判断：同源Store初始化三组磁盘0.653/0.540/0.581秒、tmpfs0.286/0.287/0.219秒，支持测试临时SQLite I/O是重要耗时因素，但不是全部耗时的排他根因。新R2目录c08b6ae4ffe1-native-job-20261026-tmpfs仅将合成测试临时文件放在私有0700 tmpfs；源码、原测试/断言、1000秒全量和90秒smoke门不变；smoke明确去掉TMPDIR，迁移、生产、备份仍原磁盘。不据此证明生产磁盘持久性或生产性能。
- 精确最新门：Mac2510项2472通过38skip/actual0、713.558秒；SDK1.30.0 74/74零skip，均绑定c08原源。新Linux2510项2474通过36skip/0fail/error、692.242秒/full0/SSH0；随后100项合成HTTP smoke/smoke0，指定gateway/两worker退出、socket/key移除。原资源警告保持，不能宣称无资源问题。R2完整数据副本1781成员，两轮幂等、63业务/11控制表逐行及schema保持、权限/账本/原账户字节保持，私有worker初始化后回收，无生产个人请求。
- 清单口径：runtime.tar=219运行源码+2metadata=221；verification.tar=512验证源码+2源码metadata+1包清单+5离线wheel=520。Mac受测源码512字节/mode未变，但实际520=514+6缓存，不称完整集合未变；Linux受测514成员精确，运行目录实际310=219源码+2metadata+89缓存。缓存逐一与声明源编译的代码属性/常量比对一致，创建PID未证。首轮过强marshal重序列化字节比较失败保留，未删除缓存或改源码。
- 发布工具：保留R1原脚本/配置，新validate只新增私有TMPDIR，原时限不变。独立新只读gate仅将允许目录常量收窄到准确R2名字，旧gate/SDK原hash保持；41自检及实际本地Mac/SDK源绑定通过，新只读发布门通过并完整读回远端全量/迁移/smoke/source证据。一次只读SSH预检被远端关闭/255，原工具输出保留，重试只读预检通过。激活仍要求即时idle、最新schema/行、完整备份读回、保留新数据的兼容reader回滚，不能恢复旧DB覆盖新写入。
- 真实计划v4：PLAN-D-TARGET-01在任何真实请求前明确claim_status只评价第33页建设目标区，整页原文/其他记录保留，独立oracle答案不改；PLAN-FREEZE-SEQUENCE-01改为A前固定根/源/profile/BC与D独立断言、A后BC前绑定完整真实策略与双臂计划、本人采用后才绑定原定新D的真实decision/revision/task/capture，不换题/阈值/根/期限；旧v1/v2/v3全部保留。
- PLAN-HUMAN-WINDOW-01：仓库外固定split_deadline_driver.py实际实现一次原始wall+monotonic/boot绑定、20分钟A/BC/12小时总根/单次120秒、在途取消与迟到成功拒绝、持久unknown/intent不重发、全槽唯一与锁、零模型等待、过期D拒绝。Mac/Linux各16边界测试通过；删除截止门的独立变体准确1目标failure/0error。两端各一次实际FiniteBroker→监督进程→回环HTTP在缩短1.5秒窗口取消，原unknown保留、子组回收、重试不增加第二次请求；这是缩短窗口合成验证，不称实际等满20分钟、真实供应商或本人采用。首轮集成因遗漏tests导入路径error保留，修正PYTHONPATH后两端通过。
- 证据：仓库外分析/RSI协调/pilot-software-20261025/coding-handoff.json、native-linux-original-failure-readback/manifest.json、native-tmpfs-member-audit-v2.json、native-real-engineering-plan/plan-v4-driver-readiness.json与linux-driver-v4/result.json。新计划和驱动已固定可审，登记前独立复核仍待；真实模型调用0、未登记工程根、未代本人采用，rsi_qualified=false/production_equivalent=false，旧多人五小时窗仍过期、null总token上限/8calls保持、旧20元不恢复。

- 发布结果：2026-10-26 **04:54:59 CST**启动c08b6ae，R2非活动目录现已成为/opt/webuddy/app目标；备份`/opt/webuddy/backups/pre-c08b6ae4ffe1-20261025T205456Z`，1781个data成员与三项目277/37/20个.tmh成员及整个旧app/配置逐字节读回通过。原63/11表行/schema、账本、非DB/项目文件及配置保持，没有生产本人会话或Agent代签；回滚只允许兼容reader、保留最新数据，未恢复旧DB。
- 延迟健康：启动超过60秒后18项公网/回环检查通过，worker身份保持；final active/running、重启0、启动以来error级日志0、219源码一致，Mac独立TLS4/4。PID仅为当时观察，不用于未来信号。服务器17份白名单证据共356751字节，根线程逐份完整重读SHA/长度通过；manifest SHA `d206e4acaf4b9f9469fb2c8959c0d89c3d330d182a8fdfc1b88a07915c700637`。首轮collector误假定R2存在旧validation-origin.json而失败，原工具输出保留；未事后伪造该文件，改收真实test-temporary-storage.json并单列来源范围说明。详见server-evidence-tmpfs/readback-manifest.json及仓库外handoff。本文档提交仅记录，无需再次重启。

## 2026-10-26：发布验收中的原生UI结论修复

- 当前项：真实浏览器发现原生job卡片/选择项显示“结论未登记”，状态done（窄修、真实合成浏览器、限定独立审查和新发布门已完成；最终收口见上节，以下保留历史）。3cc浏览器截图保留在仓库外`native-browser-3cc76b2/before-verdict.png`；实际producer/server临时合成数据，非LYB/LLA或生产个人会话，没有真人采用。机器passed不自动决定。
- 根因：普通与原生job原始行没有独立verdict列；native完整结论在result.schema=`native-learning-report-v1`及passed布尔。UI只读job.verdict导致错误标签。仅补UI的原生结论投影，并加严原生采用选项须同时status=passed、确切原生report schema和passed=true，旧普通job逻辑不变。后端native原件/本人理由/锁门无改动。
- 验证：三条新UI测试在3cc行为下2个目标assertion失败/0error（native-verdict-ui-red.log）；修后与原22条UI一起 **25/25，1.5秒量级、actual0**（native-verdict-ui-green-v3.log）。保留初次错误的job.verdict KeyError、尝试不存在SQL列导致22fixture errors的日志，已完全撤回该producer/test改动，不引入DB列或迁移。两次新mock select检查不支持完整options/innerHTML读取，改为同时核禁用按钮、可见placeholder与目标job不存在，原安全断言保留；相应失败日志不算产品通过。
- 发布准备：新外部工具绑定实际f947/63业务表/11控制表，改为精确零schema变化，保留逐表原行/列/对象、控制权限、账本、全备份和保留新数据回滚门；原3表添加发布工具完整保留。3cc包219运行文件/512声明验证文件；已新跑SDK1.30.0 **74/74、零skip、actual0**，该证据仅属3cc。3cc完整2509项Mac回归仍在原源上运行；本窄修增加1项UI用例，最终新提交需重新绑定2510项，不挪用3cc全量/SDK或旧f947结论。原1000秒外层、测试内超时及90秒合成smoke未放宽。
- 待依赖：新窄修真实浏览器相关流程、最新精确源回归/SDK/迁移兼容与独立产品审；生产仍f947，不提前激活。后续真实工程实验另列有限计划、真实时间和原始usage/未知费用；max_total_tokens=null，不恢复旧20元、不复活旧多人窗、不代本人采用或D。

## 2026-10-26：原生job、本人引用与同根D桥

- 当前项：原生评测job→确切报告→本人采用引用→同根新D；状态：**done（作者验证及固定候选；新批独立产品复审、发布待定）**。起点5eb957e工作区干净；2be与5eb固定提交各自已获限定独立接受，该结论不扩大到本批新桥。本项先推进不依赖真人回应的软件与合成验证；普通job不改名洗为native，模型自评/Agent不能代真人确认。
- 设计边界：原生job独立类型，经原预登记、实际SP与原件、确切revision/root/frontier/输入/模型/有限计划发布。原human入口只认确切原生来源与报告引用；D需新任务、原selector/renderer实际选中已采用策略，原根计数/截止/未知阻挡不变，唯一自身D不得放宽其他late attempt。旧窗口不延长/回填，真实模型暂未启动。
- 待验证：发布/回滚/原件失效/普通job拒绝、真实个人合成决定、同根新D正反例；线上runtime变更须通过必要回归与精确包验证后发布，本批不提前宣称上线。
- 当前实现：独立native_evaluate job、私有原件封存和原根锚；原个人采用门新增确切原生来源/报告引用、未知kind拒绝；UI只在本人明确提交时绑定原因。新D实际原selector/renderer消费确切已采用策略，同根第8请求与唯一自身frontier例外；原报告read不放宽。独立D断言预登记、3秒/root余时监督、唯一intent/原件回放/未知不重跑、错误答案真实失败均已实现。
- 锁与暴露：finite reserve/intent在Registry→Store/SQLite→lesson顺序内原子登记，实际commit覆盖lesson lease；真实第二进程检查锁顺序和commit持有。新增跨根原生意图/消费/D预封任务身份与rawSHA防重封，旧合同/历史不改，原根幂等创建保持。原生job与D不构成强OS隔离或完整CLI工具生产等价。
- 已跑：native-job-first 4方法/4路径别名error、9.716s/外层10.039s、actual1，Mac /var→/private/var被误拒绝，修正记录规范路径而不放宽私有文件校验。原临时fixture按cleanup移除，仅完整日志/源清单保留，不声称首轮SP原件保留。native-job-second 37/37、11.808s；atomic-first 55/55、28.716s；native-D-first 32/32、25.132s；D-second 68/68、35.027s；D-third 123/123、63.605s；native-admission-first 17/17、43.413s；exposures-first 37/37、55.014s；exposures-second 39/39、60.716s；lifecycle-final-directed 24/24、55.777s，均actual0/源保持。仅对应当时源码的定向证据，最终精确来源尚待固定验证。
- 两旧批独立结论已直接读取2be-review-decision.json和5eb-review-decision.json，均accept_scoped_implementation：2be两P2关闭，根26+额外5；5eb根244=238pass6root夹具skip/额外12新43旧8边界。独立finite导出2318原Git字节/mode保持，实际2348有30pyc，complete_member_set_unchanged=false，原现场保留；仅时间/子进程导入相关，非创建PID直接证明，不重开d0固定worker-B。作者schema筛选207是子集，独立Mac完整292=288有效+4故坏，遗漏85旧金额provider；不从Mac推断Linux完整数。原9夹具error全文本轮未读回，只有摘要/旧工具transcript，不称完整日志已核。这些接受不扩大为当前运行/UI新桥已接受。

- 本轮冻结tree188ef690：Mac35模块565项559通过/6root显式skip，192.593s/外层193.567s、actual0；10负控各1目标failure/0error/actual1；12稳定性通过。Linux同源声明513文件565项558通过/1error/6skip，397.800s/外层398.616s、actual1。失败原路径`/tmp/webuddy-native-bridge-zfwcvztx`保留：finite-native撤回时bindings为空，非通过。
- 已定位既有fixture重捕获按Store.tickets最近更新时间枚举，跨秒时任务索引从APP-1换成APP-4，后者被原生产holdout规则排除。确定性设置四任务更新时间后，旧helper准确1 assertion failure/0error（native-recapture-order-red.log，顺序4/3/2/1而非1/2/3/4）；仅将测试重捕获按固定ID排序，新增身份及真实bindings断言，不改生产selector/renderer/holdout、超时或原断言。修后重新冻结并重跑，不拿首轮Mac绿灯替代最终证明。


- 最终受测tree `159af9ca246752c8b9f353ea7aeda0d44d17b437`，完整Git导出2325文件，逐份Git blob/SHA256/长度/mode及完整集合核对；Linux从原495源加精确覆盖构成513声明成员，前后完整集合均恰为513，无额外pyc。不能将Linux513子集称为2325全树；原495文件字节也保持。`native-bridge-candidate-v2/`、`native-bridge-candidate-v2-source-verification.json`保留。最终提交相对受测tree只追加本进度记录，并移除新测试文件EOF多余空行；全部运行/私有协议代码和测试AST相同，差异在提交绑定记录中逐项核对。
- 最终命令：`NO_PROXY='*' no_proxy='*' PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tests:. python3 -B -m unittest -v <native-bridge-candidate-v2/modules.json的35模块>`；Mac Python3.14 **566项/560通过/6显式root夹具skip、195.666s/外层196.420s、actual0**；Linux UID1000/Python3.12 同35模块 **566项/560通过/6同类skip、402.807s/外层403.680s、actual0**。两端完整日志、原命令/cwd、清单、退出码保留于`native-bridge-final-mac-v2/`与`native-bridge-linux-v2-readback/`，后者由原服务器路径完整读回SHA/长度。此为相称的相关回归，不冒称新的全量或新root内核验证；旧f947全量仍仅属旧提交。
- 稳定性与负控：最终同源四条同根D实际成功/实际第8HTTP取消/真实commit持lesson锁/独立SQLite写入者与lesson锁序，每端3轮 **12/12**；Linux固定ID重捕获反例另10/10。`native-bridge-negatives-final-v2/result.json`十项各准确1目标failure/0error/actual1，含孤立预留历史、未完成隔离、确切本人报告、完整frontier、普通job洗来源、D原断言、跨根raw/task暴露、反锁序及提前释放commit。旧第6条super编译error及外层辅助脚本cwd/旧package文件名错误仍保留工具记录，不计有效反例；没有把故意红灯记作正常产品失败。
- 原件完整枚举：新审计不再按schema筛掉旧金额provider，逐个数据库意图及所有supervisor/result目录核对v2/v5/v7。最终Mac/Linux主回归各482实际SP目录＝477有效绑定+5故意追加changed的坏原件，另4意图无SP目录（既有缺原件、BC/D未知worker注入及纯锁序入场未发HTTP），全部明确列出；每端稳定性各60有效SP、另3纯锁序入场意图无SP；最终负控69有效SP、另1纯入场意图。无未匹配目录，观察到的组均已不存在，只读查询未信号历史PID。故坏/无回执不算成功原件。Linux为现场原路径核验，完整审计/日志结果读回，不声称所有raw SP下载到Mac再验证。
- 不变量核对：acceptance、guard、filelock、process_control、supervised_process、lesson_context、lesson_input与5eb逐字一致；旧reserve/intent内层逻辑抽取前后AST完全相同；既有NativeRegistered测试方法AST保持，仅修改夹具任务枚举并新增确定性反例。UI为实际JS/Node合成DOM行为回归，未新跑真实浏览器或生产个人会话；先前被阻止的强pending→applied探针未重试、未作为证明。
- 发布与待确认：普通提交/推送当前iteration/context-pack-v2，精确SHA及来源/证据哈希在仓库外`native-bridge-self-validation.json`、`native-bridge-fixed-git-members.json`和`coding-handoff.json`。runtime共219文件，仅native_learning/learning_decisions/ui_learning三处相对线上变化，Store迁移DDL未改。2026-10-26 03:21:39 CST只读核生产仍f947、218运行文件一致、active/running、重启0；本轮未激活、未改业务数据。新固定候选独立产品审及相应新发布门/迁移副本/延迟健康仍是发布前依赖，不拿旧门或旧审替代。真实有限新工程计划、真人采用及新D等待实际依赖，不复活旧00:30多人窗，不代签，真实模型调用0、rsi_qualified=false。Windows原六项阻塞沿用，尤其本批原件权限/监督进程仍只验证POSIX；无需要用户重复授权或预算答复的阻塞。

## 2026-10-26：前瞻有限执行与Token总上限豁免

- 当前项：新finite v6/v7合同与独立profile/Broker；状态：**done（作者验证；独立复审待定）**。起点2be8960工作区干净，两个a98快照P2已作者验证并普通推送，线上218一致/不重启，独立复审仍待定。人类解除Token总上限只面向新执行版本，明确max_total_tokens=null；旧100M/20元根、失败和暴露集合不回写，旧20元不恢复。
- 本批范围：有限调用/真实新起止/单次超时/停止/未知结果不重放；现有配置协议可用，不再要求为已取消的100M上限证明可信包含全部Token的硬界。完整供应商响应和原usage保留，缺失/不支持的usage为unknown，不当0，不声称隐藏请求或实费已知。只做临时合成回环，旧PPT窗口已结束，不代真人参与/采用。
- 待验证：新finite定向、旧capped/付费合同回归、native输入与快照保护；新job/D桥仍是下一依赖，不在此批伪造普通job或human adoption。

- 实际改动：trial_preparation增加显式null总上限的独立v6/v7、有限calls/window与reported/unknown账本；provider_adapter增加独立v3配置、两文本协议、完整请求字节门和缺用量不补零；registered_trial只新增FiniteBroker，原Broker/TokenBroker AST不变。新增finite_execution 12方法和finite_native 1方法，设计文档明确资源参数不是inclusive账单上界。无运行目录/外部工具权限变化。
- 首轮47方法38过/9夹具error、8.665s、actual1：新夹具引用不存在的既有方法；尚未运行新产品断言，不能当红灯。修正为真实方法后47/47、10.555s/外层10.880s、actual0；新增真实取消/5秒超时/相同编号并发及原生双臂后23/23、20.930s/外层21.459s。初次错误摘要/工具日志保留。
- 精确候选树`6288bc79ff49c3eff76689e6df81091a58daa6b7`，Mac完整2318个Git文件字节/模式/文件集合保持，0额外文件；14个相关模块244方法，238通过/6显式root Linux内核夹具跳过/0失败错误，109.496s/外层110.155s、actual0，日志SHA95ebb5655fdaa79e8b37d1a268178cc484fee59db864c4d895e84a36d0c8488f。不是重跑全量2355。
- Linux实际UID1000/Python3.12、511声明源与精确Git字节/模式一致，原495源保持；同244方法238过/6同样root夹具跳过/0失败错误，187.502s/外层187.936s、actual0/SSH0，日志SHA547bbee3216976ee30a8329e9d42dd71a50d4fada783c75ad47c4a8ab54ab7ee。新原生双臂、并发单HTTP、真实取消三场景各3次9/9、13.942s、actual0；保留原时限，未运行专门root隔离夹具，不能称已证明新模式OS隔离。
- 三严格负控：删除有限次数门、将未知billed_tokens伪作已知reported总量、跳过完整请求字节门，各准确1方法/1目标断言失败/0error/actual1；原源保持。两端原SP现场owner/nonce/完整原输出/cleanup和进程组消失核验；Linux主套204有效+3有意损坏（provider2/evaluator1），稳定套30有效/0坏；Mac计数见finite-self-validation原JSON。7份Linux白名单日志/结果/现场核验摘要320913字节SHA/长度完整读回；不声称远端原SP在本机复验。资源警告保留。
- 原断言未改；14原AST节点（旧Token常量/协议/bound/normalizer、Broker/TokenBroker/capture等）和14受保护文件字节保持，包括2be8960报告快照/worker-B/guard/acceptance/锁/采用/eval/SP/transport及既有测试。`git diff --cached --check`与逐块diff自审通过，源与最终提交仅进度MD允许不同。证据`分析/RSI协调/pilot-software-20261025/finite-self-validation.json`；普通推送后现场核218运行文件，不重启。
- 待确认/下一依赖：独立复审本批固定SHA；原生job发布→确切报告→真人采用引用→同根D尚未实现，不把普通job洗为native，不代签。新模式没有实际模型调用，不宣称真实RSI/组织收益/80分；旧00:30窗口已结束且本链未启动，不延长或倒填；后续若有工程实验须用真实新计划/时间。材料已提供，已解除总上限不再以100M可信硬界或旧20元阻塞。

## 2026-10-26：原生报告两个当前性P2

- 当前项：NATIVE-BC-CURRENT-COMMIT-01/DECISION-FRONTIER-01；状态：**done（作者验证；独立复审待定）**。起点d0bba40，git status干净；该-B窄修已普通推送、线上218保持/未重启。已读a98最终独立decision及两个已执行原反例；强pending→applied未实际运行，本批不执行/声称已证明该强场景。P2不能被reference仅部分/qualified=false掩盖。
- 新原API交错回归3项在未修d0上 **3方法/3准确断言失败/0error、6.737s/外层7.028s、actual1**：实际选中经验在最终观测后退役仍发布；已有采用后原root预留晚到仍reference；实际commit时外部OS进程能取得lesson锁。原输入/回执/JSON事实在native-snapshots-red-fixtures保留，不伪造后台快照/本人决定。
- 修复限定新Reports：原Registry→Store/SQLite→lesson顺序，输入/知识/授权和完整attempt指纹在发布/本人读取保护快照内重核；只提交自己创建的事务，在lesson锁仍持有时实际commit，外层commit为空操作。原intent/失败保留、不重跑worker、不洗普通job为native、原人类决定与旧预算/代码门不改。新设计native-bc-protected-snapshots-2026-10-26.md。
- 首次26方法 **15过/11嵌套事务error、41.804s/外层42.669s、actual1**：错误使用了Ledger.snapshot/inspect公共事务包装。日志/源保持；改在当前事务中调用原_pool和只读当前行，不放宽原禁止嵌套。第二轮 **26/26、43.553s/外层44.171s、actual0、源保持**。最终精确导出/同源/原件/严格负控继续；不挪用旧2355，真实模型0。

- 最终精确候选树 `82c8a0edb59a62f567aa02cdd78c4c8899008a41`：Mac 26/26、42.909s/外层43.671s、actual0，完整2315个Git文件字节/模式及文件集合相同、0额外文件；Linux Python3.12同源508声明文件26/26、63.690s/外层64.060s、actual0/SSH0、原495源保持。三个快照场景各3次Linux稳定性9/9、33.330s/外层33.702s。收尾当前树三项重核3/3、7.754s、actual0；未重复全量2355。
- 严格负控3项：分别移除发布当前性、本人引用frontier检查、将实际commit移至lesson解锁后；每项准确1方法/1目标断言失败/0error/actual1，原源码保持。初轮红灯原件24份有效SP；Linux主套124有效+2有意损坏原件、稳定套72有效/0坏，均现场核owner/nonce/完整输出/cleanup和原进程组不存在，不按历史PID发信号。7份白名单Linux日志/结果/现场核验摘要250779字节完整SHA/长度读回；不声称把远端原SP搬回本机再次验证。证据 `分析/RSI协调/pilot-software-20261025/snapshots-self-validation.json` 及原目录。
- `git diff --cached` 自审、protected源码原字节核验：registered_trial/worker-B/原16报告测试/7留出测试/ledger/learning_decisions/eval/guard/acceptance/锁/SP保持；源树与最终提交只允许本进度记录差异。原intent/3秒监督/不重跑worker/普通job非native/强探测未执行保持。本批非运行目录代码，按AGENTS普通推送并核在线218相同，不重启。
- 独立窄审结论已直接读取 `分析/independent-review/20261026-101d384-d0bba40-fix-review/review-decision.json`：101留出重捕获P2及d0的-B行为修复接受，独立根85/85零skip，关闭NATIVE-HOLDOUT-RECAPTURE-01（REGISTERED-HOLDOUT-01同项）；这是该两项的窄闭环，非全Linux重验或当前两个a98 P2已关闭。旧5导入错误/14pyc和本批3红灯/11嵌套error完整保留。
- 待确认/下一依赖：本批固定SHA后交独立复审；前瞻豁免合同须明确max_total_tokens=null、有限调用与时限，旧100M根不回写/旧20元不恢复。原生job→确切报告→真人采用→同根D仍待实现；真实PPT五小时窗口已结束且本链未启动，不延长或倒填，材料已提供；组织收益/80分不认定。

## 2026-10-26：固定评估进程禁写字节码窄修

- 当前项：-I使PYTHONDONTWRITEBYTECODE环境变量无效；状态：**doing**。起点101d384，P2修复已固定/普通推送并交固定SHA复审；本项不重开或掩盖P2。只给a98固定评估子进程显式加-B，新测试复制完整原依赖Py字节到独立新import树，实际运行原评估后检查无pyc，不以仅检查argv代替行为验证。
- 未修红灯 **1test/1准确断言失败/0error，3.500s/外层3.987s、actual1**：独立新树出现14pyc，日志/evaluator-bytecode-red源快照保留；该单测临时目录按原cleanup移除，不声称其SP原件仍在。更早P2导出原现场2313声明源+14pyc完整保留，不删除后追认目录保持。原-I隔离、3秒/root原期限、原评估断言、原root及人工门保持。
- 该修不新增模型调用/生产入口/状态迁移，不修改原P2实现及其回归。后续在新精确Git导出和Linux新源验证，再核完整成员；实际模型0，真实通道/真人/原生job-D仍不能由本修证明。原00:30截止不自动顺延。
- **本窄修自验：done，独立核验待固定SHA；不冒称a98两个新P2已关闭**。最终 `test_rsi_native_bc_report test_rsi_holdout_recapture`：Mac新精确Git导出candidate tree `32e2726aa4b2429adf6c19235733b532eb4a4b06` **23/23、40.111s/外层40.773s、actual0**；Linux UID1000/Py3.12新 `/tmp/webuddy-evaluator-bytecode-mvbu9hqv/source` **23/23、53.568s/外层53.937s、actual0/SSH0**，0skip。两日志SHA `b977e2f750ef5a031c817e7ac5fbbb17aec22e956dde8203ceecd8de3e146216` / `19e1229141b73a2df1ebcdf43b30ed3dfd460e04a25cb4b4b76c6515489281de`。
- Mac全部2313声明Git成员原blob/字节/mode匹配，新树完整文件与祖先目录集合无额外成员/pyc；旧14pyc现场未删，未追认旧完整集合保持。Linux506声明源及完整文件集合保持/无pyc，旧495声明源保持；506不冒充完整2313Git。新fresh-import-tree行为回归Linux再3次 **3/3、10.779s/外层见原result、actual0**，24份原SP（21provider+3evaluator）核owner/nonce/完整output/cleanup/reaped/原组不存在；Linux主100有效+2故坏（provider1/evaluator1），故坏不计通过。七白名单完整日志/结果/manifest/现场audit **190848字节**逐SHA读回，非本地远端raw transport再验证。最终进度晚于该候选测试，代码/原测试精确绑定并保留文档差异。
- 原15个报告test方法AST逐项相同，原101实现/7个P2回归及核心门逐字节保持；仅增加新行为回归、imports与固定argv的-B。设计原语义、3秒/原root期限和人工决定不变；没有重复旧全量/真实模型/生产重启。原始退出/源码/完整清单见bytecode-self-validation.json，交固定SHA复核。
- 新人类授权已直接读主协调人类turn `01a173cb-aa7b-7073-b1f1-a11125e6ffc4` / user `01a173cb-b003-73c3-9126-5383041bfb16`：对原生API/100M问题答“你可以把token上限解除”。本轮前瞻总cap豁免，max_total_tokens应明确null，旧20元不恢复；旧100M合同/失败不回写，不填巨额假cap、不无限循环。原有限调用计划、权限/留出/独立评估/本人采用与00:30不变。现有转发可复用，未知usage/内部attempt诚实披露；不再把硬Token上界或另找原生通道当当前试轮调用前置。先修a98独立确认CURRENT-COMMIT和DECISION-FRONTIER两个P2，再以前瞻新版本接有限调用/原生job-D；不能把撤cap当真实计量完整或80%证明。


## 2026-10-25：NATIVE-HOLDOUT-RECAPTURE-01 修复

- 当前项：同一预封题重捕获包装SHA不同后被训练入口接受；状态：**doing**。起点a98eb40，git status干净，已读579固定独立review/decision/root-recapture-proof；REGISTERED-HOLDOUT-01是同一P2别名。579训练/终测隔离不接受，a98语义报告门和qualified=false不能抵消题目已暴露。
- 新真实recapture回归在未修a98上 **1test/1准确Conflict not raised断言失败/0error、0.361s/外层0.627s、actual1**，实际1次合成HTTP，原contract不变，完整有效messages相同、包装SHA不同。原完整capture/历史/proof/请求及SP留holdout-recapture-red-fixtures，未覆盖原失败；本次不伪造capture或修改私有root来制造该反例。
- 修复只加严原TokenBroker：从原rawSHA找原封存输入，在首次成功计划事务内、首次attempt前绑定稳定任务/来源与完整有效messages；四训练phase拒绝同原任务或有效输入。后续核原锚/原ID，已有attempt缺锚不补签，原root/完整历史/已暴露集合不重置。合法不同任务/新历史/无工单训练保留。新设计holdout-recapture-2026-10-25.md。
- 首轮修后40/40、43.333s/外层43.907s、actual0；第二轮扩展45/45、42.738s/外层43.276s、actual0，源保持。现补无工单合法训练及最终定向、精确源/负控/原件核验；不重跑旧2355。原生job发布/同根D桥仍todo，LIVE D拒绝；先关闭该P2，不被后续桥的状态掩盖。
- **修复自验状态：done，P2独立关闭待固定SHA复审**。最终7个新方法；命令 `PYTHONPATH=tests:. python3 -B -m unittest -v test_rsi_holdout_recapture test_rsi_native_registered test_rsi_native_bc_report test_rsi_token_adapter test_rsi_registered_trial`。Mac从候选Git tree `0d63d8d2a42524859542ca540ce69b63265f1b86` 的新精确导出执行 **84/84、54.881s/外层55.413s、actual0/0skip**；Linux UID1000/Py3.12新 `/tmp/webuddy-holdout-recapture-71w_ofzn/source` **84/84、98.214s/外层98.587s、actual0/SSH0/0skip**。两日志SHA `ec2def848c18e3d92104c7ca5977f6496ceaf21f134617301eb021f7f8af8985` / `573120bdc27bda46a289a08ea6270384dc3f358ac377db1353a79c00be35b55c`。
- Mac2313声明源与候选Git原blob/字节/声明mode全匹配；完整成员核验实际exit1，发现 **14额外pyc**，原现场/列表/SHA保留holdout-mac-member-audit-initial.json，不删除后冒称完整成员不变。根因是a98固定评估子进程-I忽略PYTHONDONTWRITEBYTECODE；该独立问题不改变原2313源或本P2断言，后续单独补-B并在新树验证。最终进度文字晚于测试，候选tree与最终提交的文档差异须明确，不冒称当次Mac已跑整个最终Git树。
- Linux506声明验证文件SHA/长度/mode前后保持，旧495源保持；该集合不含本进度，不是完整Git树。四场景各三次稳定性：两端 **12/12**，Mac5.252s/外层5.486s、Linux10.301s（外层见原result），各actual0；两端各9份有效SP原件核原owner/nonce/完整输出、cleanup complete/reaped/remaining_group=false和当前原组不存在。原红灯那1份SP也已原路径核验完整/原组不存在。Linux主轮149份有效Token/evaluator原件+3故坏（provider2/evaluator1），不把未计的legacy v2监管或故坏算通过；七白名单完整日志/结果/manifest/现场审计 **232358字节**逐SHA/长度读回，非远端raw transport本地重验。
- 三内存删门负控（忽略重捕获别名/忽略稳定任务/允许旧根补签）各 **1准确目标断言失败/0error/actual1**，源保持；完整记录holdout-negative-final。原40/45绿灯和红灯/原原文/wire保留，不回填失败。12个旧核心/原测试文件逐字节保持，self-review/diff --check通过。固定SHA与精确506对Git核验/完整成员清单见外部holdout-self-validation.json和coding-handoff.json；不重跑全量、不改production入口/实际root、无真实模型调用/代签/服务重启，LIVE D仍拒绝。


## 2026-10-25：原生 BC 语义报告和本人精确引用第一段

- 当前项：原登记阈值/全部双臂原件→固定独立进程断言报告→原本人决定精确引用；状态：**doing（原生job发布/同根D桥仍todo，LIVE D拒绝保持）**。起点579d3c7，开工git status干净；579仅已固定自验/推送，新独立审待结论，不冒称通过。
- 新增scripts/rsi/native_bc_report.py、native_bc_worker.py、test_rsi_native_bc_report.py和设计native-bc-report-2026-10-25.md。只向原根事件追加登记/评估intent/报告，不写learning_jobs/steps/decisions，不新建预算/业务状态。规格来自私有原登记文件，在A前冻结完整原预封case、断言、明确阈值、授权/contract、模型应用/profile及代码束；事后登记/现场换阈值拒绝。没有真实试轮登记，当前只有合成规格，不替用户凑阈值。
- 原Adapter/SP核所有attempt与六臂来源，缺臂/未知/取消/原件变动均拒绝；独立固定进程复用原E.check，原期限内最多3秒，核nonce/owner/output/清理，原件和全部attempt绑定报告。回放不再HTTP/评估，中断/报告提交失败保留intent不重跑。控制器与评估同UID，不称独立帐号或任意代码oracle隔离。没有真实模型调用。
- 原本人决定reason须精确引用原root和native report SHA；核真实applied/adopt、当前确切修订、原source/content/普通job和已冻结输入。引用成立仍明确job_native_provenance_verified=false/live_d_eligible=false/rsi_qualified=false。原生job预登记/按真实原件发布报告及D追加attempt豁免仍未实现，不能绕过原人工采用门或把普通job洗成本根报告；本批不启用LIVE D。
- 阶段验证：首轮9/9，10.893s/外层11.366s/actual0；第二轮11/11，17.263s/外层17.761s/actual0，源保持。审实现时补Registry→Store锁顺序、报告提交事务的完整attempt指纹再检查、本人读取SQLite快照和最新采用决定；当前13新方法与原共同输入/Token相关定向正在跑，不挪用旧2355或579的226结果。
- **第一段状态：done（固定实现自验完成；不代表整个job/D桥完成或独立批准）**。最终新增15方法。首轮严格负控未检出删“已有attempt”门：提案夹具已经绑定候选，被另一门正确拒绝；原控制实际1test/0failure/0error/actual2，保留native-bc-negative-final，不算成功控制。改新测试为真实提案响应已到、尚未绑定候选窗口，不削弱断言。最终v2四删门负控（事后登记/漏晚到attempt/错本人报告引用/无改善当通过）各 **1准确目标断言失败/0error/actual1**；源保持，不伪装原失效控制成功。
- 最终命令：`PYTHONPATH=tests:. python3 -B -m unittest -v test_rsi_native_bc_report test_rsi_native_registered test_rsi_token_adapter test_learning_decisions`。Mac **92/92、40.283s/外层40.846s、actual0**；Linux UID1000/Python3.12 **92/92、85.469s/外层86.005s、actual0/SSH0**，均0skip。最终两日志SHA `64aec01d8363a59ac8c266b08345a144bdd61a421cbfaed3297185f583ec6c44` / `a7648c8467f3f4a218605d01532f816d70e354e77460f2d84700b183c5831f50`；前一轮92/92属于夹具补强前，原源/日志保留，不换成最终结果。
- 新 `/tmp/webuddy-native-bc-7r6ct9ok/source` **504声明文件**字节/长度/模式前后保持，旧495验证源未改。报告生成/提交丢失恢复/本人精确引用各三轮：两端 **9/9**，Mac17.703s/外层17.922s、Linux29.452s（外层见原result），各actual0。两端稳定性各 **72份有效SP原件=63 provider+9 evaluator**，在原路径核owner/nonce/完整output与清理complete/reaped/remaining_group=false和当前原组不存在。Linux主轮另143份有效、3份有意损坏原件（provider2/evaluator1），原损坏输出以明确changed后缀核对应三个篡改测试；未将坏原件算通过。Mac主轮未开保留，只声称稳定性原件。Linux七白名单原日志/结果/manifest/现场审计 **277681字节**逐SHA/长度完整读回，不称本地复制并重新验证了远端raw transport。
- 验证绑定 `分析/RSI协调/pilot-software-20261025/native-bc-self-validation.json`，全Git成员与504验证集合分开记录。原12个核心/保护/579实现及原测试文件字节保持，self-review与diff --check通过。没有旧全量/内核canary/真人数据/付费模型/服务重启；后续仍需native job双臂前不可变登记、按实际原根/SP独立报告发布确切修订，以及D新增attempt只豁免同根自己且核实际原selector/rendered。引用关系成立不能代替该执行来源。真实试轮规格/原生路由上界与内部尝试计量尚未验证，LIVE D和RSI/组织收益仍false/unknown，不把00:30自动顺延。
阶段说明：该段当时待核事项已由上文最终验证收口，不表示当前仍未验证。

## 2026-10-25：恢复共同输入 WIP 收口

- 当前项：原生 Token 登记、当前知识与独立 input×arm；状态：**doing（窄面验证收口，LIVE D 保持拒绝）**。恢复起点 a56b824，git status 为 provider_adapter.py/registered_trial.py 两改动与新 test_rsi_native_registered.py；不重做既有已关闭项。a56 次数诊断已独立18/18关闭；e8固定适配器99原测试+1探针限定接受，真实提供方上界仍未证明；b617负控追加勘误已关闭，旧失败未覆盖。
- 原 native-current-first 53/53、adoption12/12、selection1/1 均只属中间快照。本次第二轮21项18过3fail/actual1：两撤回夹具误选未实际注入知识的A输入，另一并发夹具创建了新代际；原门正确拒绝新代际。修为确实选中原经验的B输入、显式同进程代际双Store连接，不放宽代际/选择器/时限。原日志与before/after源保持；该轮未启用fixture保留，临时业务现场已由原cleanup清理，不能冒称有完整原DB。第三轮23/23、8.235s/外层8.505s、actual0；第四轮三模块62/62、20.099s/外层20.660s、actual0、源保持。
- 新加严：Registry→Store→lesson锁覆盖当前性/reserve/intent并在网络前释放；外部独立进程非阻塞锁探测确认知识写入不能插队。训练标签不允许读取预封B/C输入；当前工单正文变化零预留/HTTP。D策略必须等于确切本人采用的原响应策略，重复双臂历史拒绝。旧人工确认/guard/锁/MOVES及基线测试不改。
- D只读检查确切applied决定/修订/原report SHA、实际选中和渲染、独立工单/族、原根全部双臂完整回执；普通fixture采用继续qualified=false。确切原生BC语义报告→本人决定→同根D桥未实现，**LIVE D继续拒绝**，不制造报告/代签。新设计 docs/design/native-registered-input-2026-10-25.md 明确可审边界。
- 新实际通道调查只读证据位于分析/implementation/20261025-live-token-feasibility/，CPA参数翻译/内部重发/usage缺失边界未闭合；不修改外部网关、不试拨模型、不自签上界。沿原100M全链根与00:30原截止，不追加预算或顺延/倒填开始。真实模型本任务0次，历史费用未知不记0。
- 负控首次执行器字符串转义SyntaxError，未跑目标测试，保留 native-negative-final 原件且不算有效控制；修正执行器另存v2继续。最终同源双端/稳定性/原件核验尚待完成，不挪用旧2355全量作为本增量结果。
- **本窄面状态：done（实现自验完成，待新固定提交独立审；LIVE D关系仍todo）**。最终命令：`PYTHONPATH=tests:. python3 -B -m unittest -v test_rsi_native_registered test_rsi_token_adapter test_rsi_provider_adapter test_rsi_http_framing test_rsi_token_budget test_rsi_proposal_root test_rsi_trial_preparation test_rsi_trial_integrity test_rsi_registered_trial test_rsi_registered_isolation test_rsi_controller_replay`。Mac **226项/220过6条件skip、43.628s/外层44.180s、actual0**；Linux UID1000/Python3.12 同源 **226项/220过6条件skip、117.725s/外层118.123s、actual0/SSH0**。新 `/tmp/webuddy-native-registered-um5gure0/source` 500声明文件SHA/长度/模式前后保持，旧验证495源未改。这是指定验证集合，并非整个Git提交成员清单。新增24方法，旧registered/provider/token测试逐字节保持；acceptance/guard/process_control/filelock/trial_preparation字节保持。
- 最终两端主日志SHA分别 `fcd5c88f0ef87cf65d5df118ad99246fbbe43142ebbbc6d95d326bf2880be3f8` / `7f26f14302456ae319b4b2e4b1935fffa708f9bb6b220c23b0ffed765915fd8e`。稳定性五场景×三轮，Mac **15/15、10.668s/外层10.916s、actual0**，Linux **15/15、20.976s/外层21.293s、actual0**（外层以原result为准）。两端各48份稳定性SP原件在原路径核nonce/owner/完整output，cleanup complete/reaped、remaining_group=false且当前原进程组不存在；Linux主轮另57份有效及1份有意损坏原件，损坏原件只在原token篡改测试中按预期拒绝。Mac主轮未开启fixture保留，不冒称该主轮也有全部SP原件。Linux七份白名单原日志/结果/manifest/现场审计 **224383字节**逐SHA/长度完整读回；现场审计JSON不等于把原transport二进制下载后本地重新验证。
- 最终严格负控v2 **5/5**：允许训练读预封输入为1test/2准确目标及子例断言失败；重复臂、取消前当前性漏检、提前释放知识锁、漏实际选中各1test/1准确断言失败；全部0error/真实actual1。首次编译错误不回填。删门仅在外置进程内，原仓库源码保持。新三源与两端最终manifest/负控/稳定性及Git精确绑定在 `分析/RSI协调/pilot-software-20261025/native-self-validation.json`；全部原日志和失败分阶段保留。
- 自看全部实现diff与diff --check通过，不新增生产入口、不扩个人工具执行权、不重跑旧全量/内核canary、不试拨真实模型、不重启日常服务。新原生BC合格语义报告→本人决定→同根D尚未接入，原生HTTPS实际完整硬界与内部尝试计量仍未知，Windows实机锁/凭据ACL及真实Cursor完整CLI/工具计量保留；实际试点开始、本人参与与收益不伪造。后续独立审范围仅本窄面，不能宣布整体RSI/组织净提效完成。


## 2026-10-25 20:37：TOKEN-DIAGNOSTIC-01次数耗尽诊断

- 当前项：次数用尽但remaining仍满时缺阻断原因；状态：**done（窄修自验，独立关闭待核）**。d8独立审限定接受离线Token根，79正常验证和三探针无预算绕过。只在inspect增加call_limit_reached，不改blocked持久语义/取消计数/预留/金额/时间/执行权。
- 新回归连续8次预留后intent前取消，保留calls=8、remaining=100M；第9次仍拒绝且无新增attempt。原17个Token test方法AST逐项相同（编辑中曾误把末尾两行归到新方法，提交前已还原）。红灯 **1test/1failure/0error、0.075s/外层0.268s、actual1**；最终仅5定向方法 **5/5、0.210s/外层0.399s、actual0**，源前后不变，原红灯完整保留。未重复旧大矩阵、不触发HTTP/真实模型。代码/测试SHA在token-call-limit-self-validation.json；当前Adapter/registered输入WIP不进入此窄修提交。

## 2026-10-25 20:22：Token登记与共同知识输入接线

- 当前项：新独立Token登记入口/原capture与lesson selector/renderer共同输入；状态：**doing**。起点e8d990d，普通GitHub推送与线上218运行文件一致/active/restarts0核验完成，工作区干净；既有v2 Broker已显式限定，不更改其执行权。
- 方案：复用原Catalog、registered_plan锚、capture/effective和原selector/renderer，不重写算法。新kind与L5/profile显式匹配；B/C用一个封存input，核原根预封集合，独立登记每个input×arm的唯一意图；计划、正文/来源或策略变化不可借旧回执。内部live入口还须复用当前租户manager/执行门，不由个人read/content连接获得执行权。
- 新D须独立核确切本人采用和实际被原selector选中，不以模型输出或Adapter派生标记代替。真实资料/账号由review准备，不读密码、不代签、不把19:30回填实际启动；无真实可信Token上界时仍零外部模型调用。具体D门与当前知识撤回核对按现有learning_decisions代码收口，不创造人工决定。

## 2026-10-25 20:07：PROPOSAL-EVIDENCE-01追加勘误

- 当前项：修正b61771f原负控证据误标；状态：**done（追加勘误，不覆盖原件）**。原forget-proposal-cost实际为IndentationError、目标测试未执行；原result.json把exit1误当detected_with_assertion=true。旧“三项都准确断言失败”的断言在该项被本勘误撤销，不能当作三项有效控制。原3文件SHA/字节逐项保持，详情audit/negative-control-erratum-2026-10-25.md。
- 独立审查另补有效反例：1 test/1 assertion failure/0 errors/actual1、预算断言0!=16000000；保存在独立review目录，不回填原作者失效控制。b617离线v3限定接受、无产品阻断；62正常验证及同代际竞争不外推Token协议/当前Adapter WIP。新负控汇总核实际退出+结构化数量+准确目标/子用例，不能只认exit1。当前Token负控还曾因另一个不可变门而未检出删门，已加强解析器直接断言，旧无效控制保留。

## 2026-10-25 19:37：PPT自动化短期试运行与Token总根

- 当前项：显式token-only根合同/Adapter、原响应到候选派生及共同renderer/Responses接线；状态：**doing**。起点b61771f，git status干净。已直接读取独立review会话真实人类消息01a172cd-c819-7bc1-83d0-a67ccdf7b5ae与01a172cf-1794-7a41-a3bc-b2de4bc23e9e：项目PPT自动化，2026-10-25 19:30至次日00:30首轮5h；**全链100,000,000 Token替代旧20元费用门**。旧20元合同/历史完整保留，不回写为新授权；费用未知仍未知，本轮不再以价表未知阻塞。
- 账号项目由review准备，本任务不重复创建/查看密码，不代本人确认。5h只属短期试运行，既有按天双周期试点协议不伪装涵盖5h，不宣称长期收益。实际开始/结束必须有真实回执，预定时间不是实际执行。
- 首个窄增量：复用Ledger四DDL/根锚/事务/unknown与一次候选消费，新增显式Token协议，金额缺失不以0/MAX伪装；覆盖A/双臂/B-C/评估/重试/工具/新D同根累计，先预留后intent。须保留完整缓存/推理包含口径与旧版本兼容。生产个人read/content门不扩权，不在单次硬上界未可信闭合前发模型请求。
- Token根增量自验done、Adapter接线继续todo：新增显式v4/v5，不带价格/金额额度，未知金额null、确认/持有/剩余与请求阶段可读；同授权在权威DB中只能一个原根，跨项目/模型/根名和两连接竞争均不能刷新。旧四DDL AST、guard/acceptance/锁字节保持；同根绑定/B-C消费/未知/原期限不放宽。旧Adapter本批仍拒绝新schema。首轮74项73过1fail为新增窗口测试错误回拨wall，原_time按monotonic钳制正确保持，改未来窗口夹具而非弱化原时钟；日志token-root-first完整保留。第二轮156项150过6skip/actual0。最终命令为8模块 `test_rsi_token_budget test_rsi_proposal_root test_rsi_trial_preparation test_rsi_trial_integrity test_rsi_provider_adapter test_rsi_registered_trial test_rsi_registered_isolation test_rsi_controller_replay`：Mac **158项/152过6skip、21.575s/外层22.110s、actual0**；Linux UID1000/Python3.12 **158项/152过6skip、67.701s/外层68.062s、actual0/SSH0**，新/tmp/webuddy-token-root-jhcdlnk4/source的497声明源保持，原验证495源未改。两端3关键场景各5轮 **15/15**，Mac0.381s、Linux4.507s；三内存删门负控（同授权换根、跳Token额度、未知金额写零）各1准确断言失败/0error/actual1。五份Linux原结果/完整日志/声明源113905字节逐SHA读回。未跑旧全量、不重启/写生产业务/调用模型；设计docs/design/token-only-root-2026-10-25.md，自看diff/diff --check通过。
- Adapter后续doing：只扩新Token profile/固定Messages与Responses，不放开旧Broker或个人连接。新bound原件要求完整输入/输出硬上界、无隐藏重试且usage覆盖全部Token；源码校验与独立非root所有者保持。候选只由原SP原始单完整文本派生，后续双臂前重验，不允许调用方传入策略冒充。首轮52方法38过14error（13新夹具误用旧金额根名触发正确拒绝、1猜错模块名）；第二117方法116过1error为原SP按ValueError拒绝改动输出，新binder统一翻译Conflict，原SP与原断言不改；第三9模块 **190项184过6skip、32.438s/外层33.054s、actual0**。现再补隐藏重试与完整计量声明负分支，最终验证待跑；这些声明只属可信部署准入，不由本工具生成/批准真实模型上界。官方完整API文档只读取得，证实Responses输入/输出父项与缓存/推理子项、Messages缓存三项之和；第三方实际配置尚不由官方协议证明。原失败和逐项日志token-adapter-first/second/third保留，真实模型/付费0。
- 固定文本Token Adapter自验done，待固定新SHA独立审；新共同renderer/登记桥继续todo。新Token profile和v5同根，明确Messages/Responses请求与包含计量；强制可信上界原件含无隐藏重试/完整usage，原件身份变化取消。候选仅由原SP唯一完整文本派生，后续重验并核两臂system策略；Ledger声明不自动升级派生验证。旧Broker明确仅v2，旧38个provider test方法AST相同，仅夹具新增路径/Bearer观察。Token新20方法。最终10模块：Mac **201项/195过6skip、34.467s/外层35.049s、actual0**；Linux UID1000/Py3.12 **201项/195过6skip、92.318s/外层92.680s、actual0/SSH0**，/tmp/webuddy-token-adapter-3i51qr_1/source的498声明源保持，原线上495验证源未改。最终两端3场景各3轮 **9/9**；Linux5.589s，Mac见token-adapter-stability-final-mac。各15份有效SP原件和各1份故意损坏原件在原路径核nonce/owner/完整output；有效15均cleanup/reaped complete、remaining_group=false且当前原组不存在，不称全测试无资源问题。Linux六白名单原始日志/结果/审计/源manifest **134233字节**逐SHA完整读回。严格负控3项各实际exit1，准确目标1test/1failure、1test/1failure、1test/2具名subtest failures，均0error；实际退出/结构化结果/目标身份都核，不再仅认exit1。旧初版未检出proxy删门因被另一道合同门阻挡，已新增解析器直接断言；v3严格解析器误把合法subtest后缀当错目标失败，原件保留，v4及最终版按确切两个具名子例核验成功，不伪装旧控制成功。设计docs/design/native-token-adapter-2026-10-25.md；guard/acceptance/锁字节保持，自看diff/diff --check通过。未跑旧全量、未安装生产新入口/改业务/代签/付费，可信第三方实际Token上界仍未验证，声明不是保障。
- 新的预算范围明确记录既往调用：早于本次19:30窗口、其他合成/配置canary不冒充本试轮已执行；如发现本窗口内未归根调用，其实际/最大可能Token必须计入原根初始占用，不能遗漏或另起每模型/每端100M。尚未启动本任务新模型调用，付款金额仍unknown。
- fda3ea6覆盖问题已独立限定关闭，来源分析/independent-review/20261025-fda3ea6-coverage-review；不重跑旧全量。b61771f独立审查由协调侧安排，本次新Token软件不冒用其尚待结论。

## 2026-10-25：后续真实 RSI 无付费软件接线

- 当前项：试点发布记录收口后，先补回归阶段覆盖，再实现提案前原根合同与一次性候选/B/C绑定；状态：**doing（离线根账本实现与定向验证中，生产入口未改）**。起点f94791b，运行代码218文件已发布；发布文档后续只推送记录、不重启服务。主协调18:11沿原人类授权明确继续，不因真人或账单待答停掉独立软件，不重跑canary。
- FIXTURE-COVERAGE-01补强：实现与自验done、待新固定提交独立核验。只改新增回归，在真实HTTP完整响应解码后将首个已就绪响应冻结为旧verify=None；第一次recheck发出前强制检查同run的stale→ready两次消费。mock限于本人测试call，不改server/worker/原件、没有时钟/睡眠/新阈值。原test_a_change整个方法AST与f947完全相同（14原断言及原等待不改）。旧06方法内存注入新回归 **1方法/1同型TypeError、1.588s、actual1、旧源不变**；新定向3/3、4.362s/外层4.800s。Mac20轮40/40、57.765s/外层57.769s；Linux UID1000新overlay20轮40/40、72.750s/外层73.147s/SSH0，源前后不变，完整逐项日志3文件10360字节SHA读回，旧495源保持。证据initial-phase-*。此次纯测试补强不重复2355全量；旧全量只属f947，不挪为本测试新修订全量，线上218运行文件不变/不重启。
- R1实现：scripts/rsi/trial_preparation.py新增显式v3提案前合同（candidate=null保持原hash），另行一次绑定完整策略/原提案回执/B-C预封集合；绑定与全部消费同事务，A及后续阶段共同累计原预算。旧v1/v2与四DDL不变；原Adapter拒绝v3，不开放真实调用。candidate_derivation_verified=false：回执引用并非已证明候选确实由响应产生。新增test_rsi_proposal_root.py覆盖预算/并发/回滚/未知/损坏。首次47方法46过1error为新测试误对settled调用unknown，保留原API拒绝语义，改用既有invalidate_framing；第二轮6模块131方法125过6skip、21.477s/外层22.012s、actual0、源前后不变。现补两连接不同根争同一集合及第二事件故障回滚，继续精确验证；证据proposal-root-first/second。
- R1最终自验done（独立审查待结论）：新增26方法；命令 `PYTHONPATH=tests:. python3 -B -m unittest -v test_rsi_proposal_root test_rsi_trial_preparation test_rsi_trial_integrity test_rsi_provider_adapter test_rsi_registered_trial test_rsi_registered_isolation test_rsi_controller_replay`。Mac **141项/135过6skip、22.576s/外层23.153s、actual0**；Linux UID1000/Python3.12同代码 **141项/135过6skip、61.953s/外层62.298s、actual0/SSH0**。Linux新/tmp/webuddy-proposal-root-idshzraq/source，496声明文件前后不变、原线上验证495源保持；该集合不是新增设计文档的整提交清单。5份白名单完整原日志/结果/manifest **111908字节**逐SHA读回。两端4关键场景各5轮 **20/20**（Mac1.032s、Linux6.515s），无跳过。三项内存故障注入（忘记A费用/允许消费后再提案/异常仍提交）各**1断言失败/0error/actual1**；不是产品执行证据。原四DDL AST、guard/acceptance/filelock字节保持，自看diff及diff --check通过。合同docs/design/proposal-root-2026-10-25.md；新代码/测试SHA与真实退出在proposal-root-self-validation.json。未跑旧全量、未重启或改变生产路由、未付费/代签；实际策略提取、B/C/D共用renderer及Responses/Messages计量接线仍todo。
- 首个窄面：tests/test_platform.py的FIXTURE-COVERAGE-01收紧；随后scripts/rsi/trial_preparation.py、新tests/test_rsi_proposal_root.py及原test_rsi_trial_preparation.py相关验证/设计说明。必须保留旧v1/v2、原四表DDL、原create锚/根hash/预算/期限/代际/未知与一次终测消费；不得用假candidate SHA占位，也不得替换_pool返回合同来悄悄改变旧根身份。新派生绑定另有不可变锚，未绑定前仅提案、绑定后终测需原消费；需要与原提案输出证据相连。
- 后续共用原lesson selector/renderer、明确Responses/Messages计量与固定资料文本模式，复用原Ledger/SP/既有模块；具体耦合按代码再收口，不建新框架、不放开旧fixture Broker或个人read/content执行权。无付费负控可直接做，正式调用在可信费用全上界闭合前拒绝。20_000_000 micro-CNY为全链单root总额，不按阶段/模型重置。
- 只读依据：分析/implementation/20261025-pilot-fixes/live-next.md及本机pilot-software-20261025/next-rsi-software-notes.md；旧合同“未找到profile”的历史有限结论已被服务器Responses/本机Messages配置发现更新，不再说全局无配置。真实项目/日历/个人账号/本人五职责确认、供应方计费/硬上界问题已问待答，不重复问预算、不代签。模型/paid0，真实A/B/C/D和多人周期未核证。

## 2026-10-25：多人试点首批软件

- **本批软件状态：done，18:26:44 CST 已上线f94791b并普通推送GitHub。** Mac2355/2317过38skip/actual0、556.689s；Linux2355/2319过36skip/0fail/error、unittest983.076s/full984.885s、wrapper992.935s/actual0；SDK1.30.0 74/74、16.542s/外层22.367s。声明495源、218运行文件逐Git/包/长度/mode核验，100合成HTTP及指定进程/socket/key清理通过，原1000/90秒期限不改。
- 独立f947窄审限定接受等待条件与前版产品结论承接：两版各495和完整归档/218运行一致，14原断言AST+300/.05/HTTP20保持。**FIXTURE-COVERAGE-01非阻断覆盖边界仍保留**：一次注入可能落在首次recheck之后，不能声称每轮均击中初次窗口；后续补强要在首次recheck前证明旧响应被轮询消费并再读成功，不重开已关闭产品P2。Linux40逐项完整日志随后3文件10412字节读回核SHA，原审18:22未读的历史边界不改；首读误期待不存在guard结果的诊断失败保留，没有补造回执。
- 新full实际在/opt/webuddy/releases/f94791b3f421-team-pilots-20261025/verification/test-source；validation-origin原路径/495/218/9原回执摘要完整，347额外成员仅生成pyc+2准确元数据，不把声明源保持冒充完整成员不变。旧06失败/tmp树未合并为成功。新gate57685e3e...实际通过（源码/日志/SDK/迁移/HTTP/清理），GitHub源精确f947；ResourceWarning原样保留，不称全测试无资源问题。
- 完整副本1781成员重复迁移通过；正式备份/opt/webuddy/backups/pre-f94791b3f421-20261025T102641Z含旧app/data/config及三项目.tmh277/37/20成员，逐字节核验。原60业务+11控制表原行/schema保持，仅3新空试点表。18:28:27启动约102秒后18项回环/公网检查，18:29:15 final active/running、PID2809751/restarts0/error级日志0、218源码保持；worker2809754/start_ticks978998710未变。原业务/控制/非DB/项目/知识账本/配置/Caddy/另一应用保持；Mac18:29:19独立TLS4项通过，无生产个人会话、业务或代签。PID只属当次观察。
- 17份白名单服务器原证据507702字节完整读回，清单SHA0b863b2b79ca62261a7472c565a5b9cff59a6fc2d59a8c2eb2cbedcf57aaee58；备份/凭据留服务器。发布说明audit/production-deployment-2026-10-25-team-pilots.md，全部旧失败/原图原文保留。软件已发布不表示真人试点或真实RSI闭环完成；score=null，不认定80%。Windows锁/凭据ACL实机及POSIX网关限制继续待验。

- 06b精确验证：Mac2354/2316过38跳过/actual0、558.944s；SDK1.30.0 74/74、16.988s/外层23.08s。独立fixed-06b147c-review限定关闭两P2/核03（7/7+真实HTTP/桌面390/全文导出），不是发布门批准。完整副本1781成员两次迁移通过，原60业务/11控制原行/结构保持，精确3新空表，worker/socket/key清理通过，生产未切换。
- 06b Linux **完整2354、36skip、0fail/1error、unittest975.068s/full976.827s、actual1/SSH1**，并非1000秒超时；错误为test_platform.test_a_change_is_built_again_without_being_redone读取verify=None。旧1000超时仍独立保留，不能追认通过。现场 /tmp/webuddy-pilot-06b147c-KAJGi5sm；原failure-hooks及后来完整类数据/278份原件在diagnostic-platform-preserved，明确是全量结束后捕获，不冒充失败瞬间。原类数据/tmp/tmh-data-i8a9o4x8仍原地。
- 根因：api_ticket先读verify、后读events；后台在两读之间完成验证并发布review事件，原测试只凭后读事件退出，用先读的None继续断言。该测试、api_ticket/_flow_commit/verified在现役6ed与失败06的AST逐项相同，属于原基线观察时序。真实受控交错probe v2 **1方法/1同型TypeError、actual1、源不变**；v1探针误把已解码data当字符串，诊断错误单独保留，不算产品反例。新永久stale-read回归在原06方法内存注入，同样 **1方法/1TypeError、actual1**。
- 窄修只改tests/test_platform.py：等待同一响应里同一fix运行的review事件和非空verify。**原14条断言AST、range(300)、sleep(.05)逐项保持**，产品/原3秒8秒及full1000秒不改。永久回归对真实worker已发布事件注入一次旧空读取；没有新增时钟、睡眠或时间阈值。初稿曾用2秒交错屏障、定向3过，提交前移除该额外时序依赖，改为上述确定注入，未发布初稿。
- 最终定向3/3、4.280s/外层4.653s，日志2808c4f738f4d9ac59fab31d21ef2854b4aeae5b66f4e72a1afd64aa752e26e6；Mac20轮 **40/40、56.066s**，Linux UID1000同一修订叠加到新独立诊断树20轮 **40/40、73.790s/外层74.151s、SSH0**，源前后不变、旧06全部495源保持。接下来单独固定测试修复提交，并重新精确双端全量/SDK/发布门；不把06已失败全量改写为成功，不激活06。

- Linux超时诊断的窄修单独提交：两个HTTP夹具原serve_forever默认0.5秒轮询使每次shutdown空等约500ms；同一冻结Linux源4+4轮只测setup/cleanup，默认499.809–500.250ms，显式poll_interval=.01为9.493–9.866ms。只改tests/test_tenant_gateway.py与test_rsi_provider_adapter.py夹具轮询，原12+38个test_*方法AST完全相同，真实请求/进程/测试期限、3秒/8秒及full1000秒不变，非daemon请求handler仍join。8相关模块 **96/96、62.275s/外层63.241s、actual0**（http-fixture-targeted，日志SHA001de6e65a262982c66c553426ab2e3e0884d60f90cd41796a9374ebfbc1ee2e）。只能证明这部分空等改善；是否足以解决全量超时仍等新版本全量，不追认原失败。

- 独立产品审查3692：changes_requested，原候选不发布。PILOT-PRODUCT-01首验→返工→再验把14天线重置；已改按原metrics首验锚，最近验收另列，UI明确首验期内返工。PILOT-PRODUCT-02缺complexity草稿可保存后GET500；新写入显式空文本，旧成功草稿只读兼容、不重写原协议/hash。防御性PILOT-PRODUCT-03按冻结ticket.id并核原项目/key，引用身份也纳入id；维护SQL移出旧任务并复用编号时保留原件、当前未知，不宣称已证明用户可达跨项目泄漏。
- 反例与修后：red-review-regressions 4方法/2断言失败+2KeyError；其中ID夹具起初选错非末尾工单，原失败保留，改夹具后red-review-id-v2 1方法/1产品断言失败。green-review-regressions68/68；加HTTP链后69首轮1个测试误用列表字段KeyError，改为现有items后green-review-final-v2 **69/69、10.578s/外层10.980s、actual0、源不变**。日志SHA d637979ada48a6f8ab53b6ddc5fa3f0c9d966a45724da0d19230364832f8ff59；未削弱原测试或时限。
- 原3692精确Mac全量2349/2311过38跳过/actual0、608.976s与SDK1.30.0 74/74保留；Linux UID1000/Python3.12.3 **outer1000s TimeoutExpired、SSH actual1、无完整结束回执**，不算通过。原源/失败现场保全；尾部6模块75方法/59过16跳过、28.810s仅定向诊断。新修提交须重新精确全量/SDK/独立复审和迁移发布门，未部署。
- 人类新资料：LYB软件工程师、LLA项目老板/领导，首轮**20元总根预算**，覆盖所有阶段/模型/重试，不按每调用或子任务重置。实际账号ID、本人确认、五职责分配/真实项目日历仍缺；不代签。可信成本上界/计量与真实工具桥未完成，不由本预算声明开放付费运行。

- 当前项：协议draft/本人确认/投入事件/固定全集报告及原页面入口；状态：**done（软件已发布；真实试点未开始）**。基线b92375e，C2已单独固定并推送，工作区原本干净；其新的未参与实现审查者已限定批准C2（20261025-b92375e-fresh-C2-review），不把原实现者自测算独立通过，不扩大为整体真实任务完成。
- 新协调优先级：先完成pilot-analysis所列最小可用软件，不因真人未填资料停掉软件；先前宣布的生产输入对齐保留为模型桥后续，不与本批混改。可审合同 `docs/design/pilot-software-contract-2026-10-25.md` 已保存：具体字段、draft/frozen/active/ended、权限/本人确认、CAS/幂等、固定分母、未知不当0及验证发布门。
- 允许变更：新pilots/backend/UI及必要Store/server/tenant_policy/原项目与工单入口、测试/说明。复用原项目/成员/工单/交接，不改MOVES/HUMAN_ONLY/AGENT_ENV/guard/原SP/锁/真实模型门；不启用live/新root服务。真实项目/参与者/日期/阈值空时只draft，不自动freeze/start或代签。
- 资料与证据：只读引用 `分析/implementation/20261025-live-rsi/{pilot-analysis,bridge-analysis,configuration-findings,local-proxy-budget-analysis}.md`，不修改这些文件。本地一次Messages API canary不等Claude/Codex CLI/RSI；服务器仅models成功；本批不重复canary，未知实费/内部重试仍不以0或订阅无限额处理。外部实现证据将存 `分析/RSI协调/pilot-software-20261025/`。
- 实现推进：新增 `tmh/platform/pilots.py`（三表/不可覆盖原文修订/本人确认/授权代际/CAS幂等/个人劳动更正及重叠拒绝/全集报告）、`ui_pilots.py`、原Store/API/项目及工单入口；新增后端、真实租户HTTP及客户端重试测试。现役工具凭据、工单MOVES和模型执行门不改，新增四个仅记录试点的路由；原路由精确清单计数167→171，断言含义仍为精确清单，不放宽权限。
- 初稿失败如实保留：首批46方法4失败（3个HTTP被执行门拒绝、原精确路由数需随新增4项更新）；补仅记录路由策略后30方法中3个HTTP 500，定位Req.arg只接受一个参数，改调用而非放宽门；随后3项HTTP通过。客户端7方法初轮6通过/1夹具JS转义SyntaxError，改夹具原字符串后7通过，不称产品负控。初批16后端通过；新补日期对照/损坏源/跨项目移出/结束后更正等回归正在运行。
- 实际浏览器：独立合成租户已读取真实表单并保存新修订1→2，缺资料仍draft、freeze/start禁用；不是生产业务记录。后续继续做最终字节桌面/窄屏、完整表单链路、精确全量/兼容及独立审查；未发布、未声称真实收益。


- 收口补强：原start在授权锁内重核全部同版本确认；新草稿不阻断旧活动版本本人的记录/结束；更正只允许同pilot/revision及原协议摘要。新增跨归属/并发更正、部分填报、跨阶段整条未分配、旧截点保持、私有实验运行误绑拒绝回归；完整性始终unknown，费用/收益未知。报告带服务端观察时间、事件范围、完整快照摘要及数据库/文件读取区间，既有14天线不改。
- 阶段外覆盖反例：最初新增字段检查先出现1fail+1KeyError（夹具顺序不足，不冒称两个产品反例）；调整先检原缺失数后，2方法/2断言失败/0error、actual1，源字节/日志在 `red-stage-coverage/`；修后阶段外及跨界分钟完整保留未分配，不减少阶段内缺失。最终定向首次64方法1fail+24error，定位新报告直接查可选code_candidates表；改用原只读缺表兼容。第二固定运行 **64/64、10.463s（外层10.978s）、actual0、源前后摘要相同**，完整日志 `directed-final-2/`。未拿这些定向测试替代双端全量。

- 最终定向冻结前验证：**64/64、9.634s（外层9.906s）、actual0、前后源摘要相同**，日志 `directed-final-3/`。后端26、HTTP3、客户端8、原租户策略27；完整发现数2349只作后续全量预期，不冒称已执行。已保留初稿全部失败日志。
- 最终实际浏览器：桌面及390×844；初窄屏root宽647，修容器后root宽390、内部表格容器326，保留前后原截图。真实合成表单再次保存修订1→2，完整首尾空白/换行读回，budget=null、draft、freeze禁用。JSON18660字节/Markdown18951字节读回数据完全相同，报告快照摘要有效、1406字符原目标完整；阶段外10分钟不减少5个阶段内缺失、completeness=unknown。先前两合成人分别确认→freeze→start→15分钟→追加更正12分钟链路只属合成验证；不是生产业务或真人试点。截图/导出均在仓库外 `pilot-software-20261025/`，未压缩原图。
- 合同预审 `20261025-pilot-contract-review` 为固定c929合同的0阻断/4澄清，不是移动WIP产品批准；已落实start重验、完整性unknown、服务端截点/跨阶段未分配、同归属追加更正及并发回滚。运行代码候选即将固定，再跑精确Mac/Linux全量、SDK/迁移兼容及独立产品审，未完成前不部署。

## 2026-10-25：C2第二完成分支的持久快照比较

- 当前项：begin_isolation已有completed结果附带new_execution:false，与isolation_snapshot只含anchor/result的形状差异导致误拒绝；状态：**done（接管窄修与定向自验完成；新独立审查限定批准C2）**。HEAD bf4fbd4；开工工作区已有X和replay测试两文件WIP，完整diff/原字节/SHA已保存在 `分析/RSI协调/controller-C2-20261025/takeover*`。对照 `分析/implementation/20261025-live-rsi/C2/handoff-coding.md` 核对两文件hash一致，接管其3行修正/4回归及SP子进程禁pyc环境，不覆盖、不归属bf4f已提交代码。原实现者停止产品写入，其红绿属于实现自验而非独立审查。
- C1在独立bf4f复审中限定关闭；该批整体仍changes_requested，新C2 P2原4控制3过1失败/actual1保留。竞争可达只作静态分析，没有特权竞争证明。只把prior投影成持久anchor/result，不删末尾变化检测；正常snapshot和真实begin completed item均应重放，损坏/缺失/换绑定仍拒绝，事件/预算/原件不改。
- 允许变更面：X._read_replay的持久比较、必要窄模块/说明/本进度；不改派发/角色代码、root/3秒/8秒/人工权，不重开旧H1/L1/fa3/I1或root大矩阵。确定性第二分支回归含明确cached provider/SP替身与自有普通lease FD，不称真实HTTP、特权竞争或真实计费证明。
- 来源补正：上一独立491声明源字节/mode保持，但出现process_control.pyc额外成员；旧源完整成员未保持，原件不删。探针分类和SQLite表数核验器错误与C2产品缺陷分开。新导出将同时核声明文件和完整成员清单，传递PYTHONDONTWRITEBYTECODE，不用本次结果回写旧历史。
- 新人类指示已核原review turn01a171a5-9106-7bd1-8b47-2f748388a123“那么完成吧。我们的服务器和本地应该是都有配置codex和第三方API的”；已有本地代理/服务器网关新线索，旧有限未找到不作全局结论。C2固定后继续只读核新配置分析；未核真实profile/计量/可信价格与有限根预算前不放开live，多人真人材料不虚构，不重复原询问。

- 采纳WIP后冻结：489文件固定源SHA `68f4fa8465a82263280ad1473b990f372114d79497579302ddf62b5037848192`；基线bf4f+同一新测试的489源SHA `ab0eb240dd12fbc844feb9019c977f0cdf1e7ece2dbd499f6c96c16870064b36`。两条completed正控在基线 **2方法/2断言失败/0error、0.872s/外层1.203s、actual1**；原C2独立4控制3过1败及原C1红灯不改。保存调用cwd/PYTHONPATH、前后声明SHA/长度/mode与完整source成员，基线/修后均无新增pyc。
- 修后只跑`test_rsi_controller_replay test_rsi_controller_channel`：Mac **28方法/19通过/9root跳过、5.051s/外层5.363s、actual0**；Linux UID1000/Python3.12.3，同源 **28方法/19通过/9root跳过、9.283s/外层9.578s、actual0**，非特权、未设RSI_RUN_KERNEL_FIXTURE。已覆盖C1全部9原方法和C2新4方法、原协议投影，未跑全量或旧大矩阵，不称特权竞争/真实CLI/新内核观察。
- Linux证据：277文件460403字节白名单逐SHA/长度读回；39普通SP当前37有效、2为原负控故意损坏/缺输出，39套损坏前完整三文件复制保全，复制件非原SP路径。13套四表before/after逻辑行和total_changes一致，原进程组不存在；cached-provider/transport/output.bin明确是测试替身，不计原SP/HTTP。额外observer在原断言后仅保存原件与逻辑行，不改测试/时钟。原现场位于 `/tmp/webuddy-controller-C2-_nfiwo57`，不递归清理或按历史PID发信号。
- 变更审查：_read_replay AST只多一条anchor/result投影；删除该条后与bf4f AST完全相同，末尾变化检测/所有原件校验保留；WORKER/SETUP/CORE逐字不变。WIP来源哈希与交接一致，未覆盖原文件或偷偷重做别的产品改动。提交前仅补设计/进度文字；执行/测试须与489冻结源精确匹配。证据 `分析/RSI协调/controller-C2-20261025/`。
- **2026-10-25 14:31:29 CST**线上只读215运行文件SHA/长度/mode仍与6edc04f一致，active/running、PID2502485、重启0。本修无新模型/费用/生产重启或真实试点；全量未重跑。配置核查方面另一个获授权会话已记录本地一次API canary HTTP200及usage、服务器models HTTP200，不能再说全局无模型配置，也不能将该未绑定RSI根/未知实费和内部重试的canary算入本修测试或真实A/B/C/D验收。下一项沿fc6合同核新配置/可计量接线，真实多人项目/职责/周期不由Agent补齐。

## 2026-10-25：C1完成重放的原隔离证据重验

- 当前项：controller缓存完成重放绕过candidate/evaluator原证据重验；状态：**done（bf4f独立复审限定关闭C1；另有C2误拒绝待修，见本文件开头）**。开工fc6dd1f、git status干净。独立ac4b227 review/verdict为changes_requested / C1 P2；旧报告与原负控exit1保留，I1限定关闭不重开。
- 允许变更面：仅controller重放、原isolation共用只读证据验证及必要测试/说明/进度。不得调用dispatch来完成重验，不得启动HTTP/模型/角色进程、追加预算/事件/退款或改写历史；正常重放零新派发，损坏/缺原件/换绑定拒绝。保持3秒与8秒、原SP/账本/215运行文件和人工权限。
- 原反例逐字复现：使用独立review固定source及原probe_replay_binding.py，3个真实普通本地SP、合成SQLite及原分支AST，损坏candidate output后内层ValueError、外层仍evaluated/true；实际exit1，账本逻辑行不变。新红灯现场 `分析/RSI协调/controller-C1-20261025/red-original-probe`，原review失败不改。这不是完整特权Session、非root可写私有原件或namespace证明。
- 来源纠正：旧3负控是在一个诊断进程各出现1个unittest断言失败，外层SSH实际0，无3份单独exit1；处理128请求后终止，第129未读而非收到单独denied；旧初次precommit失败缺独立原命令traceback；Mac45 invocation缺cwd/源绑定，不扩张包/交接的间接支持。新验证保存cwd、前后源清单及真实退出。

- 实现：`registered_isolation._admission`复用原准入，新增`replay/_read_replay`只读原intent/binding、execution-result及candidate/evaluator原SP owner/nonce/完整output；原dispatch两个已有完成分支共用它。`controller_channel.Session.run`完成缓存离开原事务后调用replay（不调用dispatch），缓存成功须匹配独立结果；错误/缺原件拒绝，历史unknown不升级。ledger/原SP/WORKER/SETUP/3秒及8秒不变，无新事件/预算/进程/退款。新增`tests/test_rsi_controller_replay.py`，仅在原controller测试加一项root C1场景，原方法AST不改；设计同步明确128后终止不读129。
- 新测试红灯：初稿在线程内反复patch共享方法，造成mock恢复互相污染及后续setUp失败；旧源码/日志保留，不算产品有效红灯。改为每夹具一个patch后，旧实现5方法出现19预期断言失败；扩展后冻结base489源的最终8方法出现22预期断言失败、0error、unittest3.148s/外层3.424s、actual1。同源前后SHA/长度/mode一致，含完整角色损坏/缺原件/绑定、并发缓存及原provider意图/缓存判定不符。原独立AST脚本提取的分支在新helper重构后不再是完整入口，不拿提取适配错误充拦截；修后新模块直接执行完整缓存及只读API，不修改原脚本/原红灯。
- 首次冻结修复489源SHA `fd3a13ce63ca3e3b73003acee9258ceb2b5f5100cd5c9eb0db3a54093786ee58`：Mac36=21通过/15root跳过；root36=35通过/1error，actual1、36.626s/外层36.892s，原root-owned `/tmp/webuddy-controller-C1-owned-gxtpik3z`及完整日志留存。误拒绝来自新replay假设必有provider attempt，私有错误可能在intent前已结束unknown；这属于本轮初稿问题，不归因旧基线。区分合法无意图与应有证据缺失，另加一条无attempt不造新调用的回归。
- 最终修正版489源SHA `3fce0d1c3fbc7b2066efa152c6c40f449c8d70fdd102b88ed9cd521f7941e604`：`PYTHONPATH=tests:. python3 -B -m unittest -v test_rsi_controller_replay test_rsi_controller_channel test_rsi_registered_isolation`，Mac **37方法/22通过/15显式root跳过、6.961s/外层7.245s、actual0**；新root-owned `/tmp/webuddy-controller-C1-owned-b61vm9vb` **37/37、0skip/失败/error、37.183s/外层37.494s、actual0**。两端保存实际cwd/PYTHONPATH及前后489文件SHA/长度/mode核验。root37不是37次内核执行：15root门控含3准入拒绝，9个新普通回放方法的角色均为普通进程；实际隔离UID证明仍只取相应kernel场景。
- 最终普通回放稳定性：同一v2源9方法连续两轮 **18/18、7.017s、actual0**；18套before/after逻辑行及total_changes逐一相等，54套普通SP原件在损坏/删除前复制保存；复制件不冒称原SP路径。额外observer仅在原helper/断言之后复制原件/保存行，无源码/断言/时钟变化。旧v1的24/24另留，不代最终18。
- 补充角色绑定控制：同一最终冻结源上，普通SP/Catalog/SQLite完整缓存入口分别改candidate/evaluator的owner或nonce（同时改两份SP JSON使其内部仍互相匹配），四项均ValueError拒绝，原件随后恢复；1诊断方法/4控制/0失败/error/skip、actual0，3普通SP，无namespace/特权Session。原read-only断言后保存行，源前后489摘要相同。
- Linux原件读回：固定白名单368文件579978字节逐SHA/长度一致。63原路径SP=8controller/9candidate/4evaluator/15transport/27普通测试进程；61当前完整原件验证，2普通回放负控故意留下损坏/缺失输出，必须拒绝，不冒称63均当前完整；27套普通原件均在损坏前复制全三文件，原文件路径绑定保持且只按复制证据审计。相应原进程组均不存在；真实root C1正控及两角色损坏/缺失后的重放前后账本行和total_changes一致、HTTP计数仍1。审计初稿误预期14transport，实际15（原ledger释放测试发原请求及another，共6账本传输）；原审计脚本/失败stderr保留，修汇总数不改源码/测试。
- 传输与历史来源：第二次整包上传90秒超时、未root导入或开测；保留未完成临时目录，原命令traceback仅工具记录、无独立stderr，实际SSH退出不可用。仅向已完整v1非root staging补传X/新测试两文件及manifest，随后root新目录导入前完整489校验，不使用未完成上传。旧red/失败树/首次root源及数据均不覆盖，不把传输失败当测试失败或通过。
- 最终线上只读：**2026-10-25 13:28:49 CST**，215运行文件SHA/长度/mode仍与6edc04f一致，active/running、PID2502485、重启0。本批临时工具/测试/说明不接生产入口，不发布/重启服务、不用真实模型/付费；score=null，真实CLI和真人试点原信息请求继续pending，不重问、不代采用/验收。全量未重跑，只跑本修必要模块与新回放稳定性，不重开旧H1/L1/fa3/I1矩阵。

## 2026-10-25：真实CLI跨任务入口最小合同与断点

- 当前项：真实授权任务→完整capture→同根计量执行→原始产物→可信终测；状态：**done（可审合同与断点清单完成；真实接线/live/试点仍blocked_before_live，未实现）**。开工ac4b227、git status干净；controller候选已送独立review，本批不改候选源码，不重复旧H1/L1/fa3/2115或隔离矩阵。
- 允许变更面：仅新增 `docs/design/real-cli-rsi-entry-contract-2026-10-25.md` 与本进度；不增通用平台/合成隔离层，不加API/表/权限，不把消息当执行领取，不运行真实CLI/付费/生产业务。既有信息请求保持pending，不重问、不代签。
- 已核具体断点：个人工具read/content连接无执行权；普通ticket_get/Git candidate_submit没有RSI根预算/逐调用成本回执；capture是受信来源快照非未来执行授权，Messages不等CLI隐式上下文；生产固定实验仍synthetic，manual Claude费用unknown；Runner有resume fallback/busy内部重试；临时Broker拒live且live transport要求专用非root owner，不能切root夹具模式开跑。
- 最小验收合同：服务端当前成员/授权代际派生任务ID，冻结完整共同输入/CLI工具与隐式上下文，原根覆盖所有内部调用/重试/工具费且首次付费前封闭未知，原SP及完整原产物与来源/版本/根intent绑定，独立终测/真人采用/D及撤回不代签；任何一段未知均不升级等价。真实协议桥和窄执行领取权仍软件todo，不能只归咎缺真人资料。
- 本批验证：只读AST/原源码核对13文件23个具体函数/方法入口，read/content权限不含run_start/candidate_submit、synthetic版本、manual unknown费用及live拒绝在原锚/派发之前均核实；I1 review/verdict逐SHA/长度与其独立delivery清单一致，旧3b changes_requested保留。Markdown表7数据行、相对链接/UTF-8/无隐藏替代字符、git diff --check通过，215运行Git blob/mode与既有线上版本清单一致。actual0；这是静态合同/证据读回，不是新增运行或安全测试。无SSH、真实CLI/provider调用、费用或生产重启；原线上12:30只读观察保持其历史时间，不冒充本批新观察。外部证据 `分析/RSI协调/real-cli-entry-20261025/verification.json`，本次不修改既有封存handoff/清单。
- 当前依赖：原待提供的授权profile位置、明确实际CLI/provider模式及可信价格/强制计量路径决定接线可信边界；真实任务托管人/参与者/周期及试验协议决定未见B/C和D。现有有限服务器配置检查结果不扩大为全机不存在，不再扫描密钥；没有输入不造live命令或用回环换名。该批完成可审合同后停止扩框架，待实际模式/原信息或独立review确切反例再切窄增量。

## 2026-10-25：I1完整blocks类型敏感比较

- 当前项：独立3b复审I1/P2；状态：**done（4a69da72完整已解析JSON语义范围经独立复审关闭I1）**，优先于FIFO收口。原 `分析/independent-review/20261025-3b87a51-isolation-review/verdict.json` 为changes_requested：30457字节实际回环响应已settled/complete，原WORKER内存角色投影6例4过2断言失败/actual1/0error；UID/checks模拟，不是新内核逃逸/付费。原两红灯、完整原body/监管原件和review目录不改。
- 文件：仅 `scripts/rsi/registered_isolation.py` 比较/评估schema、新 `tests/test_rsi_evaluator_types.py`、`docs/design/evaluator-json-semantics-2026-10-25.md` 与本进度。完整已解析JSON值规范序列化比较，全部blocks/附加字段保留，布尔/数值分开；对象键序不计、数组顺序保留；整数1≠浮点1.0、-0.0≠0.0；1e0/1.0解析后相同。明确不是数字原词法相等或上游浮点精度恢复，原native body完整保留。evaluator schema升oracle-exact-blocks-v2，父进程仅接纳v2；UID/候选字节摘要/完整回执绑定不变，非有限值走固定错误。
- 新增首轮比较9方法3断言失败/0error/actual1（true/1、false/0及新增int/float合同），旧X和日志 `red-replay9.log` 保留；随后测试增加schema/nonfinite断言，不冒称首轮test文件完全同字。独立原脚本逐字重放旧冻结源另存 `red-independent6`，**6例4过2失败/0harness error/actual1、1.121s**；修后 `green-independent6` **6/6、actual0、1.056s**。二者真实回环native body均30457字节、逐字相同，SHA `0bc81e6a89d4e803cd34e1ead70d977683e318cdb452e5c13f8b0232226baf44`；同值/正文差异/格式错误/错误角色控制保持。这两轮UID/checks仍是模拟，root/namespace执行数0，不能算OS观察。
- 最终485文件按Git声明模式导出，SHA `fcaf3919e2c1330b4f0bac456313ec31de37bf9aec5ede89e61216cb1f0d725c`。`PYTHONPATH=tests:. python3 -m unittest -v test_rsi_evaluator_types test_rsi_registered_isolation`：Mac **25项/16通过/9显式root跳过、3.586s/外层3.868s、actual0**；Linux非root同源 **25项/16通过/9skip、5.249s/外层5.588s、actual0**，源前后SHA/长度/mode保持。仅相关比较/原隔离模块，不重做H1/L1/fa3大矩阵或旧2115全量。
- 同一485源在root-owned `/tmp/webuddy-evaluator-I1-owned-jujdqzac/`，显式 `RSI_RUN_KERNEL_FIXTURE=1` 同命令 **25/25、0skip/失败/error、16.675s/外层16.937s、actual0**，SSH21.707s/actual0。25方法包含模拟比较/账本/平台检查；9个root门控方法中2个只是准入拒绝，实际合计7次candidate/5次evaluator，不说25次内核执行。Root日志SHA `d42f986d5e7524f33b30313d266a2ed9e16167deeed4e8e3fbaa598ca001df10`。
- I1新增三个真实双身份场景：深40层true/1与false/0均false，同值完整长blocks为true；原测试参数虽反转键序，投影前encoded已排序，不额外证明真实evaluator收到不同键序；3次真实native/candidate/evaluator，各原始角色UID508101/508102、schema v2、完整输入保留、原usage已知settled。独立只读原路径核验9份SP回执/nonce/owner/output与原进程组消失，候选/评估输出不含合成oracle canary。55份完整白名单原件1031657字节读回，含这9份各自计划/结果/output与合成oracle，仅受信审计用，不是controller投影；本地复制不冒称原路径SP。证据 `分析/RSI协调/evaluator-I1-20261025/`。
- **2026-10-25 11:59:28 CST**线上215运行文件仍与6edc04f逐SHA/长度/mode一致，active/running、PID2502485、重启0。本批仅验证工具/测试/文档，未接生产入口/服务、不改data/凭据/原根预算/3秒门槛、guard/ALWAYS_PROTECTED/人工确认/MOVES，实际模型/付费0、score=null。单独固定修复提交与ordinary push由本批外置交接记录；controller新通道代码仍WIP，不混入本提交。
- 3b复审有限范围纠正：旧root门控6例=2准入拒绝+4实际candidate/2evaluator；旧最终24远端原路径回执中，本地10份主轮个体原件、稳定14为嵌入audit汇总，不能说24份均有本地完整原件。旧四负控母版0517，umask是整模块回退到初版并运行新断言，非仅删chmod；其余有限ledger/来源检查不等于整批通过，不重开H1/L1。
- 截至I1提交时controller权限分离仍doing：初始486包仅在临时非root上传目录、当时尚无新FIFO内核执行；此前Mac45相关方法31过/14root跳过是I1修前源，不代替之后通道验收。真实profile/价格与真人项目/职责/周期仍pending，不复问、不代签、不付费。固定exact-match不证明真实未见B/C、真人采用→D或多人组织收益。

- I1独立复审更新：`分析/independent-review/20261025-4a69da7-I1-review/review.md` 与 `verdict.json` 判定 accepted_within_I1_parsed_JSON_semantics_scope / closed_in_fixed_candidate；逐字原6例6/6、独立JSON合同10/10（含实际反序原文）、父AST分支20/20；新增模块12方法=9通过/3root跳过，非新namespace或服务器特权复跑。旧3b changes_requested原件/反例不改；此次关闭不覆盖ac4b227新controller、真实模型/终测或组织收益。
- 来源补正保留：旧Mac25保存日志及actual0可核，但简短invocation缺cwd/源清单/前后核验字段，不能单凭它证明从485导出树运行且前后不变；原red9缺独立invocation，旧模块/日志保留，最终测试另有后加断言，不能把最终字节/直接退出回执归给首红。真实同值kernel输入先encoded排序，对象键序性质由独立10控制证明，非那个kernel场景额外证明。旧封存handoff/清单不覆写，新结论由本进度与后续交接引用。

## 2026-10-25：非root控制器与私有评估资产分离

- 当前项：固定登记ID、非root调度控制器与受信特权配置/评估最小通道；状态：**done（限定临时合成通道自验完成；ac4b227独立复审随后要求C1窄修，修复候选见本文件开头）**。起点f14218a，git status干净；I1随后单独固定4a69da7再继续，3b隔离增量不继承fa3结论覆盖它。
- 边界：受信root provisioning保留oracle读取权，不证明root不可读；把可优化/调度角色移到第三个非root临时身份，只给公开输入与固定run/status/cancel操作，不投影oracle、其可猜测摘要、完整私有计划/错误详情。原根budget/intent/原SP及固定文本动作继续复用，不安装生产root服务、不接任意命令/UID/mount/env接口。
- 计划采用仅两条固定文件FIFO的临时命名空间IPC，root所有者固定读写权限，源与private登记合同绑定；未知/失联不自动重发。真实profile/真人试点仍沿原询问pending，不复问、不代签、不付费。

- 文件：新增 `scripts/rsi/controller_channel.py`、`tests/test_rsi_controller_channel.py`、`docs/design/controller-channel-2026-10-25.md`；只更新本进度。控制器UID/GID508103，候选508101/评估508102不变；两条root所有FIFO只赋写请求/读响应权，独立mount/PID/net/IPC namespace、chroot、清空capabilities/组/环境、no_new_privs；只挂单个端点，不挂私有目录/FD。独立随机root0400拒读canary不含oracle；root仍受信并可读oracle，未宣称root隔离。
- 通道仅精确登记的plan/input ID及input/run/status/cancel四动作；只返完整公开capture和粗状态/冻结verdict，不返私有摘要/错误正文。单请求4096字节、公开帧8MiB、128请求；超限前置拒绝，完整history/NULL/Unicode及全部公共字段不截断。重复ID相同正文原回复、不同正文冲突；一次Session最多一个原Launcher job；原controller意图/结果追加到原事件表，无新预算/表/付费路径，未知不自动重发。控制器自报成功不产生根任务成功。
- I1修后冻结488文件包清单SHA `8b01408881370446377f9ace1b8e694c3c9628506e2cc9cd21b1082b2cac1369`，按Git声明模式导出，保留旧本机两文件0600历史。`PYTHONPATH=tests:. python3 -m unittest -v test_rsi_controller_channel test_rsi_registered_isolation test_rsi_registered_trial`：Mac **45方法/31通过/14显式root跳过、actual0、外层12.522s**；不是内核证据。初始I1修前45结果另存，不替代此轮。
- 同一488源先逐SHA/长度/mode验证，再复制到root-owned0700 `/tmp/webuddy-controller-owned-ziphvcw2` 导入；显式root门控 `python3 -m unittest -v test_rsi_controller_channel` **14/14、0skip/失败/error、16.093s/外层16.434s、actual0**。其中6纯方法、8root门控（1准入拒绝无进程），实际7controller/4回环transport/4candidate/1evaluator，共16原路径SP回执，nonce/owner/output/完整清理及进程组消失均核验；68文件完整白名单读回。日志SHA `fd6ca803ae12c14bfb7d269628444e15f700b535ab7165d588c716bbded0185b`。
- 稳定性：同一488源另建root-owned `/tmp/webuddy-controller-owned-k_pzhr6d`，完整模块连续两轮 **28/28、0skip/失败/error、31.669s/外层31.975s、actual0**；实际14controller/8transport/8candidate/2evaluator，32原路径回执均清理且原进程组不存在，133文件完整白名单读回。日志SHA `60ed31b3f0407ff4405f341e811a1c5272c127e231b885cab41ad840a2edec77`。候选保留原3秒124，控制器8秒124且候选elapsed更短；取消/控制器SIGKILL分别触发原候选130，未知保留原最大预留calls1/tokens120/cost1400且不重发；已知usage/settled历史保持，不虚造第二笔费用。
- 三负控仅在独立诊断进程内patch：放开response写权、向input响应加实际私有execution摘要、将根状态错误认成controller伪成功。各原测试均 **1方法/1预期断言失败/0error/0skip**；源码前后逐字保持。实际3controller/1transport/1candidate/1evaluator，共6原路径SP回执，全部清理/原组消失，30文件完整失败现场读回；原成功日志不覆盖。不是删原断言、假时钟或放宽3秒/8秒门槛。
- 证据位于仓库外 `分析/RSI协调/controller-channel-20261025/`；保存源清单、调用实际退出/耗时、root原路径、逐份计划/结果/output及完整channel、负控脚本/日志/读回清单。复制件不冒称原路径SP。测试源为冻结488清单；提交前只新增验证文档/进度文字，导入的执行/测试字节需再与清单核对。全量未重跑：本批仅显式临时验证工具与相关45/真实root14/稳定28，不重复旧H1/L1/fa3/2115矩阵，不宣称全量或真实模型通过。
- 最终线上只读核验：**2026-10-25 12:30:09 CST**，215运行文件SHA/长度/mode仍与6edc04f一致，active/running、PID2502485、重启0；未发布/重启生产或调用真实模型。提交前初次清单门禁误把未纳入测试导出的进度文件也计入预期差异，实际仅设计文档1处差异而拒绝；没有继续commit，核对清单后改为“设计文档差异1处、进度在清单外”，再严格比较全部执行/测试与215运行文件，不改源码或清单来凑通过。
- 待确认/未完成：真实profile/可信价格、实际Claude/Cursor会话与工具接线、租户授权在真实执行入口再核、未见B/C任务、真人采用→D及多人长期试点仍pending；不复问、不代签、不用合成结果打组织收益分（score=null、真实模型/付费0）。生产专用身份/通用恶意代码资源与系统调用隔离/未知调查恢复及Windows实机仍todo。本批无生产入口或常驻root服务，不因验证工具重启生产。独立复审未完成，不能凭自验升级为生产安全或组织提效已完成。

## 2026-10-25：固定登记ID隔离执行与独立评估最小接线

- 当前项：实际Linux固定文本候选/独立exact-match双身份及登记回执接线；状态：**done（限定合成软件增量，待独立技术复审）**。起点d32954d，git status干净。新增 `scripts/rsi/registered_isolation.py`、`tests/test_rsi_registered_isolation.py`、`docs/design/registered-isolation-2026-10-25.md`；原 `scripts/rsi/trial_preparation.py` 仅加严执行待决/未知控制，本进度同步更新。未接生产入口。
- 实现：原private Catalog登记两ID与精确公开plan/input、原根合同、执行bundle、私有oracle摘要和固定动作。候选只获完整capture/native response；不同评估身份才有独立oracle副本。固定文本blocks交付与exact-match，不执行模型命令/代码。受信Python构造器不是root RPC；不接任意命令/UID/mount/env，只有内部固定路径/角色；导入前必须由受信部署流程验证root-owned源树，不能依靠导入后的摘要消除不可信Python导入风险。
- 实际controller UID0、候选UID/GID508101、评估508102；不使用共享nobody，不建持久账号/服务。root-owned/tmp锁独占两临时身份并拒绝已有账号/活动占用。各自mount/PID/net namespace+chroot，仅只读系统库/proc；清空环境/补充组/capabilities，no_new_privs。实际候选14项布尔观察均true（oracle不映射、host/proc1 root/cwd/env/fd拒绝、继承FD、网络namespace、只读挂载等），并记录真实uid/gid；不能将固定可信程序观察当任意恶意代码不可逃逸证明。
- 账本：原4表DDL不变，只追加根级isolation_intent/finished；一次provider request不能另绑执行，pending阻止新派发并按原最大预留计入。正常独立回执才结束pending；未知恢复原attempt最大预留/阻塞，原已知usage/settled事件保留，不声称新增第二笔提供商费用。原settled→unknown晚回调fence继续拒绝释放；事务故障回滚不丢pending。controller崩溃/结果提交缺失不自动重跑；生产人工调查恢复仍todo。
- 时限/清理：沿原根绝对期限，每角色取剩余期限与3000ms较小值，原SP/process_control摘要固定。真实挂起为124，看到CANDIDATE_READY后真实取消为130，评估未启动/无回执时不报评估通过；未知重放不二次HTTP或namespace。只读原监管回执核nonce/owner/output，root不递归遍历/chown/删除候选树、不做归属回收。
- 初始483源清单SHA `f1db78b421ec8422951d53fb6393d546b6e234ffde69a198672e84c6fbf0e861`：Mac145项/139执行通过/6显式内核跳过、46.596s/外层47.031s/actual0。Linux root首轮6项 **2通过/4断言失败/0error、5.825s/actual1**，原现场 `/tmp/webuddy-reg-isolation-owned-oqbt3d7z/` 与本地 `分析/RSI协调/registered-isolation-20261025/kernel-initial-readback/` 保留。原候选动态库读取Permission denied/退出127；严格umask077将mkdir0755变成0700。修复只对启动前新建的沙箱内部固定目录显式chmod0755，外层0700/oracle0400保持；新增umask回归及proc1 root/cwd/fd实际拒绝检查，不改原断言/3秒门槛。原8份监管回执核验完整/原进程组消失，原红灯不改成通过。
- 中间0517源下Mac/Linux146项各140通过/6skip，实际root6/6通过，保留其源码/日志/10原回执核验。收尾仅给新增POSIX目录模式测试声明Windows不适用，Mac/Linux仍执行全部原断言；没有修改旧本机0600文件或把源目录整体chmod洗掉历史。
- **最终483源**按Git声明模式导出（新文件0644），清单SHA `ee1630983fd2a65c9f4d2956a1c90f76be86b1235ca9dc654da8c5be662cdd2e`。命令：`PYTHONPATH=tests:. python3 -m unittest -v test_rsi_registered_isolation test_rsi_registered_trial test_lesson_input test_learning_input_capture test_learning_lesson_inputs test_rsi_trial_preparation test_rsi_trial_integrity test_rsi_provider_adapter`。Mac **146项/140通过/6显式root内核跳过、46.559s/外层46.964s、actual0**；Linux同源非root **146项/140通过/6同类skip、82.543s/外层82.996s、actual0**。前后483文件SHA/长度/mode保持。两端日志SHA分别 `9ed0d14d52528bba220c2e100025cdbe749b65749dd248ce63724bb92b88c53f` / `e189eb5c34cc0e8cb33a6194598a2fc18a74f2e2e492cb7e69c3b46023f0c1d5`，不把六项skip算内核通过。
- 同一最终483字节/声明模式在新root-owned私有目录 `/tmp/webuddy-reg-isolation-owned-pb56b0e2/`：`RSI_RUN_KERNEL_FIXTURE=1 PYTHONPATH=tests:. python3 -m unittest -v test_rsi_registered_isolation` **13/13、0skip/失败/error、14.136s/外层14.432s、actual0**（含六实际内核场景）；SSH19.156s/actual0。日志SHA `b42aee5360e0c59fa0192f19263b6941fdf50de58c61568b080d69a0cb23d64d`。正常原生文本、错误oracle布尔false、缺失/变化/任意命令零HTTP、实际timeout/READY取消、未知不重跑均核验；exact-match合成不等于真实任务正确。
- 稳定性：同最终root源码对正常交付/真实超时/READY屏障取消轮换两轮，**6/6、各actual0**，unittest6.057s/6.028s；未改3秒或可控时钟。外置负控：旧mkdir实现+新umask断言、删pending派发门、删pending最大预留、删晚结算fence，**4/4准确断言失败/actual1/无error**，保留各修改副本/日志，不把负控失败当产品失败。
- 原件：最终主轮10份监管原件（provider4+candidate4+evaluator2）及稳定性两轮各7份，共**24份**在原路径用原SP.read_receipt核nonce/owner/原始output，再只读检查原进程组不存在；全部cleanup complete/reaped、remaining_group=false，无oracle canary出现在角色输出。评估oracle副本0400/UID508102，候选root无oracle；两数值UID无账号/活动进程，宿主无夹具挂载。旧初轮8份与中间10份另保留，不混计最终24。
- 白名单读回：最终Linux非root3份104000字节；root52份190913字节，含最终/稳定性日志、原件audit、公开输入、固定执行结果和role原始输出，逐SHA/长度读回。并非全量root夹具/数据库/私有oracle/凭据复制；全部原始现场仍在远端private目录。原件本地副本不冒称可用原路径SP核验。完整清单见仓库外 `分析/RSI协调/registered-isolation-20261025/release-readback-manifest.json`。
- **2026-10-25 10:35:00 CST**只读核验线上215文件SHA/长度/mode仍与6edc04f相同，active/running、PID2502485、重启0。未重启/改生产入口、数据或凭据；未创建持久账号/常驻root服务/8791或8793日常服务，所有HTTP为临时合成回环，实际模型/付费0。guard、钩子/ALWAYS_PROTECTED、人工确认/采用/验收/关单及MOVES未改。只跑相关增量，不重做旧2115全量或已关闭H1/L1矩阵。
- 代码固定为 **3b87a51b767e4c90f46be7ee000a4d35fbde965d** 并已普通推送，483测试导出与该提交Git字节/声明模式一致；随后单独文档澄清oracle权限，不改执行/测试源码，不将文档新HEAD冒称原483逐字相同。受信root setup/controller当前同进程，确实读取oracle用于格式核验、角色文件配置及canary检查；只有语义答案比较在独立UID。**controller自身不能读oracle尚未实现**，需后续非root controller与特权资产配置/evaluator分离。本轮证明候选看不到oracle，不能升级为全部控制角色资产隔离。
- **10:42:57 CST**最终215运行文件仍与6ed相同、active/running、PID2502485、重启0；真实调用/付费0。本批不安装生产root入口。
- 固定提交/普通GitHub推送及最后运行核验由外置 `coding-handoff.json` 记录；本增量独立复审待结论。真实CLI/IDE执行工具、任意候选代码资源/系统调用隔离、生产专用身份、实际未见B/C与真人采用→D及多人长期收益仍todo。native Messages隐式会话/工具差异保持，`production_equivalent=false/rsi_qualified=false`，没有组织收益加分。
- 待确认沿原请求：可信profile/价格、真实项目/A/B/C/D、实际人/职责/周期仍pending，不复问、不代签、不付费；HTTP signed chunk-size限制在live准入前必须限定支持框定。Windows原生监管/隔离/凭据ACL仍未实现，不把POSIX测试前置当Windows验证。

## 2026-10-25：登记输入到执行回执最小接线

- 当前项：固定计划/输入 ID、真实生产输入冻结与原根预算/provider 回执串接；状态：**done（仅输入接线增量，独立复审在此范围接受）**。起点2a543fc，最初工作区干净。已核851独立verdict：原H1/晚回调fence关闭、L1保持关闭；额外signed chunk-size限制原红灯保留，不声明完整RFC解析。
- 文件：新增 `scripts/rsi/registered_trial.py`、`tests/test_rsi_registered_trial.py`、`docs/design/registered-input-execution-2026-10-25.md`，更新本进度。调用一次原 `agents.build_prompt` / selector / renderer，不重写经验算法；保存原始全量history及原生产有效最后六条窗口、完整工单/项目/提示词/经验上下文与来源前后快照。不是无副作用dry-run，只在合成临时Store验证。
- 登记合同：私有所有者/权限/单链接/nofollow；先完整写入/fsync，再原子发布非空目录，同 ID 不覆盖。计划固定输入、原根合同/request/phase/策略/broker源码摘要，拒绝任意命令/UID/mount/环境。原 `rsi_prepare_events` 根级登记锚绑定计划和输入来源；提示字节即使相同，来源变化也不能重标旧回执；已有调用缺原锚时拒绝回填。不新增表/预算，不改原attempt状态序列。
- 调用复用原Ledger/Adapter的生成、judge、probe、retry、terminal、baseline/candidate/followup阶段、唯一intent、期限和累计预算。登记记录/代码变化或外部取消走原监管取消，未知保留最大预留并阻塞，旧未知重放不二次HTTP。live声明在登记锚/预留前拒绝；fixture之外尚无实际派发通路。
- 首轮夹具用不存在的Store.add_ticket，`first.log` **9项/9初始化error**；对应两源在 `first-source/`，该轮临时数据库未完整保留，不冒称保有全部失败现场。改用原create_ticket后 `second.log` 9/9。长经验夹具弱匹配未入选导致 `third.log` 13项/1error及 `targeted-final.log` 58项/同1error，日志保留；改为显式同flow来源匹配，不削弱原selector或断言。随后58/58两轮通过。
- 阶段结果分开保留：`related-final130.log` **130/130、41.309s**，`pre-persistence-source/`保留当时版本；补类型校验/持久夹具/live拒绝后 `final131.log` **131/131、41.135s**，`source-at-final131/`封存其两个源码。本次再加输入字节变化取消与外部取消未知重放两个反例，先定向2/2、actual0；130/131均不替代最终133精确源验证。
- 最终选取原477文件加新模块/测试/合同，**480文件**精确导出，前后SHA/长度/mode保持；清单SHA `0e08a1fc3c55e71c6342afee39dedfa53cb920dfab47c4daa41e48b0be43c959`。命令：`PYTHONPATH=tests:. python3 -m unittest -v test_rsi_registered_trial test_lesson_input test_learning_input_capture test_learning_lesson_inputs test_rsi_trial_preparation test_rsi_trial_integrity test_rsi_provider_adapter`。Mac **133/133、44.282s、外层44.629s、actual0**；Linux同源 **133/133、75.746s、外层76.116s、actual0**，SSH外层80.428s/actual0，均0skip/失败/error。最终Mac/Linux日志SHA分别 `d8d2a0d43a7b4bd9b3573ce639bd0649d6b045273d9c2d80c9913813a9891e64` / `9781430ff626cc402ec15b21c10856f9479cbad97048b780eedc99eefb045d55`。未重跑未改的旧2115全量、旧151框定大矩阵或内核canary。
- 稳定性：并发同意图、原子发布屏障、代码变化取消、输入变化取消、外部取消未知重放五场景轮换5轮 **25/25、各actual0**。外置副本删除来源锚检查、代码取消检查、live入口检查三项负控 **3/3准确断言失败、各actual1、无error**；没有改原仓库运行源/旧测试，也没有放宽时钟/原5秒期限。
- 原件：Mac/Linux各12个新Broker场景、各15份transport监管回执在**原路径**用原SP.read_receipt核验nonce/owner/output字节，均清理complete/reaped、remaining_group=false、原进程组当前不存在。Linux四份白名单报告132270字节逐份SHA/长度读回；远端完整合成夹具留在 `/tmp/webuddy-registered-input-3c5q2t2b/`。原tar8499200字节保持，SSH按次使用无损压缩传输53.082秒，不改变归档/源文件。
- **2026-10-25 09:43:02 CST**只读核验：线上215运行文件SHA/长度/mode仍与6edc04f相同，active/running、PID2502485、重启0。本增量仅scripts/tests/docs，不接生产路由，不部署新运行入口、不重启、不读写真实业务data/密钥、不付费、不代签。人工确认/采用/验收/关单、guard/ALWAYS_PROTECTED/钩子/MOVES未改。
- 证据根：仓库外 `分析/RSI协调/registered-input-wiring-20261025/`，含旧失败日志/阶段源、最终480源/两端实际退出回执、稳定性/负控和原件核验。固定新SHA普通推送后由协调侧独立复审，不以自检替代独立结论。
- 代码/测试/合同固定提交 **fa3e7e2685fa28f24a1ed1c4987fe67081f56a70**。最终本机文件权限核对脚本因既有 `tmh/mapper.py` 为0600而Git/生产0644退出1；同一shell命令块随后仍执行git commit，整体工具退出0，故不能把整体退出当该核对通过。失败与原因记录在 `committed-source-verification.json`，没有改原文件权限。后续逐Git blob确认480导出字节均与fa3相同、215生产文件Git字节/模式/blob均与6ed发布清单相同；另发现导出中 `scripts/realworld_test/driver.py` 同样为既有本机0600/Git0644，精确区分测试导出文件系统权限与Git模式，不冒称两者全同。这两处无内容/执行位变化、不涉及运行源码改动，原两端133结果保留、不重复同一测试矩阵。线上实际215权限已单独在09:43核验。收尾记录另起文档提交，随fa3普通推送；实际远端HEAD与最后只读运行核验保存外置交接JSON。
- **后续执行主线（fa3交接时todo，当前固定文本最小实现见上节）**。本批 `isolated_execution=not_run`、`oracle_evaluation=not_run`、`production_equivalent=false`、`rsi_qualified=false`；native Messages无真实CLI/IDE工具及隐式会话，捕获前后快照不是未来授权，也不证明全世界原子一致。原HTTP signed chunk-size限制须在真实profile准入前收紧支持框定；不把合成调用算真实A/B/C/D或M/C/P。
- 待确认沿原询问：可信profile/价格、真实A/B/C/D、真人/职责/周期尚pending，不重复询问、不代填。Windows原生监管/隔离/凭据ACL仍未完成。真实付费0、真实试点not_run、组织收益评分null；下一个窄增量不得开放任意root命令/挂载/UID接口。

- fa3独立结论已核 `分析/independent-review/20261025-fa3e7e2-registered-review/verdict.json`：登记输入范围接受、无新增阻断；18原新增、capture8/Catalog11/Broker6有限复验。预算拒绝可能保留registered_plan锚（不等于全DB无变化），capture普通usage IO不随后续失败回滚。历史两文件FS0600/Git0644模式门仍fail，原组合shell原始回执缺失；自记实际gate1不能代替原回执。此前Linux本地仅4白名单汇总132270字节，不是15份原件副本。该审查不证明当前跨UID/生产等价，也不重开H1/L1。

## 2026-10-25：H1 HTTP响应长度与原件复核

- 当前项：H1/P2非法/矛盾Content-Length；状态：done（代码及最终固定源验证完成；851独立技术复审仍待结论）。起点9c5beb5，git status干净；已读独立f4b报告和原七例，两轮实际exit1，原反例不覆盖。只修原始响应头核验及已知坏原件的保守隔离，不重做已通过配置/预算/来源矩阵，不改变生产入口或真实试点分。
- 决策：十进制ASCII长度，所有重复/逗号列表值必须一致；仅允许明确的单chunked编码，TE与CL同存拒绝。非法原头仍保留所收完整正文，首次与reconcile共用校验；旧transport零退出不能作为充分证据。真实profile仍待外部提供，不重复询问，不付费。

- 实现：transport与原件reconcile共用原始字段校验，ASCII十进制/全部重复及逗号值一致、真实正文长度一致；合法同值列表归一化后可在keep-alive关闭前完成。单chunked无CL受支持；TE+CL/未知或重复编码拒绝。坏头保留已收到正文，仍受原期限/资源门，无重发、费用门不变。账本仅新增保守invalidate_framing事务：核原nonce和settled锚后隔离，旧结算/回执保留，最大预留恢复，重复/并发只隔离一次；合法旧版本仍拒绝版本自动升级。
- 原9c5字节新增17方法得到 **5方法通过、12方法含失败（14个断言失败事件，含3子用例）、0error、actual1、16.589s**。红源、真实wire/body、数据库及监管现场保留于仓库外 `分析/RSI协调/provider-framing-H1-20261025/red-fixtures/`；独立原两轮红灯不覆盖。修后88/88、148/148、加nonce/原锚回滚和并发后150/150均actual0，日志分别保留。
- 最后补上首次transport非零退出断言，477文件固定导出运行 `PYTHONPATH=tests:. python3 -m unittest discover -s tests -p 'test_rsi_*.py' -v`，**150/150、45.128s、0skip/失败/error、actual0**；原工作树同代码150/150、45.108s仅在此新增断言前，不冒称测试文件逐字相同。后续固定导出为最终字节证明；旧local-eval HTTPError资源警告保留。首次导出调用因cwd目录未创建被工具拒绝，进程未启动/无测试退出码，先构建目录后正常执行，未把工具拒绝说成测试失败或通过。
- 实际旧原件复核：独立原七场景的数据库各做完整副本，只读原证据；三笔旧错误settled经原零退出完整监管回执/绑定原头/body核验后隔离，恢复120/1400且blocked；两个原unknown仍保留最大值，两个合法旧原件仍被版本门拒绝自动升级。**7/7符合预期、原文件及原settled事件保持、零HTTP派发**，原件路径/摘要及副本结果在 `original-reconciliation.json`。
- 稳定性：六关键场景轮换5轮 **30/30、actual0**；外置副本分别删除transport双重校验、reconcile原头校验、隔离前原settled锚校验，**3/3准确命中断言、无harness error**。没有在原源中写故障，不重跑已通过的配置59拒绝/预算/来源矩阵，不跑未改生产的旧全量。
- 待依赖：Linux同固定源复验及独立原七例脚本重放待本次固定提交后完成；真实profile仍pending，真实模型/付费0、评分null，不能算跨任务或多人收益。

- H1首候选3474866已在Linux固定477文件 **150/150、67.834s、actual0**、原两个独立脚本七例均actual0；该候选未push/未启生产入口。自查发现直接Ledger.settle晚回调仍能绕过wrapper把隔离请求再结算，新增1方法/2历史状态反例 **2个断言失败、0error、actual1**，原源码/两库保留于 `分析/RSI协调/provider-framing-H1-fence-20261025/red-fixtures/`。不把347的通过当最终完成。
- 补齐：隔离也给原unknown写唯一已知坏框定标记；settle事务内核原unknown摘要并拒绝已标记及“旧settled后unknown”重结算。首发完整坏框定即记录标记，不仅靠reconcile；普通未知晚结算语义/原receipt锚保留。定向四模块 **94/94、46.251s、0skip/失败/error、actual0**，包括nonce/损坏原锚回滚、并发只隔离一次和原普通晚结算。固定补齐提交后另做精确导出/Linux/原脚本/原件复核，不挪用347源码结果。

- 最终代码固定为 **85133ce9f80e3bf1377f57c8b55bc6139564ad1b**（含3474866主修复及晚回调fence）。477文件直接按Git blob导出，`PYTHONPATH=tests:. python3 -m unittest discover -s tests -p 'test_rsi_*.py' -v` **151/151、46.177s、0skip/失败/error、actual0**；服务器同477文件前后摘要相同、**151/151、69.239s、actual0**，测试SSH外层73.361s。新包无损原始tar上传344.260s，期间两次只读进度先430后477文件，未中断或把传输时间混作测试时间，原tar/原件保持。
- 最终复验曾从错误cwd使用相对fixtures路径，**151项/61初始化error/0failure、actual1、4.462s**，相关夹具没有进入断言；完整日志移存 `provider-framing-H1-fence-20261025/misdirected-export-command.log`，未丢弃或修断言。改用绝对路径后才执行上述最终导出151通过；fixture错误不是产品回归，不能拿前次94/347的150替代最终851。
- 851下两个独立原脚本逐字复制重放，4例+3例均**actual0**，完整wire/body/DB/监管回执和477源前后SHA保持；原七例旧原件数据库副本再次**7/7预期、3笔错误旧settled恢复最大预留、原事件/文件保持、零新HTTP**。追加晚回调fence后六关键场景加直接回调轮换5轮 **35/35、actual0**；四个外置删检查负控均准确触发断言（最后一例2子状态失败），无harness error。所有旧红绿和新结果分目录保留，原配置/预算/来源大矩阵不重跑。
- 最终证据：仓库外 `分析/RSI协调/provider-framing-H1-fence-20261025/`；导出log SHA `6ab75eba0392ef35032df6ee55c68e33d2b76ec84a01beed7ef9ac68893f93af`，Linux log SHA `4dc9feef5ddfc71f3ff76189407b9735be26c49595c1c825e4fb4236f9e4c366`，旧原件复核JSON SHA `f21cf77bcd37d6789dad1e501834833bad8b9582b53a0a019062337a9dc98d1f`。最终导出/远端各有实际退出观察或subprocess退出回执；不将仅日志标签当新版本退出证明。
- 2026-10-25 **08:08:13 CST** 只读核验：线上215运行文件SHA/长度/mode与6edc04f相同，active/running、PID2502485、重启0。新软件仍未接生产入口，未重启、未写真实data/配置/密钥、未调用真实模型或付费；score=null、M/C/P不加分。代码和普通unknown合法晚结算/人工边界均保持，未跑或归因旧2115全量。
- 独立L1结论已核 `分析/independent-review/20261025-9c5beb5-L1-review/verdict.json`：b846/9c5固定清理范围关闭（11+8+12+22及18原件），不再重开L1/重跑内核。边界：fchmod失败会异常并关闭FD但mode可能仍0755；caller成功open前准备异常不在该finally；不等于专用生产隔离。H1固定851复审进行中，原9c5报告中的H1 open不是对851结论。原profile询问及真实A/B/C/D/多人长期试点合同仍未获外部信息，不复问、不代填、不声明80%。

## 2026-10-25：新增验证的平台前置声明

- 当前项：新增HTTP/FD验证的POSIX前置；状态：done。起点b846eb2，适配器f4b53ad及L1固定修复已分别普通推送。只给两个新增测试类明确POSIX平台skip；当前Mac/Linux不跳过任何断言，不改已有测试，不将Windows宣称为支持。供应方/账本/探针代码不改，随后定向复验并独立提交。

- `PYTHONPATH=tests:. python3 -m unittest -v test_rsi_provider_adapter test_rsi_linux_cleanup test_rsi_linux_holdout_probe`：Mac **49/49、26.401s、actual0**；服务器新476文件固定导出同命令 **49/49、actual0**，均0skip/失败/error，前后源码摘要一致。只有新测试装饰器和文档改动，f4b53ad的provider/ledger代码与b846eb2的Linux探针代码逐字保持；无需重跑同一固定探针内核场景或旧全量。
- 将实际装饰器表达式用合成os.name=nt求值，44项均在setUp前skip且无error；这是前置条件负分支验证，不冒称真实Windows执行。Windows原生监管/隔离/凭据ACL仍待完成。证据 `分析/RSI协调/provider-platform-test-contract-20261025/`。

## 2026-10-25：Linux探针L1清理边界修复

- 当前项：L1/P2特权清理链接越界；状态：done（修复与固定版本本地/真实Linux验证完成，待独立复审关闭）。起点f4b53ad（provider固定增量已普通推送），工作区干净，原独立88dd报告和红灯未覆盖；只修探针清理，不重复旧账本/评分/生产全量，不运行旧特权代码。
- 方案：取消root递归chown及工作树遍历；仅对启动前固定的原fixture目录FD收紧0700，保留root产物原所有权，不接触worker目录内容。增加真实文件链接、目录链接与路径替换的无特权回归；固定源码后再核正常/真实超时。待确认：无，真实模型/专用生产隔离仍未完成。

- 原字节e502下新增6回归 **2通过/4断言失败/0error、actual1**，原源码、精确finally AST、链接和路径替换现场保留于仓库外 `分析/RSI协调/linux-cleanup-L1-20261025/red-fixtures/`；chown仅记录，不执行真实chown。顶层路径替换红灯确实改变了外部**合成目录**的mode，该前后差异保留，不宣称原代码无影响。独立原报告/红灯未改。
- 修复：root不再递归chown、遍历/读/删worker工作树；只对运行前固定、O_NOFOLLOW且所有者核验的fixture目录FD执行fchmod0700并close。caller在sudo/预检失败时也固定FD收紧顶层，stderr经目录FD以0600排他创建。root监管目录/回执保留root所有权，工作产物保留worker归属；审计仅固定白名单逐层FD不跟链接只读获取，不能恢复递归“归属回收”。改动仅探针、新6测试、readiness说明和进度。
- 定向 `PYTHONPATH=tests:. python3 -m unittest -v test_rsi_linux_cleanup test_rsi_linux_holdout_probe`：工作树 **11/11、0.014s、actual0**；476文件独立导出 **11/11、0.013s、actual0**；相同固定源服务器临时目录 `/tmp/webuddy-cleanup-L1-3DCTH4nG` **11/11、actual0**，源码前后一致，原5契约测试断言未动。目录遍历替换攻击挂在旧walk切入点，新代码不再触发该遍历；真实顶层路径替换则确实只收紧已打开原目录。
- Linux实际固定正常探针SHA `66fa011ffc742de5d2df23d781784a844960dd71e1a0ce27b75cd5feae8c6617`：实际tool0/监管0、16项全true、cleanup complete。另两个外置诊断变体：仅加worker文件/目录链接时tool0/监管0；加同样链接+输出后sleep30并把原监管期限20改为3时tool1/监管124、reason timeout，仍保留16项全true和完整清理。变体SHA分别 `1e0b04abc6747d9d72b1ad97e1c4921499a8b4734621f36079fe5e3813e8427b` / `33e72caa48f73001914391f10a5ac4e0602d6e7873477a3dedcba385d2eacc02`，不冒称三者源码相同。
- 三场合成夹具外root-owned目标内容/SHA/UID/GID/mode前后完全一致，18份原固定产物已按SHA/长度读回；监管进程组已不存在、宿主无fixture挂载。没有运行旧特权清理、没有在真实业务文件上重现攻击，没有任意root命令新服务入口。此验证仍为共享测试UID canary，专用生产隔离/真实试点未完成、实际评分null、付费0。

- 收尾只读核验：2026-10-25 **07:16:45 CST** 线上215运行文件逐SHA/长度/mode仍与6edc04f一致，active/running、PID2502485、重启0；三份原监管回执经原SP.read_receipt在原路径核验通过，超时原进程返回241单列。未重启服务、未改生产数据/配置、未启真实模型。

## 2026-10-25：可信供应方适配器最小增量

- 当前项：S1 受控 HTTP 适配与固定执行合同；状态：done（软件控制验证完成，独立复审和真实 profile/生产隔离待完成）。起点 88dd62f，工作区干净；不重复已封存的隔离探针或原 R1/R2 复验。只新增显式调用的软件模块，不接生产路由、Store 启动或自动任务。
- 范围：服务器私有 profile、固定端点/模型/参数/价格上界、同根预算预留及唯一意图、完整原始响应、真实监管器超时/取消和未知保留；使用回环假供应方验证，不计真实费用、RSI 收益或组织提效分。
- 待依赖：实际可信服务器 profile/价格与真实试点参与者尚未提供；沿用已有询问，不扫描凭据、不复制本机 AI 配置、不代替业务验收。专用生产 OS 身份和完整输入等价仍未完成。

- 实现：新增 `scripts/rsi/provider_adapter.py`、固定 `provider_transport.py`、38项真实回环HTTP测试及执行合同文档；原准备账本仅兼容增加v2绑定、原材料摘要、snapshot/unknown及提交意图前SQLite FULL持久性门。注册私有profile固定整个根合同/协议/端点/模型/保守单价/完整输入硬上限/参数和三份源码；缺项/不符零派发。唯一意图后固定子进程单次HTTP，无代理/跳转/重试/命令/模型工具执行，凭据仅匿名stdin。缓存普通/写/读计量合并，保留完整响应，结算仍是保守上界而非真实账单；`response_complete`不代表任务正确或人工验收。
- 异常：真实时钟监管全调用期限；取消/断线/错误/配置或凭据代际变化/源码变化均保留最大预留及unknown，不退款重发。恢复同字节profile也不能掩盖运行中更换；原回执晚结算不重新开根。原v1和33项准备/一致性回归保持，Store启动/215运行文件/六保护模块/原断言与MOVES未改。
- 原失败原样保留：首轮27项26通过/1error（测试主动关闭registry后清理重复close），修夹具动态清理；第二轮63/63、第三轮68/68。汇总命令误写 `test_rsi_linux_probe`，118项117通过/1模块加载error、actual1，不算产品通过；改为发现命令，未削弱断言。源副本/完整日志及持久合成DB在仓库外 `分析/RSI协调/provider-adapter-20261025/`，前三轮和错误命令日志不覆盖。
- 最终命令 `PYTHONPATH=tests:. python3 -m unittest discover -s tests -p 'test_rsi_*.py' -v`：工作树 **122/122、31.325s、actual0**；475文件独立导出 **122/122、31.121s、actual0**；同一475文件上传服务器0700临时目录 `/tmp/webuddy-provider-adapter-c8ZjPY2U`，非root合成配置/回环HTTP **122/122、48.918s、actual0**（远端驱动52.661s）。三处均0skip/失败/error，源前后摘要一致；旧local-eval HTTPError资源警告原样保留，不宣称全套零警告。没有重跑未变生产的2115项全量，也不将旧全量归属于新适配器。
- 稳定性：8个关键并发/原材料/撤销恢复/源码变化/取消/真实1.5秒超时/晚结算场景轮换10轮，**80/80、actual0**；未使用假时钟掩盖网络超时。三个外置源副本分别移除完整长度、材料重放、profile身份检查，**3/3准确命中断言失败**；故意红灯不是正常测试失败，原源未插入故障。官方API原文、每轮fixtures/日志/摘要均保留。
- 生产边界：新模块未接服务入口、未启任何付费或真实模型请求；专用broker/evaluator/候选身份和namespace最小通道合同见 `docs/design/provider-adapter-execution-contract-2026-10-25.md`，尚非生产隔离完成。人工采用/验收继续禁止自动代办；评分null、真实付费0。
- 新独立发现：旧Linux探针特权finally的递归chown有L1/P2链接越界风险；审查原红灯另保留，本增量未再次运行旧特权探针。将按窄修单独提交，不混入provider固定源码复验结论。

## 2026-10-25：c637准备层独立R1/R2修复

- 当前项：准备层局部一致性；状态：done（实现和定向通过，待独立复审关闭）。独立固定c637报告 `分析/independent-review/20261025-score-v2-and-S1S2-c6376be-review/review-S1S2.md` 确认两处P2，均需直接损坏合成SQLite，不是正常API越权或真实费用绕过。未把原71通过当反例无效。
- R1改由原create/consume事件及claims共同驱动同scope核验，不再只枚举可丢失的pool；原scope可证的其它项目仍独立。登记/原消费重放/终测预留及提交意图均复核，历史不安全重复投影拒绝派发，不自动修DB或伪报取消。R2把原settled锚/持久化receipt/自摘要核验提为共用纯读取，幂等结算返回前与统计相同拒绝矛盾；完整原重放和unknown晚结算保持。
- 新回归先在原c637核心字节得到 **6项/3通过/3断言失败/0error、actual1**，真实DB/合同/前后表/完整备份与原源码、日志均持久保留于仓库外 `分析/RSI协调/preparation-integrity-fix-20261025/red-fixtures/`。修后新增历史重复投影拒派发正负控，**7/7 actual0**；首轮备份夹具sqlite连接未显式关闭的资源警告保留并修夹具close，不抑制警告。最终 `python3 -m unittest discover -s tests -p 'test_rsi_trial*.py' -v` **32/32、0skip/失败/错误、unittest4.248s/外层4.361s、actual0**，日志SHA `3b401b76df919fbb0739a220d4ca690af162b50f7227b5a220fde3923c548e28`。
- 两份原独立诊断脚本逐字未改，在新外置candidate仅替换受测源码位置重放，六套持久DB观察全部符合修后预期；原脚本以“旧漏洞仍可复现”为成功条件，因此末尾旧漏洞断言各exit1，不冒称脚本exit0。新的正常回归32项真实exit0。原审查目录与反例DB不覆盖；不改旧断言、保护模块或生产运行文件。顺带将B/C选择澄清为终测判定、opaque ID描述澄清为首尾空白拒绝及精确字符串比较，不声称自动语义去重。

- 同类边界补强：自查发现create在pool丢失但原事件仍存时也可能返回新建成功（后续入口会拒绝，但不应确认重建）。新增持久回归先 **1项/1断言失败/actual1**；登记前核原events/attempts/claims，拒绝重建有历史的缺池，不自动补账。原红库及源码保留于 `preparation-integrity-fix-20261025/recreate-red-fixtures/`。修后完整一致性回归 **8/8 actual0**，最终相关及471文件隔离导出各 **84/84 actual0**；日志SHA `d93b0ad78342fe0672b6a7cc4e5ae1347810ab1d774dbbe400db4d8fa67b8920` / `d19cf370f4bd9bbec2fd3aba4ed37122c226d67490cea2318884cbd6d54f1f7c`，最终准备模块SHA `6bb28d8ab9074dafbe4d82960c2b2762b47330d6386dce15c111f7a3d09f6211`。不改Linux探针e502源码或原保护模块，不归因旧6ed全量；最后生产实测仍06:22:47的215文件/原服务状态。

## 2026-10-25：供应方能力与Linux身份隔离准备

- 当前项：真实provider能力取证/Linux隔离探针；状态：done（S1适配仍缺实际配置/可信价格；专用OS身份及生产入口仍todo）。开工HEAD c6376be、工作区干净；评分v2 SHA `a5b86ae9b289062d1b76bc41ee76f08304afaf4a08ccb70a7b8f4980f01548e7` 已核，叶项dependencies为空、gate_membership仅归属，无循环；共同标准于06:07:09经联合可实施性/独立review后冻结（记录SHA `f3a81e7ec868607b61bd1476ea8b5fb935ee136d97ac9ff2a71dc1672e1867c6`）；run/pilot未冻结，实际分null。模型测试人类授权已由原消息核实，先重读生产access记忆、0600/公钥指纹及StrictHostKeyChecking，不输出凭据。
- 只读SSH初查：生产6ed、active/running、原PID2502485、重启0；Linux具备unshare/setpriv/chroot/mount及不同UID65534、sudo可用。默认Claude设置/agents.json未找到，价表/实际模型/usage未验证，付费0。只导出公开别名/端点host及凭据存在布尔值，不导出密钥、配置原文或凭据摘要。第一版补查遇root目录PermissionError、实际exit1，原脚本/错误保留，修为记录权限状态；随后按既有服务器模型信息授权仅在服务器内白名单投影root常规设置，确认该路径不存在，不输出配置原文/密钥。
- 本批已实现可信系统工具的临时mount/PID/network namespace与不同UID正负控，复用原root权限监管器保证能回收所有测试进程；临时根目录只映射公开系统库、合成输入及受保护canary，不挂生产data/配置。nobody仅为现成测试身份，不冒充专用生产隔离账号；未有内核/清理证据不报通过。

- 最终实际Linux：固定源码 `e502363070aa2f37feef578e09a8c19cdb8586209d477efa5c3bc38fd9790724` 的16项内核正负控通过（真实UID1000/65534、公开输入可读、私有答案/宿主进程环境拒绝、cap/提权/继承fd/网络/只读挂载/工作目录）。外置故障注入为输出后睡30秒、原监管3秒超时，实际工具exit1/returncode124/status=failed且完整回收，原16项输出保留；这是预期负控，不冒称退出0。普通模式exit0；两个最终现场与旧原件均保留，未覆写任何旧探针。14份服务器白名单证据6009字节全部SHA/长度读回，清单SHA `9769e626daa1f9bfe9f21699e5f9d0fc663afdcc066fb2cd2c59603d57fc4967`。06:12:26 CST确认测试组均不存在、宿主无探针挂载，生产6ed/active/running/PID2502485/重启0。
- 最终相关组合 **83/83、零跳过/失败/错误、unittest4.466s、actual0**；471文件隔离定向导出再 **83/83、actual0**，两次外层共9.711s、受测源前后相同。完整日志SHA依次 `e4a49bd712487f53da26e4df80e49c353eb60216963451e54dfa20eea15a5066` / `6f47c32d37917ce4a177a062d1820342ff9b6b13bf45773073b1a32c2d56526b`。这不是全量生产发布包；既有mock HTTPError资源警告保持。仅新增显式工具/测试/说明，Store/215运行文件/六保护模块保持，不自动装任何表、不启生产入口、不付费。核验详情见 `docs/design/provider-and-isolation-readiness-2026-10-25.md`，机器证据在仓库外 `分析/RSI协调/provider-os-capabilities-20261025/`。

- 封存校验曾因测试后补入 `scripts/rsi/README.md` 使用说明而正确拒绝（仅1份非运行文档不符），原拒绝记录保留，未放宽来源绑定。重新从精确提交94176c6导出471文件，**83/83、actual0、外层8.871s**，日志SHA `2e18715d1e54d9ffeaff78625521d6a841e625d938edbe3cb65dea39dcd60aa9`，原包/原83结果保持。06:22:47 CST又从生产实际重读215运行文件的SHA/长度/模式全部匹配6ed固定清单，active/running、PID2502485、重启0；本批未重启服务。5aaf5e0一致性修复、94176c6内核工具均已普通推送并核ls-remote；本次仅补收尾记录，运行代码及471受测文件不变。

## 2026-10-25：S1/S2 事务与终测消费技术准备

- 当前项：S1/S2事务与消费技术准备；状态：done（真实模型适配与OS隔离仍todo，未开放运行入口）。开工HEAD ea564bf、工作区干净。评分v1 SHA `58b505be3c3d32eb19689292196ddca6fac79c2e8caa08df03a9511c8830d201` 与独立S1–S6意见已读；原v0/v1实施合同保持，另写v2消除B/C用于选择歧义。评分未冻结，未启动真实或付费试验。
- 独立可做的软件：在scripts/rsi中复用Store和learning.transaction，显式临时账本用于累计调用/token/金额预留、意图、未知与原回执；固定候选、跨预算终测输入一次消费。该组件不被Store启动初始化，无HTTP/模型派发/人工采用入口；不把数据库声明当真实模型计量或OS终测隔离。将做真实两解释器SQLite竞争、回滚/期限/未知/晚到/原监管进程负控，不改guard/锁/旧状态和已有测试。
- 变化与验证：新增 `scripts/rsi/trial_preparation.py`、v2预登记JSON/测试和实施合同v2；扩展原只读检查器支持v2，保留v1格式及14项原测试字节。根实验族统一预留、意图/未知/晚到结算、原锚及一次终测消费均在真实Store事务中；新进程代际不能接管旧派发。两对独立解释器竞争各仅一方成功，真实监管器完成、READY后取消及真实3秒超时/清理通过。S0/v2/准备组件及原local-eval组合 **71/71、零跳过/失败/错误，4.265s、actual0**；现有mock HTTPError资源警告保留。
- 隔离导出按现有验证包规则复制468文件，组合再次 **71/71、4.265s、外层4.675s、actual0**，受测源前后SHA保持，日志SHA `7b3e9a179fe3abef97d1c9925e171412774c63287fb1889565549b3dfaf8d1e1`。没有把新增32项当模型/组织收益；未改215运行文件/保护模块/Store启动/已有状态及旧断言，未重跑未变的全量，也未进行生产迁移/重启/付费。固定提交后普通推送并核运行文件一致。
- 原首轮准备测试19项，17通过/1failure/1error、actual1：竞争夹具将登记回执误计为新意图（元数据重放不是二次派发），监管夹具使用不存在的raw_output字段；修夹具为精确new_intent与既有output_bytes，原唯一意图/完整输出断言保持。完整原源码/日志保留，首轮自动清理的临时DB未保留，不宣称已有完整DB现场。后续新增删除claim/attempt与伪造取消反例，原锚必须拒绝；中间19/19、23/23及最终71日志全部保留于仓库外 `分析/RSI协调/cross-task-S1S2-20261025/`。
- 待依赖：真实provider响应/usage/价表证据、受强制限额的适配器、不同OS身份隔离及完整生产输入等价未具备；真实项目/人/周期/收益数值仍待预登记。技术准备不通过M/C/P分，不以声明补分。新运行候选须固定SHA独立review后验证发布。

## 2026-10-25：跨任务改进与多人持续试点

- 当前项：S0预登记准备；状态：done（实施/评分协议待独立审查，真实试点未启动）。已核独立review聊天真实人类优先级原文；复用learning_*、人工决定及handoffs，不重做已通过合成实验。基线3440d48，运行同6ed；开工git status干净，既有stash保持。实施合同见 `docs/design/cross-task-rsi-pilot-2026-10-25.md`；原v0合同/评分草案不改，协议尚未冻结，不计分或提醒80%。
- 首个增量仅只读预登记工具 `scripts/rsi/check_preregistration.py`、未填真人信息的JSON样板及最终14项定向测试。无网络、数据库、模型或生产业务写入；声明齐全也不授予执行或验证真实性。现有min_holdout=3保持，B/C两个家族至少三独立实例；成本unknown/同用户目录不能冒充费用硬门/终测隔离。
- 首轮定向 `python3 -m unittest discover -s tests -p test_rsi_preregistration.py -v`：13项，12通过、1断言失败、exit1；空格可伪装训练家族使声明错误通过。完整日志、测试、工具与样板原字节保留在仓库外 `分析/RSI协调/cross-task-v1-S0-20261025/`，日志SHA `2f455e4747f8db17d1c7a35ee507d8d2404f1c85591f0b721513ae5bc9c68130`。修复为拒绝前后空格，不改负控断言；首轮原件与失败不覆盖。
- 最终验证：同一命令 **14/14、零跳过/失败/错误、actual exit0，unittest0.208s**；按现有验证包选择规则导出独立临时目录再跑 **14/14、actual0**，避免JSON样板漏包。完整日志SHA分别 `be55a655f2d9af1a176f9da183a451f05a0b43eec803b4fa00d0d9fecc0ebaef` / `dca28dc31a622193a317716189fed8ffdf3e0183c99bc607d670492a073d4004`。工具与样板置于既有verification包含的scripts/rsi，不改已冻结发布器。真实样板CLI退出1、blocked、零格式错误，execution_authorized/evidence_verified均false，score=null，输出及文件SHA已读回。仅新工具/新测试/设计文档，不改运行源码或旧测试，未重复运行未变的2115项全量；215现役运行文件将于提交后核对，GitHub普通推送，不为准备工具重启服务。
- 后续依赖：真实项目及至少两名不同职责参与者、托管人、本人确认、A/B/C/D来源、业务验收人、两个以上周期/基线/目标尚缺；Agent不填假人/不代签。S1需要可核的模型身份、usage/价格上界和累计调用/token/费用/期限硬门；未具备不派发付费调用。评分/具体试验协议由协调/独立review先固定，S0不作替代。建议预算24调用/100000token/1000秒/人民币10元仅待审上限，实际支出0。

## 2026-10-24：RSI-2 固定 A 合成实验闭环

- 当前项：RSI-2；状态：**done，2026-10-25 03:15:12 CST 已上线6edc04f，GitHub当前分支普通快进一致**。独立最终复审R1–R4均关闭，03:56:23封存验证passed；根逐文件复核独立最终清单1275份，SHA `57877e55ae5b7f8bb49883e86bfba64bc233d2ffcd3fe0ecd4225df5f556b8d3`。下方阶段性“等待/未发布”文字按当时事实保留，不代表当前状态。
- 发布与收尾：03:34:57延迟18/18公网及回环检查，03:35:21最终active/running、重启0、error级日志0、215运行文件与精确提交相同；03:31:14 Mac独立TLS4项通过。完整1781个data成员与三项目277/37/20成员备份读回保持，56业务/11控制表原行及结构保持，仅新增四张空实验表。15份服务器白名单证据340965字节全部重读SHA/长度一致，清单SHA `04f7efd786c955652a3374de2edff681256cf2b976c0634b44a2471d4e2e30ac`。详情见 `audit/production-deployment-2026-10-25-learning-experiments.md`；本次收尾仅提交进度/发布记录，不重启服务，运行文件与生产候选再次核对。
- 待确认/能力边界：没有需要用户回复的当前发布阻塞。外部Claude/Cursor完整执行合同、跨工作包汇合、真实独立终测、跨任务改进效果与多人长期组织收益仍须验证；Windows凭据ACL/POSIX网关限制未解决。不能把本批合成机制通过率当作组织提效完成度。既有stash不应用、不删除。
- 6ed正式验证：Mac **2115项/20可选跳过/零失败错误、外层553.555s、exit0**；官方MCP1.30.0 SDK **74/74、零跳过、18.129s、外层23.759s、exit0**。第二次Linux **2115项/18可选跳过/零失败错误、full外层888.971s、验证器整进程892.214s、真实wait退出0**；100项HTTP及指定gateway/两worker/socket/key回收通过。465验证/215运行文件保持；Mac/Linux/SDK完整日志SHA依次 `19166428e3064dbced7cb6adb7e0872de2481faeace4cf3d9df94adfa652ff8c`、`d09b4394159c7ecdfa5dc37f486599ba3e907b32956ee6904bcc11da5b36ce4a`、`d68f494d9bb2f5ff90f30dc6fa4836448a468741af0875dd460e10a4b804d0e2`。资源警告保留，不宣称全量零泄漏。
- Linux首次SSH在17:27:56中断，实际客户端exit255；远端full/smoke报告0（2115/18skip、902.385s），但原验证器整进程退出码未独立记录，**不将成功报告推断为wrapper退出0**。原verification目录2277成员原子保留为 `verification-attempt-1-ssh-reset`，清单前后相同；原SSH日志未覆盖，首轮只读下载8份记录45秒超时保留。重新使用同一固定归档、465源/mode及5个离线wheel，不改13脚本/断言/1000秒full和90秒smoke期限。仓库外detached supervisor保存真实wait退出码；1150秒外层超时会记失败并先SIGINT触发原清理，残留须另核，不伪报清完。第二次8份回执12148字节完整读回，清单SHA `3191ebadadffff70810d3a7e862c038b0d74d2af585c25052894db01c3243c66`。
- 6ed迁移演练：1781成员完整私有副本，56业务/11控制表原行与原结构保持，仅新增四张空实验表，3项目31卡原文可读；真实六槽合成调用、输入回执、来源绑定及进程清理通过，零付费/模型/生产业务请求。22:34:25 CST正式发布门通过，源Git/归档/实际文件一致，真实六槽/四表/100HTTP/清理均核验；门报告位于仓库外 `部署包/learning-experiments-20261024/candidate-6edc04f/prepublish-gate-20261024T143354Z-d356cc76/`。原独立审查仍在复验，不把局部关闭当最终通过。
- 领导者审查结论：适合有人协调兜底的辅助试点，尚不可托管多执行端交付或承诺组织ROI。已有授权固定知识、派生隔离、阶段多前置、交接/等待/质量与人工动作统计；缺外部执行合同、跨工作包汇合、完整确认条款覆盖、知识领域责任/冲突治理和全团队实际投入成本。个人工具消息不会推送或唤醒Claude/Cursor。17:06只读生产快照中协作/交付覆盖/交接/知识引用相关表0行，旧工单和运行历史存在，故缺该协作链路真实使用证据。完整报告在仓库外 `分析/组织提效对抗审查-20261024-最终.md`；合成机制通过不等于真实RSI/模型质量/组织收益。
- 2d4568d精确全量：Mac **2091项/20可选跳过/0失败错误、外层543.133s、exit0**；Linux **2091项/18可选跳过/0失败错误、893.470s、外层exit0**；两端462验证文件保持。完整日志SHA分别 `6a10f7dcdf16300839f10408cd74e02a390fec4288fdd32bf2da20eb46163d48`、`830852824220a95366182d28519e9b9d420bd5fb58a636b3e97e05c8cafbbe1e`，资源警告保留。Linux七份完整记录69169字节已读回，清单SHA `c36dc977717a4324638718cfdf21338e65398e15bbfc988575d3431513f16d41`；合成gateway/两worker/socket/key清理通过。没有为被阻断候选运行SDK或发布门，也没有push/激活。
- 独立第十一轮新反例（固定dc35，产品树与2d相同）：**R-1/P1**正常capture→propose→先封子修订再封父修订可取得第二套六槽预算；**R-2/P2**直接改三张表删除未曝光资产并重算当前合同/摘要/任务marker，原create/seal锚不动，四类读取仍成功；**R-3/P2**人为重建表移除请求UNIQUE、补同列WHERE 0假唯一索引仍被schema_state接受；**R-4/P2**发布合成报告loaded_sources摘要改全零，实际activate调用参数未传可信来源清单仍接受。后两类数据反例不等于正常API越权，R-4不证明线上执行了错误源码。原报告、探针、红灯和合成现场完整保留于仓库外 `分析/independent-review/20261024-162103-dc35e9b-rsi2-review/`。分别补预算准入双向谱系（不改变历史归属）、只读原准备锚、真实PK/非partial唯一约束及发布来源绑定；修后另起提交并重新冻结验证。
- R-1/2/3窄修已整合：修改 `learning_experiments.py`、`learning_runs.py`、`learning_experiment_views.py`，新增budget/schema/view_integrity三测试文件，补两份功能说明。原DDL、六个保护模块及全部已有测试字节保持。新预算检查在writer事务内对称拒绝显式祖先/后代；旧terminal回执、兄弟修订、历史归属保持，遗留不安全queued只拒派发不伪报取消。读取先核唯一create/seal独立锚，草稿取消与合法曝光正控保持。后端95/95、读取73/73，实际退出0；各自精确旧字节红灯、首轮新增夹具错误及全部现场保留。两方向预算竞争实际使用两个独立解释器/Store连接，仅一个六槽计划、两进程wait回收；双方静态交叉审查未见新阻断。
- 根最终整合验收：实仓14模块 **195/195、0skip/失败/错误、实际exit0、外层28.182s**，319 Python源前后不变；完整日志SHA `4d98ec77a700e2fa146d45cc5c4821d4277164231e8c10bedfc7cb06dd600c83`。原独立事务/视图探针仅适配源码/清单位置，分别 **8/8、39/39、actual0**；未修改断言，摘要保留原脚本硬编码dc35标签，实际受测根路径和源码SHA单独绑定，不能把标签当候选提交证据。首次事务复跑缺旧脚本要求的同级manifest，未开始场景即失败，完整日志保留；适配位置后通过。全量发现 **2115项、0加载错误**，尚待新提交精确双端验证。
- R-4仓库外工具已补强：checker强制独立root/commit/files；rehearse派发前及结束核实际加载源码，activate/激活前检查/postcheck从配置固定归档与RELEASE取清单，prepublish保留原Git清单校验。原真实六槽正常control通过、全零来源旧错放行新拒绝；完整 **13命令/146项、0skip、actual0、16.086s**，464产品源与43工具前后保持，32 PID/10socket-key已回收。新工具冻结SHA `1f3e39e4ac37d8a71056ddae6d168b1e5558ac2e1671b5624d7e3dbb08461267`，旧冻结/旧候选原件保持。本工具结果不替代正式迁移/全量/SDK与发布门。
- 范围：固定候选、三族双臂合成任务、封存资产、总调用/期限、串行登记派发、明确取消/未知/恢复、身份与托管投影；真实个人创建/封存/启动，工具无权替人采用。仅server-owned本地固定执行器，真实模型与付费关闭。合成结果明确mechanism_only、独立真实来源0，不混入交付统计或宣称组织收益。
- 静态对抗修复：末槽来源变更、接管前崩溃丢owner/fence、最终材料检查耗尽原期限、活动manual谱系与seal竞争、缺候选资产降级manual；后端最终7模块 **137/137、零跳过/失败/错误、71.183s、实际exit0**，7owned源码前后SHA保持。三类缺资产真红、原四问题中三类真红及单点移除最终期限复核的真实30s红灯保留；旧无最终材料屏障的deadline试验不冒称因果证据。
- 读取与UI正在验证：受管详情在旧live读取前分流；普通兄弟修订仍保留原评审/修订/采用入口，相关受管历史单独投影。只按原卡搜索，候选私词不得形成查询旁路。未知POST重试绑定原身份/epoch/请求及原正文，成功回执后只GET刷新；真实LR修订编号不得被错误hex校验拒绝。新前端/HTTP/根事务验收尚待。
- 根验收发现并修复非 Git 新租户登记误拒：原 binding 总是启动 Git，触发租户原宿主进程 audit 后误报来源变化。现先保守检查当前/祖先 Git 标记及裸库，确定普通目录才保留文件清单绑定；实际 Git、嵌套/裸库仍核对真实 HEAD，损坏、不可读或悬空标记拒绝，不改 audit。独立临时实库红灯 7 项中 3 个预期断言失败，修复后相关 9/9；原首轮网关失败仅保留日志，不能声称已保留其数据库现场。后续重新复现已保留完整合成现场。
- 最终根组合：外置 `root-validation/run.py` 实际执行事务/采用/真实签名网关/来源绑定/租户运行与策略/原知识流程/新 API/DTO/新旧 UI 共 11 模块 **151/151，0 跳过/失败/错误，实际退出 0，外层 14.867s**；314 个 Python 源码哈希前后不变。完整日志 SHA `333f5690d4d54c41bc219a341a16cbac71b6dec97bc378529a46758d33e8364c`。上一轮 107 通过加 1 loader error 是外置包装器缺 source/tests 导入路径，保留日志并修正包装器，未改原断言。
- 真实网关覆盖：个人创建/重放/封存/启动六个真实固定子进程、18 条 reserve/intent/settle 事件均绑定真实 owner；六槽完整回执、prompt SHA、清理和零预留通过。工具冒用 owner 显示名仍无全文，跨租户 404，新租户可登记但执行 403；通用运行写入口拒绝。网关关闭后被追踪 worker、socket 和 key 均回收。没有宣称已验证真实 HTTP worker 重启恢复。
- 客户端定向：DTO 20、实际 JS 22、API 17、原 UI 22 共 **81/81，6.424s，0 跳过/失败/错误**；真实 LR 编号与未知请求 8 项反例保留。当前开始真实浏览器桌面/390px、角色投影与丢响应重试验证，期间其它测试串行等待。
- 真实浏览器续查：管理者实际 create→seal→start 六槽达到 mechanism_passed，390px 无横向溢出；提交后故意丢回包、刷新后保留原请求。普通项目成员经组织“知识与记忆”入口被既有 /api/memory 管理员门拒绝，错误现场保留。该总目录尚未项目权限过滤，不能放宽；本轮补当前已授权项目详情的“分类与评审”直达链接，继续核验角色投影、原请求重放和清理。尚未把这些中间观察记为最终 UI 验收完成。
- 最终 UI：补项目页“分类与评审”直达和成功回读提示；新增4项先得到3个预期断言红灯，修后新旧组合 **69/69、0跳过/失败/错误，实际exit0**，原22方法AST保持。最终正常浏览器项目入口、六个真实合成子进程、390px与权限投影通过；丢响应后原号原正文重放、总计仍2实验。root已亲开最终三张原图并读回服务端证明；fixture/worker/六子进程均清理，端口/socket/key回收、源码SHA保持。证据清单SHA `986b30657a16809df85ac9c4e95d06e40ee0bc71de57ee8e8afd71a83f841a91`。
- 发布工具对抗补强：原检查仅比较报告自称expected，缺固定oracle与任务槽交叉绑定。保留原工具字节并实际证明4类错放行，新工具4类拒绝且正常正控保持；完整工具验证仍进行。Registry合成夹具45应用表另含sqlite_sequence，前两轮计数失败保留，生产56业务/11控制门槛保持，不将工具夹具误配称产品缺陷。
- 精确 dc35e9b 首轮双端全量否决：Mac **2082项、20skip、2failure/74error（含子例）、574.915s、exit1**，461文件保持、日志SHA `853d1ebc53e323c3adb98f90a61fdf18ef6ed94cd8bc481662cf99e8f3da4756`；Linux **2082项、18skip、1failure/75error（含子例）、894.362s、外层exit1**，461文件保持、日志SHA `5de5e5bf3f69ee700d6e529919237ae9fe16ba0ada8ccbb72f1d72127a3a124c`。原失败/临时现场保持，Linux4份完整记录220421字节已读回；没有push/SDK冒称/激活。
- 三类测试兼容窄修：预览URL原端口数字误撞完整Git SHA，保留完整URL/path断言，改核真实scheme/authority/port并加四固定正反控，旧语义正控准确红、修后15/15；旧知识API mock未登记job，补真实行、原19方法断言AST保持，加真实登记与缺行404，组合40/40；tool leaf夹具补完整身份与重入授权上下文，原99断言及旧测试方法保持。只读检查仅补index_list/index_info元数据，不泛开PRAGMA，并用四类真正写入证明仍拒绝；初始化前预载搜索代码，仍禁业务写文件/进程/网络。最终tool/history/真实gateway/DTO **57/57，0skip，exit0，14.844s**，日志SHA `e041ed23cd0990d06e4f2055b673eb758cce8ac2c181e44d355934ad4a7bd812`。中间55失败、57中1个新增夹具字典行取值error均保留，不改产品代码。
- Linux父进程夹具端口发布已窄修：原traceback确读到空串，远端17成员现场仍保留（复制时port已5字节），不能声称原空字节被保存。新socketpair屏障对精确旧server()确定1个断言红灯、0error，实际保存写入前空目标；写完同目录port.tmp再replace后通过。只改共享_GATEWAY发布，不改原类/函数、5秒等待、真实父丢失/锁/三代回收断言。提前注册socket清理覆盖Popen失败；根最终源码10轮屏障+原5项 **15/15、0skip、5.071s、实际exit0**，13源码保持、30跟踪PID不运行、25临时路径移除。证据 `分析/RSI协调/rsi2-implementation-9947f2a/port-publication-compatibility/root-final-r3/`；发现 **2091项、0加载错误**。产品源码不变，独立提交测试修复后重新精确双端全量，不沿用dc35失败包。
- 合理边界：四张新实验表将单独验证迁移；旧56业务表及11控制表全部原值/schema保持。新租户无OS执行隔离仍不能启动；允许登记不能冒称允许执行。Windows/POSIX网关、真实终测隔离、成本/token计量和生产输入同构尚未解决，不能以合成实验替代。待确认：无需要用户回复的当前阻塞。


## 2026-10-24：RSI-1 完整知识输入与运行回执

- **最终状态：done，15:08:41 CST已上线3705caa，GitHub普通快进SHA一致。** 15:10:33启动约111秒后18/18公网与回环检查通过；15:11:22最终active/running、PID2230139、重启0、error级日志0、210运行文件一致；15:11:47本机独立TLS4项通过。完整备份 `/opt/webuddy/backups/pre-3705caa944fd-20261024T070839Z` 的1781 data成员及三项目277/37/20成员读回保持，56业务/11控制表、配置与其它服务保持。14份报告196333字节逐文件重读SHA相同，清单SHA `ac33f22a0cbea6778e114a0eab0bd75eedddb17ab777d91bd8da2b36bbe22d66`。详情见 `audit/production-deployment-2026-10-24-lesson-input.md`；下方待发布文字为历史阶段记录。RSI-2仅外置草稿继续，未随本批上线。

- 精确候选3705发布门已通过（15:06:57 CST），GitHub普通快进到 `3705caa944fd93549b5f735165df3b3d4c823bda`；生产激活尚待。Mac **1945项/1925通过/20可选跳过/0失败错误**，612.005s、实际exit0；Linux **1945项/1927通过/18可选跳过/0失败错误**，801.132s、实际exit0；两端445验证文件保持。官方MCP1.30.0五模块 **74/74、零跳过、21.604s**，实际exit0、精确归档模块及源码保持。完整日志SHA依次 `5b75d7cbba5e31d3a8c7dc9fb3671a3f738ad1043371465cfab2dbcb79d73347`、`2bfe71b703312d0c8b4dffe1d3087ef59c78fbd02a5fbfd31defd37189e9ac3b`、`9a98c9e5685f2c56840a7f904d4f047369f0c67ee7b91623aef8d3e9f5dbc7e9`，原资源警告保留。
- 第九轮独立复审关闭options独改P2：三类真实SQLite篡改基线各6次stub调用、候选0次，实际worker在create_run前拒绝；独立两进程同请求仅一次登记/预留。身份事务6/6、兼容38/38、来源字段1/1，未新增阻断；不是付费RSI或组织收益实证。报告在仓库外 `分析/independent-review/20261024-145108-3705caa-pool-capture-review/review.md`。
- 发布门核验210运行/445验证Git正文与模式、100合成HTTP、私有完整副本56业务+11控制表原值/schema保持、31卡兼容、capture证明及已跟踪gateway/两worker/socket/key回收。切换前只读确认现役仍e226、PID2116573、账本/DB与演练一致；尚未代人确认或执行生产业务。原563 CLI故障仍根因未知，本次通过不追认已修。

- 独立封存修复已完成定向，尚未发布：原登记事务在 binding 中封存完整 evaluation 与8项任务身份；current/execute/resume从DB重读，比对完整池/顺序/统计，options独改后重算hash拒绝，0回调。新旧降级由独立修订内容协议约束，真旧passed人工采用正控保持；不防御同时重写整个数据库的管理员。没有DDL或旧历史补封，来源字段仅剥离保留capture键，其余仍逐项核对。
- 根最终联合11模块/单例 **185/185、31.296s、0跳过/失败/错误、实际exit0**，6源码SHA前后不变，日志 `分析/RSI协调/rsi1-pool-capture-20261024/root-final/targeted.log` SHA `d2da04dafbd7a90ce1f5ebbf0bee1099e05f4c3df8df9d47c4cc0ee486a4cbfa`。包含原bounded CLI真实1秒断言，这次通过不倒补563原失败根因。独立两Store同请求竞争仅一capture/三case预留、真旧历史D采用及Agent403正控共51/51（11.134s）；此前132/132及所有红灯/完整源副本保留。旧128断言数量保持，127 AST原样，1处仅正式登记fixture替换。
- 发布工具同步独立capture证明，12/12合成账本自检通过；首次35门测试3error是合成fixture缺新capture摘要，原失败保留，补齐fixture并新增缺摘要拒绝正反对照后 **36/36**。三道门都要求capture协议/完整封存/重算options拒绝/降级拒绝/原封存保持。没有放宽原门；这些工具自检不替代后续精确候选双端全量/SDK。RSI-2仍只在仓库外草稿，不混入本次候选。

- 563精确Linux全量完成：1933项/1915通过/18可选MCP跳过/零失败错误，780.405s、外层实际exit0、443文件保持，完整日志SHA `9481290aa8919f549663e234fa9264e586bd0de811234188575d84ada0117328`；smoke退出0，已跟踪gateway/两worker退出、socket/key移除。7份白名单报告及完整日志68973字节已独立读回SHA一致，manifest SHA `4a161c2682a7ee673f0601340d5d100ac74aeb050ac7bad994869945fd740f4c`。此结果不能抵消Mac失败与冻结池P2，不运行563发布门/激活，不补造SDK通过。

- 563精确Mac全量拒绝发布：1933项 /1912通过/20可选跳过/1failure/0error，744.012s、实际exit1、443文件保持；原bounded CLI测试实测1.375176秒超过原1秒断言，现场仅traceback，未保留当时子进程分段时序，根因未知。完整日志SHA `14de8989a6f725c5b1a50a141739b28dac29d9936f1b3d08f9771bae7c03d00e`。随后5a4/563交替10对原断言全通过，五个相关源码SHA完全相同；基线CLI中位.239s、当前.222s，不能据此声称原故障已修。诊断完整请求/响应和阶段时间保存在仓库外 `分析/RSI协调/bounded-cli-20261024/`，汇总SHA `fcf8a264d1eaa235ace7e8063bca523e3d93d683918c8ddcc4367a9aa2c46fae`。不放宽时限或修改原断言；Linux继续原精确验证。
- 新独立P2阻断：仅改持久job.options的pool成员/顺序/冻结stats并重算内部hash仍可改变实际干预。正常API会覆盖传入evaluation，未证明公开API越权；问题限options独立被改写时缺外部可信锚定。正在原job事务内以binding独立封存完整evaluation和任务身份，执行/current从DB重读封存；不从今天pool重建，不自动追认旧无封存任务，保留原完整失败材料和旧合法terminal人工证据。563尚未push/激活，生产仍e226。RSI-2仅仓库外草稿，不能混入本次候选。

- 中文展示兼容修复完成：唯一完整JSON后增加同源五字段中文阅读索引，原文/缺键/null/公开范围不变；renderer显式v3，旧v2回执不能冒充，索引纳入完整prompt哈希/字节预算。新增5项对9947原renderer全部准确断言红灯，无error；首次87项组合86通过、platform在目标断言前HTTP502夹具error原样保留，显式回环不走代理后原单例完整通过。根最终9模块/单例联合 **101/101、15.739s、0skip、实际exit0**，源码SHA保持，日志SHA `6db2c612199864415eab6edfb4030c6b0a88f26c2164f490b10bae33358f288b`。原platform文件/断言不改；发布INPUT_CONTRACT同步v3，12项合成发布账本检查全部通过。独立静态复核无新增阻断，1933项发现无加载错误；下一精确提交双端全量/SDK仍待，不沿用失败9947结果。TERM测试已单独提交 `b28882a`。
- TERM夹具窄修完成：仅第二子进程改用/bin/sh内建trap/printf，原0.25秒期限/0.3秒grace、全部78个原断言保持，新增ready/124/底层0/TERM四断言。真实FIFO两版本held/released共8情景符合预登记4红/4绿；相关5模块65/65（42.482s、0skip），单例20轮/40子进程全部清理，原启动期限覆盖仍通过。过程总120子进程已回收，不能将10个预期红灯称全绿。根已逐读报告/diff并核验process_control/supervised/filelock/acceptance/guard字节不变；独立现场报告SHA `32226551c3e2e02bbadfcdb7e6973be0700c20a1afe35d89ee5f8c2bd2a4b2ff`。单独提交测试修复，不把它当产品超时实现修复；新候选全量仍待。
- Linux正式全量同样拒绝9947：**1928项 / 1909通过 / 18可选跳过 / 1 failure / 0 errors**，770.157秒、实际退出1、442验证文件不变，日志SHA `a12420f62a36d899fee791f348942581fb533bf62de94de7b7f5f8e4be588c18`；失败为同一中文根因展示，未进入smoke/激活。Mac进程测试单独调查：原5a4/current源码相同、交替20次原例通过；真实Python启动前0.4秒延迟使两版本各3次准确失败（TERM约.251秒、-15、空输出、已清理），证明夹具存在安装handler前被杀窗口，不能倒补原全量缺失的具体ProcessResult。正在以原生shell内建handler保留原.25/.3真实时限和全部原断言，另补正控，不改产品监管。
- 正式Mac全量已结束：候选9947，**1928项 / 1906通过 / 20可选跳过 / 2 failures / 0 errors**，外层577.637秒、实际退出1、442验证文件不变；完整日志SHA `b78d4bf16cb8beacee731afa4de52e9814863389e34cbf58a583c5321eae0def`。失败分别是原platform提示词中文根因展示兼容、process_control原0.25秒TERM处理输出为空；保留两个现场，后者目前只有traceback而无完整ProcessResult，不能据此判定根因。正在修复并补充确定性反例，不发布此失败候选；Linux仍完成原精确验证。
- 精确候选 `9947f2aaca779bca3abda50b64bb3bf5887287f8` 已提交，尚未推送/切换。210运行文件、442验证文件、1928项；stage/rehearse实际退出0，1781成员私有副本、原56+11表/31卡兼容和合成v2证明通过。Mac/Linux精确全量进行中；Mac结束前不并行本机测试/构建，独立审查限只读。下批RSI-2仅在仓库外9947归档副本准备，不能与当前候选证据混用。
- 当前项：RSI-1；状态：**doing**。开工 `5a4caa8538415a79009d2c66bcf27a20d6b589a5` 工作区干净；F2-1已上线e226、文档5a4已普通推送，207运行文件Git blob/模式一致。已读进度、git log、AGENTS及两份接口契约。
- 范围：实际运行与手工经验评测共用唯一无损selector/renderer，完整冻结字段/条件/附件及实际知识块回执；只读公开视图不回填私卡。保留原500池、1500/3000检索窗口、排序/资格过滤后不补位、原holdout和人工采用语义。
- 合理决定：最终answer-only评测prompt默认上限65536 UTF-8字节，双臂任一超限整对not_executed，完整输入/失败/分母保留，不截断。旧v1待运行/恢复明确input_schema_expired并转既有stale释放活跃位；已结束旧人工结果按原有效性保留合法采用，并标明legacy/manual作用域，不授RSI资格。
- 兼容：新lesson_content_schema=v2保留合法缺键/null/空串，新旧fingerprint/投影解释显式分支；旧revision/id/账本不重写。生产知识块相同不等于plan/fix与answer-only最终prompt同构；不改plan/fix语义或用手工评测冒充RSI收益。
- 分工：client负责lesson_input.py/learn.py与新selector/renderer测试；backend负责learning.py/learning_eval.py/learning_runs.py与新冻结/恢复测试；根负责learning_decisions.py、agents.py真实注入/会话失效及集成；独立代理只读对抗复核。
- 实施红灯：根在5a4归档执行最初8项新增运行用例，9个断言失败、零error；证明正文截断、普通经验撤回不失效、回执写失败被吞等旧行为，完整日志SHA `dff8d6cac79e64f9ac19cc920696ad8a40c9caddfb5575e650d6ffbac26aaba1`。client原11项2fail/9error，其中error含尚未实现接口，不把它们都称为既有产品漏洞。backend原4项明确复现超限仍调用、候选未被选中仍强制注入。
- 根定向：r4 **61/61、17.103s**；修复固定交付误拒后r5 **82/82、28.183s**，真实退出0。完整日志分别SHA `f0287245f3a560cc66ae7b74e5b22330a99c83e46e30659099d186efddae2e09`、`c8948c6751e39d8fc8c586bf22082339e15fd076e5f3dc9293db8d38ddab94b8`，保存在仓库外 `分析/RSI协调/rsi1-runtime-20261024/`。后续公开窗口窄修及最终冻结仍待新验证，不能用这两轮替代最终全量。
- 独审红绿：实际模板替换会误改知识块内字面 `{workdir}`、only-policy sidecar会掩盖缺经验回执，均增加真实输入/会话反例后修复。新末尾current在固定工作树已清理后误拒，两个原真实交付基线准确红灯；移至模型返回后、finally清理前，原断言不变且14项独立窄复验全绿。render/binding两阶段独立Python均无法取同账本内核锁，捕获后可取；3子进程已退出。
- 继续收敛：独审指出冻结输入不能只依赖自身hash，必须从固定pool/真实revision/selector重建；未知协议不得冒称v2，malformed明确失效。另新卡挤出100000发现窗不应使已冻结公开卡误拒，初始发现窗口保持，只对已指定ID重核原公开投影/权限；client合成100001材料和根实际冻结回执反例均先红。修复与最终独立复核进行中。
- 历史测试适配仅 `test_learning_sessions.py` 夹具显式传v2 schema并附实际块，全部原断言保持；第一次4项夹具失败原日志保留。不改原进程时限、人工权限、guard、MOVES或锁实现。新增说明 `docs/lesson-input-contract.md` 明确平台提交不等于模型理解、手工评测不等于RSI收益。
- 冻结定向：client **171/171、12.100s**（25新测试），backend **113/113、24.264s**（27新测试），root运行回执 **14/14、1.332s**；后端独审15/15包含重算hash错绑、缺失/外链/替换inode的只读锁检查。单ID lookup仅去发现窗口上限，保持原坏尾行旧机器投影兼容；第一次错误使用严格reader导致基线失败已保留。r6一处共享目录mock影响take返回的夹具error也保留，不将其冒称真实窗口漏洞。
- **尚未发布：最终联合320项 /60.995s，1 failure、0 error**。原 `test_handwork_lifecycle.test_review_shares_time_spent_on_baseline_and_candidate_checks` 第131行未看到review-ready，已超3秒真实共享预算；14个产品/测试文件SHA全程相同，完整日志SHA `b26e89c550d4b7382244c2850cf36048895b6950466fdbf78d768bba65452e74`。正在隔离保存run/lifecycle/attempts并对比5a4与本批，不放宽超时或断言，也不以重跑通过代替根因。
- 发布准备仅就绪：仓库外 `部署包/lesson-input-20261024/` 继承原流程，101项工具自检、100回环HTTP、4类特定清理通过；新v2合成证明接入三道门，原full/SDK/56+11表/备份/60秒门保持，不能当本批产品验证。2026-10-24 13:22:23 CST 严格SSH只读核对仍e226671、56业务/11控制表完整，无活动运行、自动流转关闭、sudo有效；未切换服务或写业务。当前发现1925项、loader errors=0，仍待精确提交全量。
- 最后锁读窄修：普通运行回执原先仅检查锁路径存在，外部删除/替换后可继续复用旧fd。三个确定性文件屏障在原实现均断言失败，现核对进入/返回时路径及实际持fd的dev/inode；不改原锁实现。正常新锁和未变重入正控保持。runtime17+selector14共 **31/31、1.022s、0跳过**；原红灯SHA `d76988bc1da41d1ef01f5d0dfb88a401fec850b1da006516df9a94966c355d2a`。此为外部文件操作边界，未声称普通writer会自发换锁，独立5/5含真实子进程换锁并退役卡片，父持旧fd时正确拒绝；子进程已回收，源SHA保持。仍待新冻结联合验证。
- 3秒现场调查：基线/current交替11对共22次原断言通过，原handwork类各5项通过；诊断准备中位当前12.6ms、基线10.5ms，未重现预算耗尽。修正仓库外诊断器spawn入口后原同序320项全部通过、60.979s、172源SHA保持。第一次坏诊断器2fail/12error保留，不作产品结论。原失败日志13:20:00–13:21:02与发布工具自检13:20:08–13:20:32活动重叠，但缺原用例独立时间戳及临时现场，不能证明因果；原故障根因仍未知，不称已修，不改时钟、预算或断言。正式精确全量将不与其它测试负载并行。
- 故障留存补强：`test_handwork_lifecycle.setUp` 仅暴露原 `f.temp` 为 `self.temp`，让既有全量失败收集器在原清理前复制真实现场；不更改执行、清理、断言或3秒预算。另8个新用例的POSIX限制只对应原平台不支持的人工写入/独立进程监管或持fd换锁，其余新测试继续跨平台执行。
- 最终根联合：原19模块加锁边界3项，**323/323、51.618s、0跳过**，实际退出0，所有变更文件SHA前后保持；完整日志SHA `fafdf79ffe418929b65506e0630e07d8e83a7db78939404f3febeaaf46707365`，仓库外 `分析/RSI协调/rsi1-runtime-20261024/final-323/`。61个原会话断言AST、acceptance/guard/filelock/supervised_process/Store字节不变，diff检查通过。现场留存单独提交 `74c1ea9`，不声称修复3秒故障。当前发现 **1928项、loader errors=0**，随后精确提交双端全量与SDK；尚未推送/激活。
- 待确认：无须用户回答的当前阻塞。真实付费RSI试点在累计预算/可信成本上限/独立留出与完整生产输入合同就绪前保持关闭，接续RSI-2。

## 2026-10-24：F2-1 经验人工决定绑定完整版本

- 最终证据封存：14份服务器白名单报告/完整日志，共192677字节，collector实际退出0；根逐文件重新核对SHA/长度一致。readback-manifest SHA `5103ce360e477fcc5ae85f5467dda3bae9aac04f30655ac9182b5b9791a5b1e8`。没有下载业务备份或密钥。
- 最终状态：实现提交 `e22667130845736a9350741c96fa14f00b57a4df` 已普通推送 GitHub，ls-remote 完整一致，生产已激活。以下过程中的“待验证/未推送”仅为历史，最终结果以本段和 `audit/production-deployment-2026-10-24-lessons.md` 为准。
- 精确双端全量与SDK：Mac **1859项 / 1839通过 / 20可选跳过 / 0失败错误**，558.349s；Linux **1859项 / 1841通过 / 18可选MCP跳过 / 0失败错误**，754.994s；官方MCP1.30.0五模块 **74/74，零跳过**，19.007s。各外层实际退出0，434验证文件字节/模式保持。完整日志SHA依次 `4f96b562966723912f152738135fec74b6a4df2c2e6eda4a9d9f43a51439164a`、`1eb8e106f3b4fbc57210963492437d0b90fdceb623d4dd9768eb741500f76874`、`3a78b357c0f4e4807fd9bff4ce0d78bf724eefa10db1cd08fdcf8fe9ddcd6454`；警告原文保持。
- 同源验证：207运行文件/434验证文件、100唯一语义HTTP、3项目31张旧卡、1781成员私有完整副本两轮兼容、跟踪进程/socket/key清理，实际发布门与两路独立复核一致。第六轮独立审查 F2-1 在此范围内无新增阻断；不是全平台组织收益验证。
- 实际切换：切换前再次核对现役01290b8、56业务/11控制表和账本与演练相同；完整备份 `/opt/webuddy/backups/pre-e22667130845-20261024T044707Z`，1781个data成员及三项目277/37/20成员逐字节读回。原表/schema、经验账本、项目文件、配置、Caddy及另一应用保持，没有生产个人会话或业务签字。
- 上线健康：12:48:32 CST（启动约83秒后）18/18公网与回环检查；12:48:47最终active/running、207文件一致、PID2116573、重启0、启动以来error级日志0。Mac12:48:01独立TLS4项通过。首次根代理提前于60秒发起postcheck，被原时间门拒绝，完整失败日志保留；83秒后原门复跑通过，未改代码/门槛。PID只是当次观察值。
- 回退限制：新 `human_decision_v1` 不能由旧012 reader解释；故障应停止服务、保留最新数据并用兼容reader修复，不自动回切旧程序或覆盖最新账本。Windows新决定写入仍503；真实Cursor未验证，真实Claude严格原文任务失败边界保持。RSI-1、RSI-2与真实组织收益试点另计。

- 当前项：F2-1；状态：**done，2026-10-24 12:47:09 CST上线e226671**。第一批01290b8已上线；收尾文档4641d3d已普通推送，工作区开工干净。已读进度、最近十条提交、AGENTS、版本绑定计划/补充/底层及UI契约。
- 精确冻结：实现提交 `e22667130845736a9350741c96fa14f00b57a4df`；26个变更文件已逐项匹配Git正文。100项根定向原日志完整封存于仓库外 `分析/lesson-confirm-version-binding-20261024/frozen-e226671/root-final-targeted.log`，SHA `2634c9a00d62f93a6e09af778cd9e8df1cbc157e78f4157b7cc42febf1a83a49`，原路径 `/tmp/webuddy-f2-root-final-targeted.log`。完整SHA清单和命令/结果见同目录 `frozen-handoff.json`；1859项发现无加载错误，当前未将发现数视为测试通过。
- 独立最终复验：授权锁两个真实HTTP屏障20轮加冻结1轮，42次全通过、零跳过，源码与方法AST前后不变。旧4641归档2211个Git文件/模式一致，四项准确红灯共6个断言失败、无执行错误；每个legacy子情景独立新卡。最后memory坏封套异常映射已独立确认无其它夹带修改。报告 `分析/lesson-confirm-version-binding-20261024/root-stability/独立稳定性与基线红灯复验-20261024.md`；双端全量及发布门待完成。
- 精确发布验证进行中：仓库外 `部署包/lesson-confirmation-20261024/candidate-e226671` 从Git导出207运行/434验证文件，归档逐项回读；16个传输文件服务器SHA相同，stage/rehearse实际退出0。12:26 CST只读现役核验仍01290b8、56业务/11控制表、无活动运行；1781成员私有完整副本两轮初始化全行/schema不变，现有3项目31卡只读兼容、账本原字节保持，独立合成新封套及真实worker退出/socket/key清理通过。Mac/Linux全量正运行，不把工具97项自检或之前1768项结果当本批通过；生产尚未切换。
- Mac精确全量已完成：`python3 -m unittest discover -s tests`，**1859项 / 1839通过 / 20可选依赖跳过 / 0失败错误**，unittest558.349s、外层560.148s，实际退出0，434文件字节/模式不变。完整日志37805字节，SHA `4f96b562966723912f152738135fec74b6a4df2c2e6eda4a9d9f43a51439164a`。18项涉及可选MCP、另2项可选依赖；原ResourceWarning含末尾5条socket警告保留，未宣称全套零资源问题；SDK与Linux结果另行核验。
- 目标：两个人工入口统一同锁CAS和持久回执；confirm仅候选、restore需明确原因；旧请求精确重放只返回历史回执及当前卡片，禁止复活停用经验或清除后来的固定revision。新增获准项目单卡读取，普通成员全局记忆GET仍403。
- 分工：底层learn.py与新并发/故障测试；两个真实UI共享请求协调器与实际JS测试；根负责memory/server/tenant_policy/ui_access及真实HTTP集成。独立审查同步进行。
- 合理假设：损坏/歧义旧账本不自动修复，新人工决定409并保留原字节；新增封套原子replace与file/dir fsync，旧状态/锁语义保持。active正文编辑仍active的既有政策不在此批暗改，也不宣称所有active都已绑定当前正文确认。
- 发布约束：旧程序不识别新决定封套，发布前必须验证读取兼容和停止后修复策略，不自动回切旧reader/覆盖业务账本。既有全量1768与SDK74仅证明012，不作为本批验证。
- 待确认：无当前阻塞；真实RSI付费试点仍待实验预算与保留集隔离，下一步按RSI-1/RSI-2执行。
- HTTP红灯留存：冻结4641d3d四项测试失败；首次夹具被legacy租户执行门403挡住，原日志保留，不作漏洞证明；改为原可用memory路径和真实个人会话单实例legacy后，明确复现旧版本错误200、旧请求恢复active、错误动作先写正文。后续拆开子例确保每例独立原卡。
- 过程定向：真实gateway/worker个人会话11项11.654s通过，含双阶段socketpair屏障确认worker写前/耐久写后授权锁仍持有、撤权先后两序、Agent/工具/shared token拒绝、跨项目窄读、manager/contributor区分。产品仍在完善，这不是最终冻结验证。独立权限矩阵64/64通过且Store前后相同。
- 有限兼容修复：legacy两入口接同一纯ledger原语；旧tenant safe表漏列使manager也受execution gate误拒，仅四人工动作及fields-only edit列为safe，角色与strict个人身份不变；share/take及未知动作不放宽。新增单卡GET使路由目录精确计数166→167，原库存一致断言保持。
- 原测试适配：memory/platform用例补真实个人会话、真实token/request_id、明确restore原因，保留原业务断言；缺卡404测试补合法请求形状，防止格式400遮蔽范围检查。
- F2-1 实现冻结验证：底层5模块126项/12.387s通过，20轮×8并发/故障160次通过，learn SHA `1ef5e0566200ee4f99af5c867a765e4149b636f5288e5daec3401f81537408ea` 前后保持；UI7模块172项/15.028s通过，新增27共享JS+8旧入口测试。根亲自读取diff并重新核对21份底层日志、UI5源码/7日志的SHA；独立账本45、权限64、主体头14场景和UI4时序通过。
- 真实HTTP补修：新增阅读账号头，单实例跨标签换账号先409；租户Workers白名单曾漏转发，首轮7fail/1error及集成失败日志保留，修为签名元数据后28项/19.181s通过。头不认证身份，删除/添加/篡改签名字段均拒绝。最后坏封套列表500反例（两个memory GET）先红，再补异常映射，四读入口均409且字节不变。
- 根最终定向命令：`NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost PYTHONPATH=tests:. python3 -m unittest -v tests.test_lesson_decision_api tests.test_memory_workspace tests.test_tenant_policy tests.test_tenant_runtime tests.test_learning_api tests.test_platform.PlatformApiTest.test_acceptance_teaches_and_grows_the_eval_set`；**100项/30.112s/OK**，日志 `/tmp/webuddy-f2-root-final-targeted.log`。保留ResourceWarning，未声称全测试零资源问题。较早集成另出现一次本机HTTP502，原日志保留；显式回环不走代理后同例及最终组合通过，没有改断言/等待预算，未据重跑单独断言502根因。
- 实屏：合成个人正常登录，两入口换版拒绝/完整回读/保留旧稿/确认/带原因恢复/修改与确认原子合并通过；完整MEMORY_JS41028字符与冻结源相同。真实Chrome设备工具栏390px，两页scrollWidth=390；原图无压缩，根已实际打开；最终3张卡片完整字段、15文件、CRLF/尾随空格保持，恰4次预期合成决定，所属worker/socket/key回收。见 [UI记录](../design/lesson-confirmation-2026-10-24/README.md)。首次整体脚本读取被工具截断，不作旧缓存证明；设备宽度输入4的失败截图保留，不当390通过。
- 文档与发布边界：新增 `docs/lesson-decisions.md`；Windows新决定写前503，历史不补造确认，坏账本409且不修剪。新human_decision不能被旧012读取，发布失败保留最新账本并停机修复，不自动切旧reader。1859项发现、loader errors=0；acceptance/guard/filelock/agents与开工HEAD逐字一致，MOVES未改；`git diff --check`通过。待精确提交双端全量及发布，当前尚未推送本批或切换生产。

## 2026-10-24：组织提效第一批——知识可信状态与成员工具连接

- 当前项：O1/O2；状态：**done，2026-10-24 11:38 CST上线01290b8**。基线 `iteration/context-pack-v2` / `fc65a2b`，开工 `git status --short` 干净；已读最近十条提交、AGENTS 和两份 PPT/录音审查输入。用户授权由 review 会话转交到长期开发会话继续实现，并沿用验证后 GitHub/服务器自动发布约定。
- 当前冻结候选 `01290b8975a1eae25af49a241429b5e8ff7954a6`（206运行/429验证文件），**已上线**。Mac精确全量已实际退出0：1768项、1748通过、20可选依赖跳过、0失败错误；unittest503.596s、外层506.224s，429文件字节/模式不变，完整日志SHA `c0eb628fb6086ed51e80f89295786c59bf585a5b8af2a6eaeb72c683d4849f7c`。正式官方SDK五模块74/74、0跳过、19.363s，原单项10秒/外层180秒保持；完整日志SHA `940bae663583a7315bb519ea48ed52357b6a5640c91b005b89bf727fa34bb8ea`。实际发现/结果/导入路径/PID/429文件保持经独立核验。新候选SDK阻断已解除，旧失败保留。
- 当前发布进度：新包正常传输14文件SHA读回通过，stage/rehearse实际退出0；1781成员完整隔离副本迁移两轮幂等，原56业务/9控制表保持，仅新增两空授权表，真实worker退出/socket/key清理通过。Linux精确全量已实际退出0：1768项、1750通过、18可选MCP跳过、0失败错误，unittest725.589s/外层727.135s；429文件保持，76HTTP及合成进程/socket/key清理通过，完整日志SHA `29784fcc20a3a763653b09192d475eb4a9342393c3eec4975a2e22dca6233116`。10份证据134468字节已下载并由根逐文件SHA读回。独立第五轮窄审已关闭I-1/I-2，完整只读发布门已通过；11:38生产已切换01290b8。旧fe8的SDK失败、SCP半包及后来两端全量均完整保留，旧候选因嵌套反例被否决，不作为新候选成功依据。
- 发布工具误拒现场：012第一次只读gate真实退出1，只因Linux末尾5行合法 `sys:1: ResourceWarning:` 与原脚本仅允许的Mac `<sys>:0:` 不同。原gate目录/完整日志保持；仅修仓库外两个精确前缀识别，新增8项（旧版3项红）、原22项和37项工具自检均通过；完整gate第二次实际退出0，全部5行警告保留，不改产品、测试、超时或原日志。
- 旧fe8 Mac精确全量封存：1763项、1743通过、20跳过、0失败错误；unittest593.098s、单调594.512s，但UTC墙钟起止跨6小时25分，已证明机器长时间休眠，不能当作连续测试耗时。完整日志SHA `0b01ee6c34805b95a7876e567b6a3e4e793fbcbfad535eaede65d369c2baba20`；资源警告与失败原件保留。
- 最新状态（嵌套复检修复）：`fe8ba67` 已被新独立反例否决，不发布。其 Linux 精确全量已封存：1763项、1745通过、18可选MCP跳过、0失败错误，719.702s；76合成HTTP及指定进程/socket/key清理通过。原SDK失败与传输半包完整保留；电源日志证明验证期间发生长时间休眠，但缺原子进程栈，不把具体超时根因说死；原10秒限制下候选/基线20次交替单测均通过，不替代新候选SDK组合。
- 本次窄修：主运行与操作归档统一逐层校验旧平铺/真实fixloop wrapper的显式运行、项目、工单与操作身份；旧操作可不同、缺登记仍unknown、完整原文不改。探测来源严格区分bool/float/int，迭代比较保留合法深JSON；操作编号限SQLite正signed64，损坏超界返回409。未证明矛盾存档可由正常API制造，不扩大成已证线上泄露。
- 红绿证据：原fe8干净清单快照新增4项有236子例失败；补充超界/深JSON在中间版本2项20errors。修后新测试首次有1个ticket_get取值路径KeyError，仅改读真实harness_library.history，原文相等断言不变。最终官方SDK环境6模块组合 **56项/26.501s/OK、0跳过**；发现 **1768项、loader errors=0**。日志/tmp/webuddy-nested-history-final-r3-20261024.log；所有旧测试不改。独立32个深JSON读入口及29项历史契约均通过，另外28项顶层/整数边界/旧历史正控通过；最终清单源SHA和报告保存在仓库外分析目录。
- 验证方法限制：一次外部探针误对整个工作树递归计算文件摘要，范围包含.git及已有data，未改文件或输出原内容；该次结果不作为最终证据。后续全部从明确Git/manifest文件导出干净快照，禁止再对原工作树递归读取。
- 发布收口：GitHub普通快进 `4617d7b..01290b8`，ls-remote完整SHA一致。切换前实时原行/schema与演练一致；完整备份 `/opt/webuddy/backups/pre-01290b8975a1-20261024T033803Z`，1781个data成员及三项目277/37/20个成员逐字节读回。原56业务/9控制表保持，仅两空授权表新增；无生产个人会话/业务写入，未代人确认。
- 11:38:06 CST启动，11:39:32延迟约86秒后18/18公网与回环检查通过；11:39:56最终206运行文件核对、active/running、PID2073589、重启0、启动以来error级日志0。数据库完整性、原记录、非DB/项目文件、配置、Caddy及另一应用保持。Mac独立TLS4项通过。后续状态须重新实测，PID为当时观察值。
- 审查保留边界：重复JSON键仍后值覆盖、浮点仍按Python解析值比较，原文完整保留；不是全部JSON歧义解决，也未证明正常API可制造跨项目存档。真实Claude两项严格原文任务失败/Cursor未实际调用、Windows凭据ACL/POSIX网关限制、未打通外部执行生命周期/跨角色汇合/组织净收益实证均保留。下一批明确是F2-1、RSI-1、RSI-2，不把本批当RSI完成。
- 最终证据封存：12份服务器原始报告/日志共144450字节，下载脚本实际退出0、无重试，根代理逐份重新核对SHA/长度通过；readback-manifest SHA `5038baa94bf652eb616974e6ee3d8a0121f8c007ac677990ade6fd16f5287c4f`。原10份验证记录保持。

以下为实施过程历史记录；本批最终状态以上文和发布记录为准。

- O1 doing：修复术语、决定、坑等 Agent 可维护文本被无条件标为已确认；保留全文、检索和历史，确认只依据真实来源证据。知识实现与客户端分工并行，主代理负责网关、权限、回执与集成。
- O2 doing：个人网页登录授权限定项目/期限的工具凭据，CLI/MCP 使用独立凭据；回执绑定真实成员，工具标签不授予身份。只开放获准内容读取及任务/消息写入，保留全部执行/人工批准禁令。凭据撤销、权限收紧、账户停用/换密码后必须立即失效；旧请求不得绕过撤权。
- 已跑：审查无网络构造器探针（租户 URL 为 invalid_endpoint），真实聚合内存输入（3 条未经确认内容均 incorrectly 已确认）；作为红灯依据。尚未宣称第一批测试通过或发布。
- 待确认：当前无阻塞问题。真实 Claude 使用现有配置做隔离集成；未安装/未实际调用的 Cursor 等工具明确记未验证，不用合成测试替代真实团队收益。
- 后续 todo：R1 自然语言行动草稿；R2 全部约束到工作/产物/验收的稳定映射；R3 事实预填简报；R4 固定版本组织模板资产；R7 多输入汇合；R9 全链收益；R8 独立执行环境、整晚预算与夜间试点。本批完成不代表九项全部完成。

- O1 实现完成：真实解析、聚合、API/CLI/UI均不再给三类普通笔记自动授予确认；保留原文与完整文件SHA，同文不同确认状态不合并。独立95项通过；根代理亲自复查diff并将知识纳入后续107项核心组合通过。
- O2 定向验证：后端工具授权/租户45项通过；官方mcp 1.30.0 SDK + CLI/文件59项通过、0跳过；旧回执迁移4项通过，真实第二ALTER故障回滚、两个独立连接并发迁移，删除事务的反向测试准确失败。
- 对抗反例已修：内容读取触发Git被禁、历史adopt预览403/错误“提交不存在”、无关租户改权导致工具409。改为明确当前HEAD/预览未现场核验，保留历史记录并关闭URL；工具上下文只绑定自身不可变授权摘要，worker仍实时重验。新增真实HTTP历史adopt三子情景先红后绿，未改既有preview/acceptance/guard/锁。
- 根测试记录：首轮核心组合91项成功、1个UI模块因既有测试采用顶层导入而加载失败；按原discover等价路径加入PYTHONPATH=tests:.后 **107 tests /19.061s /OK**。网关/运行期新增测试首次1个夹具漏传actor参数，修正后 **23 tests /12.646s /OK**。完整日志保留/tmp/webuddy-firstbatch-core-20261024.log及tool-runtime日志；未改超时或旧断言。
- 实机验证进行中：独立临时官方MCP依赖环境已建；现有Claude配置只连接合成组织，禁用内建Bash等工具，正在核对服务端真实回执。浏览器使用正常合成成员登录；尚未宣称真实Claude、Cursor或页面最终验收通过。
- 生产只读核验：2026-10-24 02:51 CST，现役2fd2adb、56业务表、9控制面表、仅default，active/running、重启0、完整性ok；本机0600、公钥指纹及严格SSH成功。无生产写入/切换，迁移与双端精确全量尚未开始。
- 后续优先主线：第一批收口后复用learning_*开展RSI受控实验，遵循分析/RSI协调/运行说明.md。同一应用commit/模型/任务/预算，允许优化面限定为上下文/提示词/技能/执行策略；基线和弃权必须作为候选，不改评估器、guard、权限或人工采用门。真实成本未知时保持未知，不把harness_probes应用行为对照当作RSI因果收益。


- 最终定向复验：官方 MCP SDK 独立环境下完整核心组合 **272 tests /60.276s /OK，0 跳过**（/tmp/webuddy-final-targeted-r2-20261024.log）；上一轮267/59.531s也通过，但不替代最后UI修复后的结果。真实固定版本知识库长CRLF原文、HEAD前移及分享撤权都已走HTTP回读。
- UI对抗红灯与修复：focus开始后身份未返回/失败时旧token仍可下载；已改为核验开始即同步清除，busy期间也生效；新token只在最终身份与列表回读成功后显示，独立显示epoch阻止迟到响应复活。原三例先红后绿；最终30项实际JS测试及独立5情景复核通过。原请求完整保留，不通过生成新编号绕过未知结果。
- 最终实屏：正常合成Alice登录→限定项目1天只读授权→下载→CLI安全导入→身份/范围回读→页面撤销→CLI返回401；390px scrollWidth=390、明文长度0，控制台warning/error空。桌面/移动原图已亲自打开，原始字节保留。临时下载在与导入文件JSON完全相等后清理，合成worker退出、socket/key回收明确核对。
- 真实Claude两次隔离调用：现有CLI 2.1.309/既有配置报告模型路由commandcode-plan/deepseek/deepseek-v4.1-flash[1m]，未独立核验上游供应商；MCP身份、一次写入及真实回执可读、撤销后旧CLI/MCP/原请求均401。两次严格原文任务均失败：第一次把CRLF写成字面\r\n，第二次读取完整原文后转为LF；平台保存/回读与模型实际参数逐字一致。未为通过而正规化或覆盖旧回执。证据在仓库外分析/tool-connections-20261024/claude/；这是工作树集成，不冒充最终commit精确模型复测、生产业务验收或组织收益。
- 紧接修复批次：独立审查确认旧lesson_confirm缺正文/状态版本绑定，可确认后来改写内容并重放恢复停用经验；须分离confirm/restore、事务内CAS和幂等，旧历史不倒填hash。本批仅修三类笔记假确认，不能声称所有知识确认都已可信。RSI真实试点前另须统一完整条件renderer、实验级累计预算/预登记重复及优化器不可读保留集；基线/失败/未知均参与判定。
- 既有边界：Cursor未真实调用；Windows原生凭据ACL不支持，POSIX网关限制保持；本批未实现外部工具主动派发、完整组织收益度量或RSI试点。实际Claude两项原文任务失败明确保留。

- 最终冻结：发现 **1737 tests、loader errors=0**；acceptance、guard、filelock、agents四文件与fc65a2b逐字一致，MOVES未改，git diff --check通过。实现准备独立提交；随后从精确Git blobs导出两端全量，当前未推送/切换生产。

- 冻结实现 **fd3a94e**：205运行文件/425验证文件，14个传输文件逐字节读回一致。Mac Python3.14.6精确全量 **1737 tests /1718通过/19可选依赖跳过/0失败错误，外层461.092s，unittest459.976s**；425文件前后SHA/模式一致，完整日志SHA `51752428eb778a9e35e3ccf74fced6d0c35defd7f4f7642f439002b81631a032`。日志包含ResourceWarning与弃用警告，未宣称零资源警告。
- 同冻结源码官方MCP1.30.0/CLI/凭据 **59/59 /14.890s /0跳过**，8相关文件前后匹配包清单；独立审查61项通过，36个变更文件逐一匹配fd3a94e。完整生产私有副本1781成员迁移两轮幂等，56业务表原行/schema、9控制表原身份/权限保持，仅增加2空控制表，不创建生产原本不存在的agent表。真实私有worker初始化/退出/socket/key回收通过，无生产个人会话或业务操作。服务器全量仍运行，未推送/激活。

- 发布前补跑被全量跳过的知识MCP SDK用例出现 **1 error /0.344s**，fd3a94e暂不发布。旧test_knowledge_agent_api无限制Mock自动产生真值tenant，新build_server因此按个人租户连接拒绝allow_execution；真实Client无此问题。仅修夹具明确旧本地连接类型，保留原断言和产品限制；红灯日志在candidate-fd3a94e/candidate-sdk-proof/knowledge-discovery.log，后续单独提交并重新冻结双端全量。不能用前59项通过掩盖这项遗漏。

- SDK夹具最小修复：仅 `test_knowledge_agent_api.py` 一处 `Mock()`→`Mock(tenant=None)`，明确其原本测试的本地连接；所有原权限断言保持。知识模块14项+原SDK/CLI/凭据59项，共 **73/73 /14.933s /0跳过**；8149个原断言AST、148产品Python哈希不变，主代理独立核对整文件只有这一处keyword变化。证据在分析/tool-connections-20261024/knowledge-discovery-fixture-fix/；发现数仍1737，将单独提交并重跑两端精确全量。初候选Linux主套件1737项/736.058s/17跳过/0失败错误已结束，但不能覆盖这项SDK红灯。

- 最终候选 **4617d7b**：只增加知识 MCP 本地连接夹具的显式 `tenant=None`，205 运行文件与 fd3a94e 字节/模式相同。Mac Python3.14.6 精确全量 **1737 tests /1718通过/19跳过/0失败错误，外层462.356s、unittest461.159s**，425 文件前后保持；日志 SHA `3d66975d9a7380975ed85ad20acb9c358b1eb728e44c7025f3ad62574324cec7`。官方 MCP1.30.0 对同一归档补验 **73/73 /15.195s /0跳过**，425 文件保持、11 模块实际路径属于归档；日志 SHA `0896249e42d156e6eb69b8bdeec5bec971e2b866d2b3a79d66d15125637f9656`。完整日志仍有资源警告，不声称所有测试资源清理完备。Linux 尚待最终结果，未推送/激活。

- `4617d7b` Linux 精确全量 **1737 tests /1720通过/17可选MCP跳过/0失败错误，736.788s**；425文件保持、76项合成HTTP、gateway/两worker/socket/key退出与清理通过，日志SHA `c53176a4652fbcfde4b0b5aa6b7b842b7552e0a3da07c862466d7c5504588189`。GitHub已普通快进并由ls-remote确认完整SHA；**生产未激活**。
- 新独立复核阻断上线：最终连接列表已返回revoked，UI仍展示并允许下载POST返回的凭据；服务端401仍有效，不能描述为授权绕过。另 `candidate_get/candidates_list` 对工具只读凭据仍触发实时Git/预览HTTP探测，将未核对结果误投影为stale。完整反例在分析/independent-review/20261024-033921-4617d7b-review，保留失败，不修改已冻结候选；正在分别修UI回读与候选纯历史投影，修后另起提交/重新冻结验证。当前基线全量通过不覆盖这两项新反例。
- 外部发布工具附加门：activate原脚本仅查两个exit code，未独立拒绝报告error/清理失败；本次已增加仓库外只读prepublish_gate，14项正反自检通过，真实服务器gate也通过（03:46 CST），完整核对wrapper退出0、无error/中断、425/205文件、SDK、76HTTP、迁移和实际进程/文件清理。候选脚本未改；此门通过不能抵消新产品反例，故仍不激活。下一新包同时加严脚本本身，失败报告保留。


- 本轮 UI 最终列表修复：原30项保持，新增6项在旧源码33个子例红灯；修后36/36、独立15/15及原真实HTTP撤销响应重放通过。展示/下载绑定唯一有效连接行及身份/范围/期限；下载前同步检查过期，原请求编号/清屏epoch不变。根代理已审diff，最终须由新提交全量确认。
- 根真实浏览器复验：正常合成Alice登录→单项目只读1天创建→实际180字节下载→CLI导入/身份范围回读→网页撤销→旧CLI 401。CUA下载事件超时保留，实际原文件已逐JSON核对并清理，不伪称工具事件成功。桌面/390px原图亲自查看，无重编码，窄屏无横溢/明文0/下载禁用；临时fixture与worker/socket/key全部退出回收。
- 新真实MCP候选回归先红（current=False误报未知），修后1/1、2.027s通过：官方stdio→真实网关，完整长CRLF历史一致、current/human_accepted=null、预览URL空、撤销后旧会话401。此为工作树验证，最终精确提交仍待跑。
- 后端交叉审查又复现嵌套历史绑定和损坏证据截断，正在修复；错误外键夹具不声称正常API可制造，但读取必须明确拒绝错绑。正常同单多候选预览归属也须避免误挂。仍不激活旧4617d7b。


- 后端最终修复已完成：工具13项读取无现场探测/恢复；复检、探测、采纳及预览核对工单/项目/运行关系，候选历史明确工单最新预览不代表当前候选。完整CRLF/长文、损坏JSONL、非UTF-8原字节均保留；损坏合同不签发需求hash，合法Unicode分隔符不误分行。通用需求hash默认路径与人工验收链保持。
- 根最终定向组合（新只读/MCP、UI、原候选/独立验证、知识MCP、人工知识权限）**108 tests /42.762s /OK、0跳过**，日志/源哈希保存在分析/tool-connections-20261024/mcp-read-fix/。discovery **1760、loader errors=0**；六个acceptance/guard/filelock/agents/process监管文件与fc65a2b逐字节一致。尚待最终独立复核及冻结提交双端全量，不用定向成功替代发布门。
- 04:07:51 CST重新严格SSH只读核对，生产仍2fd2adb、56业务表完整、无活跃运行、自动流转关闭，接入/sudo可用；没有生产写入或切换。部署activate验证门加严与独立gate正反自检已完成，旧候选目录原样保留。


- 最终复核新增阻断与修复：登记归属正确的复检artifact仍可声明别的运行；同一结果在主run/verify.json也有副本。新增三项先红后绿，现同时检查两份文件已声明的顶层归属，兼容旧记录及同一运行的先前轮次；共享预览损坏明确409，不吞成空记录、不返回共享文件原文。此为矛盾历史夹具防御，未证明正常API可制造。
- 更新发现数 **1763、loader errors=0**（新增tool_read18、真实HTTP1、MCP1、UI6）；旧1760/108项仅为上一冻结点结果，最终三模块复验及独立复核进行中，仍未提交/激活新候选。

- V2最终源保持：根只读/真实MCP/网关组合 **31 tests /17.766s /OK、0跳过**；后端关联原候选/预览/复检组合 **109 tests /37.106s /OK、0跳过**，源哈希前后不变。日志原样保留，最终独立复核后独立提交并导出1763项全量。

- 最终独立反例重放 **12/12通过**（完整损坏行/字节、复检登记与两份artifact、探测来源、采纳运行、旧轮次、同单后续预览及共享预览损坏）；源码SHA与V2一致，读取副作用0。主代理亲读报告和最终diff，准备新修复提交，旧候选不激活。

## 2026-10-23：会后行动、工作简报与交付覆盖

- 当前项：C1–C5；状态：**done，2026-10-23 21:50:04 CST 已上线 `2fd2adb`，GitHub 已推送**。实现 `39cde13`，夹具修复 `7656667`、`090caef`、`2fd2adb`；下列中间状态按发生顺序保留，最终结果见本节末及[发布记录](../../audit/production-deployment-2026-10-23-coordination.md)。用户明确要求按标品方向实现三项及 UI，验证后自动推送 GitHub/服务器。开工 `iteration/context-pack-v2` / `68f0137` 干净，已读进度、最近十条提交和项目 AGENTS；历史 stash 保持。
- C1 done：完整会议来源、行动项草稿/期限/负责人/交付物/完成条件，原子发布到既有工单，规则提取与人工补全分开。
- C2 done：任务工作简报独立版本和当前来源绑定，简短同步与完整原文分层。
- C3 done：交付覆盖逐条绑定具体产物，个人核对与业务验收分开，新产物使旧核对过期。
- C4 done：统一标品 UI、现有页面入口、移动端与草稿/未知结果/迟到响应处理；后端两路和 UI 并行，主代理负责服务端权限/迁移/HTTP 集成与发布。
- C5 done：定向测试、独立审查、真实浏览器、精确双端全量、生产副本迁移/备份/上线及延迟检查完成。实施合同见 [设计](../design/coordination-product-2026-10-23.md)。
- 判断：保留录音全文但不纳入源码；会议资料不成为执行指令。会议原文保存后只读，修订可另存新记录，不覆盖历史；提取候选不猜人名/期限。新租户关闭执行，仍应可手工整理与协作；不外发消息，不代人验收、采用知识或关单。
- 待确认：无阻塞，按用户既有自动推进授权继续；外部办公同步、组织品牌文档引擎与独立代码执行环境仍在后续范围。
- 核心定向：coordination 28 项、coverage 27 项通过；完整原文/503 候选无隐性截断，双连接 CAS/相同请求并发唯一写入、回滚与撤权重放均验证。根真实 gateway+policy+workspace 首轮 36 项中 1 个新增夹具字段名错误（state 应为 status），修复后 36/36 / 8.262s 通过，日志保留。
- 交叉审查：覆盖来源原来只取每阶段最新运行，会漏掉材料实际引用的旧来源运行变更；新增双运行用例先红后绿，改为同时绑定实际来源、依赖来源与最新尝试。HTTP 分页原来未将 parse_qs 列表规范化，真实请求先红后修；拒绝重复参数，未放宽断言。
- 补齐可用性：原交付创建/保存入口属于执行门，新租户不能用；新增独立纯数据库手工路径，原子创建待分配工单/交付或追加材料版本，无 callback/Git/模型，不改变旧执行与阶段复核规则。新增 3 条路由与 2 张表；路由库存断言按实际 155→166 更新，仍逐项校验完全相等。
- 发布前只读核查：2026-10-23 20:32 CST 线上仍 56018de、active/running、重启 0，仅 default 租户、45 张业务表、无活跃运行，数据库完整；控制面已存在，禁止重复 bootstrap。新工具包保存在仓库外 coordination-product-20261023，副本迁移与精确验证尚未运行，未切换服务。
- 根最终核心组合 `tests.test_coordination tests.test_delivery_content tests.test_delivery_coverage tests.test_coordination_http tests.test_tenant_policy tests.test_workspace tests.test_handoffs tests.test_delivery`：**157 tests / 18.386s / OK**。其中新租户关闭执行仍通过真实 HTTP 创建交付、保存完整材料、幂等重试和材料换版失效，旧执行入口仍 403；未改原交付复核/状态门。
- 简报来源独立复查：补上当前交接 head/current 的纯数据库快照，真实 send→receive 后旧简报 stale、旧依据保存 409；mutation 移除该绑定后准确失败，再恢复通过。协调模块最终 29 项通过。
- UI 实际浏览器仍验收中，新增行为用例已通过；发布脚本独立审查发现 smoke 外层超时可能遗留 gateway/worker，正在补父进程丢失与 TERM 清理验证。尚未开始全量或切换生产。
- 来源导航修复：会议工单正文和结构化链接现带实际租户、会议与项目，逻辑 API 另存 api_url；UI 只按已授权项目定位，不能回退到当前其它项目。协调+HTTP **36 tests / 9.562s / OK**；原API来源断言仍保留并增加真实页面链接测试。
- 最终 UI 独立审查阻断：未知 POST 重挂载后 GET 失败缺少重试 DOM、成功回执后存储清理失败可能重新允许创建、导入前捕获草稿失败未显示错误；已在实际发布 JS 上复现，正在最小修复和回归。未把早期通过当作最终全量或发布凭证。


- UI 最终冻结：新增 30 项与既有 handoffs/access/delivery_design 共 **97 项通过**。独立复查原 4 个红灯及 6 个重试/刷新/存储异常场景全绿；成功回执清理失败不再发新 POST，完整刷新只重放原请求编号和正文。还保留升级前材料草稿并要求显式重新绑定，标题编辑不改正文 CRLF。
- 发布辅助进程清理：真实超时、直接 SIGKILL、忽略 TERM 的 KILL 兜底、正常 44 项 HTTP 四场景通过；gateway、两租户 worker、socket/key 回收全部核对，失败现场与自检记录留在仓库外。副本迁移拒绝 SQLite 文件或 control 父目录外链，会议来源链接已带明确租户/项目。
- 主代理亲自查看最终桌面会议、工作简报、390px 完整交付原图，文字与表单可读；窄屏原图保持 390×4865，不裁切、重编码或压缩。实际浏览器为合成双租户，不能替代生产业务验收。
- 冻结 discovery：**1631 tests，loader errors=0**；acceptance、guard、filelock、agents 与 68f0137 逐字节一致；`git diff --check` 通过。即将提交实现并针对精确提交执行本机/服务器 `python3 -m unittest discover -s tests`，未把定向测试当全量结果。


- 实现提交 **39cde13** 已冻结：202 个运行文件、416 个验证文件，归档逐文件 SHA/长度/权限读回。初次本机验证在启动测试前因工作区历史脚本权限 0600 与 Git 记录不一致被阻断（0 项运行）；保留现场，改为从同一 Git 归档导出完整字节/权限，在独立目录执行全量，不改工作区权限或断言。
- 部署脚本最终独立复核发现异常分支先保存报告可能跳过停服；修复为停服不依赖报告写入，7 项实际异常处理代码注入从全红转全绿，原异常对象保持。候选 r2 仅该外部脚本不同，运行/验证 tar 与初包 SHA 完全相同；初包未 stage 或切换生产。本机全量使用相同冻结源，服务器以 r2 为准。
- 实屏材料：16 张原图共 1,817,222 字节，字节/SHA 保持，最终会议/简报/完整390及只读交付均已亲自打开。详见 [UI 验证记录](../design/coordination-product-2026-10-23/README.md)；合成服务、worker 和验收页签已清理。


- 首轮精确本机全量：**1631 tests / 496.773s，1613 通过、16 跳过、1 failure、1 error**；416 受测文件保持。完整日志 SHA `5dad629cf413b706c81cf89b2c526605f5a1c23e962915c700a559aee5f5989f`，两处现场在 candidate-39cde13/local-validation/guard 保留。未上线该失败候选。
- 已修 error：旧 `test_run_recovery` 假设 Store 尚未创建交付表，手建简化 delivery_runs 与本轮正规迁移冲突；只把夹具改为按真实列插入完整登记。原单例先红，模块 **7/7 / 5.838s** 通过；50 个断言 AST 与全部超时不变，除两条夹具语句外全文件 AST 相同。另一个 gateway 强杀后的授权锁断言正在独立定位，不以重跑消除记录。
- 网络传输初次在外层 600 秒截止前未完成，未 stage/启动/切换；现仅续传验证归档，保留部分文件并校验最终 SHA。传输时间预算调整不涉及任何产品/测试超时。


- 首轮 failure 根因确认：真实 gateway 在转发前也短暂持同一个授权锁，旧 `guard_held()` 把这个窗口当作 worker 已进入 SQLite。测试专用 gateway 屏障准确复现原第 158 行失败；原 worker 未写 comment，并非已证明的产品锁释放错误。
- 最小修复只在 `test_tenant_parent_loss` 真实 worker 的原 `Store.comment` SQL trace 中观察 BEGIN IMMEDIATE，原子发布 PID/请求/工单/作者/SQL 标记；确认实际 worker 到达后再执行原 SIGKILL 和全部锁/撤权/无后写断言。新增 gateway-only 窗口测试；全部既有等待/HTTP/清理时限不变。模块 **3 项通过**，连续 **20 轮 60/60 / 44.898s**，独立复核 3/3 / 2.198s；移除真实 worker guard 的反向测试准确红灯，现场保留。产品锁、取消、超时与三代进程实现未改；这三项不冒充其它执行器模块的覆盖。
- 夹具修复分开提交：交付恢复 **7656667**；本次提交父死测试屏障。最终 discovery **1632、loader errors=0**，即将对修复后的精确提交重新执行两端全量。


- 第二轮精确本机全量 **090caef：1632 tests / 590.820s，1614 通过、16 跳过、2 failures、0 errors**；416 受测文件保持，日志 SHA `171cb68787ba2a4c7319f6a040774b5a7c870ecd57ded536a77c02d6cba38996`。前两处已修问题通过；新失败为共享网关夹具兼容性回归：`test_tenant_runner_owner_loss` 按原接口只传 data，新观测器却读取第二参数，导致两项真实三代进程测试在启动阶段失败。正在恢复单参数契约，并联合执行两个调用者及进程专项；不以“产品代码未变”为由忽略失败，也未部署。
- 低带宽传输改进：两次 rsync/整包传输未完成即停止，保留旧目录，所属本地传输进程已核对退出。新增差异包重构工具只读取旧 release 中经过 SHA 验证的 app/test-source/wheels，不读业务 data；本机整包字节、模式、TarInfo 与新候选完全一致，并验证已有 incoming/损坏复用源会拒绝。最终候选仍需重新打包和服务器验证；没有跳过完整归档与全量门。


- 共享夹具回归修复：将 worker 观测脚本安全嵌入 `_GATEWAY`，恢复所有调用者只传 data 的原契约；同时 owner-loss 仅加 self.temp 留存失败现场。直接 stderr 的 IndexError 红灯已保留。最终 `parent_loss + tenant_runner_owner_loss + supervised_process + run_lifecycle` **37 项 / 38.995s** 通过；真实 owner-loss **20 轮 40/40 / 48.539s**，每次清理后 gateway/worker/supervisor/三代进程及合成无关 guard 均退出。独立组合 5 项 / 4.197s 通过，64 个原断言/等待 AST 不变，仓库全部调用者已检索；产品文件未改。继续新提交精确双端全量，发现数仍 1632。


- 最终验证候选 **2fd2adb**：三个测试夹具文件相对 39cde13 有变化，202 个产品运行文件仍逐字节/模式相同。差异包 501,796 字节，服务器复用 584 个 SHA 已核验源码/依赖成员，重建 runtime.tar（SHA `b6a3bd608aabe6f85abcb796f429fe66789407361200e11999bc54a232974fb9`）与 verification.tar（SHA `02f36a7d3253e7bb3acbcc706d5ee67a522bf26e0ab08083f1c80a3b0e15a427`）和本机精确包完全一致。stage 已通过；本机/服务器全量与生产副本迁移进行中，未切换服务。


- 最终本机全量 **2fd2adb：1632 tests / 505.223s / OK，1616 通过、16 可选依赖跳过、0 failure/error**；416 受测文件字节/模式前后保持，日志 SHA `2e9e2fb552ac377a89cda97af9507a4558b583b9e6fa5817cfc07ba4eb3d97fc`。跳过为 14 项可选 MCP SDK 与 2 项可选 cryptography；服务器全量仍运行，尚未推送/切换。


- 最终服务器 Python 3.12.3 全量 **2fd2adb：1632 tests / 715.487s / OK，1618 通过、14 可选 MCP 跳过、0 failure/error**；416 受测文件保持，日志 SHA `dbae1fb2ca7302b2d29868a3dc221e1f304d73ea34eb2d9199f6c63a13db506f`。真实合成密码/协作 HTTP 检查成功，gateway 和两租户 worker 全退出、socket/key 全回收。
- GitHub 已普通快进推送 `68f0137..2fd2adb`。切换前再次只读核对生产原业务/控制面结构与行摘要完全匹配演练，仍为旧 PID 1690597、无数据漂移。现开始备份及切换；尚未宣称最终健康验收。

- **最终上线**：21:50:04 CST 启动 `2fd2adb29107368dcb23ca375ebfca5ef20f97d9`，`/opt/webuddy/app` → `/opt/webuddy/releases/2fd2adb29107-coordination-product-20261023/app`。完整备份 `/opt/webuddy/backups/pre-2fd2adb29107-20261023T135002Z`，data 1781 个成员及三项目 `.tmh` 的 277/37/20 个成员读回保持。45 张原业务表原行/结构、控制面与配置保持，仅增加 11 张空协作表；未重做 bootstrap、创建生产个人会话或代人确认。
- **上线检查**：21:53:38 CST（启动约 214 秒后）18/18 公网和回环登录/匿名/旧 token 拒绝检查通过；21:54:03 CST 最终 202 个运行文件 SHA/长度/模式一致，active/running、重启 0、启动以来 error 级日志 0。gateway PID 1778383 和 worker PID 1778392/start_ticks 962938622 保持；数据库完整性、原表及非 DB/项目文件、控制面、配置和其它服务均保持。Mac 21:51:01 CST 独立 TLS 四项通过。
- 待确认/既有边界：本轮无阻塞；规则候选不包含模型语义提取或录音转写，生产业务验收未代做。Windows 网关仍受 POSIX/Unix socket 限制；可选 MCP、真实模型、SSO/MFA、外部办公同步与新租户独立执行环境不在本轮已验证范围。GitHub CI 39964421790 于 21:54 CST 快照 6 项快速/安装成功，四项全量仍运行，不声明整个 CI 或 Windows 通过。
- 最终独立复核：两端完整日志 SHA/计数、202 个产品运行文件与实现提交一致、16 张原图与源文件逐字节一致。外层耗时 505.223s/715.487s 对应 unittest 自身 503.903s/713.987s；ResourceWarning 与 DeprecationWarning 完整保留，不声明零警告或全量所有资源无泄漏。12 份服务器报告/日志 85,821 字节已逐文件读回校验，含 44 项合成 HTTP；首次 SSH 下载 30 秒超时保留记录，按原预算重连后完成，未改产品时限。收尾只提交文档和原图，不再次重启。




## 2026-10-23：租户与权限管理

- 当前项：T1–T5；状态：**done，2026-10-23 17:23:55 CST 已上线 `56018de`，GitHub 已推送**。实现 `273dc97`，两项独立夹具修复 `5aef9d5`、`56018de`；下列中间状态按发生顺序保留，最终结果见本节末及[发布记录](../../audit/production-deployment-2026-10-23-tenants.md)。开工 `iteration/context-pack-v2` / `ace189d` 干净，未新增 stash。
- T1 done：控制面租户、账号、成员角色、项目授权、修订/CAS/请求幂等/审计同事务；已有 data 原位归 default，旧账号迁为 member，管理员由显式 bootstrap 选定，不批量提权。
- T2 done：固定租户路径、独立 data/SQLite/服务进程、会话与文档授权上下文；不在同进程放多个 Platform。默认 worker 在公开监听前就绪，初始化前关闭未隔离后台执行。
- T3 done：统一服务端路由/资源权限、项目队列过滤、非 API 下载与能力票据、路径和执行边界；未知路由默认拒绝，跨租户访问不回退 default。未配置独立执行环境的租户禁止代码/构建/预览；旧默认租户的宿主执行只允许可信平台管理员。
- T4 done：租户切换整页重建、按实例/账号/租户隔离浏览器缓存、管理界面、撤权及迟到响应处理；38 项 UI 回归及桌面/390px 实际浏览器通过。
- T5 done：双租户/同名资源/越权/撤权并发/回滚迁移/执行禁令测试，独立审查、双端精确全量、完整副本迁移、备份和上线延迟健康检查完成；没有把合成账号验证当成生产业务验收。
- 关键不变量：人工验收/知识采用/关单仍走指定本人和证据门；不修改 MOVES，不放宽 guard/acceptance/filelock。平台管理员不自动获得业务签字资格。租户管理不自动外发消息、不把逻辑分库称为 OS 沙箱。
- 管理员迁移依据：已重新读接入记忆，核对 0600、公钥指纹和严格 known_hosts SSH；生产只读查询确认仅一个现有个人账号，采用此唯一身份作为显式 bootstrap 所有者。现役仍 911e42d、active/running、重启 0；没有修改线上账号或业务记录。
- 集成定向首轮：runtime/workspace/platform/login 合计 81 项，76 通过、5 个新增夹具初始化错误（缺临时 data mkdir）；修复夹具后 runtime 5/5 / 0.734s 通过，原断言未变。覆盖 SQL 过滤先于 limit、205 条隐藏数据不挤掉可见项、撤权后队列归零、构造不恢复/启动后台执行、规则 intake 不启 Agent、请求签名绑定。
- 待确认：当前无阻塞；新租户的真实模型、构建、预览执行仍需后续独立运行环境，不能以分库/分进程冒充沙箱。
- T1–T3 实现完成、T4 界面验收中、T5 doing：新增 tenancy/tenant_gateway/tenant_runtime/tenant_policy，账号 epoch、固定 URL 与 HMAC 内部身份绑定；控制面初始化临时库事务成功后原子发布，密码请求幂等指纹使用独立加盐 PBKDF2，审计无密码。管理与业务写入先授权锁再数据锁；实际 worker 持锁至业务处理完成，网关死亡不能提前释放。两端响应发送均移出授权锁，慢客户端不阻塞撤权。
- 独立定向：policy/team/handoffs/workspace 等 107 tests / 28.544s / OK；后续根代理核心命令 118 tests / 27.446s，117 通过、1 个误写不存在模块 `test_candidates` 导入错误（完整失败已保留），改用实际三个候选模块后 30 tests / 21.332s / OK，没有削弱断言或重跑掩盖。最终 control/runtime/gateway/login 合计 **47 tests / 18.124s / OK**，涵盖真实提交屏障与撤权顺序、内部证据上下文绑定、进程启动失败清理、退出锁释放、账号密码变化。
- 异常退出专项：真实 gateway SIGKILL 的空闲退出/活跃 SQLite 写锁屏障 2 项通过，连续 10 轮 20/20 / 18.039s；真实 HTTP→Runner→独立 supervisor→父/子/孙树，分别强杀 worker 与网关，2 项通过，连续 10 轮 20/20 / 21.621s。验证实际 PPID、原子就绪、owner_lost/125、TERM+KILL、完整输出/回执、所有所属 PID/PGID 和 supervisor 退出、无关进程组存活；不声称覆盖主动 setsid 逃逸或整机故障。
- 执行门审查修复：补拒绝 `os.forkpty`，新测试先红后绿；关闭 managed workbench.on_release 隐式预览，并在 preview.start 深层拒绝所有受管租户。授权以项目 contributor 计算当前有效负责人，撤掉项目权后仍是租户成员也会进入待分配。所有原测试文件、acceptance/guard/filelock 未修改，既有 MOVES 不变。
- 说明已补：`docs/tenant-access.md` 和设计合同详细列出角色、迁移、失效与限制。普通成员 Git 提交证据核对及依赖该核对的候选评审仍受限，未为恢复它们放开通用 Git；公开分享/签收/捕获回调/预览在所有受管租户禁用。网关依赖 POSIX/Unix socket，Windows 明确跳过新增进程网关用例，不宣称 Windows 支持。
- 发布准备仍未激活：新外部脚本使用前版 911e42d、45 张原业务表、独立 control；失败后停止服务并保留当前数据，禁止回到忽略授权的旧程序。已做脚本故障分支/合成 HTTP 自检，等待精确候选提交与全量；生产数据尚未迁移。


- 最终自审补齐：默认 worker 在网关公开监听前真实初始化，启动等待仍在授权锁外；就绪失败关闭服务。新增启动回归初次因测试内模块别名误写失败，修正别名后通过，原超时及清理断言保持。worker 日志目录初始化失败同样移除本次凭据和 socket。
- 证据页修复：受管租户证据 HTML 的下载与图片链接现在保留可信 `/t/<id>` 前缀；新增用例先红（遗漏前缀）后绿，连同原签收/交付绑定 **24 tests / 9.879s / OK**，未改变证据或验收含义。
- 人工入口审查：知识确认、业务答复、改判原入口仍可依赖显示名/自报 by，现统一要求真实个人会话、拒绝 Agent 标记及冒用 by，成功记录只用当前账号。新增 7 项真实 HTTP 测试，含拒绝前后文件字节不变、完整原文和人工确认哈希。与权限/知识库合计 **41 tests / 15.169s / OK**；根代理新增七项加原两项 **9 tests / 8.385s / OK**。
- 基线夹具适配说明：`test_platform.py` 两项旧知识测试增加真实合成个人会话，结束恢复 users.json 原字节；原 59 个测试方法的断言 AST 全部相同（`platform-assertions.json`）。因此上文“原测试文件未改”只描述当时阶段，最终唯一原测试文件修改为认证夹具补齐，未改断言含义或超时。
- UI 实屏通过：桌面/390px 管理、只读、两租户同编号草稿、实际撤权清屏、无业务成员的所有者控制面访问。新增 UI 35 项通过，前轮 UI 集合 154 项通过；最后知识答复姓名字段已改为只读真实账号，提交不再接受自报作者；两项新行为回归先红后绿，最终新增 UI **37 tests / OK**，真实弹窗保存多行合成答复成功。六张原始 JPEG 与完整验证记录入 `docs/design/tenant-access-2026-10-23/`，原字节/分辨率保持，主代理已亲自打开桌面、完整移动管理与只读图。

- 实现及测试冻结：最终 discovery **1522 tests、loader errors=0**，准备独立实现提交；随后本机与服务器分别执行精确版本全量。`git diff --check` 通过；五个保护/进程监管文件与 ace189d 逐字一致，原 59 方法断言 AST 不变。此时尚未上传、推送或切换生产。


- 首轮全量绑定实现 `273dc9737eab5da29aec54a665210e98aa1dd6eb`：**1522 tests / 1498 通过 / 8 failures / 16 可选依赖跳过 / 0 errors，526.222s，退出 1**。380 个受测文件前后 SHA 一致；完整日志 `local-validation-final/full-unittest.log` 52301 字节 / SHA256 `8b68beca01dfc2932df875fd7e50d92bbea47c5faeafd391c612a1e99e7d11e6`。失败现场完整保留，未上线。
- 8 项失败原因相同：两份既有独立 JS 测试夹具只提取旧 UI 片段，未装载新增的真实 `appPath` 依赖，均在执行原断言之前 ReferenceError。修复只让 `test_python_pathmap_ui.py`、`test_recheck_signoff_ui.py` 加载页面实际 `ACCESS_BOOT_JS` 和 location.pathname；不加入 mock、不放宽租户路径、不改产品。新增实际证据按钮的租户前缀回归；修复作为单独提交，双端重新验证。
- 首轮服务器包 **197 运行文件 / 406 验证文件**逐字节/模式核验；完整 1775 成员私有数据副本重复迁移幂等，原 45 业务表、users.json/session.key 保持，旧会话失效。真实 default worker 在副本初始化并退出 0、socket/key 清理，不伪造生产会话。首轮服务器全量继续留存，不能用演练成功代替全量通过。

- 夹具修复定向：两个原模块 18 项 + UI 38 项，共 **56 tests / OK**；原两个模块全部 18 个测试方法完整 AST 不变，产品代码与 273dc97 逐字一致。最终 discovery **1523**，准备独立修复提交并从新提交重新导出验证。


- 服务器首轮 `273dc97`：**1522 tests / 1499 通过 / 8 failures / 1 error / 14 可选 MCP 跳过，647.3s，退出 1**；406 文件保持。除同一 8 项 UI 依赖失败外，新增 policy 用例重复插入已登记 BETA 主仓库来源，Linux UNIQUE(project_id,root) 正确拒绝。Mac 临时目录 `/var`→`/private/var` 别名使未规范化夹具意外成为另一字符串，因而未发现问题；这是本轮夹具缺陷，不归为基线。完整日志 SHA256 `005a963cd06680a4300f0fa2896096deff28d7e1181150bf3f92e8b6352e6928`，34 个完整失败证据成员已下载逐字节校验。未执行 smoke 或生产切换。
- UI 夹具修复提交 `5aef9d578c0e743757223c240575c5b11ba8b986` 本机全量：**1523 tests / 1507 通过 / 16 可选依赖跳过 / 0 失败错误，463.982s，退出 0**；380 文件前后相同。完整日志 34619 字节 / SHA256 `7ee3d76436460cb2baeee726bc4e06394a99bbb889e15094061b5efc46bf44ed`，记录于 `local-validation-fixed/verified-result.json`。尚需纳入 Linux 夹具修复，不能把此轮当最终新提交的完整证明。

- Linux 夹具最小修复：直接读取 BETA 已登记主仓库来源并验证项目/root 前提，不重插入、不使用 OR IGNORE；原 4 个权限断言保持。规范化临时路径下原用例准确 UNIQUE 红灯，修复后原始/规范路径均绿；policy 全部 **27 tests / 1.161s / OK**。仅测试修改，141 个产品 Python 文件与 273dc97 哈希一致；从此独立修复提交再次进行双端精确全量。


- 最终本机全量绑定 `56018de6c3bc5dd499e696d3543633f4c4557c4d`：**1523 tests / 1507 通过 / 16 跳过 / 0 失败错误，454.621s，退出 0**；380 文件 SHA 不变。完整日志 34867 字节 / SHA256 `0cbec5cf7af4487e8c00b296353c29eace8a5f56e45999b1c8e9f2b9d11a1eef`。跳过为 14 项缺可选 MCP SDK、2 项缺 cryptography；预期候选负例 test_app.VALUE=999 的捕获与主套件失败分开，全部完整日志保留。最终不变量：五个保护文件不变、三份原测试共 77 方法断言保持。
- GitHub 已普通快进 `ace189d..56018de`，ls-remote 与本地精确 SHA 相同。CI `39930617746` 已启动；尚未把它写为通过。最终服务器候选同为 56018de，197运行/406验证文件一致，1775成员完整副本迁移与真实default worker初始化再次通过，正在全量；线上仍旧版，未激活。


- 失败现场范围澄清：首轮 Linux policy 错误的 guard 产物只有完整堆栈，没有当时的临时数据库（夹具 temp 是局部变量，旧诊断器未捕获 self.root）。因此不能宣称已保留原 Linux DB。另以 273dc97 原测试、相同产品字节和规范路径独立准确重现，cleanup 前保存完整合成根、原 DB、65 schema 对象、31 表全部 15 行及 SQL dump；副本完整性/全行一致、12 份证据哈希验证通过，无残留进程。位置 `../部署包/tenant-policy-path-review-20261023/independent-reproduction-273dc97/`，明确标记独立重现，非原 Linux 现场。

- 最终服务器全量 `56018de`：Python 3.12.3，`python3 -m unittest discover -s tests`，**1523 tests / 1509 通过 / 14 可选 MCP 跳过 / 0 失败错误，658.502s，退出 0**；406 个验证文件不变。完整日志 6282 字节 / SHA256 `4a001112c6fd0a28d92b2f714bbe763c0e32f4bd725a9779a98eb1c665911810`；26/26 合成真实密码 HTTP 检查通过，临时进程和数据清理。
- 发布：197 个运行文件精确对应 `56018de`，17:23:55 CST 切换。完整备份 `/opt/webuddy/backups/pre-56018de6c3bc-20261023T092352Z`，1775 个 data 成员和三个项目 277/37/20 成员读回一致；唯一现有个人账号 `li` 显式初始化为所有者/default 管理员，原 users.json/session.key 字节及 45 张业务表全部原行/结构保持，仅增加独立 control。旧会话失效，需重新登录。
- 上线验证：10 项启动检查；17:25:58 CST（122.264s 后）18 项公网/回环匿名及旧 token 拒绝通过，default worker 的 PID/start_ticks/socket/cgroup 保持；17:26:00 active/running、重启 0、启动以来 error 日志 0。原业务/非 DB/项目文件与配置、Caddy、另一应用不变。主代理再次读回 11 份完整证据并逐文件 SHA/长度校验，17:29:29 Mac 独立 TLS 四项通过；未伪造生产个人会话或代人业务确认。
- 最终 UI 原始截图共 7 张、387298 字节，源图与仓库副本逐字节一致，无转码或降采样；主代理已亲自打开复核。最终保护文件不变、三份既有测试共 77 方法断言不变；后两提交只修测试夹具，不改产品代码。
- GitHub CI `39930617746` 于 17:29:06 CST：8 个成功（两组 Linux 全量、四组快速检查、两平台安装），Windows 3.11/3.13 全量仍运行；不宣称全平台 CI 全绿或 Windows 网关兼容。完整快照和时间已保存。
- 最终只读核验 17:30:57 CST：197 运行文件 SHA/长度/模式保持，gateway PID 与 default worker PID/start_ticks 保持，服务重启 0、错误日志 0。文档链接/JSON/原图哈希及 `git diff --check` 检查通过；当前收尾只提交 docs/audit 与原始截图，不改产品/测试，不因记录再次重启；本机接入记忆已更新，完整回执留在外部发布目录。
- 待确认/后续边界：本轮无阻塞；新租户执行环境、SSO/MFA、邀请/配额、跨租户知识发布协议未实现；所有受管租户公开分享/签收/捕获回调/预览禁用，普通成员 Git 证据核对暂受限。真实 Claude 与模型效果、生产登录后业务操作未验证。启用控制面后故障应停止服务并保留当前数据，不能回退到忽略 ACL 的旧程序或覆盖新业务数据。

## 2026-10-23：正式组织工作台与任务交接（第一批）

- 当前项：O1/O2 正式实现；状态：done（实现 `911e42d`，2026-10-23 12:06:23 CST 已上线）。用户要求“完成更具体的修改”，本轮接入真实任务工作台、交接/接收/退回、下一责任人、阻塞/恢复及研发→测试→交付路径；下列中间状态按发生顺序保留，最终结果见本节末。
- 开始：`iteration/context-pack-v2` / `033e3dd`，工作区干净；已读根 AGENTS、进度和最近十条提交。沿用验证后自动提交、GitHub 推送和生产部署授权；不重建分支，不改 Git 配置，保留历史 stash。
- 实施划分：后端新增独立 handoffs 模块及事务/迁移/并发测试；前端接现有工作台并加入交接详情；主代理负责真实 API、队列投影、集成验证与发布；独立审查身份、快照、锁序和回滚。使用计划执行、既有界面改造与交付前验证流程。
- 约束：交接不改变工单 assignee/status、独立复核人、MOVES、验收/采用/关单状态；“收到材料”只记接收事实。所有写入需要真实个人会话；共享令牌、显示名和 Agent 标识不能代人接收。仍为共享工作区，不宣称新增项目 ACL。
- 数据合同：交接绑定需求、项目来源与固定候选证据；revision 乐观并发、稳定 request_id 重放；交接/审计事件/回执同事务；不在写事务中调用会隐式 commit 的 schema/Store.x 或进行 Git/HTTP/模型调用。来源失效拒绝接收，保留完整历史；发送人/当前负责人可有理由撤回避免永久卡住。
- 展示：五种交接目标阶段与“未登记阶段”；未建立交接的历史等待为未知，不从 updated 倒推。原四类队列计数保留兼容，待接手单独计数；完整详情沿用真实团队候选状态与证据，阶段/角色不是权限。
- 验证计划：后端定向、HTTP 身份与全路径、503+队列分页、UI JS/交互/窄屏、独立代码审查；冻结提交后全量；部署精确清单、数据库副本迁移、备份/回滚路径、上线与延迟健康检查。真实 Claude 启动、Windows 与可选 MCP 的既有边界单列，不冒充本轮已解决。
- 实现已落地：新增 `handoffs.py`、`ui_handoffs.py`、四个测试文件和使用说明；扩展 Store 初始化、HTTP 路由、workspace 投影及 UI。仅新增四张交接表，保留旧工单/复核/验收模型。
- 审查修复：旧 events.ts 保持既有本地格式，专表 UTC；只读参考项目不发起新交接；来源 token 单独变化可保稿重绑；切任务期间提交结果正确解锁；成功提交后详情刷新失败不重复提交；页面下一责任人与实际候选状态一致；附加读异常仍返回持久成功回执；停用账号明确提示。
- 定向：后端 26 + 工作台新增 8 = 34 tests / 1.959s / OK；既有团队/知识/组织知识 55 tests / 17.804s / OK；HTTP 真回环六项 / 3.621s / OK；旧 workspace 四项通过。一次组合命令用 `tests.test_ui_handoffs` 导致同目录 helper 导入失败，前 44 项通过；按既有 UI 测试的 `PYTHONPATH=tests:.` 单独重跑，不改断言。UI 最终 18 项行为测试通过。
- 全量 doing：冻结 283 个实现/测试等文件 SHA，`NO_PROXY='*' no_proxy='*' TMH_UNDERSTAND=rules PYTHONPATH='<local-validation>:.' python3 -m unittest discover -s tests`，预期 1390 项。完整日志、跳过清单与失败现场保存在仓库外 `部署包/handoff-workspace-20261023/local-validation/`。全量期间不修改受测实现/测试。
- 发布准备：11:30:37 CST 严格 SSH 核实现役仍 a8e22b7、active/running、重启 0；接入记忆、0600、公钥指纹已核对。复制旧部署工具到独立新目录，更新前版、4 新表、release slug，补 learning/知识索引执行中检查；精确打包与迁移/回滚故障自检通过。生产尚未切换。
- 浏览器实测补修：成功后空表单错误继承旧 revision，现成功回读后选当前可用操作；已接收/退回/撤回明确显示“不在等待”；退回/恢复的最近完整处理说明直接可见。新增行为回归后 UI 21 项通过。已跑首轮全量期间这三个 UI 文件变化，保留首轮日志但不作为最终版本凭证，最终冻结后重新全量。
- 最终定向验证：`PYTHONPATH=tests:. ... python3 -m unittest test_handoff_api test_handoffs test_workspace test_workspace_handoffs test_ui_handoffs`，**65 tests / 7.327s / OK**，完整日志 `local-validation/targeted-final.log`。实现与全部新增测试已审阅，`git diff --check` 通过，准备冻结提交并在本机和服务器各跑精确版本全量。
- 最终实现提交 `911e42d9a34d0df13115e8f9405fbdcf0297d4b5`。本机最终全量 **1393 tests / 414.665s / OK（skipped=16）**，即 1377 通过、0 失败/错误；283 个受测文件 SHA 均不变。完整日志 SHA-256 `e09049462b1375fdafd636bdf4918dd88c75124846e29fb247d17afc22ae4389`，见仓库外 `local-validation-final/verified-result.json`。前一轮 1390 / 432.078s / OK 保留，但因后续 UI 修复不作为发布凭证。
- 浏览器最终：Chrome 临时个人账号实际完成发送/撤回、测试接收、阻塞/恢复、交付退回；3 次交接、8 个事件，工单仍 new、负责人 alice、候选决策 0；390px 无横向溢出，控制台 warning/error 空。主代理亲自打开桌面总览/详情与手机原始图复核；6 张最终 JPEG 原字节复制到设计目录，共 643189 字节，未转码降采样。临时 60032 服务和自建页签已关闭。
- 精确发布包：191 个运行文件、390 个验证文件；本地 archive 读回与临时服务 **36/36 HTTP** 通过，合成数据已清理。首次 rsync 300 秒传输超时，保留 partial 并按精确文件允许清单续传；一次在 stage 完成前尝试 rehearse 返回文件尚不存在（未执行迁移），后续按传输→stage→rehearse→validate 顺序。尚未切换生产，不把准备失败当产品测试失败。
- GitHub 已普通快进 `033e3dd..911e42d`。续传完成后服务器 191 个运行文件、390 个验证文件及两份 tar 的 SHA/权限全部通过；数据库副本连续迁移两次幂等，原 41 表全部原列/原行与结构保持，仅增加预期 4 张空表，integrity_check=ok。服务器同提交全量正在执行，生产尚未切换。
- 服务器最终全量：Python 3.12.3、精确提交 911e42d，**1393 tests / 569.803s / OK（skipped=14）**，即 1379 通过、0 失败/错误；390 个受测文件保持。完整日志 SHA-256 `aea930cd143a95cdccf50b05e1b56d8afba68777561d40e42f7d8105af7dad5b`；36/36 合成 HTTP 通过，临时数据/进程已清理。原验证 SSH 连接未收尾，独立连接确认服务器已结束且完整 report 两项退出码均 0 后，只终止本机旧验证 SSH（客户端退出 255），不修改服务或伪造测试退出码。
- GitHub CI `39897236343` 两组 Linux 全量、两平台安装及四组快速检查共 8 项通过；Windows 全量仍在观察，不宣称 Windows 兼容。已开始完整备份及程序切换，结果随后补记。
- 正式上线：12:06:23 CST，`/opt/webuddy/app` → `/opt/webuddy/releases/911e42d9a34d-handoff-workspace-20261023/app`。191 个运行文件字节/长度/权限与提交相同，16 项启动后回环读取通过；原 41 表原列/原行、非 DB 文件、项目原文件和外部配置保持，仅新增四张预期空表。完整备份 `/opt/webuddy/backups/pre-911e42d9a34d-20261023T040621Z`，1775 个 data 成员及 277/37/20 个项目成员读回一致；没有恢复旧数据。
- 延迟验证：12:08:40 CST（启动约 137 秒后）32/32 公网/回环读取通过，数据库完整性 ok；12:09:49 CST 服务 active/running、重启 0、启动以来 error 级日志 0，191 个运行文件保持。Mac 独立 TLS 三项通过；Caddy 和同机另一应用保持。生产只读检查，不代人操作实际交接或验收。
- 证据归档：服务器 11 份报告/完整日志已全部下载并重新核验 SHA-256 与长度；设计目录保存原始截图、浏览器记录、合成数据证明、本机与服务器验证摘要和哈希清单。此次上下文恢复先读进度和最近十条提交；父目录没有 AGENTS，读取仓库内实际 AGENTS 后继续，仅补充记录，不重做实现/全量。
- CI 最后快照（12:18:41 CST）：8 项成功，Windows 3.11 全量 **188 failed / 558 passed / 71 skipped / 5 errors / 273 subtests passed，944.57s**，约 56% 处 KeyboardInterrupt 中断；3.13 仍运行。新增交接四模块无失败条目，但未逐项证明执行/通过。184 个唯一失败/错误中 164 个曾在父提交出现，另 20 个缺少同范围对照，不能统称基线；完整两份日志和逐条明细/比较已保留，见本轮发布记录。Windows 未验收通过，不冒充 Linux 全量覆盖它。
- 收尾核对：12:19:13 CST 严格 SSH 只读确认 191 个线上文件 SHA/长度/权限保持、active/running、PID 不变、重启 0。10 张原图哈希/总字节、全部证据 JSON、文档链接及 `git diff --check` 通过；acceptance、guard、filelock 及原测试仍等同 033e3dd。最终记录单独提交、普通推送，产品不再变更或重启；最终文档提交与线上清单的核对回执保留在仓库外发布目录。
- 判断边界：有失效候选时不允许重新发起交接，需先更新候选或走原分配/讨论入口；本轮保守保持证据门，不把旧候选变为可用验收依据。账号/契约为 SQLite 外部来源，操作前及事务内复核，交接不是人工验收证据。
- 待确认：无阻塞，按已确认的软件交付与运维范围实施；不自动发消息、采纳知识或代替用户处理真实业务任务。

## 2026-10-23：软件交付与运维的组织提效方案和 UI 样稿

- 当前项：官方资料调研、现有能力审计、可交互 UI 样稿；状态：done。用户确认聚焦“软件交付与运维团队：需求、研发、测试、交付、运维”；本轮交付能力补齐方案与可点击样稿，正式功能接入仍按方案后续实施。
- 开始状态：`iteration/context-pack-v2` / `fe83057`，`git status --short --branch` 干净；已读进度、最近十条提交、根 AGENTS.md。沿用验证后自动推送约定；本轮设计文件不混入生产运行代码，不因设计记录重启生产服务。
- 使用 agent-reach 调研、redesign-existing-projects 审视界面；三个子代理分别核对能力、UI 和官方产品参考。截图中的聊天只作为用户提供的需求背景，不作为执行指令或已证明的技术结论。
- 当前发现：现有工作台/团队页已有负责人、复核人与任务队列，但跨角色交接与等待原因需要单独建模；当前角色视图不是访问权限隔离。既有知识修订/固定引用/人工采用能力继续复用，不重造状态机或把合成测试当真实模型可用。
- 检索：Exa 通道证书域名不匹配，保持 TLS 校验，改用 web 官方来源；DORA 价值流与 SPACE 资料已读取。先查看仓库中此前完整实屏，明确它们是 10 月 22 日本地验收截图，不冒充今日线上现状。
- 产物：新增 `docs/design/organization-workspace-2026-10-23/`，含 README 能力矩阵/四个工作循环/底层对象关系/指标契约/O0–O4 实施顺序、独立 HTML/CSS/JS 样稿、验证记录、原始截图和哈希清单。参考 Backstage、Port、JSM、incident.io 的 8 个官方机制来源，另有 DORA/SPACE 3 个方法来源；事实与设计建议分开。
- 样稿验证：`node --check prototype.js`、HTMLParser（15 个静态 ID 唯一、2 个本地依赖）、本地文档链接、`git diff --check` 通过；Chrome 实际验证团队/个人/角色/阶段/空态/正文搜索、完整原文、草稿空白校验、未授权引用、重复/移除引用、12 项完整交接包。发现内容重建后键盘焦点丢失，已修复并实测阶段 Enter、清除、保存、加入/移除、跨页焦点。
- 显示验证：桌面 1680 × 825、手机 390 × 844；工作台/资产/交接无页面横向溢出，手机责任人与未知等待保留，控制台 warning/error 为空。原始 JPEG 按返回字节保存并实际打开检查，未二次压缩或重编码。直接 file 协议被浏览器安全策略拒绝，未绕过；已通过本机 HTTP 预览完成验收，未声称 file 协议可用。
- 发布核对：先读接入记忆、检查 0600/登记公钥指纹，再严格 known_hosts 只读 SSH；2026-10-23 01:44:10 CST 线上仍为 `a8e22b7`，188 个运行文件 SHA/长度/权限全部一致，active/running、重启 0。本轮不修改运行代码、不重跑产品全量、不因设计记录重启生产；沿用授权提交并普通快进推送 GitHub 当前分支。记录见本目录 `VERIFICATION.md` 与 `runtime-verification.json`。
- 命令边界：`agent-reach check-update` 返回 127（命令不存在），未安装软件；首次浏览器项目 label 定位失败后按实际 ID 完成检查。没有读取实际 data、私钥正文或生产外部配置，没有人工采用/确认/关单。当前进度记录与设计产物同一提交，不包含真实账号或客户数据。
- 待确认：范围已获答复，无阻塞；组织效率改善先定义指标与试点，不预设收益百分比。真实 Claude 启动、Windows 与 MCP 的已知验证边界仍保留。

## 2026-10-22：知识分类与评审闭环发布

- 当前项：推送 GitHub 与发布 Webuddy；状态：done（部署版本 `a8e22b7`）。用户本轮明确授权“推到服务器和github。每次修改完都是自动推送”，覆盖历史仅本地、不 push/部署限制；已在根目录 `AGENTS.md` 保存后续完成并验证后自动发布的约定。下列中间状态按发生顺序保留，最终结果见本节末。
- 开始状态：`iteration/context-pack-v2` / `924da09`，工作区干净，历史 stash 保留；GitHub 远端实查仍为 `3ecf977`，不改分支或 Git 配置、不强推。
- 发布采用已完成本机全量的知识闭环实现；另做服务器 Python 3.12 全量、合成 HTTP 和真实数据库副本迁移，全部通过才切换。保留原始日志、精确文件清单、配置与业务数据备份；业务人工确认边界不变。
- 已提交并推送 `59aea33`；GitHub 普通快进 `3ecf977..59aea33`，包含 8 个未推送的知识闭环提交与发布约定。服务器初查仍为 `3ecf977`、Python 3.12.3、active/running、无活跃运行，完整性 ok；私钥仅验证 0600 和公钥指纹，通过严格 known_hosts 登录及 sudo 核验，未输出或复制凭据。
- 精确版本包：188 个运行文件、383 个验证文件，Git 原始 blob 字节与权限逐项校验。本机重核 265 个完整测试清单文件与 `05022ce` 全量受测内容完全相同，完整日志 SHA-256 一致；临时服务 28 项 HTTP 检查通过并清理。部署脚本本机验证覆盖归档读回、BLOB 摘要、迁移保留记录以及切换后失败/stop 超时/回滚失败三个故障分支。
- 传输：初次 SCP 速度较慢，主动停止该文件传输进程，改用可续传的 rsync 无损传输压缩；不改变任何文件编码或像素，服务器接收后 188/383 个文件及两个 tar 的长度、SHA-256 和权限全部通过。首次未传完的包未 stage 或激活；候选准备阶段已核对不存在的评审回执应返回 404，修正的仅为新增部署 smoke 脚本期望值，没有改产品或基线断言。最终包与辅助脚本保留在本机 `部署包/learning-loops-20261022/candidate-59aea33-r2/`。
- 数据库副本迁移已完成：33 张原表的全部原列、原行哈希与结构不变；只新增预期 8 张空表；连续初始化两次幂等，integrity_check=ok，未初始化实际生产 Platform。服务器全量以清洁 HOME、无模型凭据和回环网络限定运行，原始日志/跳过原因/失败现场独立保存；正式切换仍等待其结果。
- 发布验证发现并修复两处测试问题，未上线失败版本：GitHub CI `39768074700` 的 Python 3.11 为 2 failed / 1313 passed / 16 skipped，3.13 为 1 failed / 1314 passed / 16 skipped（各 491 subtests passed）。新增 `test_learning_runs` 直接对自定义字典行工厂调用 `iterdump()`，Python 3.11/3.12 将键名当表名，报 `no such table: name`；服务器 3.12 已独立复现并保留完整现场。改用仓库已有 `dump_store` 一致性副本，仍完整比较所有表、行和结构，不改活连接行工厂。
- 第二处为旧 `test_org_knowledge_api` 的 Platform 夹具未还原进程全局 `bots.INTAKE`；pytest 定义顺序下，后续企微回调会访问已关闭数据库。新增真实 HTTP 夹具顺序测试在修复前稳定 2 个 subTest 失败，随后用 addCleanup/addClassCleanup 还原原回调所有者并关闭 HTTP/SQLite 资源；原 8 个 HTTP 测试方法断言 AST 全部保持。没有修改产品代码、超时或业务校验。
- 本机定向 `NO_PROXY='*' no_proxy='*' TMH_UNDERSTAND=rules python3 -m unittest tests.test_org_knowledge_api tests.test_phase1 tests.test_learning_runs tests.test_sqlite_snapshot`：**51 tests / 10.614s / OK**。完整 `fixture-isolation-red.log`、`fixture-fixes-green.log`、`fixture-review.json` 与两份 CI 完整日志均保留在上述部署工作区；本次修复独立提交后重新验证，不复用失败套件为上线凭证。
- 修复提交 `a8e22b7` 已普通快进推送。服务器 3.12 定向 pytest **51 passed / 15 subtests passed / 18.18s**；两份受测测试文件的 SHA 与提交一致。首轮服务器全量最终 **1331 tests / 539.432s / FAILED（errors=1, skipped=14）**，唯一错误为上述快照兼容性，383 个受测文件未变；失败完整日志 SHA-256 `c0d4fb4c895b103657a71f2abd582fcd7c882d65e17a2ad89e7ea9be213dda3d`，9 份初轮/修复证据下载并校验。另捕获到 `test_app.Test.test_value` 的 999 合成失败属于候选质量门的预期负例，不冒充外层套件失败或忽略真正的快照错误。
- 新候选 `a8e22b7` 的 188 个运行文件与初轮逐字节/权限一致；383 个验证文件再次核验，迁移副本第二次演练通过，全量已重新启动，新增隔离测试后预期 1332 项。GitHub CI `39769936344` 的两组 Linux 全量、两平台安装与四组快速检查已通过；Windows 两组全量仍在执行，未声明 Windows 兼容。
- 额外只读执行器检查：沿用实际服务 PATH 和原生 Claude 配置，在临时 HOME 下执行既有 5 秒 `--help` 能力核验，出现 TimeoutExpired；未运行模型、未更改参数/权限/生产配置。原生程序确为服务器 ELF 文件，无自定义命令或额外 args。保留检查结果，真实独立评审可用性与效果仍不当作发布测试已证明。
- 最终服务器全量：精确提交 `a8e22b750cfc161189c7aa354bd1f5c1a2a1199c` 执行 `python3 -m unittest discover -s tests`，**1332 tests / 543.623s / OK（skipped=14）**，即 **1318 通过、0 失败/错误**。14 项均缺少可选 MCP SDK；383 个受测文件保持一致。全量日志 SHA-256 `bdeb2d6b751c636ae5ce5e0f3eb988d167b7834c2b4aa82dc8edf4e57dd34d89`。新候选隔离 HTTP **28/28**，两次数据库副本迁移幂等。
- 正式发布：**2026-10-22 19:33:38 CST**，`webuddy.service` 启动新版；188 个运行文件与提交逐字节/权限一致。完整旧程序、data、外部配置与三项目 `.tmh` 已备份，1775 个 data 成员和 277/37/20 个项目成员读回一致；原 33 张表原列/原行不变，仅新增 8 张空表，非 DB 文件、知识文件及人工状态保持。备份 `/opt/webuddy/backups/pre-a8e22b750cfc-20261022T113336Z`；未回滚或恢复旧数据。
- 延迟检查：19:35:46 CST（启动约 128 秒后），**24/24** 公网 HTTPS 与服务器回环读取通过，active、自动重启 0、启动以来 error 级日志 0；SQLite 完整性 ok、旧数据与外部配置保持，Caddy 未重启，同机另一应用未动。19:43:19 CST Mac 侧 TLS 直连登录页 200、两项匿名 API 401，三项通过。生产浏览器新建/读取操作超时，只有页签 URL/标题可见，未取得本轮上线后的页面渲染证据；此前临时平台实屏验证仍为本地证据，不冒充生产实屏。
- 最终 GitHub CI [39769936344](https://github.com/auntunt/webuddy-pitch/actions/runs/39769936344)：8 个任务成功；Linux 3.11/3.13 各 **1316 passed / 16 skipped / 493 subtests passed**。两组 Windows 全量各 **168 failed / 495 passed / 71 skipped / 5 errors / 273 subtests passed**；工作流原有 Windows 非阻断配置未改。完整日志与逐条明细 `github-ci-39769936344/windows-failures.json` 保留，包含新 learning 模块的正文变化/登记标识错误，不能统称为已证明的基线失败，也不能宣称 Windows 兼容。
- 执行器边界复核：全量结束后的空闲状态，仍在原 **5 秒** `--help` 核验时 TimeoutExpired，结果见 `capability-check-idle.json`；未放宽超时、未绕过无工具隔离、未调用真实模型。**独立模型评审尚未验证可用**，不以合成执行器测试替代真实模型效果或启动能力。
- 证据与交付：[完整发布记录](../../audit/production-deployment-2026-10-22-learning.md)。本机 `部署包/learning-loops-20261022/candidate-a8e22b7/server-evidence/` 的 13 份报告/完整日志按长度和 SHA-256 读回一致；首轮失败证据另存且未覆盖。最终只提交并推送发布文档，运行文件与已上线版本一致，不为文档重复重启服务。
- 待确认/后续边界：无发布许可阻塞；Claude 原生执行器启动核验、Windows 新旧失败、可选 MCP 协议和真实模型质量/费用仍未通过，不自动采用业务知识、不代人确认。后续修改继续按根目录 `AGENTS.md` 自动验证、推送和部署。

## 2026-10-22：知识分类与评审闭环实施

- 当前项：最终全量验收与交付；状态：done。用户已授权按设计自动实施；实际分支 `iteration/context-pack-v2`，起点 `949d732`。开工工作区干净，无需 stash。
- K1 done（`c453245`）：三类只读目录、不可变修订、来源绑定、历史兼容。K2 done（`edc032a`）：独立评审及有界修订。K3 done（`a50f524`）：冻结成对评测、人工采用、授权与会话依赖。K4 done（`4cc8632`）：策略允许清单、统一界面及使用说明。最终全量 **1331 tests，1315 通过、16 可选依赖跳过、0 失败/错误**；无 skipped 实施项。
- 本轮使用 executing-plans 和 verification-before-completion；按技能将独立运行引擎、界面和日志并发部分交给子代理，共享目录中限定文件所有权，最后统一审查。
- 已核对：最近十条提交、设计、进度、Store/Runner/knowledge/learn/library/人工身份入口。`Store.x` 会自动提交，新事务不能使用它；旧经验日志仍为权威，新采用用持久化待办与幂等投影。
- 判断：首版参考工作流项目可浏览固定修订，模型评审启动暂沿用 development 限制，不暗中改变项目角色；自定义命令和额外 Agent 参数不能证明只读，评审拒绝它们。成本未知时保留未知；合成测试不等于真实模型效果。
- 约束：仅临时数据/仓库测试；不访问网络、不碰实际 data/ 或密钥、不启动日常端口、不 push、不部署。人工确认、guard、提交证据和已有状态迁移保持原边界。
- 待确认：无阻塞；真实模型质量、自动采用、定时任务和组织推广均不在本轮启用范围。
- K1 修改：新增 `tmh/platform/learning.py`、`tests/test_learning.py`；`Store` 启动时进行独立可回滚迁移。完整正文/证据清单和 SHA-256、工作区、HEAD、引用授权都固定；非 Git/未提交内容明确为工作副本清单，未伪称提交内容。Agent 修订不得变更事实登记头或生成块；历史确认不伪造机器通过。
- K1 验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_learning.py'` 9 tests OK；`test_org_knowledge.py` 10 tests OK；`test_memory_workspace.py` 24 tests OK。覆盖浏览文件字节/时间不变、完整长文、内容/源码/引用/工作区失效、跨项目拒绝、修订幂等、迁移/登记故障回滚。已人工审查新增模块、Store 差异和测试，`git diff --check` 通过。
- K2 期间发现并另行修复：独立 supervisor 自身超时退出后，外层 watchdog 发送取消写入已关闭的控制管道，抛 `BrokenPipeError`，把已有真实 timeout 回执误记成调度错误。失败现场保留 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-learning-timeout-failure-qxs7tkdz/scene`。新增屏障测试先等待真实监督进程退出再发取消，修复前稳定红灯；仅处理终端控制管道 EPIPE，仍必须读取完整、匹配的监督回执，缺回执/清理未知仍失败。
- 超时修复验证：`test_supervised_process.py` 15 tests OK；新确定性屏障用例连续 20/20 通过（20.621s）；`test_learning_runs.py` 27 tests OK（6.994s）。未放宽既有 .6 秒 timeout 或取消断言，完整输出字节与清理状态保持校验。重复脚本首轮类名拼错未运行，修正后实际执行完 20 轮。


- K2 done：新增 learning_runs.py、learning_facts.py 与对应测试；Store 增量迁移、Survey 显式选择独立评审，kb/org_knowledge 读取精确正文确认。独立无工具运行、逐条结论和冻结引用、最多 2 次默认修订/6 次调用/600 秒、幂等和内核锁所有权、完整步骤回执、取消/超时/恢复均已接通。事实原子发布先登记准备回执，失败显式重试或人工放弃；数据库与文件不假称单一原子事务。
- K2 验证：test_learning_runs.py 最终 31/31；test_learning_facts.py 28/28；旧 KB/组织知识及界面相关回归合计 64/64（含新 UI 22 项）。运行引擎真实超时/取消/崩溃恢复/所有权 fence 四例各重复 5 次共 20/20。收尾新增加三个确定性截止/租约测试，修复前 3/3 红灯，修复后通过；再补完整 _work 租约过期链路，从“running 且无 owner”修为 needs_resume，恢复不新增调用、不重置 deadline/calls。
- K2 已审阅：无模型调用持有数据库事务；发布和投影固定 Store→KB/ledger 锁序；历史成功回执只补审计，不因新正文/新来源而重新发布旧版本；来源过期保留人工指针以便撤销，实际使用另行校验。已确认/撤销均只面向确切修订，历史确认未补造机器通过。当前本机原生 Claude 帮助检查失败，测试用合成执行器与真实受管子进程证明机制，未执行真实模型评审。
- K3 doing：评测样本、断言、基线、模型和输入已冻结；正在完成实际任务上下文/旧会话与评测输入一致性审查。发现并修复 token 采集竞态、同一 outbox 同时重放、生成样本升级为留出、改断言复用样本、策略改名绕过样本历史及撤销经验回退 legacy。相关 6 个并发/屏障用例各重复 20 次，共 120/120。
- K3/K4 集成核对：平台任务与策略评测共用上下文过滤和预算渲染；工单上下文预览接入同一边界；知识登记的读取与分类移入 KB 锁，防止撤销后被误当成旧式未管理页面。完整上下文省略记录留在运行回执，不截断原知识正文。已采用事实生成下一草稿时只复制经核实的人工状态头，必须重新评审和采用。
- 当前定向验证：`NO_PROXY='*' no_proxy='*' PYTHONPATH='<离线辅助目录>:tests:.' python3 -m unittest test_learning test_learning_api test_learning_context test_learning_decisions test_learning_eval test_learning_facts test_learning_ledger test_learning_runs`，**166 tests / 17.439s / OK**。新上下文测试最初夹具缺少必需 summary 字段导致 7 个准备阶段错误，仅补齐合成夹具后通过；未改生产校验或既有断言。
- 集成回归：新界面、知识 Agent API、项目库事务及原记忆界面合计 **64 tests，63 通过、1 个可选依赖跳过**。首次命令误写不存在的 `test_ui_memory_workspace`，其导入错误现场保留；改为实际模块 `test_ui_memory` 后单独执行 **15/15 / 1.757s / OK**，没有重复全部用例掩盖错误。
- 定向原始日志及后续全量现场目录：`/private/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-learning-final-g7ug78bx`，保留完整输出、失败捕获与回环限定 sitecustomize；不联网安装依赖。
- 已实际打开本地临时平台页面并检查：项目选择、三类筛选、事实全文/来源详情、机器状态与人工状态分列；无通过批次时采用按钮禁用；策略仅显示 4000–12000 上下文预算；浏览器无 warning/error。仅使用合成账号与临时端口 56208，未启动真实模型或采纳任何业务知识，检查后已关闭页签及临时服务。
- 当前提交：K1 `c453245`；独立超时修复 `5d3d1a1`；K2 `edc032a`。最终会话依赖检查及全量回归完成前不声明 K3/K4 完成。
- 最终回执审查：过滤失效页面后，评测回执的分区统计仍保留过滤前计数；新增断言先复现 `1 != 0`，随后按实际保留项重算计数/字符数。`test_learning_context` + `test_learning_eval` **22/22 / 1.415s / OK**，原文与完整省略清单均保留。
- 会话检查初版：新增独立祖先回执，逐次检查已注入事实/经验/共享副本/策略；继承会话与复制的旧结论均保留依赖，修复追加上下文、服务繁忙重试和会话丢失回退也重新核对。新会话模块 19 项及既有续会话/繁忙重试/分文件修复 3 项合计 **22/22 / 7.154s / OK**。随后总审发现固定提交只读检查与主工作区策略的区别会造成误拒，新增真实 delivery_source + active 策略测试已准确复现，正在修复其实际上下文 root 绑定。
- K3 done：`learn.py` 统一可重入进程锁与带完成标记的日志投影；`learning.py` 保存完整经验修订及样本历史；新增 `learning_decisions.py`、`learning_eval.py`；`agents.py` / `fixloop.py` 接入实际使用和会话依赖；`server.py` 提供严格个人决定与 Agent 草稿/运行的独立入口。对应新增/扩充 learning、ledger、decisions、eval、context、sessions、API 和 delivery source 测试。为使每个提交具备完整依赖，策略运行及 API 基础随 K3 提交，K4 提交页面与操作说明。
- 固定工作区修复：策略回执保存实际 `context_root`；固定 checkout 只能由同一运行的来源记录、提交、工作目录、候选/方案归属共同证明，不能凭任意路径获准。原工作区已采用策略不继承到临时只读 checkout，后者按默认 6000 预算执行；采用撤销后旧冻结输入仍被拒。最终 `test_learning_sessions` 19 + `test_delivery_source_runner` 10，**29/29 / 6.105s / OK**；新增真实进程正例、三个冒用目录反例、准备后真实撤销决定反例。完整日志 `delivery-policy-sessions-green.log`；首轮红灯工具原文转存 `delivery-policy-red-from-tool.log`，文件明确区分转存与重跑。
- K3 审阅：逐段核对后端、会话、API 及对应测试 diff，`git diff --check` 通过。基线已有 delivery source 7 个方法和 supervisor 14 个方法的全部断言 AST 未变；新修复另加测试。`tmh/acceptance.py` 与 `tmh/guard.py` 全文件等同 `949d732`，人确认、保护清单、状态迁移与提交证据约束均未放宽。
- K4 doing：界面 `ui_learning.py` / `ui.py` / `ui_memory.py`、22 个新界面用例，以及设计状态和 `docs/knowledge-learning.md` 使用说明已完成；待最终全量验证后封存结果。
- K4 done：已读回完整操作说明与设计，核对页面入口、三类流程、执行器限制、机器/人工分离、策略范围、撤销恢复与未验证事项。22 个新界面测试和实际浏览器检查均已通过，内容/错误转义、异步切换与草稿保留已覆盖；界面检查后没有再改 UI 代码。K3 提交 `a50f524`；K4 与本记录一并提交。下一步冻结源文件清单，再运行一次全量，发现问题单独提交修复。

### 本轮全量验收与收尾

- 首轮受测提交：`4cc8632`；执行 `NO_PROXY='*' no_proxy='*' PYTHONPATH='<离线辅助目录>:.' python3 -m unittest discover -s tests`。**1331 tests / 401.584s / FAILED（errors=2, skipped=16）**，即 1313 通过、2 错误、16 跳过；完整日志 `full-unittest.log` 保留。265 个受测源文件与冻结清单逐个 SHA-256 一致，运行期间未编辑实现或测试。
- 两个错误均为本轮新增会话检查后需要更新的旧测试夹具，不能记为基线已知失败：① `test_project_bootstrap` 仍 patch 已移走的 `fixloop.build_prompt`，未进入断言即报 AttributeError；② `test_run_handoff` 的模拟父会话只有 mode/ended，没有真实运行 id，新祖先回执读取时报 KeyError，现场数据库记录为 failed/id。失败现场分别为辅助目录内 `failure-b1882075bb2947419122d1a522ed0ac5`、`failure-42c90e91b15e4fe9927fa63d6606d8a6`，已保留完整 traceback 和后者临时数据库。
- 修复范围仅这两个测试文件：替换新的上下文构造接点，并增加它未被调用的断言，确认交付仍使用原冻结材料；创建真实合成父运行，再检查完整需求、resume 和祖先回执。保留全部原断言和时间预算，未为测试放宽生产会话校验。
- 定向命令：`NO_PROXY='*' no_proxy='*' PYTHONPATH='<离线辅助目录>:tests:.' python3 -m unittest test_project_bootstrap test_run_handoff test_learning_sessions`，**42/42 / 12.395s / OK**；完整 `handoff-fixtures-green.log`。已审阅两个 diff，准备单独提交并重新冻结清单后跑全量。
- 首轮跳过原因逐条保存 `first-full-skips.json`：MCP SDK 缺失 14 项（知识 Agent 发现 1 + workbench 13），cryptography 缺失 2 项；未联网安装依赖。已有 HTTPError/SQLite/socket ResourceWarning 和 fork DeprecationWarning 原样保留，未过滤日志。
- 夹具修复已独立提交 `05022ce`，K4 为 `4cc8632`。第二轮全量正在运行，命令与首轮相同，日志改为 `full-unittest-final.log`，265 个源文件冻结于 `final-tested-source-manifest.json`。临时现场捕获器额外覆盖 subTest 错误，原捕获器另存 `sitecustomize-first-full.py`；测试结果统计和断言不变。第二轮开始前工作区干净。
- 最终全量：相同离线命令在 `05022ce` 上执行完毕，**1331 tests / 402.846s / OK（skipped=16）**，即 1315 通过、0 失败/错误，退出码 0。16 条跳过与首轮逐条一致，详见 `final-full-skips.json`；对应测试文件等同设计基线，跳过没有由本轮改动引入。未新增失败现场，首轮错误和全部警告原文仍保留。
- 完整性核对：265 个实现/测试/模板/技能文件与第二轮启动前 SHA-256 清单全部一致。`acceptance.py`、`guard.py`、`filelock.py` 全文件等同 `949d732`；四个有改动的原测试文件共 44 个原方法，其原有断言 AST 全部保留，另增加 2 条断言和 4 个测试方法。结果保存 `verification-result.json`、`baseline-assertions-final.json`，未变更机器配置、真实 data/、凭据或日常服务。
- 日志校验：首轮 `full-unittest.log` 36903 字节 / SHA-256 `f09450be21f1bf0675e8a210fbde3ef304080fff666e233605d480a3f6193b2e`；最终 `full-unittest-final.log` 34756 字节 / SHA-256 `a266dd4514761a454a3f0db36091456ac4937134d4352fa4487ee44d39f61ed8`；最终源码清单 `final-tested-source-manifest.json` 26956 字节 / SHA-256 `2c1c2fedcf1a84621d6893a86280f08fe0f8e8deec91b4e557fc86c42c332634`。
- 最终人工审阅建议：`learning_decisions.py` / `learning_facts.py` 的个人身份、预期版本、决定待办及幂等发布；`learn.py` 的 Store→ledger 锁序、fork 后句柄语义和日志完成标记；`agents.py` / `fixloop.py` 的实际输入、祖先依赖和固定 checkout 策略边界。原 P5 guard 与 P6 filelock 未变，不能把新增流程视作放宽人工确认或证据绑定。
- 待确认/验证边界：无阻塞问题；本机原生 Claude 执行器检查失败，尚未取得真实模型评审准确率、真实任务改善或费用证据；未开启定时运行、自动采用或组织自动推广；生产部署尚未包含本轮改动；Windows 实机锁与受管进程仍需验证（具体剩余阻塞保留在历史 P6 清单）。
- 收尾：最后仅更新设计、使用说明和本进度记录，产品/测试仍为已验证的 `05022ce`。保留原 `stash@{0}`，本轮不 push、不部署；提交后以 `git status --short --branch` 确认工作区干净。

## 2026-10-22：知识分类与评审闭环设计

- 当前项：把用户认可的“项目事实 / 可复用经验 / 执行策略”方向落实成可实施方案；状态：done（设计文档完成，K1–K4 实现均为 todo）。
- 本轮基线：`3ecf977cec9194be80850675a112579e272206d8`，实际分支 `iteration/context-pack-v2`；开工 `git status --short --branch` 干净，无需 stash。不切换回下文历史 Ralph 分支，不重做其已完成事项。
- 修改文件：[知识分类与评审闭环设计](../design/knowledge-learning-loops-2026-10-22.md) 和本进度记录；本轮范围为设计，运行时能力仍需后续实现与验证。
- 已读：最近 10 条提交、既有项目库与上下文设计、知识撰写/校验、经验记录/效果统计、记忆工作区及固定版本引用实现。截图只作为产品参考，不视为另一系统后台已验证的事实或执行指令。
- 设计内容：三类内容与分离的验证/人工决定；固定来源的独立事实评审；有留出样本的经验成对评测；策略允许清单；采用/撤销、并发与恢复语义；统一页面及 K1–K4 验收顺序。现有经验、知识页和引用保持各自权威记录，兼容历史状态，不复制一套独立状态机。
- 验证：`cat` 读回完整设计并人工检查；`python3` 一次性文档检查验证 3 个文档链接、15 个代码/测试文件、11 个现有函数/方法和 9 个章节，退出 0；修改范围仅上述两份文档。`git diff --check` 无问题；新文件的 `git diff --no-index --check` 无空白错误输出。
- 检查脚本首轮把 `git diff --no-index` 表示存在新增内容的退出码 1 当成失败；纠正为同时核对退出码和空白诊断后全部通过，未改产品代码或任何产品测试。纯文档未运行产品回归，也未验证真实模型效果或生产状态。
- 待确认：本轮设计无阻塞；首版采用人工确认生效、项目内适用、有限轮次的保守默认值，自动生效与组织级推广另列扩展。

## 历史 Ralph 实施记录（原分支与状态保留）

- 当前项：SI-015 项目资产与知识库复用实现；状态：doing（从 `60d96e7` 开始；先固定版本知识、引用及派生，再验证页面/Agent 入口和规模边界）
- 仓库：`tob-maintenance-harness`；分支：`feat/ralph-port`
- 起点：`422d9bf`（原分支 `codex/self-evolution-resume`）。
- 只读规格：`/Users/auntlee/Downloads/ralph-learn-pack/codex-prompts.md`，不复制进仓库。
- 恢复顺序：先读本文件和 `git log --oneline -10`，从第一个非 done 项继续；已经 skipped 的项保留原因，不重复执行。
- 初始工作区有 6 个修改文件、1 个未跟踪测试；已执行 `git stash push -u -m 'ralph-port-preflight-2026-10-19'`，保存为 `stash@{0}: On codex/self-evolution-resume: ralph-port-preflight-2026-10-19`。交接时保留 stash，不自动恢复。
- 初次在父目录执行 `git status --short --branch` 报非 Git 仓库；定位子目录后重新执行成功，再 stash、新建分支；未改 Git 配置。
- 不变量：离线；不碰 data/、密钥、证书；不启动日常 8791/8793 服务；不 push；不削弱人确认、证据绑定、钩子、保护清单、状态迁移或基线断言。
- 执行：逐项仅跑指定测试；每项最多 3 轮失败修复，仍失败则撤销该项未提交实现并记 skipped；最终才跑全量。

| 项目 | 状态 | 提交 | 说明 |
|---|---|---|---|
| P1 | done | `407d196` | AGENTS 区块预算与命令路由 |
| P2 | done | `eac0e2f` | 非阻塞任务尺寸提示 |
| P3 | done | `d761bb6` | 经验卡固定开销 lint |
| P4 | done | `ff532c8` | 已知死路及来源验证 |
| P5 | done | `c594ee5` | 结构反馈草稿与人确认 |
| P6 | done | `a06c09e` | 可替换文件锁与 Windows 阻塞盘点 |

## P1

- 状态：done。
- 阅读范围：`tmh/install.py`、两个模板、`tests/test_tmh.py`。
- 计划改动：`templates/AGENTS.block.md`、`docs/agent-commands.md`、`tests/test_tmh.py`；如安装后命令指引需要随工具分发，在 `tmh/install.py` 补对应复制。
- 命令/结果：`git status --short --branch` 确认旧改动；stash 成功；`git switch -c feat/ralph-port` 成功；工作区干净。
- 差异/假设：规格“单会话只做一项”由本次用户连续完成六项的指令覆盖；不请求暂停确认。
- 待确认：无。
- 实际改动：`templates/AGENTS.block.md` 从 7832 降至 2975 字节（≤3584）；新增 `docs/agent-commands.md`，`tmh/install.py` 随安装复制到 `.tmh/docs/`；`tests/test_tmh.py` 增加预算、硬规则与分发一致性验证。全部硬规则保留，证据绑定提交和禁止绕过钩子明示。
- 验证：`python3 -m unittest discover -s tests -p 'test_tmh.py'`，46 tests，OK（5.080s）。临时 Git 仓库运行 `install(root, ['claude', 'codex'])` 后实际读回 AGENTS.md 全文，确认 CLAUDE 引用和命令文档字节相同。`git diff --check` 通过，逐段审阅实现 diff 和新文档。
- 修复轮数：0；一次 patch 格式校验失败，未写入任何文件，改为单次更新后成功。

## P2

- 状态：done。
- 范围：`tmh/acceptance.py`、`tmh/cli.py`、`tmh/platform/epic.py`、`tests/test_acceptance.py`、`tests/test_platform.py`；规格提到 `intake.py` 时只按需定位入口。
- 计划：尺寸提示与 AC 放行逻辑分离，CLI 检查/进入实现和父单日志都提示；不自动拆分或改契约。
- 命令/结果：已完成 acceptance 全文件、platform 的 big_requirement 筛选及临时仓库 check 输出核对，见下方记录。
- 待确认：无。

### P2 验证记录

- `python3 -m unittest discover -s tests -p 'test_acceptance.py'`：14 tests，OK（2.423s）。临时仓库 CLI check 显示 9 条 AC 与并列标题提示，退出码仍为 0。
- platform 首轮 3 tests 报错：访问回环测试服务得到 HTTP 502，项目列表为空；推断为继承的代理把 localhost 请求转发。改用仅当前测试进程 `NO_PROXY='*' no_proxy='*'` 重跑，禁止回环请求走代理；未改测试或产品逻辑。
- 重跑 `NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_platform.py' -k big_requirement`：3 tests，OK（1.383s）；仅有既有测试资源关闭警告。后续测试沿用 NO_PROXY，未改机器设置。
- 实际改动：上述 5 个文件。`size_warnings` 与 `ac_problems`/`advance` 放行条件隔离；CLI check/成功进入 implementing 打印提示；epic 在建子单之前用 `_edit`/`_log` 记录，保留正常创建流程。
- 假设/阈值：peers 传其他契约原文、排除自身与无有效 AC 的样本；≥5 份时按条数或“条款+检查方式”字符量达到中位数 2 倍提示；少于 5 份用 >8 条 / >1600 字。后者相当于 8 条较长的约 200 字条款。标题并列、新建数 >3 独立提示；文件数量只匹配明确数字或反引号列表，避免猜测。epic 同一批其他 item 作为 peers。
- 审阅：已逐段检查 git diff；`git diff --check` 通过；基线断言、状态机、人确认和证据逻辑未改。失败处理：环境修复 1 轮，无实现修复。

## P3

- 状态：done。
- 范围：`tmh/platform/learn.py`、`tests/test_lessons.py`。
- 计划：只过滤含全局固定动作的经验卡提示注入，返回命中原句；保留人的原文与现有状态，不改变存储格式。
- 命令/结果：`test_lessons.py` 已通过，见下方记录。
- 待确认：无。
- 实际改动：`overhead_flags` 匹配 fix/verify/anti 的每次/每轮必须、开工前先、改完一律，以及 always + 动作、before/after every/each task/run/session/change/iteration/commit；排除有场景条件的建议和非指令的事实句。匹配原句仅在 add/edit 返回值携带 flags，不写入 lessons.jsonl 新字段。
- `relevant` 对本项目与已采纳共享卡均过滤；按既有 `_note_once` 模式每工单每轮人裁决前记录一次 overhead 日志。状态、信任和失败计数规则不变。
- 代码差异：原 edit 和日志折叠均截断到 800 字，edit 还 strip；为满足“人的原文逐字保留”移除这些处理，字段/存储格式不变。长文本测试覆盖末尾命中句及空白/换行完整保存。
- 验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_lessons.py'`：16 tests，OK（0.040s）；已审阅 git diff，`git diff --check` 通过；实现修复 0 轮。
- 边界：规则有意偏保守，未显式表达全局动作的说法可能漏报；未改页面/CLI 展示层（返回值已提供 flags）。

## P4

- 状态：done。
- 范围：只读 `docs/self-improvement/` 的 verification 记录及规格允许的 STATUS，修改 `skills/legacy-feature/SKILL.md`、`skills/acceptance-l2/SKILL.md`、`tests/test_tmh.py`，新增 `docs/dead-ends.md`。
- 计划：只纳入验证记录能直接支持的结论；保留环境限定；表格不含客户标识、地址、报价或凭据。
- 命令/结果：test_tmh 和 3 条来源抽查已完成，见下方记录。
- 待确认：无。
- 实际改动：新增 15 行文档、9 条死路；两个技能正文各增加按场景指向，description 未改；新增来源文件存在和行数预算测试。
- 来源抽查：① external-candidate 的“保留的失败与修复”第 1 条直接记录沙箱 TCP/Git 拒绝；② runtime 的问题表第 1 条记录父退出 0 仍有子孙与管道阻塞，配原始红灯日志；③ harness2 的基线/候选表及后文明确双方进程退出 0 但基线业务失败。另逐条核对 preview-health 的直接 2xx/无重定向约束、裸预览 401、Git archive 和优化模式 assert，来源均支持表述。
- 差异/假设：规格举例提到 Node/原生 Codex，表使用证据直接证明的“POSIX 包装父进程”表述，不推断特定包装器；沙箱限制仅针对记录中的 workspace-write 环境。
- 审阅：读回完整表并核对 5 列，无客户名、地址、报价、凭据；逐段审阅 diff，`git diff --check` 通过。未访问链接或证据目录之外的运行数据。
- 验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_tmh.py'`：47 tests，OK（6.079s）；修复 0 轮。

## P5

- 状态：done。
- 范围：`tmh/acceptance.py`、`tmh/cli.py`、`tmh/guard.py`、`tests/test_acceptance.py`；只读规格列出的 `tmh/task.py` 与指定钩子测试。
- 计划：missing-requirement/dependency 产生非任务草稿；同源最多两份未确认；人确认入口复用 `_human`，guard 增加拦截；不改 MOVES/HUMAN_ONLY、不接平台。
- 命令/结果：test_acceptance、指定 guard 钩子及临时仓库模拟上报→人工确认已完成，见下方记录。
- 待确认：平台接入留作建议，不在本次实现。
- 首轮：19 个 acceptance 测试、10 个 GuardAndVerifyTest/AgentHookTest 均通过。补并发及确认回执失败恢复两例后 21 个测试通过（3.003s）。
- 手工流程发现绝对草稿路径 `/var/...` 与 root.resolve() 的 `/private/var/...` 别名不一致，确认后返回相对路径报 ValueError；修复第 1 轮：先检查限定目录和符号链接，再规范化 path；新增用绝对路径确认的覆盖，重新跑指定测试和手工流程。
- 最终验证：`NO_PROXY='*' no_proxy='*' python3 -m unittest discover -s tests -p 'test_acceptance.py'`：21 tests，OK（3.611s）；此前新增两例的中间版 21 tests 也通过（3.003s）。`... -p 'test_tmh.py' -k GuardAndVerifyTest -k AgentHookTest`：10 tests，OK（1.530s），包括 dangerous_bash 及 Codex hook。
- 临时 Git 仓库 CLI 手工流程复跑成功：上报→读回完整 Markdown→用测试夹具模拟人工入口→读回确认人/新任务号；新任务 T002 为 draft_contract、confirmed_by=None，源任务未迁移。不是实际任务或真人验收操作。
- 实际改动：4 个授权文件。草稿示例 `.tmh/acceptance/proposals/T001-1.md`，首行 JSON 注释标记来源/类型/状态，正文含建议标题、待补 AC 与完整原话（围栏长度避开原话反引号）；确认后原文保留并追加人名和任务号。
- 收敛：同来源两类合计最多 2 份 pending；跨进程 mkdir 写锁防并发穿透，异常释放；损坏草稿保守拒绝；重复确认拒绝；回执写失败重试复用已建 draft。进程被强杀可能留下 `.write-lock`，需人核实后清理（不把该锁用作崩溃恢复所有权证明）。
- 审阅：已逐段看实现/测试 diff，`git diff --check` 通过；guard 仅追加 propose-confirm 模式；MOVES/HUMAN_ONLY/AGENT_ENV、ALWAYS_PROTECTED、原确认/关闭拦截及证据链未改。共 1 轮实现修复。
- 平台建议：以后在父单展示结构反馈待审列表，人在正常身份验证入口选择采纳，生成 draft 后再走原有规格/AC 确认；不直接调用 `_follow_up` 自动放单。

## P6

- 状态：done。
- 范围：`tmh/platform/crash_recovery.py`、`recheck_operations.py`、`candidates.py`、`harness_probes.py`、`tmh/kb.py`，新增 `tmh/platform/filelock.py` 和 `tests/test_filelock.py`；只读指定相关测试及 Windows 剩余阻塞所需静态定位。
- 计划：POSIX flock / Windows msvcrt 第 0 字节锁统一接口，句柄/进程退出释放；保留 kb 的无原生后端 O_EXCL 回退；回执格式和恢复门槛不改。
- 命令/结果：filelock、新旧恢复/候选/探测指定测试与 KB 队列用例均已通过，见下方记录。
- 待确认：Windows 余项已列于后文，不扩展进程监管实现。
- 实际改动：新增 filelock + 12 个测试，4 个平台模块全部改用统一接口，KB 仅替换原生分支并保留 O_EXCL 回退。锁后端延迟加载，不存在 fcntl 时走 msvcrt；非阻塞竞争统一 BlockingIOError；Windows 在持有第 0 字节范围锁后初始化空文件，避免竞争写入；保留位置、非竞争错误和既有业务提示。
- 锁语义：当前所有调用点均排他；OS 句柄关闭/进程退出释放。Windows blocking=True 以非阻塞调用循环等待，避免 CRT 内建重试上限。所有权判断不使用 O_EXCL、历史 PID 或残留文件存在性。回执/数据库结构未改，process_control/supervised_process 未改。
- 验证：所有命令仅带进程级 `NO_PROXY='*' no_proxy='*'`，使用 `python3 -m unittest discover -s tests -p <文件>`：test_filelock.py **12/12**（0.148s）；test_crash_recovery_api.py **6/6**（0.612s）；test_crash_recovery_independent.py **8/8**（2.875s）；test_recheck_operations.py **14/14**（3.901s）；test_external_candidates.py **11/11**（8.724s）；test_harness_probes.py **7/7**（13.909s）；test_harness_probes_independent.py **9/9**（10.721s）；`test_tmh.py -k test_queue_is_bottom_up_and_parallel_safe` **1/1**（0.141s）。修复 0 轮。
- 实测边界：macOS/POSIX 真锁、真子进程 kill 后释放；Windows 使用 mock fcntl=None/msvcrt 验证 4 模块实际导入与锁调用、竞争/阻塞/错误/初始化。没有 Windows 实机，不把 mock 当实机结果。
- 审阅：逐段查看全部 git diff（含新文件），`git diff --check` 通过。AST 对比起点 `422d9bf`：MOVES/HUMAN_ONLY/AGENT_ENV/ALWAYS_PROTECTED 完全相同，DANGEROUS_BASH 仅追加一条；4 个有改动的既有测试文件中所有原 test_* 方法 AST 均未变。

## Windows 剩余阻塞（只盘点，不改）

1. 已知范围外：process_control.run_process / supervised_process.run_supervised 仍显式拒绝非 POSIX，受管组、管道传递等仍需另行移植。
2. `tmh/platform/preview.py` 的 `_kill` 使用 os.killpg/SIGKILL，启动依赖 shell=True/start_new_session；默认 Django 命令为 POSIX 环境变量前缀语法。预览进程身份与退出判断也需要 Windows 专门验证。
3. `tmh/platform/fixloop.py:_local` 写死 `/bin/sh -c`；命令拼装使用 shlex.quote/POSIX cd 语法。Windows 本地构建需要平台适配。
4. `tmh/install.py` 的 Codex hook/MCP 使用 sh、`$(...)`、`/dev/null` 与 python3；pre-commit 为 `/bin/sh`。`project_bootstrap.py` 用 shlex.quote 生成测试/预览命令；原生 cmd/PowerShell 不能直接视作兼容。
5. `candidates.py` Git 的 `core.hooksPath=/dev/null`，以及硬链接、POSIX 可执行位/0600/0444 权限语义，需要在 Windows/Git for Windows/目标文件系统实测；这些属于条件兼容风险，不断言 NTFS 不支持硬链接。
6. 本次默认排他锁满足所有现有调用点；`exclusive=False` 使用 CRT read-lock 模式，Windows 可能比 POSIX LOCK_SH 更严格，不能保证多个读者并行。若后续需要真共享锁，应单独设计 Windows 原生共享后端；当前无该生产调用点。

## P1–P6 首次全量回归（历史记录）

- 状态：done；测试实现提交 `a06c09e`；运行 `python3 -m unittest discover -s tests`。仅测试进程设置 NO_PROXY，并通过临时 PYTHONPATH 的 sitecustomize 禁止非回环 socket/DNS；不改机器配置、产品代码或测试断言。
- 完整原始日志：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-port-validation-i4mv6w0e/full-unittest.log`；离线辅助文件也仅在该临时目录。执行前 `git status --short --branch` 干净。
- 全量结果：806 tests，369.499s，FAILED（failures=1, skipped=15），即 790 通过、15 跳过、1 失败。唯一失败为 `test_direct_invocation_lifecycle.DirectInvocationLifecycleTest.test_intake_timeout_or_cancel_cannot_apply_a_late_successful_answer` 的 cancelled 子场景，预期 cancelled，实际 failed/124（总超时）。已有 socket/SQLite/HTTPError 资源关闭警告保留在原始日志。
- 跳过原因：用 unittest loader 只读取跳过标记，未重跑用例；`test_sign.py` 两例缺 cryptography，`test_workbench_mcp.py` 十三例缺可选 MCP SDK。未联网安装依赖。
- 当前分支单例复跑：同一离线环境执行 `python3 -m unittest discover -s tests -p 'test_direct_invocation_lifecycle.py' -k test_intake_timeout_or_cancel_cannot_apply_a_late_successful_answer -v`，1 test，OK（0.750s）。
- 基线复现：只从 `422d9bf` 导出 `tmh/`、`templates/`、`skills/`、该单个测试至临时 `baseline-422d9bf/`，没有导出 data/ 或任何密钥/证书。132 个文件的 `git hash-object` 逐个等于起点 blob，排除 archive 替换差异；基线没有本分支代码。相同环境重复原单例（最多 30 次，首次失败立即停止），第 13 次（1.705s）在同一 cancelled 子场景、同一断言、同一 failed/124 信息失败。没有修改测试夹具、断言或 0.5 秒预算，没有人为注入延时。
- 原始复现日志：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-port-validation-i4mv6w0e/baseline-reproduction.log`。入口命令为 `python3 -`，循环用 `unittest.defaultTestLoader.discover('tests', pattern='test_direct_invocation_lifecycle.py')` 只筛选上述 testMethodName，每轮以 `unittest.TextTestRunner(verbosity=2)` 执行，失败 `sys.exit(1)`。基线进程退出码 1。
- 非本分支引入的证据：该测试、`intake.py`、`agents.py`、`process_control.py`、`supervised_process.py` 的当前字节全部与起点一致；基线原样复现同一失败。测试的 0.5 秒总预算可能先于模拟 cancel 耗尽，成功返回码断言因此先失败；该时序敏感问题留待单独处理，未放宽断言或修改范围外监管逻辑。按完成标准保留并披露这一基线失败，不用反复全量重跑掩盖它。
- 原始日志校验：full-unittest.log 为 23269 字节，SHA256 `73578db1fdec8a9ef114b3b33d17420379a975af5e7bba1df34e9eafc127e19c`；baseline-reproduction.log 为 6151 字节，SHA256 `6a200d4b09675d76f125665057493138149875f8da9918576f78f305f298cb8f`。
- 收尾只更新本进度文件，产品/测试实现仍为 `a06c09e`；原 stash 保留。人工审阅重点：P5 的 guard 新规则、propose_confirm 人身份/幂等恢复边界，P6 的 filelock 字节锁/关闭释放/阻塞重试及 KB 回退边界。

## 待确认

- P5 平台接入：建议新增人工待审入口，不直接从结构反馈调用 `_follow_up` 自动派发；本次不接平台。
- P5 异常中断若留下 proposals/.write-lock，需要人先核实无活跃操作再清理；不自动猜测所有权。
- P5 升级前若确认回执写入失败，已有任务使用旧版未引用的草稿快照，升级后重试会保守拒绝；需人工核对草稿和任务内容，不自动迁移或推定已确认。
- P6：上列 Windows 剩余阻塞；需 Windows 实机验证默认排他锁自动释放，尤其不同文件系统与进程退出路径。共享读锁的并行性不在已证明范围。
- intake 基线时序失败已在下节修复并通过全量；没有新增待确认事项，生产监管实现保持原样。
- 构建树 2 秒就绪竞态已在末节自然复现、保留完整现场并修复，通过稳定性与全量回归；本次没有新增待确认事项，原时间限制和断言均保留。更早那次无现场的具体启动阶段仍不作推断。

## 后续：intake 取消测试基线时序修复

- 状态：done；起点 `db4e957`，继续在 `feat/ralph-port`；开工 `git status --short --branch` 干净，原 stash 保留。独立提交标题：`test: 消除 intake 取消用例的墙钟竞态`（本记录与修复一起提交）。
- 用户授权：修复基线时序失败，不能削弱断言或简单放宽超时；先验证稳定性，再跑全量，更新本文件并单独提交；不 push，全程自动推进。
- 定位结论：原 fixture 给真实进程与最终结果处理共用 0.5 秒预算，只有 invoke 已返回 0 才注入 cancel；若系统调度/监管收尾先耗尽预算，cancel 根本没有执行。生产超时行为符合规则，缺陷在测试未确定“成功退出→取消/超时→最终采纳”的事件先后；用测试时钟固定该顺序。
- 阅读范围：`tests/test_direct_invocation_lifecycle.py`、`tmh/platform/agents.py`、`intake.py` 及底层监管/生命周期测试。
- 待确认：无。
- 修复范围：只改 `tests/test_direct_invocation_lifecycle.py` 与本文件；生产 Runner/intake/监管器没有修改。测试局部替换 `agents.time` 的单调时钟，其他墙钟及全局 time 模块保持真实；原 0.5 秒逻辑预算和传递给监管器的预算均保留并断言。真实监管器/子进程照常执行，测试适配层仅给它独立的 5 秒墙钟 watchdog，避免进程启动决定调用者测试的事件先后。
- 原 sleep 改为把逻辑时钟精确推进到 deadline，未延长被验证的逻辑超时；新增 deadline 前 1ms 成功、取消先发生后 deadline 到达、真实监管启动延迟 0.6 秒三个场景。原断言全部保留，另增加原进程 exited/0、预算值与 cleanup.complete 的断言。
- 红灯：先只加“慢监管启动”用例，在旧夹具下运行对应 `-k test_intake_cancel_after_slow_supervisor_startup_keeps_successful_process_evidence`，1 test，0.862s，按预期失败（failed != cancelled，124 != 0）。随后应用可控时钟夹具。
- 首次绿灯：`python3 -m unittest discover -s tests -p 'test_direct_invocation_lifecycle.py' -v`，15 tests，6.893s，OK；日志位于 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/intake-lifecycle-validation-vx3ag9qb/direct-green.log`。全部后续验证继承进程级 NO_PROXY 与该临时目录的离线 sitecustomize。
- 稳定性计划：原失败用例连续 100 次，完整 direct invocation 模块连续 10 轮；任何失败立即停下修复。再核对真实墙钟监管相关测试和完整回归；不修改已有真实超时用例。
- 稳定性结果：上述 100 次原用例 + 10 轮完整模块（150 tests），合计 **250 次测试执行全部通过**，119.306s，无跳过；每轮还验证两个 patch 已正确恢复，未泄漏给后续测试。命令为 `python3 <临时目录>/stability.py`，脚本与完整 `stability.log` 保留在同一临时目录。
- 回归敏感性：临时脚本 `regression_guards.py` 分别在内存禁用 Runner.stop_reason / Runner.cancel，原用例分别按预期产生 2 / 1 个断言失败，均直接拒绝“迟到智能体答案被采纳”；脚本确认失败类型后退出 0。没有改磁盘上的生产代码。这些是有意注入错误的负向实验，完整记录在 `regression-guards.log`。
- 审阅：逐段查看测试 diff；AST 对比 `db4e957` 确认原 **42 条断言全部原样保留**；`git diff --check` 通过，生产 tmh/ 内容未变。以下真实墙钟验证、全量均已完成。
- 真实墙钟验证：分别运行 `python3 -m unittest discover -s tests -p <文件> -v`：`test_process_control.py` 14 tests / 6.808s，`test_supervised_process.py` 14 / 4.535s，`test_run_lifecycle.py` 13 / 23.677s，合计 **41/41 通过**。没有应用本次测试夹具的 clock/supervisor patch；包含监管启动计入超时、真实进程树超时/取消和总预算跨调用等既有断言。日志 `real-deadlines.log`。
- 后续全量：**809 tests，374.241s，OK（skipped=15）**，即 794 通过、15 因可选依赖缺失跳过、0 失败/错误，退出码 0。运行 `python3 -m unittest discover -s tests`，仅继承进程级 NO_PROXY 和临时离线 sitecustomize。受测基线 `db4e957`，唯一测试改动文件 SHA256 `f1354cf3b708bffe8e838a0c8994fb6679b68ef6561fdcc7f3d7f7b65448d7c1`；测试结束后再次核对相同 hash。原始输出保存到同临时目录 `full-unittest.log`，既有资源关闭警告原样保留。
- 日志校验：`stability.log` 13563 字节 / SHA256 `aa31f211063c92fcb07eb37b93c88d4821772a3c149bf72d52ae746043e7bf22`；`full-unittest.log` 22075 字节 / SHA256 `b6510cbf468941461eafefd46f0fa92e7a9093156e5796b7822b0cd6d679dc34`。临时脚本、其他验证日志均保留，无压缩/截断。
- 收尾：只提交上述测试文件和本记录；无生产代码修改、无新的失败待处理，不 push，保留原 stash。

## 最终审查

- 状态：done；起点 `11078c5`，`feat/ralph-port` 开工干净。用户授权发现问题直接修复、验证、单独提交，不 push；原离线与不触碰真实数据/凭据的限制继续适用。
- 审查重点：P5 人工确认及 guard 可接受的命令形式、草稿与恢复边界；P6 所有权释放/Windows 字节锁/错误处理；11078c5 的测试时钟与 5 秒 watchdog 是否丢失真实超时覆盖。
- 已读进度与最近 10 条提交，完成代码审查、本地复现、修复与最终全量；待确认/已知限制见前文清单及各节。

### P5 审查修复

- 状态：done；提交 `1a11236`；修改 `tmh/acceptance.py`、`tmh/guard.py`、`tests/test_acceptance.py` 和本记录。以下确认行为全部是临时仓库内的合成测试，没有替人确认真实任务。
- 复现：5 个新增用例在修复前出现 11 个断言失败、1 个错误。① 当前 Codex 无沙箱环境仅有 `CODEX_THREAD_ID`，旧 `_human` 未识别；② guard 漏过前置选项、引号、转义和 `--to` 缩写等有效 CLI 命令；③ 引用原话的 `## 4.` 可被解析成新任务 AC；④ 确认回执失败后修改草稿，重试仍复用过期任务；⑤ proposals 目录符号链接可先写出仓库，最后才报路径异常。
- 修复：AGENT_ENV 只追加 `CODEX_THREAD_ID`；保留全部原始 DANGEROUS_BASH，新增 shell 分词和真实 CLI 参数解析的补充拦截；采纳原文逐行加 blockquote 前缀（测试反向去前缀逐字相等），不再参与契约章节解析；重试必须匹配原文快照；读写前拒绝草稿存储路径及文件符号链接。既有 MOVES/HUMAN_ONLY、保护清单、证据绑定不变。
- 验证：`python3 -m unittest discover -s tests -p 'test_acceptance.py' -v` **26/26**（5.872s）；`... -p 'test_tmh.py' -k GuardAndVerifyTest -k AgentHookTest -v` **10/10**（1.675s）。完整日志在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-final-review-b2e6yow4/` 的 `p5-red.log`、`p5-green.log`、`p5-hooks.log`。所有验证使用进程级 NO_PROXY 和临时离线 sitecustomize。
- 已亲自逐段审阅 diff，`git diff --check` 通过；原有测试方法和断言未改。guard 解析明确限于可见的字面命令，不宣称是任意 shell 求值的安全沙箱，运行时 `_human` 独立拦截仍保留。
- 待确认：旧版本回执中断留下的任务使用未引用的快照，升级后重试将保守拒绝，需人核对后处理；不自动改写旧任务或推定已确认。

### P6 审查修复

- 状态：done；提交 `21e68cd`；已复现 KB 原生锁获取把 ENOSPC 错误重试 1200 次并报“被占用”，以及 KeyboardInterrupt 时句柄未关闭。只收紧 `tmh/kb.py` 的异常分类/清理，保留内核所有权锁和无后端的 O_EXCL 旧回退；新增 3 个 `tests/test_filelock.py` 用例。锁后端和生产所有权回执没有改动。
- 红灯：`test_filelock.py -k kb_` 4 tests，2 failed；ENOSPC 被隐藏为 TimeoutError，打断后 fstat 仍成功。绿灯：`python3 -m unittest discover -s tests -p 'test_filelock.py' -v` **15/15**（0.396s），涵盖真实 POSIX 互斥/阻塞/关句柄/进程杀死释放、Windows mock 初始化及异常路径；`... -p 'test_tmh.py' -k test_queue_is_bottom_up_and_parallel_safe -v` **1/1**（0.210s），并行 KB 队列仍正确。日志 `p6-red.log`、`p6-green.log`、`p6-kb-queue.log`。
- 已逐段审阅两文件 diff，`git diff --check` 通过；只对规范化的 BlockingIOError 重试，其他异常立即抛出并关 fd。竞争的 1200 次/0.05 秒策略未放宽，底层字节锁/O_EXCL 回退未改。待确认仍为前文 Windows 实机验证/进程监管等剩余阻塞，没有把 mock 结果当实机证明。

### 11078c5 超时覆盖审查

- 状态：done；可控时钟与 5 秒 watchdog 只用于调用者事件顺序，不能单独证明真实 0.5 秒超时。补独立的 `tests/test_intake_wall_clock.py`：Runner/监管器使用真实 time，透传原 timeout，仅故意延迟真实 Popen 0.6 秒；必须 failed/124、规则回退、reader 未启动且清理完整。稳定性、回归敏感性及最终全量已通过；与本记录独立提交。
- 新用例最初按 `no_spawn` 字段检查时报 KeyError；核对真实 process_control 回执后改为断言 `cleanup.trigger == timeout_before_spawn`、完整校验的监管回执 `pid is None` 及 reader marker 不存在，验证意图未变。独立测试 **1/1**（0.865s）通过。原文件只补说明，原方法和 0.5 秒逻辑预算/5 秒测试 watchdog 均未改。
- 稳定性：临时 `stability.py` 交替执行完整 direct invocation 模块（15 tests）和独立墙钟模块（1 test），共 10 轮 **160/160**，88.079s；每个模块执行完检查 agents.time 与监管函数均恢复，未污染后续真实时钟用例。完整 `stability.log` 保留。
- 负向实验：临时 `watchdog_sensitivity.py` 在内存将真实监管执行预算替换为 5 秒；新用例按预期失败，原始监管回执为 `exited/0` 而非 `timeout/124`。脚本核对这一失败后退出 0，说明 Runner 最后标记 124 不能掩盖越过真实截止时间的 reader 执行；没有修改磁盘生产代码。完整 `watchdog-sensitivity.log` 保留。
- 审阅：已读回整个新增测试；AST 对比 `11078c5`，acceptance/filelock/direct invocation 的所有原方法均未改；对比起点 `422d9bf`，MOVES/HUMAN_ONLY/ALWAYS_PROTECTED 相同，AGENT_ENV/DANGEROUS_BASH 仅追加。`git diff --check` 通过。
- 全量：运行 `python3 -m unittest discover -s tests`，仅设置进程级 NO_PROXY 与临时离线 sitecustomize。首轮及最终结果完整保留于末节。

### P5 回执临时文件追加审查

- 状态：done；提交 `3a16a62`。首轮全量运行期间只在临时夹具中继续核对写入边界，未修改受测实现。复现预先创建 `T001-1.tmp` 符号链接时，旧 staging.write_text 会先覆写仓库外合成文件，再把链接移至草稿路径；`p5-staging-reproduction.log` 保留失败断言。
- 执行顺序：首轮全量结束后改为同目录独占创建唯一临时文件，关闭后再原子 replace，保留失败清理/重试语义；新增不触碰旧临时链接目标的测试，再跑最终全量。待确认：无。
- 完成：首轮全量结束后才改实现；`NamedTemporaryFile(delete=False)` 独占创建、关闭后 replace、finally 清理，不读写旧 `.tmp` 链接。新增回归检查仓库外合成文件字节不变、旧链接未动、确认后草稿为普通文件、无新临时文件遗留。验收测试 **27/27**（4.746s），含原回执失败恢复测试；`p5-staging-green.log` 保留。亲自审阅 diff，`git diff --check` 通过。状态：done。

### 最终审查全量与构建树失败对照

- 首轮全量：**818 tests，408.143s，FAILED（failures=1, skipped=15）**；唯一失败 `test_run_lifecycle.RunLifecycleTest.test_build_tree_uses_run_budget_and_cannot_launch_model_after_timeout`，在 2 秒 `wait_ready` 内三个合成进程树标记均未出现，尚未进入后续 3 秒总预算/5.5 秒收尾断言。intake、P5、P6 新用例没有失败。日志 `full-unittest.log`，受测 8 个实现/测试文件运行前后 SHA256 完全一致（`validated-files.json`）。
- 对照方法：该测试及 `agents.py`/`process_control.py`/`supervised_process.py` 与 `422d9bf` 没有差异。不能仅凭字节相同或复跑转绿判定根因；临时 `build_tree_diagnostics.py` 连续跑原单例，失败时在清理前保存合成 run/lifecycle/监管回执，未改其断言或时间限制。另导出起点 tmh/templates/skills 与该测试，逐个核对 Git blob，用于独立对照；没有导出真实 data/ 或凭据。
- 对照结果：当前分支原单例 **20/20**（72.072s），起点原样副本 **20/20**（69.255s），均未复现。起点目录 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-review-baseline-422d9bf-15ak0872` 的 132 文件逐个等于起点 blob；日志 `build-tree-current.log`、`build-tree-baseline.log`。本轮不宣称已证明该偶发失败的根因或修复它；原 2/3/5.5 秒限制和全部断言保留。
- 最终全量：在 P5 staging 修复提交 `3a16a62` 和本节测试改动上运行 `python3 -m unittest discover -s tests`，**819 tests，400.354s，OK（skipped=15）**，即 **804 通过、15 跳过、0 失败/错误，退出码 0**。8 个受测实现/测试文件的运行前后 SHA256 一致（`validated-files-final.json`），最终再次检查全部原测试方法 AST 未变、`git diff --check` 通过。原生监管代码没有修改。
- 跳过原因只读核对（没有再执行测试）：1 项 cryptography not installed；1 项 needs both（cryptography 与 ssh-keygen，当前缺前者）；13 项 optional MCP SDK not installed。没有联网补依赖。既有资源关闭警告保留在日志中。
- 最终全量的临时 sitecustomize 阻止非回环网络；仅父 unittest 进程的 addFailure 附加只读诊断，在 run_lifecycle 失败时于清理前记录合成运行回执，不改用例/结果/断言，也不向子解释器增加 unittest 导入。最终没有失败，诊断快照未触发。
- 日志校验：`full-unittest.log` 24630 字节 / SHA256 `784f142238cfeed97351ef88097fd6844962e3e091b69d926dc6b770b256568c`；`full-final.log` 23014 字节 / SHA256 `e45a2ecb2403510eb6ffe71ca163a190d2c921af26f55ea767152f9d7df838e3`；`stability.log` 2959 字节 / SHA256 `cf340b7e96057c77d4f2417d85122daf8d15da65ba83d7ac1813455a45302f82`。其余复现/负向/对照日志及脚本同目录原样保留。
- 交接重点：`guard.py:_human_accept_command` 及 acceptance 的 agent 标记、引用/快照/路径/临时文件边界；`kb.py:_Lock` 的重试分类与失败释放，以及 `filelock.py` Windows 字节锁/共享读锁限制；`test_intake_wall_clock.py` 的真实 0.5 秒约束和未启动证据。P1–P6 均保持 done，原 stash 保留，不 push。

## 后续：构建树 2 秒就绪失败

- 状态：done；起点 `baaf980`；已读本文件和最近 10 条提交；开工 `git status --short --branch` 干净，继续使用 `feat/ralph-port`，原 stash 保留。修复和本记录一起独立提交，标题 `test: 消除构建树夹具的串行解释器启动竞态`。
- 用户授权：保留失败现场确认根因，不削弱断言或简单放宽超时；稳定性验证后再跑全量，更新本文件、单独提交、不 push，全程自动推进。
- 计划：临时诊断脚本记录原用例各阶段真实耗时与工作线程栈，失败时保留整个合成临时仓库、进程回执和数据库，同时正常清理本测试所属进程。先定位，再针对根因修复，验证红绿灯与稳定性，最后全量。
- 阅读范围：`tests/test_run_lifecycle.py`、`tmh/platform/agents.py`、`fixloop.py`、`supervised_process.py` 与相关本地监管实现；沿用进程级离线保护和 NO_PROXY。未接触真实 data/ 或凭据。
- 待确认：无；原 2 秒就绪、3 秒总预算和 5.5 秒收尾限制保留。上一轮失败没有完整现场，不能用已通过的复跑代替根因证据。
- 自然复现：临时 `diagnose.py` 只包装阶段计时/观察回执和线程栈，测试、夹具、时间限制未改，也未注入延时或外加负载。完整生命周期模块 5 轮 **65/65**（122.470s）后，原构建树单例连续诊断在第 **18 次**失败（前 17 次通过）。日志、完整逐轮 trace 与诊断脚本保存在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-build-tree-zypem_4_/`。
- 失败现场：原合成仓库、数据库和全部回执保留在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-lifecycle-7_36wxhl/`，清理前快照 `failure-083.json`、完整时间线 `trace-083.json`。未删改现场；仍执行所属进程清理，之后只查询 PID 注册表中的 39874/39875/39878，`ps` 返回 1、输出为空，无这些进程遗留（`failure-cleanup-check.txt`）。
- 根因证据：以原 `wait_ready` 开始为零点，工作树准备结束约 0.540s，本地构建进入监管约 0.735s，监管器 ready/running 约 1.620/1.687s；tree/child/leaf 标记观察于约 2.031/2.271/2.325s。约 2.042s 就绪检查失败时只看到 tree 标记，run 仍为 running，`stopped_reason` 为空，工作线程正常在监管轮询中，3 秒总预算尚余约 0.96 秒。逐代 `Popen(sys.executable, ...)` 重复 Python 初始化/导入，把真实启动抖动串行叠加进 2 秒夹具握手。失败后的 cleanup 杀父进程导致最终 `orphaned/125`，不能把这个收尾结果倒因为生产超时。原先那次“全无标记”现场未保留，本次证明的是同一就绪竞态的自然复现，不臆测旧现场的具体阶段或 OS 调度原因。
- 修复：仅修改 `tests/test_run_lifecycle.py` 夹具，使用无线程的独立 POSIX 进程内 `os.fork()` 创建真实父/子/孙，每代仍独立登记 PID、设置忽略 TERM、写就绪标记和输出并持有日志管道；去掉不必要的 json/pathlib/subprocess 导入。生产代码、控制时钟、超时和监管器均未改；原 **13 个测试及全部原有辅助方法 AST 完全未变**。
- 新回归：仅对子代重新启动 Python 注入真实 1.05 秒延时（两代合计至少 2.1 秒），复用原构建树测试的全部断言和原时间限制；就绪时用 `ps` 验证三个不同活 PID、真实 parent→child→leaf 关系和同一进程组，结束后校验真实运行至少 3 秒、只有一个构建 attempt、timeout/124、TERM/KILL/完整清理和三代原始输出。没有伪造时钟、扩大 watchdog 或只重标失败状态。
- 初次验证：完整模块 **14/14**（27.546s，`lifecycle-green.log`）；最初慢启动红灯在旧夹具下就绪失败（2.529s，`slow-start-red.log`）。随后把延时限定为子解释器启动，以准确回归重复初始化；最终版本见下方红绿对照与稳定性记录。
- 最终回归红绿对照：临时 Python 脚本只在进程内将 `FIXTURE` 替换为 `git show baaf980:tests/test_run_lifecycle.py` 中原字符串，最终新增用例于 2 秒就绪处按预期失败（3.058s）；恢复修复后字符串，同一用例通过（3.449s）。`descendant-red-green.log` 完整保存，脚本检查失败类型后退出 0；磁盘生产代码从未改动。
- 稳定性阶段一：原失败用例连续 **100/100**，356.078s；命令 `NO_PROXY='*' no_proxy='*' PYTHONPATH=<诊断目录>:. python3 <诊断目录>/diagnose.py stability 100`。仍使用真实监管器、真实时钟与原始时间限制；随后顺序执行完整模块 10 轮，失败立即停止并保留合成现场，全部通过后才运行全量。
- 审阅：亲自逐段查看测试 diff；AST 检查原 30 个函数（含 13 个原测试方法）全部相同；`git diff --check` 通过，`git diff --name-only -- tmh` 为空。失败现场 `owned-fixture.py` 与 `baaf980` 原 FIXTURE 逐字相同，SHA256 `ef831e1336ab4cb4136427098f01ce8384e54138b816759cb332f6477627c1e0`。当前受测文件 SHA256 已保存至 `validated-files.json`，后续验证结束再次核对。
- 稳定性完成：原用例 100 次 + 完整模块 10 轮 × 14 次，合计 **240/240**，621.312s、0 跳过/失败/错误，进程退出码 0。其中模块阶段 **140/140**，265.234s；原用例总共 110 次就绪时间中位数 0.226s、最大 1.134s（原限制 2s）。完整 `stability.log` 和逐次 trace 均保留；受测测试文件哈希与阶段开始一致。随后才执行以下全量。
- 全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<诊断目录>:. python3 -m unittest discover -s tests`，**820 tests，307.188s，OK（skipped=15）**，即 **805 通过、15 跳过、0 失败/错误，退出码 0**。仍为 2 项缺 cryptography、13 项缺可选 MCP SDK；没有联网安装依赖。既有资源关闭警告原样保留，未改断言或屏蔽警告。离线 sitecustomize 仅在 unittest 主进程安装失败现场保留回调，本次未触发；子解释器只有离线保护，没有增加诊断导入。
- 最终核对：测试文件 SHA256 `f6625c87113382f20fcdbf74862575ca035346aa676cd3040207edea035178ea` 与稳定性开始、全量前后完全一致；原函数 AST 仍全部相同，生产 tmh/ 无 diff，`git diff --check` 通过。读回保留现场的监管回执，身份/nonce/原始输出哈希校验通过，三代完整日志均存在，失败后的进程清理为 complete；未把这个 cleanup 导致的 orphaned 回执冒充自然 timeout。
- 日志校验：`failure-083.json` 7488 字节 / SHA256 `6aa9f6dd27656f945b1253ca13398e231030c92ac046d943971ed034e257b876`；`trace-083.json` 152026 字节 / SHA256 `a6f0adf6233bed8039617f628edfcfc83a36a3ca336e5f7a91ac6b0d3f92c6c5`；`stability.log` 55954 字节 / SHA256 `917960e399a0a24278cc0bb4022fc28da24770e94d81c8fb2e6d45e4892b1bb1`；`full-unittest.log` 23049 字节 / SHA256 `c2e97c334265b3b64e640f05d3febbda6cadc92f57fc14d1fed7afdc8e9797fb`。其余日志哈希在同目录 `evidence-manifest.json`，没有压缩或截断文件。
- 收尾：只提交测试夹具/新回归和本进度文件；原 stash 保留，不 push。建议审阅本次真实三代 fork、每代 PID/信号/管道语义，以及新增回归的父子关系和真实 deadline 断言；P5 guard/人工确认、P6 锁语义与 Windows 待确认清单保持上一轮结论。

## 后续：复审 552eab9

- 状态：done；开工 `git status --short --branch` 干净，已读本文件和 `git log --oneline -10`；继续在 `feat/ralph-port`，原 stash 保留。独立提交标题：`test: 修复 fork 夹具就绪标记的发布竞态`。
- 范围：`tests/test_run_lifecycle.py`、监管器/进程控制与相关测试；仅本地合成进程、真实时钟，原 2 秒就绪、3 秒总预算和 5.5 秒清理边界不变。
- 计划：核查真实父子关系、信号与管道继承；用故障注入检查覆盖敏感性；先复现 `.ready` 创建与 PID 写入之间的发布窗口，再做最小修复、稳定性验证和全量。
- 已知边界：前轮慢启动注入针对再次启动子解释器；fork 后不会执行这段初始化延时，它验证消除串行初始化，不证明任意子进程调度延时都能满足就绪约束。实际超时与收尾仍由真实时钟检验。
- 待确认：无。人工确认/guard/锁的既有结论及 Windows 待确认清单保持不变；不 push。
- 发现并复现：`ready()` 原先先创建最终文件，再写 PID；新三代关系断言会读到空串。将真实孙进程暂停在 `open` 之后、`write` 之前，三代 PID 均存活，`.leaf.ready` 已存在且内容为空，回归准确失败（0.244s）。完整现场 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-lifecycle-re_vrdn6/` 和写入前快照保留在 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-fork-audit-mtcvk_k2/`。
- 修复：夹具先写同目录、带 PID 的临时文件，关闭后 `os.replace` 原子发布就绪标记；新增真实孙进程发布屏障回归，释放后复用原三代取消测试的全部断言。红灯后同用例通过（0.652s）；原有时间限制和生产代码未改。慢解释器回归补注释明确其覆盖边界，不改行为。
- 故障注入：只在临时文件/测试进程内替换夹具或监管 worker，共 7 组：缺少孙进程、恢复默认 TERM、只杀 leader、忽略 invoke 取消、忽略构建取消、忽略真实 deadline、将真实 deadline 减半。全部由预期断言拒绝，非偶发错误；各轮正常清理后注册的活进程均为空，脚本/完整失败日志/现场在同目录，汇总 `mutation-summary.json`。生产文件没有写入故障代码。
- 审查结论：未发现真实三代进程、取消、超时和清理覆盖退化；发现的就绪标记发布窗口已修复。fork 发生在独立、无线程的夹具进程；每代独立登记 PID、忽略 TERM、持有原输出管道；三代真实 parent/PPID/PGID 断言保留。底层测试仍验证 TERM 忽略跨 exec、父退出而孙代持管道、输出 EOF 后清理、外部进程组不受影响、服务退出后的监管清理，以及监管启动时间计入 deadline。
- 定向验证：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 -m unittest -v test_run_lifecycle test_process_control test_supervised_process test_run_early_stop`，**47/47 通过**，34.532s、0 跳过，退出码 0；完整日志 `targeted.log`。原红灯场景注册的三个 PID 再次用精确 PID 查询，均已不存在。
- 差异验证：相对 `552eab9`，既有 **32 个函数（含 14 个测试）AST 全部不变**；FIXTURE 除 `ready` 函数外 AST 全部不变，生产 `tmh/` 无 diff，`git diff --check` 通过。受测文件 SHA256 `3151a3ab5ef58c16a13d71d2b90a2e22d3caf9edeb27b128f763cd67c1cb0f76` 写入 `validated-files.json`，稳定性和全量结束再次核对。
- 稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 <审查目录>/stability.py`，**150/150 通过**，205.006s、0 跳过/失败/错误，退出码 0。包括新发布屏障 50 次，以及原构建超时、新三代关系/真实 deadline、构建取消、invoke 取消、父退出清理各 20 次。保留完整 `stability.log`、逐次耗时与汇总；130 次就绪等待中位数 0.111s、最大 0.281s（发布屏障用例的该采样从释放后开始；其屏障等待另有 2 秒真实上限）。前后受测文件哈希一致，随后才跑全量。
- 全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 -m unittest discover -s tests`，**821 tests，299.133s，OK（skipped=15）**，即 **806 通过、15 跳过、0 失败/错误，退出码 0**。跳过原因仍为 2 项缺 cryptography、13 项缺可选 MCP SDK（逐项清单 `optional-skips.json`）；没有联网安装。资源关闭警告原样保留。父进程失败诊断未触发，子解释器仅继承离线保护。
- 最终核对：受测文件哈希在定向、稳定性、全量前后相同；审阅完整测试及本文件 diff，`git diff --check` 通过，生产目录无 diff。只提交这两个文件，原 stash 保留，不 push；提交号绑定至审查目录的 `validated-files.json`，完整文件哈希见 `evidence-manifest.json`。
- 日志校验：`publication-before-write.json` 376 字节 / SHA256 `9a0cee84a0f7a1a98ab607e0caffdcac4b71624ce5ead4a7aa2eae3a30cfefc0`；`mutation-summary.json` 2037 字节 / SHA256 `0c5503ea0a0bcbeafa756878d9aa5d636cf0bbed5501d311d47f9cfadb736648`；`stability.log` 29595 字节 / SHA256 `987b46e1cf997f6d62a194473c9f9a302ddfae3e1ab817cc999eb10b53c044cb`；`full-unittest.log` 23022 字节 / SHA256 `5a6dd94a8d8fc336da1ace364c6f832bddd501e85f4ff0459992decef8f1943a`。
- 人工审阅建议：`ready()` 的同目录原子发布；新发布屏障用例在真实孙进程写 PID 前检查标记不可见，释放后执行原取消断言；慢解释器回归注释的覆盖边界。无新增待确认，P5 guard/人工确认、P6 锁语义和 Windows 剩余阻塞点保留原清单。

## 后续：复审 7bce98f

- 状态：done；开工 `git status --short --branch` 干净，已读本文件与最近 10 条提交，继续在 `feat/ralph-port`，不 push，原 stash 保留。独立提交标题：`test: 加强发布屏障并修复迟启动清理竞态`。
- 范围：夹具原子发布、屏障握手与断言失败时的所属进程清理；只用合成临时仓库和进程、真实时钟，不放宽断言或超时。
- 计划：检查关闭/替换顺序及发布前后屏障；在临时脚本中注入关闭前发布、缺失/失败握手和迟启动，检查是否误通过或遗留进程；有实际问题再做最小修复并验证。
- 待确认：无新增；原 P5/P6 和 Windows 待确认清单保留。
- 审查发现一：原子发布实现本身顺序正确，但新增屏障只停在写入前，无法稳定检验关闭顺序。在临时夹具里把 `os.replace` 移入 `with`、放在关闭前，同一屏障用例 **5/5 错误通过**（3.061s），日志 `early-publish-before.log`。改为在真实孙进程写 PID 后、关闭前暂停，要求此时最终标记仍不存在；原夹具的原子发布实现不变。
- 审查发现二：原有 `cleanup_owned` 在 PID 快照后才启动的进程不会被清理，新屏障断言失败也会走这条路径。用 Event 将启动延后至空 PID 快照之后，真实屏障在原 2 秒处失败，原清理返回后仍有 **3 个活 PID 和 1 个活工作线程**。诊断脚本随后取消/回收它们，确认全无遗留；这是复用的旧辅助函数缺陷，不是 rename 引起。现场 `/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-lifecycle-zsf4jhdy/` 原样保留。
- 修复：测试清理先取消本测试库中尚未结束的运行，再取 PID 快照并保留原精确 PID 清理、2 秒线程 join；并发结束仅在状态已变为终态时忽略 cancel 的 ValueError。新增迟启动回归，不替换真实监管器或时钟：旧辅助函数准确失败（2.144s），修复后和屏障正常路径一起通过。
- 证据目录：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-publication-audit-0oj1565f/`。保留 `probe-before.py`、关闭前发布的错误夹具、原清理后与诊断救援后的 PID/线程快照 `late-launch-cleanup.json`、`cleanup-red.log` 及失败现场；后续日志另命名，不覆盖红灯证据。
- 红绿核对：两条正向回归 **2/2**（0.780s）；错误的“关闭前发布”夹具由此前 5/5 误通过变为 **5/5 准确失败**（0.928s，全部命中关闭前标记可见断言）。同一迟启动/屏障超时诊断在修复后不再启动任何夹具进程，清理返回时 PID 为空、工作线程已结束，后置诊断救援无需再杀进程（`late-launch-cleanup-after.json`）。
- 异常路径：释放标记写入失败、缺失暂停标记、孙进程在屏障处退出、rename 失败，四种情况都保留原错误/失败，清理后所属 PID 和工作线程均为空；现场/完整日志与 `negative-paths-summary.json` 保留。取消本身出错时仍在 `finally` 执行原精确 PID 回收和 join，合成 OSError 原样上抛，实测三个活进程全部回收、线程结束（`cancel-error.json`）。
- 初步定向：4 个相关模块 **48/48 通过**（34.562s）；随后补上上述取消异常的 finally 保证，针对最终字节重新跑同一组和稳定性。原 `FIXTURE` 字节完全未变；原 14 个其他测试方法 AST 不变，只加强清理辅助函数、屏障用例并新增迟启动回归。
- 最终定向：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 -m unittest -v test_run_lifecycle test_process_control test_supervised_process test_run_early_stop`，**48/48 通过**，34.480s、0 跳过，退出码 0，日志 `targeted-final.log`。最终受测文件 SHA256 `bb203df83d78697333344bb8713319a7defc968c84f1485e3f50fb2fb0d7ddd3` 保存至 `validated-files.json`。
- 清理复核：13 个保留的负向合成现场，逐个按注册表的精确 PID 查询，均已不存在；没有按进程名或端口查杀。`final-negative-cleanup.json` 保留核对结果。原超时/取消断言在清理前判定（或记录失败条件后明确 fail），新增清理不能把这些失败改为通过。
- 屏障语义：`.paused`/`.release` 仅用存在性握手，不读取其内容，不依赖它们的 PID 文本完整性；每个用例使用全新的私有临时目录。屏障位于真实文件关闭前，释放后才允许 close 与原子替换；最终 `.ready` 继续读取 PID 并校验活进程，原 2 秒就绪/取消和其他运行预算不变。
- 稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 <审查目录>/stability.py`，**148/148 通过**（两条重点回归各 50 次 + 完整模块 3 轮 × 16 项），115.961s、0 跳过/失败/错误，退出码 0。77 次就绪等待最大 0.838s；屏障用例的这个采样从释放后开始，暂停握手另有原 2 秒上限。真实时钟与超时不变，文件哈希前后一致；完整日志/逐次记录保留。随后才执行全量。
- 全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 -m unittest discover -s tests`，**822 tests，355.484s，OK（skipped=15）**，即 **807 通过、15 跳过、0 失败/错误，退出码 0**。逐项核对仍是缺 cryptography 的 2 项和缺可选 MCP SDK 的 13 项（`optional-skips.json`），未联网安装；原资源关闭警告保留。此前 5 份故意制造的失败快照保留，全量没有新增失败快照。
- 最终审查：原子发布实现无需改动；修复了屏障漏检和复用清理函数的迟启动漏洞。取消异常仍上抛，原精确 PID 清理和 2 秒 join 在 finally 中执行；没有扩大进程筛选范围，也没有放宽任一原时间限制。原 14 项其他测试 AST、整个 FIXTURE 字节及生产 `tmh/` 均无改动；最终代码哈希在定向、稳定性、全量前后相同，`git diff --check` 通过。只提交测试与本进度文件，提交号绑定到 `validated-files.json`。
- 日志校验：`early-publish-before.log` 1031 字节 / SHA256 `4e7e47ed0e1013982443f55e513c66fa76d3f2351a3bcecc9c94d4bd159f4338`；`early-publish-after.log` 11903 字节 / SHA256 `4360229eca2e626b3420b7d68d46ad6bd3e8d2fbdda7c2052da397ffe94fdf5a`；`late-launch-cleanup.json` 424 字节 / SHA256 `6024632cc93340ef4a325f28c524699112648e8402f21a0ebedf966c962a7df3`；`stability.log` 28555 字节 / SHA256 `b9cf73907def93a1e73b7da171617fb8669176aa16318c7729a95a142585bb52`；`full-unittest.log` 22988 字节 / SHA256 `c59c8b328de94bd64297cecaccfd5c273033980873c2a1d697f1303eef0621b6`。其余原始文件哈希在同目录 `evidence-manifest.json`。
- 人工重点：屏障从 write 前移到 close 前，是否准确捕获关闭前发布；`cleanup_owned` 先取消再取 PID 快照、并在取消出错时仍清理的顺序；迟启动回归的 Event 释放与 finally。无新增待确认，P5/P6 与 Windows 剩余阻塞点沿用原清单。

## 后续：项目资产与知识库复用设计

- 状态：done；起点 `663b98e`，`feat/ralph-port` 开工干净。P1–P6 和既有后续修复保持 done；本条是新需求设计，不将设计完成计作功能实现完成。
- 需求：标品及一个或多个参考项目可先作为知识来源，客户项目从已有标品派生；参考项目以后也能作为待修改老项目。底层需支持数十万行代码、灵活组合与知识复用。
- 已读：项目 Store/API/UI、Knowledge、graph/kb/context/parsecache、survey、Agent 上下文入口、现有相关测试与知识库/待办说明；只读本地源码和文档，不接触真实 data/ 或凭据，不启动服务。
- 发现：目前 project 主要绑定一个 root；解析按文件缓存、知识页锚点和队列可复用，但没有固定版本的跨项目引用/派生关系。图谱仍整体重建，检索缓存一次只保留一个项目；既有能力不能直接证明复杂标品规模下可用。
- 实际产物：`docs/design/project-knowledge-library-2026-10-20.md`、`docs/self-improvement/BACKLOG.md` 与本进度文件。设计包含统一实体、版本/来源/权限边界、现有落点、分段交付和行为验收；SI-015 实现仍为待办。
- 假设：角色可组合；引用默认固定版本、只提供资料；同项目继续维护与从标品派生客户项目均支持；已有人工确认和代码证据边界不变。不假定用户已指定某个真实参考仓库或授权导入。
- 验证：`cat docs/design/project-knowledge-library-2026-10-20.md` 完整读回 163 行 / 17326 UTF-8 字节；临时 Python 检查 5 条相对文档链接有效，9 个实现落点的文件/函数或类实际存在；检查代码围栏闭合与“设计/未实现”声明。`git diff --check` 通过；逐段审阅新文档与两份记录 diff。本轮仅文档，未运行或重报产品测试。
- 交接：单独文档提交 `docs: 设计标品与参考项目的版本化知识复用`，不 push。继续实施时先读 SI-015 与设计，按 A→B→C→D 验证；不重复 P1–P6，也不将当前文档视为真实项目接入或迁移授权。
- 待确认：没有阻塞设计的问题；真实仓库、分享范围与性能目标在后续接入时明确，保留为实施输入，不凭空编造。

## SI-015 实施

- 状态：done（首版交付；精细依赖分析和真实标品试点仍待续）；用户已明确“然后开始实现吧”。起点 `60d96e7`，`feat/ralph-port` 开工干净；原 stash 保持。不 push，不访问网络/真实 data/凭据，不启动日常服务，不改 Git 配置。
- 范围：兼容旧项目的来源/角色/工作区、不可变知识修订、多个固定引用及全文读取、从标品派生和同项目开始维护、任务输入绑定、网页及 CLI/MCP、失败恢复和规模验证。
- 执行：主线程实现知识构建/存储/引用/派生；按 executing-plans 技能的分工要求，由子代理独立处理页面与 Agent 接口，各自限定文件，统一审查与验收。其引用的附属技能本机未安装，使用现有 Git 分支及验证流程完成同类工作，不影响用户已授权范围。
- 合理假设：首版固定版本来自本地 Git；非 Git 项目沿用旧功能，版本化共享明确报告不支持，不伪造提交。权限范围是现有可信本地平台，跨项目共享须明确授予；不宣称组织级账号隔离。真实大型标品尚未指定，先用临时多仓库和数十万行合成项目验证，实际标品列为剩余验证项。
- 计划验证：来源不改写、同名隔离/固定引用/全文保留、更新与撤权失效、取消/失败恢复、派生字节与知识确认边界、UI/CLI/API；相关定向回归后全量。所有测试使用临时目录或临时仓库。
- 待确认：无阻塞实现的问题；真实试点仓库保留为后续接入输入。
- 初步实现：新增 `tmh/project_knowledge.py` 静态 worker 和 `tmh/platform/project_library.py`；来源原文与分析产物分目录，发布固定提交/分析器/配置/文件/索引摘要。Store 增量迁移来源与角色；知识引用、派生/维护、API/CLI/MCP/页面接入；任务与方案记录引用输入摘要。
- 第一轮定向：`python3 -m unittest -v tests.test_project_library tests.test_library_lifecycle tests.test_knowledge_agent_api tests.test_ui_library tests.test_ui_dialog`：55 tests，9.473s，OK（54 通过、1 缺 MCP SDK 跳过）。真实临时仓库/监督子进程覆盖固定版本、双来源、授权范围、全文、派生、迁移、失败/取消恢复；UI 为执行 JS 回归，尚不能替代浏览器验证。
- 自审修复：拿锁后重读 ready 状态；初次启动不抹掉 queued 取消；worker 核对真实分析器；禁用 Git replace/外部协议/继承索引配置；原文与生成知识命名空间分离；检索校验索引摘要并关闭连接。两项竞态测试注入旧行为均在预期断言失败，恢复新版通过。
- 后续加固进行中：旧执行入口拒绝 reference 工作流；共享/派生须真实登录会话或独立操作者凭据；归档来源任务/验收/验证报告，保留原始导入提交，客户知识重新确认；交付方案检查准确绑定的 run，不能由新无关方案替代。完整定向/浏览器/规模/全量尚待最终字节验证。
- 本轮验证资料目录：`/private/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/tmh-library-validation-_aov13wg/`；后续完整日志保存在此目录，离线保护仅允许测试回环连接，不修改机器设置。
- 实现范围：`tmh/project_knowledge.py`、`platform/project_library.py` 实现静态版本构建、分阶段恢复、范围授权、检索原文、独立派生与维护；Store/server/knowledge 接入兼容迁移与旧路径限制；agents/agent_api/fixloop/preview 绑定引用与执行边界；agent_contract/workbench 接 CLI/MCP；ui_library/ui 接网页。新增 6 个行为测试模块，既有测试只适配只读工具数及最小 mock fixture，原断言含义保持。
- 授权与输入：普通 API token 加人的显示名不能授予共享或创建工作区，7 类管理操作需真实签名会话或独立操作者凭据；Agent 仅能引用已有授权。任务包明确返回固定引用及摘要，与 requirement_hash 使用同一份引用输入；无引用时旧需求摘要逐字兼容。固定交付方案检查其实际 run，不能由新无关方案替代；提示词检索捕获 A→B→A 切换并拒绝启动。
- 工作流：SQLite 短事务原子核验工作流并登记 Runner；项目内核锁串行化工作流切换与预览、复检登记。后台迟到预览必须重新读工作流，仍有活动预览/运行/复检时拒绝切换。只读来源的旧 project/ticket/run/session 写入入口被拒绝，不会先写聊天再报错。
- 文件与确认：源 Git 对象原样导出到 source，分析产物在 analysis，生成页使用独立 `@knowledge/` 命名空间。派生先写精确导入提交，再另写初始化提交；来源任务/验收/报告完整归档，来源确认保留为历史并改为当前项目待确认。有排除文件的快照拒绝完整派生，未静默复制不完整工程。
- 实际排查记录：最初一组回归误写不存在的 `test_candidates` 模块（145 tests，1 导入错误、13 skips），改用真实模块；另一组 46 tests 发现既有方案选择单测的最小 Mock 缺 `project_id`，补夹具并单独模拟新增引用门槛，仍保留原方案选择全部断言并断言检查 run 10，真实边界另有集成测试。新增首次锁 I/O 错误用例时一次插入位置错误导致 NameError，恢复原取消断言位置后通过；这三次均属测试命令/夹具问题，原日志保留，没有改超时或弱化断言。
- 最终加固：首次 try_lock 的 I/O 错误关闭句柄、保留原异常且不登记/启动构建；`lease-mutation.log` 中运行期换回旧代码准确命中句柄未关闭断言，修复后同用例通过。就绪后恢复、queued 取消、分析器变更、破坏索引/监管回执、同分分页、固定方案失效及引用切换均有反例；内核锁和进程监管沿用 P6/P5 边界。
- 定向命令统一为 `NO_PROXY='*' no_proxy='*' PYTHONPATH=<资料目录>:tests:. python3 -m unittest -v <模块>`：`related-final.log` 9 组既有/新功能 **132/132**，151.319s；`feature-final.log` 新知识/生命周期/边界/集成/Agent/UI/dialog **73 tests，72 通过、1 MCP SDK 缺失跳过**，24.819s；最后锁和布局调整 `final-adjustments.log` **38/38**，4.312s；最终任务包与 UI 时序、既有 Agent API/client `packet-and-ui-final.log` **88/88**，20.969s。
- 稳定性：`python3 <资料目录>/stability.py`，queued 取消、发布后恢复、迟到预览、提示词引用 A→B→A 四条各 20 次，**80/80**，36.441s、0 跳过/失败/错误。保持真实 Git、监督子进程、内核锁与时钟，屏障只控制特定顺序；20 秒测试看门狗不改变产品 1800 秒构建预算。最后锁失败关闭修复不改变这些成功路径，随后完整生命周期模块再次通过。
- 浏览器：用合成帐号和临时回环服务实际登记 STD/REF/CLIENT → 两来源固定构建 → 分范围绑定两份引用 → 同名审批检索 → 完整原文 → 派生客户 → 原项目开始维护 → 客户改模块后与固定标品比较 → 移除引用。DOM、原始截图与全文保存在资料目录；脚本标签按文本呈现，控制台没有 error，全文逐字等于原文件。回执表实际渲染发现长路径挤窄中文列，修正列宽和横向滚动后再次截图亲自查看，未删减内容。
- 浏览器读回：三个原仓库 HEAD/状态保持，三个独立工作区干净，所有导入 blob 等于来源清单；归档报告原字节保留、当前知识待确认，原项目 id 仍为 1、两个旧引用保持、两份监管回执完整，0 模型运行/工单。最后从 CLIENT 移除 STD 后只剩 REF，旧对照消失，搜索只剩 1 条 REF 文档；`browser-verification.json`、`browser-final-state.json` 分别保留两阶段结果。临时服务与浏览器页均已关闭，日常 8791/8793 未启动。
- 网页时序：新增参考卡的比较入口；引用变化清除已有对照，迟到比较成功或错误均不能覆盖新范围；连续比较不同来源以最新请求为准。对应新增回调用例在原行为下先失败后通过；UI 不缓存独立操作者凭据，来源撤权会清除旧搜索/全文/对照，不只改提示文字。
- 规模：`scale.py` 冷/热/单文件变更三次真实构建，**286,780 行 Java、260 源文件、13 个目录组**，耗时 **9.576 / 6.355 / 6.113 秒**；解析文件 **260 / 0 / 1**，缓存条目 **0 / 520 / 518**（每文件两类解析）；峰值 **110018560 / 113344512 / 114147328 字节**；查询耗时 **0.092539 / 0.063672 / 0.061732 秒**。原文与源仓库未改变，分析器摘要与最终代码核对一致（`scale-analyzer-verified.json`）。
- 规模边界：原始脚本输出的 `modules:13` 只是目录组，`one_module_changed` 实际只改一个文件；解析器只识别 **1 个模块、0 业务域/流**。检索词包含宽泛 approval，26,522 命中是词法统计，不代表业务相关性质量。`scale-results.json` 原样保留，不能将合成速度当真实复杂标品的完整理解或多模块精度证明。
- 文档：新增 `docs/project-library.md`（82 行、8533 字节）说明网页/API/CLI/MCP、失败恢复、授权、无损归档和支持边界；设计与 BACKLOG 改为首版已实现，明确 C 的精细依赖/业务冲突与 D 的真实标品试点未完成。逐字读回，链接与代码围栏检查通过；非 Git/外部文档适配器保留后续扩展。
- 首次全量前：已记录 217 个源码/测试/模板/技能文件的 SHA256（`validated-files-before-full.json`），随后运行 `NO_PROXY='*' no_proxy='*' PYTHONPATH=<资料目录>:. python3 -m unittest discover -s tests`。仅父 unittest 进程安装既有生命周期失败现场保留回调；不改变断言、结果或子进程启动时序。首次失败和最终复跑结果、哈希复核见下方。
- 待确认/后续输入：无阻塞首版交付的问题。真实标品路径、允许共享范围与目标性能需实际试点时明确；精细业务依赖传播与升级冲突分析、非 Git/外部文档适配为后续能力。Windows 仍有上文六项阻塞，尤其 POSIX 进程监管、预览/本地 shell、hook 命令、权限/文件系统及原生锁实机验证；本轮静态 worker 复用 POSIX 监管，没有宣称 Windows 可运行。
- 审阅重点：`server.py:api_library_action` 的真实操作者认证与共享范围；`project_library.py:derive/_initialize_workspace` 的原始提交、完整归档和当前项目确认；`agents.py:reviewed_delivery_plan` 与任务包实际引用输入；`project_library.py:_lease/project_guard/resume` 的锁所有权、拿锁后重读和错误释放。`invariants.json` 核对 acceptance/guard/filelock/process_control/supervised_process 五文件与起点逐字一致；MOVES/HUMAN_ONLY/AGENT_ENV/ALWAYS_PROTECTED/DANGEROUS_BASH 的 AST 相同。P5 guard 与 P6 锁的既有人工审阅建议继续有效。

- 首次全量：895 tests，415.697s，FAILED（1 failure、16 skips），退出 1。唯一失败 `test_runtime_review.RuntimeRecoveryReviewTest.test_independent_runners_commit_and_dispatch_only_one_retry` 是本轮引入：Runner 在提示词准备至启动期间独占项目锁，阻止第二个 Runner 到达既有数据库重试去重屏障，两个均未获胜。完整 `full-unittest.log` 保留，SHA256 `8551eda86042e3acc5d4dcac11b54257b51453235db6f234e309dd466e980048`；不归因为环境或基线，也没有修改原测试屏障、断言和时限。
- 并发修复：移除 Runner 准备阶段的整段项目锁；`Store.create_run` 与工作流切换/工作区发布用 `BEGIN IMMEDIATE` 把当前工作流核验和登记置于同一短事务，唯一重试索引仍裁决两个独立 Runner。拒绝路径自动回滚，预览/复检的项目内核锁保持。运行还在事务内核对生成提示词时的工作区，阻止查阅→维护切换后用旧目录提示词启动。
- 新回归：独立连接在提示词完成后切换只读，必须不登记、不认领、不启动；真实 SQLite 写锁探针分别检查运行先登记、工作流先切换时的核验至发布原子性，以及失败后锁已释放；真实固定版本维护后旧工作区提示词拒绝启动。只有最后调度模型的 Thread 被拦截，Git、SQLite、工作流、提示词与派生仍执行真实路径。定向与稳定性结果见下方。
- 并发定向：`python3 -m unittest -v test_runtime_review test_library_boundaries test_library_integration test_run_lifecycle`，**42/42**，43.290s，退出 0（相同离线环境）。原失败的独立 Runner 重试测试逐字未改，现已通过；新三项边界回归均通过。
- 并发反例：只在诊断进程内分别移除运行事务、切换事务、登记时工作流检查、登记时工作区校验，四组均在预期断言准确失败，恢复后均通过（`registration-mutations-final.log`、JSON）。最初诊断函数复制了 globals 导致切换事务的暂停探针未接上，未把这次错误算作有效红灯；旧脚本及日志保留，改为使用原模块 globals 后重新验证。生产源码从未写入故障代码。
- 并发稳定性：上述原重试用例和三项新边界各 20 轮，**80/80**，32.052s，0 失败/错误/跳过，退出 0。真实独立连接、Git 派生、时钟及原重试屏障/时限保留；受测 5 个文件前后 SHA256 一致。最终全量前另存全部 217 文件摘要到 `validated-files-before-full-final.json`，首次失败日志和首轮摘要不覆盖。
- 最终全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<资料目录>:. python3 -m unittest discover -s tests`，**898 tests，305.777s，OK（skipped=16）**，即 **882 通过、16 跳过、0 失败/错误，退出 0**。逐项核对 14 项缺可选 MCP SDK（含 1 项新增协议用例）、2 项缺 cryptography；没有联网安装。资源关闭警告原样保留，未屏蔽。仅加载测试列出的完整跳过清单为 `optional-skips-final.json`。
- 最终字节与不变量：全量前后 217 个源码/测试/模板/技能文件 SHA256 一致（`validated-files-after-full-final.json`）；acceptance/guard/filelock/process_control/supervised_process 五个文件与 `60d96e7` 逐字一致。对比起点 1,196 个原测试/辅助函数 AST，仅两处已说明的 fixture/工具数适配；原独立 Runner 重试测试完整不变，原真实超时/取消/进程清理测试不变。`invariants-final.json` 保留结果。
- 验证日志摘要：`full-final.log` 22972 字节 / SHA256 `ce437d50b9b26a8928235b2246e6126102e60986e5227069418fc4a7b5e2b1ee`；`registration-targeted.log` 7962 字节 / `7aa55eb98ed2804c62774164d1cf2d89ba0816d94ba383a78f3488074da595e8`；`registration-stability.log` 17723 字节 / `f4707f8722a7b82c4a6163503325a4a70671dbed190ecb6c56374a5c8aae3c53`；`registration-mutations-final.log` 6092 字节 / `11844e6f15d598f13d2491bbd636eedba722abf923f887b451892d15101f83f3`。首次全量失败、反例、浏览器原图/DOM、原文、规模脚本与原始测量全部保留，无压缩或截断。
- 收尾：亲自审阅新增实现及全部集成 diff、最后四文件并发修复、基线两处夹具适配和文档；浏览器最终原图再次打开确认可读，文档链接/围栏与 `git diff --check` 通过。使用说明 [project-library.md](../project-library.md) 已读回；设计与 BACKLOG 明确首版及未完成范围。提交标题 `feat: 支持标品与参考项目的固定版本知识复用`，在 `feat/ralph-port` 独立提交，不 push，原 stash 保留。
- 新增人工审阅重点：`Store.create_run`、`project_library.configure/derive` 的短事务、回滚和工作区绑定；共享操作的真实操作者认证；来源确认的完整归档及客户重新确认。P5 guard / 人工确认和 P6 原生锁实现未改，原人工审阅建议及 Windows 六项剩余阻塞清单保持。

## 后续：复审 2c1cd53

- 状态：done；开工 `git status --short --branch` 干净，已读本文件和 `git log --oneline -10`，继续 `feat/ralph-port`，原 stash 保留。独立提交标题：`fix: 修复知识共享及运行登记的并发隔离`。
- 用户授权：重点审查跨项目共享授权、固定版本引用、派生人工确认隔离及运行登记事务并发；有问题直接修复、验证、独立提交，不 push，不等待回复。
- 范围：知识库服务与静态 worker、HTTP/Agent 入口、工作区初始化、任务绑定及 Store/Runner 事务，沿调用链核对既有确认与知识证据规则；不改状态迁移、保护规则、原断言或超时。仅临时仓库、回环与合成进程；不访问网络、真实 data/ 或凭据，不启动日常服务。
- 计划：先构造反例保留原失败，再修实现并验证回归敏感性、并发稳定性，最后全量与哈希/工作区核对。证据目录 `/private/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-library-review-3p9rpt4m/`，使用仅允许回环的进程级离线保护。
- 待确认：无；跨项目共享沿用可信本地平台的项目边界，不将本轮扩展为多租户身份系统。
- 已复现四类问题：运行先提交、引用输入后提交，导致独立连接可见无绑定运行，输入写入失败留下占用重试名额的 queued 记录，登记前最后一次引用变化也未被原子检查；共享范围读改写可覆盖另一连接刚完成的撤权；同项目开始维护更换 root 后，原方案在引用相同时仍被判断可用；发布前检查取消后，另一连接已确认的取消可能被 ready 写入覆盖。
- 原版本反例：生产代码保持 `2c1cd53` 时，新增六条反例 **6/6 准确失败**（2.424s，退出码 1，`review-red.log`）；再次运行 **6/6 失败**（2.400s，`review-red-scenes.log`），在清理前保存六个完整合成仓库、数据库及逐表快照、构建监管回执，目录 `red-scenes/`。未削弱原断言、时间限制或真实监管器。
- 修复：`Store.create_run` 在原 BEGIN IMMEDIATE 内复查引用并写入不可改写的输入/工作区，Runner 不再另行提交绑定；授权合并、引用校验/写入、发布取消检查使用数据库写事务，跨连接串行化。`run_current` 加入实际项目工作区身份，历史未知 root 不补记；已更换工作区的历史方案失效，结果原样保留。
- 修复自审：新增字段迁移初稿缺少跨连接重读；两个真实连接同时读到旧 schema 后，稳定出现重复加列错误（`migration-red.log`，1 test/1 failure/0.086s）。改成 BEGIN IMMEDIATE 后重读再迁移；9 条新增回归 **9/9 通过**（5.836s，`review-green.log`），包含并发升级、历史输入原样兼容及不可覆写绑定。该迁移问题只存在于本轮未提交初稿，未归因于 `2c1cd53`。
- 首轮定向：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 -m unittest -v test_library_review test_library_boundaries test_library_integration test_runtime_review`，**32/32 通过**（19.805s，`targeted-first.log`）；随后新增迁移/凭据边界用例，最终字节仍须重新定向、稳定性和全量验证。
- 第二轮定向与稳定性：8 个模块 **79 tests / 78 通过 / 1 可选 MCP SDK 缺失跳过**（38.231s，`targeted-final.log`）；新增 9 条边界回归加原独立 Runner 重试共 20 轮 **200/200 通过**（77.711s，`stability.log/json`），218 个文件哈希不变。操作者凭据/签名会话分别携带 Agent 标识的 7 类管理请求均 403，真人请求按范围授权正常。
- 调用链续查：`learn._run_case` 绕过 Runner.start，旧提示词可能被登记为新引用；评测、需求理解、人工提交三条直接 create_run 路径未传准备时工作区。新增四条反例 **4/4 准确失败**（1.728s，`direct-callers-red.log`），再次 **4/4 失败**（1.901s），完整合成现场保存在 `direct-callers-red-scenes/`。三个调用文件此前与 `2c1cd53` 相同。
- 补齐调用路径：评测在准备提示词前捕获引用，并将同一份输入传给提示词与登记事务；评测/需求理解/人工提交都传 `expected_root`，工作区变化时在登记前拒绝。未改其时钟、watchdog、取消/清理或人工验收逻辑。因有新的实际发现，重新跑最终定向和稳定性后再开始第一次全量；前轮日志保留，不覆盖。
- 最终定向：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 -m unittest -v test_library_review test_project_library test_library_lifecycle test_library_boundaries test_library_integration test_runtime_review test_knowledge_agent_api test_project_bootstrap test_direct_invocation_lifecycle test_handwork_lifecycle test_intake_wall_clock test_intake_recovery`，**115 tests / 114 通过 / 1 可选 MCP SDK 缺失跳过 / 0 失败错误**（43.545s、退出码 0，`targeted-after-callers.log`）。包含 14 条新增测试及既有直接调用、真实时钟、取消、人工提交生命周期。
- 不变量：原 82 个测试文件逐字未改；acceptance/guard/filelock/process_control/supervised_process 与 `2c1cd53` 逐字一致，HUMAN_ONLY/AGENT_ENV/MOVES/保护路径及钩子不变。来源决策归档、完整派生、读取授权与固定版本校验函数 AST 不变；其原行为测试通过。218 个受测文件哈希已记录至 `validated-files-final.json`，定向前后相同；检查结果在 `invariants.json`。
- 最终稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:tests:. python3 <审查目录>/stability-after-callers.py`，13 条新增运行/并发边界测试加原独立 Runner 重试，共 20 轮轮换顺序，**280/280 通过**（118.602s、0 跳过/失败/错误、退出码 0）。逐轮耗时和哈希核验见 `stability-after-callers.json/log`；218 个文件全程未变。之后才启动本轮第一次全量 `python3 -m unittest discover -s tests`。
- 失败现场回收核对：两组保留场景中 9 个真实监管构建的 supervisor/worker PID 均已不存在，`negative-scenes-cleanup.json` 保留精确 PID 查询及原清理回执；未按名称/端口查杀。其余一个输入写入失败场景没有启动进程。
- 人工重点审阅：`project_library.act/reference/_run` 中授权读改写、引用登记、发布取消检查的事务边界；`Store.create_run` 及四个调用入口的输入快照/工作区核验与整体回滚；`schema/run_current/bind_run` 的历史未知工作区、不可改写证据与并发迁移语义。派生确认归档原实现不变，P5 guard/人工确认和 P6 原生锁保持原审阅重点及 Windows 六项剩余阻塞清单；无新增待确认。
- 全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<审查目录>:. python3 -m unittest discover -s tests`，**912 tests，371.850s，OK（skipped=16）**，即 **896 通过、16 跳过、0 失败/错误，退出码 0**。14 项缺可选 MCP SDK、2 项缺 cryptography，逐项身份/原因保存在 `optional-skips.json`；未联网安装。资源关闭警告原样保留，失败现场捕获没有触发。仅测试父进程安装诊断记录，子进程只继承离线保护。
- 收尾核验：全量前后 218 个源码/测试/模板/技能文件 SHA256 相同（`validated-files-final.json` 与 `validated-files-after-full.json`）；完整审阅六个生产文件、新增测试、使用说明与进度记录 diff，`git diff --check` 通过。修改为 `platform/{agents,handwork,intake,learn,project_library,store}.py`、新增 `tests/test_library_review.py`、`docs/project-library.md` 及本文件。不改原状态迁移/验收/保护规则，不访问真实 data/凭据，不 push，不修改 Git 配置；原 stash 保留。
- 日志校验：`review-red.log` 7334 字节 / SHA256 `fa53a66d570398739bd8ee41e7d97e581e4ef897b63435aa07bb467399758ad8`；`direct-callers-red.log` 8583 字节 / `387999624fe42a656997e338cb23bdf753a558de3fc53790e70bdb745b3a7877`；`targeted-after-callers.log` 22164 字节 / `9d1c52fd2a9ca553fdd2c59bf54c257287c5379303fa8b8d7a91d406cb123afb`；`stability-after-callers.log` 52525 字节 / `b75373eea393b6acab82cd29c3f7fa79aa6907388deb2129f7ad74dfb776004e`；`full-unittest.log` 23275 字节 / `12c28a102f178656573582324a93e289a37467db47e59293b9a852c94daddb05`。提交号与完整原始证据目录绑定记录在 `validation.json`/`evidence-manifest.json`。

## 后续：复审 2bb56f4

- 状态：done；开工 `git status --short --branch` 干净，已读本文件与 `git log --oneline -10`，继续 `feat/ralph-port`，原 stash 保留，不 push。
- 范围：新事务回滚/并发、历史工作区证据和数据库迁移兼容，沿运行登记及候选验收调用链检查死锁、误拒绝和错绑。原状态迁移、人工确认/guard/锁规则、基线测试断言及超时保持。
- 计划：真实临时数据库、仓库和独立连接构造反例；保留失败现场后做最小修复；定向与稳定性验证后跑一次全量，核验字节及工作区并独立提交。
- 证据目录：`/var/folders/s1/w8fs8_h15dd3cf8nzqcv76140000gn/T/ralph-transaction-review-knzki576/`；沿用仅允许回环的进程级离线保护，旧轮证据不覆盖。不访问真实 data/凭据，不联网，不启动日常服务，不改 Git 配置。
- 开工检查记录：发现候选提交另有直接 INSERT runs 的路径，先将其与新增工作区绑定的交互列为待验证疑点；下方反例随后证实缺陷。
- 待确认：无；历史缺失工作区身份不得从当前 root 猜测补写，继续保持来源证据的保守边界。
- 反例：原 `2bb56f4` 生产代码下新增 6 条回归 **6/6 准确失败**（2.441s，退出 1，`review-red.log`），完整临时仓库和逐表数据库快照在 `red-scenes/`。包括外部候选漏绑/更换工作区后误拒绝、候选准备后工作区变化仍登记、分次读取授权拼出从未同时有效的状态、历史缺失绑定可被补写、无绑定兼容分支未核对运行所属项目。候选漏绑及分次授权读取是沿调用链发现的既有缺口；新工作区候选被历史证据规则拒绝是本次提交的兼容回归，不把所有发现都归因为该提交新引入。
- 修复：候选在原写事务内复查工作区、需求和授权并写入固定输入，去重含工作区身份；候选读取也检查来源证据。历史缺失绑定只能保留，不能用当前身份补写。当前证据核验用持有 Store 锁的读取 SAVEPOINT，整体读取运行归属/工作区/引用/授权；支持调用方已有写事务，不提前提交。
- 首轮绿灯排查：6 条中 5 通过，真实候选复检 1 失败（3.540s，`review-green-first.log`），因新夹具在基线 VALUE=1 时断言 VALUE=2，产品正确判为基线失败。改为基线严格断言 1、候选提交同时把实现和断言改为 2；未改已有测试或放宽断言。随后 12 条 **12/12**（7.306s，`review-green-second.log`）。
- 回滚/迁移覆盖：真实 SQLite 读锁使运行提交失败，运行/绑定/重试名额全部回滚；授权合并后引用写入被触发器拒绝，授权和引用一起回滚；旧五列库在 ALTER 被拒绝和 COMMIT 遇 BUSY 两阶段失败后，原数据/模式保持、写锁释放，随后可重新升级。历史空 root 不回填；读取 SAVEPOINT 的正常/拒绝/异常路径均不提交外层事务。
- 续查：候选拿到复检来源锁后会第二次读取状态，但预览分支忽略第二次 current=false。真实候选构建通过后、两次读取之间由独立连接撤权，旧执行函数仍调用预览启动；反例 **1/1 准确失败**（2.703s，`preview-red.log`），现场 `preview-red-scene/` 保留。补查锁内当前状态，最终启动调用仅在测试中拦截，不启动实际预览服务。
- 定向：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<本轮证据目录>:tests:. python3 -m unittest -v test_library_transactions test_library_review test_project_library test_library_lifecycle test_library_boundaries test_library_integration test_runtime_review test_external_candidates test_external_candidates_independent test_recheck_operations test_recheck_publication test_agent_api`，**140/140 通过**（68.272s，0 跳过/失败/错误，退出 0，`targeted.log`）。既有候选真实验证、独立人工签收、迁移和运行去重均包含在内。
- 敏感性：仅在诊断进程中换入旧候选读取、删除工作区去重字段、候选输入前提前提交、恢复分次读取、读取核验提前提交外层事务，**5/5** 均准确命中预期断言，0 非预期错误（`mutations.log` / `mutation-results.json`）。完整负向现场在 `mutation-scenes/`，生产文件未写入故障代码；不能将这些故意的红灯算作正常测试失败。
- 不变量：原 83 个测试文件逐字未改，acceptance/guard/filelock/process_control/supervised_process 与 `2bb56f4` 逐字一致；219 个受测源码/测试/模板/技能文件 SHA256 已保存至 `validated-files.json`。未改状态迁移、人工确认、钩子、锁所有权或原断言/超时。
- 稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<本轮证据目录>:tests:. python3 <本轮证据目录>/stability.py`，13 条新增回归加原有双连接迁移、双 Runner 重试，20 轮轮换顺序，**300/300 通过**（199.982s，0 跳过/失败/错误，退出 0）。逐轮结果及耗时在 `stability-results.json` / `stability.log`；219 个文件每轮哈希一致。随后才启动本轮首次全量。
- 负向现场清理：归档中 14 个真实监管任务的所有登记 PID 均已不存在，清理回执为 complete、原始输出长度/SHA256 和身份字段均匹配（`negative-scenes-cleanup.json`）。归档保留原 folder 身份，不能当作复制目录上的可恢复回执；直接用生产 read_receipt 读复制路径会正确拒绝 wrong folder，未改元数据绕过该校验。原场景构建结束时已由夹具在原位置验证真实回执。
- 最终自审补充：本轮未提交的“去重加入工作区”初稿忽略了旧版指纹。独立临时脚本在工作区未变化时重提旧候选，实际生成 id 2 并使 id 1 变为历史；反例 **1/1 准确失败**（0.418s，`legacy-replay-red.log/json`，完整现场 `legacy-replay-red-scene/`）。这是本轮初稿的新兼容问题，未归因于 `2bb56f4`。当时首次全量尚未结束；待其按未改动字节完成后，补齐安全的旧指纹重放并重新验证，未将首轮全量作为最终证明。
- 首轮全量：**925 tests，351.927s，OK（skipped=16）**，退出 0，219 个受测文件前后未变（`full-unittest.log`、`validated-files-after-first-full.json`）；由于随后补上旧指纹兼容，这一轮不是最终代码的全量证明，原日志和跳过清单保留。
- 兼容补齐：新候选仍按工作区指纹去重；找不到时只对证据仍有效的旧指纹返回原候选，不改原记录、不补写工作区。已有回归加强为“原工作区重提返回同一候选、维护后即使恢复旧 Git 引用也须新登记”；保持全部原断言，之后重新定向、敏感性、稳定性和全量。
- 最终定向：补齐旧指纹重放后，同一 12 模块命令 **140/140 通过**（50.665s，0 跳过/失败/错误，退出 0，`targeted-final.log`）；旧候选原工作区重放不新增记录、不补写输入，换工作区后生成新候选。5 组故障注入再次 **5/5 命中预期断言**（`mutations-final.log`、`mutation-final-results.json`），完整现场另存 `mutation-final-scenes/`，没有覆盖之前日志。
- 最终稳定性：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<本轮证据目录>:tests:. python3 <本轮证据目录>/stability-final.py`，20 轮轮换顺序，**300/300 通过**（168.644s，0 跳过/失败/错误，退出 0）。包含加强后的旧指纹重放/更换工作区用例；219 个文件每轮及结束哈希一致（`stability-final.log` / `stability-final-results.json`）。再核对所有负向归档共 18 个监管任务，登记 PID 均不存在，原始身份/输出一致、清理 complete（`negative-scenes-cleanup-final.json`）。随后运行最终全量。
- 最终全量：`NO_PROXY='*' no_proxy='*' PYTHONPATH=<本轮证据目录>:. python3 -m unittest discover -s tests`，**925 tests，363.250s，OK（skipped=16）**，即 **909 通过、16 跳过、0 失败/错误，退出 0**。逐项核对为 14 项缺可选 MCP SDK、2 项缺 cryptography（`optional-skips-final.json`）；没有联网安装。资源关闭警告原样保留，失败现场捕获未触发，子解释器仅继承离线保护。最终 219 个文件前后 SHA256 一致（`validated-files-before-final-full.json` / `validated-files-after-final-full.json`）。
- 跳过原因核对：汇总脚本首次只按原因文本分类，遇到 `test_sign` 的 `needs both` 而断言失败；读回原测试装饰器并检查环境，确认 ssh-keygen 存在、cryptography 缺失，因此两项签名跳过均由后者造成（`skip-environment.json`）。保留原始跳过身份与原因，不将这个汇总脚本问题当成测试失败或修改跳过条件。
- 最终审查：生产只改 `tmh/platform/candidates.py` 与 `project_library.py`，新增 `tests/test_library_transactions.py`，更新使用说明及本文件。原 83 个测试文件逐字未改；Store 及五个保护/监管文件未改；schema/configure/derive/reference/act/_run/_write_run_inputs 的 AST 与 `2bb56f4` 相同（`invariants-final.json`）。读回完整新测试及最终 diff，文档链接/围栏和 `git diff --check` 通过。
- 收尾：在 `feat/ralph-port` 独立提交，标题 `fix: 修复候选证据绑定与事务读取隔离`；提交号写入本轮外部证据 `validation.json` 并核对提交字节，不 push。原 `ralph-port-preflight-2026-10-19` stash 保留；不访问真实 data/凭据，不更改 Git 配置，不启动日常服务。
- 人工重点审阅：候选登记内工作区/需求/授权复查与输入同事务写入；旧指纹只在证据有效时重放；`run_current` 的读取 SAVEPOINT 及其在外层写事务中的释放语义；缺失历史绑定不得补写、换工作区后即使 Git 引用相同也须重新登记。无新增待确认；P5 人工确认/guard、P6 锁的原审阅重点及 Windows 六项剩余阻塞清单保持，不宣称已完成 Windows 实机验证。
- 日志校验：`review-red.log` 7598 字节 / SHA256 `5f3400ec562d582a6514dc4662306558ab6bf8a72f4e9eb6f19133fd5cb864e2`；`legacy-replay-red.log` 965 字节 / SHA256 `7e73e5081f1a8dcf799df7ebda4b4e63ee4be70995132d4cb196d644402a0f7e`；`targeted-final.log` 25664 字节 / SHA256 `4ff193e6aa5f61c73edf9010f98c862aaad6d8d481a2650960b6eb8a2f103a1f`；`mutations-final.log` 6635 字节 / SHA256 `82ed869d847562fcf0a889ca2c3c1ee8f48f97caa423e0afd207bfebd7a6b5b7`；`stability-final.log` 57438 字节 / SHA256 `77a34d3565026c5c8b82bb0c70d512147ea511acbbefd93fc2ae3fdfdc42595f`；`full-final.log` 23185 字节 / SHA256 `a604236817de8f6df8bb077aa6b14ace3c09a450934b41606e511a834c3842d2`。全部原始失败场景、脚本、首轮/最终日志保留，完整文件清单见 `evidence-manifest.json`，没有压缩或截断原文件。

## 后续：发布 9ba7a3a，候选更新为 0788a52（2026-10-20）

- 状态：doing（SSH 已恢复，正在隔离验证及备份）；用户明确要求“上线吧”，授权本次生产发布及必要接入检查。继续 `feat/ralph-port`，初始源码为 `9ba7a3a41605602dbae07ad1d82d89a73d86bb2e`，最终发布候选为下方 `0788a52`；不开新分支，不 push，不更新本地日常 8791/8793，不读取或打包本地真实 data/。生产数据仅在服务器上做一致性备份、迁移和保全核验。
- 已读本文件、`git log --oneline -10`、生产接入记忆及部署脚本。开工工作区干净，原 stash 保留。
- 目标核对：本仓库脚本使用 `webuddy.bbstack.date` / `webuddy.service` / `/opt/webuddy/app`，现存旧记忆中的 `factory-web.service` 属于另一仓库，不能混用。直连目标域名的 TLS 校验通过、IP 为 `43.153.76.85`、首页 303 跳转 `/login`；不把可达性视为当前版本已上线。
- 待接入：本机 `/Users/auntlee/.codex/memories/webuddy-production-access.md` 明确记录临时部署授权于 2026-09-30 18:23:35 CST 到期，本项目的历史部署脚本也沿用该凭据名称。已异步询问有效 SSH 配置或本机凭据路径；不索取私钥内容，不使用过期/撤销凭据，不借用其他用途账号绕过。此项是缺少有效接入信息，用户无需重复授权上线。
- 发布准备目录：`/Users/auntlee/Desktop/workspace/运维智能体/部署包/ralph-9ba7a3a-20261020/`。固定 Git blob 导出 164 个运行时文件，生成未压缩 `webuddy-9ba7a3a.tar`（3,112,960 字节，SHA256 `e2d125acc9d3aa407dfb930a077e0f72c404e2a739d04dcd534fe94ee8e815b2`）；含完整运行依赖的模板、技能、知识库及 `install()` 所需 `docs/agent-commands.md`，无生产数据、私钥、证书或环境文件。
- `python3 prepare.py` 成功；实际打开 tar、解包并逐项读回，287 个运行时及测试支持文件的字节和模式与提交一致，清单在 `package-verification.json`。发布/回滚步骤及接入阻塞写入外部 `上线记录.md`，具体服务器布局和备份锚点仍待登录后实测。
- 正在从实际发布包解包的代码运行完整回归：`NO_PROXY='*' no_proxy='*' PYTHONPATH='../diagnostics:.' python3 -m unittest discover -s tests`。完整输出保存 `full-unittest.log`；仅合成数据、临时仓库与回环连接，原断言、时钟及测试文件不改。
- 首轮导出回归：**925 tests / 907 通过 / 2 失败 / 16 可选依赖跳过，336.439s，退出 1**，原包、导出树及完整日志原样保留。失败之一为 `examples/legacy-dotnet-erp/Erp.Core/Data/ErpContext.cs` 在本地存在但被大小写不敏感的 `data/` 忽略规则排除、从未纳入提交，干净导出缺少 `Customer` 实体；另一项是发布清单遗漏 `docs/dead-ends.md` 引用的四份验证文档。这是对发布物的实际验证发现，不能用原工作树通过结果覆盖。
- 修复：只为上述合成 `.cs` 文件增加窄范围忽略例外并将原字节纳入提交，其他 Data 文件及真实 data/ 继续忽略；导出清单加入四份既有验证文档。未改产品代码、原测试、断言或超时。修正后独立导出副本运行 `test_tmh.DotnetTest test_tmh.InstallTest`，**5/5 通过，0.404s，退出 0**（`export-fix-targeted.log`）。失败原因和补齐文件哈希在 `export-failure-analysis.json`。
- 包启动验证：从实际解包目录在系统分配的回环端口启动真实 `serve()`，合成账号/令牌、空数据库；登录页 200、匿名项目 API 401、带令牌项目/API 元信息/主页面 200，共五项检查通过。共享令牌未获得人工身份；服务退出码 0、临时数据清理，日志在 `smoke-server.log` / `smoke-result.json`。未启动日常端口或连接模型。
- 接入续期：用户已明确回复“这个锁已经手动延期了，你也可以更新一下我们的信息”，已更新本机接入记忆，注明确切新到期时间未提供。两处已有本机凭据均为 0600、指纹与登记公钥一致；未输出私钥。
- 实测 SSH：严格主机检查通过并显式提交登记的部署公钥，但 `ubuntu@43.153.76.85:22` 返回 `Permission denied (publickey)`、退出 255；详细诊断已保存 `ssh-check.stderr`。尚未执行远端命令，不能断言拒绝仍因过期；已异步请用户核对服务端授权或提供当前接入信息，不重复询问上线许可。
- 发布候选更新为 `0788a52e1b517b33fbe9b593be200d1c060a1cc4`（`fix: 纳入被忽略的 .NET 回归示例`）。`tmh/templates/skills/agents/kb/tests` 相对 `9ba7a3a` 逐字未改。新发布目录 `../部署包/ralph-0788a52-20261020/`，168 个运行时文件、292 个运行时及验证文件，实际读回字节/模式一致；包为 3,174,400 字节，SHA256 `758c2d075cbfdcd50a4c96649bf373284f4f14d0a8305d26064b6c53e0a1f20c`。
- 新包五项实际 HTTP 启动检查再次通过，退出码 0、合成数据清理。正在该包实际解包代码的 `test-source/` 再运行完整 `python3 -m unittest discover -s tests`，保留旧包及首轮失败日志，不用旧结果替代本轮结论。
- 最终包全量：**925 tests，352.660s，OK（skipped=16）**，即 **909 通过、16 跳过、0 失败/错误，退出 0**；14 项缺可选 MCP SDK、2 项缺 cryptography。`full-unittest.log` SHA256 `574661a9239c5db43e9a7b08121390c8f27ec51985d878fde74a163970fc1c63`，完整跳过身份/原因见 `diagnostics/optional-skips.json`；292 个文件执行前后字节/模式一致，结果绑定 `0788a52` 与发布包的 `validation.json`。失败捕获未触发，原资源关闭警告完整保留。
- 本轮实际结果：发布准备与验证完成；生产 SSH 仍拒绝已登记公钥，尚未上传、执行远端命令、备份/迁移生产数据库或重启服务，因此**未上线**。待服务器恢复对应公钥权限或提供新的有效接入信息；已有上线授权继续有效，不再重复询问部署许可。恢复后先按新发布目录的 `上线记录.md` 核对远端实际布局与数据，再进行切换与线上验收。
- 收尾仅追加本进度记录并单独提交，不改变受测发布源码。续期及本机实测拒绝均已写入 owner-only 接入记忆（0600）。原 stash、首轮失败包、全量日志、SSH 诊断和最终包均保留，不 push。
- 恢复推进：用户再次回复“已经更新了授权”；严格主机校验、显式已登记公钥登录成功，免密 sudo 可用。先读本文件与最近 10 条提交，工作区干净、HEAD `654c73b`，不重做已完成的本地发布包全量验证。接入记忆已更新；新到期时间未知，不假定永久授权。
- 服务器只读预检：`webuddy.service` active/running，`/opt/webuddy/app` 为普通目录、无 `.git`，端口 8790，外部配置 `/etc/webuddy.env`；Python 3.12.3、Git 2.43.0。应用 6.1M、数据 57M、磁盘空闲约 34GB。SQLite quick_check=ok；3 个项目、49 张工单、254 次运行（done 243 / failed 11），无 queued/running；自动流转 `on=false`，无调查状态、无服务子进程。`factory-web.service` inactive，Caddy active，均不属于本次变更。证据续存 `../部署包/ralph-0788a52-20261020/production-resume/`，此前拒绝记录保持。
- 隔离发布目录：`/opt/webuddy/releases/0788a52-20261020`。通过 SSH 上传原始发布包及只含固定提交源码/测试和离线诊断的验证包；首次未压缩传输较慢，停止本任务上传后用 SSH 无损传输压缩重传，服务器逐包 SHA256 和 168 个运行文件 / 292 个验证文件的字节、模式全部一致。未压缩 tar 原文件不变，旧服务仍运行。
- 迁移演练：SQLite backup API 在服务器创建 0700 隔离目录下的一致性副本，执行真实 Store、复检及候选 schema，然后再次执行。`integrity_check=ok`；原 9 张表全部原列与原行哈希一致，第二次执行后所有表一致；13 张新表仅项目档案和来源各 3 行，其他均空，未补写历史输入或人工决定。副本及明细留在服务器 `migration-rehearsal/`，本地仅保存计数、模式和哈希；没有将真实业务数据下载进仓库。
- Linux 验证：正在服务器隔离的 `verification/test-source/` 执行完整 `python3 -m unittest discover -s tests`；独立合成数据，Python 子进程只允许回环连接，原测试、断言、超时均保持。验证及真实服务启动检查均通过后才切换；服务器生产目录尚未迁移或停服。
- Linux 首轮完整结果：**925 tests / 902 通过 / 9 errors / 14 跳过，415.194s，远端退出 1**。9 项均在三个测试模块调用 `Store.db.iterdump()` 时抛出 `no such table: name`，尚未运行到对应的数据库不变断言。Python 3.12 的标准库导出器沿用 Store 的字典 row_factory，把 `name/type/sql` 键误当作行值；本机 Python 3.14 已在导出器游标上设 `row_factory=None`，故原本通过。完整失败日志 `production-resume/linux-full-first.log`，SHA256 `defbbc3f2142c8f25aa1b129c8388d52aa3f454ca0caa573afba24c83bf3f8ac`，原 292 个验证文件前后未变。
- 此轮远端测试已退出并写入结果文件，但原 SSH 响应连接停滞；通过新的严格校验连接读回结果、确认测试进程不存在后，仅关闭该本机旧 SSH 客户端。后续连接增加会话级保活参数，不改 SSH/Git 配置；没有把传输失败混作测试成功。
- 兼容修复：新增 `tests/sqlite_snapshot.py`，持有 Store 锁把整个已提交数据库备份到独立内存连接，再用默认行格式完整导出；不修改活连接的 row_factory，不删表/字段/记录。遇到未提交事务立即报错，不隐式提交或忽略变化。三个原测试模块仅替换快照取法，原相等性/证据/人工确认断言、超时及产品代码保持。新增两个测试验证文本/二进制/NULL、触发器/视图/索引/序列完整保留、数据或结构变化能被发现，以及未提交写入不会被隐藏。
- 定向命令：`python3 -m unittest -v tests.test_sqlite_snapshot tests.test_intake_recovery_api tests.test_preview_health_independent tests.test_python_pathmap_api`；同样的离线保护下，本机 Python 3.14 **25/25，11.581s，退出 0**，服务器 Python 3.12 **25/25，17.760s，退出 0**。服务器使用独立 `verification-fix/`，原失败树和日志完整保留；定向日志及修复五文件 SHA256 在 `production-resume/`。准备单独提交 `test: 兼容 Python 3.12 的数据库快照断言`，随后从该提交重新导出并在两端执行完整回归；当前仍未切换生产服务。
- 启动行为复核：旧版和新版人工分支扫描的 heartbeat 完全相同，settings 只增加提醒天数，原启动默认值不变；三个既有项目当前没有 `wb/*` 引用，没有未验收的手工认领记录，调查配置为空。首个检查错误地要求整个 settings AST 完全相同，失败后保留原记录，再按实际差异做精确核对；没有改产品行为或放宽基线测试。


## 2026-10-26：独立 Codex 项目配置与 API 分发

- 人类本轮要求保留 API 接入和分发，为只接受官方 Codex 的网关建立独立配置。继续当前 `iteration/context-pack-v2`，起点 `9ae7ded6af9e7768561f410264185fd4f8d82b2d`；读取项目约定、接入记忆及最近十条提交。未恢复旧失败实验、未改变人工采用或关单规则。
- 实现：增加官方 Codex alias/profile 与完整 stdin 输入、JSON 完成答复/用量读取；新增项目路由、allowlist、直接模型 API 开关；API/CLI/MCP 接单和普通项目配置保留。页面的工单、交付、知识分析和助手使用同一项目路由。缺失执行器或非法配置明确停止，旧全局偏好不会自动改变通道。详见 [使用说明](../codex-project-route.md)。
- 独立审查发现并关闭三项 P2：普通日志误判模型成功；不可用的项目执行器被页面自动替换；助手旧全局偏好绕过项目默认。完成判定改为退出成功、完成事件、非空模型答复同时存在。缺失配置保留可见；交付默认停止，本项目明确改选仍允许。原测试断言和时限未削弱。
- 真实连接：服务器原安装官方 Codex 0.162.1，通过新的 owner-only `webuddy-cloudwave.config.toml` 继承现有 provider，一次受监督启动成功，3.486708 秒，得到正确合成答复。原基础配置字节未变；无真实业务内容、生产工单或服务变更。客户端报告输入 13,142 / 输出 13，缓存输入已包含在输入内；实际底层模型身份、HTTP 次数及账单未知，不据此宣称 RSI 成功。不再重复调用。
- 模拟完整流程：真实本地 HTTP 建单和启动 → 专用 alias → 真实隔离 Git 工作树改码 → 实际项目检查 → 保留差异、验证及进程回执。执行器是合成本地进程；主工作区及 HEAD 保持，没有人类采纳决定。
- 独立复核：42 项定向测试全部通过（4.752 秒）；另外 5 个真实合成进程完成判定案例、实际助手渲染及交付事件绑定通过。浏览器打开实际选择函数的独立验证页，确认专用/普通/缺失配置三种选择状态，保存原始截图；不是生产页面验收。
- 原始回归失败保留：首轮使用了不存在的 `test_ui_delivery` 模块（已纠正为 `test_delivery_design`），两项原生命周期用例失败；不改原测试的定向重跑 11 项通过。第二轮 258 项，257 通过，原手工构建 0.6 秒时限用例在模型/构建进程登记前超时，访问空 attempts 报错；相同模块和最终 UI 共 22 项原断言/时限重跑通过（10.494 秒）。最终整套回归和精确发布结果继续追加，不把失败记录覆盖或归因于已证明的环境问题。
- 证据：仓库外 `分析/implementation/20261026-codex-route/` 保存完整日志、真实连接原件、独立审查报告与文件哈希。未改 acceptance、guard、process_control、supervised_process、filelock、状态迁移或租户权限；自动流转保持关闭。
- 当前边界：`learning_runs` 的独立知识实验仍只适配原 Claude 隔离执行器。本批完成普通任务路由，并未接通此实验的 Codex 等价隔离。真实跨任务收益、LYB/LLA 本人交接/采用/验收、长期试点及整体 80% 尚未证明；不会因连接和测试通过加分。
- 发布准备：本机公开指纹、0600、严格 known_hosts SSH 与 sudo 新鲜核验通过；现役仍为 `c08b6ae...`，无 queued/running，`agents.json` 与 `agent-routes.json` 不存在，自动流转关闭。本批将按既有自动发布授权进行精确提交、Linux 兼容与数据副本检查后再切换；切换结果另记。
- 最终本机定向整套：16 个相关模块 **259 tests / 259 通过 / 0 失败错误 / 0 跳过，176.590 秒，退出 0**（`integration-sealed.log`）。覆盖 API、租户隔离、工具接入、运行/直接调用/手工构建生命周期、知识会话、需求理解和 UI。原 ResourceWarning 保留，不宣称全部测试无资源警告；没有重复完整 2,510 项旧基线全量。

- 候选 `975d7660553475a2f1e86f2b79d2db7310fd68fc` 已普通推送，未激活。精确发布包 Linux 259 项通过（221.229 秒），数据副本 Store/Registry 两次初始化保留原 70 业务表和 11 控制表的模式及记录；Mac 精确包 259 项有 1 项原总预算测试失败（登记到 1 个进程，原断言要求 2），188.922 秒。完整日志/失败现场保留，未改断言、时限，不把 Mac 此轮称通过。
- 上线前外部独立复核发现 `ROUTE-RETRY-REVOKE-01`（P2）：开启忙时重试后，在等待间撤销原执行器，第二次进程仍启动。示例的 retry_busy=false 不触发，但公共配置允许开启，因此暂停旧候选激活。原真实合成反例 2 次启动（预期 1），原件保留。
- 最小修复：在 invoke 内所有 spawn 紧邻 _spawn 前重新 resolve，兼顾忙时重试与恢复失败后的全新调用。新增 3 项回归，撤权/坏 JSON/alias 删除后只保留第一次实际进程与完整回执；未变路由允许第二次成功，恢复失败后撤权也阻止 fallback。原重试、取消及上下文检查保持。
- 修复验证：主任务复制原反例逐字执行通过，独立复审再次执行同字节反例通过；profiles 13/13（独立4.000秒）。相关 profiles/route/learning_sessions/direct-invocation 四模块 **63/63，17.111秒**；`git diff --check` 通过。新提交与双端精确包验证另行绑定，旧候选证据不冒充新候选通过。

- 2026-10-26 15:41:36 CST：新候选 `bdcd5f9` 已上线，221 运行文件一致；精确 Mac/Linux 均 **262/262、0 skip**，耗时175.115/223.499秒。完整备份读回、立即/60秒延迟12项HTTP、后续10项旧共享token负控通过。70业务/11控制表原schema和行保持，其他项目/权限/自动流转保持；详情 [上线记录](../../audit/production-deployment-2026-10-26-codex-route.md)。
- 实际启用 `cloudwave-codex` 和 PPTAUTO 路由，原基础模型配置保留。只读后验脚本首版误写组编号1000，现场ubuntu实际为1000:1001；保留首版失败后按账号实值复核通过，未更改生产权限。未新增模型调用、用户会话或人工决定。独立学习实验Codex适配、真实跨任务收益和多人长期试点仍未完成，整体80%未认定。


## 2026-10-26：中性主题 UI 与窄屏信息完整性

- 2026-10-26 17:11:36 CST：`1245231d4eda1def019c289ad79159533b493b27` 已上线并普通推送 GitHub；221 运行文件精确一致。浅灰/白/深色字/蓝色交互替换旧绿色低对比界面，管理导航高亮和窄屏工单/团队字段完整性修复。
- 实际桌面与390 px渲染、弹窗/键盘焦点/设置选中状态通过；独立254项通过，精确Mac/Linux各254/254、零skip。产品仅5个UI文件，无schema、后端权限或业务状态迁移变化；原断言保持。
- 首轮独立回归因导入路径遗漏产生5个模块加载错误，修正执行路径后原测试通过；传输慢链路、SCP超时、首次root锁权限预检失败均保留。没有以失败当通过、修改锁权限或重复停服；最终差量重建两个精确归档后以既有sudo身份一次实际切换。
- 数据副本70业务/11控制表schema与原行保持；共用锁、完整备份读回、即时/60秒HTTP、后验配置/全部原非DB/项目/服务保持通过。模型路由两文件未写入，未调用模型或代人操作。详情 [短上线审计](../../audit/production-deployment-2026-10-26-ui-neutral.md)。
- 只完成本批UI交付。真实跨任务收益、LYB/LLA本人长期试点及整体80%仍未认定。


## 2026-10-26：Codex 无模型协议与纯证据核验（第一批）

- 状态：doing。开始时工作区干净；基线 a1333a530d2db8b9338741fb80cb0a833ee094f8，继续当前 iteration/context-pack-v2。按仓库外前瞻包实现窄范围协议，不开启真实执行、不读取私有留出或凭据、不创建实际合同/试点窗口，暂不发布生产。
- 新建 scripts/rsi/codex_protocol.py、tmh/platform/codex_learning_evidence.py 和必要反例测试。严格新schema与外部保留的manifest摘要绑定，只读原始输入/JSONL/监督回执；不导入执行器、不写DB、不接人工采用路由。即使文件一致，也始终 adoptable=false、execution_admitted=false；执行真实性、输入实际送达、隔离、未见性、绝对期限均未证明。
- 首轮新增定向 python3 -m unittest -v tests.test_codex_learning_evidence：11/11，0.165秒，退出0。含真实合成进程监督回执读回，非真实Codex/模型；首轮日志保存在仓库外 分析/implementation/20261026-codex-evidence-v1/first-targeted.log。随后自审收紧回执字段、非有限JSON和增长中原件，补充兼容与缺字段反例，尚待最终定向。
- 不修改旧 native_learning.py（避免其自文件哈希承诺失效）、旧schema、guard/评分器/人工决定/状态迁移/进程监管语义。隔离/认证/出口和完整运行闭包仍是后续真实实验前置，未因这批无模型实现而宣布通过。
- 自审中间失败：严格字段版15项中14通过、1错误（0.276秒、退出1）；真实监督器的运行中回执含supervisor_pid，初稿未列入允许字段。按真实格式把该字段设为必需，并要求计划/最终值一致；合成夹具同步补真实字段，不改原测试或时限。日志 strict-targeted.log/json 原样保留。
- 最终定向：python3 <仓库外>/20261026-codex-evidence-v1/targeted_runner.py，原新测试方法与断言不变，仅在原清理前保留合成现场；16/16、0 skip/失败/错误，0.260秒、退出0。16个现场及实际合成进程的原始监督回执/输出已读回，cleanup complete/output_complete且无remaining_group。未运行全量或重复旧合成整套。
- 文件替换防线覆盖逐层无符号链接打开、硬链接拒绝、owner-only模式、文件读取前后身份、目录替换（即使保留文件inode）与末次读回。严格拒绝重复/非有限JSON、未知schema/字段、缺失/矛盾回执、failed/unknown/清理不完整；客户端原始报告用量不等于实付，绑定记录数不等于真实exec或HTTP次数。
- 不变量：14个既有关键文件与a1333a5字节一致，包括旧native_learning、learning_decisions、learning_eval/runs/experiments、trial_preparation/provider、acceptance/guard、锁与进程监督器；invariants.json保存逐项SHA。原schema拒绝新合同，原采用路径拒绝新观察类型的反例通过。没有新采用路由或台账迁移。
- 状态：done（限本批无模型格式/只读文件绑定实现和本机定向），待作者外审查；不是隔离/真实执行/知识改善验收。文档见 docs/codex-learning-evidence.md；待后续证明的真实认证/出口、运行闭包、可信原子台账和派发/输入送达/未见性均未抹去。旧b2a6和旧题保持停止。
- 待确认：本批无须用户决定；外审查与后续真实实验另按固定交接安排。当前仅本地提交审查，不启动模型、不改生产、不调用SSH、不push。
- 提交前diff自审补出JSON类型混淆：Python相等比较可把true/1.0当作整数1，原初稿监督回执的跨文件比较和output字节数字段不够严格。保留初稿源码，以新增同一条反例重放，17个子场景中11个准确失败（typed-receipt-red.log，退出1）；改为跨回执同时比较JSON类型，明确检查pgid和输出字节数整数。仅本轮新文件的未提交初稿存在此问题，不能归因于基线。
- 最后字节定向：targeted_runner_v2.py，17/17、0 skip/失败/错误，0.705秒、退出0；保留17个完整合成现场 final-scenes-v2/，上一轮16项日志/现场和类型反例原件不覆盖。源码未再改变；git diff --cached --check通过。当前格式只核对外部承诺的文件绑定，真实exec/输入送达、官方客户端来源、隔离、未见性、总期限和采用资格均明确false或unknown。


## 2026-10-26：Codex读取器根路径/身份稳定性P2增量

- 状态：doing。基线2e965c685555ab9c406a16c13214764cda689b8c，开始工作区干净。只依据仓库外独立files/review.md修复：规范检查后根open前的祖先链接、末次路径复核前的祖先链接，以及根私有检查后chmod三个窗口。原8个场景中3个异常接受的报告、脚本、特殊文件、原断言和场景保持原位；不重发审查或处理已失败的父会话。
- 修改范围限新读取器和回归：绝对目录链逐层相对已持有fd以O_NOFOLLOW打开，系统祖先只绑定目录节点，不新增owner-only要求；bundle及内部保持私有/链接限制。以同一份通过_private的stat作身份依据，读取后再确认对象、目录条目和绝对目录链。返回仍不可采用/不可准入，不改旧schema/guard/人工门，不调用模型、不部署。
- 原独立脚本在新的red/目录与原固定快照逐字重跑：7场景脚本和补充模式脚本均退出1，再现3个异常接受；未覆盖原scenes/FIFO/链接或报告。修复后的green/运行7+1场景均退出0、8/8符合预期。首个竞态仅将拦截条件增加“相对根目录名+dir_fd”分支，以适配新的逐层打开；所有原assert、预期拒绝、真实rename/symlink/write和其他负控AST不变，差异见probe-adaptation.json。三个窗口均确认真实变更发生、root inode保持；合法快照只读审计无写/进程/网络/DB事件，字节和非atime元数据不变。
- 定向：python3 <仓库外>/20261026-codex-evidence-root-fix/targeted_runner.py，21/21、0 skip/失败/错误，0.369秒、退出0。包含全部原17项及4项新增（3个窗口和系统祖先0755合法通过），原测试方法AST逐项不变；21个现场以保留symlink方式在原清理前保存。无模型、无真实CLI或新试点窗口；没有重复旧全量。
- 原独立审查113个证据条目的字节/模式/UID/inode/nlink或特殊文件类型按原manifest读回保持；14个关键既有文件、codex_protocol新协议字节不变。_events/_attempt/verify/_private/_identity函数AST不变，文件绑定通过依旧不授予采用/准入。所有证据在仓库外 分析/implementation/20261026-codex-evidence-root-fix/；原反例和原初稿不替换。
- 状态：done（限本地修复与增量验证），固定新提交后待作者外复核。git diff --check通过；修改仅codex_learning_evidence读取器、新增回归、使用说明及进度。不修改旧协议链/评分/guard/人工决定，不调用模型、SSH，不push或部署。


## 2026-10-26：Codex独立无模型持久台账（有限批）

- 状态：doing。基线2cc20eda7fc5fdfef1ac692e331fcc88879320c2，开始工作区干净；作者外根路径P2已在独立decision.json接受。只新增codex_ledger独立模块和测试，不接真实CLI、采用或旧native/provider/BC链；不新建rsi_prepare_%产品表，不创建真实合同/试点窗口，不push/部署。
- 范围：单一选定SQLite内固定合同/绝对结束点、原子预留→intent→结算声明或执行未知；取消、期限、代际停止保持累计槽占用。真实exec、任务验收、生产者身份和实付均不推断；计量未知不会自动变成执行未知，也不补零。跨数据库、真实派发和来源真实性仍未准入。
- 首轮定向 python3 -m unittest -v tests.test_codex_ledger：17/17、0 skip/失败/错误，0.099秒，退出0；initial-targeted.log及未提交初稿源码保留。自审补出持久化设置缺口：journal_mode=OFF仍可接受预留。新增同一反例在初稿退出1，出现“未拒绝”和“预留泄漏”两条失败（durability-red.log/scene），不是两项独立问题，也不归因于基线；增加每个写事务FULL/EXTRA同步和有效journal检查，旧代码不动。
- 最后字节定向 targeted_runner_v2.py：18/18、0 skip/失败/错误，0.110秒、退出0。两个真实SQLite连接同request仅一次新intent、不同request不重复占在途槽；真实触发器注入证明预留/intent/停止事件失败整体回滚；一个真实本地Python新进程重开保持原绝对结束点、累计与intent后unknown停态。初17/18项记录与场景不覆盖；最终18个完整SQLite现场和子进程原始stdout/stderr/退出码保存在仓库外 分析/implementation/20261026-codex-ledger-v1/。
- 读回18份最终数据库：integrity_check全部ok，表名无rsi_prepare_%；namespace哨兵最终使用legacy_synthetic命名，前轮临时夹具/日志保持。原前瞻包22文件及相关旧链共29份与2cc20ed字节一致，包括旧trial_preparation/native/provider/BC、guard/人工决定、新协议/只读读取器及其原测试；invariants.json固定逐项SHA。本批不重复旧整套/全量。
- 状态：done（限单一数据库内无模型台账与新增定向），固定小提交后待作者外审查。真实启动计数与任务验收仍None；settled只是未认证结算声明，计量unknown不补零、不当执行unknown。固定窗口/合同不允许换request或重开刷新，所有历史预留占槽；停止操作抛Stopped时停止已提交，其他失败回滚，不以异常作成功。
- 边界：仅补C03–C05单DB事务和累计；跨DB/备份回退/root别名、真实输入/权限/派发、来源认证和采用均未准入。没有实际合同/试点窗口/模型/真实Codex/真人决定，没有产品自动集成、push或生产部署。文档 docs/codex-ledger.md。


## 2026-10-26：Codex台账TX01停止提交失败增量

- 状态：doing。基线8c55783f71407bb20a6d814b4ca73743228da037，工作区开始干净。依据独立transactions/review.md只修Stopped分支commit失败未rollback的P2；原独立18项通过不抵消该问题。MONO01只收窄文档，不改时间语义，不重复旧整批。
- 新增真实第二SQLite连接持读锁的停止提交反例及普通提交对照。修复前两项定向：停止反例失败（SQLITE_BUSY后仍in_transaction），普通提交对照通过，退出1；原日志与未修源码保存在仓库外 分析/implementation/20261026-codex-ledger-tx01/。没有替换commit或事务函数。
- 最小修复：Stopped分支仅增加commit失败时rollback后原样抛数据库异常；只有commit成功才重新抛Stopped。不自动重试、执行或reconcile，不改其他台账方法。MONO01文档收窄为“单调读数低于本实例初始值”，明确默认系统时钟不回退，100→104→103不保证停止；_sync等其他方法AST不变，不扩时间机制。
- 原独立commit_busy_probe.py逐字复制到全新red-probe/、green-probe/运行，场景和普通提交对照保持；两份均原样返回SQLITE_BUSY/5/database is locked。红灯Stopped分支遗留事务，绿灯回滚退出；绿灯writer/reader视图相同、放锁后snapshot可用，关闭无未提交停止。原探针无红绿失败断言，本身退出均0，按结构化结果判断，绝不把红灯退出0当通过。原脚本内8c提交标签保留，实际快照绑定另记probe-commands/invariants。
- 窄定向：targeted_runner.py只跑2条新增真实读锁用例和原成功Stopped提交用例，3/3、0 skip/失败/错误，0.169秒、退出0；保留3个完整SQLite现场。断言提交失败原始OperationalError/SQLITE_BUSY、无遗留事务/半提交事件、累计与固定期限不变；放锁后显式reconcile持久化expired/unknown，第三连接可见。普通提交对照回滚且后续可用。没有重跑旧18项、模型或时间专项。
- 不变量：29+4共33份旧保护源码字节不变；Ledger除_transaction外全部方法AST不变，原所有测试方法AST不变，只增加两项和读锁夹具。三个数据库integrity_check及红绿原件读回通过；证据在 分析/implementation/20261026-codex-ledger-tx01/。
- 状态：done（限本地TX01修复和窄增量验证），固定新提交后待作者外复核。所有不可采用/不可准入、未知计量/真实启动和真实生产者边界保持；不接CLI或人工采用，不push/部署，不访问私有留出或凭据。

## 2026-10-27：权威输入与固定合成派发 v2（当前恢复任务）

- 状态：doing。当前任务是实施已接受的 codex-authoritative-dispatch-preparation-v2，seal `8ce9cae2bde26fe068ca5fbd8373336c3f267fbad6b711a1c9996664d9f88080`。基线 fabb52e，开工工作区干净。上一轮压缩后误转组织审计，153项审计和2个能力探针保持为独立材料，不能替代本纵切实现或P01–P12验收。
- 下一实际步骤：先为新 Ledger 增加受控 Store 连接借用、专属游标 Row 与事务内私有核心，再新增内部 codex_dispatch_probe 及本切片定向测试。压缩后先恢复这一项，不重做旧组织审查，不再增加方案门。
- 约束：仅新 Ledger、新内部适配器、新测试及必要文档；33份保护源码与旧 rsi_prepare_% 表集合保持。混合异常含 Stopped 全回滚后独立 stop-only；同槽最新检查→control→T2串行；重放不得改首次原件；只用既有单监督链，计入原绝对期限与清理。P01–P12实际结果、红灯和现场将逐项补记。
- 本批本地实施，不调用真实官方CLI、模型、凭据或私有留出，不SSH/push/部署/采用，不创建真实实验窗口；不恢复旧预算/API门。唯一产品作者工作，固定小提交后待作者外代码运行审查。
- 已实施新 Ledger 受控借用/游标 Row/事务内 reserve-intent-settle 核心及内部固定探针，未动33保护文件。T1/T2、一次性 owner、缺失命名 lesson 锁拒绝、完整参考原文/二进制保留、原绝对预算、两个完成窗口均已接线；无公共入口。
- 初始2项因夹具未建 runtime 目录而错误，原日志 initial-targeted.log 保留；该首轮发生在场景采集器加入前，临时目录已清理，不能补造原现场。加入保留器后2项因本轮初稿未 strip Git HEAD 尾换行而错误，first-targeted.log/first-scenes 保留；修正后 second-targeted.log 2/2，退出0。未改协议或既有断言。
- third-targeted.log：13项新接线+4项必要旧接口/TX01对照，共17/17、2.935秒、退出0；夹具 counts 的 SQLite context 未关闭连接产生警告，改用 closing，原日志保留。fourth-targeted.log：30/30、9.568秒、退出0。fifth-targeted.log：36/36、10.826秒、退出0，含完整授权参考与二进制、真实三代取消/超时、on_spawn后撤权/owner丢失、终态封存和结算提交故障。
- 外部证据目录：`分析/implementation/20261027-codex-dispatch-probe/`。已保存 fourth/fifth 精确受测源码和逐测试完整临时数据库/运行原件；不是模型或实际知识实验。当前仍doing：自审补齐并发测试确定性屏障、单控制器不换槽及入口预算不重置，准备最终定向、必要窄接口回归和敏感性反例；之后固定小提交并封存，不以第五轮36项当最终字节证明。
- 最终自审补齐：并发争用以屏障确保首次claim仍在途时第二控制器返回；不完整setup即使claim未提交也标待核对；一个已准备控制器不能换槽或刷新入口预算；权限绑定使用现行effective角色，冗余管理员grant和无关成员变更不误拒绝。活跃期间同控制器只读重放不得关闭首次watch，watch还核对持久launch owner。均为本轮未提交实现的自审修正，不归因基线。
- `run_checks_v2.py` / `final-v2-targeted.log`：41项本纵切加6项必要旧公开接口/TX01对照，共47/47、12.529秒、0 skip/失败/错误/资源警告，退出0；不跑旧18整套或全量。核心运行/并发/重放/清理/完成故障7项轮换3轮，21/21，三次均退出0，原始日志 stability-v2-1/2/3.log 保留。P01–P12逐项实际用例与边界另存 acceptance-results.json，不能外推真实执行准入。
- 敏感性：只在各自独立诊断进程编译载入四份明确不安全变体，不修改工作区产品文件。Stopped时错误提交混合业务→准确出现新run/输入/占槽泄漏；放开owner重领→实际新target出现但封存owner矛盾；同控制器重放错误关闭watch→命中watch断言并由夹具清理；不完整setup隐藏待核对→命中状态断言。四项分别退出1（3条断言失败、1条owner矛盾错误），不是正常测试失败，也不是4条修复前基线缺陷。red-v2-* 的有效源码/完整日志/数据库/进程原件全保留；早轮red-*不覆盖。
- 现场读回 `verify_scenes.py`：全部历史与最终/负向归档共106次监督合成目标调用，原始输出长度/SHA/监督身份一致，清理complete，登记目标/监督器及就绪三代PID均已不存在；416份临时DB integrity_check均ok，rsi_prepare_%集合未新增。归档保留原folder身份，未篡改为复制路径的可恢复回执；不把106合成目标计为Codex/模型/HTTP调用。33保护源码逐字与原清单一致，原三张台账DDL相同，原测试文件未改。
- 状态：done（仅实施与本地窄验证），固定本地小提交并封存后待作者外代码/运行审查；尚未有作者外通过结论。新增内部adapter、受控新Ledger、新测试、使用文档及本进度；没有路由/启动自动集成或采用。待确认/剩余证明：真实官方客户端认证与运行闭包、A候选待定schema、私有未见BC、本人采用/新D、Windows与直接fork宿主复用均未接入或证明；当前不向用户索要预算/API或开展上述工作。工作区收尾以提交后核验为准，不push/部署。

## 2026-10-27：独立知识运行的项目执行器配置适配

- 状态：doing。基线0f5bd8a，开始工作区干净；继续当前iteration/context-pack-v2。作者外已接受reset-v3公开Python载体17/6与原清理，只代表公开切片；官方命名权限canary仍在仓库外准备，真实模型父进程隔离尚未接线。
- 现在直接实现learning_runs.py的项目route解析、有效Codex配置冻结、同一配置向step传递及少量真实合成进程回归。不改native_learning/原协议/guard/人工决定/状态迁移，不调用模型、SSH、push或部署。Codex严格冻结输入的现有拒绝保留在能力核验边界，不能把手动sandbox canary通过当模型运行准入。
- 改动范围：tmh/platform/learning_runs.py、新增tests/test_learning_run_config.py及本进度。证据在仓库外分析/implementation/20261027-learning-runs-codex-config/；固定候选后交作者外复验，后续真正执行桥与发布单独接续。
- 已实现：_configuration按项目route选择并冻结有效执行器字段；保存Codex engine/profile/stdin/resume=false/retry_busy=false/个体timeout与公开可执行文件SHA，未知字段不进入API回执。step改用同一冻结配置，按engine决定模式，个体时限取原job剩余与冻结上限较小者。route/配置撤销不可验证转stale，不回退其他执行器；旧无route Claude冻结形状保持。
- 真实Codex模型的冻结输入拒绝保留在_capabilities（无用户开关）；手动官方sandbox或read-only不能替代模型父进程/工具dispatcher隔离。新增过程测试仅stub能力握手，调用真实本地合成CLI检验配置传递，不声称已开启真实Codex知识运行。profile名与agents.json有效字段已冻结，实际私有profile/认证/父进程上下文仍未证明，后续执行桥不能凭本提交直接准入。
- 初轮10项：9过/1错误，2.951秒退出1；新增超时测试误取不存在的stop_reason字段。实际2秒超时/124和完整清理已发生；初稿源码、完整日志和7新例数据库/原件保留。只改测试读取真实stopped_reason/attempt.reason并增加124/原2秒上限断言，不放宽时限或既有断言。
- 最终同一窄命令：7新增（实际合成stdin/取消/个体超时、profile与route撤销、公开字段和真实拒绝能力门）+3原Claude/拒绝/help能力兼容，共10/10、3.057秒、退出0。14个新例完整SQLite现场integrity_check均ok；6次新例实际合成目标原回执/完整输出/清理读回，目标PID已不存在。3个原兼容例仅保留日志，未补造其已清理临时现场；不重跑旧大套件/全量。
- 自审：原SCHEMA/TERMINAL/锁/租约/监督读回/_work/cancel/resume等AST保持，原test_learning_runs.py字节未改；git diff --check通过。未改native_learning、guard/acceptance、旧协议、原表DDL或真人决定。当前done仅指本地配置传递增量，真实执行桥仍doing；固定本地候选后交作者外复验，不push/部署。

## 2026-10-27：现役Codex非权限参数兼容增量

- 状态：done（限本地增量，待作者外复验）。基线d549936；根审指出现役docs/codex-project-route.md配置args=[--ephemeral,--color,never]，原所有非空args拒绝使配置传递准备仍不兼容。仅Codex白名单允许这两个已知非权限参数及其不重复顺序组合，冻结原值并传递；Claude不接受额外args、自定义cmd/模型/profile/目录/权限覆盖仍拒绝，真实Codex模型能力拒绝保持。
- 改learning_runs.py及新增2测试、本进度。初轮5项：4过/1错误、0.460秒；新测试误向_patch对象读call_count，所有不安全args已实际拒绝。初稿/日志/4个新框架现场保留，只修mock观测对象为lr._capabilities。最终同一窄5项（新增2+空args、项目投影、原Claude权限3兼容）：5/5、0.458秒、退出0；不重跑旧时序或大套件。
- 两轮8份DB完整性ok、4次实际合成CLI的原SP owner/PID/PGID/全输出SHA/清理匹配，PID已不存在；上一提交所有原测试方法和_configuration外全部函数/类AST保持。证据分析/implementation/20261027-learning-runs-codex-args/。只准备/验证配置通路，不声称真实私有profile/认证内容、模型冻结输入或实际Codex知识评测已可用；不push/部署。

## 2026-10-27：隔离 Codex 的配置来源与固定 worker 输入

- 状态：doing。基线237952e，开始工作区干净，GitHub已快进同步且远端一致。新增codex_frozen_config组件与测试、说明；不改既有Runner/监督器/能力门，不读本机或服务器真实凭据。组件提供完整base/profile来源绑定、变化拒绝、生成后的非秘密配置、固定环境与官方exec命令；实际载体和模型接线仍待，不将此项当可用功能部署。
- 首轮定向：7项新配置/权限/凭据变化反例加5项原profile生成兼容，12/12、0.169秒、退出0。原日志与首轮完整源码保存仓库外分析/implementation/20261027-codex-frozen-execution-config/。随后仅补POSIX/Python3.11+明确范围与说明，最终验证另记；组件不涉及schema、真人决定或状态迁移。
- 同时按独立接受执行v5唯一offline检查：53份126360字节完整原件读回；新挂载元数据可见且设备一致、新FD关闭。实际推进至固定synthetic registry路径EACCES/13，原总60秒内4.750552505秒、SP退出1/内层101、canary0/model0，清理完整。封存manifest1029ebc611358045d57b7056202b82000edae60ace508c630506067e73364c45；不重跑此ID、不改宿主策略、不据元数据通过开放模型。旧失败保持。
- 最终自审增加8MiB完整源拒绝与真实路径替换反例，未放宽原条件；9新+5原兼容共14/14、0.177秒、0 skip/失败/错误、退出0，完整final-source/final-targeted.log保留。公开binding不含原文、真实endpoint或凭据；宿主凭据变化在对象生命周期内拒绝，跨重启私有登记仍属实际载体责任，不以本对象冒充持久认证。
- 状态：done（仅必要配置组件），实际Runner/隔离载体/固定网关桥仍doing，真实Codex能力拒绝保持。产品只新增一个模块与测试/说明及本进度，不改既有生产函数/表/监督链/人工决定；无模型/真实凭据读取/全量或部署。固定小提交后供作者外增量复核，不将离线目录检查通过当模型派发通过。

## 2026-10-27：可信宿主固定 Responses 交换核心

- 状态：doing。基线8d2120c配置组件已获作者外有限接受并正常push，GitHub精确HEAD与干净工作区另存分析/implementation/20261027-github-8d2120c-sync/。本项只新增codex_gateway固定上游交换及测试，扩展FrozenConfig给可信root控制器显式登记配置owner，更新说明；不建监听服务、调度/预算体系，不改Runner/真实能力拒绝或人工决定。
- 固定POST /v1/responses、本地Host/公开占位认证、冻结模型、无歧义完整JSON；真实认证只在宿主注入，官方非逐跳身份头和body保持。严格复用provider_transport framing，不跟随redirect/升级，不隐式retry；源变化、原截止点/取消、短回包均拒绝完整成功，收到的payload保留，私密journal留服务器。实际认证通道/namespace relay/IndependentRunner载体仍待接，不能直接以公开占位key充当身份。
- 初16/16、0.069秒；补真实回环HTTP chunked/短Content-Length后18/18、0.115秒，均退出0。回环使用合成提供方与凭据，并在测试中替换HTTPS连接，不声称真实TLS或模型通过。源码/全stdout/stderr在分析/implementation/20261027-codex-fixed-gateway/。
- 自审新增“journal或close耗尽原期限”反例，针对本轮未提交初稿两子场景均准确失败（close-deadline-red，1项/2失败、0.020秒、exit1）；原源码/日志保留，非基线缺陷。修复为先保存HTTP载荷完整原始事实并关闭连接，再做最终取消/期限检查；19/19、0.123秒exit0。随后补固定模型/JSON拒绝与说明，最终字节验证另记，不把19项当最新版本证明。
- v6唯一offline检查原总60秒内3.418408432秒，bubblewrap返回namespace创建权限通用错误；53份126407字节完整原件已封存（manifest01e89ab7f33e5afe8f612c0b919a0ebc6402078b5efffd2aa873fb374898df7f），canary0/model0/清理完整/服务保持，不重跑此ID、不依提示改sysctl。作者外正在准备正确私有pivot_root后继，本作者不重复编写该候选。
- 自审进一步发现HTTPResponse在连接关闭后仍可能持有socket文件引用。新未提交初稿的成功/不完整两子场景均准确失败（response-close-red，1项/2失败、0.023秒、exit1）；原源码/日志保留。成功路径和异常finally均显式关闭response及connection，正向最终期限检查在两者关闭后，未改旧测试或门槛。
- 最终final-v3：11项固定交换+10项配置，共21/21、0.148秒、0 skip/失败/错误、exit0。包含两条真实回环HTTP、短响应原字节保留，以及仅用于新收尾单测的受控时钟；没有把受控时钟当实际网络超时/隔离证明。固定模型替换/重复JSON/非JSON数和真实源owner均在连接前检查。最终5份来源逐字节SHA读回，9份人工决定/guard/锁/监督/Runner/知识门/Store源码与8d2120c逐字一致。
- 状态：done（限交换核心与本地定向），实际可信通道/namespace TCP relay/Runner接线/模型证明仍doing。私密journal必须只在服务器保留；安装闭包需包含既有scripts/rsi/provider_transport.py，尚未验证安装或修改打包。固定小提交后作者外增量复核；无全量/真实TLS/真实提供商/官方CLI/模型/新服务/生产部署。

## 2026-10-27：固定网关的实际安装依赖闭包

- 状态：doing→done（限安装依赖）。基线79c0a66已正常push、GitHub精确HEAD/工作区干净。确认原wheel/离线/内置工具缺顶层scripts.rsi，固定交换核心的import存在源码树外缺失风险；不改原provider_transport校验器，加入resources.FILES和MANIFEST声明，从固定资源路径加载同一原始代码。普通模块、真实能力门、Runner与协议均不变。
- 新2项离线包/内置工具隔离导入及缺helper时安装原子拒绝，加原Distribution2和必要真实HTTP chunked/短回包2，共6/6、1.153秒、0 skip/失败/错误、exit0。-I -S及无检出树工作目录下，完整helper字节/SHA与行为一致；install保留原用户说明。没有重跑旧21整套。
- 系统Python3.14缺setuptools，未联网安装；使用已有bundled Python3.12.14/setuptools/wheel构建。实际sdist→解包→wheel→pip --no-index --no-deps --no-compile --target临时目录全退出0；wheel、安装后及其内置工具在-I -S下实际import和install均通过，原helper全字节/SHA一致，wheel中gateway字节与当前源码一致。完整归档、输入清单、构建/安装/隔离命令和stdout/stderr保存在分析/implementation/20261027-codex-runtime-distribution/。
- 原provider_transport字节与79c0a66一致；运行文件与实际构建输入逐字节读回。未调用模型/真实提供方/读取真实凭据，未启动服务或安装到全局环境。仅临时包验证，不宣称旧源发布清单已补齐或服务器已部署；未来源码部署必须带上resources.FILES新增的helper。真实可信载体/Runner接线仍doing。

## 2026-10-27：隔离配置显式关闭远程工具

- 状态：doing→done（限生成配置）。基线3fe50d5，开始仅本项两份源码/测试未提交增量；分发修复已获作者外有限接受，不重跑旧21项。固定官方0.162.1源码证明web_search默认cached，本地network=false不等于提供商工具关闭。生成配置明确disabled、空MCP/插件表，关闭11项相关功能，并增加官方支持的--strict-config；普通Runner/真实能力拒绝保持。
- 仅运行新增test_generated_config_explicitly_disables_remote_tool_plane：1/1、0 skip/失败/错误，unittest0.007秒，外层0.145415秒、exit0。解析实际生成TOML，核对全部明确关闭值、原源配置不被改写和strict参数；未调用官方CLI/模型，不推断实际请求tools或供应商行为。原本地日志、精确来源和固定版本Git blob/SHA核对在仓库外分析/implementation/20261027-codex-remote-tools-disabled/；上游源码不复制进产品仓库。
- 同次v8离线失败的补充诊断已经读回两条同窗精确宿主PID3587011/3587012的net_admin拒绝原行、当前unprivileged_userns(enforce)、699字节公开策略及897字节直接tunables/global；local/unprivileged_userns不存在。宿主PID到本次进程树映射仍未证明，磁盘源码不宣称等于已加载二进制策略。补查unprivileged_unconfined开关及parser版本时SSH认证拒绝/255，远程未执行，原失败保留；不改策略、不重跑v8、不扩大日志范围。
- 状态边界：实际载体/Runner接线仍doing；无模型、部署、真人决定或业务DB变更。待确认：无须重复询问用户发布授权；当前SSH认证不可用的原始失败与待核两个主机值已记录，继续本地必要编码。未开放真实能力门，未将配置单测当网络/隔离/组织收益证明。

## 2026-10-27：IndependentRunner可信载体单次监管接口

- 状态：doing。基线0a59258已正常快进push、GitHub精确HEAD/工作区干净；v8诊断补充26文件封存cb2ea4ec7bbc96c4f7112595d4f98d59f55cdc13665425e9af8f3d95b4e7663c。仅新增可信宿主constructor依赖与单次原run_command接点，普通Runner仍原监管调用；不建立新预算/台账/调度器、不从API选载体、不开放真实能力门。实际root控制器/私有通道/模型证明仍待。
- 首轮新8项全部通过，3.187秒（外层3.374198秒）；补真实子进程耗尽原期限、拒绝刷新限额/坏计划/重试/部分输入后，新11+直接原兼容4共15/15、5.909秒。末次增加每启动随机nonce供真实私有回执绑定，nonce不代替原attempt/认证/预算；因此以最终字节重跑同15项，15/15、5.876秒（外层6.108203秒）、0 skip/失败/错误、exit0。原日志/源码/合成现场分别保留在分析/implementation/20261027-codex-carrier-seam/，未重跑旧配置21项或全量。
- 新例实际监督进程证明完整440016字节中文stdin、原owner和cancel_event、真实运行中取消/清理、准备与末次验证消耗原单调期限、只返回原ProcessResult；失败不走普通命令或隐藏重试。最终11个合成SQLite完整性全部ok，6份实际process/SP输出和清理原件完整保留，读回时目标PID均不存在。普通Codex profile原完整stdin/空答案拒绝、原Claude知识运行与真实Codex能力拒绝4项兼容均通过。只用公开合成进程/输入，不是官方CLI、模型工具面或组织收益证明。
- 自审：12份既有保护源码/原测试字节与0a59258相同；Runner原run_command、owner/取消/超时/监督方法及learning_runs原能力门/Worker/数据库协议AST不变，仅_spawn改经新默认直通接点，IndependentRunner增加宿主私有依赖。无任务API开关、无载体安装/宿主装配/私有回执读取器，原业务人工确认/guard/状态迁移保持。git diff --check通过；本批done仅限接口组件，整体实际接线仍doing，待作者外窄审查。
- 待确认/阻塞：SSH公钥认证拒绝原件保持，主机开关与parser版本未知；原准备流程单独推进v9策略候选，本作者不重复、不应用策略或启动新轮。没有发布服务或重启，没有为组件空部署，也没有解除真实能力门。
