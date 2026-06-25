#!/usr/bin/env bash
# 小企业财务记账系统 —— 一键升级到最新版本
#
# 在已部署的仓库目录下执行:
#   ./upgrade.sh
#
# 流程:升级前自动备份数据 → 拉取 GitHub 最新代码 → 重建并重启(保留数据卷)→ 健康检查。
# 数据卷(数据库 + 附件)始终保留,不会丢失。
set -euo pipefail

cd "$(dirname "$0")"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[升级]${NC} $1"; }
warn() { echo -e "${YELLOW}[警告]${NC} $1"; }
err()  { echo -e "${RED}[错误]${NC} $1"; }

BRANCH="${BRANCH:-main}"

# 0. 基础检查
if [ ! -d .git ]; then
  err "当前目录不是 git 仓库,无法升级。请在 install.sh 安装的目录下运行。"
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then err "未检测到 git"; exit 1; fi

# 计算 docker 是否需要 sudo(git 操作不用 sudo,避免 dubious ownership)
DOCKER_SUDO=""
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then DOCKER_SUDO="sudo"; fi
fi

# 1. 升级前自动备份(尽力而为,服务在线才能导出)
HTTP_PORT=8080
if [ -f .env ]; then
  HTTP_PORT=$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || echo 8080)
  HTTP_PORT=${HTTP_PORT:-8080}
fi
mkdir -p backups
TS=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="backups/finance-backup-${TS}.zip"
if curl -fsS "http://localhost:${HTTP_PORT}/api/health" >/dev/null 2>&1; then
  if curl -fsS "http://localhost:${HTTP_PORT}/api/data/export" -o "$BACKUP_FILE" 2>/dev/null; then
    info "已自动备份当前数据 → ${BACKUP_FILE}"
  else
    warn "自动备份失败,继续升级(数据卷仍会保留)。"
  fi
else
  warn "服务未在线,跳过自动备份(数据卷仍会保留)。"
fi

# 2. 记录当前版本
BEFORE=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

# 3. 拉取最新代码
info "拉取最新代码(分支 ${BRANCH})..."
git fetch --all --quiet
if ! git checkout "$BRANCH" --quiet 2>/dev/null; then
  warn "切换到 ${BRANCH} 失败,尝试在当前分支升级。"
fi
if ! git pull --ff-only; then
  err "git pull 失败。若本地有改动,请先用 git stash 暂存后重试。"
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

# 4. 重建并重启(复用 deploy.sh,$DC up -d --build 保留数据卷)
chmod +x deploy.sh
info "重建镜像并重启服务(数据保留)..."
if [ -n "$DOCKER_SUDO" ]; then
  $DOCKER_SUDO ./deploy.sh
else
  ./deploy.sh
fi

info "✅ 升级完成:${BEFORE} → ${AFTER}"
