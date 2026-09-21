#!/usr/bin/env bash
# 兼容入口:安装与升级已合并进 install.sh(同一条命令自动识别首次安装 / 升级)。
# 本脚本仅转调最新 install.sh,保留旧的 upgrade 命令可用。
#
#   curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/upgrade.sh | bash
#   或在仓库目录:./upgrade.sh
#
# 环境变量(FORCE / APP_DIR / DEPLOY_MODE 等)会被继承传递给 install.sh。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$DIR" ] && [ -f "$DIR/install.sh" ]; then
  exec bash "$DIR/install.sh" "$@"
fi
# 通过管道执行(无本地文件)时,拉取最新 install.sh 运行
curl -fsSL "https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh" | bash
