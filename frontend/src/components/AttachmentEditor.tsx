import { Upload, Button, Select, Space, Tag, Progress, message } from 'antd'
import { UploadOutlined, PaperClipOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { http, Attachment, ATTACH_KIND_LABEL, fileUrl } from '../api'

interface InFlight { uid: string; name: string; percent: number; error?: boolean }

interface Props {
  /** 已存在的单据 id;新建时为 null,配合 ensureOwner 先建草稿再上传 */
  ownerId: number | null
  /** 附件端点前缀,如 '/expense-apply' 或 '/expense/claims' */
  basePath: string
  /** 新建场景:确保单据已落库并返回 id(校验/创建草稿);返回 null 表示暂不能上传 */
  ensureOwner?: () => Promise<number | null>
  existing: Attachment[]
  onChange: (atts: Attachment[]) => void
  canEdit?: boolean
  defaultKind?: string
}

/** 单据附件:选择后立即上传并显示进度,与保存动作解耦。 */
export default function AttachmentEditor({
  ownerId, basePath, ensureOwner, existing, onChange, canEdit = true, defaultKind = 'invoice',
}: Props) {
  const [kind, setKind] = useState(defaultKind)
  const [flights, setFlights] = useState<InFlight[]>([])
  // 审批记录为系统生成,不在手动上传类型中提供
  const kindOpts = Object.entries(ATTACH_KIND_LABEL)
    .filter(([value]) => value !== 'approval')
    .map(([value, label]) => ({ value, label }))

  const doUpload = async (file: File) => {
    let id = ownerId
    if (!id && ensureOwner) id = await ensureOwner()
    if (!id) { message.warning('请先填写单据必填项(如明细),再上传附件'); return }

    const uid = `${Date.now()}-${file.name}`
    setFlights((f) => [...f, { uid, name: file.name, percent: 0 }])
    const fd = new FormData()
    fd.append('file', file); fd.append('kind', kind)
    try {
      const r = await http.post<Attachment>(`${basePath}/${id}/attachments`, fd, {
        onUploadProgress: (e) => {
          const percent = e.total ? Math.round((e.loaded / e.total) * 100) : 0
          setFlights((fs) => fs.map((x) => (x.uid === uid ? { ...x, percent } : x)))
        },
      })
      setFlights((fs) => fs.filter((x) => x.uid !== uid))
      onChange([...existing, r.data])
      message.success('附件已上传')
    } catch {
      setFlights((fs) => fs.map((x) => (x.uid === uid ? { ...x, error: true } : x)))
      message.error('上传失败')
    }
  }

  const remove = (aid: number) =>
    http.delete(`/attachments/${aid}`).then(() => {
      onChange(existing.filter((a) => a.id !== aid)); message.success('附件已删除')
    })

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        <span>附件类型</span>
        <Select value={kind} style={{ width: 130 }} onChange={setKind} options={kindOpts} />
        <Upload showUploadList={false} multiple beforeUpload={(f) => { doUpload(f as File); return false }}>
          <Button icon={<UploadOutlined />}>上传附件</Button>
        </Upload>
        <span style={{ color: '#999' }}>选择后立即上传并显示进度</span>
      </Space>

      {flights.map((f) => (
        <div key={f.uid} style={{ maxWidth: 380, marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: '#666' }}>{f.name}</span>
          <Progress percent={f.percent} size="small"
            status={f.error ? 'exception' : f.percent < 100 ? 'active' : 'success'} />
        </div>
      ))}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 4 }}>
        {existing.map((a) => (
          <Tag key={a.id} icon={<PaperClipOutlined />} color="blue" closable={canEdit}
            onClose={(e) => { e.preventDefault(); remove(a.id) }}>
            <a href={fileUrl(a.id, 'preview')} target="_blank" rel="noreferrer">
              {ATTACH_KIND_LABEL[a.kind] || a.kind}·{a.original_name}
            </a>
          </Tag>
        ))}
        {existing.length === 0 && flights.length === 0 && <span style={{ color: '#bbb' }}>暂无附件</span>}
      </div>
    </div>
  )
}
