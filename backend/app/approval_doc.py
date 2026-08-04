"""生成"费用审批记录单"PDF:含申请内容 + 事前费用申请与报销的完整审批轨迹。

用于报销生成凭证时,自动作为凭证附件之一归档,形成可追溯的审批留痕。
"""
import io
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import models

_FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(_FONT))

_RESULT_LABEL = {"approved": "通过", "rejected": "驳回", "pending": "待审批", "cancelled": "撤销"}
_APPLY_TYPE_LABEL = {"general": "一般申请", "contract": "合同", "routine": "常规费用"}


def _esc(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _names(db) -> dict[int, str]:
    return {e.id: e.name for e in db.scalars(select(models.Employee)).all()}


def _cell(text: object, style) -> Paragraph:
    return Paragraph(_esc(text), style)


def build_claim_approval_pdf(db, claim: models.ExpenseClaim) -> bytes:
    """为一张报销单生成审批记录 PDF(字节)。"""
    names = _names(db)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("t", parent=styles["Title"], fontName=_FONT, fontSize=16)
    h_style = ParagraphStyle("h", parent=styles["Heading3"], fontName=_FONT, fontSize=11)
    meta_style = ParagraphStyle("m", parent=styles["Normal"], fontName=_FONT,
                                fontSize=9, textColor=colors.grey)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontName=_FONT, fontSize=9, leading=12)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm, title="费用审批记录单")
    els: list = [Paragraph("费用审批记录单", title_style),
                 Paragraph(f"生成时间 {datetime.now():%Y-%m-%d %H:%M:%S}", meta_style),
                 Spacer(1, 5 * mm)]

    emp = names.get(claim.applicant_employee_id, "")
    unit = db.get(models.OrgUnit, claim.org_unit_id) if claim.org_unit_id else None
    info = [
        ["报销单号", claim.claim_no, "申请人", emp or "-"],
        ["部门", unit.name if unit else "-", "报销金额", f"¥{Decimal(claim.total_amount):.2f}"],
        ["报销事由", claim.reason or "-", "", ""],
    ]
    els.append(_kv_table(info, cell))
    els.append(Spacer(1, 4 * mm))

    els.append(Paragraph("报销明细", h_style))
    els.append(_items_table(db, claim.items, claim.total_amount, cell, "金额"))
    els.append(Spacer(1, 4 * mm))

    # 关联的事前费用申请(含其审批轨迹)
    if claim.application_id:
        app = db.scalar(select(models.ExpenseApplication)
                        .where(models.ExpenseApplication.id == claim.application_id)
                        .options(selectinload(models.ExpenseApplication.items)))
        if app:
            els.append(Paragraph("关联费用申请(事前审批)", h_style))
            aemp = names.get(app.applicant_employee_id, "")
            els.append(_kv_table([
                ["申请单号", app.apply_no, "申请类型", _APPLY_TYPE_LABEL.get(app.apply_type, app.apply_type)],
                ["申请人", aemp or "-", "预计金额", f"¥{Decimal(app.estimated_amount):.2f}"],
                ["申请事由", app.reason or "-", "", ""],
            ], cell))
            els.append(Spacer(1, 2 * mm))
            els.append(_trail_table(db, app.workflow_instance_id, names, cell,
                                    empty="(无事前审批轨迹)"))
            els.append(Spacer(1, 4 * mm))

    els.append(Paragraph("报销审批轨迹", h_style))
    els.append(_trail_table(db, claim.workflow_instance_id, names, cell,
                            empty="(无报销审批轨迹)"))
    els.append(Spacer(1, 6 * mm))
    els.append(Paragraph("本记录由系统在生成记账凭证时自动归档,作为凭证原始审批留痕。", meta_style))

    doc.build(els)
    buf.seek(0)
    return buf.read()


def _kv_table(rows: list[list[str]], cell) -> Table:
    data = [[_cell(c, cell) for c in r] for r in rows]
    t = Table(data, colWidths=[26 * mm, 62 * mm, 26 * mm, 62 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f3f8")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f0f3f8")),
        ("SPAN", (1, -1), (-1, -1)),  # 事由整行合并
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _items_table(db, items, total, cell, amount_label: str) -> Table:
    header = ["序号", "费用类别", "会计科目", "明细科目", amount_label]
    data = [[_cell(h, cell) for h in header]]
    for i, it in enumerate(items, start=1):
        acc = db.get(models.Account, it.account_id) if it.account_id else None
        data.append([_cell(i, cell), _cell(it.category or "-", cell),
                     _cell(acc.name if acc else "-", cell),
                     _cell(it.sub_account or "-", cell),
                     _cell(f"{Decimal(it.amount):.2f}", cell)])
    data.append([_cell("合计", cell), _cell("", cell), _cell("", cell), _cell("", cell),
                 _cell(f"{Decimal(total):.2f}", cell)])
    t = Table(data, colWidths=[14 * mm, 40 * mm, 50 * mm, 40 * mm, 32 * mm], repeatRows=1)
    t.setStyle(_grid_style(header_span_last=True))
    return t


def _trail_table(db, inst_id: int | None, names: dict[int, str], cell, empty: str) -> Table:
    header = ["步骤", "审批人", "结果", "审批意见", "审批时间"]
    data = [[_cell(h, cell) for h in header]]
    rows = 0
    if inst_id:
        inst = db.scalar(select(models.WorkflowInstance)
                         .where(models.WorkflowInstance.id == inst_id)
                         .options(selectinload(models.WorkflowInstance.tasks)))
        if inst:
            for t in sorted(inst.tasks, key=lambda x: (x.step_no, x.id)):
                data.append([
                    _cell(f"{t.step_no}. {t.step_name}", cell),
                    _cell(names.get(t.approver_employee_id, "未指派"), cell),
                    _cell(_RESULT_LABEL.get(t.result, t.result), cell),
                    _cell(t.comment or "-", cell),
                    _cell(t.acted_at.strftime("%Y-%m-%d %H:%M") if t.acted_at else "-", cell),
                ])
                rows += 1
    if rows == 0:
        data.append([_cell(empty, cell), _cell("", cell), _cell("", cell),
                     _cell("", cell), _cell("", cell)])
    t = Table(data, colWidths=[46 * mm, 26 * mm, 18 * mm, 56 * mm, 30 * mm], repeatRows=1)
    t.setStyle(_grid_style())
    return t


def _grid_style(header_span_last: bool = False) -> TableStyle:
    cmds = [
        ("FONTNAME", (0, 0), (-1, -1), _FONT),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6feb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header_span_last:
        cmds.append(("SPAN", (0, -1), (3, -1)))  # 合计行左侧合并
    return TableStyle(cmds)
