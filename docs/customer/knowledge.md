# 项目知识

在获准的项目目录中执行，以下命令使用发行包里的 Python：

```bat
runtime\python\python.exe -m tmh install --repo "D:\项目"
runtime\python\python.exe -m tmh kb build --repo "D:\项目"
runtime\python\python.exe -m tmh kb status --repo "D:\项目"
runtime\python\python.exe -m tmh kb read index --repo "D:\项目"
```

初始化保留已有 AGENTS.md 正文，插入产品指引，并安装模板、技能和 Agent 配置。命令说明在项目的 `.tmh/docs/agent-commands.md`。重复初始化不会覆盖业务源码或把用户指令替换为空白。

静态构建从项目源码生成图谱、事实块和待理解页面，不调用模型。图谱、缓存、源码快照及业务知识在该项目的 `.tmh` 目录生成，不随产品发行包预置。静态结果不能证明业务规则已确认；动态分派、反射及数据环境可能无法从静态源码完整识别。

后续通过 kb next/done 完善业务理解；确有人工确认后才执行确认。改动代码后重建，指纹变化会使关联知识过期。未确认、过期、未知和已验证必须分别呈现。`kb read` 读取完整页面，`context` 按需求检索。

产品 `kb/` 目录是通用技术适配参考，不是客户项目知识快照。数据库、操作系统及密码适配要以客户目标版本和实际环境核对。
