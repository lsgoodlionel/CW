"""记账凭证 API:CRUD + 借贷平衡校验。"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/vouchers", tags=["vouchers"])


def _next_voucher_no(db: Session, voucher_date: date) -> str:
    """生成凭证号:记-YYYYMM-NNN。"""
    prefix = f"记-{voucher_date:%Y%m}-"
    count = db.scalar(
        select(func.count(models.Voucher.id)).where(
            func.extract("year", models.Voucher.voucher_date) == voucher_date.year,
            func.extract("month", models.Voucher.voucher_date) == voucher_date.month,
        )
    ) or 0
    return f"{prefix}{count + 1:03d}"


def _to_detail(voucher: models.Voucher) -> schemas.VoucherDetail:
    entries = []
    for e in voucher.entries:
        item = schemas.EntryOut.model_validate(e)
        item.account_code = e.account.code if e.account else ""
        item.account_name = e.account.name if e.account else ""
        entries.append(item)
    return schemas.VoucherDetail(
        id=voucher.id,
        voucher_no=voucher.voucher_no,
        voucher_date=voucher.voucher_date,
        note=voucher.note,
        total_debit=voucher.total_debit,
        total_credit=voucher.total_credit,
        status=voucher.status,
        created_at=voucher.created_at,
        entries=entries,
        attachments=[schemas.AttachmentOut.model_validate(a) for a in voucher.attachments],
    )


def _validate_accounts(db: Session, payload: schemas.VoucherCreate) -> None:
    account_ids = {e.account_id for e in payload.entries}
    found = set(db.scalars(
        select(models.Account.id).where(models.Account.id.in_(account_ids))
    ).all())
    missing = account_ids - found
    if missing:
        raise HTTPException(status_code=400, detail=f"科目不存在: {sorted(missing)}")


@router.get("", response_model=schemas.VoucherPage)
def list_vouchers(
    start: date | None = None,
    end: date | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(models.Voucher)
    if start:
        stmt = stmt.where(models.Voucher.voucher_date >= start)
    if end:
        stmt = stmt.where(models.Voucher.voucher_date <= end)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(
            models.Voucher.voucher_no.ilike(like),
            models.Voucher.note.ilike(like),
        ))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = (
        stmt.order_by(models.Voucher.voucher_date.desc(), models.Voucher.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
        .options(selectinload(models.Voucher.entries),
                 selectinload(models.Voucher.attachments))
    )
    vouchers = db.scalars(stmt).all()
    items = []
    for v in vouchers:
        item = schemas.VoucherListItem.model_validate(v)
        item.entry_count = len(v.entries)
        item.attachment_count = len(v.attachments)
        items.append(item)
    return schemas.VoucherPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/{voucher_id}", response_model=schemas.VoucherDetail)
def get_voucher(voucher_id: int, db: Session = Depends(get_db)):
    voucher = db.scalar(
        select(models.Voucher).where(models.Voucher.id == voucher_id).options(
            selectinload(models.Voucher.entries).selectinload(models.VoucherEntry.account),
            selectinload(models.Voucher.attachments),
        )
    )
    if voucher is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    return _to_detail(voucher)


@router.post("", response_model=schemas.VoucherDetail, status_code=201)
def create_voucher(payload: schemas.VoucherCreate, db: Session = Depends(get_db)):
    _validate_accounts(db, payload)
    total_debit = sum((e.debit for e in payload.entries), Decimal("0"))
    total_credit = sum((e.credit for e in payload.entries), Decimal("0"))
    voucher = models.Voucher(
        voucher_no=payload.voucher_no or _next_voucher_no(db, payload.voucher_date),
        voucher_date=payload.voucher_date,
        note=payload.note,
        status=payload.status,
        total_debit=total_debit,
        total_credit=total_credit,
    )
    for idx, e in enumerate(payload.entries, start=1):
        voucher.entries.append(models.VoucherEntry(
            line_no=idx, summary=e.summary, account_id=e.account_id,
            sub_account=e.sub_account, debit=e.debit, credit=e.credit,
        ))
    db.add(voucher)
    db.commit()
    db.refresh(voucher)
    return get_voucher(voucher.id, db)


@router.put("/{voucher_id}", response_model=schemas.VoucherDetail)
def update_voucher(
    voucher_id: int, payload: schemas.VoucherCreate, db: Session = Depends(get_db)
):
    voucher = db.get(models.Voucher, voucher_id)
    if voucher is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    _validate_accounts(db, payload)

    voucher.voucher_no = payload.voucher_no or voucher.voucher_no
    voucher.voucher_date = payload.voucher_date
    voucher.note = payload.note
    voucher.status = payload.status
    voucher.total_debit = sum((e.debit for e in payload.entries), Decimal("0"))
    voucher.total_credit = sum((e.credit for e in payload.entries), Decimal("0"))

    # 整体替换分录(附件保留)
    voucher.entries.clear()
    for idx, e in enumerate(payload.entries, start=1):
        voucher.entries.append(models.VoucherEntry(
            line_no=idx, summary=e.summary, account_id=e.account_id,
            sub_account=e.sub_account, debit=e.debit, credit=e.credit,
        ))
    db.commit()
    return get_voucher(voucher_id, db)


@router.delete("/{voucher_id}", status_code=204)
def delete_voucher(voucher_id: int, db: Session = Depends(get_db)):
    voucher = db.get(models.Voucher, voucher_id)
    if voucher is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    db.delete(voucher)
    db.commit()
