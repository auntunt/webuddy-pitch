# 独立复核记录

2026-10-19，agent_bridge_review（未参与后端/MCP实现）检查实际 HTTP、CLI、MCP 与自动执行边界。新增17个独立回归通过。

已发现并修复：持续滴流绕过socket空闲超时；非对象JSON错误导致traceback；非法端点；缺SDK错误；未知写回执错误类型；未知启动阻止安全取消；handwork扫描通过同名分支绕过MCP执行设置；方案绑定遗漏新增沟通。最后只读复核未发现新的阻塞问题。

root实际配置验收另外发现绝对脚本路径让tmh/mcp.py遮蔽官方SDK，修复后新增Claude/Cursor/Codex三份生成配置的启动回归；官方ClientSession从无关目录原样执行command/args。

限制：连接名是审计标识，非多租户权限；本地socket deadline不约束系统DNS解析；三个编程产品不能因协议测试通过而宣称全部实机验收。真实Codex读取已验证，非交互写工具被其审批策略阻止，未绕过。

## 收尾全量失败的独立诊断

Python 3.11 的8个旧测试快照错误可仅用stdlib sqlite3内存表和dict row_factory复现：iterdump解包字典键后查询不存在的name表；Python 3.14同输入通过，dump实现会设置cu.row_factory=None。失败点在被测API调用前，不是本次数据结构损坏。

取消用例的单轮预算为0.5秒。失败日志里invoke先返回124，测试包装器的code==0断言先抛异常，尚未调用cancel；理解流程捕获后封存failed。无证据证明本次CLI/MCP改动导致，亦不能断言具体机器负载原因。同一3.11独立复跑生命周期12项通过；抽取的2项dump测试仍稳定失败。原全量失败仍保留，复跑不抵销原失败。详情见python311-independent-diagnosis.log。
