import { useEffect, useState } from 'react'
import { Card, Descriptions, Tag, Button, Space, Spin, Typography } from 'antd'
import {
  BookOutlined, DownloadOutlined, GithubOutlined, BugOutlined, MailOutlined,
} from '@ant-design/icons'
import { http } from '../api'

const { Paragraph, Text } = Typography

interface AboutInfo {
  name: string
  version: string
  released: string
  description: string
  developer: string
  repo_url: string
  feedback_url: string
  contact: string
  manual_url: string
  manual_download: string
  tech_stack: string[]
}

export default function About() {
  const [info, setInfo] = useState<AboutInfo | null>(null)

  useEffect(() => {
    http.get<AboutInfo>('/about').then((r) => setInfo(r.data)).catch(() => setInfo(null))
  }, [])

  if (!info) return <Spin style={{ display: 'block', marginTop: 80 }} />

  return (
    <Space direction="vertical" size={16} style={{ display: 'flex', maxWidth: 820 }}>
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 40 }}>💰</div>
          <div>
            <h2 style={{ margin: 0 }}>{info.name}
              <Tag color="blue" style={{ marginLeft: 10 }}>v{info.version}</Tag>
            </h2>
            <Text type="secondary">发布日期 {info.released} · 开发者 {info.developer}</Text>
          </div>
        </div>
        <Paragraph style={{ marginTop: 16, marginBottom: 0 }}>{info.description}</Paragraph>
      </Card>

      <Card title={<span><BookOutlined /> 用户与管理员操作手册</span>}>
        <Paragraph type="secondary" style={{ marginBottom: 12 }}>
          覆盖服务器安装 → 管理员设置 → 用户使用 → 数据备份 → 升级 → 卸载 全流程,含界面示意与常见问题。
        </Paragraph>
        <Space wrap>
          <Button type="primary" icon={<BookOutlined />} href={info.manual_url} target="_blank">
            在线查看手册
          </Button>
          <Button icon={<DownloadOutlined />} href={info.manual_download} download="小企业财务记账系统-操作手册.html">
            下载手册
          </Button>
        </Space>
      </Card>

      <Card title="系统信息">
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="系统名称">{info.name}</Descriptions.Item>
          <Descriptions.Item label="当前版本">v{info.version}</Descriptions.Item>
          <Descriptions.Item label="发布日期">{info.released}</Descriptions.Item>
          <Descriptions.Item label="技术栈">
            <Space wrap>{info.tech_stack.map((t) => <Tag key={t}>{t}</Tag>)}</Space>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title={<span><BugOutlined /> 问题反馈与联系</span>}>
        <Space direction="vertical" size={10} style={{ display: 'flex' }}>
          <div><GithubOutlined /> 项目仓库:<a href={info.repo_url} target="_blank" rel="noreferrer">{info.repo_url}</a></div>
          <div><BugOutlined /> 问题反馈:<a href={info.feedback_url} target="_blank" rel="noreferrer">提交 GitHub Issue</a></div>
          <div><MailOutlined /> 联系方式:{info.contact}</div>
        </Space>
      </Card>
    </Space>
  )
}
