"""Tenant isolation inside the data-access layer.

A session opened with a tenant_id (taken from the URL slug or the owner session,
never from a request body) automatically:
  * adds `tenant_id = :tid` to every ORM SELECT/UPDATE/DELETE on tenant tables;
  * refuses to flush rows that belong to another tenant.
"""
from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from .models import TenantScoped


class TenantViolation(Exception):
    pass


@event.listens_for(Session, "do_orm_execute")
def _scope_statements(state) -> None:
    tid = state.session.info.get("tenant_id")
    if tid is None or not (state.is_select or state.is_update or state.is_delete):
        return
    state.statement = state.statement.options(
        with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == tid, include_aliases=True)
    )


@event.listens_for(Session, "before_flush")
def _guard_writes(session: Session, _ctx, _instances) -> None:
    tid = session.info.get("tenant_id")
    if tid is None:
        return
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, TenantScoped):
            continue
        if obj.tenant_id is None:
            obj.tenant_id = tid
        elif obj.tenant_id != tid:
            raise TenantViolation(f"{type(obj).__name__} belongs to tenant {obj.tenant_id}, session is {tid}")
