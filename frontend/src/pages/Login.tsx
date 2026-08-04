import { useState } from 'react'
import { Card, Form, Input, Button, Typography, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { http, setToken, AuthUser } from '../api'

const { Title, Text } = Typography

interface LoginProps { onSuccess: (user: AuthUser) => void }

export default function Login({ onSuccess }: LoginProps) {
  const [loading, setLoading] = useState(false)

  const submit = async (v: { username: string; password: string }) => {
    setLoading(true)
    try {
      const r = await http.post<{ token: string; user: AuthUser }>('/auth/login', v)
      setToken(r.data.token)
      message.success('登录成功')
      onSuccess(r.data.user)
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
          <Title level={3} style={{ marginBottom: 0 }}>💰 财务记账系统</Title>
          <Text type="secondary">请登录后使用</Text>
        </div>
        <Form onFinish={submit} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>登录</Button>
        </Form>
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 12 }}>
          初始超级管理员:admin / admin123(请登录后立即修改密码)
        </Text>
      </Card>
    </div>
  )
}
