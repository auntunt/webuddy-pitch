#!/bin/bash
# 双击运行：拉官方 .NET 版 RealWorld 和 Java 参考版 → 全量分析（5 个并行）→ 骨架 → 按业务域改造计划全部放出（5 个并行）
#   → 把各部分合到一个分支 → 出报告。中途关掉再双击会接着跑，已建的单不会重建。
# 结果：~/tmh-realworld-test/report.md ；工作台 http://127.0.0.1:8792
# 跑起 Java 版和 .NET 版之后，可以再跑一次接口测试：加参数 --report-only --verify java=http://localhost:8080,net=http://localhost:5050
HERE="$(cd "$(dirname "$0")" && pwd)"
TMH="$(cd "$HERE/../.." && pwd)"
[ -f "$HOME/.zprofile" ] && source "$HOME/.zprofile" >/dev/null 2>&1
[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc" >/dev/null 2>&1
cd "$TMH" && python3 "$HERE/driver.py" --tmh "$TMH" --parallel 5 "$@"
echo; read -n 1 -s -r -p "按任意键关闭窗口"
