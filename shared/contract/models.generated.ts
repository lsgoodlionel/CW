/**
 * ⚠️ 本文件由 scripts/gen-contract.mjs 从后端 OpenAPI 自动生成,请勿手改。
 *
 * 来源:backend/app/schemas.py + schemas_read.py(经 FastAPI 反射)
 * 重新生成:node scripts/gen-contract.mjs
 *
 * 这里的名字沿用后端 schema 名;前端习惯用的短名见同目录 models.ts 的别名映射。
 * 共 102 个类型。
 */
/* eslint-disable */

/** 关于本系统:版本、开发、反馈、手册入口。 */
export interface AboutOut {
  name: string
  version: string
  released: string
  description: string
  developer: string
  repo_url: string
  feedback_url: string
  contact: string
  manual_url: string
  manual_download: string
  tech_stack: string[]
}

export interface AccountCreate {
  code: string
  name: string
  category: string
  direction: string
}

export interface AccountOut {
  id: number
  code: string
  name: string
  category: string
  direction: string
  is_active: boolean
}

export interface AccountTreeNode {
  id: number
  code: string
  name: string
  category: string
  direction: string
  is_active: boolean
  sub_accounts?: SubAccountOut[]
}

export interface AccountUpdate {
  name?: string | null
  category?: string | null
  direction?: string | null
  is_active?: boolean | null
}

/** 某业务类型当前启用的流程;exists 为 false 时其余字段为空。 */
export interface ActiveWorkflowOut {
  exists: boolean
  id?: number | null
  name?: string | null
  steps?: ActiveWorkflowStepOut[] | null
}

export interface ActiveWorkflowStepOut {
  step_no: number
  name: string
  approver_type: string
}

/** 向部门添加成员:选已有员工或新建。 */
export interface AddMemberIn {
  employee_id?: number | null
  name?: string
  role_type?: string
  position?: string
}

export interface ApproverCheckOut {
  approver_count: number
  has_approver: boolean
  ready: boolean
  problems: ApproverProblemOut[]
}

export interface ApproverProblemOut {
  id: number
  name: string
  biz_type: string
  biz_type_label: string
  missing_steps: MissingStepOut[]
}

export interface AttachmentOut {
  id: number
  voucher_id?: number | null
  expense_application_id?: number | null
  expense_claim_id?: number | null
  kind: string
  original_name: string
  mime_type: string
  size_bytes: number
  uploaded_at: string
}

export interface AuthPresetOut {
  id: number
  org_unit_id: number | null
  org_unit_name: string
  emp_role_type: string
  emp_role_label: string
  role_id: number
  role_name: string
  note: string
}

export interface AuthUserOut {
  id: number
  username: string
  display_name: string
  is_super_admin: boolean
  employee_id: number | null
  roles: string[]
  permissions: string[]
}

export interface BalanceSheetOut {
  assets: BalanceSheetRowOut[]
  rights: BalanceSheetRowOut[]
  asset_total: number
  right_total: number
  balanced: boolean
}

export interface BalanceSheetRowOut {
  label: string
  line?: number | null
  style: string
  indent?: number | null
  end?: number | null
  begin?: number | null
}

export interface ChangePwIn {
  old_password: string
  new_password: string
}

export interface CompanyOut {
  name?: string
  tax_number?: string
  reg_address?: string
  phone?: string
  bank_name?: string
  bank_account?: string
  establish_date?: string
  industry?: string
  currency?: string
  accounting_standard?: string
  start_period?: string
  legal_person?: string
  accountant?: string
  auditor?: string
  bookkeeper?: string
  recorder?: string
  id: number
}

export interface CompanyUpdate {
  name?: string
  tax_number?: string
  reg_address?: string
  phone?: string
  bank_name?: string
  bank_account?: string
  establish_date?: string
  industry?: string
  currency?: string
  accounting_standard?: string
  start_period?: string
  legal_person?: string
  accountant?: string
  auditor?: string
  bookkeeper?: string
  recorder?: string
}

export interface CreatedOut {
  id: number
}

export interface CustomerBrief {
  id: number
  name: string
  short_name: string
}

export interface CustomerCreate {
  party_type?: string
  name: string
  short_name?: string
  tax_number?: string
  address?: string
  phone?: string
  bank_name?: string
  bank_account?: string
  contact_person?: string
  contact_phone?: string
  email?: string
  note?: string
}

export interface CustomerOut {
  party_type?: string
  name: string
  short_name?: string
  tax_number?: string
  address?: string
  phone?: string
  bank_name?: string
  bank_account?: string
  contact_person?: string
  contact_phone?: string
  email?: string
  note?: string
  id: number
  is_active: boolean
  created_at: string
}

export interface CustomerUpdate {
  party_type?: string
  name: string
  short_name?: string
  tax_number?: string
  address?: string
  phone?: string
  bank_name?: string
  bank_account?: string
  contact_person?: string
  contact_phone?: string
  email?: string
  note?: string
  is_active?: boolean | null
}

export interface CustomerVoucherItemOut {
  id: number
  voucher_no: string
  voucher_date: string
  note: string
  total_debit: number
}

export interface CustomerVouchersOut {
  items: CustomerVoucherItemOut[]
  total: number
  page: number
  page_size: number
  sum_debit: number
}

export interface DashboardOut {
  period: DashboardPeriodOut
  money: MoneyOut
  receivable: number
  payable: number
  tax_payable: number
  revenue: number
  expense: number
  net_profit: number
  voucher_count: number
  expense_breakdown: ExpenseBreakdownOut[]
  trend: TrendPointOut[]
  ops: OpsSummaryOut
}

export interface DashboardPeriodOut {
  type: string
  label: string
  start: string
  end: string
}

/** 备份 zip 恢复结果。 */
export interface DataImportOut {
  success: boolean
  accounts: number
  customers: number
  vouchers: number
  attachments: number
  links: number
}

export interface EmployeeCreate {
  name: string
  employee_no?: string
  gender?: string
  phone?: string
  id_number?: string
  email?: string
  hire_date?: string
  equity_ratio?: number
  status?: string
  note?: string
  positions?: PositionIn[]
}

export interface EmployeeOut {
  name: string
  employee_no?: string
  gender?: string
  phone?: string
  id_number?: string
  email?: string
  hire_date?: string
  equity_ratio?: number
  status?: string
  note?: string
  id: number
  positions?: PositionOut[]
  created_at: string
}

export interface EmployeeUpdate {
  name?: string | null
  employee_no?: string
  gender?: string
  phone?: string
  id_number?: string
  email?: string
  hire_date?: string
  equity_ratio?: number
  status?: string
  note?: string
  positions?: PositionIn[]
}

/** 凭证分录。允许负数金额(红字冲销):一行仍只填借方或贷方。 */
export interface EntryIn {
  summary?: string
  account_id: number
  sub_account?: string
  debit?: number | string
  credit?: number | string
}

export interface EntryOut {
  id: number
  line_no: number
  summary: string
  account_id: number
  account_code?: string
  account_name?: string
  sub_account: string
  sub_account_id?: number | null
  debit: string
  credit: string
}

export interface ExpenseApplicationIn {
  applicant_employee_id?: number | null
  org_unit_id?: number | null
  apply_type?: string
  reason?: string
  note?: string
  items: ExpenseApplicationItemIn[]
}

export interface ExpenseApplicationItemIn {
  category?: string
  account_id?: number | null
  sub_account?: string
  amount?: number | string
  note?: string
}

export interface ExpenseApplicationItemOut {
  category?: string
  account_id?: number | null
  sub_account?: string
  amount?: string
  note?: string
  id: number
  account_name?: string
}

export interface ExpenseApplicationOut {
  id: number
  apply_no: string
  applicant_employee_id: number | null
  applicant_name?: string
  org_unit_id: number | null
  org_unit_name?: string
  apply_type: string
  reason: string
  estimated_amount: string
  status: string
  workflow_instance_id: number | null
  note: string
  created_at: string
  items?: ExpenseApplicationItemOut[]
  attachments?: AttachmentOut[]
  claim_ids?: number[]
  workflow?: InstanceOut | null
}

export interface ExpenseApplyMetaOut {
  categories: string[]
  status: Record<string, string>
  apply_types: Record<string, string>
}

export interface ExpenseBreakdownOut {
  code: string
  name: string
  amount: number
}

export interface ExpenseClaimIn {
  applicant_employee_id?: number | null
  org_unit_id?: number | null
  application_id?: number | null
  reason?: string
  note?: string
  items: ExpenseItemIn[]
}

export interface ExpenseClaimOut {
  id: number
  claim_no: string
  applicant_employee_id: number | null
  applicant_name?: string
  org_unit_id: number | null
  org_unit_name?: string
  application_id?: number | null
  application_no?: string
  reason: string
  total_amount: string
  status: string
  workflow_instance_id: number | null
  voucher_id: number | null
  voucher_no?: string
  note: string
  created_at: string
  items?: ExpenseItemOut[]
  attachments?: AttachmentOut[]
  workflow?: InstanceOut | null
}

export interface ExpenseItemIn {
  category?: string
  account_id?: number | null
  sub_account?: string
  amount?: number | string
  note?: string
}

export interface ExpenseItemOut {
  category?: string
  account_id?: number | null
  sub_account?: string
  amount?: string
  note?: string
  id: number
  account_name?: string
}

export interface ExpenseMetaOut {
  categories: string[]
  status: Record<string, string>
}

export interface HealthOut {
  status: string
}

export interface InstanceOut {
  id: number
  definition_id: number
  biz_type: string
  biz_id: number | null
  title: string
  applicant_employee_id: number | null
  applicant_name?: string
  status: string
  current_step_no: number
  created_at: string
  tasks?: TaskOut[]
  steps?: InstanceStepOut[]
}

/** 完整流程链的一步(合并流程定义步骤 + 实际审批任务)。 */
export interface InstanceStepOut {
  step_no: number
  name: string
  approver_type?: string
  approver_name?: string
  state: string
  comment?: string
  acted_at?: string | null
  is_current?: boolean
}

export interface InstanceSubmit {
  definition_id: number
  biz_type?: string
  biz_id?: number | null
  title?: string
  applicant_employee_id?: number | null
}

export interface LedgerGroupOut {
  title: string
  code: string
  name: string
  sub: string
  opening: number
  closing: number
  rows: LedgerRowOut[]
  columns?: string[] | null
}

export interface LedgerOut {
  ledger_type: string
  title: string
  period_label: string
  columns: string[]
  groups: LedgerGroupOut[]
  note?: string | null
}

export interface LedgerRowOut {
  cells: (string | number | null)[]
  is_summary?: boolean | null
}

/** 账簿种类:值 → 中文名。接口直接返回该映射本身。 */
export interface LedgerTypesOut {
  general: string
  detail_three: string
  detail_multi: string
  qty_amount: string
  cash_journal: string
  bank_journal: string
}

export interface LinkedVoucher {
  link_id: number
  relation_type: string
  note: string
  direction: string
  voucher_id: number
  voucher_no: string
  voucher_date: string
  voucher_note: string
  total_debit: string
}

export interface LogItemOut {
  id: number
  created_at: string
  action_type: string
  action_type_label: string
  action: string
  method: string
  path: string
  entity_id: string
  summary: string
  operator: string
  detail: string
  status_code: number
  duration_ms: number
  ip: string
}

export interface LogPageOut {
  items: LogItemOut[]
  total: number
  page: number
  page_size: number
  types: Record<string, string>
}

export interface LoginIn {
  username: string
  password: string
}

export interface LoginOut {
  token: string
  user: AuthUserOut
}

export interface MissingStepOut {
  step_no: number
  name: string
  approver_type: string
  approver_type_label: string
}

export interface MoneyOut {
  cash: number
  bank: number
  other: number
  total: number
}

export interface OfficialReportsOut {
  period: ReportPeriodOut
  balance_sheet: BalanceSheetOut
  income: StatementOut
  cashflow: StatementOut
}

export interface OpsSummaryOut {
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

export interface OrgUnitCreate {
  name: string
  parent_id?: number | null
  note?: string
}

export interface OrgUnitOut {
  id: number
  parent_id: number | null
  name: string
  sort_no: number
  note: string
  employee_count?: number
}

export interface OrgUnitUpdate {
  name?: string | null
  parent_id?: number | null
  note?: string | null
}

export interface PermissionActionOut {
  action: string
  label: string
}

export interface PermissionModuleOut {
  module: string
  label: string
  actions: PermissionActionOut[]
}

export interface PersonnelMetaOut {
  role_types: Record<string, string>
  party_types: Record<string, string>
}

export interface PositionIn {
  org_unit_id?: number | null
  role_type?: string
  position?: string
}

export interface PositionOut {
  id: number
  org_unit_id: number | null
  org_unit_name?: string
  role_type: string
  position: string
}

export interface PresetApplyOut {
  updated: number
  total: number
}

export interface PresetIn {
  org_unit_id?: number | null
  emp_role_type?: string
  role_id: number
  note?: string
}

export interface PresetResolveOut {
  role_ids: number[]
}

export interface ReportPeriodOut {
  label: string
  report_type: string
  start: string
  end: string
}

export interface ResetPwIn {
  new_password: string
}

export interface RoleIn {
  name: string
  note?: string
  perms?: string[]
}

export interface RoleOut {
  id: number
  name: string
  note: string
  is_system: boolean
  perms: string[]
}

export interface StatementOut {
  rows: StatementRowOut[]
  col1_label: string
  col2_label: string
}

/** 利润表 / 现金流量表的行。line 为空表示分组标题行。 */
export interface StatementRowOut {
  label: string
  line?: number | null
  style: string
  indent?: number | null
  col1?: number | null
  col2?: number | null
}

export interface StepIn {
  name?: string
  approver_type?: string
  approver_employee_id?: number | null
  approver_role?: string
}

export interface StepOut {
  name?: string
  approver_type?: string
  approver_employee_id?: number | null
  approver_role?: string
  id: number
  step_no: number
  approver_name?: string
}

export interface SubAccountCreate {
  name: string
  note?: string
  code?: string
}

/** 二级科目 Excel 导入结果。 */
export interface SubAccountImportOut {
  created: number
  skipped: number
  errors: number
  messages: string[]
}

export interface SubAccountOut {
  id: number
  account_id: number
  code: string
  name: string
  note: string
  is_active: boolean
  sort_no: number
}

export interface SubAccountUpdate {
  name?: string | null
  note?: string | null
  is_active?: boolean | null
}

export interface SuccessOut {
  success: boolean
}

export interface TaskAction {
  comment?: string
}

export interface TaskOut {
  id: number
  instance_id: number
  step_no: number
  step_name: string
  approver_employee_id: number | null
  approver_name?: string
  result: string
  comment: string
  acted_at: string | null
}

export interface TaskReassign {
  employee_id?: number | null
}

export interface TrendPointOut {
  month: string
  revenue: number
  net_profit: number
}

export interface TrialBalanceOut {
  rows: TrialBalanceRowOut[]
  total_debit: number
  total_credit: number
  balanced: boolean
}

export interface TrialBalanceRowOut {
  code: string
  name: string
  category: string
  direction: string
  debit: number
  credit: number
  balance: number
}

export interface UserCreate {
  username: string
  password: string
  display_name?: string
  employee_id?: number | null
  is_super_admin?: boolean
  role_ids?: number[]
}

export interface UserOut {
  id: number
  username: string
  display_name: string
  employee_id: number | null
  is_super_admin: boolean
  is_active: boolean
  role_ids: number[]
  role_names: string[]
  created_at: string | null
}

export interface UserUpdate {
  display_name?: string | null
  employee_id?: number | null
  is_active?: boolean | null
  is_super_admin?: boolean | null
  role_ids?: number[] | null
}

export interface VoucherCreate {
  voucher_no?: string
  voucher_date: string
  note?: string
  customer_id?: number | null
  status?: string
  entries: EntryIn[]
}

export interface VoucherDetail {
  id: number
  voucher_no: string
  voucher_date: string
  note: string
  customer_id?: number | null
  customer?: CustomerBrief | null
  total_debit: string
  total_credit: string
  status: string
  created_at: string
  entries: EntryOut[]
  attachments: AttachmentOut[]
  links?: LinkedVoucher[]
}

export interface VoucherLinkCreate {
  target_id: number
  relation_type?: string
  note?: string
}

export interface VoucherListItem {
  id: number
  voucher_no: string
  voucher_date: string
  note: string
  customer_id?: number | null
  customer_name?: string
  total_debit: string
  total_credit: string
  status: string
  entry_count?: number
  attachment_count?: number
  link_count?: number
}

export interface VoucherPage {
  items: VoucherListItem[]
  total: number
  page: number
  page_size: number
}

export interface WorkflowDefIn {
  name: string
  biz_type?: string
  note?: string
  is_active?: boolean
  steps: StepIn[]
}

export interface WorkflowDefOut {
  id: number
  name: string
  biz_type: string
  note: string
  is_active: boolean
  steps?: StepOut[]
}

export interface WorkflowMetaOut {
  approver_types: Record<string, string>
  biz_types: Record<string, string>
  status: Record<string, string>
}
