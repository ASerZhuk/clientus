"""Deterministic intent parsing (no LLM). Free text is normalised and matched against
keyword stems; the result is an intent name plus entities. Pure functions, no database:
services are passed in so the parser can be tested in isolation."""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

CLIENT_INTENTS = ("book", "masters", "next_slot", "free_on_date", "price", "services_list", "duration", "address", "hours", "phone", "cancel_policy", "help")
OWNER_INTENTS = ("schedule", "count_cars", "money", "works_done", "next_booking", "unpaid", "help")

# stem -> weight. A stem matches a word that starts with it.
_CLIENT_RULES: dict[str, dict[str, int]] = {
    "next_slot": {"ближайш": 3, "окно": 3, "окошк": 3, "окн": 2, "свобод": 1, "когда": 1, "можн": 1, "запис": 1, "первое": 1},
    "free_on_date": {"свобод": 2, "врем": 1, "мест": 1, "окн": 1, "есть": 1, "запис": 1},
    "price": {"сколько": 1, "стоит": 4, "стоят": 4, "стоимост": 4, "цена": 4, "цены": 4, "цену": 4, "почем": 4, "прайс": 2, "руб": 1},
    "services_list": {"подобр": 4, "услуг": 3, "прайс": 3, "делаете": 2, "занимаетесь": 3, "список": 1, "предлагаете": 3, "умеете": 2},
    "duration": {"долго": 3, "длительн": 4, "продолжительн": 4, "времени": 2, "часов": 1, "делается": 3, "делаете": 1},
    "address": {"адрес": 4, "найти": 3, "наход": 3, "доехать": 4, "добраться": 4, "проехать": 4, "где": 2, "располож": 3, "карт": 2},
    "hours": {"график": 4, "работаете": 3, "открыт": 3, "закрыт": 3, "до скольки": 4, "часы": 2, "режим": 3, "выходн": 3, "работы": 1},
    "phone": {"телефон": 4, "позвонить": 4, "номер": 3, "связаться": 3, "звонить": 3, "контакт": 3},
    "cancel_policy": {"отмен": 4, "перенес": 4, "отказ": 2, "правил": 1, "предоплат": 3},
    "masters": {"мастер": 4, "мастера": 4, "специалист": 4, "кто работает": 5, "к кому": 5, "парикмахер": 3, "стилист": 3},
    "help": {"привет": 2, "здравств": 2, "помощь": 3, "помоги": 3, "умеешь": 3, "можешь": 2, "добрый": 2},
}
_OWNER_RULES: dict[str, dict[str, int]] = {
    "schedule": {"что": 1, "расписан": 4, "записи": 3, "записан": 2, "кто": 2, "график": 2, "меня": 1, "план": 2, "покажи": 1, "клиенты": 2},
    "count_cars": {"машин": 4, "заезд": 4, "автомобил": 3, "сколько": 2, "клиент": 2, "записей": 3, "визит": 3},
    "money": {"денег": 4, "деньги": 4, "выручк": 4, "получено": 4, "получил": 4, "заработ": 4, "оплат": 3, "касс": 3, "доход": 4, "сколько": 1, "прибыл": 2},
    "works_done": {"выполнен": 4, "готов": 3, "завершен": 4, "сделано": 3, "закончен": 3, "работ": 2},
    "next_booking": {"ближайш": 4, "следующ": 4, "следующий": 4, "скоро": 2, "запись": 1, "клиент": 1},
    "unpaid": {"неоплач": 5, "долг": 4, "должн": 4, "задолж": 4, "не оплат": 5, "остаток": 3, "доплат": 3},
    "help": {"привет": 2, "помощь": 3, "помоги": 3, "умеешь": 3, "можешь": 2},
}
_MIN_SCORE = {"masters": 4, "next_slot": 3, "free_on_date": 3, "price": 4, "services_list": 3, "duration": 3, "address": 3, "hours": 3, "phone": 3,
              "cancel_policy": 3, "help": 2, "schedule": 3, "count_cars": 4, "money": 4, "works_done": 4, "next_booking": 4, "unpaid": 4}

_MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
_WEEKDAYS = {"понедельн": 0, "вторник": 1, "сред": 2, "четверг": 3, "пятниц": 4, "суббот": 5, "воскресень": 6}


@dataclass
class Parsed:
    intent: str | None
    audience: str
    service_ids: list[int] = field(default_factory=list)  # best matches (more than one = ambiguous)
    day: date | None = None
    period: str | None = None


def normalize(text: str) -> str:
    t = text.lower().replace("ё", "е")
    t = re.sub(r"[^\w\s./:-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _words(norm: str) -> list[str]:
    return re.findall(r"[a-zа-я0-9]+", norm)


def _score(norm: str, words: list[str], rules: dict[str, int]) -> int:
    total = 0
    for stem, weight in rules.items():
        if " " in stem:
            total += weight if stem in norm else 0
        elif any(w.startswith(stem) for w in words):
            total += weight
    return total


def parse_day(norm: str, today: date) -> date | None:
    words = _words(norm)
    if "послезавтра" in words:
        return today + timedelta(days=2)
    if "завтра" in words or "завтрашний" in words:
        return today + timedelta(days=1)
    if "сегодня" in words:
        return today
    if "вчера" in words:
        return today - timedelta(days=1)
    m = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", norm)
    if m:
        d, mo = int(m[1]), int(m[2])
        y = int(m[3]) if m[3] else today.year
        y += 2000 if y < 100 else 0
        try:
            found = date(y, mo, d)
        except ValueError:
            return None
        return found if m[3] or found >= today else _safe_date(today.year + 1, mo, d)
    m = re.search(r"\b(\d{1,2})\s+([а-я]+)", norm)
    if m:
        for stem, mo in _MONTHS.items():
            if m[2].startswith(stem):
                found = _safe_date(today.year, mo, int(m[1]))
                if found and found < today:
                    found = _safe_date(today.year + 1, mo, int(m[1]))
                return found
    for w in words:
        for stem, wd in _WEEKDAYS.items():
            if w.startswith(stem) and len(w) >= 4:
                delta = (wd - today.weekday()) % 7
                return today + timedelta(days=delta)
    return None


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_period(norm: str) -> str | None:
    words = _words(norm)
    past = any(w.startswith(("прошл", "предыдущ", "прошедш")) for w in words)
    if any(w.startswith("недел") for w in words):
        return "last_week" if past else "week"
    if any(w.startswith("месяц") for w in words):
        return "last_month" if past else "month"
    if "вчера" in words:
        return "yesterday"
    if "завтра" in words:
        return "tomorrow"
    if "сегодня" in words:
        return "today"
    return None


def match_services(norm: str, services: list[dict]) -> list[int]:
    """services: [{id, name, keywords}]. Returns the ids sharing the best score (>0)."""
    words = _words(norm)
    best: dict[int, int] = {}
    for s in services:
        score = 0
        for kw in s.get("keywords") or []:
            kws = _words(normalize(kw))
            if kws and all(any(w.startswith(k[:5]) for w in words) for k in kws):
                score += 3 * len(kws)
        for nw in _words(normalize(s["name"])):
            if len(nw) >= 4 and any(w.startswith(nw[:5]) for w in words):
                score += 2
        if score:
            best[s["id"]] = score
    if not best:
        return []
    top = max(best.values())
    return [sid for sid, sc in best.items() if sc == top]


def parse(text: str, audience: str, services: list[dict], today: date) -> Parsed:
    """audience decides which rule set exists at all: a client can never reach an owner intent."""
    norm = normalize(text)
    words = _words(norm)
    rules = _CLIENT_RULES if audience == "client" else _OWNER_RULES
    scores = {intent: _score(norm, words, r) for intent, r in rules.items()}
    day = parse_day(norm, today)
    period = parse_period(norm)
    service_ids = match_services(norm, services)

    if audience == "client":
        if day and scores["free_on_date"] >= 2:
            scores["free_on_date"] += 3
        elif not day:
            scores["next_slot"] += scores["free_on_date"]  # "свободное время на мойку" without a date: nearest window
            scores["free_on_date"] = 0
        if service_ids and scores["price"] < _MIN_SCORE["price"] and scores["duration"] < _MIN_SCORE["duration"]:
            scores["price"] += 2  # bare "полировка?" -> price
    else:
        if day or period:
            scores["schedule"] += 1
        if any(w.startswith(("сколько", "количеств")) for w in words) and scores["money"] < 4:
            scores["count_cars"] += 1
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], list(rules).index(kv[0])))
    intent, score = ranked[0]
    if score < _MIN_SCORE[intent]:
        intent = None
    return Parsed(intent, audience, service_ids, day, period)
