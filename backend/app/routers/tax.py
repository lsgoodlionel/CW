"""税务管理 API:税务申报记录(国税/自然人)CRUD + 附件 + 应纳税报表生成。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas, attach_svc, tax_report, auth_svc, workflow_svc
from ..auth_mw import current_user
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
def tax_meta(db: Session = Depends(get_db)):
    return {"tax_type": TAX_TYPE_LABEL, "taxpayer_type": TAXPAYER_LABEL, "status": STATUS_LABEL,
            "approval_enabled": workflow_svc.has_active(db, "tax")}


def _tax_can_direct(db: Session, user) -> bool:
    if user is None or getattr(user, "is_super_admin", False):
        return True
    return auth_svc.user_has(user, "tax", "direct")


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


def _validate_filing(payload: schemas.TaxFilingIn) -> None:
    if payload.tax_type not in schemas.TAX_TYPES:
        raise HTTPException(status_code=400, detail="税种无效")
    if payload.taxpayer_type not in schemas.TAXPAYER_TYPES:
        raise HTTPException(status_code=400, detail="纳税人类型无效")
    if payload.status not in schemas.TAX_FILING_STATUSES:
        raise HTTPException(status_code=400, detail="申报状态无效")


@router.post("/filings", response_model=schemas.TaxFilingOut, status_code=201)
def create_filing(payload: schemas.TaxFilingIn, db: Session = Depends(get_db),
                  user=Depends(current_user)):
    _validate_filing(payload)
    f = models.TaxFiling(**payload.model_dump())
    # 审批约束:已配置税务审批流程且无 tax:direct 时,不允许直接置为已申报/已缴纳
    if (f.status in ("filed", "paid") and workflow_svc.has_active(db, "tax")
            and not _tax_can_direct(db, user)):
        f.status = "pending"
    db.add(f)
    db.commit()
    return _load(db, f.id)


@router.get("/filings/{fid}", response_model=schemas.TaxFilingOut)
def get_filing(fid: int, db: Session = Depends(get_db)):
    return _load(db, fid)


@router.put("/filings/{fid}", response_model=schemas.TaxFilingOut)
def update_filing(fid: int, payload: schemas.TaxFilingIn, db: Session = Depends(get_db)):
    f = _load(db, fid)
    _validate_filing(payload)
    for k, v in payload.model_dump().items():
        setattr(f, k, v)
    db.commit()
    return _load(db, fid)


@router.delete("/filings/{fid}", status_code=204)
def delete_filing(fid: int, db: Session = Depends(get_db)):
    db.delete(_load(db, fid))
    db.commit()


@router.post("/filings/{fid}/submit", response_model=schemas.TaxFilingOut)
def submit_filing(fid: int, db: Session = Depends(get_db)):
    """提交税务申报审批:通过后状态自动变为「已申报(filed)」。"""
    f = _load(db, fid)
    if f.workflow_instance_id:
        raise HTTPException(status_code=400, detail="该申报已提交审批")
    definition = workflow_svc.active_definition(db, "tax")
    if definition is None or not definition.steps:
        raise HTTPException(status_code=400, detail="未配置「税务申报」审批流程,请先在审批流程页新建并启用")
    sub = schemas.InstanceSubmit(
        definition_id=definition.id, biz_type="tax", biz_id=f.id,
        title=f"{TAX_TYPE_LABEL.get(f.tax_type, f.tax_type)} {f.period} 应纳{f.tax_amount}元")
    inst = workflow_svc.create_instance(db, sub, definition)
    f.workflow_instance_id = inst.id
    f.status = "pending"
    db.commit()
    return _load(db, fid)


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
                     for ln, lb, amt, lv in rows],
            "schedules": {"A201020": _a201020_rows(db, year),
                          "preferences": _pref_rows(db, year)},
            "checks": tax_report.quarterly_report_checks(db, year, quarter)}


def _a201020_rows(db: Session, year: int) -> list[dict]:
    return [{"line_no": ln, "item": it, "orig": float(ov), "book": float(bk),
             "normal": float(nm), "accel": float(ac), "reduce": float(rd),
             "benefit": float(bn), "level": lv, "editable": ed}
            for ln, it, ov, bk, nm, ac, rd, bn, lv, ed in tax_report.compute_a201020(db, year)]


def _pref_rows(db: Session, year: int) -> list[dict]:
    return [{"category": cat, "category_label": cl, "code": code, "name": name,
             "amount": float(amt), "editable": ed}
            for cat, cl, code, name, amt, ed in tax_report.compute_preferences(db, year)]


@router.get("/preference-options")
def preference_options():
    """税收优惠事项下拉选项(免税/减计/所得减免/减免所得税)。"""
    return {"options": tax_report.preference_options()}


@router.get("/preferences")
def list_preferences(year: int = Query(...), db: Session = Depends(get_db)):
    """税收优惠事项录入明细(按码表固定行,含金额)。"""
    return {"year": year, "rows": _pref_rows(db, year)}


@router.put("/preferences")
def save_preferences(payload: schemas.TaxPreferenceSave, db: Session = Depends(get_db)):
    """按年保存税收优惠事项金额(整表覆盖)。免税/减计→行22,所得减免→行25/季报23,减免所得税→行31/季报28。"""
    valid = {code for _cat, code, _name in tax_report._PREF_OPTIONS}
    db.execute(
        models.TaxPreference.__table__.delete().where(
            models.TaxPreference.report_year == payload.report_year))
    for it in payload.items:
        if it.code not in valid or not it.amount:
            continue
        db.add(models.TaxPreference(
            report_year=payload.report_year, code=it.code, amount=it.amount))
    db.commit()
    return {"year": payload.report_year, "rows": _pref_rows(db, payload.report_year)}


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


@router.get("/report/vat-small")
def vat_small(year: int = Query(...), quarter: int = Query(..., ge=1, le=4),
              rate: float | None = Query(None), half_surtax: bool = Query(True),
              db: Session = Depends(get_db)):
    """增值税及附加税费申报表(小规模纳税人适用),导出 Excel。"""
    content = tax_report.build_vat_small_xlsx(db, year, quarter, rate, half_surtax)
    fname = f"增值税及附加税费申报表-{year}年第{quarter}季度.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


@router.get("/report/vat-small/preview")
def vat_small_preview(year: int = Query(...), quarter: int = Query(..., ge=1, le=4),
                      rate: float | None = Query(None), half_surtax: bool = Query(True),
                      db: Session = Depends(get_db)):
    """小规模增值税及附加申报表结构化预览。"""
    d = tax_report.compute_vat_small(db, year, quarter, rate, half_surtax)
    return {"year": year, "quarter": quarter, "free": d["free"], "rate": float(d["rate"]),
            "rows": [{"item": it, "amount": float(am), "note": nt} for it, am, nt in d["rows"]]}


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
    a105000 = _a105_rows(db, year)
    a106000 = _a106_rows(db, year)
    a105080 = _a105080_rows(db, year)
    a107012 = _a107_rows(db, year)
    return {"year": year, "rows": main,
            "schedules": {"A101010": a101010, "A102010": a102010,
                          "A104000": a104000, "A105000": a105000,
                          "A106000": a106000, "A105080": a105080, "A107012": a107012,
                          "A105050": _a105050_rows(db, year), "A105060": _a105060_rows(db, year),
                          "preferences": _pref_rows(db, year)},
            "checks": tax_report.annual_report_checks(db, year)}


def _a105050_rows(db: Session, year: int) -> list[dict]:
    return [{"line_no": ln, "item": it, "book": float(bk), "actual": float(ac),
             "prev": float(pv), "tax": float(tx), "adjust": float(aj), "carry": float(cy),
             "level": lv, "editable": ed}
            for ln, it, bk, ac, pv, tx, aj, cy, lv, ed in tax_report.compute_a105050(db, year)]


def _a105060_rows(db: Session, year: int) -> list[dict]:
    return [{"line_no": ln, "item": it, "amount": float(am), "editable": ed}
            for ln, it, am, ed in tax_report.compute_a105060(db, year)]


def _a107_rows(db: Session, year: int) -> list[dict]:
    return [{"line_no": ln, "item": it, "amount": float(am), "level": lv, "editable": ed}
            for ln, it, am, lv, ed in tax_report.compute_a107012(db, year)]


def _a106_rows(db: Session, year: int) -> list[dict]:
    return [{"line_no": ln, "item": it, "occur_year": oy, "loss": float(ls),
             "pending": float(pd), "offset": float(of), "carry": float(cy), "editable": ed}
            for ln, it, oy, ls, pd, of, cy, ed in tax_report.compute_a106000(db, year)]


def _a105080_rows(db: Session, year: int) -> list[dict]:
    return [{"line_no": ln, "item": it, "orig": float(ov), "book_dep": float(bd),
             "tax_basis": float(tb), "tax_dep": float(td), "adjust": float(aj),
             "level": lv, "editable": ed}
            for ln, it, ov, bd, tb, td, aj, lv, ed in tax_report.compute_a105080(db, year)]


def _a105_rows(db: Session, year: int) -> list[dict]:
    return [{"line_no": ln, "label": lb, "book": float(bk), "tax": float(tx),
             "add": float(ad), "reduce": float(rd), "level": lv, "editable": ed}
            for ln, lb, bk, tx, ad, rd, lv, ed in tax_report.compute_a105000(db, year)]


@router.get("/adjustments")
def list_adjustments(year: int = Query(...), db: Session = Depends(get_db)):
    """A105000 纳税调整明细(含用户录入值与自动汇总的小计/合计)。"""
    return {"year": year, "rows": _a105_rows(db, year)}


@router.put("/adjustments")
def save_adjustments(payload: schemas.TaxAdjustmentSave, db: Session = Depends(get_db)):
    """按年保存纳税调整明细录入(整表覆盖:先删该年记录再写入非零项)。"""
    editable = {ln for ln, _i, _l, kind in tax_report._A105_ROWS if kind in ("detail", "memo")}
    db.execute(
        models.TaxAdjustment.__table__.delete().where(
            models.TaxAdjustment.year == payload.year))
    for it in payload.items:
        if it.line_no not in editable:
            continue
        if not (it.book_amount or it.tax_amount or it.add_amount or it.reduce_amount or it.note):
            continue
        db.add(models.TaxAdjustment(
            year=payload.year, line_no=it.line_no, book_amount=it.book_amount,
            tax_amount=it.tax_amount, add_amount=it.add_amount,
            reduce_amount=it.reduce_amount, note=it.note))
    db.commit()
    return {"year": payload.year, "rows": _a105_rows(db, payload.year)}


@router.get("/losses")
def list_losses(year: int = Query(...), db: Session = Depends(get_db)):
    """A106000 弥补亏损明细(含录入值与自动汇总的合计)。"""
    return {"year": year, "rows": _a106_rows(db, year)}


@router.put("/losses")
def save_losses(payload: schemas.TaxLossSave, db: Session = Depends(get_db)):
    """按年保存弥补亏损明细录入(行1..11;整表覆盖)。"""
    valid = {ln for ln, _it in tax_report._A106_ITEMS}
    db.execute(
        models.TaxLossCarryover.__table__.delete().where(
            models.TaxLossCarryover.report_year == payload.report_year))
    for it in payload.items:
        if it.line_no not in valid:
            continue
        if not (it.loss_amount or it.pending_amount or it.offset_amount):
            continue
        db.add(models.TaxLossCarryover(
            report_year=payload.report_year, line_no=it.line_no,
            loss_amount=it.loss_amount, pending_amount=it.pending_amount,
            offset_amount=it.offset_amount))
    db.commit()
    return {"year": payload.report_year, "rows": _a106_rows(db, payload.report_year)}


@router.get("/depreciations")
def list_depreciations(year: int = Query(...), db: Session = Depends(get_db)):
    """A105080 资产折旧摊销明细(含录入值与自动汇总)。"""
    return {"year": year, "rows": _a105080_rows(db, year)}


@router.put("/depreciations")
def save_depreciations(payload: schemas.TaxDepreciationSave, db: Session = Depends(get_db)):
    """按年保存资产折旧摊销明细录入(明细行;整表覆盖)。"""
    editable = {ln for ln, _i, _l, kind in tax_report._A105080_ROWS if kind == "detail"}
    db.execute(
        models.TaxAssetDepreciation.__table__.delete().where(
            models.TaxAssetDepreciation.report_year == payload.report_year))
    for it in payload.items:
        if it.line_no not in editable:
            continue
        if not (it.orig_value or it.book_dep or it.tax_basis or it.tax_dep):
            continue
        db.add(models.TaxAssetDepreciation(
            report_year=payload.report_year, line_no=it.line_no,
            orig_value=it.orig_value, book_dep=it.book_dep,
            tax_basis=it.tax_basis, tax_dep=it.tax_dep))
    db.commit()
    return {"year": payload.report_year, "rows": _a105080_rows(db, payload.report_year)}


@router.get("/rd-deductions")
def list_rd(year: int = Query(...), db: Session = Depends(get_db)):
    """A107012 研发费用加计扣除明细(含录入值与自动汇总/加计扣除额)。"""
    return {"year": year, "rows": _a107_rows(db, year)}


@router.put("/rd-deductions")
def save_rd(payload: schemas.TaxRdSave, db: Session = Depends(get_db)):
    """按年保存研发费用加计扣除录入(明细行与加计比例;整表覆盖)。"""
    editable = {ln for ln, _i, _l, kind in tax_report._A107_ROWS if kind in tax_report._RD_INPUT}
    db.execute(
        models.TaxRdDeduction.__table__.delete().where(
            models.TaxRdDeduction.report_year == payload.report_year))
    for it in payload.items:
        if it.line_no not in editable or not it.amount:
            continue
        db.add(models.TaxRdDeduction(
            report_year=payload.report_year, line_no=it.line_no, amount=it.amount))
    db.commit()
    return {"year": payload.report_year, "rows": _a107_rows(db, payload.report_year)}


@router.get("/accel-deprs")
def list_accel(year: int = Query(...), db: Session = Depends(get_db)):
    """A201020 资产加速折旧优惠明细(含录入值与自动汇总)。"""
    return {"year": year, "rows": _a201020_rows(db, year)}


@router.put("/accel-deprs")
def save_accel(payload: schemas.TaxAccelSave, db: Session = Depends(get_db)):
    """按年保存资产加速折旧优惠录入(明细行;整表覆盖)。"""
    editable = {ln for ln, _i, _l, kind in tax_report._A201020_ROWS if kind == "detail"}
    db.execute(
        models.TaxAccelDepr.__table__.delete().where(
            models.TaxAccelDepr.year == payload.year))
    for it in payload.items:
        if it.line_no not in editable:
            continue
        if not (it.orig_value or it.book_dep or it.tax_normal or it.accel_dep or it.reduce_amount):
            continue
        db.add(models.TaxAccelDepr(
            year=payload.year, line_no=it.line_no, orig_value=it.orig_value,
            book_dep=it.book_dep, tax_normal=it.tax_normal, accel_dep=it.accel_dep,
            reduce_amount=it.reduce_amount))
    db.commit()
    return {"year": payload.year, "rows": _a201020_rows(db, payload.year)}


@router.get("/salary-adjusts")
def list_salary(year: int = Query(...), db: Session = Depends(get_db)):
    """A105050 职工薪酬明细。"""
    return {"year": year, "rows": _a105050_rows(db, year)}


@router.put("/salary-adjusts")
def save_salary(payload: schemas.TaxSalarySave, db: Session = Depends(get_db)):
    """按年保存职工薪酬录入(明细行;整表覆盖)。"""
    editable = {ln for ln, _i, _l, kind in tax_report._A105050_ROWS if kind in ("detail", "memo")}
    db.execute(models.TaxSalaryAdjust.__table__.delete().where(
        models.TaxSalaryAdjust.report_year == payload.report_year))
    for it in payload.items:
        if it.line_no not in editable:
            continue
        if not (it.book_amount or it.actual_amount or it.prev_carry or it.tax_amount):
            continue
        db.add(models.TaxSalaryAdjust(
            report_year=payload.report_year, line_no=it.line_no, book_amount=it.book_amount,
            actual_amount=it.actual_amount, prev_carry=it.prev_carry, tax_amount=it.tax_amount))
    db.commit()
    return {"year": payload.report_year, "rows": _a105050_rows(db, payload.report_year)}


@router.get("/ad-medias")
def list_ad(year: int = Query(...), db: Session = Depends(get_db)):
    """A105060 广宣费明细。"""
    return {"year": year, "rows": _a105060_rows(db, year)}


@router.put("/ad-medias")
def save_ad(payload: schemas.TaxAdMediaSave, db: Session = Depends(get_db)):
    """按年保存广宣费录入(行1本年支出、行2扣除率、行4以前结转;整表覆盖)。"""
    editable = {ln for ln, _i, kind in tax_report._A105060_ROWS if kind in ("detail", "ratio")}
    db.execute(models.TaxAdMedia.__table__.delete().where(
        models.TaxAdMedia.report_year == payload.report_year))
    for it in payload.items:
        if it.line_no not in editable or not it.amount:
            continue
        db.add(models.TaxAdMedia(
            report_year=payload.report_year, line_no=it.line_no, amount=it.amount))
    db.commit()
    return {"year": payload.report_year, "rows": _a105060_rows(db, payload.report_year)}
