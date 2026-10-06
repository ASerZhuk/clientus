"""Public + client endpoints. The tenant comes from the slug; the client proves access to
one booking with an unguessable token (X-Booking-Token). No client data is ever public."""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import select

from .. import db as database
from ..config import get_settings
from ..deps import TenantCtx, client_booking_id, tenant_dep
from ..models import Booking, PushSubscription, Service, TenantSettings
from ..ratelimit import limit_request
from ..security import calendar_sig, safe_equal
from ..schemas import AssistantIn, BookingIn, PushRotateIn, PushSubscriptionIn
from ..services import assistant, subscription
from ..services import booking as bk
from ..services import media, push
from ..profiles import get_profile
from ..services.slots import compute_slots, next_available, offers_for
from ..timeutil import local_date, now_min, tz_of
from ..views import booking_client_view, public_tenant

router = APIRouter(prefix="/api")


def _error(exc: bk.BookingError) -> HTTPException:
    return HTTPException(exc.status, {"code": exc.code, **exc.detail})


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/media/{path:path}")
def media_file(path: str) -> FileResponse:
    try:
        full = media.safe_path(path)
    except media.ImageError:
        raise HTTPException(404) from None
    if not full.is_file():
        raise HTTPException(404)
    # config/upload names are content hashes or random ids; pwa assets are regenerated in place
    cache = "public, max-age=3600" if "/pwa/" in path else "public, max-age=31536000, immutable"
    return FileResponse(full, headers={"Cache-Control": cache, "X-Content-Type-Options": "nosniff"})


@router.get("/s/{slug}")
def tenant_public(tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    with database.read_session(tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        return public_tenant(db, tenant, settings)


def _service(db, service_id: int) -> Service:
    svc = db.scalar(select(Service).where(Service.id == service_id, Service.is_active.is_(True)))
    if not svc:
        raise HTTPException(404, {"code": "service_not_found"})
    return svc


@router.get("/s/{slug}/slots")
def slots(
    request: Request,
    service_id: int = Query(gt=0),
    from_date: date | None = Query(default=None, alias="from"),
    days: int = Query(default=14, ge=1, le=31),
    resource_id: int | None = Query(default=None, gt=0),
    tenant: TenantCtx = Depends(tenant_dep),
) -> dict:
    """Every start moment of the days, occupied ones explicitly marked available=false.
    Where customers pick a master (resource_id), only that master's moments are returned."""
    limit_request(request, tenant.id, "slots", 120, 60)
    with database.read_session(tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        svc = _service(db, service_id)
        tz = tz_of(settings.timezone)
        now = now_min()
        first = from_date or local_date(now, tz)
        first = max(first, local_date(now, tz))
        choose = get_profile(settings.business_type).features["choose_resource"]
        window = compute_slots(db, settings, svc, first, days, now, only_resource_id=resource_id if choose else None)
        return {
            "service_id": svc.id,
            "bookable": bool(offers_for(db, svc)),
            "days": {
                d: [{"start_min": s.start_min, "available": s.available, **({"resource_ids": list(s.resource_ids)} if choose else {})} for s in items]
                for d, items in window.items()
            },
        }


@router.get("/s/{slug}/next-slot")
def next_slot(request: Request, service_id: int = Query(gt=0), resource_id: int | None = Query(default=None, gt=0), tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    limit_request(request, tenant.id, "slots", 120, 60)
    with database.read_session(tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        svc = _service(db, service_id)
        choose = get_profile(settings.business_type).features["choose_resource"]
        slot = next_available(db, settings, svc, now_min(), only_resource_id=resource_id if choose else None)
        return {"service_id": svc.id, "start_min": slot.start_min if slot else None}


@router.post("/s/{slug}/bookings", status_code=201)
def create_booking(
    body: BookingIn,
    request: Request,
    response: Response,
    idempotency_key: str = Header(min_length=8, max_length=80),
    tenant: TenantCtx = Depends(tenant_dep),
) -> dict:
    limit_request(request, tenant.id, "book", 10, 600, per_tenant=300)
    try:
        with database.write_session(tenant.id) as db:
            settings = db.scalar(select(TenantSettings))
            subscription.assert_can_book(db, tenant)
            profile = get_profile(settings.business_type)
            if body.resource_id is not None and not profile.features["choose_resource"]:
                raise HTTPException(422, {"code": "resource_choice_not_allowed"})
            if profile.contact["car"] == "required" and not body.car.strip():
                raise HTTPException(422, {"code": "car_required"})
            res = bk.create_booking(
                db,
                tenant_id=tenant.id,
                settings=settings,
                is_preview=tenant.is_preview,
                service_id=body.service_id,
                start_min=body.start_min,
                name=body.name,
                phone=body.phone,
                car=body.car,
                plate=body.plate,
                note=body.note,
                now_min=now_min(),
                idempotency_key=idempotency_key,
                resource_id=body.resource_id,
            )
            view = booking_client_view(db, res.booking, settings, now_min())
    except bk.BookingError as exc:
        raise _error(exc) from exc
    response.status_code = 201 if res.created else 200
    response.headers["Cache-Control"] = "no-store"
    return {"booking": view, "access_token": res.access_token, "replayed": not res.created}


@router.get("/s/{slug}/my/booking")
def my_booking(response: Response, booking_id: int = Depends(client_booking_id), tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    with database.read_session(tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        booking = db.get(Booking, booking_id)
        return booking_client_view(db, booking, settings, now_min())


def _ics_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@router.get("/s/{slug}/calendar/{booking_id}.ics")
def booking_ics(booking_id: int, sig: str = Query(min_length=8, max_length=64), tenant: TenantCtx = Depends(tenant_dep)) -> Response:
    """Served as text/calendar so Safari (iPhone, Mac) opens its own "Add to Calendar" sheet instead of downloading a file."""
    if not safe_equal(sig, calendar_sig(tenant.id, booking_id)):
        raise HTTPException(404, {"code": "booking_not_found"})
    with database.read_session(tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        b = db.get(Booking, booking_id)
        if not b or b.status == "cancelled":
            raise HTTPException(404, {"code": "booking_not_found"})
        stamp = lambda m: datetime.fromtimestamp(m * 60, timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: E731
        note = (f"Автомобиль: {b.car}\n" if b.car else "") + (f"Телефон: {settings.phone}" if settings.phone else "")
        body = "\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//clientall//RU", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "BEGIN:VEVENT",
            f"UID:booking-{b.id}@{tenant.slug}", f"DTSTAMP:{stamp(now_min())}", f"DTSTART:{stamp(b.start_min)}", f"DTEND:{stamp(b.end_min)}",
            f"SUMMARY:{_ics_text(f'{b.service_name} — {settings.name}')}", f"LOCATION:{_ics_text(settings.address or '')}", f"DESCRIPTION:{_ics_text(note)}",
            "BEGIN:VALARM", "TRIGGER:-PT2H", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(b.service_name)}", "END:VALARM",
            "END:VEVENT", "END:VCALENDAR", "",
        ])
    return Response(body, media_type="text/calendar; charset=utf-8", headers={"Content-Disposition": f'inline; filename="zapis-{booking_id}.ics"', "Cache-Control": "no-store"})


@router.post("/s/{slug}/my/cancel")
def my_cancel(response: Response, booking_id: int = Depends(client_booking_id), tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    try:
        with database.write_session(tenant.id) as db:
            settings = db.scalar(select(TenantSettings))
            booking = bk.cancel_booking(db, tenant_id=tenant.id, settings=settings, is_preview=tenant.is_preview, booking_id=booking_id, by="client", now_min=now_min())
            return booking_client_view(db, booking, settings, now_min())
    except bk.BookingError as exc:
        raise _error(exc) from exc


@router.get("/s/{slug}/push/config")
def push_config(tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    """Honest capability report: the UI never promises push the server cannot deliver."""
    return {"enabled": push.vapid_configured() and not tenant.is_preview, "public_key": get_settings().vapid_public_key or None, "preview": tenant.is_preview}


@router.post("/s/{slug}/my/push", status_code=204)
def my_push_subscribe(
    body: PushSubscriptionIn, request: Request, booking_id: int = Depends(client_booking_id), tenant: TenantCtx = Depends(tenant_dep)
) -> None:
    if not push.vapid_configured():
        raise HTTPException(503, {"code": "push_not_configured"})
    device, origin = push.device_label(request.headers.get("user-agent")), push.request_origin(request.headers)
    with database.write_session(tenant.id) as db:
        existing = db.scalar(select(PushSubscription).where(PushSubscription.audience == "client", PushSubscription.endpoint == body.endpoint, PushSubscription.booking_id == booking_id))
        if existing:
            existing.p256dh, existing.auth, existing.disabled_at, existing.device, existing.failure_count, existing.origin = body.keys.p256dh, body.keys.auth, None, device, 0, origin
        else:
            db.add(PushSubscription(tenant_id=tenant.id, audience="client", booking_id=booking_id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth, device=device, origin=origin))


@router.post("/s/{slug}/push/rotate", status_code=204)
def push_rotate(body: PushRotateIn, request: Request, tenant: TenantCtx = Depends(tenant_dep)) -> None:
    """Called by the service worker when the browser replaces a subscription, so notifications keep arriving
    without the person switching them on again. Covers every audience of this studio tied to the old endpoint."""
    limit_request(request, tenant.id, "push-rotate", 10, 60)
    new = body.subscription
    with database.write_session(tenant.id) as db:
        for sub in db.scalars(select(PushSubscription).where(PushSubscription.endpoint == body.old_endpoint)):
            sub.endpoint, sub.p256dh, sub.auth, sub.disabled_at, sub.failure_count, sub.last_error = new.endpoint, new.keys.p256dh, new.keys.auth, None, 0, None


@router.get("/s/{slug}/my/push")
def my_push_status(endpoint: str = Query(min_length=10), booking_id: int = Depends(client_booking_id), tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    """Is THIS booking's reminder on for this device? A device can be subscribed for other reasons (e.g. as the owner)."""
    with database.read_session(tenant.id) as db:
        sub = db.scalar(select(PushSubscription.id).where(PushSubscription.audience == "client", PushSubscription.booking_id == booking_id, PushSubscription.endpoint == endpoint, PushSubscription.disabled_at.is_(None)))
    return {"on": sub is not None}


@router.delete("/s/{slug}/my/push", status_code=204)
def my_push_unsubscribe(endpoint: str = Query(min_length=10), booking_id: int = Depends(client_booking_id), tenant: TenantCtx = Depends(tenant_dep)) -> None:
    with database.write_session(tenant.id) as db:
        for sub in db.scalars(select(PushSubscription).where(PushSubscription.booking_id == booking_id, PushSubscription.endpoint == endpoint)):
            db.delete(sub)


@router.post("/s/{slug}/assistant")
def client_assistant(body: AssistantIn, request: Request, tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    limit_request(request, tenant.id, "assistant", 30, 60, per_tenant=600)
    with database.read_session(tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        reads = assistant.PublicReads(db, settings, now_min())
        return assistant.answer("client", body.text, body.context, reads, [h.model_dump() for h in body.history]).as_dict()


@router.get("/s/{slug}/assistant/examples")
def client_examples(tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    with database.read_session(tenant.id) as db:
        return {"examples": assistant.client_examples(db.scalar(select(TenantSettings.business_type)))}


