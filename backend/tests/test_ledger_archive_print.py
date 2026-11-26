"""归档包、A4 报表与账簿过账口径的端到端内存数据库验证。"""
import io
import tempfile
import zipfile
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from pathlib import Path
from openpyxl import load_workbook

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import archive_preview, ledger_archive, ledgers, models, report_pdf, reports_cn
from app.config import settings
from app.database import Base
from app.tenant import install_tenant_isolation, set_current_tenant


def test_archive_and_print():
    install_tenant_isolation()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    set_current_tenant(1)
    db.add(models.CompanyInfo(name="测试公司"))
    bank = models.Account(code="1002", name="银行存款", category="asset", direction="debit")
    fee = models.Account(code="6602", name="管理费用", category="profit", direction="debit")
    db.add_all([bank, fee]); db.flush()
    posted = models.Voucher(voucher_no="记-202607-001", voucher_date=date(2026, 7, 1),
                            note="办公用品", status="posted", total_debit=Decimal("100"),
                            total_credit=Decimal("100"), entries=[
        models.VoucherEntry(line_no=1, summary="办公用品", account=fee, debit=Decimal("100"), credit=0),
        models.VoucherEntry(line_no=2, summary="办公用品", account=bank, debit=0, credit=Decimal("100")),
    ])
    draft = models.Voucher(voucher_no="记-202607-002", voucher_date=date(2026, 7, 2),
                           note="草稿", status="draft", total_debit=Decimal("900"),
                           total_credit=Decimal("900"), entries=[
        models.VoucherEntry(line_no=1, account=fee, debit=Decimal("900"), credit=0),
        models.VoucherEntry(line_no=2, account=bank, debit=0, credit=Decimal("900")),
    ])
    earlier = models.Voucher(voucher_no="记-202606-001", voucher_date=date(2026, 6, 20),
                             note="上期费用", status="posted", total_debit=Decimal("50"),
                             total_credit=Decimal("50"), entries=[
        models.VoucherEntry(line_no=1, account=fee, sub_account="办公", debit=Decimal("50"), credit=0),
        models.VoucherEntry(line_no=2, account=bank, debit=0, credit=Decimal("50")),
    ])
    db.add_all([posted, draft, earlier]); db.flush()
    with tempfile.TemporaryDirectory() as temp:
        previous = settings.upload_dir
        settings.upload_dir = temp
        try:
            file = Path(temp) / "invoice.pdf"
            file.write_bytes(b"test invoice")
            db.add(models.Attachment(voucher_id=posted.id, kind="invoice", original_name="发票.pdf",
                                     stored_path=str(file), mime_type="application/pdf", size_bytes=12))
            db.commit()
            period = reports_cn.build_period("month", 2026, 7, None)
            general = ledgers.build_ledger(db, "general", period)
            assert all(row["voucher_no"] != draft.voucher_no for group in general["groups"]
                       for row in group["rows"])
            details = ledgers.build_ledger(db, "detail_three", period)
            prior_group = next(g for g in details["groups"] if g["code"] == "6602" and g["sub"] == "办公")
            assert prior_group["opening"] == 50 and prior_group["closing"] == 50
            vouchers, items = ledger_archive.make_manifest(db, period, "subject")
            assert len(vouchers) == 1
            assert any(i["type"] == "附件" and "6602" in i["path"] for i in items)
            attachment_item = next(i for i in items if i["type"] == "附件")
            assert "发票" in attachment_item["path"] and "invoice" not in attachment_item["path"]
            assert attachment_item["classification_reason"] == "按费用或成本科目借方分录归档"
            data = ledger_archive.build_archive(db, period, "all", "subject")
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                assert {i["path"] for i in items} == names
                assert zf.read(attachment_item["path"]) == b"test invoice"
                assert zf.read(attachment_item["path"]) == ledger_archive.item_content(
                    db, period, "all", vouchers, items, attachment_item)
                assert zf.read("凭证/第001册_封面与凭证.pdf").startswith(b"%PDF")
                assert zf.read("账簿/会计账簿.xlsx").startswith(b"PK")
                wb = load_workbook(io.BytesIO(zf.read("账簿/会计账簿.xlsx")))
                assert wb.sheetnames[0] == "封面"
                assert all(str(sheet.page_setup.paperSize) == str(sheet.PAPERSIZE_A4)
                           for sheet in wb.worksheets), [
                               (sheet.title, sheet.page_setup.paperSize) for sheet in wb.worksheets]
                html, mime = archive_preview.render_file("会计账簿.xlsx", zf.read("账簿/会计账簿.xlsx"))
                assert mime.startswith("text/html") and "封面".encode() in html
                pdf, mime = archive_preview.render_file("凭证.pdf", zf.read("凭证/第001册_封面与凭证.pdf"))
                assert mime == "application/pdf" and pdf.startswith(b"%PDF")
            assert report_pdf.build_report_pdf(db, period).startswith(b"%PDF")
            assert report_pdf.build_report_pdf(db, period, "portrait").startswith(b"%PDF")
            tax = SimpleNamespace(entries=[
                SimpleNamespace(account=models.Account(code="2221", name="应交税费", category="liability", direction="credit"),
                                debit=Decimal("50"), credit=Decimal("0")),
                SimpleNamespace(account=bank, debit=Decimal("0"), credit=Decimal("50")),
            ])
            folder, reason = ledger_archive._subject_folder(tax, {})
            assert folder == "附件/非费用业务/2221 应交税费" and "无费用" in reason
            empty_folder, reason = ledger_archive._subject_folder(SimpleNamespace(entries=[]), {})
            assert empty_folder == "附件/待核对" and "没有可用科目" in reason
            html, mime = archive_preview.render_file("说明.txt", b"<script>alert(1)</script>")
            assert mime.startswith("text/html") and b"&lt;script&gt;" in html and b"<script>alert" not in html
        finally:
            settings.upload_dir = previous
            set_current_tenant(None)
            db.close()


if __name__ == "__main__":
    test_archive_and_print()
    print("结果:全部通过")
