import { useEffect, useState, useCallback } from 'react'
import { Card, Tabs, DatePicker, Table, Tag, Row, Col, Statistic, Space } from 'antd'
import dayjs, { Dayjs } from 'dayjs'
import { http } from '../api'

const { RangePicker } = DatePicker
const yuan = (n: number) => '¥' + n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

interface TrialRow { code: string; name: string; category: string; debit: number; credit: number; balance: number }
interface Income { lines: { key: string; label: string; amount: number }[]; operating_profit: number; total_profit: number; net_profit: number }
interface BalanceRow { name: string; amount: number }
interface Balance {
  assets: BalanceRow[]; liabilities: BalanceRow[]; equity: BalanceRow[]
  asset_total: number; liability_total: number; equity_total: number; balanced: boolean
}

export default function Reports() {
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().startOf('year'), dayjs().endOf('year')])
  const [trial, setTrial] = useState<{ rows: TrialRow[]; total_debit: number; total_credit: number; balanced: boolean } | null>(null)
  const [income, setIncome] = useState<Income | null>(null)
  const [balance, setBalance] = useState<Balance | null>(null)

  const load = useCallback(() => {
    const params = { start: range[0].format('YYYY-MM-DD'), end: range[1].format('YYYY-MM-DD') }
    http.get('/reports/trial-balance', { params }).then((r) => setTrial(r.data))
    http.get('/reports/income', { params }).then((r) => setIncome(r.data))
    http.get('/reports/balance-sheet', { params: { as_of: params.end } }).then((r) => setBalance(r.data))
  }, [range])

  useEffect(() => { load() }, [load])

  return (
    <Card>
      <Space style={{ marginBottom: 16 }}>
        <span>统计区间:</span>
        <RangePicker value={range} allowClear={false}
          onChange={(v) => v && setRange(v as [Dayjs, Dayjs])} />
      </Space>
      <Tabs items={[
        {
          key: 'trial', label: '科目汇总表',
          children: <TrialBalance data={trial} />,
        },
        {
          key: 'income', label: '利润表',
          children: <IncomeStatement data={income} />,
        },
        {
          key: 'balance', label: '资产负债表',
          children: <BalanceSheet data={balance} asOf={range[1].format('YYYY-MM-DD')} />,
        },
      ]} />
    </Card>
  )
}

function TrialBalance({ data }: { data: { rows: TrialRow[]; total_debit: number; total_credit: number; balanced: boolean } | null }) {
  if (!data) return null
  return (
    <>
      <Tag color={data.balanced ? 'green' : 'red'} style={{ marginBottom: 12 }}>
        {data.balanced ? `试算平衡 ✓ 借贷各 ${yuan(data.total_debit)}` : '试算不平衡 ✗'}
      </Tag>
      <Table rowKey="code" size="small" pagination={false} dataSource={data.rows}
        columns={[
          { title: '科目', render: (_, r) => `${r.code} ${r.name}` },
          { title: '借方发生额', dataIndex: 'debit', align: 'right' as const, render: yuan },
          { title: '贷方发生额', dataIndex: 'credit', align: 'right' as const, render: yuan },
          { title: '余额', dataIndex: 'balance', align: 'right' as const, render: yuan },
        ]}
        summary={() => (
          <Table.Summary.Row>
            <Table.Summary.Cell index={0}><b>合计</b></Table.Summary.Cell>
            <Table.Summary.Cell index={1} align="right"><b>{yuan(data.total_debit)}</b></Table.Summary.Cell>
            <Table.Summary.Cell index={2} align="right"><b>{yuan(data.total_credit)}</b></Table.Summary.Cell>
            <Table.Summary.Cell index={3} />
          </Table.Summary.Row>
        )} />
    </>
  )
}

function IncomeStatement({ data }: { data: Income | null }) {
  if (!data) return null
  return (
    <>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}><Card size="small"><Statistic title="营业利润" value={data.operating_profit} precision={2} suffix="元" /></Card></Col>
        <Col span={8}><Card size="small"><Statistic title="利润总额" value={data.total_profit} precision={2} suffix="元" /></Card></Col>
        <Col span={8}><Card size="small"><Statistic title="净利润" value={data.net_profit} precision={2}
          valueStyle={{ color: data.net_profit >= 0 ? '#3f8600' : '#cf1322' }} suffix="元" /></Card></Col>
      </Row>
      <Table rowKey="key" size="small" pagination={false} showHeader={false} dataSource={data.lines}
        columns={[
          { title: '项目', dataIndex: 'label' },
          { title: '金额', dataIndex: 'amount', align: 'right' as const, width: 200, render: yuan },
        ]} />
    </>
  )
}

function BalanceSheet({ data, asOf }: { data: Balance | null; asOf: string }) {
  if (!data) return null
  const cols = [
    { title: '项目', dataIndex: 'name' },
    { title: '余额', dataIndex: 'amount', align: 'right' as const, width: 160, render: yuan },
  ]
  return (
    <>
      <Tag color={data.balanced ? 'green' : 'red'} style={{ marginBottom: 12 }}>
        截至 {asOf}:{data.balanced ? '资产 = 负债 + 所有者权益 ✓' : '不平衡 ✗'}
      </Tag>
      <Row gutter={16}>
        <Col xs={24} md={12}>
          <h4>资产</h4>
          <Table rowKey="name" size="small" pagination={false} dataSource={data.assets} columns={cols}
            summary={() => (
              <Table.Summary.Row>
                <Table.Summary.Cell index={0}><b>资产总计</b></Table.Summary.Cell>
                <Table.Summary.Cell index={1} align="right"><b>{yuan(data.asset_total)}</b></Table.Summary.Cell>
              </Table.Summary.Row>
            )} />
        </Col>
        <Col xs={24} md={12}>
          <h4>负债</h4>
          <Table rowKey="name" size="small" pagination={false} dataSource={data.liabilities} columns={cols} />
          <h4 style={{ marginTop: 12 }}>所有者权益</h4>
          <Table rowKey="name" size="small" pagination={false} dataSource={data.equity} columns={cols}
            summary={() => (
              <Table.Summary.Row>
                <Table.Summary.Cell index={0}><b>负债和权益总计</b></Table.Summary.Cell>
                <Table.Summary.Cell index={1} align="right">
                  <b>{yuan(data.liability_total + data.equity_total)}</b>
                </Table.Summary.Cell>
              </Table.Summary.Row>
            )} />
        </Col>
      </Row>
    </>
  )
}
