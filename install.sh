#!/usr/bin/env bash
# 小企业财务记账系统 —— 一键部署 / 升级(Ubuntu),同一条命令通吃
#
# 脚本自动识别:未部署→首次安装;已部署→升级(升级前自动备份、保留数据卷)。
#   curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | bash
#
# 网络不稳导致 curl 取到错误页(<head>/502)时,改为「先下载再执行」:
#   curl -fsSL https://cdn.jsdelivr.net/gh/lsgoodlionel/CW@main/install.sh -o /tmp/cw.sh && bash /tmp/cw.sh
#
# 可选参数(环境变量):
#   APP_DIR=/opt/cw   安装目录(默认 $HOME/CW;升级时自动定位已有部署)
#   BRANCH=main       分支
#   HTTP_PORT=8080    对外端口(可写 host:port,如 127.0.0.1:18080)
#   DEPLOY_MODE=saas  部署模式(private 私有化 / saas 多租户)
#   ALLOW_SELF_REGISTRATION=true / ADMIN_PASSWORD=... / PIP_INDEX_URL=...
#   FORCE=1           升级时即使代码已最新也强制重建
#
# 私有化一键:  curl -fsSL .../install.sh | bash
# SaaS 一键:   curl -fsSL .../install.sh | DEPLOY_MODE=saas ALLOW_SELF_REGISTRATION=true bash
set -euo pipefail

REPO_SLUG="lsgoodlionel/CW"
REPO_URL="${REPO_URL:-https://github.com/${REPO_SLUG}.git}"
APP_DIR="${APP_DIR:-$HOME/CW}"
BRANCH="${BRANCH:-main}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[部署]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
err()  { echo -e "${RED}[错误]${NC} $1"; }

# ---------- sudo ----------
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"
  else err "当前非 root 且无 sudo,请用 root 运行或先安装 sudo。"; exit 1; fi
fi

GT=""; command -v timeout >/dev/null 2>&1 && GT="timeout 120"

# docker compose(自动 sudo 兜底,兼容插件版与独立版)
dc() {
  local s=""; docker info >/dev/null 2>&1 || s="$SUDO"
  if docker compose version >/dev/null 2>&1; then $s docker compose "$@"
  else $s docker-compose "$@"; fi
}

# ---------- 依赖:git / docker / compose ----------
install_prereqs() {
  if ! command -v apt-get >/dev/null 2>&1; then
    warn "未检测到 apt-get,本脚本面向 Ubuntu/Debian。请手动装 git 与 Docker 后在仓库目录执行 ./deploy.sh。"
  fi
  if ! command -v git >/dev/null 2>&1; then
    info "安装 git ..."; $SUDO apt-get update -y
    DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y git
  fi
  if ! command -v docker >/dev/null 2>&1; then
    info "安装 Docker(官方脚本)..."
    curl -fsSL --connect-timeout 20 --max-time 300 --retry 2 https://get.docker.com | $SUDO sh
    $SUDO systemctl enable --now docker 2>/dev/null || true
  fi
  if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
    info "安装 docker compose 插件 ..."; $SUDO apt-get update -y
    DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y docker-compose-plugin || \
      warn "compose 插件安装失败,请手动安装。"
  fi
}

# ---------- 定位已部署目录(用于识别升级) ----------
_is_our_repo() {
  [ -n "$1" ] && [ -f "$1/docker-compose.yml" ] && [ -d "$1/.git" ] && \
    git -C "$1" remote get-url origin 2>/dev/null | grep -q "$REPO_SLUG"
}
_find_repo_dir() {
  _is_our_repo "$APP_DIR" && { echo "$APP_DIR"; return 0; }
  _is_our_repo "$PWD" && { echo "$PWD"; return 0; }
  local sd; sd="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
  _is_our_repo "$sd" && { echo "$sd"; return 0; }
  # 运行中的 compose 栈配置路径(最可靠)
  local json cf d
  json="$(dc ls --all --format json 2>/dev/null || true)"
  if [ -n "$json" ]; then
    for cf in $(echo "$json" | grep -o '"ConfigFiles":"[^"]*"' | sed 's/.*:"//; s/"$//' | tr ',' ' '); do
      d="$(dirname "$cf")"; _is_our_repo "$d" && { echo "$d"; return 0; }
    done
  fi
  local c
  for c in "$HOME/CW" "$HOME/cw" /opt/cw /opt/CW /root/CW /srv/CW; do
    _is_our_repo "$c" && { echo "$c"; return 0; }
  done
  return 1
}

# ---------- 归档下载(免 git 兜底)。$1=目标目录 $2=fresh|update ----------
_dl_tarball() {
  local dir="$1" mode="${2:-fresh}" tmp src url
  command -v tar >/dev/null 2>&1 || return 1
  tmp="$(mktemp -d)" || return 1
  for url in \
    "https://codeload.github.com/${REPO_SLUG}/tar.gz/refs/heads/${BRANCH}" \
    "https://github.com/${REPO_SLUG}/archive/refs/heads/${BRANCH}.tar.gz"; do
    if curl -fsSL --connect-timeout 20 --max-time 300 --retry 2 --retry-delay 2 \
         "$url" -o "$tmp/s.tgz" 2>/dev/null && tar xzf "$tmp/s.tgz" -C "$tmp" 2>/dev/null; then
      src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)"
      if [ -n "$src" ] && [ -f "$src/docker-compose.yml" ]; then
        mkdir -p "$dir"
        if [ "$mode" = "update" ] && command -v rsync >/dev/null 2>&1; then
          rsync -a --exclude='.git' --exclude='.env' --exclude='backups' \
                --exclude='.deployed_sha' "$src"/ "$dir"/ 2>/dev/null
        else
          cp -R "$src"/. "$dir"/
        fi
        rm -rf "$tmp"; return 0
      fi
    fi
  done
  rm -rf "$tmp"; return 1
}

# ---------- .env 参数透传 ----------
set_env() {
  local key="$1" val="$2"
  grep -v "^${key}=" .env > .env.tmp 2>/dev/null || true
  printf '%s=%s\n' "$key" "$val" >> .env.tmp
  mv .env.tmp .env
}
apply_env_overrides() {
  local fresh=0
  if [ ! -f .env ]; then
    cp .env.example .env
    set_env POSTGRES_PASSWORD "$(openssl rand -hex 16 2>/dev/null || date +%s%N | sha256sum | head -c 32)"
    fresh=1
  fi
  [ -n "${HTTP_PORT:-}" ] && { set_env HTTP_PORT "$HTTP_PORT"; info "对外端口:$HTTP_PORT"; }
  if [ -n "${DEPLOY_MODE:-}" ]; then
    set_env DEPLOY_MODE "$DEPLOY_MODE"; info "部署模式:$DEPLOY_MODE"
    # SaaS 首次安装默认不预置管理员(首登页面自设);升级不动已有 ADMIN_PASSWORD
    if [ "$DEPLOY_MODE" = "saas" ] && [ "$fresh" = "1" ] && [ -z "${ADMIN_PASSWORD+x}" ]; then
      set_env ADMIN_PASSWORD ""
      info "SaaS:未预置管理员,请在首次访问时于页面设置超级管理员。"
    fi
  fi
  [ -n "${ALLOW_SELF_REGISTRATION:-}" ] && set_env ALLOW_SELF_REGISTRATION "$ALLOW_SELF_REGISTRATION"
  [ "${ADMIN_PASSWORD+x}" = "x" ] && set_env ADMIN_PASSWORD "${ADMIN_PASSWORD}"
  [ -n "${PIP_INDEX_URL:-}" ] && set_env PIP_INDEX_URL "$PIP_INDEX_URL"
}

run_deploy() {
  chmod +x deploy.sh
  if docker info >/dev/null 2>&1; then ./deploy.sh; else $SUDO ./deploy.sh; fi
}

# ---------- 升级 ----------
do_upgrade() {
  local dir="$1"; cd "$dir"
  info "检测到已部署:$dir —— 执行升级(数据卷保留、数据不丢)"
  apply_env_overrides
  # 升级前自动备份。</dev/null 关键:curl|bash 时若不切断 stdin,docker 会读走管道里
  # 剩余脚本内容,导致备份后脚本静默退出、代码与容器都未更新。
  mkdir -p backups
  local bk="backups/finance-backup-$(date +%Y%m%d-%H%M%S).zip"
  if dc exec -T backend python -m app.backup_cli </dev/null > "$bk" 2>/dev/null && [ -s "$bk" ]; then
    info "已自动备份当前数据 → $dir/$bk"
  else
    rm -f "$bk" 2>/dev/null || true
    warn "升级前自动备份未成功(数据卷完整保留、数据不丢),继续升级。"
    warn "如需手动备份,可先在「企业信息 → 数据备份」导出,或 dc exec -T backend python -m app.backup_cli > bk.zip"
  fi
  local before after
  before="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  info "拉取最新代码(分支 ${BRANCH})..."
  if $GT git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=20 fetch --all --quiet 2>/dev/null \
     && git reset --hard "origin/${BRANCH}" >/dev/null 2>&1; then :
  else
    warn "git 更新失败/超时,改用归档下载覆盖最新代码..."
    _dl_tarball "$dir" update || warn "归档下载也失败,使用现有代码重建。"
    rm -f .deployed_sha 2>/dev/null || true
  fi
  after="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  if [ "$before" != "$after" ]; then
    info "版本更新:$before → $after"
    git log --oneline "${before}..${after}" 2>/dev/null | sed 's/^/  • /' || true
  elif [ "${FORCE:-}" = "1" ]; then
    warn "代码已是最新($after),按 FORCE=1 强制重建。"
  else
    info "代码已是最新($after),仍重建以确保容器为最新镜像。"
  fi
  run_deploy
  info "✅ 升级完成($before → $after)。"
}

# ---------- 首次安装 ----------
do_install() {
  info "获取代码到:$APP_DIR"
  if $GT git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR" 2>/dev/null; then :
  else
    warn "git clone 失败/超时(网络),改用 HTTPS 归档下载..."
    _dl_tarball "$APP_DIR" fresh || { err "无法获取代码:git 与归档下载均失败。请检查服务器到 GitHub 的网络后重试。"; exit 1; }
  fi
  cd "$APP_DIR"
  apply_env_overrides
  info "开始部署 ..."
  run_deploy
  echo
  info "完成。以后再次执行本命令即为「升级」(自动定位、升级前备份、保留数据)。"
}

# ---------- 主流程 ----------
install_prereqs
FOUND="$(_find_repo_dir || true)"
if [ -n "$FOUND" ]; then
  do_upgrade "$FOUND"
else
  do_install
fi
