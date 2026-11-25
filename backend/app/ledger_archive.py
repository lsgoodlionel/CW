"""会计账簿与凭证附件归档包：预览和 ZIP 使用同一份清单。"""
import csv
import io
import json
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from . import models, ledger_excel
from .attach_svc import upload_root
KIND_LABELS = {"invoice": "发票", "receipt": "银行回单", "contract": "合同",
               "tax_payment": "完税证明", "approval": "审批记录", "other": "其他"}

FONT = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(FONT))


def _safe(text: str, fallback="未命名") -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(text or "")).strip(" .")
    return cleaned[:80] or fallback


def _source_attachments(db, vouchers):
    ids = [v.id for v in vouchers]
    related = {v.id: [("本凭证", v.id)] for v in vouchers}
    if not ids:
        return related, {}
    for src, dst in db.execute(select(models.VoucherLink.source_id, models.VoucherLink.target_id)
                                .where(or_(models.VoucherLink.source_id.in_(ids),
                                           models.VoucherLink.target_id.in_(ids)))):
        if src in related:
            related[src].append(("关联凭证", dst))
        if dst in related:
            related[dst].append(("关联凭证", src))
    for vid, cid in db.execute(select(models.ContractVoucherLink.voucher_id,
                                       models.ContractVoucherLink.contract_id)
                              .where(models.ContractVoucherLink.voucher_id.in_(ids))):
        related[vid].append(("关联合同", -cid))
    voucher_ids = {sid for sources in related.values() for _, sid in sources if sid > 0}
    contract_ids = {-sid for sources in related.values() for _, sid in sources if sid < 0}
    stmt = select(models.Attachment).where(or_(
        models.Attachment.voucher_id.in_(voucher_ids),
        models.Attachment.contract_id.in_(contract_ids)))
    attachments = db.scalars(stmt).all()
    by_source = {}
    for a in attachments:
        if a.voucher_id:
            by_source.setdefault(a.voucher_id, []).append(a)
        if a.contract_id:
            by_source.setdefault(-a.contract_id, []).append(a)
    return related, by_source


def make_manifest(db, period, mode: str, account_code=None, folder_names=None):
    if mode not in ("subject", "date"):
        raise ValueError("归档方式须为科目或日期")
    folder_names = folder_names or {}
    stmt = select(models.Voucher).where(
        models.Voucher.status == "posted",
        models.Voucher.voucher_date >= period.cur_start,
        models.Voucher.voucher_date <= period.cur_end,
    ).options(selectinload(models.Voucher.entries).selectinload(models.VoucherEntry.account))
    if account_code:
        stmt = stmt.where(select(models.VoucherEntry.id).join(models.Account)
                          .where(models.VoucherEntry.voucher_id == models.Voucher.id,
                                 models.Account.code == account_code).exists())
    vouchers = db.scalars(stmt.order_by(models.Voucher.voucher_date, models.Voucher.voucher_no)).all()
    related, by_source = _source_attachments(db, vouchers)
    volume_size = 100
    volumes = [vouchers[i:i+volume_size] for i in range(0, len(vouchers), volume_size)] or [[]]
    items = [
        {"path": "账簿/会计账簿.xlsx", "type": "账簿", "voucher_id": None,
         "voucher_no": "", "date": "", "description": period.label, "source": "系统生成", "attachment_id": None},
        {"path": "清单/凭证与附件清单.csv", "type": "清单", "voucher_id": None,
         "voucher_no": "", "date": "", "description": "凭证与附件索引", "source": "系统生成", "attachment_id": None},
        {"path": "清单/归档目录.json", "type": "清单", "voucher_id": None,
         "voucher_no": "", "date": "", "description": "目录结构", "source": "系统生成", "attachment_id": None},
    ]
    for index, volume in enumerate(volumes, 1):
        items.append({"path": f"凭证/第{index:03d}册_封面与凭证.pdf", "type": "凭证册",
                      "voucher_id": None, "voucher_no": "", "date": "",
                      "description": f"第 {index} 册 / 共 {len(volumes)} 册，{len(volume)} 张凭证",
                      "source": "系统生成", "attachment_id": None})
    used = set()
    for v in vouchers:
        stem = _safe(f"{v.voucher_date:%Y%m%d}_{v.voucher_no}_{v.id}")
        voucher_dir = f"凭证/{v.voucher_date:%Y-%m}/{stem}"
        doc_path = f"{voucher_dir}/{stem}.pdf"
        items.append({"path": doc_path, "type": "凭证", "voucher_id": v.id,
                      "voucher_no": v.voucher_no, "date": v.voucher_date.isoformat(),
                      "description": v.note, "source": "本凭证", "attachment_id": None})
        used.add(doc_path)
        seen = set()
        for source, source_id in related[v.id]:
            for a in by_source.get(source_id, []):
                if a.id in seen:
                    continue
                seen.add(a.id)
                if mode == "date":
                    folder = f"附件/发生日期/{v.voucher_date:%Y/%m}/{stem}"
                else:
                    expense = next((e.account for e in v.entries if e.account and
                                    e.account.category in ("profit", "cost") and e.debit > 0), None)
                    code = expense.code if expense else "other"
                    name = folder_names.get(code) or (f"{code} {_safe(expense.name)}" if expense else "未分类")
                    parts = [_safe(p) for p in name.split("/") if p.strip()][:4]
                    folder = "附件/费用科目/" + "/".join(parts or ["未分类"])
                ext = Path(a.original_name).suffix.lower()
                ext = ext if re.fullmatch(r"\.[a-z0-9]{1,10}", ext) else ""
                filename = _safe(f"{v.voucher_date:%Y%m%d}_{v.voucher_no}_{a.kind}_{a.id}") + ext
                path = f"{folder}/{filename}"
                if path in used:
                    path = f"{folder}/{a.id}_{filename}"
                used.add(path)
                items.append({"path": path, "type": "附件", "voucher_id": v.id,
                              "voucher_no": v.voucher_no, "date": v.voucher_date.isoformat(),
                              "description": a.original_name, "source": source,
                              "attachment_id": a.id, "kind": KIND_LABELS.get(a.kind, a.kind),
                              "stored_path": a.stored_path})
    return vouchers, items


def _paragraph(text, style):
    return Paragraph(escape(str(text or "")), style)


def build_vouchers_pdf(db, vouchers, company_name="", volume_no=1, volume_count=1):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16*mm, rightMargin=16*mm,
                            topMargin=18*mm, bottomMargin=18*mm, title="记账凭证与封面")
    normal = ParagraphStyle("normal", fontName=FONT, fontSize=10, leading=16)
    title = ParagraphStyle("title", parent=normal, fontSize=20, leading=28, alignment=1)
    company = db.scalar(select(models.CompanyInfo)) if db is not None else None
    body = []
    if vouchers:
        cover_rows = [
            ("单位名称", company_name),
            ("日期范围", f"自 {vouchers[0].voucher_date} 至 {vouchers[-1].voucher_date}"),
            ("凭证号数", f"自 {vouchers[0].voucher_no} 至 {vouchers[-1].voucher_no}"),
            ("册数", f"共 {volume_count} 册　本册第 {volume_no} 册"),
            ("原始凭证、汇总凭证张数", f"记账凭证 {len(vouchers)} 张　附件 {sum(len(v.attachments) for v in vouchers)} 件"),
            ("档案编号", "全宗号：________　目录号：________　案卷号：________"),
            ("签署", "会计：________　复核：________　装订人：________"),
            ("装订日期", "______年______月______日"),
        ]
        cover = Table([[_paragraph(label, normal), _paragraph(value, normal)]
                       for label, value in cover_rows], colWidths=[53*mm, 121*mm], rowHeights=18*mm)
        cover.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#7d8790")),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 9)]))
        body += [_paragraph("会计凭证封面", title), Spacer(1, 18*mm), cover, PageBreak()]
    for idx, v in enumerate(vouchers):
        if idx:
            body.append(PageBreak())
        body += [_paragraph("记账凭证", title),
                 _paragraph(f"单位：{company_name}　日期：{v.voucher_date}　凭证号：{v.voucher_no}", normal),
                 Spacer(1, 5*mm)]
        rows = [[_paragraph(x, normal) for x in ("摘要", "总账科目", "明细科目", "借方金额", "贷方金额")]]
        for e in v.entries:
            rows.append([_paragraph(e.summary or v.note, normal),
                         _paragraph(f"{e.account.code} {e.account.name}" if e.account else "", normal),
                         _paragraph(e.sub_account, normal),
                         _paragraph(f"{e.debit:,.2f}" if e.debit else "", normal),
                         _paragraph(f"{e.credit:,.2f}" if e.credit else "", normal)])
        rows.append([_paragraph("合计", normal), "", "",
                     _paragraph(f"{v.total_debit:,.2f}", normal),
                     _paragraph(f"{v.total_credit:,.2f}", normal)])
        table = Table(rows, colWidths=[57*mm, 43*mm, 30*mm, 24*mm, 24*mm], repeatRows=1)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .4, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eff7")),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        body += [table, Spacer(1, 5*mm),
                 _paragraph(f"所附电子原始凭证：{len(v.attachments)} 份　纸质原始凭证：____ 张", normal),
                 _paragraph(f"摘要：{v.note}", normal),
                 _paragraph(f"填制：{company.recorder if company else '____________'}　稽核：{company.auditor if company else '____________'}　记账：{company.bookkeeper if company else '____________'}", normal),
                 _paragraph(f"会计主管：{company.accountant if company else '____________'}　出纳（收付款凭证）：____________", normal)]
    if not body:
        body = [_paragraph("本期无已入账凭证", normal)]

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.drawRightString(A4[0]-16*mm, 10*mm, f"第 {document.page} 页")
        canvas.restoreState()
    doc.build(body, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def build_archive(db, period, ledger_type, mode, account_code=None, folder_names=None):
    vouchers, items = make_manifest(db, period, mode, account_code, folder_names)
    company = db.scalar(select(models.CompanyInfo))
    company_name = company.name if company else ""
    root = upload_root().resolve()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("账簿/会计账簿.xlsx",
                    ledger_excel.build_ledger_workbook(db, ledger_type, period, account_code,
                                                       include_cover=True))
        volume_size = 100
        volumes = [vouchers[i:i+volume_size] for i in range(0, len(vouchers), volume_size)] or [[]]
        for index, volume in enumerate(volumes, 1):
            zf.writestr(f"凭证/第{index:03d}册_封面与凭证.pdf",
                        build_vouchers_pdf(db, volume, company_name, index, len(volumes)))
        by_id = {v.id: v for v in vouchers}
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["凭证号", "日期", "类型", "附件类别", "来源", "摘要/原文件名", "归档路径"])
        for item in items:
            if item["type"] == "凭证":
                zf.writestr(item["path"], build_vouchers_pdf(db, [by_id[item["voucher_id"]]], company_name))
            writer.writerow([item["voucher_no"], item["date"], item["type"], item.get("kind", ""),
                             item["source"], item["description"], item["path"]])
            if item["type"] == "附件":
                path = Path(item["stored_path"]).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise FileNotFoundError(f"附件 {item['attachment_id']} 文件缺失或路径无效")
                zf.write(path, item["path"])
        zf.writestr("清单/凭证与附件清单.csv", "\ufeff" + output.getvalue())
        public_items = [{k: v for k, v in item.items() if k != "stored_path"} for item in items]
        zf.writestr("清单/归档目录.json", json.dumps(public_items, ensure_ascii=False, indent=2))
    return buf.getvalue()
