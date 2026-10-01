from dataclasses import dataclass
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Path, Request
from sqlalchemy import select

from . import db as database
from .config import get_settings
from .models import Booking, Membership, OwnerSession, Tenant, now_s
from .security import safe_equal, sha256_hex
from .services import subscription

SESSION_COOKIE = "owner_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class TenantCtx:
    id: int
    slug: str
    status: str
    plan: str = "standard"
    trial_ends_at: int | None = None
    paid_until: int | None = None
    suspended: bool = False

    @property
    def is_preview(self) -> bool:
        return self.status == "preview"


def tenant_dep(slug: str = Path(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")) -> TenantCtx:
    """The tenant comes from the URL slug only, never from a body or header."""
    with database.read_session() as db:
        t = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if not t or t.status == "disabled":
        raise HTTPException(404, "studio_not_found")
    return TenantCtx(t.id, t.slug, t.status, t.plan, t.trial_ends_at, t.paid_until, t.suspended)


@dataclass(frozen=True)
class OwnerCtx:
    tenant: TenantCtx
    user_id: int
    csrf: str


def _check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    host = urlparse(origin).netloc
    allowed = {urlparse(o).netloc for o in get_settings().origins}
    seen = request.headers.get("x-forwarded-host") or request.headers.get("host")  # set by the reverse proxy
    if host != seen and host not in allowed:
        raise HTTPException(403, "bad_origin")


def owner_dep(request: Request, tenant: TenantCtx = Depends(tenant_dep)) -> OwnerCtx:
    """Session cookie -> server-side session -> membership check for THIS tenant."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(401, "not_authenticated")
    with database.read_session() as db:
        sess = db.scalar(select(OwnerSession).where(OwnerSession.token_hash == sha256_hex(raw)))
        if not sess or sess.expires_at < now_s() or sess.tenant_id != tenant.id:
            raise HTTPException(401, "not_authenticated")
        member = db.get(Membership, (sess.user_id, tenant.id))
    if not member:
        raise HTTPException(403, "no_membership")
    if request.method in UNSAFE:
        _check_origin(request)
        if not safe_equal(request.headers.get("x-csrf-token", ""), sess.csrf_token):
            raise HTTPException(403, "bad_csrf")
        if not request.url.path.endswith("/logout") and not subscription.booking_enabled(tenant):  # suspended studios are read-only
            raise HTTPException(402, {"code": "studio_suspended"})
    return OwnerCtx(tenant, sess.user_id, sess.csrf_token)


def client_booking_id(request: Request, tenant: TenantCtx = Depends(tenant_dep)) -> int:
    """X-Booking-Token -> booking id. Only the hash is stored; scoped to the slug's tenant."""
    token = request.headers.get("x-booking-token", "")
    if len(token) < 20:
        raise HTTPException(401, "booking_token_required")
    with database.read_session(tenant.id) as db:
        bid = db.scalar(select(Booking.id).where(Booking.access_hash == sha256_hex(token)))
    if bid is None:
        raise HTTPException(404, "booking_not_found")
    return bid
