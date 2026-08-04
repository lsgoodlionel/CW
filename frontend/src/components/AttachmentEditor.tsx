import { Upload, Button, Select, Space, Tag } from 'antd'
import { UploadOutlined, DeleteOutlined, PaperClipOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { Attachment, ATTACH_KIND_LABEL } from '../api'

export interface StagedFile {
  uid: string
  file: File
  kind: string
}

interface Props {
  existing: Attachment[]
  staged: StagedFile[]
  onStagedChange: (s: StagedFile[]) => void
  onDeleteExisting?: (id: number) => void
  defaultKind?: string
}

/** 单据附件编辑器:支持"新建时暂存、保存后上传"以及已存在附件的预览/删除。 */
export default function AttachmentEditor({
  existing, staged, onStagedChange, onDeleteExisting, defaultKind = 'invoice',
}: Props) {
  const [kind, setKind] = useState(defaultKind)
  const kindOpts = Object.entries(ATTACH_KIND_LABEL).map(([value, label]) => ({ value, label }))

  const stageFile = (file: File) => {
    onStagedChange([...staged, { uid: `${Date.now()}-${file.name}`, file, kind }])
    return false // 阻止 antd 自动上传,改为保存时统一上传
  }
  const removeStaged = (uid: string) => onStagedChange(staged.filter((s) => s.uid !== uid))

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        <span>附件类型</span>
        <Select value={kind} style={{ width: 130 }} onChange={setKind} options={kindOpts} />
        <Upload showUploadList={false} beforeUpload={stageFile} multiple>
          <Button icon={<UploadOutlined />}>选择附件</Button>
        </Upload>
        <span style={{ color: '#999' }}>(保存单据时一并上传)</span>
      </Space>

      {(existing.length > 0 || staged.length > 0) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {existing.map((a) => (
            <Tag key={`e${a.id}`} icon={<PaperClipOutlined />} color="blue"
              closable={Boolean(onDeleteExisting)}
              onClose={(e) => { e.preventDefault(); onDeleteExisting?.(a.id) }}>
              <a href={`/api/attachments/${a.id}/preview`} target="_blank" rel="noreferrer">
                {ATTACH_KIND_LABEL[a.kind] || a.kind}·{a.original_name}
              </a>
            </Tag>
          ))}
          {staged.map((s) => (
            <Tag key={s.uid} color="orange">
              待上传·{ATTACH_KIND_LABEL[s.kind] || s.kind}·{s.file.name}
              <DeleteOutlined style={{ marginLeft: 6, cursor: 'pointer' }} onClick={() => removeStaged(s.uid)} />
            </Tag>
          ))}
        </div>
      )}
      {existing.length === 0 && staged.length === 0 && (
        <span style={{ color: '#bbb' }}>暂无附件</span>
      )}
    </div>
  )
}

/** 保存单据后,把暂存文件逐个上传到 `${basePath}/${id}/attachments`。 */
export async function uploadStaged(
  http: { post: (url: string, data: FormData) => Promise<unknown> },
  basePath: string, id: number, staged: StagedFile[],
): Promise<void> {
  for (const s of staged) {
    const fd = new FormData()
    fd.append('file', s.file)
    fd.append('kind', s.kind)
    await http.post(`${basePath}/${id}/attachments`, fd)
  }
}
