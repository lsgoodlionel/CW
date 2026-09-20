"""多租户隔离自包含验证(内存 SQLite,无需 pytest 亦可直接 `python -m tests.test_tenant_isolation`)。

覆盖:
- do_orm_execute SELECT 级租户过滤:各租户仅见本租户数据。
- before_flush 自动回填 tenant_id。
- tenant_get 跨租户越权防护:取他租户对象返回 None。
- 当前租户为 None(平台超管/初始化)时不过滤,可见全部。
- 按租户唯一约束:不同租户可用相同科目编码。
"""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app.tenant import (
    install_tenant_isolation, set_current_tenant, get_current_tenant, tenant_get,
)


def _setup():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    install_tenant_isolation()            # 幂等:重复注册仅多一层监听,不影响正确性
    return sessionmaker(bind=engine)


def _seed_two_tenants(Session):
    set_current_tenant(None)              # 初始化:不过滤
    db = Session()
    db.add_all([
        models.Tenant(id=1, name="租户一", code="t1", is_active=True),
        models.Tenant(id=2, name="租户二", code="t2", is_active=True),
    ])
    db.commit()
    # 租户1、租户2 各建一个同编码科目(验证按租户唯一)
    set_current_tenant(1)
    db.add(models.Account(code="1001", name="库存现金-T1", category="asset", direction="debit"))
    db.commit()
    set_current_tenant(2)
    db.add(models.Account(code="1001", name="库存现金-T2", category="asset", direction="debit"))
    db.commit()
    return db


def run() -> None:
    Session = _setup()
    db = _seed_two_tenants(Session)
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # 1) 租户1 视角:仅见本租户科目
    set_current_tenant(1)
    a1 = db.scalars(select(models.Account)).all()
    check("租户1仅见1条科目", len(a1) == 1 and a1[0].name == "库存现金-T1")
    t1_acct_id = a1[0].id

    # 2) 租户2 视角:仅见本租户科目
    set_current_tenant(2)
    a2 = db.scalars(select(models.Account)).all()
    check("租户2仅见1条科目", len(a2) == 1 and a2[0].name == "库存现金-T2")
    t2_acct_id = a2[0].id

    # 3) before_flush 自动回填:租户2 上下文新建对象 tenant_id==2
    check("自动回填tenant_id=2", db.get(models.Account, t2_acct_id).tenant_id == 2)

    # 4) tenant_get 跨租户越权防护:租户2 上下文取租户1 对象 → None
    set_current_tenant(2)
    check("tenant_get拦截跨租户对象", tenant_get(db, models.Account, t1_acct_id) is None)
    check("tenant_get放行本租户对象", tenant_get(db, models.Account, t2_acct_id) is not None)

    # 5) 无上下文(平台超管):可见全部
    set_current_tenant(None)
    all_accts = db.scalars(select(models.Account)).all()
    check("超管无过滤见全部", len(all_accts) == 2)
    check("tenant_get无上下文不校验", tenant_get(db, models.Account, t1_acct_id) is not None)

    # 6) 按租户唯一:两租户同编码 1001 并存
    codes = [(x.tenant_id, x.code) for x in all_accts]
    check("两租户同编码1001并存", sorted(codes) == [(1, "1001"), (2, "1001")])

    set_current_tenant(None)
    db.close()
    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
