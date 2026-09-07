"""税务报表生成:企业所得税月(季)度预缴纳税申报表(A类)A200000。

依据国家税务总局 A200000 表式,取账套数据(本年累计:年初→所属期末)自动计算主表行次。
优惠、预缴、总分机构等行次默认 0,可在生成的 Excel 中手工调整后报送。
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
_TITLE = "中华人民共和国企业所得税月(季)度预缴纳税申报表(A类)"


def _quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    return date(year, month, monthrange(year, month)[1])


def compute_rows(db: Session, year: int, quarter: int) -> list[tuple[str, str, Decimal]]:
    """返回 (行次, 项目, 本年累计金额) 列表。"""
    start, end = date(year, 1, 1), _quarter_end(year, quarter)
    b = reports_cn.Balances(reports_cn._movement(db, start, end))

    revenue = b.net_credit("6001", "6051")
    cost = b.net_debit("6401", "6402")
    tax_surcharge = b.net_debit("6403")
    sell = b.net_debit("6601")
    admin = b.net_debit("6602")
    rd = Decimal("0")                     # 研发费用:小企业多并入管理费用,无独立科目
    fin = b.net_debit("6603")
    invest = b.net_credit("6111")
    fair_value = b.net_credit("6101")
    asset_impair = b.net_debit("6701")
    non_op_income = b.net_credit("6301")
    non_op_expense = b.net_debit("6711")

    op_profit = (revenue - cost - tax_surcharge - sell - admin - rd - fin
                 + fair_value + invest - asset_impair)
    total_profit = op_profit + non_op_income - non_op_expense
    taxable = total_profit if total_profit > 0 else Decimal("0")   # 简化:暂无纳税调整
    tax_payable = (taxable * RATE).quantize(Decimal("0.01"))
    Z = Decimal("0")

    return [
        ("1", "营业收入", revenue),
        ("2", "减:营业成本", cost),
        ("3", "减:税金及附加", tax_surcharge),
        ("4", "减:销售费用", sell),
        ("5", "减:管理费用", admin),
        ("6", "减:研发费用", rd),
        ("7", "减:财务费用", fin),
        ("8", "加:其他收益", Z),
        ("9", "加:投资收益(损失以-填列)", invest),
        ("10", "加:净敞口套期收益(损失以-填列)", Z),
        ("11", "加:公允价值变动收益(损失以-填列)", fair_value),
        ("12", "加:信用减值损失(损失以-填列)", Z),
        ("13", "加:资产减值损失(损失以-填列)", -asset_impair),
        ("14", "加:资产处置收益(损失以-填列)", Z),
        ("15", "营业利润(亏损以-填列)", op_profit),
        ("16", "加:营业外收入", non_op_income),
        ("17", "减:营业外支出", non_op_expense),
        ("18", "利润总额(15+16-17)", total_profit),
        ("19", "加:特定业务计算的应纳税所得额", Z),
        ("20", "减:不征税收入", Z),
        ("21", "减:资产加速折旧、摊销(扣除)调减额", Z),
        ("22", "减:免税收入、减计收入、加计扣除", Z),
        ("23", "减:所得减免", Z),
        ("24", "减:弥补以前年度亏损", Z),
        ("25", "实际利润额(18+19-20-21-22-23-24)", taxable if total_profit > 0 else total_profit),
        ("26", "税率(25%)", RATE),
        ("27", "应纳所得税额(25×26)", tax_payable),
        ("28", "减:减免所得税额", Z),
        ("29", "减:抵免所得税额", Z),
        ("30", "减:本年累计已预缴所得税额", Z),
        ("31", "减:特定业务预缴(征)所得税额", Z),
        ("32", "本期应补(退)所得税额(27-28-29-30-31)", tax_payable),
    ]


def build_cit_quarterly_xlsx(db: Session, year: int, quarter: int) -> bytes:
    company = db.get(models.CompanyInfo, 1)
    start, end = date(year, 1, 1), _quarter_end(year, quarter)
    rows = compute_rows(db, year, quarter)

    wb = Workbook()
    ws = wb.active
    ws.title = "A200000"
    thin = Side(style="thin", color="BBBBBB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")

    ws.merge_cells("A1:C1")
    ws["A1"] = _TITLE
    ws["A1"].font = Font(size=14, bold=True)
    ws["A1"].alignment = center
    ws.row_dimensions[1].height = 30

    meta = [
        f"税款所属期间:{start:%Y-%m-%d} 至 {end:%Y-%m-%d}",
        f"纳税人识别号(统一社会信用代码):{(company.tax_number if company else '') or ''}",
        f"纳税人名称:{(company.name if company else '') or ''}    金额单位:人民币元(列至角分)",
    ]
    r = 2
    for m in meta:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        ws.cell(r, 1, m).alignment = left
        r += 1

    header_fill = PatternFill("solid", fgColor="1F6FEB")
    head = ["行次", "项目", "本年累计金额"]
    for c, h in enumerate(head, start=1):
        cell = ws.cell(r, c, h)
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border
    r += 1

    for line_no, label, amount in rows:
        ws.cell(r, 1, line_no).alignment = center
        ws.cell(r, 2, label).alignment = left
        val = float(amount)
        vcell = ws.cell(r, 3, "25%" if line_no == "26" else round(val, 2))
        vcell.alignment = right
        for c in (1, 2, 3):
            ws.cell(r, c).border = border
        r += 1

    ws.cell(r + 1, 1, "本表由系统按账套数据自动计算(优惠/预缴/纳税调整默认0),请核对后报送。")
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 46
    ws.column_dimensions["C"].width = 20

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
