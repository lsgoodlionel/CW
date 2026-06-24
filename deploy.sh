#!/usr/bin/env bash
# 小企业财务记账系统 —— Ubuntu 一键部署脚本
set -euo pipefail

cd "$(dirname "$0")"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[部署]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
err()  { echo -e "${RED}[错误]${NC} $1"; }

# 1. 检查 Docker
if ! command -v docker >/dev/null 2>&1; then
  err "未检测到 Docker。请先安装:curl -fsSL https://get.docker.com | sh"
  exit 1
fi

# 兼容 docker compose 插件 与 docker-compose 独立版
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  err "未检测到 docker compose,请安装 Docker Compose 插件。"
  exit 1
fi
info "使用:$DC"

# 2. 准备 .env
if [ ! -f .env ]; then
  cp .env.example .env
  # 自动生成随机数据库密码(用临时文件改写,兼容 GNU/BSD sed)
  RAND_PWD=$(openssl rand -hex 16 2>/dev/null || date +%s%N | shasum -a 256 | head -c 32)
  awk -v pwd="$RAND_PWD" \
    '/^POSTGRES_PASSWORD=/{print "POSTGRES_PASSWORD=" pwd; next} {print}' \
    .env > .env.tmp && mv .env.tmp .env
  info "已生成 .env(数据库密码已随机化)。可编辑后重新运行。"
else
  info "已存在 .env,沿用现有配置。"
fi

# 3. 构建并启动
info "构建并启动容器(首次较慢)..."
$DC up -d --build

# 4. 健康检查
HTTP_PORT=$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || echo 8080)
HTTP_PORT=${HTTP_PORT:-8080}
info "等待服务就绪..."
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:${HTTP_PORT}/api/health" >/dev/null 2>&1; then
    info "✅ 部署成功!访问:http://<服务器IP>:${HTTP_PORT}"
    exit 0
  fi
  sleep 2
done

warn "健康检查超时,请查看日志:$DC logs -f backend"
exit 1
