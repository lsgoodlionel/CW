"""费用申请(事前审批)API:申请单 CRUD + 上传附件 + 提交审批(复用流程引擎)。"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas, workflow_svc, attach_svc
from .attachments import read_upload

router = APIRouter(prefix="/api/expense-apply", tags=["expense-apply"])

STATUS_LABEL = {"draft": "草稿", "pending": "审批中", "approved": "已通过",
                "rejected": "已驳回", "closed": "已关联报销"}
APPLY_TYPE_LABEL = {"general": "一般申请", "contract": "合同", "routine": "常规费用"}

# 常用费用类别预设(与报销一致)
EXPENSE_CATEGORIES = [
    "办公费", "差旅费", "交通费", "住宿费", "餐饮费", "业务招待费", "通讯费",
    "邮寄快递费", "培训费", "会议费", "市场推广费", "租赁费", "水电费",
    "维修费", "劳保费", "低值易耗品", "其他",
]


def _apply_no(db: Session, d: date) -> str:
    n = db.scalar(select(func.count(models.ExpenseApplication.id)).where(
        func.extract("year", models.ExpenseApplication.created_at) == d.year)) or 0
    return f"SQ-{d:%Y%m}-{n + 1:03d}"


def _sync_status(db: Session, app: models.ExpenseApplication) -> None:
    """从关联的流程实例同步状态(未被报销关联时)。"""
    if app.status == "closed":
        return
    if app.workflow_instance_id:
        inst = db.get(models.WorkflowInstance, app.workflow_instance_id)
        if inst:
            app.status = inst.status  # pending/approved/rejected
    elif app.status != "draft":
        app.status = "draft"


def _out(db: Session, app: models.ExpenseApplication) -> schemas.ExpenseApplicationOut:
    _sync_status(db, app)
    item = schemas.ExpenseApplicationOut.model_validate(app)
    emp = db.get(models.Employee, app.applicant_employee_id) if app.applicant_employee_id else None
    unit = db.get(models.OrgUnit, app.org_unit_id) if app.org_unit_id else None
    item.applicant_name = emp.name if emp else ""
    item.org_unit_name = unit.name if unit else ""
    for it, io in zip(app.items, item.items):
        acc = db.get(models.Account, it.account_id) if it.account_id else None
        io.account_name = acc.name if acc else ""
    item.claim_ids = list(db.scalars(select(models.ExpenseClaim.id).where(
        models.ExpenseClaim.application_id == app.id)).all())
    if app.workflow_instance_id:
        from .workflow import _instance_out
        inst = db.scalar(select(models.WorkflowInstance)
                         .where(models.WorkflowInstance.id == app.workflow_instance_id)
                         .options(selectinload(models.WorkflowInstance.tasks)))
        if inst:
            item.workflow = _instance_out(db, inst)
    return item


def _load(db: Session, app_id: int) -> models.ExpenseApplication:
    app = db.scalar(select(models.ExpenseApplication)
                    .where(models.ExpenseApplication.id == app_id)
                    .options(selectinload(models.ExpenseApplication.items),
                             selectinload(models.ExpenseApplication.attachments)))
    if app is None:
        raise HTTPException(status_code=404, detail="费用申请不存在")
    return app


def _apply_items(app: models.ExpenseApplication, items) -> None:
    app.items.clear()
    total = Decimal("0")
    for it in items:
        amt = Decimal(str(it.amount))
        total += amt
        app.items.append(models.ExpenseApplicationItem(
            category=it.category, account_id=it.account_id,
            sub_account=it.sub_account, amount=amt, note=it.note))
    app.estimated_amount = total


@router.get("/meta")
def apply_meta():
    return {"status": STATUS_LABEL, "apply_types": APPLY_TYPE_LABEL,
            "categories": EXPENSE_CATEGORIES}


@router.get("/active-workflow")
def active_workflow(db: Session = Depends(get_db)):
    d = db.scalar(select(models.WorkflowDefinition)
                  .where(models.WorkflowDefinition.biz_type == "expense_apply",
                         models.WorkflowDefinition.is_active.is_(True))
                  .order_by(models.WorkflowDefinition.id)
                  .options(selectinload(models.WorkflowDefinition.steps)))
    if d is None:
        return {"exists": False}
    return {"exists": True, "id": d.id, "name": d.name,
            "steps": [{"step_no": s.step_no, "name": s.name,
                       "approver_type": s.approver_type} for s in d.steps]}


@router.get("/approved", response_model=list[schemas.ExpenseApplicationOut])
def list_approved(db: Session = Depends(get_db)):
    """已通过审批、可用于发起报销的费用申请(含明细以便带出)。"""
    apps = db.scalars(select(models.ExpenseApplication)
                      .where(models.ExpenseApplication.status.in_(("approved", "closed")))
                      .order_by(models.ExpenseApplication.id.desc())
                      .options(selectinload(models.ExpenseApplication.items),
                               selectinload(models.ExpenseApplication.attachments))).all()
    out = [_out(db, a) for a in apps]
    db.commit()
    return out


@router.get("", response_model=list[schemas.ExpenseApplicationOut])
def list_applications(status: str | None = None, db: Session = Depends(get_db)):
    stmt = (select(models.ExpenseApplication).order_by(models.ExpenseApplication.id.desc())
            .options(selectinload(models.ExpenseApplication.items),
                     selectinload(models.ExpenseApplication.attachments)))
    if status:
        stmt = stmt.where(models.ExpenseApplication.status == status)
    apps = db.scalars(stmt).all()
    out = [_out(db, a) for a in apps]
    db.commit()
    return out


@router.post("", response_model=schemas.ExpenseApplicationOut, status_code=201)
def create_application(payload: schemas.ExpenseApplicationIn, db: Session = Depends(get_db)):
    if payload.apply_type not in schemas.APPLY_TYPES:
        raise HTTPException(status_code=400, detail="申请类型无效")
    app = models.ExpenseApplication(
        apply_no=_apply_no(db, date.today()),
        applicant_employee_id=payload.applicant_employee_id,
        org_unit_id=payload.org_unit_id, apply_type=payload.apply_type,
        reason=payload.reason, note=payload.note, status="draft")
    _apply_items(app, payload.items)
    db.add(app)
    db.commit()
    return get_application(app.id, db)


@router.get("/{app_id}", response_model=schemas.ExpenseApplicationOut)
def get_application(app_id: int, db: Session = Depends(get_db)):
    app = _load(db, app_id)
    out = _out(db, app)
    db.commit()
    return out


@router.put("/{app_id}", response_model=schemas.ExpenseApplicationOut)
def update_application(app_id: int, payload: schemas.ExpenseApplicationIn,
                       db: Session = Depends(get_db)):
    app = _load(db, app_id)
    if app.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="仅草稿或被驳回的申请可编辑")
    if payload.apply_type not in schemas.APPLY_TYPES:
        raise HTTPException(status_code=400, detail="申请类型无效")
    app.applicant_employee_id = payload.applicant_employee_id
    app.org_unit_id = payload.org_unit_id
    app.apply_type = payload.apply_type
    app.reason = payload.reason
    app.note = payload.note
    _apply_items(app, payload.items)
    app.workflow_instance_id = None
    app.status = "draft"
    db.commit()
    return get_application(app_id, db)


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: int, db: Session = Depends(get_db)):
    app = _load(db, app_id)
    linked = db.scalar(select(func.count(models.ExpenseClaim.id)).where(
        models.ExpenseClaim.application_id == app_id)) or 0
    if linked:
        raise HTTPException(status_code=400, detail="该申请已被报销单关联,不能删除")
    db.delete(app)
    db.commit()


@router.post("/{app_id}/submit", response_model=schemas.ExpenseApplicationOut)
def submit_application(app_id: int, db: Session = Depends(get_db)):
    app = _load(db, app_id)
    if app.status not in ("draft", "rejected"):
        raise HTTPException(status_code=400, detail="该申请已提交")
    definition = db.scalar(select(models.WorkflowDefinition)
                           .where(models.WorkflowDefinition.biz_type == "expense_apply",
                                  models.WorkflowDefinition.is_active.is_(True))
                           .order_by(models.WorkflowDefinition.id)
                           .options(selectinload(models.WorkflowDefinition.steps)))
    if definition is None or not definition.steps:
        raise HTTPException(status_code=400,
                            detail="未配置'费用申请'审批流程,请先在审批流程页新建")
    sub = schemas.InstanceSubmit(
        definition_id=definition.id, biz_type="expense_apply", biz_id=app.id,
        title=f"{app.apply_no} 费用申请 预计{app.estimated_amount}元 · {app.reason}",
        applicant_employee_id=app.applicant_employee_id)
    inst = workflow_svc.create_instance(db, sub, definition)
    app.workflow_instance_id = inst.id
    app.status = "pending"
    db.commit()
    return get_application(app_id, db)


@router.post("/{app_id}/attachments", response_model=schemas.AttachmentOut, status_code=201)
async def upload_attachment(app_id: int, kind: str = Form("other"),
                            file: UploadFile = File(...), db: Session = Depends(get_db)):
    """上传费用申请附件(合同/发票等);报销生成凭证时会同步到凭证附件。"""
    app = db.get(models.ExpenseApplication, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="费用申请不存在")
    content = await read_upload(file, kind)
    stored = attach_svc.store_bytes(f"apply_{app_id}", file.filename or "", content)
    attachment = attach_svc.make_attachment(
        kind=kind, original_name=file.filename or stored.name, stored_path=stored,
        mime_type=file.content_type or "", size_bytes=len(content),
        expense_application_id=app_id)
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment
