"""只读 / 计算类接口的响应模型。

`schemas.py` 覆盖的是 ORM 增删改查;本文件补齐那些直接返回 dict 的接口
(认证、用户角色、报表、账簿、日志、各类 meta),让 OpenAPI 能完整描述前端契约,
从而由 `scripts/gen-contract.mjs` 自动生成两端共用的 TypeScript 类型。

约定:
  · 形状封闭的响应用 `response_model=`,既进 OpenAPI 也做序列化校验;
  · 形状开放的响应(账簿的行随账簿种类变化)只用 `responses={200: {"model": ...}}`
    做文档标注,不参与序列化,避免动态字段被裁掉。
"""
from pydantic import BaseModel


# ---------- 通用 ----------
class SuccessOut(BaseModel):
    success: bool


class HealthOut(BaseModel):
    status: str


class AboutOut(BaseModel):
    """关于本系统:版本、开发、反馈、手册入口。"""
    name: str
    version: str
    released: str
    description: str
    developer: str
    repo_url: str
    feedback_url: str
    contact: str
    manual_url: str
    manual_download: str
    tech_stack: list[str]


# ---------- 导入结果 ----------
class SubAccountImportOut(BaseModel):
    """二级科目 Excel 导入结果。"""
    created: int
    skipped: int
    errors: int
    #: 最多前 50 条提示
    messages: list[str]


class DataImportOut(BaseModel):
    """备份 zip 恢复结果。"""
    success: bool
    accounts: int
    customers: int
    vouchers: int
    attachments: int
    links: int


# ---------- 认证 ----------
class PermissionActionOut(BaseModel):
    action: str
    label: str


class PermissionModuleOut(BaseModel):
    module: str
    label: str
    actions: list[PermissionActionOut]


class AuthUserOut(BaseModel):
    id: int
    username: str
    display_name: str
    is_super_admin: bool
    employee_id: int | None
    roles: list[str]
    #: 超管为 ["*"]
    permissions: list[str]


class LoginOut(BaseModel):
    token: str
    user: AuthUserOut


# ---------- 用户 / 角色 / 授权预设 ----------
class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    employee_id: int | None
    is_super_admin: bool
    is_active: bool
    role_ids: list[int]
    role_names: list[str]
    created_at: str | None


class RoleOut(BaseModel):
    id: int
    name: str
    note: str
    is_system: bool
    perms: list[str]


class CreatedOut(BaseModel):
    id: int


class AuthPresetOut(BaseModel):
    id: int
    org_unit_id: int | None
    org_unit_name: str
    emp_role_type: str
    emp_role_label: str
    role_id: int
    role_name: str
    note: str


class PresetResolveOut(BaseModel):
    role_ids: list[int]


class PresetApplyOut(BaseModel):
    updated: int
    total: int


# ---------- 仪表盘 ----------
class DashboardPeriodOut(BaseModel):
    type: str
    label: str
    start: str
    end: str


class MoneyOut(BaseModel):
    cash: float
    bank: float
    other: float
    total: float


class ExpenseBreakdownOut(BaseModel):
    code: str
    name: str
    amount: float


class TrendPointOut(BaseModel):
    month: str
    revenue: float
    net_profit: float


class OpsSummaryOut(BaseModel):
    workflow_pending: int
    apply_pending: int
    apply_approved: int
    claim_pending: int
    claim_approved: int
    claim_paid: int
    customers: int
    employees: int
    attachments: int


class DashboardOut(BaseModel):
    period: DashboardPeriodOut
    money: MoneyOut
    receivable: float
    payable: float
    tax_payable: float
    revenue: float
    expense: float
    net_profit: float
    voucher_count: int
    expense_breakdown: list[ExpenseBreakdownOut]
    trend: list[TrendPointOut]
    ops: OpsSummaryOut


# ---------- 官方三表 ----------
class ReportPeriodOut(BaseModel):
    label: str
    report_type: str
    start: str
    end: str


class StatementRowOut(BaseModel):
    """利润表 / 现金流量表的行。line 为空表示分组标题行。"""
    label: str
    line: int | None = None
    style: str
    indent: int | None = None
    col1: float | None = None
    col2: float | None = None


class StatementOut(BaseModel):
    rows: list[StatementRowOut]
    col1_label: str
    col2_label: str


class BalanceSheetRowOut(BaseModel):
    label: str
    line: int | None = None
    style: str
    indent: int | None = None
    end: float | None = None
    begin: float | None = None


class BalanceSheetOut(BaseModel):
    assets: list[BalanceSheetRowOut]
    rights: list[BalanceSheetRowOut]
    asset_total: float
    right_total: float
    balanced: bool


class OfficialReportsOut(BaseModel):
    period: ReportPeriodOut
    balance_sheet: BalanceSheetOut
    income: StatementOut
    cashflow: StatementOut


# ---------- 科目汇总表 ----------
class TrialBalanceRowOut(BaseModel):
    code: str
    name: str
    category: str
    direction: str
    debit: float
    credit: float
    balance: float


class TrialBalanceOut(BaseModel):
    rows: list[TrialBalanceRowOut]
    total_debit: float
    total_credit: float
    balanced: bool


# ---------- 会计账簿 ----------
# 账簿行的字段随账簿种类变化(日记账有对方科目、多栏式有明细科目列…),
# 这里只描述前端通用渲染依赖的稳定部分,仅作 OpenAPI 文档,不参与序列化。
class LedgerRowOut(BaseModel):
    #: 扁平化后的单元格,顺序与所在分组的 columns 对应
    cells: list[str | float | None]
    #: 合计 / 期初期末等强调行
    is_summary: bool | None = None


class LedgerGroupOut(BaseModel):
    title: str
    code: str
    name: str
    sub: str
    opening: float
    closing: float
    rows: list[LedgerRowOut]
    #: 多栏式明细账每组有各自的列头,缺省时用顶层 columns
    columns: list[str] | None = None


class LedgerOut(BaseModel):
    ledger_type: str
    title: str
    period_label: str
    columns: list[str]
    groups: list[LedgerGroupOut]
    note: str | None = None


# ---------- 操作日志 ----------
class LogItemOut(BaseModel):
    id: int
    created_at: str
    action_type: str
    action_type_label: str
    action: str
    method: str
    path: str
    entity_id: str
    summary: str
    operator: str
    detail: str
    status_code: int
    duration_ms: int
    ip: str


class LogPageOut(BaseModel):
    items: list[LogItemOut]
    total: int
    page: int
    page_size: int
    #: 操作类型枚举:值 → 中文名
    types: dict[str, str]


# ---------- 往来单位业务历史 ----------
class CustomerVoucherItemOut(BaseModel):
    id: int
    voucher_no: str
    voucher_date: str
    note: str
    total_debit: float


class CustomerVouchersOut(BaseModel):
    items: list[CustomerVoucherItemOut]
    total: int
    page: int
    page_size: int
    sum_debit: float


# ---------- 审批流程 ----------
class ActiveWorkflowStepOut(BaseModel):
    step_no: int
    name: str
    approver_type: str


class ActiveWorkflowOut(BaseModel):
    """某业务类型当前启用的流程;exists 为 false 时其余字段为空。"""
    exists: bool
    id: int | None = None
    name: str | None = None
    steps: list[ActiveWorkflowStepOut] | None = None


class MissingStepOut(BaseModel):
    step_no: int
    name: str
    approver_type: str
    approver_type_label: str


class ApproverProblemOut(BaseModel):
    id: int
    name: str
    biz_type: str
    biz_type_label: str
    missing_steps: list[MissingStepOut]


class ApproverCheckOut(BaseModel):
    approver_count: int
    has_approver: bool
    ready: bool
    problems: list[ApproverProblemOut]


# ---------- 各类枚举 meta ----------
class WorkflowMetaOut(BaseModel):
    approver_types: dict[str, str]
    biz_types: dict[str, str]
    status: dict[str, str]


class ExpenseMetaOut(BaseModel):
    categories: list[str]
    status: dict[str, str]


class ExpenseApplyMetaOut(BaseModel):
    categories: list[str]
    status: dict[str, str]
    apply_types: dict[str, str]


class PersonnelMetaOut(BaseModel):
    role_types: dict[str, str]
    party_types: dict[str, str]


class LedgerTypesOut(BaseModel):
    """账簿种类:值 → 中文名。接口直接返回该映射本身。"""
    general: str
    detail_three: str
    detail_multi: str
    qty_amount: str
    cash_journal: str
    bank_journal: str
