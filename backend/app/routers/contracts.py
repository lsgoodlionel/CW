"""合同管理 API:合同 CRUD + 附件上传 + 关联记账凭证。"""
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas, attach_svc
from .attachments import read_upload

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

_CENT = Decimal("0.01")


def _calc_tax(amount: Decimal, tax_rate: Decimal) -> Decimal:
    """含税总额价税分离:税金 = 金额 − 金额/(1+税率)。税率为百分数。"""
    amount = amount or Decimal("0")
    tax_rate = tax_rate or Decimal("0")
    if tax_rate <= 0:
        return Decimal("0.00")
    tax = amount - amount / (Decimal("1") + tax_rate / Decimal("100"))
    return tax.quantize(_CENT, rounding=ROUND_HALF_UP)

CATEGORY_LABEL = {
    "sales": "销售合同", "purchase": "采购合同", "service": "服务合同",
    "lease": "租赁合同", "labor": "劳务合同", "loan": "借款合同", "other": "其他",
}
STATUS_LABEL = {"draft": "草稿", "active": "履行中", "completed": "已完成", "terminated": "已终止"}
DIRECTION_LABEL = {"income": "收入类(我方提供/收款)", "expense": "支出类(我方接受/付款)"}


def _out(db: Session, c: models.Contract) -> schemas.ContractOut:
    item = schemas.ContractOut.model_validate(c)
    if c.customer:
        item.customer_name = c.customer.short_name or c.customer.name
    elif c.party_name:
        item.customer_name = c.party_name
    vouchers = []
    for link in c.voucher_links:
        v = link.voucher
        if v is None:
            continue
        vouchers.append(schemas.ContractVoucherBrief(
            id=link.id, voucher_id=v.id, voucher_no=v.voucher_no,
            voucher_date=v.voucher_date, total_debit=v.total_debit, note=link.note))
    item.vouchers = vouchers
    return item


def _load(db: Session, contract_id: int) -> models.Contract:
    c = db.scalar(select(models.Contract)
                  .where(models.Contract.id == contract_id)
                  .options(selectinload(models.Contract.attachments),
                           selectinload(models.Contract.customer),
                           selectinload(models.Contract.voucher_links)
                           .selectinload(models.ContractVoucherLink.voucher)))
    if c is None:
        raise HTTPException(status_code=404, detail="合同不存在")
    return c


@router.get("", response_model=list[schemas.ContractOut])
def list_contracts(status: str | None = None, category: str | None = None,
                   db: Session = Depends(get_db)):
    stmt = (select(models.Contract).order_by(models.Contract.id.desc())
            .options(selectinload(models.Contract.attachments),
                     selectinload(models.Contract.customer),
                     selectinload(models.Contract.voucher_links)
                     .selectinload(models.ContractVoucherLink.voucher)))
    if status:
        stmt = stmt.where(models.Contract.status == status)
    if category:
        stmt = stmt.where(models.Contract.category == category)
    return [_out(db, c) for c in db.scalars(stmt).all()]


@router.post("", response_model=schemas.ContractOut, status_code=201)
def create_contract(payload: schemas.ContractIn, db: Session = Depends(get_db)):
    if payload.category not in schemas.CONTRACT_CATEGORIES:
        raise HTTPException(status_code=400, detail="合同类型无效")
    if payload.status not in schemas.CONTRACT_STATUSES:
        raise HTTPException(status_code=400, detail="合同状态无效")
    if payload.direction not in schemas.CONTRACT_DIRECTIONS:
        raise HTTPException(status_code=400, detail="合同收支方向无效")
    c = models.Contract(**payload.model_dump())
    c.tax_amount = _calc_tax(c.amount, c.tax_rate)
    db.add(c)
    db.commit()
    return get_contract(c.id, db)


@router.get("/by-voucher/{voucher_id}", response_model=list[schemas.VoucherContractBrief])
def contracts_of_voucher(voucher_id: int, db: Session = Depends(get_db)):
    """凭证侧反查该凭证已关联的合同(供凭证页反向管理关联)。"""
    links = db.scalars(
        select(models.ContractVoucherLink)
        .where(models.ContractVoucherLink.voucher_id == voucher_id)
        .options(selectinload(models.ContractVoucherLink.contract))).all()
    out = []
    for lk in links:
        c = lk.contract
        if c is None:
            continue
        out.append(schemas.VoucherContractBrief(
            link_id=lk.id, contract_id=c.id, contract_no=c.contract_no,
            name=c.name, amount=c.amount, note=lk.note))
    return out


@router.get("/{contract_id}", response_model=schemas.ContractOut)
def get_contract(contract_id: int, db: Session = Depends(get_db)):
    return _out(db, _load(db, contract_id))


@router.put("/{contract_id}", response_model=schemas.ContractOut)
def update_contract(contract_id: int, payload: schemas.ContractIn,
                    db: Session = Depends(get_db)):
    c = _load(db, contract_id)
    if payload.category not in schemas.CONTRACT_CATEGORIES:
        raise HTTPException(status_code=400, detail="合同类型无效")
    if payload.direction not in schemas.CONTRACT_DIRECTIONS:
        raise HTTPException(status_code=400, detail="合同收支方向无效")
    for k, v in payload.model_dump().items():
        setattr(c, k, v)
    c.tax_amount = _calc_tax(c.amount, c.tax_rate)
    db.commit()
    return get_contract(contract_id, db)


@router.delete("/{contract_id}", status_code=204)
def delete_contract(contract_id: int, db: Session = Depends(get_db)):
    c = _load(db, contract_id)
    db.delete(c)
    db.commit()


@router.post("/{contract_id}/attachments", response_model=schemas.AttachmentOut, status_code=201)
async def upload_attachment(contract_id: int, kind: str = Form("contract"),
                            file: UploadFile = File(...), db: Session = Depends(get_db)):
    if db.get(models.Contract, contract_id) is None:
        raise HTTPException(status_code=404, detail="合同不存在")
    content = await read_upload(file, kind)
    stored = attach_svc.store_bytes(f"contract_{contract_id}", file.filename or "", content)
    att = attach_svc.make_attachment(
        kind=kind, original_name=file.filename or stored.name, stored_path=stored,
        mime_type=file.content_type or "", size_bytes=len(content), contract_id=contract_id)
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.post("/{contract_id}/link", response_model=schemas.ContractOut)
def link_voucher(contract_id: int, voucher_id: int, note: str = "",
                 db: Session = Depends(get_db)):
    if db.get(models.Contract, contract_id) is None:
        raise HTTPException(status_code=404, detail="合同不存在")
    if db.get(models.Voucher, voucher_id) is None:
        raise HTTPException(status_code=400, detail="凭证不存在")
    exists = db.scalar(select(models.ContractVoucherLink.id).where(
        models.ContractVoucherLink.contract_id == contract_id,
        models.ContractVoucherLink.voucher_id == voucher_id))
    if exists:
        raise HTTPException(status_code=409, detail="该凭证已关联")
    db.add(models.ContractVoucherLink(
        contract_id=contract_id, voucher_id=voucher_id, note=note))
    db.commit()
    return get_contract(contract_id, db)


@router.delete("/link/{link_id}", status_code=204)
def unlink_voucher(link_id: int, db: Session = Depends(get_db)):
    link = db.get(models.ContractVoucherLink, link_id)
    if link is None:
        raise HTTPException(status_code=404, detail="关联不存在")
    db.delete(link)
    db.commit()


@router.get("/meta/labels")
def contract_meta():
    return {"category": CATEGORY_LABEL, "status": STATUS_LABEL, "direction": DIRECTION_LABEL}
