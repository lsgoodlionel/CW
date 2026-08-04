import { useEffect, useState, useCallback } from 'react'
import {
  Card, Table, Tag, Button, Space, Modal, Form, Input, Select, Popconfirm,
  message, Alert,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import {
  http, WorkflowDef, Employee, ROLE_LABEL, ApproverCheck, APPROVER_TYPE_LABEL,
} from '../api'

const BIZ_LABEL: Record<string, string> = { general: '通用', expense_apply: '费用申请', expense: '费用报销' }

export default function Workflow() {
  const [defs, setDefs] = useState<WorkflowDef[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [check, setCheck] = useState<ApproverCheck | null>(null)

  const loadDefs = useCallback(() => {
    http.get<WorkflowDef[]>('/workflow/definitions').then((r) => setDefs(r.data))
    http.get<ApproverCheck>('/workflow/approver-check').then((r) => setCheck(r.data))
  }, [])
  useEffect(() => {
    loadDefs()
    http.get<Employee[]>('/personnel/employees').then((r) => setEmployees(r.data))
  }, [loadDefs])

  return (
    <Card>
      {check && !check.ready && (
        <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message={check.has_approver ? '部分流程步骤未匹配到审批人' : '尚未设置任何「管理层/股东」审批人'}
          description={
            <div>
              {!check.has_approver && (
                <p style={{ marginBottom: 6 }}>
                  预置的「费用申请/费用报销」流程按<b>部门负责人 / 任一管理层</b>自动找审批人
                  (<b>股东高于管理层,同样可审批</b>)。
                  请到<b>人员管理</b>给至少一名员工添加<b>「管理层」或「股东」</b>职位,否则提交的单据将<b>无人可审批</b>。
                </p>
              )}
              {check.problems.map((p) => (
                <div key={p.id}>
                  流程「{p.name}」({p.biz_type_label}):
                  {p.missing_steps.map((s) => `第${s.step_no}步「${s.name}」(${s.approver_type_label})`).join('、')}
                  {' '}未匹配到审批人 — 请在流程设计里指定具体审批人,或到人员管理补充对应职位/员工。
                </div>
              ))}
            </div>
          } />
      )}
      <Design defs={defs} employees={employees} reload={loadDefs} />
    </Card>
  )
}

// ---------------- 流程设计 ----------------
function Design({ defs, employees, reload }: { defs: WorkflowDef[]; employees: Employee[]; reload: () => void }) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<WorkflowDef | null>(null)
  const [form] = Form.useForm()

  const openEdit = (d: WorkflowDef | null) => {
    setEditing(d); form.resetFields()
    if (d) form.setFieldsValue(d)
    else form.setFieldsValue({ biz_type: 'expense', is_active: true, steps: [{ approver_type: 'employee' }] })
    setOpen(true)
  }
  const save = async () => {
    const v = await form.validateFields()
    if (editing) await http.put(`/workflow/definitions/${editing.id}`, v)
    else await http.post('/workflow/definitions', v)
    message.success('流程已保存'); setOpen(false); reload()
  }
  const remove = (id: number) =>
    http.delete(`/workflow/definitions/${id}`).then(() => { message.success('已删除'); reload() })

  const empOpts = employees.map((e) => ({ value: e.id, label: `${e.name}${e.employee_no ? ` (${e.employee_no})` : ''}` }))

  return (
    <>
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }}
        onClick={() => openEdit(null)}>新建流程</Button>
      <Table rowKey="id" size="small" dataSource={defs} pagination={false}
        columns={[
          { title: '流程名称', dataIndex: 'name' },
          { title: '业务类型', dataIndex: 'biz_type', width: 110, render: (v: string) => BIZ_LABEL[v] || v },
          {
            title: '审批步骤', dataIndex: 'steps',
            render: (steps: WorkflowDef['steps']) => (
              <Space wrap size={4}>
                {steps.map((s, i) => (
                  <Tag key={i}>{i + 1}.{s.name || '步骤'}·{s.approver_name || APPROVER_TYPE_LABEL[s.approver_type]}</Tag>
                ))}
              </Space>
            ),
          },
          { title: '状态', dataIndex: 'is_active', width: 70, render: (a: boolean) => a ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
          {
            title: '操作', width: 110, render: (_: unknown, r: WorkflowDef) => (
              <Space>
                <a onClick={() => openEdit(r)}>编辑</a>
                <Popconfirm title="删除该流程?" onConfirm={() => remove(r.id)}>
                  <a style={{ color: '#cf1322' }}>删除</a>
                </Popconfirm>
              </Space>
            ),
          },
        ]} />

      <Modal title={editing ? '编辑流程' : '新建流程'} open={open} onOk={save}
        onCancel={() => setOpen(false)} okText="保存" width={680}>
        <Form form={form} layout="vertical">
          <Space>
            <Form.Item name="name" label="流程名称" rules={[{ required: true }]}>
              <Input placeholder="如 费用报销审批" style={{ width: 260 }} />
            </Form.Item>
            <Form.Item name="biz_type" label="业务类型" rules={[{ required: true }]}>
              <Select style={{ width: 140 }}
                options={Object.entries(BIZ_LABEL).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
          </Space>
          <Form.Item name="note" label="说明"><Input /></Form.Item>
          <div style={{ fontWeight: 600, margin: '8px 0' }}>审批步骤(按顺序)</div>
          <Form.List name="steps">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field, idx) => (
                  <Space key={field.key} align="baseline" style={{ display: 'flex', marginBottom: 8 }}>
                    <span>第{idx + 1}步</span>
                    <Form.Item name={[field.name, 'name']} style={{ marginBottom: 0 }}>
                      <Input placeholder="步骤名(如 经理审批)" style={{ width: 150 }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'approver_type']} initialValue="employee" style={{ marginBottom: 0 }}>
                      <Select style={{ width: 130 }}
                        options={Object.entries(APPROVER_TYPE_LABEL).map(([value, label]) => ({ value, label }))} />
                    </Form.Item>
                    <Form.Item shouldUpdate style={{ marginBottom: 0 }}>
                      {() => {
                        const t = form.getFieldValue(['steps', field.name, 'approver_type'])
                        if (t === 'employee') return (
                          <Form.Item name={[field.name, 'approver_employee_id']} noStyle>
                            <Select showSearch placeholder="选审批人" style={{ width: 160 }}
                              optionFilterProp="label" options={empOpts} />
                          </Form.Item>
                        )
                        if (t === 'role') return (
                          <Form.Item name={[field.name, 'approver_role']} noStyle initialValue="management">
                            <Select style={{ width: 160 }}
                              options={Object.entries(ROLE_LABEL).map(([value, label]) => ({ value, label }))} />
                          </Form.Item>
                        )
                        return <span style={{ color: '#999', width: 160, display: 'inline-block' }}>系统自动指派</span>
                      }}
                    </Form.Item>
                    <DeleteOutlined style={{ color: '#cf1322' }} onClick={() => remove(field.name)} />
                  </Space>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ approver_type: 'employee' })}>
                  增加审批步骤
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </>
  )
}

