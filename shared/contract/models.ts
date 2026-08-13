/**
 * 前后端数据契约:与 backend/app/schemas.py 及各 router 的返回结构一一对应。
 *
 * 这里是唯一事实源,Web 前端与微信小程序都从这里取类型。
 * 后端改了字段,只改本文件,再跑 `node scripts/sync-shared.mjs` 同步到两端。
 */

export type Category = 'asset' | 'liability' | 'equity' | 'cost' | 'profit'

export interface AuthUser {
  id: number
  username: string
  display_name: string
  is_super_admin: boolean
  employee_id: number | null
  roles: string[]
  /** 超管为 ['*'] */
  permissions: string[]
}

export interface Account {
  id: number
  code: string
  name: string
  category: Category
  direction: 'debit' | 'credit'
  is_active: boolean
}

export interface SubAccount {
  id: number
  account_id: number
  code: string
  name: string
  note: string
  is_active: boolean
  sort_no: number
}

export interface AccountTreeNode extends Account {
  sub_accounts: SubAccount[]
}

export interface Entry {
  id?: number
  line_no?: number
  summary: string
  account_id: number
  account_code?: string
  account_name?: string
  sub_account: string
  debit: number
  credit: number
}

export interface Attachment {
  id: number
  voucher_id: number | null
  expense_application_id?: number | null
  expense_claim_id?: number | null
  kind: string
  original_name: string
  mime_type: string
  size_bytes: number
  uploaded_at: string
}

export interface VoucherListItem {
  id: number
  voucher_no: string
  voucher_date: string
  note: string
  customer_id: number | null
  customer_name: string
  total_debit: number
  total_credit: number
  status: string
  entry_count: number
  attachment_count: number
  link_count: number
}

export interface VoucherPage {
  items: VoucherListItem[]
  total: number
}

export interface LinkedVoucher {
  link_id: number
  relation_type: string
  note: string
  direction: 'in' | 'out'
  voucher_id: number
  voucher_no: string
  voucher_date: string
  voucher_note: string
  total_debit: number
}

export interface VoucherDetail {
  id: number
  voucher_no: string
  voucher_date: string
  note: string
  customer_id: number | null
  customer: { id: number; name: string; short_name: string } | null
  total_debit: number
  total_credit: number
  status: string
  created_at: string
  entries: Entry[]
  attachments: Attachment[]
  links: LinkedVoucher[]
}

export interface Customer {
  id: number
  party_type: string
  name: string
  short_name: string
  tax_number: string
  address: string
  phone: string
  bank_name: string
  bank_account: string
  contact_person: string
  contact_phone: string
  email: string
  note: string
  is_active: boolean
  created_at: string
}

export interface CustomerVoucherItem {
  id: number
  voucher_no: string
  voucher_date: string
  note: string
  total_debit: number
}

export interface OrgUnit {
  id: number
  parent_id: number | null
  name: string
  sort_no: number
  note: string
  employee_count: number
}

export interface Position {
  id?: number
  org_unit_id: number | null
  org_unit_name?: string
  role_type: string
  position: string
}

export interface Employee {
  id: number
  employee_no: string
  name: string
  gender: string
  phone: string
  id_number: string
  email: string
  hire_date: string
  equity_ratio: number
  status: string
  note: string
  positions: Position[]
  created_at: string
}

export interface WorkflowStep {
  id?: number
  step_no?: number
  name: string
  approver_type: string
  approver_employee_id: number | null
  approver_role: string
  approver_name?: string
}

export interface WorkflowDef {
  id: number
  name: string
  biz_type: string
  note: string
  is_active: boolean
  steps: WorkflowStep[]
}

export interface WorkflowTask {
  id: number
  instance_id: number
  step_no: number
  step_name: string
  approver_employee_id: number | null
  approver_name: string
  result: string
  comment: string
  acted_at: string | null
}

export interface InstanceStep {
  step_no: number
  name: string
  approver_type: string
  approver_name: string
  /** approved / rejected / current / upcoming / skipped */
  state: string
  comment: string
  acted_at: string | null
  is_current: boolean
}

export interface WorkflowInstance {
  id: number
  definition_id: number
  biz_type: string
  biz_id: number | null
  title: string
  applicant_employee_id: number | null
  applicant_name: string
  status: string
  current_step_no: number
  created_at: string
  tasks: WorkflowTask[]
  steps: InstanceStep[]
}

export interface ApproverCheckProblem {
  id: number
  name: string
  biz_type: string
  biz_type_label: string
  missing_steps: {
    step_no: number
    name: string
    approver_type: string
    approver_type_label: string
  }[]
}

export interface ApproverCheck {
  approver_count: number
  has_approver: boolean
  ready: boolean
  problems: ApproverCheckProblem[]
}

export interface ActiveWorkflow {
  exists: boolean
  id?: number
  name?: string
  steps?: { step_no: number; name: string; approver_type: string }[]
}

export interface ExpenseItem {
  id?: number
  category: string
  account_id: number | null
  sub_account: string
  amount: number
  note: string
  account_name?: string
}

export interface ExpenseClaim {
  id: number
  claim_no: string
  applicant_employee_id: number | null
  applicant_name: string
  org_unit_id: number | null
  org_unit_name: string
  application_id: number | null
  application_no: string
  reason: string
  total_amount: number
  status: string
  workflow_instance_id: number | null
  voucher_id: number | null
  voucher_no: string
  note: string
  created_at: string
  items: ExpenseItem[]
  attachments: Attachment[]
  workflow: WorkflowInstance | null
}

export interface ExpenseApplication {
  id: number
  apply_no: string
  applicant_employee_id: number | null
  applicant_name: string
  org_unit_id: number | null
  org_unit_name: string
  apply_type: string
  reason: string
  estimated_amount: number
  status: string
  workflow_instance_id: number | null
  note: string
  created_at: string
  items: ExpenseItem[]
  attachments: Attachment[]
  claim_ids: number[]
  workflow: WorkflowInstance | null
}

export interface Company {
  id: number
  name: string
  tax_number: string
  reg_address: string
  phone: string
  bank_name: string
  bank_account: string
  establish_date: string
  industry: string
  currency: string
  accounting_standard: string
  start_period: string
  legal_person: string
  accountant: string
  auditor: string
  bookkeeper: string
  recorder: string
}

/* ---------- 仪表盘 ---------- */
export interface DashboardData {
  period: { type: string; label: string; start: string; end: string }
  money: { cash: number; bank: number; other: number; total: number }
  receivable: number
  payable: number
  tax_payable: number
  revenue: number
  expense: number
  net_profit: number
  voucher_count: number
  expense_breakdown: { code: string; name: string; amount: number }[]
  trend: { month: string; revenue: number; net_profit: number }[]
  ops: {
    workflow_pending: number
    apply_pending: number
    apply_approved: number
    claim_pending: number
    claim_approved: number
    claim_paid: number
    customers: number
    employees: number
    attachments: number
  }
}

/* ---------- 报表 ---------- */
export interface StatementRow {
  label: string
  line: number | null
  style: string
  indent?: number
  col1: number | null
  col2: number | null
}

export interface Statement {
  rows: StatementRow[]
  col1_label: string
  col2_label: string
}

export interface BalanceSheetRow {
  label: string
  line: number | null
  style: string
  indent?: number
  end: number | null
  begin: number | null
}

export interface BalanceSheet {
  assets: BalanceSheetRow[]
  rights: BalanceSheetRow[]
  asset_total: number
  right_total: number
  balanced: boolean
}

export interface OfficialReports {
  period: { label: string }
  balance_sheet: BalanceSheet
  income: Statement
  cashflow: Statement
}

export interface TrialBalanceRow {
  code: string
  name: string
  debit: number
  credit: number
  balance: number
}

export interface TrialBalance {
  rows: TrialBalanceRow[]
  total_debit: number
  total_credit: number
  balanced: boolean
}

/* ---------- 账簿 ---------- */
export interface LedgerRow {
  cells: (string | number)[]
  is_summary?: boolean
}

export interface LedgerGroup {
  title: string
  opening: number
  closing: number
  rows: LedgerRow[]
  columns?: string[]
}

export interface Ledger {
  ledger_type: string
  title: string
  period_label: string
  columns: string[]
  groups: LedgerGroup[]
  note?: string
}

/* ---------- 日志 ---------- */
export interface LogItem {
  id: number
  created_at: string
  action_type: string
  action_type_label: string
  action: string
  summary: string
  operator: string
  detail: string
  status_code: number
  duration_ms: number
  ip: string
}

export interface LogPage {
  items: LogItem[]
  total: number
  types: Record<string, string>
}

/* ---------- 用户与权限 ---------- */
export interface Role {
  id: number
  name: string
  note: string
  is_system: boolean
  perms: string[]
}

export interface UserRow {
  id: number
  username: string
  display_name: string
  employee_id: number | null
  is_super_admin: boolean
  is_active: boolean
  role_ids: number[]
  role_names: string[]
}

export interface PermissionAction {
  action: string
  label: string
}

export interface PermissionModule {
  module: string
  label: string
  actions: PermissionAction[]
}

export interface AuthPreset {
  id: number
  org_unit_id: number | null
  org_unit_name: string
  emp_role_type: string
  emp_role_label: string
  role_id: number
  role_name: string
  note: string
}
