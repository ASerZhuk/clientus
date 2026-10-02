"""Operator panel API (the platform owner). Separate accounts, session cookie and CSRF from studio owners.
Every change is written to the audit log."""
import secrets
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from .. import db as database
from .. import tenants as tenant_ops
from ..config import get_settings
from ..deps import SESSION_COOKIE, _check_origin
from ..models import (
    AdminSession,
    AuditLog,
    Lead,
    Booking,
    Membership,
    Operator,
    OwnerSession,
    Tenant,
    TenantDomain,
    TenantSettings,
    User,
    now_s,
)
from ..plans import all_plans, get_plan
from ..ratelimit import hit
from ..schemas import LoginIn
from ..security import client_fingerprint, new_token, safe_equal, sha256_hex, verify_password
from ..services import domains, subscription

router = APIRouter(prefix="/api/admin")
ADMIN_COOKIE = "admin_session"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
DAY = 86400


@dataclass(frozen=True)
class AdminCtx:
    operator_id: int
    email: str
    csrf: str


def admin_dep(request: Request) -> AdminCtx:
    raw = request.cookies.get(ADMIN_COOKIE)
    if not raw:
        raise HTTPException(401, "not_authenticated")
    with database.read_session() as db:
        sess = db.scalar(select(AdminSession).where(AdminSession.token_hash == sha256_hex(raw)))
        if not sess or sess.expires_at < now_s():
            raise HTTPException(401, "not_authenticated")
        op = db.get(Operator, sess.operator_id)
    if not op:
        raise HTTPException(401, "not_authenticated")
    if request.method in UNSAFE:
        _check_origin(request)
        if not safe_equal(request.headers.get("x-csrf-token", ""), sess.csrf_token):
            raise HTTPException(403, "bad_csrf")
    return AdminCtx(op.id, op.email, sess.csrf_token)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SubscriptionPatch(Strict):
    plan: str | None = None
    trial_days: int | None = Field(default=None, ge=0, le=365)  # trial ends N days from now
    add_paid_days: int | None = Field(default=None, ge=1, le=3650)  # extends the paid period
    paid_until: int | None = None  # exact epoch seconds; 0 clears it
    suspended: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class StatusIn(Strict):
    status: str = Field(pattern="^(preview|active|disabled)$")


class DomainIn(Strict):
    host: str = Field(min_length=3, max_length=253)
    force: bool = False


class VerifyIn(Strict):
    force: bool = False


class OwnerIn(Strict):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")


def _audit(db, ctx: AdminCtx, tenant_id: int | None, action: str, **detail) -> None:
    db.add(AuditLog(actor=ctx.email, tenant_id=tenant_id, action=action, detail=detail))


def _tenant_or_404(db, slug: str) -> Tenant:
    t = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if not t:
        raise HTTPException(404, {"code": "studio_not_found"})
    return t


def _row(db, t: Tenant, now: int) -> dict:
    with database.read_session(t.id) as scoped:
        name = scoped.scalar(select(TenantSettings.name)) or t.slug
        btype = scoped.scalar(select(TenantSettings.business_type)) or "auto"
        sub = subscription.overview(scoped, t, now)
        last = scoped.scalar(select(func.max(Booking.created_at)).where(Booking.is_demo.is_(False)))
    owners = list(db.scalars(select(User.email).join(Membership, Membership.user_id == User.id).where(Membership.tenant_id == t.id)))
    doms = [{"id": d.id, "host": d.host, "status": d.status} for d in db.scalars(select(TenantDomain).where(TenantDomain.tenant_id == t.id).order_by(TenantDomain.id))]
    return {
        "slug": t.slug, "name": name, "business_type": btype, "status": t.status, "suspended": t.suspended, "notes": t.notes,
        "trial_ends_at": t.trial_ends_at, "paid_until": t.paid_until, "created_at": t.created_at,
        "owners": owners, "domains": doms, "last_booking_at": last, **sub,
    }


# ------------------------------------------------------------------- session
@router.post("/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    ip = request.client.host if request.client else "unknown"
    hit(f"admin-login:{client_fingerprint(ip)}", 6, 600)
    email = body.email.lower()
    with database.read_session() as db:
        op = db.scalar(select(Operator).where(Operator.email == email))
    if not (verify_password(body.password, op.password_hash if op else None) and op):
        raise HTTPException(401, {"code": "invalid_credentials"})
    token, csrf = new_token(), secrets.token_urlsafe(24)
    ttl = get_settings().admin_session_hours * 3600
    with database.write_session() as db:
        db.execute(delete(AdminSession).where(AdminSession.expires_at < now_s()))
        db.add(AdminSession(token_hash=sha256_hex(token), operator_id=op.id, csrf_token=csrf, expires_at=now_s() + ttl))
        db.add(AuditLog(actor=op.email, tenant_id=None, action="login", detail={}))
    response.set_cookie(ADMIN_COOKIE, token, max_age=ttl, httponly=True, samesite="strict", secure=get_settings().cookie_secure, path="/api/admin")
    response.headers["Cache-Control"] = "no-store"
    return {"email": op.email, "csrf_token": csrf}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, ctx: AdminCtx = Depends(admin_dep)) -> None:
    with database.write_session() as db:
        db.execute(delete(AdminSession).where(AdminSession.token_hash == sha256_hex(request.cookies.get(ADMIN_COOKIE, ""))))
    response.delete_cookie(ADMIN_COOKIE, path="/api/admin")


@router.get("/me")
def me(response: Response, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"email": ctx.email, "csrf_token": ctx.csrf, "plans": [{"key": p.key, "label": p.label, "price_minor": p.price_minor, "max_resources": p.max_resources, "max_bookings_month": p.max_bookings_month, "custom_domain": p.custom_domain, "remove_branding": p.remove_branding} for p in all_plans().values()]}


# ------------------------------------------------------------------ leads
@router.get("/leads")
def leads_list(response: Response, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    with database.read_session() as db:
        rows = list(db.scalars(select(Lead).order_by(Lead.created_at.desc()).limit(200)))
        return {"leads": [{k: getattr(r, k) for k in ("id", "created_at", "name", "phone", "business", "kind", "city", "comment", "status")} for r in rows]}


@router.patch("/leads/{lead_id}")
def lead_status(lead_id: int, body: dict, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    status = body.get("status")
    if status not in ("new", "done"):
        raise HTTPException(422, {"code": "validation_error"})
    with database.write_session() as db:
        lead = db.get(Lead, lead_id)
        if not lead:
            raise HTTPException(404, {"code": "not_found"})
        lead.status = status
        return {"id": lead.id, "status": lead.status}


# ------------------------------------------------------------------ overview
@router.get("/overview")
def overview(response: Response, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    now = now_s()
    with database.read_session() as db:
        rows = [_row(db, t, now) for t in db.scalars(select(Tenant).order_by(Tenant.created_at.desc(), Tenant.id.desc()))]
        month_ago = now - 30 * DAY
        bookings_30d = db.scalar(select(func.count()).select_from(Booking).where(Booking.created_at >= month_ago, Booking.is_demo.is_(False))) or 0
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    # sales: what the live (activated) studios were sold for, at current plan prices
    sold = sum(get_plan(r["plan"]).price_minor for r in rows if r["status"] == "active")
    return {"tenants_total": len(rows), "by_state": by_state, "bookings_30d": int(bookings_30d), "sales_total_minor": sold, "live_total": sum(1 for r in rows if r["status"] == "active"), "tenants": rows}


@router.get("/tenants/{slug}")
def tenant_detail(slug: str, response: Response, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    with database.read_session() as db:
        t = _tenant_or_404(db, slug)
        audit = [
            {"at": a.at, "actor": a.actor, "action": a.action, "detail": a.detail}
            for a in db.scalars(select(AuditLog).where(AuditLog.tenant_id == t.id).order_by(AuditLog.id.desc()).limit(20))
        ]
        return {**_row(db, t, now_s()), "audit": audit}


@router.get("/audit")
def audit_log(limit: int = Query(default=50, ge=1, le=200), ctx: AdminCtx = Depends(admin_dep)) -> dict:
    with database.read_session() as db:
        rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
        return {"items": [{"at": a.at, "actor": a.actor, "tenant_id": a.tenant_id, "action": a.action, "detail": a.detail} for a in rows]}


# ------------------------------------------------------------------- actions
@router.patch("/tenants/{slug}/subscription")
def patch_subscription(slug: str, body: SubscriptionPatch, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    now = now_s()
    with database.write_session() as db:
        t = _tenant_or_404(db, slug)
        changes: dict = {}
        if body.plan is not None:
            if body.plan not in all_plans():
                raise HTTPException(422, {"code": "unknown_plan"})
            changes["plan"], t.plan = body.plan, body.plan
        if body.trial_days is not None:
            t.trial_ends_at = now + body.trial_days * DAY
            changes["trial_days"] = body.trial_days
        if body.add_paid_days is not None:
            base = t.paid_until if t.paid_until and t.paid_until > now else now
            t.paid_until = base + body.add_paid_days * DAY
            changes["add_paid_days"] = body.add_paid_days
        if body.paid_until is not None:
            t.paid_until = body.paid_until or None
            changes["paid_until"] = body.paid_until
        if body.suspended is not None:
            t.suspended = body.suspended
            changes["suspended"] = body.suspended
        if body.notes is not None:
            t.notes = body.notes
            changes["notes"] = True
        _audit(db, ctx, t.id, "subscription", **changes)
        db.flush()
        return _row(db, t, now)


@router.post("/tenants/{slug}/status")
def set_status(slug: str, body: StatusIn, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    now = now_s()
    with database.write_session() as db:
        t = _tenant_or_404(db, slug)
        before = t.status
        if body.status == "active" and before != "active":
            if not db.scalar(select(Membership).where(Membership.tenant_id == t.id)):
                raise HTTPException(409, {"code": "no_owner"})
            db.info["tenant_id"] = t.id
            tenant_ops.purge_demo(db)
            db.info.pop("tenant_id", None)
            t.published_at = now
            subscription.start_trial(t, now)
        t.status = body.status
        _audit(db, ctx, t.id, "status", before=before, after=body.status)
        db.flush()
        return _row(db, t, now)


@router.post("/tenants/{slug}/domains", status_code=201)
def add_domain(slug: str, body: DomainIn, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    try:
        with database.write_session() as db:
            t = _tenant_or_404(db, slug)
            dom = domains.add_domain(db, t, body.host, force=body.force)
            _audit(db, ctx, t.id, "domain_add", host=dom.host)
            return {"id": dom.id, "host": dom.host, "status": dom.status, "dns": domains.dns_check(dom.host)}
    except domains.DomainError as exc:
        raise HTTPException(exc.status, {"code": exc.code}) from exc


@router.post("/domains/{domain_id}/verify")
def verify_domain(domain_id: int, body: VerifyIn, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    with database.write_session() as db:
        dom = db.get(TenantDomain, domain_id)
        if not dom:
            raise HTTPException(404, {"code": "domain_not_found"})
        check = domains.dns_check(dom.host)
        if check["ok"] or body.force:
            domains.activate(db, dom)
        _audit(db, ctx, dom.tenant_id, "domain_verify", host=dom.host, ok=check["ok"], forced=body.force)
        return {"id": dom.id, "host": dom.host, "status": dom.status, "dns": check}


@router.delete("/domains/{domain_id}", status_code=204)
def remove_domain(domain_id: int, ctx: AdminCtx = Depends(admin_dep)) -> None:
    with database.write_session() as db:
        dom = db.get(TenantDomain, domain_id)
        if not dom:
            raise HTTPException(404, {"code": "domain_not_found"})
        _audit(db, ctx, dom.tenant_id, "domain_remove", host=dom.host)
        db.delete(dom)


@router.post("/tenants/{slug}/owner")
def reset_owner(slug: str, body: OwnerIn, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    """Creates the owner or resets the password. The password is returned once and never stored in clear."""
    password = secrets.token_urlsafe(12)
    try:
        state = tenant_ops.create_owner(slug, body.email, password)
    except tenant_ops.ConfigProblem as exc:
        raise HTTPException(404, {"code": "studio_not_found", "problems": exc.problems}) from exc
    with database.write_session() as db:
        t = _tenant_or_404(db, slug)
        _audit(db, ctx, t.id, "owner_" + state, email=body.email.lower())
    return {"email": body.email.lower(), "password": password, "state": state}


@router.post("/tenants/{slug}/impersonate")
def impersonate(slug: str, response: Response, ctx: AdminCtx = Depends(admin_dep)) -> dict:
    """Opens the studio's cabinet as its owner for support (2 hours, audited)."""
    with database.write_session() as db:
        t = _tenant_or_404(db, slug)
        member = db.scalar(select(Membership).where(Membership.tenant_id == t.id).order_by(Membership.user_id))
        if not member:
            raise HTTPException(409, {"code": "no_owner"})
        token = new_token()
        db.add(OwnerSession(token_hash=sha256_hex(token), user_id=member.user_id, tenant_id=t.id, csrf_token=secrets.token_urlsafe(24), expires_at=now_s() + 2 * 3600))
        _audit(db, ctx, t.id, "impersonate")
    response.set_cookie(SESSION_COOKIE, token, max_age=2 * 3600, httponly=True, samesite="lax", secure=get_settings().cookie_secure, path=f"/api/s/{slug}/owner")
    response.headers["Cache-Control"] = "no-store"
    return {"path": "/owner"}
