/**
 * 数据契约的对外出口。
 *
 * 形状全部来自 `models.generated.ts`(由后端 OpenAPI 自动生成),这里只做两件事:
 *   1. 把后端 schema 名(AccountOut / InstanceOut …)映射成两端惯用的短名;
 *   2. 定义少量「表单编辑态」类型 —— 新建时还没有 id、金额在输入过程中是 number,
 *      这属于前端状态,不是接口契约,所以手写,但从生成类型派生以便跟随后端变化。
 *
 * 后端改了字段 → 跑 `node scripts/gen-contract.mjs` → 这里通常一行都不用动。
 * 后端新增了模型 → 在下面加一行别名即可。
 */
import type {
  EntryOut,
  ExpenseItemOut,
  PositionOut,
  StepOut,
} from './models.generated'

export * from './models.generated'

/* ---------------- 名称映射 ---------------- */

export type { AuthUserOut as AuthUser } from './models.generated'
export type { AccountOut as Account } from './models.generated'
export type { SubAccountOut as SubAccount } from './models.generated'
export type { AttachmentOut as Attachment } from './models.generated'
export type { CustomerOut as Customer } from './models.generated'
export type { CustomerVoucherItemOut as CustomerVoucherItem } from './models.generated'
export type { CompanyOut as Company } from './models.generated'
export type { OrgUnitOut as OrgUnit } from './models.generated'
export type { EmployeeOut as Employee } from './models.generated'
export type { WorkflowDefOut as WorkflowDef } from './models.generated'
export type { InstanceOut as WorkflowInstance } from './models.generated'
export type { InstanceStepOut as InstanceStep } from './models.generated'
export type { TaskOut as WorkflowTask } from './models.generated'
export type { ApproverCheckOut as ApproverCheck } from './models.generated'
export type { ApproverProblemOut as ApproverCheckProblem } from './models.generated'
export type { ActiveWorkflowOut as ActiveWorkflow } from './models.generated'
export type { ExpenseClaimOut as ExpenseClaim } from './models.generated'
export type { ExpenseApplicationOut as ExpenseApplication } from './models.generated'
export type { DashboardOut as DashboardData } from './models.generated'
export type { OfficialReportsOut as OfficialReports } from './models.generated'
export type { StatementOut as Statement } from './models.generated'
export type { StatementRowOut as StatementRow } from './models.generated'
export type { BalanceSheetOut as BalanceSheet } from './models.generated'
export type { BalanceSheetRowOut as BalanceSheetRow } from './models.generated'
export type { TrialBalanceOut as TrialBalance } from './models.generated'
export type { TrialBalanceRowOut as TrialBalanceRow } from './models.generated'
export type { LedgerOut as Ledger } from './models.generated'
export type { LedgerGroupOut as LedgerGroup } from './models.generated'
export type { LedgerRowOut as LedgerRow } from './models.generated'
export type { LogItemOut as LogItem } from './models.generated'
export type { LogPageOut as LogPage } from './models.generated'
export type { RoleOut as Role } from './models.generated'
export type { UserOut as UserRow } from './models.generated'
export type { PermissionActionOut as PermissionAction } from './models.generated'
export type { PermissionModuleOut as PermissionModule } from './models.generated'
export type { AuthPresetOut as AuthPreset } from './models.generated'

/* ---------------- 业务枚举 ---------------- */

/**
 * 科目类别。后端存成普通字符串(见 seed_accounts.py),OpenAPI 里只是 string,
 * 这里补一个字面量联合方便前端穷举;取值必须与 CATEGORY_LABEL 一致。
 */
export type Category = 'asset' | 'liability' | 'equity' | 'cost' | 'profit'

/* ---------------- 表单编辑态 ---------------- */

/**
 * 金额在编辑态可能是两种形态:从接口读回来是字符串(后端 Decimal 序列化为
 * "500.00"),用户在输入框里改过之后是数字。渲染与计算前用 `toAmount()` 归一。
 */
export type AmountInput = number | string

/**
 * 编辑态里「后端回填的展示字段」一律放宽为可选 —— 新建时前端造不出这些值
 * (科目名、部门名、审批人名都是后端按 id 关联出来的)。
 */
type Editable<T, Optional extends keyof T> = Omit<T, Optional> & Partial<Pick<T, Optional>>

/** 凭证分录编辑态:新建行没有 id / line_no,科目编码与名称由后端回填 */
export type Entry = Editable<
  Omit<EntryOut, 'debit' | 'credit'>,
  'id' | 'line_no' | 'account_code' | 'account_name' | 'sub_account_id'
> & {
  debit: AmountInput
  credit: AmountInput
}

/** 费用明细编辑态(费用申请与报销共用) */
export type ExpenseItem = Editable<Omit<ExpenseItemOut, 'amount'>, 'id' | 'account_name'> & {
  amount: AmountInput
}

/** 审批步骤编辑态:新建步骤没有 id / step_no,审批人名由后端解析 */
export type WorkflowStep = Editable<StepOut, 'id' | 'step_no' | 'approver_name'>

/** 员工任职编辑态:新增任职没有 id,部门名由后端回填 */
export type Position = Editable<PositionOut, 'id' | 'org_unit_name'>
