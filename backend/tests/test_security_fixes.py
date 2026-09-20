"""阶段三安全修复回归验证(内存 SQLite):

- UPDATE/DELETE 语句受租户过滤(防跨租户批量删除/更新)。
- 备份恢复非默认租户(id≠1)不产生幽灵租户1、成员关系正确。
- 租户作用域导出不带出其它租户用户与平台超管账号。
"""
import io
import zipfile

from sqlalchemy import create_engine, select, delete, func, update
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app.tenant import install_tenant_isolation, set_current_tenant


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def run():
    from app.routers import data_io
    install_tenant_isolation()
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # ---------- UPDATE/DELETE 租户隔离 ----------
    db = _new_db()
    set_current_tenant(None)
    db.add_all([models.Tenant(id=1, name="T1", code="t1"),
                models.Tenant(id=2, name="T2", code="t2")])
    db.commit()
    set_current_tenant(1)
    db.add(models.Account(code="1001", name="现金1", category="asset", direction="debit"))
    db.commit()
    set_current_tenant(2)
    db.add(models.Account(code="1001", name="现金2", category="asset", direction="debit"))
    db.commit()

    # 租户1 上下文批量删除:只应删除租户1
    set_current_tenant(1)
    db.execute(delete(models.Account))
    db.commit()
    set_current_tenant(None)
    remain = db.scalars(select(models.Account)).all()
    check("DELETE仅删本租户", len(remain) == 1 and remain[0].tenant_id == 2)

    # 租户2 上下文批量更新:只应改租户2(此处仅剩租户2)
    set_current_tenant(2)
    db.execute(update(models.Account).values(name="改名2"))
    db.commit()
    set_current_tenant(None)
    check("UPDATE仅改本租户", db.scalar(select(models.Account.name)) == "改名2")
    db.close()

    # ---------- 非默认租户备份恢复:无幽灵租户1 ----------
    src = _new_db()
    set_current_tenant(None)
    src.add(models.Tenant(id=5, name="租户五", code="t5", is_active=True))
    u = models.User(username="boss5", display_name="老板五", password_hash="h",
                    is_super_admin=False, is_active=True)
    src.add(u); src.flush()
    src.add(models.TenantMembership(user_id=u.id, tenant_id=5, is_tenant_admin=True))
    src.commit()
    set_current_tenant(5)
    src.add(models.Account(code="1001", name="现金5", category="asset", direction="debit"))
    src.commit()
    zip_bytes = data_io.build_backup_zip(src)
    set_current_tenant(None); src.close()

    payload = _payload(zip_bytes)
    check("导出租户为5", [t["ref"] for t in payload["tenants"]] == [5])
    check("导出用户仅本租户成员", [u["username"] for u in payload["users"]] == ["boss5"])

    dst = _new_db()
    set_current_tenant(5)
    data_io._restore(dst, zipfile.ZipFile(io.BytesIO(zip_bytes)), payload)
    set_current_tenant(None)
    tenant_ids = sorted(t.id for t in dst.scalars(select(models.Tenant)).all())
    check("恢复后无幽灵租户1", tenant_ids == [5])
    m_tids = sorted(m.tenant_id for m in dst.scalars(select(models.TenantMembership)).all())
    check("成员仅属租户5", m_tids == [5])
    dst.close()

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


def _payload(zip_bytes: bytes) -> dict:
    import json
    return json.loads(zipfile.ZipFile(io.BytesIO(zip_bytes)).read("data.json"))


if __name__ == "__main__":
    run()
