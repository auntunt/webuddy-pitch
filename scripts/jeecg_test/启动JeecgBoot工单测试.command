#!/bin/bash
# 双击运行：拉 JeecgBoot 代码 → 生成数据地图 → 启动工作台 → 用本机 Codex 自动处理 40 张单（前后端各 20，每张在它自己修复之前的代码上）
#   15 张改到代码，15 张停在改代码前，10 张只录入。中途关掉再双击会接着跑，已建的单不会重建。
# 结果：~/tmh-jeecg-test/report.md ；工作台 http://127.0.0.1:8791
HERE="$(cd "$(dirname "$0")" && pwd)"
TMH="$(cd "$HERE/../.." && pwd)"
[ -f "$HOME/.zprofile" ] && source "$HOME/.zprofile" >/dev/null 2>&1
[ -f "$HOME/.zshrc" ] && source "$HOME/.zshrc" >/dev/null 2>&1
cd "$TMH" && python3 "$HERE/driver.py" --tmh "$TMH" "$@"
echo; read -n 1 -s -r -p "按任意键关闭窗口"
