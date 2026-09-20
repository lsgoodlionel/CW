import { useState } from 'react'
import { Card, Form, Input, Button, Typography, message } from 'antd'
import { UserOutlined, LockOutlined, BankOutlined, IdcardOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { http, setToken, AuthUser } from '../api'

const { Title, Text } = Typography

/** 用户名最小长度 */
const MIN_USERNAME_LEN = 2
/** 密码最小长度 */
const MIN_PASSWORD_LEN = 6

/**
 * 自助注册响应契约。注册即自动登录:后端复用登录响应结构,
 * 注册场景下 token/user 必定存在,need_tenant 恒为 false。
 */
interface RegisterResponse {
  token: string
  user: AuthUser
  need_tenant: false
  tenants: []
}

/** 注册表单值 */
interface RegisterFormValues {
  tenant_name: string
  username: string
  password: string
  display_name?: string
}

interface RegisterProps {
  onSuccess: (user: AuthUser) => void
  /** 返回登录视图(可选;私有化下无注册入口,此处不影响) */
  onBackToLogin?: () => void
}

export default function Register({ onSuccess, onBackToLogin }: RegisterProps) {
  const [loading, setLoading] = useState(false)

  const submit = async (values: RegisterFormValues) => {
    setLoading(true)
    try {
      const r = await http.post<RegisterResponse>('/auth/register', values)
      const { token, user } = r.data
      setToken(token)
      message.success('注册成功,已自动登录')
      onSuccess(user)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg,#1f6feb 0%,#0b2a63 100%)',
    }}>
      <Card style={{ width: 380, boxShadow: '0 12px 40px rgba(0,0,0,.2)' }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <Title level={3} style={{ marginBottom: 0 }}>💰 注册企业</Title>
          <Text type="secondary">创建企业并成为管理员</Text>
        </div>

        <Form onFinish={submit} size="large" layout="vertical">
          <Form.Item
            name="tenant_name"
            rules={[{ required: true, message: '请输入企业/租户名称' }]}
          >
            <Input prefix={<BankOutlined />} placeholder="企业/租户名称" autoFocus />
          </Form.Item>
          <Form.Item
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: MIN_USERNAME_LEN, message: `用户名至少 ${MIN_USERNAME_LEN} 个字符` },
            ]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: MIN_PASSWORD_LEN, message: `密码至少 ${MIN_PASSWORD_LEN} 位` },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item name="display_name">
            <Input prefix={<IdcardOutlined />} placeholder="显示名(可选)" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>注册并进入</Button>
        </Form>

        {onBackToLogin && (
          <Button
            type="link" block icon={<ArrowLeftOutlined />}
            style={{ marginTop: 8 }} disabled={loading}
            onClick={onBackToLogin}
          >
            已有账号?返回登录
          </Button>
        )}
      </Card>
    </div>
  )
}
