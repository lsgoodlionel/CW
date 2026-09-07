import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Button, Space, Modal, Form, Input, Select, InputNumber, DatePicker,
  Popconfirm, message, Tabs, Card, Divider, Alert,
} from 'antd'
import { PlusOutlined, DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { http, Attachment, formatYuan, withToken } from '../api'
import AttachmentEditor from '../components/AttachmentEditor'

interface TaxFiling {
  id: number; tax_type: string; taxpayer_type: string; period: string
  period_start: string | null; period_end: string | null
  tax_basis: number | string; tax_amount: number | string; paid_amount: number | string
  filed_date: string | null; status: string; note: string; attachments: Attachment[]
}
interface Meta { tax_type: Record<string, string>; taxpayer_type: Record<string, string>; status: Record<string, string> }
interface CitRow { line_no: string; label: string; amount: number }

const STATUS_COLOR: Record<string, string> = { pending: 'default', filed: 'processing', paid: 'success' }
const D = (v: string | null | undefined) => (v ? dayjs(v) : undefined)
const opts = (m: Record<string, string>) => Object.entries(m).map(([value, label]) => ({ value, label }))

export default function Tax() {
  const [meta, setMeta] = useState<Meta | null>(null)
  useEffect(() => { http.get<Meta>('/tax/meta').then((r) => setMeta(r.data)) }, [])
  if (!meta) return null
  return (
    <div className="content-card">
      <Tabs items={[
        { key: 'filings', label: '税务申报记录', children: <Filings meta={meta} /> },
        { key: 'report', label: '应纳税报表', children: <TaxReports /> },
      ]} />
    </div>
  )
}

function Filings({ meta }: { meta: Meta }) {
  const [rows, setRows] = useState<TaxFiling[]>([])
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<TaxFiling | null>(null)
  const [draftId, setDraftId] = useState<number | null>(null)
  const [existingAtt, setExistingAtt] = useState<Attachment[]>([])
  const [form] = Form.useForm()

  const load = useCallback(() => {
    setLoading(true)
    http.get<TaxFiling[]>('/tax/filings').then((r) => setRows(r.data)).finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const openEdit = (f: TaxFiling | null) => {
    setEditing(f); setDraftId(null); form.resetFields()
    setExistingAtt(f ? f.attachments : [])
    if (f) form.setFieldsValue({
      ...f, tax_basis: Number(f.tax_basis), tax_amount: Number(f.tax_amount), paid_amount: Number(f.paid_amount),
      period_start: D(f.period_start), period_end: D(f.period_end), filed_date: D(f.filed_date),
    })
    else form.setFieldsValue({ tax_type: 'stamp', taxpayer_type: 'enterprise', status: 'pending', tax_basis: 0, tax_amount: 0, paid_amount: 0 })
    setOpen(true)
  }
  const _payload = (v: Record<string, unknown>) => ({
    ...v,
    period_start: v.period_start ? (v.period_start as dayjs.Dayjs).format('YYYY-MM-DD') : null,
    period_end: v.period_end ? (v.period_end as dayjs.Dayjs).format('YYYY-MM-DD') : null,
    filed_date: v.filed_date ? (v.filed_date as dayjs.Dayjs).format('YYYY-MM-DD') : null,
  })
  const ensureOwner = async (): Promise<number | null> => {
    if (editing) return editing.id
    if (draftId) return draftId
    try {
      const v = await form.validateFields()
      const r = await http.post<TaxFiling>('/tax/filings', _payload(v))
      setDraftId(r.data.id); load(); return r.data.id
    } catch { return null }
  }
  const save = async () => {
    const v = await form.validateFields()
    const id = editing?.id ?? draftId
    if (id) await http.put(`/tax/filings/${id}`, _payload(v))
    else await http.post('/tax/filings', _payload(v))
    message.success('已保存'); setOpen(false); load()
  }
  const remove = (id: number) => http.delete(`/tax/filings/${id}`).then(() => { message.success('已删除'); load() })

  const columns = [
    { title: '税种', dataIndex: 'tax_type', width: 120, render: (v: string) => <Tag color="blue">{meta.tax_type[v] || v}</Tag> },
    { title: '纳税人', dataIndex: 'taxpayer_type', width: 100, render: (v: string) => meta.taxpayer_type[v] || v },
    { title: '所属期', dataIndex: 'period', width: 100 },
    { title: '计税依据', dataIndex: 'tax_basis', width: 120, align: 'right' as const, render: (v: number | string) => formatYuan(v) },
    { title: '应纳税额', dataIndex: 'tax_amount', width: 120, align: 'right' as const, render: (v: number | string) => formatYuan(v) },
    { title: '已缴', dataIndex: 'paid_amount', width: 110, align: 'right' as const, render: (v: number | string) => formatYuan(v) },
    { title: '申报日期', dataIndex: 'filed_date', width: 110, render: (v: string) => v || '-' },
    { title: '状态', dataIndex: 'status', width: 90, render: (s: string) => <Tag color={STATUS_COLOR[s]}>{meta.status[s] || s}</Tag> },
    {
      title: '操作', width: 130, render: (_: unknown, r: TaxFiling) => (
        <Space>
          <a onClick={() => openEdit(r)}>编辑</a>
          <Popconfirm title="删除该记录?" onConfirm={() => remove(r.id)}>
            <a style={{ color: '#cf1322' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit(null)}>新增申报记录</Button>
      </Space>
      <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={rows}
        pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }} />

      <Modal title={editing ? '编辑申报记录' : '新增申报记录'} open={open} onOk={save}
        onCancel={() => setOpen(false)} okText="保存" width={640}>
        <Form form={form} layout="vertical">
          <Space wrap>
            <Form.Item name="tax_type" label="税种" rules={[{ required: true }]}>
              <Select style={{ width: 150 }} options={opts(meta.tax_type)} />
            </Form.Item>
            <Form.Item name="taxpayer_type" label="纳税人类型">
              <Select style={{ width: 140 }} options={opts(meta.taxpayer_type)} />
            </Form.Item>
            <Form.Item name="period" label="所属期" rules={[{ required: true }]}>
              <Input placeholder="如 2026Q2 / 2026-06 / 2026" style={{ width: 180 }} />
            </Form.Item>
          </Space>
          <Space wrap>
            <Form.Item name="period_start" label="所属期起"><DatePicker /></Form.Item>
            <Form.Item name="period_end" label="所属期止"><DatePicker /></Form.Item>
            <Form.Item name="filed_date" label="申报日期"><DatePicker /></Form.Item>
            <Form.Item name="status" label="状态">
              <Select style={{ width: 120 }} options={opts(meta.status)} />
            </Form.Item>
          </Space>
          <Space wrap>
            <Form.Item name="tax_basis" label="计税依据(元)"><InputNumber min={0} precision={2} style={{ width: 160 }} /></Form.Item>
            <Form.Item name="tax_amount" label="应纳税额(元)"><InputNumber precision={2} style={{ width: 160 }} /></Form.Item>
            <Form.Item name="paid_amount" label="已缴税额(元)"><InputNumber precision={2} style={{ width: 160 }} /></Form.Item>
          </Space>
          <Form.Item name="note" label="备注"><Input.TextArea rows={2} /></Form.Item>
          <Divider orientation="left" plain>申报/完税凭证附件</Divider>
          <AttachmentEditor ownerId={editing?.id ?? draftId} basePath="/tax/filings"
            ensureOwner={ensureOwner} existing={existingAtt} onChange={setExistingAtt} defaultKind="tax_payment" />
        </Form>
      </Modal>
    </>
  )
}

function TaxReports() {
  const now = dayjs()
  const [year, setYear] = useState<number>(now.year())
  const [quarter, setQuarter] = useState<number>(Math.floor((now.month()) / 3) + 1)
  const [preview, setPreview] = useState<CitRow[]>([])

  const loadPreview = useCallback(() => {
    http.get<{ rows: CitRow[] }>('/tax/report/cit-quarterly/preview', { params: { year, quarter } })
      .then((r) => setPreview(r.data.rows))
  }, [year, quarter])
  useEffect(() => { loadPreview() }, [loadPreview])

  const download = () =>
    window.open(withToken(`/api/tax/report/cit-quarterly?year=${year}&quarter=${quarter}`), '_blank')

  return (
    <Card size="small" title="企业所得税月(季)度预缴纳税申报表(A类)· A200000"
      extra={<Button type="primary" icon={<DownloadOutlined />} onClick={download}>导出 Excel</Button>}>
      <Space style={{ marginBottom: 12 }} wrap>
        <span>年度</span>
        <InputNumber value={year} min={2000} max={2100} onChange={(v) => v && setYear(v)} style={{ width: 100 }} />
        <span>季度</span>
        <Select value={quarter} style={{ width: 90 }} onChange={setQuarter}
          options={[1, 2, 3, 4].map((q) => ({ value: q, label: `第${q}季度` }))} />
      </Space>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
        message="本表按账套数据自动计算本年累计(年初→季末);优惠、预缴、纳税调整等行次默认 0,导出后可在 Excel 中按实际手工调整再报送。" />
      <Table rowKey="line_no" size="small" pagination={false} dataSource={preview}
        columns={[
          { title: '行次', dataIndex: 'line_no', width: 60 },
          { title: '项目', dataIndex: 'label' },
          { title: '本年累计金额', dataIndex: 'amount', width: 160, align: 'right' as const,
            render: (v: number, r: CitRow) => (r.line_no === '26' ? '25%' : formatYuan(v)) },
        ]} />
    </Card>
  )
}
