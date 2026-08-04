"""费用报销 API:申请单 CRUD + 提交审批(复用流程引擎)+ 通过后生成凭证。"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas, workflow_svc, subaccounts_svc

router = APIRouter(prefix="/api/expense", tags=["expense"])

STATUS_LABEL = {"draft": "草稿", "pending": "审批中", "approved": "已通过",
                "rejected": "已驳回", "paid": "已生成凭证"}


def _claim_no(db: Session, d: date) -> str:
    prefix = f"BX-{d:%Y%m}-"
    n = db.scalar(select(func.count(models.ExpenseClaim.id)).where(
        func.extract("year", models.ExpenseClaim.created_at) == d.year)) or 0
    return f"{prefix}{n + 1:03d}"


def _sync_status(db: Session, claim: models.ExpenseClaim) -> None:
    """从关联的流程实例同步状态(未生成凭证时)。"""
    if claim.voucher_id:
        claim.status = "paid"
        return
    if claim.workflow_instance_id:
        inst = db.get(models.WorkflowInstance, claim.workflow_instance_id)
        if inst:
            claim.status = inst.status  # pending/approved/rejected
    elif claim.status not in ("draft",):
        claim.status = "draft"


def _out(db: Session, claim: models.ExpenseClaim) -> schemas.ExpenseClaimOut:
    _sync_status(db, claim)
    item = schemas.ExpenseClaimOut.model_validate(claim)
    emp = db.get(models.Employee, claim.applicant_employee_id) if claim.applicant_employee_id else None
    unit = db.get(models.OrgUnit, claim.org_unit_id) if claim.org_unit_id else None
    item.applicant_name = emp.name if emp else ""
    item.org_unit_name = unit.name if unit else ""
    if claim.voucher_id:
        v = db.get(models.Voucher, claim.voucher_id)
        item.voucher_no = v.voucher_no if v else ""
    for it, io in zip(claim.items, item.items):
        acc = db.get(models.Account, it.account_id) if it.account_id else None
        io.account_name = acc.name if acc else ""
    if claim.workflow_instance_id:
        from .workflow import _instance_out
        inst = db.scalar(select(models.WorkflowInstance)
                         .where(models.WorkflowInstance.id == claim.workflow_instance_id)
                         .options(selectinload(models.WorkflowInstance.tasks)))
        if inst:
            item.workflow = _instance_out(db, inst)
    return item


def _load(db: Session, claim_id: int) -> models.ExpenseClaim:
    claim = db.scalar(select(models.ExpenseClaim)
                      .where(models.ExpenseClaim.id == claim_id)
                      .options(selectinload(models.ExpenseClaim.items)))
    if claim is None:
        raise HTTPException(status_code=404, detail="报销单不存在")
    return claim


@router.get("/claims", response_model=list[schemas.ExpenseClaimOut])
def list_claims(status: str | None = None, applicant_employee_id: int | None = None,
                db: Session = Depends(get_db)):
    stmt = (select(models.ExpenseClaim).order_by(models.ExpenseClaim.id.desc())
            .options(selectinload(models.ExpenseClaim.items)))
    if status:
        stmt = stmt.where(models.ExpenseClaim.status == status)
    if applicant_employee_id:
        stmt = stmt.where(models.ExpenseClaim.applicant_employee_id == applicant_employee_id)
    claims = db.scalars(stmt).all()
    out = [_out(db, c) for c in claims]
    db.commit()  # 持久化同步后的状态
    return out


@router.get("/claims/{claim_id}", response_model=schemas.ExpenseClaimOut)
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    claim = _load(db, claim_id)
    out = _out(db, claim)
    db.commit()
    return out


def _apply_items(db: Session, claim: models.ExpenseClaim, items) -> None:
    claim.items.clear()
    total = Decimal("0")
    for it in items:
        amt = Decimal(str(it.amount))
        total += amt
        claim.items.append(models.ExpenseItem(
            category=it.category, account_id=it.account_id,
            sub_account=it.sub_account, amount=amt, note=it.note))
    claim.total_amount = total


@router.post("/claims", response_model=schemas.ExpenseClaimOut, status_code=201)
def create_claim(payload: schemas.ExpenseClaimIn, db: Session = Depends(get_db)):
    claim = models.ExpenseClaim(
        claim_no=_claim_no(db, date.today()),
        applicant_employee_id=payload.applicant_employee_id,
        org_unit_id=payload.org_unit_id, reason=payload.reason,
        note=payload.note, status="draft")
    _apply_items(db, claim, payload.items)
    db.add(claim)
    db.commit()
    return get_claim(claim.id, db)


@router.put("/claims/{claim_id}", response_model=schemas.ExpenseClaimOut)
def update_claim(claim_id: int, payload: schemas.ExpenseClaimIn, db: Session = Depends(get_db)):
    claim = _load(db, claim_id)
    if claim.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="仅草稿或被驳回的报销单可编辑")
    claim.applicant_employee_id = payload.applicant_employee_id
    claim.org_unit_id = payload.org_unit_id
    claim.reason = payload.reason
    claim.note = payload.note
    _apply_items(db, claim, payload.items)
    claim.workflow_instance_id = None
    claim.status = "draft"
    db.commit()
    return get_claim(claim_id, db)


@router.delete("/claims/{claim_id}", status_code=204)
def delete_claim(claim_id: int, db: Session = Depends(get_db)):
    claim = _load(db, claim_id)
    db.delete(claim)
    db.commit()


@router.post("/claims/{claim_id}/submit", response_model=schemas.ExpenseClaimOut)
def submit_claim(claim_id: int, db: Session = Depends(get_db)):
    """提交审批:按 expense 类型的启用流程发起实例。"""
    claim = _load(db, claim_id)
    if claim.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="该报销单已提交")
    definition = db.scalar(select(models.WorkflowDefinition)
                           .where(models.WorkflowDefinition.biz_type == "expense",
                                  models.WorkflowDefinition.is_active.is_(True))
                           .order_by(models.WorkflowDefinition.id)
                           .options(selectinload(models.WorkflowDefinition.steps)))
    if definition is None or not definition.steps:
        raise HTTPException(status_code=400,
                            detail="未配置'费用报销'审批流程,请先在审批流程页新建")
    sub = schemas.InstanceSubmit(
        definition_id=definition.id, biz_type="expense", biz_id=claim.id,
        title=f"{claim.claim_no} 报销 {claim.total_amount} 元 · {claim.reason}",
        applicant_employee_id=claim.applicant_employee_id)
    inst = workflow_svc.create_instance(db, sub, definition)
    claim.workflow_instance_id = inst.id
    claim.status = "pending"
    db.commit()
    return get_claim(claim_id, db)


@router.post("/claims/{claim_id}/make-voucher", response_model=schemas.ExpenseClaimOut)
def make_voucher(claim_id: int, credit_account_code: str = Query("1002"),
                 db: Session = Depends(get_db)):
    """审批通过后生成记账凭证:借 各费用科目 / 贷 银行存款(默认1002)。"""
    claim = _load(db, claim_id)
    _sync_status(db, claim)
    if claim.status != "approved":
        raise HTTPException(status_code=400, detail="仅审批通过的报销单可生成凭证")
    if claim.voucher_id:
        raise HTTPException(status_code=409, detail="已生成凭证")
    credit_acc = db.scalar(select(models.Account).where(models.Account.code == credit_account_code))
    if credit_acc is None:
        raise HTTPException(status_code=400, detail="贷方科目不存在")

    from .vouchers import _next_voucher_no
    voucher = models.Voucher(
        voucher_no=_next_voucher_no(db, date.today()), voucher_date=date.today(),
        note=f"报销:{claim.reason or claim.claim_no}",
        status="posted", total_debit=claim.total_amount, total_credit=claim.total_amount)
    line = 1
    for it in claim.items:
        if not it.account_id or it.amount == 0:
            continue
        sub = subaccounts_svc.get_or_create(db, it.account_id, it.sub_account)
        voucher.entries.append(models.VoucherEntry(
            line_no=line, summary=it.category or claim.reason, account_id=it.account_id,
            sub_account=sub.name if sub else "", sub_account_id=sub.id if sub else None,
            debit=it.amount, credit=Decimal("0")))
        line += 1
    voucher.entries.append(models.VoucherEntry(
        line_no=line, summary="报销付款", account_id=credit_acc.id,
        debit=Decimal("0"), credit=claim.total_amount))
    db.add(voucher)
    db.flush()
    claim.voucher_id = voucher.id
    claim.status = "paid"
    db.commit()
    return get_claim(claim_id, db)


@router.get("/meta")
def expense_meta():
    return {"status": STATUS_LABEL}
