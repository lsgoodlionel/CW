import { useEffect, useState, useMemo } from 'react'
import { Card, Select, Segmented, Button, Space, Table, Tag, Empty, Alert, DatePicker, Modal, Tree, Input, message, Radio, Typography } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { http, Account, withToken, Ledger, LedgerRow, LEDGER_TYPE_LABEL, formatAmount } from '../api'

type ReportType = 'month' | 'quarter' | 'year'
type ArchiveItem = { path: string; type: string; voucher_no: string; source: string; description: string;
  classification_reason?: string }
type ArchivePreview = { period: string; voucher_count: number; attachment_count: number; items: ArchiveItem[] }

const fmt = (v: string | number | null) =>
  typeof v === 'number' ? formatAmount(v) : (v ?? '')

export default function Ledgers() {
  const now = dayjs()
  const [ledgerType, setLedgerType] = useState('general')
  const [reportType, setReportType] = useState<ReportType>('month')
  const [year, setYear] = useState(now.year())
  const [month, setMonth] = useState(now.month() + 1)
  const [quarter, setQuarter] = useState(Math.floor(now.month() / 3) + 1)
  const [accountCode, setAccountCode] = useState<string | undefined>()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [data, setData] = useState<Ledger | null>(null)
  const [loading, setLoading] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [archiveMode, setArchiveMode] = useState<'subject' | 'date'>('subject')
  const [archiveLedgerType, setArchiveLedgerType] = useState<string>('all')
  const [folderNames, setFolderNames] = useState<Record<string, string>>(() => {
    try { return JSON.parse(localStorage.getItem('ledger_archive_folders') || '{}') } catch { return {} }
  })
  const [archivePreview, setArchivePreview] = useState<ArchivePreview | null>(null)
  const [archiveBusy, setArchiveBusy] = useState(false)
  const [fileBusy, setFileBusy] = useState<string | null>(null)
  const [filePreview, setFilePreview] = useState<{ path: string; url: string; mediaType: string } | null>(null)
  const [folderCode, setFolderCode] = useState<string>()

  useEffect(() => {
    http.get<Account[]>('/accounts').then((r) => setAccounts(r.data))
  }, [])

  const params = useMemo(() => {
    const p: Record<string, string | number> = { ledger_type: ledgerType, report_type: reportType, year }
    if (reportType === 'month') p.month = month
    if (reportType === 'quarter') p.quarter = quarter
    if (accountCode) p.account_code = accountCode
    return p
  }, [ledgerType, reportType, year, month, quarter, accountCode])

  useEffect(() => {
    setLoading(true)
    http.get<Ledger>('/ledgers', { params })
      .then((r) => setData(r.data))
      .finally(() => setLoading(false))
  }, [params])

  const exportExcel = (all: boolean) => {
    const p = { ...params, ledger_type: all ? 'all' : ledgerType }
    const qs = new URLSearchParams(p as Record<string, string>).toString()
    window.open(withToken(`/api/ledgers/export-excel?${qs}`), '_blank')
  }
  const archivePayload = () => ({ ...params, ledger_type: archiveLedgerType,
    mode: archiveMode, folder_names: folderNames })
  const previewArchive = async () => {
    setArchiveBusy(true)
    try {
      const r = await http.post<ArchivePreview>('/ledgers/archive-preview', archivePayload())
      setArchivePreview(r.data)
    } catch { message.error('归档预览失败') }
    finally { setArchiveBusy(false) }
  }
  const exportArchive = async () => {
    setArchiveBusy(true)
    try {
      const r = await http.post('/ledgers/archive-export', archivePayload(), { responseType: 'blob' })
      const url = URL.createObjectURL(r.data as Blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `账簿凭证附件-${year}年-${archiveMode === 'subject' ? '科目' : '日期'}.zip`
      document.body.appendChild(link)
      link.click(); link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 30000)
      message.success('已生成归档包，可继续查看目录清单')
    } catch { message.error('归档包生成失败') }
    finally { setArchiveBusy(false) }
  }
  const closeFilePreview = () => {
    if (filePreview) URL.revokeObjectURL(filePreview.url)
    setFilePreview(null)
  }
  const previewFile = async (item: ArchiveItem) => {
    setFileBusy(item.path)
    try {
      const r = await http.post<Blob>('/ledgers/archive-file-preview',
        { ...archivePayload(), path: item.path }, { responseType: 'blob' })
      closeFilePreview()
      setFilePreview({ path: item.path, url: URL.createObjectURL(r.data),
        mediaType: String(r.headers['content-type'] || r.data.type || '') })
    } catch { message.error('文件内容预览失败，请重新预览目录后重试') }
    finally { setFileBusy(null) }
  }
  const archiveTree = useMemo(() => {
    type Node = { key: string; title: string; children?: Node[] }
    const roots: Node[] = []
    for (const item of archivePreview?.items || []) {
      let nodes = roots, path = ''
      const parts = item.path.split('/')
      parts.forEach((part, index) => {
        path += `${index ? '/' : ''}${part}`
        let node = nodes.find((n) => n.key === path)
        if (!node) { node = { key: path, title: part, children: [] }; nodes.push(node) }
        nodes = node.children || []
      })
    }
    return roots
  }, [archivePreview])

  return (
    <Card>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select value={ledgerType} style={{ width: 190 }} onChange={setLedgerType}
          options={Object.entries(LEDGER_TYPE_LABEL).map(([value, label]) => ({ value, label }))} />
        <Segmented value={reportType} onChange={(v) => setReportType(v as ReportType)}
          options={[{ label: '月', value: 'month' }, { label: '季', value: 'quarter' }, { label: '年', value: 'year' }]} />
        <DatePicker picker="year" value={dayjs().year(year)} allowClear={false}
          onChange={(v) => v && setYear(v.year())} />
        {reportType === 'month' && (
          <Select value={month} style={{ width: 80 }} onChange={setMonth}
            options={Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: `${i + 1}月` }))} />
        )}
        {reportType === 'quarter' && (
          <Select value={quarter} style={{ width: 100 }} onChange={setQuarter}
            options={[1, 2, 3, 4].map((q) => ({ value: q, label: `第${q}季度` }))} />
        )}
        <Select allowClear placeholder="全部科目" style={{ width: 200 }} value={accountCode}
          showSearch optionFilterProp="label" onChange={setAccountCode}
          options={accounts.map((a) => ({ value: a.code, label: `${a.code} ${a.name}` }))} />
        <Button type="primary" icon={<DownloadOutlined />} onClick={() => exportExcel(false)}>
          导出本账簿
        </Button>
        <Button icon={<DownloadOutlined />} onClick={() => exportExcel(true)}>
          导出全套账簿
        </Button>
        <Button icon={<DownloadOutlined />} onClick={() => { setArchiveOpen(true); setArchivePreview(null) }}>
          导出账簿及凭证附件
        </Button>
      </Space>

      {data?.note && <Alert type="info" showIcon style={{ marginBottom: 12 }} message={data.note} />}
      {data && <Tag color="blue" style={{ marginBottom: 12 }}>{data.title} · {data.period_label}</Tag>}

      {data && data.groups.length === 0 && <Empty description="本期无账簿数据" />}

      {data?.groups.map((g, gi) => (
        <div key={gi} style={{ marginBottom: 24 }}>
          <div style={{ fontWeight: 600, marginBottom: 6, color: '#1f4e79' }}>
            科目:{g.title}
          </div>
          <Table
            rowKey={(_, i) => String(i)} loading={loading} size="small" pagination={false} bordered
            dataSource={g.rows}
            columns={(g.columns ?? data.columns).map((col, ci) => ({
              title: col,
              key: ci,
              align: ci >= 3 ? ('right' as const) : ci === 2 ? ('left' as const) : ('center' as const),
              render: (_: unknown, row: LedgerRow) => (
                <span style={row.is_summary ? { fontWeight: 600 } : undefined}>{fmt(row.cells[ci])}</span>
              ),
            }))}
            rowClassName={(row) => (row.is_summary ? 'ledger-sum-row' : '')}
          />
        </div>
      ))}
      <Modal title="账簿、凭证及附件归档" open={archiveOpen} width={920}
        onCancel={() => setArchiveOpen(false)} footer={[
          <Button key="preview" loading={archiveBusy} onClick={previewArchive}>预览目录与清单</Button>,
          <Button key="export" type="primary" loading={archiveBusy} disabled={!archivePreview}
            onClick={exportArchive}>一键打包下载</Button>,
        ]}>
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Typography.Text>按当前账簿种类、期间与科目筛选归档，仅包含已入账凭证。ZIP 内含 A4 账簿、凭证封面、凭证打印件及附件清单。</Typography.Text>
          <Radio.Group value={archiveMode} onChange={(e) => { setArchiveMode(e.target.value); setArchivePreview(null) }}
            options={[{ label: '发票按费用科目', value: 'subject' }, { label: '附件按凭证日期', value: 'date' }]} />
          <Select value={archiveLedgerType} style={{ width: 250 }} onChange={(v) => {
            setArchiveLedgerType(v); setArchivePreview(null)
          }} options={[{ value: 'all', label: '全套六类账簿' },
            ...Object.entries(LEDGER_TYPE_LABEL).map(([value, label]) => ({ value, label }))]} />
          {archiveMode === 'subject' && <Space wrap>
            <Select showSearch placeholder="选择科目设置目录" style={{ width: 240 }} value={folderCode}
              onChange={setFolderCode} optionFilterProp="label"
              options={accounts.map((a) => ({ value: a.code, label: `${a.code} ${a.name}` }))} />
            {folderCode && <Input style={{ width: 310 }} placeholder="目录路径，可用 / 分多级"
              value={folderNames[folderCode] || ''} onChange={(e) => {
                setFolderNames({ ...folderNames, [folderCode]: e.target.value }); setArchivePreview(null)
              }} />}
            <Button onClick={() => { localStorage.setItem('ledger_archive_folders', JSON.stringify(folderNames)); message.success('目录设置已保存') }}>
              保存目录设置
            </Button>
          </Space>}
          {archivePreview && <>
            <Typography.Text>{archivePreview.period} · 凭证 {archivePreview.voucher_count} 张 · 附件 {archivePreview.attachment_count} 件</Typography.Text>
            {archiveMode === 'subject' && archivePreview.items.some((item) => item.path.startsWith('附件/非费用业务/') || item.path.startsWith('附件/待核对/')) &&
              <Alert type="info" showIcon message="部分凭证没有费用或成本科目借方分录"
                description="税费、资产、往来等附件改按主要业务科目归入“非费用业务”；没有可用分录的凭证归入“待核对”。可在上方选择科目调整目录。" />}
            <div style={{ maxHeight: 340, overflow: 'auto', border: '1px solid #eee', padding: 10 }}>
              <Tree treeData={archiveTree} defaultExpandAll key={`${archiveMode}-${archivePreview.items.length}`}
                onSelect={(_, info) => {
                  const item = archivePreview.items.find((entry) => entry.path === String(info.node.key))
                  if (item) previewFile(item)
                }} />
            </div>
            <Table rowKey="path" size="small" pagination={{ pageSize: 8 }} dataSource={archivePreview.items}
              columns={[{ title: '凭证号', dataIndex: 'voucher_no', width: 160 },
                { title: '类型', dataIndex: 'type', width: 80 },
                { title: '来源', dataIndex: 'source', width: 90 },
                { title: '原始名称/摘要', dataIndex: 'description', ellipsis: true },
                { title: '归档依据', dataIndex: 'classification_reason', ellipsis: true },
                { title: '归档路径（点击预览）', dataIndex: 'path', ellipsis: true,
                  render: (path: string, item: ArchiveItem) => <Button type="link" size="small"
                    loading={fileBusy === path} onClick={() => previewFile(item)}>{path}</Button> }]} />
          </>}
        </Space>
      </Modal>
      <Modal title={`文件预览：${filePreview?.path || ''}`} open={Boolean(filePreview)} width={980}
        onCancel={closeFilePreview} footer={<Button onClick={closeFilePreview}>关闭</Button>} destroyOnClose>
        {filePreview?.mediaType.startsWith('image/')
          ? <img src={filePreview.url} alt={filePreview.path} style={{ maxWidth: '100%', maxHeight: '70vh' }} />
          : filePreview?.mediaType.startsWith('application/pdf')
            ? <iframe title={filePreview.path} src={filePreview.url} style={{ width: '100%', height: '70vh', border: 0 }} />
            : filePreview && <iframe title={filePreview.path} src={filePreview.url} sandbox=""
                style={{ width: '100%', height: '70vh', border: 0 }} />}
      </Modal>
    </Card>
  )
}
