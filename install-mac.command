#!/bin/bash
# 小企业财务记账系统 —— macOS 本地一键安装 / 启动 / 更新
#
# 用法一(推荐,终端一行):
#   curl -fsSL https://raw.githubusercontent.com/lsgoodlionel/CW/main/install-mac.command | bash
# 用法二(双击):下载本文件后,右键 → 打开(首次需在“系统设置 → 隐私与安全性”允许);
#   或在“终端”执行:  bash ~/Downloads/install-mac.command
#
# 前置:已安装 Docker Desktop(https://www.docker.com/products/docker-desktop/)。
# 幂等:首次安装并构建;再次运行会更新代码并重启(数据保留在 Docker 数据卷,不丢)。
set -euo pipefail

REPO="lsgoodlionel/CW"; BRANCH="main"
APP_DIR="${CW_DIR:-$HOME/CW}"
G='\033[0;32m'; R='\033[0;31m'; Y='\033[1;33m'; N='\033[0m'
say(){ printf "${G}[CW]${N} %s\n" "$1"; }
warn(){ printf "${Y}[CW]${N} %s\n" "$1"; }
err(){ printf "${R}[CW]${N} %s\n" "$1"; }
pause(){ read -n1 -r -p "按任意键关闭本窗口..." _ 2>/dev/null || true; }

# 1) Docker Desktop 就绪
if ! command -v docker >/dev/null 2>&1; then
  err "未检测到 Docker Desktop。即将打开下载页,请安装后重新运行。"
  open "https://www.docker.com/products/docker-desktop/" 2>/dev/null || true
  pause; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  say "正在启动 Docker Desktop(首次可能较慢)..."
  open -a Docker 2>/dev/null || true
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
  if ! docker info >/dev/null 2>&1; then
    err "Docker 未就绪。请手动打开 Docker Desktop 待其变为绿色后重试。"; pause; exit 1
  fi
fi

# 2) 下载 / 更新代码(用 curl + tar,免 git)
_fetch(){
  local tmp; tmp="$(mktemp -d)"
  if curl -fsSL "https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}" \
       | tar xz -C "$tmp" 2>/dev/null; then
    local src; src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -1)"
    if [ -n "$src" ] && [ -f "$src/docker-compose.yml" ]; then
      mkdir -p "$APP_DIR"
      cp -R "$src"/. "$APP_DIR"/     # 覆盖源码;.env 不在包内会保留,数据在卷里不受影响
      rm -rf "$tmp"; return 0
    fi
  fi
  rm -rf "$tmp"; return 1
}
if [ -f "$APP_DIR/docker-compose.yml" ]; then
  say "更新应用代码..."; _fetch || warn "更新失败(网络原因),使用本地已有代码继续。"
else
  say "下载应用代码到 $APP_DIR ..."
  _fetch || { err "下载失败,请检查网络后重试。"; pause; exit 1; }
fi
cd "$APP_DIR"

# 3) 配置 .env(本地使用默认即可)
[ -f .env ] || cp .env.example .env

# 4) 构建并启动(首次较慢)
say "构建并启动容器(首次较慢,请耐心等待)..."
docker compose up -d --build

# 5) 打开浏览器
PORT="$(grep -E '^HTTP_PORT=' .env | cut -d= -f2 || true)"; PORT="${PORT:-8080}"
say "✅ 启动完成!正在打开 http://localhost:${PORT}"
sleep 3
open "http://localhost:${PORT}" 2>/dev/null || true
say "初始账号 admin / admin123(请登录后立即修改密码)。"
say "以后要打开系统:再次运行本文件即可;或在浏览器访问 http://localhost:${PORT}"
say "停止服务:打开 Docker Desktop 停止 CW 容器,或在 ${APP_DIR} 执行 docker compose stop"
pause
