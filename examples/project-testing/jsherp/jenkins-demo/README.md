# 自建 Jenkins 与 JSHERP 演示

这套资产在本机隔离 Docker 环境实施。它演练真实 Git checkout、构建、数据库/API/浏览器验证和 Webuddy 必需 CI 查询；客户仓库、客户 Jenkins、业务人员验收尚未接入。

当前实例目录：`../部署包/jenkins-erp-demo-20261106`（相对 Webuddy 仓库）。`erp/` 是独立源码副本；`git/` 是初始种子；实际远端在 `webuddy-demo-git-data` 卷；`jenkins/` 保存任务和构建记录；`proof/` 保存运行回执。`private/` 保存本机生成的演示凭据和CA，禁止提交、截图或发到聊天。

- Jenkins：<https://127.0.0.1:18443/job/erp-verification/>。本地CA需安装到访问者信任库；API通过指定CA严格验证。也可本机访问 <http://127.0.0.1:18080/>。仅绑定回环，不是客户可公网访问的地址。
- Git：`ssh://git@127.0.0.1:12222/repos/erp.git`，显式主机指纹与专用演示密钥。
- MySQL/Redis：只在Docker专用网络；无宿主公网端口。
- Jenkins账号与ERP账号是合成演示身份。默认ERP种子账号不是生产认证配置。

## 已建实例的操作

```sh
python3 examples/project-testing/jsherp/jenkins-demo/manage.py status
python3 examples/project-testing/jsherp/jenkins-demo/manage.py start
```

停止前先检查 Jenkins 没有运行中的构建，再执行 `manage.py stop`。该脚本只操作列出的五个现有容器，不删除卷或重置数据。重启不代表业务验证通过，需查看精确提交的最近构建和报告。

## 源码与测试资产

- `Dockerfile`：固定镜像来源的 Jenkins，Java8用于该ERP，Java21运行控制器，Node/Chromium/Python/MySQL客户端用于构建与实测。插件依赖版本以实际镜像为准，不称任意未来版本均已验证。
- `Dockerfile.git`、`git-sshd.conf`：专用私有Git服务；禁止密码、root及转发。
- `init.groovy`：首次初始化合成管理员、只读CI账号、Git凭据与显式主机指纹。已有初始化标记时不覆盖。
- `Jenkinsfile`：控制侧保存，候选参数只选择完整提交。每次清空专属工作区，再checkout；测试脚本非候选自报结果。
- `business.py`、`serve.py`、`verify.mjs`：在隔离执行机启动固定JAR、真实数据库接口和Chromium。记录提交/源码差异摘要、JAR与首页摘要、进程身份；执行后清理进程。没有挂载宿主Docker socket。
- `apply_refund.py` 与 `overlay/`：把明确标注的退款说明演示规则应用到独立ERP源码，不修改Webuddy的模型调用内核。
- [演示与追问](演示与追问.md)：分轮澄清、独立预期、角色操作与失败分支。

全新机器还需构建镜像、创建隔离网络与卷、生成专用SSH密钥/CA/合成账号、导入公开ERP种子、设置控制器任务及只读连接。本目录不应被描述为已经验证的一键客户安装包；现有实例启动与全新机器安装是两项结论。

## 证据边界

构建成功、测试通过、Leader复核、业务验收、负责人合并和正式发布分别显示。网页/MCP只读交付依据不能代人批准。ERP原有财务过账和库存审核不在本次范围；通过保存/回读不能证明完整财务流程正确。

原始截图不缩放像素、不重新编码压缩。失败构建和失败输入保留。依赖源、锁文件或测试宿主变化需要重新形成证据，不把旧版本成功挪给新版本。

此实例为单人受控演示，构建运行在控制器容器，只使用公开源码和合成凭据，**不是不可信多租户执行隔离方案**。客户接入应使用其已有受限构建节点和凭据管理，不能让任意项目代码读取控制器主目录。演示数据库采用Docker内网明文连接，和该ERP既有JDBC配置一致；Jenkins外部API始终使用校验证书的HTTPS。不能直接把这些演示网络与数据库设置复制为客户生产配置。
