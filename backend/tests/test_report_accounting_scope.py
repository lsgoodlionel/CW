"""财务报表与仪表盘金额统计口径回归验证。"""
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, reports_cn
from app.routers import reports
from app.tenant import install_tenant_isolation, set_current_tenant


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def _account(code: str, name: str, category: str, direction: str) -> models.Account:
    return models.Account(code=code, name=name, category=category,
                          direction=direction, is_active=True)


def _entry(line_no: int, account: models.Account, debit="0", credit="0"):
    return models.VoucherEntry(
        line_no=line_no,
        summary="测试",
        account=account,
        debit=Decimal(debit),
        credit=Decimal(credit),
    )


def _voucher(no: str, status: str, entries: list[models.VoucherEntry]) -> models.Voucher:
    total_debit = sum((e.debit for e in entries), Decimal("0"))
    total_credit = sum((e.credit for e in entries), Decimal("0"))
    return models.Voucher(
        voucher_no=no,
        voucher_date=date(2026, 9, 10),
        note="口径测试",
        status=status,
        total_debit=total_debit,
        total_credit=total_credit,
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
    bank = _account("1002", "银行存款", "asset", "debit")
    revenue = _account("6001", "主营业务收入", "profit", "credit")
    db.add_all([bank, revenue])
    db.flush()

    db.add(_voucher("记-001", "posted", [
        _entry(1, bank, debit="100.00"),
        _entry(2, revenue, credit="100.00"),
    ]))
    db.add(_voucher("记-002", "draft", [
        _entry(1, bank, debit="900.00"),
        _entry(2, revenue, credit="900.00"),
    ]))
    db.commit()

    period = reports_cn.build_period("month", 2026, 9, None)
    bs = reports_cn.balance_sheet(db, period)
    income = reports_cn.income_statement(db, period)
    cashflow = reports_cn.cashflow_statement(db, period)
    dashboard = reports.dashboard(period_type="month", ref_date=date(2026, 9, 15), db=db)
    summary = reports.dashboard_summary(start=period.cur_start, end=period.cur_end, db=db)

    def row(table: dict, line: int) -> dict:
        return next(r for r in table["rows"] if r.get("line") == line)

    check("资产负债表只统计已过账凭证",
          bs["asset_total"] == 100.0 and bs["right_total"] == 100.0 and bs["balanced"] is True)
    check("利润表只统计已过账凭证", row(income, 1)["col1"] == 100.0 and row(income, 32)["col1"] == 100.0)
    check("现金流量表只统计已过账凭证", row(cashflow, 1)["col1"] == 100.0 and row(cashflow, 22)["col1"] == 100.0)
    check("仪表盘金额与本期凭证数只统计已过账凭证",
          dashboard["revenue"] == 100.0 and dashboard["net_profit"] == 100.0
          and dashboard["voucher_count"] == 1)
    check("首页汇总凭证数按查询期间统计已过账凭证", summary["voucher_count"] == 1)
    check("趋势图只统计已过账损益凭证",
          dashboard["trend"] == [{"month": "2026-09", "revenue": 100.0, "net_profit": 100.0}])

    set_current_tenant(None)
    db.close()

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
