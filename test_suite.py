"""
test_suite.py — Полный автоматизированный тестовый комплекс для LeadHunter.
Проверяет все уровни системы:
  1. HTTP Web Server & Статические ассеты (HTML, JS, PNG, CSS)
  2. RPC протокол Mini App (/api: today, new, base, msgs, search, lead, act, runInfo, runState)
  3. База данных SQLite & CRM воронка (CRUD, переходы статусов, заметки, профили)
  4. Поисковый движок и классификатор сайтов (HOT, WARM, COLD)
  5. Генератор офферов ИИ и расчет ROI
  6. Конфигурация и логика Telegram-бота
"""

import sys
import json
import asyncio
import unittest
import urllib.request
import urllib.parse
from pathlib import Path

# Подключение корневого каталога к sys.path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

import db
import config
from miniapp.places_search import classify_website, extract_host
from miniapp.real_leads_db import clean_phone_number
from miniapp.pitch_generator import generate_pitch, calculate_business_roi
from miniapp.rpc_handler import handle_rpc_call, format_rz_item, format_rz_lead

BASE_URL = "http://127.0.0.1:8080"


class TestWebServerAndAssets(unittest.TestCase):
    """Тестирование HTTP сервера и доступности ассетов."""

    def test_01_index_html(self):
        req = urllib.request.urlopen(f"{BASE_URL}/", timeout=5)
        self.assertEqual(req.status, 200)
        html = req.read().decode("utf-8")
        self.assertIn("<title>LeadHunter</title>", html)
        self.assertIn('<canvas id="bg"', html)
        self.assertIn("telegram-web-app.js", html)
        self.assertIn('data-tab="today"', html)
        self.assertIn('data-tab="new"', html)
        self.assertIn('data-tab="base"', html)
        self.assertIn('data-tab="msgs"', html)

    def test_02_bg_js(self):
        req = urllib.request.urlopen(f"{BASE_URL}/bg.js", timeout=5)
        self.assertEqual(req.status, 200)
        content = req.read().decode("utf-8")
        self.assertIn("RZGfx", content)
        self.assertGreater(len(content), 50000)

    def test_03_logo_png(self):
        req = urllib.request.urlopen(f"{BASE_URL}/logo.png", timeout=5)
        self.assertEqual(req.status, 200)
        content = req.read()
        self.assertTrue(content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_04_rest_endpoints(self):
        # Spheres
        req_spheres = urllib.request.urlopen(f"{BASE_URL}/api/spheres", timeout=5)
        self.assertEqual(req_spheres.status, 200)
        spheres = json.loads(req_spheres.read().decode("utf-8"))
        self.assertTrue(spheres.get("ok"))
        self.assertGreaterEqual(len(spheres.get("spheres", [])), 5)

        # Cities
        req_cities = urllib.request.urlopen(f"{BASE_URL}/api/cities", timeout=5)
        self.assertEqual(req_cities.status, 200)
        cities = json.loads(req_cities.read().decode("utf-8"))
        self.assertTrue(cities.get("ok"))
        self.assertGreaterEqual(len(cities.get("cities", [])), 10)


class TestMiniAppRPC(unittest.TestCase):
    """Тестирование RPC протокола Telegram Mini App (/api)."""

    def _call_rpc(self, op: str, args: dict = None) -> dict:
        payload = json.dumps({"op": op, "args": args or {}}).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/api",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            return json.loads(resp.read().decode("utf-8"))

    def test_01_op_today(self):
        data = self._call_rpc("today")
        self.assertIn("day", data)
        self.assertIn("sent", data)
        self.assertIn("goal", data["sent"])
        self.assertEqual(data["sent"]["goal"], 20)
        self.assertIn("groups", data)
        group_keys = [g["key"] for g in data["groups"]]
        self.assertIn("w:replied", group_keys)
        self.assertIn("w:due", group_keys)
        self.assertIn("w:queued", group_keys)
        self.assertIn("ready", group_keys)
        self.assertIn("_c", data)
        self.assertIn("today", data["_c"])
        self.assertIn("new", data["_c"])
        self.assertIn("base", data["_c"])

    def test_02_op_new(self):
        data = self._call_rpc("new", {"limit": 10})
        self.assertIn("total", data)
        self.assertIn("count", data)
        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)
        if data["items"]:
            item = data["items"][0]
            self.assertIn("id", item)
            self.assertIn("name", item)
            self.assertIn("city", item)
            self.assertIn("kind", item)
            self.assertIn("kindLabel", item)
            self.assertIn("rating", item)
            self.assertIn("reviews", item)
            self.assertIn("stage", item)
            self.assertIn("links", item)

    def test_03_op_new_filters_and_sorting(self):
        # Filter by city
        data_city = self._call_rpc("new", {"city": "Москва", "limit": 10})
        for it in data_city.get("items", []):
            self.assertIn("москва", it["city"].lower())

        # Filter by kind: hot (no website)
        data_hot = self._call_rpc("new", {"kind": "hot", "limit": 10})
        for it in data_hot.get("items", []):
            self.assertEqual(it["kind"], "hot")

        # Sort by rating
        data_rating = self._call_rpc("new", {"sort": "rating", "limit": 10})
        ratings = [it["rating"] for it in data_rating.get("items", []) if it.get("rating") is not None]
        self.assertEqual(ratings, sorted(ratings, reverse=True))

    def test_04_op_base_and_tiles(self):
        data = self._call_rpc("base", {"f": "work"})
        self.assertIn("all", data)
        self.assertIn("tiles", data)
        self.assertIn("groups", data)
        tile_ids = [t["id"] for t in data["tiles"]]
        self.assertIn("work", tile_ids)
        self.assertIn("w:queued", tile_ids)
        self.assertIn("w:contacted", tile_ids)
        self.assertIn("w:replied", tile_ids)
        self.assertIn("w:client", tile_ids)
        self.assertIn("stop", tile_ids)

    def test_05_op_msgs(self):
        data = self._call_rpc("msgs")
        self.assertIn("sent", data)
        self.assertIn("groups", data)
        self.assertTrue(data.get("me"))

    def test_06_op_search(self):
        data = self._call_rpc("search", {"q": "Кофейня"})
        self.assertIn("items", data)
        self.assertIsInstance(data["items"], list)
        for it in data["items"]:
            self.assertTrue(
                "кофейня" in it["name"].lower() or "кофейня" in it.get("category", "").lower()
            )

        # Empty search
        empty_data = self._call_rpc("search", {"q": ""})
        self.assertEqual(empty_data["items"], [])

    def test_07_op_lead_and_drawer(self):
        # Get an existing lead
        base_data = self._call_rpc("base", {"f": "work"})
        items = base_data.get("groups", [{}])[0].get("items", [])
        if not items:
            items = self._call_rpc("new", {"limit": 5}).get("items", [])
        self.assertTrue(len(items) > 0, "Needs at least 1 lead")
        lead_id = items[0]["id"]

        data = self._call_rpc("lead", {"id": lead_id})
        self.assertIn("lead", data)
        l = data["lead"]
        self.assertEqual(l["id"], lead_id)
        self.assertIn("name", l)
        self.assertIn("address", l)
        self.assertIn("maps", l)
        self.assertIn("phones", l)
        self.assertIn("links", l)
        self.assertIn("call", l)
        self.assertIn("script", l["call"])

        # Test non-existent lead
        gone_data = self._call_rpc("lead", {"id": "999999"})
        self.assertTrue(gone_data.get("gone"))

    def test_08_op_act_lifecycle(self):
        base_data = self._call_rpc("base", {"f": "work"})
        items = base_data.get("groups", [{}])[0].get("items", [])
        if not items:
            items = self._call_rpc("new", {"limit": 5}).get("items", [])
        self.assertTrue(len(items) > 0, "Needs at least 1 lead")
        lead_id = items[0]["id"]

        # Ensure stage is new first
        self._call_rpc("act", {"id": lead_id, "act": "stage", "arg": "new"})

        # 1. Contact
        res_contact = self._call_rpc("act", {"id": lead_id, "act": "contact"})
        self.assertTrue(res_contact.get("res", {}).get("ok"))
        self.assertEqual(res_contact["lead"]["stage"], "contacted")

        # 2. NoteSet
        res_note = self._call_rpc("act", {"id": lead_id, "act": "noteSet", "arg": "Тестовая заметка 123"})
        self.assertTrue(res_note.get("res", {}).get("ok"))
        self.assertEqual(res_note["lead"]["note"], "Тестовая заметка 123")

        # 3. Draft & AI Pitch Gen
        res_gen = self._call_rpc("act", {"id": lead_id, "act": "gen"})
        self.assertTrue(res_gen.get("res", {}).get("ok"))
        self.assertTrue(len(res_gen.get("res", {}).get("draft", "")) > 20)

        # 4. Stage advance to client
        res_stage = self._call_rpc("act", {"id": lead_id, "act": "stage", "arg": "client"})
        self.assertTrue(res_stage.get("res", {}).get("ok"))
        self.assertEqual(res_stage["lead"]["stage"], "client")

    def test_09_op_run_info_and_state(self):
        info = self._call_rpc("runInfo")
        self.assertIn("cities", info)
        self.assertIn("cats", info)
        self.assertIn("running", info)
        self.assertGreaterEqual(len(info["cities"]), 10)
        self.assertGreaterEqual(len(info["cats"]), 5)

        state = self._call_rpc("runState")
        self.assertIn("running", state)
        self.assertIn("pct", state)
        self.assertIn("msg", state)


class TestDatabaseAndCRM(unittest.IsolatedAsyncioTestCase):
    """Тестирование SQLite базы данных и CRM функций."""

    async def test_01_lead_crud_and_stages(self):
        user_id = 99999
        lead_dict = {
            "name": "Тестовое Кафе 'Антигравити'",
            "city": "Москва",
            "category": "Кофейня",
            "address": "ул. Тестовая, 1",
            "phone": "+7 (999) 111-22-33",
            "website": "",
            "rating": 4.9,
            "user_ratings_total": 88,
            "status_lead": "hot",
            "stage": "new",
            "notes": "Первоначальная заметка"
        }

        # 1. Create
        saved = await db.save_b2b_lead(user_id, lead_dict)
        self.assertTrue(saved)

        # 2. Read
        leads = await db.get_b2b_leads(user_id)
        self.assertEqual(len(leads), 1)
        created = leads[0]
        self.assertEqual(created["name"], lead_dict["name"])
        self.assertEqual(created["city"], lead_dict["city"])
        self.assertEqual(created["category"], lead_dict["category"])
        self.assertEqual(created["stage"], "new")

        # 3. Update stage
        updated = await db.update_b2b_lead_stage(
            user_id, created["id"], stage="contacted", notes="Обновленная заметка"
        )
        self.assertTrue(updated)
        leads_updated = await db.get_b2b_leads(user_id)
        self.assertEqual(leads_updated[0]["stage"], "contacted")
        self.assertEqual(leads_updated[0]["notes"], "Обновленная заметка")

        # 4. KPI stats
        kpi = await db.get_kpi_stats(user_id)
        self.assertEqual(kpi["total"], 1)
        self.assertEqual(kpi["contacted"], 1)

        # 5. Delete
        deleted = await db.delete_b2b_lead(user_id, created["id"])
        self.assertTrue(deleted)
        leads_after = await db.get_b2b_leads(user_id)
        self.assertEqual(len(leads_after), 0)

    async def test_02_user_profile(self):
        user_id = 88888
        await db.update_user_profile(
            user_id,
            name="Алексей Веб-разработчик",
            google_api_key="AIzaSyTest123",
            city="Москва",
            niche="Рестораны и услуги"
        )

        profile = await db.get_user_profile(user_id)
        self.assertEqual(profile.get("freelancer_name"), "Алексей Веб-разработчик")
        self.assertEqual(profile.get("google_api_key"), "AIzaSyTest123")
        self.assertEqual(profile.get("city"), "Москва")
        self.assertEqual(profile.get("niche"), "Рестораны и услуги")


class TestLeadClassifiersAndAI(unittest.TestCase):
    """Тестирование эвристик классификации сайтов и ИИ-генератора."""

    def test_01_classify_website(self):
        # HOT: No website
        status, label = classify_website("")
        self.assertEqual(status, "hot")

        # HOT: Social media instead of website
        status, label = classify_website("https://instagram.com/skuratovcoffee")
        self.assertEqual(status, "hot")

        # HOT: VK group
        status, label = classify_website("https://vk.com/my_restaurant")
        self.assertEqual(status, "hot")

        # WARM: Booking/template service
        status, label = classify_website("https://n123456.yclients.com")
        self.assertEqual(status, "warm")

        # WARM: QR menu
        status, label = classify_website("https://smartmenu.me/resto123")
        self.assertEqual(status, "warm")

        # COLD: Independent website
        status, label = classify_website("https://coffeeshop-custom-site.ru")
        self.assertEqual(status, "cold")

    def test_02_clean_phone_number(self):
        fmt, digits, wa = clean_phone_number("8 (926) 123-45-67", "Москва")
        self.assertEqual(digits, "79261234567")
        self.assertEqual(fmt, "+7 (926) 123-45-67")
        self.assertEqual(wa, "https://wa.me/79261234567")

    def test_03_pitch_generator(self):
        pitch_hook = generate_pitch("Кофейня Ромашка", "food", "hot", city="Москва", style="hook")
        self.assertIn("Кофейня Ромашка", pitch_hook)
        self.assertIn("Google", pitch_hook)
        self.assertGreater(len(pitch_hook), 50)

        pitch_expert = generate_pitch("Автосервис Топ", "auto", "warm", city="Казань", style="expert")
        self.assertIn("Автосервис Топ", pitch_expert)
        self.assertGreater(len(pitch_expert), 50)

    def test_04_roi_calculator(self):
        roi = calculate_business_roi("food", user_ratings_total=60)
        self.assertIn("lost_revenue", roi)
        self.assertIn("lost_clients", roi)
        self.assertIn("monthly_views", roi)
        self.assertIn("pitch_argument", roi)
        self.assertGreater(roi["lost_revenue"], 0)


class TestTelegramBot(unittest.TestCase):
    """Тестирование маршрутов, клавиатур и логики Telegram-бота."""

    def test_01_router_handlers_registered(self):
        import bot
        self.assertTrue(hasattr(bot, "router"))
        handlers_count = len(bot.router.message.handlers) + len(bot.router.callback_query.handlers)
        self.assertGreaterEqual(handlers_count, 15)

    def test_02_keyboards_structure(self):
        import bot
        # Persistent reply keyboard
        reply_kb = bot.get_persistent_reply_keyboard(is_admin=False)
        self.assertIsNotNone(reply_kb)
        self.assertTrue(len(reply_kb.keyboard) >= 2)

        # Main inline keyboard
        main_kb = bot.get_main_keyboard(is_admin=False)
        self.assertIsNotNone(main_kb)
        self.assertTrue(len(main_kb.inline_keyboard) >= 2)

        # Download / WebApp keyboard
        dl_kb = bot.get_download_keyboard()
        self.assertIsNotNone(dl_kb)
        self.assertTrue(len(dl_kb.inline_keyboard) >= 1)


def run_all_tests():
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    suite.addTests(loader.loadTestsFromTestCase(TestWebServerAndAssets))
    suite.addTests(loader.loadTestsFromTestCase(TestMiniAppRPC))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseAndCRM))
    suite.addTests(loader.loadTestsFromTestCase(TestLeadClassifiersAndAI))
    suite.addTests(loader.loadTestsFromTestCase(TestTelegramBot))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
