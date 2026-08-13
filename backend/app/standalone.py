"""无需 Docker 的原生单进程入口。

一个进程同时:提供 /api 后端、托管前端静态页(SPA)、用 SQLite 存数据(放到用户数据目录),
启动后自动打开浏览器。供 PyInstaller 打包成 Windows/macOS/Linux 原生可执行文件。

打包见 packaging/cw.spec;直接源码运行:先构建前端 `frontend/dist`,再
    python -m app.standalone
"""
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def _data_dir() -> Path:
    """各平台的可写用户数据目录(存放 SQLite 库、附件、密钥)。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    d = base / "CWFinance"
    (d / "uploads").mkdir(parents=True, exist_ok=True)
    return d


def _static_dir() -> Path | None:
    """前端静态目录:优先 PyInstaller 解包目录,其次源码 frontend/dist,可用 CW_STATIC_DIR 覆盖。"""
    override = os.environ.get("CW_STATIC_DIR")
    if override and Path(override).is_dir():
        return Path(override)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cand = Path(meipass) / "frontend_dist"
        if cand.is_dir():
            return cand
    repo = Path(__file__).resolve().parents[2]
    cand = repo / "frontend" / "dist"
    return cand if cand.is_dir() else None


def _persist_secret(data: Path) -> str:
    """首次生成随机令牌密钥并落盘,之后复用,保证重启后登录态/令牌规则稳定。"""
    f = data / "auth_secret.txt"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    import secrets
    s = secrets.token_hex(32)
    f.write_text(s, encoding="utf-8")
    return s


def _free_port(preferred: int = 8080) -> int:
    for port in (preferred, 8090, 8123, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    return preferred


def create_app():
    """设置好本机运行所需的环境(SQLite/上传目录/密钥),构建并返回 FastAPI 应用(含静态托管)。"""
    data = _data_dir()
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{(data / 'cw.db').as_posix()}")
    os.environ.setdefault("UPLOAD_DIR", str(data / "uploads"))
    os.environ.setdefault("REQUIRE_AUTH", "true")
    os.environ.setdefault("ADMIN_PASSWORD", "admin123")
    os.environ.setdefault("AUTH_SECRET", _persist_secret(data))
    os.environ.setdefault("CORS_ORIGINS", "*")

    # 环境就绪后再导入应用(config 在导入时读取环境)
    from .main import app

    static = _static_dir()
    if static is not None:
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse
        assets = static / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
        index = static / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            # 仅兜底非 /api 的前端路由;真实静态文件直接返回,其余回退 index.html(SPA)
            if full_path.startswith("api/"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            target = static / full_path
            if full_path and target.is_file():
                return FileResponse(str(target))
            return FileResponse(str(index))

    return app


def main() -> None:
    data = _data_dir()
    app = create_app()
    port = _free_port(int(os.environ.get("CW_PORT", "8080")))
    url = f"http://127.0.0.1:{port}"
    print(f"[CW] 数据目录:{data}")
    print(f"[CW] 正在启动本地服务:{url}(初始账号 admin / admin123)")
    if os.environ.get("CW_NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
