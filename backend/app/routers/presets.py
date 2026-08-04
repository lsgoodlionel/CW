"""授权预设 API:按部门 + 员工角色预设系统角色,并可单个填充/批量应用。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models
from .personnel import ROLE_TYPES

router = APIRouter(prefix="/api/auth-presets", tags=["auth-presets"])


class PresetIn(BaseModel):
    org_unit_id: int | None = None
    emp_role_type: str = ""
    role_id: int
    note: str = ""


def _resolve_role_ids(db: Session, employee_id: int) -> list[int]:
    """按员工的任职(部门+职位角色)匹配预设,返回应授予的系统角色 id(去重)。"""
    positions = db.execute(
        select(models.EmployeePosition.org_unit_id, models.EmployeePosition.role_type)
        .where(models.EmployeePosition.employee_id == employee_id)).all()
    presets = db.scalars(select(models.AuthPreset)).all()
    role_ids: set[int] = set()
    for unit_id, role_type in positions:
        for p in presets:
            if p.org_unit_id is not None and p.org_unit_id != unit_id:
                continue
            if p.emp_role_type and p.emp_role_type != role_type:
                continue
            role_ids.add(p.role_id)
    return sorted(role_ids)


@router.get("")
def list_presets(db: Session = Depends(get_db)):
    units = {u.id: u.name for u in db.scalars(select(models.OrgUnit)).all()}
    roles = {r.id: r.name for r in db.scalars(select(models.Role)).all()}
    out = []
    for p in db.scalars(select(models.AuthPreset).order_by(models.AuthPreset.id)).all():
        out.append({
            "id": p.id, "org_unit_id": p.org_unit_id,
            "org_unit_name": units.get(p.org_unit_id, "全部部门") if p.org_unit_id else "全部部门",
            "emp_role_type": p.emp_role_type,
            "emp_role_label": ROLE_TYPES.get(p.emp_role_type, "全部职位") if p.emp_role_type else "全部职位",
            "role_id": p.role_id, "role_name": roles.get(p.role_id, ""), "note": p.note,
        })
    return out


@router.post("", status_code=201)
def create_preset(payload: PresetIn, db: Session = Depends(get_db)):
    if db.get(models.Role, payload.role_id) is None:
        raise HTTPException(status_code=400, detail="系统角色不存在")
    p = models.AuthPreset(**payload.model_dump())
    db.add(p)
    db.commit()
    return {"id": p.id}


@router.put("/{preset_id}")
def update_preset(preset_id: int, payload: PresetIn, db: Session = Depends(get_db)):
    p = db.get(models.AuthPreset, preset_id)
    if p is None:
        raise HTTPException(status_code=404, detail="预设不存在")
    for f, v in payload.model_dump().items():
        setattr(p, f, v)
    db.commit()
    return {"success": True}


@router.delete("/{preset_id}", status_code=204)
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    p = db.get(models.AuthPreset, preset_id)
    if p is None:
        raise HTTPException(status_code=404, detail="预设不存在")
    db.delete(p)
    db.commit()


@router.get("/resolve")
def resolve(employee_id: int = Query(...), db: Session = Depends(get_db)):
    """按预设计算某员工应授予的系统角色(供用户表单一键填充)。"""
    return {"role_ids": _resolve_role_ids(db, employee_id)}


@router.post("/apply")
def apply_presets(db: Session = Depends(get_db)):
    """批量应用:对所有关联了员工的非超管用户,按预设覆盖其角色(无匹配则跳过)。"""
    users = db.scalars(select(models.User).where(
        models.User.employee_id.isnot(None),
        models.User.is_super_admin.is_(False))).all()
    updated = 0
    for u in users:
        role_ids = _resolve_role_ids(db, u.employee_id)
        if not role_ids:
            continue
        db.execute(delete(models.UserRole).where(models.UserRole.user_id == u.id))
        for rid in role_ids:
            db.add(models.UserRole(user_id=u.id, role_id=rid))
        updated += 1
    db.commit()
    return {"updated": updated, "total": len(users)}
