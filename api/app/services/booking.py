"""Booking, reschedule, cancel, blocks and payments.

Every mutation runs inside one BEGIN IMMEDIATE transaction (db.write_session). The
overlap check reads occupancy cells; the PRIMARY KEY (resource_id, cell) on
occupancy_cells is the database-level backstop if that check is ever bypassed.
Raising any BookingError aborts the whole transaction, so a failed move leaves the
original booking untouched."""
import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    ACTIVE_STATUSES,
    Booking,
    Client,
    IdempotencyKey,
    OccupancyCell,
    Payment,
    Resource,
    ResourceOccupancy,
    Service,
    TenantSettings,
    now_s,
)
from ..security import derived_access_token, new_token, normalize_phone, sha256_hex
from ..timeutil import cells_for
from . import outbox
from .slots import offers_for, occupancy_span, resources_open_at, service_resources, validate_start


class BookingError(Exception):
    def __init__(self, code: str, status: int = 409, detail: dict | None = None):
        super().__init__(code)
        self.code, self.status, self.detail = code, status, detail or {}


@dataclass
class BookingResult:
    booking: Booking
    created: bool
    access_token: str  # only its sha256 is stored; re-derived from the idempotency key on retry


# ---------------------------------------------------------------- occupancy core
def _cells_taken(db: Session, resource_id: int, start: int, end: int, ignore_occupancy: int | None = None) -> int:
    rng = cells_for(start, end)
    q = select(func.count()).select_from(OccupancyCell).where(
        OccupancyCell.resource_id == resource_id, OccupancyCell.cell >= rng.start, OccupancyCell.cell < rng.stop
    )
    if ignore_occupancy is not None:
        q = q.where(OccupancyCell.occupancy_id != ignore_occupancy)
    return db.scalar(q) or 0


def _insert_cells(db: Session, tenant_id: int, occ: ResourceOccupancy) -> None:
    rows = [
        {"resource_id": occ.resource_id, "cell": c, "tenant_id": tenant_id, "occupancy_id": occ.id}
        for c in cells_for(occ.start_min, occ.end_min)
    ]
    try:
        db.execute(insert(OccupancyCell), rows)
    except IntegrityError as exc:  # the DB-level guard fired
        raise BookingError("slot_unavailable") from exc


def _claim(
    db: Session, tenant_id: int, resource_id: int, start: int, end: int, kind: str, booking_id: int | None, note: str = ""
) -> ResourceOccupancy:
    if _cells_taken(db, resource_id, start, end):
        raise BookingError("slot_unavailable")
    occ = ResourceOccupancy(
        tenant_id=tenant_id, resource_id=resource_id, kind=kind, booking_id=booking_id, start_min=start, end_min=end, note=note
    )
    db.add(occ)
    db.flush()
    _insert_cells(db, tenant_id, occ)
    return occ


def _occupancy_of(db: Session, booking_id: int) -> ResourceOccupancy | None:
    return db.scalar(select(ResourceOccupancy).where(ResourceOccupancy.booking_id == booking_id))


def _release(db: Session, occ: ResourceOccupancy | None) -> None:
    if occ is not None:  # FK ON DELETE CASCADE removes the cells
        db.execute(delete(ResourceOccupancy).where(ResourceOccupancy.id == occ.id))
        db.expire_all()


# -------------------------------------------------------------------- create
def _request_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _upsert_client(db: Session, tenant_id: int, name: str, phone: str) -> Client:
    phone_norm = normalize_phone(phone)
    client = db.scalar(select(Client).where(Client.phone_norm == phone_norm))
    if client:
        client.name = name
        return client
    client = Client(tenant_id=tenant_id, name=name, phone_norm=phone_norm)
    db.add(client)
    db.flush()
    return client


def create_booking(
    db: Session,
    *,
    tenant_id: int,
    settings: TenantSettings,
    is_preview: bool,
    service_id: int,
    start_min: int,
    name: str,
    phone: str,
    car: str = "",
    plate: str = "",
    note: str = "",
    source: str = "client",
    now_min: int,
    idempotency_key: str | None = None,
    resource_id: int | None = None,
    outside_hours: bool = False,
) -> BookingResult:
    """The client never supplies price, duration or tenant: they come from the service row."""
    scope = f"booking:{source}"
    fingerprint = _request_hash(
        {"s": service_id, "t": start_min, "n": name, "p": normalize_phone(phone), "c": car, "pl": plate, "r": resource_id}
    )
    if idempotency_key:
        prior = db.scalar(select(IdempotencyKey).where(IdempotencyKey.scope == scope, IdempotencyKey.key == idempotency_key))
        if prior:
            if prior.request_hash != fingerprint or prior.booking_id is None:
                raise BookingError("idempotency_key_reused", 422)
            return BookingResult(db.get(Booking, prior.booking_id), False, derived_access_token(tenant_id, prior.booking_id, idempotency_key))

    service = db.scalar(select(Service).where(Service.id == service_id, Service.is_active.is_(True)))
    if not service:
        raise BookingError("service_not_found", 404)
    reason = validate_start(db, settings, start_min, now_min, outside_hours=outside_hours)
    if reason:
        raise BookingError(reason, 422)

    offers = offers_for(db, service)
    if resource_id is not None:
        offers = [o for o in offers if o.resource.id == resource_id]
        if not offers:
            raise BookingError("resource_not_suitable", 422)
    if not outside_hours:  # each resource has its own working hours
        open_ids = set(resources_open_at(db, settings, [o.resource.id for o in offers], start_min))
        offers = [o for o in offers if o.resource.id in open_ids]
        if not offers:
            raise BookingError("outside_working_hours", 422)
    chosen = next((o for o in offers if not _cells_taken(db, o.resource.id, start_min, start_min + o.span)), None)
    if chosen is None:
        raise BookingError("slot_unavailable")
    span = chosen.span

    client = _upsert_client(db, tenant_id, name.strip(), phone)
    booking = Booking(
        tenant_id=tenant_id,
        service_id=service.id,
        resource_id=chosen.resource.id,
        client_id=client.id,
        start_min=start_min,
        end_min=start_min + chosen.duration_min,
        buffer_min=chosen.buffer_min,
        status="booked",
        service_name=service.name,
        price_minor=chosen.price_minor,  # this resource's price: a senior master costs more
        car=car.strip(),
        plate=plate.strip().upper(),
        note=note.strip(),
        source=source,
        access_hash=sha256_hex(f"pending:{new_token()}"),
        is_demo=is_preview,
    )
    db.add(booking)
    db.flush()
    token = derived_access_token(tenant_id, booking.id, idempotency_key) if idempotency_key else new_token()
    booking.access_hash = sha256_hex(token)
    _claim(db, tenant_id, chosen.resource.id, start_min, start_min + span, "booking", booking.id)

    if idempotency_key:
        db.add(IdempotencyKey(tenant_id=tenant_id, scope=scope, key=idempotency_key, request_hash=fingerprint, booking_id=booking.id))
    if not is_preview:
        _schedule_notifications(db, tenant_id, settings, booking, notify_owner=(source == "client"))
    return BookingResult(booking, True, token)


def _schedule_notifications(
    db: Session, tenant_id: int, settings: TenantSettings, booking: Booking, *, notify_owner: bool
) -> None:
    if notify_owner:
        outbox.enqueue(db, tenant_id, booking_id=booking.id, audience="owner", kind="new", dedupe_key=f"new:{booking.id}")
    remind_at = booking.start_min * 60 - settings.reminder_hours * 3600
    if remind_at > now_s():
        outbox.enqueue(
            db,
            tenant_id,
            booking_id=booking.id,
            audience="client",
            kind="reminder",
            dedupe_key=f"reminder:{booking.id}:{booking.start_min}",
            run_at=remind_at,
            payload={"start_min": booking.start_min},
        )


# ------------------------------------------------------------------ reschedule
def reschedule_booking(
    db: Session,
    *,
    tenant_id: int,
    settings: TenantSettings,
    is_preview: bool,
    booking_id: int,
    new_start_min: int,
    now_min: int,
    resource_id: int | None = None,
    outside_hours: bool = True,
) -> Booking:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    if not booking:
        raise BookingError("booking_not_found", 404)
    if booking.status not in ACTIVE_STATUSES:
        raise BookingError("booking_not_active", 409)
    reason = validate_start(db, settings, new_start_min, now_min, outside_hours=outside_hours)
    if reason:
        raise BookingError(reason, 422)

    occ = _occupancy_of(db, booking_id)
    span = (occ.end_min - occ.start_min) if occ else booking.end_min - booking.start_min + booking.buffer_min
    service = db.get(Service, booking.service_id)
    candidates = service_resources(db, booking.service_id) if service else []
    current = db.get(Resource, booking.resource_id)
    if current and current.id not in {r.id for r in candidates}:
        candidates.insert(0, current)
    if resource_id is not None:
        candidates = [r for r in candidates if r.id == resource_id]
        if not candidates:
            raise BookingError("resource_not_suitable", 422)
    else:  # prefer staying on the current resource
        candidates.sort(key=lambda r: r.id != booking.resource_id)

    own = occ.id if occ else None
    target = next((r for r in candidates if not _cells_taken(db, r.id, new_start_min, new_start_min + span, own)), None)
    if target is None:
        raise BookingError("slot_unavailable")

    duration = booking.end_min - booking.start_min
    _release(db, occ)
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    _claim(db, tenant_id, target.id, new_start_min, new_start_min + span, "booking", booking.id)
    booking.resource_id = target.id
    booking.start_min = new_start_min
    booking.end_min = new_start_min + duration
    if not is_preview:
        outbox.skip_pending(db, booking.id, ("reminder",))
        _schedule_notifications(db, tenant_id, settings, booking, notify_owner=False)
        outbox.enqueue(
            db, tenant_id, booking_id=booking.id, audience="client", kind="moved", dedupe_key=f"moved:{booking.id}:{new_start_min}"
        )
    return booking


# --------------------------------------------------------------------- cancel
def cancel_booking(
    db: Session,
    *,
    tenant_id: int,
    settings: TenantSettings,
    is_preview: bool,
    booking_id: int,
    by: str,
    now_min: int,
) -> Booking:
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    if not booking:
        raise BookingError("booking_not_found", 404)
    if booking.status == "cancelled":
        return booking  # idempotent
    if by == "client":
        if booking.status != "booked":
            raise BookingError("cancel_not_allowed", 403)
        if booking.start_min - now_min < settings.cancel_before_hours * 60:
            raise BookingError("cancel_window_closed", 403, {"hours": settings.cancel_before_hours})
    _release(db, _occupancy_of(db, booking_id))
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    booking.status = "cancelled"
    booking.cancelled_at = now_s()
    booking.cancelled_by = by
    if not is_preview:
        outbox.skip_pending(db, booking.id, ("reminder", "moved"))
        outbox.enqueue(
            db,
            tenant_id,
            booking_id=booking.id,
            audience="owner" if by == "client" else "client",
            kind="cancelled",
            dedupe_key=f"cancelled:{booking.id}",
        )
    return booking


def set_status(db: Session, booking_id: int, status: str) -> Booking:
    if status not in ACTIVE_STATUSES:
        raise BookingError("invalid_status", 422)
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    if not booking:
        raise BookingError("booking_not_found", 404)
    if booking.status == "cancelled":
        raise BookingError("booking_not_active", 409)
    booking.status = status
    return booking


# --------------------------------------------------------------------- blocks
def create_block(db: Session, *, tenant_id: int, resource_id: int, start_min: int, end_min: int, note: str) -> ResourceOccupancy:
    if end_min <= start_min:
        raise BookingError("invalid_range", 422)
    if not db.scalar(select(Resource.id).where(Resource.id == resource_id)):
        raise BookingError("resource_not_found", 404)
    blockers = list(
        db.scalars(
            select(ResourceOccupancy.id).where(
                ResourceOccupancy.resource_id == resource_id, ResourceOccupancy.start_min < end_min, ResourceOccupancy.end_min > start_min
            )
        )
    )
    if blockers:
        raise BookingError("slot_unavailable", 409, {"conflicts": blockers})
    return _claim(db, tenant_id, resource_id, start_min, end_min, "block", None, note)


def remove_block(db: Session, occupancy_id: int) -> None:
    occ = db.scalar(select(ResourceOccupancy).where(ResourceOccupancy.id == occupancy_id, ResourceOccupancy.kind == "block"))
    if not occ:
        raise BookingError("block_not_found", 404)
    _release(db, occ)


# ------------------------------------------------------------------- payments
def balance(db: Session, booking: Booking) -> dict:
    rows = dict(
        db.execute(select(Payment.kind, func.coalesce(func.sum(Payment.amount_minor), 0)).where(Payment.booking_id == booking.id).group_by(Payment.kind)).all()
    )
    paid, refunded = int(rows.get("payment", 0)), int(rows.get("refund", 0))
    return {"paid_minor": paid, "refunded_minor": refunded, "net_minor": paid - refunded, "due_minor": max(booking.price_minor - (paid - refunded), 0)}


def add_payment(db: Session, *, tenant_id: int, booking_id: int, kind: str, amount_minor: int, method: str, note: str) -> Payment:
    if amount_minor <= 0 or kind not in ("payment", "refund"):
        raise BookingError("invalid_amount", 422)
    booking = db.scalar(select(Booking).where(Booking.id == booking_id))
    if not booking:
        raise BookingError("booking_not_found", 404)
    bal = balance(db, booking)
    if kind == "payment" and booking.status == "cancelled":
        raise BookingError("booking_not_active", 409)
    if kind == "refund" and amount_minor > bal["net_minor"]:
        raise BookingError("refund_exceeds_paid", 422, {"max_minor": bal["net_minor"]})
    payment = Payment(tenant_id=tenant_id, booking_id=booking_id, kind=kind, amount_minor=amount_minor, method=method, note=note)
    db.add(payment)
    db.flush()
    return payment
