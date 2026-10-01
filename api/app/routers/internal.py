"""Endpoints for our own infrastructure only (never exposed by the reverse proxy)."""
import hmac

from fastapi import APIRouter, Header, HTTPException, Query, Request

from .. import db as database
from ..config import get_settings
from ..services import domains

router = APIRouter(prefix="/api/internal")


@router.get("/host")
def host_lookup(host: str = Query(min_length=3, max_length=253), x_internal_token: str = Header(default="")) -> dict:
    """Next.js asks which studio a custom domain belongs to."""
    if not hmac.compare_digest(x_internal_token, get_settings().internal_token):
        raise HTTPException(403, "forbidden")
    with database.read_session() as db:
        found = domains.resolve(db, host)
    if not found:
        raise HTTPException(404, "unknown_host")
    return {"slug": found[0], "status": found[1]}


@router.get("/tls-allowed")
def tls_allowed(request: Request, domain: str = Query(min_length=3, max_length=253)) -> dict:
    """Caddy's on-demand TLS `ask` hook: issue a certificate only for domains we serve.
    Loopback only (Caddy calls us directly; public traffic arrives with a real client address)."""
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "forbidden")
    host = domain.lower()
    with database.read_session() as db:
        if host in get_settings().platform_host_list or domains.resolve(db, host):
            return {"allowed": True}
    raise HTTPException(404, "not_allowed")
