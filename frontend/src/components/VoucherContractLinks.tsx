import { useCallback, useEffect, useState } from 'react'
import { Table, Select, Button, Space, Popconfirm, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { http, formatYuan } from '../api'

interface ContractOption {
  id: number; contract_no: string; name: string
}
interface VoucherContractLink {
  link_id: number; contract_id: number; contract_no: string
  name: string; amount: number | string; note: string
}
interface Props {
  voucherId: number
}

// 凭证侧反向管理「关联合同」:选择合同建立关联,或解除已有关联。
export default function VoucherContractLinks({ voucherId }: Props) {
  const navigate = useNavigate()
  const [contracts, setContracts] = useState<ContractOption[]>([])
  const [links, setLinks] = useState<VoucherContractLink[]>([])
  const [selected, setSelected] = useState<number>()

  const loadLinks = useCallback(() => {
    http.get<VoucherContractLink[]>(`/contracts/by-voucher/${voucherId}`)
      .then((r) => setLinks(r.data))
  }, [voucherId])

  useEffect(() => {
    http.get<ContractOption[]>('/contracts').then((r) => setContracts(r.data))
    loadLinks()
  }, [loadLinks])

  const link = async () => {
    if (!selected) return
    await http.post(`/contracts/${selected}/link`, null, { params: { voucher_id: voucherId } })
    message.success('已关联合同'); setSelected(undefined); loadLinks()
  }
  const unlink = async (linkId: number) => {
    await http.delete(`/contracts/link/${linkId}`)
    loadLinks()
  }

  const linkedIds = new Set(links.map((l) => l.contract_id))

  return (
    <>
      <Space style={{ marginBottom: 8 }} wrap>
        <Select showSearch placeholder="选择要关联的合同" style={{ width: 340 }}
          optionFilterProp="label" value={selected} onChange={setSelected}
          options={contracts
            .filter((c) => !linkedIds.has(c.id))
            .map((c) => ({ value: c.id, label: `${c.contract_no} · ${c.name}` }))} />
        <Button onClick={link} disabled={!selected}>关联</Button>
      </Space>
      <Table rowKey="link_id" size="small" pagination={false} dataSource={links}
        locale={{ emptyText: '暂无关联合同' }}
        columns={[
          { title: '合同编号', dataIndex: 'contract_no', width: 160,
            render: (v: string, r: VoucherContractLink) => <a onClick={() => navigate(`/contracts?focus=${r.contract_id}`)}>{v}</a> },
          { title: '合同名称', dataIndex: 'name', ellipsis: true },
          { title: '合同金额', dataIndex: 'amount', width: 130, align: 'right' as const,
            render: (v: number | string) => formatYuan(v) },
          { title: '操作', width: 70,
            render: (_: unknown, r: VoucherContractLink) => (
              <Popconfirm title="解除该关联?" onConfirm={() => unlink(r.link_id)}>
                <a style={{ color: '#cf1322' }}>移除</a>
              </Popconfirm>
            ) },
        ]} />
    </>
  )
}
