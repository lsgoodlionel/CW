"""会计科目 API。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[schemas.AccountOut])
def list_accounts(
    category: str | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
):
    stmt = select(models.Account).order_by(models.Account.code)
    if category:
        stmt = stmt.where(models.Account.category == category)
    if active_only:
        stmt = stmt.where(models.Account.is_active.is_(True))
    return db.scalars(stmt).all()


@router.post("", response_model=schemas.AccountOut, status_code=201)
def create_account(payload: schemas.AccountCreate, db: Session = Depends(get_db)):
    exists = db.scalar(
        select(models.Account).where(models.Account.code == payload.code)
    )
    if exists:
        raise HTTPException(status_code=409, detail=f"科目编码 {payload.code} 已存在")
    account = models.Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.put("/{account_id}", response_model=schemas.AccountOut)
def update_account(
    account_id: int, payload: schemas.AccountUpdate, db: Session = Depends(get_db)
):
    account = db.get(models.Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="科目不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
def deactivate_account(account_id: int, db: Session = Depends(get_db)):
    """停用科目(软删除);若已被凭证引用则不允许物理删除。"""
    account = db.get(models.Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="科目不存在")
    used = db.scalar(
        select(models.VoucherEntry.id).where(
            models.VoucherEntry.account_id == account_id
        ).limit(1)
    )
    if used:
        account.is_active = False
        db.commit()
    else:
        db.delete(account)
        db.commit()
