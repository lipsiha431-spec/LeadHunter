"""
config.py — Модуль конфигурации проекта Telegram SaaS-парсера.
Загружает переменные окружения, реквизиты оплаты (СБП, Карты, Крипта, Stars)
и задает базовые триггеры для фильтрации лидов.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные из файла .env рядом с config.py
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    load_dotenv()

def _get_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is not None and val.strip().isdigit():
        return int(val.strip())
    return default

# --- Настройки авторизации Telethon (Client API) ---
API_ID: int = _get_int("API_ID", 30968277)
API_HASH: str = (os.getenv("API_HASH") or "2e621b790f02875a3ea72b245a909551").strip()

# Имя файла сессии для Telethon или строковая сессия (для серверов/контейнеров)
SESSION_NAME: str = os.getenv("SESSION_NAME", "lead_parser_session")
TELEGRAM_STRING_SESSION: str = (
    os.getenv("TELEGRAM_STRING_SESSION")
    or os.getenv("SESSION_STRING")
    or "1ApWapzMBu7P0dt91YBB0-fkOPN85auNv626Y_Cs6NpOrK3RlMWGIfUDkjXPcJfjfz-ehrUrLTJjf9p3j1ZuPu8GdTkcDjrmmQjrTxyACBl1CtqCC6Ou1mW6hVbZq1lKbv71sC1YLRPrTiCZFe2LsP2IQ8E5TO-ZFWv1C0avSeK-LaAZc7NWFshYFNOeTxxI0VWaCKnfgDWKkzDl7K0ww4UxUzezxdbl7_ysZMjDVazPP2Xk8R-FLVRC07baSQwLrZ0_R2osxMfdrulwGgRx1PHevTWOjrifRKchrIAztClzWQVLiup_dp44g4616GgagCvXVYACuKkOBDX4s8haEmSATkWFjy2k="
).strip()

# --- Настройки Telegram-бота (aiogram) ---
BOT_TOKEN: str = (os.getenv("BOT_TOKEN") or "8870871677:AAFz3dqgPv3ikwUDevfhSc2_gK0--tJU2ks").strip()

# Telegram ID администратора (узнать свой ID можно в боте @userinfobot)
ADMIN_ID: int = _get_int("ADMIN_ID", 1795524760)

# --- Настройки базы данных ---
DB_NAME: str = os.getenv("DB_NAME", "leads.db")

# --- Опциональные настройки прокси ---
USE_PROXY: bool = os.getenv("USE_PROXY", "false").lower() in ("true", "1", "yes")
PROXY_TYPE: str = os.getenv("PROXY_TYPE", "socks5").lower()
PROXY_HOST: str = os.getenv("PROXY_HOST", "127.0.0.1")
PROXY_PORT: int = _get_int("PROXY_PORT", 10808)
PROXY_USER: str = os.getenv("PROXY_USER", "")
PROXY_PASS: str = os.getenv("PROXY_PASS", "")

# --- РЕКВИЗИТЫ ОПЛАТЫ (СБП, КАРТЫ, КРИПТА) ---
PAY_SBP_PHONE: str = os.getenv("PAY_SBP_PHONE", "+7 (999) 000-00-00")
PAY_SBP_BANK: str = os.getenv("PAY_SBP_BANK", "Т-Банк (Тинькофф) / Сбер")
PAY_CARD_NUMBER: str = os.getenv("PAY_CARD_NUMBER", "2200 7000 0000 0000")

# Криптовалюта
PAY_CRYPTO_USDT_TRC20: str = os.getenv("PAY_CRYPTO_USDT_TRC20", "TXxxYourUsdtTrc20AddressHerexxxxxxxx")
PAY_CRYPTO_TON: str = os.getenv("PAY_CRYPTO_TON", "UQYourTonWalletAddressHerexxxxxxxxxxxxxxxxx")
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "paniicca")

# --- Настройки Telegram Mini App (B2B Lead Generator) ---
MINI_APP_PORT: int = _get_int("PORT", _get_int("MINI_APP_PORT", 8080))
MINI_APP_HOST: str = os.getenv("MINI_APP_HOST", "0.0.0.0")
_raw_url = os.getenv("MINI_APP_URL") or os.getenv("BOTHOST_DOMAIN") or os.getenv("DOMAIN") or os.getenv("APP_URL") or "https://leadhunter.bothost.tech"
if _raw_url and not _raw_url.startswith("http"):
    _raw_url = f"https://{_raw_url}"
MINI_APP_URL: str = _raw_url
GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

# --- Базовый список триггер-слов покупателей / заказчиков ---
BUYER_TRIGGERS: list[str] = [
    "ищу",
    "нужен",
    "нужна",
    "нужны",
    "нужно",
    "надо",
    "требуется",
    "требуются",
    "кто сделает",
    "кто может",
    "посоветуйте",
    "подскажите",
    "ищем",
    "ищется",
    "заказ",
    "бюджет",
    "тз",
    "оплата",
    "проект",
    "задача",
    "стоимость",
    "дедлайн",
    "сделать",
    "разработка",
    "создание",
    "вакансия",
    "исполнитель",
    "специалист",
    "разработчик",
    "дизайнер",
    "верстальщик",
    "программист",
    "копирайтер",
    "оплачивается",
    "ставка",
    "руб",
    "рублей",
    "rub",
    "usdt",
    "$",
    "₽",
    "в лс",
    "в личку",
    "писать в лс",
    "отклик",
    "ищу человека",
    "ищу спеца",
]
