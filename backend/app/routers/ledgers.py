"""会计账簿 API:按种类/年月季生成与导出 Excel。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .. import ledgers, ledger_excel, reports_cn

router = APIRouter(prefix="/api/ledgers", tags=["ledgers"])


def _period(report_type: str, year: int, month: int | None, quarter: int | None):
    if report_type not in ("month", "quarter", "year"):
        raise HTTPException(status_code=400, detail="report_type 必须是 month/quarter/year")
    if report_type == "month" and not (month and 1 <= month <= 12):
        raise HTTPException(status_code=400, detail="月度账需提供 1-12 的 month")
    if report_type == "quarter" and not (quarter and 1 <= quarter <= 4):
        raise HTTPException(status_code=400, detail="季度账需提供 1-4 的 quarter")
    return reports_cn.build_period(report_type, year, month, quarter)


@router.get("/types")
def ledger_types():
    return ledgers.LEDGER_TYPES


@router.get("")
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
