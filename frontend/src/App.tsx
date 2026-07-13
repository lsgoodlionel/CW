import { Layout, Menu } from 'antd'
import {
  DashboardOutlined,
  FileTextOutlined,
  ProfileOutlined,
  BarChartOutlined,
  SettingOutlined,
  BookOutlined,
  HistoryOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import VoucherList from './pages/VoucherList'
import VoucherEdit from './pages/VoucherEdit'
import Accounts from './pages/Accounts'
import Customers from './pages/Customers'
import Reports from './pages/Reports'
import Ledgers from './pages/Ledgers'
import Logs from './pages/Logs'
import Settings from './pages/Settings'

const { Sider, Header, Content } = Layout

const MENU = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/vouchers', icon: <FileTextOutlined />, label: '记账凭证' },
  { key: '/customers', icon: <TeamOutlined />, label: '客户管理' },
  { key: '/accounts', icon: <ProfileOutlined />, label: '会计科目' },
  { key: '/ledgers', icon: <BookOutlined />, label: '会计账簿' },
  { key: '/reports', icon: <BarChartOutlined />, label: '财务报表' },
  { key: '/logs', icon: <HistoryOutlined />, label: '操作日志' },
  { key: '/settings', icon: <SettingOutlined />, label: '企业信息' },
]

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const selectedKey =
    MENU.map((m) => m.key)
      .filter((k) => k !== '/' && location.pathname.startsWith(k))
      .sort((a, b) => b.length - a.length)[0] || '/'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider breakpoint="lg" collapsedWidth="0">
        <div className="app-logo">💰 财务记账系统</div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={MENU}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', paddingLeft: 24, fontSize: 18, fontWeight: 600 }}>
          {MENU.find((m) => m.key === selectedKey)?.label}
        </Header>
        <Content style={{ margin: 24 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/vouchers" element={<VoucherList />} />
            <Route path="/vouchers/new" element={<VoucherEdit />} />
            <Route path="/vouchers/:id" element={<VoucherEdit />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/ledgers" element={<Ledgers />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
