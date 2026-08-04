"""认证 API:登录、当前用户信息、修改密码。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, auth_svc
from ..auth_mw import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePwIn(BaseModel):
    old_password: str
    new_password: str


def _user_info(db: Session, user: models.User) -> dict:
    perms = ["*"] if user.is_super_admin else sorted(auth_svc.user_perms(user))
    return {
        "id": user.id, "username": user.username, "display_name": user.display_name,
        "is_super_admin": user.is_super_admin,
        "employee_id": user.employee_id,
        "roles": [r.name for r in user.roles],
        "permissions": perms,
    }


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.username == payload.username))
    if user is None or not user.is_active or not auth_svc.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth_svc.make_token(user.id)
    return {"token": token, "user": _user_info(db, user)}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    fresh = db.get(models.User, user.id)
    return _user_info(db, fresh)


@router.post("/change-password")
def change_password(payload: ChangePwIn, request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    fresh = db.get(models.User, user.id)
    if not auth_svc.verify_password(payload.old_password, fresh.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    fresh.password_hash = auth_svc.hash_password(payload.new_password)
    db.commit()
    return {"success": True}


@router.get("/permission-catalog")
def permission_catalog():
    return auth_svc.catalog()
