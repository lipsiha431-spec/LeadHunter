"""
miniapp/server.py — Асинхронный веб-сервер Telegram Mini App (на базе aiohttp).
Предоставляет REST API и отдает интерфейс B2B лидогенератора.
"""

import os
import json
import hmac
import hashlib
import urllib.parse
from pathlib import Path
from typing import Optional
from aiohttp import web

import config
import db
from miniapp.spheres_data import SPHERES
from miniapp.cities_data import search_cities, get_popular_cities
from miniapp.places_search import search_leads, verify_google_key
from miniapp.pitch_generator import generate_pitch, calculate_business_roi, get_demo_catalog
from miniapp.rpc_handler import handle_rpc_call

STATIC_DIR = Path(__file__).parent / "static"
_INDEX_CACHE: Optional[bytes] = None


def get_cached_index() -> bytes:
    """Кэширует index.html в оперативной памяти для мгновенной отдачи (<0.01с)."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            _INDEX_CACHE = index_file.read_bytes()
        else:
            _INDEX_CACHE = b"index.html not found"
    return _INDEX_CACHE


def verify_telegram_init_data(init_data: str, bot_token: str) -> Optional[dict]:
    """Проверяет HMAC-SHA256 подпись initData от Telegram WebApp."""
    if not init_data or not bot_token:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))
        hash_val = parsed.pop("hash", None)
        if not hash_val:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(calc_hash, hash_val):
            user_data = json.loads(parsed.get("user", "{}"))
            return user_data
    except Exception:
        pass
    return None


# --- CORS Middleware ---
@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        response = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
        except Exception as e:
            response = web.json_response({"error": str(e)}, status=500)

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org telegram:;"
    response.headers["X-Frame-Options"] = "ALLOWALL"

    try:
        response.enable_compression()
    except Exception:
        pass

    return response


# --- Handlers ---

async def handle_ping(request: web.Request) -> web.Response:
    """Ультралегкий эндпоинт для мгновенной проверки работоспособности туннеля."""
    return web.Response(text="pong", content_type="text/plain")


async def handle_index(request: web.Request) -> web.Response:
    content = get_cached_index()
    return web.Response(
        body=content,
        content_type="text/html",
        charset="utf-8",
        headers={
            "Cache-Control": "no-cache, must-revalidate",
        }
    )



async def handle_bg_js(request: web.Request) -> web.Response:
    bg_file = STATIC_DIR / "bg.js"
    if not bg_file.exists():
        return web.Response(text="// bg not found", status=404)
    return web.FileResponse(bg_file)


async def handle_logo_png(request: web.Request) -> web.Response:
    logo_file = STATIC_DIR / "logo.png"
    if not logo_file.exists():
        return web.Response(text="not found", status=404)
    return web.FileResponse(logo_file)


async def handle_rpc_api(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = {}

    op = str(data.get("op", "")).strip()
    args = data.get("args") or {}
    init_data = str(data.get("initData", "")).strip()

    user_id = 0
    if init_data:
        u = verify_telegram_init_data(init_data, config.BOT_TOKEN)
        if u and "id" in u:
            user_id = int(u["id"])

    # Если user_id не определен или запуск идет из браузера / предпросмотра
    if not user_id and getattr(config, "ADMIN_ID", 0):
        user_id = int(config.ADMIN_ID)

    res = await handle_rpc_call(op, args, user_id)
    return web.json_response(res)


async def handle_spheres(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "spheres": SPHERES})


async def handle_cities(request: web.Request) -> web.Response:
    q = request.query.get("q", "").strip()
    if q:
        cities = search_cities(q, limit=15)
    else:
        cities = get_popular_cities()
    return web.json_response({"ok": True, "cities": cities})


async def handle_verify_key(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = {}
    key = data.get("api_key", "").strip()
    res = await verify_google_key(key)
    return web.json_response(res)


async def handle_kpi(request: web.Request) -> web.Response:
    user_id = int(request.query.get("user_id") or 0)
    stats = await db.get_kpi_stats(user_id) if user_id else {
        "ok": True,
        "total": 0,
        "new": 0,
        "contacted": 0,
        "won": 0,
        "daily_goal": 20,
        "goal_progress": 0,
    }
    return web.json_response(stats)


async def handle_search(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = {}

    query = data.get("query", "").strip()
    city = data.get("city", "").strip() or "Москва"
    sphere_id = data.get("sphere_id", "food")
    depth = data.get("depth", "deep")
    only_hot = bool(data.get("only_hot", False))
    user_id = int(data.get("user_id") or 0)
    custom_key = data.get("api_key", "").strip()

    # Проверяем ключ пользователя в базе, если не передан в запросе
    effective_key = custom_key
    if not effective_key and user_id:
        profile = await db.get_user_profile(user_id)
        effective_key = profile.get("google_api_key", "")
    if not effective_key:
        effective_key = getattr(config, "GOOGLE_PLACES_API_KEY", "")

    page_limit = 35 if depth == "quick" else 150 if depth == "max" else 90

    # Полноценный живой поиск сотен заведений (Google Places New или Live OSM/Web Engine)
    places = await search_leads(
        query=query,
        city=city,
        sphere_id=sphere_id,
        depth=depth,
        api_key=effective_key,
        page_size=page_limit
    )

    total_scanned = len(places)
    hot_count = sum(1 for p in places if p.get("status_lead") == "hot")

    if only_hot:
        places = [p for p in places if p.get("status_lead") == "hot"]

    return web.json_response({
        "ok": True,
        "places": places,
        "count": len(places),
        "total_scanned": total_scanned,
        "hot_count": hot_count,
        "city": city,
        "query": query,
    })


async def handle_pitch(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = {}

    name = data.get("name", "")
    sphere_id = data.get("sphere_id", "food")
    status_lead = data.get("status_lead", "hot")
    freelancer_name = data.get("freelancer_name", "")
    city = data.get("city", "")
    style = data.get("style", "hook")
    user_ratings = int(data.get("user_ratings_total") or 45)

    # Генерируем сразу 3 стиля оффера для удобного A/B тестирования
    pitches = {
        "hook": generate_pitch(name, sphere_id, status_lead, freelancer_name, city, style="hook"),
        "expert": generate_pitch(name, sphere_id, status_lead, freelancer_name, city, style="expert"),
        "short": generate_pitch(name, sphere_id, status_lead, freelancer_name, city, style="short"),
    }
    roi = calculate_business_roi(sphere_id, user_ratings)

    return web.json_response({
        "ok": True,
        "pitch": pitches.get(style, pitches["hook"]),
        "pitches": pitches,
        "roi": roi,
    })


async def handle_mockup(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = {}
    name = data.get("name", "")
    sphere_id = data.get("sphere_id", "food")
    catalog = get_demo_catalog(name, sphere_id)
    return web.json_response({"ok": True, "catalog": catalog})


async def handle_roi(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = {}
    sphere_id = data.get("sphere_id", "food")
    ratings = int(data.get("ratings") or 50)
    roi = calculate_business_roi(sphere_id, ratings)
    return web.json_response({"ok": True, "roi": roi})


async def handle_get_crm_leads(request: web.Request) -> web.Response:
    user_id = int(request.query.get("user_id") or 0)
    stage = request.query.get("stage", None)
    if stage == "all":
        stage = None
    leads = await db.get_b2b_leads(user_id=user_id, stage=stage)
    return web.json_response({"ok": True, "leads": leads, "count": len(leads)})


async def handle_save_crm_lead(request: web.Request) -> web.Response:
    data = await request.json()
    user_id = int(data.get("user_id") or 0)
    lead_data = data.get("lead", {})
    if not user_id or not lead_data:
        # Может быть отправлен напрямую объект лида
        lead_data = {k: v for k, v in data.items() if k != "user_id"}
    if not user_id or not lead_data.get("name"):
        return web.json_response({"ok": False, "error": "Invalid data"}, status=400)

    ok = await db.save_b2b_lead(user_id, lead_data)
    return web.json_response({"ok": ok})


async def handle_update_stage(request: web.Request) -> web.Response:
    data = await request.json()
    user_id = int(data.get("user_id") or 0)
    lead_id = int(data.get("lead_id") or 0)
    stage = data.get("stage", "new")
    note = data.get("note", None)
    ok = await db.update_b2b_lead_stage(user_id=user_id, lead_id=lead_id, stage=stage, notes=note)
    return web.json_response({"ok": ok})


async def handle_delete_crm_lead(request: web.Request) -> web.Response:
    data = await request.json()
    user_id = int(data.get("user_id") or 0)
    lead_id = int(data.get("lead_id") or 0)
    ok = await db.delete_b2b_lead(user_id=user_id, lead_id=lead_id)
    return web.json_response({"ok": ok})


async def handle_profile_get(request: web.Request) -> web.Response:
    user_id = int(request.query.get("user_id") or 0)
    profile = await db.get_user_profile(user_id)
    user = await db.get_user(user_id)
    is_pro = user.get("is_pro", 0) if user else 0
    pro_until = user.get("pro_until", "") if user else ""
    return web.json_response({
        "ok": True,
        "profile": profile,
        "is_pro": is_pro,
        "pro_until": pro_until,
    })


async def handle_profile_post(request: web.Request) -> web.Response:
    data = await request.json()
    user_id = int(data.get("user_id") or 0)
    name = data.get("freelancer_name", "")
    key = data.get("google_api_key", "")
    city = data.get("city", "")
    niche = data.get("niche", "")
    await db.update_user_profile(user_id, name, key, city, niche)
    return web.json_response({"ok": True})


def create_app() -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/ping", handle_ping)
    app.router.add_get("/health", handle_ping)
    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/bg.js", handle_bg_js)
    app.router.add_get("/logo.png", handle_logo_png)
    app.router.add_post("/api", handle_rpc_api)
    app.router.add_post("/api/rpc", handle_rpc_api)
    app.router.add_get("/api/spheres", handle_spheres)
    app.router.add_get("/api/cities", handle_cities)
    app.router.add_post("/api/verify_key", handle_verify_key)
    app.router.add_get("/api/kpi", handle_kpi)
    app.router.add_post("/api/search", handle_search)
    app.router.add_post("/api/pitch", handle_pitch)
    app.router.add_post("/api/mockup", handle_mockup)
    app.router.add_post("/api/roi", handle_roi)
    app.router.add_get("/api/crm/leads", handle_get_crm_leads)
    app.router.add_post("/api/crm/lead", handle_save_crm_lead)
    app.router.add_post("/api/crm/stage", handle_update_stage)
    app.router.add_delete("/api/crm/lead", handle_delete_crm_lead)
    app.router.add_get("/api/profile", handle_profile_get)
    app.router.add_post("/api/profile", handle_profile_post)

    # Static assets
    if STATIC_DIR.exists():
        app.router.add_static("/static/", path=str(STATIC_DIR), name="static")

    return app
