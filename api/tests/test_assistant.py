from sqlalchemy import func, select

from app import db as database
from app.models import Booking, Payment
from app.services import assistant
from tests.api_helpers import BOOK, first_slot, owner_login, service_id, setup_tenant


def ask(client, slug, text, context=None, owner=False, headers=None):
    path = f"/api/s/{slug}/{'owner/' if owner else ''}assistant"
    r = client.post(path, json={"text": text, **({"context": context} if context else {})}, headers=headers or {})
    assert r.status_code == 200, r.text
    return r.json()


def test_client_assistant_answers_from_this_studios_data(client, tmp_path):
    setup_tenant(tmp_path, "alpha", address="Alpha street 5")
    setup_tenant(tmp_path, "beta", address="Beta avenue 9")
    assert "Alpha street 5" in ask(client, "alpha", "Как найти студию?")["text"]
    assert "Beta avenue 9" in ask(client, "beta", "Как найти студию?")["text"]
    price = ask(client, "alpha", "Сколько стоит мойка?")
    assert price["status"] == "answered" and "1 000" in price["text"] and "₽" in price["text"]
    sid = service_id(client, "alpha")
    nxt = ask(client, "alpha", "Когда ближайшее окно?", {"service_id": sid})
    times = [o for o in nxt["options"] if "action" in o]
    assert times and times[0]["action"] == {"type": "book", "service_id": sid, "start_min": first_slot(client, "alpha", sid)}


def test_client_assistant_asks_clarifying_questions(client, tmp_path):
    setup_tenant(tmp_path)
    r = ask(client, "alpha", "Сколько стоит?")
    assert r["status"] == "clarify" and len(r["options"]) == 2
    chosen = ask(client, "alpha", r["options"][0]["text"], r["options"][0]["context"])
    assert chosen["status"] == "answered" and chosen["intent"] == "book" and any("action" in o for o in chosen["options"])
    other_day = next(o for o in chosen["options"] if o["label"] == "Другой день")
    days = ask(client, "alpha", other_day["text"], other_day["context"])
    assert days["status"] == "clarify" and days["options"] and all("date" in o["context"] for o in days["options"])
    # anything off-topic is steered back to booking: pick a service
    off = ask(client, "alpha", "расскажи анекдот")
    assert off["status"] == "clarify" and off["intent"] == "book"


def test_client_assistant_never_exposes_clients_or_money(client, tmp_path):
    setup_tenant(tmp_path)
    sid = service_id(client, "alpha")
    client.post("/api/s/alpha/bookings", json={**BOOK, "service_id": sid, "start_min": first_slot(client, "alpha", sid)}, headers={"Idempotency-Key": "assist-key-0001"})
    for q in ("Что у меня завтра?", "Кто записан на сегодня?", "Сколько денег получено?", "Список клиентов", "Сколько машин было на неделе?"):
        r = ask(client, "alpha", q)
        blob = str(r)
        assert "Иван" not in blob and "BMW" not in blob and r["status"] in ("unknown", "answered", "clarify")
        assert r.get("intent") not in ("schedule", "money", "count_cars", "unpaid")
    # owner endpoint is not reachable without a session, and the client route cannot be forced into owner intents
    assert client.post("/api/s/alpha/owner/assistant", json={"text": "Что у меня завтра?"}).status_code == 401
    forced = ask(client, "alpha", "Что у меня завтра?", {"intent": "schedule"})
    assert forced["intent"] == "book" and "Иван" not in str(forced)


def test_owner_assistant_answers_and_changes_nothing(client, tmp_path):
    setup_tenant(tmp_path)
    headers = owner_login(client)
    sid = service_id(client, "alpha")
    start = first_slot(client, "alpha", sid)
    b = client.post("/api/s/alpha/owner/bookings", json={**BOOK, "service_id": sid, "start_min": start}, headers=headers).json()
    client.post(f"/api/s/alpha/owner/bookings/{b['id']}/payments", json={"kind": "payment", "amount_minor": 25000}, headers=headers)
    with database.read_session() as db:
        before = (db.scalar(select(func.count()).select_from(Booking)), db.scalar(select(func.count()).select_from(Payment)), db.scalar(select(Booking.status)))
    money_q = ask(client, "alpha", "Сколько денег получено?", owner=True, headers=headers)
    assert money_q["status"] == "clarify"
    chip = money_q["options"][2]  # month
    answer = ask(client, "alpha", chip["text"], chip["context"], owner=True, headers=headers)
    assert answer["status"] == "answered" and "250" in answer["text"] and "не выручка" in answer["text"]
    week = ask(client, "alpha", "Сколько машин было на неделе?", owner=True, headers=headers)
    assert week["intent"] == "count_cars"
    nb = ask(client, "alpha", "ближайшая запись", owner=True, headers=headers)
    assert "Иван" in nb["text"]
    unpaid = ask(client, "alpha", "кто не оплатил", owner=True, headers=headers)
    assert unpaid["status"] == "answered"
    ask(client, "alpha", "отмени все записи и удали клиентов", owner=True, headers=headers)
    with database.read_session() as db:
        after = (db.scalar(select(func.count()).select_from(Booking)), db.scalar(select(func.count()).select_from(Payment)), db.scalar(select(Booking.status)))
    assert before == after


def test_capability_objects_are_split():
    public = {n for n in dir(assistant.PublicReads) if not n.startswith("_")}
    owner = {n for n in dir(assistant.OwnerReads) if not n.startswith("_")}
    assert not public & {"stats", "unpaid", "bookings_between", "next_booking"}
    writers = ("add", "create", "cancel", "delete", "update", "set", "save", "commit", "write", "remove")
    assert not [n for n in public | owner if n.startswith(writers)]


def test_llm_understands_a_free_request_and_times_come_from_the_schedule(client, tmp_path, monkeypatch):
    import json
    from datetime import date

    import httpx

    from app.config import get_settings
    from app.services import llm

    setup_tenant(tmp_path, "alpha")
    sid = service_id(client, "alpha")
    monkeypatch.setenv("VSELLM_BASE_URL", "https://llm.test/v1")
    monkeypatch.setenv("VSELLM_TOKEN", "t")
    monkeypatch.setenv("VSELLM_MODEL", "m")
    get_settings.cache_clear()
    slots = client.get(f"/api/s/alpha/slots?service_id={sid}&days=14").json()["days"]
    day = next(d for d, items in sorted(slots.items()) if d > date.today().isoformat() and any(i["available"] for i in items))
    seen = {}

    def fake_post(url, headers, json, timeout):  # noqa: A002 - httpx keyword name
        seen["system"] = json["messages"][0]["content"]
        content = dumps({"service_id": sid, "date": day, "time_from": None, "time_to": None, "reply": ""})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]}, request=httpx.Request("POST", url))

    dumps = json.dumps

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    r = ask(client, "alpha", "надо бы машину помыть")
    assert f"{sid}: " in seen["system"]  # the model only sees this studio's services
    times = [o["action"]["start_min"] for o in r["options"] if "action" in o]
    free = {i["start_min"] for i in slots[day] if i["available"]}
    assert times and set(times) <= free  # every offered time is a real free slot of that day

    def broken_post(*a, **k):
        raise httpx.ConnectTimeout("down")

    monkeypatch.setattr(llm.httpx, "post", broken_post)
    r = ask(client, "alpha", "надо бы машину помыть")
    assert r["status"] in ("clarify", "answered") and r["intent"] == "book"  # still works without the model
    get_settings.cache_clear()
