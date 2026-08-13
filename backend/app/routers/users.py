"""用户与角色权限管理 API(用户模块 + RBAC + 超管授权)。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, auth_svc
from ..schemas_read import CreatedOut, RoleOut, SuccessOut, UserOut
from ..auth_mw import current_user

router = APIRouter(tags=["users"])


# ---------- 用户 ----------
class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6)
    display_name: str = ""
    employee_id: int | None = None
    is_super_admin: bool = False
    role_ids: list[int] = []


class UserUpdate(BaseModel):
    display_name: str | None = None
    employee_id: int | None = None
    is_active: bool | None = None
    is_super_admin: bool | None = None
    role_ids: list[int] | None = None


class ResetPwIn(BaseModel):
    new_password: str = Field(min_length=6)


def _require_super(request: Request):
    u = current_user(request)
    if u is None or not u.is_super_admin:
        raise HTTPException(status_code=403, detail="仅超级管理员可执行此操作")


def _user_out(u: models.User) -> dict:
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name,
        "employee_id": u.employee_id, "is_super_admin": u.is_super_admin,
        "is_active": u.is_active, "role_ids": [r.id for r in u.roles],
        "role_names": [r.name for r in u.roles],
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _set_roles(db: Session, user: models.User, role_ids: list[int]) -> None:
    db.execute(delete(models.UserRole).where(models.UserRole.user_id == user.id))
    for rid in role_ids:
        if db.get(models.Role, rid):
            db.add(models.UserRole(user_id=user.id, role_id=rid))


@router.get("/api/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return [_user_out(u) for u in db.scalars(select(models.User).order_by(models.User.id)).all()]


@router.post("/api/users", status_code=201, response_model=UserOut)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    if db.scalar(select(models.User).where(models.User.username == payload.username)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    if payload.is_super_admin:
        _require_super(request)
    user = models.User(
        username=payload.username, display_name=payload.display_name,
        password_hash=auth_svc.hash_password(payload.password),
        employee_id=payload.employee_id, is_super_admin=payload.is_super_admin,
        is_active=True)
    db.add(user)
    db.flush()
    _set_roles(db, user, payload.role_ids)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.put("/api/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = payload.model_dump(exclude_unset=True)
    if "is_super_admin" in data and data["is_super_admin"] is not None:
        _require_super(request)
        # 不允许取消最后一个超管
        if not data["is_super_admin"] and user.is_super_admin:
            cnt = db.scalar(select(models.User).where(models.User.is_super_admin.is_(True)))
            supers = db.scalars(select(models.User.id).where(models.User.is_super_admin.is_(True))).all()
            if len(supers) <= 1:
                raise HTTPException(status_code=400, detail="至少保留一个超级管理员")
        user.is_super_admin = data["is_super_admin"]
    for f in ("display_name", "employee_id", "is_active"):
        if f in data and data[f] is not None:
            setattr(user, f, data[f])
    if data.get("role_ids") is not None:
        _set_roles(db, user, data["role_ids"])
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/api/users/{user_id}/reset-password", response_model=SuccessOut)
def reset_password(user_id: int, payload: ResetPwIn, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = auth_svc.hash_password(payload.new_password)
    db.commit()
    return {"success": True}


@router.delete("/api/users/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.username == "admin":
        raise HTTPException(status_code=400, detail="内置超管 admin 不可删除")
    db.delete(user)
    db.commit()


# ---------- 角色 ----------
class RoleIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    note: str = ""
    perms: list[str] = []


@router.get("/api/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(models.Role).order_by(models.Role.id)).all():
        out.append({"id": r.id, "name": r.name, "note": r.note, "is_system": r.is_system,
                    "perms": sorted(p.perm for p in r.permissions)})
    return out


@router.post("/api/roles", status_code=201, response_model=CreatedOut)
def create_role(payload: RoleIn, db: Session = Depends(get_db)):
    if db.scalar(select(models.Role).where(models.Role.name == payload.name)):
        raise HTTPException(status_code=409, detail="角色名已存在")
    role = models.Role(name=payload.name, note=payload.note)
    for p in payload.perms:
        role.permissions.append(models.RolePermission(perm=p))
    db.add(role)
    db.commit()
    return {"id": role.id}


@router.put("/api/roles/{role_id}", response_model=SuccessOut)
def update_role(role_id: int, payload: RoleIn, db: Session = Depends(get_db)):
    role = db.get(models.Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    role.name, role.note = payload.name, payload.note
    role.permissions.clear()
    for p in payload.perms:
        role.permissions.append(models.RolePermission(perm=p))
    db.commit()
    return {"success": True}


@router.delete("/api/roles/{role_id}", status_code=204)
def delete_role(role_id: int, db: Session = Depends(get_db)):
    role = db.get(models.Role, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    db.delete(role)
    db.commit()
