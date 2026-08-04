"""审批流程服务:审批人解析、发起实例、审批推进。"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def resolve_approver(db: Session, step: models.WorkflowStep,
                     applicant_id: int | None) -> int | None:
    """把步骤的审批人配置解析为具体员工 id。"""
    t = step.approver_type
    if t == "employee":
        return step.approver_employee_id
    if t == "role":
        row = db.scalar(
            select(models.EmployeePosition.employee_id)
            .where(models.EmployeePosition.role_type == (step.approver_role or "management"))
            .limit(1))
        return row
    if t == "department_head":
        # 申请人所在部门的管理层;取不到则任一管理层
        emp_unit = None
        if applicant_id:
            emp_unit = db.scalar(
                select(models.EmployeePosition.org_unit_id)
                .where(models.EmployeePosition.employee_id == applicant_id).limit(1))
        q = select(models.EmployeePosition.employee_id).where(
            models.EmployeePosition.role_type == "management")
        if emp_unit:
            q = q.where(models.EmployeePosition.org_unit_id == emp_unit)
        return db.scalar(q.limit(1))
    # any:任一管理层
    return db.scalar(
        select(models.EmployeePosition.employee_id)
        .where(models.EmployeePosition.role_type == "management").limit(1))


def create_instance(db: Session, sub, definition: models.WorkflowDefinition
                    ) -> models.WorkflowInstance:
    """发起流程实例并生成第一步待办。"""
    inst = models.WorkflowInstance(
        definition_id=definition.id, biz_type=sub.biz_type, biz_id=sub.biz_id,
        title=sub.title, applicant_employee_id=sub.applicant_employee_id,
        status="pending", current_step_no=1,
    )
    db.add(inst)
    db.flush()
    first = definition.steps[0]
    db.add(models.WorkflowTask(
        instance_id=inst.id, step_no=first.step_no, step_name=first.name or f"第{first.step_no}步",
        approver_employee_id=resolve_approver(db, first, sub.applicant_employee_id),
        result="pending",
    ))
    db.flush()
    return inst


def act(db: Session, task: models.WorkflowTask, approve: bool, comment: str) -> None:
    """处理一条待办:通过则推进下一步或结束,驳回则整单驳回。"""
    inst = db.get(models.WorkflowInstance, task.instance_id)
    task.result = "approved" if approve else "rejected"
    task.comment = comment
    task.acted_at = datetime.now()
    if not approve:
        inst.status = "rejected"
        db.flush()
        return
    steps = db.scalars(
        select(models.WorkflowStep)
        .where(models.WorkflowStep.definition_id == inst.definition_id)
        .order_by(models.WorkflowStep.step_no)).all()
    idx = next((i for i, s in enumerate(steps) if s.step_no == task.step_no), 0)
    if idx + 1 < len(steps):
        nxt = steps[idx + 1]
        inst.current_step_no = nxt.step_no
        db.add(models.WorkflowTask(
            instance_id=inst.id, step_no=nxt.step_no,
            step_name=nxt.name or f"第{nxt.step_no}步",
            approver_employee_id=resolve_approver(db, nxt, inst.applicant_employee_id),
            result="pending"))
    else:
        inst.status = "approved"
    db.flush()
