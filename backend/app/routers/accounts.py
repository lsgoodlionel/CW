"""会计科目 API(含二级明细科目、Excel 导入导出)。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas, subaccounts_svc, account_excel
from ..schemas_read import SubAccountImportOut

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([content]), media_type=XLSX,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


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


@router.get("/tree", response_model=list[schemas.AccountTreeNode])
def account_tree(category: str | None = None, db: Session = Depends(get_db)):
    """一级科目 + 其二级科目(用于多级科目管理页面)。"""
    stmt = (select(models.Account).order_by(models.Account.code)
            .options(selectinload(models.Account.sub_accounts)))
    if category:
        stmt = stmt.where(models.Account.category == category)
    return db.scalars(stmt).all()


# ---------- Excel 导入导出 ----------
@router.get("/export-excel")
def export_excel(db: Session = Depends(get_db)):
    return _xlsx(account_excel.export_accounts(db), "会计科目表(含二级科目).xlsx")


@router.get("/subaccounts/template")
def subaccount_template(db: Session = Depends(get_db)):
    return _xlsx(account_excel.import_template(db), "二级科目导入模板.xlsx")


@router.post("/subaccounts/import", response_model=SubAccountImportOut)
async def subaccount_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        return account_excel.import_subaccounts(db, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------- 二级科目 CRUD ----------
@router.get("/{account_id}/subaccounts", response_model=list[schemas.SubAccountOut])
def list_subaccounts(account_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(models.SubAccount).where(models.SubAccount.account_id == account_id)
        .order_by(models.SubAccount.code)
    ).all()


@router.post("/{account_id}/subaccounts", response_model=schemas.SubAccountOut, status_code=201)
def create_subaccount(
    account_id: int, payload: schemas.SubAccountCreate, db: Session = Depends(get_db)
):
    account = db.get(models.Account, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="一级科目不存在")
    dup = db.scalar(select(models.SubAccount).where(
        models.SubAccount.account_id == account_id,
        models.SubAccount.name == payload.name.strip()))
    if dup:
        raise HTTPException(status_code=409, detail="该一级科目下已存在同名二级科目")
    code = payload.code.strip() or subaccounts_svc.next_code(db, account)
    if db.scalar(select(models.SubAccount).where(models.SubAccount.code == code)):
        raise HTTPException(status_code=409, detail=f"二级科目编码 {code} 已存在")
    sub = models.SubAccount(
        account_id=account_id, code=code, name=payload.name.strip(),
        note=payload.note, sort_no=subaccounts_svc.next_sort(db, account_id),
        is_active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.put("/subaccounts/{sub_id}", response_model=schemas.SubAccountOut)
def update_subaccount(
    sub_id: int, payload: schemas.SubAccountUpdate, db: Session = Depends(get_db)
):
    """编辑二级科目;改名会同步更新引用它的凭证明细科目。"""
    sub = db.get(models.SubAccount, sub_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="二级科目不存在")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] and data["name"].strip() != sub.name:
        subaccounts_svc.rename_sync_vouchers(db, sub, data["name"].strip())
    if "note" in data and data["note"] is not None:
        sub.note = data["note"]
    if "is_active" in data and data["is_active"] is not None:
        sub.is_active = data["is_active"]
    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/subaccounts/{sub_id}", status_code=204)
def delete_subaccount(sub_id: int, db: Session = Depends(get_db)):
    """删除二级科目;若已被凭证引用则改为停用。"""
    sub = db.get(models.SubAccount, sub_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="二级科目不存在")
    used = db.scalar(select(models.VoucherEntry.id).where(
        models.VoucherEntry.sub_account_id == sub_id).limit(1))
    if used:
        sub.is_active = False
        db.commit()
    else:
        db.delete(sub)
        db.commit()


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
