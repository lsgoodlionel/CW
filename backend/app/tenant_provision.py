"""租户开通初始化:为新建租户预置一套基础数据(科目/二级科目/系统角色/审批流程)。

设计:复用 init_db 中的按租户种子函数,统一置于目标租户上下文中执行——
新建对象经 before_flush 自动回填 tenant_id,存在性检查经 SELECT 过滤仅针对该租户,
因此天然幂等且不污染其它租户。这是「按租户初始化」的唯一入口,私有化默认租户由
init_db 走同一批函数,避免逻辑漂移。
"""
from .database import SessionLocal
from .tenant import set_current_tenant, get_current_tenant
from . import init_db as _init


def provision_tenant(db, tenant_id: int) -> None:
    """在指定租户上下文内预置基础数据。调用方负责保证 Tenant 行已存在。幂等。"""
    prev = get_current_tenant()
    set_current_tenant(tenant_id)
    try:
        _init._seed_accounts(db)
        db.commit()
        _init._seed_subaccounts(db)
        _init._seed_roles(db)
        _init._seed_workflow(db)
        db.commit()
    finally:
        set_current_tenant(prev)


def provision_tenant_by_id(tenant_id: int) -> None:
    """独立会话版本(供平台管理后台创建租户后调用)。"""
    db = SessionLocal()
    try:
        provision_tenant(db, tenant_id)
    finally:
        db.close()
