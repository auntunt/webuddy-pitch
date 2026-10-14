## Claude Code 补充说明

- 本仓库的 `.claude/settings.json` 配置了 tmh 钩子：编辑前保护基线测试与验证配置，编辑后检查是否引入与改造目标不兼容的写法，危险命令会被拦截，有代码改动但未验证时结束前会提醒运行 `tmh verify`；每次工具调用会记入 `.tmh/activity.jsonl`，在报告的“分析过程”里展示。钩子拦截时请按提示调整，不要绕过。
- 修改文件请用 Edit/Write 工具，不要用 shell 脚本（sed、python、重定向）改源码：编辑钩子只对编辑工具生效，用脚本改会绕过即时检查（`verify` 仍会在最后发现问题）。
- 子代理：`kb-writer`（领取并撰写知识库页面，可并行派出多个，各用不同 --who）、`code-cartographer`（只读勘察、写知识笔记）、`impact-analyst`（只读影响分析）、`sql-dialect-converter`（SQL 方言改写建议）、`independent-verifier`（独立复核改动与验证结果）。大范围阅读和批量撰写交给子代理，主会话只保留结论，节省上下文。
