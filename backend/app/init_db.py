"""初始化:建表、轻量迁移、预置科目与企业信息单例。幂等。"""
from sqlalchemy import inspect, text, select

from .database import Base, engine, SessionLocal
from . import models
from .seed_accounts import ACCOUNTS
from .seed_subaccounts import SUB_ACCOUNTS
from . import subaccounts_svc


def init_db() -> None:
    from .tenant import set_current_tenant
    from .config import DEFAULT_TENANT_ID
    Base.metadata.create_all(bind=engine)
    _migrate(engine)
    db = SessionLocal()
    # 种子/回填全程置于默认租户上下文:新建对象经 before_flush 自动回填 tenant_id=1,
    # 存在性检查经 SELECT 过滤仅针对默认租户,行为与单机版一致。
    set_current_tenant(DEFAULT_TENANT_ID)
    try:
        _seed_tenant(db)                 # 默认租户须先于其它种子(存量数据归属租户1)
        _seed_accounts(db)
        _seed_company(db)
        db.commit()
        _seed_subaccounts(db)
        _backfill_entry_sub_account_id(db)
        _backfill_employee_positions(db)
        _seed_super_admin(db)            # 平台超管(全局用户,仅首次)
        _seed_roles(db)                  # 默认租户的系统角色
        _backfill_approval_perms(db)
        _seed_workflow(db)
        _seed_membership(db)             # 为已有用户补齐默认租户成员关系
        db.commit()
    finally:
        set_current_tenant(None)
        db.close()


def _seed_tenant(db) -> None:
    """确保默认租户(id=1)存在且为长期有效;私有化模式与存量数据均归属该租户。"""
    default = db.get(models.Tenant, 1)
    if default is None:
        company = db.get(models.CompanyInfo, 1)
        name = (company.name if company else None) or "默认企业"
        db.add(models.Tenant(
            id=1, name=name, code="default", is_active=True,
            plan="enterprise", status="active", expires_at="", max_users=0))
        db.commit()
    elif default.status != "active":
        # 存量默认租户经迁移得到 trial 默认值,回填为长期有效企业版(不受到期/配额限制)
        default.plan = "enterprise"
        default.status = "active"
        default.expires_at = ""
        default.max_users = 0
        db.commit()


def _seed_membership(db) -> None:
    """为所有用户补齐与默认租户的成员关系(超管为租户管理员)。幂等。"""
    existing = {uid for (uid,) in db.execute(
        select(models.TenantMembership.user_id).where(
            models.TenantMembership.tenant_id == 1)).all()}
    changed = False
    for u in db.scalars(select(models.User)).all():
        if u.id in existing:
            continue
        db.add(models.TenantMembership(
            user_id=u.id, tenant_id=1, is_tenant_admin=bool(u.is_super_admin)))
        changed = True
    if changed:
        db.commit()


# 已存在的表在版本迭代中新增的列:{表名: [(列名, 建列 DDL 片段), ...]}
_ADDED_COLUMNS = {
    "vouchers": [
        ("customer_id", "INTEGER"),
        ("workflow_instance_id", "INTEGER"),
    ],
    "voucher_entries": [
        ("sub_account_id", "INTEGER"),
    ],
    "attachments": [
        ("expense_application_id", "INTEGER"),
        ("expense_claim_id", "INTEGER"),
        ("contract_id", "INTEGER"),
        ("tax_filing_id", "INTEGER"),
    ],
    "expense_claims": [
        ("application_id", "INTEGER"),
        ("contract_id", "INTEGER"),
    ],
    "expense_applications": [
        ("contract_id", "INTEGER"),
    ],
    "employees": [
        ("leave_date", "VARCHAR(20) DEFAULT ''"),
    ],
    "customers": [
        ("party_type", "VARCHAR(20) DEFAULT 'enterprise'"),
    ],
    "contracts": [
        ("tax_rate", "NUMERIC(6,2) DEFAULT 0"),
        ("tax_amount", "NUMERIC(18,2) DEFAULT 0"),
        ("direction", "VARCHAR(10) DEFAULT 'income'"),
        ("workflow_instance_id", "INTEGER"),
    ],
    "tax_filings": [
        ("workflow_instance_id", "INTEGER"),
    ],
    "tenants": [
        ("plan", "VARCHAR(20) DEFAULT 'trial'"),
        ("status", "VARCHAR(20) DEFAULT 'trial'"),
        ("expires_at", "VARCHAR(20) DEFAULT ''"),
        ("max_users", "INTEGER DEFAULT 0"),
    ],
    "operation_logs": [
        ("detail", "TEXT DEFAULT ''"),
        ("operator", "VARCHAR(50) DEFAULT ''"),
    ],
    "company_info": [
        ("tax_number", "VARCHAR(40) DEFAULT ''"),
        ("reg_address", "VARCHAR(200) DEFAULT ''"),
        ("phone", "VARCHAR(50) DEFAULT ''"),
        ("bank_name", "VARCHAR(120) DEFAULT ''"),
        ("bank_account", "VARCHAR(60) DEFAULT ''"),
        ("establish_date", "VARCHAR(20) DEFAULT ''"),
        ("industry", "VARCHAR(60) DEFAULT ''"),
        ("currency", "VARCHAR(20) DEFAULT '人民币'"),
        ("accounting_standard", "VARCHAR(40) DEFAULT '小企业会计准则'"),
        ("start_period", "VARCHAR(20) DEFAULT ''"),
        ("taxpayer_kind", "VARCHAR(20) DEFAULT 'general'"),
        ("is_small_micro", "BOOLEAN DEFAULT FALSE"),
        ("small_micro_auto", "BOOLEAN DEFAULT TRUE"),
        ("restricted_industry", "BOOLEAN DEFAULT FALSE"),
        ("large_voucher_threshold", "NUMERIC(18,2) DEFAULT 0"),
    ],
}


def _migrate(bind) -> None:
    """为已存在的表补充新增列(create_all 不会 ALTER 现有表)。幂等。"""
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table, cols in _ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in cols:
            if name not in have:
                with bind.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    _migrate_tenant_id(bind, inspector, existing_tables)
    _relax_attachment_voucher(bind, inspector)
    _migrate_unique_constraints(bind, inspector)


def _migrate_tenant_id(bind, inspector, existing_tables) -> None:
    """为所有租户业务表补充 tenant_id 列并回填默认租户(存量数据归属租户 1)。幂等。"""
    from .tenant import TenantMixin
    from .config import DEFAULT_TENANT_ID
    # 取所有继承 TenantMixin 的映射表名
    tenant_tables = {
        m.local_table.name for m in Base.registry.mappers
        if issubclass(m.class_, TenantMixin)
    }
    for table in tenant_tables:
        if table not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table)}
        if "tenant_id" not in have:
            with bind.begin() as conn:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER "
                    f"NOT NULL DEFAULT {DEFAULT_TENANT_ID}"))


def _migrate_unique_constraints(bind, inspector) -> None:
    """将科目/二级科目/角色的全局唯一(code/name)迁移为按租户复合唯一。仅 Postgres,幂等。

    存量库用唯一索引 ix_*_code / ix_*_name 强制全局唯一,多租户下会阻止不同租户使用
    相同编码/角色名。此处删除旧单列唯一索引/约束,改建 (tenant_id, 列) 复合唯一约束。
    动态发现旧对象名,不依赖硬编码命名。
    """
    if bind.dialect.name != "postgresql":
        return
    # (表名, 目标单列, 新复合唯一约束名, 复合列 DDL)
    specs = [
        ("accounts", "code", "uq_account_tenant_code", "(tenant_id, code)"),
        ("sub_accounts", "code", "uq_subaccount_tenant_code", "(tenant_id, code)"),
        ("roles", "name", "uq_role_tenant_name", "(tenant_id, name)"),
    ]
    tables = set(inspector.get_table_names())
    for table, col, new_name, cols in specs:
        if table not in tables:
            continue
        ucs = inspector.get_unique_constraints(table)
        if any(uc.get("name") == new_name for uc in ucs):
            continue                      # 已迁移
        idxs = inspector.get_indexes(table)
        with bind.begin() as conn:
            # 删除旧单列唯一约束(如有)
            for uc in ucs:
                if uc.get("column_names") == [col]:
                    conn.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{uc["name"]}"'))
            # 删除旧单列唯一索引(存量库实际以此强制全局唯一)
            for ix in idxs:
                if ix.get("unique") and ix.get("column_names") == [col]:
                    conn.execute(text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
            # 新建按租户复合唯一约束
            conn.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {new_name} UNIQUE {cols}"))
            # 保留单列普通索引以加速按编码/名称查找
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS ix_{table}_{col} ON {table} ({col})'))


def _relax_attachment_voucher(bind, inspector) -> None:
    """附件支持多归属:voucher_id 由 NOT NULL 放宽为可空(仅 Postgres 需要 ALTER)。"""
    if "attachments" not in set(inspector.get_table_names()):
        return
    col = next((c for c in inspector.get_columns("attachments")
                if c["name"] == "voucher_id"), None)
    if col is None or col.get("nullable", True):
        return
    if bind.dialect.name != "postgresql":
        return
    with bind.begin() as conn:
        conn.execute(text("ALTER TABLE attachments ALTER COLUMN voucher_id DROP NOT NULL"))


def _seed_accounts(db) -> None:
    existing = {code for (code,) in db.query(models.Account.code).all()}
    for code, name, category, direction in ACCOUNTS:
        if code in existing:
            continue
        db.add(models.Account(
            code=code, name=name, category=category,
            direction=direction, is_active=True,
        ))


def _seed_company(db, name: str = "我的小微企业") -> None:
    """按当前租户上下文确保存在一条企业信息(经租户过滤判断)。tenant_id 由 before_flush 回填。"""
    if db.scalar(select(models.CompanyInfo).limit(1)) is None:
        db.add(models.CompanyInfo(name=name))


def _seed_super_admin(db) -> None:
    """首次创建平台超级管理员(全局用户,不隶属任何租户)。幂等。"""
    from . import auth_svc
    from .config import settings
    if db.scalar(select(models.User.id).limit(1)) is None:
        admin = models.User(
            username="admin", display_name="超级管理员",
            password_hash=auth_svc.hash_password(settings.admin_password),
            is_super_admin=True, is_active=True)
        db.add(admin)
        print(f"[init] 已创建超级管理员 admin(初始密码来自 ADMIN_PASSWORD,"
              f"默认 admin123),请登录后立即修改。", flush=True)
        db.commit()


def _seed_roles(db) -> None:
    """为当前租户上下文创建 3 个系统角色。幂等(按当前租户判空)。

    依赖调用方已通过 set_current_tenant 设置租户:新建角色/权限经 before_flush
    自动回填 tenant_id,存在性检查经 SELECT 过滤仅针对当前租户。供 init_db 与
    tenant_provision 复用,是「按租户初始化角色」的单一实现。
    """
    from . import auth_svc
    if db.scalar(select(models.Role.id).limit(1)) is not None:
        return
    readonly = models.Role(name="只读查看", note="所有模块仅查看", is_system=True)
    for m in auth_svc.MODULES:
        readonly.permissions.append(models.RolePermission(perm=f"{m}:view"))
    db.add(readonly)
    finance = models.Role(name="财务操作", note="凭证/科目/往来/合同/税务/报表/账簿/申请/报销 常规操作", is_system=True)
    for m in ("voucher", "account", "customer", "expense_apply", "expense", "contract", "tax"):
        for a in ("view", "create", "edit", "delete"):
            finance.permissions.append(models.RolePermission(perm=f"{m}:{a}"))
    # 财务操作默认可直录(免审批)合同/税务/凭证
    for m in ("voucher", "contract", "tax"):
        finance.permissions.append(models.RolePermission(perm=f"{m}:direct"))
    for m in ("report", "ledger", "company", "approval"):
        finance.permissions.append(models.RolePermission(perm=f"{m}:view"))
    db.add(finance)
    approver = models.Role(name="审批人", note="审批中心:申请/报销审批", is_system=True)
    for m in ("approval", "expense_apply", "expense"):
        approver.permissions.append(models.RolePermission(perm=f"{m}:view"))
        approver.permissions.append(models.RolePermission(perm=f"{m}:approve"))
    db.add(approver)
    db.commit()


def _seed_subaccounts(db) -> None:
    """预置二级科目(仅当该二级表为空时);按一级科目名称归属并生成编码。"""
    if db.scalar(select(models.SubAccount.id).limit(1)) is not None:
        return
    name_to_account = {a.name: a for a in db.scalars(select(models.Account)).all()}
    for parent_name, subs in SUB_ACCOUNTS.items():
        account = name_to_account.get(parent_name)
        if account is None:
            continue
        for idx, (sub_name, note) in enumerate(subs, start=1):
            db.add(models.SubAccount(
                account_id=account.id,
                code=f"{account.code}{idx:02d}",
                name=sub_name, note=note, sort_no=idx, is_active=True,
            ))
    db.commit()


def _backfill_approval_perms(db) -> None:
    """审批中心从流程设计拆分后,为已有角色补齐 approval:* 权限(依据其 workflow:* 权限)。幂等。

    映射:workflow:view→approval:view,workflow:approve→approval:approve,
    workflow:create/edit→approval:edit,workflow:delete→approval:delete。
    确保旧「审批人/只读」等角色在权限拆分后仍能进入审批中心并审批。
    """
    mapping = {"view": "view", "approve": "approve",
               "create": "edit", "edit": "edit", "delete": "delete"}
    roles = db.scalars(select(models.Role)).all()
    changed = False
    for role in roles:
        perms = {p.perm for p in role.permissions}
        for p in list(perms):
            if not p.startswith("workflow:"):
                continue
            action = p.split(":", 1)[1]
            target = f"approval:{mapping.get(action, action)}"
            if target not in perms:
                role.permissions.append(models.RolePermission(perm=target))
                perms.add(target)
                changed = True
    if changed:
        db.commit()


def _seed_workflow(db) -> None:
    """预置默认「费用申请」「费用报销」审批流程,使其可在审批流程设计页查看/修改。幂等。"""
    changed = False
    if db.scalar(select(models.WorkflowDefinition.id).where(
            models.WorkflowDefinition.biz_type == "expense").limit(1)) is None:
        d = models.WorkflowDefinition(
            name="费用报销审批流程", biz_type="expense",
            note="系统预置,可在审批流程页修改审批人与步骤", is_active=True)
        d.steps.append(models.WorkflowStep(
            step_no=1, name="部门负责人审批", approver_type="department_head"))
        d.steps.append(models.WorkflowStep(
            step_no=2, name="财务/管理层审批", approver_type="any"))
        db.add(d)
        changed = True
    if db.scalar(select(models.WorkflowDefinition.id).where(
            models.WorkflowDefinition.biz_type == "expense_apply").limit(1)) is None:
        d = models.WorkflowDefinition(
            name="费用申请审批流程", biz_type="expense_apply",
            note="系统预置事前审批,可在审批流程页修改审批人与步骤", is_active=True)
        d.steps.append(models.WorkflowStep(
            step_no=1, name="部门负责人审批", approver_type="department_head"))
        d.steps.append(models.WorkflowStep(
            step_no=2, name="分管/管理层审批", approver_type="any"))
        db.add(d)
        changed = True
    if changed:
        db.commit()


def _backfill_employee_positions(db) -> None:
    """把旧版单部门员工(org_unit_id/role_type/position)迁移为一条任职记录。"""
    employees = db.scalars(select(models.Employee)).all()
    if not employees:
        return
    existing = {pid for (pid,) in db.execute(
        select(models.EmployeePosition.employee_id)).all()}
    changed = False
    for e in employees:
        if e.id in existing:
            continue
        if e.org_unit_id or (e.role_type and e.role_type != "staff") or e.position:
            db.add(models.EmployeePosition(
                employee_id=e.id, org_unit_id=e.org_unit_id,
                role_type=e.role_type or "staff", position=e.position, sort_no=1))
            changed = True
    if changed:
        db.commit()


def _backfill_entry_sub_account_id(db) -> None:
    """为历史凭证分录按(科目, 明细科目名)回填 sub_account_id,缺失的二级自动补建。"""
    entries = db.scalars(
        select(models.VoucherEntry).where(
            models.VoucherEntry.sub_account != "",
            models.VoucherEntry.sub_account_id.is_(None))
    ).all()
    if not entries:
        return
    for e in entries:
        sub = subaccounts_svc.get_or_create(db, e.account_id, e.sub_account)
        if sub:
            e.sub_account_id = sub.id
    db.commit()
