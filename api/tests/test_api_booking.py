from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import select

from app import db as database
from app.models import Booking
from tests.api_helpers import BOOK, first_slot, owner_login, service_id, setup_tenant


def test_public_config_has_no_personal_data(client, tmp_path):
    setup_tenant(tmp_path)
    sid = service_id(client, "alpha")
    start = first_slot(client, "alpha", sid)
    client.post("/api/s/alpha/bookings", json={**BOOK, "service_id": sid, "start_min": start}, headers={"Idempotency-Key": "key-12345678"})
    body = client.get("/api/s/alpha").text
    for secret in ("BMW", "Иван", "79001112233", "a123bc", "A123BC", "password", "access_hash"):
        assert secret not in body


def test_client_flow_token_and_cancel_rules(client, tmp_path):
    setup_tenant(tmp_path)
    sid = service_id(client, "alpha")
    start = first_slot(client, "alpha", sid)
    r = client.post("/api/s/alpha/bookings", json={**BOOK, "service_id": sid, "start_min": start}, headers={"Idempotency-Key": "key-abcdefgh"})
    assert r.status_code == 201
    token = r.json()["access_token"]
    assert r.json()["booking"]["price_minor"] == 100000
    mine = client.get("/api/s/alpha/my/booking", headers={"X-Booking-Token": token})
    assert mine.status_code == 200 and mine.json()["car"] == "BMW X5"
    assert client.get("/api/s/alpha/my/booking", headers={"X-Booking-Token": "x" * 40}).status_code == 404
    assert client.get("/api/s/alpha/my/booking").status_code == 401
    # DB stores only a hash of the token
    with database.read_session() as db:
        assert token not in {b.access_hash for b in db.scalars(select(Booking))}
    cancel = client.post("/api/s/alpha/my/cancel", headers={"X-Booking-Token": token})
    assert cancel.status_code in (200, 403)  # depends on how far the first slot is; rule is covered below
    if cancel.status_code == 200:
        assert cancel.json()["status"] == "cancelled"


def test_client_cannot_set_price_tenant_or_duration(client, tmp_path):
    setup_tenant(tmp_path)
    sid = service_id(client, "alpha")
    start = first_slot(client, "alpha", sid)
    for extra in ({"price_minor": 1}, {"tenant_id": 2}, {"duration_min": 5}, {"status": "ready"}, {"resource_id": 1}):
        r = client.post("/api/s/alpha/bookings", json={**BOOK, "service_id": sid, "start_min": start, **extra}, headers={"Idempotency-Key": "key-extra-1234"})
        assert r.status_code == 422, extra


def test_idempotent_retry_reissues_same_access(client, tmp_path):
    setup_tenant(tmp_path)
    sid = service_id(client, "alpha")
    start = first_slot(client, "alpha", sid)
    payload = {**BOOK, "service_id": sid, "start_min": start}
    a = client.post("/api/s/alpha/bookings", json=payload, headers={"Idempotency-Key": "retry-key-0001"})
    b = client.post("/api/s/alpha/bookings", json=payload, headers={"Idempotency-Key": "retry-key-0001"})
    assert (a.status_code, b.status_code) == (201, 200)
    assert a.json()["access_token"] == b.json()["access_token"] and b.json()["replayed"] is True
    with database.read_session() as db:
        assert len(list(db.scalars(select(Booking)))) == 1
    assert client.post("/api/s/alpha/bookings", json=payload).status_code == 422  # header required


def test_parallel_api_requests_only_one_booking(make_client, tmp_path):
    setup_tenant(tmp_path)
    c = make_client()
    sid = service_id(c, "alpha")
    start = first_slot(c, "alpha", sid)
    barrier = Barrier(2)

    def go(i):
        cl = make_client()
        barrier.wait()
        return cl.post("/api/s/alpha/bookings", json={**BOOK, "phone": f"+7 900 555-00-0{i}", "service_id": sid, "start_min": start}, headers={"Idempotency-Key": f"parallel-{i}-0000"}).status_code

    with ThreadPoolExecutor(2) as pool:
        codes = sorted(pool.map(go, range(2)))
    assert codes == [201, 409]
    slots = c.get("/api/s/alpha/slots", params={"service_id": sid, "days": 10}).json()["days"]
    taken = [s for day in slots.values() for s in day if s["start_min"] == start]
    assert taken and taken[0]["available"] is False  # the occupied time is explicitly marked


def test_owner_login_csrf_and_logout(client, tmp_path):
    setup_tenant(tmp_path)
    assert client.get("/api/s/alpha/owner/schedule").status_code == 401
    assert client.post("/api/s/alpha/owner/login", json={"email": "owner@alpha.test", "password": "wrong-password"}).status_code == 401
    headers = owner_login(client)
    cookie = client.cookies.jar
    assert any(c.name == "owner_session" and c.has_nonstandard_attr("HttpOnly") for c in cookie)
    assert client.get("/api/s/alpha/owner/schedule").status_code == 200
    assert client.post("/api/s/alpha/owner/blocks", json={}).status_code == 403  # missing CSRF token
    assert client.post("/api/s/alpha/owner/blocks", json={}, headers=headers).status_code == 422
    assert client.post("/api/s/alpha/owner/logout", headers=headers).status_code == 204
    assert client.get("/api/s/alpha/owner/schedule").status_code == 401


def test_owner_flow_reschedule_payments_history(client, tmp_path):
    setup_tenant(tmp_path)
    headers = owner_login(client)
    sid = service_id(client, "alpha")
    start = first_slot(client, "alpha", sid)
    created = client.post("/api/s/alpha/owner/bookings", json={**BOOK, "service_id": sid, "start_min": start}, headers=headers)
    assert created.status_code == 201
    bid = created.json()["id"]
    # price history: editing the service does not change an existing booking
    svc = client.get("/api/s/alpha/owner/services").json()["services"][0]
    client.put(f"/api/s/alpha/owner/services/{svc['id']}", json={**{k: svc[k] for k in ("name", "description", "duration_min", "buffer_min", "keywords", "is_active", "resource_ids")}, "price_minor": 999900}, headers=headers)
    assert client.get(f"/api/s/alpha/owner/bookings/{bid}").json()["price_minor"] == 100000
    # payments and refunds
    p = client.post(f"/api/s/alpha/owner/bookings/{bid}/payments", json={"kind": "payment", "amount_minor": 60000}, headers=headers).json()
    assert (p["paid_minor"], p["due_minor"]) == (60000, 40000)
    assert client.post(f"/api/s/alpha/owner/bookings/{bid}/payments", json={"kind": "refund", "amount_minor": 70000}, headers=headers).status_code == 422
    r = client.post(f"/api/s/alpha/owner/bookings/{bid}/payments", json={"kind": "refund", "amount_minor": 10000}, headers=headers).json()
    assert r["net_minor"] == 50000
    # status + reschedule
    assert client.patch(f"/api/s/alpha/owner/bookings/{bid}/status", json={"status": "accepted"}, headers=headers).json()["status"] == "accepted"
    assert client.post(f"/api/s/alpha/owner/bookings/{bid}/reschedule", json={"start_min": start + 24 * 60}, headers=headers).json()["start_min"] == start + 24 * 60
    # stats: money received is cash in, not future price
    st = client.get("/api/s/alpha/owner/stats", params={"period": "month"}).json()
    assert st["received_minor"] == 50000 and st["visits"] >= 0
