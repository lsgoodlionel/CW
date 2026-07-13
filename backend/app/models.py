"""SQLAlchemy ORM 模型。"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Integer, Numeric, Date, DateTime, ForeignKey, Boolean, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 金额统一精度:18 位整数 + 2 位小数
MONEY = Numeric(18, 2)


class CompanyInfo(Base):
    """企业基本信息(单例,id 恒为 1)。"""
    __tablename__ = "company_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    legal_person: Mapped[str] = mapped_column(String(100), default="")
    accountant: Mapped[str] = mapped_column(String(100), default="")
    auditor: Mapped[str] = mapped_column(String(100), default="")
    bookkeeper: Mapped[str] = mapped_column(String(100), default="")
    recorder: Mapped[str] = mapped_column(String(100), default="")


class Account(Base):
    """会计科目。"""
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    # asset 资产 / liability 负债 / equity 权益 / cost 成本 / profit 损益
    category: Mapped[str] = mapped_column(String(20), index=True)
    # debit 借 / credit 贷:科目的余额方向
    direction: Mapped[str] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    """企业客户/往来单位信息。"""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)          # 名称
    short_name: Mapped[str] = mapped_column(String(60), default="")     # 简称
    tax_number: Mapped[str] = mapped_column(String(40), default="", index=True)  # 税号
    address: Mapped[str] = mapped_column(String(200), default="")       # 开票地址
    phone: Mapped[str] = mapped_column(String(50), default="")          # 开票电话
    bank_name: Mapped[str] = mapped_column(String(120), default="")     # 开户行
    bank_account: Mapped[str] = mapped_column(String(60), default="")   # 银行账号
    contact_person: Mapped[str] = mapped_column(String(50), default="") # 联系人
    contact_phone: Mapped[str] = mapped_column(String(50), default="")  # 联系电话
    email: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Voucher(Base):
    """记账凭证。"""
    __tablename__ = "vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_no: Mapped[str] = mapped_column(String(40), index=True)
    voucher_date: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    total_debit: Mapped[Decimal] = mapped_column(MONEY, default=0)
    total_credit: Mapped[Decimal] = mapped_column(MONEY, default=0)
    status: Mapped[str] = mapped_column(String(20), default="posted")  # draft / posted
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped["Customer | None"] = relationship()
    entries: Mapped[list["VoucherEntry"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan",
        order_by="VoucherEntry.line_no",
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan",
    )


class VoucherEntry(Base):
    """凭证分录(明细行)。一行只填借方或贷方。"""
    __tablename__ = "voucher_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str] = mapped_column(String(200), default="")  # 摘要
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    sub_account: Mapped[str] = mapped_column(String(100), default="")  # 明细科目
    debit: Mapped[Decimal] = mapped_column(MONEY, default=0)
    credit: Mapped[Decimal] = mapped_column(MONEY, default=0)

    voucher: Mapped["Voucher"] = relationship(back_populates="entries")
    account: Mapped["Account"] = relationship()


class Attachment(Base):
    """附件:发票/回单等原始单据。"""
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="other")  # invoice/receipt/other
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    voucher: Mapped["Voucher"] = relationship(back_populates="attachments")


class VoucherLink(Base):
    """凭证关联:预收款/挂账/核销/应收款等人工关联,用于展示相关凭证。"""
    __tablename__ = "voucher_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE"), index=True
    )
    # advance(预收款) / on_account(挂账) / write_off(核销) / receivable(应收款) / other
    relation_type: Mapped[str] = mapped_column(String(20), default="other")
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OperationLog(Base):
    """操作日志:记录全系统数据变更与导入导出/下载行为。"""
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
    # voucher/account/attachment/company/report/ledger/data/other
    action_type: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(100))       # 中文行为描述
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[str] = mapped_column(String(50), default="")
