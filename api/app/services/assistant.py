"""Assistants without an LLM.

The text is parsed into an intent (services/intents.py); the answer is built only from
database facts, fetched through a small set of server functions. The two audiences use
different capability objects:

  * PublicReads  - what any visitor can already see (services, prices, free time, address).
                   It has no method that reads clients, bookings or payments.
  * OwnerReads   - schedule, counts, money. Read-only: there is no write method here.

A client request is parsed with the client rule set only, so an owner intent cannot even
be recognised on that endpoint."""
from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Booking, Client, Payment, Resource, Service, TenantSettings, WorkingHours
from ..profiles import get_profile
from ..timeutil import day_bounds, local_date, min_to_dt, tz_of
from . import intents, llm, stats
from .slots import compute_slots, next_available

WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WEEKDAYS_LONG = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
CURRENCY = {"RUB": "₽", "USD": "$", "EUR": "€", "KZT": "₸", "BYN": "Br", "UAH": "₴"}
PERIOD_TITLES = {
    "today": "сегодня", "tomorrow": "завтра", "yesterday": "вчера", "week": "на этой неделе",
    "last_week": "на прошлой неделе", "month": "в этом месяце", "last_month": "в прошлом месяце",
}
PERIOD_CHIPS = [("Сегодня", "today"), ("Эта неделя", "week"), ("Этот месяц", "month")]

CLIENT_EXAMPLES_MASTERS = ["Записаться на ближайшее время", "Хочу записаться на завтра", "Какие мастера принимают?", "Как найти студию?"]
CLIENT_EXAMPLES = ["Записаться на ближайшее время", "Хочу записаться на завтра", "Записаться на выходные", "Как найти студию?"]
OWNER_EXAMPLES = ["Что у меня завтра?", "Сколько машин было на неделе?", "Сколько денег получено?", "Кто не оплатил?"]


def money(minor: int, currency: str) -> str:
    whole = f"{minor / 100:,.2f}".rstrip("0").rstrip(".").replace(",", " ") if minor % 100 else f"{minor // 100:,}".replace(",", " ")
    return f"{whole} {CURRENCY.get(currency, currency)}"


def when_text(start_min: int, tz: ZoneInfo, today: date) -> str:
    dt = min_to_dt(start_min, tz)
    d = dt.date()
    day = "сегодня" if d == today else "завтра" if d == today + timedelta(days=1) else f"{WEEKDAYS_SHORT[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"
    return f"{day} в {dt:%H:%M}"


def day_title(d: date, today: date) -> str:
    label = {0: "Сегодня", 1: "Завтра", -1: "Вчера"}.get((d - today).days)
    base = f"{WEEKDAYS_LONG[d.weekday()]}, {d.day} {MONTHS_GEN[d.month - 1]}"
    return f"{label} ({base})" if label else base.capitalize()


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n10, n100 = n % 10, n % 100
    form = forms[0] if n10 == 1 and n100 != 11 else forms[1] if 2 <= n10 <= 4 and not 12 <= n100 <= 14 else forms[2]
    return f"{n} {form}"


# ------------------------------------------------------------------ capabilities
class PublicReads:
    """Everything a visitor may know. No client, booking or payment access."""

    def __init__(self, db: Session, settings: TenantSettings, now_min: int):
        self.db, self.settings, self.now_min = db, settings, now_min
        self.tz = tz_of(settings.timezone)
        self.today = local_date(now_min, self.tz)

    def services(self) -> list[Service]:
        return list(self.db.scalars(select(Service).where(Service.is_active.is_(True)).order_by(Service.sort, Service.id)))

    def masters(self) -> list[Resource]:
        """Only for profiles where masters are public (salons, private masters)."""
        if not get_profile(self.settings.business_type).features["resource_profiles"]:
            return []
        return list(self.db.scalars(select(Resource).where(Resource.is_active.is_(True)).order_by(Resource.sort, Resource.id)))

    def service(self, service_id: int) -> Service | None:
        return self.db.scalar(select(Service).where(Service.id == service_id, Service.is_active.is_(True)))

    def next_slot(self, service: Service):
        return next_available(self.db, self.settings, service, self.now_min)

    def free_slots(self, service: Service, d: date) -> list[int]:
        return [s.start_min for s in compute_slots(self.db, self.settings, service, d, 1, self.now_min)[d.isoformat()] if s.available]

    def working_hours(self) -> list[WorkingHours]:
        return list(self.db.scalars(select(WorkingHours).order_by(WorkingHours.weekday)))


class OwnerReads:
    """Read-only owner facts. Deliberately has no methods that modify anything."""

    def __init__(self, db: Session, settings: TenantSettings, now_min: int):
        self.db, self.settings, self.now_min = db, settings, now_min
        self.tz = tz_of(settings.timezone)
        self.today = local_date(now_min, self.tz)

    def stats(self, period: str | None = None, day: date | None = None) -> dict:
        if day:
            first, after = day, day + timedelta(days=1)
        else:
            first, after = stats.period_dates(period or "today", self.tz, self.now_min)
        return stats.compute(self.db, self.tz, first, after, self.now_min)

    def bookings_between(self, first: date, after: date) -> list[dict]:
        lo, _ = day_bounds(first, self.tz)
        hi, _ = day_bounds(after, self.tz)
        rows = self.db.execute(
            select(Booking, Client.name).join(Client, Client.id == Booking.client_id)
            .where(Booking.start_min >= lo, Booking.start_min < hi, Booking.status != "cancelled").order_by(Booking.start_min)
        ).all()
        return [{"start_min": b.start_min, "service": b.service_name, "client": name, "car": b.car, "status": b.status} for b, name in rows]

    def next_booking(self) -> dict | None:
        row = self.db.execute(
            select(Booking, Client.name).join(Client, Client.id == Booking.client_id)
            .where(Booking.start_min >= self.now_min, Booking.status.in_(("booked", "accepted"))).order_by(Booking.start_min).limit(1)
        ).first()
        if not row:
            return None
        b, name = row
        return {"start_min": b.start_min, "service": b.service_name, "client": name, "car": b.car}

    def unpaid(self) -> list[dict]:
        paid = (
            select(Payment.booking_id, func.sum(func.iif(Payment.kind == "payment", Payment.amount_minor, -Payment.amount_minor)).label("net"))
            .group_by(Payment.booking_id).subquery()
        )
        rows = self.db.execute(
            select(Booking, Client.name, func.coalesce(paid.c.net, 0))
            .join(Client, Client.id == Booking.client_id).outerjoin(paid, paid.c.booking_id == Booking.id)
            .where(Booking.status.in_(("accepted", "ready")), Booking.price_minor > func.coalesce(paid.c.net, 0))
            .order_by(Booking.start_min.desc()).limit(10)
        ).all()
        return [{"client": n, "service": b.service_name, "due_minor": b.price_minor - int(net), "start_min": b.start_min} for b, n, net in rows]


# ------------------------------------------------------------------- answers
@dataclass
class Reply:
    status: str  # answered | clarify | unknown
    text: str
    intent: str | None = None
    options: list[dict] | None = None  # clickable follow-ups: {label, text, context}
    items: list[dict] | None = None
    action: dict | None = None  # e.g. {"type": "book", "service_id": 3, "start_min": ...}

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def _service_options(intent: str, services: list[Service]) -> list[dict]:
    return [{"label": s.name, "text": s.name, "context": {"intent": intent, "service_id": s.id}} for s in services[:8]]


def client_examples(business_type: str | None) -> list[str]:
    return CLIENT_EXAMPLES_MASTERS if get_profile(business_type).features["resource_profiles"] else CLIENT_EXAMPLES


def _unknown(examples: list[str]) -> Reply:
    return Reply("unknown", "Не совсем понял вопрос. Выберите пример или спросите иначе.",
                 options=[{"label": e, "text": e, "context": {}} for e in examples])


def _choose_service(reads: PublicReads, parsed: intents.Parsed, ctx: dict, intent: str) -> tuple[Service | None, Reply | None]:
    services = reads.services()
    if isinstance(ctx.get("service_id"), int):
        found = reads.service(ctx["service_id"])
        if found:
            return found, None
    candidates = [s for s in services if s.id in parsed.service_ids]
    if len(candidates) == 1:
        return candidates[0], None
    if len(services) == 1:
        return services[0], None
    pool = candidates or services
    question = "Уточните, какая именно услуга?" if candidates else "По какой услуге?"
    return None, Reply("clarify", question, intent, options=_service_options(intent, pool))


def _client_answer(intent: str, parsed: intents.Parsed, ctx: dict, reads: PublicReads) -> Reply:
    s, cur = reads.settings, reads.settings.currency
    if intent == "help":
        return Reply("answered", "Я отвечаю про услуги, цены, свободное время и как нас найти. Спросите или нажмите пример.",
                     intent, options=[{"label": e, "text": e, "context": {}} for e in client_examples(reads.settings.business_type)])
    if intent == "masters":
        masters = reads.masters()
        if not masters:
            return _unknown(client_examples(reads.settings.business_type))
        lines = [f"• {m.name}" + (f" — {m.description}" if m.description else "") for m in masters]
        return Reply("answered", "У нас принимают:\n" + "\n".join(lines), intent, items=[{"name": m.name, "description": m.description} for m in masters])
    if intent == "services_list":
        items = [{"name": v.name, "price": money(v.price_minor, cur), "duration_min": v.duration_min} for v in reads.services()]
        text = "Наши услуги:\n" + "\n".join(f"• {i['name']} — {i['price']}" for i in items) if items else "Пока нет доступных услуг."
        return Reply("answered", text + ("\nВыберите услугу — покажу цену и время." if items else ""), intent, items=items, options=_service_options("price", reads.services()) if items else None)
    if intent == "address":
        text = f"Мы находимся по адресу: {s.address}." if s.address else "Адрес пока не указан."
        return Reply("answered", text + (f" Карта: {s.map_url}" if s.map_url else ""), intent)
    if intent == "phone":
        return Reply("answered", f"Телефон студии: {s.phone}." if s.phone else "Телефон пока не указан.", intent)
    if intent == "hours":
        rows = []
        for h in reads.working_hours():
            rows.append(f"{WEEKDAYS_SHORT[h.weekday]}: " + ("выходной" if h.is_closed else f"{h.open_min // 60:02d}:{h.open_min % 60:02d}–{h.close_min // 60:02d}:{h.close_min % 60:02d}"))
        return Reply("answered", "Время приёма машин:\n" + "\n".join(rows) if rows else "График пока не указан.", intent)
    if intent == "cancel_policy":
        return Reply("answered", f"Отменить запись можно не позднее чем за {plural(s.cancel_before_hours, ('час', 'часа', 'часов'))} до начала — в разделе «Моя запись». Позже — позвоните в студию.", intent)

    service, ask = _choose_service(reads, parsed, ctx, intent)
    if ask:
        return ask
    assert service is not None
    if intent == "price":
        return Reply("answered", f"«{service.name}» — {money(service.price_minor, cur)}. Занимает около {_duration(service.duration_min)}.", intent,
                     action={"type": "book", "service_id": service.id})
    if intent == "duration":
        return Reply("answered", f"«{service.name}» занимает около {_duration(service.duration_min)}.", intent)
    if intent == "next_slot":
        slot = reads.next_slot(service)
        if not slot:
            return Reply("answered", f"На «{service.name}» ближайшие {reads.settings.max_advance_days} дней свободного времени нет. Позвоните в студию.", intent)
        return Reply("answered", f"Ближайшее окно на «{service.name}»: {when_text(slot.start_min, reads.tz, reads.today)}.", intent,
                     action={"type": "book", "service_id": service.id, "start_min": slot.start_min})
    if intent == "free_on_date":
        day = parsed.day
        if day is None:
            return Reply("clarify", "На какую дату посмотреть свободное время?", intent,
                         options=[{"label": lbl, "text": lbl, "context": {"intent": intent, "service_id": service.id, "date": (reads.today + timedelta(days=n)).isoformat()}}
                                  for lbl, n in (("Сегодня", 0), ("Завтра", 1), ("Послезавтра", 2))])
        free = reads.free_slots(service, day)
        title = day_title(day, reads.today).lower()
        if not free:
            return Reply("answered", f"На {title} для «{service.name}» свободного времени нет.", intent)
        times = ", ".join(min_to_dt(m, reads.tz).strftime("%H:%M") for m in free[:12])
        return Reply("answered", f"Свободно на {title} («{service.name}»): {times}.", intent, action={"type": "book", "service_id": service.id, "start_min": free[0]})
    return _unknown(client_examples(reads.settings.business_type))


def _duration(minutes: int) -> str:
    if minutes >= 24 * 60 and minutes % (24 * 60) == 0:
        return plural(minutes // (24 * 60), ("день", "дня", "дней"))
    if minutes >= 60:
        h, m = divmod(minutes, 60)
        return plural(h, ("час", "часа", "часов")) + (f" {m} мин" if m else "")
    return f"{minutes} мин"


def _period_options(intent: str) -> list[dict]:
    return [{"label": label, "text": label, "context": {"intent": intent, "period": key}} for label, key in PERIOD_CHIPS]


def _owner_answer(intent: str, parsed: intents.Parsed, ctx: dict, reads: OwnerReads) -> Reply:
    cur, tz, today = reads.settings.currency, reads.tz, reads.today
    if intent == "help":
        return Reply("answered", "Спросите про расписание, заезды, деньги или неоплаченные работы.", intent,
                     options=[{"label": e, "text": e, "context": {}} for e in OWNER_EXAMPLES])
    period = ctx.get("period") if isinstance(ctx.get("period"), str) else parsed.period
    if period not in stats.PERIODS:
        period = None
    day = parsed.day or (date.fromisoformat(ctx["date"]) if isinstance(ctx.get("date"), str) else None)

    if intent == "schedule":
        if period in ("week", "last_week", "month", "last_month"):
            first, after = stats.period_dates(period, tz, reads.now_min)
        else:
            day = day or (stats.period_dates(period, tz, reads.now_min)[0] if period else today)
            first, after = day, day + timedelta(days=1)
        rows = reads.bookings_between(first, after)
        title = day_title(first, today) if after - first == timedelta(days=1) else f"{first:%d.%m}–{(after - timedelta(days=1)):%d.%m}"
        if not rows:
            return Reply("answered", f"{title}: записей нет.", intent)
        lines = [f"{min_to_dt(r['start_min'], tz):%H:%M} {r['service']} — {r['client']}" + (f" ({r['car']})" if r["car"] else "") for r in rows]
        return Reply("answered", f"{title}: {plural(len(rows), ('запись', 'записи', 'записей'))}.\n" + "\n".join(lines), intent, items=rows)
    if intent == "next_booking":
        nb = reads.next_booking()
        if not nb:
            return Reply("answered", "Предстоящих записей нет.", intent)
        return Reply("answered", f"Ближайшая запись: {when_text(nb['start_min'], tz, today)} — {nb['service']}, {nb['client']}" + (f" ({nb['car']})." if nb["car"] else "."), intent, items=[nb])
    if intent == "unpaid":
        rows = reads.unpaid()
        if not rows:
            return Reply("answered", "Неоплаченных принятых или готовых работ нет.", intent)
        lines = [f"• {r['client']} — {r['service']}: {money(r['due_minor'], cur)}" for r in rows]
        return Reply("answered", "Не оплачено полностью:\n" + "\n".join(lines), intent, items=rows)

    if period is None and day is None:
        return Reply("clarify", "За какой период посчитать?", intent, options=_period_options(intent))
    st = reads.stats(period, day)
    label = PERIOD_TITLES.get(period or "", day_title(day, today).lower() if day else "")
    if intent == "count_cars":
        return Reply("answered", f"{label.capitalize()}: {plural(st['visits'], ('заезд', 'заезда', 'заездов'))}, выполнено работ — {st['completed']}, отмен — {st['cancelled']}.", intent, items=[st])
    if intent == "works_done":
        return Reply("answered", f"{label.capitalize()} выполнено работ: {st['completed']} из {st['visits']} заездов.", intent, items=[st])
    if intent == "money":
        extra = f" Ожидается по будущим записям: {money(st['scheduled_value_minor'], cur)} (это ещё не выручка)." if st["scheduled_value_minor"] else ""
        return Reply("answered", f"{label.capitalize()} получено: {money(st['received_minor'], cur)} (возвраты учтены).{extra}", intent, items=[st])
    return _unknown(OWNER_EXAMPLES)


def _hours_text(reads: PublicReads | OwnerReads) -> str:
    rows = reads.db.scalars(select(WorkingHours).order_by(WorkingHours.weekday))
    return "; ".join(
        f"{WEEKDAYS_SHORT[h.weekday]} " + ("выходной" if h.is_closed else f"{h.open_min // 60:02d}:{h.open_min % 60:02d}–{h.close_min // 60:02d}:{h.close_min % 60:02d}")
        for h in rows
    )


def owner_facts(reads: OwnerReads) -> str:
    st = reads.stats("today")
    nb = reads.next_booking()
    lines = [
        f"Студия: {reads.settings.name}. Сегодня: {reads.today:%d.%m.%Y}.",
        f"Сегодня: заездов {st['visits']}, выполнено {st['completed']}, отмен {st['cancelled']}, получено {money(st['received_minor'], reads.settings.currency)}.",
    ]
    if nb:
        lines.append(f"Ближайшая запись: {when_text(nb['start_min'], reads.tz, reads.today)} — {nb['service']}, {nb['client']}.")
    lines.append("Разделы кабинета: Расписание (записи, статусы, оплаты), Услуги (цены, рабочие места), Студия (контакты, график, фото).")
    return "\n".join(lines)


INFO_INTENTS = ("masters", "address", "phone", "hours", "cancel_policy")
PART_OF_DAY = (("утр", 8, 12), ("днём", 12, 16), ("днем", 12, 16), ("обед", 12, 15), ("вечер", 16, 23))
BOOK_CHIP = {"label": "Подобрать время", "text": "Подобрать время", "context": {"intent": "book"}}


def _hm(v) -> int | None:
    if not isinstance(v, str) or len(v) < 4:
        return None
    try:
        h, m = v.split(":")[:2]
        return int(h) * 60 + int(m)
    except ValueError:
        return None


def _slot_label(start_min: int, reads: PublicReads, with_day: bool) -> str:
    dt = min_to_dt(start_min, reads.tz)
    if not with_day:
        return f"{dt:%H:%M}"
    d = dt.date()
    day = "Сегодня" if d == reads.today else "Завтра" if d == reads.today + timedelta(days=1) else f"{WEEKDAYS_SHORT[d.weekday()].capitalize()} {d.day} {MONTHS_GEN[d.month - 1][:3]}"
    return f"{day}, {dt:%H:%M}"


def _booking_flow(text: str, parsed: intents.Parsed, ctx: dict, reads: PublicReads, history: list[dict]) -> Reply:
    """Lead the visitor to a booking: find the service, then offer real free times as buttons."""
    services = reads.services()
    by_id = {v.id: v for v in services}
    norm = intents.normalize(text)
    service = by_id.get(ctx["service_id"]) if isinstance(ctx.get("service_id"), int) else None
    day = parsed.day
    window = next(((a * 60, b * 60) for word, a, b in PART_OF_DAY if word in norm), None)
    ask_text = ""
    if service is None:
        candidates = [v for v in services if v.id in parsed.service_ids]
        service = candidates[0] if len(candidates) == 1 else services[0] if len(services) == 1 else None
    if (service is None or day is None) and not ctx:
        got = llm.extract(reads.settings.name, reads.today.isoformat(), WEEKDAYS_LONG[reads.today.weekday()], [(v.id, v.name) for v in services], text, history)
        if got:
            service = service or by_id.get(got.get("service_id")) if isinstance(got.get("service_id"), int) else service
            if day is None and isinstance(got.get("date"), str):
                try:
                    day = date.fromisoformat(got["date"])
                except ValueError:
                    pass
            lo, hi = _hm(got.get("time_from")), _hm(got.get("time_to"))
            if lo is not None or hi is not None:
                window = (lo or 0, hi or 24 * 60)
            ask_text = str(got.get("reply") or "")[:300]
    if day is not None and not (reads.today <= day <= reads.today + timedelta(days=reads.settings.max_advance_days)):
        day = None
    keep = {k: v for k, v in (("date", day.isoformat() if day else None),) if v}
    if service is None:
        return Reply("clarify", ask_text or "Что нужно сделать? Выберите услугу — подберу свободное время.", "book",
                     options=[{"label": v.name, "text": v.name, "context": {"intent": "book", "service_id": v.id, **keep}} for v in services[:10]])

    def fits(m: int) -> bool:
        if not window:
            return True
        local = min_to_dt(m, reads.tz)
        return window[0] <= local.hour * 60 + local.minute < window[1]

    head = f"«{service.name}» — {money(service.price_minor, reads.settings.currency)}, занимает {_duration(service.duration_min)}."
    picked: list[int] = []
    note = ""
    if day is not None:
        picked = [m for m in reads.free_slots(service, day) if fits(m)][:8]
        if not picked:
            note = f"\n{day_title(day, reads.today)}: подходящего свободного времени нет, показываю ближайшее."
    if not picked:
        start = (day + timedelta(days=1)) if day is not None and note else reads.today
        days_with = 0
        for i in range(min(reads.settings.max_advance_days, 21)):
            d = start + timedelta(days=i)
            if d > reads.today + timedelta(days=reads.settings.max_advance_days):
                break
            free = [m for m in reads.free_slots(service, d) if fits(m)][:3]
            if free:
                picked += free
                days_with += 1
            if days_with >= 3:
                break
    if not picked:
        return Reply("answered", f"{head} Ближайшие {reads.settings.max_advance_days} дней свободного времени нет. Позвоните в студию{': ' + reads.settings.phone if reads.settings.phone else ''}.", "book")
    one_day = len({min_to_dt(m, reads.tz).date() for m in picked}) == 1
    when = f"\n{day_title(min_to_dt(picked[0], reads.tz).date(), reads.today)} — свободное время ниже." if one_day and not note else note or "\nБлижайшее свободное время ниже."
    options = [{"label": _slot_label(m, reads, not one_day), "text": "", "action": {"type": "book", "service_id": service.id, "start_min": m}} for m in picked]
    options.append({"label": "Другой день", "text": "Другой день", "context": {"intent": "book", "service_id": service.id, "pick": "day"}})
    return Reply("answered", f"{head}{when} Нажмите на удобное — останется ввести имя и телефон.", "book", options=options)


def _day_choice(service: Service, reads: PublicReads) -> Reply:
    opts = []
    for i in range(min(reads.settings.max_advance_days, 14) + 1):
        d = reads.today + timedelta(days=i)
        if reads.free_slots(service, d):
            label = day_title(d, reads.today) if i < 2 else f"{WEEKDAYS_SHORT[d.weekday()].capitalize()} {d.day} {MONTHS_GEN[d.month - 1][:3]}"
            opts.append({"label": label, "text": label, "context": {"intent": "book", "service_id": service.id, "date": d.isoformat()}})
    return Reply("clarify", f"На какой день записать на «{service.name}»?", "book", options=opts[:10])


def answer(audience: str, text: str, ctx: dict | None, reads: PublicReads | OwnerReads, history: list[dict] | None = None) -> Reply:
    ctx = ctx or {}
    if audience == "client":
        assert isinstance(reads, PublicReads)
        parsed = _parse(audience, text, ctx, reads)
        intent = ctx.get("intent") if isinstance(ctx.get("intent"), str) else parsed.intent
        if intent in INFO_INTENTS or intent == "help":
            reply = _client_answer(intent, parsed, ctx, reads)
            reply.options = (reply.options or []) + [BOOK_CHIP] if intent != "help" else reply.options
            return reply
        if ctx.get("pick") == "day" and isinstance(ctx.get("service_id"), int):
            service = reads.service(ctx["service_id"])
            if service:
                return _day_choice(service, reads)
        return _booking_flow(text, parsed, ctx, reads, history or [])

    assert isinstance(reads, OwnerReads)
    reply = _rule_answer(audience, text, ctx, reads)
    # a tapped chip already carries an exact answer; free text gets natural wording from the model
    if ctx or not llm.enabled():
        return reply
    draft = reply.text if reply.status != "unknown" else "в базе нет готового ответа на этот вопрос"
    worded = llm.phrase(audience, reads.settings.name, reads.settings.phone or "", owner_facts(reads), draft, text, history or [])
    if worded:
        reply.text = worded
        if reply.status == "unknown":
            reply.status, reply.options = "answered", None
    return reply


def _parse(audience: str, text: str, ctx: dict, reads: PublicReads | OwnerReads) -> intents.Parsed:
    services = [{"id": v.id, "name": v.name, "keywords": v.keywords or []} for v in _services_for_parsing(reads)]
    parsed = intents.parse(text, audience, services, reads.today)
    if isinstance(ctx.get("date"), str):
        try:
            parsed.day = date.fromisoformat(ctx["date"])
        except ValueError:
            pass
    return parsed


def _rule_answer(audience: str, text: str, ctx: dict | None, reads: PublicReads | OwnerReads) -> Reply:
    ctx = ctx or {}
    services = [{"id": s.id, "name": s.name, "keywords": s.keywords or []} for s in _services_for_parsing(reads)]
    parsed = intents.parse(text, audience, services, reads.today)
    # a clarification chip carries its intent and the missing entity in `context`
    forced = ctx.get("intent")
    allowed = intents.CLIENT_INTENTS if audience == "client" else intents.OWNER_INTENTS
    intent = forced if isinstance(forced, str) and forced in allowed else parsed.intent
    if isinstance(ctx.get("date"), str):
        try:
            parsed.day = date.fromisoformat(ctx["date"])
        except ValueError:
            pass
    if intent is None:
        return _unknown(client_examples(reads.settings.business_type) if audience == "client" else OWNER_EXAMPLES)
    if audience == "client":
        assert isinstance(reads, PublicReads)
        return _client_answer(intent, parsed, ctx, reads)
    assert isinstance(reads, OwnerReads)
    return _owner_answer(intent, parsed, ctx, reads)


def _services_for_parsing(reads: PublicReads | OwnerReads) -> list[Service]:
    return list(reads.db.scalars(select(Service).where(Service.is_active.is_(True))))
