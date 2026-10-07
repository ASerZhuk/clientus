"""Request bodies. extra='forbid' everywhere: price, duration, tenant and status are
never accepted from a client, only the fields listed here."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .security import normalize_phone


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ContactFields(Strict):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=5, max_length=32)
    car: str = Field(default="", max_length=80)
    plate: str = Field(default="", max_length=16)
    note: str = Field(default="", max_length=300)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        digits = normalize_phone(v)
        if not 10 <= len(digits) <= 15:
            raise ValueError("phone must have 10-15 digits")
        return v


class BookingIn(ContactFields):
    service_id: int = Field(gt=0)
    start_min: int = Field(gt=0)
    resource_id: int | None = Field(default=None, gt=0)  # only accepted where the profile lets customers pick a master


class OwnerBookingIn(BookingIn):
    outside_hours: bool = False


class LoginIn(Strict):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    password: str = Field(min_length=1, max_length=200)


class LeadIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=5, max_length=32)
    business: str = Field(default="", max_length=120)
    kind: Literal["", "auto", "wash", "beauty_master", "beauty_studio", "other"] = ""
    city: str = Field(default="", max_length=80)
    comment: str = Field(default="", max_length=500)
    website: str = Field(default="", max_length=200)  # honeypot: people never see this field

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        if not 10 <= len(normalize_phone(v)) <= 15:
            raise ValueError("phone must have 10-15 digits")
        return v


class InstallCodeIn(Strict):
    code: str = Field(min_length=10, max_length=120)


class PasswordChangeIn(Strict):
    new: str = Field(min_length=10, max_length=200)  # same minimum as owner:create


class StatusIn(Strict):
    status: Literal["booked", "accepted", "ready"]


class RescheduleIn(Strict):
    start_min: int = Field(gt=0)
    resource_id: int | None = None


class PaymentIn(Strict):
    kind: Literal["payment", "refund"]
    amount_minor: int = Field(gt=0, le=100_000_000)
    method: Literal["cash", "card", "transfer"] = "cash"
    note: str = Field(default="", max_length=200)


class BlockIn(Strict):
    resource_id: int
    start_min: int = Field(gt=0)
    end_min: int = Field(gt=0)
    note: str = Field(default="", max_length=200)


class OfferIn(Strict):
    """One resource that performs the service, with optional own price/duration."""

    resource_id: int
    price_minor: int | None = Field(default=None, ge=0, le=100_000_000)
    duration_min: int | None = Field(default=None, gt=0, le=60 * 24 * 30)


class ServiceIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    price_minor: int = Field(ge=0, le=100_000_000)
    price_kind: Literal["exact", "from", "on_request"] = "exact"
    duration_min: int = Field(gt=0, le=60 * 24 * 30)
    buffer_min: int = Field(default=0, ge=0, le=60 * 24)
    resource_ids: list[int] = []
    offers: list[OfferIn] = []  # when given, replaces resource_ids and carries per-resource price/duration
    keywords: list[str] = Field(default=[], max_length=12)
    is_active: bool = True


class ResourceIn(Strict):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    is_active: bool = True


class ResourceScheduleIn(Strict):
    """Own weekly hours + days off of one resource. use_studio_hours=True removes the own schedule."""

    use_studio_hours: bool = False
    days: list["DayHours"] = Field(default=[], max_length=7)
    exceptions: list["ExceptionIn"] = Field(default=[], max_length=200)


class InfoCardIn(Strict):
    title: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=220)
    icon: str = Field(default="sparkle", max_length=24)


class SettingsPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    tagline: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=200)
    map_url: str | None = Field(default=None, max_length=300)
    cancel_before_hours: int | None = Field(default=None, ge=0, le=24 * 14)
    lead_time_min: int | None = Field(default=None, ge=0, le=60 * 24 * 7)
    reminder_hours: int | None = Field(default=None, ge=1, le=24 * 7)
    info_cards: list[InfoCardIn] | None = Field(default=None, max_length=3)

    @field_validator("map_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        if v and not re.match(r"^https?://", v):
            raise ValueError("map_url must start with http(s)://")
        return v


class DayHours(Strict):
    weekday: int = Field(ge=0, le=6)
    is_closed: bool
    open_min: int = Field(default=540, ge=0, le=1425)
    close_min: int = Field(default=1140, gt=0, le=1440)

    @field_validator("open_min", "close_min")
    @classmethod
    def _grid(cls, v: int) -> int:
        if v % 15:
            raise ValueError("times must be multiples of 15 minutes")
        return v


class HoursIn(Strict):
    days: list[DayHours] = Field(min_length=7, max_length=7)
    exceptions: list["ExceptionIn"] = Field(default=[], max_length=120)


class ExceptionIn(Strict):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_closed: bool = True
    open_min: int | None = Field(default=None, ge=0, le=1425)
    close_min: int | None = Field(default=None, gt=0, le=1440)
    note: str = Field(default="", max_length=120)


HoursIn.model_rebuild()
ResourceScheduleIn.model_rebuild()


class CaptionIn(Strict):
    caption: str = Field(max_length=160)


class PushKeys(Strict):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=6, max_length=80)


class PushSubscriptionIn(Strict):
    endpoint: str = Field(min_length=10, max_length=600, pattern=r"^https://")
    keys: PushKeys


class PushRotateIn(Strict):
    """The browser replaced a subscription (pushsubscriptionchange): knowing the old endpoint proves ownership."""
    old_endpoint: str = Field(min_length=10, max_length=600, pattern=r"^https://")
    subscription: PushSubscriptionIn


class AssistantTurn(Strict):
    role: Literal["me", "bot"]
    text: str = Field(max_length=1500)


class AssistantIn(Strict):
    text: str = Field(min_length=1, max_length=300)
    context: dict[str, str | int] | None = None  # e.g. {"service_id": 3} answering a clarifying question
    history: list[AssistantTurn] = Field(default_factory=list, max_length=8)  # earlier turns, so follow-ups make sense
