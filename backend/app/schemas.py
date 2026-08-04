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
class CompanyFields(BaseModel):
    name: str = ""
    tax_number: str = ""
    reg_address: str = ""
    phone: str = ""
    bank_name: str = ""
    bank_account: str = ""
    establish_date: str = ""
    industry: str = ""
    currency: str = "人民币"
    accounting_standard: str = "小企业会计准则"
    start_period: str = ""
    legal_person: str = ""
    accountant: str = ""
    auditor: str = ""
    bookkeeper: str = ""
    recorder: str = ""


class CompanyOut(CompanyFields):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CompanyUpdate(CompanyFields):
    pass


# ---------- 二级科目 ----------
class SubAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    code: str
    name: str
    note: str
    is_active: bool
    sort_no: int


class SubAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    note: str = ""
    code: str = ""  # 留空自动按一级编码延续生成


class SubAccountUpdate(BaseModel):
    name: str | None = None
    note: str | None = None
    is_active: bool | None = None


# ---------- 科目 ----------
class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    category: str
    direction: str
    is_active: bool


class AccountTreeNode(AccountOut):
    sub_accounts: list[SubAccountOut] = []


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
    """凭证分录。允许负数金额(红字冲销):一行仍只填借方或贷方。"""
    summary: str = ""
    account_id: int
    sub_account: str = ""
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_no: int
    summary: str
    account_id: int
    account_code: str = ""
    account_name: str = ""
    sub_account: str
    sub_account_id: int | None = None
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


# ---------- 往来单位 ----------
PARTY_TYPES = {"enterprise", "individual", "supplier", "partner"}


class CustomerBase(BaseModel):
    party_type: str = "enterprise"
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


# ---------- 组织架构 ----------
class OrgUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    note: str = ""


class OrgUnitUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    note: str | None = None


class OrgUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    parent_id: int | None
    name: str
    sort_no: int
    note: str
    employee_count: int = 0


# ---------- 员工任职(一人多岗)----------
class PositionIn(BaseModel):
    org_unit_id: int | None = None
    role_type: str = "staff"
    position: str = ""


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    org_unit_id: int | None
    org_unit_name: str = ""
    role_type: str
    position: str


# ---------- 员工档案 ----------
class EmployeeBase(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    employee_no: str = ""
    gender: str = ""
    phone: str = ""
    id_number: str = ""
    email: str = ""
    hire_date: str = ""
    equity_ratio: float = 0
    status: str = "active"
    note: str = ""


class EmployeeCreate(EmployeeBase):
    positions: list[PositionIn] = []


class EmployeeUpdate(EmployeeCreate):
    name: str | None = None


class EmployeeOut(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    positions: list[PositionOut] = []
    created_at: datetime


class AddMemberIn(BaseModel):
    """向部门添加成员:选已有员工或新建。"""
    employee_id: int | None = None      # 选已有员工
    name: str = ""                       # 或新建员工姓名
    role_type: str = "staff"
    position: str = ""


# ---------- 审批流程 ----------
class StepIn(BaseModel):
    name: str = ""
    approver_type: str = "employee"   # employee/role/department_head/any
    approver_employee_id: int | None = None
    approver_role: str = ""


class StepOut(StepIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    step_no: int
    approver_name: str = ""


class WorkflowDefIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    biz_type: str = "general"
    note: str = ""
    is_active: bool = True
    steps: list[StepIn] = Field(min_length=1)


class WorkflowDefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    biz_type: str
    note: str
    is_active: bool
    steps: list[StepOut] = []


class InstanceSubmit(BaseModel):
    definition_id: int
    biz_type: str = "general"
    biz_id: int | None = None
    title: str = ""
    applicant_employee_id: int | None = None


class TaskAction(BaseModel):
    comment: str = ""


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instance_id: int
    step_no: int
    step_name: str
    approver_employee_id: int | None
    approver_name: str = ""
    result: str
    comment: str
    acted_at: datetime | None


class InstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    definition_id: int
    biz_type: str
    biz_id: int | None
    title: str
    applicant_employee_id: int | None
    applicant_name: str = ""
    status: str
    current_step_no: int
    created_at: datetime
    tasks: list[TaskOut] = []


# ---------- 费用报销 ----------
class ExpenseItemIn(BaseModel):
    category: str = ""
    account_id: int | None = None
    sub_account: str = ""
    amount: Decimal = Decimal("0")
    note: str = ""


class ExpenseItemOut(ExpenseItemIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_name: str = ""


class ExpenseClaimIn(BaseModel):
    applicant_employee_id: int | None = None
    org_unit_id: int | None = None
    reason: str = ""
    note: str = ""
    items: list[ExpenseItemIn] = Field(min_length=1)


class ExpenseClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    claim_no: str
    applicant_employee_id: int | None
    applicant_name: str = ""
    org_unit_id: int | None
    org_unit_name: str = ""
    reason: str
    total_amount: Decimal
    status: str
    workflow_instance_id: int | None
    voucher_id: int | None
    voucher_no: str = ""
    note: str
    created_at: datetime
    items: list[ExpenseItemOut] = []
    workflow: InstanceOut | None = None


# ---------- 凭证关联 ----------
RELATION_TYPES = {"advance", "on_account", "write_off", "receivable", "reversal", "other"}


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
        # 允许红字(负数)冲销:判定用「非零」而非「大于零」
        for e in entries:
            has_debit = e.debit != 0
            has_credit = e.credit != 0
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
