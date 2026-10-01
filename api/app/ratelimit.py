"""Shared atomic fixed-window counters in SQLite (one UPSERT ... RETURNING statement).
Keys carry the tenant and a hashed client address, so limits are per tenant and per client."""
from fastapi import HTTPException, Request
from sqlalchemy import text

from . import db as database
from .models import now_s
from .security import client_fingerprint

_HIT = text(
    """
    INSERT INTO rate_counters(key, window_start, count) VALUES (:k, :w, 1)
    ON CONFLICT(key) DO UPDATE SET
        count = CASE WHEN rate_counters.window_start = :w THEN rate_counters.count + 1 ELSE 1 END,
        window_start = :w
    RETURNING count
    """
)


def hit(key: str, limit: int, window_s: int) -> None:
    window = now_s() // window_s * window_s
    with database.write_engine().begin() as conn:
        count = conn.execute(_HIT, {"k": key, "w": window}).scalar_one()
    if count > limit:
        raise HTTPException(429, "too_many_requests", headers={"Retry-After": str(window + window_s - now_s())})


def limit_request(request: Request, tenant_id: int, bucket: str, per_client: int, window_s: int, per_tenant: int | None = None) -> None:
    ip = request.client.host if request.client else "unknown"
    hit(f"{bucket}:{tenant_id}:{client_fingerprint(ip)}", per_client, window_s)
    if per_tenant:
        hit(f"{bucket}:{tenant_id}:*", per_tenant, window_s)
