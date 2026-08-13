# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置 —— 无需 Docker 的原生单文件可执行程序。
# 在仓库根目录、目标操作系统上执行:  pyinstaller --clean -y packaging/cw.spec
# 产物:dist/CWFinance(.exe)。前端需先构建到 frontend/dist。
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH 由 PyInstaller 注入,为本 .spec 所在目录(packaging/),据此定位仓库根
ROOT = os.path.dirname(SPECPATH)
BACKEND = os.path.join(ROOT, "backend")
FRONTEND_DIST = os.path.join(ROOT, "frontend", "dist")
RUN_PY = os.path.join(SPECPATH, "run.py")

if not os.path.isdir(FRONTEND_DIST):
    raise SystemExit("缺少 frontend/dist,请先在 frontend 目录执行 npm ci && npm run build")

datas = [(FRONTEND_DIST, "frontend_dist")]
datas += collect_data_files("reportlab")   # 内置中文 CID 字体等

hiddenimports = []
hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["reportlab", "openpyxl", "anyio", "email.mime.multipart"]

a = Analysis(
    [RUN_PY],
    pathex=[BACKEND],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["psycopg", "psycopg2", "tkinter"],  # 原生用 SQLite,无需 PostgreSQL 驱动
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="CWFinance",
    console=True,      # 保留控制台窗口以显示本地地址/日志
    disable_windowed_traceback=False,
    upx=False,
)
