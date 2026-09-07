import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Button, Space, Modal, Form, Input, Select, InputNumber, DatePicker,
  Popconfirm, message, Tabs, Card, Divider, Alert, Segmented,
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
interface CitRow { line_no: string; label: string; amount: number; level: number; category?: string }
interface A104Row { line_no: string; label: string; sell: number; admin: number; fin: number }
interface A105Row {
  line_no: string; label: string; level: number; editable: boolean
  book: number; tax: number; add: number; reduce: number
}
interface A106Row {
  line_no: string; item: string; occur_year: number | null
  loss: number; pending: number; offset: number; carry: number; editable: boolean
}
interface A105080Row {
  line_no: string; item: string; level: number; editable: boolean
  orig: number; book_dep: number; tax_basis: number; tax_dep: number; adjust: number
}
interface A107Row {
  line_no: string; item: string; amount: number; level: number; editable: boolean
}
interface A201020Row {
  line_no: string; item: string; level: number; editable: boolean
  orig: number; book: number; normal: number; accel: number; reduce: number; benefit: number
}
interface PrefRow {
  category: string; category_label: string; code: string; name: string
  amount: number; editable: boolean
}
interface SmCheckItem { name: string; value: number | string; limit: number | string; unit: string; ok: boolean }
interface SmallMicroCheck { mode: string; effective: boolean; qualified: boolean; checks: SmCheckItem[]; reasons: string[] }
interface TaxpayerCheck { sales_12m: number; limit: number; should_be: string; current: string; mismatch: boolean; reason: string }
interface Reconcile { annual_taxable: number; q4_prepay_profit: number; diff: number; note: string }
interface ReportChecks { small_micro: SmallMicroCheck; taxpayer: TaxpayerCheck; reconcile?: Reconcile }
interface Schedules { A101010: CitRow[]; A102010: CitRow[]; A104000: A104Row[] }

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

// 项目列按行次层级缩进;税率行显示百分比
const renderLabel = (label: string, r: { level: number }) => {
  const isSection = /^[一二三四五六七八九十]、/.test(label)
  return (
    <span style={{ paddingLeft: r.level * 22, fontWeight: isSection ? 600 : 400 }}>{label}</span>
  )
}
const renderAmount = (v: number, r: CitRow) => (r.label.startsWith('税率') ? '25%' : formatYuan(v))

// 小型微利 / 增值税身份 / 年度季度核对 复核提示面板
function ReportCheckPanel({ checks, isAnnual }: { checks: ReportChecks; isAnnual: boolean }) {
  const sm = checks.small_micro
  const tk = checks.taxpayer
  const fmtVal = (c: SmCheckItem) => (typeof c.value === 'number' ? formatYuan(c.value) : c.value)
  const fmtLimit = (c: SmCheckItem) => (typeof c.limit === 'number' ? formatYuan(c.limit) : c.limit)

  const smType = sm.effective ? 'success' : 'warning'
  const smTitle = sm.mode === 'auto'
    ? `自动复核:${sm.qualified ? '符合' : '不符合'}小型微利企业,本期按${sm.effective ? '小型微利优惠(实际税负5%)' : '法定25%'}计算`
    : `手动模式:按手动值${sm.effective ? '(是)' : '(否)'}计算;自动复核结果为${sm.qualified ? '符合' : '不符合'}`

  return (
    <div style={{ marginBottom: 12 }}>
      <Alert type={smType} showIcon style={{ marginBottom: 8 }}
        message={smTitle}
        description={
          <>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px', margin: '6px 0' }}>
              {sm.checks.map((c) => (
                <span key={c.name} style={{ color: c.ok ? '#389e0d' : '#cf1322' }}>
                  {c.ok ? '✓' : '✗'} {c.name}:{fmtVal(c)}{c.unit}
                  {c.limit !== '-' && ` (标准 ≤ ${fmtLimit(c)}${c.unit})`}
                </span>
              ))}
            </div>
            {!sm.qualified && sm.reasons.length > 0 && (
              <div style={{ color: '#cf1322' }}>
                不满足原因:{sm.reasons.join(';')}。
                {sm.mode === 'auto'
                  ? '本计算周期已自动按非小型微利计算;如需固定,可在「企业信息」关闭自动判断并将小型微利设为否。'
                  : '请在「企业信息」将小型微利手动值改为否,或开启自动判断。'}
              </div>
            )}
            <div style={{ color: '#888', marginTop: 4 }}>
              判断依据:同时满足 应纳税所得额≤300万、从业人数≤300、资产总额≤5000万、非国家限制或禁止行业。
              数据口径:销售额/资产总额取自账套,从业人数取自人员档案在职数。
            </div>
          </>
        } />
      {tk.mismatch && (
        <Alert type="warning" showIcon style={{ marginBottom: 8 }}
          message="增值税纳税人身份复核:已超过小规模标准" description={tk.reason} />
      )}
      {!tk.mismatch && (
        <Alert type="info" showIcon style={{ marginBottom: 8 }}
          message={`增值税身份复核:近12个月销售额 ${formatYuan(tk.sales_12m)} 元,当前为${tk.current === 'general' ? '一般纳税人' : '小规模纳税人'},符合标准(小规模 ≤ ${formatYuan(tk.limit)} 元)。`} />
      )}
      {isAnnual && checks.reconcile && (
        <Alert type="info" showIcon
          message={`年度与季度核对:年报应纳税所得额 ${formatYuan(checks.reconcile.annual_taxable)} 元,第四季度预缴口径实际利润额 ${formatYuan(checks.reconcile.q4_prepay_profit)} 元,差异 ${formatYuan(checks.reconcile.diff)} 元。`}
          description={checks.reconcile.note} />
      )}
    </div>
  )
}

function TaxReports() {
  const now = dayjs()
  const [reportType, setReportType] = useState<'quarterly' | 'annual'>('quarterly')
  const [year, setYear] = useState<number>(now.year())
  const [quarter, setQuarter] = useState<number>(Math.floor((now.month()) / 3) + 1)
  const [preview, setPreview] = useState<CitRow[]>([])
  const [sched, setSched] = useState<Schedules | null>(null)
  const [checks, setChecks] = useState<ReportChecks | null>(null)

  const isAnnual = reportType === 'annual'
  const loadPreview = useCallback(() => {
    if (isAnnual) {
      http.get<{ rows: CitRow[]; schedules: Schedules; checks: ReportChecks }>('/tax/report/cit-annual/preview', { params: { year } })
        .then((r) => { setPreview(r.data.rows); setSched(r.data.schedules); setChecks(r.data.checks) })
    } else {
      http.get<{ rows: CitRow[]; checks: ReportChecks }>('/tax/report/cit-quarterly/preview', { params: { year, quarter } })
        .then((r) => { setPreview(r.data.rows); setSched(null); setChecks(r.data.checks) })
    }
  }, [isAnnual, year, quarter])
  useEffect(() => { loadPreview() }, [loadPreview])

  const download = () => {
    const url = isAnnual
      ? `/api/tax/report/cit-annual?year=${year}`
      : `/api/tax/report/cit-quarterly?year=${year}&quarter=${quarter}`
    window.open(withToken(url), '_blank')
  }

  const quarterlyCols = [
    { title: '行次', dataIndex: 'line_no', width: 60 },
    { title: '项目', dataIndex: 'label', render: renderLabel },
    { title: '本年累计金额', dataIndex: 'amount', width: 160, align: 'right' as const, render: renderAmount },
  ]
  const annualCols = [
    { title: '行次', dataIndex: 'line_no', width: 60 },
    { title: '类别', dataIndex: 'category', width: 120 },
    { title: '项目', dataIndex: 'label', render: renderLabel },
    { title: '本年金额', dataIndex: 'amount', width: 160, align: 'right' as const, render: renderAmount },
  ]
  const scheduleCols = [
    { title: '行次', dataIndex: 'line_no', width: 60 },
    { title: '项目', dataIndex: 'label', render: renderLabel },
    { title: '本年金额', dataIndex: 'amount', width: 160, align: 'right' as const, render: renderAmount },
  ]

  const title = isAnnual
    ? '企业所得税年度纳税申报表(A类)· A100000'
    : '企业所得税月(季)度预缴纳税申报表(A类)· A200000'

  return (
    <Card size="small" title={title}
      extra={<Button type="primary" icon={<DownloadOutlined />} onClick={download}>导出 Excel</Button>}>
      <Space style={{ marginBottom: 12 }} wrap>
        <Segmented value={reportType} onChange={(v) => setReportType(v as 'quarterly' | 'annual')}
          options={[{ label: '季度预缴(A200000)', value: 'quarterly' },
            { label: '年度汇算(A100000)', value: 'annual' }]} />
        <span>年度</span>
        <InputNumber value={year} min={2000} max={2100} onChange={(v) => v && setYear(v)} style={{ width: 100 }} />
        {!isAnnual && <>
          <span>季度</span>
          <Select value={quarter} style={{ width: 90 }} onChange={setQuarter}
            options={[1, 2, 3, 4].map((q) => ({ value: q, label: `第${q}季度` }))} />
        </>}
      </Space>
      <Alert type="info" showIcon style={{ marginBottom: 12 }}
        message={isAnnual
          ? '年报按账套全年数据自动计算利润总额及应纳税额;境外所得、纳税调整、各类优惠、预缴税额及总分机构分摊等行次默认 0,导出后可结合各附表按实际手工调整再报送。'
          : '本表按账套数据自动计算本年累计(年初→季末);优惠、预缴、纳税调整等行次默认 0,导出后可在 Excel 中按实际手工调整再报送。'} />
      {checks && <ReportCheckPanel checks={checks} isAnnual={isAnnual} />}
      {!isAnnual && (
        <Tabs size="small" items={[
          { key: 'main', label: 'A200000 主表', children: (
            <Table rowKey="line_no" size="small" pagination={false} dataSource={preview} columns={quarterlyCols} />
          ) },
          { key: 'a201020', label: 'A201020 加速折旧', children: (
            <A201020Editor year={year} onSaved={loadPreview} />
          ) },
          { key: 'pref', label: '税收优惠', children: (
            <PrefEditor year={year} onSaved={loadPreview} />
          ) },
        ]} />
      )}
      {isAnnual && (
        <Tabs size="small" items={[
          { key: 'main', label: 'A100000 主表', children: (
            <Table rowKey="line_no" size="small" pagination={false} dataSource={preview} columns={annualCols} />
          ) },
          { key: 'a101', label: 'A101010 收入', children: (
            <Table rowKey="line_no" size="small" pagination={false} dataSource={sched?.A101010 || []}
              columns={scheduleCols} />
          ) },
          { key: 'a102', label: 'A102010 成本', children: (
            <Table rowKey="line_no" size="small" pagination={false} dataSource={sched?.A102010 || []}
              columns={scheduleCols} />
          ) },
          { key: 'a104', label: 'A104000 期间费用', children: (
            <Table rowKey="line_no" size="small" pagination={false} dataSource={sched?.A104000 || []}
              columns={[
                { title: '行次', dataIndex: 'line_no', width: 60 },
                { title: '项目', dataIndex: 'label' },
                { title: '销售费用', dataIndex: 'sell', width: 120, align: 'right' as const, render: (v: number) => formatYuan(v) },
                { title: '管理费用', dataIndex: 'admin', width: 120, align: 'right' as const, render: (v: number) => formatYuan(v) },
                { title: '财务费用', dataIndex: 'fin', width: 120, align: 'right' as const, render: (v: number) => formatYuan(v) },
              ]} />
          ) },
          { key: 'a105', label: 'A105000 纳税调整', children: (
            <A105Editor year={year} onSaved={loadPreview} />
          ) },
          { key: 'a106', label: 'A106000 弥补亏损', children: (
            <A106Editor year={year} onSaved={loadPreview} />
          ) },
          { key: 'a105080', label: 'A105080 折旧摊销', children: (
            <A105080Editor year={year} onSaved={loadPreview} />
          ) },
          { key: 'a107012', label: 'A107012 研发加计', children: (
            <A107Editor year={year} onSaved={loadPreview} />
          ) },
          { key: 'pref', label: '税收优惠', children: (
            <PrefEditor year={year} onSaved={loadPreview} />
          ) },
        ]} />
      )}
    </Card>
  )
}

// A105000 纳税调整明细录入:明细行可编辑账载/税收/调增/调减,小计合计自动汇总并联动主表
function A105Editor({ year, onSaved }: { year: number; onSaved: () => void }) {
  const [rows, setRows] = useState<A105Row[]>([])
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    http.get<{ rows: A105Row[] }>('/tax/adjustments', { params: { year } })
      .then((r) => setRows(r.data.rows))
  }, [year])
  useEffect(() => { load() }, [load])

  const setCell = (lineNo: string, key: 'book' | 'tax' | 'add' | 'reduce', v: number | null) =>
    setRows((rs) => rs.map((r) => (r.line_no === lineNo ? { ...r, [key]: v ?? 0 } : r)))

  const save = async () => {
    setSaving(true)
    try {
      const items = rows.filter((r) => r.editable).map((r) => ({
        line_no: r.line_no, book_amount: r.book, tax_amount: r.tax,
        add_amount: r.add, reduce_amount: r.reduce,
      }))
      const res = await http.put<{ rows: A105Row[] }>('/tax/adjustments', { year, items })
      setRows(res.data.rows); message.success('纳税调整已保存'); onSaved()
    } finally { setSaving(false) }
  }

  const numCell = (key: 'book' | 'tax' | 'add' | 'reduce') =>
    (v: number, r: A105Row) => (r.editable
      ? <InputNumber size="small" value={v} controls={false} precision={2} style={{ width: 118 }}
          onChange={(nv) => setCell(r.line_no, key, nv as number | null)} />
      : formatYuan(v))

  return (
    <>
      <Space style={{ marginBottom: 8 }} wrap>
        <Button type="primary" loading={saving} onClick={save}>保存纳税调整</Button>
        <span style={{ color: '#888' }}>明细行可录入账载/税收/调增/调减;小计、合计自动汇总,并联动主表行20/21。</span>
      </Space>
      <Table rowKey="line_no" size="small" pagination={false} dataSource={rows} scroll={{ x: 720 }}
        columns={[
          { title: '行次', dataIndex: 'line_no', width: 56 },
          { title: '项目', dataIndex: 'label', render: renderLabel },
          { title: '账载金额', dataIndex: 'book', width: 130, align: 'right' as const, render: numCell('book') },
          { title: '税收金额', dataIndex: 'tax', width: 130, align: 'right' as const, render: numCell('tax') },
          { title: '调增金额', dataIndex: 'add', width: 130, align: 'right' as const, render: numCell('add') },
          { title: '调减金额', dataIndex: 'reduce', width: 130, align: 'right' as const, render: numCell('reduce') },
        ]} />
    </>
  )
}

// A106000 弥补亏损明细录入:行1..11 可录入亏损额/待弥补额/本年弥补额,合计自动汇总并联动主表行26
function A106Editor({ year, onSaved }: { year: number; onSaved: () => void }) {
  const [rows, setRows] = useState<A106Row[]>([])
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    http.get<{ rows: A106Row[] }>('/tax/losses', { params: { year } })
      .then((r) => setRows(r.data.rows))
  }, [year])
  useEffect(() => { load() }, [load])

  const setCell = (lineNo: string, key: 'loss' | 'pending' | 'offset', v: number | null) =>
    setRows((rs) => rs.map((r) => (r.line_no === lineNo ? { ...r, [key]: v ?? 0 } : r)))

  const save = async () => {
    setSaving(true)
    try {
      const items = rows.filter((r) => r.editable).map((r) => ({
        line_no: r.line_no, loss_amount: r.loss, pending_amount: r.pending, offset_amount: r.offset,
      }))
      const res = await http.put<{ rows: A106Row[] }>('/tax/losses', { report_year: year, items })
      setRows(res.data.rows); message.success('弥补亏损已保存'); onSaved()
    } finally { setSaving(false) }
  }

  const numCell = (key: 'loss' | 'pending' | 'offset') =>
    (v: number, r: A106Row) => (r.editable
      ? <InputNumber size="small" value={v} controls={false} precision={2} style={{ width: 118 }}
          onChange={(nv) => setCell(r.line_no, key, nv as number | null)} />
      : formatYuan(v))

  return (
    <>
      <Space style={{ marginBottom: 8 }} wrap>
        <Button type="primary" loading={saving} onClick={save}>保存弥补亏损</Button>
        <span style={{ color: '#888' }}>录入各以前年度亏损额、待弥补额及用本年度所得弥补额;合计自动汇总,并联动主表行26(弥补以前年度亏损)。</span>
      </Space>
      <Table rowKey="line_no" size="small" pagination={false} dataSource={rows} scroll={{ x: 820 }}
        columns={[
          { title: '行次', dataIndex: 'line_no', width: 56 },
          { title: '项目', dataIndex: 'item', width: 110 },
          { title: '所属年度', dataIndex: 'occur_year', width: 90, render: (v: number | null) => v ?? '' },
          { title: '当年亏损额', dataIndex: 'loss', width: 130, align: 'right' as const, render: numCell('loss') },
          { title: '当年待弥补的亏损额', dataIndex: 'pending', width: 150, align: 'right' as const, render: numCell('pending') },
          { title: '用本年度所得额弥补的以前年度亏损额', dataIndex: 'offset', width: 180, align: 'right' as const, render: numCell('offset') },
          { title: '可结转以后年度弥补的亏损额', dataIndex: 'carry', width: 160, align: 'right' as const, render: (v: number) => formatYuan(v) },
        ]} />
    </>
  )
}

// A105080 资产折旧摊销录入:明细行录入资产原值/账载折旧/计税基础/税收折旧,纳税调整=账载−税收,联动 A105000 行32
function A105080Editor({ year, onSaved }: { year: number; onSaved: () => void }) {
  const [rows, setRows] = useState<A105080Row[]>([])
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    http.get<{ rows: A105080Row[] }>('/tax/depreciations', { params: { year } })
      .then((r) => setRows(r.data.rows))
  }, [year])
  useEffect(() => { load() }, [load])

  const setCell = (lineNo: string, key: 'orig' | 'book_dep' | 'tax_basis' | 'tax_dep', v: number | null) =>
    setRows((rs) => rs.map((r) => (r.line_no === lineNo ? { ...r, [key]: v ?? 0 } : r)))

  const save = async () => {
    setSaving(true)
    try {
      const items = rows.filter((r) => r.editable).map((r) => ({
        line_no: r.line_no, orig_value: r.orig, book_dep: r.book_dep,
        tax_basis: r.tax_basis, tax_dep: r.tax_dep,
      }))
      const res = await http.put<{ rows: A105080Row[] }>('/tax/depreciations', { report_year: year, items })
      setRows(res.data.rows); message.success('资产折旧摊销已保存'); onSaved()
    } finally { setSaving(false) }
  }

  const numCell = (key: 'orig' | 'book_dep' | 'tax_basis' | 'tax_dep') =>
    (v: number, r: A105080Row) => (r.editable
      ? <InputNumber size="small" value={v} controls={false} precision={2} style={{ width: 110 }}
          onChange={(nv) => setCell(r.line_no, key, nv as number | null)} />
      : formatYuan(v))

  return (
    <>
      <Space style={{ marginBottom: 8 }} wrap>
        <Button type="primary" loading={saving} onClick={save}>保存折旧摊销</Button>
        <span style={{ color: '#888' }}>录入各资产类别的账载/税收折旧;纳税调整金额=账载−税收,自动汇总并联动 A105000 行32、主表纳税调整。</span>
      </Space>
      <Table rowKey="line_no" size="small" pagination={false} dataSource={rows} scroll={{ x: 880 }}
        columns={[
          { title: '行次', dataIndex: 'line_no', width: 56 },
          { title: '项目', dataIndex: 'item', render: renderLabel },
          { title: '资产原值', dataIndex: 'orig', width: 120, align: 'right' as const, render: numCell('orig') },
          { title: '账载本年折旧摊销额', dataIndex: 'book_dep', width: 140, align: 'right' as const, render: numCell('book_dep') },
          { title: '资产计税基础', dataIndex: 'tax_basis', width: 120, align: 'right' as const, render: numCell('tax_basis') },
          { title: '税收折旧摊销额', dataIndex: 'tax_dep', width: 130, align: 'right' as const, render: numCell('tax_dep') },
          { title: '纳税调整金额', dataIndex: 'adjust', width: 120, align: 'right' as const, render: (v: number) => formatYuan(v) },
        ]} />
    </>
  )
}

// A107012 研发费用加计扣除录入:明细行录入研发费用,行50填加计比例,行51加计扣除总额联动主表行22
function A107Editor({ year, onSaved }: { year: number; onSaved: () => void }) {
  const [rows, setRows] = useState<A107Row[]>([])
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    http.get<{ rows: A107Row[] }>('/tax/rd-deductions', { params: { year } })
      .then((r) => setRows(r.data.rows))
  }, [year])
  useEffect(() => { load() }, [load])

  const setAmount = (lineNo: string, v: number | null) =>
    setRows((rs) => rs.map((r) => (r.line_no === lineNo ? { ...r, amount: v ?? 0 } : r)))

  const save = async () => {
    setSaving(true)
    try {
      const items = rows.filter((r) => r.editable).map((r) => ({ line_no: r.line_no, amount: r.amount }))
      const res = await http.put<{ rows: A107Row[] }>('/tax/rd-deductions', { report_year: year, items })
      setRows(res.data.rows); message.success('研发加计扣除已保存'); onSaved()
    } finally { setSaving(false) }
  }

  return (
    <>
      <Space style={{ marginBottom: 8 }} wrap>
        <Button type="primary" loading={saving} onClick={save}>保存研发加计</Button>
        <span style={{ color: '#888' }}>录入各研发费用明细,行50填加计比例(1.00=100%);行51加计扣除总额自动计算并联动主表行22。</span>
      </Space>
      <Table rowKey="line_no" size="small" pagination={false} dataSource={rows} scroll={{ x: 620 }}
        columns={[
          { title: '行次', dataIndex: 'line_no', width: 56 },
          { title: '项目', dataIndex: 'item', render: renderLabel },
          { title: '金额(数量)', dataIndex: 'amount', width: 150, align: 'right' as const,
            render: (v: number, r: A107Row) => (r.editable
              ? <InputNumber size="small" value={v} controls={false} precision={2} style={{ width: 130 }}
                  onChange={(nv) => setAmount(r.line_no, nv as number | null)} />
              : formatYuan(v)) },
        ]} />
    </>
  )
}

// A201020 资产加速折旧优惠录入(季报,本年累计):明细行录入,纳税调减合计联动季报主表行21
function A201020Editor({ year, onSaved }: { year: number; onSaved: () => void }) {
  const [rows, setRows] = useState<A201020Row[]>([])
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    http.get<{ rows: A201020Row[] }>('/tax/accel-deprs', { params: { year } })
      .then((r) => setRows(r.data.rows))
  }, [year])
  useEffect(() => { load() }, [load])

  const setCell = (lineNo: string, key: 'orig' | 'book' | 'normal' | 'accel' | 'reduce', v: number | null) =>
    setRows((rs) => rs.map((r) => (r.line_no === lineNo ? { ...r, [key]: v ?? 0 } : r)))

  const save = async () => {
    setSaving(true)
    try {
      const items = rows.filter((r) => r.editable).map((r) => ({
        line_no: r.line_no, orig_value: r.orig, book_dep: r.book,
        tax_normal: r.normal, accel_dep: r.accel, reduce_amount: r.reduce,
      }))
      const res = await http.put<{ rows: A201020Row[] }>('/tax/accel-deprs', { year, items })
      setRows(res.data.rows); message.success('加速折旧优惠已保存'); onSaved()
    } finally { setSaving(false) }
  }

  const numCell = (key: 'orig' | 'book' | 'normal' | 'accel' | 'reduce') =>
    (v: number, r: A201020Row) => (r.editable
      ? <InputNumber size="small" value={v} controls={false} precision={2} style={{ width: 104 }}
          onChange={(nv) => setCell(r.line_no, key, nv as number | null)} />
      : formatYuan(v))

  return (
    <>
      <Space style={{ marginBottom: 8 }} wrap>
        <Button type="primary" loading={saving} onClick={save}>保存加速折旧</Button>
        <span style={{ color: '#888' }}>按本年累计口径录入加速折旧/一次性扣除明细;纳税调减金额合计联动季报主表行21。</span>
      </Space>
      <Table rowKey="line_no" size="small" pagination={false} dataSource={rows} scroll={{ x: 900 }}
        columns={[
          { title: '行次', dataIndex: 'line_no', width: 50 },
          { title: '项目', dataIndex: 'item', render: renderLabel },
          { title: '资产原值', dataIndex: 'orig', width: 116, align: 'right' as const, render: numCell('orig') },
          { title: '账载折旧', dataIndex: 'book', width: 116, align: 'right' as const, render: numCell('book') },
          { title: '税收一般折旧', dataIndex: 'normal', width: 116, align: 'right' as const, render: numCell('normal') },
          { title: '加速折旧', dataIndex: 'accel', width: 116, align: 'right' as const, render: numCell('accel') },
          { title: '纳税调减金额', dataIndex: 'reduce', width: 116, align: 'right' as const, render: numCell('reduce') },
          { title: '加速优惠金额', dataIndex: 'benefit', width: 116, align: 'right' as const, render: (v: number) => formatYuan(v) },
        ]} />
    </>
  )
}

// 税收优惠事项录入(免税/减计/所得减免/减免所得税):按国税码表固定行填金额,汇总联动主表行22/25/31(季报22/23/28)
function PrefEditor({ year, onSaved }: { year: number; onSaved: () => void }) {
  const [rows, setRows] = useState<PrefRow[]>([])
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    http.get<{ rows: PrefRow[] }>('/tax/preferences', { params: { year } })
      .then((r) => setRows(r.data.rows))
  }, [year])
  useEffect(() => { load() }, [load])

  const setAmount = (code: string, v: number | null) =>
    setRows((rs) => rs.map((r) => (r.code === code ? { ...r, amount: v ?? 0 } : r)))

  const save = async () => {
    setSaving(true)
    try {
      const items = rows.map((r) => ({ code: r.code, amount: r.amount }))
      const res = await http.put<{ rows: PrefRow[] }>('/tax/preferences', { report_year: year, items })
      setRows(res.data.rows); message.success('税收优惠已保存'); onSaved()
    } finally { setSaving(false) }
  }

  return (
    <>
      <Space style={{ marginBottom: 8 }} wrap>
        <Button type="primary" loading={saving} onClick={save}>保存税收优惠</Button>
        <span style={{ color: '#888' }}>按优惠事项填金额:免税/减计/加计→行22,所得减免→行25(季报23),减免所得税额→行31(季报28)。小型微利请用企业信息开关。</span>
      </Space>
      <Table rowKey="code" size="small" pagination={false} dataSource={rows} scroll={{ x: 620 }}
        columns={[
          { title: '类别', dataIndex: 'category_label', width: 170,
            render: (v: string, _r: PrefRow, i: number) =>
              (i === 0 || rows[i - 1].category_label !== v ? v : '') },
          { title: '优惠事项', dataIndex: 'name' },
          { title: '代码', dataIndex: 'code', width: 110 },
          { title: '金额', dataIndex: 'amount', width: 150, align: 'right' as const,
            render: (v: number, r: PrefRow) => (
              <InputNumber size="small" value={v} controls={false} precision={2} style={{ width: 130 }}
                onChange={(nv) => setAmount(r.code, nv as number | null)} />
            ) },
        ]} />
    </>
  )
}
