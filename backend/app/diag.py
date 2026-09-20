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
import threading
import time
import traceback as _tb
import urllib.request
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
    return bool(settings.error_report_enabled and settings.paper_repo_token and settings.paper_repo)


def recent_lines() -> list[str]:
    return list(_ring)


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


def _upload(path: str, content: bytes, message: str) -> int:
    """经 GitHub Contents API 新建文件(时间戳路径唯一,无需 SHA)。返回 HTTP 状态。"""
    url = f"{_GITHUB_API}/repos/{settings.paper_repo}/contents/{path}"
    body = json.dumps({
        "message": message,
        "content": base64.b64encode(content).decode(),
        "branch": settings.paper_repo_branch,
    }).encode()
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Authorization", f"Bearer {settings.paper_repo_token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", f"{settings.log_app_slug}-diag")
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (固定 GitHub API)
        return resp.status


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
