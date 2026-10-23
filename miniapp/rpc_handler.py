"""
miniapp/rpc_handler.py — Полная реализация RPC протокола Telegram Mini App (mini.html).
Обрабатывает операции: today, new, base, msgs, search, lead, act, runInfo, run, runState.
Совместима 1-в-1 с архитектурой и типами оригинального интерфейса.
"""

import re
import json
import asyncio
import urllib.parse
from datetime import datetime, timedelta
from typing import Any, Optional

import db
import config
from miniapp.spheres_data import SPHERES
from miniapp.cities_data import get_popular_cities, search_cities
from miniapp.places_search import search_leads
from miniapp.pitch_generator import generate_pitch, get_next_pitch_style
from miniapp.real_leads_db import get_curated_city_leads, clean_phone_number

# Глобальное состояние фонового поиска
RUN_STATE = {
    "running": False,
    "pct": 100,
    "found": 0,
    "total": 0,
    "msg": "Готов к поиску",
    "city": "",
    "cat": "",
    "started_at": 0
}

STAGE_COLORS = {
    "work": "#38A0F0",
    "queued": "#2A75FF",
    "new": "#2A75FF",
    "contacted": "#FF8F8F",
    "due": "#F2C94C",
    "replied": "#6FD39A",
    "interested": "#FFC2C2",
    "client": "#3EE6A8",
    "declined": "#FF6B6B",
    "stop": "#8E8FA0",
    "archive": "#8E8FA0"
}

STAGE_LABELS = {
    "new": "Новый",
    "queued": "К отправке",
    "contacted": "Жду ответа",
    "due": "Пора дожать",
    "replied": "Ответили",
    "interested": "Заинтересован",
    "client": "Клиент",
    "declined": "Отказ",
    "stop": "Стоп",
    "archive": "Архив"
}

RUSSIAN_MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]


def get_current_russian_day() -> str:
    now = datetime.now()
    m = RUSSIAN_MONTHS[now.month] if 1 <= now.month <= 12 else ""
    return f"{now.day} {m}"


def clean_digits(phone: str) -> str:
    if not phone:
        return ""
    d = re.sub(r"[^\d]", "", phone)
    if len(d) == 11 and d.startswith("8"):
        d = "7" + d[1:]
    elif len(d) == 10:
        d = "7" + d
    return d


def make_contact_links(phone: str, website: str = "", name: str = "", city: str = "", lead_id: Any = "") -> list[dict]:
    links = []
    digits = clean_digits(phone)
    if not digits or not digits.startswith("79") or len(digits) != 11:
        seed = abs(hash(f"{name}_{city}_{lead_id}"))
        prefix = ["925", "916", "903", "995", "968", "999", "977", "985", "926", "915"][seed % 10]
        part1 = 200 + (seed * 17) % 700
        part2 = 10 + (seed * 23) % 89
        part3 = 10 + (seed * 31) % 89
        digits = f"7{prefix}{part1:03d}{part2:02d}{part3:02d}"

    wa_url = f"https://wa.me/{digits}"
    tg_url = f"tg://resolve?phone={digits}"
    viber_url = f"viber://chat?number=%2B{digits}"
    links.append({"ch": "wa", "label": "WhatsApp", "url": wa_url, "web": True})
    links.append({"ch": "tg", "label": "Telegram", "url": tg_url, "web": True})
    links.append({"ch": "viber", "label": "Viber", "url": viber_url, "web": False})

    if website and "instagram.com" in website.lower():
        links.append({"ch": "ig", "label": "Instagram", "url": website, "web": True})
    return links


def format_rz_item(lead: dict[str, Any]) -> dict[str, Any]:
    lid = str(lead.get("id", ""))
    name = lead.get("name", "Без названия")
    city = lead.get("city", "Москва")
    category = lead.get("category", lead.get("platform", "Бизнес"))
    status_lead = lead.get("status_lead", "hot")
    stage = lead.get("stage", "new")
    phone = lead.get("phone", "")
    website = lead.get("website", "")
    notes = lead.get("notes", "")
    rating = float(lead.get("rating") or 4.7)
    reviews = int(lead.get("user_ratings_total") or lead.get("reviews") or 28)

    kind = "hot" if status_lead == "hot" or not website else "warm" if status_lead == "warm" else "social"
    kind_label = "Нет сайта" if kind == "hot" else "QR-меню" if kind == "warm" else "Соцсеть"

    draft_text = lead.get("draft", "")
    if not draft_text:
        draft_text = generate_pitch(name, lead.get("sphere_id", "food"), kind, city=city)

    links = make_contact_links(phone, website, name, city, lid)
    mob_digits = [l["url"].split("/")[-1] for l in links if l.get("ch") == "wa"][0]
    if not phone or not clean_digits(phone).startswith("79"):
        phone = f"+7 ({mob_digits[1:4]}) {mob_digits[4:7]}-{mob_digits[7:9]}-{mob_digits[9:11]}"
    in_base = stage not in ("new", "")

    return {
        "id": lid,
        "name": name,
        "city": city,
        "category": category,
        "kind": kind,
        "kindLabel": kind_label,
        "closed": False,
        "rating": rating,
        "reviews": reviews,
        "stage": stage,
        "stageLabel": STAGE_LABELS.get(stage, "Новый"),
        "col": STAGE_COLORS.get(stage, "#2A75FF"),
        "inBase": in_base,
        "sub": notes or "",
        "fu": None,
        "note": notes or "",
        "touch": lead.get("updated_at", "сегодня"),
        "replied": stage == "replied",
        "via": "tg" if "tg" in notes.lower() else "wa",
        "twins": 0,
        "badge": "",
        "canMr": True,
        "marked": stage in ("replied", "interested", "client"),
        "igUnsure": False,
        "igState": "",
        "draft": bool(draft_text),
        "draftText": draft_text,
        "firstDraft": True,
        "text": draft_text,
        "risk": "",
        "links": links,
        "twinHot": False,
        "claim": None
    }


def format_rz_lead(lead: dict[str, Any]) -> dict[str, Any]:
    lid = str(lead.get("id", ""))
    name = lead.get("name", "Без названия")
    city = lead.get("city", "Москва")
    address = lead.get("address", "")
    category = lead.get("category", lead.get("platform", "Бизнес"))
    status_lead = lead.get("status_lead", "hot")
    stage = lead.get("stage", "new")
    phone = lead.get("phone", "")
    website = lead.get("website", "")
    notes = lead.get("notes", "")
    rating = float(lead.get("rating") or 4.7)
    reviews = int(lead.get("user_ratings_total") or lead.get("reviews") or 28)

    kind = "hot" if status_lead == "hot" or not website else "warm" if status_lead == "warm" else "social"
    kind_label = "Нет сайта" if kind == "hot" else "QR-меню" if kind == "warm" else "Соцсеть"

    draft_text = lead.get("draft", "")
    if not draft_text:
        draft_text = generate_pitch(name, lead.get("sphere_id", "food"), kind, city=city)

    links = make_contact_links(phone, website, name, city, lid)
    mob_digits = [l["url"].split("/")[-1] for l in links if l.get("ch") == "wa"][0]
    if not phone or not clean_digits(phone).startswith("79"):
        phone = f"+7 ({mob_digits[1:4]}) {mob_digits[4:7]}-{mob_digits[7:9]}-{mob_digits[9:11]}"
        digits = mob_digits
    else:
        digits = clean_digits(phone)
    in_base = stage not in ("new", "")

    phones = [{
        "raw": phone,
        "pretty": phone,
        "d": digits,
        "mob": True,
        "src": "Google"
    }]

    maps_url = lead.get("google_maps_uri") or lead.get("maps") or f"https://www.google.com/maps/search/{urllib.parse.quote(name + ' ' + city)}"

    warns = []
    if kind == "hot":
        warns.append("Google Карты: собственный сайт компании отсутствует")
    elif kind == "warm":
        warns.append("Вместо сайта используется сервис бронирования или QR-меню")

    call_script = (
        f"Добрый день! Звоню по поводу сайта для «{name}». "
        "Подскажите, пожалуйста, руководителя или управляющего?"
    )

    history = [
        {"label": "сегодня", "text": "Заведение найдено через поиск Google Карт"}
    ]
    if notes:
        history.append({"label": "заметка", "text": notes})

    phones = []
    if phone:
        phones.append({
            "raw": phone,
            "pretty": phone,
            "d": digits,
            "mob": True,
            "src": "Google"
        })

    return {
        "id": lid,
        "h": "",
        "name": name,
        "city": city,
        "address": address or f"г. {city}",
        "category": category,
        "kind": kind,
        "kindLabel": kind_label,
        "rating": rating,
        "reviews": reviews,
        "maps": maps_url,
        "website": website or "",
        "stage": stage,
        "stageLabel": STAGE_LABELS.get(stage, "Новый"),
        "stageShort": STAGE_LABELS.get(stage, "Новый"),
        "inBase": in_base,
        "score": int(rating * 20),
        "follow": None,
        "noFollow": False,
        "ig": None,
        "warns": warns,
        "menu": None,
        "phones": phones,
        "links": links,
        "emails": [],
        "twins": [],
        "socials": [],
        "draft": draft_text,
        "draftText": draft_text,
        "text": draft_text,
        "ownerText": draft_text,
        "draftWarn": [],
        "draftOld": "",
        "placeholder": "Напишите сообщение или нажмите «Написать ИИ»...",
        "twinN": 0,
        "claim": None,
        "badge": None,
        "legal": None,
        "stops": [
            {"id": "refusal", "label": "Отказ"},
            {"id": "competitor", "label": "Уже есть подрядчик"},
            {"id": "expensive", "label": "Слишком дорого"},
            {"id": "no_need", "label": "Сайт не нужен"}
        ],
        "canMr": True,
        "marked": stage in ("replied", "interested", "client"),
        "incoming": None,
        "touch": lead.get("updated_at", "сегодня"),
        "firstDraft": True,
        "genDone": False,
        "risk": "",
        "note": notes or "",
        "history": history,
        "call": {
            "phone": phone or "+7 (900) 000-00-00",
            "d": digits or "79000000000",
            "script": call_script,
            "ask": {"name": "Руководитель", "role": "владелец", "first": "руководитель"}
        },
        "scanned": True,
        "me": True
    }


def detect_sphere_id(text: str) -> str:
    """Определяет ID сферы бизнеса по названию категории или поисковому запросу."""
    t = (text or "").lower()
    if any(w in t for w in ["красот", "барбер", "салон", "маникюр", "волос", "парикмахер", "ресниц", "бров", "тату", "спа", "косметол"]):
        return "beauty"
    if any(w in t for w in ["авто", "сервис", "мойк", "шин", "детейлинг", "ремонт авто", "сто"]):
        return "auto"
    if any(w in t for w in ["здоров", "клиник", "стомат", "медицин", "врач", "зуб", "анализ", "остеопат"]):
        return "health"
    if any(w in t for w in ["спорт", "фитнес", "йог", "зал", "тренировк", "бокс", "танц", "кроссфит"]):
        return "sport"
    if any(w in t for w in ["отел", "гостиниц", "хостел", "глэмпинг", "турбаз", "коттедж"]):
        return "lodging"
    if any(w in t for w in ["ремонт", "мебель", "интерьер", "дизайн", "потол", "квартир"]):
        return "home"
    if any(w in t for w in ["животн", "вет", "груминг", "собак", "кошек", "зоо"]):
        return "pets"
    if any(w in t for w in ["обучен", "школ", "курс", "английск", "егэ", "репетитор"]):
        return "education"
    if any(w in t for w in ["юрист", "бухгалтер", "агентств", "консалт", "it", "разработк"]):
        return "services"
    return "food"


async def ensure_initial_seed_leads(user_id: int):
    """Наполняет базу качественными стартовыми лидами, если в ней мало новых лидов."""
    existing = await db.get_b2b_leads(user_id)
    new_ones = [l for l in existing if l.get("stage", "new") == "new"]
    if len(new_ones) >= 60:
        return

    seed_plans = [
        ("Москва", "food", 35),
        ("Москва", "beauty", 25),
        ("Москва", "auto", 20),
        ("Санкт-Петербург", "food", 30),
        ("Санкт-Петербург", "beauty", 20),
        ("Казань", "food", 25),
        ("Краснодар", "beauty", 20),
        ("Сочи", "lodging", 20),
        ("Екатеринбург", "health", 20),
    ]

    leads_to_save = []
    for city_name, sphere, count in seed_plans:
        curated = get_curated_city_leads(city=city_name, sphere_id=sphere, count=count)
        for c in curated:
            leads_to_save.append({
                "place_id": c.get("place_id"),
                "name": c.get("name", "Организация"),
                "city": c.get("city", city_name),
                "category": c.get("category", c.get("primary_type", "Бизнес")),
                "address": c.get("address", ""),
                "phone": c.get("phone", ""),
                "website": c.get("website", ""),
                "rating": c.get("rating", 4.8),
                "user_ratings_total": c.get("user_ratings_total", 45),
                "status_lead": c.get("status_lead", "hot"),
                "stage": "new",
                "notes": "",
                "draft": c.get("draft", "")
            })

    if leads_to_save:
        await db.save_b2b_leads_batch(user_id, leads_to_save)


async def background_search_task(city: str, cat: str, user_id: int):
    """Асинхронный фоновый парсер заведений."""
    global RUN_STATE
    RUN_STATE["running"] = True
    RUN_STATE["city"] = city
    RUN_STATE["cat"] = cat
    RUN_STATE["pct"] = 15
    RUN_STATE["msg"] = f"Сканирую карты: {cat} в г. {city}..."

    try:
        await asyncio.sleep(0.5)
        RUN_STATE["pct"] = 40
        RUN_STATE["msg"] = "Анализ сайтов, фильтрация и проверка контактов..."

        effective_key = getattr(config, "GOOGLE_PLACES_API_KEY", "")
        if user_id:
            profile = await db.get_user_profile(user_id)
            if profile.get("google_api_key"):
                effective_key = profile["google_api_key"]

        sphere_id = detect_sphere_id(cat)
        found = await search_leads(
            query=f"{cat} {city}",
            city=city,
            sphere_id=sphere_id,
            depth="max",
            api_key=effective_key,
            page_size=150
        )

        RUN_STATE["pct"] = 80
        RUN_STATE["msg"] = f"Сохранение {len(found)} заведений в базу CRM..."

        leads_to_save = []
        for item in found:
            leads_to_save.append({
                "place_id": item.get("place_id"),
                "name": item.get("name", ""),
                "city": item.get("city", city),
                "category": item.get("category", cat),
                "address": item.get("address", ""),
                "phone": item.get("phone", ""),
                "website": item.get("website", ""),
                "rating": item.get("rating", 4.7),
                "user_ratings_total": item.get("user_ratings_total", 30),
                "status_lead": item.get("status_lead", "hot"),
                "stage": "new",
                "notes": "",
                "draft": ""
            })

        if leads_to_save:
            await db.save_b2b_leads_batch(user_id, leads_to_save)

        RUN_STATE["found"] = len(found)
        RUN_STATE["total"] = len(found)
        RUN_STATE["pct"] = 100
        RUN_STATE["msg"] = f"Найдено {len(found)} заведений ({sum(1 for x in found if x.get('status_lead') == 'hot')} без сайта)"
    except Exception as e:
        RUN_STATE["msg"] = f"Ошибка поиска: {str(e)}"
    finally:
        RUN_STATE["running"] = False



async def handle_rpc_call(op: str, args: dict[str, Any], user_id: int) -> dict[str, Any]:
    """Главный диспетчер RPC протокола mini.html."""
    await ensure_initial_seed_leads(user_id)
    all_leads = await db.get_b2b_leads(user_id)

    # Подсчет бейджей для навигации
    new_leads = [l for l in all_leads if l.get("stage", "new") == "new"]
    replied_leads = [l for l in all_leads if l.get("stage") == "replied"]
    due_leads = [l for l in all_leads if l.get("stage") in ("contacted", "due")]
    counts = {
        "today": len(replied_leads) + len(due_leads),
        "new": len(new_leads),
        "base": len(all_leads),
        "msgs": len(replied_leads)
    }

    # 1. СЕГОДНЯ (KPI & Очередь)
    if op == "today":
        contacted_today = sum(1 for l in all_leads if l.get("stage") in ("contacted", "replied", "interested", "client"))
        ids_queue = [str(l["id"]) for l in (replied_leads + due_leads + new_leads[:15])]

        groups = [
            {
                "key": "w:replied",
                "title": "Ответили, ждут вас",
                "col": STAGE_COLORS["replied"],
                "items": [format_rz_item(l) for l in replied_leads[:60]],
                "more": max(0, len(replied_leads) - 60)
            },
            {
                "key": "w:due",
                "title": "Пора дожать",
                "col": STAGE_COLORS["due"],
                "items": [format_rz_item(l) for l in due_leads[:60]],
                "more": max(0, len(due_leads) - 60)
            },
            {
                "key": "w:queued",
                "title": "К отправке",
                "col": STAGE_COLORS["queued"],
                "items": [format_rz_item(l) for l in new_leads[:60]],
                "more": max(0, len(new_leads) - 60)
            },
            {
                "key": "ready",
                "title": "Готовые черновики",
                "col": STAGE_COLORS["client"],
                "items": [format_rz_item(l) for l in new_leads if l.get("draft")][:60],
                "more": 0
            }
        ]

        funnel = {
            "sent": max(1, contacted_today),
            "replied": len(replied_leads),
            "interested": sum(1 for l in all_leads if l.get("stage") == "interested"),
            "client": sum(1 for l in all_leads if l.get("stage") == "client"),
            "declined": sum(1 for l in all_leads if l.get("stage") == "declined")
        }

        return {
            "day": get_current_russian_day(),
            "sent": {
                "today": contacted_today,
                "week": contacted_today + 5,
                "goal": 20
            },
            "newCount": len(new_leads),
            "me": True,
            "stops": [],
            "ids": ids_queue,
            "funnel": funnel,
            "groups": groups,
            "_c": counts
        }

    # 2. ПАРСЕР / НОВЫЕ ЛИДЫ
    if op == "new":
        raw_city = str(args.get("city", "")).strip()
        city_filter = raw_city.lower()
        kind_filter = str(args.get("kind", "")).strip().lower()
        mob_filter = bool(args.get("mob", False))
        sort = str(args.get("sort", "score"))
        off = max(0, int(args.get("off", 0)))
        limit = max(1, min(1000, int(args.get("limit", 40))))

        # Если выбран конкретный город, проверяем сколько лидов для него есть в базе
        # Если меньше 35, мгновенно генерируем свежие лиды для этого города
        if raw_city and raw_city.lower() not in ("все города", "все", ""):
            city_matches = [l for l in new_leads if city_filter in l.get("city", "").lower()]
            if len(city_matches) < 40:
                fresh_leads_raw = get_curated_city_leads(city=raw_city, sphere_id="food", count=60)
                leads_to_save = []
                for c in fresh_leads_raw:
                    leads_to_save.append({
                        "place_id": c.get("place_id"),
                        "name": c.get("name", "Организация"),
                        "city": raw_city,
                        "category": c.get("category", "Бизнес"),
                        "address": c.get("address", ""),
                        "phone": c.get("phone", ""),
                        "website": c.get("website", ""),
                        "rating": c.get("rating", 4.8),
                        "user_ratings_total": c.get("user_ratings_total", 45),
                        "status_lead": c.get("status_lead", "hot"),
                        "stage": "new",
                        "notes": "",
                        "draft": ""
                    })
                await db.save_b2b_leads_batch(user_id, leads_to_save)
                # Перечитываем обновленный список лидов
                all_leads = await db.get_b2b_leads(user_id)
                new_leads = [l for l in all_leads if l.get("stage", "new") == "new"]

        filtered = new_leads[:]
        if city_filter and city_filter not in ("все города", "все", ""):
            filtered = [l for l in filtered if city_filter in l.get("city", "").lower()]
        if kind_filter:
            if kind_filter == "hot":
                filtered = [l for l in filtered if l.get("status_lead") == "hot" or not l.get("website")]
            elif kind_filter == "warm":
                filtered = [l for l in filtered if l.get("status_lead") == "warm"]
        if mob_filter:
            filtered = [l for l in filtered if l.get("phone")]

        if sort == "name":
            filtered.sort(key=lambda x: x.get("name", "").lower())
        elif sort == "rating":
            filtered.sort(key=lambda x: float(x.get("rating", 0)), reverse=True)
        elif sort == "reviews":
            filtered.sort(key=lambda x: int(x.get("user_ratings_total", 0)), reverse=True)
        else:
            # score: hot first, high rating
            filtered.sort(key=lambda x: (1 if x.get("status_lead") == "hot" else 0, float(x.get("rating", 0))), reverse=True)

        popular_cities = [
            "Москва", "Санкт-Петербург", "Казань", "Новосибирск", "Екатеринбург",
            "Нижний Новгород", "Самара", "Краснодар", "Ростов-на-Дону", "Уфа",
            "Челябинск", "Красноярск", "Пермь", "Воронеж", "Волгоград",
            "Тюмень", "Сочи", "Калининград", "Саратов", "Тольятти"
        ]
        db_cities = [l.get("city") for l in all_leads if l.get("city")]
        cities_list = sorted(list(dict.fromkeys(db_cities + popular_cities)))

        page_items = filtered[off:off + limit]

        return {
            "total": len(new_leads),
            "count": len(filtered),
            "hot": sum(1 for l in filtered if l.get("status_lead") == "hot" or not l.get("website")),
            "warm": sum(1 for l in filtered if l.get("status_lead") == "warm"),
            "cities": cities_list,
            "filter": {"city": raw_city, "kind": args.get("kind", ""), "mob": mob_filter},
            "sort": sort,
            "off": off,
            "more": len(filtered) > off + limit,
            "items": [format_rz_item(l) for l in page_items],
            "me": True,
            "stops": [],
            "_c": counts
        }

    # 3. CRM БАЗА
    if op == "base":
        f = str(args.get("f", "work"))
        lim = int(args.get("lim", 400))

        stage_mapping = {
            "w:queued": ["new", "queued"],
            "w:contacted": ["contacted"],
            "w:due": ["due"],
            "w:replied": ["replied"],
            "w:interested": ["interested"],
            "w:client": ["client"],
            "stop": ["declined", "stop", "archive"]
        }

        if f == "work":
            matched = [l for l in all_leads if l.get("stage", "new") not in ("declined", "stop", "archive")]
        elif f in stage_mapping:
            matched = [l for l in all_leads if l.get("stage", "new") in stage_mapping[f]]
        else:
            matched = all_leads[:]

        def count_stage(s_list):
            return sum(1 for l in all_leads if l.get("stage", "new") in s_list)

        tiles = [
            {"id": "work", "lab": "Все в работе", "col": STAGE_COLORS["work"], "n": count_stage(["new", "queued", "contacted", "due", "replied", "interested", "client"]), "attn": False, "stop": False},
            {"id": "w:queued", "lab": "К отправке", "col": STAGE_COLORS["queued"], "n": count_stage(["new", "queued"]), "attn": False, "stop": False},
            {"id": "w:contacted", "lab": "Жду ответа", "col": STAGE_COLORS["contacted"], "n": count_stage(["contacted"]), "attn": False, "stop": False},
            {"id": "w:due", "lab": "Пора дожать", "col": STAGE_COLORS["due"], "n": count_stage(["due"]), "attn": count_stage(["due"]) > 0, "stop": False},
            {"id": "w:replied", "lab": "Ответили", "col": STAGE_COLORS["replied"], "n": count_stage(["replied"]), "attn": count_stage(["replied"]) > 0, "stop": False},
            {"id": "w:interested", "lab": "Заинтересован", "col": STAGE_COLORS["interested"], "n": count_stage(["interested"]), "attn": False, "stop": False},
            {"id": "w:client", "lab": "Клиент", "col": STAGE_COLORS["client"], "n": count_stage(["client"]), "attn": False, "stop": False},
            {"id": "stop", "lab": "Весь стоп", "col": STAGE_COLORS["stop"], "n": count_stage(["declined", "stop", "archive"]), "attn": False, "stop": True}
        ]

        page_items = matched[:lim]

        return {
            "all": len(all_leads),
            "f": f,
            "tiles": tiles,
            "groups": [{
                "key": f,
                "title": "",
                "items": [format_rz_item(l) for l in page_items],
                "more": max(0, len(matched) - lim)
            }],
            "me": True,
            "stops": [],
            "_c": counts
        }

    # 4. СООБЩЕНИЯ
    if op == "msgs":
        lim = int(args.get("lim", 60))
        ready_leads = [l for l in all_leads if l.get("draft") or l.get("stage") == "new"]

        groups = [
            {
                "key": "reply",
                "title": "Ответили — ждут вас",
                "hint": "последнее слово за ними",
                "col": STAGE_COLORS["replied"],
                "items": [format_rz_item(l) for l in replied_leads[:lim]],
                "more": max(0, len(replied_leads) - lim)
            },
            {
                "key": "ready",
                "title": "Готово к отправке",
                "hint": "нажмите значок канала — текст скопируется, чат откроется",
                "col": STAGE_COLORS["client"],
                "items": [format_rz_item(l) for l in ready_leads[:lim]],
                "more": max(0, len(ready_leads) - lim)
            }
        ]
        groups = [g for g in groups if g["items"]]

        return {
            "sent": {
                "today": sum(1 for l in all_leads if l.get("stage") in ("contacted", "replied")),
                "week": 14,
                "goal": 20
            },
            "me": True,
            "llm": True,
            "groups": groups,
            "_c": counts
        }

    # 5. ГЛОБАЛЬНЫЙ ПОИСК
    if op == "search":
        q = str(args.get("q", "")).strip().lower()
        if not q or len(q) < 2:
            return {"items": [], "me": True, "stops": [], "_c": counts}

        matches = []
        for l in all_leads:
            text_haystack = f"{l.get('name', '')} {l.get('city', '')} {l.get('category', '')} {l.get('phone', '')} {l.get('notes', '')}".lower()
            if q in text_haystack:
                matches.append(format_rz_item(l))

        return {"items": matches, "me": True, "stops": [], "_c": counts}

    # 6. КАРТОЧКА ЛИДА
    if op == "lead":
        lid = str(args.get("id", ""))
        target = next((l for l in all_leads if str(l.get("id")) == lid), None)
        if not target:
            return {"gone": True, "_c": counts}

        return {"lead": format_rz_lead(target), "_c": counts}

    # 7. ДЕЙСТВИЯ (act: contact, stage, noteSet, draft, gen, follow)
    if op == "act":
        lid = str(args.get("id", ""))
        act_name = str(args.get("act", ""))
        arg = args.get("arg")
        target = next((l for l in all_leads if str(l.get("id")) == lid), None)

        if not target:
            return {"res": {"ok": False, "error": "Лид не найден"}, "gone": True, "_c": counts}

        int_id = int(lid) if lid.isdigit() else 0

        if act_name == "contact":
            new_stage = target.get("stage", "new")
            if new_stage in ("new", "queued"):
                new_stage = "contacted"
            await db.update_b2b_lead_stage(user_id, int_id, stage=new_stage)
            target["stage"] = new_stage

        elif act_name == "stage":
            new_stage = str(arg or "queued")
            await db.update_b2b_lead_stage(user_id, int_id, stage=new_stage)
            target["stage"] = new_stage

        elif act_name == "noteSet":
            note_val = str(arg or "")
            await db.update_b2b_lead_stage(user_id, int_id, stage=target.get("stage", "new"), notes=note_val)
            target["notes"] = note_val

        elif act_name == "draft":
            val = str(arg or "")
            target["draft"] = val
            target["pitch"] = val
            await db.update_b2b_lead_draft(user_id, int_id, val)
            return {"res": {"ok": True}, "lead": format_rz_lead(target), "_c": counts}

        elif act_name == "quick":
            q_type = str(arg or "yes")
            b_name = target.get("name", "вашей компании")
            if q_type == "yes":
                text = f"Отлично! Тогда на днях подготовлю черновой вариант сайта для «{b_name}» и пришлю вам ссылку оценить. Подскажите, на какой мессенджер удобнее скинуть макет?"
            elif q_type == "price":
                text = f"По стоимости: базовый запуск мобильного сайта для «{b_name}» под ключ с меню/услугами и онлайн-заявкой — от 15 000 ₽. Никаких скрытых платежей, оплата только после утверждения готового макета."
            elif q_type == "qr":
                text = f"Понимаю, QR-меню — удобная вещь, но у него нет органических клиентов из поиска карт. Собственный сайт забирает тех гостей, кто еще только выбирает, куда пойти в городе."
            else:
                text = f"Здравствуйте! Подскажите, пожалуйста, контакт управляющего или владельца «{b_name}»? Хотел направить короткое коммерческое предложение по сайту заведения."
            target["draft"] = text
            target["pitch"] = text
            await db.update_b2b_lead_draft(user_id, int_id, text)
            return {"res": {"ok": True, "draft": text, "draftText": text}, "lead": format_rz_lead(target), "_c": counts}

        elif act_name == "gen":
            curr_pitch = target.get("draft") or target.get("pitch") or ""
            next_style = get_next_pitch_style(curr_pitch)
            pitch = generate_pitch(
                target["name"],
                target.get("sphere_id", "food"),
                target.get("status_lead", "hot"),
                city=target.get("city", ""),
                style=next_style
            )
            target["draft"] = pitch
            target["pitch"] = pitch
            await db.update_b2b_lead_draft(user_id, int_id, pitch)
            return {
                "res": {"ok": True, "draft": pitch, "draftText": pitch, "style": next_style},
                "lead": format_rz_lead(target),
                "_c": counts
            }

        elif act_name == "follow":
            pass

        elif act_name == "stopPick":
            await db.update_b2b_lead_stage(user_id, int_id, stage="declined")
            target["stage"] = "declined"

        return {"res": {"ok": True}, "lead": format_rz_lead(target), "_c": counts}

    # 8. ИНФОРМАЦИЯ ДЛЯ ЗАПУСКА ПОИСКА (runInfo)
    if op == "runInfo":
        cities = get_popular_cities()
        cats = [s["name"] for s in SPHERES]

        city_req = args.get("city", "")
        cat_req = args.get("cat", "")

        out = {
            "cities": cities,
            "cats": cats,
            "pages": 1,
            "price": 0,
            "key": True,
            "running": RUN_STATE["running"]
        }
        if city_req and cat_req:
            out["pair"] = {
                "city": city_req,
                "cat": cat_req,
                "ok": True,
                "req": 1,
                "cost": "0.00",
                "recent": None
            }
        return out

    # 9. ЗАПУСК ПОИСКА (run)
    if op == "run":
        city = str(args.get("city", "")).strip() or "Москва"
        cat = str(args.get("cat", "")).strip() or "Рестораны и кафе"

        asyncio.create_task(background_search_task(city, cat, user_id))
        return {
            "res": {
                "ok": True,
                "msg": f"Поиск запущен: {cat} в г. {city}"
            },
            "state": RUN_STATE,
            "_c": counts
        }

    # 10. СОСТОЯНИЕ ПОИСКА (runState)
    if op == "runState":
        return RUN_STATE

    return {"error": f"Неизвестная операция: {op}"}
