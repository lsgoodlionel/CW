"""Pydantic 模式:请求/响应数据校验。"""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------- 通用响应信封 ----------
class Envelope(BaseModel):
    success: bool = True
    data: object | None = None
    error: str | None = None


# ---------- 企业信息 ----------
class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    legal_person: str
    accountant: str
    auditor: str
    bookkeeper: str
    recorder: str


class CompanyUpdate(BaseModel):
    name: str = ""
    legal_person: str = ""
    accountant: str = ""
    auditor: str = ""
    bookkeeper: str = ""
    recorder: str = ""


# ---------- 科目 ----------
class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    category: str
    direction: str
    is_active: bool


class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    category: str
    direction: str

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        allowed = {"asset", "liability", "equity", "cost", "profit"}
        if v not in allowed:
            raise ValueError(f"category 必须是 {allowed} 之一")
        return v

    @field_validator("direction")
    @classmethod
    def _check_direction(cls, v: str) -> str:
        if v not in {"debit", "credit"}:
            raise ValueError("direction 必须是 debit 或 credit")
        return v


class AccountUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    direction: str | None = None
    is_active: bool | None = None


# ---------- 凭证分录 ----------
class EntryIn(BaseModel):
    summary: str = ""
    account_id: int
    sub_account: str = ""
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")

    @field_validator("debit", "credit")
    @classmethod
    def _non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("金额不能为负")
        return v


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_no: int
    summary: str
    account_id: int
    account_code: str = ""
    account_name: str = ""
    sub_account: str
    debit: Decimal
    credit: Decimal


# ---------- 附件 ----------
class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    voucher_id: int
    kind: str
    original_name: str
    mime_type: str
    size_bytes: int
    uploaded_at: datetime


# ---------- 客户 ----------
class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    short_name: str = ""
    tax_number: str = ""
    address: str = ""
    phone: str = ""
    bank_name: str = ""
    bank_account: str = ""
    contact_person: str = ""
    contact_phone: str = ""
    email: str = ""
    note: str = ""


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(CustomerBase):
    is_active: bool | None = None


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: datetime


class CustomerBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    short_name: str


# ---------- 凭证关联 ----------
RELATION_TYPES = {"advance", "on_account", "write_off", "receivable", "other"}


class VoucherLinkCreate(BaseModel):
    target_id: int
    relation_type: str = "other"
    note: str = ""

    @field_validator("relation_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in RELATION_TYPES:
            raise ValueError(f"relation_type 必须是 {RELATION_TYPES} 之一")
        return v


class LinkedVoucher(BaseModel):
    link_id: int
    relation_type: str
    note: str
    direction: str  # out(本凭证指向对方) / in(对方指向本凭证)
    voucher_id: int
    voucher_no: str
    voucher_date: date
    voucher_note: str
    total_debit: Decimal


# ---------- 凭证 ----------
class VoucherCreate(BaseModel):
    voucher_no: str = ""
    voucher_date: date
    note: str = ""
    customer_id: int | None = None
    status: str = "posted"
    entries: list[EntryIn] = Field(min_length=1)

    @field_validator("entries")
    @classmethod
    def _check_entries(cls, entries: list[EntryIn]) -> list[EntryIn]:
        for e in entries:
            has_debit = e.debit > 0
            has_credit = e.credit > 0
            if has_debit and has_credit:
                raise ValueError("同一分录不能同时填借方和贷方")
            if not has_debit and not has_credit:
                raise ValueError("每条分录必须填借方或贷方金额")
        total_debit = sum((e.debit for e in entries), Decimal("0"))
        total_credit = sum((e.credit for e in entries), Decimal("0"))
        if total_debit != total_credit:
            raise ValueError(
                f"借贷不平衡:借方合计 {total_debit} ≠ 贷方合计 {total_credit}"
            )
        return entries


class VoucherListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    voucher_no: str
    voucher_date: date
    note: str
    customer_id: int | None = None
    customer_name: str = ""
    total_debit: Decimal
    total_credit: Decimal
    status: str
    entry_count: int = 0
    attachment_count: int = 0
    link_count: int = 0


class VoucherDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    voucher_no: str
    voucher_date: date
    note: str
    customer_id: int | None = None
    customer: CustomerBrief | None = None
    total_debit: Decimal
    total_credit: Decimal
    status: str
    created_at: datetime
    entries: list[EntryOut]
    attachments: list[AttachmentOut]
    links: list[LinkedVoucher] = []


class VoucherPage(BaseModel):
    items: list[VoucherListItem]
    total: int
    page: int
    page_size: int
