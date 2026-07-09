"""会计账簿生成:根据凭证自动生成全套账簿。

六类账簿:
- general        总分类账
- detail_three   金额三栏式明细账
- cash_journal   现金日记账
- bank_journal   银行存款日记账
- detail_multi   金额多栏式明细账
- qty_amount     数量金额式明细账

统一返回 {ledger_type, title, period_label, columns, groups};
group = 一个科目(或科目+明细),含期初、明细行、本期合计、期末。
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import models
from .reports_cn import Period

ZERO = Decimal("0")

LEDGER_TYPES = {
    "general": "总分类账",
    "detail_three": "金额三栏式明细账",
    "cash_journal": "现金日记账",
    "bank_journal": "银行存款日记账",
    "detail_multi": "金额多栏式明细账",
    "qty_amount": "数量金额式明细账",
}

# 存货类科目(数量金额式明细账默认范围)
INVENTORY_CODES = ["1403", "1405", "1406", "1411", "1408", "1401"]


def _f(d: Decimal) -> float:
    return float(d)


def row_cells(ledger_type: str, row: dict, sub_columns: list[str]) -> list:
    """将一行账簿数据扁平化为与 columns 对齐的单元格值(供 Excel 与前端复用)。"""
    def m(v):
        return "" if v is None else v

    if ledger_type in ("cash_journal", "bank_journal"):
        return [row["date"], row["voucher_no"], row["summary"], row.get("counter", ""),
                m(row["debit"]), m(row["credit"]), row["direction"], m(row["balance"])]
    if ledger_type == "detail_multi":
        subs = row.get("subs", {})
        return ([row["date"], row["voucher_no"], row["summary"], m(row["debit"])]
                + [m(subs.get(s)) for s in sub_columns]
                + [m(row["credit"]), m(row["balance"])])
    if ledger_type == "qty_amount":
        return [row["date"], row["voucher_no"], row["summary"],
                row.get("in_qty", ""), m(row.get("in_amount")),
                row.get("out_qty", ""), m(row.get("out_amount")),
                row.get("bal_qty", ""), m(row.get("bal_amount"))]
    return [row["date"], row["voucher_no"], row["summary"],
            m(row["debit"]), m(row["credit"]), row["direction"], m(row["balance"])]


def attach_cells(data: dict) -> dict:
    """为每个分组的行附加扁平化 cells,便于前端通用渲染。"""
    sub_cols = data.get("sub_columns", [])
    for group in data.get("groups", []):
        for row in group["rows"]:
            row["cells"] = row_cells(data["ledger_type"], row, sub_cols)
    return data


def _opening_balance(db: Session, code: str, before: date) -> Decimal:
    """科目在 before(含)之前的累计余额(借-贷)。"""
    val = db.scalar(
        select(func.coalesce(func.sum(models.VoucherEntry.debit), 0)
               - func.coalesce(func.sum(models.VoucherEntry.credit), 0))
        .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
        .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
        .where(models.Account.code == code, models.Voucher.voucher_date <= before)
    )
    return Decimal(val or 0)


def _load_entries(db: Session, start: date, end: date, codes: list[str] | None):
    """加载区间内分录,连带凭证与科目。返回按日期/凭证号排序的列表。"""
    stmt = (
        select(models.VoucherEntry, models.Voucher, models.Account)
        .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
        .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
        .where(models.Voucher.voucher_date >= start,
               models.Voucher.voucher_date <= end)
        .order_by(models.Voucher.voucher_date, models.Voucher.voucher_no,
                  models.VoucherEntry.line_no)
    )
    if codes:
        stmt = stmt.where(models.Account.code.in_(codes))
    return db.execute(stmt).all()


def _counter_accounts(db: Session, voucher_ids: set[int]) -> dict[int, list]:
    """凭证 → 其全部分录(科目名, 借, 贷),用于日记账"对方科目"。"""
    if not voucher_ids:
        return {}
    rows = db.execute(
        select(models.VoucherEntry.voucher_id, models.Account.name,
               models.VoucherEntry.debit, models.VoucherEntry.credit)
        .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
        .where(models.VoucherEntry.voucher_id.in_(voucher_ids))
    ).all()
    out: dict[int, list] = {}
    for vid, name, debit, credit in rows:
        out.setdefault(vid, []).append((name, Decimal(debit), Decimal(credit)))
    return out


def _dir_label(bal: Decimal) -> str:
    if bal > 0:
        return "借"
    if bal < 0:
        return "贷"
    return "平"


# ---------------------------------------------------------------------------
# 三栏式(总账 / 明细账 / 现金 / 银行 共用底层)
# ---------------------------------------------------------------------------
def _three_column_group(db, code, name, sub_label, start, end, entries,
                        counter=None, journal=False) -> dict:
    """构造一个科目(或明细)的三栏式账簿分组。"""
    opening = _opening_balance(db, code, start - timedelta(days=1))
    running = opening
    rows = [{
        "date": "", "voucher_no": "", "summary": "期初余额", "counter": "",
        "debit": None, "credit": None,
        "direction": _dir_label(running), "balance": _f(running),
        "is_summary": True,
    }]
    total_d = total_c = ZERO
    for entry, voucher, account in entries:
        debit = Decimal(entry.debit)
        credit = Decimal(entry.credit)
        running += debit - credit
        total_d += debit
        total_c += credit
        row = {
            "date": voucher.voucher_date.isoformat(),
            "voucher_no": voucher.voucher_no,
            "summary": entry.summary or voucher.note,
            "debit": _f(debit), "credit": _f(credit),
            "direction": _dir_label(running), "balance": _f(running),
            "is_summary": False,
        }
        if journal and counter is not None:
            legs = counter.get(voucher.id, [])
            others = [nm for nm, d, c in legs if nm != name]
            row["counter"] = "、".join(dict.fromkeys(others))
        rows.append(row)

    rows.append({
        "date": "", "voucher_no": "", "summary": "本期合计", "counter": "",
        "debit": _f(total_d), "credit": _f(total_c),
        "direction": _dir_label(running), "balance": _f(running),
        "is_summary": True,
    })
    title = f"{code} {name}" + (f" — {sub_label}" if sub_label else "")
    return {"code": code, "name": name, "sub": sub_label, "title": title,
            "opening": _f(opening), "closing": _f(running), "rows": rows}


def _all_active_codes(db: Session, start: date, end: date) -> list[str]:
    """有期初余额或本期发生的科目编码(按编码排序)。"""
    codes = set(db.scalars(
        select(models.Account.code)
        .join(models.VoucherEntry, models.VoucherEntry.account_id == models.Account.id)
        .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
        .where(models.Voucher.voucher_date <= end)
    ).all())
    return sorted(codes)


def build_ledger(db: Session, ledger_type: str, period: Period,
                 account_code: str | None = None) -> dict:
    start, end = period.cur_start, period.cur_end
    base = {"ledger_type": ledger_type, "title": LEDGER_TYPES[ledger_type],
            "period_label": period.label}

    if ledger_type in ("cash_journal", "bank_journal"):
        code = "1001" if ledger_type == "cash_journal" else "1002"
        name = "库存资金" if ledger_type == "cash_journal" else "银行存款"
        rows = _load_entries(db, start, end, [code])
        counter = _counter_accounts(db, {v.id for _, v, _ in rows})
        group = _three_column_group(db, code, name, "", start, end, rows,
                                    counter=counter, journal=True)
        base["columns"] = ["日期", "凭证字号", "摘要", "对方科目",
                           "收入(借方)", "付出(贷方)", "借或贷", "结余"]
        base["journal"] = True
        base["groups"] = [group]
        return base

    if ledger_type == "general":
        codes = [account_code] if account_code else _all_active_codes(db, start, end)
        acc_names = _code_name_map(db)
        groups = []
        for code in codes:
            rows = _load_entries(db, start, end, [code])
            if not rows and _opening_balance(db, code, start - timedelta(days=1)) == 0:
                continue
            groups.append(_three_column_group(
                db, code, acc_names.get(code, ""), "", start, end, rows))
        base["columns"] = ["日期", "凭证字号", "摘要", "借方金额", "贷方金额", "借或贷", "余额"]
        base["groups"] = groups
        return base

    if ledger_type == "detail_three":
        return _detail_three(db, base, period, account_code)

    if ledger_type == "detail_multi":
        return _detail_multi(db, base, period, account_code)

    if ledger_type == "qty_amount":
        return _qty_amount(db, base, period, account_code)

    raise ValueError(f"未知账簿类型: {ledger_type}")


def _code_name_map(db: Session) -> dict[str, str]:
    return {c: n for c, n in db.execute(
        select(models.Account.code, models.Account.name)).all()}


def _detail_three(db, base, period: Period, account_code):
    """三栏式明细账:按科目 + 明细科目分组。"""
    start, end = period.cur_start, period.cur_end
    codes = [account_code] if account_code else _all_active_codes(db, start, end)
    acc_names = _code_name_map(db)
    groups = []
    for code in codes:
        rows = _load_entries(db, start, end, [code])
        # 按明细科目分组
        subs: dict[str, list] = {}
        for r in rows:
            subs.setdefault(r[0].sub_account or "", []).append(r)
        if not subs and _opening_balance(db, code, start - timedelta(days=1)) == 0:
            continue
        for sub, sub_rows in (subs.items() or [("", [])]):
            groups.append(_three_column_group(
                db, code, acc_names.get(code, ""), sub, start, end, sub_rows))
    base["columns"] = ["日期", "凭证字号", "摘要", "借方金额", "贷方金额", "借或贷", "余额"]
    base["groups"] = groups
    return base


def _detail_multi(db, base, period: Period, account_code):
    """多栏式明细账:某科目按明细科目横向展开借方。"""
    start, end = period.cur_start, period.cur_end
    acc_names = _code_name_map(db)
    # 默认选发生额最大的费用类科目(管理费用/销售费用),否则第一个有明细的科目
    code = account_code or _pick_multi_default(db, start, end)
    if not code:
        base["columns"] = ["日期", "凭证字号", "摘要", "借方合计", "贷方金额", "余额"]
        base["groups"] = []
        base["sub_columns"] = []
        return base

    rows = _load_entries(db, start, end, [code])
    sub_cols = sorted({(r[0].sub_account or "其他") for r in rows})
    opening = _opening_balance(db, code, start - timedelta(days=1))
    running = opening
    out_rows = []
    total_by_sub = {s: ZERO for s in sub_cols}
    total_d = total_c = ZERO
    for entry, voucher, account in rows:
        debit = Decimal(entry.debit)
        credit = Decimal(entry.credit)
        running += debit - credit
        total_d += debit
        total_c += credit
        sub = entry.sub_account or "其他"
        total_by_sub[sub] = total_by_sub.get(sub, ZERO) + debit
        out_rows.append({
            "date": voucher.voucher_date.isoformat(),
            "voucher_no": voucher.voucher_no,
            "summary": entry.summary or voucher.note,
            "debit": _f(debit), "credit": _f(credit),
            "balance": _f(running),
            "subs": {s: _f(debit if s == sub else ZERO) for s in sub_cols},
            "is_summary": False,
        })
    out_rows.append({
        "date": "", "voucher_no": "", "summary": "本期合计",
        "debit": _f(total_d), "credit": _f(total_c), "balance": _f(running),
        "subs": {s: _f(total_by_sub.get(s, ZERO)) for s in sub_cols},
        "is_summary": True,
    })
    base["columns"] = ["日期", "凭证字号", "摘要", "借方合计"] + sub_cols + ["贷方金额", "余额"]
    base["sub_columns"] = sub_cols
    base["groups"] = [{
        "code": code, "name": acc_names.get(code, ""),
        "title": f"{code} {acc_names.get(code, '')}",
        "opening": _f(opening), "closing": _f(running), "rows": out_rows,
    }]
    return base


def _pick_multi_default(db, start, end) -> str | None:
    for code in ("6602", "6601", "6603"):
        if db.scalar(
            select(func.count(models.VoucherEntry.id))
            .join(models.Voucher, models.Voucher.id == models.VoucherEntry.voucher_id)
            .join(models.Account, models.Account.id == models.VoucherEntry.account_id)
            .where(models.Account.code == code,
                   models.Voucher.voucher_date >= start,
                   models.Voucher.voucher_date <= end)
        ):
            return code
    codes = _all_active_codes(db, start, end)
    return codes[0] if codes else None


def _qty_amount(db, base, period: Period, account_code):
    """数量金额式明细账:存货类科目。系统无数量/单价字段,仅出金额,数量列留空。"""
    start, end = period.cur_start, period.cur_end
    acc_names = _code_name_map(db)
    codes = [account_code] if account_code else INVENTORY_CODES
    groups = []
    for code in codes:
        rows = _load_entries(db, start, end, [code])
        opening = _opening_balance(db, code, start - timedelta(days=1))
        if not rows and opening == 0:
            continue
        running = opening
        out_rows = [{
            "date": "", "voucher_no": "", "summary": "期初余额",
            "in_qty": "", "in_amount": None, "out_qty": "", "out_amount": None,
            "bal_qty": "", "bal_amount": _f(running), "is_summary": True,
        }]
        for entry, voucher, account in rows:
            debit = Decimal(entry.debit)
            credit = Decimal(entry.credit)
            running += debit - credit
            out_rows.append({
                "date": voucher.voucher_date.isoformat(),
                "voucher_no": voucher.voucher_no,
                "summary": entry.summary or voucher.note,
                "in_qty": "", "in_amount": _f(debit) if debit else None,
                "out_qty": "", "out_amount": _f(credit) if credit else None,
                "bal_qty": "", "bal_amount": _f(running), "is_summary": False,
            })
        groups.append({
            "code": code, "name": acc_names.get(code, ""),
            "title": f"{code} {acc_names.get(code, '')}",
            "opening": _f(opening), "closing": _f(running), "rows": out_rows,
        })
    base["columns"] = ["日期", "凭证字号", "摘要", "收入-数量", "收入-金额",
                       "发出-数量", "发出-金额", "结存-数量", "结存-金额"]
    base["note"] = "系统未记录数量/单价,数量列留空,仅列示金额。"
    base["groups"] = groups
    return base
