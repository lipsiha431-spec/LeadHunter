"""
chat_manager.py — Модуль управления базой целевых чатов и каналов Telegram.
Позволяет администратору добавлять, удалять, искать, импортировать и экспортировать чаты.
"""

import os
import re
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFIED_CHATS_FILE = os.path.join(BASE_DIR, "chats_verified.txt")
LIST_CHATS_FILE = os.path.join(BASE_DIR, "chats_list.txt")


def clean_chat_identifier(raw: str) -> str:
    """Очищает строку и возвращает чистый юзернейм или ссылку."""
    s = raw.strip()
    if s.startswith("#"):
        return ""
    # Отсекаем комментарии
    s = s.split("#")[0].strip()
    # Убираем пробелы
    s = s.replace(" ", "")
    return s


def extract_username_or_link(raw: str) -> str:
    """Извлекает username (без @) или t.me-ссылку."""
    clean = clean_chat_identifier(raw)
    if not clean:
        return ""
    # https://t.me/joinchat/... или t.me/+...
    if "t.me/+" in clean or "joinchat" in clean:
        return clean
    # t.me/username -> username
    m = re.search(r"t\.me/([a-zA-Z0-9_]+)", clean)
    if m:
        return m.group(1).lower()
    if clean.startswith("@"):
        return clean[1:].lower()
    return clean.lower()


def get_all_chats() -> list[str]:
    """Возвращает список всех очищенных ссылок/юзернеймов чатов из базы."""
    if not os.path.exists(VERIFIED_CHATS_FILE):
        return []

    results = []
    seen = set()
    with open(VERIFIED_CHATS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            c = clean_chat_identifier(line)
            if not c:
                continue
            key = extract_username_or_link(c)
            if key and key not in seen:
                seen.add(key)
                results.append(c)
    return results


def add_chat(raw_chat: str, comment: str = "") -> tuple[bool, str]:
    """Добавляет новый чат в базу."""
    c = clean_chat_identifier(raw_chat)
    if not c:
        return False, "Неверный формат чата."

    key = extract_username_or_link(c)
    if not key:
        return False, "Не удалось распознать ссылку или юзернейм чата."

    # Проверяем наличие
    existing = get_all_chats()
    existing_keys = {extract_username_or_link(x) for x in existing}
    if key in existing_keys:
        return False, f"Чат <code>{key}</code> уже есть в базе."

    # Формируем строку
    formatted_line = c if c.startswith("http") or c.startswith("@") else f"https://t.me/{c}"
    if comment:
        formatted_line = f"{formatted_line}  # {comment.strip()}"

    with open(VERIFIED_CHATS_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{formatted_line}")

    if os.path.exists(LIST_CHATS_FILE):
        with open(LIST_CHATS_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{formatted_line}")

    return True, f"✅ Чат <b>{key}</b> успешно добавлен в мониторинг!"


def remove_chat(raw_chat: str) -> tuple[bool, str]:
    """Удаляет чат из базы."""
    key = extract_username_or_link(raw_chat)
    if not key:
        return False, "Не удалось распознать юзернейм или ссылку."

    if not os.path.exists(VERIFIED_CHATS_FILE):
        return False, "Файл базы чатов не найден."

    found = False
    new_lines = []
    with open(VERIFIED_CHATS_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            c = clean_chat_identifier(line)
            if c and extract_username_or_link(c) == key:
                found = True
                continue
            new_lines.append(line)

    if not found:
        return False, f"Чат <code>{key}</code> не найден в базе."

    with open(VERIFIED_CHATS_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    if os.path.exists(LIST_CHATS_FILE):
        list_lines = []
        with open(LIST_CHATS_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                c = clean_chat_identifier(line)
                if c and extract_username_or_link(c) == key:
                    continue
                list_lines.append(line)
        with open(LIST_CHATS_FILE, "w", encoding="utf-8") as f:
            f.writelines(list_lines)

    return True, f"✅ Чат <b>{key}</b> успешно удален из базы мониторинга."


def search_chats(query: str) -> list[str]:
    """Ищет чаты в базе по подстроке."""
    q = query.strip().lower()
    if not q:
        return []
    all_chats = get_all_chats()
    return [c for c in all_chats if q in c.lower()]


def import_chats_from_text(raw_text: str) -> tuple[int, int]:
    """Пакетный импорт чатов из текста или файла."""
    existing_keys = {extract_username_or_link(x) for x in get_all_chats()}
    added_lines = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Поиск ссылок или юзернеймов в строке
        matches = re.findall(r"(?:https?://t\.me/[a-zA-Z0-9_+/]+|@[a-zA-Z0-9_]+)", line)
        for m in matches:
            key = extract_username_or_link(m)
            if key and key not in existing_keys:
                existing_keys.add(key)
                formatted = m if m.startswith("http") else f"https://t.me/{m.lstrip('@')}"
                added_lines.append(formatted)

    if added_lines:
        with open(VERIFIED_CHATS_FILE, "a", encoding="utf-8") as f:
            for l in added_lines:
                f.write(f"\n{l}")

        if os.path.exists(LIST_CHATS_FILE):
            with open(LIST_CHATS_FILE, "a", encoding="utf-8") as f:
                for l in added_lines:
                    f.write(f"\n{l}")

    return len(added_lines), len(existing_keys)
