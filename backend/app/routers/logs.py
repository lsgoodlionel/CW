"""操作日志 API:按类型/年月季查询,导出 PDF。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, oplog, oplog_pdf

router = APIRouter(prefix="/api/logs", tags=["logs"])


def _filtered_query(action_type: str | None, year: int | None,
                    month: int | None, quarter: int | None):
    stmt = select(models.OperationLog)
    if action_type:
        stmt = stmt.where(models.OperationLog.action_type == action_type)
    if year:
        start, end = oplog.period_range(year, month, quarter)
        dt_start, dt_end = oplog.to_dt_range(start, end)
        stmt = stmt.where(models.OperationLog.created_at >= dt_start,
                          models.OperationLog.created_at <= dt_end)
    return stmt


def _to_dict(log: models.OperationLog) -> dict:
    return {
        "id": log.id,
        "created_at": log.created_at.isoformat() if log.created_at else "",
        "action_type": log.action_type,
        "action_type_label": oplog.ACTION_TYPES.get(log.action_type, log.action_type),
        "action": log.action,
        "method": log.method,
        "path": log.path,
        "entity_id": log.entity_id,
        "summary": log.summary,
        "status_code": log.status_code,
        "duration_ms": log.duration_ms,
        "ip": log.ip,
    }


@router.get("")
def list_logs(
    action_type: str | None = None,
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = _filtered_query(action_type, year, month, quarter)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(models.OperationLog.created_at.desc(),
                      models.OperationLog.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_to_dict(r) for r in rows],
        "total": total, "page": page, "page_size": page_size,
        "types": oplog.ACTION_TYPES,
    }


@router.get("/export-pdf")
def export_pdf(
    action_type: str | None = None,
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    db: Session = Depends(get_db),
):
    stmt = _filtered_query(action_type, year, month, quarter)
    rows = db.scalars(
        stmt.order_by(models.OperationLog.created_at.desc(),
                      models.OperationLog.id.desc()).limit(5000)
    ).all()
    data = [_to_dict(r) for r in rows]

    label = oplog.period_label(year, month, quarter) if year else "全部时间"
    type_label = oplog.ACTION_TYPES.get(action_type, "全部类型") if action_type else "全部类型"
    title = f"操作日志 - {label} - {type_label}"
    content = oplog_pdf.build_logs_pdf(data, title)

    fname = f"{title}.pdf"
    return StreamingResponse(
        iter([content]), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )
