"""SQLAlchemy ORM 模型。"""
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    String, Integer, Numeric, Date, DateTime, ForeignKey, Boolean, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# 金额统一精度:18 位整数 + 2 位小数
MONEY = Numeric(18, 2)


class CompanyInfo(Base):
    """企业基本信息(单例,id 恒为 1)。"""
    __tablename__ = "company_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    # 常规工商/税务信息
    tax_number: Mapped[str] = mapped_column(String(40), default="")     # 纳税人识别号
    reg_address: Mapped[str] = mapped_column(String(200), default="")   # 注册地址
    phone: Mapped[str] = mapped_column(String(50), default="")          # 电话
    bank_name: Mapped[str] = mapped_column(String(120), default="")     # 开户银行
    bank_account: Mapped[str] = mapped_column(String(60), default="")   # 银行账号
    establish_date: Mapped[str] = mapped_column(String(20), default="") # 成立日期
    industry: Mapped[str] = mapped_column(String(60), default="")       # 所属行业
    currency: Mapped[str] = mapped_column(String(20), default="人民币")  # 记账本位币
    accounting_standard: Mapped[str] = mapped_column(
        String(40), default="小企业会计准则")                            # 执行会计准则
    start_period: Mapped[str] = mapped_column(String(20), default="")   # 启用期间
    # 人员
    legal_person: Mapped[str] = mapped_column(String(100), default="")
    accountant: Mapped[str] = mapped_column(String(100), default="")
    auditor: Mapped[str] = mapped_column(String(100), default="")
    bookkeeper: Mapped[str] = mapped_column(String(100), default="")
    recorder: Mapped[str] = mapped_column(String(100), default="")


class Account(Base):
    """会计科目。"""
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    # asset 资产 / liability 负债 / equity 权益 / cost 成本 / profit 损益
    category: Mapped[str] = mapped_column(String(20), index=True)
    # debit 借 / credit 贷:科目的余额方向
    direction: Mapped[str] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    sub_accounts: Mapped[list["SubAccount"]] = relationship(
        back_populates="account", cascade="all, delete-orphan",
        order_by="SubAccount.code",
    )


class SubAccount(Base):
    """二级明细科目(隶属于一级会计科目)。编码 = 一级编码(4位) + 顺序(2位)。"""
    __tablename__ = "sub_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_no: Mapped[int] = mapped_column(Integer, default=0)

    account: Mapped["Account"] = relationship(back_populates="sub_accounts")


class Customer(Base):
    """往来单位:企业客户/个人客户/供应商/往来单位(银行、平台、租赁对象等)。"""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # enterprise 企业客户 / individual 个人客户 / supplier 供应商 / partner 往来单位
    party_type: Mapped[str] = mapped_column(String(20), default="enterprise", index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)          # 名称
    short_name: Mapped[str] = mapped_column(String(60), default="")     # 简称
    tax_number: Mapped[str] = mapped_column(String(40), default="", index=True)  # 税号
    address: Mapped[str] = mapped_column(String(200), default="")       # 开票地址
    phone: Mapped[str] = mapped_column(String(50), default="")          # 开票电话
    bank_name: Mapped[str] = mapped_column(String(120), default="")     # 开户行
    bank_account: Mapped[str] = mapped_column(String(60), default="")   # 银行账号
    contact_person: Mapped[str] = mapped_column(String(50), default="") # 联系人
    contact_phone: Mapped[str] = mapped_column(String(50), default="")  # 联系电话
    email: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Voucher(Base):
    """记账凭证。"""
    __tablename__ = "vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_no: Mapped[str] = mapped_column(String(40), index=True)
    voucher_date: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    total_debit: Mapped[Decimal] = mapped_column(MONEY, default=0)
    total_credit: Mapped[Decimal] = mapped_column(MONEY, default=0)
    status: Mapped[str] = mapped_column(String(20), default="posted")  # draft / posted
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped["Customer | None"] = relationship()
    entries: Mapped[list["VoucherEntry"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan",
        order_by="VoucherEntry.line_no",
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="voucher", cascade="all, delete-orphan",
    )


class VoucherEntry(Base):
    """凭证分录(明细行)。一行只填借方或贷方。"""
    __tablename__ = "voucher_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE"), index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, default=1)
    summary: Mapped[str] = mapped_column(String(200), default="")  # 摘要
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    sub_account: Mapped[str] = mapped_column(String(100), default="")  # 明细科目名称(与二级科目同步)
    sub_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("sub_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    debit: Mapped[Decimal] = mapped_column(MONEY, default=0)
    credit: Mapped[Decimal] = mapped_column(MONEY, default=0)

    voucher: Mapped["Voucher"] = relationship(back_populates="entries")
    account: Mapped["Account"] = relationship()


class Attachment(Base):
    """附件:发票/回单等原始单据。"""
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20), default="other")  # invoice/receipt/other
    original_name: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    voucher: Mapped["Voucher"] = relationship(back_populates="attachments")


class VoucherLink(Base):
    """凭证关联:预收款/挂账/核销/应收款等人工关联,用于展示相关凭证。"""
    __tablename__ = "voucher_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("vouchers.id", ondelete="CASCADE"), index=True
    )
    # advance(预收款) / on_account(挂账) / write_off(核销) / receivable(应收款) / other
    relation_type: Mapped[str] = mapped_column(String(20), default="other")
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OperationLog(Base):
    """操作日志:记录全系统数据变更与导入导出/下载行为。"""
    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
    # voucher/account/attachment/company/report/ledger/data/other
    action_type: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(100))       # 中文行为描述
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(300))
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[str] = mapped_column(String(50), default="")
    operator: Mapped[str] = mapped_column(String(50), default="")  # 操作人(登录用户名)
    detail: Mapped[str] = mapped_column(Text, default="")   # 变更详情(提交内容/差异 JSON)


class OrgUnit(Base):
    """组织架构单元(可自引用形成多级组织树)。"""
    __tablename__ = "org_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("org_units.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), index=True)
    sort_no: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(200), default="")


class Employee(Base):
    """员工档案(个人信息);部门与角色见 employee_positions(支持一人多岗兼职)。"""
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_no: Mapped[str] = mapped_column(String(40), default="", index=True)  # 工号
    name: Mapped[str] = mapped_column(String(60), index=True)
    # 以下三列为历史遗留(旧版单部门),已迁移至 employee_positions,保留以兼容
    org_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("org_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role_type: Mapped[str] = mapped_column(String(20), default="staff")
    position: Mapped[str] = mapped_column(String(60), default="")
    gender: Mapped[str] = mapped_column(String(10), default="")     # 性别
    phone: Mapped[str] = mapped_column(String(30), default="")
    id_number: Mapped[str] = mapped_column(String(40), default="")  # 身份证号
    email: Mapped[str] = mapped_column(String(120), default="")
    hire_date: Mapped[str] = mapped_column(String(20), default="")  # 入职日期
    equity_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 4), default=0)  # 持股比例%
    status: Mapped[str] = mapped_column(String(20), default="active")  # active 在职 / left 离职
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    positions: Mapped[list["EmployeePosition"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan",
        order_by="EmployeePosition.sort_no",
    )


class User(Base):
    """系统用户(登录账号)。可关联员工;超管拥有全部权限。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(60), default="")
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    roles: Mapped[list["Role"]] = relationship(secondary="user_roles", lazy="selectin")


class Role(Base):
    """角色(权限集合),可授予多个用户。"""
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    permissions: Mapped[list["RolePermission"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin",
    )


class RolePermission(Base):
    """角色权限点:perm 形如 'voucher:create'。"""
    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    perm: Mapped[str] = mapped_column(String(50))


class AuthPreset(Base):
    """授权预设:某部门 + 某员工角色 → 授予某系统角色。用于按部门/职位预设权限。"""
    __tablename__ = "auth_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("org_units.id", ondelete="CASCADE"), nullable=True, index=True
    )  # 空 = 任意部门
    emp_role_type: Mapped[str] = mapped_column(String(20), default="")  # 空 = 任意职位角色
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )
    note: Mapped[str] = mapped_column(String(200), default="")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class ExpenseClaim(Base):
    """费用报销申请单(复用审批流程,通过后可生成记账凭证)。"""
    __tablename__ = "expense_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_no: Mapped[str] = mapped_column(String(40), index=True)
    applicant_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    org_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("org_units.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(200), default="")   # 报销事由
    total_amount: Mapped[Decimal] = mapped_column(MONEY, default=0)
    # draft 草稿 / pending 审批中 / approved 已通过 / rejected 已驳回 / paid 已生成凭证
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    workflow_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="SET NULL"), nullable=True
    )
    voucher_id: Mapped[int | None] = mapped_column(
        ForeignKey("vouchers.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    items: Mapped[list["ExpenseItem"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="ExpenseItem.id",
    )


class ExpenseItem(Base):
    """报销明细行。account_id/sub_account 用于生成凭证的费用科目。"""
    __tablename__ = "expense_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        ForeignKey("expense_claims.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(60), default="")   # 费用类别
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    sub_account: Mapped[str] = mapped_column(String(100), default="")  # 明细科目
    amount: Mapped[Decimal] = mapped_column(MONEY, default=0)
    note: Mapped[str] = mapped_column(String(200), default="")

    claim: Mapped["ExpenseClaim"] = relationship(back_populates="items")


class WorkflowDefinition(Base):
    """审批流程定义(可复用于报销等业务单据)。"""
    __tablename__ = "workflow_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    biz_type: Mapped[str] = mapped_column(String(30), default="general", index=True)  # expense/general...
    note: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="definition", cascade="all, delete-orphan",
        order_by="WorkflowStep.step_no",
    )


class WorkflowStep(Base):
    """流程步骤:第 N 步由谁审批。"""
    __tablename__ = "workflow_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(60), default="")
    # employee 指定员工 / role 按角色 / department_head 部门负责人 / any 任意管理层
    approver_type: Mapped[str] = mapped_column(String(20), default="employee")
    approver_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    approver_role: Mapped[str] = mapped_column(String(20), default="")  # role 时用

    definition: Mapped["WorkflowDefinition"] = relationship(back_populates="steps")


class WorkflowInstance(Base):
    """流程实例:一张业务单据走一次审批。"""
    __tablename__ = "workflow_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("workflow_definitions.id"))
    biz_type: Mapped[str] = mapped_column(String(30), default="general", index=True)
    biz_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    applicant_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)  # pending/approved/rejected/cancelled
    current_step_no: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tasks: Mapped[list["WorkflowTask"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan",
        order_by="WorkflowTask.id",
    )


class WorkflowTask(Base):
    """审批任务/轨迹:某实例某步骤指派给某审批人的处理记录。"""
    __tablename__ = "workflow_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, default=1)
    step_name: Mapped[str] = mapped_column(String(60), default="")
    approver_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    result: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/rejected
    comment: Mapped[str] = mapped_column(String(300), default="")
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    instance: Mapped["WorkflowInstance"] = relationship(back_populates="tasks")


class EmployeePosition(Base):
    """员工任职:一名员工在某部门担任某角色/职位(支持跨多部门兼职)。"""
    __tablename__ = "employee_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    org_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("org_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # shareholder 股东 / management 管理层 / staff 普通员工 / other 其他
    role_type: Mapped[str] = mapped_column(String(20), default="staff", index=True)
    position: Mapped[str] = mapped_column(String(60), default="")   # 职位
    sort_no: Mapped[int] = mapped_column(Integer, default=0)

    employee: Mapped["Employee"] = relationship(back_populates="positions")
    org_unit: Mapped["OrgUnit | None"] = relationship()
