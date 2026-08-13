import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Segmented, Button, Modal, Form, Input, Select, Space, Popconfirm,
  message, Upload, Tooltip,
} from 'antd'
import {
  PlusOutlined, DownloadOutlined, UploadOutlined, FileExcelOutlined,
} from '@ant-design/icons'
import { http, AccountTreeNode, SubAccount, CATEGORY_LABEL, withToken } from '../api'

const CAT_COLOR: Record<string, string> = {
  asset: 'blue', liability: 'orange', equity: 'purple', cost: 'cyan', profit: 'green',
}

export default function Accounts() {
  const [tree, setTree] = useState<AccountTreeNode[]>([])
  const [filter, setFilter] = useState<string>('all')
  const [loading, setLoading] = useState(false)

  // 一级科目新增
  const [accOpen, setAccOpen] = useState(false)
  const [accForm] = Form.useForm()
  // 二级科目新增/编辑
  const [subOpen, setSubOpen] = useState(false)
  const [subForm] = Form.useForm()
  const [subParent, setSubParent] = useState<AccountTreeNode | null>(null)
  const [subEditing, setSubEditing] = useState<SubAccount | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    http.get<AccountTreeNode[]>('/accounts/tree')
      .then((r) => setTree(r.data)).finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const data = filter === 'all' ? tree : tree.filter((a) => a.category === filter)

  const createAccount = async () => {
    const v = await accForm.validateFields()
    await http.post('/accounts', v)
    message.success('一级科目已新增'); setAccOpen(false); accForm.resetFields(); load()
  }

  const removeAccount = (id: number) =>
    http.delete(`/accounts/${id}`).then(() => { message.success('已停用/删除'); load() })

  const openSub = (parent: AccountTreeNode, sub: SubAccount | null) => {
    setSubParent(parent); setSubEditing(sub)
    subForm.resetFields()
    if (sub) subForm.setFieldsValue({ name: sub.name, note: sub.note })
    setSubOpen(true)
  }

  const saveSub = async () => {
    const v = await subForm.validateFields()
    if (subEditing) await http.put(`/accounts/subaccounts/${subEditing.id}`, v)
    else await http.post(`/accounts/${subParent!.id}/subaccounts`, v)
    message.success('二级科目已保存'); setSubOpen(false); load()
  }

  const removeSub = (id: number) =>
    http.delete(`/accounts/subaccounts/${id}`).then(() => { message.success('已停用/删除'); load() })

  const importProps = {
    showUploadList: false,
    accept: '.xlsx',
    customRequest: async (opt: { file: unknown; onSuccess?: (b: unknown) => void }) => {
      const fd = new FormData()
      fd.append('file', opt.file as Blob)
      const r = await http.post('/accounts/subaccounts/import', fd)
      const d = r.data
      message.success(`导入完成:新增 ${d.created}、跳过 ${d.skipped}、失败 ${d.errors}`)
      if (d.messages?.length) Modal.info({ title: '导入提示', content: d.messages.join('\n') })
      opt.onSuccess?.({}); load()
    },
  }

  const expandedRowRender = (account: AccountTreeNode) => (
    <div style={{ padding: '4px 0 4px 24px' }}>
      <Button size="small" type="dashed" icon={<PlusOutlined />}
        style={{ marginBottom: 8 }} onClick={() => openSub(account, null)}>
        新增二级科目
      </Button>
      <Table<SubAccount>
        rowKey="id" size="small" pagination={false}
        dataSource={account.sub_accounts}
        locale={{ emptyText: '暂无二级科目,可新增或凭证录入时自动创建' }}
        columns={[
          { title: '二级编码', dataIndex: 'code', width: 120 },
          { title: '二级科目名称', dataIndex: 'name' },
          { title: '备注', dataIndex: 'note', ellipsis: true, render: (v: string) => v || '-' },
          {
            title: '状态', dataIndex: 'is_active', width: 80,
            render: (a: boolean) => (a ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
          },
          {
            title: '操作', width: 120,
            render: (_: unknown, s: SubAccount) => (
              <Space>
                <a onClick={() => openSub(account, s)}>编辑</a>
                <Popconfirm title="停用/删除该二级科目?" onConfirm={() => removeSub(s.id)}>
                  <a style={{ color: '#cf1322' }}>删除</a>
                </Popconfirm>
              </Space>
            ),
          },
        ]} />
    </div>
  )

  const columns = [
    { title: '一级编码', dataIndex: 'code', width: 100 },
    { title: '一级科目名称', dataIndex: 'name' },
    {
      title: '类别', dataIndex: 'category', width: 100,
      render: (c: string) => <Tag color={CAT_COLOR[c]}>{CATEGORY_LABEL[c]}</Tag>,
    },
    { title: '方向', dataIndex: 'direction', width: 70, render: (d: string) => (d === 'debit' ? '借' : '贷') },
    {
      title: '二级科目', dataIndex: 'sub_accounts', width: 100,
      render: (subs: SubAccount[]) => subs.length
        ? <Tag color="geekblue">{subs.length} 个</Tag> : <span style={{ color: '#bbb' }}>无</span>,
    },
    {
      title: '状态', dataIndex: 'is_active', width: 80,
      render: (a: boolean) => (a ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>),
    },
    {
      title: '操作', width: 90,
      render: (_: unknown, r: AccountTreeNode) => (
        <Popconfirm title="停用/删除该一级科目?" onConfirm={() => removeAccount(r.id)}>
          <a style={{ color: '#cf1322' }}>停用</a>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="content-card">
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%', flexWrap: 'wrap' }}>
        <Segmented value={filter} onChange={(v) => setFilter(v as string)}
          options={[
            { label: '全部', value: 'all' }, { label: '资产', value: 'asset' },
            { label: '负债', value: 'liability' }, { label: '权益', value: 'equity' },
            { label: '成本', value: 'cost' }, { label: '损益', value: 'profit' },
          ]} />
        <Space wrap>
          <Tooltip title="下载二级科目导入模板">
            <Button icon={<FileExcelOutlined />}
              onClick={() => window.open(withToken('/api/accounts/subaccounts/template'), '_blank')}>
              导入模板
            </Button>
          </Tooltip>
          <Upload {...importProps}>
            <Button icon={<UploadOutlined />}>导入二级科目</Button>
          </Upload>
          <Button icon={<DownloadOutlined />}
            onClick={() => window.open(withToken('/api/accounts/export-excel'), '_blank')}>
            导出全部科目
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setAccOpen(true)}>新增一级科目</Button>
        </Space>
      </Space>

      <Table<AccountTreeNode>
        rowKey="id" loading={loading} columns={columns} dataSource={data}
        expandable={{ expandedRowRender, rowExpandable: () => true }}
        pagination={{ pageSize: 30, showTotal: (t) => `共 ${t} 个一级科目` }} />

      {/* 新增一级科目 */}
      <Modal title="新增一级科目" open={accOpen} onOk={createAccount}
        onCancel={() => setAccOpen(false)} okText="保存">
        <Form form={accForm} layout="vertical" initialValues={{ category: 'asset', direction: 'debit' }}>
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

      {/* 新增/编辑二级科目 */}
      <Modal title={subEditing ? '编辑二级科目' : `新增二级科目 — ${subParent?.name}`}
        open={subOpen} onOk={saveSub} onCancel={() => setSubOpen(false)} okText="保存">
        <Form form={subForm} layout="vertical">
          <Form.Item name="name" label="二级科目名称" rules={[{ required: true, message: '请填写名称' }]}>
            <Input placeholder="如 办公费" />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="可选" />
          </Form.Item>
          {!subEditing && (
            <div style={{ color: '#999' }}>编码将按一级科目「{subParent?.code}」自动延续生成。</div>
          )}
        </Form>
      </Modal>
    </div>
  )
}
