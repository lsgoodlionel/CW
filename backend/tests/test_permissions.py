"""权限体系验证:超管 / 账套管理员(is_tenant_admin)/ 普通用户 RBAC + 平台超管管理。"""
from types import SimpleNamespace

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, auth_svc
from app.tenant import install_tenant_isolation, set_current_tenant


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _perm(perm):
    return SimpleNamespace(perm=perm)


def run():
    install_tenant_isolation()
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # ---------- user_has 判定 ----------
    superadmin = SimpleNamespace(is_super_admin=True)
    check("超管对任意模块全权", auth_svc.user_has(superadmin, "user", "delete") is True)

    tenant_admin = SimpleNamespace(is_super_admin=False, _is_tenant_admin=True, roles=[])
    check("账套管理员对任意模块全权", auth_svc.user_has(tenant_admin, "user", "create") is True
          and auth_svc.user_has(tenant_admin, "voucher", "delete") is True)

    role = SimpleNamespace(permissions=[_perm("voucher:view"), _perm("voucher:create")])
    normal = SimpleNamespace(is_super_admin=False, roles=[role])
    check("普通用户仅授予的权限", auth_svc.user_has(normal, "voucher", "view") is True)
    check("普通用户无越权", auth_svc.user_has(normal, "voucher", "delete") is False
          and auth_svc.user_has(normal, "user", "view") is False)

    role_star = SimpleNamespace(permissions=[_perm("tax:*")])
    normal2 = SimpleNamespace(is_super_admin=False, roles=[role_star])
    check("module:* 展开为该模块全部动作", auth_svc.user_has(normal2, "tax", "direct") is True
          and auth_svc.user_has(normal2, "tax", "delete") is True)

    # ---------- 平台超管管理端点 ----------
    from app.routers import platform as P
    db = _new_db()
    set_current_tenant(None)
    db.add(models.Tenant(id=1, name="甲公司", code="a", is_active=True,
                         plan="enterprise", status="active", expires_at="", max_users=0))
    a1 = models.User(username="root1", password_hash="h", is_super_admin=True, is_active=True)
    a2 = models.User(username="root2", password_hash="h", is_super_admin=True, is_active=True)
    u = models.User(username="boss", display_name="老板", password_hash="h",
                    is_super_admin=False, is_active=True)
    db.add_all([a1, a2, u]); db.flush()
    db.add(models.TenantMembership(user_id=u.id, tenant_id=1, is_tenant_admin=True))
    db.commit()

    users = P.list_all_users("", db, a1)
    check("平台用户列表跨租户", len(users) == 3)
    boss_row = next(r for r in users if r["username"] == "boss")
    check("列表含所属租户名", boss_row["tenants"] == ["甲公司"])

    P.set_super_admin(u.id, P.SuperAdminIn(is_super_admin=True), db, a1)
    check("可提升为平台超管", db.get(models.User, u.id).is_super_admin is True)

    # 现有 3 个超管,依次取消到 1 个
    P.set_super_admin(a1.id, P.SuperAdminIn(is_super_admin=False), db, a2)
    P.set_super_admin(a2.id, P.SuperAdminIn(is_super_admin=False), db, u)
    count = db.scalar(select(func.count()).select_from(models.User)
                      .where(models.User.is_super_admin.is_(True)))
    check("取消后仍余 1 个超管", count == 1)
    try:
        P.set_super_admin(u.id, P.SuperAdminIn(is_super_admin=False), db, u)
        check("取消最后一个超管被拒", False)
    except Exception as e:
        check("取消最后一个超管被拒", getattr(e, "status_code", None) == 400)
    set_current_tenant(None); db.close()

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
