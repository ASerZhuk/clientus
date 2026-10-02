"""Schema. Every tenant-dependent table carries tenant_id and composite tenant FKs,
so a row can never point at another tenant's parent row."""
import time

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

CELL_MINUTES = 15  # occupancy grid; UNIQUE(resource_id, cell) is the DB-level overlap guard

BOOKING_STATUSES = ("booked", "accepted", "ready", "cancelled")
ACTIVE_STATUSES = ("booked", "accepted", "ready")


def now_s() -> int:
    return int(time.time())


class Base(DeclarativeBase):
    pass


class TenantScoped:
    """Marker mixin: rows filtered/checked against session.info['tenant_id'] (see tenancy.py)."""

    @declared_attr
    def tenant_id(cls) -> Mapped[int]:
        return mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True)
    status: Mapped[str] = mapped_column(String(12), default="preview")  # preview | active | disabled
    config_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    published_at: Mapped[int | None] = mapped_column(Integer)
    # subscription (managed by the operator; see services/subscription.py)
    plan: Mapped[str] = mapped_column(String(16), default="standard", server_default="standard")
    trial_ends_at: Mapped[int | None] = mapped_column(Integer)
    paid_until: Mapped[int | None] = mapped_column(Integer)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    __table_args__ = (CheckConstraint("status in ('preview','active','disabled')", name="ck_tenant_status"),)


class TenantDomain(Base):
    """A customer's own domain. Platform-level table: it is read before the tenant is known."""

    __tablename__ = "tenant_domains"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    host: Mapped[str] = mapped_column(String(253), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | active | disabled
    verified_at: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    __table_args__ = (CheckConstraint("status in ('pending','active','disabled')", name="ck_domain_status"),)


class Operator(Base):
    """Platform operator (the product owner). Separate from studio owners."""

    __tablename__ = "operators"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    operator_id: Mapped[int] = mapped_column(ForeignKey("operators.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    expires_at: Mapped[int] = mapped_column(Integer)


class Lead(Base):
    """A request from the platform landing page: a business that wants online booking."""

    __tablename__ = "leads"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now_s, index=True)
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(32))
    business: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(24), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    comment: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(12), default="new")  # new | done


class AuditLog(Base):
    """Who changed what on the platform side (plans, domains, suspensions, impersonation)."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[int] = mapped_column(Integer, default=now_s, index=True)
    actor: Mapped[str] = mapped_column(String(254))
    tenant_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class TenantSettings(TenantScoped, Base):
    __tablename__ = "tenant_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tagline: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    address: Mapped[str] = mapped_column(String(200), default="")
    map_url: Mapped[str] = mapped_column(String(300), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    accent: Mapped[str] = mapped_column(String(9), default="#4690FF")
    logo_path: Mapped[str | None] = mapped_column(String(200))
    hero_path: Mapped[str | None] = mapped_column(String(200))
    info_cards: Mapped[list] = mapped_column(JSON, default=list)
    cancel_before_hours: Mapped[int] = mapped_column(Integer, default=12)
    slot_step_min: Mapped[int] = mapped_column(Integer, default=60)
    lead_time_min: Mapped[int] = mapped_column(Integer, default=60)
    max_advance_days: Mapped[int] = mapped_column(Integer, default=60)
    reminder_hours: Mapped[int] = mapped_column(Integer, default=24)
    business_type: Mapped[str] = mapped_column(String(24), default="auto", server_default="auto")
    owner_edited: Mapped[list] = mapped_column(JSON, default=list)  # fields changed in the cabinet
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_settings_tenant"),
        CheckConstraint("slot_step_min % 15 = 0 AND slot_step_min > 0", name="ck_step_grid"),
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)


class Membership(Base):
    """Server-side proof that a user owns a tenant (auth lookup, not tenant-scoped)."""

    __tablename__ = "memberships"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), default="owner")
    seen_at: Mapped[int | None] = mapped_column(Integer)  # app icon badge counts client bookings made after this


class OwnerSession(Base):
    __tablename__ = "owner_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    expires_at: Mapped[int] = mapped_column(Integer)


class Resource(TenantScoped, Base):
    __tablename__ = "resources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300), default="", server_default="")
    photo_path: Mapped[str | None] = mapped_column(String(200))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_resource_tenant_id"),
        UniqueConstraint("tenant_id", "key", name="uq_resource_tenant_key"),
    )


class Service(TenantScoped, Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    price_minor: Mapped[int] = mapped_column(Integer)
    duration_min: Mapped[int] = mapped_column(Integer)
    buffer_min: Mapped[int] = mapped_column(Integer, default=0)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_service_tenant_id"),
        UniqueConstraint("tenant_id", "key", name="uq_service_tenant_key"),
        CheckConstraint("price_minor >= 0 AND duration_min > 0 AND buffer_min >= 0", name="ck_service_values"),
    )


class ServiceResource(TenantScoped, Base):
    """Which resource performs a service. price/duration override the service's own values
    (a senior master costs more; a big car takes longer on a given post)."""

    __tablename__ = "service_resources"
    service_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_minor: Mapped[int | None] = mapped_column(Integer)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "service_id"], ["services.tenant_id", "services.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "resource_id"], ["resources.tenant_id", "resources.id"], ondelete="CASCADE"),
    )


class WorkingHours(TenantScoped, Base):
    __tablename__ = "working_hours"
    id: Mapped[int] = mapped_column(primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0 = Monday
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    open_min: Mapped[int] = mapped_column(Integer, default=540)
    close_min: Mapped[int] = mapped_column(Integer, default=1140)
    __table_args__ = (
        UniqueConstraint("tenant_id", "weekday", name="uq_hours_weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6 AND open_min >= 0 AND close_min <= 1440 AND close_min > open_min", name="ck_hours"),
    )


class ResourceHours(TenantScoped, Base):
    """Own weekly schedule of one resource (a master). No rows = the studio's hours apply."""

    __tablename__ = "resource_hours"
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(Integer)
    weekday: Mapped[int] = mapped_column(Integer)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False)
    open_min: Mapped[int] = mapped_column(Integer, default=540)
    close_min: Mapped[int] = mapped_column(Integer, default=1140)
    __table_args__ = (
        UniqueConstraint("resource_id", "weekday", name="uq_resource_hours_weekday"),
        ForeignKeyConstraint(["tenant_id", "resource_id"], ["resources.tenant_id", "resources.id"], ondelete="CASCADE"),
        CheckConstraint("weekday BETWEEN 0 AND 6 AND open_min >= 0 AND close_min <= 1440 AND close_min > open_min", name="ck_resource_hours"),
    )


class ResourceException(TenantScoped, Base):
    """A day off / special hours for one resource (vacation, sick day, extra shift)."""

    __tablename__ = "resource_exceptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(String(10))
    is_closed: Mapped[bool] = mapped_column(Boolean, default=True)
    open_min: Mapped[int | None] = mapped_column(Integer)
    close_min: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(120), default="")
    __table_args__ = (
        UniqueConstraint("resource_id", "date", name="uq_resource_exception_date"),
        ForeignKeyConstraint(["tenant_id", "resource_id"], ["resources.tenant_id", "resources.id"], ondelete="CASCADE"),
    )


class ScheduleException(TenantScoped, Base):
    __tablename__ = "schedule_exceptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD in the tenant timezone
    is_closed: Mapped[bool] = mapped_column(Boolean, default=True)
    open_min: Mapped[int | None] = mapped_column(Integer)
    close_min: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(120), default="")
    __table_args__ = (UniqueConstraint("tenant_id", "date", name="uq_exception_date"),)


class Client(TenantScoped, Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    phone_norm: Mapped[str] = mapped_column(String(20))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_client_tenant_id"),
        UniqueConstraint("tenant_id", "phone_norm", name="uq_client_phone"),
    )


class Booking(TenantScoped, Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(Integer)
    resource_id: Mapped[int] = mapped_column(Integer)
    client_id: Mapped[int] = mapped_column(Integer)
    start_min: Mapped[int] = mapped_column(Integer)  # UTC epoch minutes: visit start
    end_min: Mapped[int] = mapped_column(Integer)  # visit end (without buffer)
    buffer_min: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="booked")
    service_name: Mapped[str] = mapped_column(String(120))  # snapshots: history survives price edits
    price_minor: Mapped[int] = mapped_column(Integer)
    car: Mapped[str] = mapped_column(String(80), default="")
    plate: Mapped[str] = mapped_column(String(16), default="")
    note: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(8), default="client")  # client | owner
    access_hash: Mapped[str] = mapped_column(String(64))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    cancelled_at: Mapped[int | None] = mapped_column(Integer)
    cancelled_by: Mapped[str | None] = mapped_column(String(8))
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_booking_tenant_id"),
        UniqueConstraint("access_hash", name="uq_booking_access_hash"),
        ForeignKeyConstraint(["tenant_id", "service_id"], ["services.tenant_id", "services.id"]),
        ForeignKeyConstraint(["tenant_id", "resource_id"], ["resources.tenant_id", "resources.id"]),
        ForeignKeyConstraint(["tenant_id", "client_id"], ["clients.tenant_id", "clients.id"]),
        CheckConstraint("end_min > start_min AND price_minor >= 0", name="ck_booking_range"),
        CheckConstraint("status in ('booked','accepted','ready','cancelled')", name="ck_booking_status"),
        Index("ix_booking_tenant_start", "tenant_id", "start_min"),
    )


class ResourceOccupancy(TenantScoped, Base):
    """Bookings and post blocks share this table; both occupy a resource for a continuous range."""

    __tablename__ = "resource_occupancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    resource_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(8))  # booking | block
    booking_id: Mapped[int | None] = mapped_column(Integer)
    start_min: Mapped[int] = mapped_column(Integer)
    end_min: Mapped[int] = mapped_column(Integer)  # includes buffer
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_occ_tenant_id"),
        ForeignKeyConstraint(["tenant_id", "resource_id"], ["resources.tenant_id", "resources.id"]),
        ForeignKeyConstraint(["tenant_id", "booking_id"], ["bookings.tenant_id", "bookings.id"], ondelete="CASCADE"),
        CheckConstraint("end_min > start_min", name="ck_occ_range"),
        CheckConstraint("kind in ('booking','block')", name="ck_occ_kind"),
        CheckConstraint("(kind = 'booking') = (booking_id IS NOT NULL)", name="ck_occ_booking_link"),
        Index("ix_occ_resource_range", "resource_id", "start_min", "end_min"),
    )


class OccupancyCell(Base):
    """One row per 15-minute cell of an occupancy. The primary key is the unique
    (resource_id, cell) index: two overlapping writers cannot both insert."""

    __tablename__ = "occupancy_cells"
    resource_id: Mapped[int] = mapped_column(Integer)
    cell: Mapped[int] = mapped_column(Integer)  # epoch minutes // CELL_MINUTES
    tenant_id: Mapped[int] = mapped_column(Integer)
    occupancy_id: Mapped[int] = mapped_column(Integer)
    __table_args__ = (
        PrimaryKeyConstraint("resource_id", "cell", name="uq_occupancy_cell"),
        ForeignKeyConstraint(["tenant_id", "occupancy_id"], ["resource_occupancies.tenant_id", "resource_occupancies.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id", "resource_id"], ["resources.tenant_id", "resources.id"]),
        Index("ix_cell_occupancy", "occupancy_id"),
        {"sqlite_with_rowid": False},
    )


class Payment(TenantScoped, Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(8))  # payment | refund
    amount_minor: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16), default="cash")
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "booking_id"], ["bookings.tenant_id", "bookings.id"]),
        CheckConstraint("amount_minor > 0 AND kind in ('payment','refund')", name="ck_payment"),
        Index("ix_payment_tenant_time", "tenant_id", "created_at"),
    )


class GalleryPhoto(TenantScoped, Base):
    __tablename__ = "gallery_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(200))
    caption: Mapped[str] = mapped_column(String(160), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(8), default="config")  # config | owner
    config_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)


class IdempotencyKey(TenantScoped, Base):
    __tablename__ = "idempotency_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    booking_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    __table_args__ = (UniqueConstraint("tenant_id", "scope", "key", name="uq_idempotency"),)


class PushSubscription(TenantScoped, Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    audience: Mapped[str] = mapped_column(String(8))  # client | owner
    booking_id: Mapped[int | None] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(600))
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    disabled_at: Mapped[int | None] = mapped_column(Integer)
    device: Mapped[str] = mapped_column(String(80), default="", server_default="")  # "Android · Chrome", from the User-Agent
    last_success_at: Mapped[int | None] = mapped_column(Integer)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(200))
    origin: Mapped[str] = mapped_column(String(200), default="", server_default="")  # "https://studio.ru": the app that subscribed
    __table_args__ = (
        UniqueConstraint("tenant_id", "audience", "endpoint", "booking_id", name="uq_push_endpoint"),
        ForeignKeyConstraint(["tenant_id", "booking_id"], ["bookings.tenant_id", "bookings.id"], ondelete="CASCADE"),
        CheckConstraint("audience in ('client','owner')", name="ck_push_audience"),
    )


class NotificationJob(TenantScoped, Base):
    """Outbox: rows are written in the same transaction as the booking change."""

    __tablename__ = "notification_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int | None] = mapped_column(Integer)
    audience: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(16))  # reminder | new | cancelled | moved
    dedupe_key: Mapped[str] = mapped_column(String(120))
    run_at: Mapped[int] = mapped_column(Integer)  # epoch seconds
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|leased|sent|failed|skipped
    lease_until: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[int] = mapped_column(Integer, default=now_s)
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_job_dedupe"),
        ForeignKeyConstraint(["tenant_id", "booking_id"], ["bookings.tenant_id", "bookings.id"], ondelete="CASCADE"),
        Index("ix_job_due", "status", "run_at"),
    )


class RateCounter(Base):
    """Shared atomic fixed-window counters (key already contains tenant + client hash)."""

    __tablename__ = "rate_counters"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer)
    count: Mapped[int] = mapped_column(Integer, default=0)
