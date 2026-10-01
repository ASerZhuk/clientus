from datetime import date

from app.services.intents import parse

TODAY = date(2030, 1, 7)  # Monday
SERVICES = [
    {"id": 1, "name": "Полировка кузова", "keywords": ["полировка кузова"]},
    {"id": 2, "name": "Полировка фар", "keywords": []},
    {"id": 3, "name": "Керамика", "keywords": ["керамическое покрытие"]},
    {"id": 4, "name": "Комплексная мойка", "keywords": ["мойка"]},
]


def c(text):
    return parse(text, "client", SERVICES, TODAY)


def o(text):
    return parse(text, "owner", SERVICES, TODAY)


def test_client_example_buttons():
    assert c("Когда ближайшее окно?").intent == "next_slot"
    assert c("Сколько стоит керамика?").intent == "price"
    assert c("Сколько стоит керамика?").service_ids == [3]
    assert c("Как найти студию?").intent == "address"
    assert c("Во сколько вы работаете?").intent == "hours"
    assert c("Дайте телефон").intent == "phone"
    assert c("какие у вас услуги").intent == "services_list"
    assert c("Подобрать услугу").intent == "services_list"
    assert c("сколько по времени делается мойка").intent == "duration"
    assert c("можно отменить запись?").intent == "cancel_policy"


def test_service_ambiguity_and_keywords():
    assert c("Сколько стоит полировка?").service_ids == [1, 2]  # both match: the assistant must ask
    assert c("сколько стоит керамическое покрытие").service_ids == [3]
    assert c("Сколько стоит?").service_ids == []


def test_dates():
    assert c("есть свободное время завтра?").day == date(2030, 1, 8)
    assert c("свободно в пятницу?").day == date(2030, 1, 11)
    assert c("свободно 25 января").day == date(2030, 1, 25)
    assert c("свободно 10.02").day == date(2030, 2, 10)
    assert c("свободно 3 января").day == date(2031, 1, 3)  # past date rolls to next year
    assert c("свободно завтра?").intent == "free_on_date"


def test_owner_examples():
    q = o("Что у меня завтра?")
    assert (q.intent, q.day) == ("schedule", date(2030, 1, 8))
    q = o("Сколько машин было на неделе?")
    assert (q.intent, q.period) == ("count_cars", "week")
    q = o("Сколько денег получено?")
    assert (q.intent, q.period) == ("money", None)
    assert o("выручка за прошлый месяц").period == "last_month"
    assert o("кто не оплатил").intent == "unpaid"
    assert o("ближайшая запись").intent == "next_booking"


def test_unknown_text_and_audience_separation():
    assert c("расскажи анекдот про ежа").intent is None
    assert c("").intent is None
    # owner-only questions do not exist in the client rule set
    assert c("Сколько денег получено?").intent is None
    assert c("Что у меня завтра?").intent in (None, "free_on_date")
    assert c("что у меня завтра").intent != "schedule"
    # and client questions do not leak into the owner rule set
    assert o("Как найти студию?").intent is None


def test_masters_intent():
    assert c("Какие мастера принимают?").intent == "masters"
    assert c("к кому можно записаться").intent == "masters"
