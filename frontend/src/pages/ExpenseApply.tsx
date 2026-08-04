import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Button, Space, Modal, Form, Input, Select, InputNumber,
  Popconfirm, message, Segmented, Timeline, Divider, AutoComplete, Alert, Upload,
} from 'antd'
import { PlusOutlined, DeleteOutlined, UploadOutlined, PaperClipOutlined } from '@ant-design/icons'
import {
  http, ExpenseApplication, Attachment, AccountTreeNode, Employee, OrgUnit,
  APPLY_STATUS_LABEL, APPLY_TYPE_LABEL, ATTACH_KIND_LABEL,
  STEP_STATE_LABEL, STEP_STATE_COLOR,
} from '../api'

const STATUS_COLOR: Record<string, string> = {
  draft: 'default', pending: 'processing', approved: 'success', rejected: 'error', closed: 'gold',
}

interface ActiveWorkflow {
  exists: boolean; id?: number; name?: string
  steps?: { step_no: number; name: string; approver_type: string }[]
}

export default function ExpenseApply() {
  const [apps, setApps] = useState<ExpenseApplication[]>([])
  const [accounts, setAccounts] = useState<AccountTreeNode[]>([])
  const [subMap, setSubMap] = useState<Record<number, { value: string }[]>>({})
  const [categories, setCategories] = useState<string[]>([])
  const [wf, setWf] = useState<ActiveWorkflow | null>(null)
  const [approverWarn, setApproverWarn] = useState<string | null>(null)
  const [employees, setEmployees] = useState<Employee[]>([])
  const [units, setUnits] = useState<OrgUnit[]>([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [loading, setLoading] = useState(false)

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<ExpenseApplication | null>(null)
  const [form] = Form.useForm()
  const [detail, setDetail] = useState<ExpenseApplication | null>(null)
  const [uploadKind, setUploadKind] = useState('contract')

  const load = useCallback(() => {
    setLoading(true)
    const params = statusFilter === 'all' ? {} : { status: statusFilter }
    http.get<ExpenseApplication[]>('/expense-apply', { params })
      .then((r) => setApps(r.data)).finally(() => setLoading(false))
  }, [statusFilter])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    http.get<AccountTreeNode[]>('/accounts/tree').then((r) => {
      const feeAccounts = r.data.filter((a) => a.category === 'profit' || a.category === 'cost')
      setAccounts(feeAccounts)
      const map: Record<number, { value: string }[]> = {}
      feeAccounts.forEach((a) => {
        map[a.id] = (a.sub_accounts || []).filter((s) => s.is_active).map((s) => ({ value: s.name }))
      })
      setSubMap(map)
    })
    http.get<{ categories: string[] }>('/expense-apply/meta').then((r) => setCategories(r.data.categories || []))
    http.get<ActiveWorkflow>('/expense-apply/active-workflow').then((r) => setWf(r.data))
    http.get<{ has_management: boolean; problems: { biz_type: string }[] }>('/workflow/approver-check')
      .then((r) => {
        if (!r.data.has_management) setApproverWarn('系统尚未设置「管理层」审批人,提交后可能无人可审批。请到人员管理给员工添加「管理层」职位。')
        else if (r.data.problems.some((p) => p.biz_type === 'expense_apply')) setApproverWarn('费用申请流程存在未匹配到审批人的步骤,请到审批流程页检查。')
      })
    http.get<Employee[]>('/personnel/employees').then((r) => setEmployees(r.data))
    http.get<OrgUnit[]>('/personnel/org-units').then((r) => setUnits(r.data))
  }, [])

  const openEdit = (a: ExpenseApplication | null) => {
    setEditing(a); form.resetFields()
    if (a) form.setFieldsValue({ ...a, items: a.items })
    else form.setFieldsValue({ apply_type: 'general', items: [{ amount: 0 }] })
    setOpen(true)
  }
  const save = async () => {
    const v = await form.validateFields()
    if (editing) await http.put(`/expense-apply/${editing.id}`, v)
    else await http.post('/expense-apply', v)
    message.success('已保存'); setOpen(false); load()
  }
  const submit = (id: number) =>
    http.post(`/expense-apply/${id}/submit`).then(() => { message.success('已提交审批'); load() })
  const remove = (id: number) =>
    http.delete(`/expense-apply/${id}`).then(() => { message.success('已删除'); load() })

  const refreshDetail = (id: number) =>
    http.get<ExpenseApplication>(`/expense-apply/${id}`).then((r) => setDetail(r.data))

  const uploadProps = {
    showUploadList: false,
    customRequest: async (opt: { file: unknown; onSuccess?: (b: unknown) => void; onError?: (e: Error) => void }) => {
      if (!detail) return
      const fd = new FormData()
      fd.append('file', opt.file as Blob)
      fd.append('kind', uploadKind)
      try {
        await http.post<Attachment>(`/expense-apply/${detail.id}/attachments`, fd)
        message.success('附件已上传'); await refreshDetail(detail.id); opt.onSuccess?.({})
      } catch (e) { opt.onError?.(e as Error) }
    },
  }
  const removeAttachment = (aid: number) =>
    http.delete(`/attachments/${aid}`).then(() => { if (detail) refreshDetail(detail.id) })

  const accOpts = accounts.map((a) => ({ value: a.id, label: `${a.code} ${a.name}` }))

  const columns = [
    { title: '申请单号', dataIndex: 'apply_no', width: 150,
      render: (v: string, r: ExpenseApplication) => <a onClick={() => setDetail(r)}>{v}</a> },
    { title: '类型', dataIndex: 'apply_type', width: 90,
      render: (v: string) => <Tag>{APPLY_TYPE_LABEL[v] || v}</Tag> },
    { title: '申请人', dataIndex: 'applicant_name', width: 90, render: (v: string) => v || '-' },
    { title: '事由', dataIndex: 'reason', ellipsis: true },
    { title: '预计金额', dataIndex: 'estimated_amount', width: 110, align: 'right' as const,
      render: (v: number) => `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` },
    { title: '附件', dataIndex: 'attachments', width: 60, align: 'center' as const,
      render: (a: Attachment[]) => a.length ? <Tag icon={<PaperClipOutlined />}>{a.length}</Tag> : '-' },
    { title: '状态', dataIndex: 'status', width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s]}>{APPLY_STATUS_LABEL[s] || s}</Tag> },
    { title: '关联报销', dataIndex: 'claim_ids', width: 90, align: 'center' as const,
      render: (ids: number[]) => ids.length ? <Tag color="blue">{ids.length} 单</Tag> : '-' },
    {
      title: '操作', width: 180, render: (_: unknown, r: ExpenseApplication) => (
        <Space wrap>
          {(r.status === 'draft' || r.status === 'rejected') && <>
            <a onClick={() => openEdit(r)}>编辑</a>
            <a onClick={() => submit(r.id)}>提交</a>
            <Popconfirm title="删除该申请?" onConfirm={() => remove(r.id)}>
              <a style={{ color: '#cf1322' }}>删除</a>
            </Popconfirm>
          </>}
          <a onClick={() => setDetail(r)}>详情/附件</a>
        </Space>
      ),
    },
  ]

  return (
    <div className="content-card">
      <Space style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <Segmented value={statusFilter} onChange={(v) => setStatusFilter(v as string)}
          options={[{ label: '全部', value: 'all' },
            ...Object.entries(APPLY_STATUS_LABEL).map(([value, label]) => ({ value, label }))]} />
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEdit(null)}>新建费用申请</Button>
      </Space>
      <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={apps}
        pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 单` }} />

      {/* 新建/编辑费用申请 */}
      <Modal title={editing ? '编辑费用申请' : '新建费用申请'} open={open} onOk={save}
        onCancel={() => setOpen(false)} okText="保存" width={780}>
        <Alert type={wf?.exists ? 'info' : 'warning'} showIcon style={{ marginBottom: 12 }}
          message={wf?.exists
            ? <span>提交后将走事前审批流程「{wf.name}」:{(wf.steps || []).map((s) => `${s.step_no}.${s.name}`).join(' → ')}</span>
            : <span>尚未配置「费用申请」审批流程,提交时将报错。请先到审批流程页新建。</span>} />
        {approverWarn && <Alert type="warning" showIcon style={{ marginBottom: 12 }} message={approverWarn} />}
        <Form form={form} layout="vertical">
          <Space wrap>
            <Form.Item name="applicant_employee_id" label="申请人">
              <Select allowClear showSearch style={{ width: 160 }} optionFilterProp="label"
                options={employees.map((e) => ({ value: e.id, label: e.name }))} />
            </Form.Item>
            <Form.Item name="org_unit_id" label="部门">
              <Select allowClear style={{ width: 150 }}
                options={units.map((u) => ({ value: u.id, label: u.name }))} />
            </Form.Item>
            <Form.Item name="apply_type" label="申请类型">
              <Select style={{ width: 130 }}
                options={Object.entries(APPLY_TYPE_LABEL).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="reason" label="申请事由" style={{ flex: 1, minWidth: 220 }}>
              <Input placeholder="如 签订年度办公用品采购合同" />
            </Form.Item>
          </Space>
          <Divider orientation="left" plain>预计费用明细</Divider>
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
                      <InputNumber min={0} precision={2} placeholder="预计金额" style={{ width: 120 }} />
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

      {/* 详情 + 附件 + 审批轨迹 */}
      <Modal title={detail?.apply_no} open={Boolean(detail)} footer={null} onCancel={() => setDetail(null)} width={680}>
        {detail && (
          <>
            <p>
              <Tag>{APPLY_TYPE_LABEL[detail.apply_type]}</Tag>
              申请人 {detail.applicant_name || '-'} · {detail.org_unit_name || '-'} ·
              <Tag color={STATUS_COLOR[detail.status]} style={{ marginLeft: 6 }}>{APPLY_STATUS_LABEL[detail.status]}</Tag>
            </p>
            <p>事由:{detail.reason || '-'}</p>
            <Table rowKey={(_, i) => String(i)} size="small" pagination={false} dataSource={detail.items}
              columns={[
                { title: '类别', dataIndex: 'category', render: (v: string) => v || '-' },
                { title: '科目', dataIndex: 'account_name' },
                { title: '明细', dataIndex: 'sub_account', render: (v: string) => v || '-' },
                { title: '预计金额', dataIndex: 'amount', align: 'right' as const, render: (v: number) => v.toFixed(2) },
              ]} summary={() => (
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={3}><b>合计</b></Table.Summary.Cell>
                  <Table.Summary.Cell index={3} align="right"><b>{detail.estimated_amount.toFixed(2)}</b></Table.Summary.Cell>
                </Table.Summary.Row>
              )} />

            <Divider orientation="left" plain>申请附件(合同/发票等,生成报销凭证时自动同步)</Divider>
            {detail.status !== 'closed' && (
              <Space style={{ marginBottom: 8 }}>
                <Select value={uploadKind} style={{ width: 130 }} onChange={setUploadKind}
                  options={Object.entries(ATTACH_KIND_LABEL).map(([value, label]) => ({ value, label }))} />
                <Upload {...uploadProps}><Button icon={<UploadOutlined />}>上传附件</Button></Upload>
              </Space>
            )}
            <Table rowKey="id" size="small" pagination={false} dataSource={detail.attachments}
              locale={{ emptyText: '暂无附件' }}
              columns={[
                { title: '类型', dataIndex: 'kind', width: 90, render: (k: string) => <Tag>{ATTACH_KIND_LABEL[k] || k}</Tag> },
                { title: '文件名', dataIndex: 'original_name',
                  render: (v: string, a: Attachment) => <a href={`/api/attachments/${a.id}/preview`} target="_blank" rel="noreferrer">{v}</a> },
                { title: '操作', width: 60, render: (_: unknown, a: Attachment) => (
                  detail.status !== 'closed'
                    ? <Popconfirm title="删除该附件?" onConfirm={() => removeAttachment(a.id)}><a style={{ color: '#cf1322' }}>删除</a></Popconfirm>
                    : <a href={`/api/attachments/${a.id}/download`}>下载</a>) },
              ]} />

            {detail.claim_ids.length > 0 && (
              <p style={{ marginTop: 12 }}>已关联报销单:{detail.claim_ids.length} 单(可在费用报销页查看)</p>
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
