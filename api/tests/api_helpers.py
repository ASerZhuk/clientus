from app import tenants
from tests.helpers import PWD, publish


def owner_login(client, slug="alpha", email=None):
    email = email or f"owner@{slug}.test"
    r = client.post(f"/api/s/{slug}/owner/login", json={"email": email, "password": PWD})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def setup_tenant(tmp_path, slug="alpha", **over):
    publish(tmp_path, slug, **over)
    tenants.create_owner(slug, f"owner@{slug}.test", PWD)


def first_slot(client, slug, service_id, days=10):
    data = client.get(f"/api/s/{slug}/slots", params={"service_id": service_id, "days": days}).json()
    for day in sorted(data["days"]):
        for s in data["days"][day]:
            if s["available"]:
                return s["start_min"]
    raise AssertionError("no free slot")


def service_id(client, slug, key_name="Мойка"):
    return next(s["id"] for s in client.get(f"/api/s/{slug}").json()["services"] if s["name"] == key_name)


BOOK = {"name": "Иван", "phone": "+7 900 111-22-33", "car": "BMW X5", "plate": "a123bc"}
