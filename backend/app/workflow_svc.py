"""审批流程服务:审批人解析、发起实例、审批推进。"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


# 审批资格与优先级:股东(董事会)高于管理层,均可审批部门/管理层流程。
APPROVER_ROLES = ("management", "shareholder")


def _first_by_role(db: Session, role_type: str, org_unit_id: int | None = None) -> int | None:
    q = select(models.EmployeePosition.employee_id).where(
        models.EmployeePosition.role_type == role_type)
    if org_unit_id is not None:
        q = q.where(models.EmployeePosition.org_unit_id == org_unit_id)
    return db.scalar(q.limit(1))


def _first_approver(db: Session, org_unit_id: int | None = None,
                    exclude_id: int | None = None) -> int | None:
    """在指定部门(或全局)按 管理层→股东 顺序取一名审批人,可排除申请人本人。"""
    for rt in APPROVER_ROLES:
        q = select(models.EmployeePosition.employee_id).where(
            models.EmployeePosition.role_type == rt)
        if org_unit_id is not None:
            q = q.where(models.EmployeePosition.org_unit_id == org_unit_id)
        if exclude_id is not None:
            q = q.where(models.EmployeePosition.employee_id != exclude_id)
        row = db.scalar(q.limit(1))
        if row:
            return row
    return None


def resolve_approver(db: Session, step: models.WorkflowStep,
                     applicant_id: int | None) -> int | None:
    """把步骤的审批人配置解析为具体员工 id。

    审批资格层级:股东(董事会)高于管理层,二者都可审批部门/管理层步骤。
    - 部门负责人:优先本部门(管理层→股东);本部门无人 / 申请人无部门时,
      回退到全局(管理层→股东),即由股东兜底审批。
    - 任一管理层:全局(管理层→股东)。
    这样董事会股东发起、或系统管理员(无部门)发起时,仍能由股东完成审批。
    """
    t = step.approver_type
    if t == "employee":
        return step.approver_employee_id
    if t == "role":
        # 指定角色精确匹配;取不到则按通用审批资格兜底
        return _first_by_role(db, step.approver_role or "management") or _first_approver(db)
    if t == "department_head":
        emp_unit = None
        if applicant_id:
            emp_unit = db.scalar(
                select(models.EmployeePosition.org_unit_id)
                .where(models.EmployeePosition.employee_id == applicant_id).limit(1))
        if emp_unit is not None:
            in_dept = _first_approver(db, emp_unit, exclude_id=applicant_id)
            if in_dept:
                return in_dept
        # 本部门找不到 / 无部门:回退到全局(股东可审批任何部门流程)
        return _first_approver(db, exclude_id=applicant_id) or _first_approver(db)
    # any:任一管理层(股东亦可,且更高)
    return _first_approver(db)


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
