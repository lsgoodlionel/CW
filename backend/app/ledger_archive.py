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


def _subject_folder(voucher, folder_names):
    """按凭证分录确定归档业务科目,避免非费用凭证被笼统归为未分类。"""
    entries = [entry for entry in voucher.entries if entry.account]
    expense = [entry for entry in entries if entry.debit > 0 and
               entry.account.direction == "debit" and
               entry.account.category in ("cost", "profit")]
    if expense:
        chosen = max(expense, key=lambda entry: entry.debit)
        group = "费用科目"
        reason = ("多个费用或成本科目，按最大借方金额归档" if len(expense) > 1
                  else "按费用或成本科目借方分录归档")
    else:
        non_cash = [entry for entry in entries if entry.account.code not in ("1001", "1002", "1012")]
        debit = [entry for entry in non_cash if entry.debit > 0]
        credit = [entry for entry in non_cash if entry.credit > 0]
        chosen = (max(debit, key=lambda entry: entry.debit) if debit else
                  max(credit, key=lambda entry: entry.credit) if credit else
                  entries[0] if entries else None)
        group = "非费用业务" if chosen else "待核对"
        reason = ("无费用或成本借方分录，按主要业务科目归档" if chosen else
                  "凭证没有可用科目分录，请核对凭证")
    if chosen is None:
        return "附件/待核对", reason
    account = chosen.account
    name = folder_names.get(account.code) or f"{account.code} {account.name}"
    parts = [_safe(part) for part in name.split("/") if part.strip()][:4]
    return f"附件/{group}/" + "/".join(parts or [f"{account.code} {_safe(account.name)}"]), reason


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
                      "volume_index": index,
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
        subject_folder, classification_reason = _subject_folder(v, folder_names)
        for source, source_id in related[v.id]:
            for a in by_source.get(source_id, []):
                if a.id in seen:
                    continue
                seen.add(a.id)
                if mode == "date":
                    folder = f"附件/发生日期/{v.voucher_date:%Y/%m}/{stem}"
                    reason = "按凭证发生日期归档"
                else:
                    folder = subject_folder
                    reason = classification_reason
                ext = Path(a.original_name).suffix.lower()
                ext = ext if re.fullmatch(r"\.[a-z0-9]{1,10}", ext) else ""
                kind_label = KIND_LABELS.get(a.kind, "其他附件")
                filename = _safe(f"{v.voucher_date:%Y%m%d}_{v.voucher_no}_{kind_label}_{a.id}") + ext
                path = f"{folder}/{filename}"
                if path in used:
                    path = f"{folder}/{a.id}_{filename}"
                used.add(path)
                items.append({"path": path, "type": "附件", "voucher_id": v.id,
                              "voucher_no": v.voucher_no, "date": v.voucher_date.isoformat(),
                              "description": a.original_name, "source": source,
                              "attachment_id": a.id, "kind": kind_label,
                              "classification_reason": reason,
                              "mime_type": a.mime_type,
                              "stored_path": a.stored_path})
    return vouchers, items


def _public_items(items):
    return [{key: value for key, value in item.items() if key != "stored_path"} for item in items]


def _manifest_csv(items):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["凭证号", "日期", "类型", "附件类别", "来源", "摘要/原文件名", "归档路径", "归档依据"])
    for item in items:
        writer.writerow([item["voucher_no"], item["date"], item["type"], item.get("kind", ""),
                         item["source"], item["description"], item["path"],
                         item.get("classification_reason", "")])
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def _attachment_bytes(item):
    root = upload_root().resolve()
    path = Path(item["stored_path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError(f"附件 {item['attachment_id']} 文件缺失或路径无效")
    return path.read_bytes()


def item_content(db, period, ledger_type, vouchers, items, item, account_code=None):
    """返回某一清单文件的实际内容;在线预览与 ZIP 取同一来源。"""
    kind = item["type"]
    if kind == "账簿":
        return ledger_excel.build_ledger_workbook(db, ledger_type, period, account_code, include_cover=True)
    if kind == "清单":
        return (_manifest_csv(items) if item["path"].endswith(".csv") else
                json.dumps(_public_items(items), ensure_ascii=False, indent=2).encode("utf-8"))
    if kind == "凭证册":
        volume_size = 100
        volumes = [vouchers[i:i+volume_size] for i in range(0, len(vouchers), volume_size)] or [[]]
        index = item["volume_index"]
        company = db.scalar(select(models.CompanyInfo))
        return build_vouchers_pdf(db, volumes[index-1], company.name if company else "", index, len(volumes))
    if kind == "凭证":
        voucher = next((voucher for voucher in vouchers if voucher.id == item["voucher_id"]), None)
        if voucher is None:
            raise ValueError("凭证不在归档清单中")
        company = db.scalar(select(models.CompanyInfo))
        return build_vouchers_pdf(db, [voucher], company.name if company else "")
    if kind == "附件":
        return _attachment_bytes(item)
    raise ValueError("未知归档文件类型")


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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            zf.writestr(item["path"], item_content(db, period, ledger_type, vouchers, items, item, account_code))
    return buf.getvalue()
