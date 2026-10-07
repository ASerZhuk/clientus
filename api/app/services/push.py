"""Outbox delivery: lease -> send -> finalise. Runs in the separate worker process
(app/worker.py). Network I/O never happens while a write transaction is open."""
import json
import re
from typing import Callable

from sqlalchemy import and_, func, or_, select, update

from .. import db as database
from ..config import get_settings
from ..models import Booking, Membership, NotificationJob, PushSubscription, Resource, Service, Tenant, TenantSettings, now_s
from ..profiles import get_profile
from ..timeutil import min_to_dt, tz_of
from .assistant import MONTHS_GEN, WEEKDAYS_SHORT

MAX_ATTEMPTS = 5
LEASE_SECONDS = 120

Sender = Callable[[dict, dict], None]  # (subscription_info, payload) -> raises PushGone / Exception


class PushGone(Exception):
    """The subscription is dead (HTTP 404/410): disable it."""


def device_label(user_agent: str | None) -> str:
    """'Android · Chrome', 'iPhone · Safari'… shown in the owner's device list; never used for decisions."""
    ua = user_agent or ""
    os_name = next((n for pat, n in ((r"iPhone", "iPhone"), (r"iPad", "iPad"), (r"Android", "Android"), (r"Windows", "Windows"),
                                      (r"Mac OS X|Macintosh", "Mac"), (r"Linux", "Linux")) if re.search(pat, ua)), "Устройство")
    browser = next((n for pat, n in ((r"YaBrowser", "Яндекс Браузер"), (r"SamsungBrowser", "Samsung Internet"), (r"Edg/|EdgA/|EdgiOS", "Edge"),
                                      (r"OPR/|Opera", "Opera"), (r"Firefox|FxiOS", "Firefox"), (r"CriOS|Chrome/", "Chrome"), (r"Safari/", "Safari"))
                    if re.search(pat, ua)), "браузер")
    return f"{os_name} · {browser}"


def request_origin(headers) -> str:
    """The site the subscription is made on ("https://test.clientall.ru", a studio's own domain…)."""
    origin = (headers.get("origin") or "").rstrip("/")
    if re.fullmatch(r"https?://[A-Za-z0-9.\-]+(:\d+)?", origin):
        return origin
    host = headers.get("x-forwarded-host") or headers.get("host") or ""
    return f"{headers.get('x-forwarded-proto', 'https')}://{host}" if host else ""


def declarative(message: dict, origin: str, slug: str, badge: int | None = None) -> dict:
    """Declarative Web Push (Safari 18.4+): Safari can show this even if the service worker does not run in time.
    Chrome and older browsers receive the same JSON in the service worker's push event. `mutable` keeps our
    worker in charge where it runs (live refresh, badge), with this as the fallback on Apple devices."""
    s = get_settings()
    origin = origin or (s.origins[0] if s.origins else "")
    host = re.sub(r"^https?://", "", origin).split(":")[0]
    path = message.get("url") or f"/s/{slug}/"
    if host and host not in s.platform_host_list:  # a studio's own domain serves the studio at the root
        path = path.removeprefix(f"/s/{slug}") or "/"
    notification = {"title": message["title"], "body": message["body"], "navigate": f"{origin}{path}", "lang": "ru", "dir": "ltr"}
    if message.get("tag"):
        notification["tag"] = message["tag"]
    if badge is not None:
        notification["app_badge"] = max(0, int(badge))
    return {"web_push": 8030, "notification": notification, "mutable": True, "kind": message.get("kind")}


def unseen_for_owners(db, tenant_id: int, user_ids: set[int]) -> dict[int, int]:
    """App icon badge: client bookings made after the owner last opened the schedule (cancelled ones excluded)."""
    out: dict[int, int] = {}
    for m in db.scalars(select(Membership).where(Membership.tenant_id == tenant_id, Membership.user_id.in_(user_ids))):
        out[m.user_id] = db.scalar(
            select(func.count()).select_from(Booking).where(Booking.source == "client", Booking.status != "cancelled", Booking.created_at > (m.seen_at or 0))
        ) or 0
    return out


def record_delivery(results: dict[int, str | None]) -> None:
    """Per subscription: None = delivered, text = the error. Feeds the device list in the cabinet."""
    if not results:
        return
    now = now_s()
    with database.write_session() as db:
        for sub in db.scalars(select(PushSubscription).where(PushSubscription.id.in_(list(results)))):
            err = results[sub.id]
            if err is None:
                sub.last_success_at, sub.failure_count, sub.last_error = now, 0, None
            else:
                sub.failure_count, sub.last_error = (sub.failure_count or 0) + 1, err[:200]


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


def _message(job: NotificationJob, booking: Booking, settings: TenantSettings, slug: str, place: str = "") -> dict:
    tz = tz_of(settings.timezone)
    dt = min_to_dt(booking.start_min, tz)
    when = f"{WEEKDAYS_SHORT[dt.weekday()]}, {dt.day} {MONTHS_GEN[dt.month - 1]} в {dt:%H:%M}"
    what = f"{booking.service_name} · {settings.name}"
    titles = {
        "reminder": ("Напоминание о записи", f"{when}: {what}" + (f" · {place}" if place else "")),
        "new": ("Новая запись", f"{when}: {booking.service_name}" + (f", {booking.car}" if booking.car else "")),
        "cancelled": ("Запись отменена", f"{when}: {what}"),
        "moved": ("Запись перенесена", f"Новое время — {when}: {what}"),
    }
    title, body = titles[job.kind]
    url = f"/s/{slug}/owner" if job.audience == "owner" else f"/s/{slug}/my"
    return {"title": title, "body": body, "url": url, "tag": f"{job.kind}-{booking.id}", "kind": job.kind}


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
            rows = list(db.scalars(q))
            subs = [(s.id, {"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}}) for s in rows]
            owner_of = {s.id: s.user_id for s in rows if s.user_id}
            origin_of = {s.id: s.origin for s in rows}
            badges = unseen_for_owners(db, job.tenant_id, set(owner_of.values())) if job.audience == "owner" and owner_of else {}
        skip_reason = None
        if booking is None or tenant is None or tenant.status not in ("active", "preview"):
            skip_reason = "not_active"
        elif job.kind != "cancelled" and booking.status == "cancelled":
            skip_reason = "booking_cancelled"
        elif job.kind == "reminder" and (booking.start_min != job.payload.get("start_min", booking.start_min) or booking.start_min * 60 < now):
            skip_reason = "stale_reminder"
        elif not vapid_configured() and sender is real_sender:
            skip_reason = "push_not_configured"
        elif not subs:
            skip_reason = "no_subscription"
        res = db.get(Resource, booking.resource_id) if skip_reason is None and get_profile(settings.business_type).kind == "vehicle" else None
        message = _message(job, booking, settings, tenant.slug, res.name if res else "") if skip_reason is None else None
        tenant_slug = tenant.slug if tenant else ""
        attempts = job.attempts

    if skip_reason:
        return _finish(job_id, "skipped", skip_reason, now=now)

    delivered, errors, dead, results = 0, [], [], {}
    for sub_id, info in subs:
        badge = badges.get(owner_of.get(sub_id)) if owner_of.get(sub_id) in badges else None
        payload = declarative(message, origin_of.get(sub_id, ""), tenant_slug, badge)
        try:
            sender(info, payload)
            delivered += 1
            results[sub_id] = None
        except PushGone:
            dead.append(sub_id)
            results[sub_id] = "subscription gone (404/410)"
        except Exception as exc:  # transient network / push service error
            errors.append(str(exc)[:200])
            results[sub_id] = str(exc)
    record_delivery(results)
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
