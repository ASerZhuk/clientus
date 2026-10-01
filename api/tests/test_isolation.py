import pytest
from sqlalchemy import select

from app import db as database
from app.models import Booking, Service, Tenant
from app.tenancy import TenantViolation
from tests.api_helpers import BOOK, first_slot, owner_login, service_id, setup_tenant


def two_tenants(tmp_path):
    setup_tenant(tmp_path, "alpha")
    setup_tenant(tmp_path, "beta")


def test_owner_of_one_studio_cannot_touch_another(client, tmp_path):
    two_tenants(tmp_path)
    headers_a = owner_login(client, "alpha")
    sid_b = service_id(client, "beta")
    slot_b = first_slot(client, "beta", sid_b)
    booking_b = client.post("/api/s/beta/bookings", json={**BOOK, "service_id": sid_b, "start_min": slot_b}, headers={"Idempotency-Key": "beta-key-00001"})
    bid_b = booking_b.json()["booking"]["id"]
    # alpha's session cookie is scoped to alpha's path: beta's cabinet sees nobody
    assert client.get("/api/s/beta/owner/schedule").status_code == 401
    # alpha's session against alpha's routes cannot see beta's booking id
    assert client.get(f"/api/s/alpha/owner/bookings/{bid_b}").status_code == 404
    assert client.patch(f"/api/s/alpha/owner/bookings/{bid_b}/status", json={"status": "ready"}, headers=headers_a).status_code == 404
    assert client.post(f"/api/s/alpha/owner/bookings/{bid_b}/cancel", headers=headers_a).status_code == 404
    with database.read_session() as db:
        assert db.scalar(select(Booking).where(Booking.id == bid_b)).status == "booked"


def test_cookie_replayed_on_other_slug_is_rejected(client, tmp_path):
    two_tenants(tmp_path)
    owner_login(client, "alpha")
    token = client.cookies.get("owner_session", path="/api/s/alpha/owner")
    other = client.__class__(client.app, base_url="http://testserver")
    other.cookies.set("owner_session", token, path="/api/s/beta/owner")
    assert other.get("/api/s/beta/owner/schedule").status_code == 401  # session belongs to alpha


def test_owner_without_membership_cannot_log_into_other_studio(client, tmp_path):
    two_tenants(tmp_path)
    r = client.post("/api/s/beta/owner/login", json={"email": "owner@alpha.test", "password": "correct horse battery"})
    assert r.status_code == 401


def test_booking_token_is_bound_to_its_studio(client, tmp_path):
    two_tenants(tmp_path)
    sid = service_id(client, "alpha")
    token = client.post("/api/s/alpha/bookings", json={**BOOK, "service_id": sid, "start_min": first_slot(client, "alpha", sid)}, headers={"Idempotency-Key": "alpha-key-0001"}).json()["access_token"]
    assert client.get("/api/s/beta/my/booking", headers={"X-Booking-Token": token}).status_code == 404
    assert client.get("/api/s/alpha/my/booking", headers={"X-Booking-Token": token}).status_code == 200


def test_data_layer_scopes_every_query_and_blocks_foreign_writes(app_db, tmp_path):
    two_tenants(tmp_path)
    with database.read_session() as db:
        a = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        b = db.scalar(select(Tenant).where(Tenant.slug == "beta"))
    with database.read_session(a.id) as db:
        assert {s.tenant_id for s in db.scalars(select(Service))} == {a.id}
        foreign = db.scalar(select(Service.id).execution_options(populate_existing=True).where(Service.tenant_id == b.id))
        assert foreign is None  # even an explicit foreign tenant_id filter finds nothing
    with pytest.raises(TenantViolation):
        with database.write_session(a.id) as db:
            db.add(Service(tenant_id=b.id, key="evil", name="x", price_minor=1, duration_min=15))


def test_composite_fk_rejects_cross_tenant_rows(app_db, tmp_path):
    from sqlalchemy.exc import IntegrityError

    two_tenants(tmp_path)
    with database.read_session() as db:
        a = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        b = db.scalar(select(Tenant).where(Tenant.slug == "beta"))
        svc_b = db.scalar(select(Service).where(Service.tenant_id == b.id))
    from app.models import ServiceResource

    with pytest.raises(IntegrityError):
        with database.write_session() as db:  # unscoped session on purpose: the schema itself must refuse
            db.add(ServiceResource(tenant_id=a.id, service_id=svc_b.id, resource_id=1))
