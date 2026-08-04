"""初始化:建表、轻量迁移、预置科目与企业信息单例。幂等。"""
from sqlalchemy import inspect, text, select

from .database import Base, engine, SessionLocal
from . import models
from .seed_accounts import ACCOUNTS
from .seed_subaccounts import SUB_ACCOUNTS
from . import subaccounts_svc


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate(engine)
    db = SessionLocal()
    try:
        _seed_accounts(db)
        _seed_company(db)
        db.commit()
        _seed_subaccounts(db)
        _backfill_entry_sub_account_id(db)
        _backfill_employee_positions(db)
        db.commit()
    finally:
        db.close()


# 已存在的表在版本迭代中新增的列:{表名: [(列名, 建列 DDL 片段), ...]}
_ADDED_COLUMNS = {
    "vouchers": [
        ("customer_id", "INTEGER"),
    ],
    "voucher_entries": [
        ("sub_account_id", "INTEGER"),
    ],
    "customers": [
        ("party_type", "VARCHAR(20) DEFAULT 'enterprise'"),
    ],
    "operation_logs": [
        ("detail", "TEXT DEFAULT ''"),
    ],
    "company_info": [
        ("tax_number", "VARCHAR(40) DEFAULT ''"),
        ("reg_address", "VARCHAR(200) DEFAULT ''"),
        ("phone", "VARCHAR(50) DEFAULT ''"),
        ("bank_name", "VARCHAR(120) DEFAULT ''"),
        ("bank_account", "VARCHAR(60) DEFAULT ''"),
        ("establish_date", "VARCHAR(20) DEFAULT ''"),
        ("industry", "VARCHAR(60) DEFAULT ''"),
        ("currency", "VARCHAR(20) DEFAULT '人民币'"),
        ("accounting_standard", "VARCHAR(40) DEFAULT '小企业会计准则'"),
        ("start_period", "VARCHAR(20) DEFAULT ''"),
    ],
}


def _migrate(bind) -> None:
    """为已存在的表补充新增列(create_all 不会 ALTER 现有表)。幂等。"""
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table, cols in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in cols:
            if name not in have:
                with bind.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _seed_accounts(db) -> None:
    existing = {code for (code,) in db.query(models.Account.code).all()}
    for code, name, category, direction in ACCOUNTS:
        if code in existing:
            continue
        db.add(models.Account(
            code=code, name=name, category=category,
            direction=direction, is_active=True,
        ))


def _seed_company(db) -> None:
    if db.get(models.CompanyInfo, 1) is None:
        db.add(models.CompanyInfo(id=1, name="我的小微企业"))


def _seed_subaccounts(db) -> None:
    """预置二级科目(仅当该二级表为空时);按一级科目名称归属并生成编码。"""
    if db.scalar(select(models.SubAccount.id).limit(1)) is not None:
        return
    name_to_account = {a.name: a for a in db.scalars(select(models.Account)).all()}
    for parent_name, subs in SUB_ACCOUNTS.items():
        account = name_to_account.get(parent_name)
        if account is None:
            continue
        for idx, (sub_name, note) in enumerate(subs, start=1):
            db.add(models.SubAccount(
                account_id=account.id,
                code=f"{account.code}{idx:02d}",
                name=sub_name, note=note, sort_no=idx, is_active=True,
            ))
    db.commit()


def _backfill_employee_positions(db) -> None:
    """把旧版单部门员工(org_unit_id/role_type/position)迁移为一条任职记录。"""
    employees = db.scalars(select(models.Employee)).all()
    if not employees:
        return
    existing = {pid for (pid,) in db.execute(
        select(models.EmployeePosition.employee_id)).all()}
    changed = False
    for e in employees:
        if e.id in existing:
            continue
        if e.org_unit_id or (e.role_type and e.role_type != "staff") or e.position:
            db.add(models.EmployeePosition(
                employee_id=e.id, org_unit_id=e.org_unit_id,
                role_type=e.role_type or "staff", position=e.position, sort_no=1))
            changed = True
    if changed:
        db.commit()


def _backfill_entry_sub_account_id(db) -> None:
    """为历史凭证分录按(科目, 明细科目名)回填 sub_account_id,缺失的二级自动补建。"""
    entries = db.scalars(
        select(models.VoucherEntry).where(
            models.VoucherEntry.sub_account != "",
            models.VoucherEntry.sub_account_id.is_(None))
    ).all()
    if not entries:
        return
    for e in entries:
        sub = subaccounts_svc.get_or_create(db, e.account_id, e.sub_account)
        if sub:
            e.sub_account_id = sub.id
    db.commit()
