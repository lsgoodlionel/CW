#!/usr/bin/env bash
# 小企业财务记账系统 —— 一键升级到最新版本
#
# 【远程一行升级】在已部署的 Ubuntu 服务器上,任意目录直接执行:
#   curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/upgrade.sh | bash
#
# 【本地升级】在仓库目录执行: ./upgrade.sh
#
# 脚本会自动定位已部署目录 → 升级前自动备份 → 拉取最新代码 → 重建重启(保留数据卷)。
# 若自动定位失败,可显式指定: APP_DIR=/路径 curl ... | bash
set -euo pipefail

REPO_MATCH="lsgoodlionel/CW"          # 用于识别本项目仓库
BRANCH="${BRANCH:-main}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[升级]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
err()  { echo -e "${RED}[错误]${NC} $1"; }

# docker 是否需要 sudo(git 操作保持当前用户,避免 dubious ownership)
DOCKER_SUDO=""
if ! docker info >/dev/null 2>&1; then
  command -v sudo >/dev/null 2>&1 && DOCKER_SUDO="sudo"
fi

# 判断某目录是否为本项目部署目录
_is_our_repo() {
  [ -n "$1" ] && [ -f "$1/docker-compose.yml" ] && [ -d "$1/.git" ] && \
    git -C "$1" remote get-url origin 2>/dev/null | grep -q "$REPO_MATCH"
}

# 自动定位已部署目录
_find_repo_dir() {
  # 1. 显式 APP_DIR
  if [ -n "${APP_DIR:-}" ] && _is_our_repo "$APP_DIR"; then echo "$APP_DIR"; return 0; fi
  # 2. 脚本自身所在目录(本地 ./upgrade.sh 运行时)
  local sd
  sd="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
  if _is_our_repo "$sd"; then echo "$sd"; return 0; fi
  # 3. 当前目录
  if _is_our_repo "$PWD"; then echo "$PWD"; return 0; fi
  # 4. 运行中的 docker compose 栈配置路径(最可靠)
  local json cf d
  json="$($DOCKER_SUDO docker compose ls --all --format json 2>/dev/null || true)"
  if [ -n "$json" ]; then
    for cf in $(echo "$json" | grep -o '"ConfigFiles":"[^"]*"' | sed 's/.*:"//; s/"$//' | tr ',' ' '); do
      d="$(dirname "$cf")"
      if _is_our_repo "$d"; then echo "$d"; return 0; fi
    done
  fi
  # 5. 常见安装目录
  local c
  for c in "$HOME/CW" "$HOME/cw" /opt/cw /opt/CW /root/CW /srv/CW; do
    if _is_our_repo "$c"; then echo "$c"; return 0; fi
  done
  # 6. 在常见根路径下搜索带本仓库 remote 的目录
  local base gc
  for base in "$HOME" /opt /srv /root; do
    [ -d "$base" ] || continue
    while IFS= read -r gc; do
      d="$(dirname "$(dirname "$gc")")"
      if _is_our_repo "$d"; then echo "$d"; return 0; fi
    done < <(find "$base" -maxdepth 4 -path '*/.git/config' 2>/dev/null \
             | xargs grep -l "$REPO_MATCH" 2>/dev/null || true)
  done
  return 1
}

REPO_DIR="$(_find_repo_dir || true)"
if [ -z "$REPO_DIR" ]; then
  err "未能自动定位已部署目录。"
  echo "  · 请确认服务器上已通过 install.sh 部署过本系统"
  echo "  · 或显式指定目录后重试,例如:"
  echo "      APP_DIR=/opt/cw bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/${REPO_MATCH}/main/upgrade.sh)\""
  exit 1
fi
info "已定位部署目录:$REPO_DIR"
# 仅自检定位(调试用):UPGRADE_DETECT_ONLY=1 时打印目录后退出
if [ "${UPGRADE_DETECT_ONLY:-}" = "1" ]; then echo "$REPO_DIR"; exit 0; fi
cd "$REPO_DIR"

if ! command -v git >/dev/null 2>&1; then err "未检测到 git"; exit 1; fi
# 校验目录可写(避免 root 安装、普通用户升级导致失败)
if [ ! -w "$REPO_DIR/.git" ]; then
  warn "目录不可写,可能需要用安装时的用户或 sudo 运行。"
fi

# 1. 升级前自动备份(服务在线才可导出)
HTTP_PORT=8080
if [ -f .env ]; then
  HTTP_PORT=$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || echo 8080)
  HTTP_PORT=${HTTP_PORT:-8080}
fi
mkdir -p backups
BACKUP_FILE="backups/finance-backup-$(date +%Y%m%d-%H%M%S).zip"
if curl -fsS "http://localhost:${HTTP_PORT}/api/health" >/dev/null 2>&1 \
   && curl -fsS "http://localhost:${HTTP_PORT}/api/data/export" -o "$BACKUP_FILE" 2>/dev/null; then
  info "已自动备份当前数据 → ${REPO_DIR}/${BACKUP_FILE}"
else
  warn "服务未在线或备份失败,继续升级(数据卷仍会保留)。"
fi

# 2. 记录当前版本
BEFORE=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# 3. 拉取最新代码
info "拉取最新代码(分支 ${BRANCH})..."
git fetch --all --quiet
git checkout "$BRANCH" --quiet 2>/dev/null || warn "切换到 ${BRANCH} 失败,使用当前分支。"
if ! git pull --ff-only; then
  err "git pull 失败。若本地有改动,请先 git stash 暂存后重试。"
  exit 1
fi
AFTER=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

if [ "$BEFORE" = "$AFTER" ]; then
  info "当前已是最新版本(${AFTER}),无需升级。"
  exit 0
fi
info "版本更新:${BEFORE} → ${AFTER}"
echo "本次更新内容:"
git log --oneline "${BEFORE}..${AFTER}" 2>/dev/null | sed 's/^/  • /' || true

# 4. 重建并重启(复用 deploy.sh,保留数据卷)
chmod +x deploy.sh
info "重建镜像并重启服务(数据保留)..."
if [ -n "$DOCKER_SUDO" ]; then
  $DOCKER_SUDO ./deploy.sh
else
  ./deploy.sh
fi

info "✅ 升级完成:${BEFORE} → ${AFTER}"
