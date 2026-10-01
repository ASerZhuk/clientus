import json
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app import tenants
from app.timeutil import dt_to_min

# A fixed "now" keeps every test deterministic: Monday 2030-01-07 08:00 UTC (11:00 Moscow).
NOW = dt_to_min(datetime(2030, 1, 7, 8, 0, tzinfo=timezone.utc))
DAY = 24 * 60
PWD = "correct horse battery"


def base_config(slug: str = "alpha", **over) -> dict:
    cfg = {
        "slug": slug,
        "plan": "domain",
        "name": f"Studio {slug}",
        "tagline": "Test studio",
        "phone": "+7 900 000-00-00",
        "address": "Test street 1",
        "timezone": "Europe/Moscow",
        "images": {"hero": "hero.jpg"},
        "info_cards": [{"title": f"Card {i}", "text": "text"} for i in range(3)],
        "booking": {"slot_step_min": 60, "lead_time_min": 60, "max_advance_days": 60, "cancel_before_hours": 24, "reminder_hours": 24},
        "hours": {d: ["09:00", "19:00"] for d in ("mon", "tue", "wed", "thu", "fri", "sat")} | {"sun": None},
        "resources": [{"key": "bay1", "name": "Bay 1"}],
        "services": [
            {"key": "wash", "name": "Мойка", "price": 1000, "duration_min": 120, "buffer_min": 30, "keywords": ["мойка"]},
            {"key": "ceramic", "name": "Керамика", "price": 50000, "duration_min": 2880, "buffer_min": 60},
        ],
    }
    cfg.update(over)
    return cfg


def publish(tmp_path: Path, slug: str = "alpha", *, activate: bool = True, **over) -> dict:
    root = tmp_path / "tenants" / slug
    root.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 300), (30, 60, 200)).save(root / "hero.jpg")
    (root / "business.json").write_text(json.dumps(base_config(slug, **over)), encoding="utf-8")
    return tenants.publish(root, activate=activate, seed_demo=False)


def local_start(day_offset: int, hour: int, tz: str = "Europe/Moscow") -> int:
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    from app.timeutil import local_date, local_to_min

    z = ZoneInfo(tz)
    return local_to_min(local_date(NOW, z) + timedelta(days=day_offset), hour * 60, z)
