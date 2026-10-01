"""Transactional outbox helpers. Jobs are inserted in the same transaction as the
booking change; a separate worker (services/push.py) delivers them."""
from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..models import NotificationJob, now_s


def enqueue(
    db: Session,
    tenant_id: int,
    *,
    booking_id: int | None,
    audience: str,
    kind: str,
    dedupe_key: str,
    run_at: int | None = None,
    payload: dict | None = None,
) -> None:
    """Idempotent: the UNIQUE(tenant_id, dedupe_key) makes a repeat a no-op."""
    db.execute(
        insert(NotificationJob)
        .values(
            tenant_id=tenant_id,
            booking_id=booking_id,
            audience=audience,
            kind=kind,
            dedupe_key=dedupe_key,
            run_at=run_at if run_at is not None else now_s(),
            payload=payload or {},
            status="pending",
            attempts=0,
            created_at=now_s(),
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "dedupe_key"])
    )


def skip_pending(db: Session, booking_id: int, kinds: tuple[str, ...] = ("reminder",)) -> None:
    db.execute(
        update(NotificationJob)
        .where(NotificationJob.booking_id == booking_id, NotificationJob.kind.in_(kinds), NotificationJob.status.in_(("pending", "leased")))
        .values(status="skipped", lease_until=None)
    )
