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


def test_preview_tenant_sends_nothing(app_db, tmp_path):
    setup_tenant(tmp_path)
    tid = ctx()
    with database.write_session() as db:
        db.get(Tenant, tid).status = "preview"
    with database.write_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        from app.models import Service

        svc = db.scalar(select(Service))
        bk.create_booking(db, tenant_id=tid, settings=settings, is_preview=True, service_id=svc.id, start_min=local_start(3, 10), name="D", phone="+7 900 000-00-00", now_min=NOW)
    assert jobs(tid) == []


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
    titles = [p["title"] for _, p in rec.sent]
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
