import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Button, Space, Modal, Form, Input, Select, InputNumber,
  Popconfirm, message, Segmented, Timeline, Divider, AutoComplete, Alert,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  http, ExpenseClaim, ExpenseApplication, Attachment, AccountTreeNode, Employee, OrgUnit,
  ActiveWorkflow, APPROVER_TYPE_LABEL, EXPENSE_STATUS_LABEL, APPLY_TYPE_LABEL,
  STEP_STATE_LABEL, STEP_STATE_COLOR, fileUrl, formatYuan,
} from '../api'
import AttachmentEditor from '../components/AttachmentEditor'

const STATUS_COLOR: Record<string, string> = {
  draft: 'default', pending: 'processing', approved: 'success', rejected: 'error', paid: 'gold',
}

export default function Expense() {
  const navigate = useNavigate()
  const [claims, setClaims] = useState<ExpenseClaim[]>([])
  const [accounts, setAccounts] = useState<AccountTreeNode[]>([])
  const [subMap, setSubMap] = useState<Record<number, { value: string }[]>>({})
  const [categories, setCategories] = useState<string[]>([])
  const [wf, setWf] = useState<ActiveWorkflow | null>(null)
  const [approverWarn, setApproverWarn] = useState<string | null>(null)
  const [employees, setEmployees] = useState<Employee[]>([])
  const [units, setUnits] = useState<OrgUnit[]>([])
  const [approvedApps, setApprovedApps] = useState<ExpenseApplication[]>([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [loading, setLoading] = useState(false)

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<ExpenseClaim | null>(null)
  const [form] = Form.useForm()
  const [detail, setDetail] = useState<ExpenseClaim | null>(null)
  const [draftId, setDraftId] = useState<number | null>(null)
  const [existingAtt, setExistingAtt] = useState<Attachment[]>([])

  const load = useCallback(() => {
    setLoading(true)
    const params = statusFilter === 'all' ? {} : { status: statusFilter }
    http.get<ExpenseClaim[]>('/expense/claims', { params })
      .then((r) => setClaims(r.data)).finally(() => setLoading(false))
  }, [statusFilter])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    http.get<AccountTreeNode[]>('/accounts/tree').then((r) => {
      const feeAccounts = r.data.filter((a) => a.category === 'profit' || a.category === 'cost')
      setAccounts(feeAccounts)
      const map: Record<number, { value: string }[]> = {}
      feeAccounts.forEach((a) => {
        map[a.id] = (a.sub_accounts || []).filter((s) => s.is_active)
          .map((s) => ({ value: s.name, label: `${s.code} ${s.name}` } as { value: string }))
      })
      setSubMap(map)
    })
    http.get<{ categories: string[] }>('/expense/meta').then((r) => setCategories(r.data.categories || []))
    http.get<ActiveWorkflow>('/expense/active-workflow').then((r) => setWf(r.data))
    http.get<{ has_approver: boolean; problems: { biz_type: string }[] }>('/workflow/approver-check')
      .then((r) => {
        if (!r.data.has_approver) setApproverWarn('系统尚未设置「管理层/股东」审批人,提交后可能无人可审批。请到人员管理给员工添加「管理层」或「股东」职位。')
        else if (r.data.problems.some((p) => p.biz_type === 'expense')) setApproverWarn('费用报销流程存在未匹配到审批人的步骤,请到审批流程页检查。')
      })
    http.get<Employee[]>('/personnel/employees').then((r) => setEmployees(r.data))
    http.get<OrgUnit[]>('/personnel/org-units').then((r) => setUnits(r.data))
    http.get<ExpenseApplication[]>('/expense-apply/approved').then((r) => setApprovedApps(r.data))
  }, [])

  // 选择关联的费用申请后,带出申请人/部门/事由/明细
  const pickApplication = (appId: number | undefined) => {
    if (!appId) { form.setFieldsValue({ application_id: undefined }); return }
    const app = approvedApps.find((a) => a.id === appId)
    if (!app) return
    form.setFieldsValue({
      application_id: appId,
      applicant_employee_id: app.applicant_employee_id ?? form.getFieldValue('applicant_employee_id'),
      org_unit_id: app.org_unit_id ?? form.getFieldValue('org_unit_id'),
      reason: app.reason,
      items: app.items.map((it) => ({
        category: it.category, account_id: it.account_id,
        sub_account: it.sub_account, amount: it.amount, note: it.note,
      })),
    })
  }

  const openEdit = (c: ExpenseClaim | null) => {
    setEditing(c); form.resetFields(); setDraftId(null)
    setExistingAtt(c ? c.attachments : [])
    if (c) form.setFieldsValue({ ...c, items: c.items })
    else form.setFieldsValue({ items: [{ amount: 0 }] })
    setOpen(true)
  }
  // 上传附件前确保报销单已落库(新建则先建草稿),返回单据 id
  const ensureOwner = async (): Promise<number | null> => {
    if (editing) return editing.id
    if (draftId) return draftId
    try {
      const v = await form.validateFields()
      const r = await http.post<ExpenseClaim>('/expense/claims', v)
      setDraftId(r.data.id); load(); return r.data.id
    } catch { return null }
  }
  const save = async () => {
    const v = await form.validateFields()
    const id = editing?.id ?? draftId
    if (id) await http.put(`/expense/claims/${id}`, v)
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
  const regenDoc = (id: number) =>
    http.post(`/expense/claims/${id}/regenerate-approval-doc`).then((r) => {
      message.success('已补生成审批记录单'); if (detail?.id === id) setDetail(r.data)
    })

  const accOpts = accounts.map((a) => ({ value: a.id, label: `${a.code} ${a.name}` }))

  const columns = [
    { title: '单号', dataIndex: 'claim_no', width: 140,
      render: (v: string, r: ExpenseClaim) => <a onClick={() => setDetail(r)}>{v}</a> },
    { title: '申请人', dataIndex: 'applicant_name', width: 90, render: (v: string) => v || '-' },
    { title: '事由', dataIndex: 'reason', ellipsis: true },
    { title: '金额', dataIndex: 'total_amount', width: 110, align: 'right' as const,
      render: (v: string) => formatYuan(v) },
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
          {r.status === 'paid' && (
            <Popconfirm title="重新生成审批记录单并挂到凭证附件?" onConfirm={() => regenDoc(r.id)}>
              <a>补生成审批单</a>
            </Popconfirm>
          )}
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
        <Alert type={wf?.exists ? 'info' : 'warning'} showIcon style={{ marginBottom: 12 }}
          message={wf?.exists
            ? <span>提交后将走审批流程「{wf.name}」:{(wf.steps || []).map((s) => `${s.step_no}.${s.name}(${APPROVER_TYPE_LABEL[s.approver_type] || s.approver_type})`).join(' → ')}
              <a style={{ marginLeft: 8 }} onClick={() => navigate('/workflow')}>查看/修改</a></span>
            : <span>尚未配置「费用报销」审批流程,提交时将报错。请先到<a onClick={() => navigate('/workflow')}>审批流程</a>页新建。</span>} />
        {approverWarn && <Alert type="warning" showIcon style={{ marginBottom: 12 }}
          message={<span>{approverWarn} <a onClick={() => navigate('/personnel')}>去人员管理</a></span>} />}
        <Form form={form} layout="vertical">
          <Form.Item name="application_id" label="关联费用申请(事前审批)"
            extra="选择已通过的费用申请可自动带出事由与明细,并在生成凭证时同步其附件">
            <Select allowClear showSearch placeholder="不关联 / 选择已审批的费用申请"
              optionFilterProp="label" onChange={(v) => pickApplication(v as number | undefined)}
              options={approvedApps.map((a) => ({
                value: a.id,
                label: `${a.apply_no} · ${APPLY_TYPE_LABEL[a.apply_type] || ''} · ${a.reason} · 预计¥${a.estimated_amount}`,
              }))} />
          </Form.Item>
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
                      <AutoComplete placeholder="费用类别" style={{ width: 120 }}
                        options={categories.map((c) => ({ value: c }))}
                        filterOption={(input, opt) => (opt?.value ?? '').toLowerCase().includes(input.toLowerCase())} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'account_id']} style={{ marginBottom: 0 }}
                      rules={[{ required: true, message: '选科目' }]}>
                      <Select showSearch placeholder="费用科目" style={{ width: 180 }}
                        optionFilterProp="label" options={accOpts} />
                    </Form.Item>
                    <Form.Item noStyle shouldUpdate={(prev, cur) =>
                      prev.items?.[field.name]?.account_id !== cur.items?.[field.name]?.account_id}>
                      {({ getFieldValue }) => {
                        const accId = getFieldValue(['items', field.name, 'account_id']) as number | undefined
                        const opts = accId ? (subMap[accId] || []) : []
                        return (
                          <Form.Item name={[field.name, 'sub_account']} style={{ marginBottom: 0 }}>
                            <AutoComplete placeholder="明细科目" style={{ width: 120 }} options={opts}
                              filterOption={(input, opt) => (opt?.value ?? '').toLowerCase().includes(input.toLowerCase())} />
                          </Form.Item>
                        )
                      }}
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
          <Divider orientation="left" plain>报销附件(发票/回单等,生成凭证时自动同步)</Divider>
          <AttachmentEditor ownerId={editing?.id ?? draftId} basePath="/expense/claims"
            ensureOwner={ensureOwner} existing={existingAtt} onChange={setExistingAtt} defaultKind="invoice" />
        </Form>
      </Modal>

      {/* 详情 + 审批轨迹 */}
      <Modal title={detail?.claim_no} open={Boolean(detail)} footer={null} onCancel={() => setDetail(null)} width={640}>
        {detail && (
          <>
            <p>申请人 {detail.applicant_name || '-'} · {detail.org_unit_name || '-'} ·
              <Tag color={STATUS_COLOR[detail.status]} style={{ marginLeft: 6 }}>{EXPENSE_STATUS_LABEL[detail.status]}</Tag></p>
            <p>事由:{detail.reason || '-'}
              {detail.application_no && <Tag color="geekblue" style={{ marginLeft: 8 }}>关联申请 {detail.application_no}</Tag>}</p>
            <Table rowKey={(_, i) => String(i)} size="small" pagination={false} dataSource={detail.items}
              columns={[
                { title: '类别', dataIndex: 'category', render: (v: string) => v || '-' },
                { title: '科目', dataIndex: 'account_name' },
                { title: '明细', dataIndex: 'sub_account', render: (v: string) => v || '-' },
                { title: '金额', dataIndex: 'amount', align: 'right' as const, render: (v: number | string) => Number(v).toFixed(2) },
              ]} summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={3}><b>合计</b></Table.Summary.Cell>
                  <Table.Summary.Cell index={3} align="right"><b>{Number(detail.total_amount).toFixed(2)}</b></Table.Summary.Cell>
                </Table.Summary.Row>
              )} />
            {detail.attachments && detail.attachments.length > 0 && (
              <>
                <Divider orientation="left" plain>相关附件(含从费用申请同步)</Divider>
                <Space wrap>
                  {detail.attachments.map((a) => (
                    <a key={a.id} href={fileUrl(a.id, 'preview')} target="_blank" rel="noreferrer">
                      <Tag>{a.original_name}</Tag>
                    </a>
                  ))}
                </Space>
              </>
            )}
            {detail.workflow && (
              <>
                <Divider orientation="left" plain>审批流程</Divider>
                <Timeline items={detail.workflow.steps.map((s) => ({
                  color: STEP_STATE_COLOR[s.state] || 'gray',
                  children: (
                    <div style={{ opacity: s.state === 'upcoming' || s.state === 'skipped' ? 0.65 : 1 }}>
                      <b>{s.step_no}. {s.name}</b> — {s.approver_name || '未指派'}
                      {' '}<Tag color={STEP_STATE_COLOR[s.state]}>{STEP_STATE_LABEL[s.state] || s.state}</Tag>
                      {s.is_current && <Tag color="blue">当前</Tag>}
                      {s.comment && <div style={{ color: '#666' }}>意见:{s.comment}</div>}
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
