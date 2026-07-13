import { useEffect, useMemo, useState } from 'react'
import {
  Card, Form, DatePicker, Input, Button, Table, Select, InputNumber, Space,
  message, Upload, Tag, Popconfirm, Divider, Typography,
} from 'antd'
import { DeleteOutlined, PlusOutlined, UploadOutlined, SaveOutlined, EyeOutlined } from '@ant-design/icons'
import { useNavigate, useParams } from 'react-router-dom'
import dayjs from 'dayjs'
import {
  http, Account, Entry, Attachment, VoucherDetail, Customer, LinkedVoucher,
  CATEGORY_LABEL,
} from '../api'
import AttachmentPreview from '../components/AttachmentPreview'
import VoucherLinks from '../components/VoucherLinks'

const { Text } = Typography
const emptyEntry = (): Entry => ({ summary: '', account_id: 0, sub_account: '', debit: 0, credit: 0 })
const yuan = (n: number) => n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const KIND_LABEL: Record<string, string> = { invoice: '发票', receipt: '回单', other: '其他' }

export default function VoucherEdit() {
  const { id } = useParams()
  const isEdit = Boolean(id)
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [entries, setEntries] = useState<Entry[]>([emptyEntry(), emptyEntry()])
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [links, setLinks] = useState<LinkedVoucher[]>([])
  const [saving, setSaving] = useState(false)
  const [uploadKind, setUploadKind] = useState('invoice')
  const [previewing, setPreviewing] = useState<Attachment | null>(null)

  useEffect(() => {
    http.get<Account[]>('/accounts', { params: { active_only: true } })
      .then((r) => setAccounts(r.data))
    http.get<Customer[]>('/customers', { params: { active_only: true } })
      .then((r) => setCustomers(r.data))
  }, [])

  useEffect(() => {
    if (!isEdit) return
    http.get<VoucherDetail>(`/vouchers/${id}`).then((r) => {
      const v = r.data
      form.setFieldsValue({
        voucher_date: dayjs(v.voucher_date), note: v.note,
        voucher_no: v.voucher_no, customer_id: v.customer_id ?? undefined,
      })
      setEntries(v.entries.length ? v.entries : [emptyEntry(), emptyEntry()])
      setAttachments(v.attachments)
      setLinks(v.links)
    })
  }, [id, isEdit, form])

  const accountOptions = useMemo(() => {
    const groups: Record<string, { label: string; options: { label: string; value: number }[] }> = {}
    accounts.forEach((a) => {
      const g = groups[a.category] || (groups[a.category] = { label: CATEGORY_LABEL[a.category], options: [] })
      g.options.push({ label: `${a.code} ${a.name}`, value: a.id })
    })
    return Object.values(groups)
  }, [accounts])

  const totalDebit = entries.reduce((s, e) => s + (Number(e.debit) || 0), 0)
  const totalCredit = entries.reduce((s, e) => s + (Number(e.credit) || 0), 0)
  const balanced = totalDebit === totalCredit && totalDebit > 0

  const updateEntry = (idx: number, patch: Partial<Entry>) =>
    setEntries((prev) => prev.map((e, i) => (i === idx ? { ...e, ...patch } : e)))

  const columns = [
    {
      title: '摘要', dataIndex: 'summary',
      render: (_: unknown, _r: Entry, i: number) => (
        <Input value={entries[i].summary} placeholder="摘要"
          onChange={(e) => updateEntry(i, { summary: e.target.value })} />
      ),
    },
    {
      title: '会计科目', dataIndex: 'account_id', width: 240,
      render: (_: unknown, _r: Entry, i: number) => (
        <Select showSearch value={entries[i].account_id || undefined} placeholder="选择科目"
          style={{ width: '100%' }} options={accountOptions}
          filterOption={(input, opt) => (opt?.label ?? '').toString().includes(input)}
          onChange={(v) => updateEntry(i, { account_id: v })} />
      ),
    },
    {
      title: '明细科目', dataIndex: 'sub_account', width: 130,
      render: (_: unknown, _r: Entry, i: number) => (
        <Input value={entries[i].sub_account} placeholder="可选"
          onChange={(e) => updateEntry(i, { sub_account: e.target.value })} />
      ),
    },
    {
      title: '借方金额', dataIndex: 'debit', width: 150,
      render: (_: unknown, _r: Entry, i: number) => (
        <InputNumber value={entries[i].debit || null} min={0} precision={2} style={{ width: '100%' }}
          controls={false} placeholder="0.00"
          onChange={(v) => updateEntry(i, { debit: Number(v) || 0, credit: 0 })} />
      ),
    },
    {
      title: '贷方金额', dataIndex: 'credit', width: 150,
      render: (_: unknown, _r: Entry, i: number) => (
        <InputNumber value={entries[i].credit || null} min={0} precision={2} style={{ width: '100%' }}
          controls={false} placeholder="0.00"
          onChange={(v) => updateEntry(i, { credit: Number(v) || 0, debit: 0 })} />
      ),
    },
    {
      title: '', width: 50,
      render: (_: unknown, _r: Entry, i: number) => (
        <Button type="text" danger icon={<DeleteOutlined />} disabled={entries.length <= 1}
          onClick={() => setEntries((prev) => prev.filter((_, idx) => idx !== i))} />
      ),
    },
  ]

  const save = async () => {
    const values = await form.validateFields()
    const valid = entries.filter((e) => e.account_id && (e.debit > 0 || e.credit > 0))
    if (valid.length < 1) return message.error('请至少填写一条有效分录')
    if (!balanced) return message.error(`借贷不平衡:借 ${yuan(totalDebit)} ≠ 贷 ${yuan(totalCredit)}`)

    const payload = {
      voucher_no: values.voucher_no || '',
      voucher_date: values.voucher_date.format('YYYY-MM-DD'),
      note: values.note || '',
      customer_id: values.customer_id ?? null,
      status: 'posted',
      entries: valid.map((e) => ({
        summary: e.summary, account_id: e.account_id, sub_account: e.sub_account,
        debit: e.debit, credit: e.credit,
      })),
    }
    setSaving(true)
    try {
      const res = isEdit
        ? await http.put<VoucherDetail>(`/vouchers/${id}`, payload)
        : await http.post<VoucherDetail>('/vouchers', payload)
      message.success('保存成功')
      if (!isEdit) navigate(`/vouchers/${res.data.id}`, { replace: true })
    } finally {
      setSaving(false)
    }
  }

  const uploadProps = {
    showUploadList: false,
    customRequest: async (opt: { file: unknown; onSuccess?: (b: unknown) => void; onError?: (e: Error) => void }) => {
      if (!isEdit) { message.warning('请先保存凭证,再上传附件'); return }
      const fd = new FormData()
      fd.append('file', opt.file as Blob)
      fd.append('kind', uploadKind)
      try {
        const r = await http.post<Attachment>(`/vouchers/${id}/attachments`, fd)
        setAttachments((prev) => [...prev, r.data])
        message.success('附件已上传')
        opt.onSuccess?.({})
      } catch (e) {
        opt.onError?.(e as Error)
      }
    },
  }

  const removeAttachment = (aid: number) =>
    http.delete(`/attachments/${aid}`).then(() => {
      setAttachments((prev) => prev.filter((a) => a.id !== aid))
      message.success('附件已删除')
    })

  return (
    <Card title={isEdit ? '编辑凭证' : '新建凭证'}
      extra={<Button onClick={() => navigate('/vouchers')}>返回列表</Button>}>
      <Form form={form} layout="inline" initialValues={{ voucher_date: dayjs() }}
        style={{ marginBottom: 16, rowGap: 12 }}>
        <Form.Item name="voucher_date" label="凭证日期" rules={[{ required: true }]}>
          <DatePicker />
        </Form.Item>
        <Form.Item name="voucher_no" label="凭证号">
          <Input placeholder="留空自动生成" allowClear />
        </Form.Item>
        <Form.Item name="customer_id" label="客户">
          <Select allowClear showSearch placeholder="关联客户(可选)" style={{ width: 220 }}
            optionFilterProp="label"
            options={customers.map((c) => ({
              value: c.id, label: c.short_name ? `${c.name}(${c.short_name})` : c.name,
            }))} />
        </Form.Item>
        <Form.Item name="note" label="摘要" style={{ flex: 1, minWidth: 200 }}>
          <Input placeholder="本张凭证摘要" allowClear />
        </Form.Item>
      </Form>

      <Table rowKey={(_, i) => String(i)} columns={columns} dataSource={entries}
        pagination={false} size="small"
        summary={() => (
          <Table.Summary fixed>
            <Table.Summary.Row>
              <Table.Summary.Cell index={0} colSpan={3}>
                <Text strong>合计</Text>
                {' '}
                <Tag color={balanced ? 'green' : 'red'}>
                  {balanced ? '借贷平衡' : '借贷不平衡'}
                </Tag>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={3}>
                <Text strong>{yuan(totalDebit)}</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={4}>
                <Text strong>{yuan(totalCredit)}</Text>
              </Table.Summary.Cell>
              <Table.Summary.Cell index={5} />
            </Table.Summary.Row>
          </Table.Summary>
        )}
      />

      <Space style={{ marginTop: 12 }}>
        <Button icon={<PlusOutlined />} onClick={() => setEntries((p) => [...p, emptyEntry()])}>
          增加分录
        </Button>
        <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>
          保存凭证
        </Button>
      </Space>

      <Divider />
      <h3>附件凭证(发票 / 回单)</h3>
      {!isEdit && <Text type="secondary">保存凭证后即可上传附件。</Text>}
      {isEdit && (
        <>
          <Space style={{ marginBottom: 12 }}>
            <Select value={uploadKind} style={{ width: 120 }} onChange={setUploadKind}
              options={[
                { value: 'invoice', label: '发票' },
                { value: 'receipt', label: '回单' },
                { value: 'other', label: '其他' },
              ]} />
            <Upload {...uploadProps}>
              <Button icon={<UploadOutlined />}>上传附件</Button>
            </Upload>
          </Space>
          <Table rowKey="id" size="small" pagination={false} dataSource={attachments}
            locale={{ emptyText: '暂无附件' }}
            columns={[
              { title: '类型', dataIndex: 'kind', width: 80, render: (k: string) => <Tag>{KIND_LABEL[k]}</Tag> },
              {
                title: '文件名', dataIndex: 'original_name',
                render: (name: string, r: Attachment) => (
                  <a onClick={() => setPreviewing(r)}>{name}</a>
                ),
              },
              { title: '大小', dataIndex: 'size_bytes', width: 110, render: (b: number) => `${(b / 1024).toFixed(1)} KB` },
              {
                title: '操作', width: 110,
                render: (_: unknown, r: Attachment) => (
                  <Space>
                    <Button type="text" icon={<EyeOutlined />} onClick={() => setPreviewing(r)}>预览</Button>
                    <Popconfirm title="删除该附件?" onConfirm={() => removeAttachment(r.id)}>
                      <Button type="text" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  </Space>
                ),
              },
            ]} />
        </>
      )}

      <Divider />
      <h3>凭证关联(预收款 / 挂账 / 核销 / 应收款)</h3>
      {!isEdit && <Text type="secondary">保存凭证后即可添加关联。</Text>}
      {isEdit && (
        <VoucherLinks voucherId={Number(id)} links={links} onChange={setLinks} />
      )}

      <AttachmentPreview attachment={previewing} open={Boolean(previewing)}
        onClose={() => setPreviewing(null)} />
    </Card>
  )
}
