import { useEffect, useState, useMemo } from 'react'
import { Row, Col, Card, Statistic, Spin, Empty, Segmented, DatePicker, Space, Tag, Progress } from 'antd'
import {
  BankOutlined, WalletOutlined, RiseOutlined, FallOutlined,
  AccountBookOutlined, FileTextOutlined, ArrowUpOutlined, ArrowDownOutlined,
} from '@ant-design/icons'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
} from 'recharts'
import dayjs, { Dayjs } from 'dayjs'
import { http } from '../api'

type PeriodType = 'day' | 'month' | 'quarter' | 'year'

interface Dashboard {
  period: { type: string; label: string; start: string; end: string }
  money: { cash: number; bank: number; other: number; total: number }
  receivable: number
  payable: number
  tax_payable: number
  revenue: number
  expense: number
  net_profit: number
  voucher_count: number
  expense_breakdown: { code: string; name: string; amount: number }[]
  trend: { month: string; revenue: number; net_profit: number }[]
}

const yuan = (n: number) =>
  '¥' + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const EXP_COLORS = ['#1f6feb', '#52c41a', '#faad14', '#eb2f96', '#722ed1', '#13c2c2', '#fa541c']

export default function Dashboard() {
  const [periodType, setPeriodType] = useState<PeriodType>('month')
  const [refDate, setRefDate] = useState<Dayjs>(dayjs())
  const [data, setData] = useState<Dashboard | null>(null)
  const [loading, setLoading] = useState(true)

  const params = useMemo(() => ({
    period_type: periodType, ref_date: refDate.format('YYYY-MM-DD'),
  }), [periodType, refDate])

  useEffect(() => {
    setLoading(true)
    http.get<Dashboard>('/reports/dashboard', { params })
      .then((r) => setData(r.data)).finally(() => setLoading(false))
  }, [params])

  if (loading && !data) return <Spin style={{ display: 'block', marginTop: 80 }} />
  if (!data) return null

  const picker = periodType === 'year' ? 'year' : periodType === 'quarter' ? 'quarter'
    : periodType === 'month' ? 'month' : 'date'
  const expTotal = data.expense_breakdown.reduce((s, e) => s + Math.abs(e.amount), 0)

  return (
    <div>
      <Space wrap style={{ marginBottom: 16 }}>
        <Segmented value={periodType} onChange={(v) => setPeriodType(v as PeriodType)}
          options={[
            { label: '日', value: 'day' }, { label: '月', value: 'month' },
            { label: '季', value: 'quarter' }, { label: '年', value: 'year' },
          ]} />
        <DatePicker picker={picker as 'date'} value={refDate} allowClear={false}
          onChange={(v) => v && setRefDate(v)} />
        <Tag color="blue">{data.period.label}</Tag>
      </Space>

      {/* 货币资金余额(期末时点) */}
      <Row gutter={16}>
        <Col xs={12} lg={6}>
          <Card><Statistic title="货币资金合计" value={data.money.total} precision={2}
            valueStyle={{ color: '#1f6feb' }} prefix={<WalletOutlined />} suffix="元" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="银行存款" value={data.money.bank} precision={2}
            prefix={<BankOutlined />} suffix="元" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="库存现金" value={data.money.cash} precision={2}
            prefix={<WalletOutlined />} suffix="元" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="其他货币资金" value={data.money.other} precision={2} suffix="元" /></Card>
        </Col>
      </Row>

      {/* 周期收支利润 + 往来款 */}
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={12} lg={6}>
          <Card><Statistic title={`营业收入(${data.period.label})`} value={data.revenue} precision={2}
            valueStyle={{ color: '#3f8600' }} prefix={<RiseOutlined />} suffix="元" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title={`总支出(${data.period.label})`} value={data.expense} precision={2}
            valueStyle={{ color: '#cf1322' }} prefix={<FallOutlined />} suffix="元" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="净利润" value={data.net_profit} precision={2}
            valueStyle={{ color: data.net_profit >= 0 ? '#3f8600' : '#cf1322' }}
            prefix={<AccountBookOutlined />} suffix="元" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="本期凭证数" value={data.voucher_count}
            prefix={<FileTextOutlined />} /></Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} lg={8}>
          <Card size="small">
            <Statistic title="应收账款" value={data.receivable} precision={2}
              valueStyle={{ color: '#3f8600' }} prefix={<ArrowUpOutlined />} suffix="元" />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small">
            <Statistic title="应付账款" value={data.payable} precision={2}
              valueStyle={{ color: '#cf1322' }} prefix={<ArrowDownOutlined />} suffix="元" />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card size="small">
            <Statistic title="应交税费" value={data.tax_payable} precision={2}
              valueStyle={{ color: '#d48806' }} suffix="元" />
          </Card>
        </Col>
      </Row>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} lg={14}>
          <Card title="近 6 个月收入 / 净利润趋势">
            {data.trend.length === 0 ? <Empty description="暂无数据" /> : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={data.trend}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" /><YAxis />
                  <Tooltip formatter={(v: number) => yuan(v)} /><Legend />
                  <Bar dataKey="revenue" name="营业收入" fill="#1f6feb" />
                  <Bar dataKey="net_profit" name="净利润" fill="#52c41a" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title={`支出构成(${data.period.label})`}>
            {data.expense_breakdown.length === 0 ? <Empty description="本期无支出" /> : (
              <div>
                {data.expense_breakdown.map((e, i) => (
                  <div key={e.code} style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span>{e.name}</span><span>{yuan(e.amount)}</span>
                    </div>
                    <Progress percent={expTotal ? Math.round((Math.abs(e.amount) / expTotal) * 100) : 0}
                      strokeColor={EXP_COLORS[i % EXP_COLORS.length]} size="small" />
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
