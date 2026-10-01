from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import db as database
from app.models import Service, Tenant, TenantSettings
from app.services import slots
from app.timeutil import day_bounds, dt_to_min, min_to_dt
from tests.helpers import NOW, publish


def setup(tmp_path, **over):
    publish(tmp_path, **over)
    with database.read_session() as db:
        tid = db.scalar(select(Tenant.id))
    return tid


def window(tid, key, first, days=1, now=NOW):
    with database.read_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        svc = db.scalar(select(Service).where(Service.key == key))
        return settings.timezone, slots.compute_slots(db, settings, svc, first, days, now)


def hours(tz, items):
    return [min_to_dt(s.start_min, ZoneInfo(tz)).strftime("%H:%M") for s in items]


def test_start_moments_follow_hours_and_step(app_db, tmp_path):
    tid = setup(tmp_path)
    tz, w = window(tid, "wash", date(2030, 1, 9))  # Wednesday
    assert hours(tz, w["2030-01-09"]) == [f"{h:02d}:00" for h in range(9, 19)]
    _, sunday = window(tid, "wash", date(2030, 1, 13))
    assert sunday["2030-01-13"] == []


def test_exceptions_override_weekly_hours(app_db, tmp_path):
    tid = setup(tmp_path, exceptions=[{"date": "2030-01-09", "closed": True, "note": "x"}, {"date": "2030-01-10", "closed": False, "open": "12:00", "close": "14:00"},
                                      {"date": "2030-01-13", "closed": False, "open": "10:00", "close": "12:00"}])
    tz, w = window(tid, "wash", date(2030, 1, 9), days=5)
    assert w["2030-01-09"] == []
    assert hours(tz, w["2030-01-10"]) == ["12:00", "13:00"]
    assert hours(tz, w["2030-01-13"]) == ["10:00", "11:00"]  # a normally closed Sunday can open


def test_timezone_of_the_studio_decides_the_day(app_db, tmp_path):
    tid = setup(tmp_path, timezone="Asia/Yekaterinburg")
    tz, w = window(tid, "wash", date(2030, 1, 9))
    first = w["2030-01-09"][0].start_min
    assert min_to_dt(first, timezone.utc).strftime("%H:%M") == "04:00"  # 09:00 at UTC+5
    lo, hi = day_bounds(date(2030, 1, 9), ZoneInfo(tz))
    assert hi - lo == 24 * 60 and all(lo <= s.start_min < hi for s in w["2030-01-09"])


def test_dst_transition_day_has_23_hours_but_correct_local_times(app_db, tmp_path):
    tid = setup(tmp_path, timezone="Europe/Berlin", hours={d: ["00:00", "24:00"] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
                booking={"slot_step_min": 60, "lead_time_min": 0, "max_advance_days": 400, "cancel_before_hours": 1, "reminder_hours": 1})
    now = dt_to_min(datetime(2030, 3, 1, tzinfo=timezone.utc))
    tz, w = window(tid, "wash", date(2030, 3, 31), now=now)  # clocks jump 02:00 -> 03:00
    labels = hours(tz, w["2030-03-31"])
    assert "02:00" not in labels and "01:00" in labels and "03:00" in labels
    lo, hi = day_bounds(date(2030, 3, 31), ZoneInfo(tz))
    assert hi - lo == 23 * 60


def test_lead_time_past_and_horizon(app_db, tmp_path):
    tid = setup(tmp_path, booking={"slot_step_min": 60, "lead_time_min": 180, "max_advance_days": 3, "cancel_before_hours": 1, "reminder_hours": 1})
    tz, w = window(tid, "wash", date(2030, 1, 7), days=7)  # now = Mon 11:00 Moscow
    monday = {s.start_min: s.available for s in w["2030-01-07"]}
    avail_hours = [h for h, s in zip(hours(tz, w["2030-01-07"]), w["2030-01-07"]) if s.available]
    assert avail_hours[0] == "14:00"  # 11:00 + 3h lead time
    assert not any(s.available for s in w["2030-01-11"])  # beyond max_advance_days (3)
    assert any(s.available for s in w["2030-01-10"]) and monday


def test_validate_start_rejects_unlisted_moments(app_db, tmp_path):
    tid = setup(tmp_path)
    tz, w = window(tid, "wash", date(2030, 1, 9))
    ok = w["2030-01-09"][0].start_min
    with database.read_session(tid) as db:
        settings = db.scalar(select(TenantSettings))
        assert slots.validate_start(db, settings, ok, NOW) is None
        assert slots.validate_start(db, settings, ok + 30, NOW) == "outside_working_hours"
        assert slots.validate_start(db, settings, ok + 1, NOW) == "time_not_aligned"
        assert slots.validate_start(db, settings, NOW - 60, NOW) == "in_the_past"
        assert slots.validate_start(db, settings, ok + 24 * 60 * 90, NOW) == "too_far"
        assert slots.validate_start(db, settings, ok + 30, NOW, outside_hours=True) is None
