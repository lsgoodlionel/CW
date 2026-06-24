import { Modal, Empty, Button } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { Attachment } from '../api'

interface Props {
  attachment: Attachment | null
  open: boolean
  onClose: () => void
}

const isImage = (mime: string) => mime.startsWith('image/')
const isPdf = (mime: string) => mime === 'application/pdf'
const isText = (mime: string) => mime.startsWith('text/')

export default function AttachmentPreview({ attachment, open, onClose }: Props) {
  if (!attachment) return null
  const src = `/api/attachments/${attachment.id}/preview`
  const downloadUrl = `/api/attachments/${attachment.id}/download`
  const mime = attachment.mime_type || ''

  const renderBody = () => {
    if (isImage(mime)) {
      return (
        <img src={src} alt={attachment.original_name}
          style={{ maxWidth: '100%', maxHeight: '70vh', display: 'block', margin: '0 auto' }} />
      )
    }
    if (isPdf(mime) || isText(mime)) {
      return (
        <iframe src={src} title={attachment.original_name}
          style={{ width: '100%', height: '70vh', border: 'none' }} />
      )
    }
    return (
      <Empty description={`该类型(${mime || '未知'})暂不支持在线预览,请下载查看`}>
        <Button type="primary" icon={<DownloadOutlined />} href={downloadUrl} target="_blank">
          下载文件
        </Button>
      </Empty>
    )
  }

  return (
    <Modal
      open={open}
      title={attachment.original_name}
      onCancel={onClose}
      width={900}
      footer={[
        <Button key="download" icon={<DownloadOutlined />} href={downloadUrl} target="_blank">
          下载
        </Button>,
        <Button key="close" type="primary" onClick={onClose}>关闭</Button>,
      ]}
    >
      {renderBody()}
    </Modal>
  )
}
