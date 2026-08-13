import { useEffect, useState, useCallback } from 'react'
import {
  Card, Table, Tag, Button, Space, Modal, Form, Input, Select, Alert, Timeline,
  Divider, message, Popconfirm,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import {
  http, WorkflowDef, WorkflowInstance, Employee, AuthUser, ExpenseClaim, ExpenseApplication,
  WF_STATUS_LABEL, STEP_STATE_LABEL, STEP_STATE_COLOR, ATTACH_KIND_LABEL, APPLY_TYPE_LABEL, BIZ_TYPE_LABEL,
  hasPerm, fileUrl,
} from '../api'

const STATUS_COLOR: Record<string, string> = {
  pending: 'processing', approved: 'success', rejected: 'error', cancelled: 'default',
}

type BizDoc =
  | { kind: 'expense'; data: ExpenseClaim }
  | { kind: 'expense_apply'; data: ExpenseApplication }
  | null

export default function ApprovalCenter() {
  const [me, setMe] = useState<AuthUser | null>(null)
  const [actorId, setActorId] = useState<number | undefined>()
  const [defs, setDefs] = useState<WorkflowDef[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [todos, setTodos] = useState<WorkflowInstance[]>([])
  const [all, setAll] = useState<WorkflowInstance[]>([])
  const [detail, setDetail] = useState<WorkflowInstance | null>(null)
  const [bizDoc, setBizDoc] = useState<BizDoc>(null)
  const [submitOpen, setSubmitOpen] = useState(false)
  const [submitForm] = Form.useForm()
  const [reassignTo, setReassignTo] = useState<number | undefined>()

  // 能否管理审批(改派/撤销/删除):超管或拥有审批中心的管理/删除权限
  const canManage = Boolean(me?.is_super_admin
    || hasPerm(me, 'approval', 'edit') || hasPerm(me, 'approval', 'delete'))

  // 当前审批人身份默认取登录账号绑定的员工
  useEffect(() => {
    http.get<AuthUser>('/auth/me').then((r) => {
      setMe(r.data)
      if (r.data.employee_id) setActorId(r.data.employee_id)
    })
    http.get<WorkflowDef[]>('/workflow/definitions').then((r) => setDefs(r.data))
    http.get<Employee[]>('/personnel/employees').then((r) => setEmployees(r.data))
  }, [])

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

  // 打开详情时,拉取对应业务单据的完整内容
  const openDetail = (inst: WorkflowInstance) => {
    setDetail(inst); setBizDoc(null)
    if (inst.biz_type === 'expense' && inst.biz_id) {
      http.get<ExpenseClaim>(`/expense/claims/${inst.biz_id}`)
        .then((r) => setBizDoc({ kind: 'expense', data: r.data })).catch(() => {})
    } else if (inst.biz_type === 'expense_apply' && inst.biz_id) {
      http.get<ExpenseApplication>(`/expense-apply/${inst.biz_id}`)
        .then((r) => setBizDoc({ kind: 'expense_apply', data: r.data })).catch(() => {})
    }
  }

  const empOpts = employees.map((e) => ({ value: e.id, label: e.name }))
  const pendingTask = (inst: WorkflowInstance) =>
    inst.tasks.find((t) => t.result === 'pending' && t.approver_employee_id === actorId)
  const anyPendingTask = (inst: WorkflowInstance) =>
    inst.tasks.find((t) => t.result === 'pending')

  const refreshAll = (inst?: WorkflowInstance) => {
    loadTodos(); loadAll()
    if (inst) http.get<WorkflowInstance>(`/workflow/instances/${inst.id}`).then((r) => setDetail(r.data))
  }
  // 改派处理人:传 employeeId 指定,否则按流程配置自动重新匹配
  const reassign = async (inst: WorkflowInstance, employeeId?: number) => {
    const task = anyPendingTask(inst)
    if (!task) { message.warning('无进行中的待办可改派'); return }
    try {
      await http.post(`/workflow/tasks/${task.id}/reassign`, { employee_id: employeeId ?? null })
      message.success(employeeId ? '已改派处理人' : '已按流程重新匹配'); setReassignTo(undefined); refreshAll(inst)
    } catch { /* 全局拦截已提示 */ }
  }
  const cancelInst = async (inst: WorkflowInstance) => {
    await http.post(`/workflow/instances/${inst.id}/cancel`)
    message.success('已撤销,关联单据已退回草稿'); setDetail(null); loadTodos(); loadAll()
  }
  const delInst = async (inst: WorkflowInstance) => {
    await http.delete(`/workflow/instances/${inst.id}`)
    message.success('已删除审批实例'); setDetail(null); loadTodos(); loadAll()
  }

  const act = (inst: WorkflowInstance, approve: boolean) => {
    const task = pendingTask(inst)
    if (!task) { message.warning('该单当前步骤不由你审批'); return }
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
    { title: '标题', dataIndex: 'title', render: (v: string, r: WorkflowInstance) => <a onClick={() => openDetail(r)}>{v || `#${r.id}`}</a> },
    { title: '类型', dataIndex: 'biz_type', width: 90, render: (v: string) => <Tag>{BIZ_TYPE_LABEL[v] || v}</Tag> },
    { title: '申请人', dataIndex: 'applicant_name', width: 90, render: (v: string) => v || '-' },
    { title: '当前步', dataIndex: 'current_step_no', width: 70 },
    { title: '状态', dataIndex: 'status', width: 90,
      render: (s: string) => <Tag color={STATUS_COLOR[s]}>{WF_STATUS_LABEL[s] || s}</Tag> },
    { title: '发起时间', dataIndex: 'created_at', width: 160, render: (v: string) => v.slice(0, 19).replace('T', ' ') },
    ...(withAction ? [{
      title: '操作', width: 160, render: (_: unknown, r: WorkflowInstance) => (
        <Space>
          <a onClick={() => openDetail(r)}>查看</a>
          <a onClick={() => act(r, true)}>通过</a>
          <a style={{ color: '#cf1322' }} onClick={() => act(r, false)}>驳回</a>
        </Space>
      ),
    }] : []),
  ]

  return (
    <Card>
      <Space wrap style={{ marginBottom: 12 }}>
        <span>当前审批人身份:</span>
        <Select allowClear showSearch placeholder="选择你的员工身份" style={{ width: 240 }}
          optionFilterProp="label" value={actorId} onChange={setActorId} options={empOpts} />
        {me && !me.employee_id && (
          <span style={{ color: '#faad14' }}>
            当前账号未绑定员工,请在「用户与权限」为账号绑定员工后自动识别身份
          </span>
        )}
        <Button type="primary" icon={<PlusOutlined />} onClick={() => { submitForm.resetFields(); setSubmitOpen(true) }}>
          发起审批
        </Button>
      </Space>

      <h4>我的待办({todos.length})</h4>
      <Table rowKey="id" size="small" dataSource={todos} pagination={false}
        locale={{ emptyText: actorId ? '暂无待办' : '请先选择/绑定审批人身份' }} columns={cols(true)} />

      <h4 style={{ marginTop: 16 }}>全部审批单</h4>
      <Table rowKey="id" size="small" dataSource={all} pagination={{ pageSize: 10 }} columns={cols(false)} />

      {/* 审批详情:完整申请内容 + 流程链 */}
      <Modal title="审批详情" open={Boolean(detail)} width={720} onCancel={() => setDetail(null)}
        footer={detail && pendingTask(detail) ? [
          <Button key="r" danger onClick={() => act(detail, false)}>驳回</Button>,
          <Button key="a" type="primary" onClick={() => act(detail, true)}>通过</Button>,
        ] : null}>
        {detail && (
          <>
            <p><b>{detail.title}</b> · 申请人 {detail.applicant_name || '-'} ·
              <Tag style={{ marginLeft: 6 }}>{BIZ_TYPE_LABEL[detail.biz_type] || detail.biz_type}</Tag>
              <Tag color={STATUS_COLOR[detail.status]}>{WF_STATUS_LABEL[detail.status]}</Tag></p>

            {bizDoc && <BizContent doc={bizDoc} />}

            <Divider orientation="left" plain>审批流程</Divider>
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

            {canManage && detail.status === 'pending' && (
              <>
                <Divider orientation="left" plain>处理人管理</Divider>
                <Space wrap>
                  <span>当前处理人:{anyPendingTask(detail)?.approver_name || <Tag color="red">未指派</Tag>}</span>
                  <Select showSearch placeholder="改派给…" style={{ width: 170 }} optionFilterProp="label"
                    value={reassignTo} onChange={setReassignTo} options={empOpts} />
                  <Button onClick={() => reassign(detail, reassignTo)} disabled={!reassignTo}>改派</Button>
                  <Button onClick={() => reassign(detail)}>按流程自动匹配</Button>
                  <Popconfirm title="撤销该审批?关联单据将退回草稿" onConfirm={() => cancelInst(detail)}>
                    <Button>撤销审批</Button>
                  </Popconfirm>
                  <Popconfirm title="删除该审批实例?(关联单据退回草稿)" onConfirm={() => delInst(detail)}>
                    <Button danger>删除</Button>
                  </Popconfirm>
                </Space>
                <div style={{ color: '#999', fontSize: 12, marginTop: 6 }}>
                  提示:未匹配到审批人时,可先到「人员管理」设置管理层/股东后点「自动匹配」,或直接「改派」给指定处理人。
                </div>
              </>
            )}
          </>
        )}
      </Modal>

      {/* 发起审批(通用) */}
      <Modal title="发起审批" open={submitOpen} onOk={doSubmit} onCancel={() => setSubmitOpen(false)} okText="发起">
        <Form form={submitForm} layout="vertical">
          <Form.Item name="definition_id" label="选择流程" rules={[{ required: true }]}>
            <Select placeholder="选择审批流程"
              options={defs.filter((d) => d.is_active).map((d) => ({ value: d.id, label: `${d.name} (${BIZ_TYPE_LABEL[d.biz_type] || d.biz_type})` }))} />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="如 报销差旅费 500 元" />
          </Form.Item>
          <Form.Item name="applicant_employee_id" label="申请人">
            <Select allowClear showSearch optionFilterProp="label" options={empOpts} />
          </Form.Item>
          <Alert type="info" showIcon message="费用申请/报销单在各自页面提交后会自动出现在此。此处用于发起通用审批。" />
        </Form>
      </Modal>
    </Card>
  )
}

// 审批详情里的业务单据内容(费用申请/报销:明细 + 附件)
function BizContent({ doc }: { doc: NonNullable<BizDoc> }) {
  const items = doc.data.items
  const attachments = doc.data.attachments
  const total = doc.kind === 'expense'
    ? (doc.data as ExpenseClaim).total_amount
    : (doc.data as ExpenseApplication).estimated_amount
  return (
    <>
      <Divider orientation="left" plain>
        {doc.kind === 'expense' ? '报销明细' : '费用申请明细'}
        {doc.kind === 'expense_apply' && (
          <Tag style={{ marginLeft: 8 }}>{APPLY_TYPE_LABEL[(doc.data as ExpenseApplication).apply_type]}</Tag>
        )}
      </Divider>
      <p style={{ color: '#666' }}>事由:{doc.data.reason || '-'}</p>
      <Table rowKey={(_, i) => String(i)} size="small" pagination={false} dataSource={items}
        columns={[
          { title: '类别', dataIndex: 'category', render: (v: string) => v || '-' },
          { title: '科目', dataIndex: 'account_name', render: (v: string) => v || '-' },
          { title: '明细', dataIndex: 'sub_account', render: (v: string) => v || '-' },
          { title: doc.kind === 'expense' ? '金额' : '预计金额', dataIndex: 'amount',
            align: 'right' as const, render: (v: number | string) => Number(v).toFixed(2) },
        ]}
        summary={() => (
          <Table.Summary.Row>
            <Table.Summary.Cell index={0} colSpan={3}><b>合计</b></Table.Summary.Cell>
            <Table.Summary.Cell index={3} align="right"><b>{Number(total).toFixed(2)}</b></Table.Summary.Cell>
          </Table.Summary.Row>
        )} />
      <div style={{ marginTop: 8 }}>
        <span style={{ color: '#666' }}>附件:</span>
        {attachments.length ? attachments.map((a) => (
          <a key={a.id} href={fileUrl(a.id, 'preview')} target="_blank" rel="noreferrer" style={{ marginLeft: 6 }}>
            <Tag color="blue">{ATTACH_KIND_LABEL[a.kind] || a.kind}·{a.original_name}</Tag>
          </a>
        )) : <span style={{ color: '#bbb' }}>无</span>}
      </div>
    </>
  )
}
