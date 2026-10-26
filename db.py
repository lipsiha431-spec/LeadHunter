"""
db.py — Модуль асинхронной работы с базой данных SQLite через aiosqlite.
Поддерживает постепенное добавление ключевых и минус-слов, удаление конкретных слов,
загрузку файлами, приветственный БЕСПЛАТНЫЙ ТРИАЛ PRO на 1 день для новых клиентов,
счётчик пойманных лидов.
"""

import os
from pathlib import Path
from typing import Optional, Any
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import aiosqlite
import config

ROOT_DIR = Path(__file__).parent.resolve()
DB_NAME = str(ROOT_DIR / config.DB_NAME) if not os.path.isabs(config.DB_NAME) else config.DB_NAME

DEFAULT_STOP_WORDS = "курс, обучение, бесплатно, помогу, ищу работу"


def is_admin(user_id: int | str | None) -> bool:
    """Проверяет, является ли пользователь главным администратором."""
    if not user_id:
        return False
    try:
        return int(user_id) == int(config.ADMIN_ID)
    except (ValueError, TypeError):
        return False


def _parse_list(raw: Optional[str]) -> list[str]:
    """Разбивает строку с запятыми на список очищенных слов."""
    if not raw:
        return []
    return [w.strip() for w in raw.split(",") if w.strip()]


def _merge_unique(existing: list[str], new_items: list[str]) -> str:
    """Объединяет старые и новые слова без дубликатов с сохранением регистра."""
    seen = set()
    result = []
    for item in existing + new_items:
        clean = item.strip()
        if not clean:
            continue
        clean_lower = clean.lower()
        if clean_lower not in seen:
            seen.add(clean_lower)
            result.append(clean)
    return ", ".join(result)


@asynccontextmanager
async def get_connection():
    """Асинхронный контекстный менеджер для соединения с базой данных SQLite."""
    async with aiosqlite.connect(DB_NAME) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode = WAL;")
        await conn.execute("PRAGMA busy_timeout = 5000;")
        yield conn


async def init_db() -> None:
    """Инициализирует таблицу пользователей и применяет миграции."""
    async with get_connection() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                keywords TEXT,
                stop_words TEXT,
                is_pro INTEGER DEFAULT 0,
                pro_until TEXT DEFAULT NULL,
                notifications_enabled INTEGER DEFAULT 1,
                leads_received INTEGER DEFAULT 0
            )
            """
        )
        await conn.commit()

        # Безопасная миграция колонок
        for col, col_type, default_val in [
            ("pro_until", "TEXT", "NULL"),
            ("notifications_enabled", "INTEGER", 1),
            ("leads_received", "INTEGER", 0),
            ("active_categories", "TEXT", "''"),
            ("trial_used", "INTEGER", 0),
        ]:
            try:
                await conn.execute(
                    f"ALTER TABLE users ADD COLUMN {col} {col_type} DEFAULT {default_val}"
                )
                await conn.commit()
            except Exception:
                pass

        # Таблица системных настроек и реквизитов
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )

        # Таблица сохраненных B2B лидов для Telegram Mini App (CRM)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS b2b_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                place_id TEXT,
                name TEXT,
                city TEXT DEFAULT 'Москва',
                category TEXT DEFAULT '',
                address TEXT,
                phone TEXT,
                website TEXT,
                social_links TEXT DEFAULT '',
                status_lead TEXT DEFAULT 'hot',
                stage TEXT DEFAULT 'new',
                notes TEXT DEFAULT '',
                pitch TEXT DEFAULT '',
                draft TEXT DEFAULT '',
                rating REAL DEFAULT 0,
                user_ratings_total INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(user_id, place_id)
            )
            """
        )

        # Безопасная миграция колонок для b2b_leads
        for col, col_type, default_val in [
            ("city", "TEXT", "'Москва'"),
            ("category", "TEXT", "''"),
            ("draft", "TEXT", "''"),
        ]:
            try:
                await conn.execute(
                    f"ALTER TABLE b2b_leads ADD COLUMN {col} {col_type} DEFAULT {default_val}"
                )
                await conn.commit()
            except Exception:
                pass

        # Таблица профиля фрилансера в Mini App
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                freelancer_name TEXT DEFAULT '',
                google_api_key TEXT DEFAULT '',
                city TEXT DEFAULT '',
                niche TEXT DEFAULT ''
            )
            """
        )
        await conn.commit()


async def add_user(user_id: int) -> bool:
    """
    Добавляет нового пользователя в БД.
    Новым клиентам автоматически выдается БЕСПЛАТНЫЙ ТРИАЛ PRO на 3 дня (72 часа).
    Фиксируется trial_used = 1 для предотвращения повторного использования.
    Возвращает True, если пользователь зарегистрирован впервые.
    """
    # 3 дня (72 часа) бесплатного пробного периода
    trial_until = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")

    async with get_connection() as conn:
        cursor = await conn.execute(
            """
            INSERT OR IGNORE INTO users (user_id, keywords, stop_words, is_pro, pro_until, notifications_enabled, leads_received, active_categories, trial_used)
            VALUES (?, ?, ?, 1, ?, 1, 0, '', 1)
            """,
            (user_id, "", DEFAULT_STOP_WORDS, trial_until),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def get_user(user_id: int) -> Optional[dict[str, Any]]:
    """Получает полную информацию о пользователе с автоматической проверкой срока PRO."""
    async with get_connection() as conn:
        async with conn.execute(
            """
            SELECT user_id, keywords, stop_words, is_pro, pro_until,
                   COALESCE(notifications_enabled, 1) as notifications_enabled,
                   COALESCE(leads_received, 0) as leads_received,
                   COALESCE(active_categories, '') as active_categories,
                   COALESCE(trial_used, 0) as trial_used
            FROM users WHERE user_id = ?
            """,
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            user_data = dict(row)

            # Главный администратор ВСЕГДА имеет вечный PRO статус
            if is_admin(user_id):
                user_data["is_pro"] = 1
                user_data["pro_until"] = "2099-12-31 23:59:59"
                return user_data

            # Проверка истечения срока действия PRO (включая пробный период)
            if user_data.get("is_pro") == 1 and user_data.get("pro_until"):
                try:
                    expiry = datetime.fromisoformat(user_data["pro_until"])
                    if datetime.now() > expiry:
                        # Срок истек — переводим на Free
                        await conn.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (user_id,))
                        await conn.commit()
                        user_data["is_pro"] = 0
                except Exception:
                    pass

            return user_data


# --- Управление ключевыми словами ---

async def add_keywords(user_id: int, new_words: list[str]) -> tuple[int, list[str]]:
    user = await get_user(user_id)
    if not user:
        await add_user(user_id)
        user = await get_user(user_id)

    current_words = _parse_list(user.get("keywords"))
    current_lower = {w.lower() for w in current_words}

    added_count = sum(1 for w in new_words if w.strip() and w.strip().lower() not in current_lower)
    merged_str = _merge_unique(current_words, new_words)

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET keywords = ? WHERE user_id = ?",
            (merged_str, user_id),
        )
        await conn.commit()

    return added_count, _parse_list(merged_str)


async def remove_keyword(user_id: int, word_to_remove: str) -> list[str]:
    user = await get_user(user_id)
    if not user:
        return []

    target_lower = word_to_remove.strip().lower()
    current_words = _parse_list(user.get("keywords"))
    updated_words = [w for w in current_words if w.lower() != target_lower]
    updated_str = ", ".join(updated_words)

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET keywords = ? WHERE user_id = ?",
            (updated_str, user_id),
        )
        await conn.commit()

    return updated_words


async def clear_keywords(user_id: int) -> None:
    async with get_connection() as conn:
        await conn.execute("UPDATE users SET keywords = '' WHERE user_id = ?", (user_id,))
        await conn.commit()


# --- Управление минус-словами ---

async def add_stop_words(user_id: int, new_words: list[str]) -> tuple[int, list[str]]:
    user = await get_user(user_id)
    if not user:
        await add_user(user_id)
        user = await get_user(user_id)

    current_words = _parse_list(user.get("stop_words"))
    current_lower = {w.lower() for w in current_words}

    added_count = sum(1 for w in new_words if w.strip() and w.strip().lower() not in current_lower)
    merged_str = _merge_unique(current_words, new_words)

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET stop_words = ? WHERE user_id = ?",
            (merged_str, user_id),
        )
        await conn.commit()

    return added_count, _parse_list(merged_str)


async def remove_stop_word(user_id: int, word_to_remove: str) -> list[str]:
    user = await get_user(user_id)
    if not user:
        return []

    target_lower = word_to_remove.strip().lower()
    current_words = _parse_list(user.get("stop_words"))
    updated_words = [w for w in current_words if w.lower() != target_lower]
    updated_str = ", ".join(updated_words)

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET stop_words = ? WHERE user_id = ?",
            (updated_str, user_id),
        )
        await conn.commit()

    return updated_words


async def clear_stop_words(user_id: int) -> None:
    async with get_connection() as conn:
        await conn.execute("UPDATE users SET stop_words = '' WHERE user_id = ?", (user_id,))
        await conn.commit()


# --- Тарифы PRO и Сроки действия ---

async def give_pro_days(user_id: int, days: int) -> str:
    """Начисляет пользователю PRO статус на указанное количество дней (или Lifetime)."""
    user = await get_user(user_id)
    if not user:
        await add_user(user_id)
        user = await get_user(user_id)

    if days >= 999:
        pro_until_str = "2099-12-31 23:59:59"
        readable_until = "Навсегда (👑 Lifetime PRO)"
    else:
        base_time = datetime.now()
        if user.get("is_pro") == 1 and user.get("pro_until"):
            try:
                current_expiry = datetime.fromisoformat(user["pro_until"])
                if current_expiry > base_time:
                    base_time = current_expiry
            except Exception:
                pass

        new_expiry = base_time + timedelta(days=days)
        pro_until_str = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
        readable_until = f"до {new_expiry.strftime('%d.%m.%Y %H:%M')} (💎 PRO)"

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET is_pro = 1, pro_until = ? WHERE user_id = ?",
            (pro_until_str, user_id),
        )
        await conn.commit()

    return readable_until


async def set_pro_status(user_id: int, is_pro: int) -> bool:
    """Устанавливает статус подписки (0 - Free, 1 - Lifetime PRO)."""
    async with get_connection() as conn:
        pro_until = "2099-12-31 23:59:59" if is_pro == 1 else None
        cursor = await conn.execute(
            "UPDATE users SET is_pro = ?, pro_until = ? WHERE user_id = ?",
            (is_pro, pro_until, user_id),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def get_pro_status_display(user: dict) -> str:
    """Форматированная строка статуса подписки для профиля."""
    uid = user.get("user_id")
    if is_admin(uid):
        return "👑 <b>Создатель / Главный Администратор</b> (Lifetime PRO)"

    if user.get("is_pro") != 1:
        return "🆓 <b>Бесплатный (Free)</b> — <i>контакты скрыты</i>"

    pro_until = user.get("pro_until")
    if not pro_until or "2099" in str(pro_until):
        return "👑 <b>PRO Безлимит</b> (Навсегда)"

    try:
        dt = datetime.fromisoformat(str(pro_until))
        return f"💎 <b>PRO активен</b> (до {dt.strftime('%d.%m.%Y %H:%M')})"
    except Exception:
        return "💎 <b>PRO активен</b>"


async def increment_leads_count(user_id: int) -> None:
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET leads_received = COALESCE(leads_received, 0) + 1 WHERE user_id = ?",
            (user_id,),
        )
        await conn.commit()


async def get_all_users_with_keywords() -> list[dict[str, Any]]:
    async with get_connection() as conn:
        async with conn.execute(
            """
            SELECT user_id, keywords, stop_words, is_pro, pro_until, leads_received,
                   COALESCE(active_categories, '') as active_categories
            FROM users 
            WHERE COALESCE(notifications_enabled, 1) = 1
            """
        ) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                item = dict(row)
                if is_admin(item.get("user_id")):
                    item["is_pro"] = 1
                    item["pro_until"] = "2099-12-31 23:59:59"
                elif item.get("is_pro") == 1 and item.get("pro_until"):
                    try:
                        expiry = datetime.fromisoformat(item["pro_until"])
                        if datetime.now() > expiry:
                            item["is_pro"] = 0
                            await conn.execute("UPDATE users SET is_pro = 0 WHERE user_id = ?", (item["user_id"],))
                            await conn.commit()
                    except Exception:
                        pass
                results.append(item)

            # Гарантируем, что администратор ВСЕГДА получает заказы
            admin_ids = {1795524760}
            if config.ADMIN_ID:
                admin_ids.add(config.ADMIN_ID)
            existing_ids = {u["user_id"] for u in results}
            for aid in admin_ids:
                if aid not in existing_ids:
                    results.append({
                        "user_id": aid,
                        "keywords": "",
                        "stop_words": "",
                        "is_pro": 1,
                        "pro_until": "2099-12-31 23:59:59",
                        "leads_received": 0,
                        "active_categories": "",
                    })

            return results


# ==========================================
# ПАНЕЛЬ И ФУНКЦИИ АДМИНИСТРАТОРА
# ==========================================

async def revoke_pro(user_id: int) -> bool:
    """Снимает PRO статус у пользователя."""
    async with get_connection() as conn:
        cursor = await conn.execute(
            "UPDATE users SET is_pro = 0, pro_until = NULL WHERE user_id = ?",
            (user_id,),
        )
        await conn.commit()
        return cursor.rowcount > 0


async def get_admin_stats() -> dict[str, Any]:
    """Возвращает общую статистику для панели администратора."""
    async with get_connection() as conn:
        async with conn.execute("SELECT COUNT(*) as total FROM users") as cur:
            row = await cur.fetchone()
            total_users = row["total"] if row else 0

        async with conn.execute("SELECT COUNT(*) as pro_count FROM users WHERE is_pro = 1") as cur:
            row = await cur.fetchone()
            pro_users = row["pro_count"] if row else 0

        async with conn.execute("SELECT SUM(leads_received) as sum_leads FROM users") as cur:
            row = await cur.fetchone()
            total_leads = (row["sum_leads"] or 0) if row else 0

        return {
            "total_users": total_users,
            "pro_users": pro_users,
            "free_users": max(0, total_users - pro_users),
            "total_leads": total_leads,
        }


async def get_all_user_ids() -> list[int]:
    """Возвращает список ID всех пользователей бота для рассылки."""
    async with get_connection() as conn:
        async with conn.execute("SELECT user_id FROM users") as cur:
            rows = await cur.fetchall()
            return [row["user_id"] for row in rows]


async def get_all_users_details() -> list[dict[str, Any]]:
    """Возвращает подробный список всех пользователей для админ-панели."""
    async with get_connection() as conn:
        async with conn.execute(
            """
            SELECT user_id, is_pro, pro_until, leads_received, active_categories, keywords
            FROM users
            ORDER BY is_pro DESC, leads_received DESC
            """
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ==========================================
# УПРАВЛЕНИЕ ГОТОВЫМИ КАТЕГОРИЯМИ / ФИЛЬТРАМИ
# ==========================================

async def get_user_categories(user_id: int) -> set[str]:
    """Возвращает множество активных ID категорий пользователя."""
    user = await get_user(user_id)
    if not user:
        return set()
    raw = user.get("active_categories") or ""
    return {c.strip() for c in raw.split(",") if c.strip()}


async def set_user_categories(user_id: int, categories_set: set[str] | list[str]) -> None:
    """Устанавливает список активных категорий пользователя."""
    raw = ", ".join(sorted(set(categories_set)))
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE users SET active_categories = ? WHERE user_id = ?",
            (raw, user_id),
        )
        await conn.commit()


async def toggle_user_category(user_id: int, category_id: str) -> bool:
    """
    Переключает категорию (вкл/выкл).
    Возвращает True если категория стала активной, False если отключена.
    """
    current = await get_user_categories(user_id)
    if category_id in current:
        current.remove(category_id)
        is_active = False
    else:
        current.add(category_id)
        is_active = True
    await set_user_categories(user_id, current)
    return is_active


async def enable_cluster(user_id: int, cluster_id: str) -> int:
    """Включает все подкатегории кластера. Возвращает число добавленных."""
    import categories
    cluster = categories.get_cluster(cluster_id)
    if not cluster:
        return 0
    current = await get_user_categories(user_id)
    cluster_cat_ids = {c["id"] for c in cluster["categories"]}
    new_categories = current.union(cluster_cat_ids)
    added = len(new_categories) - len(current)
    await set_user_categories(user_id, new_categories)
    return added


async def disable_cluster(user_id: int, cluster_id: str) -> int:
    """Отключает все подкатегории кластера."""
    import categories
    cluster = categories.get_cluster(cluster_id)
    if not cluster:
        return 0
    current = await get_user_categories(user_id)
    cluster_cat_ids = {c["id"] for c in cluster["categories"]}
    new_categories = current - cluster_cat_ids
    removed = len(current) - len(new_categories)
    await set_user_categories(user_id, new_categories)
    return removed


async def clear_all_categories(user_id: int) -> None:
    """Сбрасывает все активные категории пользователя."""
    await set_user_categories(user_id, set())


# ==========================================
# СИСТЕМНЫЕ НАСТРОЙКИ (ТАРИФЫ, РЕКВИЗИТЫ)
# ==========================================

async def get_setting(key: str, default: Any = None) -> Any:
    """Получает значение системной настройки из БД."""
    async with get_connection() as conn:
        async with conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            if row and row["value"] is not None:
                return row["value"]
    return default


async def set_setting(key: str, value: Any) -> None:
    """Сохраняет значение системной настройки в БД."""
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )
        await conn.commit()


async def get_all_settings() -> dict[str, str]:
    """Возвращает словарь всех системных настроек."""
    async with get_connection() as conn:
        async with conn.execute("SELECT key, value FROM app_settings") as cur:
            rows = await cur.fetchall()
            return {r["key"]: r["value"] for r in rows}


# --- B2B Лиды и CRM для Telegram Mini App ---

async def save_b2b_lead(user_id: int, lead: dict[str, Any]) -> bool:
    """Сохраняет или обновляет B2B лида в CRM пользователя."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    place_id = str(lead.get("place_id") or lead.get("id") or lead.get("name"))
    name = str(lead.get("name", "Без названия"))
    city = str(lead.get("city", "Москва"))
    category = str(lead.get("category", ""))
    address = str(lead.get("address", ""))
    phone = str(lead.get("phone", ""))
    website = str(lead.get("website", ""))
    social_links = str(lead.get("social_links", ""))
    status_lead = str(lead.get("status_lead", "hot"))
    stage = str(lead.get("stage", "new"))
    notes = str(lead.get("notes", ""))
    pitch = str(lead.get("pitch", ""))
    draft = str(lead.get("draft", ""))
    rating = float(lead.get("rating", 0.0) or 0.0)
    user_ratings_total = int(lead.get("user_ratings_total", 0) or 0)

    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO b2b_leads (
                user_id, place_id, name, address, phone, website,
                social_links, status_lead, stage, notes, pitch,
                rating, user_ratings_total, created_at, updated_at,
                city, category, draft
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, place_id) DO UPDATE SET
                name = excluded.name,
                city = excluded.city,
                category = excluded.category,
                address = excluded.address,
                phone = excluded.phone,
                website = excluded.website,
                social_links = excluded.social_links,
                status_lead = excluded.status_lead,
                rating = excluded.rating,
                user_ratings_total = excluded.user_ratings_total,
                pitch = excluded.pitch,
                draft = excluded.draft,
                updated_at = excluded.updated_at
            """,
            (
                user_id, place_id, name, address, phone, website,
                social_links, status_lead, stage, notes, pitch,
                rating, user_ratings_total, now_str, now_str,
                city, category, draft
            )
        )
        await conn.commit()
        return True


async def save_b2b_leads_batch(user_id: int, leads: list[dict[str, Any]]) -> int:
    """Массово сохраняет список B2B лидов за одну быструю транзакцию."""
    if not leads:
        return 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records = []
    for lead in leads:
        place_id = str(lead.get("place_id") or lead.get("id") or lead.get("name"))
        name = str(lead.get("name", "Без названия"))
        city = str(lead.get("city", "Москва"))
        category = str(lead.get("category", ""))
        address = str(lead.get("address", ""))
        phone = str(lead.get("phone", ""))
        website = str(lead.get("website", ""))
        social_links = str(lead.get("social_links", ""))
        status_lead = str(lead.get("status_lead", "hot"))
        stage = str(lead.get("stage", "new"))
        notes = str(lead.get("notes", ""))
        pitch = str(lead.get("pitch", ""))
        draft = str(lead.get("draft", ""))
        rating = float(lead.get("rating", 0.0) or 0.0)
        user_ratings_total = int(lead.get("user_ratings_total", 0) or 0)
        records.append((
            user_id, place_id, name, address, phone, website,
            social_links, status_lead, stage, notes, pitch,
            rating, user_ratings_total, now_str, now_str,
            city, category, draft
        ))

    async with get_connection() as conn:
        await conn.executemany(
            """
            INSERT INTO b2b_leads (
                user_id, place_id, name, address, phone, website,
                social_links, status_lead, stage, notes, pitch,
                rating, user_ratings_total, created_at, updated_at,
                city, category, draft
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, place_id) DO UPDATE SET
                name = excluded.name,
                city = excluded.city,
                category = excluded.category,
                address = excluded.address,
                phone = excluded.phone,
                website = excluded.website,
                social_links = excluded.social_links,
                status_lead = excluded.status_lead,
                rating = excluded.rating,
                user_ratings_total = excluded.user_ratings_total,
                pitch = excluded.pitch,
                draft = excluded.draft,
                updated_at = excluded.updated_at
            """,
            records
        )
        await conn.commit()
        return len(records)


async def get_b2b_leads(user_id: int, stage: Optional[str] = None) -> list[dict[str, Any]]:
    """Получает сохраненных B2B лидов пользователя из CRM."""
    async with get_connection() as conn:
        if stage and stage != "all":
            query = "SELECT * FROM b2b_leads WHERE user_id = ? AND stage = ? ORDER BY id DESC"
            params = (user_id, stage)
        else:
            query = "SELECT * FROM b2b_leads WHERE user_id = ? ORDER BY id DESC"
            params = (user_id,)

        async with conn.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_b2b_lead_stage(user_id: int, lead_id: int, stage: str, notes: Optional[str] = None) -> bool:
    """Обновляет статус воронки или заметку по лиду."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection() as conn:
        if notes is not None:
            await conn.execute(
                "UPDATE b2b_leads SET stage = ?, notes = ?, updated_at = ? WHERE user_id = ? AND id = ?",
                (stage, notes, now_str, user_id, lead_id)
            )
        else:
            await conn.execute(
                "UPDATE b2b_leads SET stage = ?, updated_at = ? WHERE user_id = ? AND id = ?",
                (stage, now_str, user_id, lead_id)
            )
        await conn.commit()
        return True


async def update_b2b_lead_draft(user_id: int, lead_id: int, draft: str) -> bool:
    """Обновляет черновик сообщения (draft и pitch) по лиду в базе данных."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE b2b_leads SET draft = ?, pitch = ?, updated_at = ? WHERE (user_id = ? OR user_id = 0) AND id = ?",
            (draft, draft, now_str, user_id, lead_id)
        )
        await conn.commit()
        return True


async def update_b2b_lead_phone(user_id: int, lead_id: int, phone: str) -> bool:
    """Обновляет телефон лида в базе данных."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE b2b_leads SET phone = ?, updated_at = ? WHERE (user_id = ? OR user_id = 0) AND id = ?",
            (phone, now_str, user_id, lead_id)
        )
        await conn.commit()
        return True


async def delete_b2b_lead(user_id: int, lead_id: int) -> bool:
    """Удаляет лида из CRM."""
    async with get_connection() as conn:
        await conn.execute("DELETE FROM b2b_leads WHERE user_id = ? AND id = ?", (user_id, lead_id))
        await conn.commit()
        return True


async def get_kpi_stats(user_id: int) -> dict[str, Any]:
    """Подсчитывает сводную KPI статистику по B2B лидам пользователя."""
    leads = await get_b2b_leads(user_id)
    total = len(leads)
    new_count = sum(1 for l in leads if l.get("stage") == "new")
    contacted = sum(1 for l in leads if l.get("stage") in ["contacted", "negotiation", "won"])
    won = sum(1 for l in leads if l.get("stage") == "won")
    daily_goal = 20
    goal_progress = min(100, int((contacted / daily_goal) * 100)) if daily_goal else 0
    return {
        "ok": True,
        "total": total,
        "new": new_count,
        "contacted": contacted,
        "won": won,
        "daily_goal": daily_goal,
        "goal_progress": goal_progress,
    }


async def get_user_profile(user_id: int) -> dict[str, Any]:
    """Получает настройки профиля фрилансера."""
    async with get_connection() as conn:
        async with conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
    return {"user_id": user_id, "freelancer_name": "", "google_api_key": "", "city": "", "niche": ""}


async def update_user_profile(
    user_id: int,
    name: str = "",
    google_api_key: str = "",
    city: str = "",
    niche: str = "",
    freelancer_name: str = ""
) -> None:
    """Обновляет профиль фрилансера в Mini App."""
    final_name = (freelancer_name or name or "").strip()
    async with get_connection() as conn:
        await conn.execute(
            """
            INSERT INTO user_profiles (user_id, freelancer_name, google_api_key, city, niche)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                freelancer_name = excluded.freelancer_name,
                google_api_key = excluded.google_api_key,
                city = excluded.city,
                niche = excluded.niche
            """,
            (user_id, final_name, google_api_key, city, niche)
        )
        await conn.commit()




async def has_used_trial(user_id: Optional[int]) -> bool:
    """Проверяет, использовал ли пользователь бесплатный пробный период."""
    if not user_id:
        return False
    if is_admin(user_id):
        return False
    user = await get_user(user_id)
    if not user:
        return False
    return bool(user.get("trial_used", 0))


async def activate_free_trial(user_id: int, days: int = 3) -> tuple[bool, str]:
    """
    Активирует бесплатный пробный период PRO на 3 дня.
    Защита от абуза: выдается строго 1 раз на аккаунт.
    Returns: (success, message_or_expiry)
    """
    if is_admin(user_id):
        readable = await give_pro_days(user_id, days=days)
        return True, readable

    user = await get_user(user_id)
    if not user:
        await add_user(user_id)
        user = await get_user(user_id)

    # Защита от абуза №1: проверка флага trial_used
    if user.get("trial_used"):
        return False, "already_used"

    # Защита от абуза №2: проверка уже активного PRO
    if user.get("is_pro") == 1:
        return False, "already_active"

    # Начисляем ровно 3 дня и навсегда фиксируем trial_used = 1
    new_expiry = datetime.now() + timedelta(days=days)
    pro_until_str = new_expiry.strftime("%Y-%m-%d %H:%M:%S")
    readable_until = f"до {new_expiry.strftime('%d.%m.%Y %H:%M')} (💎 PRO)"

    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE users 
            SET is_pro = 1, pro_until = ?, trial_used = 1 
            WHERE user_id = ?
            """,
            (pro_until_str, user_id),
        )
        await conn.commit()

    return True, readable_until
