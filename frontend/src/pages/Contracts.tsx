import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Button, Space, Modal, Form, Input, Select, InputNumber, DatePicker,
  Popconfirm, message, Divider, Segmented, AutoComplete,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate, useSearchParams } from 'react-router-dom'
import dayjs from 'dayjs'
import { http, Attachment, Customer, VoucherListItem, formatYuan, PARTY_LABEL } from '../api'
import AttachmentEditor from '../components/AttachmentEditor'

interface ContractVoucher {
  id: number; voucher_id: number; voucher_no: string
  voucher_date: string | null; total_debit: number | string; note: string
}
interface Contract {
  id: number; contract_no: string; name: string; category: string; direction: string
  customer_id: number | null; customer_name: string; party_name: string
  amount: number | string; tax_rate: number | string; tax_amount: number | string
  sign_date: string | null; start_date: string | null
  end_date: string | null; status: string; our_signatory: string
  counterparty_contact: string; note: string
  attachments: Attachment[]; vouchers: ContractVoucher[]
}

const CATEGORY_LABEL: Record<string, string> = {
  sales: '销售合同', purchase: '采购合同', service: '服务合同',
  lease: '租赁合同', labor: '劳务合同', loan: '借款合同', other: '其他',
}
const DIRECTION_LABEL: Record<string, string> = {
  income: '收入类(我方提供/收款)', expense: '支出类(我方接受/付款)',
}
const DIRECTION_COLOR: Record<string, string> = { income: 'green', expense: 'volcano' }
const STATUS_LABEL: Record<string, string> = {
  draft: '草稿', active: '履行中', completed: '已完成', terminated: '已终止',
}
const STATUS_COLOR: Record<string, string> = {
  draft: 'default', active: 'processing', completed: 'success', terminated: 'error',
}
const D = (v: string | null | undefined) => (v ? dayjs(v) : undefined)
const COMMON_RATES = [13, 9, 6, 5, 3, 1, 0]  // 常见增值税率(%)

// 含税总额价税分离:税金 = 金额 − 金额/(1+税率)
const splitTax = (amount: number, rate: number) => {
  const amt = Number(amount) || 0
  const r = Number(rate) || 0
  const tax = r > 0 ? amt - amt / (1 + r / 100) : 0
  return { tax: Math.round(tax * 100) / 100, net: Math.round((amt - tax) * 100) / 100 }
}

export default function Contracts() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<Contract[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Contract | null>(null)
  const [draftId, setDraftId] = useState<number | null>(null)
  const [existingAtt, setExistingAtt] = useState<Attachment[]>([])
  const [form] = Form.useForm()
  const watchAmount = Form.useWatch('amount', form)
  const watchRate = Form.useWatch('tax_rate', form)
  const taxCalc = splitTax(watchAmount, watchRate)
  const [detail, setDetail] = useState<Contract | null>(null)
  const [vouchers, setVouchers] = useState<VoucherListItem[]>([])
  const [linkVoucherId, setLinkVoucherId] = useState<number>()

  const load = useCallback(() => {
    setLoading(true)
    const params = statusFilter === 'all' ? {} : { status: statusFilter }
    http.get<Contract[]>('/contracts', { params })
      .then((r) => setRows(r.data)).finally(() => setLoading(false))
  }, [statusFilter])
  useEffect(() => { load() }, [load])
  // 凭证支持远程搜索(按凭证号/摘要),避免一次性拉全量(后端 page_size 上限 100)
  const loadVouchers = useCallback((keyword?: string) => {
    const params: Record<string, unknown> = { page_size: 50 }
    if (keyword) params.keyword = keyword
    http.get<{ items: VoucherListItem[] }>('/vouchers', { params })
      .then((r) => setVouchers(r.data.items || []))
  }, [])
  useEffect(() => {
    http.get<Customer[]>('/customers', { params: { active_only: true } }).then((r) => setCustomers(r.data))
    loadVouchers()
  }, [loadVouchers])

  const openEdit = (c: Contract | null) => {
    setEditing(c); setDraftId(null); form.resetFields()
    setExistingAtt(c ? c.attachments : [])
    if (c) form.setFieldsValue({
      ...c, amount: Number(c.amount), tax_rate: Number(c.tax_rate),
      // 合并字段:优先显示往来单位名称,否则显示手填名称
      party_name: c.customer_name || c.party_name, customer_id: c.customer_id ?? null,
      sign_date: D(c.sign_date), start_date: D(c.start_date), end_date: D(c.end_date),
    })
    else form.setFieldsValue({ category: 'other', direction: 'income', status: 'active', amount: 0, tax_rate: 0 })
    setOpen(true)
  }
  const _payload = (v: Record<string, unknown>) => {
    const hasCust = Boolean(v.customer_id)
    return {
      ...v,
      customer_id: hasCust ? v.customer_id : null,
      // 选中往来单位则以其为准清空手填名;否则保留手填名称
      party_name: hasCust ? '' : ((v.party_name as string) || ''),
      sign_date: v.sign_date ? (v.sign_date as dayjs.Dayjs).format('YYYY-MM-DD') : null,
      start_date: v.start_date ? (v.start_date as dayjs.Dayjs).format('YYYY-MM-DD') : null,
      end_date: v.end_date ? (v.end_date as dayjs.Dayjs).format('YYYY-MM-DD') : null,
    }
  }
  const ensureOwner = async (): Promise<number | null> => {
    if (editing) return editing.id
    if (draftId) return draftId
    try {
      const v = await form.validateFields()
      const r = await http.post<Contract>('/contracts', _payload(v))
      setDraftId(r.data.id); load(); return r.data.id
    } catch { return null }
  }
  const save = async () => {
    const v = await form.validateFields()
    const id = editing?.id ?? draftId
    if (id) await http.put(`/contracts/${id}`, _payload(v))
    else await http.post('/contracts', _payload(v))
    message.success('已保存'); setOpen(false); load()
  }
  const remove = (id: number) =>
    http.delete(`/contracts/${id}`).then(() => { message.success('已删除'); load() })

  const openDetail = (id: number) =>
    http.get<Contract>(`/contracts/${id}`).then((r) => { setDetail(r.data); setLinkVoucherId(undefined) })
  // 从凭证页「关联合同」跳转过来时,自动打开对应合同详情
  const [searchParams] = useSearchParams()
  useEffect(() => {
    const focus = searchParams.get('focus')
    if (focus) openDetail(Number(focus))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])
  const linkVoucher = async () => {
    if (!detail || !linkVoucherId) return
    await http.post(`/contracts/${detail.id}/link`, null, { params: { voucher_id: linkVoucherId } })
    message.success('已关联凭证'); openDetail(detail.id)
  }
  const unlink = async (linkId: number) => {
    await http.delete(`/contracts/link/${linkId}`)
    if (detail) openDetail(detail.id)
  }

  const columns = [
    { title: '合同编号', dataIndex: 'contract_no', width: 140,
      render: (v: string, r: Contract) => <a onClick={() => openDetail(r.id)}>{v}</a> },
    { title: '合同名称', dataIndex: 'name', ellipsis: true },
    { title: '收支', dataIndex: 'direction', width: 80,
      render: (v: string) => <Tag color={DIRECTION_COLOR[v]}>{v === 'expense' ? '支出' : '收入'}</Tag> },
    { title: '类型', dataIndex: 'category', width: 100, render: (v: string) => <Tag>{CATEGORY_LABEL[v] || v}</Tag> },
    { title: '对方单位', dataIndex: 'customer_name', width: 140, render: (v: string) => v || '-' },
    { title: '含税金额', dataIndex: 'amount', width: 120, align: 'right' as const, render: (v: number | string) => formatYuan(v) },
    { title: '税金', dataIndex: 'tax_amount', width: 110, align: 'right' as const,
      render: (v: number | string, r: Contract) => (Number(r.tax_rate) > 0 ? `${formatYuan(v)} (${Number(r.tax_rate)}%)` : '-') },
    { title: '状态', dataIndex: 'status', width: 90, render: (s: string) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s] || s}</Tag> },
    { title: '附件', dataIndex: 'attachments', width: 60, align: 'center' as const, render: (a: Attachment[]) => a.length || '-' },
    {
      title: '操作', width: 150, render: (_: unknown, r: Contract) => (
        <Space>
          <a onClick={() => openEdit(r)}>编辑</a>
          <a onClick={() => openDetail(r.id)}>详情</a>
          <Popconfirm title="删除该合同?" onConfirm={() => remove(r.id)}>
            <a style={{ color: '#cf1322' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="content-card">
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <Segmented value={statusFilter} onChange={(v) => setStatusFilter(v as string)}
          options={[{ label: '全部', value: 'all' },
            ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))]} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit(null)}>新建合同</Button>
      </Space>
      <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={rows}
        pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 份` }} />

      {/* 新建/编辑 */}
      <Modal title={editing ? '编辑合同' : '新建合同'} open={open} onOk={save}
        onCancel={() => setOpen(false)} okText="保存" width={720}>
        <Form form={form} layout="vertical">
          <Space wrap>
            <Form.Item name="contract_no" label="合同编号" rules={[{ required: true }]}>
              <Input placeholder="如 HT-2026-001" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="name" label="合同名称" rules={[{ required: true }]} style={{ flex: 1, minWidth: 260 }}>
              <Input placeholder="合同名称" />
            </Form.Item>
          </Space>
          <Space wrap>
            <Form.Item name="direction" label="收支方向">
              <Select style={{ width: 180 }}
                options={Object.entries(DIRECTION_LABEL).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="category" label="合同类型">
              <Select style={{ width: 140 }} options={Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select style={{ width: 120 }} options={Object.entries(STATUS_LABEL).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="amount" label="合同金额(含税,元)">
              <InputNumber min={0} precision={2} style={{ width: 160 }} />
            </Form.Item>
          </Space>
          <Form.Item label="税率 / 税金(价税分离,自动计算)">
            <Space wrap>
              <Form.Item name="tax_rate" noStyle>
                <InputNumber min={0} max={100} precision={2} addonAfter="%" style={{ width: 130 }} />
              </Form.Item>
              <Segmented size="small" value={watchRate}
                options={COMMON_RATES.map((r) => ({ label: `${r}%`, value: r }))}
                onChange={(val) => form.setFieldValue('tax_rate', val)} />
              <span style={{ color: '#666' }}>
                税金 <b style={{ color: '#cf1322' }}>{formatYuan(taxCalc.tax)}</b> · 不含税 {formatYuan(taxCalc.net)}
              </span>
            </Space>
          </Form.Item>
          <Form.Item name="party_name" label="对方单位(可搜索选择往来单位,或直接输入名称)">
            <AutoComplete allowClear style={{ width: 460 }} placeholder="输入或选择对方单位"
              options={customers.map((c) => ({
                value: c.short_name || c.name,
                label: `[${PARTY_LABEL[c.party_type] || '往来'}] ${c.short_name || c.name}`,
              }))}
              filterOption={(input, opt) => String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())}
              onChange={(val) => {
                const m = customers.find((c) => (c.short_name || c.name) === val)
                form.setFieldValue('customer_id', m ? m.id : null)
              }} />
          </Form.Item>
          {/* 隐藏承载:选中已有往来单位时记录其 id,否则为空(按手填名称保存) */}
          <Form.Item name="customer_id" hidden><Input /></Form.Item>
          <Space wrap>
            <Form.Item name="sign_date" label="签订日期"><DatePicker /></Form.Item>
            <Form.Item name="start_date" label="开始日期"><DatePicker /></Form.Item>
            <Form.Item name="end_date" label="结束日期"><DatePicker /></Form.Item>
            <Form.Item name="our_signatory" label="我方签署人"><Input style={{ width: 140 }} /></Form.Item>
          </Space>
          <Form.Item name="counterparty_contact" label="对方联系人/电话"><Input /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea rows={2} /></Form.Item>
          <Divider orientation="left" plain>合同附件(扫描件等)</Divider>
          <AttachmentEditor ownerId={editing?.id ?? draftId} basePath="/contracts"
            ensureOwner={ensureOwner} existing={existingAtt} onChange={setExistingAtt} defaultKind="contract" />
        </Form>
      </Modal>

      {/* 详情 + 关联凭证 */}
      <Modal title={detail?.contract_no} open={Boolean(detail)} footer={null} onCancel={() => setDetail(null)} width={720}>
        {detail && (
          <>
            <p><b>{detail.name}</b> <Tag color={DIRECTION_COLOR[detail.direction]}>{DIRECTION_LABEL[detail.direction] || '收入类'}</Tag>
              <Tag>{CATEGORY_LABEL[detail.category]}</Tag>
              <Tag color={STATUS_COLOR[detail.status]}>{STATUS_LABEL[detail.status]}</Tag></p>
            <p>对方:{detail.customer_name || detail.party_name || '-'} · 含税金额 {formatYuan(detail.amount)}
              {Number(detail.tax_rate) > 0 && <> · 税率 {Number(detail.tax_rate)}% · 税金 {formatYuan(detail.tax_amount)}
                · 不含税 {formatYuan(Number(detail.amount) - Number(detail.tax_amount))}</>}</p>
            <p>签订 {detail.sign_date || '-'} · 期限 {detail.start_date || '-'} ~ {detail.end_date || '-'}</p>
            {detail.note && <p style={{ color: '#666' }}>备注:{detail.note}</p>}
            <Divider orientation="left" plain>合同附件</Divider>
            <AttachmentEditor ownerId={detail.id} basePath="/contracts" existing={detail.attachments}
              onChange={(atts) => setDetail({ ...detail, attachments: atts })} defaultKind="contract" />
            <Divider orientation="left" plain>关联记账凭证</Divider>
            <Space style={{ marginBottom: 8 }} wrap>
              <Select showSearch placeholder="输入凭证号/摘要搜索" style={{ width: 320 }}
                filterOption={false} onSearch={loadVouchers}
                value={linkVoucherId} onChange={setLinkVoucherId}
                options={vouchers.map((v) => ({ value: v.id, label: `${v.voucher_no} · ${v.voucher_date} · ${v.note || ''}` }))} />
              <Button onClick={linkVoucher} disabled={!linkVoucherId}>关联</Button>
            </Space>
            <Table rowKey="id" size="small" pagination={false} dataSource={detail.vouchers}
              locale={{ emptyText: '暂无关联凭证' }}
              columns={[
                { title: '凭证号', dataIndex: 'voucher_no', render: (v: string, r: ContractVoucher) => <a onClick={() => navigate(`/vouchers/${r.voucher_id}`)}>{v}</a> },
                { title: '日期', dataIndex: 'voucher_date', width: 120 },
                { title: '金额', dataIndex: 'total_debit', width: 120, align: 'right' as const, render: (v: number | string) => formatYuan(v) },
                { title: '操作', width: 60, render: (_: unknown, r: ContractVoucher) => <a style={{ color: '#cf1322' }} onClick={() => unlink(r.id)}>移除</a> },
              ]} />
          </>
        )}
      </Modal>
    </div>
  )
}
