import { useCallback, useEffect, useState } from 'react'
import {
  Card, Tabs, Table, Tag, Button, Space, Modal, Form, Input, Select, Popconfirm,
  message, Switch, Empty,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { http } from '../api'

// 平台管理返回结构(本地 interface,后端契约见页面头部说明,不改生成文件)
interface PlatformTenant {
  id: number
  name: string
  code: string
  is_active: boolean
  note: string
  created_at: string | null
  member_count: number
}

interface PlatformMember {
  id: number
  user_id: number
  username: string
  display_name: string
  is_tenant_admin: boolean
}

// 新建租户表单(可选同时创建租户管理员)
interface TenantFormValues {
  name: string
  code?: string
  note?: string
  admin_username?: string
  admin_password?: string
  admin_display_name?: string
}

interface TenantEditFormValues {
  name: string
  note?: string
}

interface MemberFormValues {
  username: string
  display_name?: string
  password?: string
  is_tenant_admin?: boolean
}

export default function PlatformAdmin() {
  // 「管理成员」跳转:由租户页签写入,成员页签据此预选租户
  const [activeTab, setActiveTab] = useState('tenants')
  const [focusTenantId, setFocusTenantId] = useState<number | null>(null)

  const manageMembers = useCallback((tenantId: number) => {
    setFocusTenantId(tenantId)
    setActiveTab('members')
  }, [])

  return (
    <Card>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'tenants', label: '租户管理', children: <TenantTab onManageMembers={manageMembers} /> },
          { key: 'members', label: '成员管理', children: <MemberTab focusTenantId={focusTenantId} /> },
        ]}
      />
    </Card>
  )
}

interface TenantTabProps {
  onManageMembers: (tenantId: number) => void
}

function TenantTab({ onManageMembers }: TenantTabProps) {
  const [tenants, setTenants] = useState<PlatformTenant[]>([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<PlatformTenant | null>(null)
  const [form] = Form.useForm<TenantFormValues>()
  const [editForm] = Form.useForm<TenantEditFormValues>()

  const load = useCallback(() => {
    http.get<PlatformTenant[]>('/platform/tenants').then((r) => setTenants(r.data))
  }, [])
  useEffect(() => { load() }, [load])

  const openCreate = () => { form.resetFields(); setOpen(true) }
  const create = async () => {
    const values = await form.validateFields()
    await http.post<PlatformTenant>('/platform/tenants', values)
    message.success('租户已创建')
    setOpen(false); load()
  }

  const openEdit = (tenant: PlatformTenant) => {
    setEditing(tenant)
    editForm.resetFields()
    editForm.setFieldsValue({ name: tenant.name, note: tenant.note })
  }
  const saveEdit = async () => {
    const values = await editForm.validateFields()
    await http.put<PlatformTenant>(`/platform/tenants/${editing!.id}`, values)
    message.success('已保存'); setEditing(null); load()
  }

  const toggleActive = async (tenant: PlatformTenant) => {
    await http.put<PlatformTenant>(`/platform/tenants/${tenant.id}`, { is_active: !tenant.is_active })
    message.success(tenant.is_active ? '已停用' : '已启用'); load()
  }

  const columns = [
    { title: '名称', dataIndex: 'name', width: 180 },
    { title: '编码', dataIndex: 'code', width: 140, render: (v: string) => v || '-' },
    {
      title: '状态', dataIndex: 'is_active', width: 90,
      render: (active: boolean) => active ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
    },
    {
      title: '成员数', dataIndex: 'member_count', width: 90,
      render: (count: number) => <Tag color="blue">{count}</Tag>,
    },
    {
      title: '创建时间', dataIndex: 'created_at', width: 180,
      render: (v: string | null) => v || '-',
    },
    {
      title: '操作', width: 240, render: (_: unknown, tenant: PlatformTenant) => (
        <Space>
          <a onClick={() => openEdit(tenant)}>编辑</a>
          <a onClick={() => onManageMembers(tenant.id)}>管理成员</a>
          <Popconfirm
            title={tenant.is_active ? '停用该租户?' : '启用该租户?'}
            onConfirm={() => toggleActive(tenant)}
          >
            <a style={{ color: tenant.is_active ? '#cf1322' : '#389e0d' }}>
              {tenant.is_active ? '停用' : '启用'}
            </a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={openCreate}>新建租户</Button>
      <Table rowKey="id" size="small" columns={columns} dataSource={tenants} pagination={false} />

      <Modal title="新建租户" open={open} onOk={create} onCancel={() => setOpen(false)} okText="创建">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="租户名称" rules={[{ required: true, message: '请输入租户名称' }]}><Input /></Form.Item>
          <Form.Item name="code" label="编码"><Input /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea rows={2} /></Form.Item>
          <div style={{ fontWeight: 600, margin: '4px 0 8px' }}>同时创建租户管理员(可选)</div>
          <Form.Item name="admin_username" label="管理员用户名"><Input /></Form.Item>
          <Form.Item name="admin_password" label="管理员密码"><Input.Password /></Form.Item>
          <Form.Item name="admin_display_name" label="管理员姓名"><Input /></Form.Item>
        </Form>
      </Modal>

      <Modal title="编辑租户" open={Boolean(editing)} onOk={saveEdit} onCancel={() => setEditing(null)} okText="保存">
        <Form form={editForm} layout="vertical">
          <Form.Item name="name" label="租户名称" rules={[{ required: true, message: '请输入租户名称' }]}><Input /></Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}

interface MemberTabProps {
  focusTenantId: number | null
}

function MemberTab({ focusTenantId }: MemberTabProps) {
  const [tenants, setTenants] = useState<PlatformTenant[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(null)
  const [members, setMembers] = useState<PlatformMember[]>([])
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm<MemberFormValues>()

  useEffect(() => {
    http.get<PlatformTenant[]>('/platform/tenants').then((r) => setTenants(r.data))
  }, [])

  // 从租户页签「管理成员」跳转过来时,预选对应租户
  useEffect(() => {
    if (focusTenantId != null) setSelectedTenantId(focusTenantId)
  }, [focusTenantId])

  const loadMembers = useCallback((tenantId: number) => {
    http.get<PlatformMember[]>(`/platform/tenants/${tenantId}/members`).then((r) => setMembers(r.data))
  }, [])
  useEffect(() => {
    if (selectedTenantId != null) loadMembers(selectedTenantId)
    else setMembers([])
  }, [selectedTenantId, loadMembers])

  const openCreate = () => { form.resetFields(); form.setFieldsValue({ is_tenant_admin: false }); setOpen(true) }
  const create = async () => {
    const values = await form.validateFields()
    await http.post<PlatformMember>(`/platform/tenants/${selectedTenantId}/members`, values)
    message.success('成员已添加'); setOpen(false); loadMembers(selectedTenantId!)
  }

  const toggleAdmin = async (member: PlatformMember) => {
    await http.put<PlatformMember>(`/platform/members/${member.id}`, { is_tenant_admin: !member.is_tenant_admin })
    message.success('已更新'); loadMembers(selectedTenantId!)
  }

  const remove = async (member: PlatformMember) => {
    await http.delete(`/platform/members/${member.id}`)
    message.success('已移除'); loadMembers(selectedTenantId!)
  }

  const columns = [
    { title: '用户名', dataIndex: 'username', width: 150 },
    { title: '显示名', dataIndex: 'display_name', width: 150, render: (v: string) => v || '-' },
    {
      title: '租户管理员', dataIndex: 'is_tenant_admin', width: 120,
      render: (isAdmin: boolean) => isAdmin ? <Tag color="gold">租户管理员</Tag> : <Tag>成员</Tag>,
    },
    {
      title: '操作', width: 200, render: (_: unknown, member: PlatformMember) => (
        <Space>
          <a onClick={() => toggleAdmin(member)}>
            {member.is_tenant_admin ? '取消管理员' : '设为管理员'}
          </a>
          <Popconfirm title="从该租户移除此成员?" onConfirm={() => remove(member)}>
            <a style={{ color: '#cf1322' }}>移除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <Space style={{ marginBottom: 12 }}>
        <span>选择租户:</span>
        <Select
          style={{ width: 260 }}
          placeholder="请选择租户"
          value={selectedTenantId ?? undefined}
          onChange={(value) => setSelectedTenantId(value)}
          showSearch
          optionFilterProp="label"
          options={tenants.map((t) => ({ value: t.id, label: t.name }))}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          disabled={selectedTenantId == null}
          onClick={openCreate}
        >添加成员</Button>
      </Space>

      {selectedTenantId == null
        ? <Empty description="请先选择一个租户" />
        : <Table rowKey="id" size="small" columns={columns} dataSource={members} pagination={false} />}

      <Modal title="添加成员" open={open} onOk={create} onCancel={() => setOpen(false)} okText="添加">
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}><Input /></Form.Item>
          <p style={{ color: '#888', marginTop: -8 }}>用户名已存在则关联该全局用户;不存在则以下方密码新建全局用户。</p>
          <Form.Item name="display_name" label="显示名(新建用户时使用)"><Input /></Form.Item>
          <Form.Item name="password" label="密码(新建用户时使用)"><Input.Password /></Form.Item>
          <Form.Item name="is_tenant_admin" label="设为租户管理员" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}
