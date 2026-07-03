import { useEffect, useState, useMemo } from 'react'
import { Card, Tabs, Table, Tag, Segmented, Select, Button, Space } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { http } from '../api'

const yuan = (n: number | null) =>
  n === null || n === undefined
    ? ''
    : n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

type ReportType = 'month' | 'quarter' | 'year'

interface StmtRow { label: string; line: number | null; style: string; col1: number | null; col2: number | null }
interface Statement { rows: StmtRow[]; col1_label: string; col2_label: string }
interface BsRow { label: string; line: number | null; style: string; end: number | null; begin: number | null }
interface BalanceSheet {
  assets: BsRow[]; rights: BsRow[]
  asset_total: number; right_total: number; balanced: boolean
}
interface Official {
  period: { label: string }
  balance_sheet: BalanceSheet
  income: Statement
  cashflow: Statement
}

interface TrialRow { code: string; name: string; debit: number; credit: number; balance: number }
interface Trial { rows: TrialRow[]; total_debit: number; total_credit: number; balanced: boolean }

export default function Reports() {
  const now = dayjs()
  const [reportType, setReportType] = useState<ReportType>('month')
  const [year, setYear] = useState(now.year())
  const [month, setMonth] = useState(now.month() + 1)
  const [quarter, setQuarter] = useState(Math.floor(now.month() / 3) + 1)
  const [data, setData] = useState<Official | null>(null)
  const [trial, setTrial] = useState<Trial | null>(null)

  const params = useMemo(() => {
    const p: Record<string, string | number> = { report_type: reportType, year }
    if (reportType === 'month') p.month = month
    if (reportType === 'quarter') p.quarter = quarter
    return p
  }, [reportType, year, month, quarter])

  useEffect(() => {
    http.get<Official>('/reports/official', { params }).then((r) => setData(r.data))
  }, [params])

  useEffect(() => {
    // 科目汇总表:与官方报表相同的本期时间口径
    const s =
      reportType === 'year' ? `${year}-01-01`
        : reportType === 'quarter' ? `${year}-${String((quarter - 1) * 3 + 1).padStart(2, '0')}-01`
          : `${year}-${String(month).padStart(2, '0')}-01`
    const eMonth = reportType === 'year' ? 12 : reportType === 'quarter' ? quarter * 3 : month
    const e = dayjs(`${year}-${String(eMonth).padStart(2, '0')}-01`).endOf('month').format('YYYY-MM-DD')
    http.get<Trial>('/reports/trial-balance', { params: { start: s, end: e } }).then((r) => setTrial(r.data))
  }, [reportType, year, month, quarter])

  const exportExcel = () => {
    const qs = new URLSearchParams(params as Record<string, string>).toString()
    window.open(`/api/reports/export-excel?${qs}`, '_blank')
  }

  const years = Array.from({ length: 8 }, (_, i) => now.year() - i)

  return (
    <Card>
      <Space wrap style={{ marginBottom: 16 }}>
        <Segmented value={reportType} onChange={(v) => setReportType(v as ReportType)}
          options={[{ label: '月报', value: 'month' }, { label: '季报', value: 'quarter' }, { label: '年报', value: 'year' }]} />
        <Select value={year} style={{ width: 100 }} onChange={setYear}
          options={years.map((y) => ({ value: y, label: `${y}年` }))} />
        {reportType === 'month' && (
          <Select value={month} style={{ width: 90 }} onChange={setMonth}
            options={Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}月` }))} />
        )}
        {reportType === 'quarter' && (
          <Select value={quarter} style={{ width: 110 }} onChange={setQuarter}
            options={[1, 2, 3, 4].map((q) => ({ value: q, label: `第${q}季度` }))} />
        )}
        <Button type="primary" icon={<DownloadOutlined />} onClick={exportExcel}>
          一键导出 Excel
        </Button>
        {data && <Tag color="blue">{data.period.label}</Tag>}
      </Space>

      {data && (
        <Tabs
          items={[
            { key: 'bs', label: '资产负债表', children: <BalanceSheetView data={data.balance_sheet} /> },
            { key: 'is', label: '利润表', children: <StatementView data={data.income} /> },
            { key: 'cf', label: '现金流量表', children: <StatementView data={data.cashflow} /> },
            { key: 'tb', label: '科目汇总表', children: <TrialView data={trial} /> },
          ]}
        />
      )}
    </Card>
  )
}

const styleFont = (s: string) =>
  ['total', 'grand', 'header', 'head'].includes(s) ? { fontWeight: 600 as const } : {}

function BalanceSheetView({ data }: { data: BalanceSheet }) {
  const n = Math.max(data.assets.length, data.rights.length)
  const merged = Array.from({ length: n }, (_, i) => ({
    key: i, a: data.assets[i], r: data.rights[i],
  }))
  const cell = (row: BsRow | undefined, field: 'end' | 'begin') =>
    row && row[field] !== null ? yuan(row[field]) : ''
  return (
    <>
      <Tag color={data.balanced ? 'green' : 'red'} style={{ marginBottom: 12 }}>
        {data.balanced ? `资产 = 负债 + 所有者权益 ✓（${yuan(data.asset_total)} 元）` : '未平衡 ✗'}
      </Tag>
      <Table rowKey="key" size="small" pagination={false} dataSource={merged} bordered
        columns={[
          { title: '资产', dataIndex: ['a', 'label'], render: (_, r) => <span style={styleFont(r.a?.style || '')}>{r.a?.label}</span> },
          { title: '行次', width: 46, align: 'center', render: (_, r) => r.a?.line ?? '' },
          { title: '期末余额', width: 120, align: 'right', render: (_, r) => cell(r.a, 'end') },
          { title: '年初余额', width: 120, align: 'right', render: (_, r) => cell(r.a, 'begin') },
          { title: '负债和所有者权益', dataIndex: ['r', 'label'], render: (_, r) => <span style={styleFont(r.r?.style || '')}>{r.r?.label}</span> },
          { title: '行次', width: 46, align: 'center', render: (_, r) => r.r?.line ?? '' },
          { title: '期末余额', width: 120, align: 'right', render: (_, r) => cell(r.r, 'end') },
          { title: '年初余额', width: 120, align: 'right', render: (_, r) => cell(r.r, 'begin') },
        ]} />
    </>
  )
}

function StatementView({ data }: { data: Statement }) {
  return (
    <Table rowKey="line" size="small" pagination={false} dataSource={data.rows} bordered
      rowClassName={(r) => (r.line === null ? 'report-header-row' : '')}
      columns={[
        { title: '项目', dataIndex: 'label', render: (v, r) => <span style={styleFont(r.style)}>{v}</span> },
        { title: '行次', dataIndex: 'line', width: 56, align: 'center', render: (v) => v ?? '' },
        { title: data.col1_label, dataIndex: 'col1', width: 150, align: 'right', render: (v, r) => <span style={styleFont(r.style)}>{yuan(v)}</span> },
        { title: data.col2_label, dataIndex: 'col2', width: 150, align: 'right', render: (v, r) => <span style={styleFont(r.style)}>{yuan(v)}</span> },
      ]} />
  )
}

function TrialView({ data }: { data: Trial | null }) {
  if (!data) return null
  return (
    <>
      <Tag color={data.balanced ? 'green' : 'red'} style={{ marginBottom: 12 }}>
        {data.balanced ? `试算平衡 ✓ 借贷各 ${yuan(data.total_debit)}` : '试算不平衡 ✗'}
      </Tag>
      <Table rowKey="code" size="small" pagination={false} dataSource={data.rows} bordered
        columns={[
          { title: '科目', render: (_, r) => `${r.code} ${r.name}` },
          { title: '借方发生额', dataIndex: 'debit', align: 'right', render: yuan },
          { title: '贷方发生额', dataIndex: 'credit', align: 'right', render: yuan },
          { title: '余额', dataIndex: 'balance', align: 'right', render: yuan },
        ]} />
    </>
  )
}
