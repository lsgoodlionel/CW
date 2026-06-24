import { useEffect, useState } from 'react'
import {
  Card, Form, Input, Button, message, Spin, Divider, Space, Upload, Typography, Modal,
} from 'antd'
import { DownloadOutlined, UploadOutlined, ExclamationCircleFilled } from '@ant-design/icons'
import { http, Company } from '../api'

const { Text, Paragraph } = Typography

const FIELDS: { name: keyof Company; label: string }[] = [
  { name: 'name', label: '公司名称' },
  { name: 'legal_person', label: '单位负责人' },
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

  return (
    <>
      <Card title="企业基本信息" style={{ maxWidth: 560 }}>
        <Form form={form} layout="vertical">
          {FIELDS.map((f) => (
            <Form.Item key={f.name} name={f.name} label={f.label}
              rules={f.name === 'name' ? [{ required: true, message: '请填写公司名称' }] : []}>
              <Input />
            </Form.Item>
          ))}
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
