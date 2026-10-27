"""
parser.py — Умный модуль парсера Telegram-сообщений на базе Telethon.
Особенности:
1. Фильтр свежести: полностью игнорирует старый бэклог сообщений (защита от +35 спам-уведомлений при запуске).
2. Анти-спам и анти-резюме: отсеивает саморекламу фрилансеров ("ищу работу", "портфолио", "готов сделать").
3. Дедупликация: не присылает одинаковые посты, растиражированные по нескольким чатам.
4. Минимальная длина и качество текста: отсекает 1-2 словный мусор.
5. Защита от флуда Telegram Bot API: контролирует частоту отправки сообщений пользователям.
6. Красивый UI лид-карточек: аккуратная цитата, инлайн-кнопки для перехода к заказчику и к посту.
"""

import sys
import re
import html
import time
import hashlib
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from telethon import TelegramClient, events
from telethon.tl.types import User, Channel, Chat
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
import db
import categories
import chat_manager

logger = logging.getLogger("LeadParser")

# Кеш для дедупликации сообщений (хэш текста -> время получения)
SEEN_MESSAGES_CACHE: dict[str, float] = {}

# Защита от флуда по пользователям (user_id -> время последней отправки)
USER_LAST_NOTIFICATION: dict[int, float] = {}

# Глобальные счетчики работы парсера
PARSER_STATS = {
    "incoming_total": 0,
    "leads_matched": 0,
    "leads_delivered": 0,
    "last_message_at": None,
    "last_lead_at": None,
    "last_chat_title": "—",
}


def get_parser_stats() -> dict:
    """Возвращает живую статистику работы парсера."""
    return dict(PARSER_STATS)


# Стоп-триггеры паразитных каналов, ботов-переходников и заманух
PARASITIC_BOT_TRIGGERS: list[str] = [
    "бот с заказами",
    "забрать заказ",
    "ищешь клиентов",
    "ищешь заказы",
    "тогда тебе точно сюда",
    "переходи в бота",
    "наш бот",
    "бот поможет",
    "ссылка на бота",
    "перейти в бота",
    "заказы в боте",
    "биржа в боте",
    "бот агрегатор",
    "бот для фрилансеров",
    "бот с вакансиями",
    "хэштеги: #",
    "хештеги: #",
    "ты фрилансер и ищешь",
    "хочешь много заказов",
    "где брать заказы",
    "как находить клиентов",
    "слив курсов",
    "бесплатный вебинар",
    "переходи по ссылке",
    "жми на кнопку",
    "кнопка ниже",
    "подпишись на канал",
    "подписывайтесь на канал",
    "вступайте в наш чат",
    "наш закрытый канал",
    "закрепе канала",
    "канал в закрепе",
]

# Регулярные выражения для жесткого отсеивания саморекламы, резюме и предложений услуг
SELLER_RESUME_REGEXES: list[str] = [
    # 1. От первого лица о себе и своих услугах
    r'\bя\s+(?:занимаюсь|разрабатываю|создаю|делаю|верстаю|рисую|настраиваю|монтирую|пишу)\b',
    r'\bмы\s+(?:занимаемся|разрабатываем|создаем|делаем|верстаем|настраиваем)\b',
    r'\bя\s+(?:веб[- ]?разработчик|программист|дизайнер|верстальщик|таргетолог|маркетолог|копирайтер|монтажер|специалист|фрилансер)\b',
    r'\bзанимаюсь\s+(?:веб[- ]?разработкой|разработкой|созданием|дизайном|настройкой|монтажом|продвижением)\b',
    r'\bразрабатываю\s+(?:сайты|лендинги|ботов|приложения|сервисы)\b',
    r'\bсоздаю\s+(?:сайты|ботов|дизайн|логотипы|креативы)\b',
    r'\b(?:мо[её]\s+портфолио|портфолио\s+и\s+примеры|мои\s+кейсы|мои\s+работы|ссылка\s+на\s+портфолио)\b',
    r'\b(?:обо\s+мне|о\s+себе|мой\s+стек|мой\s+опыт|мой\s+стаж)\s*:',
    r'\b(?:стек|навыки|skills|hard\s+skills)\s*:',
    r'\b(?:опыт|стаж)\s+(?:более|больше|около)\s+\d+\s+(?:лет|года|месяц)',
    r'\b\d+\s+(?:лет|года)\s+(?:в\s+дизайне|в\s+разработке|в\s+маркетинге|в\s+сфере|опыта)\b',

    # 2. Поиск работы и предложений фрилансером
    r'\bищу\s+(?:работу|заказы|проекты|подработку|клиентов|удаленку|постоянную\s+работу)\b',
    r'\bвозьму\s+(?:заказ|проект|работу|в\s+работу|на\s+ведение)\b',
    r'\bготов\s+(?:взяться|выполнить|к\s+работе|к\s+сотрудничеству)\b',
    r'\bоткрыт\s+(?:для\s+заказов|к\s+сотрудничеству|к\s+предложениям)\b',
    r'\bпредлагаю\s+(?:свои\s+услуги|услуги)\b',
    r'\bоказываю\s+услуги\b',
    r'\bпредоставляем\s+услуги\b',

    # 3. Партнерки, проценты и рекрутинг продажников
    r'\bищу\s+(?:\d+[- ]?\d*\s+)?партн[её]р',
    r'\bищем\s+партн[её]р',
    r'\bпартн[её]р\s+по\s+продажам\b',
    r'\bпо\s+продажам\s+сайтов\b',
    r'\bпроцент\s+(?:со\s+сделки|от\s+продаж|от\s+чека)\b',
    r'\bпартн[её]рская\s+программа\b',

    # 4. Спам-тематики (крипта, арбитраж, казино)
    r'\b(?:казино|ставки на спорт|крипто сигналы|арбитраж крипты|слив схем)\b',
]


def is_seller_or_resume_post(raw_text: str) -> bool:
    """
    Определяет, является ли сообщение резюме, саморекламой фрилансера или партнеркой,
    а не реальным клиентским заказом.
    """
    t = raw_text.lower()

    for pattern in SELLER_RESUME_REGEXES:
        if re.search(pattern, t):
            return True

    # Проверка портфолио: отсекаем ссылки на личные портфолио фрилансеров,
    # но не отсекаем заказчиков, которые просят прислать портфолио в отклике
    if "портфолио" in t or "portfolio" in t:
        buyer_asking = re.search(r'(?:присылайте|скидывайте|жду|отправляйте|покажите|без|с)\s+(?:сво[её]|ваше\s+)?портфолио', t)
        if not buyer_asking:
            if re.search(r'(?:портфолио\s*:|портфолио\s+тут|портфолио\s+в\s+закрепе|примеры\s+работ|setrize|behance\.net|dribbble\.com|artstation\.com|tilda\.ws)', t):
                return True

    return False


def extract_direct_client_contact(raw_text: str, sender: any, chat: any) -> tuple[Optional[str], Optional[int], str]:
    """
    Извлекает подтвержденный контакт заказчика (реального человека, не бота и не канала).
    Возвращает (username, user_id, contact_display).
    Если контакта живого человека нет — возвращает (None, None, "В источнике / чате").
    """
    chat_username = (getattr(chat, "username", "") or "").lower()

    # 1. Если сообщение отправлено живым человеком в группе / супергруппе биржи:
    if isinstance(sender, User) and not getattr(sender, "bot", False):
        s_user = getattr(sender, "username", None)
        s_id = getattr(sender, "id", None)
        f_name = getattr(sender, "first_name", "") or ""
        if s_user:
            return s_user, s_id, f"@{s_user}"
        elif s_id:
            display = f"{f_name} (ID: {s_id})" if f_name else f"ID: {s_id}"
            return None, s_id, display

    # 2. Если в тексте объявления указан личный контакт заказчика:
    found_handles = re.findall(r"(?:@|t\.me/)([a-zA-Z0-9_]{4,32})", raw_text)
    for handle in found_handles:
        h_lower = handle.lower()
        if h_lower.endswith("bot") or h_lower == chat_username:
            continue
        if h_lower in ("joinchat", "telegram", "channel", "admin", "moderator", "support", "share", "boost", "bot"):
            continue
        return handle, None, f"@{handle}"

    # 3. Резервный контакт: если автор анонимен или контакт не в тексте,
    # перенаправляем к сообщению в чате (чтобы не терять реальные заказы)
    chat_title = getattr(chat, "title", "Чат/Канал")
    return None, None, f"В источнике: {chat_title}"


def mask_contact(username: Optional[str], first_name: Optional[str]) -> str:
    """Маскирует контакт автора для бесплатных пользователей (Free-тариф)."""
    if username:
        clean_user = username.lstrip("@")
        if len(clean_user) <= 3:
            return f"@{clean_user[0]}***"
        visible_part = clean_user[:3]
        return f"@{visible_part}***"

    if first_name:
        if len(first_name) <= 2:
            return f"{first_name[0]}***"
        return f"{first_name[:2]}***"

    return "Заказчик [ID: ***]"


def generate_message_link(chat_obj: any, event_id: int) -> Optional[str]:
    """Генерирует прямую ссылку на сообщение в Telegram."""
    if not chat_obj:
        return None

    username = getattr(chat_obj, "username", None)
    if username:
        return f"https://t.me/{username}/{event_id}"

    chat_id = getattr(chat_obj, "id", None)
    if chat_id:
        chat_id_str = str(chat_id)
        if chat_id_str.startswith("-100"):
            clean_id = chat_id_str[4:]
        elif chat_id_str.startswith("-"):
            clean_id = chat_id_str[1:]
        else:
            clean_id = chat_id_str
        return f"https://t.me/c/{clean_id}/{event_id}"

    return None


def is_duplicate_message(raw_text: str) -> bool:
    """Проверяет, было ли это же сообщение недавно отправлено (дедупликация кросс-постинга)."""
    clean_chars = [c for c in raw_text.lower() if c.isalnum()]
    if len(clean_chars) < 15:
        return True

    text_fingerprint = "".join(clean_chars[:250])
    text_hash = hashlib.md5(text_fingerprint.encode("utf-8")).hexdigest()

    now = time.time()
    # Очистка устаревших записей (> 45 минут)
    to_delete = [h for h, t in SEEN_MESSAGES_CACHE.items() if now - t > 2700]
    for h in to_delete:
        del SEEN_MESSAGES_CACHE[h]

    if text_hash in SEEN_MESSAGES_CACHE:
        return True

    SEEN_MESSAGES_CACHE[text_hash] = now
    return False


def setup_parser(client: TelegramClient, bot: Bot) -> None:
    """Регистрирует обработчик входящих сообщений Telethon с умной оптимизацией."""

    @client.on(events.NewMessage(incoming=True))
    async def handler(event: events.NewMessage.Event) -> None:
        raw_text = event.raw_text
        if not raw_text or len(raw_text.strip()) < 15:
            return

        # Игнорируем личные диалоги
        if event.is_private:
            return

        # --- 1. ФИЛЬТР СВЕЖЕСТИ (Защита от спама старыми сообщениями при реконнекте) ---
        msg_date = getattr(event, "date", None)
        if msg_date:
            now_utc = datetime.now(timezone.utc)
            if (now_utc - msg_date).total_seconds() > 7200:
                return

        try:
            chat = await event.get_chat()
            chat_title = getattr(chat, "title", "чат")
        except Exception:
            chat = None
            chat_title = "чат"

        # Увеличиваем счетчик входящих сообщений
        PARSER_STATS["incoming_total"] += 1
        PARSER_STATS["last_message_at"] = datetime.now().strftime("%H:%M:%S")
        PARSER_STATS["last_chat_title"] = str(chat_title)

        if PARSER_STATS["incoming_total"] % 25 == 1:
            logger.info("📡 [Parser] Прослушка активна. Получено сообщений: %d (последнее из «%s»)", PARSER_STATS["incoming_total"], chat_title)

        text_lower = raw_text.lower()

        # --- 2. АНТИ-БАЙТ: Блокировка рекламы ботов, переходников и паразитных каналов ---
        if any(bait in text_lower for bait in PARASITIC_BOT_TRIGGERS):
            return

        # --- 3. АНТИ-РЕЗЮМЕ: Отсеиваем саморекламу фрилансеров и партнерки ---
        if is_seller_or_resume_post(raw_text):
            return

        # --- 4. ПРОВЕРКА МИНИМАЛЬНОЙ ДЛИНЫ ---
        clean_desc = re.sub(r"#\w+", "", raw_text)
        clean_desc = re.sub(r"https?://\S+", "", clean_desc).strip()
        if len(clean_desc) < 12:
            return

        # --- 5. ФИЛЬТР ЗАКАЗЧИКА (BUYER TRIGGERS) ---
        has_buyer_trigger = any(trigger in text_lower for trigger in config.BUYER_TRIGGERS)
        if not has_buyer_trigger:
            return

        # --- 6. ДЕДУПЛИКАЦИЯ ---
        if is_duplicate_message(raw_text):
            return

        # --- 7. ПОЛУЧЕНИЕ ОТПРАВИТЕЛЯ И ПРОВЕРКА ПРЯМОГО КОНТАКТА ---
        try:
            sender = await event.get_sender()
        except Exception:
            sender = None

        client_username, client_user_id, contact_display = extract_direct_client_contact(raw_text, sender, chat)
        if not contact_display:
            return

        # --- 8. ПОЛУЧЕНИЕ АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ ИЗ БД ---
        active_users = await db.get_all_users_with_keywords()
        if not active_users:
            return

        sender_first_name = getattr(sender, "first_name", "") if isinstance(sender, User) else ""
        msg_link = generate_message_link(chat, event.id)

        safe_chat_title = html.escape(str(chat_title))
        safe_text = html.escape(raw_text.strip())

        # Компактный предпросмотр (до 850 символов) для легкой читаемости
        if len(safe_text) > 850:
            safe_text = safe_text[:850] + "... <i>(далее в источнике)</i>"

        now = time.time()

        # Формируем кликабельный контакт заказчика для текста
        if client_username:
            contact_html = f'<a href="https://t.me/{client_username}">@{html.escape(client_username)}</a>'
        elif client_user_id:
            contact_html = f'<a href="tg://user?id={client_user_id}">{html.escape(contact_display)}</a>'
        else:
            contact_html = f'<b>{html.escape(contact_display)}</b>'

        # Формируем кнопки перехода (гарантированно валидные URL)
        action_buttons = []
        if client_username:
            action_buttons.append(
                InlineKeyboardButton(
                    text="💬 Написать заказчику",
                    url=f"https://t.me/{client_username}",
                )
            )
        if msg_link and str(msg_link).startswith("http"):
            action_buttons.append(
                InlineKeyboardButton(
                    text="🔗 Исходный пост",
                    url=str(msg_link),
                )
            )

        reply_markup_pro = InlineKeyboardMarkup(inline_keyboard=[action_buttons]) if action_buttons else None

        # --- 9. МАТЧИНГ С НАСТРОЙКАМИ ПОЛЬЗОВАТЕЛЕЙ ---
        for user in active_users:
            user_id = user["user_id"]
            is_admin_user = (user_id == config.ADMIN_ID) or (user_id == 1795524760) or db.is_admin(user_id)
            is_pro = 1 if is_admin_user else user.get("is_pro", 0)
            keywords_raw = user.get("keywords") or ""
            stop_words_raw = user.get("stop_words") or ""
            active_cats_raw = user.get("active_categories") or ""

            # Защита от флуда в ЛС пользователю (не чаще 1 уведомления в 1.5 секунды)
            last_sent = USER_LAST_NOTIFICATION.get(user_id, 0)
            if now - last_sent < 1.5:
                continue

            user_keywords = [k.strip().lower() for k in keywords_raw.split(",") if k.strip()]
            user_cats = [c.strip() for c in active_cats_raw.split(",") if c.strip()]
            
            # Если у пользователя (или админа) не выбраны фильтры — по умолчанию слушаем ВСЕ категории фриланса,
            # чтобы заказы летели в чат сразу, как и положено!
            if user_cats:
                cat_keywords = categories.get_keywords_for_categories(user_cats)
                search_cats = user_cats
            else:
                cat_keywords = categories.ALL_KEYWORDS_CACHE
                search_cats = list(categories.ALL_CATEGORIES_DICT.keys())

            all_search_keywords = list(dict.fromkeys(user_keywords + cat_keywords))
            user_stop_words = [s.strip().lower() for s in stop_words_raw.split(",") if s.strip()]

            # Проверка наличия ключевых слов с учетом морфологии и границ слов
            matched_keywords = [kw for kw in all_search_keywords if categories.match_keyword_in_text(kw, text_lower)]
            if not matched_keywords:
                continue

            # Проверка отсутствия минус-слов
            if any(categories.match_keyword_in_text(sw, text_lower) for sw in user_stop_words):
                continue

            PARSER_STATS["leads_matched"] += 1

            # Определение наиболее релевантной категории
            cat_match = categories.find_matched_category_info(text_lower, search_cats)
            category_badge = f"🎯 <b>Категория:</b> {cat_match[0]}\n" if cat_match else ""

            # --- 10. КАРТОЧКА ЗАКАЗА ДЛЯ ПОЛЬЗОВАТЕЛЯ ---
            if is_pro == 1:
                # === PRO ТАРИФ (ВСЕ КОНТАКТЫ ОТКРЫТЫ) ===
                notification_text = (
                    f"💼 <b>Новый заказ</b> <code>[PRO]</code>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{category_badge}"
                    f"📍 <b>Источник:</b> <i>{safe_chat_title}</i>\n"
                    f"👤 <b>Заказчик:</b> {contact_html}\n\n"
                    f"📝 <b>Текст заявки:</b>\n"
                    f"<blockquote>{safe_text}</blockquote>"
                )
                user_markup = reply_markup_pro

            else:
                # === FREE ТАРИФ ===
                masked_contact = mask_contact(client_username, sender_first_name)

                notification_text = (
                    f"💼 <b>Новый заказ</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{category_badge}"
                    f"📍 <b>Источник:</b> <i>{safe_chat_title}</i>\n"
                    f"👤 <b>Заказчик:</b> <code>{html.escape(masked_contact)}</code> 🔒\n\n"
                    f"📝 <b>Текст заявки:</b>\n"
                    f"<blockquote>{safe_text}</blockquote>"
                )

                user_markup = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔓 Открыть контакт (PRO от 99 ₽)",
                                callback_data="btn_buy_pro",
                            )
                        ]
                    ]
                )

            # Отправка уведомления
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=notification_text,
                    reply_markup=user_markup,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                USER_LAST_NOTIFICATION[user_id] = time.time()
                await db.increment_leads_count(user_id)
                PARSER_STATS["leads_delivered"] += 1
                PARSER_STATS["last_lead_at"] = datetime.now().strftime("%H:%M:%S")
                logger.info("🎯 [Parser] Заказ #%d отправлен пользователю %s: «%s» (ключи: %s)", PARSER_STATS["leads_delivered"], user_id, safe_chat_title, matched_keywords)
            except Exception as send_err:
                logger.warning(f"Ошибка отправки пользователю {user_id}: {send_err}")
