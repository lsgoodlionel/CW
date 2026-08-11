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

# 1. 升级前自动备份(优先容器内直连导出;回退到带令牌的 HTTP 导出)
HTTP_PORT=8080
if [ -f .env ]; then
  HTTP_PORT=$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || echo 8080)
  HTTP_PORT=${HTTP_PORT:-8080}
fi

_do_backup() {  # $1=输出文件
  local out="$1" pw token
  # 方式一:容器内命令行导出(本版本起支持,无需登录)
  if $DOCKER_SUDO docker compose exec -T backend python -m app.backup_cli > "$out" 2>/dev/null \
     && [ -s "$out" ]; then
    return 0
  fi
  # 方式二(兼容旧镜像):用 .env 的 ADMIN_PASSWORD 登录取令牌后 HTTP 导出
  pw=$(grep -E '^ADMIN_PASSWORD=' .env 2>/dev/null | cut -d= -f2 || true); pw=${pw:-admin123}
  token=$(curl -fsS -X POST "http://localhost:${HTTP_PORT}/api/auth/login" \
            -H 'Content-Type: application/json' \
            -d "{\"username\":\"admin\",\"password\":\"${pw}\"}" 2>/dev/null \
          | sed -n 's/.*"token":"\([^"]*\)".*/\1/p' || true)
  if [ -n "$token" ] \
     && curl -fsS "http://localhost:${HTTP_PORT}/api/data/export?token=${token}" -o "$out" 2>/dev/null \
     && [ -s "$out" ]; then
    return 0
  fi
  return 1
}

# 当 git 无法访问 github.com 时,改用 HTTPS 归档(codeload CDN)下载最新源码覆盖
_fetch_tarball() {
  command -v curl >/dev/null 2>&1 || return 1
  command -v tar  >/dev/null 2>&1 || return 1
  local tmp src
  tmp="$(mktemp -d)" || return 1
  if curl -fsSL "https://codeload.github.com/${REPO_MATCH}/tar.gz/refs/heads/${BRANCH}" \
       2>/dev/null | tar xz -C "$tmp" 2>/dev/null; then
    src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1)"
    if [ -n "$src" ] && [ -f "$src/docker-compose.yml" ]; then
      if command -v rsync >/dev/null 2>&1; then
        rsync -a --exclude='.git' --exclude='.env' --exclude='backups' \
              --exclude='.deployed_sha' "$src"/ "$REPO_DIR"/ 2>/dev/null
      else
        cp -R "$src"/. "$REPO_DIR"/ 2>/dev/null
      fi
      rm -f "$REPO_DIR/.deployed_sha" 2>/dev/null || true   # 强制后续重建
      rm -rf "$tmp"; return 0
    fi
  fi
  rm -rf "$tmp"; return 1
}

mkdir -p backups
BACKUP_FILE="backups/finance-backup-$(date +%Y%m%d-%H%M%S).zip"
if _do_backup "$BACKUP_FILE"; then
  info "已自动备份当前数据 → ${REPO_DIR}/${BACKUP_FILE}"
else
  rm -f "$BACKUP_FILE" 2>/dev/null || true
  warn "升级前备份未成功(首次升级到本版本或管理员密码已改属正常),继续升级。"
  warn "数据卷会完整保留、数据不丢;升级完成后可在「企业信息 → 数据备份」手动导出。"
fi

# 2. 记录当前版本
BEFORE=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# 3. 拉取最新代码(部署目录以远程为准:硬同步到 origin/分支)。
#    获取失败不终止升级——仍用当前本地代码重建容器,确保服务可用。
info "拉取最新代码(分支 ${BRANCH})..."
GIT_ERR="$(mktemp 2>/dev/null || echo /tmp/cw_git_err)"
SYNC_OK=1
if git fetch --all --quiet 2>"$GIT_ERR"; then
  if ! git diff --quiet || ! git diff --cached --quiet; then
    warn "检测到本地改动,已 git stash 暂存(可用 git stash list 查看)。"
    git stash push -m "upgrade-autostash-$(date +%Y%m%d-%H%M%S)" >/dev/null 2>&1 || true
  fi
  git checkout "$BRANCH" --quiet 2>/dev/null \
    || git checkout -B "$BRANCH" "origin/${BRANCH}" --quiet 2>/dev/null || true
  git reset --hard "origin/${BRANCH}" >/dev/null 2>"$GIT_ERR" || SYNC_OK=0
else
  SYNC_OK=0
fi
if [ "$SYNC_OK" != "1" ]; then
  warn "git 方式获取失败,改用 HTTPS 归档下载最新代码..."
  if _fetch_tarball; then
    SYNC_OK=1
    info "已通过归档下载更新到最新代码(将重建容器应用)。"
  else
    warn "获取最新代码失败,将用当前本地代码重建容器(不影响数据)。原因:"
    sed 's/^/    /' "$GIT_ERR" 2>/dev/null | head -4
    warn "多为服务器网络无法访问 GitHub;数据卷保留、服务仍会重建。"
    warn "若为权限问题,可尝试:sudo chown -R \"\$USER\" \"${REPO_DIR}\" 后重试。"
  fi
fi
rm -f "$GIT_ERR" 2>/dev/null || true
AFTER=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# 已构建部署的版本(deploy.sh 记录);与代码不一致说明容器落后于代码,需重建
DEPLOYED="$(cat .deployed_sha 2>/dev/null || echo "")"
DEPLOYED_FULL=""
[ -n "$DEPLOYED" ] && DEPLOYED_FULL="$(git rev-parse "$DEPLOYED" 2>/dev/null || echo "$DEPLOYED")"
HEAD_FULL="$(git rev-parse HEAD 2>/dev/null || echo "")"

if [ "$BEFORE" = "$AFTER" ]; then
  if [ "${FORCE:-}" = "1" ]; then
    warn "代码已是最新(${AFTER}),但按 FORCE=1 强制重建容器..."
  elif [ -n "$HEAD_FULL" ] && [ "$HEAD_FULL" != "$DEPLOYED_FULL" ]; then
    warn "代码已是最新(${AFTER}),但运行中的容器版本落后,自动重建以应用最新代码..."
  else
    info "当前已是最新版本(${AFTER}),且容器已为该版本。"
    info "若界面仍未显示新功能,请在浏览器按 Ctrl+Shift+R 强制刷新清除缓存;"
    info "或用 FORCE=1 强制重建:FORCE=1 curl -fsSL .../upgrade.sh | bash"
    exit 0
  fi
else
  info "版本更新:${BEFORE} → ${AFTER}"
  echo "本次更新内容:"
  git log --oneline "${BEFORE}..${AFTER}" 2>/dev/null | sed 's/^/  • /' || true
fi

# 4. 重建并重启(复用 deploy.sh,保留数据卷)
chmod +x deploy.sh
info "重建镜像并重启服务(数据保留)..."
if [ -n "$DOCKER_SUDO" ]; then
  $DOCKER_SUDO ./deploy.sh
else
  ./deploy.sh
fi

info "✅ 升级完成:${BEFORE} → ${AFTER}"
