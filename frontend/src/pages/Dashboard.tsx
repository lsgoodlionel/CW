import { useEffect, useState, useMemo } from 'react'
import { Row, Col, Card, Statistic, Spin, Empty, Segmented, DatePicker, Space, Tag, Progress } from 'antd'
import {
  BankOutlined, WalletOutlined, RiseOutlined, FallOutlined,
  AccountBookOutlined, FileTextOutlined, ArrowUpOutlined, ArrowDownOutlined,
  AuditOutlined, SolutionOutlined, FileDoneOutlined, TeamOutlined, IdcardOutlined,
  FileProtectOutlined, CalculatorOutlined, GoldOutlined, PayCircleOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
} from 'recharts'
import dayjs, { Dayjs } from 'dayjs'
import { http, DashboardData, formatYuan as yuan } from '../api'

type PeriodType = 'day' | 'month' | 'quarter' | 'year'

const EXP_COLORS = ['#1f6feb', '#52c41a', '#faad14', '#eb2f96', '#722ed1', '#13c2c2', '#fa541c']
const BODY = { body: { padding: '10px 12px' } }
const VS = { fontSize: 18 }

export default function Dashboard() {
  const navigate = useNavigate()
  const [periodType, setPeriodType] = useState<PeriodType>('month')
  const [refDate, setRefDate] = useState<Dayjs>(dayjs())
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  const params = useMemo(() => ({
    period_type: periodType, ref_date: refDate.format('YYYY-MM-DD'),
  }), [periodType, refDate])

  useEffect(() => {
    setLoading(true)
    http.get<DashboardData>('/reports/dashboard', { params })
      .then((r) => setData(r.data)).finally(() => setLoading(false))
  }, [params])

  if (loading && !data) return <Spin style={{ display: 'block', marginTop: 80 }} />
  if (!data) return null

  const picker = periodType === 'year' ? 'year' : periodType === 'quarter' ? 'quarter'
    : periodType === 'month' ? 'month' : 'date'
  const expTotal = data.expense_breakdown.reduce((s, e) => s + Math.abs(e.amount), 0)
  const fin = data.finance
  const ops = data.ops
  const lab = data.period.label

  // 紧凑 KPI 卡
  const Kpi = ({ span = 3, title, value, prefix, suffix = '元', color, precision = 2, onClick }: {
    span?: number; title: string; value: number; prefix?: React.ReactNode
    suffix?: string; color?: string; precision?: number; onClick?: () => void
  }) => (
    <Col xs={12} sm={8} lg={span}>
      <Card size="small" styles={BODY} hoverable={!!onClick} onClick={onClick}>
        <Statistic title={title} value={value} precision={precision}
          valueStyle={{ ...VS, color }} prefix={prefix} suffix={suffix} />
      </Card>
    </Col>
  )
  const Op = ({ title, value, icon, color, to }: {
    title: string; value: number; icon: React.ReactNode; color?: string; to: string
  }) => (
    <Col xs={12} sm={8} lg={3}>
      <Card size="small" styles={BODY} hoverable onClick={() => navigate(to)}>
        <Statistic title={title} value={value} valueStyle={{ ...VS, color: value ? color : undefined }} prefix={icon} />
      </Card>
    </Col>
  )

  return (
    <div>
      <Space wrap style={{ marginBottom: 12 }}>
        <Segmented value={periodType} onChange={(v) => setPeriodType(v as PeriodType)}
          options={[{ label: '日', value: 'day' }, { label: '月', value: 'month' },
            { label: '季', value: 'quarter' }, { label: '年', value: 'year' }]} />
        <DatePicker picker={picker as 'date'} value={refDate} allowClear={false}
          onChange={(v) => v && setRefDate(v)} />
        <Tag color="blue">{lab}</Tag>
      </Space>

      {/* 经营成果(本期) + 资产负债(期末) */}
      <Row gutter={[12, 12]}>
        <Kpi title={`营业收入(${lab})`} value={data.revenue} prefix={<RiseOutlined />} color="#3f8600" />
        <Kpi title={`总支出(${lab})`} value={data.expense} prefix={<FallOutlined />} color="#cf1322" />
        <Kpi title="净利润" value={data.net_profit} prefix={<AccountBookOutlined />}
          color={data.net_profit >= 0 ? '#3f8600' : '#cf1322'} />
        <Kpi title="货币资金合计" value={data.money.total} prefix={<WalletOutlined />} color="#1f6feb" />
        <Kpi title="资产总额" value={fin.assets} prefix={<GoldOutlined />} />
        <Kpi title="负债总额" value={fin.liabilities} prefix={<PayCircleOutlined />} color="#cf1322" />
        <Kpi title="所有者权益" value={fin.equity} color="#1f6feb" />
        <Kpi title="资产负债率" value={fin.debt_ratio * 100} suffix="%" precision={1}
          color={fin.debt_ratio > 0.7 ? '#cf1322' : '#3f8600'} />
      </Row>

      {/* 财务比率 + 往来/税费 + 货币构成 */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Kpi span={4} title="毛利率" value={fin.gross_margin * 100} suffix="%" precision={1} color="#3f8600" />
        <Kpi span={4} title="净利率" value={fin.net_margin * 100} suffix="%" precision={1}
          color={fin.net_margin >= 0 ? '#3f8600' : '#cf1322'} />
        <Kpi span={4} title="应收账款" value={data.receivable} prefix={<ArrowUpOutlined />} color="#3f8600" />
        <Kpi span={4} title="应付账款" value={data.payable} prefix={<ArrowDownOutlined />} color="#cf1322" />
        <Kpi span={4} title="应交税费" value={data.tax_payable} color="#d48806" />
        <Kpi span={4} title="银行存款" value={data.money.bank} prefix={<BankOutlined />} />
      </Row>

      {/* 运营 / 待办(覆盖各模块) */}
      <Card size="small" title="运营 / 待办概览" style={{ marginTop: 12 }} styles={{ body: { padding: 12 } }}>
        <Row gutter={[12, 12]}>
          <Op title="审批进行中" value={ops.workflow_pending} icon={<AuditOutlined />} color="#1f6feb" to="/approvals" />
          <Op title="费用申请待审" value={ops.apply_pending} icon={<FileDoneOutlined />} color="#d48806" to="/expense-apply" />
          <Op title="报销审批中" value={ops.claim_pending} icon={<SolutionOutlined />} color="#d48806" to="/expense" />
          <Op title="待生成凭证" value={ops.claim_approved} icon={<SolutionOutlined />} color="#d48806" to="/expense" />
          <Op title="税务待申报" value={ops.tax_pending} icon={<CalculatorOutlined />} color="#cf1322" to="/tax" />
          <Op title="履行中合同" value={ops.contracts_active} icon={<FileProtectOutlined />} color="#1f6feb" to="/contracts" />
          <Op title="往来单位" value={ops.customers} icon={<TeamOutlined />} to="/customers" />
          <Op title="在册员工" value={ops.employees} icon={<IdcardOutlined />} to="/personnel" />
        </Row>
        <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
          <Op title="凭证总数" value={ops.vouchers_total} icon={<FileTextOutlined />} to="/vouchers" />
          <Op title={`本期凭证(${lab})`} value={data.voucher_count} icon={<FileTextOutlined />} to="/vouchers" />
          <Op title="合同总数" value={ops.contracts_total} icon={<FileProtectOutlined />} to="/contracts" />
          <Op title="附件总数" value={ops.attachments} icon={<FileTextOutlined />} to="/vouchers" />
        </Row>
      </Card>

      {/* 趋势 + 支出构成 */}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        <Col xs={24} lg={14}>
          <Card size="small" title="近 6 个月 收入 / 净利润趋势">
            {data.trend.length === 0 ? <Empty description="暂无数据" /> : (
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={data.trend} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month" fontSize={12} /><YAxis fontSize={12} />
                  <Tooltip formatter={(v: number) => yuan(v)} /><Legend />
                  <Bar dataKey="revenue" name="营业收入" fill="#1f6feb" />
                  <Bar dataKey="net_profit" name="净利润" fill="#52c41a" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card size="small" title={`支出构成(${lab})`} styles={{ body: { padding: '8px 16px', maxHeight: 232, overflowY: 'auto' } }}>
            {data.expense_breakdown.length === 0 ? <Empty description="本期无支出" /> : (
              data.expense_breakdown.map((e, i) => (
                <div key={e.code} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>{e.name}</span><span>{yuan(e.amount)}</span>
                  </div>
                  <Progress percent={expTotal ? Math.round((Math.abs(e.amount) / expTotal) * 100) : 0}
                    strokeColor={EXP_COLORS[i % EXP_COLORS.length]} size="small" />
                </div>
              ))
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
