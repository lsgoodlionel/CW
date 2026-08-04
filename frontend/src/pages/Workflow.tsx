import { useEffect, useState, useCallback } from 'react'
import {
  Card, Tabs, Table, Tag, Button, Space, Modal, Form, Input, Select, Popconfirm,
  message, Timeline, Alert,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import {
  http, WorkflowDef, WorkflowInstance, Employee, ROLE_LABEL,
  APPROVER_TYPE_LABEL, WF_STATUS_LABEL, STEP_STATE_LABEL, STEP_STATE_COLOR,
} from '../api'

const STATUS_COLOR: Record<string, string> = {
  pending: 'processing', approved: 'success', rejected: 'error', cancelled: 'default',
}
const BIZ_LABEL: Record<string, string> = { general: '通用', expense_apply: '费用申请', expense: '费用报销' }

export default function Workflow() {
  const [defs, setDefs] = useState<WorkflowDef[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])

  const loadDefs = useCallback(() => {
    http.get<WorkflowDef[]>('/workflow/definitions').then((r) => setDefs(r.data))
  }, [])
  useEffect(() => {
    loadDefs()
    http.get<Employee[]>('/personnel/employees').then((r) => setEmployees(r.data))
  }, [loadDefs])

  return (
    <Card>
      <Tabs items={[
        { key: 'design', label: '流程设计', children: <Design defs={defs} employees={employees} reload={loadDefs} /> },
        { key: 'center', label: '审批中心', children: <ApprovalCenter defs={defs} employees={employees} /> },
      ]} />
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

// ---------------- 审批中心 ----------------
function ApprovalCenter({ defs, employees }: { defs: WorkflowDef[]; employees: Employee[] }) {
  const [actorId, setActorId] = useState<number | undefined>()
  const [todos, setTodos] = useState<WorkflowInstance[]>([])
  const [all, setAll] = useState<WorkflowInstance[]>([])
  const [detail, setDetail] = useState<WorkflowInstance | null>(null)
  const [submitOpen, setSubmitOpen] = useState(false)
  const [submitForm] = Form.useForm()

  const loadTodos = useCallback(() => {
    if (!actorId) { setTodos([]); return }
    http.get<WorkflowInstance[]>('/workflow/my-tasks', { params: { employee_id: actorId } })
      .then((r) => setTodos(r.data))
  }, [actorId])
  const loadAll = useCallback(() => {
    http.get<WorkflowInstance[]>('/workflow/instances').then((r) => setAll(r.data))
  }, [])
  useEffect(() => { loadTodos() }, [loadTodos])
  useEffect(() => { loadAll() }, [loadAll])

  const empOpts = employees.map((e) => ({ value: e.id, label: e.name }))

  const pendingTask = (inst: WorkflowInstance) =>
    inst.tasks.find((t) => t.result === 'pending' && t.approver_employee_id === actorId)

  const act = async (inst: WorkflowInstance, approve: boolean) => {
    const task = pendingTask(inst)
    if (!task) return
    let comment = ''
    Modal.confirm({
      title: approve ? '审批通过' : '审批驳回',
      content: <Input.TextArea placeholder="审批意见(可选)" onChange={(e) => { comment = e.target.value }} />,
      okText: approve ? '通过' : '驳回', okButtonProps: { danger: !approve },
      onOk: async () => {
        await http.post(`/workflow/tasks/${task.id}/${approve ? 'approve' : 'reject'}`, { comment })
        message.success('已处理'); loadTodos(); loadAll(); setDetail(null)
      },
    })
  }

  const doSubmit = async () => {
    const v = await submitForm.validateFields()
    await http.post('/workflow/instances', v)
    message.success('已发起审批'); setSubmitOpen(false); loadAll()
  }

  const cols = (withAction: boolean) => [
    { title: '标题', dataIndex: 'title', render: (v: string, r: WorkflowInstance) => <a onClick={() => setDetail(r)}>{v || `#${r.id}`}</a> },
    { title: '申请人', dataIndex: 'applicant_name', width: 100, render: (v: string) => v || '-' },
    { title: '当前步', dataIndex: 'current_step_no', width: 70 },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => <Tag color={STATUS_COLOR[s]}>{WF_STATUS_LABEL[s] || s}</Tag>,
    },
    { title: '发起时间', dataIndex: 'created_at', width: 160, render: (v: string) => v.slice(0, 19).replace('T', ' ') },
    ...(withAction ? [{
      title: '操作', width: 130, render: (_: unknown, r: WorkflowInstance) => (
        <Space>
          <a onClick={() => act(r, true)}>通过</a>
          <a style={{ color: '#cf1322' }} onClick={() => act(r, false)}>驳回</a>
        </Space>
      ),
    }] : []),
  ]

  return (
    <>
      <Space wrap style={{ marginBottom: 12 }}>
        <span>当前审批人身份:</span>
        <Select allowClear showSearch placeholder="选择你的员工身份(登录模块上线后自动识别)"
          style={{ width: 280 }} optionFilterProp="label" value={actorId}
          onChange={setActorId} options={empOpts} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { submitForm.resetFields(); setSubmitOpen(true) }}>
          发起审批
        </Button>
      </Space>

      <h4>我的待办({todos.length})</h4>
      <Table rowKey="id" size="small" dataSource={todos} pagination={false}
        locale={{ emptyText: actorId ? '暂无待办' : '请先选择审批人身份' }} columns={cols(true)} />

      <h4 style={{ marginTop: 16 }}>全部审批单</h4>
      <Table rowKey="id" size="small" dataSource={all}
        pagination={{ pageSize: 10 }} columns={cols(false)} />

      {/* 审批轨迹 */}
      <Modal title="审批轨迹" open={Boolean(detail)} footer={null} onCancel={() => setDetail(null)}>
        {detail && (
          <>
            <p><b>{detail.title}</b> · 申请人 {detail.applicant_name || '-'} ·
              <Tag color={STATUS_COLOR[detail.status]} style={{ marginLeft: 6 }}>{WF_STATUS_LABEL[detail.status]}</Tag></p>
            <Timeline items={detail.steps.map((s) => ({
              color: STEP_STATE_COLOR[s.state] || 'gray',
              children: (
                <div style={{ opacity: s.state === 'upcoming' || s.state === 'skipped' ? 0.65 : 1 }}>
                  <b>{s.step_no}. {s.name}</b> — {s.approver_name || '未指派'}
                  {' '}<Tag color={STEP_STATE_COLOR[s.state]}>{STEP_STATE_LABEL[s.state] || s.state}</Tag>
                  {s.is_current && <Tag color="blue">当前</Tag>}
                  {s.comment && <div style={{ color: '#666' }}>意见:{s.comment}</div>}
                  {s.acted_at && <div style={{ color: '#999', fontSize: 12 }}>{s.acted_at.slice(0, 19).replace('T', ' ')}</div>}
                </div>
              ),
            }))} />
          </>
        )}
      </Modal>

      {/* 发起审批 */}
      <Modal title="发起审批" open={submitOpen} onOk={doSubmit} onCancel={() => setSubmitOpen(false)} okText="发起">
        <Form form={submitForm} layout="vertical">
          <Form.Item name="definition_id" label="选择流程" rules={[{ required: true }]}>
            <Select placeholder="选择审批流程"
              options={defs.filter((d) => d.is_active).map((d) => ({ value: d.id, label: `${d.name} (${BIZ_LABEL[d.biz_type] || d.biz_type})` }))} />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="如 报销差旅费 500 元" />
          </Form.Item>
          <Form.Item name="applicant_employee_id" label="申请人">
            <Select allowClear showSearch optionFilterProp="label" options={employees.map((e) => ({ value: e.id, label: e.name }))} />
          </Form.Item>
          <Alert type="info" showIcon message="发起后将按流程步骤依次生成审批待办。费用报销单(#3)将复用此引擎。" />
        </Form>
      </Modal>
    </>
  )
}
