"""审批流程 API:流程定义设计、发起实例、审批待办。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from .. import models, schemas, workflow_svc

router = APIRouter(prefix="/api/workflow", tags=["workflow"])

APPROVER_TYPES = {
    "employee": "指定员工", "role": "按角色", "department_head": "部门负责人", "any": "任一管理层",
}
BIZ_TYPES = {"general": "通用", "expense_apply": "费用申请", "expense": "费用报销"}
STATUS_LABEL = {"pending": "审批中", "approved": "已通过", "rejected": "已驳回", "cancelled": "已撤销"}


def _emp_names(db: Session) -> dict[int, str]:
    return {e.id: e.name for e in db.scalars(select(models.Employee)).all()}


# ---------- 流程定义 ----------
@router.get("/definitions", response_model=list[schemas.WorkflowDefOut])
def list_definitions(biz_type: str | None = None, db: Session = Depends(get_db)):
    stmt = (select(models.WorkflowDefinition)
            .order_by(models.WorkflowDefinition.id)
            .options(selectinload(models.WorkflowDefinition.steps)))
    if biz_type:
        stmt = stmt.where(models.WorkflowDefinition.biz_type == biz_type)
    names = _emp_names(db)
    out = []
    for d in db.scalars(stmt).all():
        item = schemas.WorkflowDefOut.model_validate(d)
        for s, so in zip(d.steps, item.steps):
            so.approver_name = names.get(s.approver_employee_id, "") if s.approver_employee_id else ""
        out.append(item)
    return out


@router.post("/definitions", response_model=schemas.WorkflowDefOut, status_code=201)
def create_definition(payload: schemas.WorkflowDefIn, db: Session = Depends(get_db)):
    d = models.WorkflowDefinition(name=payload.name, biz_type=payload.biz_type,
                                  note=payload.note, is_active=payload.is_active)
    for i, s in enumerate(payload.steps, start=1):
        d.steps.append(models.WorkflowStep(
            step_no=i, name=s.name, approver_type=s.approver_type,
            approver_employee_id=s.approver_employee_id, approver_role=s.approver_role))
    db.add(d)
    db.commit()
    return list_one(d.id, db)


@router.put("/definitions/{def_id}", response_model=schemas.WorkflowDefOut)
def update_definition(def_id: int, payload: schemas.WorkflowDefIn, db: Session = Depends(get_db)):
    d = db.get(models.WorkflowDefinition, def_id)
    if d is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    d.name, d.biz_type, d.note, d.is_active = payload.name, payload.biz_type, payload.note, payload.is_active
    d.steps.clear()
    for i, s in enumerate(payload.steps, start=1):
        d.steps.append(models.WorkflowStep(
            step_no=i, name=s.name, approver_type=s.approver_type,
            approver_employee_id=s.approver_employee_id, approver_role=s.approver_role))
    db.commit()
    return list_one(def_id, db)


@router.delete("/definitions/{def_id}", status_code=204)
def delete_definition(def_id: int, db: Session = Depends(get_db)):
    d = db.get(models.WorkflowDefinition, def_id)
    if d is None:
        raise HTTPException(status_code=404, detail="流程不存在")
    db.delete(d)
    db.commit()


def list_one(def_id: int, db: Session) -> schemas.WorkflowDefOut:
    d = db.scalar(select(models.WorkflowDefinition)
                  .where(models.WorkflowDefinition.id == def_id)
                  .options(selectinload(models.WorkflowDefinition.steps)))
    names = _emp_names(db)
    item = schemas.WorkflowDefOut.model_validate(d)
    for s, so in zip(d.steps, item.steps):
        so.approver_name = names.get(s.approver_employee_id, "") if s.approver_employee_id else ""
    return item


# ---------- 实例 / 审批 ----------
def _instance_out(db: Session, inst: models.WorkflowInstance) -> schemas.InstanceOut:
    names = _emp_names(db)
    item = schemas.InstanceOut.model_validate(inst)
    item.applicant_name = names.get(inst.applicant_employee_id, "") if inst.applicant_employee_id else ""
    for t, to in zip(inst.tasks, item.tasks):
        to.approver_name = names.get(t.approver_employee_id, "") if t.approver_employee_id else ""
    item.steps = _build_step_chain(db, inst, names)
    return item


def _build_step_chain(db: Session, inst: models.WorkflowInstance,
                      names: dict[int, str]) -> list[schemas.InstanceStepOut]:
    """合并「流程定义的全部步骤」与「实际审批任务」,得到含后续审批人的完整链。"""
    steps = db.scalars(
        select(models.WorkflowStep)
        .where(models.WorkflowStep.definition_id == inst.definition_id)
        .order_by(models.WorkflowStep.step_no)).all()
    # 每一步取最后一条任务(同一步可能被驳回后重来)
    task_by_step: dict[int, models.WorkflowTask] = {}
    for t in sorted(inst.tasks, key=lambda x: x.id):
        task_by_step[t.step_no] = t

    chain: list[schemas.InstanceStepOut] = []
    reached_end = inst.status in ("approved", "rejected")
    for s in steps:
        task = task_by_step.get(s.step_no)
        approver_label = APPROVER_TYPES.get(s.approver_type, s.approver_type)
        if task is not None:
            if task.result == "approved":
                state = "approved"
            elif task.result == "rejected":
                state = "rejected"
            else:
                # 有待办任务:整单已结束(被前面驳回)则视为未进行,否则为当前步
                state = "skipped" if inst.status == "rejected" else "current"
            approver_name = (names.get(task.approver_employee_id, "")
                             if task.approver_employee_id else "")
            chain.append(schemas.InstanceStepOut(
                step_no=s.step_no, name=s.name or f"第{s.step_no}步",
                approver_type=s.approver_type,
                approver_name=approver_name or f"({approver_label})",
                state=state, comment=task.comment, acted_at=task.acted_at,
                is_current=(state == "current")))
        else:
            # 尚未生成任务的后续步骤:预计审批人 + 待审批/未进行
            expect_id = workflow_svc.resolve_approver(db, s, inst.applicant_employee_id)
            expect_name = names.get(expect_id, "") if expect_id else ""
            state = "skipped" if reached_end else "upcoming"
            chain.append(schemas.InstanceStepOut(
                step_no=s.step_no, name=s.name or f"第{s.step_no}步",
                approver_type=s.approver_type,
                approver_name=(f"{expect_name}(预计)" if expect_name
                               else f"预计:{approver_label}"),
                state=state))
    return chain


@router.post("/instances", response_model=schemas.InstanceOut, status_code=201)
def submit_instance(payload: schemas.InstanceSubmit, db: Session = Depends(get_db)):
    d = db.scalar(select(models.WorkflowDefinition)
                  .where(models.WorkflowDefinition.id == payload.definition_id)
                  .options(selectinload(models.WorkflowDefinition.steps)))
    if d is None:
        raise HTTPException(status_code=400, detail="流程定义不存在")
    if not d.steps:
        raise HTTPException(status_code=400, detail="流程未配置步骤")
    inst = workflow_svc.create_instance(db, payload, d)
    db.commit()
    return get_instance(inst.id, db)


@router.get("/instances", response_model=list[schemas.InstanceOut])
def list_instances(
    biz_type: str | None = None, status: str | None = None,
    biz_id: int | None = None, db: Session = Depends(get_db),
):
    stmt = (select(models.WorkflowInstance).order_by(models.WorkflowInstance.id.desc())
            .options(selectinload(models.WorkflowInstance.tasks)))
    if biz_type:
        stmt = stmt.where(models.WorkflowInstance.biz_type == biz_type)
    if status:
        stmt = stmt.where(models.WorkflowInstance.status == status)
    if biz_id is not None:
        stmt = stmt.where(models.WorkflowInstance.biz_id == biz_id)
    return [_instance_out(db, i) for i in db.scalars(stmt).all()]


@router.get("/instances/{inst_id}", response_model=schemas.InstanceOut)
def get_instance(inst_id: int, db: Session = Depends(get_db)):
    inst = db.scalar(select(models.WorkflowInstance)
                     .where(models.WorkflowInstance.id == inst_id)
                     .options(selectinload(models.WorkflowInstance.tasks)))
    if inst is None:
        raise HTTPException(status_code=404, detail="流程实例不存在")
    return _instance_out(db, inst)


@router.get("/my-tasks", response_model=list[schemas.InstanceOut])
def my_tasks(employee_id: int = Query(...), pending: bool = True, db: Session = Depends(get_db)):
    """某员工的待办(待其审批的实例)。"""
    tq = select(models.WorkflowTask.instance_id).where(
        models.WorkflowTask.approver_employee_id == employee_id)
    if pending:
        tq = tq.where(models.WorkflowTask.result == "pending")
    inst_ids = set(db.scalars(tq).all())
    if not inst_ids:
        return []
    stmt = (select(models.WorkflowInstance)
            .where(models.WorkflowInstance.id.in_(inst_ids),
                   models.WorkflowInstance.status == "pending")
            .order_by(models.WorkflowInstance.id.desc())
            .options(selectinload(models.WorkflowInstance.tasks)))
    return [_instance_out(db, i) for i in db.scalars(stmt).all()]


@router.post("/tasks/{task_id}/approve", response_model=schemas.InstanceOut)
def approve_task(task_id: int, payload: schemas.TaskAction, db: Session = Depends(get_db)):
    return _act(task_id, True, payload.comment, db)


@router.post("/tasks/{task_id}/reject", response_model=schemas.InstanceOut)
def reject_task(task_id: int, payload: schemas.TaskAction, db: Session = Depends(get_db)):
    return _act(task_id, False, payload.comment, db)


def _act(task_id: int, approve: bool, comment: str, db: Session) -> schemas.InstanceOut:
    task = db.get(models.WorkflowTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="待办不存在")
    if task.result != "pending":
        raise HTTPException(status_code=409, detail="该待办已处理")
    workflow_svc.act(db, task, approve, comment)
    db.commit()
    return get_instance(task.instance_id, db)


@router.get("/meta")
def workflow_meta():
    return {"approver_types": APPROVER_TYPES, "biz_types": BIZ_TYPES, "status": STATUS_LABEL}


@router.get("/approver-check")
def approver_check(db: Session = Depends(get_db)):
    """审批人就绪自检:是否有『管理层』员工、启用流程里哪些步骤解析不到审批人。"""
    mgmt_count = db.scalar(
        select(func.count(func.distinct(models.EmployeePosition.employee_id)))
        .where(models.EmployeePosition.role_type == "management")) or 0
    names = _emp_names(db)
    defs = db.scalars(
        select(models.WorkflowDefinition)
        .where(models.WorkflowDefinition.is_active.is_(True))
        .order_by(models.WorkflowDefinition.id)
        .options(selectinload(models.WorkflowDefinition.steps))).all()
    problems: list[dict] = []
    for d in defs:
        missing = []
        for s in d.steps:
            approver_id = workflow_svc.resolve_approver(db, s, None)
            if not approver_id or approver_id not in names:
                missing.append({"step_no": s.step_no, "name": s.name or f"第{s.step_no}步",
                                "approver_type": s.approver_type,
                                "approver_type_label": APPROVER_TYPES.get(s.approver_type, s.approver_type)})
        if missing:
            problems.append({"id": d.id, "name": d.name, "biz_type": d.biz_type,
                             "biz_type_label": BIZ_TYPES.get(d.biz_type, d.biz_type),
                             "missing_steps": missing})
    return {"management_count": mgmt_count, "has_management": mgmt_count > 0,
            "ready": not problems, "problems": problems}
