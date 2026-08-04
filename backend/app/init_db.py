"""初始化:建表、轻量迁移、预置科目与企业信息单例。幂等。"""
from sqlalchemy import inspect, text, select

from .database import Base, engine, SessionLocal
from . import models
from .seed_accounts import ACCOUNTS
from .seed_subaccounts import SUB_ACCOUNTS
from . import subaccounts_svc


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate(engine)
    db = SessionLocal()
    try:
        _seed_accounts(db)
        _seed_company(db)
        db.commit()
        _seed_subaccounts(db)
        _backfill_entry_sub_account_id(db)
        _backfill_employee_positions(db)
        _seed_auth(db)
        _seed_workflow(db)
        db.commit()
    finally:
        db.close()


# 已存在的表在版本迭代中新增的列:{表名: [(列名, 建列 DDL 片段), ...]}
_ADDED_COLUMNS = {
    "vouchers": [
        ("customer_id", "INTEGER"),
    ],
    "voucher_entries": [
        ("sub_account_id", "INTEGER"),
    ],
    "attachments": [
        ("expense_application_id", "INTEGER"),
        ("expense_claim_id", "INTEGER"),
    ],
    "expense_claims": [
        ("application_id", "INTEGER"),
    ],
    "customers": [
        ("party_type", "VARCHAR(20) DEFAULT 'enterprise'"),
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
    _relax_attachment_voucher(bind, inspector)


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


def _seed_company(db) -> None:
    if db.get(models.CompanyInfo, 1) is None:
        db.add(models.CompanyInfo(id=1, name="我的小微企业"))


def _seed_auth(db) -> None:
    """首次创建超级管理员与默认角色。幂等。"""
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
    if db.scalar(select(models.Role.id).limit(1)) is None:
        readonly = models.Role(name="只读查看", note="所有模块仅查看", is_system=True)
        for m in auth_svc.MODULES:
            readonly.permissions.append(models.RolePermission(perm=f"{m}:view"))
        db.add(readonly)
        finance = models.Role(name="财务操作", note="凭证/科目/往来/报表/账簿/申请/报销 常规操作", is_system=True)
        for m in ("voucher", "account", "customer", "expense_apply", "expense"):
            for a in ("view", "create", "edit", "delete"):
                finance.permissions.append(models.RolePermission(perm=f"{m}:{a}"))
        for m in ("report", "ledger", "company"):
            finance.permissions.append(models.RolePermission(perm=f"{m}:view"))
        db.add(finance)
        approver = models.Role(name="审批人", note="审批流程与申请/报销审批", is_system=True)
        for m in ("workflow", "expense_apply", "expense"):
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
