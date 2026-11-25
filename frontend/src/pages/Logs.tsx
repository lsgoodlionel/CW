import { useEffect, useState, useMemo } from 'react'
import { Card, Table, Tag, Select, Segmented, Button, Space, DatePicker, Descriptions, Typography } from 'antd'
import { FilePdfOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { http, withToken, LogItem } from '../api'

type ReportType = 'month' | 'quarter' | 'year'

const TYPE_COLOR: Record<string, string> = {
  voucher: 'blue', account: 'geekblue', attachment: 'cyan', company: 'purple',
  customer: 'gold', personnel: 'magenta',
  report: 'green', ledger: 'lime', data: 'volcano', other: 'default',
}
const FIELD_LABEL: Record<string, string> = {
  voucher_no: '凭证号', voucher_date: '凭证日期', note: '备注', status: '状态',
  amount: '金额', total_debit: '借方合计', total_credit: '贷方合计',
  summary: '摘要', account_id: '会计科目', sub_account: '明细科目',
  debit: '借方金额', credit: '贷方金额', kind: '附件类型',
  name: '名称', category: '类别', reason: '事由', period: '所属期',
  tax_type: '税种', tax_amount: '应纳税额', paid_amount: '已缴税额',
  customer_id: '往来单位', contract_id: '关联合同',
}
const fieldLabel = (key: string) => FIELD_LABEL[key] || `字段 ${key}`

function DetailView({ detail }: { detail: string }) {
  let obj: unknown
  try { obj = JSON.parse(detail) } catch { obj = detail }
  const renderValue = (value: unknown): React.ReactNode => {
    if (value === null || value === undefined || value === '') return '—'
    if (typeof value === 'boolean') return value ? '是' : '否'
    if (Array.isArray(value)) return value.map((item, index) =>
      <div key={index} style={{ marginBottom: 4 }}>{renderValue(item)}</div>)
    if (typeof value === 'object') return <Descriptions size="small" bordered column={1}
      items={Object.entries(value as Record<string, unknown>).map(([key, item]) => ({
        key, label: fieldLabel(key), children: renderValue(item),
      }))} />
    return <Typography.Text style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{String(value)}</Typography.Text>
  }
  if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
    const sections = obj as Record<string, unknown>
    const changes = sections['变更'] as Record<string, { 改前: unknown; 改后: unknown }> | undefined
    if (changes && typeof changes === 'object') {
      return <div style={{ padding: 12, background: '#fafafa', borderRadius: 6 }}>
        <Typography.Text strong>修改内容</Typography.Text>
        <Table rowKey="key" size="small" pagination={false} style={{ marginTop: 8 }}
          dataSource={Object.entries(changes).map(([key, values]) => ({ key, ...values }))}
          columns={[{ title: '字段', dataIndex: 'key', width: 180, render: fieldLabel },
            { title: '修改前', dataIndex: '改前', render: renderValue },
            { title: '修改后', dataIndex: '改后', render: renderValue }]} />
      </div>
    }
    if (sections['提交内容'] || sections['删除前']) {
      return <div style={{ padding: 12, background: '#fafafa', borderRadius: 6 }}>
        <Typography.Text strong>{sections['删除前'] ? '删除前内容' : '提交内容'}</Typography.Text>
        <div style={{ marginTop: 8 }}>{renderValue(sections['删除前'] || sections['提交内容'])}</div>
      </div>
    }
  }
  return <div style={{ padding: 12, background: '#fafafa', borderRadius: 6 }}>{renderValue(obj)}</div>
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
    window.open(withToken(`/api/logs/export-pdf?${qs}`), '_blank')
  }

  const columns = [
    { title: '时间', dataIndex: 'created_at', width: 170,
      render: (v: string) => v.slice(0, 19).replace('T', ' ') },
    { title: '类型', dataIndex: 'action_type', width: 90,
      render: (v: string, r: LogItem) => <Tag color={TYPE_COLOR[v] || 'default'}>{r.action_type_label}</Tag> },
    { title: '操作', dataIndex: 'action', width: 170 },
    { title: '操作人', dataIndex: 'operator', width: 90, render: (v: string) => v || '-' },
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
        <DatePicker picker="year" value={dayjs().year(year)} allowClear={false}
          onChange={(v) => { if (v) { setPage(1); setYear(v.year()) } }} />
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
        expandable={{
          expandedRowRender: (r) => <DetailView detail={r.detail} />,
          rowExpandable: (r) => Boolean(r.detail),
        }}
        pagination={{ current: page, total, pageSize: 30, showTotal: (t) => `共 ${t} 条`, onChange: setPage }} />
    </Card>
  )
}
