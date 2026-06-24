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
  kind: 'invoice' | 'receipt' | 'other'
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
  total_debit: number
  total_credit: number
  status: string
  entry_count: number
  attachment_count: number
}

export interface VoucherDetail {
  id: number
  voucher_no: string
  voucher_date: string
  note: string
  total_debit: number
  total_credit: number
  status: string
  created_at: string
  entries: Entry[]
  attachments: Attachment[]
}

export interface Company {
  id: number
  name: string
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
