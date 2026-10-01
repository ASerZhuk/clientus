"""Packages sold once (no subscriptions yet). A plan decides only two things: whether the studio may use its
own domain and whether the «Работает на …» line is shown. There are no usage limits.

  standard    3 500 ₽  studio on our platform, cabinet, «Работает на …» shown
  domain      4 000 ₽  the same + the studio's own domain
  self_hosted 7 000 ₽  installed on the customer's own server, no «Работает на …»

Prices are the sale prices used by the operator panel. Override without code with PLANS_FILE (JSON), e.g.
{"standard": {"price_minor": 390000}}. Limit fields exist for a future subscription model and are unlimited (None) now."""
import json
from dataclasses import dataclass, replace
from pathlib import Path

from .config import get_settings


@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    price_minor: int  # one-time sale price
    max_resources: int | None  # posts / boxes / masters (None = unlimited)
    max_bookings_month: int | None
    custom_domain: bool
    remove_branding: bool  # hide «Работает на …»


_DEFAULTS: dict[str, Plan] = {
    "standard": Plan("standard", "Стандарт", 350000, None, None, False, False),
    "domain": Plan("domain", "Свой домен", 400000, None, None, True, False),
    "self_hosted": Plan("self_hosted", "Свой сервер", 700000, None, None, True, True),
}

DAY = 86400


def all_plans() -> dict[str, Plan]:
    plans = dict(_DEFAULTS)
    path = get_settings().plans_file
    if path and Path(path).is_file():
        for key, patch in json.loads(Path(path).read_text(encoding="utf-8")).items():
            if key in plans:
                plans[key] = replace(plans[key], **patch)
    return plans


def get_plan(key: str | None) -> Plan:
    """Unknown/legacy keys behave like the standard package."""
    return all_plans().get(key or "standard", _DEFAULTS["standard"])
