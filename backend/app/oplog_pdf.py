"""操作日志 PDF 导出(reportlab,使用内置 Adobe 中文 CID 字体,无需外挂字体)。"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)

from . import oplog

_FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(_FONT))


def build_logs_pdf(rows: list[dict], title: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "cnTitle", parent=styles["Title"], fontName=_FONT, fontSize=16)
    meta_style = ParagraphStyle(
        "cnMeta", parent=styles["Normal"], fontName=_FONT, fontSize=9,
        textColor=colors.grey)
    cell_style = ParagraphStyle(
        "cnCell", parent=styles["Normal"], fontName=_FONT, fontSize=8, leading=10)

    elements = [
        Paragraph(title, title_style),
        Paragraph(f"共 {len(rows)} 条  ·  生成时间 "
                  f"{_now()}", meta_style),
        Spacer(1, 6 * mm),
    ]

    header = ["时间", "类型", "操作", "摘要", "状态", "来源IP"]
    data = [[Paragraph(h, cell_style) for h in header]]
    for r in rows:
        data.append([
            Paragraph(r["created_at"][:19].replace("T", " "), cell_style),
            Paragraph(oplog.ACTION_TYPES.get(r["action_type"], r["action_type"]), cell_style),
            Paragraph(_esc(r["action"]), cell_style),
            Paragraph(_esc(r.get("summary") or "-"), cell_style),
            Paragraph(str(r["status_code"]), cell_style),
            Paragraph(_esc(r.get("ip") or "-"), cell_style),
        ])

    col_widths = [34 * mm, 18 * mm, 55 * mm, 95 * mm, 14 * mm, 30 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6feb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(table)
    doc.build(elements)
    buf.seek(0)
    return buf.read()


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
