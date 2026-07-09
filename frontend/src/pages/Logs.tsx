import { useEffect, useState, useMemo } from 'react'
import { Card, Table, Tag, Select, Segmented, Button, Space } from 'antd'
import { FilePdfOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { http } from '../api'

type ReportType = 'month' | 'quarter' | 'year'

interface LogItem {
  id: number
  created_at: string
  action_type: string
  action_type_label: string
  action: string
  summary: string
  status_code: number
  duration_ms: number
  ip: string
}

const TYPE_COLOR: Record<string, string> = {
  voucher: 'blue', account: 'geekblue', attachment: 'cyan', company: 'purple',
  report: 'green', ledger: 'lime', data: 'volcano', other: 'default',
}

export default function Logs() {
  const now = dayjs()
  const [types, setTypes] = useState<Record<string, string>>({})
  const [actionType, setActionType] = useState<string | undefined>()
  const [reportType, setReportType] = useState<ReportType>('month')
  const [year, setYear] = useState(now.year())
  const [month, setMonth] = useState(now.month() + 1)
  const [quarter, setQuarter] = useState(Math.floor(now.month() / 3) + 1)
  const [items, setItems] = useState<LogItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  const params = useMemo(() => {
    const p: Record<string, string | number> = { year, page, page_size: 30 }
    if (actionType) p.action_type = actionType
    if (reportType === 'month') p.month = month
    if (reportType === 'quarter') p.quarter = quarter
    return p
  }, [actionType, reportType, year, month, quarter, page])

  useEffect(() => {
    setLoading(true)
    http.get('/logs', { params })
      .then((r) => { setItems(r.data.items); setTotal(r.data.total); setTypes(r.data.types) })
      .finally(() => setLoading(false))
  }, [params])

  const exportPdf = () => {
    const p: Record<string, string | number> = { year }
    if (actionType) p.action_type = actionType
    if (reportType === 'month') p.month = month
    if (reportType === 'quarter') p.quarter = quarter
    const qs = new URLSearchParams(p as Record<string, string>).toString()
    window.open(`/api/logs/export-pdf?${qs}`, '_blank')
  }

  const years = Array.from({ length: 8 }, (_, i) => now.year() - i)

  const columns = [
    { title: '时间', dataIndex: 'created_at', width: 170,
      render: (v: string) => v.slice(0, 19).replace('T', ' ') },
    { title: '类型', dataIndex: 'action_type', width: 90,
      render: (v: string, r: LogItem) => <Tag color={TYPE_COLOR[v] || 'default'}>{r.action_type_label}</Tag> },
    { title: '操作', dataIndex: 'action', width: 180 },
    { title: '摘要', dataIndex: 'summary', ellipsis: true, render: (v: string) => v || '-' },
    { title: '状态', dataIndex: 'status_code', width: 70,
      render: (v: number) => <Tag color={v < 400 ? 'green' : 'red'}>{v}</Tag> },
    { title: '耗时', dataIndex: 'duration_ms', width: 80, render: (v: number) => `${v}ms` },
    { title: '来源IP', dataIndex: 'ip', width: 120, render: (v: string) => v || '-' },
  ]

  return (
    <Card>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select allowClear placeholder="全部类型" style={{ width: 130 }} value={actionType}
          onChange={(v) => { setPage(1); setActionType(v) }}
          options={Object.entries(types).map(([value, label]) => ({ value, label }))} />
        <Segmented value={reportType} onChange={(v) => { setPage(1); setReportType(v as ReportType) }}
          options={[{ label: '月', value: 'month' }, { label: '季', value: 'quarter' }, { label: '年', value: 'year' }]} />
        <Select value={year} style={{ width: 95 }} onChange={(v) => { setPage(1); setYear(v) }}
          options={years.map((y) => ({ value: y, label: `${y}年` }))} />
        {reportType === 'month' && (
          <Select value={month} style={{ width: 80 }} onChange={(v) => { setPage(1); setMonth(v) }}
            options={Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}月` }))} />
        )}
        {reportType === 'quarter' && (
          <Select value={quarter} style={{ width: 100 }} onChange={(v) => { setPage(1); setQuarter(v) }}
            options={[1, 2, 3, 4].map((q) => ({ value: q, label: `第${q}季度` }))} />
        )}
        <Button type="primary" icon={<FilePdfOutlined />} onClick={exportPdf}>导出 PDF</Button>
      </Space>

      <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={items}
        pagination={{ current: page, total, pageSize: 30, showTotal: (t) => `共 ${t} 条`, onChange: setPage }} />
    </Card>
  )
}
