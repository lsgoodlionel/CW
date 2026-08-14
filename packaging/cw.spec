# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置 —— 无需 Docker 的原生可执行程序。
# 在仓库根目录、目标操作系统上执行:  pyinstaller --clean -y packaging/cw.spec
# 产物:Windows dist/CWFinance.exe;macOS dist/CWFinance.app;Linux dist/CWFinance。
# 前端需先构建到 frontend/dist。
import os
import sys
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
# 平台相关:图标、版本资源、是否显示控制台窗口
_ICON = None
_VERSION = None
if sys.platform == "win32":
    _ICON = os.path.join(SPECPATH, "icon.ico")
    _VERSION = os.path.join(SPECPATH, "version_win.txt")
elif sys.platform == "darwin":
    _ICON = os.path.join(SPECPATH, "icon.icns")
# Windows/macOS 采用“无控制台窗口”模式;Linux 保留控制台
_CONSOLE = sys.platform not in ("win32", "darwin")

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="CWFinance",
    console=_CONSOLE,
    disable_windowed_traceback=False,
    icon=_ICON,
    version=_VERSION,
    upx=False,
)

# macOS 打成 .app 应用包,双击不弹终端
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="CWFinance.app",
        icon=_ICON,
        bundle_identifier="com.lsgoodlionel.cwfinance",
        info_plist={
            "CFBundleName": "小企业财务记账系统",
            "CFBundleDisplayName": "小企业财务记账系统",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )
