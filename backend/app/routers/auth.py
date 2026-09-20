"""认证 API:登录、当前用户信息、修改密码。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, auth_svc, subscription
from ..config import is_saas, DEFAULT_TENANT_ID, settings
from ..tenant import set_current_tenant
from ..schemas_read import (
    AuthUserOut, LoginOut, PermissionModuleOut, SuccessOut,
)
from ..auth_mw import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str
    tenant_id: int | None = None        # 多租户:会话选定的租户(私有化忽略)


class ChangePwIn(BaseModel):
    old_password: str
    new_password: str


def _memberships(db: Session, user: models.User) -> list[tuple[models.Tenant, bool]]:
    """返回用户可登录的(启用中)租户列表及其是否为该租户管理员。"""
    rows = db.execute(
        select(models.Tenant, models.TenantMembership.is_tenant_admin)
        .join(models.TenantMembership,
              models.TenantMembership.tenant_id == models.Tenant.id)
        .where(models.TenantMembership.user_id == user.id,
               models.Tenant.is_active.is_(True))
        .order_by(models.Tenant.id)
    ).all()
    return [(t, bool(admin)) for t, admin in rows]


def _user_info(db: Session, user: models.User, tenant_id: int | None,
               is_tenant_admin: bool = False) -> dict:
    # 权限依赖 user.roles,后者按当前租户过滤——调用前须已 set_current_tenant(tenant_id)
    perms = ["*"] if user.is_super_admin else sorted(auth_svc.user_perms(user))
    tenant = db.get(models.Tenant, tenant_id) if tenant_id else None
    return {
        "id": user.id, "username": user.username, "display_name": user.display_name,
        "is_super_admin": user.is_super_admin,
        "employee_id": user.employee_id,
        "roles": [r.name for r in user.roles],
        "permissions": perms,
        "tenant_id": tenant_id,
        "tenant_name": tenant.name if tenant else None,
        "is_tenant_admin": is_tenant_admin,
    }


def _issue(db: Session, user: models.User, tenant_id: int, is_tenant_admin: bool) -> dict:
    """在指定租户上下文内签发令牌并返回用户信息。"""
    # SaaS 订阅管控:非超管登录到期/停用租户直接拒绝(超管豁免,可进后台处理)
    if is_saas() and not user.is_super_admin:
        reason = subscription.usable_reason(db.get(models.Tenant, tenant_id))
        if reason is not None:
            raise HTTPException(status_code=403, detail=reason)
    set_current_tenant(tenant_id)        # 使 user.roles/权限按该租户过滤
    db.refresh(user)                     # 重新加载 roles(应用租户过滤)
    token = auth_svc.make_token(user.id, tenant_id)
    return {"token": token, "user": _user_info(db, user, tenant_id, is_tenant_admin),
            "need_tenant": False, "tenants": []}


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.username == payload.username))
    if user is None or not user.is_active or not auth_svc.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 私有化:恒为默认租户,前端无需选择
    if not is_saas():
        return _issue(db, user, DEFAULT_TENANT_ID, bool(user.is_super_admin))

    # SaaS:按成员关系解析/选择租户
    members = _memberships(db, user)
    admin_map = {t.id: adm for t, adm in members}

    # 平台超管:无成员关系时允许进入(可指定租户,否则默认租户)——跨租户管理属阶段三
    if user.is_super_admin and not members:
        tid = payload.tenant_id or DEFAULT_TENANT_ID
        if db.get(models.Tenant, tid) is None:
            raise HTTPException(status_code=400, detail="指定租户不存在")
        return _issue(db, user, tid, True)

    if not members:
        raise HTTPException(status_code=403, detail="该账号未分配任何租户,请联系管理员")

    if payload.tenant_id is not None:
        if payload.tenant_id not in admin_map:
            raise HTTPException(status_code=403, detail="无权登录所选租户")
        return _issue(db, user, payload.tenant_id, admin_map[payload.tenant_id])

    if len(members) == 1:
        t, adm = members[0]
        return _issue(db, user, t.id, adm)

    # 多个可选租户:返回列表,前端选择后携带 tenant_id 重新登录
    return {
        "token": None, "user": None, "need_tenant": True,
        "tenants": [{"id": t.id, "name": t.name, "code": t.code,
                     "is_tenant_admin": adm} for t, adm in members],
    }


class RegisterIn(BaseModel):
    tenant_name: str
    username: str
    password: str
    display_name: str = ""


@router.get("/register-open", response_model=SuccessOut)
def register_open():
    """前端探测:当前是否开放自助注册(saas 且开关开启)。"""
    return {"success": is_saas() and settings.allow_self_registration}


@router.post("/register", response_model=LoginOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """自助注册:开通新租户 + 管理员账号,进入试用期并自动登录。仅 saas 且开关开启。"""
    from datetime import date, timedelta
    from ..tenant_provision import provision_tenant
    if not (is_saas() and settings.allow_self_registration):
        raise HTTPException(status_code=403, detail="当前未开放自助注册")
    tenant_name = payload.tenant_name.strip()
    uname = payload.username.strip()
    if not tenant_name:
        raise HTTPException(status_code=400, detail="企业/租户名称不能为空")
    if len(uname) < 2:
        raise HTTPException(status_code=400, detail="用户名至少 2 位")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if db.scalar(select(models.User).where(models.User.username == uname)):
        raise HTTPException(status_code=409, detail="用户名已存在")

    set_current_tenant(None)
    expires = (date.today() + timedelta(days=settings.trial_days)).isoformat()
    tenant = models.Tenant(name=tenant_name, code="", is_active=True,
                           plan="trial", status="trial", expires_at=expires, max_users=0)
    db.add(tenant)
    db.flush()
    admin = models.User(
        username=uname, display_name=(payload.display_name or uname).strip(),
        password_hash=auth_svc.hash_password(payload.password),
        is_super_admin=False, is_active=True)
    db.add(admin)
    db.flush()
    db.add(models.TenantMembership(user_id=admin.id, tenant_id=tenant.id, is_tenant_admin=True))
    db.commit()
    provision_tenant(db, tenant.id)      # 预置科目/明细/角色/流程/企业信息
    set_current_tenant(None)
    db.refresh(admin)
    return _issue(db, admin, tenant.id, True)


@router.get("/me", response_model=AuthUserOut)
def me(request: Request, db: Session = Depends(get_db)):
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    fresh = db.get(models.User, user.id)
    tid = getattr(request.state, "tenant_id", None)
    is_admin = False
    if tid is not None and not fresh.is_super_admin:
        m = db.scalar(select(models.TenantMembership.is_tenant_admin).where(
            models.TenantMembership.user_id == fresh.id,
            models.TenantMembership.tenant_id == tid))
        is_admin = bool(m)
    elif fresh.is_super_admin:
        is_admin = True
    return _user_info(db, fresh, tid, is_admin)


@router.post("/change-password", response_model=SuccessOut)
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


@router.get("/permission-catalog", response_model=list[PermissionModuleOut])
def permission_catalog():
    return auth_svc.catalog()
