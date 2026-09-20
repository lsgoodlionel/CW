"""租户订阅/计费判定:到期、停用、用户配额。

约定:
- Tenant.status:trial(试用)/active(有效)/expired(到期)/suspended(停用)。
- Tenant.expires_at:ISO 日期字符串("YYYY-MM-DD"),""=不设到期。
- Tenant.max_users:用户数上限,0=不限。
- 默认租户(私有化 id=1)为 active + 无到期 + 不限,故私有化不受任何限制。
"""
from datetime import date

from sqlalchemy import select, func

from . import models


def usable_reason(tenant: models.Tenant | None) -> str | None:
    """租户不可用时返回原因文案;可用返回 None。"""
    if tenant is None:
        return "租户不存在"
    if not tenant.is_active or tenant.status == "suspended":
        return "租户已停用,请联系平台管理员"
    if tenant.status == "expired":
        return "租户订阅已到期,请续费后使用"
    if tenant.expires_at and tenant.expires_at < date.today().isoformat():
        return "租户订阅已到期,请续费后使用"
    return None


def is_usable(tenant: models.Tenant | None) -> bool:
    return usable_reason(tenant) is None


def user_count(db, tenant_id: int) -> int:
    return db.scalar(select(func.count()).select_from(models.TenantMembership)
                     .where(models.TenantMembership.tenant_id == tenant_id)) or 0


def quota_exceeded(db, tenant: models.Tenant) -> bool:
    """按 max_users 判断是否已达用户数上限(0=不限)。"""
    return bool(tenant.max_users) and user_count(db, tenant.id) >= tenant.max_users
