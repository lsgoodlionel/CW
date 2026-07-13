"""客户管理 API:企业客户/往来单位信息 + 往来凭证历史。"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("", response_model=list[schemas.CustomerOut])
def list_customers(
    keyword: str | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    stmt = select(models.Customer).order_by(models.Customer.name)
    if active_only:
        stmt = stmt.where(models.Customer.is_active.is_(True))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(
            models.Customer.name.ilike(like),
            models.Customer.short_name.ilike(like),
            models.Customer.tax_number.ilike(like),
        ))
    return db.scalars(stmt).all()


@router.post("", response_model=schemas.CustomerOut, status_code=201)
def create_customer(payload: schemas.CustomerCreate, db: Session = Depends(get_db)):
    customer = models.Customer(**payload.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.get(models.Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    return customer


@router.put("/{customer_id}", response_model=schemas.CustomerOut)
def update_customer(
    customer_id: int, payload: schemas.CustomerUpdate, db: Session = Depends(get_db)
):
    customer = db.get(models.Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    """删除客户;若已被凭证关联则改为停用(软删除)。"""
    customer = db.get(models.Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    used = db.scalar(
        select(models.Voucher.id).where(
            models.Voucher.customer_id == customer_id).limit(1))
    if used:
        customer.is_active = False
        db.commit()
    else:
        db.delete(customer)
        db.commit()


@router.get("/{customer_id}/vouchers")
def customer_vouchers(
    customer_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """客户往来业务历史:关联到该客户的凭证列表 + 借贷合计。"""
    if db.get(models.Customer, customer_id) is None:
        raise HTTPException(status_code=404, detail="客户不存在")
    base = select(models.Voucher).where(models.Voucher.customer_id == customer_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    vouchers = db.scalars(
        base.order_by(models.Voucher.voucher_date.desc(), models.Voucher.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    sum_debit = db.scalar(
        select(func.coalesce(func.sum(models.Voucher.total_debit), 0))
        .where(models.Voucher.customer_id == customer_id)) or Decimal("0")
    items = [{
        "id": v.id, "voucher_no": v.voucher_no,
        "voucher_date": v.voucher_date.isoformat(), "note": v.note,
        "total_debit": float(v.total_debit),
    } for v in vouchers]
    return {"items": items, "total": total, "page": page,
            "page_size": page_size, "sum_debit": float(sum_debit)}
