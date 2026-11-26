"""运行日志采集 + 出错自动打包上传 GitHub(共享 paper 仓库)。

设计:
- 内存环形缓冲记录最近日志(所有级别),供出错时附带上下文。
- 捕获未处理异常/500 时,打包(traceback + 近期日志 + 元信息)为 zip,经 GitHub
  Contents API 上传到 <repo>/<slug>/logs/<UTC时间戳>_<sig>.zip。
- 节流去重:同类错误在冷却期内只上传一次;上传在后台线程执行,绝不阻塞请求或抛出异常。
- 凭据(PAT)仅来自环境变量(settings.paper_repo_token),缺失则功能自动禁用;绝不记录 token。
- 安全提示:日志可能含敏感信息,paper 仓库应设为 private。
"""
import base64
import hashlib
import io
import json
import logging
import re
import threading
import time
import traceback as _tb
import urllib.request
import urllib.error
from urllib.parse import quote
import zipfile
from collections import deque
from datetime import datetime, timezone

from .config import settings
from .version import APP_VERSION

_LOG = logging.getLogger("cw.diag")

_RING_MAX = 800
_ring: deque[str] = deque(maxlen=_RING_MAX)
_last_upload: dict[str, float] = {}
_lock = threading.Lock()
_GITHUB_API = "https://api.github.com"
_USER_AGENT = "CW-Diagnostics/1.0"


class _RingHandler(logging.Handler):
    """把日志记录写入内存环形缓冲。"""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _ring.append(self.format(record))
        except Exception:
            pass


def install_log_capture() -> None:
    """在根及 uvicorn 日志器挂载环形缓冲处理器(幂等)。应用启动调用一次。"""
    handler = _RingHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.setLevel(logging.INFO)
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        if not any(isinstance(h, _RingHandler) for h in lg.handlers):
            lg.addHandler(handler)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel(logging.INFO)


def enabled() -> bool:
    return bool(settings.error_report_enabled and token_valid() and settings.paper_repo)


def token_valid() -> bool:
    """GitHub PAT 必须可安全写入 HTTP 头;注释占位值不能算已配置。"""
    token = settings.paper_repo_token
    return bool(token and token.isascii() and not any(ch.isspace() for ch in token)
                and "#" not in token)


def token_error() -> str | None:
    if settings.paper_repo_token and not token_valid():
        return "PAPER_REPO_TOKEN 格式无效:请检查 .env 是否把注释写入令牌值"
    return None


def recent_lines() -> list[str]:
    return list(_ring)


def capture_enabled() -> bool:
    """日志采集与外部上传分别报告,避免未配 token 时误报采集关闭。"""
    return any(isinstance(handler, _RingHandler) for handler in logging.getLogger().handlers)


def _signature(exc: BaseException) -> str:
    """错误签名:异常类型 + 最末栈帧(文件:行),用于节流去重。"""
    frames = _tb.extract_tb(exc.__traceback__)
    last = frames[-1] if frames else None
    base = f"{type(exc).__name__}:{last.filename}:{last.lineno}" if last else type(exc).__name__
    return hashlib.sha1(base.encode()).hexdigest()[:10]


def _build_zip(meta: dict, tb_text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
        zf.writestr("traceback.txt", tb_text or "(无异常栈)")
        zf.writestr("recent.log", "\n".join(_ring) or "(无日志)")
    return buf.getvalue()


def package_local(note: str = "") -> bytes:
    """仅打包当前进程的日志,不访问外部仓库或要求 token。"""
    meta = {
        "app": settings.log_app_slug, "version": APP_VERSION,
        "deploy_mode": settings.deploy_mode,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "error_type": "manual", "error": note,
        "trigger": "local_download",
    }
    return _build_zip(meta, "")


def _upload(path: str, content: bytes, message: str) -> int:
    """经 GitHub Contents API 新建文件(时间戳路径唯一,无需 SHA)。返回 HTTP 状态。"""
    url = f"{_GITHUB_API}/repos/{quote(settings.paper_repo, safe='/')}/contents/{quote(path, safe='/')}"
    body = json.dumps({
        "message": message,
        "content": base64.b64encode(content).decode(),
        "branch": settings.paper_repo_branch,
    }).encode()
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Authorization", f"Bearer {settings.paper_repo_token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", _USER_AGENT)
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (固定 GitHub API)
        return resp.status


def _github_get(path: str) -> dict | list:
    url = f"{_GITHUB_API}/repos/{quote(settings.paper_repo, safe='/')}/contents/{quote(path, safe='/')}?ref={quote(settings.paper_repo_branch, safe='')}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {settings.paper_repo_token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", _USER_AGENT)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def upload_history(start: str | None = None, end: str | None = None) -> list[dict]:
    """按 ZIP 文件名中的 UTC 时间过滤上传记录。"""
    if not enabled():
        return []
    try:
        rows = _github_get(f"{settings.log_app_slug}/logs")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        name = row.get("name", "")
        if not name.endswith(".zip") or len(name) < 15:
            continue
        stamp = name[:8]
        if start and stamp < start.replace("-", ""):
            continue
        if end and stamp > end.replace("-", ""):
            continue
        out.append({"name": name, "uploaded_at_utc": f"{name[:4]}-{name[4:6]}-{name[6:8]} {name[9:11]}:{name[11:13]}:{name[13:15]} UTC",
                    "size": row.get("size", 0)})
    return sorted(out, key=lambda x: x["name"], reverse=True)


def download_uploaded(name: str) -> bytes:
    if not enabled() or not re.fullmatch(r"\d{8}-\d{6}_[A-Za-z0-9_-]+\.zip", name):
        raise ValueError("无效的诊断文件名")
    item = _github_get(f"{settings.log_app_slug}/logs/{name}")
    if not isinstance(item, dict) or item.get("encoding") != "base64":
        raise ValueError("诊断文件不可下载")
    return base64.b64decode(item["content"])


def _package_and_upload(meta: dict, tb_text: str) -> str | None:
    slug = settings.log_app_slug
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sig = meta.get("signature", "manual")
    path = f"{slug}/logs/{ts}_{sig}.zip"
    content = _build_zip(meta, tb_text)
    _upload(path, content, f"[{slug}] {meta.get('error_type', 'report')} @ {ts}Z")
    _LOG.info("诊断日志已上传: %s", path)
    return path


def report_exception(exc: BaseException, extra: dict | None = None) -> None:
    """出错时触发(后台上传,带节流去重)。绝不抛出、绝不阻塞主流程。"""
    if not enabled():
        return
    sig = _signature(exc)
    now = time.time()
    with _lock:
        if now - _last_upload.get(sig, 0.0) < settings.error_report_cooldown:
            return
        _last_upload[sig] = now
    tb_text = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
    meta = {
        "app": settings.log_app_slug, "version": APP_VERSION,
        "deploy_mode": settings.deploy_mode,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "error_type": type(exc).__name__, "error": str(exc), "signature": sig,
        **(extra or {}),
    }
    threading.Thread(target=_safe_report, args=(meta, tb_text), daemon=True).start()


def _safe_report(meta: dict, tb_text: str) -> None:
    try:
        _package_and_upload(meta, tb_text)
    except Exception as e:  # noqa: BLE001 上传失败绝不影响主流程
        _LOG.warning("诊断日志上传失败: %s", e)


def report_manual(note: str = "", extra: dict | None = None) -> str | None:
    """手动打包近期日志并上传(同步,超管触发;绕过冷却)。返回上传路径或 None。"""
    if not enabled():
        return None
    meta = {
        "app": settings.log_app_slug, "version": APP_VERSION,
        "deploy_mode": settings.deploy_mode,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "error_type": "manual", "error": note, "signature": "manual",
        **(extra or {}),
    }
    return _package_and_upload(meta, "")
