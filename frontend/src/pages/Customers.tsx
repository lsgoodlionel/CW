import { useEffect, useState, useCallback } from 'react'
import {
  Table, Button, Input, Space, Modal, Form, Tag, Popconfirm, message, Drawer, Descriptions,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { http, Customer } from '../api'

const FIELDS: { name: keyof Customer; label: string; required?: boolean }[] = [
  { name: 'name', label: '客户名称', required: true },
  { name: 'short_name', label: '简称' },
  { name: 'tax_number', label: '税号' },
  { name: 'address', label: '开票地址' },
  { name: 'phone', label: '开票电话' },
  { name: 'bank_name', label: '开户行' },
  { name: 'bank_account', label: '银行账号' },
  { name: 'contact_person', label: '联系人' },
  { name: 'contact_phone', label: '联系电话' },
  { name: 'email', label: '邮箱' },
  { name: 'note', label: '备注' },
]

interface HistItem { id: number; voucher_no: string; voucher_date: string; note: string; total_debit: number }

export default function Customers() {
  const navigate = useNavigate()
  const [list, setList] = useState<Customer[]>([])
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Customer | null>(null)
  const [form] = Form.useForm()
  const [detail, setDetail] = useState<Customer | null>(null)
  const [hist, setHist] = useState<HistItem[]>([])
  const [histSum, setHistSum] = useState(0)

  const load = useCallback(() => {
    setLoading(true)
    http.get<Customer[]>('/customers', { params: keyword ? { keyword } : {} })
      .then((r) => setList(r.data)).finally(() => setLoading(false))
  }, [keyword])
  useEffect(() => { load() }, [load])

  const openEdit = (c: Customer | null) => {
    setEditing(c)
    form.resetFields()
    if (c) form.setFieldsValue(c)
    setOpen(true)
  }

  const save = async () => {
    const v = await form.validateFields()
    if (editing) await http.put(`/customers/${editing.id}`, v)
    else await http.post('/customers', v)
    message.success('已保存'); setOpen(false); load()
  }

  const remove = (id: number) =>
    http.delete(`/customers/${id}`).then(() => { message.success('已删除/停用'); load() })

  const openDetail = (c: Customer) => {
    setDetail(c)
    http.get(`/customers/${c.id}/vouchers`).then((r) => {
      setHist(r.data.items); setHistSum(r.data.sum_debit)
    })
  }

  const columns = [
    { title: '名称', dataIndex: 'name', render: (v: string, r: Customer) => <a onClick={() => openDetail(r)}>{v}</a> },
    { title: '简称', dataIndex: 'short_name', width: 120 },
    { title: '税号', dataIndex: 'tax_number', width: 180 },
    { title: '联系人', dataIndex: 'contact_person', width: 100 },
    { title: '电话', dataIndex: 'contact_phone', width: 130 },
    { title: '状态', dataIndex: 'is_active', width: 80, render: (a: boolean) => a ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
    {
      title: '操作', width: 130, render: (_: unknown, r: Customer) => (
        <Space>
          <a onClick={() => openEdit(r)}>编辑</a>
          <Popconfirm title="删除/停用该客户?" onConfirm={() => remove(r.id)}>
            <a style={{ color: '#cf1322' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="content-card">
      <Space style={{ marginBottom: 16 }}>
        <Input.Search placeholder="搜索名称/简称/税号" allowClear style={{ width: 260 }}
          onSearch={setKeyword} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit(null)}>新增客户</Button>
      </Space>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={list}
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 家客户` }} />

      <Modal title={editing ? '编辑客户' : '新增客户'} open={open} onOk={save}
        onCancel={() => setOpen(false)} okText="保存" width={560}>
        <Form form={form} layout="vertical">
          {FIELDS.map((f) => (
            <Form.Item key={f.name} name={f.name} label={f.label}
              rules={f.required ? [{ required: true, message: `请填写${f.label}` }] : []}
              style={{ marginBottom: 12 }}>
              {f.name === 'note' ? <Input.TextArea rows={2} /> : <Input />}
            </Form.Item>
          ))}
        </Form>
      </Modal>

      <Drawer title={detail?.name} open={Boolean(detail)} onClose={() => setDetail(null)} width={640}>
        {detail && (
          <>
            <Descriptions bordered size="small" column={1} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="简称">{detail.short_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="税号">{detail.tax_number || '-'}</Descriptions.Item>
              <Descriptions.Item label="开票地址">{detail.address || '-'}</Descriptions.Item>
              <Descriptions.Item label="开票电话">{detail.phone || '-'}</Descriptions.Item>
              <Descriptions.Item label="开户行">{detail.bank_name || '-'}</Descriptions.Item>
              <Descriptions.Item label="银行账号">{detail.bank_account || '-'}</Descriptions.Item>
              <Descriptions.Item label="联系人">{detail.contact_person || '-'}</Descriptions.Item>
              <Descriptions.Item label="联系电话">{detail.contact_phone || '-'}</Descriptions.Item>
            </Descriptions>
            <h4>往来业务历史(借方合计 ¥{histSum.toLocaleString('zh-CN', { minimumFractionDigits: 2 })})</h4>
            <Table rowKey="id" size="small" pagination={false} dataSource={hist}
              locale={{ emptyText: '暂无关联凭证' }}
              columns={[
                { title: '凭证号', dataIndex: 'voucher_no', render: (v: string, r: HistItem) => <a onClick={() => navigate(`/vouchers/${r.id}`)}>{v}</a> },
                { title: '日期', dataIndex: 'voucher_date', width: 110 },
                { title: '摘要', dataIndex: 'note', ellipsis: true },
                { title: '金额', dataIndex: 'total_debit', width: 110, align: 'right', render: (v: number) => v.toLocaleString('zh-CN', { minimumFractionDigits: 2 }) },
              ]} />
          </>
        )}
      </Drawer>
    </div>
  )
}
