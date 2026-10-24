"""
prototype.py — Расширенный Telegram-парсер лидов и заказов с аккаунта.
Пересылает найденные заказы в «Избранное» (Saved Messages) с карточкой, файлами,
анти-спамом и сохранением истории в CSV.
"""

import sys
import os
import csv
import html
import hashlib
from datetime import datetime
from collections import deque
from telethon import TelegramClient, events
from telethon.tl.types import User, Channel, Chat

# Принудительно включаем UTF-8 для вывода в консоль Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ==========================================
# 🔑 НАСТРОЙКИ АВТОРИЗАЦИИ TELEGRAM
# ==========================================
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
SESSION_NAME = os.getenv("SESSION_NAME", "lead_hunter_session")
CSV_FILE = "leads_history.csv"

# ==========================================
# 🎯 НАСТРОЙКИ ФИЛЬТРОВ И КЛЮЧЕВЫХ СЛОВ
# ==========================================
# 1. Триггеры заказчика (отсекают спам и резюме)
BUYER_TRIGGERS = [
    "ищу", "нужен", "нужна", "нужны", "требуется", "требуются",
    "кто сделает", "посоветуйте", "подскажите", "ищем", "заказ",
    "бюджет", "тз", "оплата", "разработать", "сделать"
]

# 2. Ключевые слова по вашей специальности
KEYWORDS = [
    "сайт", "лендинг", "бот", "telegram бот", "дизайн", "python",
    "копирайтер", "верстка", "таргет", "парсинг", "парсер",
    "скрипт", "разработка", "веб", "frontend", "backend", "логотип"
]

# 3. Минус-слова (сообщения с этими словами отсекаются)
STOP_WORDS = [
    "курс", "обучение", "бесплатно", "помогу", "ищу работу", "резюме", "стажировка"
]

# Кэш последних 200 сообщений для защиты от дублей и флуда
recent_hashes = deque(maxlen=200)


def init_csv():
    """Создает CSV-файл для накопления истории лидов, если его еще нет."""
    if not os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([
                    "Дата и время",
                    "Источник (Чат)",
                    "Имя автора",
                    "Юзернейм",
                    "Ключевое слово",
                    "Текст заказа",
                    "Ссылка на сообщение",
                    "Наличие вложения"
                ])
        except Exception as e:
            print(f"⚠️ Ошибка инициализации CSV: {e}")


def save_to_csv(chat_title: str, author_name: str, username: str, keywords: str, text: str, link: str, has_media: bool):
    """Добавляет пойманный лид в CSV-файл."""
    try:
        with open(CSV_FILE, mode="a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            # Очищаем переносы строк для красивого открытия в Excel
            clean_text = " ".join(text.split())
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                chat_title,
                author_name,
                f"@{username}" if username else "",
                keywords,
                clean_text,
                link or "",
                "Да" if has_media else "Нет"
            ])
    except Exception as e:
        print(f"⚠️ Ошибка записи в CSV: {e}")


def get_text_hash(text: str) -> str:
    """Генерирует уникальный хэш по первым 120 символам для анти-дублирования."""
    normalized = " ".join(text.lower().split())[:120]
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def generate_message_link(chat_obj: any, event_id: int) -> str:
    """Формирует прямую кликабельную ссылку на исходное сообщение."""
    if not chat_obj:
        return ""

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

    return ""


# Инициализация клиента Telethon
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


@client.on(events.NewMessage(incoming=True))
async def lead_handler(event: events.NewMessage.Event):
    """Основной обработчик входящих сообщений."""
    try:
        # 1. Игнорируем ЛС и само «Избранное», чтобы не зацикливать скрипт
        if event.is_private:
            return

        # 2. Извлекаем текст (включая подписи к медиа/файлам)
        raw_text = event.raw_text or event.message.message or ""
        if not raw_text.strip():
            return

        text_lower = raw_text.lower()

        # 3. Фильтр 1: Проверяем наличие триггеров заказчика
        has_buyer_trigger = any(trigger in text_lower for trigger in BUYER_TRIGGERS)
        if not has_buyer_trigger:
            return

        # 4. Фильтр 2: Проверяем наличие ключевых слов
        matched_keywords = [kw for kw in KEYWORDS if kw in text_lower]
        if not matched_keywords:
            return

        # 5. Фильтр 3: Проверяем минус-слова
        has_stop_word = any(sw in text_lower for sw in STOP_WORDS)
        if has_stop_word:
            return

        # 6. Защита от дублей (Анти-флуд)
        text_hash = get_text_hash(raw_text)
        if text_hash in recent_hashes:
            return
        recent_hashes.append(text_hash)

        # 7. Получаем данные об авторе (игнорируем ботов)
        sender = await event.get_sender()
        if getattr(sender, "bot", False):
            return

        chat = await event.get_chat()
        chat_title = getattr(chat, "title", "Группа/Канал")

        sender_id = getattr(sender, "id", None)
        sender_first = getattr(sender, "first_name", "") or ""
        sender_last = getattr(sender, "last_name", "") or ""
        sender_full_name = f"{sender_first} {sender_last}".strip() or "Заказчик"
        sender_username = getattr(sender, "username", None)

        msg_link = generate_message_link(chat, event.id)
        has_media = bool(event.message.media)

        # 8. Формируем кликабельные ссылки и строки карточки
        safe_kw = html.escape(", ".join(matched_keywords))
        safe_chat = html.escape(str(chat_title))
        safe_author = html.escape(sender_full_name)
        safe_text = html.escape(raw_text.strip())

        # Ссылка на чат/сообщение
        if msg_link:
            chat_line = f'<a href="{msg_link}">{safe_chat}</a>'
        else:
            chat_line = safe_chat

        # Строка автора: Имя + @username + Вечная ссылка tg://user?id=
        author_parts = [f"<b>{safe_author}</b>"]
        if sender_username:
            author_parts.append(f"(@{sender_username})")
        if sender_id:
            author_parts.append(f'• <a href="tg://user?id={sender_id}">Открыть профиль</a>')
        author_line = " ".join(author_parts)

        # Пометка о вложении
        media_notice = "📎 <b>К заказу прикреплен файл/ТЗ</b>\n" if has_media else ""

        # Учитываем лимит Telegram: подпись к медиа максимум 1024 символа
        max_preview_len = 800 if has_media else 3200
        if len(safe_text) > max_preview_len:
            display_text = safe_text[:max_preview_len] + "... <i>(текст сокращен)</i>"
        else:
            display_text = safe_text

        # 9. Итоговая красивая карточка лида
        card_text = (
            f"🎯 <b>Ключевое слово:</b> <code>{safe_kw}</code>\n"
            f"📍 <b>Источник:</b> {chat_line}\n"
            f"👤 <b>Автор:</b> {author_line}\n"
            f"{media_notice}\n"
            f"📄 <b>Текст заказа:</b>\n"
            f"<blockquote>{display_text}</blockquote>"
        )

        # 10. Отправка в «Избранное» (Saved Messages)
        if has_media:
            await client.send_file(
                "me",
                file=event.message.media,
                caption=card_text,
                parse_mode="html",
            )
        else:
            await client.send_message(
                "me",
                card_text,
                parse_mode="html",
                link_preview=False,
            )

        # 11. Логирование в консоль и CSV
        curr_time = datetime.now().strftime("%H:%M:%S")
        print(f"[{curr_time}] 🚀 НАЙДЕН ЗАКАЗ! Чат: {chat_title} | Ключевые слова: {', '.join(matched_keywords)}")
        save_to_csv(chat_title, sender_full_name, sender_username, ", ".join(matched_keywords), raw_text, msg_link, has_media)

    except Exception as e:
        # Защита от любых непредвиденных сбоев
        print(f"⚠️ Ошибка при обработке сообщения: {e}")


def main():
    init_csv()

    print("=" * 65)
    print("🚀 TELEGRAM LEAD HUNTER PROTOTYPE")
    print("=" * 65)
    print(f"• Триггеров заказчика: {len(BUYER_TRIGGERS)}")
    print(f"• Ключевых слов в фильтре: {len(KEYWORDS)}")
    print(f"• Минус-слов исключения: {len(STOP_WORDS)}")
    print(f"• История сохраняется в: {os.path.abspath(CSV_FILE)}")
    print("• Назначение: отправка лидов и файлов в 'Избранное' ('me')")
    print("=" * 65)
    print("Ожидание новых заказов во всех чатах... (Нажмите Ctrl+C для выхода)\n")

    client.start()
    client.run_until_disconnected()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПарсер остановлен.")
