"""Owner statistics. Everything is computed by SQL; the cabinet and the owner assistant
call the same function, so period boundaries (tenant timezone) always agree.

Kept apart on purpose: visits (cars scheduled), completed works, money actually received
(payments minus refunds, by payment date) and scheduled value of future work, which is
never reported as revenue."""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import Booking, Payment
from ..timeutil import day_bounds, local_date

PERIODS = ("today", "tomorrow", "yesterday", "week", "last_week", "month", "last_month")


def period_dates(period: str, tz: ZoneInfo, now_min: int, anchor: date | None = None) -> tuple[date, date]:
    """[first_day, day_after_last) in tenant-local dates."""
    today = anchor or local_date(now_min, tz)
    if period == "today":
        return today, today + timedelta(days=1)
    if period == "tomorrow":
        return today + timedelta(days=1), today + timedelta(days=2)
    if period == "yesterday":
        return today - timedelta(days=1), today
    monday = today - timedelta(days=today.weekday())
    if period == "week":
        return monday, monday + timedelta(days=7)
    if period == "last_week":
        return monday - timedelta(days=7), monday
    first = today.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    if period == "month":
        return first, nxt
    if period == "last_month":
        return (first - timedelta(days=1)).replace(day=1), first
    raise ValueError(f"unknown period {period}")


def compute(db: Session, tz: ZoneInfo, first: date, after: date, now_min: int) -> dict:
    lo, _ = day_bounds(first, tz)
    hi, _ = day_bounds(after, tz)
    b = db.execute(
        select(
            func.coalesce(func.sum(case((Booking.status != "cancelled", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Booking.status == "ready", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Booking.status == "cancelled", 1), else_=0)), 0),
            func.coalesce(
                func.sum(case(((Booking.status.in_(("booked", "accepted"))) & (Booking.start_min >= now_min), Booking.price_minor), else_=0)), 0
            ),
        ).where(Booking.start_min >= lo, Booking.start_min < hi)
    ).one()
    p = db.execute(
        select(
            func.coalesce(func.sum(case((Payment.kind == "payment", Payment.amount_minor), else_=0)), 0),
            func.coalesce(func.sum(case((Payment.kind == "refund", Payment.amount_minor), else_=0)), 0),
        ).where(Payment.created_at >= lo * 60, Payment.created_at < hi * 60)
    ).one()
    return {
        "from": first.isoformat(),
        "to": (after - timedelta(days=1)).isoformat(),
        "visits": int(b[0]),
        "completed": int(b[1]),
        "cancelled": int(b[2]),
        "scheduled_value_minor": int(b[3]),
        "received_minor": int(p[0]) - int(p[1]),
        "payments_minor": int(p[0]),
        "refunds_minor": int(p[1]),
    }
