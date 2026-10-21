#!/usr/bin/env bash
# scripts/release-check.sh — 发布前本机检查（Linux / macOS；Windows 用 release-check.ps1）
#
# 依次：环境与版本一致性 → pytest collect-only → CI fast gate → 关键套件 → 可选 pip install 冒烟 → ops 测试。
# 用法：
#   bash scripts/release-check.sh
#   INSTALL_SMOKE=1 bash scripts/release-check.sh
#   PYTHON=/opt/webuddy/venv/bin/python bash scripts/release-check.sh
# 退出码：0 全部通过（允许 SKIP）；1 有 FAIL。
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
PY=${PYTHON:-python3}
INSTALL_SMOKE=${INSTALL_SMOKE:-0}
SKIP_NODE=${SKIP_NODE:-0}

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export NO_PROXY=${NO_PROXY:-127.0.0.1,localhost,::1}
export no_proxy=${no_proxy:-$NO_PROXY}
export PATH="$PATH:/usr/local/bin"

PASS=0
FAIL=0
SKIP=0
FAILURES=()

head() { printf '\n== %s\n' "$1"; }
tail_out() {
  # $1 = file with output
  [ -s "$1" ] && tail -n 30 "$1" | sed 's/^/    /'
}
ok()   { PASS=$((PASS+1)); printf '  [PASS] %s (%ss) %s\n' "$1" "$2" "$3"; }
skip() { SKIP=$((SKIP+1)); printf '  [SKIP] %s — %s\n' "$1" "$2"; }
bad()  { FAIL=$((FAIL+1)); FAILURES+=("$1 — $3"); printf '  [FAIL] %s (%ss) %s\n' "$1" "$2" "$3"; }

run_step() {
  local name=$1; shift
  local tmp start secs code last
  tmp=$(mktemp)
  start=$(date +%s)
  "$@" >"$tmp" 2>&1
  code=$?
  secs=$(( $(date +%s) - start ))
  if [ "$code" -eq 0 ]; then
    last=$(grep -v '^[[:space:]]*$' "$tmp" | tail -n 1)
    ok "$name" "$secs" "$last"
  else
    bad "$name" "$secs" "exit $code"
    tail_out "$tmp"
  fi
  rm -f "$tmp"
  return "$code"
}

printf 'release-check: %s\n' "$ROOT"
printf 'python: %s  (%s)\n' "$PY" "$("$PY" --version 2>&1)"
printf 'node:   %s\n' "$(command -v node >/dev/null 2>&1 && node --version || echo 'not found')"
printf 'git:    %s\n' "$(command -v git >/dev/null 2>&1 && git --version || echo 'not found')"

# 1) 版本一致性：pyproject.toml 与 tmh/__init__.py 必须相同
head '版本一致性'
VERSION_CODE='
import re, sys, pathlib
root = pathlib.Path(".")
py = re.search(r"^version\s*=\s*\"([^\"]+)\"", (root / "pyproject.toml").read_text(encoding="utf-8"), re.M)
init = re.search(r"__version__\s*=\s*\"([^\"]+)\"", (root / "tmh" / "__init__.py").read_text(encoding="utf-8"))
print("pyproject=%s tmh=%s" % (py.group(1) if py else "?", init.group(1) if init else "?"))
sys.exit(0 if py and init and py.group(1) == init.group(1) else 1)
'
run_step 'version consistency' "$PY" -c "$VERSION_CODE"

# 2) git >= 2.38（平台分支/工作树操作依赖）
head 'git 版本'
GIT_CODE='
import re, subprocess, sys
try:
    text = subprocess.check_output(["git", "--version"], text=True)
    m = re.search(r"(\d+)\.(\d+)", text)
    major, minor = map(int, m.groups())
    print("git %d.%d (need >=2.38)" % (major, minor))
    sys.exit(0 if (major, minor) >= (2, 38) else 1)
except Exception as exc:
    print("git check failed: %s" % exc)
    sys.exit(1)
'
run_step 'git >= 2.38' "$PY" -c "$GIT_CODE"

# 3) 全量收集（能 import、无收集错误）
head 'pytest collect-only'
run_step 'pytest collect-only' "$PY" -m pytest --collect-only -q -p no:cacheprovider tests

# 4) CI fast gate（与 .github/workflows/ci.yml 保持一致）
head 'CI fast gate'
run_step 'fast gate' "$PY" -m pytest -q -p no:cacheprovider \
  tests/test_command.py tests/test_gates.py tests/test_golang.py tests/test_jpa.py \
  tests/test_lessons.py tests/test_filelock.py tests/test_comment_drafts.py

# 5) 本轮关键套件
head '本轮关键套件'
run_step 'key suites' "$PY" -m pytest -q -p no:cacheprovider \
  tests/test_context_pack.py tests/test_org_knowledge.py tests/test_habits.py tests/test_g4_local_pilot.py

# 6) 可选：pip install . 打包冒烟（临时目录，不污染环境）
if [ "$INSTALL_SMOKE" = "1" ]; then
  head 'pip install . 冒烟'
  TMP=$(mktemp -d)
  if run_step 'pip install .' "$PY" -m pip install . --no-deps --no-build-isolation --target "$TMP" --disable-pip-version-check -q; then
    run_step 'installed functional smoke' "$PY" -I -X utf8 "$ROOT/scripts/installed-smoke.py" "$TMP"
  else
    skip 'installed functional smoke' 'install failed'
  fi
  rm -rf "$TMP"
else
  head 'pip install . 冒烟'
  skip 'pip install .' '未开启；用 INSTALL_SMOKE=1 运行'
fi

# 7) ops 工具测试（存在才跑；本仓库之外，可能在 ../ops）
if [ "$SKIP_NODE" != "1" ]; then
  head 'ops CLI 测试'
  OPS_DIR=''
  for candidate in "$ROOT/ops" "$ROOT/../ops"; do
    [ -d "$candidate/tests" ] && OPS_DIR=$candidate && break
  done
  if ! command -v node >/dev/null 2>&1; then
    skip 'node --test ops' '未安装 node'
  elif [ -z "$OPS_DIR" ]; then
    skip 'node --test ops' '没有找到 ops/tests（部署机通常不带 ops）'
  else
    TMP=$(mktemp)
    start=$(date +%s)
    ( cd "$OPS_DIR" && node --test 'tests/*.test.mjs' >"$TMP" 2>&1 )
    code=$?
    secs=$(( $(date +%s) - start ))
    if [ "$code" -eq 0 ]; then
      last=$(grep -E 'pass [0-9]+' "$TMP" | tail -n 1)
      ok 'node --test ops' "$secs" "${last:-ok}"
    else
      bad 'node --test ops' "$secs" "exit $code"
      tail_out "$TMP"
    fi
    rm -f "$TMP"
  fi
fi

# 汇总
head '汇总'
printf '  PASS %d  FAIL %d  SKIP %d\n' "$PASS" "$FAIL" "$SKIP"
if [ "$FAIL" -gt 0 ]; then
  printf '\n  失败项：\n'
  for f in "${FAILURES[@]}"; do printf '   - %s\n' "$f"; done
  printf '\nRELEASE CHECK: FAIL\n'
  exit 1
fi
printf '\nRELEASE CHECK: PASS\n'
exit 0
