"""Serializers. Public views never contain client data or payments."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Booking, Client, GalleryPhoto, Resource, ScheduleException, Service, TenantSettings, WorkingHours
from .services import booking as bk
from .services import media
from .config import get_settings
from .plans import get_plan
from .profiles import get_profile
from .security import calendar_sig
from .services import subscription
from .services.slots import offers_for


def media_url(rel: str | None) -> str | None:
    return f"/api/media/{rel}" if rel else None


def hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def public_tenant(db: Session, tenant, s: TenantSettings) -> dict:
    """tenant: a TenantCtx (slug, status and subscription fields)."""
    slug, status = tenant.slug, tenant.status
    plan = get_plan(tenant.plan)
    services = db.scalars(select(Service).where(Service.is_active.is_(True)).order_by(Service.sort, Service.id))
    hours = {h.weekday: h for h in db.scalars(select(WorkingHours))}
    profile = get_profile(s.business_type)
    choose = profile.features["choose_resource"]
    service_views = []
    for v in services:
        offers = offers_for(db, v)
        prices = [o.price_minor for o in offers] or [v.price_minor]
        durations = [o.duration_min for o in offers] or [v.duration_min]
        item = {
            "id": v.id,
            "name": v.name,
            "description": v.description,
            "price_minor": min(prices),
            "price_varies": min(prices) != max(prices),
            "duration_min": min(durations),
            "duration_varies": min(durations) != max(durations),
            "bookable": bool(offers),
        }
        if choose:  # customers pick the master: they may see who does what and for how much
            item["offers"] = [{"resource_id": o.resource.id, "price_minor": o.price_minor, "duration_min": o.duration_min} for o in offers]
        service_views.append(item)
    resources = list(db.scalars(select(Resource).where(Resource.is_active.is_(True)).order_by(Resource.sort, Resource.id)))
    return {
        "slug": slug,
        "status": status,
        "is_preview": status == "preview",
        "booking_enabled": subscription.booking_enabled(tenant),
        "subscription_state": subscription.state_of(tenant),
        "branding": {"show": not plan.remove_branding, "name": get_settings().platform_name, "url": get_settings().platform_url},
        "resources_count": len(resources),
        "business_type": profile.type,
        "profile": profile.public(),
        "resources": [{"id": r.id, "name": r.name, "description": r.description, "photo_url": media_url(r.photo_path)} for r in resources]
        if profile.features["resource_profiles"]
        else [],
        "name": s.name,
        "tagline": s.tagline,
        "description": s.description,
        "phone": s.phone,
        "address": s.address,
        "map_url": s.map_url,
        "timezone": s.timezone,
        "currency": s.currency,
        "accent": s.accent,
        "logo_url": media_url(s.logo_path),
        "hero_url": media_url(s.hero_path),
        "info_cards": s.info_cards or [],
        "rules": {
            "cancel_before_hours": s.cancel_before_hours,
            "lead_time_min": s.lead_time_min,
            "max_advance_days": s.max_advance_days,
            "slot_step_min": s.slot_step_min,
            "reminder_hours": s.reminder_hours,
        },
        "hours": [
            {
                "weekday": d,
                "closed": d not in hours or hours[d].is_closed,
                "open": hhmm(hours[d].open_min) if d in hours else None,
                "close": hhmm(hours[d].close_min) if d in hours else None,
            }
            for d in range(7)
        ],
        "services": service_views,
        "gallery": [
            {"id": g.id, "url": media_url(g.path), "caption": g.caption}
            for g in db.scalars(select(GalleryPhoto).order_by(GalleryPhoto.sort, GalleryPhoto.id))
        ],
        "pwa": {
            "icon192": media_url(f"{slug}/pwa/icon-192.png"),
            "icon512": media_url(f"{slug}/pwa/icon-512.png"),
            "maskable512": media_url(f"{slug}/pwa/maskable-512.png"),
            "apple_touch": media_url(f"{slug}/pwa/apple-touch-icon.png"),
            "startup": [
                {"url": media_url(f"{slug}/pwa/splash-{w}x{h}.png"), "dw": dw, "dh": dh, "ratio": ratio}
                for (w, h, dw, dh, ratio) in media.SPLASH_SIZES
            ],
        },
    }


def booking_client_view(db: Session, b: Booking, s: TenantSettings, now_min: int) -> dict:
    """What a client sees through their access token: their own booking only."""
    res = db.get(Resource, b.resource_id)
    deadline = b.start_min - s.cancel_before_hours * 60
    return {
        "id": b.id,
        "status": b.status,
        "service_name": b.service_name,
        "price_minor": b.price_minor,
        "start_min": b.start_min,
        "end_min": b.end_min,
        "car": b.car,
        "plate": b.plate,
        "post_name": res.name if res else "",
        "can_cancel": b.status == "booked" and now_min <= deadline,
        "cancel_deadline_min": deadline,
        "cancel_before_hours": s.cancel_before_hours,
        "calendar_sig": calendar_sig(b.tenant_id, b.id),
    }


def booking_owner_view(db: Session, b: Booking) -> dict:
    client = db.get(Client, b.client_id)
    res = db.get(Resource, b.resource_id)
    return {
        "id": b.id,
        "status": b.status,
        "service_id": b.service_id,
        "service_name": b.service_name,
        "price_minor": b.price_minor,
        "start_min": b.start_min,
        "end_min": b.end_min,
        "buffer_min": b.buffer_min,
        "resource_id": b.resource_id,
        "post_name": res.name if res else "",
        "client_name": client.name if client else "",
        "client_phone": client.phone_norm if client else "",
        "car": b.car,
        "plate": b.plate,
        "note": b.note,
        "source": b.source,
        "is_demo": b.is_demo,
        "cancelled_by": b.cancelled_by,
        **bk.balance(db, b),
    }


def exceptions_view(db: Session) -> list[dict]:
    return [
        {"date": e.date, "is_closed": e.is_closed, "open_min": e.open_min, "close_min": e.close_min, "note": e.note}
        for e in db.scalars(select(ScheduleException).order_by(ScheduleException.date))
    ]
