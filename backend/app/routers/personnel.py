"""人员管理 API:组织架构(多级)+ 员工档案。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..schemas_read import PersonnelMetaOut
from .. import models, schemas

router = APIRouter(prefix="/api/personnel", tags=["personnel"])

ROLE_TYPES = {
    "shareholder": "股东", "management": "管理层", "staff": "普通员工", "other": "其他",
}
PARTY_LABEL = {
    "enterprise": "企业客户", "individual": "个人客户",
    "supplier": "供应商", "partner": "往来单位",
}


# ---------- 组织架构 ----------
@router.get("/org-units", response_model=list[schemas.OrgUnitOut])
def list_org_units(db: Session = Depends(get_db)):
    units = db.scalars(
        select(models.OrgUnit).order_by(models.OrgUnit.sort_no, models.OrgUnit.id)
    ).all()
    counts = dict(db.execute(
        select(models.EmployeePosition.org_unit_id,
               func.count(func.distinct(models.EmployeePosition.employee_id)))
        .group_by(models.EmployeePosition.org_unit_id)
    ).all())
    out = []
    for u in units:
        item = schemas.OrgUnitOut.model_validate(u)
        item.employee_count = counts.get(u.id, 0)
        out.append(item)
    return out


@router.post("/org-units", response_model=schemas.OrgUnitOut, status_code=201)
def create_org_unit(payload: schemas.OrgUnitCreate, db: Session = Depends(get_db)):
    if payload.parent_id and db.get(models.OrgUnit, payload.parent_id) is None:
        raise HTTPException(status_code=400, detail="上级部门不存在")
    nxt = (db.scalar(select(func.coalesce(func.max(models.OrgUnit.sort_no), 0))) or 0) + 1
    unit = models.OrgUnit(name=payload.name, parent_id=payload.parent_id,
                          note=payload.note, sort_no=nxt)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@router.put("/org-units/{unit_id}", response_model=schemas.OrgUnitOut)
def update_org_unit(
    unit_id: int, payload: schemas.OrgUnitUpdate, db: Session = Depends(get_db)
):
    unit = db.get(models.OrgUnit, unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="部门不存在")
    if payload.parent_id == unit_id:
        raise HTTPException(status_code=400, detail="上级部门不能是自己")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)
    db.commit()
    db.refresh(unit)
    return unit


@router.delete("/org-units/{unit_id}", status_code=204)
def delete_org_unit(unit_id: int, db: Session = Depends(get_db)):
    unit = db.get(models.OrgUnit, unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="部门不存在")
    has_child = db.scalar(select(models.OrgUnit.id).where(
        models.OrgUnit.parent_id == unit_id).limit(1))
    if has_child:
        raise HTTPException(status_code=400, detail="请先删除下级部门")
    db.delete(unit)  # 员工 org_unit_id 置空(SET NULL)
    db.commit()


# ---------- 员工档案(支持一人多岗兼职)----------
def _unit_names(db: Session) -> dict[int, str]:
    return {u.id: u.name for u in db.scalars(select(models.OrgUnit)).all()}


def _employee_out(e: models.Employee, unit_names: dict[int, str]) -> schemas.EmployeeOut:
    item = schemas.EmployeeOut.model_validate(e)
    for p, po in zip(e.positions, item.positions):
        po.org_unit_name = unit_names.get(p.org_unit_id, "") if p.org_unit_id else ""
    return item


def _apply_positions(db: Session, emp: models.Employee, positions) -> None:
    emp.positions.clear()
    for i, p in enumerate(positions, start=1):
        if p.org_unit_id and db.get(models.OrgUnit, p.org_unit_id) is None:
            raise HTTPException(status_code=400, detail="任职部门不存在")
        emp.positions.append(models.EmployeePosition(
            org_unit_id=p.org_unit_id, role_type=p.role_type,
            position=p.position, sort_no=i))


@router.get("/employees", response_model=list[schemas.EmployeeOut])
def list_employees(
    keyword: str | None = None,
    role_type: str | None = None,
    org_unit_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = (select(models.Employee).order_by(models.Employee.employee_no,
                                             models.Employee.id)
            .options(selectinload(models.Employee.positions)))
    if status:
        stmt = stmt.where(models.Employee.status == status)
    # 按部门/角色筛选:存在满足条件的任职记录
    if org_unit_id or role_type:
        pos = select(models.EmployeePosition.employee_id)
        if org_unit_id:
            pos = pos.where(models.EmployeePosition.org_unit_id == org_unit_id)
        if role_type:
            pos = pos.where(models.EmployeePosition.role_type == role_type)
        stmt = stmt.where(models.Employee.id.in_(pos))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(models.Employee.name.ilike(like)
                          | models.Employee.employee_no.ilike(like)
                          | models.Employee.phone.ilike(like))
    names = _unit_names(db)
    return [_employee_out(e, names) for e in db.scalars(stmt).all()]


@router.post("/employees", response_model=schemas.EmployeeOut, status_code=201)
def create_employee(payload: schemas.EmployeeCreate, db: Session = Depends(get_db)):
    fields = payload.model_dump(exclude={"positions"})
    emp = models.Employee(**fields)
    _apply_positions(db, emp, payload.positions)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _employee_out(emp, _unit_names(db))


@router.put("/employees/{emp_id}", response_model=schemas.EmployeeOut)
def update_employee(
    emp_id: int, payload: schemas.EmployeeUpdate, db: Session = Depends(get_db)
):
    emp = db.get(models.Employee, emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="员工不存在")
    data = payload.model_dump(exclude_unset=True, exclude={"positions"})
    for field, value in data.items():
        setattr(emp, field, value)
    if payload.positions is not None:
        _apply_positions(db, emp, payload.positions)
    db.commit()
    db.refresh(emp)
    return _employee_out(emp, _unit_names(db))


@router.delete("/employees/{emp_id}", status_code=204)
def delete_employee(emp_id: int, db: Session = Depends(get_db)):
    emp = db.get(models.Employee, emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="员工不存在")
    db.delete(emp)
    db.commit()


@router.post("/org-units/{unit_id}/members", response_model=schemas.EmployeeOut, status_code=201)
def add_member(
    unit_id: int, payload: schemas.AddMemberIn, db: Session = Depends(get_db)
):
    """向部门添加成员:选已有员工则新增一条任职;否则新建员工并任职。"""
    if db.get(models.OrgUnit, unit_id) is None:
        raise HTTPException(status_code=404, detail="部门不存在")
    if payload.employee_id:
        emp = db.get(models.Employee, payload.employee_id)
        if emp is None:
            raise HTTPException(status_code=404, detail="员工不存在")
    else:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="请填写员工姓名或选择已有员工")
        emp = models.Employee(name=payload.name.strip())
        db.add(emp)
        db.flush()
    nxt = (max((p.sort_no for p in emp.positions), default=0)) + 1
    emp.positions.append(models.EmployeePosition(
        org_unit_id=unit_id, role_type=payload.role_type,
        position=payload.position, sort_no=nxt))
    db.commit()
    db.refresh(emp)
    return _employee_out(emp, _unit_names(db))


@router.get("/meta", response_model=PersonnelMetaOut)
def personnel_meta():
    """人员/往来单位的枚举标签。"""
    return {"role_types": ROLE_TYPES, "party_types": PARTY_LABEL}
