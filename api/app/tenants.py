"""Tenant pipeline: business.json (+ images) -> validated config -> database.

business.json and images are pipeline *input*; the database is the runtime source.
Republishing is safe: services/resources/settings the owner edited in the cabinet are
kept (unless --force), bookings and owner-uploaded photos are never touched, and
entities dropped from the config are deactivated rather than deleted."""
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import db as database
from . import plans, profiles
from .models import (
    Booking,
    Client,
    GalleryPhoto,
    Membership,
    Payment,
    Resource,
    ResourceException,
    ResourceHours,
    ResourceOccupancy,
    ScheduleException,
    Service,
    ServiceResource,
    Tenant,
    TenantSettings,
    User,
    WorkingHours,
    now_s,
)
from .security import hash_password
from .services import booking as booking_service
from .services import media, subscription
from .services.slots import service_resources
from .timeutil import dt_to_min, local_to_min, now_min

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
RESERVED_SLUGS = {"api", "admin", "owner", "static", "_next", "s", "www"}


def _minutes(value: str) -> int:
    if value == "24:00":
        return 1440
    m = HHMM.match(value)
    if not m:
        raise ValueError(f"time '{value}' must be HH:MM")
    total = int(m[1]) * 60 + int(m[2])
    if total % 15:
        raise ValueError(f"time '{value}' must be a multiple of 15 minutes")
    return total


class InfoCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=220)
    icon: str = "sparkle"


class GalleryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    image: str
    caption: str = ""


class ServiceOfferCfg(BaseModel):
    """A resource that performs a service with its own price and/or duration."""

    model_config = ConfigDict(extra="forbid")
    key: str
    price: float | None = Field(default=None, ge=0)
    duration_min: int | None = Field(default=None, gt=0, le=60 * 24 * 30)


class ServiceCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    price: float | None = Field(default=None, ge=0)  # null: "по договорённости"
    price_from: bool = False  # the studio writes "от …"
    duration_min: int = Field(gt=0, le=60 * 24 * 30)
    buffer_min: int = Field(default=0, ge=0, le=60 * 24)
    resources: list[str | ServiceOfferCfg] | None = None
    keywords: list[str] = []


class ResourceCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    photo: str | None = None
    hours: dict[str, list[str] | None] | None = None  # own weekly hours (masters); omitted = studio hours
    exceptions: list["ExceptionCfg"] = []


class ExceptionCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    closed: bool = True
    open: str | None = None
    close: str | None = None
    note: str = ""


class BookingRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_step_min: int = 60
    lead_time_min: int = 120
    max_advance_days: int = 60
    cancel_before_hours: int = 24
    reminder_hours: int = 24

    @field_validator("slot_step_min")
    @classmethod
    def _grid(cls, v: int) -> int:
        if v <= 0 or v % 15:
            raise ValueError("slot_step_min must be a positive multiple of 15")
        return v


class BusinessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_type: str = "auto"
    plan: str = "standard"  # initial plan of a NEW studio; later changes are the operator's (admin panel / CLI)
    slug: str
    name: str = Field(min_length=1, max_length=120)
    tagline: str = Field(default="", max_length=200)
    description: str = ""
    phone: str = ""
    address: str = ""
    map_url: str = ""
    timezone: str = "Europe/Moscow"
    currency: str = "RUB"
    accent: str = "#4690FF"
    button_color: str | None = None  # buttons as on the studio's website, e.g. "#25702A"
    images: dict[str, str] = {}
    info_cards: list[InfoCard] = []
    gallery: list[GalleryItem] = []
    booking: BookingRules = BookingRules()
    hours: dict[str, list[str] | None]
    exceptions: list[ExceptionCfg] = []
    resources: list[ResourceCfg] = Field(min_length=1)
    services: list[ServiceCfg] = Field(min_length=1)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v) or v in RESERVED_SLUGS:
            raise ValueError("slug must be 2-41 chars of a-z, 0-9, '-' and not reserved")
        return v

    @field_validator("business_type")
    @classmethod
    def _type(cls, v: str) -> str:
        if not profiles.is_valid(v):
            raise ValueError(f"business_type must be one of {', '.join(profiles.TYPES)}")
        return v

    @field_validator("plan")
    @classmethod
    def _plan(cls, v: str) -> str:
        if v not in plans.all_plans():
            raise ValueError(f"plan must be one of {', '.join(plans.all_plans())}")
        return v

    @field_validator("button_color")
    @classmethod
    def _button_color(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            raise ValueError("button_color must be #RRGGBB")
        return v

    @field_validator("accent")
    @classmethod
    def _accent(cls, v: str) -> str:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError("accent must be #RRGGBB")
        return v.upper()

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {v}") from exc
        return v

    @field_validator("info_cards")
    @classmethod
    def _cards(cls, v: list[InfoCard]) -> list[InfoCard]:
        if len(v) > 3:
            raise ValueError("at most 3 info cards")
        return v

    @model_validator(mode="after")
    def _cross(self) -> "BusinessConfig":
        res_keys = [r.key for r in self.resources]
        if len(set(res_keys)) != len(res_keys):
            raise ValueError("duplicate resource keys")
        svc_keys = [s.key for s in self.services]
        if len(set(svc_keys)) != len(svc_keys):
            raise ValueError("duplicate service keys")
        profile = profiles.get_profile(self.business_type)
        if profile.max_resources is not None and len(self.resources) > profile.max_resources:
            raise ValueError(f"business type '{profile.type}' allows at most {profile.max_resources} resource(s)")
        for r in self.resources:
            if r.hours is not None:
                if not profile.features["per_resource_hours"]:
                    raise ValueError(f"resource '{r.key}': own hours are not available for '{profile.type}'")
                _check_week(r.hours, f"resource '{r.key}' hours")
            if r.exceptions and not profile.features["per_resource_hours"]:
                raise ValueError(f"resource '{r.key}': own days off are not available for '{profile.type}'")
        for s in self.services:
            if s.duration_min > 1440 and not profile.features["multi_day"]:
                raise ValueError(f"service '{s.key}': multi-day duration is not available for '{profile.type}'")
            for r in s.resources or []:
                key = r if isinstance(r, str) else r.key
                if key not in res_keys:
                    raise ValueError(f"service '{s.key}' references unknown resource '{key}'")
                if not isinstance(r, str) and not profile.features["per_resource_prices"]:
                    raise ValueError(f"service '{s.key}': per-resource price/duration is not available for '{profile.type}'")
            if profile.features["choose_resource"] and s.resources is None:
                raise ValueError(f"service '{s.key}': list the masters who perform it in 'resources'")
        _check_week(self.hours, "hours")
        if all(self.hours.get(d) is None for d in DAYS):
            raise ValueError("at least one working day is required")
        for e in self.exceptions:
            if not e.closed and not (e.open and e.close and _minutes(e.close) > _minutes(e.open)):
                raise ValueError(f"exception {e.date}: open/close required when not closed")
        if len({g.key for g in self.gallery}) != len(self.gallery):
            raise ValueError("duplicate gallery keys")
        return self


def _check_week(hours: dict, label: str) -> None:
    if set(hours) - set(DAYS):
        raise ValueError(f"{label} keys must be in {DAYS}")
    for day, span in hours.items():
        if span is None:
            continue
        if len(span) != 2:
            raise ValueError(f"{label}.{day} must be [open, close] or null")
        if _minutes(span[1]) <= _minutes(span[0]):
            raise ValueError(f"{label}.{day}: close must be after open")


class ConfigProblem(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def tenants_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tenants"


def load_config(path: Path) -> tuple[BusinessConfig, Path]:
    """path: a tenant directory or its business.json."""
    cfg_file = path / "business.json" if path.is_dir() else path
    if not cfg_file.exists():
        raise ConfigProblem([f"{cfg_file} not found"])
    try:
        raw = json.loads(cfg_file.read_text(encoding="utf-8"))
        cfg = BusinessConfig.model_validate(raw)
    except json.JSONDecodeError as exc:
        raise ConfigProblem([f"invalid JSON: {exc}"]) from exc
    except ValidationError as exc:
        raise ConfigProblem([f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]) from exc
    return cfg, cfg_file.parent


def validate_files(cfg: BusinessConfig, root: Path) -> list[str]:
    problems: list[str] = []
    wanted = [(f"images.{k}", v) for k, v in cfg.images.items()] + [(f"gallery.{g.key}", g.image) for g in cfg.gallery]
    wanted += [(f"resources.{r.key}.photo", r.photo) for r in cfg.resources if r.photo]
    for label, name in wanted:
        f = root / name
        if not f.is_file():
            problems.append(f"{label}: file '{name}' not found in {root}")
            continue
        try:
            media.process_image(f.read_bytes(), max_side=64)
        except media.ImageError as exc:
            problems.append(f"{label}: {name} is not a valid jpg/png/webp image ({exc})")
    if "hero" not in cfg.images:
        problems.append("images.hero: a main photo is required")
    if cfg.info_cards and len(cfg.info_cards) != 3:
        problems.append("info_cards: exactly 3 cards are expected on the home page")
    return problems


def validate(path: Path) -> BusinessConfig:
    cfg, root = load_config(path)
    problems = validate_files(cfg, root)
    if problems:
        raise ConfigProblem(problems)
    return cfg


# -------------------------------------------------------------------- publish
def _config_hash(cfg: BusinessConfig, root: Path) -> str:
    h = hashlib.sha256(cfg.model_dump_json().encode())
    for name in sorted({*cfg.images.values(), *(g.image for g in cfg.gallery), *(r.photo for r in cfg.resources if r.photo)}):
        f = root / name
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()


def _import_image(slug: str, root: Path, name: str, *, kind: str) -> str:
    side = {"logo": 512, "hero": 1800, "photo": 1600}[kind]
    data, ext = media.process_image((root / name).read_bytes(), max_side=side, keep_alpha=(kind == "logo"))
    return media.store(slug, "config", data, ext)


def _apply(obj, fields: dict, edited: bool, force: bool) -> None:
    if edited and not force:
        return
    for k, v in fields.items():
        setattr(obj, k, v)


def publish(path: Path, *, activate: bool = False, force: bool = False, seed_demo: bool | None = None) -> dict:
    """Idempotent. Returns a small report. New tenants start as 'preview'."""
    cfg, root = load_config(path)
    problems = validate_files(cfg, root)
    if problems:
        raise ConfigProblem(problems)
    report = {"slug": cfg.slug, "created": False, "kept_owner_edits": []}

    with database.write_session() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == cfg.slug))
        if not tenant:
            tenant = Tenant(slug=cfg.slug, status="preview", plan=cfg.plan)
            db.add(tenant)
            db.flush()
            report["created"] = True
        tid = tenant.id
        db.info["tenant_id"] = tid

        settings = db.scalar(select(TenantSettings))
        if not settings:
            settings = TenantSettings(tenant_id=tid, name=cfg.name)
            db.add(settings)
            db.flush()
        edited = set(settings.owner_edited or [])
        if force:
            settings.owner_edited = []
            edited = set()

        def guarded(field: str, value) -> None:
            if field in edited:
                report["kept_owner_edits"].append(field)
                return
            setattr(settings, field, value)

        for field in ("name", "tagline", "description", "phone", "address", "map_url", "accent", "button_color", "info_cards"):
            value = getattr(cfg, field)
            guarded(field, [c.model_dump() for c in cfg.info_cards] if field == "info_cards" else value)
        settings.timezone, settings.currency, settings.business_type = cfg.timezone, cfg.currency, cfg.business_type
        settings.slot_step_min = cfg.booking.slot_step_min
        settings.lead_time_min = cfg.booking.lead_time_min
        settings.max_advance_days = cfg.booking.max_advance_days
        settings.cancel_before_hours = cfg.booking.cancel_before_hours
        settings.reminder_hours = cfg.booking.reminder_hours
        if "logo" in cfg.images and "logo" not in edited:
            settings.logo_path = _import_image(cfg.slug, root, cfg.images["logo"], kind="logo")
        if "hero" in cfg.images and "hero" not in edited:
            settings.hero_path = _import_image(cfg.slug, root, cfg.images["hero"], kind="hero")

        _publish_resources(db, tid, cfg, root, force, report)
        _publish_services(db, tid, cfg, force, report)
        if "hours" not in edited:
            _publish_hours(db, tid, cfg)
        _publish_gallery(db, tid, cfg, root)

        tenant.config_hash = _config_hash(cfg, root)
        if activate:
            tenant.status, tenant.published_at = "active", now_s()
            subscription.start_trial(tenant)
        db.flush()
        settings_snapshot = (settings.name, settings.accent, settings.logo_path)
        want_demo = tenant.status == "preview" if seed_demo is None else seed_demo
        if tenant.status == "preview":
            # a sample is rebuilt from the file on every publish: fresh demo rows on the current services,
            # and posts/services removed from the file disappear instead of lingering as "inactive"
            purge_demo(db)
            _drop_unused_inactive(db)
            if want_demo:
                _seed_demo_bookings(db, tenant, settings)
        if activate:
            purge_demo(db)
        report["status"] = tenant.status

    media.build_pwa_assets(cfg.slug, settings_snapshot[0], settings_snapshot[1], settings_snapshot[2])
    return report


def _publish_resources(db: Session, tid: int, cfg: BusinessConfig, root: Path, force: bool, report: dict) -> None:
    existing = {r.key: r for r in db.scalars(select(Resource))}
    for i, rc in enumerate(cfg.resources):
        r = existing.get(rc.key) or Resource(tenant_id=tid, key=rc.key, name=rc.name)
        if r.id is None:
            db.add(r)
        elif r.owner_edited and not force:
            report["kept_owner_edits"].append(f"resource:{rc.key}")
            continue
        r.name, r.description, r.sort, r.is_active = rc.name, rc.description, i, True
        if rc.photo:
            r.photo_path = _import_image(cfg.slug, root, rc.photo, kind="photo")
        if force:
            r.owner_edited = False
        db.flush()
        _publish_resource_schedule(db, tid, r, rc)
    for key, r in existing.items():
        if key not in {x.key for x in cfg.resources} and not r.owner_edited:
            r.is_active = False
    db.flush()


def _publish_resource_schedule(db: Session, tid: int, r: Resource, rc: ResourceCfg) -> None:
    """Own weekly hours and days off of a master; no `hours` in the file = studio hours apply."""
    db.execute(delete(ResourceHours).where(ResourceHours.resource_id == r.id))
    db.execute(delete(ResourceException).where(ResourceException.resource_id == r.id))
    if rc.hours is not None:
        for wd, day in enumerate(DAYS):
            span = rc.hours.get(day)
            if span is None:
                db.add(ResourceHours(tenant_id=tid, resource_id=r.id, weekday=wd, is_closed=True, open_min=540, close_min=1140))
            else:
                db.add(ResourceHours(tenant_id=tid, resource_id=r.id, weekday=wd, is_closed=False, open_min=_minutes(span[0]), close_min=_minutes(span[1])))
    for e in rc.exceptions:
        db.add(
            ResourceException(
                tenant_id=tid, resource_id=r.id, date=e.date.isoformat(), is_closed=e.closed,
                open_min=None if e.closed else _minutes(e.open or "00:00"), close_min=None if e.closed else _minutes(e.close or "00:00"), note=e.note,
            )
        )
    db.flush()


def _publish_services(db: Session, tid: int, cfg: BusinessConfig, force: bool, report: dict) -> None:
    resources = {r.key: r for r in db.scalars(select(Resource))}
    existing = {s.key: s for s in db.scalars(select(Service))}
    for i, sc in enumerate(cfg.services):
        svc = existing.get(sc.key)
        if svc is None:
            svc = Service(tenant_id=tid, key=sc.key, name=sc.name, price_minor=0, duration_min=sc.duration_min)
            db.add(svc)
        elif svc.owner_edited and not force:
            report["kept_owner_edits"].append(f"service:{sc.key}")
            continue
        svc.name, svc.description = sc.name, sc.description
        svc.price_minor = round((sc.price or 0) * 100)
        svc.price_kind = "on_request" if sc.price is None else "from" if sc.price_from else "exact"
        svc.duration_min, svc.buffer_min = sc.duration_min, sc.buffer_min
        svc.keywords, svc.sort, svc.is_active = list(sc.keywords), i, True
        if force:
            svc.owner_edited = False
        db.flush()
        db.execute(delete(ServiceResource).where(ServiceResource.service_id == svc.id))
        for entry in sc.resources or list(resources):
            key = entry if isinstance(entry, str) else entry.key
            price = None if isinstance(entry, str) or entry.price is None else round(entry.price * 100)
            duration = None if isinstance(entry, str) else entry.duration_min
            db.add(ServiceResource(tenant_id=tid, service_id=svc.id, resource_id=resources[key].id, price_minor=price, duration_min=duration))
    for key, svc in existing.items():
        if key not in {s.key for s in cfg.services} and not svc.owner_edited:
            svc.is_active = False
    db.flush()


def _publish_hours(db: Session, tid: int, cfg: BusinessConfig) -> None:
    db.execute(delete(WorkingHours))
    for wd, day in enumerate(DAYS):
        span = cfg.hours.get(day)
        if span is None:
            db.add(WorkingHours(tenant_id=tid, weekday=wd, is_closed=True, open_min=540, close_min=1140))
        else:
            db.add(WorkingHours(tenant_id=tid, weekday=wd, is_closed=False, open_min=_minutes(span[0]), close_min=_minutes(span[1])))
    db.execute(delete(ScheduleException))
    for e in cfg.exceptions:
        db.add(
            ScheduleException(
                tenant_id=tid,
                date=e.date.isoformat(),
                is_closed=e.closed,
                open_min=None if e.closed else _minutes(e.open or "00:00"),
                close_min=None if e.closed else _minutes(e.close or "00:00"),
                note=e.note,
            )
        )
    db.flush()


def _publish_gallery(db: Session, tid: int, cfg: BusinessConfig, root: Path) -> None:
    existing = {p.config_key: p for p in db.scalars(select(GalleryPhoto).where(GalleryPhoto.source == "config"))}
    for i, item in enumerate(cfg.gallery):
        path = _import_image(cfg.slug, root, item.image, kind="photo")
        photo = existing.get(item.key)
        if photo is None:
            db.add(GalleryPhoto(tenant_id=tid, path=path, caption=item.caption, sort=i, source="config", config_key=item.key))
        else:
            photo.path, photo.caption, photo.sort = path, item.caption, i
    for key, photo in existing.items():
        if key not in {g.key for g in cfg.gallery}:
            db.delete(photo)
    db.flush()


# ----------------------------------------------------------------------- demo
def _seed_demo_bookings(db: Session, tenant: Tenant, settings: TenantSettings) -> None:
    """Clearly marked (is_demo) sample rows so a preview link looks alive. Removed on activation."""
    if db.scalar(select(Booking.id).where(Booking.is_demo.is_(True)).limit(1)):
        return
    services = list(db.scalars(select(Service).where(Service.is_active.is_(True)).order_by(Service.sort)))
    if not services:
        return
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    # ordinary names: the prospect sees these rows in the cabinet; they are still marked is_demo and removed on activation
    vehicle = profiles.get_profile(settings.business_type).kind == "vehicle"
    samples = [("Сергей", "79990000001", -2, 10, "Toyota Camry"), ("Анна", "79990000002", 0, 11, "Kia Rio"), ("Дмитрий", "79990000003", 1, 14, "BMW X5")]
    for i, (name, phone, offset, hour, car) in enumerate(samples):
        svc = services[i % len(services)]
        day = today + timedelta(days=offset)
        start = local_to_min(day, hour * 60, tz)
        try:
            res = booking_service.create_booking(
                db,
                tenant_id=tenant.id,
                settings=settings,
                is_preview=True,
                service_id=svc.id,
                start_min=start,
                name=name,
                phone=phone,
                car=car if vehicle else "",
                source="owner",
                now_min=start - 24 * 60 if offset < 0 else now_min(),
                outside_hours=True,
            )
        except booking_service.BookingError:
            continue
        b = res.booking
        db.query(Client).filter(Client.id == b.client_id).update({"is_demo": True})
        if offset < 0:
            b.status = "ready"
            if b.price_minor:  # a free visit (inspection) has nothing to pay
                db.add(Payment(tenant_id=tenant.id, booking_id=b.id, kind="payment", amount_minor=b.price_minor, method="cash"))
    db.flush()


def _drop_unused_inactive(db: Session) -> None:
    """Delete inactive resources/services that no real booking or block refers to (sample studios only)."""
    used_res = set(db.scalars(select(Booking.resource_id))) | set(db.scalars(select(ResourceOccupancy.resource_id)))
    used_svc = set(db.scalars(select(Booking.service_id)))
    for r in db.scalars(select(Resource).where(Resource.is_active.is_(False))):
        if r.id not in used_res:
            db.execute(delete(ServiceResource).where(ServiceResource.resource_id == r.id))
            db.delete(r)
    for svc in db.scalars(select(Service).where(Service.is_active.is_(False))):
        if svc.id not in used_svc:
            db.execute(delete(ServiceResource).where(ServiceResource.service_id == svc.id))
            db.delete(svc)
    db.flush()


def purge_demo(db: Session) -> int:
    ids = list(db.scalars(select(Booking.id).where(Booking.is_demo.is_(True))))
    if not ids:
        return 0
    db.execute(delete(Payment).where(Payment.booking_id.in_(ids)))
    db.execute(delete(ResourceOccupancy).where(ResourceOccupancy.booking_id.in_(ids)))
    db.execute(delete(Booking).where(Booking.id.in_(ids)))
    db.execute(delete(Client).where(Client.is_demo.is_(True)))
    return len(ids)


# ---------------------------------------------------------------------- owner
def create_owner(slug: str, email: str, password: str) -> str:
    """Only path that creates owner accounts (no public sign-up). Returns 'created'|'updated'."""
    if len(password) < 10:
        raise ConfigProblem(["password must be at least 10 characters"])
    email = email.strip().lower()
    with database.write_session() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if not tenant:
            raise ConfigProblem([f"tenant '{slug}' is not published yet"])
        user = db.scalar(select(User).where(User.email == email))
        state = "updated"
        if user:
            user.password_hash = hash_password(password)
        else:
            user = User(email=email, password_hash=hash_password(password))
            db.add(user)
            db.flush()
            state = "created"
        if not db.get(Membership, (user.id, tenant.id)):
            db.add(Membership(user_id=user.id, tenant_id=tenant.id, role="owner"))
    return state


def create_operator(email: str, password: str) -> str:
    """The platform operator account (admin panel). Created only from the CLI."""
    from .models import Operator

    if len(password) < 12:
        raise ConfigProblem(["operator password must be at least 12 characters"])
    email = email.strip().lower()
    with database.write_session() as db:
        op = db.scalar(select(Operator).where(Operator.email == email))
        if op:
            op.password_hash = hash_password(password)
            return "updated"
        db.add(Operator(email=email, password_hash=hash_password(password)))
        return "created"


def tenant_report(slug: str) -> dict:
    with database.read_session() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if not tenant:
            raise ConfigProblem([f"tenant '{slug}' not found"])
        db.info["tenant_id"] = tenant.id
        services = list(db.scalars(select(Service).where(Service.is_active.is_(True))))
        unbookable = [s.key for s in services if not service_resources(db, s.id)]
        return {
            "slug": slug,
            "status": tenant.status,
            "services": len(services),
            "unbookable_services": unbookable,
            "dt": dt_to_min(datetime.now(ZoneInfo("UTC"))),
        }




def activation_problems(path: Path) -> list[str]:
    """What must be true before a preview becomes a live studio."""
    try:
        cfg = validate(path)
    except ConfigProblem as exc:
        return exc.problems
    problems: list[str] = []
    with database.read_session() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == cfg.slug))
        if not tenant:
            return [f"'{cfg.slug}' was never published as a preview: run tenant:publish {cfg.slug} first and check the link"]
        if not db.scalar(select(Membership).where(Membership.tenant_id == tenant.id)):
            problems.append(f"no owner account: run owner:create {cfg.slug} <email>")
        db.info["tenant_id"] = tenant.id
        for s in db.scalars(select(Service).where(Service.is_active.is_(True))):
            if not service_resources(db, s.id):
                problems.append(f"service '{s.key}' has no working post")
    return problems


def handover(slug: str, email: str, plan: str | None = None, password: str | None = None) -> dict:
    """Sale closed: make the studio live (lifetime, no trial), set its package, create the owner.
    Returns what to tell the customer. The password is returned once."""
    import secrets as _secrets

    from .models import Membership as _Membership

    password = password or _secrets.token_urlsafe(9)
    if plan is not None and plan not in plans.all_plans():
        raise ConfigProblem([f"plan must be one of {', '.join(plans.all_plans())}"])
    state = create_owner(slug, email, password)
    with database.write_session() as db:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
        if plan:
            tenant.plan = plan
        if tenant.status != "active":
            db.info["tenant_id"] = tenant.id
            purge_demo(db)
            db.info.pop("tenant_id", None)
            tenant.status, tenant.published_at = "active", now_s()
            subscription.start_trial(tenant)  # no-op unless TRIAL_DAYS > 0
        chosen = tenant.plan
        assert db.scalar(select(_Membership).where(_Membership.tenant_id == tenant.id))
    return {"slug": slug, "email": email.strip().lower(), "password": password, "owner": state, "plan": chosen}
