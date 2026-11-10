#!/usr/bin/env bash
# 校验各处版本号一致:VERSION、backend/app/version.py、frontend/package.json、
# frontend/package-lock.json、packaging/version_win.txt。
# 传入标签(如 v1.0.9)时,另校验标签与 VERSION 一致。用法:scripts/check-version.sh [tag]
set -euo pipefail
cd "$(dirname "$0")/.."

# 读取文件中第一处匹配(先去掉 CR,兼容 Windows 检出的 CRLF)
field() { tr -d '\r' < "$1" | sed -n "$2" | head -1; }

want=$(tr -d '[:space:]' < VERSION)
fail=0
check() {  # 名称 实际值
  if [ "$2" = "$want" ]; then
    echo "ok   $1 = $2"
  else
    echo "FAIL $1 = ${2:-<空>},应为 $want"
    fail=1
  fi
}

check "backend/app/version.py APP_VERSION" \
  "$(field backend/app/version.py 's/^APP_VERSION = "\(.*\)"$/\1/p')"
check "frontend/package.json version" \
  "$(field frontend/package.json 's/^  "version": "\(.*\)",$/\1/p')"
check "frontend/package-lock.json version" \
  "$(field frontend/package-lock.json 's/^  "version": "\(.*\)",$/\1/p')"
check "packaging/version_win.txt ProductVersion" \
  "$(field packaging/version_win.txt "s/.*'ProductVersion', '\([0-9.]*\)\.0'.*/\1/p")"
check "packaging/version_win.txt filevers" \
  "$(field packaging/version_win.txt 's/.*filevers=(\([0-9]*\), \([0-9]*\), \([0-9]*\), 0).*/\1.\2.\3/p')"

if [ $# -ge 1 ] && [ -n "$1" ]; then
  check "git 标签" "${1#v}"
fi

if [ $fail -ne 0 ]; then
  echo "版本号不一致:请同步修改上述文件(以 VERSION 为准)。"
  exit 1
fi
echo "版本号一致:$want"
