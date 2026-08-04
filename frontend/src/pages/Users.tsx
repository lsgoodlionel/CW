import { useEffect, useState, useCallback } from 'react'
import {
  Card, Tabs, Table, Tag, Button, Space, Modal, Form, Input, Select, Popconfirm,
  message, Checkbox, Switch,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { http, Employee } from '../api'

interface Role { id: number; name: string; note: string; is_system: boolean; perms: string[] }
interface UserRow {
  id: number; username: string; display_name: string; employee_id: number | null
  is_super_admin: boolean; is_active: boolean; role_ids: number[]; role_names: string[]
}
interface CatAction { action: string; label: string }
interface CatModule { module: string; label: string; actions: CatAction[] }

export default function Users() {
  return (
    <Card>
      <Tabs items={[
        { key: 'users', label: '用户管理', children: <UserTab /> },
        { key: 'roles', label: '角色与权限', children: <RoleTab /> },
      ]} />
    </Card>
  )
}

function UserTab() {
  const [users, setUsers] = useState<UserRow[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<UserRow | null>(null)
  const [form] = Form.useForm()
  const [pwOpen, setPwOpen] = useState<UserRow | null>(null)
  const [pwForm] = Form.useForm()

  const load = useCallback(() => {
    http.get<UserRow[]>('/users').then((r) => setUsers(r.data))
    http.get<Role[]>('/roles').then((r) => setRoles(r.data))
    http.get<Employee[]>('/personnel/employees').then((r) => setEmployees(r.data))
  }, [])
  useEffect(() => { load() }, [load])

  const openEdit = (u: UserRow | null) => {
    setEditing(u); form.resetFields()
    if (u) form.setFieldsValue(u)
    else form.setFieldsValue({ is_super_admin: false, role_ids: [] })
    setOpen(true)
  }
  const save = async () => {
    const v = await form.validateFields()
    if (editing) await http.put(`/users/${editing.id}`, v)
    else await http.post('/users', v)
    message.success('已保存'); setOpen(false); load()
  }
  const remove = (id: number) =>
    http.delete(`/users/${id}`).then(() => { message.success('已删除'); load() })
  const resetPw = async () => {
    const v = await pwForm.validateFields()
    await http.post(`/users/${pwOpen!.id}/reset-password`, v)
    message.success('密码已重置'); setPwOpen(null)
  }

  const columns = [
    { title: '用户名', dataIndex: 'username', width: 130 },
    { title: '姓名', dataIndex: 'display_name', width: 120, render: (v: string) => v || '-' },
    { title: '角色', dataIndex: 'role_names', render: (v: string[], r: UserRow) => r.is_super_admin ? <Tag color="red">超级管理员</Tag> : v.map((n) => <Tag key={n}>{n}</Tag>) },
    { title: '状态', dataIndex: 'is_active', width: 80, render: (a: boolean) => a ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
    {
      title: '操作', width: 180, render: (_: unknown, r: UserRow) => (
        <Space>
          <a onClick={() => openEdit(r)}>编辑</a>
          <a onClick={() => { setPwOpen(r); pwForm.resetFields() }}>重置密码</a>
          {r.username !== 'admin' && (
            <Popconfirm title="删除该用户?" onConfirm={() => remove(r.id)}>
              <a style={{ color: '#cf1322' }}>删除</a>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <>
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={() => openEdit(null)}>新建用户</Button>
      <Table rowKey="id" size="small" columns={columns} dataSource={users} pagination={false} />

      <Modal title={editing ? '编辑用户' : '新建用户'} open={open} onOk={save} onCancel={() => setOpen(false)} okText="保存">
        <Form form={form} layout="vertical">
          {!editing && <>
            <Form.Item name="username" label="用户名" rules={[{ required: true, min: 2 }]}><Input /></Form.Item>
            <Form.Item name="password" label="初始密码" rules={[{ required: true, min: 6 }]}><Input.Password /></Form.Item>
          </>}
          <Form.Item name="display_name" label="姓名"><Input /></Form.Item>
          <Form.Item name="employee_id" label="关联员工">
            <Select allowClear showSearch optionFilterProp="label"
              options={employees.map((e) => ({ value: e.id, label: e.name }))} />
          </Form.Item>
          <Form.Item name="role_ids" label="角色(可多选)">
            <Select mode="multiple" options={roles.map((r) => ({ value: r.id, label: r.name }))} />
          </Form.Item>
          {editing && <Form.Item name="is_active" label="启用" valuePropName="checked"><Switch /></Form.Item>}
          <Form.Item name="is_super_admin" label="超级管理员(拥有全部权限)" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={`重置密码 — ${pwOpen?.username}`} open={Boolean(pwOpen)} onOk={resetPw} onCancel={() => setPwOpen(null)} okText="重置">
        <Form form={pwForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, min: 6 }]}><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}

function RoleTab() {
  const [roles, setRoles] = useState<Role[]>([])
  const [catalog, setCatalog] = useState<CatModule[]>([])
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<Role | null>(null)
  const [form] = Form.useForm()
  const [perms, setPerms] = useState<Set<string>>(new Set())

  const load = useCallback(() => {
    http.get<Role[]>('/roles').then((r) => setRoles(r.data))
    http.get<CatModule[]>('/auth/permission-catalog').then((r) => setCatalog(r.data))
  }, [])
  useEffect(() => { load() }, [load])

  const openEdit = (r: Role | null) => {
    setEditing(r); form.resetFields()
    if (r) { form.setFieldsValue(r); setPerms(new Set(r.perms)) }
    else setPerms(new Set())
    setOpen(true)
  }
  const toggle = (perm: string, checked: boolean) => {
    setPerms((prev) => { const n = new Set(prev); checked ? n.add(perm) : n.delete(perm); return n })
  }
  const toggleModule = (m: CatModule, checked: boolean) => {
    setPerms((prev) => {
      const n = new Set(prev)
      m.actions.forEach((a) => { const p = `${m.module}:${a.action}`; checked ? n.add(p) : n.delete(p) })
      return n
    })
  }
  const save = async () => {
    const v = await form.validateFields()
    const body = { ...v, perms: Array.from(perms) }
    if (editing) await http.put(`/roles/${editing.id}`, body)
    else await http.post('/roles', body)
    message.success('已保存'); setOpen(false); load()
  }
  const remove = (id: number) =>
    http.delete(`/roles/${id}`).then(() => { message.success('已删除'); load() })

  return (
    <>
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={() => openEdit(null)}>新建角色</Button>
      <Table rowKey="id" size="small" pagination={false} dataSource={roles}
        columns={[
          { title: '角色', dataIndex: 'name', width: 150 },
          { title: '说明', dataIndex: 'note', ellipsis: true },
          { title: '权限数', dataIndex: 'perms', width: 90, render: (p: string[]) => <Tag color="blue">{p.length}</Tag> },
          {
            title: '操作', width: 120, render: (_: unknown, r: Role) => (
              <Space>
                <a onClick={() => openEdit(r)}>编辑</a>
                <Popconfirm title="删除该角色?" onConfirm={() => remove(r.id)}>
                  <a style={{ color: '#cf1322' }}>删除</a>
                </Popconfirm>
              </Space>
            ),
          },
        ]} />

      <Modal title={editing ? '编辑角色' : '新建角色'} open={open} onOk={save} onCancel={() => setOpen(false)} okText="保存" width={640}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="角色名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="note" label="说明"><Input /></Form.Item>
        </Form>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>权限设置(勾选允许的操作)</div>
        {catalog.map((m) => {
          const allChecked = m.actions.every((a) => perms.has(`${m.module}:${a.action}`))
          return (
            <div key={m.module} style={{ borderBottom: '1px solid #f0f0f0', padding: '6px 0' }}>
              <Checkbox checked={allChecked} onChange={(e) => toggleModule(m, e.target.checked)}>
                <b>{m.label}</b>
              </Checkbox>
              <span style={{ marginLeft: 16 }}>
                {m.actions.map((a) => {
                  const p = `${m.module}:${a.action}`
                  return (
                    <Checkbox key={p} checked={perms.has(p)} onChange={(e) => toggle(p, e.target.checked)}
                      style={{ marginLeft: 8 }}>{a.label}</Checkbox>
                  )
                })}
              </span>
            </div>
          )
        })}
      </Modal>
    </>
  )
}
