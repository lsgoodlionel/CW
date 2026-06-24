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
  curl -fsSL https://get.docker.com | $SUDO sh
  $SUDO systemctl enable --now docker 2>/dev/null || true
fi

# 4. 确保 docker compose 可用
if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
  info "安装 docker compose 插件 ..."
  $SUDO apt-get update -y
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y docker-compose-plugin || \
    warn "compose 插件安装失败,请手动安装。"
fi

# 5. 克隆或更新代码
if [ -d "$APP_DIR/.git" ]; then
  info "检测到已存在安装,拉取最新代码:$APP_DIR"
  git -C "$APP_DIR" fetch --all --quiet
  git -C "$APP_DIR" checkout "$BRANCH" --quiet
  git -C "$APP_DIR" pull --ff-only
else
  info "克隆仓库到:$APP_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
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
