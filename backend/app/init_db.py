"""初始化:建表、轻量迁移、预置科目与企业信息单例。幂等。"""
from sqlalchemy import inspect, text

from .database import Base, engine, SessionLocal
from . import models
from .seed_accounts import ACCOUNTS


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate(engine)
    db = SessionLocal()
    try:
        _seed_accounts(db)
        _seed_company(db)
        db.commit()
    finally:
        db.close()


# 已存在的表在版本迭代中新增的列:{表名: [(列名, 建列 DDL 片段), ...]}
_ADDED_COLUMNS = {
    "vouchers": [
        ("customer_id", "INTEGER"),
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
