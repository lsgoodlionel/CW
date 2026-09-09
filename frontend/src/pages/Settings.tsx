import { useEffect, useState } from 'react'
import {
  Card, Form, Input, Button, message, Spin, Divider, Space, Upload, Typography, Modal, Row, Col,
  Select, Switch, InputNumber,
} from 'antd'
import { DownloadOutlined, UploadOutlined, ExclamationCircleFilled } from '@ant-design/icons'
import { http, Company, withToken } from '../api'

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
      .then((r) => form.setFieldsValue({
        ...r.data,
        large_voucher_threshold: Number((r.data as { large_voucher_threshold?: number | string }).large_voucher_threshold || 0),
      }))
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
          <Divider orientation="left" plain>税务身份</Divider>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="taxpayer_kind" label="增值税纳税人身份"
                tooltip="影响增值税征收率与合同/发票默认税率:一般纳税人 13/9/6%,小规模纳税人 1/3%">
                <Select options={[
                  { value: 'general', label: '一般纳税人' },
                  { value: 'small', label: '小规模纳税人' },
                ]} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="is_small_micro" label="小型微利企业(手动值)" valuePropName="checked"
                tooltip="自动判断关闭时以此手动值为准;开启自动判断时,报表按标准自动复核并可手动覆盖">
                <Switch checkedChildren="是" unCheckedChildren="否" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="small_micro_auto" label="小型微利自动判断" valuePropName="checked"
                tooltip="开启后,报表生成时按标准(应纳税所得额≤300万、从业人数≤300、资产总额≤5000万、非限制行业)自动判断;关闭则用上方手动值">
                <Switch checkedChildren="自动" unCheckedChildren="手动" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="restricted_industry" label="从事国家限制或禁止行业" valuePropName="checked"
                tooltip="小型微利企业要求非国家限制或禁止行业;勾选则不符合小型微利条件">
                <Switch checkedChildren="是" unCheckedChildren="否" />
              </Form.Item>
            </Col>
          </Row>
          <Divider orientation="left" plain>审批设置</Divider>
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Form.Item name="large_voucher_threshold" label="大额凭证审批阈值(元)"
                tooltip="0=不启用凭证审批;>0 时,金额≥该值的凭证在无「凭证直录」权限时须提交审批,通过后才过账入账。还需在「流程设计」新建并启用「记账凭证(大额)」流程">
                <InputNumber min={0} precision={2} style={{ width: 200 }} placeholder="0 表示不启用" />
              </Form.Item>
            </Col>
          </Row>
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
    window.open(withToken('/api/data/export'), '_blank')
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
