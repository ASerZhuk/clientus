from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import cli
from app import db as database
from app import tenants
from app.config import get_settings
from app.main import app
from app.models import AuditLog, Booking, OwnerSession, Tenant, TenantDomain, now_s
from app.services import domains, subscription
from tests.api_helpers import BOOK, first_slot, owner_login, service_id, setup_tenant
from tests.helpers import PWD, publish

DAY = 86400


def T(**kw):
    base = dict(status="active", suspended=False, trial_ends_at=None, paid_until=None, plan="standard")
    return SimpleNamespace(**(base | kw))


# --------------------------------------------------------------- lifecycle
def test_subscription_state_machine():
    now = 1_800_000_000
    s = lambda **kw: subscription.state_of(T(**kw), now)  # noqa: E731
    assert s(status="preview", trial_ends_at=now - 99 * DAY) == "preview"  # samples are never enforced
    assert s(status="disabled") == "disabled"
    assert s(trial_ends_at=now + DAY) == "trial"
    assert s(paid_until=now + DAY, trial_ends_at=now - DAY) == "active"
    assert s() == "active"  # activated with no dates: lifetime (the one-time purchase)
    assert s(trial_ends_at=now - DAY) == "past_due"  # grace period keeps the studio working
    assert s(trial_ends_at=now - 8 * DAY) == "suspended"
    assert s(paid_until=now - 3 * DAY, trial_ends_at=now - 30 * DAY) == "past_due"
    assert s(paid_until=now - 9 * DAY) == "suspended"
    assert s(paid_until=now + 30 * DAY, suspended=True) == "suspended"  # the operator's manual switch wins
    assert subscription.booking_enabled(T(trial_ends_at=now - DAY), now) and not subscription.booking_enabled(T(suspended=True), now)


def set_tenant(slug, **fields):
    with database.write_session() as db:
        t = db.scalar(select(Tenant).where(Tenant.slug == slug))
        for k, v in fields.items():
            setattr(t, k, v)


def book(client, slug, phone, offset=0):
    sid = service_id(client, slug)
    return client.post(f"/api/s/{slug}/bookings", json={**BOOK, "phone": phone, "service_id": sid, "start_min": first_slot(client, slug, sid, days=20) + offset}, headers={"Idempotency-Key": f"k-{phone}-{offset}0000"})


def test_suspended_studio_is_read_only_but_data_stays(client, tmp_path):
    setup_tenant(tmp_path)
    h = owner_login(client)
    assert client.get("/api/s/alpha").json()["booking_enabled"] is True
    set_tenant("alpha", suspended=True)
    cfg = client.get("/api/s/alpha").json()
    assert cfg["booking_enabled"] is False and cfg["subscription_state"] == "suspended" and cfg["services"]
    r = book(client, "alpha", "+7 900 000-00-01")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "studio_suspended"
    assert client.get("/api/s/alpha/owner/schedule").status_code == 200  # can still look
    blocked = client.post("/api/s/alpha/owner/blocks", json={"resource_id": 1, "start_min": 1, "end_min": 2}, headers=h)
    assert blocked.status_code == 402 and blocked.json()["detail"]["code"] == "studio_suspended"
    assert client.get("/api/s/alpha/owner/me").json()["subscription"]["state"] == "suspended"
    assert client.post("/api/s/alpha/owner/logout", headers=h).status_code == 204  # leaving is always possible
    set_tenant("alpha", suspended=False)
    assert book(client, "alpha", "+7 900 000-00-02").status_code == 201


def test_grace_period_still_takes_bookings(client, tmp_path):
    setup_tenant(tmp_path)
    set_tenant("alpha", trial_ends_at=now_s() - 2 * DAY, paid_until=None)
    assert client.get("/api/s/alpha").json()["subscription_state"] == "past_due"
    assert book(client, "alpha", "+7 900 000-00-03").status_code == 201
    set_tenant("alpha", trial_ends_at=now_s() - 30 * DAY)
    assert book(client, "alpha", "+7 900 000-00-04").status_code == 402


def test_plan_limits_resources_and_bookings(client, tmp_path, monkeypatch):
    plans_file = tmp_path / "plans.json"
    plans_file.write_text('{"standard": {"max_resources": 2, "max_bookings_month": 2}}')
    monkeypatch.setenv("PLANS_FILE", str(plans_file))
    get_settings.cache_clear()
    publish(tmp_path, "alpha", plan="standard", resources=[{"key": "b1", "name": "B1"}, {"key": "b2", "name": "B2"}])
    tenants.create_owner("alpha", "owner@alpha.test", PWD)
    h = owner_login(client)
    r = client.post("/api/s/alpha/owner/resources", json={"name": "Third"}, headers=h)
    assert r.status_code == 402 and r.json()["detail"] == {"code": "plan_limit_resources", "limit": 2, "plan": "standard"}
    assert book(client, "alpha", "+7 900 000-01-01").status_code == 201  # two bays: the same time fits twice
    assert book(client, "alpha", "+7 900 000-01-02").status_code == 201
    third = book(client, "alpha", "+7 900 000-01-03")
    assert third.status_code == 402 and third.json()["detail"]["code"] == "plan_limit_bookings"
    with database.read_session() as db:
        assert len(list(db.scalars(select(Booking)))) == 2
    sid = service_id(client, "alpha")
    owner_try = client.post("/api/s/alpha/owner/bookings", json={**BOOK, "service_id": sid, "start_min": first_slot(client, "alpha", sid, days=20)}, headers=h)
    assert owner_try.status_code == 402 and owner_try.json()["detail"]["code"] == "plan_limit_bookings"  # the owner cannot bypass it
    get_settings.cache_clear()


def test_branding_is_removed_only_for_the_self_hosted_package(client, tmp_path):
    publish(tmp_path, "cheap", plan="standard")
    publish(tmp_path, "pricey", plan="domain")
    publish(tmp_path, "own", plan="self_hosted")
    a, b, c = (client.get(f"/api/s/{x}").json()["branding"] for x in ("cheap", "pricey", "own"))
    assert a["show"] is True and a["name"] and b["show"] is True and c["show"] is False  # a domain alone keeps the line


# ----------------------------------------------------------------- domains
def test_domain_normalisation_and_rules():
    assert domains.normalize_host("https://Book.Example.COM/path?x=1") == "book.example.com"
    for bad in ("localhost", "127.0.0.1", "example", "a b.com", "-x.com", "x..com", "book.example.com:8080", "", "https://"):
        with pytest.raises(domains.DomainError):
            domains.normalize_host(bad)


def test_domain_add_verify_resolve(app_db, tmp_path, monkeypatch):
    publish(tmp_path, "alpha", plan="standard")
    publish(tmp_path, "beta", plan="domain")
    with database.write_session() as db:
        alpha = db.scalar(select(Tenant).where(Tenant.slug == "alpha"))
        beta = db.scalar(select(Tenant).where(Tenant.slug == "beta"))
        with pytest.raises(domains.DomainError) as e:
            domains.add_domain(db, alpha, "alpha.example.com")
        assert e.value.code == "plan_no_custom_domain"
        d = domains.add_domain(db, beta, "Book.Beta.com")
        with pytest.raises(domains.DomainError) as e:
            domains.add_domain(db, alpha, "book.beta.com", force=True)
        assert e.value.code == "domain_taken"
    with database.read_session() as db:
        assert domains.resolve(db, "book.beta.com") is None  # pending domains serve nothing
    monkeypatch.setenv("PLATFORM_IPS", "203.0.113.10")
    get_settings.cache_clear()
    monkeypatch.setattr(domains.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("203.0.113.10", 0))])
    check = domains.dns_check("book.beta.com")
    assert check["ok"] and check["expected"] == ["203.0.113.10"]
    monkeypatch.setattr(domains.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("198.51.100.7", 0))])
    assert not domains.dns_check("book.beta.com")["ok"]
    with database.write_session() as db:
        domains.activate(db, db.get(TenantDomain, d.id))
    with database.read_session() as db:
        assert domains.resolve(db, "BOOK.beta.com") == ("beta", "active")
        assert domains.resolve(db, "book.alpha.com") is None
    get_settings.cache_clear()


def test_internal_endpoints_are_not_public(app_db, tmp_path, monkeypatch):
    publish(tmp_path, "beta", plan="domain")
    with database.write_session() as db:
        beta = db.scalar(select(Tenant).where(Tenant.slug == "beta"))
        domains.activate(db, domains.add_domain(db, beta, "book.beta.com"))
    web = TestClient(app)
    tok = {"X-Internal-Token": get_settings().internal_token}
    assert web.get("/api/internal/host", params={"host": "book.beta.com"}).status_code == 403  # no token
    assert web.get("/api/internal/host", params={"host": "book.beta.com"}, headers={"X-Internal-Token": "wrong"}).status_code == 403
    assert web.get("/api/internal/host", params={"host": "book.beta.com"}, headers=tok).json() == {"slug": "beta", "status": "active"}
    assert web.get("/api/internal/host", params={"host": "evil.com"}, headers=tok).status_code == 404
    assert web.get("/api/internal/tls-allowed", params={"domain": "book.beta.com"}).status_code == 403  # not from loopback
    caddy = TestClient(app, client=("127.0.0.1", 5555))
    assert caddy.get("/api/internal/tls-allowed", params={"domain": "book.beta.com"}).status_code == 200
    assert caddy.get("/api/internal/tls-allowed", params={"domain": "evil.com"}).status_code == 404
    set_tenant("beta", status="disabled")
    assert caddy.get("/api/internal/tls-allowed", params={"domain": "book.beta.com"}).status_code == 404  # taken offline


# ------------------------------------------------------------ admin panel
def operator(client):
    tenants.create_operator("boss@platform.test", "long operator password")
    r = client.post("/api/admin/login", json={"email": "boss@platform.test", "password": "long operator password"})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def test_admin_requires_its_own_session_and_csrf(client, tmp_path):
    setup_tenant(tmp_path)
    assert client.get("/api/admin/overview").status_code == 401
    owner_login(client)  # a studio owner is not an operator
    assert client.get("/api/admin/overview").status_code == 401
    assert client.post("/api/admin/login", json={"email": "boss@platform.test", "password": "nope-nope-nope"}).status_code == 401
    h = operator(client)
    assert client.get("/api/admin/overview").status_code == 200
    assert client.patch("/api/admin/tenants/alpha/subscription", json={"plan": "domain"}).status_code == 403  # CSRF
    assert client.patch("/api/admin/tenants/alpha/subscription", json={"plan": "domain"}, headers={**h, "Origin": "https://evil.example"}).status_code == 403
    assert client.patch("/api/admin/tenants/alpha/subscription", json={"plan": "domain", "extra": 1}, headers=h).status_code == 422


def test_admin_overview_subscription_status_and_audit(client, tmp_path):
    setup_tenant(tmp_path, "alpha")
    publish(tmp_path, "sample", activate=False)
    h = operator(client)
    ov = client.get("/api/admin/overview").json()
    rows = {r["slug"]: r for r in ov["tenants"]}
    assert ov["tenants_total"] == 2 and rows["alpha"]["owners"] == ["owner@alpha.test"] and rows["sample"]["state"] == "preview"
    up = client.patch("/api/admin/tenants/alpha/subscription", json={"plan": "standard", "add_paid_days": 30, "notes": "invoice 17"}, headers=h).json()
    assert up["plan"] == "standard" and up["state"] == "active" and 29 <= up["days_left"] <= 30 and up["notes"] == "invoice 17"
    assert client.patch("/api/admin/tenants/alpha/subscription", json={"plan": "gold"}, headers=h).status_code == 422
    sus = client.patch("/api/admin/tenants/alpha/subscription", json={"suspended": True}, headers=h).json()
    assert sus["state"] == "suspended"
    ov = client.get("/api/admin/overview").json()
    assert ov["by_state"]["suspended"] == 1 and ov["sales_total_minor"] == 350000 and ov["live_total"] == 1  # one live studio sold as the standard package
    # a sample cannot go live without an owner; with an owner it starts a trial and drops demo rows
    assert client.post("/api/admin/tenants/sample/status", json={"status": "active"}, headers=h).status_code == 409
    pw = client.post("/api/admin/tenants/sample/owner", json={"email": "New@Sample.test"}, headers=h).json()
    assert pw["email"] == "new@sample.test" and len(pw["password"]) >= 12
    live = client.post("/api/admin/tenants/sample/status", json={"status": "active"}, headers=h).json()
    assert live["state"] == "active" and live["days_left"] is None  # lifetime: no trial, no end date
    detail = client.get("/api/admin/tenants/alpha").json()
    assert {a["action"] for a in detail["audit"]} >= {"subscription"} and detail["audit"][0]["actor"] == "boss@platform.test"
    # the generated owner password really works, and only for that studio
    other = TestClient(app)
    assert other.post("/api/s/sample/owner/login", json={"email": "new@sample.test", "password": pw["password"]}).status_code == 200
    assert other.post("/api/s/alpha/owner/login", json={"email": "new@sample.test", "password": pw["password"]}).status_code == 401


def test_admin_impersonation_opens_the_owner_cabinet_and_is_audited(client, tmp_path):
    setup_tenant(tmp_path, "alpha")
    h = operator(client)
    assert client.get("/api/s/alpha/owner/schedule").status_code == 401
    assert client.post("/api/admin/tenants/alpha/impersonate", headers=h).status_code == 200
    assert client.get("/api/s/alpha/owner/schedule").status_code == 200
    assert client.get("/api/s/alpha/owner/me").json()["email"] == "owner@alpha.test"
    with database.read_session() as db:
        assert [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))][-1] == "impersonate"
        assert len(list(db.scalars(select(OwnerSession)))) == 1


def test_admin_domain_flow_and_login_rate_limit(client, tmp_path, monkeypatch):
    publish(tmp_path, "alpha", plan="domain")
    h = operator(client)
    r = client.post("/api/admin/tenants/alpha/domains", json={"host": "https://Book.Alpha.ru/"}, headers=h)
    assert r.status_code == 201 and r.json()["host"] == "book.alpha.ru" and r.json()["status"] == "pending"
    did = r.json()["id"]
    assert client.post("/api/admin/tenants/alpha/domains", json={"host": "book.alpha.ru"}, headers=h).status_code == 409
    assert client.post("/api/admin/tenants/alpha/domains", json={"host": "localhost"}, headers=h).status_code == 422
    monkeypatch.setattr(domains.socket, "getaddrinfo", lambda *a, **k: [])
    assert client.post(f"/api/admin/domains/{did}/verify", json={}, headers=h).json()["status"] == "pending"  # DNS not ready
    assert client.post(f"/api/admin/domains/{did}/verify", json={"force": True}, headers=h).json()["status"] == "active"
    assert client.get("/api/admin/overview").json()["tenants"][0]["domains"] == [{"id": did, "host": "book.alpha.ru", "status": "active"}]
    assert client.delete(f"/api/admin/domains/{did}", headers=h).status_code == 204
    fresh = TestClient(app)
    codes = [fresh.post("/api/admin/login", json={"email": "boss@platform.test", "password": "wrong-password-1"}).status_code for _ in range(8)]
    assert codes[:5] == [401] * 5 and codes[5:] == [429, 429, 429]  # the operator login above used one of the six attempts


def test_cli_domain_and_plan_commands(app_db, tmp_path, capsys):
    publish(tmp_path, "alpha", plan="domain")
    assert cli.main(["domain:add", "alpha", "book.alpha.ru"]) == 0
    assert cli.main(["domain:add", "alpha", "book.alpha.ru"]) == 1  # taken
    assert cli.main(["domain:verify", "book.alpha.ru"]) == 1  # PLATFORM_IPS not configured -> not provable
    assert cli.main(["domain:verify", "book.alpha.ru", "--force"]) == 0
    capsys.readouterr()
    assert cli.main(["domain:list"]) == 0 and "book.alpha.ru" in capsys.readouterr().out
    assert cli.main(["plan:set", "alpha", "--plan", "domain", "--paid-days", "30"]) == 0 and "state active" in capsys.readouterr().out
    assert cli.main(["plan:set", "alpha", "--suspend"]) == 0 and "state suspended" in capsys.readouterr().out
    assert cli.main(["plan:set", "alpha", "--plan", "gold"]) == 1
    assert cli.main(["domain:remove", "book.alpha.ru"]) == 0
