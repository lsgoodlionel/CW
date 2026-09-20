"""多租户隔离机制:租户上下文 + SQLAlchemy 全局自动过滤/回填。

设计要点:
- 业务模型继承 TenantMixin(附带 tenant_id 列),即自动纳入隔离,无需逐查询手加 where。
- do_orm_execute 事件:对 SELECT 统一注入 tenant_id 过滤(with_loader_criteria 覆盖所有 TenantMixin 子类)。
- before_flush 事件:对新建对象自动回填当前租户 tenant_id。
- 平台超管跨租户 / 系统初始化:将当前租户置空(None)即不过滤;或用 skip_tenant 执行选项。
- 私有化(private)模式:当前租户恒为默认租户,单租户下过滤对结果无影响,行为与单机版一致。
"""
from contextvars import ContextVar

from sqlalchemy import Integer, event
from sqlalchemy.orm import Mapped, mapped_column, Session, with_loader_criteria

from .config import DEFAULT_TENANT_ID

# 当前请求的租户;None 表示不做租户过滤(平台超管跨租户 / 系统初始化)
_current_tenant: ContextVar[int | None] = ContextVar("current_tenant", default=None)


def set_current_tenant(tenant_id: int | None) -> None:
    _current_tenant.set(tenant_id)


def get_current_tenant() -> int | None:
    return _current_tenant.get()


class TenantMixin:
    """业务模型混入:附带 tenant_id 列,自动参与租户隔离。"""
    tenant_id: Mapped[int] = mapped_column(
        Integer, index=True, nullable=False,
        default=DEFAULT_TENANT_ID, server_default=str(DEFAULT_TENANT_ID),
    )


def install_tenant_isolation() -> None:
    """注册 SQLAlchemy 事件,启用全局租户过滤与回填。仅需在应用启动调用一次。"""

    @event.listens_for(Session, "do_orm_execute")
    def _apply_tenant_filter(orm_execute_state):  # noqa: ANN001
        if not orm_execute_state.is_select:
            return
        if orm_execute_state.execution_options.get("skip_tenant"):
            return
        tid = _current_tenant.get()
        if tid is None:
            return
        orm_execute_state.statement = orm_execute_state.statement.options(
            with_loader_criteria(
                TenantMixin,
                lambda cls: cls.tenant_id == tid,
                include_aliases=True,
            )
        )

    @event.listens_for(Session, "before_flush")
    def _fill_tenant_id(session, flush_context, instances):  # noqa: ANN001
        tid = _current_tenant.get()
        if tid is None:
            return
        for obj in session.new:
            if isinstance(obj, TenantMixin) and getattr(obj, "tenant_id", None) in (None, 0):
                obj.tenant_id = tid
