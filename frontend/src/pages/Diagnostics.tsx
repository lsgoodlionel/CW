import { useCallback, useEffect, useState } from 'react'
import {
  Card, Descriptions, Tag, Button, Space, Input, Select, message, Spin, Typography,
} from 'antd'
import { ReloadOutlined, CloudUploadOutlined } from '@ant-design/icons'
import { http } from '../api'

// 诊断状态返回结构(本地 interface,后端契约见页面头部说明,不改生成文件)
interface DiagStatus {
  enabled: boolean
  repo: string
  branch: string
  slug: string
  cooldown: number
  token_configured: boolean
  buffered_lines: number
}

interface DiagRecent {
  lines: string[]
}

interface DiagReportResult {
  success: boolean
  path: string
}

// 最近日志可选行数(避免魔法数字)
const LINE_COUNT_OPTIONS = [100, 200, 500] as const
const DEFAULT_LINE_COUNT = 200
const LOG_VIEW_HEIGHT = 420

export default function Diagnostics() {
  const [status, setStatus] = useState<DiagStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [note, setNote] = useState('')
  const [reporting, setReporting] = useState(false)
  const [lines, setLines] = useState<string[]>([])
  const [logLoading, setLogLoading] = useState(false)
  const [lineCount, setLineCount] = useState<number>(DEFAULT_LINE_COUNT)

  const loadStatus = useCallback(() => {
    setStatusLoading(true)
    http.get<DiagStatus>('/diag/status')
      .then((r) => setStatus(r.data))
      .finally(() => setStatusLoading(false))
  }, [])

  const loadRecent = useCallback((limit: number) => {
    setLogLoading(true)
    http.get<DiagRecent>('/diag/recent', { params: { limit } })
      .then((r) => setLines(r.data.lines))
      .finally(() => setLogLoading(false))
  }, [])

  useEffect(() => { loadStatus() }, [loadStatus])
  useEffect(() => { loadRecent(lineCount) }, [loadRecent, lineCount])

  const report = async () => {
    setReporting(true)
    try {
      const r = await http.post<DiagReportResult>('/diag/report', { note: note || undefined })
      message.success(`已上传:${r.data.path}`)
      setNote('')
      loadStatus()
    } finally {
      setReporting(false)
    }
  }

  const canUpload = Boolean(status?.enabled)

  return (
    <Space direction="vertical" size={16} style={{ display: 'flex' }}>
      <Card
        title="日志采集与上传状态"
        extra={
          <Button icon={<ReloadOutlined />} loading={statusLoading} onClick={loadStatus}>刷新</Button>
        }
      >
        <Spin spinning={statusLoading}>
          {status && (
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="采集状态">
                {status.enabled
                  ? <Tag color="green">启用</Tag>
                  : <Tag>未启用</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="令牌配置">
                {status.token_configured
                  ? <Tag color="green">已配置</Tag>
                  : <Tag color="red">未配置</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="排查仓库">{status.repo || '-'}</Descriptions.Item>
              <Descriptions.Item label="分支">{status.branch || '-'}</Descriptions.Item>
              <Descriptions.Item label="标识(slug)">{status.slug || '-'}</Descriptions.Item>
              <Descriptions.Item label="冷却时间(秒)">{status.cooldown}</Descriptions.Item>
              <Descriptions.Item label="缓冲日志行数">{status.buffered_lines}</Descriptions.Item>
            </Descriptions>
          )}
        </Spin>

        <Space direction="vertical" size={8} style={{ display: 'flex', marginTop: 16 }}>
          <Input
            placeholder="备注(可选,便于在排查仓库中区分本次上传)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={200}
            allowClear
          />
          <Space>
            <Button
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={reporting}
              disabled={!canUpload}
              onClick={report}
            >立即打包上传</Button>
            {!canUpload && (
              <Typography.Text type="danger">未配置 PAPER_REPO_TOKEN,无法上传</Typography.Text>
            )}
          </Space>
        </Space>
      </Card>

      <Card
        title="最近日志"
        extra={
          <Space>
            <span>行数:</span>
            <Select
              style={{ width: 100 }}
              value={lineCount}
              onChange={setLineCount}
              options={LINE_COUNT_OPTIONS.map((n) => ({ value: n, label: String(n) }))}
            />
            <Button icon={<ReloadOutlined />} loading={logLoading} onClick={() => loadRecent(lineCount)}>刷新日志</Button>
          </Space>
        }
      >
        <Spin spinning={logLoading}>
          <pre
            style={{
              height: LOG_VIEW_HEIGHT,
              overflow: 'auto',
              margin: 0,
              padding: 12,
              background: '#1e1e1e',
              color: '#d4d4d4',
              borderRadius: 4,
              fontFamily: 'Menlo, Monaco, Consolas, "Courier New", monospace',
              fontSize: 12,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}
          >
            {lines.length ? lines.join('\n') : '暂无日志'}
          </pre>
        </Spin>
      </Card>
    </Space>
  )
}
