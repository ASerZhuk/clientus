"""Owner cabinet API. Every route except login depends on owner_dep: session cookie ->
server-side session -> membership for the slug's tenant -> CSRF token on unsafe methods."""
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import delete, func, select

from .. import db as database
from ..config import get_settings
from ..deps import SESSION_COOKIE, OwnerCtx, TenantCtx, owner_dep, tenant_dep
from ..models import (
    Booking,
    GalleryPhoto,
    Membership,
    OwnerSession,
    PushSubscription,
    Resource,
    ResourceException,
    ResourceHours,
    ResourceOccupancy,
    ScheduleException,
    Service,
    ServiceResource,
    TenantSettings,
    User,
    WorkingHours,
    now_s,
)
from ..ratelimit import limit_request
from ..schemas import (
    AssistantIn,
    BlockIn,
    CaptionIn,
    HoursIn,
    LoginIn,
    OfferIn,
    OwnerBookingIn,
    PaymentIn,
    PushSubscriptionIn,
    RescheduleIn,
    ResourceIn,
    ResourceScheduleIn,
    ServiceIn,
    SettingsPatch,
    StatusIn,
)
from ..profiles import get_profile
from ..security import new_token, sha256_hex, verify_password
from ..services import assistant, media, push, stats, subscription
from ..services import booking as bk
from ..services.slots import compute_slots, service_resources
from ..timeutil import day_bounds, local_date, now_min, tz_of
from ..views import booking_owner_view, exceptions_view, public_tenant

router = APIRouter(prefix="/api/s/{slug}/owner")


def _error(exc: bk.BookingError) -> HTTPException:
    return HTTPException(exc.status, {"code": exc.code, **exc.detail})


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


# ------------------------------------------------------------------- session
@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, tenant: TenantCtx = Depends(tenant_dep)) -> dict:
    limit_request(request, tenant.id, "login", 8, 600, per_tenant=60)
    email = body.email.lower()
    with database.read_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        member = db.get(Membership, (user.id, tenant.id)) if user else None
    password_ok = verify_password(body.password, user.password_hash if user else None)
    if not (user and member and password_ok):  # same answer for every failure
        raise HTTPException(401, {"code": "invalid_credentials"})
    token, csrf = new_token(), secrets.token_urlsafe(24)
    ttl = get_settings().session_days * 86400
    with database.write_session() as db:
        db.add(OwnerSession(token_hash=sha256_hex(token), user_id=user.id, tenant_id=tenant.id, csrf_token=csrf, expires_at=now_s() + ttl))
    response.set_cookie(
        SESSION_COOKIE, token, max_age=ttl, httponly=True, samesite="lax", secure=get_settings().cookie_secure,
        path=f"/api/s/{tenant.slug}/owner",
    )
    _no_store(response)
    return {"email": user.email, "csrf_token": csrf}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, ctx: OwnerCtx = Depends(owner_dep)) -> None:
    raw = request.cookies.get(SESSION_COOKIE, "")
    with database.write_session() as db:
        db.execute(delete(OwnerSession).where(OwnerSession.token_hash == sha256_hex(raw)))
    response.delete_cookie(SESSION_COOKIE, path=f"/api/s/{ctx.tenant.slug}/owner")
    response.headers["Clear-Site-Data"] = '"cache"'


@router.get("/me")
def me(response: Response, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    _no_store(response)
    with database.read_session() as db:
        user = db.get(User, ctx.user_id)
    with database.read_session(ctx.tenant.id) as db:
        sub = subscription.overview(db, ctx.tenant)
    return {"email": user.email, "csrf_token": ctx.csrf, "tenant": {"slug": ctx.tenant.slug, "status": ctx.tenant.status}, "subscription": sub}


# ------------------------------------------------------------------ schedule
@router.get("/schedule")
def schedule(
    response: Response,
    from_date: date | None = Query(default=None, alias="from"),
    days: int = Query(default=7, ge=1, le=31),
    ctx: OwnerCtx = Depends(owner_dep),
) -> dict:
    _no_store(response)
    with database.read_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        tz = tz_of(settings.timezone)
        first = from_date or local_date(now_min(), tz)
        lo, _ = day_bounds(first, tz)
        hi, _ = day_bounds(first + timedelta(days=days), tz)
        bookings = db.scalars(select(Booking).where(Booking.start_min < hi, Booking.end_min > lo).order_by(Booking.start_min))
        blocks = db.scalars(select(ResourceOccupancy).where(ResourceOccupancy.kind == "block", ResourceOccupancy.start_min < hi, ResourceOccupancy.end_min > lo))
        return {
            "from": first.isoformat(),
            "days": days,
            "timezone": settings.timezone,
            "resources": [{"id": r.id, "name": r.name} for r in db.scalars(select(Resource).where(Resource.is_active.is_(True)).order_by(Resource.sort, Resource.id))],
            "bookings": [booking_owner_view(db, b) for b in bookings],
            "blocks": [{"id": o.id, "resource_id": o.resource_id, "start_min": o.start_min, "end_min": o.end_min, "note": o.note} for o in blocks],
        }


@router.get("/stats")
def owner_stats(response: Response, period: str = Query(default="today"), ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    _no_store(response)
    if period not in stats.PERIODS:
        raise HTTPException(422, {"code": "bad_period"})
    with database.read_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        tz, now = tz_of(settings.timezone), now_min()
        first, after = stats.period_dates(period, tz, now)
        return {"period": period, "currency": settings.currency, **stats.compute(db, tz, first, after, now)}


@router.get("/slots")
def owner_slots(
    service_id: int = Query(gt=0), from_date: date | None = Query(default=None, alias="from"), days: int = Query(default=7, ge=1, le=31),
    ctx: OwnerCtx = Depends(owner_dep),
) -> dict:
    with database.read_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        svc = db.scalar(select(Service).where(Service.id == service_id))
        if not svc:
            raise HTTPException(404, {"code": "service_not_found"})
        tz = tz_of(settings.timezone)
        first = from_date or local_date(now_min(), tz)
        window = compute_slots(db, settings, svc, first, days, now_min())
        return {"days": {d: [{"start_min": s.start_min, "available": s.available, "resource_ids": list(s.resource_ids)} for s in v] for d, v in window.items()}}


# ------------------------------------------------------------------ bookings
def _settings_and_now(db):
    return db.scalar(select(TenantSettings)), now_min()


@router.post("/bookings", status_code=201)
def owner_create_booking(body: OwnerBookingIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    try:
        with database.write_session(ctx.tenant.id) as db:
            settings, now = _settings_and_now(db)
            subscription.assert_can_book(db, ctx.tenant)
            res = bk.create_booking(
                db, tenant_id=ctx.tenant.id, settings=settings, is_preview=ctx.tenant.is_preview, service_id=body.service_id,
                start_min=body.start_min, name=body.name, phone=body.phone, car=body.car, plate=body.plate, note=body.note,
                source="owner", now_min=now, resource_id=body.resource_id, outside_hours=body.outside_hours,
            )
            return {**booking_owner_view(db, res.booking), "access_token": res.access_token}
    except bk.BookingError as exc:
        raise _error(exc) from exc


def _booking_or_404(db, booking_id: int) -> Booking:
    b = db.get(Booking, booking_id)
    if not b:
        raise HTTPException(404, {"code": "booking_not_found"})
    return b


@router.get("/bookings/{booking_id}")
def owner_get_booking(booking_id: int, response: Response, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    _no_store(response)
    with database.read_session(ctx.tenant.id) as db:
        return booking_owner_view(db, _booking_or_404(db, booking_id))


@router.patch("/bookings/{booking_id}/status")
def owner_status(booking_id: int, body: StatusIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    try:
        with database.write_session(ctx.tenant.id) as db:
            return booking_owner_view(db, bk.set_status(db, booking_id, body.status))
    except bk.BookingError as exc:
        raise _error(exc) from exc


@router.post("/bookings/{booking_id}/reschedule")
def owner_reschedule(booking_id: int, body: RescheduleIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    try:
        with database.write_session(ctx.tenant.id) as db:
            settings, now = _settings_and_now(db)
            b = bk.reschedule_booking(
                db, tenant_id=ctx.tenant.id, settings=settings, is_preview=ctx.tenant.is_preview, booking_id=booking_id,
                new_start_min=body.start_min, now_min=now, resource_id=body.resource_id,
            )
            return booking_owner_view(db, b)
    except bk.BookingError as exc:  # transaction rolled back: the original booking is untouched
        raise _error(exc) from exc


@router.post("/bookings/{booking_id}/cancel")
def owner_cancel(booking_id: int, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    try:
        with database.write_session(ctx.tenant.id) as db:
            settings, now = _settings_and_now(db)
            b = bk.cancel_booking(db, tenant_id=ctx.tenant.id, settings=settings, is_preview=ctx.tenant.is_preview, booking_id=booking_id, by="owner", now_min=now)
            return booking_owner_view(db, b)
    except bk.BookingError as exc:
        raise _error(exc) from exc


@router.post("/bookings/{booking_id}/payments", status_code=201)
def owner_payment(booking_id: int, body: PaymentIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    try:
        with database.write_session(ctx.tenant.id) as db:
            bk.add_payment(db, tenant_id=ctx.tenant.id, booking_id=booking_id, kind=body.kind, amount_minor=body.amount_minor, method=body.method, note=body.note)
            return booking_owner_view(db, _booking_or_404(db, booking_id))
    except bk.BookingError as exc:
        raise _error(exc) from exc


@router.post("/bookings/{booking_id}/access-link")
def owner_access_link(booking_id: int, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    """Issues a fresh client link (the previous one stops working)."""
    token = new_token()
    with database.write_session(ctx.tenant.id) as db:
        _booking_or_404(db, booking_id).access_hash = sha256_hex(token)
    return {"access_token": token}


@router.post("/blocks", status_code=201)
def owner_block(body: BlockIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    try:
        with database.write_session(ctx.tenant.id) as db:
            occ = bk.create_block(db, tenant_id=ctx.tenant.id, resource_id=body.resource_id, start_min=body.start_min, end_min=body.end_min, note=body.note)
            return {"id": occ.id}
    except bk.BookingError as exc:
        raise _error(exc) from exc


@router.delete("/blocks/{block_id}", status_code=204)
def owner_unblock(block_id: int, ctx: OwnerCtx = Depends(owner_dep)) -> None:
    try:
        with database.write_session(ctx.tenant.id) as db:
            bk.remove_block(db, block_id)
    except bk.BookingError as exc:
        raise _error(exc) from exc


# ----------------------------------------------------------------- catalogue
def _profile(db):
    return get_profile(db.scalar(select(TenantSettings.business_type)))


def _offer_rows(db, service_id: int) -> list[dict]:
    rows = db.execute(
        select(ServiceResource.resource_id, ServiceResource.price_minor, ServiceResource.duration_min)
        .join(Resource, Resource.id == ServiceResource.resource_id)
        .where(ServiceResource.service_id == service_id, Resource.is_active.is_(True))
        .order_by(Resource.sort, Resource.id)
    ).all()
    return [{"resource_id": rid, "price_minor": price, "duration_min": dur} for rid, price, dur in rows]


def _service_view(db, s: Service) -> dict:
    offers = _offer_rows(db, s.id)
    return {
        "id": s.id, "name": s.name, "description": s.description, "price_minor": s.price_minor, "duration_min": s.duration_min,
        "buffer_min": s.buffer_min, "keywords": s.keywords or [], "is_active": s.is_active,
        "resource_ids": [o["resource_id"] for o in offers], "offers": offers,
    }


def _resource_view(db, r: Resource) -> dict:
    week = list(db.scalars(select(ResourceHours).where(ResourceHours.resource_id == r.id)))
    by_day = {h.weekday: h for h in week}
    return {
        "id": r.id, "name": r.name, "description": r.description, "photo_url": f"/api/media/{r.photo_path}" if r.photo_path else None, "is_active": r.is_active,
        "has_own_hours": bool(week),
        "hours_edit": [
            {"weekday": d, "is_closed": d not in by_day or by_day[d].is_closed, "open_min": by_day[d].open_min if d in by_day else 540, "close_min": by_day[d].close_min if d in by_day else 1140}
            for d in range(7)
        ],
        "exceptions": [
            {"date": e.date, "is_closed": e.is_closed, "open_min": e.open_min, "close_min": e.close_min, "note": e.note}
            for e in db.scalars(select(ResourceException).where(ResourceException.resource_id == r.id).order_by(ResourceException.date))
        ],
    }


@router.get("/services")
def owner_services(response: Response, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    _no_store(response)
    with database.read_session(ctx.tenant.id) as db:
        resources = db.scalars(select(Resource).order_by(Resource.sort, Resource.id))
        services = db.scalars(select(Service).order_by(Service.sort, Service.id))
        return {
            "profile": _profile(db).public(),
            "services": [_service_view(db, s) for s in services],
            "resources": [_resource_view(db, r) for r in resources],
        }


def _set_service_offers(db, tenant_id: int, service: Service, body: ServiceIn) -> None:
    profile = _profile(db)
    offers = body.offers or [OfferIn(resource_id=rid) for rid in body.resource_ids]
    ids = [o.resource_id for o in offers]
    valid = set(db.scalars(select(Resource.id).where(Resource.id.in_(ids)))) if ids else set()
    if ids and (valid != set(ids) or len(ids) != len(set(ids))):
        raise HTTPException(422, {"code": "unknown_resource"})
    if any(o.price_minor is not None or o.duration_min is not None for o in offers) and not profile.features["per_resource_prices"]:
        raise HTTPException(422, {"code": "feature_disabled"})
    db.execute(delete(ServiceResource).where(ServiceResource.service_id == service.id))
    for o in offers:
        db.add(ServiceResource(tenant_id=tenant_id, service_id=service.id, resource_id=o.resource_id, price_minor=o.price_minor, duration_min=o.duration_min))


@router.post("/services", status_code=201)
def owner_service_create(body: ServiceIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    with database.write_session(ctx.tenant.id) as db:
        sort = (db.scalar(select(func.max(Service.sort))) or 0) + 1
        svc = Service(
            tenant_id=ctx.tenant.id, key=f"own-{secrets.token_hex(4)}", name=body.name, description=body.description, price_minor=body.price_minor,
            duration_min=body.duration_min, buffer_min=body.buffer_min, keywords=body.keywords, is_active=body.is_active, sort=sort, owner_edited=True,
        )
        db.add(svc)
        db.flush()
        if not (body.offers or body.resource_ids):
            body = body.model_copy(update={"resource_ids": list(db.scalars(select(Resource.id).where(Resource.is_active.is_(True))))})
        _set_service_offers(db, ctx.tenant.id, svc, body)
        db.flush()
        return _service_view(db, svc)


@router.put("/services/{service_id}")
def owner_service_update(service_id: int, body: ServiceIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    """Edits only affect future bookings: existing ones keep their snapshot of price and duration."""
    with database.write_session(ctx.tenant.id) as db:
        svc = db.get(Service, service_id)
        if not svc:
            raise HTTPException(404, {"code": "service_not_found"})
        svc.name, svc.description, svc.price_minor = body.name, body.description, body.price_minor
        svc.duration_min, svc.buffer_min, svc.keywords, svc.is_active = body.duration_min, body.buffer_min, body.keywords, body.is_active
        svc.owner_edited = True
        if body.offers or body.resource_ids:
            _set_service_offers(db, ctx.tenant.id, svc, body)
        db.flush()
        return _service_view(db, svc)


@router.delete("/services/{service_id}", status_code=204)
def owner_service_delete(service_id: int, ctx: OwnerCtx = Depends(owner_dep)) -> None:
    """Hides the service; history is kept."""
    with database.write_session(ctx.tenant.id) as db:
        svc = db.get(Service, service_id)
        if not svc:
            raise HTTPException(404, {"code": "service_not_found"})
        svc.is_active, svc.owner_edited = False, True


@router.post("/resources", status_code=201)
def owner_resource_create(body: ResourceIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    with database.write_session(ctx.tenant.id) as db:
        profile = _profile(db)
        subscription.assert_can_add_resource(db, ctx.tenant)
        active = db.scalar(select(func.count()).select_from(Resource).where(Resource.is_active.is_(True))) or 0
        if profile.max_resources is not None and active >= profile.max_resources:
            raise HTTPException(409, {"code": "resource_limit", "max": profile.max_resources})
        sort = (db.scalar(select(func.max(Resource.sort))) or 0) + 1
        res = Resource(tenant_id=ctx.tenant.id, key=f"own-{secrets.token_hex(4)}", name=body.name, description=body.description, sort=sort, is_active=body.is_active, owner_edited=True)
        db.add(res)
        db.flush()
        if not profile.features["choose_resource"]:  # bays do every service; a new master starts with none and is assigned by the owner
            for svc in db.scalars(select(Service).where(Service.is_active.is_(True))):
                db.add(ServiceResource(tenant_id=ctx.tenant.id, service_id=svc.id, resource_id=res.id))
        return _resource_view(db, res)


def _resource_or_404(db, resource_id: int) -> Resource:
    res = db.get(Resource, resource_id)
    if not res:
        raise HTTPException(404, {"code": "resource_not_found"})
    return res


@router.put("/resources/{resource_id}")
def owner_resource_update(resource_id: int, body: ResourceIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    with database.write_session(ctx.tenant.id) as db:
        res = _resource_or_404(db, resource_id)
        res.name, res.description, res.is_active, res.owner_edited = body.name, body.description, body.is_active, True
        return _resource_view(db, res)


@router.post("/resources/{resource_id}/photo")
async def owner_resource_photo(resource_id: int, file: UploadFile = File(...), ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    rel = await _read_image(file, "photo", ctx.tenant.slug)
    with database.write_session(ctx.tenant.id) as db:
        res = _resource_or_404(db, resource_id)
        res.photo_path, res.owner_edited = rel, True
        return _resource_view(db, res)


@router.put("/resources/{resource_id}/schedule")
def owner_resource_schedule(resource_id: int, body: ResourceScheduleIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    """A master's own weekly hours and days off. Only for profiles with per-resource hours."""
    with database.write_session(ctx.tenant.id) as db:
        if not _profile(db).features["per_resource_hours"]:
            raise HTTPException(403, {"code": "feature_disabled"})
        res = _resource_or_404(db, resource_id)
        db.execute(delete(ResourceHours).where(ResourceHours.resource_id == res.id))
        db.execute(delete(ResourceException).where(ResourceException.resource_id == res.id))
        if not body.use_studio_hours:
            if len({d.weekday for d in body.days}) != len(body.days):
                raise HTTPException(422, {"code": "weekdays_must_be_unique"})
            for d in body.days:
                if not d.is_closed and d.close_min <= d.open_min:
                    raise HTTPException(422, {"code": "close_before_open"})
                db.add(ResourceHours(tenant_id=ctx.tenant.id, resource_id=res.id, weekday=d.weekday, is_closed=d.is_closed, open_min=d.open_min, close_min=d.close_min))
            # a weekday missing from `days` means "does not work that day"
            for wd in set(range(7)) - {d.weekday for d in body.days}:
                db.add(ResourceHours(tenant_id=ctx.tenant.id, resource_id=res.id, weekday=wd, is_closed=True, open_min=540, close_min=1140))
        for e in body.exceptions:
            try:
                date.fromisoformat(e.date)
            except ValueError:
                raise HTTPException(422, {"code": "bad_date"}) from None
            if not e.is_closed and not (e.open_min is not None and e.close_min is not None and e.close_min > e.open_min):
                raise HTTPException(422, {"code": "bad_exception_hours"})
            db.add(ResourceException(tenant_id=ctx.tenant.id, resource_id=res.id, date=e.date, is_closed=e.is_closed, open_min=e.open_min, close_min=e.close_min, note=e.note))
        res.owner_edited = True
        db.flush()
        return _resource_view(db, res)


# ------------------------------------------------------------------- studio
def _mark_edited(settings: TenantSettings, *fields: str) -> None:
    settings.owner_edited = sorted({*(settings.owner_edited or []), *fields})


@router.get("/settings")
def owner_settings(response: Response, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    _no_store(response)
    with database.read_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        pub = public_tenant(db, ctx.tenant, settings)
        wh = {h.weekday: h for h in db.scalars(select(WorkingHours))}
        pub["hours_edit"] = [
            {"weekday": d, "is_closed": d not in wh or wh[d].is_closed, "open_min": wh[d].open_min if d in wh else 540, "close_min": wh[d].close_min if d in wh else 1140}
            for d in range(7)
        ]
        pub["exceptions"] = exceptions_view(db)
        return pub


@router.patch("/settings")
def owner_settings_patch(body: SettingsPatch, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    with database.write_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        for field, value in changes.items():
            setattr(settings, field, value)
        _mark_edited(settings, *changes.keys())
        db.flush()
        return public_tenant(db, ctx.tenant, settings)


@router.put("/hours")
def owner_hours(body: HoursIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    for d in body.days:
        if not d.is_closed and d.close_min <= d.open_min:
            raise HTTPException(422, {"code": "close_before_open"})
    if len({d.weekday for d in body.days}) != 7:
        raise HTTPException(422, {"code": "weekdays_must_be_unique"})
    with database.write_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        db.execute(delete(WorkingHours))
        for d in body.days:
            db.add(WorkingHours(tenant_id=ctx.tenant.id, weekday=d.weekday, is_closed=d.is_closed, open_min=d.open_min, close_min=d.close_min))
        db.execute(delete(ScheduleException))
        for e in body.exceptions:
            if not e.is_closed and not (e.open_min is not None and e.close_min is not None and e.close_min > e.open_min):
                raise HTTPException(422, {"code": "bad_exception_hours"})
            try:
                date.fromisoformat(e.date)
            except ValueError:
                raise HTTPException(422, {"code": "bad_date"}) from None
            db.add(ScheduleException(tenant_id=ctx.tenant.id, date=e.date, is_closed=e.is_closed, open_min=e.open_min, close_min=e.close_min, note=e.note))
        _mark_edited(settings, "hours")
        db.flush()
        return {"hours": [d.model_dump() for d in body.days], "exceptions": exceptions_view(db)}


async def _read_image(file: UploadFile, kind: str, slug: str) -> str:
    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    try:
        return media.store_upload(slug, data, kind=kind)
    except media.ImageError as exc:
        raise HTTPException(422, {"code": str(exc)}) from exc


@router.post("/logo")
async def owner_logo(file: UploadFile = File(...), ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    rel = await _read_image(file, "logo", ctx.tenant.slug)
    with database.write_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        settings.logo_path = rel
        _mark_edited(settings, "logo")
        snapshot = (settings.name, settings.accent)
    media.build_pwa_assets(ctx.tenant.slug, snapshot[0], snapshot[1], rel)  # install icon follows the logo
    return {"logo_url": f"/api/media/{rel}"}


@router.post("/hero")
async def owner_hero(file: UploadFile = File(...), ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    rel = await _read_image(file, "hero", ctx.tenant.slug)
    with database.write_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        settings.hero_path = rel
        _mark_edited(settings, "hero")
    return {"hero_url": f"/api/media/{rel}"}


# ------------------------------------------------------------------- gallery
def _photo_or_404(db, photo_id: int) -> GalleryPhoto:
    p = db.get(GalleryPhoto, photo_id)
    if not p:
        raise HTTPException(404, {"code": "photo_not_found"})
    return p


@router.post("/gallery", status_code=201)
async def gallery_add(file: UploadFile = File(...), caption: str = Form(default="", max_length=160), ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    """Action 1: add a new card. Existing photos stay where they are."""
    rel = await _read_image(file, "photo", ctx.tenant.slug)
    with database.write_session(ctx.tenant.id) as db:
        sort = (db.scalar(select(func.max(GalleryPhoto.sort))) or 0) + 1
        photo = GalleryPhoto(tenant_id=ctx.tenant.id, path=rel, caption=caption.strip(), sort=sort, source="owner")
        db.add(photo)
        db.flush()
        return {"id": photo.id, "url": f"/api/media/{rel}", "caption": photo.caption}


@router.put("/gallery/{photo_id}/photo")
async def gallery_replace(photo_id: int, file: UploadFile = File(...), ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    """Action 2: replace one photo only (caption and position are kept)."""
    rel = await _read_image(file, "photo", ctx.tenant.slug)
    with database.write_session(ctx.tenant.id) as db:
        photo = _photo_or_404(db, photo_id)
        photo.path, photo.source = rel, "owner"  # owner-owned now: republishing the config will not overwrite it
        return {"id": photo.id, "url": f"/api/media/{rel}", "caption": photo.caption}


@router.patch("/gallery/{photo_id}")
def gallery_caption(photo_id: int, body: CaptionIn, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    """Action 3: change one caption only."""
    with database.write_session(ctx.tenant.id) as db:
        photo = _photo_or_404(db, photo_id)
        photo.caption, photo.source = body.caption.strip(), "owner"
        return {"id": photo.id, "url": f"/api/media/{photo.path}", "caption": photo.caption}


@router.delete("/gallery/{photo_id}", status_code=204)
def gallery_delete(photo_id: int, ctx: OwnerCtx = Depends(owner_dep)) -> None:
    with database.write_session(ctx.tenant.id) as db:
        db.delete(_photo_or_404(db, photo_id))


# --------------------------------------------------------------- push + helper
@router.post("/push", status_code=204)
def owner_push(body: PushSubscriptionIn, ctx: OwnerCtx = Depends(owner_dep)) -> None:
    if not push.vapid_configured():
        raise HTTPException(503, {"code": "push_not_configured"})
    with database.write_session(ctx.tenant.id) as db:
        existing = db.scalar(select(PushSubscription).where(PushSubscription.audience == "owner", PushSubscription.endpoint == body.endpoint))
        if existing:
            existing.p256dh, existing.auth, existing.disabled_at, existing.user_id = body.keys.p256dh, body.keys.auth, None, ctx.user_id
        else:
            db.add(PushSubscription(tenant_id=ctx.tenant.id, audience="owner", user_id=ctx.user_id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth))


@router.delete("/push", status_code=204)
def owner_push_off(endpoint: str = Query(min_length=10), ctx: OwnerCtx = Depends(owner_dep)) -> None:
    with database.write_session(ctx.tenant.id) as db:
        for sub in db.scalars(select(PushSubscription).where(PushSubscription.audience == "owner", PushSubscription.endpoint == endpoint)):
            db.delete(sub)


@router.post("/assistant")
def owner_assistant(body: AssistantIn, response: Response, ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    _no_store(response)
    with database.read_session(ctx.tenant.id) as db:
        settings = db.scalar(select(TenantSettings))
        reads = assistant.OwnerReads(db, settings, now_min())
        return assistant.answer("owner", body.text, body.context, reads, [h.model_dump() for h in body.history]).as_dict()


@router.get("/assistant/examples")
def owner_examples(ctx: OwnerCtx = Depends(owner_dep)) -> dict:
    return {"examples": assistant.OWNER_EXAMPLES}
