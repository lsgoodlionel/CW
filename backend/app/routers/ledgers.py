"""会计账簿 API:按种类/年月季生成与导出 Excel。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..database import get_db
from .. import ledgers, ledger_excel, ledger_archive, reports_cn, auth_svc
from ..auth_mw import current_user
from ..schemas_read import LedgerOut, LedgerTypesOut

router = APIRouter(prefix="/api/ledgers", tags=["ledgers"])


class ArchiveRequest(BaseModel):
    ledger_type: str = "all"
    report_type: str = "year"
    year: int
    month: int | None = None
    quarter: int | None = None
    account_code: str | None = None
    mode: str = "subject"
    folder_names: dict[str, str] = Field(default_factory=dict)


def _archive_params(payload: ArchiveRequest):
    if payload.ledger_type != "all" and payload.ledger_type not in ledgers.LEDGER_TYPES:
        raise HTTPException(status_code=400, detail="未知账簿种类")
    if payload.mode not in ("subject", "date"):
        raise HTTPException(status_code=400, detail="归档方式须为费用科目或日期")
    if len(payload.folder_names) > 200 or any(len(v) > 160 for v in payload.folder_names.values()):
        raise HTTPException(status_code=400, detail="目录设置过长")
    return _period(payload.report_type, payload.year, payload.month, payload.quarter)


def _guard_archive(user, items):
    if user is None or user.is_super_admin:
        return
    if not auth_svc.user_has(user, "voucher", "view"):
        raise HTTPException(status_code=403, detail="需要记账凭证查看权限")
    if any(i.get("source") == "关联合同" for i in items) and not auth_svc.user_has(user, "contract", "view"):
        raise HTTPException(status_code=403, detail="归档包含合同附件，需要合同查看权限")


def _period(report_type: str, year: int, month: int | None, quarter: int | None):
    if report_type not in ("month", "quarter", "year"):
        raise HTTPException(status_code=400, detail="report_type 必须是 month/quarter/year")
    if report_type == "month" and not (month and 1 <= month <= 12):
        raise HTTPException(status_code=400, detail="月度账需提供 1-12 的 month")
    if report_type == "quarter" and not (quarter and 1 <= quarter <= 4):
        raise HTTPException(status_code=400, detail="季度账需提供 1-4 的 quarter")
    return reports_cn.build_period(report_type, year, month, quarter)


@router.get("/types", responses={200: {"model": LedgerTypesOut}})
def ledger_types():
    return ledgers.LEDGER_TYPES


@router.get("", responses={200: {"model": LedgerOut}})
def get_ledger(
    ledger_type: str = Query("general"),
    report_type: str = Query("month"),
    year: int = Query(...),
    month: int | None = None,
    quarter: int | None = None,
    account_code: str | None = None,
    db: Session = Depends(get_db),
):
    if ledger_type not in ledgers.LEDGER_TYPES:
        raise HTTPException(status_code=400, detail="未知账簿种类")
    period = _period(report_type, year, month, quarter)
    return ledgers.attach_cells(ledgers.build_ledger(db, ledger_type, period, account_code))


@router.get("/export-excel")
def export_excel(
    ledger_type: str = Query("general"),
    report_type: str = Query("month"),
    year: int = Query(...),
    month: int | None = None,
    quarter: int | None = None,
    account_code: str | None = None,
    db: Session = Depends(get_db),
):
    if ledger_type != "all" and ledger_type not in ledgers.LEDGER_TYPES:
        raise HTTPException(status_code=400, detail="未知账簿种类")
    period = _period(report_type, year, month, quarter)
    content = ledger_excel.build_ledger_workbook(db, ledger_type, period, account_code)
    tname = "全套账簿" if ledger_type == "all" else ledgers.LEDGER_TYPES[ledger_type]
    fname = f"{tname}-{period.label}.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


@router.post("/archive-preview")
def archive_preview(payload: ArchiveRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    period = _archive_params(payload)
    vouchers, items = ledger_archive.make_manifest(
        db, period, payload.mode, payload.account_code, payload.folder_names)
    _guard_archive(user, items)
    public = [{k: v for k, v in item.items() if k != "stored_path"} for item in items]
    return {"period": period.label, "voucher_count": len(vouchers),
            "attachment_count": sum(i["type"] == "附件" for i in items),
            "items": public}


@router.post("/archive-export")
def archive_export(payload: ArchiveRequest, db: Session = Depends(get_db), user=Depends(current_user)):
    period = _archive_params(payload)
    _, items = ledger_archive.make_manifest(db, period, payload.mode, payload.account_code,
                                             payload.folder_names)
    _guard_archive(user, items)
    try:
        content = ledger_archive.build_archive(db, period, payload.ledger_type, payload.mode,
                                               payload.account_code, payload.folder_names)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    fname = f"账簿凭证附件-{period.label}.zip"
    return StreamingResponse(iter([content]), media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"})
