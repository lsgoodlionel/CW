# 在 Windows 上构建"无需 Docker 的原生可执行程序"。
# 前置:已装 Node 18+ 与 Python 3.11+。产物:dist\CWFinance.exe
# 用法(PowerShell):  ./packaging/build-native.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "[1/3] 构建前端 frontend/dist ..."
Push-Location frontend
npm ci
npm run build
Pop-Location

Write-Host "[2/3] 准备 Python 环境与依赖 ..."
python -m venv .buildvenv
& .\.buildvenv\Scripts\python.exe -m pip install -U pip wheel
& .\.buildvenv\Scripts\python.exe -m pip install -r backend/requirements.txt pyinstaller

Write-Host "[3/3] PyInstaller 打包 ..."
& .\.buildvenv\Scripts\pyinstaller.exe --clean -y packaging/cw.spec

Write-Host ""
Write-Host "✅ 完成。原生程序:dist\CWFinance.exe"
Write-Host "   双击运行即可(自动用 SQLite 存到用户数据目录,并打开浏览器)。"
