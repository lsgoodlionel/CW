"""税务凭证、财务报表与税务申报记录联动审查。"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import models

ZERO = Decimal("0")
TAX_SUB_BY_TYPE = {
    "vat": "应交增值税",
    "stamp": "应交印花税",
    "cit": "应交企业所得税",
    "iit": "应交个人所得税",
}
TAX_TYPE_LABEL = {
    "vat": "增值税",
    "stamp": "印花税",
    "cit": "企业所得税",
    "iit": "个人所得税",
    "vat_surtax": "增值税及附加",
    "other": "其他",
}


def audit(db: Session, as_of: date | None = None) -> dict:
    """返回应交税费明细余额和税务申报记录联动审查结果。"""
    as_of = as_of or date.today()
    sub_rows = _tax_payable_subaccounts(db, as_of)
    issues = _subaccount_issues(sub_rows)
    filings = [_filing_row(db, f, sub_rows, issues)
               for f in db.scalars(select(models.TaxFiling).order_by(models.TaxFiling.id.desc())).all()]
    return {
        "as_of": as_of.isoformat(),
        "tax_payable_total": float(sum((r["balance_decimal"] for r in sub_rows), ZERO)),
        "tax_payable_subaccounts": [
            {k: v for k, v in r.items() if k != "balance_decimal"} for r in sub_rows
        ],
        "issues": issues,
        "filings": filings,
    }


def _tax_payable_subaccounts(db: Session, as_of: date) -> list[dict]:
    rows = db.execute(
        select(
            models.VoucherEntry.sub_account,
            func.coalesce(func.sum(models.VoucherEntry.debit), 0),
            func.coalesce(func.sum(models.VoucherEntry.credit), 0),
        )
        .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
        .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
        .where(models.Account.code == "2221",
               models.Voucher.status == "posted",
               models.Voucher.voucher_date <= as_of)
        .group_by(models.VoucherEntry.sub_account)
        .order_by(models.VoucherEntry.sub_account)
    ).all()
    out = []
    for sub, debit, credit in rows:
        debit, credit = Decimal(debit), Decimal(credit)
        balance = credit - debit
        if balance == 0:
            continue
        out.append({
            "sub_account": sub or "(无明细)",
            "debit": float(debit),
            "credit": float(credit),
            "balance": float(balance),
            "balance_decimal": balance,
        })
    return out


def _subaccount_issues(sub_rows: list[dict]) -> list[dict]:
    issues: list[dict] = []
    total = sum((r["balance_decimal"] for r in sub_rows), ZERO)
    positives = [r for r in sub_rows if r["balance_decimal"] > 0]
    negatives = [r for r in sub_rows if r["balance_decimal"] < 0]
    if positives and negatives:
        level = "error" if total == 0 else "warning"
        issues.append({
            "code": "tax_subaccount_offset",
            "level": level,
            "title": "应交税费明细互抵",
            "message": "2221 应交税费存在明细科目一正一负互相抵消,请检查是否把某一税种余额结转到其他税种。",
            "amount": float(total),
            "related": [r["sub_account"] for r in positives + negatives],
        })
    for r in negatives:
        issues.append({
            "code": "tax_subaccount_negative",
            "level": "warning",
            "title": f"{r['sub_account']} 出现借方余额",
            "message": "应交税费明细出现负数,通常表示多缴、多冲或税种串户。",
            "amount": float(r["balance_decimal"]),
            "related": [r["sub_account"]],
        })
    return issues


def _filing_row(db: Session, filing: models.TaxFiling, sub_rows: list[dict],
                issues: list[dict]) -> dict:
    expected_sub = TAX_SUB_BY_TYPE.get(filing.tax_type)
    account_balance = _period_tax_movement(db, expected_sub, filing.period_start, filing.period_end) \
        if expected_sub else None
    current_balance = next((r["balance_decimal"] for r in sub_rows
                            if r["sub_account"] == expected_sub), None)
    filing_issues: list[dict] = []
    if expected_sub and filing.status != "paid" and filing.tax_amount and account_balance is not None:
        if abs(account_balance - Decimal(filing.tax_amount)) >= Decimal("0.01"):
            filing_issues.append({
                "code": "filing_amount_mismatch",
                "level": "warning",
                "message": f"申报应纳税额与账务期间计提金额不一致:申报 {filing.tax_amount},账务 {account_balance}。",
            })
    if filing.status == "pending" and current_balance and current_balance > 0:
        filing_issues.append({
            "code": "filing_pending_with_balance",
            "level": "info",
            "message": "该税种仍有应交余额且申报记录为待申报。",
        })
    if filing_issues:
        issues.extend({
            "code": it["code"],
            "level": it["level"],
            "title": f"{TAX_TYPE_LABEL.get(filing.tax_type, filing.tax_type)} {filing.period}",
            "message": it["message"],
            "amount": float(current_balance or ZERO),
            "related": [expected_sub] if expected_sub else [],
        } for it in filing_issues)
    return {
        "filing_id": filing.id,
        "tax_type": filing.tax_type,
        "tax_type_label": TAX_TYPE_LABEL.get(filing.tax_type, filing.tax_type),
        "period": filing.period,
        "status": filing.status,
        "tax_amount": float(filing.tax_amount),
        "paid_amount": float(filing.paid_amount),
        "expected_sub_account": expected_sub,
        "account_balance": float(account_balance) if account_balance is not None else None,
        "current_balance": float(current_balance) if current_balance is not None else 0.0,
        "issues": filing_issues,
    }


def _period_tax_movement(db: Session, sub_account: str | None,
                         start: date | None, end: date | None) -> Decimal | None:
    if not sub_account or not start or not end:
        return None
    stmt = (
        select(
            func.coalesce(func.sum(models.VoucherEntry.credit), 0)
            - func.coalesce(func.sum(models.VoucherEntry.debit), 0)
        )
        .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
        .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
        .where(models.Account.code == "2221",
               models.VoucherEntry.sub_account == sub_account,
               models.Voucher.status == "posted",
               models.Voucher.voucher_date >= start,
               models.Voucher.voucher_date <= end)
    )
    return Decimal(db.scalar(stmt) or 0)
