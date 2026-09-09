"""税务报表生成:企业所得税预缴(季报 A200000)与年度汇算(年报 A100000)主表。

依据国家税务总局表式,取账套数据(利润表口径)自动计算主表行次;优惠、预缴、
纳税调整、总分机构分摊等无法从账套自动取得的行次默认 0,可在生成的 Excel 中
手工调整后报送。行次的上下级关系以缩进呈现:子行次(如 1.1、9.1)相对父行次
缩进一级。
"""
import io
from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, reports_cn

RATE = Decimal("0.25")           # 法定税率 25%
# 小型微利企业优惠:应纳税所得额减按 25% 计入、按 20% 征收(实际税负 5%),
# 相对法定 25% 的减免率 = 25% - 5% = 20%(简化按全额适用,不分 300 万档)
SMALL_MICRO_RELIEF = Decimal("0.20")


_Q_TITLE = "中华人民共和国企业所得税月(季)度预缴纳税申报表(A类)"
_A_TITLE = "中华人民共和国企业所得税年度纳税申报表(A类)"
Z = Decimal("0")

# 小型微利企业判断标准(2023-2027):同时满足以下条件
SMALL_MICRO_TAXABLE_LIMIT = Decimal("3000000")     # 应纳税所得额 ≤ 300 万元
SMALL_MICRO_STAFF_LIMIT = 300                       # 从业人数 ≤ 300 人
SMALL_MICRO_ASSET_LIMIT = Decimal("50000000")      # 资产总额 ≤ 5000 万元
# 小规模纳税人标准:连续 12 个月应征增值税销售额 ≤ 500 万元
VAT_SMALL_SALES_LIMIT = Decimal("5000000")
# 小规模增值税:季度销售额 ≤ 30 万元免征;征收率默认 1%(2023-2027优惠,可选3%)
VAT_FREE_QUARTER = Decimal("300000")
VAT_RATE_DEFAULT = Decimal("0.01")
# 附加税费率:城建税(市区7%)、教育费附加3%、地方教育附加2%
SURTAX_CITY = Decimal("0.07")
SURTAX_EDU = Decimal("0.03")
SURTAX_LOCAL_EDU = Decimal("0.02")


def compute_vat_small(db: Session, year: int, quarter: int,
                      rate: Decimal | None = None, half_surtax: bool = True) -> dict:
    """增值税及附加税费申报表(小规模纳税人适用)本季度计算。
    销售额取本季度 6001/6051;季销售额≤30万免征;附加税以实纳增值税为基,小微「六税两费」减半。"""
    start = date(year, quarter * 3 - 2, 1)
    end = _quarter_end(year, quarter)
    sales = reports_cn.Balances(reports_cn._movement(db, start, end)).net_credit("6001", "6051")
    rate = Decimal(str(rate)) if rate is not None else VAT_RATE_DEFAULT
    free = sales <= VAT_FREE_QUARTER
    gross_vat = (sales * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    relief = gross_vat if free else Z                 # 小微免征减征额
    vat = gross_vat - relief                           # 本期应纳(减免后)增值税
    half = Decimal("0.5") if half_surtax else Decimal("1")
    city = (vat * SURTAX_CITY * half).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    edu = (vat * SURTAX_EDU * half).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    local = (vat * SURTAX_LOCAL_EDU * half).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    surtax = city + edu + local
    rows = [
        ("一、应征增值税不含税销售额", sales, ""),
        ("二、征收率", rate, "小规模征收率(优惠1%/一般3%)"),
        ("三、本期应纳增值税额(一×二)", gross_vat, ""),
        ("四、小微免征增值税减征额", relief, "季度销售额≤30万免征" if free else "本季销售额超30万,不免征"),
        ("五、本期实纳增值税额(三−四)", vat, ""),
        ("六、城市维护建设税(五×7%)", city, "小微减半" if half_surtax else ""),
        ("七、教育费附加(五×3%)", edu, "小微减半" if half_surtax else ""),
        ("八、地方教育附加(五×2%)", local, "小微减半" if half_surtax else ""),
        ("九、附加税费合计(六+七+八)", surtax, ""),
        ("十、本期应纳税费合计(五+九)", vat + surtax, "增值税+附加税费"),
    ]
    return {"year": year, "quarter": quarter, "sales": sales, "rate": rate, "free": free,
            "gross_vat": gross_vat, "relief": relief, "vat": vat,
            "city": city, "edu": edu, "local": local, "surtax": surtax,
            "total": vat + surtax, "rows": rows}


def build_vat_small_xlsx(db: Session, year: int, quarter: int,
                         rate: Decimal | None = None, half_surtax: bool = True) -> bytes:
    company = db.get(models.CompanyInfo, 1)
    data = compute_vat_small(db, year, quarter, rate, half_surtax)
    start = date(year, quarter * 3 - 2, 1)
    period = f"{start:%Y-%m-%d} 至 {_quarter_end(year, quarter):%Y-%m-%d}"
    wb = Workbook()
    ws = wb.active
    ws.title = "增值税及附加税费申报表"
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    ws.merge_cells("A1:C1")
    ws["A1"] = "增值税及附加税费申报表(小规模纳税人适用)"
    ws["A1"].font = Font(size=14, bold=True)
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 30
    for i, m in enumerate((f"税款所属期间:{period}",
                           f"纳税人名称:{(company.name if company else '') or ''}    金额单位:人民币元")):
        ws.merge_cells(start_row=2 + i, start_column=1, end_row=2 + i, end_column=3)
        ws.cell(2 + i, 1, m).alignment = left
    r = 4
    for c, h in enumerate(["项目", "金额/比率", "说明"], start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="1F6FEB")
        cell.alignment = center
        cell.border = border
    r += 1
    for item, amount, note in data["rows"]:
        ws.cell(r, 1, item).alignment = left
        if item.startswith("二、征收率"):
            ws.cell(r, 2, f"{float(amount) * 100:.0f}%").alignment = right
        else:
            ws.cell(r, 2, round(float(amount), 2)).alignment = right
        ws.cell(r, 3, note).alignment = left
        for c in (1, 2, 3):
            ws.cell(r, c).border = border
        r += 1
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 30
    return _save(wb)

def _total_assets(db: Session, as_of: date) -> Decimal:
    """资产总额:资产类科目净额合计(借-贷,备抵科目自然抵减);口径含在产品/生产成本,与资产负债表存货一致。"""
    b = reports_cn.balances_asof(db, as_of)
    return sum((v for code, v in b._d.items()
                if code.startswith("1") or code in ("5001", "5101", "5201")), Z)


def _active_headcount(db: Session) -> int:
    """从业人数:人员档案中在职员工数(status=active)。"""
    return db.query(models.Employee).filter(models.Employee.status == "active").count()


def _avg_headcount(db: Session, year: int, as_of: date) -> Decimal:
    """从业人数(季度平均):按人员档案 hire_date 推算该年各季末在职人数,取平均。
    离职员工(status!=active)不计入;入职日期缺失视为期初已在职。"""
    emps = db.query(models.Employee).all()
    ends = [d for d in (date(year, 3, 31), date(year, 6, 30),
                        date(year, 9, 30), date(year, 12, 31)) if d <= as_of] or [as_of]

    def _pd(v):
        try:
            return date.fromisoformat(str(v)[:10]) if v else None
        except ValueError:
            return None

    def active_at(qe: date) -> int:
        n = 0
        for e in emps:
            hd = _pd(e.hire_date)
            if hd and hd > qe:            # 该季末尚未入职
                continue
            ld = _pd(getattr(e, "leave_date", ""))
            if ld and ld <= qe:           # 该季末已离职
                continue
            if ld is None and e.status != "active":
                continue                  # 无离职日期但当前已离职:保守不计入
            n += 1
        return n

    counts = [active_at(qe) for qe in ends]
    if not counts:
        return Decimal("0")
    return (Decimal(sum(counts)) / Decimal(len(counts))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _prepaid_cit(db: Session, year: int) -> Decimal:
    """本年累计已预缴企业所得税额:汇总「税务申报记录」中该年度企业所得税(cit)的已缴税额。"""
    total = Z
    for r in db.scalars(select(models.TaxFiling).where(models.TaxFiling.tax_type == "cit")).all():
        y = r.period_start.year if r.period_start else None
        if y is None and r.period:
            digits = "".join(ch for ch in str(r.period)[:4] if ch.isdigit())
            y = int(digits) if len(digits) == 4 else None
        if y == year:
            total += r.paid_amount or Z
    return total


def _vat_sales_12m(db: Session, as_of: date) -> Decimal:
    """近 12 个月应征增值税销售额(主营+其他业务收入 6001/6051 贷方发生)。"""
    start = date(as_of.year - 1, as_of.month, 1)
    b = reports_cn.Balances(reports_cn._movement(db, start, as_of))
    return b.net_credit("6001", "6051")


def _avg_assets(db: Session, year: int, as_of: date) -> Decimal:
    """资产总额(季度平均):按该年各季末资产总额取平均,与从业人数口径一致。"""
    ends = [d for d in (date(year, 3, 31), date(year, 6, 30),
                        date(year, 9, 30), date(year, 12, 31)) if d <= as_of] or [as_of]
    vals = [_total_assets(db, e) for e in ends]
    return (sum(vals, Decimal("0")) / Decimal(len(vals))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def evaluate_small_micro(db: Session, taxable: Decimal, as_of: date, year: int) -> dict:
    """按标准判断是否符合小型微利企业,返回各条件复核明细与原因。"""
    c = db.get(models.CompanyInfo, 1)
    assets_avg = _avg_assets(db, year, as_of)
    staff = _avg_headcount(db, year, as_of)          # 从业人数(季度平均)
    restricted = bool(c and c.restricted_industry)
    checks = [
        {"name": "年应纳税所得额", "value": float(taxable),
         "limit": float(SMALL_MICRO_TAXABLE_LIMIT), "unit": "元",
         "ok": taxable <= SMALL_MICRO_TAXABLE_LIMIT},
        {"name": "从业人数(季度平均)", "value": float(staff), "limit": SMALL_MICRO_STAFF_LIMIT,
         "unit": "人", "ok": staff <= SMALL_MICRO_STAFF_LIMIT},
        {"name": "资产总额(季度平均)", "value": float(assets_avg),
         "limit": float(SMALL_MICRO_ASSET_LIMIT), "unit": "元",
         "ok": assets_avg <= SMALL_MICRO_ASSET_LIMIT},
        {"name": "非国家限制或禁止行业", "value": "是" if not restricted else "否(限制/禁止行业)",
         "limit": "-", "unit": "", "ok": not restricted},
    ]
    reasons = []
    for ck in checks:
        if not ck["ok"]:
            if ck["name"] == "非国家限制或禁止行业":
                reasons.append("企业从事国家限制或禁止行业")
            else:
                reasons.append(f"{ck['name']} {ck['value']}{ck['unit']} 超过标准 "
                               f"{ck['limit']}{ck['unit']}")
    return {"qualified": all(ck["ok"] for ck in checks), "checks": checks, "reasons": reasons}


def small_micro_status(db: Session, taxable: Decimal, as_of: date, year: int) -> dict:
    """综合自动判断与手动开关,返回本期是否按小型微利处理及复核信息。"""
    c = db.get(models.CompanyInfo, 1)
    info = evaluate_small_micro(db, taxable, as_of, year)
    auto = bool(c and c.small_micro_auto)
    if auto:
        effective = info["qualified"]
    else:
        effective = bool(c and c.is_small_micro)
    return {"mode": "auto" if auto else "manual", "effective": effective,
            "qualified": info["qualified"], "checks": info["checks"],
            "reasons": info["reasons"]}


def evaluate_taxpayer_kind(db: Session, as_of: date) -> dict:
    """增值税纳税人身份复核:按近12个月销售额判断应为一般/小规模,与设置对比。"""
    c = db.get(models.CompanyInfo, 1)
    sales = _vat_sales_12m(db, as_of)
    should = "general" if sales > VAT_SMALL_SALES_LIMIT else "small"
    current = (c.taxpayer_kind if c else "general") or "general"
    mismatch = (current == "small" and should == "general")
    reason = ""
    if mismatch:
        reason = (f"近12个月应征增值税销售额 {float(sales):.2f} 元 已超过小规模标准 "
                  f"{float(VAT_SMALL_SALES_LIMIT):.0f} 元,应自超标当月1日起转登记为一般纳税人")
    return {"sales_12m": float(sales), "limit": float(VAT_SMALL_SALES_LIMIT),
            "should_be": should, "current": current, "mismatch": mismatch, "reason": reason}


def quarterly_report_checks(db: Session, year: int, quarter: int) -> dict:
    """季报复核信息:小型微利判断 + 增值税身份复核。"""
    rows = {r[0]: r for r in compute_rows(db, year, quarter)}
    taxable = rows["25"][2]
    taxable = taxable if taxable > 0 else Z
    end = _quarter_end(year, quarter)
    return {"small_micro": small_micro_status(db, taxable, end, year),
            "taxpayer": evaluate_taxpayer_kind(db, end)}


def annual_report_checks(db: Session, year: int) -> dict:
    """年报复核信息:小型微利判断 + 增值税身份复核 + 年度与四季度(Q4)口径核对。"""
    rows = {r[0]: r for r in compute_annual_rows(db, year)}
    taxable = rows["28"][3]
    end = date(year, 12, 31)
    q4 = {r[0]: r for r in compute_rows(db, year, 4)}
    q4_profit = q4["25"][2]
    reconcile = {
        "annual_taxable": float(taxable), "q4_prepay_profit": float(q4_profit),
        "diff": float(taxable - q4_profit),
        "note": ("年报为全年汇算(含纳税调整、弥补亏损、税收优惠等),季报预缴为简化口径;"
                 "若企业无上述调整事项,两者应一致,差异即由这些事项构成。"),
    }
    return {"small_micro": small_micro_status(db, taxable, end, year),
            "taxpayer": evaluate_taxpayer_kind(db, end), "reconcile": reconcile}


# 行(行次, [类别,] 项目, 金额, 层级)。层级 0 为主行次,1 为子行次(缩进一级)。


def _quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    return date(year, month, monthrange(year, month)[1])


def _level(line_no: str) -> int:
    """行次层级:主行次(整数)为 0;子行次(含"."或以 FZ 开头)为 1。"""
    if line_no.startswith("FZ"):
        return 1
    return line_no.count(".")


def _core_amounts(db: Session, start: date, end: date) -> dict:
    """按利润表口径从账套汇总核心金额(利润总额及其构成)。"""
    b = reports_cn.Balances(reports_cn._movement(db, start, end))
    a = {
        "revenue": b.net_credit("6001", "6051"),
        "cost": b.net_debit("6401", "6402"),
        "tax_surcharge": b.net_debit("6403"),
        "sell": b.net_debit("6601"),
        "admin": b.net_debit("6602"),
        "rd": Z,                       # 研发费用:小企业多并入管理费用,无独立科目
        "fin": b.net_debit("6603"),
        "invest": b.net_credit("6111"),
        "fair_value": b.net_credit("6101"),
        "asset_impair": b.net_debit("6701"),
        "non_op_income": b.net_credit("6301"),
        "non_op_expense": b.net_debit("6711"),
    }
    a["op_profit"] = (a["revenue"] - a["cost"] - a["tax_surcharge"] - a["sell"]
                      - a["admin"] - a["rd"] - a["fin"] + a["fair_value"]
                      + a["invest"] - a["asset_impair"])
    a["total_profit"] = a["op_profit"] + a["non_op_income"] - a["non_op_expense"]
    return a


# ---------- 季报附表 A201020 资产加速折旧、摊销(扣除)优惠明细表 ----------

# (行次, 项目, 层级, 类型)。sum=小计/合计;detail=可录入明细。
_A201020_ROWS = [
    ("1", "一、加速折旧、摊销(不含一次性扣除,1.1+1.2+…)", 0, "sum"),
    ("1.1", "(明细)加速折旧、摊销项目", 1, "detail"),
    ("2", "二、一次性扣除(2.1+2.2+…)", 0, "sum"),
    ("2.1", "(明细)一次性扣除项目", 1, "detail"),
    ("3", "合计(1+2)", 0, "sum"),
]
_A201020_SUBTOTALS = [("1", ["1.1"]), ("2", ["2.1"]), ("3", ["1", "2"])]
_A201020_COLS = ("orig", "book", "normal", "accel", "reduce")


def compute_a201020(db: Session, year: int):
    """资产加速折旧优惠:返回 (行次, 项目, 资产原值, 账载折旧, 税收一般折旧, 加速折旧, 纳税调减, 加速优惠, 层级, 可录入)。
    加速优惠=加速−一般;纳税调减合计联动季报主表行21。"""
    recs = {r.line_no: r for r in db.scalars(
        select(models.TaxAccelDepr).where(models.TaxAccelDepr.year == year)).all()}
    vals: dict[str, dict] = {}
    for ln, _item, _lv, kind in _A201020_ROWS:
        r = recs.get(ln)
        if kind == "detail" and r is not None:
            vals[ln] = {"orig": r.orig_value, "book": r.book_dep, "normal": r.tax_normal,
                        "accel": r.accel_dep, "reduce": r.reduce_amount}
        else:
            vals[ln] = {k: Z for k in _A201020_COLS}
    for total, members in _A201020_SUBTOTALS:
        for k in _A201020_COLS:
            vals[total][k] = sum((vals[m][k] for m in members), Z)
    return [(ln, item, vals[ln]["orig"], vals[ln]["book"], vals[ln]["normal"],
             vals[ln]["accel"], vals[ln]["reduce"], vals[ln]["accel"] - vals[ln]["normal"],
             lv, kind == "detail")
            for ln, item, lv, kind in _A201020_ROWS]


def a201020_reduce_total(db: Session, year: int) -> Decimal:
    """资产加速折旧纳税调减金额合计(供季报主表行21联动)。"""
    return {r[0]: r for r in compute_a201020(db, year)}["3"][6]


# ---------- 税收优惠事项选项(国税码表)与汇总 ----------

# (类别, 代码, 名称)。类别:exempt 免税/减计/加计(→行22);income_relief 所得减免(→行25/季报23);
# tax_relief 减免所得税额(→行31/季报28)。加计扣除中的研发费用由 A107012 专表处理,不在此重复。
_PREF_OPTIONS = [
    ("exempt", "MSSR00010", "免税收入-国债利息收入"),
    ("exempt", "MSSR00021", "免税收入-符合条件的居民企业之间的股息红利"),
    ("exempt", "MSSR00030", "免税收入-符合条件的非营利组织的收入"),
    ("exempt", "MSSR00040", "免税收入-证券投资基金分配取得的收入"),
    ("exempt", "MSSR99999", "免税收入-其他"),
    ("exempt", "JJSR00010", "减计收入-取得铁路债券利息收入减半"),
    ("exempt", "JJSR00020", "减计收入-综合利用资源生产产品取得的收入"),
    ("exempt", "JJSR99999", "减计收入-其他"),
    ("exempt", "JASR00099", "加计扣除-其他(研发费用请在A107012填报)"),
    ("income_relief", "SD011", "所得减免-农、林、牧、渔业项目"),
    ("income_relief", "SD021", "所得减免-国家重点扶持的公共基础设施项目"),
    ("income_relief", "SD030", "所得减免-符合条件的环境保护、节能节水项目"),
    ("income_relief", "SD041", "所得减免-符合条件的技术转让项目"),
    ("income_relief", "SD060", "所得减免-合同能源管理项目"),
    ("income_relief", "SD999", "所得减免-其他"),
    ("tax_relief", "JMSE00201", "减免所得税-高新技术企业减按15%"),
    ("tax_relief", "JMSE00202", "减免所得税-经济特区等新设高新技术企业"),
    ("tax_relief", "JMSE99999", "减免所得税-其他(小型微利请用企业信息开关)"),
]
_PREF_CATEGORY_LABEL = {"exempt": "免税、减计收入及加计扣除",
                        "income_relief": "所得减免", "tax_relief": "减免所得税额"}


def preference_options() -> list[dict]:
    """税收优惠事项下拉选项(供前端展示)。"""
    return [{"category": cat, "category_label": _PREF_CATEGORY_LABEL[cat],
             "code": code, "name": name} for cat, code, name in _PREF_OPTIONS]


def compute_preferences(db: Session, report_year: int):
    """返回按码表顺序的优惠事项行 (类别, 类别名, 代码, 名称, 金额, 可录入=True)。"""
    recs = {p.code: p.amount for p in db.scalars(
        select(models.TaxPreference).where(
            models.TaxPreference.report_year == report_year)).all()}
    return [(cat, _PREF_CATEGORY_LABEL[cat], code, name, recs.get(code, Z), True)
            for cat, code, name in _PREF_OPTIONS]


def preference_totals(db: Session, report_year: int) -> dict[str, Decimal]:
    """按类别汇总优惠金额:{exempt, income_relief, tax_relief}。"""
    totals = {"exempt": Z, "income_relief": Z, "tax_relief": Z}
    recs = {p.code: p.amount for p in db.scalars(
        select(models.TaxPreference).where(
            models.TaxPreference.report_year == report_year)).all()}
    for cat, code, _name in _PREF_OPTIONS:
        totals[cat] += recs.get(code, Z)
    return totals


# ---------- 季报 A200000 ----------

def compute_rows(db: Session, year: int, quarter: int):
    """季报主表:返回 (行次, 项目, 金额, 层级) 列表。"""
    start, end = date(year, 1, 1), _quarter_end(year, quarter)
    a = _core_amounts(db, start, end)
    accel_reduce = a201020_reduce_total(db, year)                 # 21 资产加速折旧调减(A201020)
    pref = preference_totals(db, year)                            # 税收优惠事项汇总
    exempt = pref["exempt"]                                       # 22 免税、减计收入及加计扣除
    income_relief = pref["income_relief"]                         # 23 所得减免
    real_profit = a["total_profit"] - accel_reduce - exempt - income_relief   # 25 实际利润额
    taxable = real_profit if real_profit > 0 else Z
    tax_payable = (taxable * RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sm = small_micro_status(db, taxable, end, year)              # 小型微利复核(报表生成时按当前口径)
    micro = (taxable * SMALL_MICRO_RELIEF).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if sm["effective"] else Z
    relief = micro + pref["tax_relief"]                          # 28 减免所得税额(小微+其他优惠)
    after_relief = tax_payable - relief                          # 27-28
    rows = [
        ("1", "营业收入", a["revenue"]),
        ("1.1", "其中:自营出口收入", Z),
        ("1.2", "委托出口收入", Z),
        ("1.3", "出口代理费收入", Z),
        ("2", "减:营业成本", a["cost"]),
        ("3", "减:税金及附加", a["tax_surcharge"]),
        ("4", "减:销售费用", a["sell"]),
        ("5", "减:管理费用", a["admin"]),
        ("6", "减:研发费用", a["rd"]),
        ("7", "减:财务费用", a["fin"]),
        ("8", "加:其他收益", Z),
        ("9", "加:投资收益(9.1+9.2)(损失以-号填列)", a["invest"]),
        ("9.1", "其中:股权投资确认的处置收益", Z),
        ("9.2", "其他投资收益", Z),
        ("10", "加:净敞口套期收益(损失以-号填列)", Z),
        ("11", "加:公允价值变动收益(损失以-号填列)", a["fair_value"]),
        ("12", "加:信用减值损失(损失以-号填列)", Z),
        ("13", "加:资产减值损失(损失以-号填列)", -a["asset_impair"]),
        ("14", "加:资产处置收益(损失以-号填列)", Z),
        ("15", "营业利润(亏损以-号填列)", a["op_profit"]),
        ("16", "加:营业外收入", a["non_op_income"]),
        ("17", "减:营业外支出", a["non_op_expense"]),
        ("18", "利润总额(15+16-17)", a["total_profit"]),
        ("19", "加:特定业务计算的应纳税所得额", Z),
        ("19.1", "其中:销售未完工产品的收入", Z),
        ("20", "减:不征税收入", Z),
        ("21", "减:资产加速折旧、摊销(扣除)调减额(填写A201020)", accel_reduce),
        ("22", "减:免税收入、减计收入、加计扣除(22.1+22.2+…)", exempt),
        ("23", "减:所得减免(23.1+23.2+……)", income_relief),
        ("24", "减:弥补以前年度亏损", Z),
        ("25", "实际利润额(18+19-20-21-22-23-24)", real_profit),
        ("26", "税率(25%)", RATE),
        ("27", "应纳所得税额(25×26)", tax_payable),
        ("28", "减:减免所得税额(28.1+28.2+……)", relief),
        ("28.1", "其中:符合条件的小型微利企业减免企业所得税", micro),
        ("29", "减:抵免所得税额", Z),
        ("30", "减:本年累计已预缴所得税额", Z),
        ("31", "减:特定业务预缴(征)所得税额", Z),
        ("32", "本期应补(退)所得税额(27-28-29-30-31)", after_relief),
    ]
    return [(n, lb, v, _level(n)) for n, lb, v in rows]


# ---------- 年报 A100000 ----------

def compute_annual_rows(db: Session, year: int):
    """年报主表:返回 (行次, 类别, 项目, 金额, 层级) 列表。类别仅在该类首行填写。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    a = _core_amounts(db, start, end)
    profit = a["total_profit"]
    # 20/21 纳税调整增加/减少额,来自 A105000 合计(行46)的调增/调减
    a105 = compute_a105000(db, year)
    _, _, _, _, adj_add, adj_reduce, _, _ = a105[-1]
    pref = preference_totals(db, year)                   # 税收优惠事项汇总
    # 22 免税、减计收入及加计扣除 = A107012 研发加计扣除 + 其他免税/减计/加计事项
    exempt = a107012_deduction_total(db, year) + pref["exempt"]
    income_relief = pref["income_relief"]                # 25 所得减免
    adj_after = profit + adj_add - adj_reduce - exempt    # 24 纳税调整后所得(19/23=0)
    loss_offset = a106_offset_total(db, year)             # 26 弥补以前年度亏损(A106000)
    taxable = adj_after - income_relief - loss_offset     # 28 应纳税所得额(27=0),可为负(亏损)
    taxable_tax = taxable if taxable > 0 else Z           # 计税基数:亏损按 0
    tax_amount = (taxable_tax * RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)   # 30 应纳所得税额
    sm = small_micro_status(db, taxable_tax, end, year)  # 小型微利复核(应纳税所得额口径)
    micro = (taxable_tax * SMALL_MICRO_RELIEF).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if sm["effective"] else Z
    relief = micro + pref["tax_relief"]                  # 31 减免所得税额(小微+其他优惠)
    payable = tax_amount - relief                         # 33 应纳税额=36 实际应纳(32/34/35=0)
    prepaid = _prepaid_cit(db, year)                     # 37 本年累计已预缴(税务申报记录汇总)
    net_pay = payable - prepaid                          # 38/45 本年应补(退)所得税额
    C1, C2 = "利润总额计算", "应纳税所得额计算"
    C3, C4 = "应纳税额计算", "实际应补(退)税额计算"
    rows = [
        ("1", C1, "营业收入(填写A101010/101020/103000)", a["revenue"]),
        ("2", "", "减:营业成本(填写A102010/102020/103000)", a["cost"]),
        ("3", "", "减:税金及附加", a["tax_surcharge"]),
        ("4", "", "减:销售费用(填写A104000)", a["sell"]),
        ("5", "", "减:管理费用(填写A104000)", a["admin"]),
        ("6", "", "减:研发费用(填写A104000)", a["rd"]),
        ("7", "", "减:财务费用(填写A104000)", a["fin"]),
        ("8", "", "加:其他收益", Z),
        ("9", "", "加:投资收益(损失以-号填列)", a["invest"]),
        ("10", "", "加:净敞口套期收益(损失以-号填列)", Z),
        ("11", "", "加:公允价值变动收益(损失以-号填列)", a["fair_value"]),
        ("12", "", "加:信用减值损失(损失以-号填列)", Z),
        ("13", "", "加:资产减值损失(损失以-号填列)", -a["asset_impair"]),
        ("14", "", "加:资产处置收益(损失以-号填列)", Z),
        ("15", "", "二、营业利润(亏损以-号填列)", a["op_profit"]),
        ("16", "", "加:营业外收入(填写A101010/101020/103000)", a["non_op_income"]),
        ("17", "", "减:营业外支出(填写A102010/102020/103000)", a["non_op_expense"]),
        ("18", "", "三、利润总额(15+16-17)", profit),
        ("19", C2, "减:境外所得(填写A108010)", Z),
        ("20", "", "加:纳税调整增加额(填写A105000)", adj_add),
        ("21", "", "减:纳税调整减少额(填写A105000)", adj_reduce),
        ("22", "", "减:免税、减计收入及加计扣除(填写A107010)", exempt),
        ("23", "", "加:境外应税所得抵减境内亏损(填写A108000)", Z),
        ("24", "", "四、纳税调整后所得(18-19+20-21-22+23)", adj_after),
        ("25", "", "减:所得减免(填写A107020)", income_relief),
        ("26", "", "减:弥补以前年度亏损(填写A106000)", loss_offset),
        ("27", "", "减:抵扣应纳税所得额(填写A107030)", Z),
        ("28", "", "五、应纳税所得额(24-25-26-27)", taxable),
        ("29", C3, "税率(25%)", RATE),
        ("30", "", "六、应纳所得税额(28×29)", tax_amount),
        ("31", "", "减:减免所得税额(填写A107040)", relief),
        ("32", "", "减:抵免所得税额(填写A107050)", Z),
        ("33", "", "七、应纳税额(30-31-32)", payable),
        ("34", "", "加:境外所得应纳所得税额(填写A108000)", Z),
        ("35", "", "减:境外所得抵免所得税额(填写A108000)", Z),
        ("36", "", "八、实际应纳所得税额(33+34-35)", payable),
        ("37", C4, "减:本年累计预缴所得税额", prepaid),
        ("38", "", "九、本年应补(退)所得税额(36-37)", net_pay),
        ("39", "", "其中:总机构分摊本年应补(退)所得税额(填写A109000)", Z),
        ("40", "", "财政集中分配本年应补(退)所得税额(填写A109000)", Z),
        ("41", "", "总机构主体生产经营部门分摊本年应补(退)所得税额(填写A109000)", Z),
        ("45", "", "十、本年实际应补(退)所得税额", net_pay),
    ]
    return [(n, cat, lb, v, _level(n)) for n, cat, lb, v in rows]


# ---------- 附表 A101010 一般企业收入明细表 ----------

def compute_a101010(db: Session, year: int):
    """收入明细:返回 (行次, 项目, 金额, 层级)。主营/其他/营业外收入自动取数。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    b = reports_cn.Balances(reports_cn._movement(db, start, end))
    main = b.net_credit("6001")       # 主营业务收入
    other = b.net_credit("6051")      # 其他业务收入
    nonop = b.net_credit("6301")      # 营业外收入
    return [
        ("1", "一、营业收入(2+9)", main + other, 0),
        ("2", "(一)主营业务收入(3+5+6+7+8)", main, 1),
        ("3", "1.销售商品收入", main, 2),
        ("4", "其中:非货币性资产交换收入", Z, 3),
        ("5", "2.提供劳务收入", Z, 2),
        ("6", "3.建造合同收入", Z, 2),
        ("7", "4.让渡资产使用权收入", Z, 2),
        ("8", "5.其他", Z, 2),
        ("9", "(二)其他业务收入(10+12+13+14+15)", other, 1),
        ("10", "1.销售材料收入", Z, 2),
        ("11", "其中:非货币性资产交换收入", Z, 3),
        ("12", "2.出租固定资产收入", Z, 2),
        ("13", "3.出租无形资产收入", Z, 2),
        ("14", "4.出租包装物和商品收入", Z, 2),
        ("15", "5.其他", other, 2),
        ("16", "二、营业外收入(17+18+…+26)", nonop, 0),
        ("17", "(一)非流动资产处置利得", Z, 1),
        ("18", "(二)非货币性资产交换利得", Z, 1),
        ("19", "(三)债务重组利得", Z, 1),
        ("20", "(四)政府补助利得", Z, 1),
        ("21", "(五)盘盈利得", Z, 1),
        ("22", "(六)捐赠利得", Z, 1),
        ("23", "(七)罚没利得", Z, 1),
        ("24", "(八)确实无法偿付的应付款项", Z, 1),
        ("25", "(九)汇兑收益", Z, 1),
        ("26", "(十)其他", nonop, 1),
    ]


# ---------- 附表 A102010 一般企业成本支出明细表 ----------

def compute_a102010(db: Session, year: int):
    """成本支出明细:返回 (行次, 项目, 金额, 层级)。主营/其他/营业外支出自动取数。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    b = reports_cn.Balances(reports_cn._movement(db, start, end))
    main = b.net_debit("6401")        # 主营业务成本
    other = b.net_debit("6402")       # 其他业务成本
    nonop = b.net_debit("6711")       # 营业外支出
    return [
        ("1", "一、营业成本(2+9)", main + other, 0),
        ("2", "(一)主营业务成本(3+5+6+7+8)", main, 1),
        ("3", "1.销售商品成本", main, 2),
        ("4", "其中:非货币性资产交换成本", Z, 3),
        ("5", "2.提供劳务成本", Z, 2),
        ("6", "3.建造合同成本", Z, 2),
        ("7", "4.让渡资产使用权成本", Z, 2),
        ("8", "5.其他", Z, 2),
        ("9", "(二)其他业务成本(10+12+13+14+15)", other, 1),
        ("10", "1.材料销售成本", Z, 2),
        ("11", "其中:非货币性资产交换成本", Z, 3),
        ("12", "2.出租固定资产成本", Z, 2),
        ("13", "3.出租无形资产成本", Z, 2),
        ("14", "4.包装物出租成本", Z, 2),
        ("15", "5.其他", other, 2),
        ("16", "二、营业外支出(17+18+…+26)", nonop, 0),
        ("17", "(一)非流动资产处置损失", Z, 1),
        ("18", "(二)非货币性资产交换损失", Z, 1),
        ("19", "(三)债务重组损失", Z, 1),
        ("20", "(四)非常损失", Z, 1),
        ("21", "(五)捐赠支出", Z, 1),
        ("22", "(六)赞助支出", Z, 1),
        ("23", "(七)罚没支出", Z, 1),
        ("24", "(八)坏账损失", Z, 1),
        ("25", "(九)无法收回的债券股权投资损失", Z, 1),
        ("26", "(十)其他", nonop, 1),
    ]


# ---------- 附表 A104000 期间费用明细表 ----------

# (行次, 项目, 归集关键字);关键字命中二级科目名称即归入该行。空关键字为兜底「其他」。
_A104_ROWS = [
    ("1", "一、职工薪酬", ("薪酬", "工资", "社保", "公积金", "福利", "五险")),
    ("2", "二、劳务费", ("劳务",)),
    ("3", "三、咨询顾问费", ("咨询", "顾问")),
    ("4", "四、业务招待费", ("招待",)),
    ("5", "五、广告费和业务宣传费", ("广告", "宣传")),
    ("6", "六、佣金和手续费", ("佣金", "手续费")),
    ("7", "七、资产折旧摊销费", ("折旧", "摊销")),
    ("8", "八、财产损耗、盘亏及毁损损失", ("盘亏", "毁损", "损耗")),
    ("9", "九、办公费", ("办公",)),
    ("10", "十、董事会费", ("董事会",)),
    ("11", "十一、租赁费", ("租赁", "房租", "租金")),
    ("12", "十二、诉讼费", ("诉讼",)),
    ("13", "十三、差旅费", ("差旅",)),
    ("14", "十四、保险费", ("保险",)),
    ("15", "十五、运输、仓储费", ("运输", "仓储", "物流")),
    ("16", "十六、修理费", ("修理", "维修")),
    ("17", "十七、包装费", ("包装",)),
    ("18", "十八、技术转让费", ("技术转让",)),
    ("19", "十九、研究费用", ("研究", "研发")),
    ("20", "二十、各项税费", ("税费", "印花", "税金")),
    ("21", "二十一、利息收支", ("利息",)),
    ("22", "二十二、汇兑差额", ("汇兑",)),
    ("23", "二十三、现金折扣", ("折扣",)),
    ("24", "二十四、党组织工作经费", ("党组织", "党费", "党建")),
    ("25", "二十五、其他", ()),
]
_A104_FEE_CODES = ("6601", "6602", "6603")   # 销售 / 管理 / 财务费用


def _a104_classify(name: str) -> str:
    for rno, _label, kws in _A104_ROWS:
        if kws and any(k in name for k in kws):
            return rno
    return "25"


def compute_a104000(db: Session, year: int):
    """期间费用明细:返回 (行次, 项目, 销售费用, 管理费用, 财务费用)。
    按二级科目名称关键字归集到标准行,未匹配或无二级的差额计入「其他」,列合计=各费用发生额。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    mv = reports_cn._movement(db, start, end)
    sub = reports_cn._movement_by_sub(db, start, end)
    totals = {code: mv.get(code, Z) for code in _A104_FEE_CODES}
    grid = {rno: {c: Z for c in _A104_FEE_CODES} for rno, _l, _k in _A104_ROWS}
    matched = {c: Z for c in _A104_FEE_CODES}
    for (code, subname), (d, c) in sub.items():
        if code not in _A104_FEE_CODES:
            continue
        amt = d - c
        rno = _a104_classify(subname)
        grid[rno][code] += amt
        matched[code] += amt
    # 无二级或未归集的差额并入「其他」,保证列合计 = 费用发生额
    for code in _A104_FEE_CODES:
        diff = totals[code] - matched[code]
        if diff != 0:
            grid["25"][code] += diff
    rows = [(rno, label, grid[rno]["6601"], grid[rno]["6602"], grid[rno]["6603"])
            for rno, label, _k in _A104_ROWS]
    rows.append(("26", "合计(1+2+3+…24+25)",
                 totals["6601"], totals["6602"], totals["6603"]))
    return rows


# ---------- 附表 A105000 纳税调整项目明细表 ----------

# (行次, 项目, 层级, 类型)。sum=小计/合计(自动汇总),detail=可录入且计入小计,
# memo=「其中」行(可录入,不计入小计)。
_A105_ROWS = [
    ("1", "一、收入类调整项目(2+3+…8+10+11)", 0, "sum"),
    ("2", "(一)视同销售收入(填写A105010)", 1, "detail"),
    ("3", "(二)未按权责发生制原则确认的收入(填写A105020)", 1, "detail"),
    ("4", "(三)投资收益(填写A105030)", 1, "detail"),
    ("5", "(四)按权益法核算长期股权投资对初始投资成本调整确认收益", 1, "detail"),
    ("6", "(五)交易性金融资产初始投资调整", 1, "detail"),
    ("7", "(六)公允价值变动净损益", 1, "detail"),
    ("8", "(七)不征税收入", 1, "detail"),
    ("9", "其中:专项用途财政性资金(填写A105040)", 2, "memo"),
    ("10", "(八)销售折扣、折让和退回", 1, "detail"),
    ("11", "(九)其他", 1, "detail"),
    ("12", "二、扣除类调整项目(13+14+…24+26+27+28+29+30)", 0, "sum"),
    ("13", "(一)视同销售成本(填写A105010)", 1, "detail"),
    ("14", "(二)职工薪酬(填写A105050)", 1, "linked"),
    ("15", "(三)业务招待费支出", 1, "detail"),
    ("16", "(四)广告费和业务宣传费支出(填写A105060)", 1, "linked"),
    ("17", "(五)捐赠支出(填写A105070)", 1, "detail"),
    ("18", "(六)利息支出", 1, "detail"),
    ("19", "(七)罚金、罚款和被没收财物的损失", 1, "detail"),
    ("20", "(八)税收滞纳金、加收利息", 1, "detail"),
    ("21", "(九)赞助支出", 1, "detail"),
    ("22", "(十)与未实现融资收益相关在当期确认的财务费用", 1, "detail"),
    ("23", "(十一)佣金和手续费支出(保险企业填写A105060)", 1, "detail"),
    ("24", "(十二)不征税收入用于支出所形成的费用", 1, "detail"),
    ("25", "其中:专项用途财政性资金用于支出所形成的费用(填写A105040)", 2, "memo"),
    ("26", "(十三)跨期扣除项目", 1, "detail"),
    ("27", "(十四)与取得收入无关的支出", 1, "detail"),
    ("28", "(十五)境外所得分摊的共同支出", 1, "detail"),
    ("29", "(十六)党组织工作经费", 1, "detail"),
    ("30", "(十七)其他", 1, "detail"),
    ("31", "三、资产类调整项目(32+33+34+35)", 0, "sum"),
    ("32", "(一)资产折旧、摊销(填写A105080)", 1, "linked"),
    ("33", "(二)资产减值准备金", 1, "detail"),
    ("34", "(三)资产损失(填写A105090)", 1, "detail"),
    ("35", "(四)其他", 1, "detail"),
    ("36", "四、特殊事项调整项目(37+38+…+43)", 0, "sum"),
    ("37", "(一)企业重组及递延纳税事项(填写A105100)", 1, "detail"),
    ("38", "(二)政策性搬迁(填写A105110)", 1, "detail"),
    ("39", "(三)特殊行业准备金", 1, "sum"),
    ("39.1", "1.保险公司保险保障基金", 2, "detail"),
    ("39.2", "2.保险公司准备金", 2, "detail"),
    ("39.3", "其中:已发生未报案未决赔款准备金", 3, "memo"),
    ("39.4", "3.证券行业准备金", 2, "detail"),
    ("39.5", "4.期货行业准备金", 2, "detail"),
    ("39.6", "5.中小企业融资(信用)担保机构准备金", 2, "detail"),
    ("39.7", "6.金融企业、小额贷款公司准备金(填写A105120)", 2, "detail"),
    ("40", "(四)房地产开发企业特定业务计算的纳税调整额(填写A105010)", 1, "detail"),
    ("41", "(五)合伙企业法人合伙人应分得的应纳税所得额", 1, "detail"),
    ("42", "(六)发行永续债利息支出", 1, "detail"),
    ("43", "(七)其他", 1, "detail"),
    ("44", "五、特别纳税调整应税所得", 0, "detail"),
    ("45", "六、其他", 0, "detail"),
    ("46", "合计(1+12+31+36+44+45)", 0, "sum"),
]

# 小计计算(按依赖顺序:先子小计 39,再顶层小计,最后合计 46)
_A105_SUBTOTALS = [
    ("1", ["2", "3", "4", "5", "6", "7", "8", "10", "11"]),
    ("12", ["13", "14", "15", "16", "17", "18", "19", "20", "21", "22", "23",
            "24", "26", "27", "28", "29", "30"]),
    ("31", ["32", "33", "34", "35"]),
    ("39", ["39.1", "39.2", "39.4", "39.5", "39.6", "39.7"]),
    ("36", ["37", "38", "39", "40", "41", "42", "43"]),
    ("46", ["1", "12", "31", "36", "44", "45"]),
]
_A105_COLS = ("book", "tax", "add", "reduce")


def compute_a105000(db: Session, year: int):
    """纳税调整明细:返回 (行次, 项目, 账载, 税收, 调增, 调减, 层级, 可录入)。
    明细行取用户录入值,小计/合计自动汇总。"""
    recs = {r.line_no: r for r in db.scalars(
        select(models.TaxAdjustment).where(models.TaxAdjustment.year == year)).all()}
    vals: dict[str, dict] = {}
    for ln, _item, _lv, kind in _A105_ROWS:
        r = recs.get(ln)
        if kind in ("detail", "memo") and r is not None:
            vals[ln] = {"book": r.book_amount, "tax": r.tax_amount,
                        "add": r.add_amount, "reduce": r.reduce_amount}
        else:
            vals[ln] = {k: Z for k in _A105_COLS}
    # 行14/16/32 由专表带出(账载−税收:>0 调增,<0 调减)
    def _linked(adj):
        return {"book": Z, "tax": Z, "add": adj if adj > 0 else Z, "reduce": -adj if adj < 0 else Z}
    vals["14"] = _linked(a105050_adjust_total(db, year))   # 职工薪酬 A105050
    vals["16"] = _linked(a105060_adjust_total(db, year))   # 广宣费 A105060
    vals["32"] = _linked(a105080_adjust_total(db, year))   # 资产折旧摊销 A105080
    for total, members in _A105_SUBTOTALS:
        for k in _A105_COLS:
            vals[total][k] = sum((vals[m][k] for m in members), Z)
    return [(ln, item, vals[ln]["book"], vals[ln]["tax"], vals[ln]["add"],
             vals[ln]["reduce"], lv, kind in ("detail", "memo"))
            for ln, item, lv, kind in _A105_ROWS]


# ---------- 附表 A106000 企业所得税弥补亏损明细表 ----------

# 行1..10 前十..前一年度,行11 本年度,行12 合计。
_A106_ITEMS = [
    ("1", "前十年度"), ("2", "前九年度"), ("3", "前八年度"), ("4", "前七年度"),
    ("5", "前六年度"), ("6", "前五年度"), ("7", "前四年度"), ("8", "前三年度"),
    ("9", "前二年度"), ("10", "前一年度"), ("11", "本年度"),
]


def compute_a106000(db: Session, report_year: int):
    """弥补亏损明细:返回 (行次, 项目, 所属年度, 当年亏损额, 当年待弥补额, 本年弥补额, 可结转以后年度, 可录入)。
    行1..10 为以前年度(可弥补),行11 本年度,行12 合计。主表行26=以前年度本年弥补额合计。"""
    recs = {r.line_no: r for r in db.scalars(
        select(models.TaxLossCarryover).where(
            models.TaxLossCarryover.report_year == report_year)).all()}
    rows = []
    sum_loss = sum_pending = sum_offset = sum_carry = Z
    for idx, (ln, item) in enumerate(_A106_ITEMS):
        occur_year = report_year - (10 - idx)   # 行1(idx0)→前十年 … 行10→前一年,行11(idx10)→本年
        r = recs.get(ln)
        loss = r.loss_amount if r else Z
        pending = r.pending_amount if r else Z
        offset = r.offset_amount if r else Z
        carry = pending - offset                # 可结转以后年度弥补
        rows.append((ln, item, occur_year, loss, pending, offset, carry, True))
        if ln != "11":                          # 本年度不计入"以前年度弥补"合计
            sum_offset += offset
        sum_loss += loss
        sum_pending += pending
        sum_carry += carry
    rows.append(("12", "可结转以后年度弥补的亏损额合计", None,
                 sum_loss, sum_pending, sum_offset, sum_carry, False))
    return rows


def a106_offset_total(db: Session, report_year: int) -> Decimal:
    """以前年度用本年度所得弥补的亏损额合计(供主表行26联动)。"""
    return compute_a106000(db, report_year)[-1][5]


# ---------- 附表 A105080 资产折旧、摊销及纳税调整明细表 ----------

# (行次, 项目, 层级, 类型)。sum=小计/合计(自动),detail=可录入明细。
_A105080_ROWS = [
    ("1", "一、固定资产(2+3+4+5+6+7)", 0, "sum"),
    ("2", "(一)房屋、建筑物", 1, "detail"),
    ("3", "(二)飞机、火车、轮船、机器、机械和其他生产设备", 1, "detail"),
    ("4", "(三)与生产经营活动有关的器具、工具、家具等", 1, "detail"),
    ("5", "(四)飞机、火车、轮船以外的运输工具", 1, "detail"),
    ("6", "(五)电子设备", 1, "detail"),
    ("7", "(六)其他", 1, "detail"),
    ("8", "二、生产性生物资产(9+10)", 0, "sum"),
    ("9", "(一)林木类", 1, "detail"),
    ("10", "(二)畜类", 1, "detail"),
    ("11", "三、无形资产(12+13+…+19)", 0, "sum"),
    ("12", "(一)专利权", 1, "detail"),
    ("13", "(二)商标权", 1, "detail"),
    ("14", "(三)著作权", 1, "detail"),
    ("15", "(四)土地使用权", 1, "detail"),
    ("16", "(五)非专利技术", 1, "detail"),
    ("17", "(六)特许权使用费", 1, "detail"),
    ("18", "(七)软件", 1, "detail"),
    ("19", "(八)其他", 1, "detail"),
    ("20", "四、长期待摊费用(21+22+23+24+25)", 0, "sum"),
    ("21", "(一)已足额提取折旧的固定资产的改建支出", 1, "detail"),
    ("22", "(二)租入固定资产的改建支出", 1, "detail"),
    ("23", "(三)固定资产的大修理支出", 1, "detail"),
    ("24", "(四)开办费", 1, "detail"),
    ("25", "(五)其他", 1, "detail"),
    ("26", "五、油气勘探投资", 0, "detail"),
    ("27", "六、油气开发投资", 0, "detail"),
    ("30", "合计", 0, "sum"),
]
_A105080_SUBTOTALS = [
    ("1", ["2", "3", "4", "5", "6", "7"]),
    ("8", ["9", "10"]),
    ("11", ["12", "13", "14", "15", "16", "17", "18", "19"]),
    ("20", ["21", "22", "23", "24", "25"]),
    ("30", ["1", "8", "11", "20", "26", "27"]),
]
_A105080_COLS = ("orig", "book_dep", "tax_basis", "tax_dep")


def compute_a105080(db: Session, report_year: int):
    """资产折旧摊销明细:返回 (行次, 项目, 资产原值, 账载折旧, 计税基础, 税收折旧, 纳税调整金额, 层级, 可录入)。
    纳税调整金额 = 账载折旧 − 税收折旧;合计联动 A105000 行32。"""
    recs = {r.line_no: r for r in db.scalars(
        select(models.TaxAssetDepreciation).where(
            models.TaxAssetDepreciation.report_year == report_year)).all()}
    vals: dict[str, dict] = {}
    for ln, _item, _lv, kind in _A105080_ROWS:
        r = recs.get(ln)
        if kind == "detail" and r is not None:
            vals[ln] = {"orig": r.orig_value, "book_dep": r.book_dep,
                        "tax_basis": r.tax_basis, "tax_dep": r.tax_dep}
        else:
            vals[ln] = {k: Z for k in _A105080_COLS}
    for total, members in _A105080_SUBTOTALS:
        for k in _A105080_COLS:
            vals[total][k] = sum((vals[m][k] for m in members), Z)
    return [(ln, item, vals[ln]["orig"], vals[ln]["book_dep"], vals[ln]["tax_basis"],
             vals[ln]["tax_dep"], vals[ln]["book_dep"] - vals[ln]["tax_dep"], lv, kind == "detail")
            for ln, item, lv, kind in _A105080_ROWS]


def a105080_adjust_total(db: Session, report_year: int) -> Decimal:
    """资产折旧摊销纳税调整金额合计(账载−税收,供 A105000 行32联动)。"""
    return compute_a105080(db, report_year)[-1][6]


# ---------- 附表 A107012 研发费用加计扣除优惠明细表 ----------

# (行次, 项目, 层级, 类型)。sum=按成员小计;detail=录入;memo=其中;ratio=加计比例(默认1.0);
# formula=特殊公式(行40/45/47/51)。
_A107_ROWS = [
    ("1", "本年可享受研发费用加计扣除项目数量", 0, "detail"),
    ("2", "一、自主研发、合作研发、集中研发(3+7+16+19+23+34)", 0, "sum"),
    ("3", "(一)人员人工费用(4+5+6)", 1, "sum"),
    ("4", "1.直接从事研发活动人员工资薪金", 2, "detail"),
    ("5", "2.直接从事研发活动人员五险一金", 2, "detail"),
    ("6", "3.外聘研发人员的劳务费用", 2, "detail"),
    ("7", "(二)直接投入费用(8+9+…+15)", 1, "sum"),
    ("8", "1.研发活动直接消耗材料费用", 2, "detail"),
    ("9", "2.研发活动直接消耗燃料费用", 2, "detail"),
    ("10", "3.研发活动直接消耗动力费用", 2, "detail"),
    ("11", "4.用于中间试验和产品试制的模具、工艺装备开发及制造费", 2, "detail"),
    ("12", "5.用于不构成固定资产的样品、样机及一般测试手段购置费", 2, "detail"),
    ("13", "6.用于试制产品的检验费", 2, "detail"),
    ("14", "7.用于研发活动的仪器、设备的运行维护、调整、检验、维修等费用", 2, "detail"),
    ("15", "8.通过经营租赁方式租入的用于研发活动的仪器、设备租赁费", 2, "detail"),
    ("16", "(三)折旧费用(17+18)", 1, "sum"),
    ("17", "1.用于研发活动的仪器的折旧费", 2, "detail"),
    ("18", "2.用于研发活动的设备的折旧费", 2, "detail"),
    ("19", "(四)无形资产摊销(20+21+22)", 1, "sum"),
    ("20", "1.用于研发活动的软件的摊销费用", 2, "detail"),
    ("21", "2.用于研发活动的专利权的摊销费用", 2, "detail"),
    ("22", "3.用于研发活动的非专利技术的摊销费用", 2, "detail"),
    ("23", "(五)新产品设计费等(24+25+26+27)", 1, "sum"),
    ("24", "1.新产品设计费", 2, "detail"),
    ("25", "2.新工艺规程制定费", 2, "detail"),
    ("26", "3.新药研制的临床试验费", 2, "detail"),
    ("27", "4.勘探开发技术的现场试验费", 2, "detail"),
    ("28", "(六)其他相关费用(29+30+31+32+33)", 1, "sum"),
    ("29", "1.技术图书资料费、资料翻译费、专家咨询费等", 2, "detail"),
    ("30", "2.研发成果的检索、分析、评议、论证、鉴定等费用", 2, "detail"),
    ("31", "3.知识产权的申请费、注册费、代理费", 2, "detail"),
    ("32", "4.职工福利费、补充养老保险费、补充医疗保险费", 2, "detail"),
    ("33", "5.差旅费、会议费", 2, "detail"),
    ("34", "(七)经限额调整后的其他相关费用", 1, "detail"),
    ("35", "二、委托研发(36+37+39)", 0, "sum"),
    ("36", "(一)委托境内机构或个人进行研发活动所发生的费用", 1, "detail"),
    ("37", "(二)委托境外机构进行研发活动发生的费用", 1, "detail"),
    ("38", "其中:允许加计扣除的委托境外机构进行研发活动发生的费用", 2, "detail"),
    ("39", "(三)委托境外个人进行研发活动发生的费用", 1, "detail"),
    ("40", "三、年度研发费用小计(2+36×80%+38)", 0, "formula"),
    ("41", "(一)本年费用化金额", 1, "detail"),
    ("42", "(二)本年资本化金额", 1, "detail"),
    ("43", "四、本年形成无形资产摊销额", 0, "detail"),
    ("44", "五、以前年度形成无形资产本年摊销额", 0, "detail"),
    ("45", "六、允许扣除的研发费用合计(41+43+44)", 0, "formula"),
    ("46", "减:特殊收入部分", 0, "detail"),
    ("47", "七、允许扣除的研发费用抵减特殊收入后的金额(45-46)", 0, "formula"),
    ("48", "减:当年销售研发活动直接形成产品对应的材料部分", 0, "detail"),
    ("49", "减:以前年度销售研发活动直接形成产品对应材料部分结转", 0, "detail"),
    ("50", "八、加计扣除比例(如 1.00 表示 100%)", 0, "ratio"),
    ("51", "九、本年研发费用加计扣除总额((47-48-49)×50)", 0, "formula"),
    ("52", "十、销售产品对应材料部分结转以后年度扣减金额", 0, "detail"),
]
_A107_SUBTOTALS = [
    ("3", ["4", "5", "6"]),
    ("7", ["8", "9", "10", "11", "12", "13", "14", "15"]),
    ("16", ["17", "18"]),
    ("19", ["20", "21", "22"]),
    ("23", ["24", "25", "26", "27"]),
    ("28", ["29", "30", "31", "32", "33"]),
    ("2", ["3", "7", "16", "19", "23", "34"]),
    ("35", ["36", "37", "39"]),
]
_RD_INPUT = {"detail", "memo", "ratio"}


def compute_a107012(db: Session, report_year: int):
    """研发费用加计扣除:返回 (行次, 项目, 金额, 层级, 可录入)。行51为本年加计扣除总额。"""
    recs = {r.line_no: r for r in db.scalars(
        select(models.TaxRdDeduction).where(
            models.TaxRdDeduction.report_year == report_year)).all()}
    v: dict[str, Decimal] = {}
    for ln, _item, _lv, kind in _A107_ROWS:
        r = recs.get(ln)
        if kind in _RD_INPUT and r is not None:
            v[ln] = r.amount
        elif kind == "ratio":
            v[ln] = Decimal("1")            # 加计比例默认 100%
        else:
            v[ln] = Z
    for total, members in _A107_SUBTOTALS:
        v[total] = sum((v[m] for m in members), Z)
    # 特殊公式行
    v["40"] = v["2"] + (v["36"] * Decimal("0.8")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) + v["38"]
    v["45"] = v["41"] + v["43"] + v["44"]
    v["47"] = v["45"] - v["46"]
    ratio = v["50"]   # 行50 已在读取时对未录入置默认 1;显式录入 0(不加计)须保留
    v["51"] = ((v["47"] - v["48"] - v["49"]) * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return [(ln, item, v[ln], lv, kind in _RD_INPUT)
            for ln, item, lv, kind in _A107_ROWS]


def a107012_deduction_total(db: Session, report_year: int) -> Decimal:
    """本年研发费用加计扣除总额(行51,供主表行22联动)。"""
    return {r[0]: r for r in compute_a107012(db, report_year)}["51"][2]


def a107012_warnings(db: Session, report_year: int) -> list[str]:
    """研发费用加计扣除合规校验:委托境外研发限额等。返回警示文本列表(空=无异常)。"""
    v = {r[0]: r[2] for r in compute_a107012(db, report_year)}
    warns = []
    domestic = v.get("2", Z)                 # 境内自主/合作/集中研发费用合计
    entrust_oversea = v.get("37", Z)         # 委托境外机构研发费用
    allowed_oversea = v.get("38", Z)         # 其中:允许加计扣除的委托境外费用(录入)
    # 政策:委托境外研发费用按实际发生额80%计入,且不超过境内符合条件研发费用的2/3
    limit = min((entrust_oversea * Decimal("0.8")).quantize(Decimal("0.01")),
                (domestic * Decimal("2") / Decimal("3")).quantize(Decimal("0.01")))
    if allowed_oversea > limit:
        warns.append(
            f"行38「允许加计扣除的委托境外研发费用」{float(allowed_oversea):.2f} 元 已超过限额 "
            f"{float(limit):.2f} 元(不超过 委托境外×80% 与 境内研发费用×2/3 的较小者),请核减。")
    return warns


# ---------- 附表 A105050 职工薪酬支出及纳税调整明细表 ----------

# (行次, 项目, 层级, 类型)。sum=合计;detail=可录入;memo=其中/子项(不计入合计)。
_A105050_ROWS = [
    ("1", "一、工资薪金支出", 0, "detail"),
    ("2", "其中:股权激励", 1, "memo"),
    ("3", "二、职工福利费支出", 0, "detail"),
    ("4", "三、职工教育经费支出", 0, "detail"),
    ("5", "其中:按税收规定比例扣除的职工教育经费", 1, "memo"),
    ("6", "按税收规定全额扣除的职工培训费用", 1, "memo"),
    ("7", "四、工会经费支出", 0, "detail"),
    ("8", "五、各类基本社会保障性缴款", 0, "detail"),
    ("9", "六、住房公积金", 0, "detail"),
    ("10", "七、补充养老保险", 0, "detail"),
    ("11", "八、补充医疗保险", 0, "detail"),
    ("12", "九、其他", 0, "detail"),
    ("13", "合计(1+3+4+7+8+9+10+11+12)", 0, "sum"),
]
_A105050_SUM_MEMBERS = ["1", "3", "4", "7", "8", "9", "10", "11", "12"]


def compute_a105050(db: Session, report_year: int):
    """职工薪酬纳税调整:返回 (行次, 项目, 账载, 实际发生, 以前结转, 税收金额, 纳税调整, 结转以后, 层级, 可录入)。
    纳税调整=账载−税收;结转以后=实际+以前结转−税收;合计联动 A105000 行14。"""
    recs = {r.line_no: r for r in db.scalars(
        select(models.TaxSalaryAdjust).where(
            models.TaxSalaryAdjust.report_year == report_year)).all()}
    cols = ("book", "actual", "prev", "tax")
    vals: dict[str, dict] = {}
    for ln, _item, _lv, kind in _A105050_ROWS:
        r = recs.get(ln)
        if kind in ("detail", "memo") and r is not None:
            vals[ln] = {"book": r.book_amount, "actual": r.actual_amount,
                        "prev": r.prev_carry, "tax": r.tax_amount}
        else:
            vals[ln] = {k: Z for k in cols}
    for k in cols:
        vals["13"][k] = sum((vals[m][k] for m in _A105050_SUM_MEMBERS), Z)
    out = []
    for ln, item, lv, kind in _A105050_ROWS:
        v = vals[ln]
        adjust = v["book"] - v["tax"]
        carry = v["actual"] + v["prev"] - v["tax"]
        out.append((ln, item, v["book"], v["actual"], v["prev"], v["tax"],
                    adjust, carry, lv, kind in ("detail", "memo")))
    return out


def a105050_adjust_total(db: Session, report_year: int) -> Decimal:
    """职工薪酬纳税调整合计(账载−税收,供 A105000 行14联动)。"""
    return {r[0]: r for r in compute_a105050(db, report_year)}["13"][6]


# ---------- 附表 A105060 广告费和业务宣传费跨年度纳税调整明细表 ----------

# (行次, 项目, 类型)。detail=录入;ratio=扣除率;formula=公式;base=营业收入基数(自动)。
_A105060_ROWS = [
    ("1", "本年广告费和业务宣传费支出", "detail"),
    ("2", "税收规定扣除率(如 0.15=15%)", "ratio"),
    ("3", "本年计算扣除限额(营业收入×扣除率)", "formula"),
    ("4", "以前年度累计结转扣除额", "detail"),
    ("5", "本年扣除的广宣费(不超过限额)", "formula"),
    ("6", "纳税调整金额(本年支出−本年扣除)", "formula"),
    ("7", "累计结转以后年度扣除额(本年支出+以前结转−本年扣除)", "formula"),
]


def compute_a105060(db: Session, report_year: int):
    """广宣费跨年度纳税调整:返回 (行次, 项目, 金额, 可录入)。行6纳税调整联动 A105000 行16。"""
    recs = {r.line_no: r.amount for r in db.scalars(
        select(models.TaxAdMedia).where(models.TaxAdMedia.report_year == report_year)).all()}
    start, end = date(report_year, 1, 1), date(report_year, 12, 31)
    revenue = _core_amounts(db, start, end)["revenue"]           # 营业收入基数
    v = {}
    v["1"] = recs.get("1", Z)
    v["2"] = recs.get("2") if recs.get("2") is not None else Decimal("0.15")  # 扣除率默认15%;显式0(如烟草不得扣除)须保留
    v["3"] = (revenue * v["2"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)        # 扣除限额
    v["4"] = recs.get("4", Z)
    v["5"] = min(v["1"] + v["4"], v["3"])                        # 本年可扣除
    v["6"] = v["1"] - v["5"]                                     # 纳税调整(通常调增)
    v["7"] = v["1"] + v["4"] - v["5"]                            # 结转以后
    return [(ln, item, v[ln], kind in ("detail", "ratio")) for ln, item, kind in _A105060_ROWS]


def a105060_adjust_total(db: Session, report_year: int) -> Decimal:
    """广宣费纳税调整金额(行6,供 A105000 行16联动)。"""
    return {r[0]: r for r in compute_a105060(db, report_year)}["6"][2]


# ---------- Excel 渲染 ----------

def _write_kv(ws, title: str, company, period: str,
              rows: list, has_category: bool) -> None:
    """通用「行次 / [类别] / 项目(按层级缩进) / 金额」表渲染到给定 worksheet。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 4 if has_category else 3

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30

    meta = [
        f"税款所属期间:{period}",
        f"纳税人识别号(统一社会信用代码):{(company.tax_number if company else '') or ''}",
        f"纳税人名称:{(company.name if company else '') or ''}    金额单位:人民币元(列至角分)",
    ]
    r = 2
    for m in meta:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        ws.cell(r, 1, m).alignment = left
        r += 1

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "类别", "项目", "本年金额"] if has_category else ["行次", "项目", "本年累计金额"]
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for row in rows:
        if has_category:
            line_no, category, label, amount, level = row
        else:
            line_no, label, amount, level = row
            category = None
        col = 1
        ws.cell(r, col, line_no).alignment = center
        col += 1
        if has_category:
            ws.cell(r, col, category or "").alignment = center
            col += 1
        # 项目列:按层级缩进(子行次相对父行次缩进一级)
        lbl_cell = ws.cell(r, col, label)
        lbl_cell.alignment = Alignment(horizontal="left", vertical="center",
                                       wrap_text=True, indent=level * 2)
        col += 1
        # 金额列:税率行显示百分比,其余显示数值
        if str(label).startswith("税率"):
            vcell = ws.cell(r, col, f"{amount * 100:.0f}%")
            vcell.alignment = center
        else:
            vcell = ws.cell(r, col, round(float(amount), 2))
            vcell.alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    note = ("本表由系统按账套利润表口径自动计算,纳税调整/优惠/预缴/总分机构分摊等"
            "行次默认 0,请核对并按实际情况调整后报送。")
    ws.merge_cells(start_row=r + 1, start_column=1, end_row=r + 1, end_column=last_col)
    ws.cell(r + 1, 1, note).alignment = left

    if has_category:
        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 52
        ws.column_dimensions["D"].width = 20
    else:
        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 52
        ws.column_dimensions["C"].width = 20


def _write_a104(ws, title: str, company, period: str, rows: list) -> None:
    """A104000 期间费用明细表:行次 / 项目 / 销售费用 / 管理费用 / 财务费用。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 5

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30

    meta = [
        f"税款所属期间:{period}",
        f"纳税人名称:{(company.name if company else '') or ''}    金额单位:人民币元(列至角分)",
    ]
    r = 2
    for m in meta:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        ws.cell(r, 1, m).alignment = left
        r += 1

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "项目", "销售费用", "管理费用", "财务费用"]
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for line_no, label, sell, admin, fin in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, label).alignment = left
        for c, val in ((3, sell), (4, admin), (5, fin)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 34
    for col in ("C", "D", "E"):
        ws.column_dimensions[col].width = 16


def _write_a105(ws, title: str, company, period: str, rows: list) -> None:
    """A105000 纳税调整明细表:行次 / 项目(按层级缩进) / 账载 / 税收 / 调增 / 调减。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 6

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30

    meta = [
        f"税款所属期间:{period}",
        f"纳税人名称:{(company.name if company else '') or ''}    金额单位:人民币元(列至角分)",
    ]
    r = 2
    for m in meta:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        ws.cell(r, 1, m).alignment = left
        r += 1

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    for c, h in enumerate(["行次", "项目", "账载金额", "税收金额", "调增金额", "调减金额"], start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for line_no, label, book, tax, add, reduce_, level, _editable in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, label).alignment = Alignment(
            horizontal="left", vertical="center", wrap_text=True, indent=level * 2)
        for c, val in ((3, book), (4, tax), (5, add), (6, reduce_)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 44
    for col in ("C", "D", "E", "F"):
        ws.column_dimensions[col].width = 15


def _write_a106(ws, title: str, company, period: str, rows: list) -> None:
    """A106000 弥补亏损明细表:行次 / 项目 / 所属年度 / 当年亏损额 / 当年待弥补额 / 本年弥补额 / 可结转以后年度。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 7

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, f"税款所属期间:{period}    金额单位:人民币元(列至角分)").alignment = left

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "项目", "所属年度", "当年亏损额", "当年待弥补的亏损额",
            "用本年度所得额弥补的以前年度亏损额", "当年可结转以后年度弥补的亏损额"]
    r = 3
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for line_no, item, occur_year, loss, pending, offset, carry, _ed in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, item).alignment = left
        ws.cell(r, 3, occur_year if occur_year is not None else "").alignment = center
        for c, val in ((4, loss), (5, pending), (6, offset), (7, carry)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    for col, w in (("A", 8), ("B", 24), ("C", 12), ("D", 14), ("E", 18), ("F", 24), ("G", 24)):
        ws.column_dimensions[col].width = w


def _write_a105080(ws, title: str, company, period: str, rows: list) -> None:
    """A105080 资产折旧摊销明细表:行次/项目/资产原值/账载折旧/计税基础/税收折旧/纳税调整金额。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 7

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, f"税款所属期间:{period}    金额单位:人民币元(列至角分)").alignment = left

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "项目", "资产原值", "账载本年折旧摊销额", "资产计税基础",
            "税收折旧摊销额", "纳税调整金额"]
    r = 3
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for line_no, item, orig, book_dep, tax_basis, tax_dep, adj, level, _ed in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, item).alignment = Alignment(
            horizontal="left", vertical="center", wrap_text=True, indent=level * 2)
        for c, val in ((3, orig), (4, book_dep), (5, tax_basis), (6, tax_dep), (7, adj)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    for col, w in (("A", 8), ("B", 40), ("C", 14), ("D", 16), ("E", 14), ("F", 14), ("G", 14)):
        ws.column_dimensions[col].width = w


def _write_a107(ws, title: str, company, period: str, rows: list) -> None:
    """A107012 研发费用加计扣除明细表:行次 / 项目(按层级缩进) / 金额(数量)。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 3

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, f"税款所属期间:{period}    金额单位:人民币元(列至角分)").alignment = left

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    for c, h in enumerate(["行次", "项目", "金额(数量)"], start=1):
        cell = ws.cell(3, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r = 4
    for line_no, item, amount, level, _ed in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, item).alignment = Alignment(
            horizontal="left", vertical="center", wrap_text=True, indent=level * 2)
        ws.cell(r, 3, round(float(amount), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 56
    ws.column_dimensions["C"].width = 18


def _write_a201020(ws, title: str, company, period: str, rows: list) -> None:
    """A201020 资产加速折旧优惠表:行次/项目/资产原值/账载折旧/税收一般折旧/加速折旧/纳税调减/加速优惠。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 8

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title)
    ws.cell(1, 1).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, f"税款所属期间:{period}    金额单位:人民币元(列至角分)").alignment = left

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "项目", "本年享受优惠的资产原值", "账载折旧摊销金额",
            "按税收一般规定计算的折旧摊销", "享受加速政策计算的折旧摊销",
            "纳税调减金额", "享受加速政策优惠金额"]
    r = 3
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1
    for line_no, item, orig, book, normal, accel, reduce_, benefit, level, _ed in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, item).alignment = Alignment(
            horizontal="left", vertical="center", wrap_text=True, indent=level * 2)
        for c, val in ((3, orig), (4, book), (5, normal), (6, accel), (7, reduce_), (8, benefit)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1

    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 34
    for col in ("C", "D", "E", "F", "G", "H"):
        ws.column_dimensions[col].width = 15


def _write_a105050(ws, title: str, company, period: str, rows: list) -> None:
    """A105050 职工薪酬明细表:行次/项目/账载/实际发生/以前结转/税收金额/纳税调整/结转以后。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 8
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, f"税款所属期间:{period}    金额单位:人民币元(列至角分)").alignment = left
    head = ["行次", "项目", "账载金额", "实际发生额", "以前年度累计结转扣除额",
            "税收金额", "纳税调整金额", "累计结转以后年度扣除额"]
    for c, h in enumerate(head, start=1):
        cell = ws.cell(3, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="1F6FEB")
        cell.alignment = center
        cell.border = border
    r = 4
    for ln, item, book, actual, prev, tax, adjust, carry, level, _ed in rows:
        ws.cell(r, 1, ln).alignment = center
        ws.cell(r, 2, item).alignment = Alignment(horizontal="left", vertical="center",
                                                  wrap_text=True, indent=level * 2)
        for c, val in ((3, book), (4, actual), (5, prev), (6, tax), (7, adjust), (8, carry)):
            ws.cell(r, c, round(float(val), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1
    for col, w in (("A", 8), ("B", 34), ("C", 13), ("D", 13), ("E", 18), ("F", 13), ("G", 13), ("H", 20)):
        ws.column_dimensions[col].width = w


def _write_a105060(ws, title: str, company, period: str, rows: list) -> None:
    """A105060 广宣费明细表:行次/项目/金额。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 3
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, f"税款所属期间:{period}    金额单位:人民币元(列至角分)").alignment = left
    for c, h in enumerate(["行次", "项目", "金额"], start=1):
        cell = ws.cell(3, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="1F6FEB")
        cell.alignment = center
        cell.border = border
    r = 4
    for ln, item, amount, _ed in rows:
        ws.cell(r, 1, ln).alignment = center
        ws.cell(r, 2, item).alignment = left
        ws.cell(r, 3, round(float(amount), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 56
    ws.column_dimensions["C"].width = 18


def _write_preferences(ws, title: str, company, period: str, rows: list) -> None:
    """税收优惠事项明细表:类别 / 代码 / 项目 / 金额。"""
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    last_col = 4
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title).font = Font(size=14, bold=True)
    ws.cell(1, 1).alignment = center
    ws.row_dimensions[1].height = 30
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(2, 1, f"税款所属期间:{period}    金额单位:人民币元(列至角分)").alignment = left
    for c, h in enumerate(["类别", "代码", "优惠事项", "金额"], start=1):
        cell = ws.cell(3, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = PatternFill("solid", fgColor="1F6FEB")
        cell.alignment = center
        cell.border = border
    r = 4
    for cat, cat_label, code, name, amount, _ed in rows:
        ws.cell(r, 1, cat_label).alignment = center
        ws.cell(r, 2, code).alignment = center
        ws.cell(r, 3, name).alignment = left
        ws.cell(r, 4, round(float(amount), 2)).alignment = right
        for c in range(1, last_col + 1):
            ws.cell(r, c).border = border
        r += 1
    for col, w in (("A", 24), ("B", 14), ("C", 44), ("D", 16)):
        ws.column_dimensions[col].width = w


def build_cit_quarterly_xlsx(db: Session, year: int, quarter: int) -> bytes:
    company = db.get(models.CompanyInfo, 1)
    start, end = date(year, 1, 1), _quarter_end(year, quarter)
    period = f"{start:%Y-%m-%d} 至 {end:%Y-%m-%d}"
    wb = Workbook()
    ws = wb.active
    ws.title = "A200000"
    _write_kv(ws, _Q_TITLE, company, period, compute_rows(db, year, quarter),
              has_category=False)
    _write_a201020(wb.create_sheet("A201020"), "A201020 资产加速折旧、摊销(扣除)优惠明细表",
                   company, period, compute_a201020(db, year))
    _write_preferences(wb.create_sheet("税收优惠"), "税收优惠事项明细表",
                       company, period, compute_preferences(db, year))
    return _save(wb)


def build_cit_annual_xlsx(db: Session, year: int) -> bytes:
    """年报导出:A100000 主表 + A101010/A102010/A104000 附表(多 sheet)。"""
    company = db.get(models.CompanyInfo, 1)
    period = f"{year}-01-01 至 {year}-12-31"
    wb = Workbook()
    ws = wb.active
    ws.title = "A100000"
    _write_kv(ws, _A_TITLE, company, period, compute_annual_rows(db, year),
              has_category=True)
    _write_kv(wb.create_sheet("A101010"), "A101010 一般企业收入明细表",
              company, period, compute_a101010(db, year), has_category=False)
    _write_kv(wb.create_sheet("A102010"), "A102010 一般企业成本支出明细表",
              company, period, compute_a102010(db, year), has_category=False)
    _write_a104(wb.create_sheet("A104000"), "A104000 期间费用明细表",
                company, period, compute_a104000(db, year))
    _write_a105(wb.create_sheet("A105000"), "A105000 纳税调整项目明细表",
                company, period, compute_a105000(db, year))
    _write_a106(wb.create_sheet("A106000"), "A106000 企业所得税弥补亏损明细表",
                company, period, compute_a106000(db, year))
    _write_a105080(wb.create_sheet("A105080"), "A105080 资产折旧、摊销及纳税调整明细表",
                   company, period, compute_a105080(db, year))
    _write_a107(wb.create_sheet("A107012"), "A107012 研发费用加计扣除优惠明细表",
                company, period, compute_a107012(db, year))
    _write_a105050(wb.create_sheet("A105050"), "A105050 职工薪酬支出及纳税调整明细表",
                   company, period, compute_a105050(db, year))
    _write_a105060(wb.create_sheet("A105060"), "A105060 广告费和业务宣传费跨年度纳税调整明细表",
                   company, period, compute_a105060(db, year))
    _write_preferences(wb.create_sheet("税收优惠"), "税收优惠事项明细表",
                       company, period, compute_preferences(db, year))
    return _save(wb)


def _save(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
