#!/usr/bin/env bash
# 小企业财务记账系统 —— Ubuntu 一键部署脚本
set -euo pipefail

cd "$(dirname "$0")"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[部署]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
err()  { echo -e "${RED}[错误]${NC} $1"; }

diagnose_docker_hub_ipv6() {
  command -v curl >/dev/null 2>&1 || return 0
  if curl -4 -fsS --connect-timeout 8 --max-time 15 https://registry-1.docker.io/v2/ >/dev/null 2>&1; then
    return 0
  fi
  local v4_rc=$?
  if curl -6 -fsS --connect-timeout 8 --max-time 15 https://registry-1.docker.io/v2/ >/dev/null 2>&1; then
    return 0
  fi
  local v6_rc=$?
  if [ "$v4_rc" = "22" ] && [ "$v6_rc" != "22" ]; then
    warn "检测到 Docker Hub IPv4 可达但 IPv6 访问异常,本地构建拉取 node/python 基础镜像可能失败。"
    warn "建议优先使用 GHCR 预构建镜像;若必须本地构建,请在服务器网络层临时禁用 Docker 到 Docker Hub 的 IPv6 或配置可审计的 IPv4 优先策略后重试。"
  fi
}

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

# 优先使用当前提交的不可混淆镜像标签。正式 Release 使用 vX.Y.Z，
# 其他提交使用 CI 的 sha-XXXXXXX；显式配置的镜像仍由管理员决定。
HEAD_SHA="$(git -c "safe.directory=$(pwd)" rev-parse HEAD 2>/dev/null || true)"
if [ -n "$HEAD_SHA" ]; then
  IMAGE_TAG="sha-${HEAD_SHA:0:7}"
  if [ -f VERSION ]; then
    RELEASE_TAG="v$(cat VERSION)"
    TAG_SHA="$(git -c "safe.directory=$(pwd)" rev-parse -q --verify "refs/tags/${RELEASE_TAG}^{commit}" 2>/dev/null || true)"
    [ "$TAG_SHA" != "$HEAD_SHA" ] || IMAGE_TAG="$RELEASE_TAG"
  fi
  if [ -z "${BACKEND_IMAGE:-}" ] && ! grep -q '^BACKEND_IMAGE=' .env; then
    export BACKEND_IMAGE="ghcr.io/lsgoodlionel/cw-backend:${IMAGE_TAG}"
  fi
  if [ -z "${FRONTEND_IMAGE:-}" ] && ! grep -q '^FRONTEND_IMAGE=' .env; then
    export FRONTEND_IMAGE="ghcr.io/lsgoodlionel/cw-frontend:${IMAGE_TAG}"
  fi
fi

command -v python3 >/dev/null 2>&1 || { err "缺少 python3,无法验证数据库认证。"; exit 1; }
python3 scripts/check-db-auth.py || { err "数据库预检失败,未切换应用容器。"; exit 1; }

# 保存旧容器镜像。仅对已有服务回退,不触及数据库卷。
OLD_BACKEND_ID=""; OLD_FRONTEND_ID=""
BACKEND_CID="$($DC ps -q backend 2>/dev/null || true)"
FRONTEND_CID="$($DC ps -q frontend 2>/dev/null || true)"
[ -z "$BACKEND_CID" ] || OLD_BACKEND_ID="$(docker inspect --format '{{.Image}}' "$BACKEND_CID" 2>/dev/null || true)"
[ -z "$FRONTEND_CID" ] || OLD_FRONTEND_ID="$(docker inspect --format '{{.Image}}' "$FRONTEND_CID" 2>/dev/null || true)"
if [ -n "$OLD_BACKEND_ID" ] && [ -n "$OLD_FRONTEND_ID" ]; then
  docker tag "$OLD_BACKEND_ID" cw-backend:pre-deploy-local
  docker tag "$OLD_FRONTEND_ID" cw-frontend:pre-deploy-local
fi
DB_CID="$($DC ps -q db 2>/dev/null || true)"
UP_ARGS=(up -d)
[ -z "$DB_CID" ] || UP_ARGS=(up -d --no-deps)
RAW_PORT=$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || echo 8080)
RAW_PORT=${RAW_PORT:-8080}
PORT="${RAW_PORT##*:}"          # 支持 127.0.0.1:18080 等回环绑定

rollback() {
  [ -n "$OLD_BACKEND_ID" ] && [ -n "$OLD_FRONTEND_ID" ] || return 0
  warn "部署验证失败,恢复升级前的前后端镜像。"
  BACKEND_IMAGE=cw-backend:pre-deploy-local FRONTEND_IMAGE=cw-frontend:pre-deploy-local \
    $DC up -d --no-deps --force-recreate --no-build backend frontend || true
  local i
  for i in $(seq 1 18); do
    if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
      warn "旧版服务已恢复健康; .deployed_sha 保持原值。"
      return 0
    fi
    sleep 2
  done
  err "旧版服务未恢复健康,请检查备份与后端日志。"
}

# 3. 启动:优先拉取预构建镜像(GHCR,免服务器本地 pip/npm 构建);失败回退本地构建
if [ "${FORCE_BUILD:-0}" = "1" ]; then
  info "FORCE_BUILD=1,本地构建并启动..."
  $DC "${UP_ARGS[@]}" --build backend frontend || { rollback; exit 1; }
elif timeout 180 $DC pull backend frontend >/dev/null 2>&1; then
  info "已拉取预构建镜像(GHCR),直接启动(免本地构建)..."
  $DC "${UP_ARGS[@]}" --no-build backend frontend || { rollback; exit 1; }
else
  if [ -n "$OLD_BACKEND_ID" ] && [ -n "$OLD_FRONTEND_ID" ]; then
    err "预构建镜像拉取失败或超时;现有服务保持运行。若确需本地构建,请显式设置 FORCE_BUILD=1。"
    exit 1
  fi
  warn "首次安装无法拉取预构建镜像,回退本地构建..."
  diagnose_docker_hub_ipv6
  $DC "${UP_ARGS[@]}" --build backend frontend || { rollback; exit 1; }
fi

# 4. 健康检查
info "等待服务就绪..."
for i in $(seq 1 30); do
  if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
if ! curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
  rollback
  err "健康检查超时,部署记录未更新。请查看后端日志。"
  exit 1
fi

BACKEND_CID="$($DC ps -q backend)"; FRONTEND_CID="$($DC ps -q frontend)"
BACKEND_RUNNING="$(docker inspect --format '{{.Image}}' "$BACKEND_CID")"
FRONTEND_RUNNING="$(docker inspect --format '{{.Image}}' "$FRONTEND_CID")"
mapfile -t IMAGE_REFS < <($DC config --format json | python3 -c 'import json,sys; s=json.load(sys.stdin)["services"]; print(s["backend"]["image"]); print(s["frontend"]["image"])')
BACKEND_EXPECTED="$(docker image inspect --format '{{.Id}}' "${IMAGE_REFS[0]}")"
FRONTEND_EXPECTED="$(docker image inspect --format '{{.Id}}' "${IMAGE_REFS[1]}")"
if [ "$BACKEND_RUNNING" != "$BACKEND_EXPECTED" ] || [ "$FRONTEND_RUNNING" != "$FRONTEND_EXPECTED" ]; then
  rollback
  err "运行镜像与目标镜像不一致,部署记录未更新。"
  exit 1
fi
EXPECTED_VERSION="$(cat VERSION)"
if [ "$(docker exec "$BACKEND_CID" python -c 'from app.version import APP_VERSION; print(APP_VERSION)' 2>/dev/null)" != "$EXPECTED_VERSION" ] || \
   ! docker exec "$FRONTEND_CID" grep -q "适用系统版本 v${EXPECTED_VERSION}" /usr/share/nginx/html/manual.html; then
  rollback
  err "容器版本与仓库 VERSION 不一致,部署记录未更新。"
  exit 1
fi
if [ -n "$HEAD_SHA" ]; then
  printf '%s\n' "$HEAD_SHA" > .deployed_sha.tmp
  mv .deployed_sha.tmp .deployed_sha
fi
info "✅ 部署成功!访问:http://<服务器IP>:${PORT}"
