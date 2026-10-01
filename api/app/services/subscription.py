"""Subscription lifecycle, computed from dates at request time (no cron needed).

  preview  - a sample link; nothing is enforced
  trial    - trial_ends_at in the future
  active   - paid_until in the future, or an activated studio with no dates (lifetime: the one-time purchase)
  past_due - the period ended less than GRACE_DAYS ago: works, with a warning
  suspended- the grace period is over or the operator suspended it: read-only, customers cannot book
  disabled - taken offline by the operator
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Booking, Resource, now_s
from ..config import get_settings
from ..plans import Plan, get_plan

GRACE_DAYS = 7  # after a paid/trial period with an end date runs out (only used when dates are set)

DAY = 86400


class SubscriptionError(Exception):
    def __init__(self, code: str, detail: dict | None = None):
        super().__init__(code)
        self.code, self.detail = code, detail or {}


def state_of(tenant, now: int | None = None) -> str:
    """tenant: anything with status, suspended, trial_ends_at, paid_until."""
    now = now or now_s()
    if tenant.status == "disabled":
        return "disabled"
    if tenant.status == "preview":
        return "preview"
    if tenant.suspended:
        return "suspended"
    if tenant.paid_until and now <= tenant.paid_until:
        return "active"
    if tenant.trial_ends_at and now <= tenant.trial_ends_at and not tenant.paid_until:
        return "trial"
    deadline = max(tenant.paid_until or 0, tenant.trial_ends_at or 0)
    if deadline == 0:
        return "active"  # activated without dates: complimentary
    return "past_due" if now <= deadline + GRACE_DAYS * DAY else "suspended"


def booking_enabled(tenant, now: int | None = None) -> bool:
    return state_of(tenant, now) not in ("suspended", "disabled")


def month_start(now: int) -> int:
    d = datetime.fromtimestamp(now, tz=timezone.utc)
    return int(d.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())


def usage(db: Session, now: int | None = None) -> dict:
    """Counts inside the (tenant-scoped) session."""
    now = now or now_s()
    bookings = db.scalar(select(func.count()).select_from(Booking).where(Booking.created_at >= month_start(now), Booking.is_demo.is_(False))) or 0
    resources = db.scalar(select(func.count()).select_from(Resource).where(Resource.is_active.is_(True))) or 0
    return {"bookings_month": int(bookings), "resources": int(resources)}


def assert_can_book(db: Session, tenant, now: int | None = None) -> None:
    now = now or now_s()
    if not booking_enabled(tenant, now):
        raise SubscriptionError("studio_suspended")
    if tenant.status == "preview":
        return
    plan = get_plan(tenant.plan)
    if plan.max_bookings_month is not None and usage(db, now)["bookings_month"] >= plan.max_bookings_month:
        raise SubscriptionError("plan_limit_bookings", {"limit": plan.max_bookings_month, "plan": plan.key})


def assert_can_add_resource(db: Session, tenant) -> None:
    plan = get_plan(tenant.plan)
    if plan.max_resources is not None and usage(db)["resources"] >= plan.max_resources:
        raise SubscriptionError("plan_limit_resources", {"limit": plan.max_resources, "plan": plan.key})


def overview(db: Session, tenant, now: int | None = None) -> dict:
    """What the cabinet and the operator panel show."""
    now = now or now_s()
    plan: Plan = get_plan(tenant.plan)
    u = usage(db, now)
    end = tenant.paid_until if tenant.paid_until and now <= tenant.paid_until else tenant.trial_ends_at
    return {
        "plan": plan.key,
        "plan_label": plan.label,
        "state": state_of(tenant, now),
        "ends_at": end,
        "days_left": max(0, -(-(end - now) // DAY)) if end else None,
        "limits": {"resources": plan.max_resources, "bookings_month": plan.max_bookings_month, "custom_domain": plan.custom_domain, "remove_branding": plan.remove_branding},
        "usage": u,
    }


def start_trial(tenant, now: int | None = None) -> None:
    """Only when TRIAL_DAYS > 0. By default an activated studio is lifetime: no dates, never expires."""
    days = get_settings().trial_days
    now = now or now_s()
    if days > 0 and not tenant.trial_ends_at and not tenant.paid_until:
        tenant.trial_ends_at = now + days * DAY
