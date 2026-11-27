"""财务报表与仪表盘金额统计口径回归验证。"""
from datetime import date
from decimal import Decimal
from math import isclose

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

    cost = _account("6401", "营业成本", "profit", "debit")
    nonop = _account("6301", "营业外收入", "profit", "credit")
    tax = _account("2221", "应交税费", "liability", "credit")
    development = _account("5301", "开发支出", "cost", "debit")
    prior_adjustment = _account("6901", "以前年度损益调整", "profit", "debit")
    db.add_all([cost, nonop, tax, development, prior_adjustment])
    db.flush()
    db.add_all([
        _voucher("记-003", "posted", [_entry(1, cost, debit="40.00"), _entry(2, bank, credit="40.00")]),
        _voucher("记-004", "posted", [_entry(1, cost, debit="-10.00"), _entry(2, bank, credit="-10.00")]),
        _voucher("记-005", "posted", [_entry(1, bank, debit="20.00"), _entry(2, nonop, credit="20.00")]),
        _voucher("记-006", "posted", [_entry(1, bank, debit="12.00"), _entry(2, tax, credit="12.00")]),
        _voucher("记-007", "posted", [_entry(1, bank, debit="-2.00"), _entry(2, tax, credit="-2.00")]),
        _voucher("记-008", "posted", [_entry(1, bank, debit="-30.00"), _entry(2, revenue, credit="-30.00")]),
        _voucher("记-009", "posted", [_entry(1, development, debit="15.00"), _entry(2, bank, credit="15.00")]),
        _voucher("记-010", "posted", [_entry(1, development, debit="-5.00"), _entry(2, bank, credit="-5.00")]),
        _voucher("记-011", "posted", [_entry(1, prior_adjustment, debit="3.00"), _entry(2, bank, credit="3.00")]),
        _voucher("记-012", "posted", [_entry(1, prior_adjustment, debit="-1.00"), _entry(2, bank, credit="-1.00")]),
    ])
    db.commit()
    dashboard = reports.dashboard(period_type="month", ref_date=date(2026, 9, 15), db=db)
    summary = reports.dashboard_summary(start=period.cur_start, end=period.cur_end, db=db)
    bs = reports_cn.balance_sheet(db, period)
    income = reports_cn.income_statement(db, period)
    check("红字成本在原科目抵减，营业外收入不抵减总支出",
          dashboard["expense"] == summary["expense"] == 30.0
          and dashboard["expense_breakdown"] == [{"code": "6401", "name": "营业成本", "amount": 30.0}])
    check("红字税费抵减期末余额并与资产负债表一致",
          dashboard["tax_payable"] == 10.0
          and next(r for r in bs["rights"] if r.get("line") == 36)["end"] == 10.0)
    check("红字进入利润、银行余额和趋势且与官方报表一致",
          dashboard["revenue"] == 70.0 and dashboard["net_profit"] == 60.0
          and dashboard["money"]["bank"] == 58.0 and dashboard["finance"]["assets"] == 68.0
          and dashboard["trend"] == [{"month": "2026-09", "revenue": 70.0, "net_profit": 60.0}]
          and row(income, 1)["col1"] == 70.0 and row(income, 32)["col1"] == 60.0
          and bs["balanced"] is True)
    check("资产、负债、权益及比率与报表一致",
          dashboard["finance"]["assets"] == bs["asset_total"] == 68.0
          and dashboard["finance"]["liabilities"] == next(r for r in bs["rights"] if r.get("line") == 47)["end"] == 10.0
          and dashboard["finance"]["equity"] == next(r for r in bs["rights"] if r.get("line") == 52)["end"] == 58.0
          and next(r for r in bs["assets"] if r.get("line") == 26)["end"] == 10.0
          and isclose(dashboard["finance"]["debt_ratio"], 10 / 68)
          and isclose(dashboard["finance"]["gross_margin"], 40 / 70)
          and isclose(dashboard["finance"]["net_margin"], 60 / 70))
    check("以前年度损益调整不进入当期利润与趋势", row(income, 32)["col1"] == 60.0)
    check("红字凭证仍计入本期已过账张数", dashboard["voucher_count"] == 11)

    set_current_tenant(None)
    db.close()

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
