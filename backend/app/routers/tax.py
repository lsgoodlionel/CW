"""税务管理 API:税务申报记录(国税/自然人)CRUD + 附件 + 应纳税报表生成。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas, attach_svc, tax_report
from .attachments import read_upload

router = APIRouter(prefix="/api/tax", tags=["tax"])

TAX_TYPE_LABEL = {
    "stamp": "印花税", "vat": "增值税", "vat_surtax": "增值税及附加",
    "cit": "企业所得税", "iit": "个人所得税", "other": "其他",
}
TAXPAYER_LABEL = {"enterprise": "国税(企业)", "individual": "自然人"}
STATUS_LABEL = {"pending": "待申报", "filed": "已申报", "paid": "已缴纳"}


def _load(db: Session, fid: int) -> models.TaxFiling:
    f = db.scalar(select(models.TaxFiling).where(models.TaxFiling.id == fid)
                  .options(selectinload(models.TaxFiling.attachments)))
    if f is None:
        raise HTTPException(status_code=404, detail="税务申报记录不存在")
    return f


@router.get("/meta")
def tax_meta():
    return {"tax_type": TAX_TYPE_LABEL, "taxpayer_type": TAXPAYER_LABEL, "status": STATUS_LABEL}


@router.get("/filings", response_model=list[schemas.TaxFilingOut])
def list_filings(tax_type: str | None = None, taxpayer_type: str | None = None,
                 status: str | None = None, db: Session = Depends(get_db)):
    stmt = (select(models.TaxFiling).order_by(models.TaxFiling.id.desc())
            .options(selectinload(models.TaxFiling.attachments)))
    if tax_type:
        stmt = stmt.where(models.TaxFiling.tax_type == tax_type)
    if taxpayer_type:
        stmt = stmt.where(models.TaxFiling.taxpayer_type == taxpayer_type)
    if status:
        stmt = stmt.where(models.TaxFiling.status == status)
    return list(db.scalars(stmt).all())


@router.post("/filings", response_model=schemas.TaxFilingOut, status_code=201)
def create_filing(payload: schemas.TaxFilingIn, db: Session = Depends(get_db)):
    if payload.tax_type not in schemas.TAX_TYPES:
        raise HTTPException(status_code=400, detail="税种无效")
    if payload.taxpayer_type not in schemas.TAXPAYER_TYPES:
        raise HTTPException(status_code=400, detail="纳税人类型无效")
    f = models.TaxFiling(**payload.model_dump())
    db.add(f)
    db.commit()
    return _load(db, f.id)


@router.get("/filings/{fid}", response_model=schemas.TaxFilingOut)
def get_filing(fid: int, db: Session = Depends(get_db)):
    return _load(db, fid)


@router.put("/filings/{fid}", response_model=schemas.TaxFilingOut)
def update_filing(fid: int, payload: schemas.TaxFilingIn, db: Session = Depends(get_db)):
    f = _load(db, fid)
    for k, v in payload.model_dump().items():
        setattr(f, k, v)
    db.commit()
    return _load(db, fid)


@router.delete("/filings/{fid}", status_code=204)
def delete_filing(fid: int, db: Session = Depends(get_db)):
    db.delete(_load(db, fid))
    db.commit()


@router.post("/filings/{fid}/attachments", response_model=schemas.AttachmentOut, status_code=201)
async def upload_attachment(fid: int, kind: str = Form("tax_payment"),
                            file: UploadFile = File(...), db: Session = Depends(get_db)):
    if db.get(models.TaxFiling, fid) is None:
        raise HTTPException(status_code=404, detail="税务申报记录不存在")
    content = await read_upload(file, kind)
    stored = attach_svc.store_bytes(f"tax_{fid}", file.filename or "", content)
    att = attach_svc.make_attachment(
        kind=kind, original_name=file.filename or stored.name, stored_path=stored,
        mime_type=file.content_type or "", size_bytes=len(content), tax_filing_id=fid)
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.get("/report/cit-quarterly")
def cit_quarterly(year: int = Query(...), quarter: int = Query(..., ge=1, le=4),
                  db: Session = Depends(get_db)):
    """企业所得税月(季)度预缴纳税申报表(A类)A200000,按账套数据自动计算并导出 Excel。"""
    content = tax_report.build_cit_quarterly_xlsx(db, year, quarter)
    fname = f"企业所得税季度预缴申报表-{year}年第{quarter}季度.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


@router.get("/report/cit-quarterly/preview")
def cit_quarterly_preview(year: int = Query(...), quarter: int = Query(..., ge=1, le=4),
                          db: Session = Depends(get_db)):
    """季报主表行次的结构化预览(供页面展示,不下载)。"""
    rows = tax_report.compute_rows(db, year, quarter)
    return {"year": year, "quarter": quarter,
            "rows": [{"line_no": ln, "label": lb, "amount": float(amt), "level": lv}
                     for ln, lb, amt, lv in rows]}


@router.get("/report/cit-annual")
def cit_annual(year: int = Query(...), db: Session = Depends(get_db)):
    """企业所得税年度纳税申报表(A类)A100000 主表,按账套年度数据自动计算并导出 Excel。"""
    content = tax_report.build_cit_annual_xlsx(db, year)
    fname = f"企业所得税年度纳税申报表-{year}年度.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


@router.get("/report/cit-annual/preview")
def cit_annual_preview(year: int = Query(...), db: Session = Depends(get_db)):
    """年报主表 + 附表行次的结构化预览(供页面展示,不下载)。"""
    main = [{"line_no": ln, "category": cat, "label": lb, "amount": float(amt), "level": lv}
            for ln, cat, lb, amt, lv in tax_report.compute_annual_rows(db, year)]
    a101010 = [{"line_no": ln, "label": lb, "amount": float(amt), "level": lv}
               for ln, lb, amt, lv in tax_report.compute_a101010(db, year)]
    a102010 = [{"line_no": ln, "label": lb, "amount": float(amt), "level": lv}
               for ln, lb, amt, lv in tax_report.compute_a102010(db, year)]
    a104000 = [{"line_no": ln, "label": lb, "sell": float(s), "admin": float(a), "fin": float(f)}
               for ln, lb, s, a, f in tax_report.compute_a104000(db, year)]
    return {"year": year, "rows": main,
            "schedules": {"A101010": a101010, "A102010": a102010, "A104000": a104000}}
