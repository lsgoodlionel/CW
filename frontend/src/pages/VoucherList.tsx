import { useEffect, useState, useCallback } from 'react'
import {
  Table, Button, Space, DatePicker, Input, Popconfirm, Tag, message,
} from 'antd'
import { PlusOutlined, PaperClipOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import type { Dayjs } from 'dayjs'
import { http, VoucherListItem } from '../api'

const { RangePicker } = DatePicker

export default function VoucherList() {
  const navigate = useNavigate()
  const [items, setItems] = useState<VoucherListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null)
  const [keyword, setKeyword] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    const params: Record<string, string | number> = { page, page_size: 20 }
    if (range) {
      params.start = range[0].format('YYYY-MM-DD')
      params.end = range[1].format('YYYY-MM-DD')
    }
    if (keyword) params.keyword = keyword
    http.get('/vouchers', { params })
      .then((r) => { setItems(r.data.items); setTotal(r.data.total) })
      .finally(() => setLoading(false))
  }, [page, range, keyword])

  useEffect(() => { load() }, [load])

  const remove = (id: number) =>
    http.delete(`/vouchers/${id}`).then(() => { message.success('已删除'); load() })

  const columns = [
    { title: '凭证号', dataIndex: 'voucher_no', width: 150 },
    { title: '日期', dataIndex: 'voucher_date', width: 120 },
    { title: '摘要', dataIndex: 'note', ellipsis: true },
    {
      title: '借/贷合计', dataIndex: 'total_debit', width: 140,
      render: (v: number) => `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
    },
    { title: '分录', dataIndex: 'entry_count', width: 70 },
    {
      title: '附件', dataIndex: 'attachment_count', width: 80,
      render: (n: number) => n > 0
        ? <Tag color="blue"><PaperClipOutlined /> {n}</Tag> : '-',
    },
    {
      title: '操作', width: 140,
      render: (_: unknown, r: VoucherListItem) => (
        <Space>
          <a onClick={() => navigate(`/vouchers/${r.id}`)}>编辑</a>
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
          onSearch={(v) => { setPage(1); setKeyword(v) }} style={{ width: 220 }} />
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
