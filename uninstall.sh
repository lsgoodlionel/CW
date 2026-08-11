#!/usr/bin/env bash
# 小企业财务记账系统 —— 一键卸载(停用服务 + 删除数据)
#
# 【远程一行卸载】在已部署的 Ubuntu 服务器上执行(非交互需显式确认 ASSUME_YES=1):
#   ASSUME_YES=1 bash -c "$(curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/uninstall.sh)"
#
# 【本地卸载】在仓库目录执行: ./uninstall.sh
#
# 作用:停止并删除容器、删除数据卷(数据库 db_data + 附件 uploads)、删除本地构建镜像。
# 默认在卸载前把现有数据导出到仓库目录之外做一次安全备份。
#
# 可选环境变量:
#   ASSUME_YES=1   跳过交互确认(管道/非交互环境卸载必须显式设置)
#   NO_BACKUP=1    跳过卸载前的数据备份
#   BACKUP_DIR=... 备份保存目录(默认 $HOME/cw-uninstall-backups)
#   PURGE_DIR=1    连同部署目录一起删除(默认保留代码目录,仅清数据)
#   KEEP_IMAGES=1  保留本地构建镜像(默认删除 backend/frontend 镜像)
#   APP_DIR=...    显式指定部署目录(自动定位失败时使用)
set -euo pipefail

REPO_MATCH="lsgoodlionel/CW"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[卸载]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
err()  { echo -e "${RED}[错误]${NC} $1"; }

DOCKER_SUDO=""
if ! docker info >/dev/null 2>&1; then
  command -v sudo >/dev/null 2>&1 && DOCKER_SUDO="sudo"
fi

_is_our_repo() {
  [ -n "$1" ] && [ -f "$1/docker-compose.yml" ] && [ -d "$1/.git" ] && \
    git -C "$1" remote get-url origin 2>/dev/null | grep -q "$REPO_MATCH"
}

_find_repo_dir() {
  if [ -n "${APP_DIR:-}" ] && _is_our_repo "$APP_DIR"; then echo "$APP_DIR"; return 0; fi
  local sd
  sd="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
  if _is_our_repo "$sd"; then echo "$sd"; return 0; fi
  if _is_our_repo "$PWD"; then echo "$PWD"; return 0; fi
  local json cf d
  json="$($DOCKER_SUDO docker compose ls --all --format json 2>/dev/null || true)"
  if [ -n "$json" ]; then
    for cf in $(echo "$json" | grep -o '"ConfigFiles":"[^"]*"' | sed 's/.*:"//; s/"$//' | tr ',' ' '); do
      d="$(dirname "$cf")"
      if _is_our_repo "$d"; then echo "$d"; return 0; fi
    done
  fi
  local c
  for c in "$HOME/CW" "$HOME/cw" /opt/cw /opt/CW /root/CW /srv/CW; do
    if _is_our_repo "$c"; then echo "$c"; return 0; fi
  done
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
  echo "  · 请显式指定目录后重试,例如:"
  echo "      APP_DIR=/opt/cw ASSUME_YES=1 bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/${REPO_MATCH}/main/uninstall.sh)\""
  exit 1
fi
info "已定位部署目录:$REPO_DIR"
cd "$REPO_DIR"

HTTP_PORT=8080
if [ -f .env ]; then
  HTTP_PORT=$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || echo 8080)
  HTTP_PORT=${HTTP_PORT:-8080}
fi

# 危险操作确认
echo
warn "此操作将永久删除以下内容,且不可恢复:"
echo "    · 运行中的容器(db / backend / frontend)"
echo "    · 数据卷 db_data(全部数据库数据:凭证/科目/用户/审批等)"
echo "    · 数据卷 uploads(全部上传附件与生成的审批记录单)"
[ "${KEEP_IMAGES:-}" = "1" ] || echo "    · 本地构建的镜像(backend / frontend)"
[ "${PURGE_DIR:-}" = "1" ] && echo "    · 部署目录本身:$REPO_DIR"
echo
if [ "${ASSUME_YES:-}" != "1" ]; then
  if [ ! -t 0 ]; then
    err "检测到非交互环境(管道运行)。为避免误删,请显式设置 ASSUME_YES=1 后重试。"
    exit 1
  fi
  read -r -p "确认卸载并删除以上数据?输入 yes 继续:" ans
  [ "$ans" = "yes" ] || { info "已取消,未做任何更改。"; exit 0; }
fi

# 1. 卸载前安全备份(导出到仓库目录之外,避免随目录删除)
if [ "${NO_BACKUP:-}" != "1" ]; then
  BACKUP_DIR="${BACKUP_DIR:-$HOME/cw-uninstall-backups}"
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="$BACKUP_DIR/finance-backup-$(date +%Y%m%d-%H%M%S).zip"
  if $DOCKER_SUDO docker compose exec -T backend python -m app.backup_cli > "$BACKUP_FILE" 2>/dev/null \
     && [ -s "$BACKUP_FILE" ]; then
    info "已备份当前数据 → $BACKUP_FILE(卸载后仍保留,可用于重装恢复)"
  else
    warn "备份失败(容器未运行或数据库不可用),跳过备份继续卸载。可加 NO_BACKUP=1 明确跳过。"
    rm -f "$BACKUP_FILE" 2>/dev/null || true
  fi
else
  warn "已按 NO_BACKUP=1 跳过备份。"
fi

# 2. 停止并删除容器 + 数据卷(+ 本地镜像)
DOWN_ARGS="-v --remove-orphans"
[ "${KEEP_IMAGES:-}" = "1" ] || DOWN_ARGS="$DOWN_ARGS --rmi local"
info "停止服务并删除容器与数据卷..."
$DOCKER_SUDO docker compose down $DOWN_ARGS || {
  err "docker compose down 执行失败,请检查 Docker 是否运行。"
  exit 1
}
info "容器与数据卷(db_data / uploads)已删除。"

# 3. 可选:删除部署目录
if [ "${PURGE_DIR:-}" = "1" ]; then
  PARENT="$(dirname "$REPO_DIR")"
  cd "$PARENT"
  info "删除部署目录:$REPO_DIR"
  $DOCKER_SUDO rm -rf "$REPO_DIR"
  info "部署目录已删除。"
else
  info "已保留代码目录(如需彻底清除:PURGE_DIR=1 重新执行,或手动 rm -rf $REPO_DIR)。"
fi

echo
info "✅ 卸载完成。系统服务已停止,相关数据已删除。"
[ "${NO_BACKUP:-}" != "1" ] && info "如需恢复:重新部署后,在「数据备份」页导入上面保留的备份 zip。"
