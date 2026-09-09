import { useEffect, useState, useCallback } from 'react'
import {
  Table, Button, Space, DatePicker, Input, Popconfirm, Tag, message, Select,
} from 'antd'
import { PlusOutlined, PaperClipOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import type { Dayjs } from 'dayjs'
import { http, VoucherListItem, Customer, AccountTreeNode, formatYuan } from '../api'

const { RangePicker } = DatePicker

export default function VoucherList() {
  const navigate = useNavigate()
  const [items, setItems] = useState<VoucherListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [keyword, setKeyword] = useState('')
  const [customerId, setCustomerId] = useState<number>()
  const [accountId, setAccountId] = useState<number>()
  const [flow, setFlow] = useState<string>()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [accounts, setAccounts] = useState<AccountTreeNode[]>([])

  useEffect(() => {
    http.get<Customer[]>('/customers', { params: { active_only: true } }).then((r) => setCustomers(r.data))
    http.get<AccountTreeNode[]>('/accounts/tree').then((r) => setAccounts(r.data.filter((a) => a.is_active)))
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    const params: Record<string, string | number> = { page, page_size: 20 }
    if (range) {
      params.start = range[0].format('YYYY-MM-DD')
      params.end = range[1].format('YYYY-MM-DD')
    }
    if (keyword) params.keyword = keyword
    if (customerId) params.customer_id = customerId
    if (accountId) params.account_id = accountId
    if (flow) params.flow = flow
    http.get('/vouchers', { params })
      .then((r) => { setItems(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }, [page, range, keyword, customerId, accountId, flow])

  useEffect(() => { load() }, [load])

  const remove = (id: number) =>
    http.delete(`/vouchers/${id}`).then(() => { message.success('已删除'); load() })
      .catch((e) => message.error(e?.response?.data?.detail || '删除失败'))
  const submitApproval = (id: number) =>
    http.post(`/vouchers/${id}/submit`).then(() => { message.success('已提交审批'); load() })
      .catch((e) => message.error(e?.response?.data?.detail || '提交失败'))

  const columns = [
    { title: '凭证号', dataIndex: 'voucher_no', width: 150 },
    { title: '日期', dataIndex: 'voucher_date', width: 120 },
    { title: '摘要', dataIndex: 'note', ellipsis: true },
    { title: '状态', dataIndex: 'status', width: 84, render: (s: string, r: VoucherListItem) => (
      s === 'posted' ? <Tag color="success">已过账</Tag>
        : (r.workflow_instance_id ? <Tag color="processing">审批中</Tag> : <Tag>草稿</Tag>)) },
    {
      title: '往来单位', dataIndex: 'customer_name', width: 140, ellipsis: true,
      render: (v: string) => v || '-',
    },
    {
      title: '借/贷合计', dataIndex: 'total_debit', width: 130,
      render: (v: string) => formatYuan(v),
    },
    { title: '分录', dataIndex: 'entry_count', width: 60 },
    {
      title: '附件', dataIndex: 'attachment_count', width: 70,
      render: (n: number) => n > 0
        ? <Tag color="blue"><PaperClipOutlined /> {n}</Tag> : '-',
    },
    {
      title: '关联', dataIndex: 'link_count', width: 70,
      render: (n: number) => n > 0 ? <Tag color="purple">{n}</Tag> : '-',
    },
    {
      title: '操作', width: 180,
      render: (_: unknown, r: VoucherListItem) => (
        <Space>
          <a onClick={() => navigate(`/vouchers/${r.id}`)}>编辑</a>
          <a onClick={() => navigate(`/vouchers/new?copyFrom=${r.id}`)}>复制新建</a>
          {r.status === 'draft' && !r.workflow_instance_id && (
            <a onClick={() => submitApproval(r.id)}>提交审批</a>
          )}
          <Popconfirm title="确认删除该凭证?" onConfirm={() => remove(r.id)}>
            <a style={{ color: '#cf1322' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="content-card">
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <RangePicker value={range} onChange={(v) => { setPage(1); setRange(v as [Dayjs, Dayjs]) }} />
        <Input.Search placeholder="搜索凭证号/摘要" allowClear
          onSearch={(v) => { setPage(1); setKeyword(v) }} style={{ width: 200 }} />
        <Select allowClear showSearch placeholder="往来单位" style={{ width: 180 }} optionFilterProp="label"
          value={customerId} onChange={(v) => { setPage(1); setCustomerId(v) }}
          options={customers.map((c) => ({ value: c.id, label: c.short_name || c.name }))} />
        <Select allowClear showSearch placeholder="费用/科目类型" style={{ width: 200 }} optionFilterProp="label"
          value={accountId} onChange={(v) => { setPage(1); setAccountId(v) }}
          options={accounts.map((a) => ({ value: a.id, label: `${a.code} ${a.name}` }))} />
        <Select allowClear placeholder="收支类型" style={{ width: 120 }}
          value={flow} onChange={(v) => { setPage(1); setFlow(v) }}
          options={[{ value: 'income', label: '收入' }, { value: 'expense', label: '支出' }]} />
        <Button type="primary" icon={<PlusOutlined />}
          onClick={() => navigate('/vouchers/new')}>新建凭证</Button>
      </Space>
      <Table
        rowKey="id" loading={loading} columns={columns} dataSource={items}
        pagination={{
          current: page, total, pageSize: 20, showTotal: (t) => `共 ${t} 张`,
          onChange: setPage,
        }}
      />
    </div>
  )
}
