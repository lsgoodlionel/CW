"""企业信息 API。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter(prefix="/api/company", tags=["company"])


def _get_or_create(db: Session) -> models.CompanyInfo:
    company = db.get(models.CompanyInfo, 1)
    if company is None:
        company = models.CompanyInfo(id=1, name="")
        db.add(company)
        db.commit()
    return company


@router.get("", response_model=schemas.CompanyOut)
def read_company(db: Session = Depends(get_db)):
    return _get_or_create(db)


@router.put("", response_model=schemas.CompanyOut)
def update_company(payload: schemas.CompanyUpdate, db: Session = Depends(get_db)):
    company = _get_or_create(db)
    for field, value in payload.model_dump().items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return company
