import { useEffect, useState, useCallback, useMemo } from 'react'
import {
  Row, Col, Card, Tree, Button, Table, Tag, Space, Modal, Form, Input, Select,
  Popconfirm, message, Segmented, InputNumber,
} from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ApartmentOutlined } from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'
import { http, OrgUnit, Employee, ROLE_LABEL } from '../api'

const ROLE_COLOR: Record<string, string> = {
  shareholder: 'gold', management: 'blue', staff: 'default', other: 'purple',
}

export default function Personnel() {
  const [units, setUnits] = useState<OrgUnit[]>([])
  const [employees, setEmployees] = useState<Employee[]>([])
  const [selectedUnit, setSelectedUnit] = useState<number | null>(null)
  const [roleFilter, setRoleFilter] = useState('all')
  const [loading, setLoading] = useState(false)

  // 部门 modal
  const [unitOpen, setUnitOpen] = useState(false)
  const [unitForm] = Form.useForm()
  const [unitEditing, setUnitEditing] = useState<OrgUnit | null>(null)
  // 员工 modal
  const [empOpen, setEmpOpen] = useState(false)
  const [empForm] = Form.useForm()
  const [empEditing, setEmpEditing] = useState<Employee | null>(null)

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

  useEffect(() => { loadUnits() }, [loadUnits])
  useEffect(() => { loadEmployees() }, [loadEmployees])

  const treeData = useMemo<DataNode[]>(() => {
    const byParent: Record<string, OrgUnit[]> = {}
    units.forEach((u) => {
      const k = String(u.parent_id ?? 'root')
      ;(byParent[k] ||= []).push(u)
    })
    const build = (pid: string): DataNode[] =>
      (byParent[pid] || []).map((u) => ({
        key: u.id,
        title: `${u.name} (${u.employee_count})`,
        children: build(String(u.id)),
      }))
    return build('root')
  }, [units])

  const openUnit = (parent: OrgUnit | null, editing: OrgUnit | null) => {
    setUnitEditing(editing)
    unitForm.resetFields()
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
      message.success('部门已删除'); if (selectedUnit === id) setSelectedUnit(null); loadUnits(); loadEmployees()
    })

  const openEmp = (e: Employee | null) => {
    setEmpEditing(e)
    empForm.resetFields()
    if (e) empForm.setFieldsValue(e)
    else empForm.setFieldsValue({ role_type: 'staff', status: 'active', org_unit_id: selectedUnit ?? undefined })
    setEmpOpen(true)
  }
  const saveEmp = async () => {
    const v = await empForm.validateFields()
    if (empEditing) await http.put(`/personnel/employees/${empEditing.id}`, v)
    else await http.post('/personnel/employees', v)
    message.success('员工已保存'); setEmpOpen(false); loadEmployees(); loadUnits()
  }
  const removeEmp = (id: number) =>
    http.delete(`/personnel/employees/${id}`).then(() => { message.success('已删除'); loadEmployees(); loadUnits() })

  const selectedName = units.find((u) => u.id === selectedUnit)?.name

  const columns = [
    { title: '工号', dataIndex: 'employee_no', width: 90 },
    { title: '姓名', dataIndex: 'name', width: 100 },
    {
      title: '角色', dataIndex: 'role_type', width: 90,
      render: (t: string) => <Tag color={ROLE_COLOR[t]}>{ROLE_LABEL[t] || t}</Tag>,
    },
    { title: '部门', dataIndex: 'org_unit_name', width: 110, render: (v: string) => v || '-' },
    { title: '职位', dataIndex: 'position', width: 110, render: (v: string) => v || '-' },
    { title: '电话', dataIndex: 'phone', width: 130, render: (v: string) => v || '-' },
    {
      title: '持股%', dataIndex: 'equity_ratio', width: 80,
      render: (v: number) => (v ? `${v}%` : '-'),
    },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (s: string) => (s === 'active' ? <Tag color="green">在职</Tag> : <Tag>离职</Tag>),
    },
    {
      title: '操作', width: 110, render: (_: unknown, r: Employee) => (
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
                    <a onClick={(e) => { e.stopPropagation(); openUnit(unit, null) }}><PlusOutlined /></a>
                    {' '}
                    <a onClick={(e) => { e.stopPropagation(); openUnit(null, unit) }}><EditOutlined /></a>
                    {' '}
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
          title={`员工档案${selectedName ? ' — ' + selectedName : ''}`}
          extra={
            <Space>
              <Segmented size="small" value={roleFilter} onChange={(v) => setRoleFilter(v as string)}
                options={[{ label: '全部', value: 'all' },
                  ...Object.entries(ROLE_LABEL).map(([value, label]) => ({ value, label }))]} />
              <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => openEmp(null)}>新增员工</Button>
            </Space>
          }>
          <Table rowKey="id" size="small" loading={loading} columns={columns} dataSource={employees}
            pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 人` }} scroll={{ x: 900 }} />
        </Card>
      </Col>

      {/* 部门 modal */}
      <Modal title={unitEditing ? '编辑部门' : '新增部门'} open={unitOpen}
        onOk={saveUnit} onCancel={() => setUnitOpen(false)} okText="保存">
        <Form form={unitForm} layout="vertical">
          <Form.Item name="name" label="部门名称" rules={[{ required: true }]}>
            <Input placeholder="如 技术部" />
          </Form.Item>
          <Form.Item name="parent_id" label="上级部门">
            <Select allowClear placeholder="顶级部门(留空)"
              options={units.filter((u) => u.id !== unitEditing?.id)
                .map((u) => ({ value: u.id, label: u.name }))} />
          </Form.Item>
          <Form.Item name="note" label="备注"><Input /></Form.Item>
        </Form>
      </Modal>

      {/* 员工 modal */}
      <Modal title={empEditing ? '编辑员工' : '新增员工'} open={empOpen} width={620}
        onOk={saveEmp} onCancel={() => setEmpOpen(false)} okText="保存">
        <Form form={empForm} layout="vertical">
          <Row gutter={12}>
            <Col span={12}><Form.Item name="name" label="姓名" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="employee_no" label="工号"><Input /></Form.Item></Col>
            <Col span={12}>
              <Form.Item name="role_type" label="角色" rules={[{ required: true }]}>
                <Select options={Object.entries(ROLE_LABEL).map(([value, label]) => ({ value, label }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="org_unit_id" label="所属部门">
                <Select allowClear options={units.map((u) => ({ value: u.id, label: u.name }))} />
              </Form.Item>
            </Col>
            <Col span={12}><Form.Item name="position" label="职位"><Input /></Form.Item></Col>
            <Col span={12}>
              <Form.Item name="gender" label="性别">
                <Select allowClear options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
              </Form.Item>
            </Col>
            <Col span={12}><Form.Item name="phone" label="电话"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="hire_date" label="入职日期"><Input placeholder="如 2024-01-01" /></Form.Item></Col>
            <Col span={12}><Form.Item name="id_number" label="身份证号"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="email" label="邮箱"><Input /></Form.Item></Col>
            <Col span={12}>
              <Form.Item name="equity_ratio" label="持股比例(%)">
                <InputNumber min={0} max={100} precision={4} style={{ width: '100%' }} placeholder="股东填写" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="status" label="状态" rules={[{ required: true }]}>
                <Select options={[{ value: 'active', label: '在职' }, { value: 'left', label: '离职' }]} />
              </Form.Item>
            </Col>
            <Col span={24}><Form.Item name="note" label="备注"><Input.TextArea rows={2} /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </Row>
  )
}
