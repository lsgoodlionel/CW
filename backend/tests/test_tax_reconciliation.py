"""税务凭证、财务报表与税务申报记录联动审查回归验证。"""
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, tax_reconcile
from app.tenant import install_tenant_isolation, set_current_tenant


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _account(code: str, name: str, category: str, direction: str) -> models.Account:
    return models.Account(code=code, name=name, category=category,
                          direction=direction, is_active=True)


def _entry(line_no: int, account: models.Account, sub: str, debit="0", credit="0"):
    return models.VoucherEntry(
        line_no=line_no, summary="", account=account, sub_account=sub,
        debit=Decimal(debit), credit=Decimal(credit),
    )


def _voucher(no: str, vdate: date, note: str, entries: list[models.VoucherEntry]):
    return models.Voucher(
        voucher_no=no, voucher_date=vdate, note=note, status="posted",
        total_debit=sum((e.debit for e in entries), Decimal("0")),
        total_credit=sum((e.credit for e in entries), Decimal("0")),
        entries=entries,
    )


def run():
    install_tenant_isolation()
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    db = _new_db()
    set_current_tenant(1)
    tax = _account("2221", "应交税费", "liability", "credit")
    income = _account("6301", "营业外收入", "profit", "credit")
    expense = _account("6403", "营业税金及附加", "profit", "debit")
    db.add_all([tax, income, expense])
    db.flush()

    db.add(_voucher("记-001", date(2026, 7, 10), "计提增值税", [
        _entry(1, tax, "应交增值税", credit="396.04"),
        _entry(2, income, "主营业务收入", debit="396.04"),
    ]))
    db.add(_voucher("记-002", date(2026, 7, 31), "计提印花税", [
        _entry(1, expense, "印花税", debit="0.14"),
        _entry(2, tax, "应交印花税", credit="0.14"),
    ]))
    db.add(_voucher("记-003", date(2026, 9, 18), "错误按总余额结转增值税减免", [
        _entry(1, tax, "应交增值税", debit="396.18"),
        _entry(2, income, "减免税款", credit="396.18"),
    ]))
    db.add(models.TaxFiling(
        tax_type="stamp", taxpayer_type="enterprise", period="2026",
        period_start=date(2026, 1, 1), period_end=date(2026, 12, 31),
        tax_basis=Decimal("1100.00"), tax_amount=Decimal("0.14"),
        paid_amount=Decimal("0.00"), filed_date=date(2027, 1, 5),
        status="pending", note="营业账簿印花税",
    ))
    db.commit()

    result = tax_reconcile.audit(db, as_of=date(2026, 12, 31))
    issue_codes = {it["code"] for it in result["issues"]}
    sub = {row["sub_account"]: Decimal(str(row["balance"]))
           for row in result["tax_payable_subaccounts"]}

    check("识别 2221 一级余额为零但明细互抵",
          "tax_subaccount_offset" in issue_codes)
    check("应交增值税明细被多冲为负数",
          sub["应交增值税"] == Decimal("-0.14"))
    check("应交印花税明细仍有贷方余额",
          sub["应交印花税"] == Decimal("0.14"))
    check("识别待申报印花税仍有账务余额",
          "filing_pending_with_balance" in issue_codes)

    set_current_tenant(None)
    db.close()

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
