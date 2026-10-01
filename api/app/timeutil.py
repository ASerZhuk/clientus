"""Time helpers. Instants are stored as UTC epoch *minutes*; calendar logic
(working hours, 'today', period boundaries) always uses the tenant's timezone."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import CELL_MINUTES


def tz_of(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def now_min() -> int:
    return int(datetime.now(timezone.utc).timestamp() // 60)


def dt_to_min(dt: datetime) -> int:
    return int(dt.timestamp() // 60)


def min_to_dt(m: int, tz: ZoneInfo) -> datetime:
    return datetime.fromtimestamp(m * 60, tz=timezone.utc).astimezone(tz)


def local_to_min(d: date, minute_of_day: int, tz: ZoneInfo) -> int:
    base = datetime.combine(d, time(0), tzinfo=tz)
    # wall-clock arithmetic: add to the naive time, then attach the zone
    wall = datetime.combine(d, time(0)) + timedelta(minutes=minute_of_day)
    return dt_to_min(wall.replace(tzinfo=tz)) if minute_of_day < 1440 else dt_to_min(base + timedelta(days=1))


def day_bounds(d: date, tz: ZoneInfo) -> tuple[int, int]:
    """[start, end) of a local calendar day in UTC minutes (23/25h on DST days)."""
    return local_to_min(d, 0, tz), local_to_min(d + timedelta(days=1), 0, tz)


def local_date(m: int, tz: ZoneInfo) -> date:
    return min_to_dt(m, tz).date()


def local_minute_of_day(m: int, tz: ZoneInfo) -> int:
    dt = min_to_dt(m, tz)
    return dt.hour * 60 + dt.minute


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def ceil_cells(minutes: int) -> int:
    return -(-minutes // CELL_MINUTES) * CELL_MINUTES


def cells_for(start_min: int, end_min: int) -> range:
    return range(start_min // CELL_MINUTES, -(-end_min // CELL_MINUTES))
