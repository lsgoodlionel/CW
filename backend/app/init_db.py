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


def _migrate(bind) -> None:
    """为已存在的表补充新增列(create_all 不会 ALTER 现有表)。幂等。"""
    inspector = inspect(bind)
    if "vouchers" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("vouchers")}
    if "customer_id" not in columns:
        with bind.begin() as conn:
            conn.execute(text("ALTER TABLE vouchers ADD COLUMN customer_id INTEGER"))


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
