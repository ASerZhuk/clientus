"""Outbox delivery: lease -> send -> finalise. Runs in the separate worker process
(app/worker.py). Network I/O never happens while a write transaction is open."""
import json
from typing import Callable

from sqlalchemy import and_, or_, select, update

from .. import db as database
from ..config import get_settings
from ..models import Booking, NotificationJob, PushSubscription, Service, Tenant, TenantSettings, now_s
from ..timeutil import min_to_dt, tz_of
from .assistant import MONTHS_GEN, WEEKDAYS_SHORT

MAX_ATTEMPTS = 5
LEASE_SECONDS = 120

Sender = Callable[[dict, dict], None]  # (subscription_info, payload) -> raises PushGone / Exception


class PushGone(Exception):
    """The subscription is dead (HTTP 404/410): disable it."""


def vapid_configured() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key_path)


def real_sender(subscription: dict, payload: dict) -> None:
    from pywebpush import WebPushException, webpush

    s = get_settings()
    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=s.vapid_private_key_path,
            vapid_claims={"sub": s.vapid_subject},
            ttl=60 * 60 * 12,
        )
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            raise PushGone(str(exc)) from exc
        raise


def lease_due(limit: int = 20, now: int | None = None) -> list[int]:
    """Atomically claim due jobs (BEGIN IMMEDIATE). A crashed worker's lease simply expires."""
    now = now or now_s()
    with database.write_session() as db:
        ids = list(
            db.scalars(
                select(NotificationJob.id)
                .where(
                    NotificationJob.run_at <= now,
                    or_(NotificationJob.status == "pending", and_(NotificationJob.status == "leased", NotificationJob.lease_until < now)),
                )
                .order_by(NotificationJob.run_at)
                .limit(limit)
            )
        )
        if ids:
            db.execute(
                update(NotificationJob)
                .where(NotificationJob.id.in_(ids))
                .values(status="leased", lease_until=now + LEASE_SECONDS, attempts=NotificationJob.attempts + 1)
            )
    return ids


def _message(job: NotificationJob, booking: Booking, settings: TenantSettings, slug: str) -> dict:
    tz = tz_of(settings.timezone)
    dt = min_to_dt(booking.start_min, tz)
    when = f"{WEEKDAYS_SHORT[dt.weekday()]}, {dt.day} {MONTHS_GEN[dt.month - 1]} в {dt:%H:%M}"
    what = f"{booking.service_name} · {settings.name}"
    titles = {
        "reminder": ("Напоминание о записи", f"{when}: {what}"),
        "new": ("Новая запись", f"{when}: {booking.service_name}" + (f", {booking.car}" if booking.car else "")),
        "cancelled": ("Запись отменена", f"{when}: {what}"),
        "moved": ("Запись перенесена", f"Новое время — {when}: {what}"),
    }
    title, body = titles[job.kind]
    url = f"/s/{slug}/owner" if job.audience == "owner" else f"/s/{slug}/my"
    return {"title": title, "body": body, "url": url, "tag": f"{job.kind}-{booking.id}"}


def process(job_id: int, sender: Sender = real_sender, now: int | None = None) -> str:
    """Returns the final status of the job."""
    now = now or now_s()
    with database.read_session() as db:
        job = db.get(NotificationJob, job_id)
        if not job or job.status != "leased":
            return "ignored"
        tenant = db.get(Tenant, job.tenant_id)
        db.info["tenant_id"] = job.tenant_id
        booking = db.get(Booking, job.booking_id) if job.booking_id else None
        settings = db.scalar(select(TenantSettings))
        subs = []
        if booking is not None:
            q = select(PushSubscription).where(PushSubscription.audience == job.audience, PushSubscription.disabled_at.is_(None))
            if job.audience == "client":
                q = q.where(PushSubscription.booking_id == booking.id)
            subs = [(s.id, {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}}) for s in db.scalars(q)]
        skip_reason = None
        if booking is None or tenant is None or tenant.status != "active":
            skip_reason = "not_active"
        elif job.kind != "cancelled" and booking.status == "cancelled":
            skip_reason = "booking_cancelled"
        elif job.kind == "reminder" and (booking.start_min != job.payload.get("start_min", booking.start_min) or booking.start_min * 60 < now):
            skip_reason = "stale_reminder"
        elif not vapid_configured() and sender is real_sender:
            skip_reason = "push_not_configured"
        elif not subs:
            skip_reason = "no_subscription"
        message = _message(job, booking, settings, tenant.slug) if skip_reason is None else None
        attempts = job.attempts

    if skip_reason:
        return _finish(job_id, "skipped", skip_reason, now=now)

    delivered, errors, dead = 0, [], []
    for sub_id, info in subs:
        try:
            sender(info, message)
            delivered += 1
        except PushGone:
            dead.append(sub_id)
        except Exception as exc:  # transient network / push service error
            errors.append(str(exc)[:200])
    if dead:
        with database.write_session() as db:
            db.execute(update(PushSubscription).where(PushSubscription.id.in_(dead)).values(disabled_at=now_s()))
    if delivered:
        return _finish(job_id, "sent", None, now=now)
    if errors and attempts < MAX_ATTEMPTS:
        return _finish(job_id, "pending", errors[0], retry_in=60 * 2 ** (attempts - 1), now=now)
    return _finish(job_id, "failed" if errors else "skipped", errors[0] if errors else "subscription_gone", now=now)


def _finish(job_id: int, status: str, error: str | None, retry_in: int = 0, now: int | None = None) -> str:
    with database.write_session() as db:
        values: dict = {"status": status, "last_error": error, "lease_until": None}
        if retry_in:
            values["run_at"] = (now or now_s()) + retry_in
        db.execute(update(NotificationJob).where(NotificationJob.id == job_id).values(**values))
    return status


def run_once(sender: Sender = real_sender, limit: int = 20, now: int | None = None) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job_id in lease_due(limit, now):
        status = process(job_id, sender, now)
        counts[status] = counts.get(status, 0) + 1
    return counts
