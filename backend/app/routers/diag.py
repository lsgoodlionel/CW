"""运行诊断 API(仅平台超级管理员):查看诊断状态/近期日志、手动打包上传。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import models, diag
from ..config import settings

router = APIRouter(prefix="/api/diag", tags=["diag"])


def require_super_admin(request: Request) -> models.User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    if not user.is_super_admin:
        raise HTTPException(status_code=403, detail="仅平台超级管理员可访问")
    return user


class ManualReportIn(BaseModel):
    note: str = ""


@router.get("/status")
def diag_status(_: models.User = Depends(require_super_admin)):
    """诊断配置与状态(不含 token)。"""
    return {
        "enabled": diag.enabled(),
        "repo": settings.paper_repo,
        "branch": settings.paper_repo_branch,
        "slug": settings.log_app_slug,
        "cooldown": settings.error_report_cooldown,
        "token_configured": bool(settings.paper_repo_token),
        "buffered_lines": len(diag.recent_lines()),
    }


@router.get("/recent")
def diag_recent(limit: int = 200, _: models.User = Depends(require_super_admin)):
    """返回最近日志行(用于界面快速查看)。"""
    lines = diag.recent_lines()
    return {"lines": lines[-max(1, min(limit, 800)):]}


@router.post("/report")
def diag_report(payload: ManualReportIn, _: models.User = Depends(require_super_admin)):
    """手动打包近期日志并上传到 paper 仓库。"""
    if not diag.enabled():
        raise HTTPException(status_code=400, detail="诊断上传未启用(未配置 PAPER_REPO_TOKEN)")
    try:
        path = diag.report_manual(payload.note, extra={"trigger": "manual"})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"上传失败:{e}")
    if path is None:
        raise HTTPException(status_code=400, detail="诊断上传未启用")
    return {"success": True, "path": path}
