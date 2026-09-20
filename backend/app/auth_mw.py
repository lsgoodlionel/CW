"""鉴权中间件:全站强制登录 + 按路径的权限校验。超管放行一切。"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import auth_svc, models
from .config import settings
from .database import SessionLocal

# 无需登录即可访问
_OPEN = {"/api/health", "/api/auth/login"}


def _resolve_user(request: Request):
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        raw = auth[7:].strip()
    else:
        # 附件预览/下载等由浏览器直接发起(img/iframe/a),无法带 Authorization 头,
        # 允许通过 ?token= 传令牌;令牌仍经同一校验。
        raw = request.query_params.get("token", "")
    if not raw:
        return None
    uid = auth_svc.parse_token(raw)
    if uid is None:
        return None
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


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method
        if method == "OPTIONS" or not path.startswith("/api") or path in _OPEN:
            return await call_next(request)

        user = _resolve_user(request)
        request.state.user = user

        if settings.require_auth and user is None:
            return JSONResponse({"detail": "未登录或登录已过期"}, status_code=401)

        # 设置租户上下文:私有化恒为默认租户;SaaS 取会话选定租户(token 携带,阶段二完善)。
        from .config import is_saas, DEFAULT_TENANT_ID
        from . import tenant as tenant_ctx
        if not is_saas():
            tenant_ctx.set_current_tenant(DEFAULT_TENANT_ID)
        else:
            # 阶段二:从签名令牌解析选定租户并校验成员关系;当前占位为默认租户
            tid = getattr(request.state, "tenant_id", None) or DEFAULT_TENANT_ID
            tenant_ctx.set_current_tenant(tid)

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
