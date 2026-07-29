"""记账凭证 API:CRUD + 借贷平衡校验。"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas, subaccounts_svc

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


def _linked_vouchers(db: Session, voucher_id: int) -> list[schemas.LinkedVoucher]:
    """收集与该凭证相关的凭证(双向)。"""
    links = db.scalars(
        select(models.VoucherLink).where(or_(
            models.VoucherLink.source_id == voucher_id,
            models.VoucherLink.target_id == voucher_id,
        ))
    ).all()
    out: list[schemas.LinkedVoucher] = []
    for link in links:
        outgoing = link.source_id == voucher_id
        other_id = link.target_id if outgoing else link.source_id
        other = db.get(models.Voucher, other_id)
        if other is None:
            continue
        out.append(schemas.LinkedVoucher(
            link_id=link.id, relation_type=link.relation_type, note=link.note,
            direction="out" if outgoing else "in",
            voucher_id=other.id, voucher_no=other.voucher_no,
            voucher_date=other.voucher_date, voucher_note=other.note,
            total_debit=other.total_debit,
        ))
    return out


def _to_detail(voucher: models.Voucher, db: Session) -> schemas.VoucherDetail:
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
        customer_id=voucher.customer_id,
        customer=schemas.CustomerBrief.model_validate(voucher.customer)
        if voucher.customer else None,
        total_debit=voucher.total_debit,
        total_credit=voucher.total_credit,
        status=voucher.status,
        created_at=voucher.created_at,
        entries=entries,
        attachments=[schemas.AttachmentOut.model_validate(a) for a in voucher.attachments],
        links=_linked_vouchers(db, voucher.id),
    )


def _validate_customer(db: Session, customer_id: int | None) -> None:
    if customer_id is not None and db.get(models.Customer, customer_id) is None:
        raise HTTPException(status_code=400, detail="客户不存在")


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
                 selectinload(models.Voucher.attachments),
                 selectinload(models.Voucher.customer))
    )
    vouchers = db.scalars(stmt).all()
    link_counts = _link_counts(db, [v.id for v in vouchers])
    items = []
    for v in vouchers:
        item = schemas.VoucherListItem.model_validate(v)
        item.entry_count = len(v.entries)
        item.attachment_count = len(v.attachments)
        item.customer_name = v.customer.name if v.customer else ""
        item.link_count = link_counts.get(v.id, 0)
        items.append(item)
    return schemas.VoucherPage(items=items, total=total, page=page, page_size=page_size)


def _link_counts(db: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    counts: dict[int, int] = {}
    rows = db.execute(
        select(models.VoucherLink.source_id, models.VoucherLink.target_id)
        .where(or_(models.VoucherLink.source_id.in_(ids),
                   models.VoucherLink.target_id.in_(ids)))
    ).all()
    idset = set(ids)
    for src, tgt in rows:
        if src in idset:
            counts[src] = counts.get(src, 0) + 1
        if tgt in idset:
            counts[tgt] = counts.get(tgt, 0) + 1
    return counts


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
    return _to_detail(voucher, db)


@router.post("", response_model=schemas.VoucherDetail, status_code=201)
def create_voucher(payload: schemas.VoucherCreate, db: Session = Depends(get_db)):
    _validate_accounts(db, payload)
    _validate_customer(db, payload.customer_id)
    total_debit = sum((e.debit for e in payload.entries), Decimal("0"))
    total_credit = sum((e.credit for e in payload.entries), Decimal("0"))
    voucher = models.Voucher(
        voucher_no=payload.voucher_no or _next_voucher_no(db, payload.voucher_date),
        voucher_date=payload.voucher_date,
        note=payload.note,
        customer_id=payload.customer_id,
        status=payload.status,
        total_debit=total_debit,
        total_credit=total_credit,
    )
    _build_entries(db, voucher, payload)
    db.add(voucher)
    db.commit()
    db.refresh(voucher)
    return get_voucher(voucher.id, db)


def _build_entries(db: Session, voucher: models.Voucher, payload: schemas.VoucherCreate):
    """构建分录;二级明细科目按(科目,名称)查找或自动新建(编号延续)。"""
    for idx, e in enumerate(payload.entries, start=1):
        sub = subaccounts_svc.get_or_create(db, e.account_id, e.sub_account)
        voucher.entries.append(models.VoucherEntry(
            line_no=idx, summary=e.summary, account_id=e.account_id,
            sub_account=sub.name if sub else "",
            sub_account_id=sub.id if sub else None,
            debit=e.debit, credit=e.credit,
        ))


@router.put("/{voucher_id}", response_model=schemas.VoucherDetail)
def update_voucher(
    voucher_id: int, payload: schemas.VoucherCreate, db: Session = Depends(get_db)
):
    voucher = db.get(models.Voucher, voucher_id)
    if voucher is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    _validate_accounts(db, payload)
    _validate_customer(db, payload.customer_id)

    voucher.voucher_no = payload.voucher_no or voucher.voucher_no
    voucher.voucher_date = payload.voucher_date
    voucher.note = payload.note
    voucher.customer_id = payload.customer_id
    voucher.status = payload.status
    voucher.total_debit = sum((e.debit for e in payload.entries), Decimal("0"))
    voucher.total_credit = sum((e.credit for e in payload.entries), Decimal("0"))

    # 整体替换分录(附件保留)
    voucher.entries.clear()
    _build_entries(db, voucher, payload)
    db.commit()
    return get_voucher(voucher_id, db)


@router.delete("/{voucher_id}", status_code=204)
def delete_voucher(voucher_id: int, db: Session = Depends(get_db)):
    voucher = db.get(models.Voucher, voucher_id)
    if voucher is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    db.delete(voucher)
    db.commit()


@router.post("/{voucher_id}/links", response_model=schemas.VoucherDetail, status_code=201)
def add_link(
    voucher_id: int, payload: schemas.VoucherLinkCreate, db: Session = Depends(get_db)
):
    """为凭证添加关联(预收款/挂账/核销/应收款等)。"""
    if db.get(models.Voucher, voucher_id) is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if payload.target_id == voucher_id:
        raise HTTPException(status_code=400, detail="不能关联自身")
    if db.get(models.Voucher, payload.target_id) is None:
        raise HTTPException(status_code=400, detail="目标凭证不存在")
    # 去重(无向)
    exists = db.scalar(select(models.VoucherLink).where(or_(
        (models.VoucherLink.source_id == voucher_id)
        & (models.VoucherLink.target_id == payload.target_id),
        (models.VoucherLink.source_id == payload.target_id)
        & (models.VoucherLink.target_id == voucher_id),
    )))
    if exists:
        raise HTTPException(status_code=409, detail="该关联已存在")
    db.add(models.VoucherLink(
        source_id=voucher_id, target_id=payload.target_id,
        relation_type=payload.relation_type, note=payload.note,
    ))
    db.commit()
    return get_voucher(voucher_id, db)


@router.delete("/links/{link_id}", status_code=204)
def delete_link(link_id: int, db: Session = Depends(get_db)):
    link = db.get(models.VoucherLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="关联不存在")
    db.delete(link)
    db.commit()


@router.post("/{voucher_id}/reverse", response_model=schemas.VoucherDetail, status_code=201)
def reverse_voucher(
    voucher_id: int,
    reverse_date: date | None = None,
    db: Session = Depends(get_db),
):
    """生成红字冲销凭证:金额取负,借贷科目不变,并与原凭证建立「冲销」关联。"""
    origin = db.scalar(
        select(models.Voucher).where(models.Voucher.id == voucher_id)
        .options(selectinload(models.Voucher.entries))
    )
    if origin is None:
        raise HTTPException(status_code=404, detail="凭证不存在")

    vdate = reverse_date or origin.voucher_date
    reversal = models.Voucher(
        voucher_no=_next_voucher_no(db, vdate),
        voucher_date=vdate,
        note=f"红字冲销:{origin.note or origin.voucher_no}",
        customer_id=origin.customer_id,
        status="posted",
        total_debit=-origin.total_debit,
        total_credit=-origin.total_credit,
    )
    for e in origin.entries:
        reversal.entries.append(models.VoucherEntry(
            line_no=e.line_no, summary=e.summary, account_id=e.account_id,
            sub_account=e.sub_account, debit=-e.debit, credit=-e.credit,
        ))
    db.add(reversal)
    db.flush()
    db.add(models.VoucherLink(
        source_id=reversal.id, target_id=origin.id,
        relation_type="reversal", note="红字冲销",
    ))
    db.commit()
    return get_voucher(reversal.id, db)
