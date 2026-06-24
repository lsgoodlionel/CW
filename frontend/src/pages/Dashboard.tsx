import { useEffect, useState } from 'react'
import { Row, Col, Card, Statistic, Spin, Empty } from 'antd'
import {
  FileTextOutlined,
  RiseOutlined,
  FallOutlined,
  AccountBookOutlined,
} from '@ant-design/icons'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid,
} from 'recharts'
import { http } from '../api'

interface Summary {
  voucher_count: number
  revenue: number
  expense: number
  net_profit: number
  trend: { month: string; revenue: number; net_profit: number }[]
}

const yuan = (n: number) =>
  '¥' + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function Dashboard() {
  const [data, setData] = useState<Summary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    http.get<Summary>('/reports/summary')
      .then((r) => setData(r.data))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin style={{ display: 'block', marginTop: 80 }} />
  if (!data) return null

  return (
    <div>
      <Row gutter={16}>
        <Col xs={12} lg={6}>
          <Card><Statistic title="凭证总数" value={data.voucher_count}
            prefix={<FileTextOutlined />} /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="营业收入" value={data.revenue} precision={2}
            valueStyle={{ color: '#3f8600' }} prefix={<RiseOutlined />} suffix="元" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="总支出" value={data.expense} precision={2}
            valueStyle={{ color: '#cf1322' }} prefix={<FallOutlined />} suffix="元" /></Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card><Statistic title="净利润" value={data.net_profit} precision={2}
            valueStyle={{ color: data.net_profit >= 0 ? '#3f8600' : '#cf1322' }}
            prefix={<AccountBookOutlined />} suffix="元" /></Card>
        </Col>
      </Row>

      <Card title="近 6 个月收入 / 净利润趋势" style={{ marginTop: 16 }}>
        {data.trend.length === 0 ? (
          <Empty description="暂无数据,先去录入凭证吧" />
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={data.trend}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis />
              <Tooltip formatter={(v: number) => yuan(v)} />
              <Legend />
              <Bar dataKey="revenue" name="营业收入" fill="#1f6feb" />
              <Bar dataKey="net_profit" name="净利润" fill="#52c41a" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>
    </div>
  )
}
