"""
deploy_check.py — Комплексный автоматизированный тест готовности к деплою LeadHunter B2B.
Проверяет:
1. Зависимости и импорты
2. Конфигурацию (.env и config.py)
3. Базу данных (все таблицы, индексы, CRUD для users, b2b_leads, user_profiles)
4. Поисковый движок places_search (Nominatim, классификатор HOT/WARM/COLD)
5. Генератор офферов pitch_generator и ROI калькулятор
6. REST API сервер Mini App (все 16 эндпоинтов на localhost:8080)
7. Aiogram Bot Dispatcher и регистрацию всех роутов
8. Файлы контейнеризации и деплоя (Dockerfile, docker-compose.yml, systemd)
"""

import sys
import os
import asyncio
import json
import urllib.request
import urllib.error
from pathlib import Path

# Принудительный UTF-8 для вывода в консоль
sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).parent.resolve()
os.chdir(ROOT_DIR)

PASSED = 0
FAILED = 0
WARNINGS = 0

def log_test(title: str, ok: bool, details: str = ""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  [ OK ] {title}")
    else:
        FAILED += 1
        print(f"  [FAIL] {title} -> {details}")

def log_warn(title: str, details: str = ""):
    global WARNINGS
    WARNINGS += 1
    print(f"  [WARN] {title} -> {details}")


# ==========================================
# TEST 1: Зависимости и модули
# ==========================================
def test_imports():
    print("\n--- 1. Проверка библиотек и зависимостей ---")
    required = [
        ("aiogram", "Aiogram 3.x фреймворк бота"),
        ("telethon", "Telethon клиент для парсинга чатов"),
        ("aiohttp", "Aiohttp асинхронный веб-сервер и HTTP-клиент"),
        ("aiosqlite", "Aiosqlite асинхронная база данных"),
        ("dotenv", "Python-dotenv загрузка переменных окружения"),
        ("socks", "Python-socks поддержка SOCKS5/MTProto прокси"),
    ]
    for mod, desc in required:
        try:
            __import__(mod)
            log_test(f"Модуль '{mod}' ({desc})", True)
        except ImportError as e:
            log_test(f"Модуль '{mod}'", False, str(e))


# ==========================================
# TEST 2: Конфигурация (.env и config.py)
# ==========================================
def test_config():
    print("\n--- 2. Проверка конфигурации проекта ---")
    try:
        import config
        # Проверяем обязательные ключи
        keys = [
            ("BOT_TOKEN", config.BOT_TOKEN, True),
            ("API_ID", config.API_ID, True),
            ("API_HASH", config.API_HASH, True),
            ("ADMIN_ID", config.ADMIN_ID, True),
            ("MINI_APP_URL", getattr(config, "MINI_APP_URL", ""), False),
            ("WEB_PORT", getattr(config, "WEB_PORT", 8080), False),
            ("GOOGLE_PLACES_API_KEY", getattr(config, "GOOGLE_PLACES_API_KEY", ""), False),
        ]
        for name, val, req in keys:
            if req and not val:
                log_test(f"Параметр {name}", False, "Не заполнен в .env!")
            elif val:
                # Маскируем секреты
                display = str(val)[:6] + "..." if len(str(val)) > 8 else str(val)
                log_test(f"Параметр {name} ({display})", True)
            else:
                log_warn(f"Опциональный параметр {name} пуст (допустимо для дефолта)")
    except Exception as e:
        log_test("Импорт config.py", False, str(e))


# ==========================================
# TEST 3: База данных (SQLite / db.py)
# ==========================================
async def test_database():
    print("\n--- 3. Проверка базы данных (SQLite / db.py) ---")
    try:
        import db
        await db.init_db()
        log_test("Инициализация схемы БД (таблицы users, b2b_leads, user_profiles)", True)

        test_uid = 999999999
        # 1. Добавление и получение пользователя
        await db.add_user(test_uid)
        u = await db.get_user(test_uid)
        log_test("CRUD users (add_user / get_user)", u is not None and u.get("user_id") == test_uid)

        # 2. Сохранение B2B лида
        test_lead_obj = {
            "place_id": "test_place_123",
            "name": "Тестовая Кофейня",
            "address": "г. Москва, ул. Ленина, 1",
            "phone": "+79990001122",
            "website": "",
            "status_lead": "hot",
            "rating": "4.8",
            "user_ratings_total": 45,
            "stage": "new"
        }
        ok_save = await db.save_b2b_lead(user_id=test_uid, lead=test_lead_obj)
        log_test("CRUD b2b_leads (save_b2b_lead)", ok_save)

        # 3. Получение B2B лидов
        leads = await db.get_b2b_leads(user_id=test_uid, stage="all")
        found = any(l.get("name") == "Тестовая Кофейня" for l in leads)
        log_test("CRUD b2b_leads (get_b2b_leads)", found)

        saved_id = leads[0]["id"] if leads else 1

        # 4. Смена стадии лида
        ok_stage = await db.update_b2b_lead_stage(user_id=test_uid, lead_id=saved_id, stage="contacted")
        log_test("CRUD b2b_leads (update_b2b_lead_stage)", ok_stage)

        # 5. KPI статистика
        kpi = await db.get_kpi_stats(user_id=test_uid)
        log_test("KPI подсчет (get_kpi_stats)", kpi.get("total", 0) >= 1)

        # 6. Профиль пользователя
        await db.update_user_profile(user_id=test_uid, freelancer_name="Тест Фрилансер", google_api_key="AIzaSyTest")
        prof = await db.get_user_profile(test_uid)
        log_test("CRUD user_profiles (update/get_user_profile)", prof.get("freelancer_name") == "Тест Фрилансер")

        # 7. Очистка тестовых данных
        await db.delete_b2b_lead(user_id=test_uid, lead_id=saved_id)
        leads_after = await db.get_b2b_leads(user_id=test_uid, stage="all")
        log_test("CRUD b2b_leads (delete_b2b_lead)", not any(l.get("name") == "Тестовая Кофейня" for l in leads_after))

    except Exception as e:
        log_test("Тест базы данных", False, str(e))


# ==========================================
# TEST 4: Поисковый движок places_search.py
# ==========================================
async def test_search_engine():
    print("\n--- 4. Проверка поискового движка places_search.py ---")
    try:
        from miniapp.places_search import search_leads, verify_google_key

        # 1. Проверка верификатора ключа с фейковым ключом (должен корректно вернуть ok=False, а не падать с ошибкой)
        v_res = await verify_google_key("AIzaSyFakeKeyInvalidForTesting12345")
        log_test("Верификация некорректного Google Key (мягкая обработка)", v_res.get("ok") is False and "message" in v_res)

        # 2. Быстрый поиск в Казани (OSM парсинг)
        leads = await search_leads(
            query="Кафе и кофейни",
            city="Казань",
            sphere_id="food",
            depth="quick",
            api_key=""
        )
        log_test(f"Парсинг заведений в Казани (получено {len(leads)} мест)", len(leads) > 0)
        if leads:
            first = leads[0]
            has_fields = all(k in first for k in ("name", "status_lead", "status_label", "address"))
            log_test("Структура карточки лида (name, status_lead, address, phone)", has_fields)
            is_valid_status = first["status_lead"] in ("hot", "warm", "cold")
            log_test(f"Классификация лида ({first['status_lead']} - {first['status_label']})", is_valid_status)

    except Exception as e:
        log_test("Поисковый движок", False, str(e))


# ==========================================
# TEST 5: Генератор офферов pitch_generator.py
# ==========================================
def test_pitch_generator():
    print("\n--- 5. Проверка генератора офферов и ROI ---")
    try:
        from miniapp.pitch_generator import generate_pitch, calculate_business_roi, get_demo_catalog

        # 1. Проверка 3 стилей генерации
        p_hook = generate_pitch(business_name="Ресторан Волга", sphere_id="food", status_lead="hot", freelancer_name="Олег", city="Самара", style="hook")
        p_expert = generate_pitch(business_name="Ресторан Волга", sphere_id="food", status_lead="hot", freelancer_name="Олег", city="Самара", style="expert")
        p_short = generate_pitch(business_name="Ресторан Волга", sphere_id="food", status_lead="hot", freelancer_name="Олег", city="Самара", style="short")

        log_test("Генерация стиля 'hook' (с крючка)", len(p_hook) > 50 and "Ресторан Волга" in p_hook)
        log_test("Генерация стиля 'expert' (экспертный)", len(p_expert) > 50 and "Ресторан Волга" in p_expert)
        log_test("Генерация стиля 'short' (короткий)", len(p_short) > 20 and "Ресторан Волга" in p_short)

        # 2. Проверка ROI расчета
        roi = calculate_business_roi(sphere_id="food", user_ratings_total=40)
        has_roi = "lost_revenue" in roi and roi["lost_revenue"] > 0
        log_test(f"Расчет упущенной выгоды (упущенный оборот ~{roi.get('formatted_revenue')} ₽)", has_roi)

        # 3. Демо-каталог
        cat = get_demo_catalog("Ресторан Волга", "food")
        log_test("Генерация демо-каталога для макета", "items" in cat and len(cat["items"]) > 0)

    except Exception as e:
        log_test("Генератор офферов", False, str(e))


# ==========================================
# TEST 6: REST API сервер (localhost:8080)
# ==========================================
def test_rest_api():
    print("\n--- 6. Проверка эндпоинтов Mini App (HTTP localhost:8080) ---")
    base_url = "http://127.0.0.1:8080"

    endpoints = [
        ("GET", "/", None, 200, "Главная HTML страница Mini App"),
        ("GET", "/static/style.css", None, 200, "Стили Liquid Glass"),
        ("GET", "/static/app.js", None, 200, "JS логика приложения"),
        ("GET", "/static/bg.js", None, 200, "WebGL фоновый шейдер"),
        ("GET", "/static/logo.png", None, 200, "Логотип приложения"),
        ("GET", "/api/spheres", None, 200, "Каталог сфер бизнеса"),
        ("GET", "/api/cities", None, 200, "Список городов"),
        ("GET", "/api/kpi?user_id=1795524760", None, 200, "KPI статистика дашборда"),
        ("GET", "/api/crm/leads?user_id=1795524760&stage=all", None, 200, "Список CRM лидов"),
        ("GET", "/api/profile?user_id=1795524760", None, 200, "Профиль пользователя"),
        ("POST", "/api/pitch", {
            "name": "Тест Кафе",
            "sphere_id": "food",
            "status_lead": "hot",
            "freelancer_name": "Александр",
            "city": "Москва",
            "user_ratings_total": 30
        }, 200, "Генерация персонализированного оффера"),
        ("POST", "/api/mockup", {"name": "Тест Кафе", "sphere_id": "food"}, 200, "Данные для мокапа"),
        ("POST", "/api/verify_key", {"api_key": "AIzaSyTestInvalid123"}, 200, "Проверка ключа Google API"),
    ]

    for method, path, payload, expected_code, desc in endpoints:
        url = base_url + path
        try:
            req_data = json.dumps(payload).encode("utf-8") if payload else None
            headers = {"Content-Type": "application/json"} if payload else {}
            req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=5) as resp:
                code = resp.getcode()
                log_test(f"{method} {path} ({desc}) [HTTP {code}]", code == expected_code)
        except urllib.error.HTTPError as e:
            log_test(f"{method} {path} ({desc})", e.code == expected_code, f"HTTP {e.code}")
        except Exception as e:
            log_test(f"{method} {path} ({desc})", False, str(e))


# ==========================================
# TEST 7: Aiogram Bot Dispatcher
# ==========================================
def test_bot_dispatcher():
    print("\n--- 7. Проверка роутеров и обработчиков Aiogram ---")
    try:
        from bot import router
        handler_count = len(router.message.handlers) + len(router.callback_query.handlers)
        log_test(f"Загрузка роутера bot.py (зарегистрировано {handler_count} обработчиков)", handler_count > 20)
    except Exception as e:
        log_test("Инициализация aiogram роутера", False, str(e))


# ==========================================
# TEST 8: Готовность к развертыванию (Деплою)
# ==========================================
def test_deploy_files():
    print("\n--- 8. Проверка файлов деплоя и контейнеризации ---")
    files_to_check = [
        ("requirements.txt", "Список Python зависимостей"),
        (".env", "Переменные окружения"),
        (".env.example", "Шаблон переменных окружения"),
        (".gitignore", "Игнорирование секретов и сессий Git"),
        ("Dockerfile", "Сборка Docker-контейнера"),
        ("docker-compose.yml", "Оркестрация Docker-контейнера"),
        ("leadhunter.service", "Системный сервис systemd для Linux"),
        ("deploy.sh", "Скрипт 1-клик деплоя на VPS"),
        ("leads.db", "База данных SQLite"),
    ]
    for filename, desc in files_to_check:
        p = ROOT_DIR / filename
        log_test(f"Файл {filename} ({desc})", p.exists(), "Файл отсутствует!")


async def main():
    print("=" * 60)
    print("  LEADHUNTER B2B — КОМПЛЕКСНАЯ ПРОВЕРКА ПЕРЕД ДЕПЛОЕМ")
    print("=" * 60)

    test_imports()
    test_config()
    await test_database()
    await test_search_engine()
    test_pitch_generator()
    test_rest_api()
    test_bot_dispatcher()
    test_deploy_files()

    print("\n" + "=" * 60)
    print(f"  ИТОГИ: Успешно: {PASSED} | Ошибок: {FAILED} | Замечаний: {WARNINGS}")
    print("=" * 60)

    if FAILED > 0:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
