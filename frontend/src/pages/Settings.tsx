import { useEffect, useState } from 'react'
import {
  Card, Form, Input, Button, message, Spin, Divider, Space, Upload, Typography, Modal, Row, Col,
} from 'antd'
import { DownloadOutlined, UploadOutlined, ExclamationCircleFilled } from '@ant-design/icons'
import { http, Company } from '../api'

const { Text, Paragraph } = Typography

interface FieldDef { name: keyof Company; label: string; required?: boolean; placeholder?: string }

const WORKINDUSTRY: FieldDef[] = [
  { name: 'name', label: '公司名称', required: true },
  { name: 'tax_number', label: '纳税人识别号(税号)' },
  { name: 'legal_person', label: '法定代表人 / 负责人' },
  { name: 'industry', label: '所属行业' },
  { name: 'establish_date', label: '成立日期', placeholder: '如 2020-01-01' },
  { name: 'reg_address', label: '注册地址' },
  { name: 'phone', label: '联系电话' },
]

const FINANCE: FieldDef[] = [
  { name: 'bank_name', label: '开户银行' },
  { name: 'bank_account', label: '银行账号' },
  { name: 'accounting_standard', label: '执行会计准则', placeholder: '小企业会计准则' },
  { name: 'currency', label: '记账本位币', placeholder: '人民币' },
  { name: 'start_period', label: '启用会计期间', placeholder: '如 2025-01' },
]

const STAFF: FieldDef[] = [
  { name: 'accountant', label: '会计主管' },
  { name: 'auditor', label: '审核' },
  { name: 'bookkeeper', label: '记账' },
  { name: 'recorder', label: '录入' },
]

export default function Settings() {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    http.get<Company>('/company')
      .then((r) => form.setFieldsValue(r.data))
      .finally(() => setLoading(false))
  }, [form])

  const save = async () => {
    const v = await form.validateFields()
    setSaving(true)
    try {
      await http.put('/company', v)
      message.success('企业信息已保存')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spin style={{ display: 'block', marginTop: 80 }} />

  const renderFields = (fields: FieldDef[]) => (
    <Row gutter={16}>
      {fields.map((f) => (
        <Col xs={24} md={12} key={f.name}>
          <Form.Item name={f.name} label={f.label}
            rules={f.required ? [{ required: true, message: `请填写${f.label}` }] : []}>
            <Input placeholder={f.placeholder} />
          </Form.Item>
        </Col>
      ))}
    </Row>
  )

  return (
    <>
      <Card title="企业基本信息" style={{ maxWidth: 760 }}>
        <Form form={form} layout="vertical">
          <Divider orientation="left" plain>工商登记</Divider>
          {renderFields(WORKINDUSTRY)}
          <Divider orientation="left" plain>财务设置</Divider>
          {renderFields(FINANCE)}
          <Divider orientation="left" plain>人员</Divider>
          {renderFields(STAFF)}
          <Button type="primary" loading={saving} onClick={save}>保存</Button>
        </Form>
      </Card>

      <DataBackup />
    </>
  )
}

function DataBackup() {
  const [importing, setImporting] = useState(false)

  const exportData = () => {
    // 直接以浏览器下载方式导出 zip 备份
    window.open('/api/data/export', '_blank')
  }

  const doImport = (file: File) => {
    Modal.confirm({
      title: '确认导入备份?',
      icon: <ExclamationCircleFilled />,
      content: '导入将【整体替换】当前所有数据(凭证、附件、科目、企业信息),此操作不可撤销。',
      okText: '确认导入', okButtonProps: { danger: true }, cancelText: '取消',
      onOk: async () => {
        setImporting(true)
        const fd = new FormData()
        fd.append('file', file)
        try {
          const r = await http.post('/data/import', fd)
          message.success(
            `导入成功:科目 ${r.data.accounts}、凭证 ${r.data.vouchers}、附件 ${r.data.attachments}`,
          )
        } finally {
          setImporting(false)
        }
      },
    })
    return false // 阻止 antd 默认上传
  }

  return (
    <Card title="数据备份 / 恢复" style={{ maxWidth: 560, marginTop: 16 }}>
      <Paragraph type="secondary">
        导出会将企业信息、会计科目、全部凭证与附件打包为一个 zip 文件;
        导入可从该 zip 恢复整站数据(用于迁移或备份还原)。
      </Paragraph>
      <Space>
        <Button type="primary" icon={<DownloadOutlined />} onClick={exportData}>
          一键导出备份
        </Button>
        <Upload accept=".zip" showUploadList={false} beforeUpload={doImport}>
          <Button icon={<UploadOutlined />} loading={importing}>导入备份(.zip)</Button>
        </Upload>
      </Space>
      <Divider style={{ margin: '16px 0' }} />
      <Text type="warning">注意:导入为整体替换,请先导出当前数据做好备份。</Text>
    </Card>
  )
}
