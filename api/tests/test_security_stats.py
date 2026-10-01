from datetime import timedelta

from sqlalchemy import select

from app import cli
from app import db as database
from app.models import Tenant, TenantSettings
from app.services import stats
from app.timeutil import local_date, now_min, tz_of
from tests.api_helpers import BOOK, first_slot, owner_login, service_id, setup_tenant


def test_login_and_booking_are_rate_limited(client, tmp_path):
    setup_tenant(tmp_path)
    codes = [client.post("/api/s/alpha/owner/login", json={"email": "owner@alpha.test", "password": "bad-password-1"}).status_code for _ in range(10)]
    assert codes[:8] == [401] * 8 and codes[8:] == [429, 429]
    assert "retry-after" in client.post("/api/s/alpha/owner/login", json={"email": "owner@alpha.test", "password": "x"}).headers
    sid = service_id(client, "alpha")
    start = first_slot(client, "alpha", sid)
    got = [client.post("/api/s/alpha/bookings", json={**BOOK, "phone": f"+7 900 000-00-{i:02d}", "service_id": sid, "start_min": start + 60 * (i % 3)}, headers={"Idempotency-Key": f"rate-key-{i:04d}"}).status_code for i in range(12)]
    assert 429 in got and got.index(429) == 10


def test_cross_site_origin_is_refused_even_with_a_valid_csrf_token(client, tmp_path):
    setup_tenant(tmp_path)
    headers = owner_login(client)
    body = {"resource_id": 1, "start_min": 1, "end_min": 2}
    evil = client.post("/api/s/alpha/owner/blocks", json=body, headers={**headers, "Origin": "https://evil.example"})
    assert evil.status_code == 403 and evil.json()["detail"] == "bad_origin"
    same = client.post("/api/s/alpha/owner/blocks", json=body, headers={**headers, "Origin": "http://testserver"})
    assert same.status_code != 403
    proxied = client.post("/api/s/alpha/owner/blocks", json=body, headers={**headers, "Origin": "https://studio.example", "X-Forwarded-Host": "studio.example"})
    assert proxied.status_code != 403


def test_session_cookie_flags(client, tmp_path):
    setup_tenant(tmp_path)
    r = client.post("/api/s/alpha/owner/login", json={"email": "owner@alpha.test", "password": "correct horse battery"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/api/s/alpha/owner" in cookie
    assert client.get("/api/s/alpha/owner/me").headers["cache-control"] == "no-store"


def test_stats_separate_visits_completed_money_and_future_value(client, tmp_path):
    setup_tenant(tmp_path)
    h = owner_login(client)
    sid = service_id(client, "alpha")
    first = first_slot(client, "alpha", sid, days=14)
    ids = []
    for i in range(3):
        r = client.post("/api/s/alpha/owner/bookings", json={**BOOK, "phone": f"+7 900 000-00-0{i}", "service_id": sid, "start_min": first + i * 24 * 60, "outside_hours": True}, headers=h)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    client.patch(f"/api/s/alpha/owner/bookings/{ids[0]}/status", json={"status": "ready"}, headers=h)
    client.post(f"/api/s/alpha/owner/bookings/{ids[0]}/payments", json={"kind": "payment", "amount_minor": 100000}, headers=h)
    client.post(f"/api/s/alpha/owner/bookings/{ids[0]}/payments", json={"kind": "refund", "amount_minor": 20000}, headers=h)
    client.post(f"/api/s/alpha/owner/bookings/{ids[2]}/cancel", headers=h)
    with database.read_session() as db:
        tid = db.scalar(select(Tenant.id))
        db.info["tenant_id"] = tid
        tz = tz_of(db.scalar(select(TenantSettings)).timezone)
        today = local_date(now_min(), tz)
        st = stats.compute(db, tz, today, today + timedelta(days=12), now_min())
    # 3 bookings made, one cancelled -> 2 visits; 1 marked ready; money is cash in minus refund; the future one is "scheduled", not revenue
    assert (st["visits"], st["completed"], st["cancelled"]) == (2, 1, 1)
    assert st["received_minor"] == 80000 and st["refunds_minor"] == 20000
    assert st["scheduled_value_minor"] == 100000  # ids[1] still to come


def test_vapid_generate_writes_key_and_prints_public_key(tmp_path, capsys):
    out = tmp_path / "v.pem"
    assert cli.main(["vapid:generate", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert out.read_text().startswith("-----BEGIN") and oct(out.stat().st_mode)[-3:] == "600"
    pub = next(line for line in text.splitlines() if line.startswith("VAPID_PUBLIC_KEY=")).split("=", 1)[1]
    assert len(pub) >= 86
    assert cli.main(["vapid:generate", "--out", str(out)]) == 1  # never overwrites silently
