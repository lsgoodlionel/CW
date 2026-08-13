#!/usr/bin/env bash
# 在 macOS / Linux 上构建"无需 Docker 的原生可执行程序"。
# 前置:已装 Node 18+ 与 Python 3.11+。产物:dist/CWFinance
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/3] 构建前端 frontend/dist ..."
( cd frontend && npm ci && npm run build )

echo "[2/3] 准备 Python 环境与依赖 ..."
python3 -m venv .buildvenv
# shellcheck disable=SC1091
. .buildvenv/bin/activate
python -m pip install -U pip wheel
python -m pip install -r backend/requirements.txt pyinstaller

echo "[3/3] PyInstaller 打包 ..."
pyinstaller --clean -y packaging/cw.spec

echo
echo "✅ 完成。原生程序:$(pwd)/dist/CWFinance"
echo "   双击或在终端运行即可(自动用 SQLite 存到用户数据目录,并打开浏览器)。"
