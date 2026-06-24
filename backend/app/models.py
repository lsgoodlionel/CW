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


class Voucher(Base):
    """记账凭证。"""
    __tablename__ = "vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_no: Mapped[str] = mapped_column(String(40), index=True)
    voucher_date: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    total_debit: Mapped[Decimal] = mapped_column(MONEY, default=0)
    total_credit: Mapped[Decimal] = mapped_column(MONEY, default=0)
    status: Mapped[str] = mapped_column(String(20), default="posted")  # draft / posted
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

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
