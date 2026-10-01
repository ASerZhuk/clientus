"""Business profiles: one booking engine, several kinds of business.

A profile is data, not code paths: which resource a customer books (a bay or a master),
which words the UI uses, which fields the booking form asks for, which capabilities
(feature flags) are switched on, and a starter kit for `tenant:new`. The web app reads the
public part of the profile from the studio config and adapts; the API enforces the flags.
"""
from dataclasses import dataclass, field

TYPES = ("auto", "wash", "beauty_master", "beauty_studio")


@dataclass(frozen=True)
class Profile:
    type: str
    label: str
    summary: str
    kind: str  # "vehicle" (bays, cars) | "person" (masters, clients)
    features: dict[str, bool]
    vocab: dict[str, str]
    contact: dict[str, str]  # field -> required | optional | hidden
    defaults: dict
    home: tuple[str, ...]  # order of home-page sections
    max_resources: int | None = None
    starter: dict = field(default_factory=dict)

    def public(self) -> dict:
        return {
            "type": self.type,
            "label": self.label,
            "kind": self.kind,
            "features": self.features,
            "vocab": self.vocab,
            "contact": self.contact,
            "home": list(self.home),
        }


_VEHICLE_VOCAB = {
    "resource_one": "место",
    "resource_many": "места",
    "resource_in_work": "в работе",
    "resource_new": "Новое место",
    "resource_block": "Занять место",
    "resource_section": "Рабочие места",
    "status_accepted": "Автомобиль принят",
    "status_ready": "Автомобиль готов",
    "action_accept": "Принять авто",
    "action_ready": "Готова",
    "works_title": "Работы студии",
    "book_title": "Запись в студию",
    "book_card_title": "Свежий вид для вашего авто",
    "book_card_text": "Выберите услугу и удобное время — остальное возьмём на себя",
    "client_word": "клиент",
}

_PERSON_VOCAB = {
    "resource_one": "мастер",
    "resource_many": "мастера",
    "resource_in_work": "принимают",
    "resource_new": "Новый мастер",
    "resource_block": "Отметить занятость",
    "resource_section": "Мастера",
    "status_accepted": "Клиент пришёл",
    "status_ready": "Услуга оказана",
    "action_accept": "Клиент пришёл",
    "action_ready": "Готово",
    "works_title": "Наши работы",
    "book_title": "Запись онлайн",
    "book_card_title": "Выберите удобное время",
    "book_card_text": "Запишитесь без звонков — подтверждение придёт сразу",
    "client_word": "клиент",
}

PROFILES: dict[str, Profile] = {
    "auto": Profile(
        type="auto",
        label="Автосервис и детейлинг",
        summary="Рабочие места (подъёмники, боксы, стенды), длительные работы (в том числе несколько дней), автомобиль и госномер в записи.",
        kind="vehicle",
        features={"choose_resource": False, "per_resource_hours": False, "resource_profiles": False, "multi_day": True, "vehicle_fields": True, "per_resource_prices": False},
        vocab=_VEHICLE_VOCAB,
        contact={"car": "required", "plate": "optional", "note": "hidden"},
        defaults={"accent": "#4690FF", "slot_step_min": 60, "lead_time_min": 120, "cancel_before_hours": 24, "reminder_hours": 24},
        home=("hero", "tiles", "book", "services", "works", "install"),
    ),
    "wash": Profile(
        type="wash",
        label="Автомойка",
        summary="Боксы и короткие услуги, шаг записи 30 минут, быстрая отмена.",
        kind="vehicle",
        features={"choose_resource": False, "per_resource_hours": False, "resource_profiles": False, "multi_day": False, "vehicle_fields": True, "per_resource_prices": False},
        vocab={**_VEHICLE_VOCAB, "resource_one": "бокс", "resource_many": "боксы", "resource_new": "Новый бокс", "resource_block": "Заблокировать бокс", "resource_section": "Боксы",
               "book_card_title": "Чистый автомобиль за час", "book_card_text": "Выберите услугу и время — приедете к своему боксу без очереди"},
        contact={"car": "required", "plate": "optional", "note": "hidden"},
        defaults={"accent": "#22C3E6", "slot_step_min": 30, "lead_time_min": 30, "cancel_before_hours": 2, "reminder_hours": 2},
        home=("hero", "tiles", "book", "services", "install"),
    ),
    "beauty_master": Profile(
        type="beauty_master",
        label="Мастер красоты",
        summary="Один специалист: услуги, личное расписание, без выбора мастера.",
        kind="person",
        features={"choose_resource": False, "per_resource_hours": False, "resource_profiles": True, "multi_day": False, "vehicle_fields": False, "per_resource_prices": False},
        vocab={**_PERSON_VOCAB, "book_title": "Запись ко мне", "book_card_title": "Запишитесь на удобное время", "book_card_text": "Выберите услугу и время — я подтвержу запись сразу"},
        contact={"car": "hidden", "plate": "hidden", "note": "optional"},
        defaults={"accent": "#E58BB5", "slot_step_min": 30, "lead_time_min": 120, "cancel_before_hours": 12, "reminder_hours": 24},
        home=("hero", "tiles", "book", "services", "works", "install"),
        max_resources=1,
    ),
    "beauty_studio": Profile(
        type="beauty_studio",
        label="Студия красоты",
        summary="Несколько мастеров: у каждого своё расписание и цены, клиент выбирает мастера или «любого свободного».",
        kind="person",
        features={"choose_resource": True, "per_resource_hours": True, "resource_profiles": True, "multi_day": False, "vehicle_fields": False, "per_resource_prices": True},
        vocab=_PERSON_VOCAB,
        contact={"car": "hidden", "plate": "hidden", "note": "optional"},
        defaults={"accent": "#C79BFF", "slot_step_min": 30, "lead_time_min": 120, "cancel_before_hours": 12, "reminder_hours": 24},
        home=("hero", "tiles", "book", "masters", "services", "works", "install"),
    ),
}


def get_profile(business_type: str | None) -> Profile:
    return PROFILES.get(business_type or "auto", PROFILES["auto"])


def is_valid(business_type: str) -> bool:
    return business_type in PROFILES


def starter_config(business_type: str, slug: str, name: str) -> dict:
    """business.json skeleton for `tenant:new --type`. Photo names match tenants.placeholder_art."""
    p = get_profile(business_type)
    week = {d: ["09:00", "19:00"] for d in ("mon", "tue", "wed", "thu", "fri")}
    base = {
        "business_type": p.type,
        "slug": slug,
        "name": name,
        "phone": "+7 000 000-00-00",
        "address": "Город, улица, дом",
        "map_url": "",
        "timezone": "Europe/Moscow",
        "currency": "RUB",
        "accent": p.defaults["accent"],
        "images": {"logo": "logo.png", "hero": "hero.jpg"},
        "gallery": [{"key": f"work-{i}", "image": f"work-{i}.jpg", "caption": f"Работа {i}"} for i in range(1, 4)],
        "booking": {k: p.defaults[k] for k in ("slot_step_min", "lead_time_min", "cancel_before_hours", "reminder_hours")} | {"max_advance_days": 60},
        "exceptions": [],
    }
    if p.type == "auto":
        return base | {
            "tagline": "Детейлинг и уход за автомобилем",
            "description": "Коротко о студии: чем занимаетесь и чем отличаетесь.",
            "info_cards": [
                {"title": "{services}", "text": "{services_word:услуга|услуги|услуг} в прайсе", "icon": "wrench"},
                {"title": "{resources}", "text": "{resources_word:рабочее место|рабочих места|рабочих мест}", "icon": "images"},
                {"title": "от {min_price}", "text": "за услугу", "icon": "tag"},
            ],
            "hours": week | {"sat": ["10:00", "17:00"], "sun": None},
            "resources": [{"key": "bay-1", "name": "Место 1"}, {"key": "bay-2", "name": "Место 2"}],
            "services": [
                {"key": "wash", "name": "Мойка", "description": "Бесконтактная мойка кузова и салона.", "price": 2500, "duration_min": 120, "buffer_min": 30, "keywords": ["мойка"]},
                {"key": "polish", "name": "Полировка кузова", "description": "Удаление царапин и голограмм.", "price": 15000, "duration_min": 480, "buffer_min": 60, "keywords": ["полировка"]},
            ],
        }
    if p.type == "wash":
        return base | {
            "tagline": "Быстрая мойка без очереди",
            "description": "Записывайтесь на удобное время — бокс будет свободен.",
            "info_cards": [
                {"title": "{services}", "text": "{services_word:услуга|услуги|услуг} в прайсе", "icon": "wrench"},
                {"title": "{resources}", "text": "{resources_word:бокс|бокса|боксов} в работе", "icon": "images"},
                {"title": "от {min_price}", "text": "за мойку", "icon": "tag"},
            ],
            "hours": {d: ["08:00", "22:00"] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
            "resources": [{"key": "box-1", "name": "Бокс 1"}, {"key": "box-2", "name": "Бокс 2"}, {"key": "box-3", "name": "Бокс 3"}],
            "services": [
                {"key": "express", "name": "Экспресс-мойка", "description": "Кузов, стёкла, коврики.", "price": 700, "duration_min": 30, "buffer_min": 10, "keywords": ["экспресс", "мойка"]},
                {"key": "complex", "name": "Комплексная мойка", "description": "Кузов, салон, порог, чернение резины.", "price": 1500, "duration_min": 60, "buffer_min": 10, "keywords": ["комплексная"]},
                {"key": "interior", "name": "Химчистка салона", "description": "Глубокая чистка тканей и пластика.", "price": 6000, "duration_min": 240, "buffer_min": 15, "keywords": ["химчистка"]},
            ],
        }
    if p.type == "beauty_master":
        return base | {
            "tagline": "Маникюр и уход за руками",
            "description": "Работаю по записи, стерильные инструменты, аккуратный результат.",
            "info_cards": [
                {"title": "5", "text": "лет опыта", "icon": "sparkle"},
                {"title": "{services}", "text": "{services_word:услуга|услуги|услуг} в прайсе", "icon": "wrench"},
                {"title": "от {min_price}", "text": "за услугу", "icon": "tag"},
            ],
            "hours": week | {"sat": ["10:00", "16:00"], "sun": None},
            "resources": [{"key": "me", "name": "Мастер", "description": "Мастер маникюра и педикюра"}],
            "services": [
                {"key": "manicure", "name": "Маникюр", "description": "Классический или аппаратный.", "price": 1800, "duration_min": 90, "buffer_min": 15, "keywords": ["маникюр"]},
                {"key": "gel", "name": "Маникюр с покрытием", "description": "Гель-лак, стойкость до 3 недель.", "price": 2500, "duration_min": 120, "buffer_min": 15, "keywords": ["гель", "покрытие"]},
                {"key": "pedicure", "name": "Педикюр", "description": "Аппаратный педикюр.", "price": 3000, "duration_min": 120, "buffer_min": 15, "keywords": ["педикюр"]},
            ],
        }
    return base | {  # beauty_studio
        "tagline": "Салон красоты: волосы, ногти, уход",
        "description": "Мастера с опытом, запись к конкретному специалисту.",
        "info_cards": [
            {"title": "{resources}", "text": "{resources_word:мастер принимает|мастера принимают|мастеров принимают}", "icon": "user"},
            {"title": "{services}", "text": "{services_word:услуга|услуги|услуг} в прайсе", "icon": "wrench"},
            {"title": "от {min_price}", "text": "за услугу", "icon": "tag"},
        ],
        "hours": {d: ["10:00", "20:00"] for d in ("mon", "tue", "wed", "thu", "fri", "sat")} | {"sun": None},
        "resources": [
            {"key": "anna", "name": "Анна", "description": "Стилист-парикмахер", "hours": {d: ["10:00", "19:00"] for d in ("mon", "tue", "wed", "thu", "fri")} | {"sat": None, "sun": None}},
            {"key": "olga", "name": "Ольга", "description": "Мастер маникюра", "hours": {d: ["12:00", "20:00"] for d in ("wed", "thu", "fri", "sat")} | {"mon": None, "tue": None, "sun": None}},
        ],
        "services": [
            {"key": "cut", "name": "Стрижка", "description": "Женская стрижка с укладкой.", "price": 2500, "duration_min": 60, "buffer_min": 10, "resources": ["anna"], "keywords": ["стрижка"]},
            {"key": "color", "name": "Окрашивание", "description": "Однотонное окрашивание.", "price": 6000, "duration_min": 180, "buffer_min": 15, "resources": ["anna"], "keywords": ["окрашивание", "покраска"]},
            {"key": "manicure", "name": "Маникюр", "description": "Классический или аппаратный.", "price": 1800, "duration_min": 90, "buffer_min": 15, "resources": ["olga"], "keywords": ["маникюр"]},
            {"key": "gel", "name": "Маникюр с покрытием", "description": "Гель-лак.", "price": 2500, "duration_min": 120, "buffer_min": 15, "resources": ["olga"], "keywords": ["гель"]},
        ],
    }
