import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Form, Input, Button, Typography, Radio, Space, Spin, message } from 'antd'
import {
  UserOutlined, LockOutlined, BankOutlined, ArrowLeftOutlined,
  IdcardOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons'
import { http, setToken, AuthUser } from '../api'

const { Title, Text } = Typography

/** 用户名最小长度 */
const MIN_USERNAME_LEN = 2
/** 密码最小长度 */
const MIN_PASSWORD_LEN = 6

/** 可登录租户(SaaS 多租户模式下,后端在 need_tenant 时返回) */
interface TenantOption {
  id: number
  name: string
  code: string
  is_tenant_admin: boolean
}

/**
 * 登录响应契约(已升级为多租户)。
 * - 私有化/单租户:token+user 直接返回,need_tenant=false,tenants=[]。
 * - SaaS 多租户且需选择:token/user 为 null,need_tenant=true,tenants 为可选列表。
 */
interface LoginResponse {
  token: string | null
  user: AuthUser | null
  need_tenant: boolean
  tenants: TenantOption[]
}

/** 已输入的账号凭据,用于选定租户后携带 tenant_id 二次登录 */
interface Credentials {
  username: string
  password: string
}

type LoginStep = 'credentials' | 'selectTenant'

interface LoginProps {
  onSuccess: (user: AuthUser) => void
}

/** 自助注册开关响应契约 */
interface RegisterOpenResponse {
  success: boolean
}

/** 首次部署初始化状态契约(success=true 表示系统尚无任何用户,需首次设置) */
interface SetupState {
  success: boolean
}

/** 首次设置超级管理员表单值 */
interface SetupFormValues {
  username: string
  password: string
  confirmPassword: string
  display_name?: string
}

/**
 * 首次设置响应契约。设置即自动登录:后端复用登录响应结构,
 * 此场景下 token/user 必定存在,need_tenant 恒为 false。
 */
interface SetupResponse {
  token: string
  user: AuthUser
  need_tenant: false
  tenants: []
}

export default function Login({ onSuccess }: LoginProps) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState<LoginStep>('credentials')
  const [tenants, setTenants] = useState<TenantOption[]>([])
  const [credentials, setCredentials] = useState<Credentials | null>(null)
  const [selectedTenantId, setSelectedTenantId] = useState<number | null>(null)
  // 是否开放自助注册(saas 且开关开启;私有化恒 false)
  const [registerOpen, setRegisterOpen] = useState(false)
  // 首次部署初始化探测:checking 期间不渲染任何表单,避免闪烁
  const [checkingSetup, setCheckingSetup] = useState(true)
  const [needSetup, setNeedSetup] = useState(false)

  // 挂载时先探测是否需要首次设置超级管理员;失败则回退为正常登录(不阻断)
  useEffect(() => {
    http.get<SetupState>('/auth/setup-state')
      .then((r) => setNeedSetup(r.data.success === true))
      .catch(() => setNeedSetup(false))
      .finally(() => setCheckingSetup(false))
  }, [])

  // 无需首次设置时,再探测是否开放自助注册,以决定是否显示注册入口
  useEffect(() => {
    if (checkingSetup || needSetup) return
    http.get<RegisterOpenResponse>('/auth/register-open')
      .then((r) => setRegisterOpen(r.data.success))
      .catch(() => setRegisterOpen(false))
  }, [checkingSetup, needSetup])

  /** 完成进入系统:存令牌并回调(登录 / 首次设置共用) */
  const finishAuth = (token: string, user: AuthUser, successText: string) => {
    setToken(token)
    message.success(successText)
    onSuccess(user)
  }

  /**
   * 发起登录请求。tenantId 存在时携带,用于多租户二次登录。
   * 返回是否已完成登录(拿到 token)。
   */
  const requestLogin = async (creds: Credentials, tenantId?: number): Promise<boolean> => {
    const body = tenantId == null ? creds : { ...creds, tenant_id: tenantId }
    const r = await http.post<LoginResponse>('/auth/login', body)
    const { token, user, need_tenant, tenants: tenantList } = r.data

    // 私有化 / 单租户 / 已带 tenant_id:直接拿到令牌
    if (token && user) {
      finishAuth(token, user, '登录成功')
      return true
    }

    if (need_tenant) {
      if (tenantList.length === 0) {
        message.error('该账号未分配任何租户')
        return false
      }
      // 进入租户选择步骤
      setCredentials(creds)
      setTenants(tenantList)
      setSelectedTenantId(tenantList[0].id)
      setStep('selectTenant')
      return false
    }

    // 兜底:契约异常(既无令牌也未要求选租户)
    message.error('登录失败,请稍后重试')
    return false
  }

  const submitCredentials = async (v: Credentials) => {
    setLoading(true)
    try {
      await requestLogin(v)
    } finally {
      setLoading(false)
    }
  }

  /** 提交首次设置:创建超级管理员并自动登录进入系统 */
  const submitSetup = async (v: SetupFormValues) => {
    setLoading(true)
    try {
      const body = {
        username: v.username,
        password: v.password,
        display_name: v.display_name,
      }
      const r = await http.post<SetupResponse>('/auth/setup', body)
      const { token, user } = r.data
      finishAuth(token, user, '初始化成功,已自动登录')
    } finally {
      setLoading(false)
    }
  }

  const confirmTenant = async () => {
    if (!credentials || selectedTenantId == null) return
    setLoading(true)
    try {
      await requestLogin(credentials, selectedTenantId)
    } finally {
      setLoading(false)
    }
  }

  /** 返回上一步重填账号 */
  const backToCredentials = () => {
    setStep('credentials')
    setTenants([])
    setCredentials(null)
    setSelectedTenantId(null)
  }

  /** 卡片副标题文案随当前视图变化 */
  const subtitle = needSetup
    ? '首次部署初始化,请创建超级管理员'
    : step === 'credentials' ? '请登录后使用' : '请选择要进入的租户'

  const title = needSetup ? '🚀 系统初始化' : '💰 财务记账系统'

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'linear-gradient(135deg,#1f6feb 0%,#0b2a63 100%)',
    }}>
      <Card style={{ width: 380, boxShadow: '0 12px 40px rgba(0,0,0,.2)' }}>
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <Title level={3} style={{ marginBottom: 0 }}>{title}</Title>
          <Text type="secondary">{subtitle}</Text>
        </div>

        {checkingSetup ? (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <Spin />
          </div>
        ) : needSetup ? (
          <>
            <Form onFinish={submitSetup} size="large" layout="vertical">
              <Form.Item
                name="username"
                rules={[
                  { required: true, message: '请输入用户名' },
                  { min: MIN_USERNAME_LEN, message: `用户名至少 ${MIN_USERNAME_LEN} 个字符` },
                ]}
              >
                <Input prefix={<UserOutlined />} placeholder="超级管理员用户名" autoFocus />
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
              <Form.Item
                name="confirmPassword"
                dependencies={['password']}
                rules={[
                  { required: true, message: '请再次输入密码' },
                  ({ getFieldValue }) => ({
                    validator(_, value) {
                      if (!value || getFieldValue('password') === value) {
                        return Promise.resolve()
                      }
                      return Promise.reject(new Error('两次输入的密码不一致'))
                    },
                  }),
                ]}
              >
                <Input.Password prefix={<SafetyCertificateOutlined />} placeholder="确认密码" />
              </Form.Item>
              <Form.Item name="display_name">
                <Input prefix={<IdcardOutlined />} placeholder="显示名(可选)" />
              </Form.Item>
              <Button type="primary" htmlType="submit" block loading={loading}>初始化并进入</Button>
            </Form>
            <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 12 }}>
              该账号将成为系统首个超级管理员,请妥善保管凭据。
            </Text>
          </>
        ) : step === 'credentials' ? (
          <>
            <Form onFinish={submitCredentials} size="large">
              <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
                <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus />
              </Form.Item>
              <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
                <Input.Password prefix={<LockOutlined />} placeholder="密码" />
              </Form.Item>
              <Button type="primary" htmlType="submit" block loading={loading}>登录</Button>
            </Form>
            {registerOpen && (
              <div style={{ textAlign: 'center', marginTop: 12 }}>
                <Text type="secondary">没有账号?</Text>
                <Button type="link" style={{ padding: '0 4px' }} onClick={() => navigate('/register')}>
                  注册企业
                </Button>
              </div>
            )}
          </>
        ) : (
          <>
            <Radio.Group
              value={selectedTenantId}
              onChange={(e) => setSelectedTenantId(e.target.value)}
              style={{ display: 'block', marginBottom: 16 }}
            >
              <Space direction="vertical" style={{ width: '100%' }}>
                {tenants.map((t) => (
                  <Radio key={t.id} value={t.id} style={{ width: '100%', padding: '4px 0' }}>
                    <BankOutlined style={{ marginRight: 6 }} />
                    <Text strong>{t.name}</Text>
                    <Text type="secondary" style={{ marginLeft: 8 }}>({t.code})</Text>
                  </Radio>
                ))}
              </Space>
            </Radio.Group>
            <Button
              type="primary" block size="large" loading={loading}
              disabled={selectedTenantId == null}
              onClick={confirmTenant}
            >
              进入
            </Button>
            <Button
              type="link" block icon={<ArrowLeftOutlined />}
              style={{ marginTop: 8 }} disabled={loading}
              onClick={backToCredentials}
            >
              返回重新输入账号
            </Button>
          </>
        )}
      </Card>
    </div>
  )
}
