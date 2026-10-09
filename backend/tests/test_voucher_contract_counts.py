"""凭证列表关联数量回归验证。"""
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models
from app.routers import reports, vouchers
from app.tenant import install_tenant_isolation, set_current_tenant


def _new_db():
    eng = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def run():
    install_tenant_isolation()
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    db = _new_db()
    set_current_tenant(1)
    account = models.Account(code="1001", name="库存现金", category="asset", direction="debit")
    db.add(account)
    db.flush()

    voucher = models.Voucher(
        voucher_no="记-202610-001",
        voucher_date=date(2026, 10, 8),
        note="有关联的凭证",
        total_debit=Decimal("100.00"),
        total_credit=Decimal("100.00"),
        required_attachment_kinds="invoice,receipt,contract",
    )
    linked_voucher = models.Voucher(
        voucher_no="记-202610-002",
        voucher_date=date(2026, 10, 8),
        note="普通关联凭证",
        total_debit=Decimal("100.00"),
        total_credit=Decimal("100.00"),
    )
    db.add_all([voucher, linked_voucher])
    db.flush()
    db.add_all([
        models.VoucherEntry(
            voucher_id=voucher.id, line_no=1, summary="借方",
            account_id=account.id, debit=Decimal("100.00"), credit=Decimal("0"),
        ),
        models.VoucherEntry(
            voucher_id=linked_voucher.id, line_no=1, summary="借方",
            account_id=account.id, debit=Decimal("100.00"), credit=Decimal("0"),
        ),
        models.VoucherLink(source_id=voucher.id, target_id=linked_voucher.id, relation_type="other"),
    ])
    contract = models.Contract(contract_no="HT-001", name="测试合同")
    db.add(contract)
    db.flush()
    db.add(models.ContractVoucherLink(contract_id=contract.id, voucher_id=voucher.id))
    db.add_all([
        models.Attachment(
            voucher_id=voucher.id,
            kind="invoice",
            original_name="invoice.pdf",
            stored_path="/tmp/invoice.pdf",
            mime_type="application/pdf",
            size_bytes=100,
        ),
        models.Attachment(
            voucher_id=linked_voucher.id,
            kind="receipt",
            original_name="receipt.pdf",
            stored_path="/tmp/receipt.pdf",
            mime_type="application/pdf",
            size_bytes=100,
        ),
        models.Attachment(
            contract_id=contract.id,
            kind="contract",
            original_name="contract.pdf",
            stored_path="/tmp/contract.pdf",
            mime_type="application/pdf",
            size_bytes=100,
        ),
    ])
    db.commit()

    page = vouchers.list_vouchers(page=1, page_size=20, db=db)
    item = next(i for i in page.items if i.id == voucher.id)
    check("凭证关联数量", item.link_count == 1)
    check("关联合同数量", item.contract_link_count == 1)
    check("附件类型数量含关联来源",
          item.attachment_kind_counts == {"invoice": 1, "receipt": 1, "contract": 1})
    check("附件来源数量", item.attachment_source_counts == {
        "self": 1, "linked_voucher": 1, "linked_contract": 1})
    check("关联来源补齐必需附件", item.missing_attachment_kinds == [])

    detail = vouchers.get_voucher(voucher.id, db)
    check("详情附件类型数量含关联来源",
          detail.attachment_kind_counts == {"invoice": 1, "receipt": 1, "contract": 1})
    check("详情关联来源补齐必需附件", detail.missing_attachment_kinds == [])

    incomplete = models.Voucher(
        voucher_no="记-202610-003",
        voucher_date=date(2026, 10, 8),
        note="缺少银行回单",
        total_debit=Decimal("100.00"),
        total_credit=Decimal("100.00"),
        required_attachment_kinds="invoice,receipt",
    )
    db.add(incomplete)
    db.flush()
    db.add(models.Attachment(
        voucher_id=incomplete.id,
        kind="invoice",
        original_name="only-invoice.pdf",
        stored_path="/tmp/only-invoice.pdf",
        mime_type="application/pdf",
        size_bytes=100,
    ))
    db.commit()

    ops = reports._ops_summary(db)
    check("仪表盘统计真正缺附件的凭证",
          ops["vouchers_missing_attachments"] == 1)

    set_current_tenant(None)
    db.close()

    print("\n结果:" + ("全部通过" if not failures else f"{len(failures)} 项失败: {failures}"))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
