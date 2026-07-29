"""人员管理 API:组织架构(多级)+ 员工档案。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
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
        select(models.Employee.org_unit_id, func.count(models.Employee.id))
        .group_by(models.Employee.org_unit_id)
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


# ---------- 员工档案 ----------
def _employee_out(e: models.Employee) -> schemas.EmployeeOut:
    item = schemas.EmployeeOut.model_validate(e)
    item.org_unit_name = e.org_unit.name if e.org_unit else ""
    return item


@router.get("/employees", response_model=list[schemas.EmployeeOut])
def list_employees(
    keyword: str | None = None,
    role_type: str | None = None,
    org_unit_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(models.Employee).order_by(models.Employee.employee_no,
                                            models.Employee.id)
    if role_type:
        stmt = stmt.where(models.Employee.role_type == role_type)
    if org_unit_id:
        stmt = stmt.where(models.Employee.org_unit_id == org_unit_id)
    if status:
        stmt = stmt.where(models.Employee.status == status)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(models.Employee.name.ilike(like)
                          | models.Employee.employee_no.ilike(like)
                          | models.Employee.phone.ilike(like))
    return [_employee_out(e) for e in db.scalars(stmt).all()]


@router.post("/employees", response_model=schemas.EmployeeOut, status_code=201)
def create_employee(payload: schemas.EmployeeCreate, db: Session = Depends(get_db)):
    if payload.org_unit_id and db.get(models.OrgUnit, payload.org_unit_id) is None:
        raise HTTPException(status_code=400, detail="所属部门不存在")
    emp = models.Employee(**payload.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _employee_out(emp)


@router.put("/employees/{emp_id}", response_model=schemas.EmployeeOut)
def update_employee(
    emp_id: int, payload: schemas.EmployeeUpdate, db: Session = Depends(get_db)
):
    emp = db.get(models.Employee, emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="员工不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(emp, field, value)
    db.commit()
    db.refresh(emp)
    return _employee_out(emp)


@router.delete("/employees/{emp_id}", status_code=204)
def delete_employee(emp_id: int, db: Session = Depends(get_db)):
    emp = db.get(models.Employee, emp_id)
    if emp is None:
        raise HTTPException(status_code=404, detail="员工不存在")
    db.delete(emp)
    db.commit()


@router.get("/meta")
def personnel_meta():
    """人员/往来单位的枚举标签。"""
    return {"role_types": ROLE_TYPES, "party_types": PARTY_LABEL}
