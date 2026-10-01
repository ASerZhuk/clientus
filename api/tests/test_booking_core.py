from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app import db as database
from app.models import Booking, OccupancyCell, ResourceOccupancy, Service, Tenant, TenantSettings
from app.services import booking as bk
from tests.helpers import NOW, local_start, publish


def ctx(slug="alpha"):
    with database.read_session() as db:
        t = db.scalar(select(Tenant).where(Tenant.slug == slug))
        db.info["tenant_id"] = t.id
        return t.id


def book(tid, service_key, start, name="Ivan", phone="+7 900 111-22-33", key=None, resource_id=None, source="client"):
    with database.write_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        svc = db.scalar(select(Service).where(Service.key == service_key))
        res = bk.create_booking(
            db, tenant_id=tid, settings=settings, is_preview=False, service_id=svc.id, start_min=start, name=name,
            phone=phone, now_min=NOW, idempotency_key=key, resource_id=resource_id, source=source,
        )
        return res.booking.id, res.created


def test_parallel_requests_only_one_wins(app_db, tmp_path):
    publish(tmp_path)
    tid = ctx()
    start = local_start(2, 10)
    barrier = Barrier(4)

    def attempt(i):
        barrier.wait()
        try:
            return book(tid, "wash", start, name=f"C{i}", phone=f"+7 900 000-00-0{i}")
        except bk.BookingError as e:
            return e.code

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert sum(isinstance(r, tuple) for r in results) == 1
    assert results.count("slot_unavailable") == 3
    with database.read_session(tid) as db:
        assert db.scalar(select(func.count()).select_from(Booking)) == 1


def test_db_unique_cell_index_blocks_overlap_even_without_check(app_db, tmp_path):
    publish(tmp_path)
    tid = ctx()
    book(tid, "wash", local_start(2, 10))
    from sqlalchemy.exc import IntegrityError

    with database.write_session(tid) as db:
        occ = db.scalar(select(ResourceOccupancy))
        cell = db.scalar(select(OccupancyCell).where(OccupancyCell.occupancy_id == occ.id))
        with pytest.raises(IntegrityError):
            db.execute(OccupancyCell.__table__.insert().values(resource_id=cell.resource_id, cell=cell.cell, tenant_id=tid, occupancy_id=occ.id))


def test_two_resources_take_two_bookings_then_full(app_db, tmp_path):
    publish(tmp_path, resources=[{"key": "bay1", "name": "Bay 1"}, {"key": "bay2", "name": "Bay 2"}])
    tid = ctx()
    start = local_start(2, 10)
    a, _ = book(tid, "wash", start, name="A", phone="+7 900 000-00-01")
    b, _ = book(tid, "wash", start, name="B", phone="+7 900 000-00-02")
    with database.read_session(tid) as db:
        rids = {x.resource_id for x in db.scalars(select(Booking))}
    assert len(rids) == 2
    with pytest.raises(bk.BookingError) as e:
        book(tid, "wash", start, name="C", phone="+7 900 000-00-03")
    assert e.value.code == "slot_unavailable"


def test_multi_day_service_occupies_every_day(app_db, tmp_path):
    publish(tmp_path)
    tid = ctx()
    book(tid, "ceramic", local_start(1, 10))  # 2 days + 60 min buffer, from Tue 10:00
    for offset, hour, ok in [(1, 15, False), (2, 10, False), (2, 18, False), (3, 9, False), (3, 12, True), (0, 15, True)]:
        try:
            book(tid, "wash", local_start(offset, hour), name=f"x{offset}{hour}", phone=f"+7 91{offset}{hour:02d}00000")
            assert ok, f"day+{offset} {hour}:00 should be occupied"
        except bk.BookingError as e:
            assert not ok and e.code == "slot_unavailable"


def test_block_and_booking_share_one_table(app_db, tmp_path):
    publish(tmp_path)
    tid = ctx()
    with database.write_session(tid) as db:
        from app.models import Resource

        rid = db.scalar(select(Resource.id))
        bk.create_block(db, tenant_id=tid, resource_id=rid, start_min=local_start(2, 9), end_min=local_start(2, 13), note="repair")
    with pytest.raises(bk.BookingError):
        book(tid, "wash", local_start(2, 11))
    book(tid, "wash", local_start(2, 13))
    with database.read_session(tid) as db:
        kinds = sorted(o.kind for o in db.scalars(select(ResourceOccupancy)))
    assert kinds == ["block", "booking"]
    with database.write_session(tid) as db, pytest.raises(bk.BookingError) as e:
        bk.create_block(db, tenant_id=tid, resource_id=rid, start_min=local_start(2, 12), end_min=local_start(2, 15), note="clash")
    assert e.value.code == "slot_unavailable"


def test_failed_reschedule_keeps_original(app_db, tmp_path):
    publish(tmp_path)
    tid = ctx()
    first, _ = book(tid, "wash", local_start(2, 10), name="A", phone="+7 900 000-00-01")
    second, _ = book(tid, "wash", local_start(3, 10), name="B", phone="+7 900 000-00-02")
    with pytest.raises(bk.BookingError):
        with database.write_session(tid) as db:
            settings = db.scalar(select(TenantSettings))
            bk.reschedule_booking(db, tenant_id=tid, settings=settings, is_preview=False, booking_id=second, new_start_min=local_start(2, 10), now_min=NOW)
    with database.read_session(tid) as db:
        b = db.get(Booking, second)
        occ = db.scalar(select(ResourceOccupancy).where(ResourceOccupancy.booking_id == second))
        assert b.start_min == local_start(3, 10) and occ.start_min == b.start_min
        cells = db.scalar(select(func.count()).select_from(OccupancyCell).where(OccupancyCell.occupancy_id == occ.id))
        assert cells == (occ.end_min - occ.start_min) // 15
    # a valid move works and frees the old time
    with database.write_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        bk.reschedule_booking(db, tenant_id=tid, settings=settings, is_preview=False, booking_id=second, new_start_min=local_start(4, 12), now_min=NOW)
    book(tid, "wash", local_start(3, 10), name="C", phone="+7 900 000-00-03")


def test_idempotent_create_returns_same_booking(app_db, tmp_path):
    publish(tmp_path)
    tid = ctx()
    start = local_start(2, 10)
    first, created1 = book(tid, "wash", start, key="k-1")
    again, created2 = book(tid, "wash", start, key="k-1")
    assert first == again and created1 and not created2
    with pytest.raises(bk.BookingError) as e:
        book(tid, "wash", local_start(2, 15), key="k-1")
    assert e.value.code == "idempotency_key_reused"
    with database.read_session(tid) as db:
        assert db.scalar(select(func.count()).select_from(Booking)) == 1


def test_cancel_frees_slot_and_respects_window(app_db, tmp_path):
    publish(tmp_path)
    tid = ctx()
    soon, _ = book(tid, "wash", local_start(0, 14), name="S", phone="+7 900 000-00-01")  # 3h away: inside 24h window
    far, _ = book(tid, "wash", local_start(3, 10), name="F", phone="+7 900 000-00-02")
    with database.write_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        with pytest.raises(bk.BookingError) as e:
            bk.cancel_booking(db, tenant_id=tid, settings=settings, is_preview=False, booking_id=soon, by="client", now_min=NOW)
        assert e.value.code == "cancel_window_closed"
        bk.cancel_booking(db, tenant_id=tid, settings=settings, is_preview=False, booking_id=far, by="client", now_min=NOW)
    book(tid, "wash", local_start(3, 10), name="N", phone="+7 900 000-00-03")
