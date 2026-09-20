"""阶段三自包含验证(内存 SQLite):平台建租户/成员 + 备份导出恢复往返含租户与成员。

直接调用路由函数(绕过 FastAPI 依赖注入,手动传入 db 与超管用户)。
"""
import io
import zipfile

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app.tenant import install_tenant_isolation, set_current_tenant
from app.tenant_provision import provision_tenant


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _seed_base(db):
    """种子:默认租户 + 一个超管用户 + 成员关系 + 预置租户1基础数据。"""
    set_current_tenant(None)
    db.add(models.Tenant(id=1, name="租户一", code="default", is_active=True))
    admin = models.User(username="admin", display_name="超管", password_hash="x",
                        is_super_admin=True, is_active=True)
    db.add(admin)
    db.flush()
    db.add(models.TenantMembership(user_id=admin.id, tenant_id=1, is_tenant_admin=True))
    db.commit()
    provision_tenant(db, 1)
    set_current_tenant(None)
    return admin


def run():
    from app.routers import platform as plat
    from app.routers import data_io
    install_tenant_isolation()           # 注册租户过滤/回填(应用启动时亦会注册)
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # ---------- 平台管理:建租户 + 成员 ----------
    db = _new_db()
    admin = _seed_base(db)
    # 建租户(含租户管理员)
    out = plat.create_tenant(plat.TenantCreateIn(
        name="租户二", code="t2", admin_username="boss2",
        admin_password="secret123", admin_display_name="老板二"), db, admin)
    check("建租户返回", out["name"] == "租户二" and out["id"] != 1)
    t2 = out["id"]
    set_current_tenant(None)
    check("新租户预置科目", db.scalar(select(func.count()).select_from(models.Account)
                                 .where(models.Account.tenant_id == t2)) == 81)
    check("新租户预置角色3", db.scalar(select(func.count()).select_from(models.Role)
                                 .where(models.Role.tenant_id == t2)) == 3)
    check("租户管理员已建", out["member_count"] == 1)
    # 加成员(已存在用户 admin 加入租户二)
    m = plat.add_member(t2, plat.MemberAddIn(username="admin", is_tenant_admin=False), db, admin)
    check("加成员返回", m["username"] == "admin" and m["is_tenant_admin"] is False)
    # 改成员为管理员
    m2 = plat.update_member(m["id"], plat.MemberUpdateIn(is_tenant_admin=True), db, admin)
    check("改成员管理员", m2["is_tenant_admin"] is True)
    # 列成员(租户二应有 boss2 + admin = 2)
    members = plat.list_members(t2, db, admin)
    check("成员列表2人", len(members) == 2)
    # 停用租户
    upd = plat.update_tenant(t2, plat.TenantUpdateIn(is_active=False), db, admin)
    check("停用租户", upd["is_active"] is False)
    # 移除成员
    plat.remove_member(m["id"], db, admin)
    check("移除成员后1人", len(plat.list_members(t2, db, admin)) == 1)
    set_current_tenant(None); db.close()

    # ---------- 备份导出→恢复 往返(含租户与成员) ----------
    src = _new_db()
    _seed_base(src)
    # 再加一个普通用户与成员
    set_current_tenant(None)
    u = models.User(username="clerk", display_name="出纳", password_hash="y",
                    is_super_admin=False, is_active=True)
    src.add(u); src.flush()
    src.add(models.TenantMembership(user_id=u.id, tenant_id=1, is_tenant_admin=False))
    src.commit()
    # 租户1 作用域导出
    set_current_tenant(1)
    zip_bytes = data_io.build_backup_zip(src)
    set_current_tenant(None); src.close()

    payload = _read_payload(zip_bytes)
    check("导出版本21", payload["version"] == 21)
    check("导出含租户1", [t["ref"] for t in payload["tenants"]] == [1])
    check("导出含成员2", len(payload["tenant_memberships"]) == 2)

    # 恢复到全新库(context=租户1)
    dst = _new_db()
    set_current_tenant(1)
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    counts = data_io._restore(dst, zf, payload)
    set_current_tenant(None)
    check("恢复科目81", counts["accounts"] == 81)
    check("恢复后租户存在", dst.scalar(select(func.count()).select_from(models.Tenant)) == 1)
    check("恢复后成员2", dst.scalar(select(func.count()).select_from(models.TenantMembership)) == 2)
    check("恢复后用户存在admin", dst.scalar(select(models.User.id)
                                     .where(models.User.username == "admin")) is not None)
    set_current_tenant(None); dst.close()

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


def _read_payload(zip_bytes: bytes) -> dict:
    import json
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    return json.loads(zf.read("data.json"))


if __name__ == "__main__":
    run()
