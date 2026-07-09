import { useEffect, useState, useMemo } from 'react'
import { Card, Select, Segmented, Button, Space, Table, Tag, Empty, Alert } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { http, Account } from '../api'

type ReportType = 'month' | 'quarter' | 'year'

interface LedgerRow { cells: (string | number)[]; is_summary?: boolean }
interface Group { title: string; opening: number; closing: number; rows: LedgerRow[] }
interface Ledger {
  ledger_type: string; title: string; period_label: string
  columns: string[]; groups: Group[]; note?: string
}

const LEDGER_TYPES: Record<string, string> = {
  general: '总分类账',
  detail_three: '金额三栏式明细账',
  cash_journal: '现金日记账',
  bank_journal: '银行存款日记账',
  detail_multi: '金额多栏式明细账',
  qty_amount: '数量金额式明细账',
}

const fmt = (v: string | number) =>
  typeof v === 'number' ? v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : v

export default function Ledgers() {
  const now = dayjs()
  const [ledgerType, setLedgerType] = useState('general')
  const [reportType, setReportType] = useState<ReportType>('month')
  const [year, setYear] = useState(now.year())
  const [month, setMonth] = useState(now.month() + 1)
  const [quarter, setQuarter] = useState(Math.floor(now.month() / 3) + 1)
  const [accountCode, setAccountCode] = useState<string | undefined>()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [data, setData] = useState<Ledger | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    http.get<Account[]>('/accounts').then((r) => setAccounts(r.data))
  }, [])

  const params = useMemo(() => {
    const p: Record<string, string | number> = { ledger_type: ledgerType, report_type: reportType, year }
    if (reportType === 'month') p.month = month
    if (reportType === 'quarter') p.quarter = quarter
    if (accountCode) p.account_code = accountCode
    return p
  }, [ledgerType, reportType, year, month, quarter, accountCode])

  useEffect(() => {
    setLoading(true)
    http.get<Ledger>('/ledgers', { params })
      .then((r) => setData(r.data))
      .finally(() => setLoading(false))
  }, [params])

  const exportExcel = (all: boolean) => {
    const p = { ...params, ledger_type: all ? 'all' : ledgerType }
    const qs = new URLSearchParams(p as Record<string, string>).toString()
    window.open(`/api/ledgers/export-excel?${qs}`, '_blank')
  }

  const years = Array.from({ length: 8 }, (_, i) => now.year() - i)

  return (
    <Card>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={ledgerType} style={{ width: 190 }} onChange={setLedgerType}
          options={Object.entries(LEDGER_TYPES).map(([value, label]) => ({ value, label }))} />
        <Segmented value={reportType} onChange={(v) => setReportType(v as ReportType)}
          options={[{ label: '月', value: 'month' }, { label: '季', value: 'quarter' }, { label: '年', value: 'year' }]} />
        <Select value={year} style={{ width: 95 }} onChange={setYear}
          options={years.map((y) => ({ value: y, label: `${y}年` }))} />
        {reportType === 'month' && (
          <Select value={month} style={{ width: 80 }} onChange={setMonth}
            options={Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}月` }))} />
        )}
        {reportType === 'quarter' && (
          <Select value={quarter} style={{ width: 100 }} onChange={setQuarter}
            options={[1, 2, 3, 4].map((q) => ({ value: q, label: `第${q}季度` }))} />
        )}
        <Select allowClear placeholder="全部科目" style={{ width: 200 }} value={accountCode}
          showSearch optionFilterProp="label" onChange={setAccountCode}
          options={accounts.map((a) => ({ value: a.code, label: `${a.code} ${a.name}` }))} />
        <Button type="primary" icon={<DownloadOutlined />} onClick={() => exportExcel(false)}>
          导出本账簿
        </Button>
        <Button icon={<DownloadOutlined />} onClick={() => exportExcel(true)}>
          导出全套账簿
        </Button>
      </Space>

      {data?.note && <Alert type="info" showIcon style={{ marginBottom: 12 }} message={data.note} />}
      {data && <Tag color="blue" style={{ marginBottom: 12 }}>{data.title} · {data.period_label}</Tag>}

      {data && data.groups.length === 0 && <Empty description="本期无账簿数据" />}

      {data?.groups.map((g, gi) => (
        <div key={gi} style={{ marginBottom: 24 }}>
          <div style={{ fontWeight: 600, marginBottom: 6, color: '#1f4e79' }}>
            科目:{g.title}
          </div>
          <Table
            rowKey={(_, i) => String(i)} loading={loading} size="small" pagination={false} bordered
            dataSource={g.rows}
            columns={data.columns.map((col, ci) => ({
              title: col,
              key: ci,
              align: ci >= 3 ? ('right' as const) : ci === 2 ? ('left' as const) : ('center' as const),
              render: (_: unknown, row: LedgerRow) => (
                <span style={row.is_summary ? { fontWeight: 600 } : undefined}>{fmt(row.cells[ci])}</span>
              ),
            }))}
            rowClassName={(row) => (row.is_summary ? 'ledger-sum-row' : '')}
          />
        </div>
      ))}
    </Card>
  )
}
