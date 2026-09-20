"""平台管理 API(仅平台超级管理员):跨租户开通/停用/改名租户、管理租户成员。

- 全部端点要求 request.state.user.is_super_admin,否则 403。
- 租户与成员关系(Tenant/TenantMembership/User)均非 TenantMixin,不受租户 SELECT 过滤,
  故超管在此可跨租户操作;新建租户后调用 tenant_provision 预置基础数据。
- 说明:企业信息(CompanyInfo)当前为 id=1 单例,未随租户开通预置,属已知遗留待后续重构。
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, auth_svc
from ..schemas_read import TenantOut, TenantMemberOut, SuccessOut
from ..tenant import set_current_tenant
from ..tenant_provision import provision_tenant

router = APIRouter(prefix="/api/platform", tags=["platform"])


def require_super_admin(request: Request) -> models.User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    if not user.is_super_admin:
        raise HTTPException(status_code=403, detail="仅平台超级管理员可访问")
    return user


class TenantCreateIn(BaseModel):
    name: str
    code: str = ""
    note: str = ""
    admin_username: str | None = None
    admin_password: str | None = None
    admin_display_name: str | None = None


class TenantUpdateIn(BaseModel):
    name: str | None = None
    note: str | None = None
    is_active: bool | None = None


class MemberAddIn(BaseModel):
    username: str
    is_tenant_admin: bool = False
    password: str | None = None          # 新建全局用户时使用
    display_name: str | None = None


class MemberUpdateIn(BaseModel):
    is_tenant_admin: bool


def _member_count(db: Session, tenant_id: int) -> int:
    return db.scalar(select(func.count()).select_from(models.TenantMembership)
                     .where(models.TenantMembership.tenant_id == tenant_id)) or 0


def _tenant_out(db: Session, t: models.Tenant) -> dict:
    return {
        "id": t.id, "name": t.name, "code": t.code, "is_active": t.is_active,
        "note": t.note or "", "created_at": t.created_at.isoformat() if t.created_at else None,
        "member_count": _member_count(db, t.id),
    }


def _member_out(m: models.TenantMembership, u: models.User) -> dict:
    return {
        "id": m.id, "user_id": u.id, "username": u.username,
        "display_name": u.display_name, "is_tenant_admin": m.is_tenant_admin,
    }


# ---------- 租户 ----------
@router.get("/tenants", response_model=list[TenantOut])
def list_tenants(db: Session = Depends(get_db), _: models.User = Depends(require_super_admin)):
    set_current_tenant(None)             # 跨租户视图,不过滤
    tenants = db.scalars(select(models.Tenant).order_by(models.Tenant.id)).all()
    return [_tenant_out(db, t) for t in tenants]


@router.post("/tenants", response_model=TenantOut, status_code=201)
def create_tenant(payload: TenantCreateIn, db: Session = Depends(get_db),
                  _: models.User = Depends(require_super_admin)):
    set_current_tenant(None)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="租户名称不能为空")
    code = payload.code.strip()
    if code and db.scalar(select(models.Tenant).where(models.Tenant.code == code)):
        raise HTTPException(status_code=409, detail=f"租户编码 {code} 已存在")
    tenant = models.Tenant(name=name, code=code, note=payload.note or "", is_active=True)
    db.add(tenant)
    db.flush()                           # 取得 tenant.id

    # 可选:创建/关联租户管理员
    if payload.admin_username:
        uname = payload.admin_username.strip()
        user = db.scalar(select(models.User).where(models.User.username == uname))
        if user is None:
            if not payload.admin_password or len(payload.admin_password) < 6:
                raise HTTPException(status_code=400, detail="新建租户管理员需提供至少 6 位密码")
            user = models.User(
                username=uname,
                display_name=(payload.admin_display_name or uname).strip(),
                password_hash=auth_svc.hash_password(payload.admin_password),
                is_super_admin=False, is_active=True)
            db.add(user)
            db.flush()
        db.add(models.TenantMembership(
            user_id=user.id, tenant_id=tenant.id, is_tenant_admin=True))
    db.commit()

    provision_tenant(db, tenant.id)      # 预置科目/明细/角色/审批流程(自管理租户上下文)
    set_current_tenant(None)
    db.refresh(tenant)
    return _tenant_out(db, tenant)


@router.post("/tenants/{tenant_id}/reprovision", response_model=SuccessOut)
def reprovision_tenant(tenant_id: int, db: Session = Depends(get_db),
                       _: models.User = Depends(require_super_admin)):
    """幂等补齐租户基础数据(科目/明细/角色/流程/企业信息)。用于开通中途失败的补救。"""
    set_current_tenant(None)
    if db.get(models.Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    provision_tenant(db, tenant_id)
    set_current_tenant(None)
    return {"success": True}


@router.put("/tenants/{tenant_id}", response_model=TenantOut)
def update_tenant(tenant_id: int, payload: TenantUpdateIn, db: Session = Depends(get_db),
                  _: models.User = Depends(require_super_admin)):
    set_current_tenant(None)
    tenant = db.get(models.Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        if not data["name"].strip():
            raise HTTPException(status_code=400, detail="租户名称不能为空")
        tenant.name = data["name"].strip()
    if "note" in data and data["note"] is not None:
        tenant.note = data["note"]
    if "is_active" in data and data["is_active"] is not None:
        tenant.is_active = data["is_active"]
    db.commit()
    db.refresh(tenant)
    return _tenant_out(db, tenant)


# ---------- 成员 ----------
@router.get("/tenants/{tenant_id}/members", response_model=list[TenantMemberOut])
def list_members(tenant_id: int, db: Session = Depends(get_db),
                 _: models.User = Depends(require_super_admin)):
    set_current_tenant(None)
    if db.get(models.Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    rows = db.execute(
        select(models.TenantMembership, models.User)
        .join(models.User, models.User.id == models.TenantMembership.user_id)
        .where(models.TenantMembership.tenant_id == tenant_id)
        .order_by(models.TenantMembership.id)
    ).all()
    return [_member_out(m, u) for m, u in rows]


@router.post("/tenants/{tenant_id}/members", response_model=TenantMemberOut, status_code=201)
def add_member(tenant_id: int, payload: MemberAddIn, db: Session = Depends(get_db),
               _: models.User = Depends(require_super_admin)):
    set_current_tenant(None)
    if db.get(models.Tenant, tenant_id) is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    uname = payload.username.strip()
    if not uname:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    user = db.scalar(select(models.User).where(models.User.username == uname))
    if user is None:
        if not payload.password or len(payload.password) < 6:
            raise HTTPException(status_code=400, detail="新建用户需提供至少 6 位密码")
        user = models.User(
            username=uname, display_name=(payload.display_name or uname).strip(),
            password_hash=auth_svc.hash_password(payload.password),
            is_super_admin=False, is_active=True)
        db.add(user)
        db.flush()
    existing = db.scalar(select(models.TenantMembership).where(
        models.TenantMembership.user_id == user.id,
        models.TenantMembership.tenant_id == tenant_id))
    if existing:
        raise HTTPException(status_code=409, detail="该用户已是此租户成员")
    m = models.TenantMembership(
        user_id=user.id, tenant_id=tenant_id, is_tenant_admin=payload.is_tenant_admin)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _member_out(m, user)


@router.put("/members/{membership_id}", response_model=TenantMemberOut)
def update_member(membership_id: int, payload: MemberUpdateIn, db: Session = Depends(get_db),
                  _: models.User = Depends(require_super_admin)):
    set_current_tenant(None)
    m = db.get(models.TenantMembership, membership_id)
    if m is None:
        raise HTTPException(status_code=404, detail="成员关系不存在")
    m.is_tenant_admin = payload.is_tenant_admin
    db.commit()
    db.refresh(m)
    user = db.get(models.User, m.user_id)
    return _member_out(m, user)


@router.delete("/members/{membership_id}", status_code=204)
def remove_member(membership_id: int, db: Session = Depends(get_db),
                  _: models.User = Depends(require_super_admin)):
    set_current_tenant(None)
    m = db.get(models.TenantMembership, membership_id)
    if m is None:
        raise HTTPException(status_code=404, detail="成员关系不存在")
    db.delete(m)
    db.commit()
