import axios from 'axios'
import { message } from 'antd'

export const http = axios.create({ baseURL: '/api', timeout: 30000 })

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err?.response?.data?.detail
    const text =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg: string }) => d.msg).join('; ')
          : err.message || '请求失败'
    message.error(text)
    return Promise.reject(err)
  },
)

// ---------- 类型 ----------
export type Category = 'asset' | 'liability' | 'equity' | 'cost' | 'profit'

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
  voucher_id: number
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

export const PARTY_LABEL: Record<string, string> = {
  enterprise: '企业客户',
  individual: '个人客户',
  supplier: '供应商',
  partner: '往来单位',
}

export const ROLE_LABEL: Record<string, string> = {
  shareholder: '股东',
  management: '管理层',
  staff: '普通员工',
  other: '其他',
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
  reason: string
  total_amount: number
  status: string
  workflow_instance_id: number | null
  voucher_id: number | null
  voucher_no: string
  note: string
  created_at: string
  items: ExpenseItem[]
  workflow: WorkflowInstance | null
}

export const EXPENSE_STATUS_LABEL: Record<string, string> = {
  draft: '草稿', pending: '审批中', approved: '已通过', rejected: '已驳回', paid: '已生成凭证',
}

export const APPROVER_TYPE_LABEL: Record<string, string> = {
  employee: '指定员工', role: '按角色', department_head: '部门负责人', any: '任一管理层',
}
export const WF_STATUS_LABEL: Record<string, string> = {
  pending: '审批中', approved: '已通过', rejected: '已驳回', cancelled: '已撤销',
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

export const RELATION_LABEL: Record<string, string> = {
  advance: '预收款',
  on_account: '挂账',
  write_off: '核销',
  receivable: '应收款',
  reversal: '冲销',
  other: '其他',
}

export const ATTACHMENT_KIND_LABEL: Record<string, string> = {
  invoice: '发票',
  receipt: '银行回单',
  contract: '合同',
  tax_payment: '完税证明',
  other: '其他',
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

export const CATEGORY_LABEL: Record<Category, string> = {
  asset: '资产类',
  liability: '负债类',
  equity: '权益类',
  cost: '成本类',
  profit: '损益类',
}
