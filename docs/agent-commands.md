# Agent 命令速查

需要查命令时阅读。安装后位于 `.tmh/docs/agent-commands.md`。
`tmh` 是 `python3 .tmh/tool/tmh.py` 的简写；以下 `|` 表示备选子命令，不是 shell 管道。

```text
tmh context "需求原文"               # 定位相关知识页、业务流、表、代码位置时使用
tmh kb build | status | next | done <id> | show <名称>   # 构建/增量更新、覆盖情况、领取任务、校验入库、查图谱
tmh kb chain "需求" | read <id>…      # 读业务链路 / 指定页面的原文
tmh kb triage "需求" [--record] | questions | ask "问题" --pages <id> --to <人>   # 预判、待答问题；人用 tmh kb answer <号> "原话" --who <姓名> 答复
tmh kb metrics      # 少找人统计；人用 tmh kb overrule <预判编号> --who <姓名> --reason "…" 纠正预判
tmh status | flows [关键词] [--changed] | report | note finding|decision|question "…"
tmh where 关键词 | impact 目标 | task new "标题" --kind feature | baseline | verify [--task T001]
tmh accept check|path-check|advance|reject|status T001 [--to 状态] [--note 原因]   # confirm/close 只能由人执行
tmh assess | items [-v]            # 有信创等改造目标时
tmh ticket 工单号 [--task] | build failure [job] | quality | doc search 词 | trace 工单号
tmh int list | types -v | add | test   # 运维工具接入
```
