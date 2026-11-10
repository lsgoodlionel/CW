"""租户级备份恢复隔离回归验证(内存 SQLite,#38):

- SaaS 下在租户内导入备份,只替换本租户业务数据;其他租户的数据、用户、成员关系不受影响。
- 平台账号与已有账号不被改动(密码、超管身份);伪造备份中的超管账号不会生效。
- 当前租户的订阅信息保留;成员关系只增不删,导入者不会被移出。
- 平台全量备份(多个租户)不能在单个租户内导入。
- 整站恢复(私有化)保留租户订阅信息。
"""
import io
import json
import zipfile

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
from app import models
from app.tenant import install_tenant_isolation, set_current_tenant


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _user(db, username, pw="h", super_admin=False):
    u = models.User(username=username, display_name=username, password_hash=pw,
                    is_super_admin=super_admin, is_active=True)
    db.add(u)
    db.flush()
    return u


def _seed_two_tenants(db):
    """租户1、租户2 各有科目与成员;平台超管 admin 属租户1。"""
    set_current_tenant(None)
    db.add_all([
        models.Tenant(id=1, name="租户一", code="t1", plan="pro", status="active"),
        models.Tenant(id=2, name="租户二", code="t2", plan="standard", status="active",
                      expires_at="2027-12-31", max_users=5),
    ])
    admin = _user(db, "admin", pw="admin-hash", super_admin=True)
    boss1 = _user(db, "boss1")
    boss2 = _user(db, "boss2", pw="boss2-hash")
    clerk2 = _user(db, "clerk2")
    db.add_all([
        models.TenantMembership(user_id=admin.id, tenant_id=1, is_tenant_admin=True),
        models.TenantMembership(user_id=boss1.id, tenant_id=1, is_tenant_admin=True),
        models.TenantMembership(user_id=boss2.id, tenant_id=2, is_tenant_admin=True),
        models.TenantMembership(user_id=clerk2.id, tenant_id=2, is_tenant_admin=False),
    ])
    db.commit()
    for tid, names in ((1, ["现金1"]), (2, ["现金2", "银行2"])):
        set_current_tenant(tid)
        for i, name in enumerate(names):
            db.add(models.Account(code=f"100{i + 1}", name=name, category="asset",
                                  direction="debit"))
        db.commit()
    set_current_tenant(None)


def _payload(zip_bytes: bytes) -> dict:
    return json.loads(zipfile.ZipFile(io.BytesIO(zip_bytes)).read("data.json"))


def _zip(payload: dict) -> zipfile.ZipFile:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.json", json.dumps(payload, ensure_ascii=False))
    return zipfile.ZipFile(io.BytesIO(buf.getvalue()))


def run():
    from app.routers import data_io
    install_tenant_isolation()
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    prev_mode = settings.deploy_mode
    settings.deploy_mode = "saas"
    try:
        # ---------- 租户1 导出 → 改动 → 在租户1 内导入 ----------
        db = _new_db()
        _seed_two_tenants(db)
        set_current_tenant(1)
        payload = _payload(data_io.build_backup_zip(db))
        # 导出后:租户1 新增科目与新成员 late1
        db.add(models.Account(code="1009", name="导出后新增", category="asset", direction="debit"))
        db.commit()
        set_current_tenant(None)
        late1 = _user(db, "late1")
        db.add(models.TenantMembership(user_id=late1.id, tenant_id=1, is_tenant_admin=False))
        db.commit()
        # 伪造备份:夹带超管账号,并试图改写他租户已有账号 boss2 的密码
        payload["users"] += [
            {"username": "evil", "password_hash": "evil-hash", "display_name": "evil",
             "employee_ref": None, "is_super_admin": True, "is_active": True, "role_names": []},
            {"username": "boss2", "password_hash": "hacked", "display_name": "boss2",
             "employee_ref": None, "is_super_admin": True, "is_active": True, "role_names": []},
        ]

        set_current_tenant(1)
        data_io._restore(db, _zip(payload), payload)
        set_current_tenant(None)

        def names(tid):
            return sorted(a.name for a in db.scalars(
                select(models.Account).where(models.Account.tenant_id == tid)).all())

        def members(tid):
            return sorted(db.scalars(
                select(models.User.username).join(
                    models.TenantMembership, models.TenantMembership.user_id == models.User.id)
                .where(models.TenantMembership.tenant_id == tid)).all())

        users = {u.username: u for u in db.scalars(select(models.User)).all()}
        t2 = db.get(models.Tenant, 2)
        t1 = db.get(models.Tenant, 1)

        check("租户1科目恢复为备份内容", names(1) == ["现金1"])
        check("租户2科目不受影响", names(2) == ["现金2", "银行2"])
        check("两个租户都还在", sorted(t.id for t in db.scalars(select(models.Tenant)).all()) == [1, 2])
        check("租户2订阅信息不变", (t2.plan, t2.expires_at, t2.max_users) == ("standard", "2027-12-31", 5))
        check("租户1订阅信息不变", (t1.plan, t1.status) == ("pro", "active"))
        check("租户2成员不受影响", members(2) == ["boss2", "clerk2"])
        check("租户1成员只增不删(保留 late1)", "late1" in members(1) and "boss1" in members(1))
        check("平台超管仍为超管且密码未变",
              users["admin"].is_super_admin and users["admin"].password_hash == "admin-hash")
        check("伪造的超管账号未获超管身份", "evil" in users and users["evil"].is_super_admin is False)
        check("他租户已有账号的密码未被改写", users["boss2"].password_hash == "boss2-hash")
        check("他租户已有账号未被提权为超管", users["boss2"].is_super_admin is False)
        check("租户1系统角色已补齐", len(db.scalars(
            select(models.Role).where(models.Role.tenant_id == 1)).all()) >= 3)
        db.close()

        # ---------- 平台全量备份不能在单个租户内导入 ----------
        db = _new_db()
        _seed_two_tenants(db)
        set_current_tenant(None)
        full = _payload(data_io.build_backup_zip(db))
        check("全量备份含两个租户", len(full["tenants"]) == 2)
        set_current_tenant(1)
        try:
            data_io._restore(db, _zip(full), full)
            rejected = False
        except HTTPException as e:
            rejected = e.status_code == 400
        db.rollback()
        set_current_tenant(None)
        check("租户内导入全量备份被拒绝", rejected)
        check("被拒绝后租户2数据仍在", len(db.scalars(
            select(models.Account).where(models.Account.tenant_id == 2)).all()) == 2)
        db.close()
    finally:
        settings.deploy_mode = prev_mode
        set_current_tenant(None)

    # ---------- 私有化整站恢复:保留租户订阅信息 ----------
    src = _new_db()
    set_current_tenant(None)
    src.add(models.Tenant(id=1, name="默认企业", code="default", plan="enterprise",
                          status="active", expires_at="", max_users=0))
    src.commit()
    set_current_tenant(1)
    zip_bytes = data_io.build_backup_zip(src)
    set_current_tenant(None)
    src.close()
    p = _payload(zip_bytes)
    dst = _new_db()
    set_current_tenant(1)
    data_io._restore(dst, zipfile.ZipFile(io.BytesIO(zip_bytes)), p)
    set_current_tenant(None)
    t = dst.get(models.Tenant, 1)
    check("整站恢复保留套餐与状态", (t.plan, t.status) == ("enterprise", "active"))
    dst.close()

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
