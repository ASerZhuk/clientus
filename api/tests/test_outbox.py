from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app import db as database
from app.config import get_settings
from app.models import Booking, NotificationJob, PushSubscription, Tenant, TenantSettings
from app.services import booking as bk
from app.services import push
from tests.api_helpers import setup_tenant
from tests.helpers import NOW, local_start
from tests.test_booking_core import book, ctx


@pytest.fixture(autouse=True)
def vapid(monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setenv("VAPID_PRIVATE_KEY_PATH", "/nonexistent.pem")
    get_settings.cache_clear()


def jobs(tid):
    with database.read_session(tid) as db:
        return list(db.scalars(select(NotificationJob).order_by(NotificationJob.id)))


def add_sub(tid, audience, booking_id=None, endpoint="https://push.example/abc"):
    with database.write_session(tid) as db:
        db.add(PushSubscription(tenant_id=tid, audience=audience, booking_id=booking_id, endpoint=endpoint, p256dh="p" * 20, auth="a" * 10))


class Recorder:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    def __call__(self, sub, payload):
        if self.fail:
            raise self.fail
        self.sent.append((sub["endpoint"], payload))


def test_booking_writes_owner_and_reminder_jobs_once(app_db, tmp_path):
    setup_tenant(tmp_path)
    tid = ctx()
    bid, _ = book(tid, "wash", local_start(3, 10), key="ob-key-0001")
    book(tid, "wash", local_start(3, 10), key="ob-key-0001")  # idempotent replay adds nothing
    kinds = sorted((j.audience, j.kind) for j in jobs(tid))
    assert kinds == [("client", "reminder"), ("owner", "new")]
    reminder = next(j for j in jobs(tid) if j.kind == "reminder")
    assert reminder.run_at == (local_start(3, 10) - 24 * 60) * 60 and reminder.dedupe_key == f"reminder:{bid}:{local_start(3, 10)}"


def test_unsold_studio_notifies_like_a_live_one(app_db, tmp_path):
    """A studio sent to a prospect before purchase works for real: the prospect tries it and gets the pushes."""
    setup_tenant(tmp_path)
    tid = ctx()
    with database.write_session() as db:
        db.get(Tenant, tid).status = "preview"
    with database.write_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        from app.models import Service

        svc = db.scalar(select(Service))
        bk.create_booking(db, tenant_id=tid, settings=settings, is_preview=True, service_id=svc.id, start_min=local_start(3, 10), name="D", phone="+7 900 000-00-00", now_min=NOW)
    assert {j.kind for j in jobs(tid)} >= {"new", "reminder"}


def test_worker_delivers_owner_and_client_pushes(app_db, tmp_path):
    setup_tenant(tmp_path)
    tid = ctx()
    bid, _ = book(tid, "wash", local_start(3, 10))
    add_sub(tid, "owner", endpoint="https://push.example/owner")
    add_sub(tid, "client", booking_id=bid, endpoint="https://push.example/client")
    rec = Recorder()
    far = (local_start(3, 10)) * 60
    assert push.run_once(rec, now=far - 3600) == {"sent": 2}
    assert {e for e, _ in rec.sent} == {"https://push.example/owner", "https://push.example/client"}
    assert {j.status for j in jobs(tid)} == {"sent"}
    assert push.run_once(rec, now=far) == {}  # nothing is sent twice


def test_leases_do_not_overlap_between_workers(app_db, tmp_path):
    setup_tenant(tmp_path)
    tid = ctx()
    for i in range(6):
        book(tid, "wash", local_start(2 + i // 2, 10 + i % 2 * 3), name=f"C{i}", phone=f"+7 900 000-00-0{i}")
    now = local_start(9, 0) * 60
    with ThreadPoolExecutor(3) as pool:
        batches = list(pool.map(lambda _: push.lease_due(4, now), range(3)))
    flat = [i for b in batches for i in b]
    assert len(flat) == len(set(flat)) == 12  # 6 bookings x (owner new + reminder), each leased exactly once


def test_expired_lease_is_reclaimed(app_db, tmp_path):
    setup_tenant(tmp_path)
    tid = ctx()
    book(tid, "wash", local_start(3, 10))
    now = local_start(3, 10) * 60
    first = push.lease_due(10, now)
    assert first and push.lease_due(10, now) == []
    assert sorted(push.lease_due(10, now + push.LEASE_SECONDS + 1)) == sorted(first)  # crashed worker: lease expired


def test_cancel_skips_reminder_and_notifies_owner(app_db, tmp_path):
    setup_tenant(tmp_path)
    tid = ctx()
    bid, _ = book(tid, "wash", local_start(3, 10))
    with database.write_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        bk.cancel_booking(db, tenant_id=tid, settings=settings, is_preview=False, booking_id=bid, by="client", now_min=NOW)
    by_kind = {j.kind: j for j in jobs(tid)}
    assert by_kind["reminder"].status == "skipped" and by_kind["cancelled"].audience == "owner"
    add_sub(tid, "owner")
    rec = Recorder()
    push.run_once(rec, now=local_start(3, 10) * 60)
    titles = [p["notification"]["title"] for _, p in rec.sent]
    assert "Запись отменена" in titles and "Напоминание о записи" not in titles


def test_reschedule_replaces_reminder_and_notifies_client(app_db, tmp_path):
    setup_tenant(tmp_path)
    tid = ctx()
    bid, _ = book(tid, "wash", local_start(3, 10))
    with database.write_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        bk.reschedule_booking(db, tenant_id=tid, settings=settings, is_preview=False, booking_id=bid, new_start_min=local_start(5, 12), now_min=NOW)
    jl = jobs(tid)
    old = next(j for j in jl if j.dedupe_key.endswith(str(local_start(3, 10))) and j.kind == "reminder")
    new = next(j for j in jl if j.kind == "reminder" and j.dedupe_key.endswith(str(local_start(5, 12))))
    assert old.status == "skipped" and new.status == "pending"
    assert any(j.kind == "moved" and j.audience == "client" for j in jl)


def test_dead_subscription_disabled_and_transient_errors_retry(app_db, tmp_path):
    setup_tenant(tmp_path)
    tid = ctx()
    bid, _ = book(tid, "wash", local_start(3, 10))
    add_sub(tid, "owner")
    far = local_start(3, 10) * 60 - 3600
    push.run_once(Recorder(push.PushGone()), now=far)
    with database.read_session(tid) as db:
        assert db.scalar(select(PushSubscription)).disabled_at is not None
    add_sub(tid, "owner", endpoint="https://push.example/second")
    with database.write_session(tid) as db:  # a fresh job for the retry scenario
        from app.services import outbox

        outbox.enqueue(db, tid, booking_id=bid, audience="owner", kind="new", dedupe_key="new:retry")
    result = push.run_once(Recorder(RuntimeError("push service down")), now=far)
    assert result == {"pending": 1}
    job = next(j for j in jobs(tid) if j.dedupe_key == "new:retry")
    assert job.status == "pending" and job.attempts == 1 and job.run_at > far and "down" in job.last_error


def test_no_vapid_means_honest_skip(app_db, tmp_path, monkeypatch):
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "")
    get_settings.cache_clear()
    setup_tenant(tmp_path)
    tid = ctx()
    book(tid, "wash", local_start(3, 10))
    add_sub(tid, "owner")
    push.run_once(now=local_start(3, 10) * 60)
    assert {j.status for j in jobs(tid)} == {"skipped"} and jobs(tid)[0].last_error == "push_not_configured"


def test_one_device_as_client_then_owner_keeps_both_subscriptions_apart(client, tmp_path):
    """A phone that enabled a booking reminder is not thereby subscribed as the owner, and the owner switching
    notifications off does not silence the client's reminder on the same device."""
    from tests.api_helpers import BOOK, first_slot, owner_login, service_id

    setup_tenant(tmp_path)
    sid = service_id(client, "alpha")
    r = client.post("/api/s/alpha/bookings", json={**BOOK, "service_id": sid, "start_min": first_slot(client, "alpha", sid)}, headers={"Idempotency-Key": "device-key-0001"})
    mine = {"X-Booking-Token": r.json()["access_token"]}
    device = {"endpoint": "https://fcm.example/send/device-1", "keys": {"p256dh": "p" * 20, "auth": "a" * 10}}
    q = {"endpoint": device["endpoint"]}

    assert client.post("/api/s/alpha/my/push", json=device, headers=mine).status_code == 204
    assert client.get("/api/s/alpha/my/push", params=q, headers=mine).json() == {"on": True}
    csrf = owner_login(client)
    assert client.get("/api/s/alpha/owner/push", params=q).json() == {"on": False}  # the cabinet must offer "enable"

    assert client.post("/api/s/alpha/owner/push", json=device, headers=csrf).status_code == 204
    assert client.get("/api/s/alpha/owner/push", params=q).json() == {"on": True}
    assert client.delete("/api/s/alpha/owner/push", params=q, headers=csrf).status_code == 204
    assert client.get("/api/s/alpha/owner/push", params=q).json() == {"on": False}
    assert client.get("/api/s/alpha/my/push", params=q, headers=mine).json() == {"on": True}  # reminder untouched


def test_delivery_health_badge_rotation_and_device_list(client, tmp_path):
    from tests.api_helpers import BOOK, first_slot, owner_login, service_id

    setup_tenant(tmp_path)
    tid = ctx()
    csrf = owner_login(client)
    phone = {"endpoint": "https://fcm.example/send/owner-phone", "keys": {"p256dh": "p" * 20, "auth": "a" * 10}}
    android = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36", "Origin": "http://localhost:3000"}
    assert client.post("/api/s/alpha/owner/push", json=phone, headers={**csrf, **android}).status_code == 204

    sid = service_id(client, "alpha")
    r = client.post("/api/s/alpha/bookings", json={**BOOK, "service_id": sid, "start_min": first_slot(client, "alpha", sid)}, headers={"Idempotency-Key": "badge-key-00001"})
    mine = {"X-Booking-Token": r.json()["access_token"]}
    rec = Recorder()
    push.run_once(rec)
    owner_push = next(p for e, p in rec.sent if e == phone["endpoint"])
    assert owner_push["web_push"] == 8030 and owner_push["mutable"] is True and owner_push["kind"] == "new"  # declarative for Safari
    assert owner_push["notification"]["app_badge"] == 1  # one client booking not seen yet
    assert owner_push["notification"]["navigate"].endswith("/s/alpha/owner") and owner_push["notification"]["navigate"].startswith("http")

    devices = client.get("/api/s/alpha/owner/push/devices", params={"endpoint": phone["endpoint"]}).json()["devices"]
    assert len(devices) == 1 and devices[0]["device"] == "Android · Chrome" and devices[0]["this_device"]
    assert devices[0]["last_success_at"] and devices[0]["failure_count"] == 0

    # the owner opens the schedule: everything so far is seen
    assert client.post("/api/s/alpha/owner/seen", headers=csrf).json() == {"badge": 0}
    from app.models import Membership

    with database.read_session() as db:
        m = db.scalar(select(Membership))
        uid, seen = m.user_id, m.seen_at
    with database.read_session(tid) as db:
        assert push.unseen_for_owners(db, tid, {uid})[uid] == 0
    with database.write_session(tid) as db:  # a booking made after that moment counts again
        db.scalar(select(Booking)).created_at = seen + 10
    with database.read_session(tid) as db:
        assert push.unseen_for_owners(db, tid, {uid})[uid] == 1

    # the browser replaces the subscription: the owner and the client reminder both move to the new endpoint
    client_sub = {**phone}
    assert client.post("/api/s/alpha/my/push", json=client_sub, headers=mine).status_code == 204
    new = {"endpoint": "https://fcm.example/send/owner-phone-2", "keys": {"p256dh": "q" * 20, "auth": "b" * 10}}
    assert client.post("/api/s/alpha/push/rotate", json={"old_endpoint": phone["endpoint"], "subscription": new}).status_code == 204
    assert client.get("/api/s/alpha/owner/push", params={"endpoint": new["endpoint"]}).json() == {"on": True}
    assert client.get("/api/s/alpha/my/push", params={"endpoint": new["endpoint"]}, headers=mine).json() == {"on": True}
    assert client.get("/api/s/alpha/owner/push", params={"endpoint": phone["endpoint"]}).json() == {"on": False}

    # a failed delivery is counted; switching a device off removes it from the list
    dev_id = client.get("/api/s/alpha/owner/push/devices").json()["devices"][0]["id"]
    push.record_delivery({dev_id: "push service timeout"})
    dev = client.get("/api/s/alpha/owner/push/devices").json()["devices"][0]
    assert dev["failure_count"] == 1 and dev["last_error"] == "push service timeout"
    assert client.delete(f"/api/s/alpha/owner/push/devices/{dev_id}", headers=csrf).status_code == 204
    assert client.get("/api/s/alpha/owner/push/devices").json()["devices"] == []


def test_declarative_payload_links_to_the_site_the_device_subscribed_on():
    msg = {"title": "Новая запись", "body": "пт, 10:00", "url": "/s/alpha/owner", "tag": "new-1", "kind": "new"}
    platform = push.declarative(msg, "http://localhost:3000", "alpha", badge=2)
    assert platform == {
        "web_push": 8030, "mutable": True, "kind": "new",
        "notification": {"title": "Новая запись", "body": "пт, 10:00", "navigate": "http://localhost:3000/s/alpha/owner", "lang": "ru", "dir": "ltr", "tag": "new-1", "app_badge": 2},
    }
    own = push.declarative(msg, "https://book.alpha.ru", "alpha")  # a studio's own domain serves it at the root
    assert own["notification"]["navigate"] == "https://book.alpha.ru/owner" and "app_badge" not in own["notification"]
