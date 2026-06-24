import { useEffect, useState } from 'react'
import {
  Table, Tag, Segmented, Button, Modal, Form, Input, Select, Space, Popconfirm, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { http, Account, Category, CATEGORY_LABEL } from '../api'

const CAT_COLOR: Record<Category, string> = {
  asset: 'blue', liability: 'orange', equity: 'purple', cost: 'cyan', profit: 'green',
}

export default function Accounts() {
  const [all, setAll] = useState<Account[]>([])
  const [filter, setFilter] = useState<string>('all')
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = () => {
    setLoading(true)
    http.get<Account[]>('/accounts').then((r) => setAll(r.data)).finally(() => setLoading(false))
  }
  useEffect(load, [])

  const data = filter === 'all' ? all : all.filter((a) => a.category === filter)

  const create = async () => {
    const v = await form.validateFields()
    await http.post('/accounts', v)
    message.success('科目已新增')
    setOpen(false); form.resetFields(); load()
  }

  const remove = (id: number) =>
    http.delete(`/accounts/${id}`).then(() => { message.success('已停用/删除'); load() })

  const columns = [
    { title: '编码', dataIndex: 'code', width: 100 },
    { title: '科目名称', dataIndex: 'name' },
    {
      title: '类别', dataIndex: 'category', width: 110,
      render: (c: Category) => <Tag color={CAT_COLOR[c]}>{CATEGORY_LABEL[c]}</Tag>,
    },
    {
      title: '余额方向', dataIndex: 'direction', width: 100,
      render: (d: string) => (d === 'debit' ? '借' : '贷'),
    },
    {
      title: '状态', dataIndex: 'is_active', width: 90,
      render: (a: boolean) => (a ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '操作', width: 90,
      render: (_: unknown, r: Account) => (
        <Popconfirm title="停用/删除该科目?" onConfirm={() => remove(r.id)}>
          <a style={{ color: '#cf1322' }}>停用</a>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="content-card">
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Segmented value={filter} onChange={(v) => setFilter(v as string)}
          options={[
            { label: '全部', value: 'all' },
            { label: '资产', value: 'asset' },
            { label: '负债', value: 'liability' },
            { label: '权益', value: 'equity' },
            { label: '成本', value: 'cost' },
            { label: '损益', value: 'profit' },
          ]} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>新增科目</Button>
      </Space>
      <Table rowKey="id" loading={loading} columns={columns} dataSource={data}
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 个科目` }} />

      <Modal title="新增会计科目" open={open} onOk={create} onCancel={() => setOpen(false)} okText="保存">
        <Form form={form} layout="vertical" initialValues={{ category: 'asset', direction: 'debit' }}>
          <Form.Item name="code" label="科目编码" rules={[{ required: true }]}>
            <Input placeholder="如 6602" />
          </Form.Item>
          <Form.Item name="name" label="科目名称" rules={[{ required: true }]}>
            <Input placeholder="如 管理费用" />
          </Form.Item>
          <Form.Item name="category" label="类别" rules={[{ required: true }]}>
            <Select options={Object.entries(CATEGORY_LABEL).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item name="direction" label="余额方向" rules={[{ required: true }]}>
            <Select options={[{ value: 'debit', label: '借方' }, { value: 'credit', label: '贷方' }]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
