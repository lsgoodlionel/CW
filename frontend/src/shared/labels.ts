/**
 * ⚠️ 本文件由 scripts/sync-shared.mjs 自动生成,请勿直接修改。
 * 源文件:shared/contract/labels.ts
 * 修改流程:改 shared/contract/labels.ts → 跑 node scripts/sync-shared.mjs
 */
/**
 * 业务枚举文案:与后端的取值一一对应,Web 与小程序共用。
 *
 * 只放「值 → 中文名」的映射。颜色 / 主题这类表现层映射留在各端自己的 UI 层,
 * 因为 antd 的色板与小程序自建组件的色板并不通用。
 */
/** 后端把科目类别存成普通字符串,这里用 Record<string, …> 以便直接按接口值索引 */
export const CATEGORY_LABEL: Record<string, string> = {
  asset: '资产类',
  liability: '负债类',
  equity: '权益类',
  cost: '成本类',
  profit: '损益类',
}

/** 往来单位类型 */
export const PARTY_LABEL: Record<string, string> = {
  enterprise: '企业客户',
  individual: '个人客户',
  supplier: '供应商',
  partner: '往来单位',
}

/** 员工任职角色 */
export const ROLE_LABEL: Record<string, string> = {
  shareholder: '股东',
  management: '管理层',
  staff: '普通员工',
  other: '其他',
}

/** 凭证关联关系 */
export const RELATION_LABEL: Record<string, string> = {
  advance: '预收款',
  on_account: '挂账',
  write_off: '核销',
  receivable: '应收款',
  reversal: '冲销',
  other: '其他',
}

/** 附件类型(与 backend/app/routers/attachments.py 的 ALLOWED_KINDS 对应) */
export const ATTACHMENT_KIND_LABEL: Record<string, string> = {
  invoice: '发票',
  receipt: '银行回单',
  contract: '合同',
  tax_payment: '完税证明',
  approval: '费用审批记录',
  other: '其他',
}

/**
 * 历史遗留的简称版附件文案(Web 版费用/审批页在用,"回单" 而非 "银行回单")。
 * 保留是为了不改动现有界面文案;新代码请用 ATTACHMENT_KIND_LABEL。
 */
export const ATTACH_KIND_LABEL: Record<string, string> = {
  invoice: '发票',
  receipt: '回单',
  contract: '合同',
  tax_payment: '完税证明',
  approval: '费用审批记录',
  other: '其他',
}

/** 审批步骤的审批人类型 */
export const APPROVER_TYPE_LABEL: Record<string, string> = {
  employee: '指定员工',
  role: '按角色',
  department_head: '部门负责人',
  any: '任一管理层',
}

/** 审批实例状态 */
export const WF_STATUS_LABEL: Record<string, string> = {
  pending: '审批中',
  approved: '已通过',
  rejected: '已驳回',
  cancelled: '已撤销',
}

/** 审批链路上单个步骤的状态 */
export const STEP_STATE_LABEL: Record<string, string> = {
  approved: '已通过',
  rejected: '已驳回',
  current: '审批中',
  upcoming: '待审批',
  skipped: '未进行',
}

/** 费用报销单状态 */
export const EXPENSE_STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  pending: '审批中',
  approved: '已通过',
  rejected: '已驳回',
  paid: '已生成凭证',
}

/** 费用申请单(事前审批)状态 */
export const APPLY_STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  pending: '审批中',
  approved: '已通过',
  rejected: '已驳回',
  closed: '已关联报销',
}

/** 费用申请类型 */
export const APPLY_TYPE_LABEL: Record<string, string> = {
  general: '一般申请',
  contract: '合同',
  routine: '常规费用',
}

/** 审批流程的业务类型 */
export const BIZ_TYPE_LABEL: Record<string, string> = {
  general: '通用',
  expense_apply: '费用申请',
  expense: '费用报销',
}

/** 六类会计账簿(与 backend/app/ledgers.py 的 ledger_type 对应) */
export const LEDGER_TYPE_LABEL: Record<string, string> = {
  general: '总分类账',
  detail_three: '金额三栏式明细账',
  cash_journal: '现金日记账',
  bank_journal: '银行存款日记账',
  detail_multi: '金额多栏式明细账',
  qty_amount: '数量金额式明细账',
}
