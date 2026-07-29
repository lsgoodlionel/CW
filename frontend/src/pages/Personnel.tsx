import { useEffect, useState, useCallback, useMemo } from 'react'
import {
  Row, Col, Card, Tree, Button, Table, Tag, Space, Modal, Form, Input, Select,
  Popconfirm, message, Segmented, InputNumber, Divider, Alert,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ApartmentOutlined, UsergroupAddOutlined,
} from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import { http, OrgUnit, Employee, Position, ROLE_LABEL } from '../api'

const ROLE_COLOR: Record<string, string> = {
  shareholder: 'gold', management: 'blue', staff: 'default', other: 'purple',
}
const roleOptions = Object.entries(ROLE_LABEL).map(([value, label]) => ({ value, label }))

export default function Personnel() {
  const [units, setUnits] = useState<OrgUnit[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [allEmployees, setAllEmployees] = useState<Employee[]>([])
  const [selectedUnit, setSelectedUnit] = useState<number | null>(null)
  const [roleFilter, setRoleFilter] = useState('all')
  const [loading, setLoading] = useState(false)

  const [unitOpen, setUnitOpen] = useState(false)
  const [unitForm] = Form.useForm()
  const [unitEditing, setUnitEditing] = useState<OrgUnit | null>(null)

  const [empOpen, setEmpOpen] = useState(false)
  const [empForm] = Form.useForm()
  const [empEditing, setEmpEditing] = useState<Employee | null>(null)

  const [memberOpen, setMemberOpen] = useState(false)
  const [memberForm] = Form.useForm()
  const [pickedEmp, setPickedEmp] = useState<Employee | null>(null)

  const loadUnits = useCallback(() => {
    http.get<OrgUnit[]>('/personnel/org-units').then((r) => setUnits(r.data))
  }, [])
  const loadEmployees = useCallback(() => {
    setLoading(true)
    const params: Record<string, string | number> = {}
    if (selectedUnit) params.org_unit_id = selectedUnit
    if (roleFilter !== 'all') params.role_type = roleFilter
    http.get<Employee[]>('/personnel/employees', { params })
      .then((r) => setEmployees(r.data)).finally(() => setLoading(false))
  }, [selectedUnit, roleFilter])
  const loadAll = useCallback(() => {
    http.get<Employee[]>('/personnel/employees').then((r) => setAllEmployees(r.data))
  }, [])

  useEffect(() => { loadUnits(); loadAll() }, [loadUnits, loadAll])
  useEffect(() => { loadEmployees() }, [loadEmployees])

  const refresh = () => { loadUnits(); loadEmployees(); loadAll() }
  const unitName = (id: number | null) => units.find((u) => u.id === id)?.name || ''

  const treeData = useMemo<DataNode[]>(() => {
    const byParent: Record<string, OrgUnit[]> = {}
    units.forEach((u) => { (byParent[String(u.parent_id ?? 'root')] ||= []).push(u) })
    const build = (pid: string): DataNode[] =>
      (byParent[pid] || []).map((u) => ({
        key: u.id, title: `${u.name} (${u.employee_count})`, children: build(String(u.id)),
      }))
    return build('root')
  }, [units])

  // ---------- 部门 ----------
  const openUnit = (parent: OrgUnit | null, editing: OrgUnit | null) => {
    setUnitEditing(editing); unitForm.resetFields()
    if (editing) unitForm.setFieldsValue(editing)
    else unitForm.setFieldsValue({ parent_id: parent?.id ?? null })
    setUnitOpen(true)
  }
  const saveUnit = async () => {
    const v = await unitForm.validateFields()
    if (unitEditing) await http.put(`/personnel/org-units/${unitEditing.id}`, v)
    else await http.post('/personnel/org-units', v)
    message.success('部门已保存'); setUnitOpen(false); loadUnits()
  }
  const removeUnit = (id: number) =>
    http.delete(`/personnel/org-units/${id}`).then(() => {
      message.success('部门已删除'); if (selectedUnit === id) setSelectedUnit(null); refresh()
    })

  // ---------- 员工(含多岗)----------
  const openEmp = (e: Employee | null) => {
    setEmpEditing(e); empForm.resetFields()
    if (e) empForm.setFieldsValue(e)
    else empForm.setFieldsValue({
      status: 'active',
      positions: [{ org_unit_id: selectedUnit ?? null, role_type: 'staff', position: '' }],
    })
    setEmpOpen(true)
  }
  const saveEmp = async () => {
    const v = await empForm.validateFields()
    if (empEditing) await http.put(`/personnel/employees/${empEditing.id}`, v)
    else await http.post('/personnel/employees', v)
    message.success('员工已保存'); setEmpOpen(false); refresh()
  }
  const removeEmp = (id: number) =>
    http.delete(`/personnel/employees/${id}`).then(() => { message.success('已删除'); refresh() })

  // ---------- 向部门添加成员(选已有或新建)----------
  const openMember = () => {
    if (!selectedUnit) return message.warning('请先在左侧选择一个部门')
    setPickedEmp(null); memberForm.resetFields()
    memberForm.setFieldsValue({ role_type: 'staff' })
    setMemberOpen(true)
  }
  const onPickEmp = (id: number | undefined) => {
    setPickedEmp(id ? allEmployees.find((e) => e.id === id) || null : null)
  }
  const saveMember = async () => {
    const v = await memberForm.validateFields()
    await http.post(`/personnel/org-units/${selectedUnit}/members`, v)
    message.success('成员已添加'); setMemberOpen(false); refresh()
  }

  const posTags = (positions: Position[]) => (
    <Space wrap size={[4, 4]}>
      {positions.length === 0 && <span style={{ color: '#bbb' }}>未任职</span>}
      {positions.map((p, i) => (
        <Tag key={i} color={ROLE_COLOR[p.role_type]}>
          {p.org_unit_name || '未分配'}·{ROLE_LABEL[p.role_type] || p.role_type}
          {p.position ? `·${p.position}` : ''}
        </Tag>
      ))}
    </Space>
  )

  const columns = [
    { title: '工号', dataIndex: 'employee_no', width: 80, render: (v: string) => v || '-' },
    { title: '姓名', dataIndex: 'name', width: 90 },
    { title: '任职(部门·角色·职位)', dataIndex: 'positions', render: posTags },
    { title: '电话', dataIndex: 'phone', width: 120, render: (v: string) => v || '-' },
    { title: '持股%', dataIndex: 'equity_ratio', width: 70, render: (v: number) => (v ? `${v}%` : '-') },
    {
      title: '状态', dataIndex: 'status', width: 75,
      render: (s: string) => (s === 'active' ? <Tag color="green">在职</Tag> : <Tag>离职</Tag>),
    },
    {
      title: '操作', width: 100, render: (_: unknown, r: Employee) => (
        <Space>
          <a onClick={() => openEmp(r)}>编辑</a>
          <Popconfirm title="删除该员工?" onConfirm={() => removeEmp(r.id)}>
            <a style={{ color: '#cf1322' }}>删除</a>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <Row gutter={16}>
      <Col xs={24} lg={7}>
        <Card size="small" title={<><ApartmentOutlined /> 组织架构</>}
          extra={<Button size="small" type="primary" icon={<PlusOutlined />}
            onClick={() => openUnit(null, null)}>顶级部门</Button>}>
          <div style={{ marginBottom: 8 }}>
            <a onClick={() => setSelectedUnit(null)}
              style={{ fontWeight: selectedUnit === null ? 600 : 400 }}>全部员工</a>
          </div>
          <Tree treeData={treeData} defaultExpandAll blockNode
            selectedKeys={selectedUnit ? [selectedUnit] : []}
            onSelect={(keys) => setSelectedUnit(keys[0] ? Number(keys[0]) : null)}
            titleRender={(node) => {
              const unit = units.find((u) => u.id === node.key)!
              return (
                <span>
                  {node.title as string}
                  <span style={{ marginLeft: 8 }}>
                    <a onClick={(e) => { e.stopPropagation(); openUnit(unit, null) }}><PlusOutlined /></a>{' '}
                    <a onClick={(e) => { e.stopPropagation(); openUnit(null, unit) }}><EditOutlined /></a>{' '}
                    <Popconfirm title="删除该部门?" onConfirm={() => removeUnit(unit.id)}>
                      <a style={{ color: '#cf1322' }} onClick={(e) => e.stopPropagation()}><DeleteOutlined /></a>
                    </Popconfirm>
                  </span>
                </span>
              )
            }} />
          {units.length === 0 && <div style={{ color: '#999' }}>暂无部门,点右上角新增</div>}
        </Card>
      </Col>

      <Col xs={24} lg={17}>
        <Card size="small"
          title={`员工档案${selectedUnit ? ' — ' + unitName(selectedUnit) : ''}`}
          extra={
            <Space wrap>
              <Segmented size="small" value={roleFilter} onChange={(v) => setRoleFilter(v as string)}
                options={[{ label: '全部', value: 'all' }, ...roleOptions]} />
              <Button size="small" icon={<UsergroupAddOutlined />} disabled={!selectedUnit}
                onClick={openMember}>向本部门添加成员</Button>
              <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => openEmp(null)}>新增员工</Button>
            </Space>
          }>
          <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={employees}
            pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 人` }} scroll={{ x: 800 }} />
        </Card>
      </Col>

      {/* 部门 modal */}
      <Modal title={unitEditing ? '编辑部门' : '新增部门'} open={unitOpen}
        onOk={saveUnit} onCancel={() => setUnitOpen(false)} okText="保存">
        <Form form={unitForm} layout="vertical">
          <Form.Item name="name" label="部门名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="parent_id" label="上级部门">
            <Select allowClear placeholder="顶级部门(留空)"
              options={units.filter((u) => u.id !== unitEditing?.id).map((u) => ({ value: u.id, label: u.name }))} />
          </Form.Item>
          <Form.Item name="note" label="备注"><Input /></Form.Item>
        </Form>
      </Modal>

      {/* 员工 modal(个人信息 + 多岗任职)*/}
      <Modal title={empEditing ? '编辑员工' : '新增员工'} open={empOpen} width={680}
        onOk={saveEmp} onCancel={() => setEmpOpen(false)} okText="保存">
        <Form form={empForm} layout="vertical">
          <Row gutter={12}>
            <Col span={8}><Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="employee_no" label="工号"><Input /></Form.Item></Col>
            <Col span={8}>
              <Form.Item name="gender" label="性别">
                <Select allowClear options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
              </Form.Item>
            </Col>
            <Col span={8}><Form.Item name="phone" label="电话"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="hire_date" label="入职日期"><Input placeholder="2024-01-01" /></Form.Item></Col>
            <Col span={8}>
              <Form.Item name="equity_ratio" label="持股比例(%)">
                <InputNumber min={0} max={100} precision={4} style={{ width: '100%' }} placeholder="股东填写" />
              </Form.Item>
            </Col>
            <Col span={8}><Form.Item name="id_number" label="身份证号"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="email" label="邮箱"><Input /></Form.Item></Col>
            <Col span={8}>
              <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                <Select options={[{ value: 'active', label: '在职' }, { value: 'left', label: '离职' }]} />
              </Form.Item>
            </Col>
            <Col span={24}><Form.Item name="note" label="备注"><Input.TextArea rows={1} /></Form.Item></Col>
          </Row>

          <Divider orientation="left" plain>任职(可跨多个部门兼任不同角色)</Divider>
          <Form.List name="positions">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline" style={{ display: 'flex', marginBottom: 8 }}>
                    <Form.Item name={[field.name, 'org_unit_id']} style={{ marginBottom: 0 }}>
                      <Select placeholder="部门" style={{ width: 150 }} allowClear
                        options={units.map((u) => ({ value: u.id, label: u.name }))} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'role_type']} initialValue="staff" style={{ marginBottom: 0 }}>
                      <Select placeholder="角色" style={{ width: 120 }} options={roleOptions} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'position']} style={{ marginBottom: 0 }}>
                      <Input placeholder="职位(如 财务经理)" style={{ width: 180 }} />
                    </Form.Item>
                    <DeleteOutlined style={{ color: '#cf1322' }} onClick={() => remove(field.name)} />
                  </Space>
                ))}
                <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ role_type: 'staff' })}>
                  增加一个任职部门
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>

      {/* 向部门添加成员 */}
      <Modal title={`向「${unitName(selectedUnit)}」添加成员`} open={memberOpen}
        onOk={saveMember} onCancel={() => setMemberOpen(false)} okText="添加">
        <Form form={memberForm} layout="vertical">
          <Form.Item name="employee_id" label="选择已有员工(兼职)">
            <Select allowClear showSearch placeholder="选已有员工,自动带入其档案" optionFilterProp="label"
              onChange={onPickEmp}
              options={allEmployees.map((e) => ({ value: e.id, label: `${e.name}${e.employee_no ? ` (${e.employee_no})` : ''}` }))} />
          </Form.Item>
          {pickedEmp && (
            <Alert style={{ marginBottom: 12 }} type="info" showIcon
              message={`已有档案:${pickedEmp.name}  电话 ${pickedEmp.phone || '-'}  现有 ${pickedEmp.positions.length} 个任职`} />
          )}
          {!pickedEmp && (
            <Form.Item name="name" label="或新建员工姓名">
              <Input placeholder="不选已有员工时,填写新员工姓名" />
            </Form.Item>
          )}
          <Space>
            <Form.Item name="role_type" label="角色" initialValue="staff">
              <Select style={{ width: 130 }} options={roleOptions} />
            </Form.Item>
            <Form.Item name="position" label="职位">
              <Input placeholder="如 技术顾问" style={{ width: 200 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Row>
  )
}
