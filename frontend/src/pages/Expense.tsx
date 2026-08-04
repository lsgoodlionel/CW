import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Button, Space, Modal, Form, Input, Select, InputNumber,
  Popconfirm, message, Segmented, Timeline, Divider,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  http, ExpenseClaim, Account, Employee, OrgUnit,
  EXPENSE_STATUS_LABEL, WF_STATUS_LABEL,
} from '../api'

const STATUS_COLOR: Record<string, string> = {
  draft: 'default', pending: 'processing', approved: 'success', rejected: 'error', paid: 'gold',
}

export default function Expense() {
  const navigate = useNavigate()
  const [claims, setClaims] = useState<ExpenseClaim[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [units, setUnits] = useState<OrgUnit[]>([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [loading, setLoading] = useState(false)

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<ExpenseClaim | null>(null)
  const [form] = Form.useForm()
  const [detail, setDetail] = useState<ExpenseClaim | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    const params = statusFilter === 'all' ? {} : { status: statusFilter }
    http.get<ExpenseClaim[]>('/expense/claims', { params })
      .then((r) => setClaims(r.data)).finally(() => setLoading(false))
  }, [statusFilter])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    http.get<Account[]>('/accounts', { params: { active_only: true } }).then((r) => setAccounts(r.data.filter((a) => a.category === 'profit' || a.category === 'cost')))
    http.get<Employee[]>('/personnel/employees').then((r) => setEmployees(r.data))
    http.get<OrgUnit[]>('/personnel/org-units').then((r) => setUnits(r.data))
  }, [])

  const openEdit = (c: ExpenseClaim | null) => {
    setEditing(c); form.resetFields()
    if (c) form.setFieldsValue({ ...c, items: c.items })
    else form.setFieldsValue({ items: [{ amount: 0 }] })
    setOpen(true)
  }
  const save = async () => {
    const v = await form.validateFields()
    if (editing) await http.put(`/expense/claims/${editing.id}`, v)
    else await http.post('/expense/claims', v)
    message.success('已保存'); setOpen(false); load()
  }
  const submit = (id: number) =>
    http.post(`/expense/claims/${id}/submit`).then(() => { message.success('已提交审批'); load() })
  const remove = (id: number) =>
    http.delete(`/expense/claims/${id}`).then(() => { message.success('已删除'); load() })
  const makeVoucher = (id: number) =>
    http.post(`/expense/claims/${id}/make-voucher`).then((r) => {
      message.success(`已生成凭证 ${r.data.voucher_no}`); load()
    })

  const accOpts = accounts.map((a) => ({ value: a.id, label: `${a.code} ${a.name}` }))

  const columns = [
    { title: '单号', dataIndex: 'claim_no', width: 140,
      render: (v: string, r: ExpenseClaim) => <a onClick={() => setDetail(r)}>{v}</a> },
    { title: '申请人', dataIndex: 'applicant_name', width: 90, render: (v: string) => v || '-' },
    { title: '事由', dataIndex: 'reason', ellipsis: true },
    { title: '金额', dataIndex: 'total_amount', width: 110, align: 'right' as const,
      render: (v: number) => `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` },
    { title: '状态', dataIndex: 'status', width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s]}>{EXPENSE_STATUS_LABEL[s] || s}</Tag> },
    { title: '凭证', dataIndex: 'voucher_no', width: 130,
      render: (v: string, r: ExpenseClaim) => v ? <a onClick={() => navigate(`/vouchers/${r.voucher_id}`)}>{v}</a> : '-' },
    {
      title: '操作', width: 190, render: (_: unknown, r: ExpenseClaim) => (
        <Space wrap>
          {(r.status === 'draft' || r.status === 'rejected') && <>
            <a onClick={() => openEdit(r)}>编辑</a>
            <a onClick={() => submit(r.id)}>提交</a>
            <Popconfirm title="删除该报销单?" onConfirm={() => remove(r.id)}>
              <a style={{ color: '#cf1322' }}>删除</a>
            </Popconfirm>
          </>}
          {r.status === 'approved' && <a onClick={() => makeVoucher(r.id)}>生成凭证</a>}
          <a onClick={() => setDetail(r)}>详情</a>
        </Space>
      ),
    },
  ]

  return (
    <div className="content-card">
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <Segmented value={statusFilter} onChange={(v) => setStatusFilter(v as string)}
          options={[{ label: '全部', value: 'all' },
            ...Object.entries(EXPENSE_STATUS_LABEL).map(([value, label]) => ({ value, label }))]} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit(null)}>新建报销单</Button>
      </Space>
      <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={claims}
        pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 单` }} />

      {/* 新建/编辑报销单 */}
      <Modal title={editing ? '编辑报销单' : '新建报销单'} open={open} onOk={save}
        onCancel={() => setOpen(false)} okText="保存" width={760}>
        <Form form={form} layout="vertical">
          <Space wrap>
            <Form.Item name="applicant_employee_id" label="申请人">
              <Select allowClear showSearch style={{ width: 180 }} optionFilterProp="label"
                options={employees.map((e) => ({ value: e.id, label: e.name }))} />
            </Form.Item>
            <Form.Item name="org_unit_id" label="部门">
              <Select allowClear style={{ width: 180 }}
                options={units.map((u) => ({ value: u.id, label: u.name }))} />
            </Form.Item>
            <Form.Item name="reason" label="报销事由" style={{ flex: 1, minWidth: 240 }}>
              <Input placeholder="如 7月市场部差旅及办公费用" />
            </Form.Item>
          </Space>
          <Divider orientation="left" plain>费用明细</Divider>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline" style={{ display: 'flex', marginBottom: 8 }} wrap>
                    <Form.Item name={[field.name, 'category']} style={{ marginBottom: 0 }}>
                      <Input placeholder="费用类别" style={{ width: 120 }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'account_id']} style={{ marginBottom: 0 }}
                      rules={[{ required: true, message: '选科目' }]}>
                      <Select showSearch placeholder="费用科目" style={{ width: 180 }}
                        optionFilterProp="label" options={accOpts} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'sub_account']} style={{ marginBottom: 0 }}>
                      <Input placeholder="明细科目" style={{ width: 120 }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'amount']} style={{ marginBottom: 0 }}
                      rules={[{ required: true, message: '金额' }]}>
                      <InputNumber min={0} precision={2} placeholder="金额" style={{ width: 110 }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'note']} style={{ marginBottom: 0 }}>
                      <Input placeholder="备注" style={{ width: 120 }} />
                    </Form.Item>
                    <DeleteOutlined style={{ color: '#cf1322' }} onClick={() => remove(field.name)} />
                  </Space>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ amount: 0 })}>增加明细</Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>

      {/* 详情 + 审批轨迹 */}
      <Modal title={detail?.claim_no} open={Boolean(detail)} footer={null} onCancel={() => setDetail(null)} width={640}>
        {detail && (
          <>
            <p>申请人 {detail.applicant_name || '-'} · {detail.org_unit_name || '-'} ·
              <Tag color={STATUS_COLOR[detail.status]} style={{ marginLeft: 6 }}>{EXPENSE_STATUS_LABEL[detail.status]}</Tag></p>
            <p>事由:{detail.reason || '-'}</p>
            <Table rowKey={(_, i) => String(i)} size="small" pagination={false} dataSource={detail.items}
              columns={[
                { title: '类别', dataIndex: 'category', render: (v: string) => v || '-' },
                { title: '科目', dataIndex: 'account_name' },
                { title: '明细', dataIndex: 'sub_account', render: (v: string) => v || '-' },
                { title: '金额', dataIndex: 'amount', align: 'right' as const, render: (v: number) => v.toFixed(2) },
              ]} summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={3}><b>合计</b></Table.Summary.Cell>
                  <Table.Summary.Cell index={3} align="right"><b>{detail.total_amount.toFixed(2)}</b></Table.Summary.Cell>
                </Table.Summary.Row>
              )} />
            {detail.workflow && (
              <>
                <Divider orientation="left" plain>审批轨迹</Divider>
                <Timeline items={detail.workflow.tasks.map((t) => ({
                  color: t.result === 'approved' ? 'green' : t.result === 'rejected' ? 'red' : 'blue',
                  children: (
                    <div>
                      <b>{t.step_name}</b> — {t.approver_name || '未指派'} <Tag>{WF_STATUS_LABEL[t.result] || t.result}</Tag>
                      {t.comment && <div style={{ color: '#666' }}>意见:{t.comment}</div>}
                    </div>
                  ),
                }))} />
              </>
            )}
          </>
        )}
      </Modal>
    </div>
  )
}
