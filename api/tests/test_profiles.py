import json
from datetime import date

import pytest
from sqlalchemy import select

from app import db as database
from app import tenants
from app.models import Booking, ResourceOccupancy, Service, Tenant, TenantSettings
from app.services import booking as bk
from app.services import slots
from app.timeutil import local_to_min, tz_of
from tests.api_helpers import BOOK, owner_login, setup_tenant
from tests.helpers import NOW, base_config, publish

WEEK = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def hrs(**days):
    return {d: days.get(d) for d in WEEK}


def salon(**over):
    cfg = {
        "business_type": "beauty_studio",
        "hours": {d: ["10:00", "20:00"] for d in WEEK[:6]} | {"sun": None},
        "resources": [
            {"key": "anna", "name": "Анна", "description": "Стилист", "hours": hrs(mon=["10:00", "18:00"], tue=["10:00", "18:00"], wed=["10:00", "18:00"])},
            {"key": "olga", "name": "Ольга", "description": "Маникюр", "hours": hrs(thu=["12:00", "20:00"], fri=["12:00", "20:00"], sat=["12:00", "20:00"])},
        ],
        "services": [
            {"key": "cut", "name": "Стрижка", "price": 2500, "duration_min": 60, "buffer_min": 0, "resources": ["anna", {"key": "olga", "price": 1800, "duration_min": 75}]},
            {"key": "gel", "name": "Гель", "price": 2000, "duration_min": 90, "buffer_min": 15, "resources": ["olga"]},
        ],
    }
    cfg.update(over)
    return cfg


def ctx_for(slug="alpha"):
    with database.read_session() as db:
        t = db.scalar(select(Tenant).where(Tenant.slug == slug))
        db.info["tenant_id"] = t.id
        return t.id


def day_slots(tid, key, day: date, resource_id=None):
    with database.read_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        svc = db.scalar(select(Service).where(Service.key == key))
        return settings, slots.compute_slots(db, settings, svc, day, 1, NOW, only_resource_id=resource_id)[day.isoformat()]


def hhmm(settings, m):
    from app.timeutil import min_to_dt

    return min_to_dt(m, tz_of(settings.timezone)).strftime("%H:%M")


def make(tmp_path, **over):
    publish(tmp_path, **salon(**over))
    return ctx_for()


# ------------------------------------------------------------------ validation
def bad(tmp_path, slug, **over):
    root = tmp_path / "tenants" / slug
    root.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    Image.new("RGB", (50, 50)).save(root / "hero.jpg")
    (root / "business.json").write_text(json.dumps(base_config(slug, **over)), encoding="utf-8")
    with pytest.raises(tenants.ConfigProblem) as e:
        tenants.validate(root)
    return " ".join(e.value.problems)


def test_profile_rules_are_validated(tmp_path):
    assert "business_type" in bad(tmp_path, "a1", business_type="spa")
    assert "at most 1" in bad(tmp_path, "a2", business_type="beauty_master", resources=[{"key": "a", "name": "A"}, {"key": "b", "name": "B"}])
    assert "own hours are not available" in bad(tmp_path, "a3", business_type="auto", resources=[{"key": "bay", "name": "B", "hours": hrs(mon=["09:00", "18:00"])}])
    assert "multi-day" in bad(tmp_path, "a4", business_type="wash", services=[{"key": "x", "name": "X", "price": 1, "duration_min": 2880}])
    assert "per-resource price" in bad(tmp_path, "a5", business_type="auto", services=[{"key": "x", "name": "X", "price": 1, "duration_min": 60, "resources": [{"key": "bay1", "price": 5}]}])
    assert "list the masters" in bad(tmp_path, "a6", **salon(services=[{"key": "x", "name": "X", "price": 1, "duration_min": 60}]))
    assert "unknown resource" in bad(tmp_path, "a7", **salon(services=[{"key": "x", "name": "X", "price": 1, "duration_min": 60, "resources": ["ghost"]}]))
    assert "close must be after open" in bad(tmp_path, "a8", **salon(resources=[{"key": "anna", "name": "A", "hours": hrs(mon=["18:00", "10:00"])}]))


# ------------------------------------------------------------ per-master hours
def test_each_master_has_own_moments_and_union_is_offered(app_db, tmp_path):
    tid = make(tmp_path)
    settings, monday = day_slots(tid, "cut", date(2030, 1, 14))  # Monday: only Anna works
    assert hhmm(settings, monday[0].start_min) == "10:00" and hhmm(settings, monday[-1].start_min) == "17:00"
    assert {rid for s in monday for rid in s.resource_ids} == {monday[0].resource_ids[0]}
    settings, thursday = day_slots(tid, "cut", date(2030, 1, 10))  # Thursday: only Olga (12:00-20:00)
    assert hhmm(settings, thursday[0].start_min) == "12:00" and hhmm(settings, thursday[-1].start_min) == "19:00"
    _, sunday = day_slots(tid, "cut", date(2030, 1, 13))
    assert sunday == []  # nobody works and the studio is closed
    with database.read_session(tid) as db:
        assert [r.name for r in slots.service_resources(db, db.scalar(select(Service.id).where(Service.key == "gel")))] == ["Ольга"]


def test_booking_checks_the_chosen_masters_hours(app_db, tmp_path):
    tid = make(tmp_path)
    monday = local_to_min(date(2030, 1, 14), 11 * 60, tz_of("Europe/Moscow"))
    with database.read_session(tid) as db:
        anna, olga = [r for r in slots.service_resources(db, db.scalar(select(Service.id).where(Service.key == "cut")))]

    def book(resource_id=None, start=monday, key="cut"):
        with database.write_session(tid) as db:
            settings = db.scalar(select(TenantSettings))
            svc = db.scalar(select(Service).where(Service.key == key))
            return bk.create_booking(db, tenant_id=tid, settings=settings, is_preview=False, service_id=svc.id, start_min=start, name="K", phone="+7 900 000-00-01", now_min=NOW, resource_id=resource_id).booking

    with pytest.raises(bk.BookingError) as e:
        book(olga.id)  # Olga does not work on Mondays
    assert e.value.code == "outside_working_hours"
    assert book(None).resource_id == anna.id  # "any free master" resolves to the one who works
    with pytest.raises(bk.BookingError) as e:
        book(anna.id, key="gel")  # Anna does not perform 'gel'
    assert e.value.code == "resource_not_suitable"


def test_exceptions_precedence(app_db, tmp_path):
    cfg = salon(
        exceptions=[{"date": "2030-01-16", "closed": True, "note": "studio holiday"}],  # Wednesday: studio closed
        resources=[
            {"key": "anna", "name": "Анна", "hours": hrs(mon=["10:00", "18:00"], tue=["10:00", "18:00"], wed=["10:00", "18:00"]),
             "exceptions": [{"date": "2030-01-15", "closed": True, "note": "vacation"}, {"date": "2030-01-13", "closed": False, "open": "11:00", "close": "13:00", "note": "extra shift"}]},
            {"key": "olga", "name": "Ольга", "hours": hrs(thu=["12:00", "20:00"])},
        ],
    )
    publish(tmp_path, **cfg)
    tid = ctx_for()
    _, tue = day_slots(tid, "cut", date(2030, 1, 15))
    assert tue == []  # Anna's own day off
    _, wed = day_slots(tid, "cut", date(2030, 1, 16))
    assert wed == []  # studio holiday closes everyone
    settings, sun = day_slots(tid, "cut", date(2030, 1, 13))  # Sunday, studio closed, but Anna has an extra shift
    assert [hhmm(settings, s.start_min) for s in sun] == ["11:00", "12:00"]


def test_resource_without_own_hours_uses_studio_hours(app_db, tmp_path):
    tid = make(tmp_path, resources=[{"key": "anna", "name": "Анна"}, {"key": "olga", "name": "Ольга", "hours": hrs(sat=["12:00", "14:00"])}])
    settings, monday = day_slots(tid, "cut", date(2030, 1, 14))
    assert hhmm(settings, monday[0].start_min) == "10:00" and hhmm(settings, monday[-1].start_min) == "19:00"  # studio hours


# ---------------------------------------------------------- price / duration
def test_master_price_and_duration_are_snapshotted_into_the_booking(app_db, tmp_path):
    tid = make(tmp_path)
    thursday = local_to_min(date(2030, 1, 10), 13 * 60, tz_of("Europe/Moscow"))
    with database.write_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        svc = db.scalar(select(Service).where(Service.key == "cut"))
        b = bk.create_booking(db, tenant_id=tid, settings=settings, is_preview=False, service_id=svc.id, start_min=thursday, name="K", phone="+7 900 000-00-02", now_min=NOW).booking
        occ = db.scalar(select(ResourceOccupancy).where(ResourceOccupancy.booking_id == b.id))
        assert (b.price_minor, b.end_min - b.start_min) == (180000, 75)  # Olga's own price and duration
        assert occ.end_min - occ.start_min == 75  # 75 + 0 buffer, already on the 15-minute grid
    with database.read_session(tid) as db:
        assert slots.compute_slots(db, db.scalar(select(TenantSettings)), db.scalar(select(Service).where(Service.key == "cut")), date(2030, 1, 10), 1, NOW)


# --------------------------------------------------------------------- API
def test_api_exposes_masters_only_where_customers_choose(client, tmp_path):
    publish(tmp_path, "salon", **salon())
    tenants.create_owner("salon", "boss@salon.test", "correct horse battery")
    setup_tenant(tmp_path, "shop")  # auto profile
    cfg = client.get("/api/s/salon").json()
    assert cfg["business_type"] == "beauty_studio" and cfg["profile"]["features"]["choose_resource"] is True
    assert [r["name"] for r in cfg["resources"]] == ["Анна", "Ольга"]
    cut = next(s for s in cfg["services"] if s["name"] == "Стрижка")
    assert cut["price_varies"] and cut["price_minor"] == 180000 and len(cut["offers"]) == 2
    auto = client.get("/api/s/shop").json()
    assert auto["business_type"] == "auto" and auto["resources"] == [] and "offers" not in auto["services"][0]
    assert auto["profile"]["contact"]["car"] == "required"


def test_customer_picks_a_master_and_sees_only_that_masters_time(client, tmp_path):
    publish(tmp_path, "salon", **salon())
    cfg = client.get("/api/s/salon").json()
    cut = next(s for s in cfg["services"] if s["name"] == "Стрижка")
    anna, olga = cfg["resources"][0]["id"], cfg["resources"][1]["id"]
    days = client.get("/api/s/salon/slots", params={"service_id": cut["id"], "days": 14, "resource_id": olga}).json()["days"]
    for day, items in days.items():
        wd = date.fromisoformat(day).weekday()
        assert (not items) or wd in (3, 4, 5)  # Thu/Fri/Sat only
        assert all(s["resource_ids"] == [olga] for s in items if s["available"])
    free = next(s for items in days.values() for s in items if s["available"])
    ok = client.post("/api/s/salon/bookings", json={"name": "Мила", "phone": "+7 900 123-45-67", "service_id": cut["id"], "start_min": free["start_min"], "resource_id": olga}, headers={"Idempotency-Key": "salon-key-0001"})
    assert ok.status_code == 201 and ok.json()["booking"]["price_minor"] == 180000  # no car needed in a salon
    wrong = client.post("/api/s/salon/bookings", json={"name": "Мила", "phone": "+7 900 123-45-67", "service_id": cut["id"], "start_min": free["start_min"], "resource_id": anna}, headers={"Idempotency-Key": "salon-key-0002"})
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "outside_working_hours"


def test_auto_profile_rejects_master_choice_and_requires_a_car(client, tmp_path):
    setup_tenant(tmp_path, "shop")
    svc = client.get("/api/s/shop").json()["services"][0]["id"]
    days = client.get("/api/s/shop/slots", params={"service_id": svc, "days": 10}).json()["days"]
    start = next(s["start_min"] for items in days.values() for s in items if s["available"])
    assert "resource_ids" not in next(iter(next(iter(days.values())) or [{}]), {})
    base = {"name": "Иван", "phone": "+7 900 111-22-33", "service_id": svc, "start_min": start}
    r = client.post("/api/s/shop/bookings", json={**base, "car": "BMW", "resource_id": 1}, headers={"Idempotency-Key": "shop-key-0001"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "resource_choice_not_allowed"
    r = client.post("/api/s/shop/bookings", json={**base}, headers={"Idempotency-Key": "shop-key-0002"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "car_required"
    assert client.post("/api/s/shop/bookings", json={**base, "car": "BMW"}, headers={"Idempotency-Key": "shop-key-0003"}).status_code == 201


def test_owner_manages_masters_schedule_and_offers(client, tmp_path):
    publish(tmp_path, "salon", **salon())
    tenants.create_owner("salon", "boss@salon.test", "correct horse battery")
    h = owner_login(client, "salon", "boss@salon.test")
    cat = client.get("/api/s/salon/owner/services").json()
    anna = cat["resources"][0]
    assert cat["profile"]["type"] == "beauty_studio" and anna["has_own_hours"] and anna["hours_edit"][0]["open_min"] == 600
    # extend Anna's week and add a vacation
    days = [{"weekday": d, "is_closed": False, "open_min": 600, "close_min": 1080} for d in range(0, 5)]
    r = client.put(f"/api/s/salon/owner/resources/{anna['id']}/schedule", json={"days": days, "exceptions": [{"date": "2030-02-01", "is_closed": True, "note": "отпуск"}]}, headers=h)
    assert r.status_code == 200 and r.json()["exceptions"][0]["note"] == "отпуск" and r.json()["hours_edit"][4]["is_closed"] is False and r.json()["hours_edit"][5]["is_closed"] is True
    assert client.put(f"/api/s/salon/owner/resources/{anna['id']}/schedule", json={"use_studio_hours": True}, headers=h).json()["has_own_hours"] is False
    # per-master price
    cut = next(s for s in cat["services"] if s["name"] == "Стрижка")
    offers = [{"resource_id": anna["id"], "price_minor": 300000}, {"resource_id": cat["resources"][1]["id"]}]
    body = {"name": cut["name"], "description": "", "price_minor": 250000, "duration_min": 60, "buffer_min": 0, "offers": offers}
    upd = client.put(f"/api/s/salon/owner/services/{cut['id']}", json=body, headers=h).json()
    assert {o["resource_id"]: o["price_minor"] for o in upd["offers"]}[anna["id"]] == 300000
    # a new master starts with no services, and can be given a description
    new = client.post("/api/s/salon/owner/resources", json={"name": "Ирина", "description": "Бровист"}, headers=h).json()
    assert new["description"] == "Бровист" and client.get("/api/s/salon/owner/services").json()["services"][0]["resource_ids"].count(new["id"]) == 0


def test_features_are_enforced_by_profile(client, tmp_path):
    setup_tenant(tmp_path, "shop")
    h = owner_login(client, "shop")
    cat = client.get("/api/s/shop/owner/services").json()
    bay = cat["resources"][0]["id"]
    assert client.put(f"/api/s/shop/owner/resources/{bay}/schedule", json={"use_studio_hours": True}, headers=h).status_code == 403
    svc = cat["services"][0]
    body = {"name": svc["name"], "description": "", "price_minor": 1000, "duration_min": 60, "buffer_min": 0, "offers": [{"resource_id": bay, "price_minor": 5}]}
    r = client.put(f"/api/s/shop/owner/services/{svc['id']}", json=body, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "feature_disabled"
    # the private master profile is limited to one resource
    publish(tmp_path, "solo", business_type="beauty_master", resources=[{"key": "me", "name": "Анна"}], services=[{"key": "m", "name": "Маникюр", "price": 1800, "duration_min": 90}])
    tenants.create_owner("solo", "anna@solo.test", "correct horse battery")
    h2 = owner_login(client, "solo", "anna@solo.test")
    r = client.post("/api/s/solo/owner/resources", json={"name": "Второй"}, headers=h2)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "resource_limit"


def test_starter_kits_are_valid_for_every_type(tmp_path, app_db):
    from app import profiles

    for t in profiles.TYPES:
        cfg = profiles.starter_config(t, f"kit-{t.replace('_', '-')}", "Kit")
        root = tmp_path / "tenants" / cfg["slug"]
        root.mkdir(parents=True)
        from PIL import Image

        for name in ["hero.jpg", *[g["image"] for g in cfg["gallery"]]] + [f"{r['key']}.jpg" for r in cfg["resources"]]:
            Image.new("RGB", (40, 40)).save(root / name)
        for r in cfg["resources"]:
            if profiles.get_profile(t).kind == "person":
                r["photo"] = f"{r['key']}.jpg"
        cfg["images"] = {"hero": "hero.jpg"}
        (root / "business.json").write_text(json.dumps(cfg), encoding="utf-8")
        tenants.validate(root)
        tenants.publish(root, activate=True, seed_demo=False)


def test_assistant_lists_masters_only_where_they_are_public(client, tmp_path):
    publish(tmp_path, "salon", **salon())
    setup_tenant(tmp_path, "shop")
    r = client.post("/api/s/salon/assistant", json={"text": "Какие мастера принимают?"}).json()
    assert r["status"] == "answered" and "Анна" in r["text"] and "Стилист" in r["text"] or "Анна" in r["text"]
    assert "Какие мастера принимают?" in client.get("/api/s/salon/assistant/examples").json()["examples"]
    assert client.post("/api/s/shop/assistant", json={"text": "Какие мастера принимают?"}).json()["status"] == "unknown"
