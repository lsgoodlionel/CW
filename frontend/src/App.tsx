import { useEffect, useState } from 'react'
import { Layout, Menu, Dropdown, Spin, Modal, Form, Input, message, Tag } from 'antd'
import {
  DashboardOutlined, FileTextOutlined, ProfileOutlined, BarChartOutlined,
  SettingOutlined, BookOutlined, HistoryOutlined, TeamOutlined, IdcardOutlined,
  PartitionOutlined, SolutionOutlined, SafetyCertificateOutlined, UserOutlined,
  LogoutOutlined, KeyOutlined, FileDoneOutlined, AuditOutlined,
} from '@ant-design/icons'
import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import VoucherList from './pages/VoucherList'
import VoucherEdit from './pages/VoucherEdit'
import Accounts from './pages/Accounts'
import Customers from './pages/Customers'
import Personnel from './pages/Personnel'
import Workflow from './pages/Workflow'
import ApprovalCenter from './pages/ApprovalCenter'
import Expense from './pages/Expense'
import ExpenseApply from './pages/ExpenseApply'
import Reports from './pages/Reports'
import Ledgers from './pages/Ledgers'
import Logs from './pages/Logs'
import UsersAdmin from './pages/Users'
import Settings from './pages/Settings'
import Login from './pages/Login'
import { http, getToken, clearToken, AuthUser, hasPerm } from './api'

const { Sider, Header, Content } = Layout

// 每个菜单项对应权限模块(用于按 <module>:view 过滤显示)
const MENU = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘', module: '' },
  { key: '/vouchers', icon: <FileTextOutlined />, label: '记账凭证', module: 'voucher' },
  { key: '/customers', icon: <TeamOutlined />, label: '往来单位', module: 'customer' },
  { key: '/personnel', icon: <IdcardOutlined />, label: '人员管理', module: 'personnel' },
  { key: '/accounts', icon: <ProfileOutlined />, label: '会计科目', module: 'account' },
  { key: '/ledgers', icon: <BookOutlined />, label: '会计账簿', module: 'ledger' },
  { key: '/reports', icon: <BarChartOutlined />, label: '财务报表', module: 'report' },
  { key: '/workflow', icon: <PartitionOutlined />, label: '流程设计', module: 'workflow' },
  { key: '/approvals', icon: <AuditOutlined />, label: '审批中心', module: 'approval' },
  { key: '/expense-apply', icon: <FileDoneOutlined />, label: '费用申请', module: 'expense_apply' },
  { key: '/expense', icon: <SolutionOutlined />, label: '费用报销', module: 'expense' },
  { key: '/logs', icon: <HistoryOutlined />, label: '操作日志', module: 'logs' },
  { key: '/users', icon: <SafetyCertificateOutlined />, label: '用户与权限', module: 'user' },
  { key: '/settings', icon: <SettingOutlined />, label: '企业信息', module: 'company' },
]

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [pwOpen, setPwOpen] = useState(false)
  const [pwForm] = Form.useForm()

  useEffect(() => {
    if (!getToken()) { setLoading(false); return }
    http.get<AuthUser>('/auth/me')
      .then((r) => setUser(r.data))
      .catch(() => clearToken())
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Spin style={{ display: 'block', marginTop: '20vh' }} size="large" />

  if (location.pathname === '/login' || !user) {
    return (
      <Routes>
        <Route path="*" element={<Login onSuccess={(u) => { setUser(u); navigate('/') }} />} />
      </Routes>
    )
  }

  const visibleMenu = MENU.filter((m) => !m.module || hasPerm(user, m.module, 'view'))
  const selectedKey =
    visibleMenu.map((m) => m.key)
      .filter((k) => k !== '/' && location.pathname.startsWith(k))
      .sort((a, b) => b.length - a.length)[0] || '/'

  const logout = () => { clearToken(); setUser(null); navigate('/login') }

  const changePassword = async () => {
    const v = await pwForm.validateFields()
    await http.post('/auth/change-password', v)
    message.success('密码已修改,请重新登录'); setPwOpen(false)
    setTimeout(logout, 800)
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth="0">
        <div className="app-logo">💰 财务记账系统</div>
        <Menu theme="dark" mode="inline" selectedKeys={[selectedKey]}
          items={visibleMenu.map(({ key, icon, label }) => ({ key, icon, label }))}
          onClick={({ key }) => navigate(key)} />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex',
          alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 18, fontWeight: 600 }}>
            {visibleMenu.find((m) => m.key === selectedKey)?.label}
          </span>
          <Dropdown menu={{ items: [
            { key: 'pw', icon: <KeyOutlined />, label: '修改密码', onClick: () => { pwForm.resetFields(); setPwOpen(true) } },
            { key: 'out', icon: <LogoutOutlined />, label: '退出登录', onClick: logout },
          ] }}>
            <span style={{ cursor: 'pointer' }}>
              <UserOutlined /> {user.display_name || user.username}
              {user.is_super_admin && <Tag color="red" style={{ marginLeft: 6 }}>超管</Tag>}
            </span>
          </Dropdown>
        </Header>
        <Content style={{ margin: 24 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/vouchers" element={<VoucherList />} />
            <Route path="/vouchers/new" element={<VoucherEdit />} />
            <Route path="/vouchers/:id" element={<VoucherEdit />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/personnel" element={<Personnel />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/ledgers" element={<Ledgers />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/workflow" element={<Workflow />} />
            <Route path="/approvals" element={<ApprovalCenter />} />
            <Route path="/expense-apply" element={<ExpenseApply />} />
            <Route path="/expense" element={<Expense />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/users" element={<UsersAdmin />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Content>
      </Layout>

      <Modal title="修改密码" open={pwOpen} onOk={changePassword} onCancel={() => setPwOpen(false)} okText="确认">
        <Form form={pwForm} layout="vertical">
          <Form.Item name="old_password" label="原密码" rules={[{ required: true }]}><Input.Password /></Form.Item>
          <Form.Item name="new_password" label="新密码(至少6位)" rules={[{ required: true, min: 6 }]}><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </Layout>
  )
}
