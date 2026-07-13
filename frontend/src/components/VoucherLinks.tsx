import { useState } from 'react'
import { Table, Tag, Button, Space, Select, Input, Popconfirm, message } from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { http, LinkedVoucher, VoucherListItem, RELATION_LABEL } from '../api'

interface VoucherLinksProps {
  voucherId: number
  links: LinkedVoucher[]
  onChange: (links: LinkedVoucher[]) => void
}

const RELATION_COLOR: Record<string, string> = {
  advance: 'blue', on_account: 'orange', write_off: 'green',
  receivable: 'purple', other: 'default',
}

export default function VoucherLinks({ voucherId, links, onChange }: VoucherLinksProps) {
  const navigate = useNavigate()
  const [relationType, setRelationType] = useState('advance')
  const [note, setNote] = useState('')
  const [targetId, setTargetId] = useState<number | undefined>()
  const [options, setOptions] = useState<VoucherListItem[]>([])
  const [adding, setAdding] = useState(false)

  const searchVouchers = (kw: string) => {
    http.get('/vouchers', { params: { keyword: kw, page_size: 20 } })
      .then((r) => setOptions(r.data.items.filter((v: VoucherListItem) => v.id !== voucherId)))
  }

  const addLink = async () => {
    if (!targetId) return message.warning('请选择要关联的凭证')
    setAdding(true)
    try {
      const r = await http.post(`/vouchers/${voucherId}/links`, {
        target_id: targetId, relation_type: relationType, note,
      })
      onChange(r.data.links)
      setTargetId(undefined); setNote('')
      message.success('已添加关联')
    } finally {
      setAdding(false)
    }
  }

  const removeLink = async (linkId: number) => {
    await http.delete(`/vouchers/links/${linkId}`)
    onChange(links.filter((l) => l.link_id !== linkId))
    message.success('已删除关联')
  }

  return (
    <>
      <Space wrap style={{ marginBottom: 12 }}>
        <Select value={relationType} style={{ width: 110 }} onChange={setRelationType}
          options={Object.entries(RELATION_LABEL).map(([value, label]) => ({ value, label }))} />
        <Select showSearch placeholder="搜索凭证号/摘要关联" style={{ width: 280 }}
          value={targetId} filterOption={false} onSearch={searchVouchers} onChange={setTargetId}
          options={options.map((v) => ({
            value: v.id, label: `${v.voucher_no} ${v.voucher_date} ${v.note}`,
          }))} />
        <Input placeholder="备注(可选)" style={{ width: 160 }} value={note}
          onChange={(e) => setNote(e.target.value)} />
        <Button type="primary" icon={<PlusOutlined />} loading={adding} onClick={addLink}>
          添加关联
        </Button>
      </Space>
      <Table rowKey="link_id" size="small" pagination={false} dataSource={links}
        locale={{ emptyText: '暂无关联凭证' }}
        columns={[
          {
            title: '关系', dataIndex: 'relation_type', width: 90,
            render: (t: string) => <Tag color={RELATION_COLOR[t]}>{RELATION_LABEL[t] || t}</Tag>,
          },
          {
            title: '方向', dataIndex: 'direction', width: 70,
            render: (d: string) => (d === 'out' ? '→ 指向' : '← 被指向'),
          },
          {
            title: '凭证号', dataIndex: 'voucher_no', width: 130,
            render: (v: string, r: LinkedVoucher) => <a onClick={() => navigate(`/vouchers/${r.voucher_id}`)}>{v}</a>,
          },
          { title: '日期', dataIndex: 'voucher_date', width: 110 },
          { title: '摘要', dataIndex: 'voucher_note', ellipsis: true },
          {
            title: '金额', dataIndex: 'total_debit', width: 110, align: 'right',
            render: (v: number) => v.toLocaleString('zh-CN', { minimumFractionDigits: 2 }),
          },
          { title: '备注', dataIndex: 'note', width: 120, render: (v: string) => v || '-' },
          {
            title: '', width: 50,
            render: (_: unknown, r: LinkedVoucher) => (
              <Popconfirm title="删除该关联?" onConfirm={() => removeLink(r.link_id)}>
                <Button type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            ),
          },
        ]} />
    </>
  )
}
