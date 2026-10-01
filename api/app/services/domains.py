"""Customer domains: validation, DNS check, host -> studio resolution."""
import re
import socket

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Tenant, TenantDomain, now_s
from ..plans import get_plan

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class DomainError(Exception):
    def __init__(self, code: str, status: int = 422):
        super().__init__(code)
        self.code, self.status = code, status


def normalize_host(raw: str) -> str:
    """'https://Book.Example.com/path' -> 'book.example.com'. Rejects IPs, ports, single labels and platform hosts."""
    host = raw.strip().lower()
    host = re.sub(r"^[a-z]+://", "", host).split("/")[0].split("?")[0]
    if ":" in host or not host:
        raise DomainError("invalid_domain")
    if re.fullmatch(r"[\d.]+", host):
        raise DomainError("invalid_domain")
    labels = host.split(".")
    if len(host) > 253 or len(labels) < 2 or not all(_LABEL.match(part) for part in labels) or not re.search(r"[a-z]", labels[-1]):
        raise DomainError("invalid_domain")
    if host in get_settings().platform_host_list or host == "localhost":
        raise DomainError("reserved_domain")
    return host


def add_domain(db: Session, tenant: Tenant, raw: str, *, force: bool = False) -> TenantDomain:
    host = normalize_host(raw)
    if not force and not get_plan(tenant.plan).custom_domain:
        raise DomainError("plan_no_custom_domain", 402)
    if db.scalar(select(TenantDomain).where(TenantDomain.host == host)):
        raise DomainError("domain_taken", 409)
    dom = TenantDomain(tenant_id=tenant.id, host=host, status="pending")
    db.add(dom)
    db.flush()
    return dom


def dns_check(host: str) -> dict:
    """Does the domain point at us? Compares its A/AAAA records with PLATFORM_IPS."""
    expected = [ip.strip() for ip in get_settings().platform_ips.split(",") if ip.strip()]
    try:
        resolved = sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror:
        resolved = []
    return {"host": host, "resolved": resolved, "expected": expected, "ok": bool(expected) and bool(set(resolved) & set(expected)), "configured": bool(expected)}


def activate(db: Session, dom: TenantDomain) -> None:
    dom.status, dom.verified_at = "active", now_s()


def resolve(db: Session, host: str) -> tuple[str, str] | None:
    """(slug, tenant status) for an active custom domain, else None."""
    row = db.execute(
        select(Tenant.slug, Tenant.status).join(TenantDomain, TenantDomain.tenant_id == Tenant.id).where(TenantDomain.host == host.lower(), TenantDomain.status == "active")
    ).first()
    return (row[0], row[1]) if row and row[1] != "disabled" else None
