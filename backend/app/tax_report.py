"""税务报表生成:企业所得税预缴(季报 A200000)与年度汇算(年报 A100000)主表。

依据国家税务总局表式,取账套数据(利润表口径)自动计算主表行次;优惠、预缴、
纳税调整、总分机构分摊等无法从账套自动取得的行次默认 0,可在生成的 Excel 中
手工调整后报送。行次的上下级关系以缩进呈现:子行次(如 1.1、9.1)相对父行次
缩进一级。
"""
import io
from calendar import monthrange
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy.orm import Session

from . import models, reports_cn

RATE = Decimal("0.25")           # 法定税率 25%
_Q_TITLE = "中华人民共和国企业所得税月(季)度预缴纳税申报表(A类)"
_A_TITLE = "中华人民共和国企业所得税年度纳税申报表(A类)"
Z = Decimal("0")

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


# ---------- 季报 A200000 ----------

def compute_rows(db: Session, year: int, quarter: int):
    """季报主表:返回 (行次, 项目, 金额, 层级) 列表。"""
    start, end = date(year, 1, 1), _quarter_end(year, quarter)
    a = _core_amounts(db, start, end)
    taxable = a["total_profit"] if a["total_profit"] > 0 else Z    # 简化:暂无纳税调整
    tax_payable = (taxable * RATE).quantize(Decimal("0.01"))
    real_profit = a["total_profit"]                               # 实际利润额=利润总额(无调整)
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
        ("21", "减:资产加速折旧、摊销(扣除)调减额(填写A201020)", Z),
        ("22", "减:免税收入、减计收入、加计扣除(22.1+22.2+…)", Z),
        ("23", "减:所得减免(23.1+23.2+……)", Z),
        ("24", "减:弥补以前年度亏损", Z),
        ("25", "实际利润额(18+19-20-21-22-23-24)", real_profit),
        ("26", "税率(25%)", RATE),
        ("27", "应纳所得税额(25×26)", tax_payable),
        ("28", "减:减免所得税额(28.1+28.2+……)", Z),
        ("28.1", "其中:符合条件的小型微利企业减免企业所得税", Z),
        ("29", "减:抵免所得税额", Z),
        ("30", "减:本年累计已预缴所得税额", Z),
        ("31", "减:特定业务预缴(征)所得税额", Z),
        ("32", "本期应补(退)所得税额(27-28-29-30-31)", tax_payable),
    ]
    return [(n, lb, v, _level(n)) for n, lb, v in rows]


# ---------- 年报 A100000 ----------

def compute_annual_rows(db: Session, year: int):
    """年报主表:返回 (行次, 类别, 项目, 金额, 层级) 列表。类别仅在该类首行填写。"""
    start, end = date(year, 1, 1), date(year, 12, 31)
    a = _core_amounts(db, start, end)
    profit = a["total_profit"]
    adj_after = profit                                    # 24 纳税调整后所得(19/20/21/22/23=0)=18
    taxable = adj_after if adj_after > 0 else Z           # 28 应纳税所得额(25/26/27=0)
    tax_amount = (taxable * RATE).quantize(Decimal("0.01"))   # 30 应纳所得税额
    payable = tax_amount                                  # 33 应纳税额=36 实际应纳(31/32/34/35=0)
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
        ("20", "", "加:纳税调整增加额(填写A105000)", Z),
        ("21", "", "减:纳税调整减少额(填写A105000)", Z),
        ("22", "", "减:免税、减计收入及加计扣除(填写A107010)", Z),
        ("23", "", "加:境外应税所得抵减境内亏损(填写A108000)", Z),
        ("24", "", "四、纳税调整后所得(18-19+20-21-22+23)", adj_after),
        ("25", "", "减:所得减免(填写A107020)", Z),
        ("26", "", "减:弥补以前年度亏损(填写A106000)", Z),
        ("27", "", "减:抵扣应纳税所得额(填写A107030)", Z),
        ("28", "", "五、应纳税所得额(24-25-26-27)", taxable),
        ("29", C3, "税率(25%)", RATE),
        ("30", "", "六、应纳所得税额(28×29)", tax_amount),
        ("31", "", "减:减免所得税额(填写A107040)", Z),
        ("32", "", "减:抵免所得税额(填写A107050)", Z),
        ("33", "", "七、应纳税额(30-31-32)", payable),
        ("34", "", "加:境外所得应纳所得税额(填写A108000)", Z),
        ("35", "", "减:境外所得抵免所得税额(填写A108000)", Z),
        ("36", "", "八、实际应纳所得税额(33+34-35)", payable),
        ("37", C4, "减:本年累计预缴所得税额", Z),
        ("38", "", "九、本年应补(退)所得税额(36-37)", payable),
        ("39", "", "其中:总机构分摊本年应补(退)所得税额(填写A109000)", Z),
        ("40", "", "财政集中分配本年应补(退)所得税额(填写A109000)", Z),
        ("41", "", "总机构主体生产经营部门分摊本年应补(退)所得税额(填写A109000)", Z),
        ("45", "", "十、本年实际应补(退)所得税额", payable),
    ]
    return [(n, cat, lb, v, _level(n)) for n, cat, lb, v in rows]


# ---------- Excel 渲染 ----------

def _render_xlsx(sheet_name: str, title: str, company, period: str,
                 rows: list, has_category: bool) -> bytes:
    """通用主表渲染:行次 / [类别] / 项目(按层级缩进) / 金额。"""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
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

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def build_cit_quarterly_xlsx(db: Session, year: int, quarter: int) -> bytes:
    company = db.get(models.CompanyInfo, 1)
    start, end = date(year, 1, 1), _quarter_end(year, quarter)
    rows = compute_rows(db, year, quarter)
    period = f"{start:%Y-%m-%d} 至 {end:%Y-%m-%d}"
    return _render_xlsx("A200000", _Q_TITLE, company, period, rows, has_category=False)


def build_cit_annual_xlsx(db: Session, year: int) -> bytes:
    company = db.get(models.CompanyInfo, 1)
    rows = compute_annual_rows(db, year)
    period = f"{year}-01-01 至 {year}-12-31"
    return _render_xlsx("A100000", _A_TITLE, company, period, rows, has_category=True)
