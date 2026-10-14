#!/usr/bin/env bash
# 在本机打部署包：平台代码 + 一份平台数据（运维 JeecgBoot 和重构 RealWorld 两个项目合在一起）+ 两个项目的知识库和改动分支。
# 不含源码仓库本身（服务器上从 GitHub 克隆），不含任何密钥。
# 用法：pack.sh <平台代码目录> <JeecgBoot 测试目录> <重构数据快照目录> <输出目录>
#   例：pack.sh ~/Desktop/workspace/运维智能体/tob-maintenance-harness ~/tmh-jeecg-test \
#             ~/Desktop/workspace/运维智能体/实测项目/_截图数据/RW ~/Desktop/webuddy-包
set -euo pipefail
APP=$(cd "$1" && pwd); JB=$(cd "$2" && pwd); RW=$(cd "$3" && pwd); OUT=$4
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
P="$W/webuddy"; mkdir -p "$P/data" "$P/repos"

echo "== 平台代码"
tar -C "$(dirname "$APP")" --exclude='__pycache__' --exclude='.DS_Store' --exclude='.git' -cf - "$(basename "$APP")" | tar -C "$W" -xf -
mv "$W/$(basename "$APP")" "$P/app"
cp "$P/app/scripts/deploy/install.sh" "$P/install.sh"

copy_data() {  # <平台数据目录> <目标>：不带工作树；数据库用 sqlite 备份，正在运行也能拷
  mkdir -p "$2"
  tar -C "$1" --exclude='./worktrees' --exclude='platform.db' --exclude='platform.db-journal' --exclude='platform.db-wal' \
      --exclude='platform.db-shm' --exclude='.DS_Store' -cf - . | tar -C "$2" -xf -
  python3 - "$1/platform.db" "$2/platform.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
}
echo "== 运维数据（JeecgBoot）"
copy_data "$JB/data" "$P/data"
echo "== 重构数据（RealWorld）并进同一份数据"
copy_data "$RW/data" "$W/rw"
python3 "$P/app/scripts/deploy/merge_data.py" "$P/data" "$W/rw"

echo "== JeecgBoot 的知识库和智能体改出来的分支"
G="$JB/JeecgBoot"
tar -C "$G" --exclude='.DS_Store' --exclude='knowledge-*' -czf "$P/repos/JeecgBoot.tmh.tgz" .tmh
refs=$(git -C "$G" for-each-ref --format='%(refname)' refs/heads/tmh/ refs/heads/tmh-test)
git -C "$G" bundle create "$P/repos/JeecgBoot-tmh.bundle" $refs --not --remotes >/dev/null 2>&1 \
  || echo "  （改动分支没有打进包：仓库里没有远端分支可以对照，服务器上只看得到平台里记的改动）"
git -C "$G" rev-parse tmh-test > "$P/repos/JeecgBoot.head"

echo "== RealWorld 的知识库"
tar -C "$RW" --exclude='.DS_Store' -czf "$P/repos/realworld-net.tmh.tgz" tmh

date '+%Y-%m-%d %H:%M:%S' > "$P/打包时间.txt"
tar -C "$W" -czf "$OUT/webuddy-deploy.tgz" webuddy
ls -la "$OUT/webuddy-deploy.tgz"
