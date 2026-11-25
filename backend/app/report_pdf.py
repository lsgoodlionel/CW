"""财务报表 A4 打印版。数据与页面、Excel 共用 reports_cn 口径。"""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
from sqlalchemy import select

from . import models, reports_cn

FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _cell(value, style):
    return Paragraph(escape(str(value if value is not None else "")), style)


def build_report_pdf(db, period, orientation="auto") -> bytes:
    if orientation not in ("auto", "portrait", "landscape"):
        raise ValueError("无效纸张方向")
    company = db.scalar(select(models.CompanyInfo))
    name = company.name if company else ""
    accountant = company.accountant if company else ""
    legal = company.legal_person if company else ""
    auditor = company.auditor if company else ""
    page_size = landscape(A4) if orientation in ("auto", "landscape") else A4
    width = page_size[0] - 28 * mm
    normal = ParagraphStyle("normalCN", fontName=FONT, fontSize=7.5, leading=9)
    head = ParagraphStyle("headCN", parent=normal, fontSize=15, leading=20, alignment=1)
    meta = ParagraphStyle("metaCN", parent=normal, fontSize=8, leading=12)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=page_size, leftMargin=12*mm, rightMargin=12*mm,
                            topMargin=10*mm, bottomMargin=10*mm, title=f"财务报表-{period.label}")
    elements = []

    def section(title, headers, rows, widths):
        if elements:
            elements.append(PageBreak())
        elements.extend([
            Paragraph(title, head), Spacer(1, 3*mm),
            Paragraph(f"企业名称：{escape(name)}　期间：{period.cur_start} 至 {period.cur_end}　单位：元", meta),
            Spacer(1, 3*mm),
        ])
        data = [[_cell(h, normal) for h in headers]]
        for row in rows:
            data.append([_cell(v, normal) for v in row])
        table = Table(data, colWidths=[width * x for x in widths], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT),
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#aab3bd")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eff7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.extend([table, Spacer(1, 4*mm),
                         Paragraph(f"企业负责人：{escape(legal)}　会计：{escape(accountant)}　复核：{escape(auditor)}", meta)])

    bs = reports_cn.balance_sheet(db, period)
    bs_rows = []
    for i in range(max(len(bs["assets"]), len(bs["rights"]))):
        a = bs["assets"][i] if i < len(bs["assets"]) else {}
        r = bs["rights"][i] if i < len(bs["rights"]) else {}
        bs_rows.append([a.get("label", ""), a.get("line", ""), _money(a.get("end")), _money(a.get("begin")),
                        r.get("label", ""), r.get("line", ""), _money(r.get("end")), _money(r.get("begin"))])
    section("资产负债表", ["资产", "行次", "期末余额", "年初余额", "负债和所有者权益", "行次", "期末余额", "年初余额"],
            bs_rows, [.21, .05, .12, .12, .21, .05, .12, .12])
    for title, statement in (("利润表", reports_cn.income_statement(db, period)),
                             ("现金流量表", reports_cn.cashflow_statement(db, period))):
        section(title, ["项目", "行次", statement["col1_label"], statement["col2_label"]],
                [[r.get("label"), r.get("line"), _money(r.get("col1")), _money(r.get("col2"))]
                 for r in statement["rows"]], [.48, .08, .22, .22])

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.drawRightString(page_size[0] - 14*mm, 9*mm, f"第 {document.page} 页")
        canvas.restoreState()

    doc.build(elements, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def _money(value):
    return "" if value is None else f"{float(value):,.2f}"
