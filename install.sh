#!/usr/bin/env bash
# 小企业财务记账系统 —— 云端一键下载并部署(Ubuntu)
#
# 用法(在 Ubuntu 服务器上执行一行命令即可):
#   curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install.sh | bash
#
# 可选参数(通过环境变量传入):
#   APP_DIR=/opt/cw      安装目录(默认 $HOME/CW)
#   BRANCH=main          分支(默认 main)
#   HTTP_PORT=8080       对外端口(默认 8080)
#   例: curl -fsSL .../install.sh | HTTP_PORT=80 APP_DIR=/opt/cw bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/lsgoodlionel/CW.git}"
APP_DIR="${APP_DIR:-$HOME/CW}"
BRANCH="${BRANCH:-main}"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[安装]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
err()  { echo -e "${RED}[错误]${NC} $1"; }

# 0. 计算是否需要 sudo(非 root 时)
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    err "当前非 root 且无 sudo,请用 root 运行或先安装 sudo。"
    exit 1
  fi
fi

# 1. 检测系统包管理器(本脚本面向 Ubuntu/Debian)
if ! command -v apt-get >/dev/null 2>&1; then
  warn "未检测到 apt-get,本脚本面向 Ubuntu/Debian。"
  warn "请手动安装 git 与 Docker 后,在仓库目录执行 ./deploy.sh。"
fi

# 2. 安装 git
if ! command -v git >/dev/null 2>&1; then
  info "安装 git ..."
  $SUDO apt-get update -y
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y git
fi

# 3. 安装 Docker
if ! command -v docker >/dev/null 2>&1; then
  info "安装 Docker(官方脚本)..."
  curl -fsSL --connect-timeout 20 --max-time 300 --retry 2 https://get.docker.com | $SUDO sh
  $SUDO systemctl enable --now docker 2>/dev/null || true
fi

# 4. 确保 docker compose 可用
if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
  info "安装 docker compose 插件 ..."
  $SUDO apt-get update -y
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y docker-compose-plugin || \
    warn "compose 插件安装失败,请手动安装。"
fi

# 5. 获取代码:优先 git(带超时);失败则用 HTTPS 归档下载(免 git,应对 GitHub 被墙/502/卡住)
REPO_SLUG="lsgoodlionel/CW"
GT=""; command -v timeout >/dev/null 2>&1 && GT="timeout 120"
_dl_tarball() {
  command -v tar >/dev/null 2>&1 || return 1
  local tmp src url
  tmp="$(mktemp -d)" || return 1
  for url in \
    "https://codeload.github.com/${REPO_SLUG}/tar.gz/refs/heads/${BRANCH}" \
    "https://github.com/${REPO_SLUG}/archive/refs/heads/${BRANCH}.tar.gz"; do
    if curl -fsSL --connect-timeout 20 --max-time 300 --retry 2 --retry-delay 2 \
         "$url" -o "$tmp/s.tgz" 2>/dev/null \
       && tar xzf "$tmp/s.tgz" -C "$tmp" 2>/dev/null; then
      src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)"
      if [ -n "$src" ] && [ -f "$src/docker-compose.yml" ]; then
        mkdir -p "$APP_DIR"; cp -R "$src"/. "$APP_DIR"/; rm -rf "$tmp"; return 0
      fi
    fi
  done
  rm -rf "$tmp"; return 1
}
if [ -d "$APP_DIR/.git" ]; then
  info "检测到已存在安装,更新代码:$APP_DIR"
  if $GT git -C "$APP_DIR" -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=20 fetch --all --quiet 2>/dev/null \
     && git -C "$APP_DIR" reset --hard "origin/${BRANCH}" >/dev/null 2>&1; then
    :
  else
    warn "git 更新失败/超时,改用归档下载覆盖最新代码..."
    _dl_tarball || warn "归档下载也失败,使用现有代码继续。"
  fi
else
  info "获取代码到:$APP_DIR"
  if $GT git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR" 2>/dev/null; then
    :
  else
    warn "git clone 失败/超时(网络),改用 HTTPS 归档下载..."
    _dl_tarball || { err "无法获取代码:git 与归档下载均失败。请检查服务器到 GitHub 的网络后重试。"; exit 1; }
  fi
fi

cd "$APP_DIR"
chmod +x deploy.sh

# 6. 透传 HTTP_PORT 到 .env(若用户指定)
# 若需新建 .env,同时随机化数据库密码,避免沿用示例占位密码
if [ -n "${HTTP_PORT:-}" ]; then
  if [ ! -f .env ]; then
    cp .env.example .env
    RAND_PWD=$(openssl rand -hex 16 2>/dev/null || date +%s%N | sha256sum | head -c 32)
    awk -v pwd="$RAND_PWD" \
      '/^POSTGRES_PASSWORD=/{print "POSTGRES_PASSWORD=" pwd; next} {print}' \
      .env > .env.tmp && mv .env.tmp .env
  fi
  awk -v port="$HTTP_PORT" \
    '/^HTTP_PORT=/{print "HTTP_PORT=" port; next} {print}' \
    .env > .env.tmp && mv .env.tmp .env
  info "已设置对外端口:$HTTP_PORT"
fi

# 7. 部署(新装 Docker 时当前会话尚未加入 docker 组,统一用 sudo 跑)
info "开始部署 ..."
if docker info >/dev/null 2>&1; then
  ./deploy.sh
else
  $SUDO ./deploy.sh
fi

echo
info "完成。后续更新只需重新执行本命令即可(会自动拉取最新代码并重建)。"
