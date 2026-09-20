"""阶段四自包含验证(内存 SQLite):订阅到期/配额判定 + 自助注册。"""
from datetime import date, timedelta

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, subscription
from app.config import settings
from app.tenant import install_tenant_isolation, set_current_tenant


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def run():
    install_tenant_isolation()
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    today = date.today().isoformat()
    future = (date.today() + timedelta(days=10)).isoformat()
    past = (date.today() - timedelta(days=1)).isoformat()

    # ---------- 到期判定 ----------
    T = models.Tenant
    check("active无到期可用", subscription.usable_reason(
        T(name="a", is_active=True, status="active", expires_at="")) is None)
    check("trial未过期可用", subscription.usable_reason(
        T(name="b", is_active=True, status="trial", expires_at=future)) is None)
    check("过期日拦截", subscription.usable_reason(
        T(name="c", is_active=True, status="trial", expires_at=past)) is not None)
    check("status=expired拦截", subscription.usable_reason(
        T(name="d", is_active=True, status="expired", expires_at="")) is not None)
    check("suspended拦截", subscription.usable_reason(
        T(name="e", is_active=True, status="suspended", expires_at="")) is not None)
    check("停用拦截", subscription.usable_reason(
        T(name="f", is_active=False, status="active", expires_at="")) is not None)

    # ---------- 配额判定 ----------
    db = _new_db()
    set_current_tenant(None)
    db.add(T(id=1, name="配额租户", is_active=True, status="active", max_users=2))
    for i in range(2):
        u = models.User(username=f"u{i}", password_hash="h", is_active=True)
        db.add(u); db.flush()
        db.add(models.TenantMembership(user_id=u.id, tenant_id=1))
    db.commit()
    t = db.get(T, 1)
    check("达上限时配额超限", subscription.quota_exceeded(db, t) is True)
    t.max_users = 0
    check("上限0=不限", subscription.quota_exceeded(db, t) is False)
    db.close()

    # ---------- 自助注册 ----------
    from app.routers import auth as auth_router
    prev_mode, prev_reg = settings.deploy_mode, settings.allow_self_registration
    settings.deploy_mode = "saas"
    settings.allow_self_registration = True
    try:
        db = _new_db()
        res = auth_router.register(auth_router.RegisterIn(
            tenant_name="新客户公司", username="owner", password="pass12", display_name="业主"), db)
        check("注册返回令牌", bool(res["token"]) and res["user"]["username"] == "owner")
        check("注册用户为租户管理员", res["user"]["is_tenant_admin"] is True)
        set_current_tenant(None)
        tenant = db.scalar(select(models.Tenant).where(models.Tenant.name == "新客户公司"))
        check("注册租户为试用且有到期日",
              tenant is not None and tenant.status == "trial" and tenant.expires_at >= today)
        check("注册已预置科目", db.scalar(select(func.count()).select_from(models.Account)
                                    .where(models.Account.tenant_id == tenant.id)) == 81)
        set_current_tenant(None); db.close()
    finally:
        settings.deploy_mode, settings.allow_self_registration = prev_mode, prev_reg

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
