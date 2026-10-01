"""Availability. A service occupies one suitable resource for a continuous range
[start, start + duration + buffer), possibly across several days. Working hours
only decide at which moments a car/client can be accepted.

Hours are resolved per resource (a master may work Thu-Sat only):
  1. the resource's own exception for that date (vacation, extra shift);
  2. else the studio's exception for that date (holiday closes everyone, special hours apply to all);
  3. else the resource's own weekly hours, if it has any;
  4. else the studio's weekly hours.
A resource's price and duration for a service may differ from the service's own (ServiceResource)."""
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CELL_MINUTES,
    Resource,
    ResourceException,
    ResourceHours,
    ResourceOccupancy,
    ScheduleException,
    Service,
    ServiceResource,
    TenantSettings,
    WorkingHours,
)
from ..timeutil import ceil_cells, day_bounds, local_date, local_to_min, tz_of


@dataclass(frozen=True)
class Slot:
    start_min: int
    available: bool
    resource_ids: tuple[int, ...]


@dataclass(frozen=True)
class Offer:
    """What one resource charges and how long it takes for one service."""

    resource: Resource
    price_minor: int
    duration_min: int
    buffer_min: int

    @property
    def span(self) -> int:
        return ceil_cells(self.duration_min + self.buffer_min)


def offers_for(db: Session, service: Service) -> list[Offer]:
    rows = db.execute(
        select(Resource, ServiceResource.price_minor, ServiceResource.duration_min)
        .join(ServiceResource, ServiceResource.resource_id == Resource.id)
        .where(ServiceResource.service_id == service.id, Resource.is_active.is_(True))
        .order_by(Resource.sort, Resource.id)
    ).all()
    return [
        Offer(r, price if price is not None else service.price_minor, dur if dur is not None else service.duration_min, service.buffer_min)
        for r, price, dur in rows
    ]


def occupancy_span(service: Service) -> int:
    return ceil_cells(service.duration_min + service.buffer_min)


def service_resources(db: Session, service_id: int) -> list[Resource]:
    return list(
        db.scalars(
            select(Resource)
            .join(ServiceResource, ServiceResource.resource_id == Resource.id)
            .where(ServiceResource.service_id == service_id, Resource.is_active.is_(True))
            .order_by(Resource.sort, Resource.id)
        )
    )


class Hours:
    """Loads every schedule row once; answers 'when does resource R accept cars on date D'."""

    def __init__(self, db: Session):
        self.studio_week = {h.weekday: h for h in db.scalars(select(WorkingHours))}
        self.studio_exc = {e.date: e for e in db.scalars(select(ScheduleException))}
        self.res_week: dict[int, dict[int, ResourceHours]] = {}
        for h in db.scalars(select(ResourceHours)):
            self.res_week.setdefault(h.resource_id, {})[h.weekday] = h
        self.res_exc: dict[tuple[int, str], ResourceException] = {(e.resource_id, e.date): e for e in db.scalars(select(ResourceException))}

    def window(self, d: date, resource_id: int | None = None) -> tuple[int, int] | None:
        """(open_min, close_min) in local minutes, or None when closed."""
        if resource_id is not None:
            exc = self.res_exc.get((resource_id, d.isoformat()))
            if exc:
                return None if exc.is_closed or exc.open_min is None or exc.close_min is None else (exc.open_min, exc.close_min)
        studio_exc = self.studio_exc.get(d.isoformat())
        if studio_exc:
            if studio_exc.is_closed or studio_exc.open_min is None or studio_exc.close_min is None:
                return None
            return studio_exc.open_min, studio_exc.close_min
        own = self.res_week.get(resource_id) if resource_id is not None else None
        row = own.get(d.weekday()) if own else self.studio_week.get(d.weekday())
        if own and row is None:
            return None  # the resource has its own week and this weekday is not in it
        if not row or row.is_closed:
            return None
        return row.open_min, row.close_min


def _moments(win: tuple[int, int] | None, d: date, settings: TenantSettings) -> list[int]:
    if not win:
        return []
    tz = tz_of(settings.timezone)
    out, t = [], win[0]
    while t < win[1]:
        out.append(local_to_min(d, t, tz))
        t += settings.slot_step_min
    return out


def day_window(db: Session, d: date) -> tuple[int, int] | None:
    return Hours(db).window(d)


def day_start_moments(db: Session, settings: TenantSettings, d: date, resource_id: int | None = None, hours: Hours | None = None) -> list[int]:
    return _moments((hours or Hours(db)).window(d, resource_id), d, settings)


def _busy(db: Session, resource_ids: list[int], lo: int, hi: int) -> dict[int, list[tuple[int, int]]]:
    busy: dict[int, list[tuple[int, int]]] = {rid: [] for rid in resource_ids}
    if not resource_ids:
        return busy
    rows = db.execute(
        select(ResourceOccupancy.resource_id, ResourceOccupancy.start_min, ResourceOccupancy.end_min).where(
            ResourceOccupancy.resource_id.in_(resource_ids),
            ResourceOccupancy.end_min > lo,
            ResourceOccupancy.start_min < hi,
        )
    )
    for rid, s, e in rows:
        busy[rid].append((s, e))
    return busy


def _is_free(intervals: list[tuple[int, int]], start: int, end: int) -> bool:
    return all(not (s < end and e > start) for s, e in intervals)


def compute_slots(
    db: Session,
    settings: TenantSettings,
    service: Service,
    first_day: date,
    days: int,
    now_min: int,
    offers: list[Offer] | None = None,
    only_resource_id: int | None = None,
) -> dict[str, list[Slot]]:
    """Every start moment of the days (union over the resources that work then), occupied ones marked."""
    tz = tz_of(settings.timezone)
    offers = offers if offers is not None else offers_for(db, service)
    if only_resource_id is not None:
        offers = [o for o in offers if o.resource.id == only_resource_id]
    hours = Hours(db)
    max_span = max((o.span for o in offers), default=0)
    lo, _ = day_bounds(first_day, tz)
    _, hi = day_bounds(first_day + timedelta(days=days - 1), tz)
    busy = _busy(db, [o.resource.id for o in offers], lo, hi + max_span)
    earliest = now_min + settings.lead_time_min
    last_day = local_date(now_min, tz) + timedelta(days=settings.max_advance_days)
    out: dict[str, list[Slot]] = {}
    for i in range(days):
        d = first_day + timedelta(days=i)
        starts: dict[int, list[int]] = {}  # start -> resources that accept a car at that moment
        for o in offers:
            for m in _moments(hours.window(d, o.resource.id), d, settings):
                starts.setdefault(m, []).append(o.resource.id)
        by_id = {o.resource.id: o for o in offers}
        slots: list[Slot] = []
        for start in sorted(starts):
            free = tuple(r for r in starts[start] if _is_free(busy[r], start, start + by_id[r].span))
            ok = bool(free) and start >= earliest and d <= last_day
            slots.append(Slot(start, ok, free if ok else ()))
        out[d.isoformat()] = slots
    return out


def next_available(
    db: Session, settings: TenantSettings, service: Service, now_min: int, horizon_days: int | None = None, only_resource_id: int | None = None
) -> Slot | None:
    tz = tz_of(settings.timezone)
    horizon = horizon_days or settings.max_advance_days
    today = local_date(now_min, tz)
    offers = offers_for(db, service)
    chunk = 14
    for offset in range(0, horizon + 1, chunk):
        window = compute_slots(db, settings, service, today + timedelta(days=offset), min(chunk, horizon + 1 - offset), now_min, offers, only_resource_id)
        for day in sorted(window):
            for slot in window[day]:
                if slot.available:
                    return slot
    return None


def resources_open_at(db: Session, settings: TenantSettings, resource_ids: list[int], start_min: int, hours: Hours | None = None) -> list[int]:
    """Which of these resources accept a car/client at exactly this start moment."""
    tz = tz_of(settings.timezone)
    d = local_date(start_min, tz)
    hours = hours or Hours(db)
    return [r for r in resource_ids if start_min in _moments(hours.window(d, r), d, settings)]


def validate_start(
    db: Session, settings: TenantSettings, start_min: int, now_min: int, *, outside_hours: bool = False
) -> str | None:
    """Reason a start is unacceptable regardless of resource, or None. Owners may pass outside_hours.
    Whether a particular resource works at that moment is checked with resources_open_at."""
    tz = tz_of(settings.timezone)
    if start_min % CELL_MINUTES:
        return "time_not_aligned"
    if start_min < now_min and not outside_hours:
        return "in_the_past"
    if outside_hours:
        return None
    if start_min < now_min + settings.lead_time_min:
        return "too_soon"
    d = local_date(start_min, tz)
    if d > local_date(now_min, tz) + timedelta(days=settings.max_advance_days):
        return "too_far"
    all_ids = list(db.scalars(select(Resource.id).where(Resource.is_active.is_(True))))
    if not resources_open_at(db, settings, all_ids, start_min) and start_min not in _moments(Hours(db).window(d), d, settings):
        return "outside_working_hours"
    return None
