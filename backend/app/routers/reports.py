"""财务报表 API:科目汇总表、利润表、资产负债表、首页概览。

均为基于凭证分录的实时聚合,不做月末结转。
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models

router = APIRouter(prefix="/api/reports", tags=["reports"])

ZERO = Decimal("0")


def _sum_by_account(db: Session, start: date | None, end: date | None):
    """返回 {account_id: (debit_sum, credit_sum)},按日期区间过滤。"""
    stmt = (
        select(
            models.VoucherEntry.account_id,
            func.coalesce(func.sum(models.VoucherEntry.debit), 0),
            func.coalesce(func.sum(models.VoucherEntry.credit), 0),
        )
        .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
        .group_by(models.VoucherEntry.account_id)
    )
    if start:
        stmt = stmt.where(models.Voucher.voucher_date >= start)
    if end:
        stmt = stmt.where(models.Voucher.voucher_date <= end)
    return {
        acc_id: (Decimal(d), Decimal(c))
        for acc_id, d, c in db.execute(stmt).all()
    }


@router.get("/trial-balance")
def trial_balance(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
):
    """科目汇总表:每个发生过业务的科目的借/贷方发生额与净额。"""
    sums = _sum_by_account(db, start, end)
    accounts = {a.id: a for a in db.scalars(select(models.Account)).all()}
    rows = []
    total_debit = total_credit = ZERO
    for acc_id, (debit, credit) in sums.items():
        acc = accounts.get(acc_id)
        if acc is None:
            continue
        balance = debit - credit if acc.direction == "debit" else credit - debit
        rows.append({
            "code": acc.code, "name": acc.name, "category": acc.category,
            "direction": acc.direction,
            "debit": float(debit), "credit": float(credit),
            "balance": float(balance),
        })
        total_debit += debit
        total_credit += credit
    rows.sort(key=lambda r: r["code"])
    return {
        "rows": rows,
        "total_debit": float(total_debit),
        "total_credit": float(total_credit),
        "balanced": total_debit == total_credit,
    }


# 利润表科目映射(损益类)
_INCOME_LINES = [
    ("main_revenue", "一、营业收入", ["6001", "6051"], "credit"),
    ("main_cost", "减:营业成本", ["6401", "6402"], "debit"),
    ("tax_surcharge", "税金及附加", ["6403"], "debit"),
    ("sell_expense", "销售费用", ["6601"], "debit"),
    ("admin_expense", "管理费用", ["6602"], "debit"),
    ("fin_expense", "财务费用", ["6603"], "debit"),
    ("impairment", "资产减值损失", ["6701"], "debit"),
    ("fair_value", "加:公允价值变动收益", ["6101"], "credit"),
    ("invest_income", "投资收益", ["6111"], "credit"),
    ("non_op_income", "加:营业外收入", ["6301"], "credit"),
    ("non_op_expense", "减:营业外支出", ["6711"], "debit"),
    ("income_tax", "减:所得税费用", ["6801"], "debit"),
]


@router.get("/income")
def income_statement(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
):
    """利润表(会企02 简版)。"""
    sums = _sum_by_account(db, start, end)
    code_to_id = {a.code: a.id for a in db.scalars(select(models.Account)).all()}

    def amount(codes: list[str], direction: str) -> Decimal:
        total = ZERO
        for code in codes:
            acc_id = code_to_id.get(code)
            if acc_id is None:
                continue
            debit, credit = sums.get(acc_id, (ZERO, ZERO))
            total += (credit - debit) if direction == "credit" else (debit - credit)
        return total

    vals = {key: amount(codes, d) for key, _, codes, d in _INCOME_LINES}
    lines = [
        {"key": key, "label": label, "amount": float(vals[key])}
        for key, label, _, _ in _INCOME_LINES
    ]

    operating_profit = (
        vals["main_revenue"] - vals["main_cost"] - vals["tax_surcharge"]
        - vals["sell_expense"] - vals["admin_expense"] - vals["fin_expense"]
        - vals["impairment"] + vals["fair_value"] + vals["invest_income"]
    )
    total_profit = operating_profit + vals["non_op_income"] - vals["non_op_expense"]
    net_profit = total_profit - vals["income_tax"]

    return {
        "lines": lines,
        "operating_profit": float(operating_profit),
        "total_profit": float(total_profit),
        "net_profit": float(net_profit),
    }


@router.get("/balance-sheet")
def balance_sheet(
    as_of: date | None = None,
    db: Session = Depends(get_db),
):
    """资产负债表(简版):按大类汇总余额 + 本期净利润计入未分配利润。"""
    sums = _sum_by_account(db, None, as_of)
    accounts = {a.id: a for a in db.scalars(select(models.Account)).all()}

    asset_total = liability_total = equity_total = profit_net = ZERO
    asset_rows, liability_rows, equity_rows = [], [], []

    for acc_id, (debit, credit) in sums.items():
        acc = accounts.get(acc_id)
        if acc is None:
            continue
        if acc.category == "asset":
            bal = debit - credit
            asset_total += bal
            if bal != ZERO:
                asset_rows.append({"name": acc.name, "amount": float(bal)})
        elif acc.category == "liability":
            bal = credit - debit
            liability_total += bal
            if bal != ZERO:
                liability_rows.append({"name": acc.name, "amount": float(bal)})
        elif acc.category == "equity":
            bal = credit - debit
            equity_total += bal
            if bal != ZERO:
                equity_rows.append({"name": acc.name, "amount": float(bal)})
        elif acc.category == "profit":
            # 损益类净额累计为未分配利润(收入为贷、费用为借)
            profit_net += credit - debit

    equity_total += profit_net
    if profit_net != ZERO:
        equity_rows.append({"name": "未分配利润(本期损益)", "amount": float(profit_net)})

    for rows in (asset_rows, liability_rows, equity_rows):
        rows.sort(key=lambda r: -abs(r["amount"]))

    return {
        "as_of": as_of.isoformat() if as_of else None,
        "assets": asset_rows,
        "liabilities": liability_rows,
        "equity": equity_rows,
        "asset_total": float(asset_total),
        "liability_total": float(liability_total),
        "equity_total": float(equity_total),
        "balanced": asset_total == liability_total + equity_total,
    }


@router.get("/summary")
def dashboard_summary(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
):
    """首页概览:凭证数、收入、支出、净利润、近 6 月趋势。"""
    income = income_statement(start, end, db)
    revenue = income["lines"][0]["amount"]  # 营业收入
    voucher_count = db.scalar(select(func.count(models.Voucher.id))) or 0

    # 总支出 = 营业收入 - 净利润(粗略,用于概览)
    expense = revenue - income["net_profit"]

    # 近 6 个月营业收入/净利润趋势
    trend = _monthly_trend(db, months=6)

    return {
        "voucher_count": voucher_count,
        "revenue": revenue,
        "expense": expense,
        "net_profit": income["net_profit"],
        "trend": trend,
    }


def _monthly_trend(db: Session, months: int = 6):
    """按月聚合营业收入(6001/6051)与净利润(全部损益净额)。

    月份在 Python 端归并,避免数据库方言差异(Postgres/SQLite)。
    """
    rows = db.execute(
        select(
            models.Voucher.voucher_date,
            models.Account.code,
            func.coalesce(func.sum(models.VoucherEntry.debit), 0),
            func.coalesce(func.sum(models.VoucherEntry.credit), 0),
        )
        .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
        .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
        .where(models.Account.category == "profit")
        .group_by(models.Voucher.voucher_date, models.Account.code)
    ).all()

    bucket: dict[str, dict[str, Decimal]] = {}
    revenue_codes = {"6001", "6051"}
    for vdate, code, debit, credit in rows:
        ym = f"{vdate:%Y-%m}"
        b = bucket.setdefault(ym, {"revenue": ZERO, "profit": ZERO})
        debit, credit = Decimal(debit), Decimal(credit)
        b["profit"] += credit - debit
        if code in revenue_codes:
            b["revenue"] += credit - debit

    ordered = sorted(bucket.items())[-months:]
    return [
        {"month": ym, "revenue": float(v["revenue"]), "net_profit": float(v["profit"])}
        for ym, v in ordered
    ]
