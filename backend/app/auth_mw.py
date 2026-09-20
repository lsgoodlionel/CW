"""鉴权中间件:全站强制登录 + 按路径的权限校验。超管放行一切。"""
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import auth_svc, models
from .config import settings
from .database import SessionLocal

# 无需登录即可访问
_OPEN = {"/api/health", "/api/auth/login", "/api/auth/register", "/api/auth/register-open"}


def _token_from_request(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # 附件预览/下载等由浏览器直接发起(img/iframe/a),无法带 Authorization 头,
    # 允许通过 ?token= 传令牌;令牌仍经同一校验。
    return request.query_params.get("token", "")


def _load_user(uid: int):
    """在当前租户上下文内加载用户及其角色/权限(角色按租户过滤)。"""
    db = SessionLocal()
    try:
        user = db.get(models.User, uid)
        if user is None or not user.is_active:
            return None
        # 触发加载 roles/permissions(lazy selectin)后 expunge,供中间件与下游使用
        _ = [(r.id, [p.perm for p in r.permissions]) for r in user.roles]
        db.expunge(user)
        return user
    finally:
        db.close()


def _has_membership(uid: int, tid: int) -> bool:
    db = SessionLocal()
    try:
        return db.scalar(select(models.TenantMembership.id).where(
            models.TenantMembership.user_id == uid,
            models.TenantMembership.tenant_id == tid)) is not None
    finally:
        db.close()


def _tenant_block_reason(tid: int) -> str | None:
    """租户到期/停用时返回拦截原因(可用返回 None)。"""
    from . import subscription
    db = SessionLocal()
    try:
        return subscription.usable_reason(db.get(models.Tenant, tid))
    finally:
        db.close()


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        if method == "OPTIONS" or not path.startswith("/api") or path in _OPEN:
            return await call_next(request)

        from .config import is_saas, DEFAULT_TENANT_ID
        from . import tenant as tenant_ctx

        # 1) 先解析令牌得到 uid 与令牌内选定租户 tid
        raw = _token_from_request(request)
        payload = auth_svc.parse_token_payload(raw) if raw else None
        uid = int(payload["uid"]) if payload else None
        token_tid = payload.get("tid") if payload else None

        # 2) 确定并设置当前租户上下文(须在加载角色之前,使角色/权限按租户过滤)
        if not is_saas():
            tid = DEFAULT_TENANT_ID
        else:
            tid = token_tid                # SaaS 恒以令牌携带的租户为准(缺失→None→未授权)
        request.state.tenant_id = tid
        tenant_ctx.set_current_tenant(tid)

        # 3) 加载用户(角色已按租户过滤),并在 SaaS 下校验成员关系
        user = _load_user(uid) if uid is not None else None
        if user is not None and is_saas():
            if not user.is_super_admin and (tid is None or not _has_membership(uid, tid)):
                user = None                # 令牌未选租户或非该租户成员 → 视为未授权
        request.state.user = user

        if settings.require_auth and user is None:
            return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)

        # 3b) SaaS 订阅管控:租户到期/停用则拦截(超管豁免)
        if user is not None and is_saas() and not user.is_super_admin and tid is not None:
            reason = _tenant_block_reason(tid)
            if reason is not None:
                return JSONResponse({"detail": reason}, status_code=403)

        if user is not None and not user.is_super_admin:
            need = auth_svc.classify_perm(method, path)
            if need is not None:
                module, action = need
                if not auth_svc.user_has(user, module, action):
                    return JSONResponse(
                        {"detail": f"无权限:{auth_svc.MODULES.get(module, module)}·"
                                   f"{auth_svc.ACTIONS.get(action, action)}"},
                        status_code=403)
        return await call_next(request)


def current_user(request: Request):
    """FastAPI 依赖:取当前登录用户(中间件已解析)。"""
    return getattr(request.state, "user", None)
