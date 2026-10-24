# 真实供应方与Linux隔离能力：准备增量

本批基线c6376be，不改现役215运行文件。完成的是Linux能力探针与有限配置取证，未开放生产模型/终测入口，没有付费调用、评分、真人采用或业务验收。

## 评分v2可实施性

已核固定评分v2 SHA `a5b86ae9b289062d1b76bc41ee76f08304afaf4a08ccb70a7b8f4980f01548e7`。18叶项合计100分，dependencies为空，gate_membership是汇总归属，不再循环依赖自身汇总门。所有required_items存在且归属一致；必达叶项合计90分，另有W1核心撤回谓词。coding确认该结构可实施，无结构性阻断。主协调结合独立review于06:07:09 CST冻结共同标准，分离冻结记录SHA `f3a81e7ec868607b61bd1476ea8b5fb935ee136d97ac9ff2a71dc1672e1867c6`，原评分JSON字节保持。具体run/pilot真人、日历、数值协议仍未冻结，不计算当前得分；共同冻结不代替独立核证或真人业务决定。

B类复用旧证据需核当前相关字节/语义；C门仍缺完整生产有效输入等价、真实A→B/C→人工采用→D；M门缺实际供应方身份/usage/价格和执行适配器；P门缺真实项目/人/任务全集/周期和数值收益线；W1缺真实人工撤回后任务证据。不能把本批探针或旧合成账本填成这些项通过。

## 有限模型配置取证

已通过严格known_hosts SSH和登记公钥核验现役 `6edc04f`。服务用户HOME为 `/home/ubuntu`，CLI存在于 `.npm-global/bin/claude` 与 `codex`，但本次有限检查中没有找到可用模型连接配置：

- `/etc/webuddy.env` 和现役进程环境没有发现已检查的模型别名、Anthropic/OpenAI端点或相应凭据变量。
- `/opt/webuddy/data/agents.json`、ubuntu的Claude常规设置不存在；直接查root目录先被拒，保留原PermissionError，随后按既有服务器模型信息授权只在服务器内白名单投影root常规设置，确认该路径也不存在。
- 两个用户的常规shell启动配置及 `/etc/environment` 没有发现已检查的模型端点/别名/凭据赋值。脚本静态解析，不执行shell配置。常规Claude凭据文件只查存在性（均未发现），未读取内容。

仅导出必要公开字段、配置路径与存在/权限状态，没有配置原文、API key/token、凭据摘要或完整环境。以上是有限位置的观察，不能推出服务器任何位置都没有配置，也不能把CLI存在当作连接可用。当前明确缺少：获授权的实际配置位置/有效接口、供应方实际响应模型与计量、可核价表或硬价格上界、可强制计量的适配器；因此真实派发0。无需发送密钥内容，后续配置仍留服务器。

## 已执行的内核正负控

工具 `scripts/rsi/linux_holdout_probe.py` 只有显式 `--run` 才可执行，非Linux拒绝且不创建目录/不sudo。Linux上使用现成UID65534，与证据保管用户UID1000不同；所有材料是新生成的合成canary，不挂生产data/配置，不改账号或服务。它是能力测试身份，尚未配置为专用生产试点身份。

在私有mount/PID/network namespace中构造临时根目录，仅只读映射公开系统库、只读proc、合成公开输入、UID1000私有答案目录与UID65534可写工作目录。进入chroot后清空环境、附加组、全部能力bounding/permitted/effective/ambient，启用no_new_privs。只继承标准输入输出；不把宿主目录fd或供应方凭据交给工作进程。

固定探针的16项检查全部通过：不同UID、公开输入可读、答案PermissionError、宿主根路径未映射、能力清空、不可提升权限、不能恢复root、宿主父进程不可见、namespace父进程环境被拒、环境清空、cwd在临时根、系统映射只读、proc只读、无继承目录fd、网络不可达及工作目录可写。合成答案未出现在完整stdout/stderr中。

复用原保护模块的监管器，并以root监管有特权的namespace setup和降权子进程；无权用户不能可靠回收root子进程，不能仅给普通监管器套sudo。保护模块按固定源码SHA核验，未修改；显式禁用root监管加载的字节码写入。最终正常探针源码SHA `e502363070aa2f37feef578e09a8c19cdb8586209d477efa5c3bc38fd9790724`。正常进程exit0且完整回收；另保留外置故障注入原件：输出全部检查后固定睡眠30秒，原监管器3秒超时，工具正确exit1/returncode124、status=failed，TERM回收完整，16项原始输出仍保留。流式继承输出，避免在中间setup缓冲后丢失被强停进程的已产生材料。

最终正常与超时两个现场均保留在服务器 `/tmp/webuddy-holdout-probe-*`（owner-only顶层）。14份白名单证据6009字节已完整读回，清单SHA `9769e626daa1f9bfe9f21699e5f9d0fc663afdcc066fb2cd2c59603d57fc4967`。06:12:26 CST只读后查：两个测试进程组不存在，宿主mount namespace没有探针挂载，Webuddy仍6ed/active/running/PID2502485/重启0。未重启Caddy或其它应用。

## 尚未完成

该工具执行的是固定canary，不是恶意任意代码安全证明，也不是已部署终测服务。共享nobody身份、内核漏洞、namespace外的其它同UID进程、专用托管账号、受控通信通道、任务/权限/输入版本绑定、终测一次消费与真实执行事务接入、完整生产提示等价均须后续实现/核验。实际优化进程必须在隔离环境中运行，不能仅先测一次再让宿主Claude直接读留出材料。报告始终 `production_qualified=false`、`dedicated_trial_identity=false`、provider_calls=0。

下一运行增量须绑定真实服务器profile/价格上界与原根预算，并使用专用身份及最小托管通道；不能把本工具的root setup或底层脚本方法直接开放为任意命令API。对应run/pilot协议及数值未齐时继续保持not_run，不回填评分。


收尾：R1/R2准备账本修复为5aaf5e0，Linux工具为94176c6，分别提交推送，独立关闭/新工具复审仍待。相关83项及精确941导出83项实际exit0；一次晚补README造成的封存拒绝原件保留，以新精确导出重验，不跳过来源门。06:22:47 CST实际重读服务器215运行文件的SHA/长度/模式均匹配6ed清单，服务active/running、重启0。本次收尾文档不改受测脚本或重启服务。


一致性补强：另拒绝重建仍有原始事件、attempt或claim的缺失pool。该边界已保留1项实际红灯及持久DB，修后8项一致性、84项相关与隔离导出全部通过。最新账本源码SHA `6bb28d8ab9074dafbe4d82960c2b2762b47330d6386dce15c111f7a3d09f6211`；Linux探针e502与前述服务器证据保持，独立关闭结论仍需复审。


## L1 清理路径修订（2026-10-25）

独立审查发现旧 e502 探针的 root finally 递归 chown 会跟随 worker 工作树中的链接；旧正常/超时观察不覆盖该攻击路径，不代表生产沙箱合格。新版本删除整个递归归属回收和工作树遍历，只对运行前 O_NOFOLLOW 打开并核验所有者的原 fixture 目录 FD 执行 fchmod(0700)，随后关闭 FD。目录名或子目录被替换不会改变最终权限操作对象。

原监管回执、完整二进制输出、report 和 work 保持各自原所有权。不能再假设调用方可直接读取 root-owned 0600 产物；需要审计时，使用明确授权的固定文件白名单和目录 FD 逐层 O_NOFOLLOW 只读收集，禁止递归 root chown、chmod、删除或遍历 worker 树。caller 在 sudo/前置失败时也通过自己的原目录 FD 收紧顶层，stderr 固定以0600排他创建。

新增无特权回归直接执行本版本 finally AST：真实链接/目录FD/路径替换/fchmod，chown 只作为旧代码的记录器；不把它说成真实内核隔离验证。固定正常及受控超时源码须另在 Linux 核验，原16项、真实监管清理与不泄露oracle断言不放宽。专用生产身份、真实终测入口和组织收益仍未完成。


修后实际验证：正常固定探针源码SHA `66fa011ffc742de5d2df23d781784a844960dd71e1a0ce27b75cd5feae8c6617` 在Linux实际tool0/监管0、16项true；外置链接注入变体仍正常通过，链接注入后sleep30/真实3秒期限变体tool1/监管124并完整清理。三场夹具外root-owned合成目标内容/UID/GID/mode完全不变；原SP.read_receipt逐场核验通过，超时原进程返回241另记，不冒称124。18份原产物按SHA/长度完整读回，宿主无该fixture挂载/进程组。证据 `分析/RSI协调/linux-cleanup-L1-20261025/`。本地/独立导出/服务器各11项通过；独立复审仍待固定提交后关闭。
