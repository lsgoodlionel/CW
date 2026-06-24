"""初始化:建表、预置科目与企业信息单例。幂等。"""
from .database import Base, engine, SessionLocal
from . import models
from .seed_accounts import ACCOUNTS


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_accounts(db)
        _seed_company(db)
        db.commit()
    finally:
        db.close()


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
